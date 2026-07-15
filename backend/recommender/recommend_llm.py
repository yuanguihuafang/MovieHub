"""推荐链路中的大模型调用：偏好分解、审核、定榜、解读、总结与卡片短评。"""
import json
import os
import re
import time
import hashlib
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from backend.recommender.common import (
    ALLOWED_GENRES,
    DEFAULT_LLM_MODEL,
    MOE_RELATION_CORE,
    MOE_RELATION_FILL,
    MOVIE_NAME_MAPPING,
    PROJECT_ROOT,
    llm_client,
)

_db15k_movie_cache: Optional[list] = None


def _load_db15k_movie_list() -> list[str]:
    """加载 DB15K 电影实体短名列表（去重、排序）。"""
    global _db15k_movie_cache
    if _db15k_movie_cache is not None:
        return _db15k_movie_cache
    lex_path = os.path.join(PROJECT_ROOT, "backend", "data", "kg", "db15k_movie_lexicon.json")
    try:
        with open(lex_path, encoding="utf-8") as f:
            data = json.load(f)
        entities = sorted(set(data.get("alias_to_entity", {}).values()))
    except Exception:
        entities = []
    _db15k_movie_cache = entities
    return entities


_db15k_rag_collection = None
_db15k_rag_loaded = False


def _retrieve_db15k_movies(query: str, n_results: int = 30) -> list[str]:
    """从 DB15K 电影向量库中检索与 query 最相关的电影实体短名。"""
    global _db15k_rag_collection, _db15k_rag_loaded

    if not _db15k_rag_loaded:
        _db15k_rag_loaded = True
        try:
            import chromadb
            from backend.recommender.common import CHROMA_DIR, embedding_client, RAG_EMBEDDING_MODEL

            if not embedding_client:
                return []

            client = chromadb.PersistentClient(path=CHROMA_DIR)
            _db15k_rag_collection = client.get_collection("db15k_movies")
        except Exception:
            _db15k_rag_collection = None

    if _db15k_rag_collection is None:
        return []

    try:
        from backend.recommender.common import embedding_client, RAG_EMBEDDING_MODEL

        resp = embedding_client.embeddings.create(
            model=RAG_EMBEDDING_MODEL, input=[query]
        )
        q_vec = resp.data[0].embedding

        count = _db15k_rag_collection.count()
        n = min(n_results, count)
        if n <= 0:
            return []

        results = _db15k_rag_collection.query(
            query_embeddings=[q_vec],
            n_results=n,
            include=["documents"],
        )
        return results["ids"][0] if results.get("ids") else []
    except Exception:
        return []


def _llm_disabled() -> bool:
    raw = (os.getenv("MOVIEHUB_DISABLE_LLM") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _movie_display_key(m: dict) -> str:
    return (m.get("display") or m.get("name") or "").strip()


def _get_movie_display_name(entity_name: str) -> str:
    name_without_film = entity_name.replace("_(film)", "").replace("(film)", "")
    if name_without_film in MOVIE_NAME_MAPPING:
        return MOVIE_NAME_MAPPING[name_without_film]
    display_name = entity_name.replace("_(film)", "").replace("(film)", "")
    display_name = display_name.replace("_", " ")
    return display_name


def _json_sanitize(obj):
    """将 MySQL 等返回的 Decimal/datetime 等转为 json.dumps 可序列化类型。"""
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return int(obj) if obj == obj.to_integral_value() else float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_sanitize(x) for x in obj]
    return obj


def _parse_llm_json_obj(raw: str) -> dict:
    txt = (raw or "").strip()
    if "```" in txt:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", txt, re.I)
        if m:
            txt = m.group(1).strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        a, b = txt.find("{"), txt.rfind("}")
        if a >= 0 and b > a:
            return json.loads(txt[a : b + 1])
        raise


_LLM_STEP_MODEL_ENV = {
    "llm_decompose": "LLM_DECOMPOSE_MODEL",
    "llm_filter": "LLM_FILTER_MODEL",
    "llm_finalize": "LLM_FINALIZE_MODEL",
    "llm_explain": "LLM_EXPLAIN_MODEL",
    "llm_summary": "LLM_SUMMARY_MODEL",
    "llm_card_blurbs": "LLM_CARD_BLURB_MODEL",
    "rag_llm": "RAG_LLM_MODEL",
}

_DECOMPOSE_CACHE: dict[str, tuple[float, dict]] = {}


def _env_int(name: str, default: int, *, min_v: int = 1, max_v: int = 10000) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        v = default
    else:
        try:
            v = int(raw)
        except ValueError:
            v = default
    return max(min_v, min(max_v, v))


def _decompose_cache_ttl_s() -> int:
    return _env_int("LLM_DECOMPOSE_CACHE_TTL_SEC", 600, min_v=0, max_v=86400)


