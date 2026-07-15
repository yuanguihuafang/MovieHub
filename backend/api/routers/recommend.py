"""
backend/api/routers/recommend.py

智能推荐接口（对应前端"推荐"页面）。

- POST /api/recommend

该接口会综合：
- 收藏（favorites）
- 已看过（watched）
- 浏览历史（history）
- 用户输入偏好（user_input）
并调用 recommender.recommend_for_user 生成推荐结果。

第三路「TMDB 最近/即将上映」候选池 ``recent_pool`` 的构建与说明见
``backend.recommender.recent_tmdb_pool``。
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.db.database import (
    fav_list,
    history_get_movies_with_count,
    notification_add,
    rec_log_add,
    user_get,
    watched_list,
)
from backend.recommender.recommend import (
    generate_recommend_card_blurbs,
    generate_recommend_explain,
    generate_recommend_summary,
    recommend_for_user,
)
from backend.services.redis_cache import get as cache_get, set as cache_set
from backend.recommender.recent_tmdb_pool import recent_pool_for_recommend
from backend.schemas.recommend import (
    RecommendCardBlurbsJobRequest,
    RecommendExplainJobRequest,
    RecommendRequest,
    RecommendSummaryJobRequest,
)
router = APIRouter(tags=["recommend"])

_RECOMMEND_JOB_STEPS = [
    "分解偏好（大模型）",
    "构建种子与偏好约束",
    "读取反馈信号（喜欢/不喜欢/屏蔽）",
    "片库检索（RAG/向量检索）",
    "知识图谱召回（Multi_MoE）",
    "合并排序（初榜）",
    "大模型审核过滤（通义）",
    "大模型定榜挑选（图谱/片库）",
    "定榜后补全卡片（海报/简介等）",
]

_jobs_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def _job_set(job_id: str, patch: dict) -> None:
    with _jobs_lock:
        cur = _jobs.get(job_id)
        if not cur:
            return
        cur.update(patch)


def _job_get(job_id: str) -> dict | None:
    with _jobs_lock:
        j = _jobs.get(job_id)
        return dict(j) if j else None


def _inference_meta_for_admin_log(result: dict) -> dict[str, Any]:
    """供管理后台展示的推理流水线、图谱 Multi_MoE 元信息、种子与 LLM 调用摘要。"""
    pl = (result.get("pipeline") or [])[:50]
    clean_pipeline: list[dict[str, Any]] = []
    for step in pl:
        if not isinstance(step, dict):
            continue
        clean_pipeline.append(
            {
                "id": step.get("id"),
                "title": step.get("title"),
                "status": step.get("status"),
                "call_kind": step.get("call_kind"),
                "message": (str(step.get("message") or ""))[:2500],
                "elapsed_ms": int(step.get("elapsed_ms") or 0),
            }
        )
    kg_meta = result.get("kg_model_meta")
    if not isinstance(kg_meta, dict):
        kg_meta = {}
    else:
        keep = (
            "method",
            "relations_used",
            "preferred_relations",
            "relation_weights",
            "genre_boost",
            "max_relations",
            "note",
            "flow_summary",
            "candidate_stage",
        )
        kg_meta = {k: kg_meta[k] for k in keep if k in kg_meta}
        if kg_meta.get("note"):
            kg_meta["note"] = str(kg_meta["note"])[:4000]
    seeds = result.get("seed_movies") or []
    if not isinstance(seeds, list):
        seeds = []
    seeds = seeds[:40]
    gh = result.get("genre_hints") or []
    if not isinstance(gh, list):
        gh = []
    llm_inv = result.get("llm_invocations") or []
    if not isinstance(llm_inv, list):
        llm_inv = []
    llm_inv = llm_inv[:50]
    pref = result.get("preference_decompose")
    if not isinstance(pref, dict):
        pref = {}
    peer_raw = result.get("peer_fav_movies") or []
    peer_clean: list[dict[str, Any]] = []
    if isinstance(peer_raw, list):
        for x in peer_raw[:40]:
            if not isinstance(x, dict) or not x.get("name"):
                continue
            peer_clean.append(
                {
                    "name": str(x.get("name") or "")[:256],
                    "display": str(x.get("display") or x.get("name") or "")[:256],
                    "genres": str(x.get("genres") or "")[:200],
                    "weight": float(x.get("weight") or 0.0),
                }
            )
    return {
        "pipeline": clean_pipeline,
        "kg_model_meta": kg_meta,
        "seed_movies": seeds,
        "genre_hints": gh,
        "llm_invocations": llm_inv,
        "preference_decompose": pref,
        "peer_fav_movies": peer_clean,
    }


def _recommend_snapshot_payload(result: dict, user_input: str) -> dict[str, Any]:
    """消息中心「推荐快照」：与推荐页定榜清单 + 图谱/检索候选一致（JSON 存 payload）。"""
    cards: list[dict[str, str]] = []
    for m in (result.get("movies") or [])[:48]:
        if not isinstance(m, dict):
            continue
        nm = str(m.get("name") or "")
        if not nm:
            continue
        disp = str(m.get("display") or nm)
        cards.append(
            {
                "name": nm,
                "display": disp,
                "source": str(m.get("source") or ""),
            }
        )
    kg = [str(x) for x in (result.get("kg_movies") or [])[:80]]
    rag: list[str] = []
    for x in (result.get("rag_movies") or [])[:40]:
        if isinstance(x, dict) and x.get("name"):
            rag.append(str(x["name"]))
    rt = str(result.get("recommend_text") or "")
    if len(rt) > 100_000:
        rt = rt[:100_000] + "\n…(正文过长已截断)"
    return {
        "snapshot_version": 1,
        "recommend_text": rt,
        "final_movies": cards,
        "kg_movies": kg,
        "rag_movies": rag,
        "elapsed_ms": int(result.get("elapsed_ms") or 0),
        "user_input": (user_input or "")[:1200],
    }


def _rec_log_from_result(user_id: int, user_input: str, result: dict | None) -> None:
    """推荐成功后写入 recommend_logs（异步 job 与同步接口共用）。"""
    if not result or not result.get("success"):
        return
    try:
        final_names: list[str] = []
        for m in (result.get("movies") or [])[:60]:
            if isinstance(m, dict) and m.get("name"):
                final_names.append(str(m["name"]))
        rec_log_add(
            int(user_id),
            user_input or "",
            list(result.get("kg_movies") or []),
            [
                x.get("name")
                for x in (result.get("rag_movies") or [])
                if isinstance(x, dict) and x.get("name")
            ],
            final_movies=final_names,
            recommend_text=str(result.get("recommend_text") or ""),
            elapsed_ms=int(result.get("elapsed_ms") or 0),
            inference_meta=_inference_meta_for_admin_log(result),
        )
    except Exception as ex:
        print(f"⚠️  [推荐] 推荐日志记录失败: {str(ex)[:100]}")
    try:
        pl = _recommend_snapshot_payload(result, user_input or "")
        n_final = len(pl.get("final_movies") or [])
        ms = int(result.get("elapsed_ms") or 0)
        detail = f"本次共推荐 {n_final} 部"
        if ms > 0:
            detail += f"，耗时 {ms / 1000.0:.1f}s"
        notification_add(
            int(user_id),
            "recommend_done",
            "推荐已完成",
            detail[:600],
            pl,
        )
    except Exception as ex:
        print(f"⚠️  [推荐] 通知发送失败: {str(ex)[:100]}")


def _create_job(payload: dict, *, steps: list[str] | None = None, text: str = "") -> str:
    job_id = uuid.uuid4().hex
    now = time.time()
    st = list(steps) if steps else list(_RECOMMEND_JOB_STEPS)
    init_text = text or (st[0] if st else "")
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "created_at": now,
            "running": True,
            "done": False,
            "error": "",
            "step": 0,
            "text": init_text,
            "steps": st,
            "result": None,
            "payload": payload,
            "phase": "running",
            "filter_pending": False,
        }
    return job_id


def _run_job(job_id: str) -> None:
    job = _job_get(job_id)
    if not job:
        return
    payload = job.get("payload") or {}
    try:
        user_id = int(payload.get("user_id") or 0)
        user_input = str(payload.get("user_input") or "")
        selected_favs = list(payload.get("selected_favorites") or [])
        watched_rows = payload.get("watched_rows") or []
        history_movies = payload.get("history_movies") or []
        history_genres = payload.get("history_genres") or []
        # 勿把 None 改成 []：None 表示未开启「追加最近上映」，[] 表示已开启但本地缓存无片源
        recent_pool = payload.get("recent_pool")
        topk_kg = int(payload.get("topk_kg") or 6)
        topk_rag = int(payload.get("topk_rag") or 10)
        fast_llm = bool(payload.get("fast_llm"))
        exclude_titles = list(payload.get("exclude_titles") or [])

        def progress_cb(step: int, text: str):
            step = int(step or 0)
            if step < 0:
                step = 0
            if step >= len(_RECOMMEND_JOB_STEPS):
                step = len(_RECOMMEND_JOB_STEPS) - 1 if _RECOMMEND_JOB_STEPS else 0
            _job_set(job_id, {"step": step, "text": text or (_RECOMMEND_JOB_STEPS[step] if _RECOMMEND_JOB_STEPS else "")})

        result = recommend_for_user(
            user_id=user_id,
            user_input=user_input or "根据我的收藏和已看片单推荐",
            favorite_movies=selected_favs,
            watched_items=watched_rows,
            history_genres=history_genres,
            history_movies=history_movies,
            recent_pool=recent_pool,
            topk_kg=topk_kg,
            topk_rag=topk_rag,
            with_llm_explain=bool(payload.get("with_llm_explain")),
            fast_llm=fast_llm,
            progress_cb=progress_cb,
            phased_cards=False,
            defer_optional_llm=False,
            on_cards_ready=None,
            exclude_display_titles=exclude_titles,
        )

        _rec_log_from_result(user_id, user_input, result)

        # 推荐成功，存入缓存（1 小时）
        ck = str(payload.get("cache_key") or "")
        if ck and result and result.get("success"):
            cache_set(ck, result, ttl=3600)

        _job_set(
            job_id,
            {
                "result": result,
                "phase": "complete",
                "filter_pending": False,
                "done": True,
                "running": False,
                "step": len(_RECOMMEND_JOB_STEPS) - 1,
                "text": "完成",
            },
        )
    except Exception as e:
        _job_set(job_id, {"error": str(e), "done": True, "running": False})


def _run_card_blurbs_job(job_id: str) -> None:
    job = _job_get(job_id)
    if not job:
        return
    payload = job.get("payload") or {}
    try:
        user_input = str(payload.get("user_input") or "")
        movies = list(payload.get("movies") or [])
        _job_set(job_id, {"step": 0, "text": "生成清单短评（大模型）"})
        out = generate_recommend_card_blurbs(user_input=user_input, movies=movies)
        _job_set(job_id, {"result": out})
        _job_set(job_id, {"done": True, "running": False, "step": 0, "text": "完成"})
    except Exception as e:
        _job_set(job_id, {"error": str(e), "done": True, "running": False})


def _run_explain_job(job_id: str) -> None:
    job = _job_get(job_id)
    if not job:
        return
    payload = job.get("payload") or {}
    try:
        _job_set(job_id, {"step": 0, "text": "生成推荐解读（大模型）"})
        out = generate_recommend_explain(
            user_input=str(payload.get("user_input") or ""),
            favorite_movies=list(payload.get("favorite_movies") or []),
            watched_titles=list(payload.get("watched_titles") or []),
            seed_movies=list(payload.get("seed_movies") or []),
            kg_movies=list(payload.get("kg_movies") or []),
            rag_movies=list(payload.get("rag_movies") or []),
            genre_hints=list(payload.get("genre_hints") or []),
            final_titles=list(payload.get("final_titles") or []),
        )
        _job_set(job_id, {"result": out})
        _job_set(job_id, {"done": True, "running": False, "step": 0, "text": "完成"})
    except Exception as e:
        _job_set(job_id, {"error": str(e), "done": True, "running": False})


def _run_summary_job(job_id: str) -> None:
    job = _job_get(job_id)
    if not job:
        return
    payload = job.get("payload") or {}
    try:
        user_input = str(payload.get("user_input") or "")
        movies = list(payload.get("movies") or [])
        _job_set(job_id, {"step": 0, "text": "生成推荐总结（大模型）"})
        out = generate_recommend_summary(user_input=user_input, movies=movies)
        _job_set(job_id, {"result": out})
        _job_set(job_id, {"done": True, "running": False, "step": 0, "text": "完成"})
    except Exception as e:
        _job_set(job_id, {"error": str(e), "done": True, "running": False})


@router.post("/api/recommend/jobs")
async def api_recommend_create_job(body: RecommendRequest):
    """创建推荐任务（用于实时进度展示）。"""
    user_id = int(body.user_id)

    if body.selected_favorites and len(body.selected_favorites) > 0:
        selected_favs = list(body.selected_favorites)
    else:
        selected_favs = [f.get("movie_name") for f in fav_list(user_id) if f.get("movie_name")]

    watched_rows = watched_list(user_id, limit=120)
    history_movies = history_get_movies_with_count(user_id, limit=18)

    genres_result: list[dict] = []
    urow = user_get(user_id)
    if urow:
        pref = (urow.get("preferred_genres") or "").strip()
        if pref:
            genres_result.insert(0, {"genres": pref.replace(",", "/")})

    recent_pool = None
    if body.use_recent:
        recent_pool = recent_pool_for_recommend()

    excl = [str(x).strip() for x in (body.exclude_titles or []) if str(x).strip()][:40]

    # --- 缓存检查（exclude_titles 非空说明"换一批"，不走缓存）---
    use_cache = not excl
    cache_key = ""
    if use_cache:
        import hashlib
        fav_sig = ",".join(sorted(selected_favs))
        pref_sig = (urow.get("preferred_genres") or "") if urow else ""
        # key 只看 user_id + 收藏 + 偏好 + topk，不看 user_input（避免输入框内容变化导致 miss）
        raw = f"rec:{user_id}:{fav_sig}:{pref_sig}:{body.topk_kg}:{body.topk_rag}:{body.use_recent}"
        cache_key = "recommend:" + hashlib.md5(raw.encode()).hexdigest()
        cached = cache_get(cache_key)
        if cached is not None:
            # 命中缓存：创建一个立即完成的 job，直接返回缓存结果
            steps = list(_RECOMMEND_JOB_STEPS)
            job_id = _create_job({}, steps=steps)
            _job_set(job_id, {
                "result": cached,
                "phase": "complete",
                "filter_pending": False,
                "done": True,
                "running": False,
                "step": len(steps) - 1,
                "text": "完成（缓存）",
            })
            return {"success": True, "job_id": job_id}

    payload = {
        "user_id": user_id,
        "user_input": body.user_input or "",
        "selected_favorites": selected_favs,
        "watched_rows": watched_rows,
        "history_movies": history_movies,
        "history_genres": genres_result,
        "recent_pool": recent_pool,
        "topk_kg": int(body.topk_kg or 6),
        "topk_rag": int(body.topk_rag or 6),
        "with_llm_explain": bool(body.with_llm_explain),
        "fast_llm": bool(body.fast_llm),
        "exclude_titles": excl,
        "cache_key": cache_key,
    }
    job_id = _create_job(payload)
    t = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
    t.start()
    return {"success": True, "job_id": job_id}


@router.post("/api/recommend/card-blurbs/jobs")
async def api_recommend_card_blurbs_job(body: RecommendCardBlurbsJobRequest):
    payload = {"user_input": body.user_input or "", "movies": list(body.movies or [])}
    job_id = _create_job(payload, steps=["生成清单短评（大模型）"], text="生成清单短评（大模型）")
    t = threading.Thread(target=_run_card_blurbs_job, args=(job_id,), daemon=True)
    t.start()
    return {"success": True, "job_id": job_id}


@router.post("/api/recommend/summary/jobs")
async def api_recommend_summary_job(body: RecommendSummaryJobRequest):
    payload = {"user_input": body.user_input or "", "movies": list(body.movies or [])}
    job_id = _create_job(payload, steps=["生成推荐总结（大模型）"], text="生成推荐总结（大模型）")
    t = threading.Thread(target=_run_summary_job, args=(job_id,), daemon=True)
    t.start()
    return {"success": True, "job_id": job_id}


@router.post("/api/recommend/explain/jobs")
async def api_recommend_explain_job(body: RecommendExplainJobRequest):
    payload = {
        "user_input": body.user_input or "",
        "favorite_movies": list(body.favorite_movies or []),
        "watched_titles": list(body.watched_titles or []),
        "seed_movies": list(body.seed_movies or []),
        "kg_movies": list(body.kg_movies or []),
        "rag_movies": list(body.rag_movies or []),
        "genre_hints": list(body.genre_hints or []),
        "final_titles": list(body.final_titles or []),
    }
    job_id = _create_job(payload, steps=["生成推荐解读（大模型）"], text="生成推荐解读（大模型）")
    t = threading.Thread(target=_run_explain_job, args=(job_id,), daemon=True)
    t.start()
    return {"success": True, "job_id": job_id}


@router.get("/api/recommend/jobs/{job_id}")
async def api_recommend_job_status(job_id: str):
    job = _job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    # 默认不返回 payload，避免泄漏用户输入
    return {
        "success": True,
        "job_id": job_id,
        "running": bool(job.get("running")),
        "done": bool(job.get("done")),
        "error": job.get("error") or "",
        "step": int(job.get("step") or 0),
        "text": job.get("text") or "",
        "steps": job.get("steps") or [],
        "result": job.get("result"),
        "phase": job.get("phase") or "running",
        "filter_pending": bool(job.get("filter_pending", False)),
    }


@router.post("/api/recommend")
async def api_recommend(body: RecommendRequest):
    """智能推荐（结合收藏/已看过/浏览历史）"""
    user_id = int(body.user_id)

    # 使用用户选中的收藏电影；若未选中则使用全部收藏
    if body.selected_favorites and len(body.selected_favorites) > 0:
        selected_favs = list(body.selected_favorites)
    else:
        selected_favs = [f.get("movie_name") for f in fav_list(user_id) if f.get("movie_name")]

    watched_rows = watched_list(user_id, limit=120)
    history_movies = history_get_movies_with_count(user_id, limit=18)

    # 个人偏好类型（用户在 profile/preferences 保存的）
    genres_result: list[dict] = []
    urow = user_get(user_id)
    if urow:
        pref = (urow.get("preferred_genres") or "").strip()
        if pref:
            genres_result.insert(0, {"genres": pref.replace(",", "/")})

    # 可选：把"近期上映/即将上映"作为候选池，辅助大模型分解偏好
    recent_pool = None
    if body.use_recent:
        recent_pool = recent_pool_for_recommend()

    excl = [str(x).strip() for x in (body.exclude_titles or []) if str(x).strip()][:40]

    # --- 推荐结果缓存（偏好不变时 1 小时内直接返回）---
    # exclude_titles 非空说明用户点了"换一批"，不走缓存
    use_cache = not excl
    cache_key = ""
    if use_cache:
        import hashlib
        fav_sig = ",".join(sorted(selected_favs))
        pref_sig = (urow.get("preferred_genres") or "") if urow else ""
        raw = f"rec:{user_id}:{fav_sig}:{pref_sig}:{body.topk_kg}:{body.topk_rag}:{body.use_recent}"
        cache_key = "recommend:" + hashlib.md5(raw.encode()).hexdigest()
        cached = cache_get(cache_key)
        if cached is not None:
            return cached

    result = recommend_for_user(
        user_id=user_id,
        user_input=body.user_input or "根据我的收藏和已看片单推荐",
        favorite_movies=selected_favs,
        watched_items=watched_rows,
        history_genres=genres_result,
        history_movies=history_movies,
        recent_pool=recent_pool,
        topk_kg=int(body.topk_kg or 6),
        topk_rag=int(body.topk_rag or 10),
        with_llm_explain=bool(body.with_llm_explain),
        fast_llm=bool(body.fast_llm),
        defer_optional_llm=True,
        exclude_display_titles=excl,
    )

    _rec_log_from_result(user_id, body.user_input or "", result)

    if not result.get("success", False):
        raise HTTPException(status_code=500, detail=result.get("error") or "推荐失败")

    # 推荐成功，存入缓存（1 小时）
    if use_cache and cache_key:
        cache_set(cache_key, result, ttl=3600)

    return result