def _decompose_cache_key(payload: dict) -> str:
    raw = json.dumps(_json_sanitize(payload), ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def preference_description_from_user_input(user_input: str) -> str:
    """
    与前端 RecommendView 一致：完整串可能为「我喜欢的电影类型：…。{偏好描述}」。
    拆出用户在「偏好描述」框中填写的那段，供分解 LLM 显式参考。
    """
    s = (user_input or "").strip()
    if not s:
        return ""
    prefix = "我喜欢的电影类型："
    if not s.startswith(prefix):
        return s
    rest = s[len(prefix) :].lstrip()
    dot = rest.find("。")
    if dot == -1:
        return ""
    return rest[dot + 1 :].strip()


def _normalize_str_list(v, *, limit: int = 12) -> list[str]:
    """将 LLM 返回的字段规范为字符串数组，避免字符串被按字符迭代。"""
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    out: list[str] = []
    if isinstance(v, (list, tuple)):
        for x in v:
            sx = str(x).strip()
            if sx:
                out.append(sx)
                if len(out) >= max(1, int(limit)):
                    break
    return out


def _normalize_decompose_payload(data: dict) -> dict:
    """规范偏好分解字段类型，避免前后端 join/遍历时出现单字拆分。"""
    if not isinstance(data, dict):
        return {}
    out = dict(data)
    out["liked_genres"] = _normalize_str_list(out.get("liked_genres"), limit=20)
    out["disliked_genres"] = _normalize_str_list(out.get("disliked_genres"), limit=20)
    out["liked_movies"] = _normalize_str_list(out.get("liked_movies"), limit=24)
    out["avoid_movies"] = _normalize_str_list(out.get("avoid_movies"), limit=24)
    out["relations"] = _normalize_str_list(out.get("relations"), limit=24)
    out["constraints"] = _normalize_str_list(out.get("constraints"), limit=24)
    out["must_have_constraints"] = _normalize_str_list(
        out.get("must_have_constraints"), limit=16
    )
    out["soft_constraints"] = _normalize_str_list(out.get("soft_constraints"), limit=16)
    out["movie_entities_zh"] = _normalize_str_list(out.get("movie_entities_zh"), limit=20)

    cands = out.get("movie_entity_candidates_en")
    cand_out: dict[str, list[str]] = {}
    if isinstance(cands, dict):
        for k, v in cands.items():
            kk = str(k).strip()
            if not kk:
                continue
            vv = _normalize_str_list(v, limit=5)
            if vv:
                cand_out[kk] = vv
    out["movie_entity_candidates_en"] = cand_out

    allowed_rel = {str(x) for x in (*MOE_RELATION_CORE, *MOE_RELATION_FILL)}
    out["relations"] = [r for r in out.get("relations", []) if r in allowed_rel]
    out["query"] = str(out.get("query") or "").strip()
    return out


def public_decompose_preview(data: dict) -> dict:
    """偏好分解结果摘要（控制体积，供前端展示）。"""
    d = _normalize_decompose_payload(data)
    if not d:
        return {}
    q = d.get("query")
    return {
        "query": (str(q).strip()[:400] if q else ""),
        "liked_genres": d.get("liked_genres", [])[:12],
        "disliked_genres": d.get("disliked_genres", [])[:8],
        "liked_movies": d.get("liked_movies", [])[:12],
        "avoid_movies": d.get("avoid_movies", [])[:12],
        "relations": d.get("relations", [])[:16],
        "constraints": d.get("constraints", [])[:10],
        "must_have_constraints": d.get("must_have_constraints", [])[:10],
        "soft_constraints": d.get("soft_constraints", [])[:10],
        "movie_entities_zh": d.get("movie_entities_zh", [])[:12],
        "movie_entity_candidates_en": {
            k: v[:5] for k, v in (d.get("movie_entity_candidates_en") or {}).items()
        },
    }


def llm_invocation_rows_from_pipeline(pipeline: list) -> list[dict]:
    """从 pipeline 提取大模型调用记录（步骤、耗时、所用模型环境变量）。"""
    rows: list[dict] = []
    for step in pipeline or []:
        if not isinstance(step, dict):
            continue
        if step.get("call_kind") != "llm":
            continue
        sid = str(step.get("id") or "")
        envn = _LLM_STEP_MODEL_ENV.get(sid)
        model = (
            (os.getenv(envn) or DEFAULT_LLM_MODEL).strip()
            if envn
            else (DEFAULT_LLM_MODEL or "").strip()
        )
        rows.append(
            {
                "step_id": sid,
                "title": str(step.get("title") or ""),
                "status": str(step.get("status") or ""),
                "elapsed_ms": int(step.get("elapsed_ms") or 0),
                "model": model,
            }
        )
    return rows


def llm_decompose_preferences(
    user_input: str,
    favorite_movies: list,
    watched_names: list,
    history_genre_hints: list,
    history_movies: Optional[list] = None,
    recent_pool: Optional[list] = None,
) -> dict:
    """
    用大模型把用户偏好结构化分解成（头实体/关系/尾实体 + 约束），供后续 KG/RAG 生成更稳的 query。
    失败时返回 {"ok": False, "error": "..."}。
    """
    t0 = time.time()
    if _llm_disabled():
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": "已通过 MOVIEHUB_DISABLE_LLM 禁用大模型调用"}
    if not llm_client:
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": "未配置 OPENAI_API_KEY"}

    model = os.getenv("LLM_DECOMPOSE_MODEL", DEFAULT_LLM_MODEL)
    pref_desc = preference_description_from_user_input(user_input or "")
    allowed_relations = list(dict.fromkeys([*MOE_RELATION_CORE, *MOE_RELATION_FILL]))

    # RAG 检索相关 DB15K 电影实体
    def _str_list(items, limit=10):
        """从可能是 dict 或 str 的列表中提取字符串。"""
        out = []
        for item in (items or [])[:limit]:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                out.append(item.get("name") or item.get("title") or item.get("display") or "")
        return out

    rag_query = " ".join(filter(None, [
        (user_input or "")[:500],
        " ".join(_str_list(favorite_movies, 10)),
        " ".join(_str_list(history_genre_hints, 5)),
    ]))
    relevant_movies = _retrieve_db15k_movies(rag_query, n_results=30) if rag_query.strip() else []
    # 如果 RAG 未返回结果（向量库未建或 API 不可用），回退到全量列表（截取前 200）
    if not relevant_movies:
        relevant_movies = _load_db15k_movie_list()[:200]

    system = (
        "你是电影推荐系统的偏好解析器。"
        "请把用户输入与历史信号分解成结构化 JSON，用于后续知识图谱(实体-关系-实体)与RAG检索。"
        "必须严格输出 JSON，不要输出其它文本。"
        "务必优先理解并体现输入中的 preference_description（用户在「偏好描述」里写的自由文本）；"
        "若该字段非空，归纳 liked_genres、relations、constraints 与 RAG 的 query 时应以其为核心依据，再综合收藏/已看/浏览等信号。"
        "relations 必须且只能从 allowed_relations 里选择。"
        "movie_entity_candidates_en 的值必须且只能从 db15k_movies 候选列表中选择最匹配的，不要自造名称。"
    )
    payload = {
        "user_input": (user_input or "")[:1800],
        "preference_description": pref_desc[:1200],
        "favorite_movies": favorite_movies[:30] if favorite_movies else [],
        "watched_movies": watched_names[:50] if watched_names else [],
        "history_genre_hints": history_genre_hints[:20] if history_genre_hints else [],
        "history_top_movies": (history_movies or [])[:18],
        "recent_pool": (recent_pool or [])[:24],
        "allowed_genres": ALLOWED_GENRES,
        "allowed_relations": allowed_relations,
        "db15k_movies": relevant_movies,
    }
    ttl_s = _decompose_cache_ttl_s()
    ck = _decompose_cache_key(payload)
    now = time.time()
    if ttl_s > 0:
        hit = _DECOMPOSE_CACHE.get(ck)
        if hit and now - float(hit[0]) <= float(ttl_s):
            return {
                "ok": True,
                "ms": int((time.time() - t0) * 1000),
                "data": dict(hit[1]),
                "cached": True,
            }
    user = (
        "请基于如下信息输出 JSON（字段固定）。"
        "其中 preference_description 是从界面「偏好描述」文本框拆出的正文（不含类型勾选前缀）；"
        "若其非空，请重点依据它来写 constraints、query，并校正 liked_genres/relations。\n"
        "{\n"
        '  \"liked_genres\": [\"...\"],\n'
        '  \"disliked_genres\": [\"...\"],\n'
        '  \"liked_movies\": [\"...\"],\n'
        '  \"avoid_movies\": [\"...\"],\n'
        '  \"relations\": [\"从 allowed_relations 中选择\"],\n'
        '  \"constraints\": [\"...\"],\n'
        '  \"must_have_constraints\": [\"硬约束，如不要恐怖、必须科幻\"],\n'
        '  \"soft_constraints\": [\"软偏好，如节奏快、近十年\"],\n'
        '  \"movie_entities_zh\": [\"用户提及电影中文名\"],\n'
        '  \"movie_entity_candidates_en\": {\"中文片名\": [\"从db15k_movies中选最匹配的英文短名\"]},\n'
        '  \"query\": \"用于RAG的中文查询一句话\"\n'
        "}\n"
        "注意：liked_genres/disliked_genres 必须从 allowed_genres 里选；relations 必须从 allowed_relations 里选；"
        "liked_movies/avoid_movies/movie_entities_zh 用中文片名。"
        "movie_entity_candidates_en 的英文短名必须从 db15k_movies 列表中选取，不要自造。\n\n输入：\n"
        + json.dumps(_json_sanitize(payload), ensure_ascii=False)
    )
    try:
        resp = llm_client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
        )
        txt = (resp.choices[0].message.content or "").strip()
        data = _normalize_decompose_payload(_parse_llm_json_obj(txt))
        if ttl_s > 0:
            _DECOMPOSE_CACHE[ck] = (time.time(), dict(data))
            # 防止缓存无限膨胀
            if len(_DECOMPOSE_CACHE) > 600:
                old = sorted(_DECOMPOSE_CACHE.items(), key=lambda x: x[1][0])[:120]
                for k, _ in old:
                    _DECOMPOSE_CACHE.pop(k, None)
        return {"ok": True, "ms": int((time.time() - t0) * 1000), "data": data}
    except Exception as e:
        return {
            "ok": False,
            "ms": int((time.time() - t0) * 1000),
            "error": f"{type(e).__name__}: {e}",
        }


def _collect_summary_allowed_titles(movies: list) -> list[str]:
    """推荐总结允许出现的片名（展示名与内部名，去重保序）。"""
    out: list[str] = []
    for m in movies or []:
        if not isinstance(m, dict):
            continue
        for k in ("display", "name"):
            v = (m.get(k) or "").strip()
            if v and v not in out:
                out.append(v)
    return out


def _summary_title_matches_allowed(bracket: str, allowed: list[str]) -> bool:
    b = re.sub(r"\s+", " ", (bracket or "").strip())
    if not b:
        return True
    for a in allowed:
        an = re.sub(r"\s+", " ", (a or "").strip())
        if not an:
            continue
        if b == an or b in an or an in b:
            return True
        if b.casefold() == an.casefold():
            return True
        if an.casefold() in b.casefold() or b.casefold() in an.casefold():
            return True
    return False


def _summary_text_respects_allowed_titles(text: str, allowed: list[str]) -> bool:
    s = (text or "").strip()
    if not s:
        return False
    brackets = re.findall(r"《([^》]{1,160})》", s)
    for b in brackets:
        if not _summary_title_matches_allowed(b, allowed):
            return False
    if not allowed:
        return False
    low = s.casefold()
    for a in allowed:
        an = (a or "").strip()
        if not an:
            continue
        if an in s or an.replace("_", " ") in s:
            return True
        if an.casefold() in low:
            return True
    return False


def _fallback_recommend_summary_text(movies: list) -> str:
    parts: list[str] = []
    for m in (movies or [])[:10]:
        if not isinstance(m, dict):
            continue
        disp = (m.get("display") or m.get("name") or "").strip()
        if not disp:
            continue
        sr = (m.get("short_review") or m.get("blurb") or "").strip()
        if sr:
            parts.append(f"《{disp}》：{sr[:120]}{'…' if len(sr) > 120 else ''}")
        else:
            parts.append(f"《{disp}》")
    if not parts:
        return ""
    head = "本次推荐基于当前列表："
    body = " ".join(parts[:5])
    out = (head + body)[:300]
    return re.sub(r"\s{2,}", " ", out).strip()


def llm_summarize_recommendation(user_input: str, final_movies: list) -> dict:
    """用千问把推荐结果整合为一段话（面向普通用户）。"""
    t0 = time.time()
    if not llm_client:
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": "未配置 OPENAI_API_KEY"}
    if not final_movies:
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": "无推荐结果"}

    model = os.getenv("LLM_SUMMARY_MODEL", DEFAULT_LLM_MODEL)
    allowed_titles = _collect_summary_allowed_titles(final_movies)
    top = []
    for m in (final_movies or [])[:10]:
        top.append({"title": (m.get("display") or m.get("name") or "").strip(), "source": m.get("source")})

    def _clean_user_summary(txt: str) -> str:
        s = (txt or "").strip()
        if not s:
            return ""
        s = re.sub(r"<think>[\s\S]*?</think>", "", s, flags=re.IGNORECASE).strip()
        bad_markers = [
            "用户要求",
            "提示词",
            "不超过",
            "只输出",
            "不要分点",
            "不要Markdown",
            "推荐列表中有",
        ]
        for mk in bad_markers:
            if mk in s:
                s = s.split(mk)[-1].strip()
        s = s.replace("\n", " ").replace("\r", " ")
        s = re.sub(r"\s{2,}", " ", s).strip()
        return s[:300]

    n = len(top)
    only_names = [x["title"] for x in top if x.get("title")]
    names_line = "、".join([f"《{t}》" for t in only_names if t]) or "（无）"
    system = (
        "你是电影推荐文案助手。"
        "请把推荐列表写成一段自然中文总结，包含“电影短评/理由”。"
        "总字数不超过300字，只输出一段话，不要分点，不要Markdown。"
        f"【硬性约束】本次系统只推荐了 {n} 部影片，片名必须且只能来自用户消息中的「推荐TOP」JSON，"
        f"逐字与其中 title 字段一致；用《》括起每一处片名。"
        f"仅允许出现以下片名（须原样）：{names_line}。"
        "严禁凭常识或检索补充其它影片：不要写「此外」「同样值得」「常看清单」「不妨看看」等引出列表外片名；"
        "禁止出现任何未在 JSON 中出现的《》片名。"
        "若只有1～2部则全部展开；多于3部可重点写前3部，其余一句带过，但所点名的《》必须全部来自 JSON。"
    )
    user = (
        "用户偏好："
        + (user_input or "（无）")[:500]
        + "\n推荐TOP（仅此列表，title 为唯一合法片名）："
        + json.dumps(top, ensure_ascii=False)
    )
    retry_user = (
        user
        + "\n\n【纠错】上一稿若出现了不在 JSON 中的《》片名，属于严重错误。请重写："
        "全文只允许《》中出现上述 title；不得提及任何未列出影片。"
    )
    try:
        raw = ""
        for attempt in range(2):
            resp = llm_client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": retry_user if attempt else user}],
                temperature=0.2 if attempt else 0.25,
                max_tokens=420,
            )
            raw = (resp.choices[0].message.content or "").strip()
            cleaned = _clean_user_summary(raw)
            if cleaned and _summary_text_respects_allowed_titles(cleaned, allowed_titles):
                return {"ok": True, "ms": int((time.time() - t0) * 1000), "text": cleaned, "error": ""}
        fb = _fallback_recommend_summary_text(final_movies)
        if fb:
            return {
                "ok": True,
                "ms": int((time.time() - t0) * 1000),
                "text": fb,
                "error": "",
            }
        return {
            "ok": False,
            "ms": int((time.time() - t0) * 1000),
            "text": "",
            "error": "大模型总结含列表外片名且无法生成安全摘要，请重试。",
        }
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        low = err.lower()
        if "apiconnectionerror" in low or "connection error" in low or "connect" in low or "timeout" in low:
            err = "网络连接失败：无法访问大模型服务。请开启代理/检查 API 地址与密钥后重试。"
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": err}


def llm_filter_recommendations(user_input: str, candidates: list[dict]) -> dict:
    """
    用大模型对候选推荐做“审核过滤”：
    - 只输出需剔除的 drop_titles（噪声/非电影等）；不得输出“保留子集”替代完整初榜。
    - 代码侧仅按 drop 剔除；初榜其余条目一律保留，避免模型反复只挑固定几部导致结果僵死。
    """
    t0 = time.time()
    if not llm_client:
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": "未配置 OPENAI_API_KEY"}
    if not candidates:
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": "无候选"}

    model = os.getenv("LLM_FILTER_MODEL", DEFAULT_LLM_MODEL)
    system = (
        "你是电影推荐系统的审核器。"
        "任务：仅从候选中标注「应剔除」的条目（明显非叙事长片电影、人物/剧集/书籍/唱片等噪声实体）。"
        "不要决定最终推荐几部；不要从候选里再“精选”子集。"
        "【禁止】输出 keep_titles 或等价“保留清单”；系统会保留所有未被 drop 的候选。"
        "【剔除范围】必须剔除：人物、电视剧/综艺、书籍、音乐专辑/流派、公司等；"
        "名称带 (film)/(movie) 的一般视为电影应保留，除非明显不是电影。"
        "【不要过度严格】确属电影的条目勿因题材冷僻而剔除；不得以语种/译名为由剔除。"
        "若无任何应剔除项，drop_titles 必须为 []。"
        "必须严格输出 JSON，不要输出其它文本。"
    )
    cand_cap = _env_int("LLM_FILTER_CANDIDATE_CAP", 28, min_v=8, max_v=80)
    payload = {
        "user_input": (user_input or "")[:1400],
        "candidates": [
            {"title": (m.get("display") or m.get("name") or "")[:120], "source": m.get("source") or ""}
            for m in candidates[: min(cand_cap, len(candidates))]
        ],
    }
    user = (
        "请输出 JSON（仅含 drop 与说明）：\n"
        "{\n"
        '  "drop_titles": ["仅填需剔除的片名/实体名，与候选 title 尽量一致"],\n'
        '  "analysis": "用中文写一段简短解释（100-220字），可指出噪声来源；末句声明主观不保证客观正确。"\n'
        "}\n\n输入：\n"
        + json.dumps(_json_sanitize(payload), ensure_ascii=False)
    )
    try:
        resp = llm_client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.35,
        )
        txt = (resp.choices[0].message.content or "").strip()
        data = _parse_llm_json_obj(txt)
        drop = [x.strip() for x in (data.get("drop_titles") or []) if isinstance(x, str) and x.strip()]
        analysis = (data.get("analysis") or "").strip()
        return {
            "ok": True,
            "ms": int((time.time() - t0) * 1000),
            "keep_titles": [],
            "drop_titles": drop,
            "analysis": analysis,
        }
    except Exception as e:
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": f"{type(e).__name__}: {e}"}


def llm_finalize_single_lane(
    user_input: str,
    genre_hints: list,
    candidates: list[dict],
    topk: int,
    lane_label: str,
    avoid_titles: Optional[list[str]] = None,
    must_have_constraints: Optional[list[str]] = None,
    soft_constraints: Optional[list[str]] = None,
) -> dict:
    """
    单路定榜：大模型从一路候选中挑选 topk 部。
    lane_label: "kg" / "library" / "peer_fav"，用于 prompt 说明。
    返回 ok, picks, note, ms, error。
    """
    t0 = time.time()
    if not llm_client:
        return {"ok": False, "ms": 0, "error": "未配置 OPENAI_API_KEY", "picks": [], "note": ""}
    topk = max(0, int(topk))
    if topk == 0:
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": "配额为 0", "picks": [], "note": ""}
    model = os.getenv("LLM_FINALIZE_MODEL") or os.getenv("LLM_FILTER_MODEL", DEFAULT_LLM_MODEL)
    gh = "、".join([str(x) for x in (genre_hints or [])[:14] if x])
    lane_cap = _env_int("LLM_FINALIZE_POOL_PER_LANE", 24, min_v=6, max_v=64)

    payload_list = []
    for m in candidates[:lane_cap]:
        t = _movie_display_key(m)
        if not t:
            continue
        item = {"title": t[:130], "weight": round(float(m.get("weight") or 0), 3)}
        g = (m.get("genres_str") or m.get("genres") or "").strip()
        if g:
            item["genres"] = g[:80]
        payload_list.append(item)

    av_raw = [str(x).strip() for x in (avoid_titles or []) if str(x).strip()][:28]
    must_raw = [str(x).strip() for x in (must_have_constraints or []) if str(x).strip()][:20]
    soft_raw = [str(x).strip() for x in (soft_constraints or []) if str(x).strip()][:20]

    avoid_line = ""
    if av_raw:
        avoid_line = "【避让】下列片名尽量不选（除非候选里仅剩这些）：" + "、".join(av_raw[:24]) + "。"
    constraint_line = ""
    if must_raw:
        constraint_line += "【硬约束】" + "；".join(must_raw[:12]) + "。"
    if soft_raw:
        constraint_line += "【软偏好】" + "；".join(soft_raw[:12]) + "。"

    if lane_label == "kg":
        lane_desc = "知识图谱（Multi_MoE 链路预测）"
    elif lane_label == "peer_fav":
        lane_desc = "同偏好他人收藏（弱协同）"
    else:
        lane_desc = "片库（RAG 向量检索 + LLM 生成）"
    system = (
        f"你是电影推荐系统的「定榜」助手，当前负责从{lane_desc}一路的候选中挑选最佳影片。"
        "你必须**只从下方 JSON 里出现的 title 字符串中**挑选，禁止编造、改写片名，禁止输出列表外的影片。"
        "【剔除噪声】在挑选前，先剔除明显非叙事长片电影的条目：人物、电视剧/综艺、书籍、音乐专辑/流派、公司等噪声实体。"
        "名称带 (film)/(movie) 的一般视为电影应保留，除非明显不是电影。"
        "不要过度严格，确属电影的条目勿因题材冷僻而剔除；不得以语种/译名为由剔除。"
        f"输出要求：picks 必须恰好 {topk} 个字符串（若候选不足 {topk} 部则尽量多选且只从该列表选）。"
        "挑选原则（按优先级从高到低）：\n"
        "1. **类型匹配（最高优先）**：候选的 genres 字段是该电影的实际类型。优先选 genres 与用户偏好类型（genre_hints）高度重合的电影；"
        "若用户指定了类型（如科幻、悬疑），则类型不匹配的候选应被淘汰，即使它在其它方面看起来不错。\n"
        "2. **用户偏好与硬约束**：在类型匹配的基础上，选最贴合用户文字描述与 must_have_constraints 的电影。\n"
        "3. **软偏好与多样性**：得分接近时，兼顾 soft_preferences 并优先多样化（不同导演/年代/风格）。"
        + (avoid_line if avoid_line else "")
        + (constraint_line if constraint_line else "")
        + "必须严格输出 JSON，不要其它文本。"
    )
    payload = {
        "user_input": (user_input or "")[:1200],
        "genre_hints": gh,
        "candidates": payload_list,
        "avoid_previous_round": av_raw,
        "must_have_constraints": must_raw,
        "soft_constraints": soft_raw,
    }
    user = (
        "输出 JSON 格式：\n"
        '{\n  "picks": ["片名1", "片名2", ...],\n  "note": "一句话说明取舍（中文）"\n}\n\n'
        "注意：每个候选都有 genres 字段（电影实际类型），请务必优先根据 genres 与用户偏好类型的匹配程度来筛选。\n\n"
        + json.dumps(_json_sanitize(payload), ensure_ascii=False)
    )
    try:
        resp = llm_client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.45,
        )
        txt = (resp.choices[0].message.content or "").strip()
        data = _parse_llm_json_obj(txt)
        picks = [str(x).strip() for x in (data.get("picks") or []) if isinstance(x, str) and str(x).strip()]
        picks = picks[:topk]
        note = (data.get("note") or "").strip()
        return {"ok": True, "ms": int((time.time() - t0) * 1000), "error": "", "picks": picks, "note": note}
    except Exception as e:
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": f"{type(e).__name__}: {e}", "picks": [], "note": ""}


def llm_finalize_recommendations(
    user_input: str,
    genre_hints: list,
    kg_candidates: list[dict],
    library_candidates: list[dict],
    kk: int,
    kr: int,
    avoid_titles: Optional[list[str]] = None,
    must_have_constraints: Optional[list[str]] = None,
    soft_constraints: Optional[list[str]] = None,
) -> dict:
    """
    定榜（兼容旧接口）：内部改为两次单路调用，分别从 KG 和 RAG 候选中各选 kk / kr 部。
    返回 ok, kg_picks, library_picks, note, ms, error。
    """
    t0 = time.time()
    kk = max(0, int(kk))
    kr = max(0, int(kr))
    if kk == 0 and kr == 0:
        return {"ok": False, "ms": 0, "error": "配额为 0", "kg_picks": [], "library_picks": [], "note": ""}

    kg_res = llm_finalize_single_lane(
        user_input, genre_hints, kg_candidates, kk, "kg",
        avoid_titles, must_have_constraints, soft_constraints,
    )
    rag_res = llm_finalize_single_lane(
        user_input, genre_hints, library_candidates, kr, "library",
        avoid_titles, must_have_constraints, soft_constraints,
    )

    kg_picks = kg_res.get("picks") or []
    lib_picks = rag_res.get("picks") or []
    note_parts = []
    if kg_res.get("note"):
        note_parts.append(f"图谱：{kg_res['note']}")
    if rag_res.get("note"):
        note_parts.append(f"片库：{rag_res['note']}")
    ok = kg_res.get("ok") or rag_res.get("ok")
    err = ""
    if not kg_res.get("ok"):
        err = f"图谱定榜失败：{kg_res.get('error', '')}"
    if not rag_res.get("ok"):
        err = (err + "；" if err else "") + f"片库定榜失败：{rag_res.get('error', '')}"

    return {
        "ok": ok,
        "ms": int((time.time() - t0) * 1000),
        "error": err,
        "kg_picks": kg_picks,
        "library_picks": lib_picks,
        "note": "；".join(note_parts),
    }


def llm_explain_recommendation(
    preference_summary: str,
    selected_favorites: list,
    seed_entities: list,
    kg_entities: list,
    rag_movies: list,
    history_genre_hints: list,
    watched_titles: Optional[list] = None,
    final_titles: Optional[list[str]] = None,
) -> dict:
    t0 = time.time()
    if not llm_client:
        return {
            "text": "",
            "ms": int((time.time() - t0) * 1000),
            "ok": False,
            "error": "未配置 OPENAI_API_KEY，已跳过大模型解读。",
        }

    model = os.getenv("LLM_EXPLAIN_MODEL", DEFAULT_LLM_MODEL)
    kg_readable = [_get_movie_display_name(m) for m in kg_entities]
    rag_lines = []
    for m in rag_movies or []:
        if isinstance(m, dict):
            nm = m.get("name", "")
            sim = m.get("similarity")
            meta = m.get("metadata") or {}
            g = meta.get("genres", "")
            src = m.get("source", "")
            sim_str = ""
            if sim is not None:
                try:
                    sim_str = f"，相似度约{float(sim):.2f}"
                except (TypeError, ValueError):
                    sim_str = f"，相似度:{sim}"
            rr = str(m.get("rag_llm_reason") or "").strip()
            reason_part = f"，RAG说明:{rr[:160]}" if rr else ""
            extra = (
                f"（来源:{src}{sim_str}"
                + (f"，类型:{g}" if g else "")
                + reason_part
                + "）"
            )
            rag_lines.append(f"- {nm}{extra}")
        else:
            rag_lines.append(f"- {m}")

    ft = [str(x).strip() for x in (final_titles or []) if str(x).strip()][:16]
    user_block = "\n".join(
        [
            "【用户偏好摘要】",
            preference_summary.strip() or "（无额外描述）",
            "",
            "【定榜后真正推荐给用户的影片（解读应主要围绕这几部；勿把下列长列表当最终清单逐一点评）】",
            "、".join(ft) if ft else "（请等待前端传入定榜结果；若暂无则侧重两路与偏好的关系，少点名具体片名）",
            "",
            "【本次用作种子的收藏片名】",
            "、".join([str(x) if isinstance(x, str) else (x.get("movie_name") or x.get("name") or x.get("title") or str(x)) for x in selected_favorites]) if selected_favorites else "（未选收藏或为空）",
            "",
            "【映射到知识图谱的种子实体（短名）】",
            "、".join(seed_entities) if seed_entities else "（无，则 KG 一路通常无结果）",
            "",
            "【来自「已看过」影片的类型提示】",
            "、".join([str(x) if isinstance(x, str) else (x.get("genres") or x.get("name") or str(x)) for x in history_genre_hints[:8]]) if history_genre_hints else "（无）",
            "",
            "【用户主动标记已看过的影片（作口味参考，不应出现在推荐列表中）】",
            "、".join(watched_titles[:20]) if watched_titles else "（无）",
            "",
            "【知识图谱一路召回长列表（中间过程，非最终推荐清单）】",
            "、".join(kg_readable) if kg_readable else "（本路无输出）",
            "",
            "【片库标准 RAG 一路（向量证据→LLM 生成，或检索直出回退）】",
            "\n".join(rag_lines) if rag_lines else "（本路无输出）",
        ]
    )

    system = (
        "你是电影推荐系统的解释助手，只根据给定材料写中文说明，不要编造用户未提供的信息。"
        "若有「定榜后真正推荐给用户的影片」列表，请**以该列表为主**说明与用户偏好的对应关系；"
        "「知识图谱一路召回长列表」仅为 MoE 中间过程，不要默认按该列表前几部影片展开长评，除非它们出现在定榜列表中。"
        "知识图谱这一路来自 Multi_MoE 在 DB15K 上的链路预测（融合分支 pred_mm），"
        "按 (种子实体, genre/director/starring) 对全实体打分后筛电影实体；知识库中实体名常为英文，不代表系统排斥其它语言作品。"
        "片库 RAG 一路来自向量检索得到的片库证据，由大模型按编号选片并写理由（失败时可能为检索直出/豆瓣补位），元数据可能含 TMDB/豆瓣等来源。"
        "【重要】系统可以推荐任何语言的影片；片名语种、是否有中文译名、是否“中文阅读习惯”“中文观影习惯”"
        "一律不作为筛选或否定理由，"
        "禁止在文中以「外文片名」「中文阅读习惯」「中文观影习惯」「语言」为由建议排除某部影片；"
        "若讨论某条候选与用户需求是否匹配，仅从题材/类型/内容是否与用户偏好（如科幻类型）等角度说明，不要评价语言。"
        "请写一段 200～450 字的连贯说明，必须包含："
        "（1）两路结果与用户偏好的大致对应关系；"
        "（2）若知识图谱这一路中某条目在题材/类型上与用户偏好明显不符，可点名并说明原因（勿从语言角度）；"
        "（3）若 RAG 一路也有明显题材/类型偏离，可简要指出；"
        "（4）最后一句话声明：以上为主观辅助说明，不保证客观正确。"
        "不要使用 Markdown 标题符号（不要写 # 号），不要输出 JSON。"
    )

    try:
        resp = llm_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_block},
            ],
            temperature=0.4,
            max_tokens=900,
        )
        text = (resp.choices[0].message.content or "").strip()
        return {
            "text": text,
            "ms": int((time.time() - t0) * 1000),
            "ok": bool(text),
            "error": "" if text else "大模型返回为空",
        }
    except Exception as e:
        err = str(e)[:500]
        print(f"❌ [LLM] 解读失败: {str(err)[:120]}")
        return {
            "text": "",
            "ms": int((time.time() - t0) * 1000),
            "ok": False,
            "error": err,
        }


def llm_movie_card_blurbs(user_input: str, movies: list) -> dict:
    """一次调用为每条推荐生成杂志清单式一句短评（JSON 字符串数组，与输入顺序一致）。"""
    t0 = time.time()
    if not llm_client:
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": "未配置 OPENAI_API_KEY", "blurbs": []}
    if not movies:
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": "无影片", "blurbs": []}

    model = os.getenv("LLM_CARD_BLURB_MODEL", DEFAULT_LLM_MODEL)
    lines = []
    for i, m in enumerate(movies, 1):
        lines.append(
            {
                "i": i,
                "title": ((m.get("display") or m.get("name") or "")[:80]).strip(),
                "genres": ((m.get("genres_str") or "")[:80]).strip(),
                "score": ((m.get("score_str") or "")[:20]).strip(),
                "source": ((m.get("source") or "")[:40]).strip(),
            }
        )
    system = (
        "你是电影清单栏目的中文撰稿人。"
        "输入为若干部电影的标题、类型、评分与来源。请为每一部各写一句“像影评但不剧透”的短句："
        "要具体、有画面感，别用空话套话。"
        "每条建议 18～32 个汉字，尽量包含一个看点关键词（如“窒息感”“反转”“治愈”“燃”“黑色幽默”等）。"
        "禁止使用这些套话：值得关注、佳作、适合放入片单、本期观影。"
        "只输出一个 JSON 字符串数组，长度必须与电影条数完全一致、顺序一致；不要 Markdown，不要其它说明。"
    )
    user = json.dumps(
        {"user_preference": (user_input or "")[:900], "movies": lines},
        ensure_ascii=False,
    )
    try:
        resp = llm_client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.55,
            max_tokens=min(1400, 120 + 90 * len(lines)),
        )
        txt = (resp.choices[0].message.content or "").strip()
        if txt.startswith("```"):
            txt = re.sub(r"^```[a-zA-Z]*", "", txt).strip()
            txt = re.sub(r"```\s*$", "", txt).strip()
        arr = json.loads(txt)
        if not isinstance(arr, list):
            return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": "解析失败：非数组", "blurbs": []}
        blurbs = []
        for x in arr[: len(movies)]:
            blurbs.append((str(x) if x is not None else "").strip()[:120])
        while len(blurbs) < len(movies):
            blurbs.append("")
        return {
            "ok": True,
            "ms": int((time.time() - t0) * 1000),
            "blurbs": blurbs[: len(movies)],
            "error": "",
        }
    except Exception as e:
        return {
            "ok": False,
            "ms": int((time.time() - t0) * 1000),
            "error": f"{type(e).__name__}: {e}",
            "blurbs": [],
        }


def generate_recommend_card_blurbs(*, user_input: str, movies: list[dict]) -> dict:
    """为推荐结果卡片生成短评（独立任务，供前端两阶段推荐异步拉取）。"""
    t0 = time.time()
    ms = 0
    bl: dict = {"ok": False, "error": ""}
    try:
        slice_m = [m for m in (movies or []) if isinstance(m, dict)][:12]
        bl = llm_movie_card_blurbs((user_input or ""), slice_m)
        ms = int(bl.get("ms") or int((time.time() - t0) * 1000))
        if bl.get("ok"):
            for i, m in enumerate(slice_m):
                arr = bl.get("blurbs") or []
                if i < len(arr) and (arr[i] or "").strip():
                    m["short_review"] = (arr[i] or "").strip()[:160]
        for m in slice_m:
            if not (m.get("short_review") or "").strip():
                g = (m.get("genres_str") or "").strip()
                if g:
                    parts = [x.strip() for x in g.replace("、", "/").split("/") if x.strip()]
                else:
                    parts = []
                g1 = parts[0] if parts else "故事"
                g2 = parts[1] if len(parts) > 1 else ""
                tag = f"{g1}/{g2}" if g2 else g1
                m["short_review"] = f"{tag}气质鲜明，节奏利落，情绪落点很准。"
        return {
            "success": True,
            "movies": slice_m,
            "blurbs_ok": bool(bl.get("ok")),
            "blurbs_error": (bl.get("error") or "").strip(),
            "elapsed_ms": ms,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "movies": [], "elapsed_ms": int((time.time() - t0) * 1000)}


def generate_recommend_summary(*, user_input: str, movies: list[dict]) -> dict:
    """生成推荐总结（独立任务）。"""
    t0 = time.time()
    try:
        top = [m for m in (movies or []) if isinstance(m, dict)][:10]
        sum_res = llm_summarize_recommendation((user_input or "")[:600], top)
        ms = int(sum_res.get("ms") or int((time.time() - t0) * 1000))
        if sum_res.get("ok"):
            return {
                "success": True,
                "llm_summary": (sum_res.get("text") or "").strip(),
                "llm_summary_error": "",
                "elapsed_ms": ms,
            }
        return {
            "success": True,
            "llm_summary": "",
            "llm_summary_error": (sum_res.get("error") or "").strip(),
            "elapsed_ms": ms,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "elapsed_ms": int((time.time() - t0) * 1000)}


def generate_recommend_explain(
    *,
    user_input: str,
    favorite_movies: list,
    watched_titles: list,
    seed_movies: list,
    kg_movies: list,
    rag_movies: list,
    genre_hints: list,
    final_titles: Optional[list[str]] = None,
) -> dict:
    """按需生成推荐解读（独立任务，与主链路解读逻辑一致）。"""
    t0 = time.time()
    try:
        llm_res = llm_explain_recommendation(
            (user_input or "")[:2500],
            list(favorite_movies) if favorite_movies else [],
            seed_movies,
            kg_movies,
            rag_movies,
            genre_hints,
            watched_titles=watched_titles or None,
            final_titles=final_titles,
        )
        ms = int(llm_res.get("ms") or int((time.time() - t0) * 1000))
        return {
            "success": bool(llm_res.get("ok")),
            "llm_explanation": (llm_res.get("text") or "").strip(),
            "llm_explanation_error": (llm_res.get("error") or "").strip(),
            "elapsed_ms": ms,
        }
    except Exception as e:
        return {
            "success": False,
            "llm_explanation": "",
            "llm_explanation_error": str(e)[:500],
            "elapsed_ms": int((time.time() - t0) * 1000),
        }
