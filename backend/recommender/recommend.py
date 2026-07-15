"""
推荐页：知识图谱 Multi_MoE、片库标准 RAG（向量证据→LLM）、TMDB 最近上映、合并定榜与大模型解读。
与 browse / home 共用 common 中的缓存与映射。

第三路「TMDB 最近/即将上映」工具池（recent_pool）的职责与数据来源说明见
``backend.recommender.recent_tmdb_pool``。
"""
import math
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional, Tuple

import pandas as pd

from backend.db.database import get_conn, rec_log_add, feedback_list
from backend.services.tmdb_client import (
    TMDB_GENRE_TO_CN,
    search_movie_first,
    tmdb_configured,
    tmdb_genres_cn,
    tmdb_movie_detail,
)
from backend.recommender.common import (
    ALLOWED_GENRES,
    MOVIE_GENRE_MAPPING,
    MOVIE_NAME_MAPPING,
    _cache,
    llm_client,
)


from backend.recommender.recommend_rag import (
    load_rag_db,
    rag_combined_chroma_n_results,
    rag_fetch_shared_vector_rows,
    rag_llm_recommend,
    rag_retrieve_for_kg_seeds,
)
from backend.recommender.recent_tmdb_pool import recent_extra_pipeline_message
from backend.recommender.recommend_kg import (
    find_entity_in_kg,
    intermediate_moe_seeds_from_movies,
    load_kg_model,
    moe_link_prediction_recommend,
    structural_bridge_seeds,
    _graph_expand_kg_neighbors,
)
from backend.recommender.recommend_llm import (
    llm_decompose_preferences,
    llm_explain_recommendation,
    llm_finalize_recommendations,
    llm_finalize_single_lane,
    llm_summarize_recommendation,
    llm_invocation_rows_from_pipeline as _llm_invocation_rows_from_pipeline,
    public_decompose_preview as _public_decompose_preview,
    generate_recommend_card_blurbs,
    generate_recommend_summary,
    generate_recommend_explain,
)


def _norm_title_for_dedupe(s: str) -> str:
    t = (s or "").strip().lower()
    for suf in (" (film)", " (movie)", "(film)", "(movie)"):
        sl = suf.lower()
        if t.endswith(sl):
            t = t[: -len(sl)].strip()
            break
    return t


def _movie_display_key(m: dict) -> str:
    return (m.get("display") or m.get("name") or "").strip()


def _quota_pad_to_cap(
    merged: list[dict],
    pool_full: list[dict],
    cap: int,
    kk: int,
    kr: int,
    drop_norm: set[str],
    k_peer: int = 0,
) -> list[dict]:
    out = list(merged)
    have = {_movie_display_key(m) for m in out if _movie_display_key(m)}
    pool_sorted = sorted(
        pool_full,
        key=lambda x: float(x.get("weight") or 0),
        reverse=True,
    )

    def _is_kg(mm: dict) -> bool:
        return str(mm.get("source") or "").strip() == "kg"

    def _is_peer(mm: dict) -> bool:
        return str(mm.get("source") or "").strip() == "peer_fav"

    def _n_kg(mm: list[dict]) -> int:
        return sum(1 for x in mm if _is_kg(x))

    def _n_rag_lib(mm: list[dict]) -> int:
        return sum(1 for x in mm if not _is_kg(x) and not _is_peer(x))

    def _n_peer(mm: list[dict]) -> int:
        return sum(1 for x in mm if _is_peer(x))

    k_peer = max(0, int(k_peer))

    def _can_take(mm: dict) -> bool:
        t = _movie_display_key(mm)
        if not t or t in have:
            return False
        if drop_norm and _norm_title_for_dedupe(t) in drop_norm:
            return False
        return True

    while len(out) < cap:
        nk = _n_kg(out)
        nr = _n_rag_lib(out)
        np = _n_peer(out)
        took = False
        if nr < kr:
            for mm in pool_sorted:
                if not _can_take(mm) or _is_kg(mm) or _is_peer(mm):
                    continue
                out.append(mm)
                have.add(_movie_display_key(mm))
                took = True
                break
        if len(out) >= cap:
            break
        if nk < kk:
            for mm in pool_sorted:
                if not _can_take(mm) or not _is_kg(mm):
                    continue
                out.append(mm)
                have.add(_movie_display_key(mm))
                took = True
                break
        if len(out) >= cap:
            break
        if k_peer > 0 and np < k_peer:
            for mm in pool_sorted:
                if not _can_take(mm) or not _is_peer(mm):
                    continue
                out.append(mm)
                have.add(_movie_display_key(mm))
                took = True
                break
        if len(out) >= cap:
            break
        if not took:
            for mm in pool_sorted:
                if not _can_take(mm):
                    continue
                out.append(mm)
                have.add(_movie_display_key(mm))
                took = True
                break
        if not took:
            break
    return out


def _recent_genre_tokens_cn(gtxt: str) -> set[str]:
    s: set[str] = set()
    raw = (gtxt or "").replace("\u3001", "/").replace(",", "/")
    for x in raw.split("/"):
        p = x.strip()
        if not p:
            continue
        if p in ALLOWED_GENRES:
            s.add(p)
            continue
        cn = TMDB_GENRE_TO_CN.get(p)
        if cn and cn in ALLOWED_GENRES:
            s.add(cn)
        pl = p.lower()
        if "science fiction" in pl or pl in ("sci-fi", "scifi"):
            s.add("\u79d1\u5e7b")
    return s


def _peer_pref_genres_from_inputs(
    user_input: str,
    history_genres: list,
    genre_hints: list[str],
    extra_genres: list[str],
) -> set[str]:
    """与 recommend_for_user 内「偏好类型」抽取一致，用于弱协同补候选。"""
    s: set[str] = set()
    txt = (user_input or "") + " " + " ".join([str(x) for x in (history_genres or []) if x])
    for g in ALLOWED_GENRES:
        if g and g in txt:
            s.add(g)
    for it in (history_genres or [])[:20]:
        if isinstance(it, dict):
            gs = str(it.get("genres") or "")
            for part in gs.split("/"):
                p = part.strip()
                if p in ALLOWED_GENRES:
                    s.add(p)
    for g in genre_hints or []:
        if isinstance(g, str) and g.strip() in ALLOWED_GENRES:
            s.add(g.strip())
    for g in extra_genres or []:
        if isinstance(g, str) and g in ALLOWED_GENRES:
            s.add(g)
    return s


def _fetch_peer_favorites_by_genre(
    user_id: int,
    pref_genres: set[str],
    *,
    exclude_title_norms: set[str],
    limit_sql: int = 160,
    max_take: int = 24,
    min_distinct_users: int = 1,
) -> list[tuple[str, float, str]]:
    """
    其他用户收藏中与当前偏好类型有交集的电影（按「多少用户收藏过」排序）。
    返回 (movie_name, weight, genres_str)。
    """
    if not pref_genres or user_id <= 0:
        return []
    conn = None
    cur = None
    try:
        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT movie_name,
                   MAX(genres) AS genres,
                   COUNT(DISTINCT user_id) AS nu
            FROM user_movie_state
            WHERE user_id <> %s
              AND blocked = 0
              AND is_favorite = 1
              AND fav_at IS NOT NULL
              AND CHAR_LENGTH(movie_name) > 0
            GROUP BY movie_name
            HAVING nu >= %s
            ORDER BY nu DESC
            LIMIT %s
            """,
            (int(user_id), int(min_distinct_users), int(limit_sql)),
        )
        rows = list(cur.fetchall() or [])
    except Exception:
        return []
    finally:
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass

    out: list[tuple[str, float, str]] = []
    for r in rows:
        nm = str((r or {}).get("movie_name") or "").strip()
        if not nm:
            continue
        gtxt = str((r or {}).get("genres") or "")
        gset = _recent_genre_tokens_cn(gtxt)
        if not (gset & pref_genres):
            continue
        nk = _norm_title_for_dedupe(nm)
        if nk and nk in exclude_title_norms:
            continue
        try:
            nu = int((r or {}).get("nu") or 0)
        except (TypeError, ValueError):
            nu = 0
        nu = max(1, nu)
        w = 0.52 + min(0.22, 0.045 * float(nu - 1))
        out.append((nm, float(w), gtxt))
        if len(out) >= int(max_take):
            break
    return out


# ===== 规则层噪声过滤（兜底，防止 TV/非电影实体混入推荐） =====
_NOISE_PATTERNS = re.compile(
    r"(?i)"
    r"\b(tv\s*serial|tv\s*series|television|综艺|电视剧)\b"
    r"|\(tv\b"
    r"|\bseason\s*\d|\bepisode\s*\d|\bs\d{1,2}e\d{1,2}\b"
    r"|\b(soundtrack|ost|原声|专辑|唱片)\b"
    r"|\b(novel|小说|漫画|书籍|书)\b"
    r"|\b(company|公司|studio|工作室)\b"
)


def _is_noise_movie(m: dict) -> bool:
    """快速判断一条推荐是否为明显的非电影噪声实体。"""
    t = (m.get("display") or m.get("name") or "").strip()
    if not t:
        return True
    if _NOISE_PATTERNS.search(t):
        return True
    # 名称带 (film)/(movie) 的一般视为电影，应保留
    tl = t.lower()
    if "(film)" in tl or "(movie)" in tl:
        return False
    return False


def _stratified_core_pick(
    pool: list[dict], kk: int, kr: int, k_peer: int = 0
) -> list[dict]:
    """图谱 kk + 片库(RAG/豆瓣等，不含 peer_fav) kr + 同偏好他人收藏 k_peer（按权重）。不含「最近上映」额外推荐。"""
    pool = [m for m in pool if not _is_noise_movie(m)]
    pool = sorted(pool, key=lambda x: float(x.get("weight") or 0), reverse=True)
    kg_only = [m for m in pool if str(m.get("source") or "").strip() == "kg"]
    rag_only = [
        m for m in pool if str(m.get("source") or "").strip() not in ("kg", "peer_fav")
    ]
    peer_only = [m for m in pool if str(m.get("source") or "").strip() == "peer_fav"]
    seen_t: set[str] = set()
    merged: list[dict] = []
    for m in kg_only[: max(0, kk)]:
        t = _movie_display_key(m)
        if t and t not in seen_t:
            merged.append(m)
            seen_t.add(t)
    for m in rag_only[: max(0, kr)]:
        t = _movie_display_key(m)
        if t and t not in seen_t:
            merged.append(m)
            seen_t.add(t)
    for m in peer_only[: max(0, k_peer)]:
        t = _movie_display_key(m)
        if t and t not in seen_t:
            merged.append(m)
            seen_t.add(t)
    return merged


def _poster_cache_alias_list(m: dict, row) -> list[str]:
    """海报本地缓存可能以豆瓣中文名、英文名等键入；合并 RAG 元数据与 CSV 行。"""
    acc: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        t = (s or "").strip()
        if t and t not in seen:
            acc.append(t)
            seen.add(t)

    pcm = m.get("poster_cache_aliases")
    if isinstance(pcm, list):
        for x in pcm:
            add(str(x))
    if row is not None:
        add(str(row.get("title") or ""))
    return acc


def _douban_row_by_title(title: str):
    """按中文片名在豆瓣 CSV 中查找一行（用于卡片类型/评分）。"""
    df = _cache.get("douban_movies")
    if df is None or df.empty:
        return None
    t = (title or "").strip()
    if not t:
        return None
    try:
        m = df[df["title"] == t]
        if m is not None and not m.empty:
            return m.iloc[0]
        t2 = t.replace("_", " ")
        m = df[df["title"] == t2]
        if m is not None and not m.empty:
            return m.iloc[0]
    except Exception:
        return None
    return None


def _movie_card_fields_incomplete(m: dict) -> bool:
    pu = str(m.get("poster_url") or "").strip()
    gs = str(m.get("genres_str") or "").strip()
    ss = str(m.get("score_str") or "").strip()
    return (not pu) or (not gs) or (not ss)


def _recommend_card_quality_first() -> bool:
    """卡片补全优先质量（单次 TMDB 请求更长超时、多片名尝试）。RECOMMEND_CARD_QUALITY_FIRST=0 可关闭。

    注意：TMDB_SEARCH_TIMEOUT / detail 超时指「每一次」HTTP 请求的最长等待，
    不是「所有影片搜完」的总时长；多部影片会多次请求，总耗时会累加。
    """
    return (os.getenv("RECOMMEND_CARD_QUALITY_FIRST") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _recommend_card_enrich_cap() -> int:
    try:
        n = int((os.getenv("RECOMMEND_CARD_ENRICH_MAX") or "24").strip())
    except ValueError:
        n = 24
    return max(4, min(40, n))


def _prefill_card_from_rag_chroma_meta(m: dict) -> None:
    """RAG 向量库 metadata（豆瓣/TMDB 入库字段）优先写到卡片，避免被 enrich 清空后丢失。"""
    meta = m.get("rag_metadata")
    if not isinstance(meta, dict):
        meta = {}
    g = str(meta.get("genres") or m.get("rag_genres_hint") or "").strip()
    if g:
        m["genres_str"] = g.replace(" / ", "/").replace("、", "/")
    r = meta.get("rating")
    if r is None or not str(r).strip():
        r = meta.get("score")
    if r is not None and str(r).strip():
        m["score_str"] = str(r).strip()[:8]
    y = str(meta.get("year") or "").strip()
    if y and not str(m.get("release_year") or "").strip():
        m["release_year"] = y[:4]
    # 简介：若 Chroma 未单独存 overview，留给后续 TMDB
    cnt = str(meta.get("country") or "").strip()
    if cnt and not str(m.get("region_hint") or "").strip():
        m["region_hint"] = cnt[:80]


def _tmdb_backfill_title_variants(m: dict, titles: list[str]) -> None:
    """按多个片名依次尝试 TMDB 搜索+详情，直到卡片字段较完整或候选用尽。"""
    seen: set[str] = set()
    qf = _recommend_card_quality_first()
    try:
        st = float((os.getenv("TMDB_SEARCH_TIMEOUT") or ("22" if qf else "8")).strip())
    except ValueError:
        st = 22.0 if qf else 8.0
    dt = 28.0 if qf else 6.0
    for raw in titles:
        qt = (raw or "").strip()
        if not qt or qt in seen:
            continue
        seen.add(qt)
        before_inc = _movie_card_fields_incomplete(m)
        before_bl = not str(m.get("short_review") or "").strip()
        _tmdb_backfill_movie_card(m, query_title=qt, search_timeout=st, detail_timeout=dt)
        if not before_inc and not before_bl:
            break
        if not _movie_card_fields_incomplete(m) and str(m.get("short_review") or "").strip():
            break


def _overview_to_blurb(overview: str, *, limit: int = 90) -> str:
    s = (overview or "").strip().replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\s{2,}", " ", s).strip()
    if not s:
        return ""
    if len(s) <= limit:
        return s
    # 尽量在标点处截断
    cut = s[: limit + 1]
    for sep in ("。", "！", "？", ".", "!", "?", "；", ";", "，", ",", "、"):
        pos = cut.rfind(sep)
        if pos >= max(18, limit - 25):
            return cut[: pos + 1].strip()
    return (s[:limit].rstrip("，,;；") + "…").strip()


def _tmdb_backfill_movie_card(
    m: dict,
    *,
    query_title: str,
    search_timeout: Optional[float] = None,
    detail_timeout: Optional[float] = None,
) -> None:
    """
    卡片字段兜底：本地/缓存仍缺海报、类型或评分且已配置 TMDB 时，
    先尝试 tmdb_id 的 detail；否则按片名 search + detail。
    可用 RECOMMEND_TMDB_BACKFILL=0 关闭。

    search_timeout / detail_timeout：单次 requests 超时（秒），非全库总时长。
    """
    if (os.getenv("RECOMMEND_TMDB_BACKFILL") or "1").strip().lower() in ("0", "false", "no", "off"):
        return
    if not tmdb_configured() or not (_movie_card_fields_incomplete(m) or (not str(m.get("short_review") or "").strip())):
        return
    qt = (query_title or "").strip()
    tid_i = 0
    try:
        if m.get("tmdb_id") is not None and str(m.get("tmdb_id")).strip():
            tid_i = int(m.get("tmdb_id"))
    except Exception:
        tid_i = 0
    if search_timeout is None:
        try:
            search_timeout = float(
                (os.getenv("TMDB_SEARCH_TIMEOUT") or ("22" if _recommend_card_quality_first() else "8")).strip()
            )
        except ValueError:
            search_timeout = 22.0 if _recommend_card_quality_first() else 8.0
    if detail_timeout is None:
        detail_timeout = 28.0 if _recommend_card_quality_first() else 6.0
    if tid_i <= 0 and not qt:
        return
    d = None
    if tid_i > 0:
        d = tmdb_movie_detail(tid_i, timeout=detail_timeout) or {}
    elif qt:
        fr = search_movie_first(
            qt, timeout=min(45.0, max(4.0, search_timeout)), log_errors=False
        )
        if fr and fr.get("id"):
            try:
                tid_i = int(fr.get("id"))
                if tid_i > 0 and m.get("tmdb_id") in (None, "", 0, False):
                    m["tmdb_id"] = tid_i
            except Exception:
                tid_i = 0
            if tid_i > 0:
                d = tmdb_movie_detail(tid_i, timeout=detail_timeout) or {}
    if not d:
        return
    if not str(m.get("genres_str") or "").strip():
        m["genres_str"] = tmdb_genres_cn(d.get("genres") or [])
    if not str(m.get("score_str") or "").strip():
        va = d.get("vote_average")
        if va is not None:
            m["score_str"] = str(va)[:4]
    if not str(m.get("poster_url") or "").strip():
        pp = d.get("poster_path")
        if pp:
            m["poster_url"] = f"https://image.tmdb.org/t/p/w500{pp}"
    # 提取上映年份
    if not str(m.get("release_year") or "").strip():
        rd = str(d.get("release_date") or "").strip()
        if len(rd) >= 4:
            m["release_year"] = rd[:4]

    # 不走大模型时：用 TMDB overview 当作短评/简介
    if (os.getenv("RECOMMEND_BLURB_FROM_TMDB_OVERVIEW") or "1").strip().lower() not in ("0", "false", "no", "off"):
        if not str(m.get("short_review") or "").strip():
            bl = _overview_to_blurb(str(d.get("overview") or ""))
            if bl:
                m["short_review"] = bl


def _enrich_single_card(m: dict, *, allow_remote_poster: bool = True) -> None:
    """补全单部电影的卡片信息（海报/类型/评分/简介）。"""
    from backend.services.poster_service import resolve_movie_poster, resolve_movie_poster_cached_only

    if not isinstance(m, dict):
        return
    disp = (m.get("display") or m.get("name") or "").strip()
    nm = (m.get("name") or "").strip()
    src = (m.get("source") or "").strip()
    m["poster_url"] = None
    m["genres_str"] = ""
    m["score_str"] = ""
    m.setdefault("short_review", "")
    _prefill_card_from_rag_chroma_meta(m)
    try:
        if src == "recent" and m.get("tmdb_id"):
            pu = str(m.get("poster_url") or "").strip()
            if pu.startswith("/api/tmdb-home-poster/"):
                m["poster_url"] = pu
            elif pu.startswith("http"):
                m["poster_url"] = pu if allow_remote_poster else None
            else:
                m["poster_url"] = None
            gtxt = str(m.get("genres") or "").strip()
            if gtxt:
                m["genres_str"] = gtxt.replace("、", "/")
            sc = str(m.get("score") or "").strip()
            if sc:
                m["score_str"] = sc[:4]
            _tmdb_backfill_movie_card(m, query_title=disp.replace("_", " ") or nm.replace("_", " "))
            return
        row = _douban_row_by_title(disp)
        if row is None:
            row = _douban_row_by_title(nm)
        pal = _poster_cache_alias_list(m, row)
        if src == "kg" and nm:
            stem = re.sub(r"_\(\d{4}_film\)$", "", nm, flags=re.I)
            stem = re.sub(r"_\(film\)$|_\(movie\)$", "", stem, flags=re.I)
            spaced = stem.replace("_", " ").strip()
            if spaced and spaced not in pal:
                pal.append(spaced)
        if row is not None:
            st = row.get("type_simplified")
            if isinstance(st, list):
                m["genres_str"] = "/".join(st)
            elif isinstance(st, str) and st.strip():
                m["genres_str"] = st.strip()
            sc = row.get("score")
            m["score_str"] = str(sc) if pd.notna(sc) else ""
            if allow_remote_poster:
                pv = resolve_movie_poster(disp, cache_aliases=pal) or resolve_movie_poster(
                    disp.replace("_", " "), cache_aliases=pal
                )
            else:
                pv = resolve_movie_poster_cached_only(disp, cache_aliases=pal) or resolve_movie_poster_cached_only(
                    disp.replace("_", " "), cache_aliases=pal
                )
            if pv:
                m["poster_url"] = pv
        else:
            ghint = str(m.get("rag_genres_hint") or "").strip()
            if ghint:
                m["genres_str"] = ghint.replace(" / ", "/")
            else:
                glist = get_movie_genres(nm or disp)
                if glist:
                    m["genres_str"] = "/".join(glist[:6])
            if allow_remote_poster:
                pv = resolve_movie_poster(disp.replace("_", " "), cache_aliases=pal) or resolve_movie_poster(
                    nm, cache_aliases=pal
                )
            else:
                pv = resolve_movie_poster_cached_only(
                    disp.replace("_", " "), cache_aliases=pal
                ) or resolve_movie_poster_cached_only(nm, cache_aliases=pal)
            if pv:
                m["poster_url"] = pv
        q0 = disp.replace("_", " ") or nm.replace("_", " ")
        tmdb_try_titles: list[str] = []
        for x in (q0, disp, nm.replace("_", " "), *pal):
            t = (x or "").strip()
            if t and t not in tmdb_try_titles:
                tmdb_try_titles.append(t)
        rm = m.get("rag_metadata")
        if isinstance(rm, dict):
            for k in ("title", "en_title", "original_title"):
                t = str(rm.get(k) or "").strip()
                if t and t not in tmdb_try_titles:
                    tmdb_try_titles.append(t)
        _tmdb_backfill_title_variants(m, tmdb_try_titles)
        if (os.getenv("RECOMMEND_POSTER_API_FALLBACK") or "1").strip().lower() not in ("0", "false", "no", "off"):
            if not str(m.get("poster_url") or "").strip():
                try:
                    pv2 = resolve_movie_poster(disp.replace("_", " "), cache_aliases=pal) or resolve_movie_poster(
                        nm, cache_aliases=pal
                    )
                    if pv2:
                        m["poster_url"] = pv2
                except Exception:
                    pass
    except Exception as ex:
        print(f"⚠️  [推荐] 卡片补全异常: {str(ex)[:120]}")


def enrich_final_movie_cards(movies: list, *, allow_remote_poster: bool = True) -> None:
    """为推荐结果前若干条补充海报、类型串、评分（并行处理，减少 TMDB 串行等待）。"""
    valid = [m for m in (movies or []) if isinstance(m, dict)]
    if not valid:
        return
    if len(valid) <= 2:
        # 少量电影直接串行，避免线程开销
        for m in valid:
            _enrich_single_card(m, allow_remote_poster=allow_remote_poster)
    else:
        with ThreadPoolExecutor(max_workers=min(len(valid), 6)) as ex:
            list(ex.map(lambda m: _enrich_single_card(m, allow_remote_poster=allow_remote_poster), valid))


# --- 展示名与类型 ---


def get_movie_display_name(entity_name: str):
    """获取电影的显示名称（处理中文映射和 (film) 后缀）"""
    name_without_film = entity_name.replace("_(film)", "").replace("(film)", "")
    if name_without_film in MOVIE_NAME_MAPPING:
        return MOVIE_NAME_MAPPING[name_without_film]
    display_name = entity_name.replace("_(film)", "").replace("(film)", "")
    display_name = display_name.replace("_", " ")
    return display_name


def get_movie_genres(entity_name: str) -> list:
    """获取电影的类型列表"""
    genres = []
    entity_relations = _cache.get("entity_relations", {})
    for rel, tail in entity_relations.get(entity_name, []):
        if rel == "genre":
            genre_name = tail.rstrip(">").rsplit("/", 1)[-1]
            if genre_name in MOVIE_GENRE_MAPPING:
                genres.append(MOVIE_GENRE_MAPPING[genre_name])
            else:
                genres.append(genre_name)

    if not genres:
        douban_movies = _cache.get("douban_movies", pd.DataFrame())
        if not douban_movies.empty:
            display_name = get_movie_display_name(entity_name)
            matched = douban_movies[
                douban_movies["title"].str.contains(
                    display_name, na=False, case=False, regex=False
                )
            ]
            if len(matched) > 0:
                types_list = matched.iloc[0]["type_simplified"]
                if isinstance(types_list, list):
                    genres.extend(types_list)

    return genres


def _hints_from_history_genres(history_genres: list) -> list[str]:
    out: list[str] = []
    if not history_genres:
        return out
    for item in history_genres[:12]:
        if isinstance(item, dict):
            g = item.get("genres") or ""
            if g:
                out.append(str(g))
        elif item:
            out.append(str(item))
    return out


def _watched_exclude_sets(watched_items: list) -> Tuple[set, set]:
    """返回 (图谱实体短名集合, 豆瓣/展示片名片名字符串集合)，用于从推荐结果中剔除。"""
    titles: set = set()
    entities: set = set()
    for it in watched_items or []:
        raw = (it.get("movie_name") or "").strip()
        if not raw:
            continue
        titles.add(raw)
        titles.add(raw.replace("_", " "))
        mapped = find_entity_in_kg(raw)
        if mapped:
            entities.add(mapped)
    return entities, titles


def _feedback_exclude_sets(user_id: int) -> Tuple[set, set, set]:
    """
    返回 (blocked_titles, disliked_titles, liked_titles) 三个集合，用于推荐过滤/加权。
    仅按 movie_name 维度做集合；对 KG 实体短名的排除仍由 find_entity_in_kg 兜底映射。
    """
    blocked: set = set()
    disliked: set = set()
    liked: set = set()
    try:
        rows = feedback_list(user_id, vote=None, blocked=None, limit=800) or []
    except Exception:
        rows = []
    for r in rows:
        nm = (r.get("movie_name") or "").strip()
        if not nm:
            continue
        nm2 = nm.replace("_", " ")
        if int(r.get("blocked") or 0) == 1:
            blocked.add(nm)
            blocked.add(nm2)
        v = (r.get("vote") or "").strip().lower()
        if v == "dislike":
            disliked.add(nm)
            disliked.add(nm2)
        elif v == "like":
            liked.add(nm)
            liked.add(nm2)
    return blocked, disliked, liked


def recommend_for_user(
    user_id: int,
    user_input: str,
    favorite_movies: list,
    watched_items: list,
    history_genres: list,
    history_movies: Optional[list] = None,
    recent_pool: Optional[list] = None,
    topk_kg: int = 6,
    topk_rag: int = 6,
    verbose: bool = True,
    with_llm_explain: bool = True,
    fast_llm: bool = False,
    progress_cb=None,
    phased_cards: bool = False,
    defer_optional_llm: bool = False,
    on_cards_ready: Optional[Callable[[dict], None]] = None,
    exclude_display_titles: Optional[list[str]] = None,
):
    """为用户生成推荐：收藏 + 用户勾选「已看过」参与种子与 RAG 偏好，但已看过影片不会出现在最终推荐列表中。"""
    try:
        start = time.time()
        pipeline: list = []
        llm_drop_norm: set[str] = set()
        t_step = time.time()
        _exclude_norm: set[str] = set()
        for x in exclude_display_titles or []:
            if isinstance(x, str) and x.strip():
                _exclude_norm.add(_norm_title_for_dedupe(x.strip()))

        def _progress(step: int, text: str):
            try:
                if progress_cb:
                    progress_cb(int(step), str(text))
            except Exception:
                pass

        watched_names = [
            (it.get("movie_name") or "").strip()
            for it in (watched_items or [])
            if it.get("movie_name")
        ]

        # 0) 大模型先做偏好分解（仅用于增强 KG/RAG；展示在管理员的 pipeline）
        decompose = {"ok": False, "data": {}, "error": "", "ms": 0}
        decompose_data: dict = {}
        extra_genres: list[str] = []
        extra_movies: list[str] = []
        must_constraints: list[str] = []
        soft_constraints: list[str] = []
        _progress(0, "分解偏好（大模型）")
        decompose = llm_decompose_preferences(
            user_input=user_input or "",
            favorite_movies=list(favorite_movies) if favorite_movies else [],
            watched_names=watched_names,
            history_genre_hints=history_genres or [],
            history_movies=history_movies,
            recent_pool=recent_pool,
        )
        decompose_data = (decompose.get("data") or {}) if decompose.get("ok") else {}
        extra_genres = [
            g
            for g in (decompose_data.get("liked_genres") or [])
            if isinstance(g, str) and g in ALLOWED_GENRES
        ]
        extra_movies = [
            m
            for m in (decompose_data.get("liked_movies") or [])
            if isinstance(m, str) and m.strip()
        ]
        must_constraints = [
            c
            for c in (decompose_data.get("must_have_constraints") or [])
            if isinstance(c, str) and c.strip()
        ]
        soft_constraints = [
            c
            for c in (decompose_data.get("soft_constraints") or [])
            if isinstance(c, str) and c.strip()
        ]
        _rel_ct = len(
            [r for r in (decompose_data.get("relations") or []) if isinstance(r, str) and r.strip()]
        )
        _c_ct = len(
            [c for c in (decompose_data.get("constraints") or []) if isinstance(c, str) and c.strip()]
        )
        pipeline.append(
            {
                "id": "llm_decompose",
                "title": "大模型分解偏好（头实体/关系/尾实体）",
                "call_kind": "llm",
                "status": "ok" if decompose.get("ok") else "warn",
                "message": (
                    (
                        f"偏好分解完成：归纳可映射类型 {len(extra_genres)} 项、候选偏好影片 {len(extra_movies)} 部，"
                        f"关系线索 {_rel_ct} 条、约束要点 {_c_ct} 条（硬约束 {len(must_constraints)}，软偏好 {len(soft_constraints)}）；"
                        "用于后续图谱关系偏好与 RAG 查询增强。"
                    )
                    if decompose.get("ok")
                    else (decompose.get("error") or "未生成")
                ),
                "elapsed_ms": int(decompose.get("ms") or 0),
            }
        )
        t_step = time.time()

        # 将大模型解析出的关系映射到 KG 可用关系短名
        _progress(1, "构建种子与偏好约束")
        rel_pref: list[str] = []
        _rel_map = {
            "director": "director",
            "导演": "director",
            "actor": "starring",
            "演员": "starring",
            "starring": "starring",
            "genre": "genre",
            "类型": "genre",
            "country": "country",
            "国家": "country",
            "language": "language",
            "语言": "language",
            "writer": "writer",
            "编剧": "writer",
            "producer": "producer",
            "制片": "producer",
            "musiccomposer": "musicComposer",
            "配乐": "musicComposer",
            "similar_to": "related",
            "similar": "related",
            "related": "related",
        }
        for r in (decompose_data.get("relations") or []):
            if not isinstance(r, str):
                continue
            k = r.strip()
            if not k:
                continue
            mapped = _rel_map.get(k) or _rel_map.get(k.lower())
            if mapped and mapped not in rel_pref:
                rel_pref.append(mapped)

        # constraints 里若显式提到"更看重类型/导演/演员"，也加入优先关系
        for c in (decompose_data.get("constraints") or []) + must_constraints + soft_constraints:
            if not isinstance(c, str):
                continue
            s = c.strip()
            if not s:
                continue
            if ("类型" in s or "题材" in s) and "genre" not in rel_pref:
                rel_pref.insert(0, "genre")
            if ("导演" in s) and "director" not in rel_pref:
                rel_pref.insert(0, "director")
            if ("演员" in s or "主演" in s) and "starring" not in rel_pref:
                rel_pref.insert(0, "starring")

        movies_from_input = []
        for movie in MOVIE_NAME_MAPPING.keys():
            if movie.lower() in user_input.lower():
                movies_from_input.append(movie)
        # 解析出的偏好影片做弱匹配补充（别名/中英混写情况下更稳）
        for nm in extra_movies:
            for k in MOVIE_NAME_MAPPING.keys():
                if k.lower() in nm.lower() or nm.lower() in k.lower():
                    if k not in movies_from_input:
                        movies_from_input.append(k)
        # 大模型给出的"中文片名 -> 英文实体候选"直接并入种子映射尝试
        cand_en = decompose_data.get("movie_entity_candidates_en") or {}
        if isinstance(cand_en, dict):
            for _zh, arr in cand_en.items():
                if not isinstance(arr, list):
                    continue
                for en in arr[:5]:
                    if isinstance(en, str) and en.strip() and en.strip() not in movies_from_input:
                        movies_from_input.append(en.strip())

        seed_movies = []
        seed_movie_weights = {}

        for fav in favorite_movies:
            fav_name = fav if isinstance(fav, str) else (fav.get("movie_name") or fav.get("name") or fav.get("title") or "")
            if not fav_name:
                continue
            matched = find_entity_in_kg(fav_name)
            if matched:
                seed_movies.append(matched)
                seed_movie_weights[matched] = 3.0

        # 浏览/点击次数信号：常点的电影给较低权重补充（避免盖过收藏）
        for it in history_movies or []:
            try:
                raw = (it.get("movie_name") or "").strip()
                if not raw:
                    continue
                matched = find_entity_in_kg(raw)
                if not matched:
                    continue
                vc = it.get("view_count") or 0
                try:
                    vc = int(vc)
                except Exception:
                    vc = 0
                # 1~3 次：轻微；更高次数：逐步增强，但不超过收藏权重
                w = 1.2 + min(1.4, (vc ** 0.5) * 0.35)
                if matched not in seed_movies:
                    seed_movies.append(matched)
                    seed_movie_weights[matched] = w
                else:
                    seed_movie_weights[matched] = max(seed_movie_weights.get(matched, 0.0), w)
            except Exception:
                continue

        for w in watched_items or []:
            movie_name = (w.get("movie_name") or "").strip()
            if not movie_name:
                continue
            matched = find_entity_in_kg(movie_name)
            if matched:
                if matched not in seed_movies:
                    seed_movies.append(matched)
                    seed_movie_weights[matched] = 2.4
                else:
                    seed_movie_weights[matched] += 0.8

        for movie in movies_from_input:
            matched = find_entity_in_kg(movie)
            if matched:
                if matched not in seed_movies:
                    seed_movies.append(matched)
                    seed_movie_weights[matched] = 4.0
                else:
                    seed_movie_weights[matched] += 1.0

        seed_msg = (
            f"种子构建：输入侧含收藏 {len(favorite_movies)} 部、「已看过」{len(watched_items or [])} 部、"
            f"浏览行为影片 {len(history_movies or [])} 部；经片名→实体对齐得到图谱种子实体 {len(seed_movies)} 个（含权重），"
            f"供 Multi_MoE 链路预测与后续合并排序使用。"
        )
        if not seed_movies and (favorite_movies or (watched_items or [])):
            seed_msg += (
                " 提示：若片名无法对齐到 DB15K 电影实体，图谱一路可能无输出（数据覆盖限制，属正常现象）。"
            )
        pipeline.append(
            {
                "id": "seeds",
                "title": "偏好解析与种子构建",
                "status": "warn"
                if ((favorite_movies or (watched_items or [])) and not seed_movies)
                else "ok",
                "message": seed_msg,
                "elapsed_ms": int((time.time() - t_step) * 1000),
            }
        )
        t_step = time.time()

        genre_hints: list[str] = _hints_from_history_genres(history_genres or [])
        for g in extra_genres:
            if g and g not in genre_hints:
                genre_hints.insert(0, g)

        kg_movies = []
        kg_model_note = ""
        kg_moe_meta: dict = {}
        exclude_entities, exclude_titles = _watched_exclude_sets(watched_items)
        _progress(2, "读取反馈信号（喜欢/不喜欢/屏蔽）")
        blocked_titles, disliked_titles, liked_titles = _feedback_exclude_sets(user_id)
        # 反馈中若是 KG 可映射实体，也加入实体排除（用于 kg_movies 阶段更早剔除）
        blocked_entities = set()
        for nm in list(blocked_titles)[:400]:
            mapped = find_entity_in_kg(nm)
            if mapped:
                blocked_entities.add(mapped)
        pipeline.append(
            {
                "id": "feedback",
                "title": "用户反馈信号（喜欢/不喜欢/屏蔽）",
                "status": "ok",
                "message": (
                    f"反馈库已加载：点赞 {len(liked_titles)//2} 部、点踩 {len(disliked_titles)//2} 部、"
                    f"屏蔽 {len(blocked_titles)//2} 部（片名去重口径）；"
                    f"点踩与屏蔽对应影片将在后续候选与定榜中剔除。"
                ),
                "elapsed_ms": int((time.time() - t_step) * 1000),
            }
        )
        t_step = time.time()

        rag_query = user_input or ""
        if genre_hints:
            genre_str = "、".join(genre_hints[:5])
            rag_query = f"{rag_query}。偏好类型：{genre_str}"
        if watched_names:
            rag_query = (
                f"{rag_query}。用户已看过（表示口味，请勿把下列影片作为推荐结果）："
                f"{'、'.join(watched_names[:15])}"
            )
        if isinstance(decompose_data.get("query"), str) and decompose_data.get("query").strip():
            rag_query = f"{rag_query}。{decompose_data.get('query').strip()}"

        _progress(3, "片库：向量检索（图谱种子，与 RAG·LLM 共用一次 Chroma 查询）")
        try:
            _seed_pool_n = int((os.getenv("RAG_SEED_POOL") or "28").strip())
        except ValueError:
            _seed_pool_n = 28
        _seed_pool_n = max(8, min(64, _seed_pool_n))
        _chroma_n = rag_combined_chroma_n_results(_seed_pool_n)
        shared_vector_rows, fetch_diag = rag_fetch_shared_vector_rows(
            rag_query, n_results=_chroma_n
        )
        rag_seed_candidates, seed_diag = rag_retrieve_for_kg_seeds(
            rag_query,
            genre_hints=genre_hints,
            max_candidates=_seed_pool_n,
            shared_vector_rows=shared_vector_rows,
            fetch_diag=fetch_diag,
        )
        rag_seed_for_align = [
            m
            for m in rag_seed_candidates
            if (m.get("name") or "").strip() not in exclude_titles
        ]
        try:
            rag_seed_w = float((os.getenv("KG_RAG_SEED_WEIGHT") or "1.2").strip())
        except ValueError:
            rag_seed_w = 1.2
        rag_seed_hits = 0
        for movie_info in rag_seed_for_align:
            nm = (movie_info.get("name") or "").strip()
            if not nm or nm in blocked_titles or nm in disliked_titles:
                continue
            ent = find_entity_in_kg(nm)
            if ent and ent not in exclude_entities and ent not in blocked_entities:
                rag_seed_hits += 1
                if ent not in seed_movies:
                    seed_movies.append(ent)
                    seed_movie_weights[ent] = rag_seed_w
                else:
                    seed_movie_weights[ent] = max(
                        float(seed_movie_weights.get(ent, 1.0)), rag_seed_w
                    )
        _seed_msg_parts = [
            f"种子池 {len(rag_seed_candidates)} 条（对齐用 {len(rag_seed_for_align)} 条）；"
            f"{rag_seed_hits} 条对齐为图谱实体并并入 MoE。"
        ]
        if seed_diag.get("shared_chroma_query"):
            _seed_msg_parts.append(f"单次 Chroma 拉取 {_chroma_n} 条（与下一步 RAG·LLM 共用）。")
        if not seed_diag.get("chroma_available"):
            _seed_msg_parts.append("Chroma 未就绪，豆瓣补位。")
        elif seed_diag.get("vector_error"):
            _seed_msg_parts.append(f"向量提示：{str(seed_diag['vector_error'])[:120]}")
        elif int(seed_diag.get("n_vector") or 0) == 0:
            _seed_msg_parts.append("向量无命中，豆瓣补位。")
        else:
            _seed_msg_parts.append(f"向量命中 {int(seed_diag.get('n_vector') or 0)} 条。")
        pipeline.append(
            {
                "id": "rag_seeds",
                "title": "片库 · 向量检索 → 图谱种子（MoE）",
                "status": "ok" if rag_seed_candidates else "warn",
                "message": " ".join(_seed_msg_parts),
                "elapsed_ms": int((time.time() - t_step) * 1000),
            }
        )
        t_step = time.time()

        rag_exclude = set(exclude_titles) | set(blocked_titles) | set(disliked_titles)
        def _run_rag_call():
            rm, rd = rag_llm_recommend(
                rag_query,
                topk_rag,
                genre_hints=genre_hints,
                exclude_titles=rag_exclude,
                fast_llm=fast_llm,
                shared_vector_rows=shared_vector_rows,
                fetch_diag=fetch_diag,
            )
            rm = [m for m in rm if (m.get("name") or "").strip() not in exclude_titles]
            for m in rm:
                m.pop("_rag_rank_score", None)
            return rm, rd

        def _run_kg_call():
            try:
                _km = float((os.getenv("KG_MOE_RECALL_MULT") or "3").strip())
            except ValueError:
                _km = 3.0
            kg_moe_topk = max(12, int(topk_kg * _km), int(topk_kg))
            try:
                mh = int((os.getenv("KG_MULTIHOP_MOE", "1") or "1").strip())
            except ValueError:
                mh = 1
            try:
                bridge_n = int((os.getenv("KG_MULTIHOP_BRIDGE", "4") or "4").strip())
            except ValueError:
                bridge_n = 4
            bridge_n = max(1, bridge_n)

            moe_seeds = list(dict.fromkeys(seed_movies))
            w_moe = {k: float(v) for k, v in seed_movie_weights.items()}
            bridge_from_graph: list[str] = []
            inter_from_graph: list[str] = []
            if mh >= 1:
                bridge_from_graph = structural_bridge_seeds(
                    moe_seeds,
                    max_bridges=bridge_n,
                    per_seed=max(12, bridge_n * 3),
                )
                bridge_from_graph = [b for b in bridge_from_graph if b not in blocked_entities]
                for b in bridge_from_graph:
                    if b not in moe_seeds:
                        moe_seeds.append(b)
                    w_moe[b] = min(2.2, float(w_moe.get(b, 1.0)) * 0.72)
                if (os.getenv("KG_INTERMEDIATE_MOE", "1") or "1").strip().lower() not in (
                    "0",
                    "false",
                    "no",
                    "off",
                ):
                    try:
                        imax = int((os.getenv("KG_INTERMEDIATE_MAX", "12") or "12").strip())
                    except ValueError:
                        imax = 12
                    try:
                        ipm = int((os.getenv("KG_INTERMEDIATE_PER_MOVIE", "24") or "24").strip())
                    except ValueError:
                        ipm = 24
                    imax = max(1, min(32, imax))
                    ipm = max(8, min(64, ipm))
                    inter_from_graph, inter_w = intermediate_moe_seeds_from_movies(
                        moe_seeds,
                        max_seeds=imax,
                        per_movie=ipm,
                        blocked=blocked_entities,
                    )
                    for t in inter_from_graph:
                        if t not in moe_seeds:
                            moe_seeds.append(t)
                        w_moe[t] = min(2.2, max(float(inter_w.get(t, 0.36)), float(w_moe.get(t, 0.0))))
                kg_moe_topk_eff = max(kg_moe_topk * 2, 24)
            else:
                kg_moe_topk_eff = kg_moe_topk

            km, kn, km_meta = moe_link_prediction_recommend(
                moe_seeds,
                kg_moe_topk_eff,
                user_input=user_input or "",
                genre_hints=genre_hints,
                preferred_relations=rel_pref,
                max_relations=10,
                seed_weights=w_moe,
            )
            km = [m for m in km if m not in exclude_entities]
            if mh >= 1 and bridge_from_graph:
                kn = (kn or "") + (
                    f" 单次预测：已并入图谱 1 跳电影桥接 {len(bridge_from_graph)} 个（弱权重），"
                    f"与用户行为及 RAG 对齐种子同批 forward。"
                )[:280]
            if mh >= 1 and inter_from_graph:
                kn = (kn or "") + (
                    f" 中间实体种子 {len(inter_from_graph)} 个（主演/导演等，按与种子片共现加权），"
                    f"用于从人/职员实体再预测电影。"
                )[:220]
            graph_extra = _graph_expand_kg_neighbors(km[:8], moe_seeds, cap=18, per_bridge=12)
            ge_used = 0
            for ge in graph_extra:
                if ge not in km and ge not in exclude_entities and ge not in blocked_entities:
                    km.append(ge)
                    ge_used += 1
            if ge_used:
                kn = (kn or "") + f" 图1跳扩展+{ge_used}。"
            return km, kn, km_meta

        rag_t0 = time.time()
        kg_t0 = time.time()
        if seed_movies:
            _progress(4, "并行召回（RAG + KG）")
            with ThreadPoolExecutor(max_workers=2) as ex:
                f_rag = ex.submit(_run_rag_call)
                f_kg = ex.submit(_run_kg_call)
                rag_movies, rag_diag = f_rag.result()
                kg_movies, kg_model_note, kg_moe_meta = f_kg.result()
            kg_elapsed_ms = int((time.time() - kg_t0) * 1000)
        else:
            _progress(4, "片库：RAG 检索 + LLM 生成片库候选")
            rag_movies, rag_diag = _run_rag_call()
            kg_elapsed_ms = 0

        _rag_msg_parts = [
            f"片库 RAG 输出 {len(rag_movies)} 条（主路 source=rag_llm；回退补位可为 douban_fallback）。"
        ]
        if rag_diag.get("llm_ok"):
            _rag_msg_parts.append("大模型已按证据编号选片并生成理由。")
        elif rag_diag.get("rag_llm_fallback"):
            _rag_msg_parts.append(f"生成回退：{str(rag_diag.get('rag_llm_fallback'))[:120]}。")
        if not rag_diag.get("chroma_available"):
            _rag_msg_parts.append("Chroma 未就绪，以豆瓣/检索直出补位。")
        elif rag_diag.get("n_retrieved", 0) == 0 and not rag_diag.get("vector_error"):
            _rag_msg_parts.append("无检索证据。")
        elif rag_diag.get("vector_error") and not rag_diag.get("llm_ok"):
            _rag_msg_parts.append(f"向量：{str(rag_diag.get('vector_error'))[:100]}")
        pipeline.append(
            {
                "id": "rag_llm",
                "title": "片库 · 标准 RAG（向量证据 → LLM 生成推荐）",
                "call_kind": "llm" if (rag_diag.get("llm_ok") or rag_diag.get("llm_ms")) else "code",
                "status": "ok" if rag_movies else "warn",
                "message": " ".join(_rag_msg_parts),
                "elapsed_ms": int((time.time() - rag_t0) * 1000),
            }
        )
        t_step = time.time()

        pipeline.append(
            {
                "id": "kg",
                "title": "知识图谱一路（Multi_MoE · 四分支平均 + 中间实体 + 图扩展）",
                "status": "ok" if kg_movies else "skip",
                "message": (kg_model_note or "")
                + (f" 共 {len(kg_movies)} 个电影实体。" if kg_movies else " 本路无输出。"),
                "elapsed_ms": int(kg_elapsed_ms),
            }
        )
        t_step = time.time()

        _progress(6, "合并与加权排序")
        final_movies = []
        seen = set()
        movie_entities = _cache.get("movie_entities", set())

        for movie in kg_movies:
            if movie in exclude_entities or movie in blocked_entities:
                continue
            if movie not in seen and movie in movie_entities:
                display_name = get_movie_display_name(movie)
                if display_name in blocked_titles or display_name in disliked_titles:
                    continue
                if _exclude_norm and _norm_title_for_dedupe(display_name) in _exclude_norm:
                    continue
                final_movies.append(
                    {"name": movie, "source": "kg", "display": display_name, "weight": 1.0}
                )
                seen.add(movie)

        for movie_info in rag_movies:
            movie_name = movie_info["name"]
            if movie_name in exclude_titles or movie_name in blocked_titles or movie_name in disliked_titles:
                continue
            if _exclude_norm and _norm_title_for_dedupe(movie_name) in _exclude_norm:
                continue
            if movie_name not in seen:
                meta = movie_info.get("metadata") or {}
                tid_raw = meta.get("tmdb_id")
                tmdb_id_val = None
                if tid_raw is not None and str(tid_raw).strip():
                    try:
                        tmdb_id_val = int(float(str(tid_raw).strip()))
                    except (TypeError, ValueError):
                        tmdb_id_val = None
                rag_genres_hint = str(meta.get("genres") or "").strip()
                entry = {
                    "name": movie_name,
                    "source": movie_info["source"],
                    "display": movie_name,
                    "weight": 0.8,
                }
                if tmdb_id_val and tmdb_id_val > 0:
                    entry["tmdb_id"] = tmdb_id_val
                if rag_genres_hint:
                    entry["rag_genres_hint"] = rag_genres_hint
                poster_aliases: list[str] = []
                pseen: set[str] = set()
                for key in ("title", "en_title", "original_title"):
                    v = str(meta.get(key) or "").strip()
                    if v and v not in pseen:
                        pseen.add(v)
                        if v != movie_name:
                            poster_aliases.append(v)
                if poster_aliases:
                    entry["poster_cache_aliases"] = poster_aliases
                if isinstance(meta, dict) and meta:
                    entry["rag_metadata"] = dict(meta)
                rr = str(movie_info.get("rag_llm_reason") or "").strip()
                if rr:
                    entry["rag_llm_reason"] = rr
                final_movies.append(entry)
                seen.add(movie_name)

        # --- 同偏好类型：从其他用户收藏中补候选（弱协同，并入 merged 池；不设单独一路）---
        peer_fav_movies: list[dict] = []
        peer_added = 0
        peer_pref_label = ""
        try:
            peer_on = (os.getenv("MOVIEHUB_PEER_FAV_ENABLE") or "1").strip().lower() not in (
                "0",
                "false",
                "no",
                "off",
            )
        except Exception:
            peer_on = True
        if peer_on:
            pref_peer = _peer_pref_genres_from_inputs(
                user_input or "",
                history_genres or [],
                genre_hints,
                extra_genres or [],
            )
            if pref_peer:
                peer_pref_label = "、".join(sorted(pref_peer)[:6])
                try:
                    peer_max = int((os.getenv("MOVIEHUB_PEER_FAV_MAX") or "24").strip())
                except ValueError:
                    peer_max = 24
                peer_max = max(4, min(48, peer_max))
                try:
                    peer_sql_lim = int((os.getenv("MOVIEHUB_PEER_FAV_SQL_LIMIT") or "160").strip())
                except ValueError:
                    peer_sql_lim = 160
                peer_sql_lim = max(40, min(400, peer_sql_lim))
                try:
                    peer_min_u = int((os.getenv("MOVIEHUB_PEER_FAV_MIN_USERS") or "1").strip())
                except ValueError:
                    peer_min_u = 1
                peer_min_u = max(1, min(20, peer_min_u))

                ex_norm_peer = set(_exclude_norm)
                for nm in list(exclude_titles or []):
                    if isinstance(nm, str) and nm.strip():
                        ex_norm_peer.add(_norm_title_for_dedupe(nm.strip()))
                for nm in list(blocked_titles or []):
                    if isinstance(nm, str) and nm.strip():
                        ex_norm_peer.add(_norm_title_for_dedupe(nm.strip()))
                for nm in list(disliked_titles or []):
                    if isinstance(nm, str) and nm.strip():
                        ex_norm_peer.add(_norm_title_for_dedupe(nm.strip()))
                for x in favorite_movies or []:
                    fn = (
                        x
                        if isinstance(x, str)
                        else (x.get("movie_name") or x.get("name") or "")
                    )
                    if isinstance(fn, str) and fn.strip():
                        ex_norm_peer.add(_norm_title_for_dedupe(fn.strip()))

                seen_norm_peer = {
                    _norm_title_for_dedupe(_movie_display_key(m))
                    for m in final_movies
                    if _movie_display_key(m)
                }

                for nm, w, gtxt in _fetch_peer_favorites_by_genre(
                    int(user_id),
                    pref_peer,
                    exclude_title_norms=ex_norm_peer,
                    limit_sql=peer_sql_lim,
                    max_take=peer_max,
                    min_distinct_users=peer_min_u,
                ):
                    if nm in seen:
                        continue
                    nn = _norm_title_for_dedupe(nm)
                    if nn and nn in seen_norm_peer:
                        continue
                    if (
                        nm in exclude_titles
                        or nm in blocked_titles
                        or nm in disliked_titles
                    ):
                        continue
                    if _is_noise_movie({"display": nm, "name": nm}):
                        continue
                    entry_pf = {
                        "name": nm,
                        "source": "peer_fav",
                        "display": nm,
                        "weight": float(w),
                    }
                    if isinstance(gtxt, str) and gtxt.strip():
                        entry_pf["genres"] = gtxt.strip()
                    peer_fav_movies.append(
                        {
                            "name": nm,
                            "display": nm,
                            "genres": (gtxt.strip() if isinstance(gtxt, str) else "") or "",
                            "weight": float(w),
                        }
                    )
                    final_movies.append(entry_pf)
                    seen.add(nm)
                    if nn:
                        seen_norm_peer.add(nn)
                    peer_added += 1

        if peer_added > 0 and peer_pref_label:
            pipeline.append(
                {
                    "id": "peer_fav",
                    "title": "同偏好 · 他人收藏候选",
                    "call_kind": "code",
                    "status": "ok",
                    "message": (
                        f"偏好类型（{peer_pref_label}）：收集 {peer_added} 条候选（source=peer_fav）；"
                        "与片库 RAG 分开定榜，不占 topk_rag 名额，仍走大模型定榜一路。"
                    ),
                    "elapsed_ms": 0,
                }
            )

        # 「最近上映/即将上映」：与 KG/RAG **分开**，定榜后再追加 1～3 部，不占 topk_kg / topk_rag 名额
        extra_recent_movies: list[dict] = []
        used_recent = 0
        matched_recent = 0

        def _extract_preferred_genres() -> set[str]:
            s = set()
            # history_genres 可能既有 str 也有 dict（{"genres": "剧情/爱情"}）
            txt = (user_input or "") + " " + " ".join([str(x) for x in (history_genres or []) if x])
            for g in ALLOWED_GENRES:
                if g and g in txt:
                    s.add(g)
            for it in (history_genres or [])[:20]:
                if isinstance(it, dict):
                    gs = str(it.get("genres") or "")
                    for part in gs.split("/"):
                        p = part.strip()
                        if p in ALLOWED_GENRES:
                            s.add(p)
            for g in genre_hints or []:
                if isinstance(g, str) and g.strip() in ALLOWED_GENRES:
                    s.add(g.strip())
            for g in extra_genres or []:
                if isinstance(g, str) and g in ALLOWED_GENRES:
                    s.add(g)
            return s

        pref_genres = _extract_preferred_genres()
        candidates: list[dict] = []
        for it in (recent_pool or [])[:50]:
            if isinstance(it, str):
                nm = it.strip()
                if nm:
                    candidates.append(
                        {
                            "name": nm,
                            "tmdb_id": None,
                            "score": 0,
                            "genres": "",
                            "poster_url": None,
                        }
                    )
            elif isinstance(it, dict):
                nm = str(it.get("name") or it.get("title") or "").strip()
                if not nm:
                    continue
                candidates.append(
                    {
                        "name": nm,
                        "tmdb_id": it.get("tmdb_id"),
                        "score": it.get("score"),
                        "genres": str(it.get("genres") or ""),
                        "poster_url": it.get("poster_url"),
                    }
                )

        def _score_num(v) -> float:
            try:
                return float(v)
            except Exception:
                return 0.0

        candidates.sort(key=lambda x: _score_num(x.get("score")), reverse=True)

        def _append_recent_candidate(c: dict, *, genre_hit: bool) -> None:
            nonlocal used_recent, matched_recent
            nm = str(c.get("name") or "").strip()
            if (
                (not nm)
                or nm in exclude_titles
                or nm in blocked_titles
                or nm in disliked_titles
                or nm in seen
            ):
                return
            if _exclude_norm and _norm_title_for_dedupe(nm) in _exclude_norm:
                return
            gtxt = str(c.get("genres") or "").strip()
            tid_raw = c.get("tmdb_id")
            tid_i = None
            if tid_raw is not None and str(tid_raw).strip():
                try:
                    tid_i = int(tid_raw)
                except (TypeError, ValueError):
                    tid_i = None
            extra_recent_movies.append(
                {
                    "name": nm,
                    "source": "recent",
                    "display": nm,
                    "weight": 0.82 if genre_hit else 0.75,
                    "tmdb_id": tid_i,
                    "genres": gtxt,
                    "score": c.get("score"),
                    "poster_url": c.get("poster_url"),
                }
            )
            seen.add(nm)
            used_recent += 1
            if genre_hit:
                matched_recent += 1

        if recent_pool is not None and candidates:
            if pref_genres:
                for c in candidates[:30]:
                    if used_recent >= 3:
                        break
                    gset = _recent_genre_tokens_cn(str(c.get("genres") or ""))
                    if not (gset & pref_genres):
                        continue
                    _append_recent_candidate(c, genre_hit=True)
            while used_recent < 3:
                added = False
                for c in candidates:
                    if used_recent >= 3:
                        break
                    nm = str(c.get("name") or "").strip()
                    if not nm or nm in seen:
                        continue
                    if (
                        nm in exclude_titles
                        or nm in blocked_titles
                        or nm in disliked_titles
                    ):
                        continue
                    _append_recent_candidate(c, genre_hit=False)
                    added = True
                    break
                if not added:
                    break

        # --- 用户偏好强化：收藏/点赞/高频浏览 + 类型命中时显著加权 ---
        # 目标：当用户明确希望某些类型（pref_genres 非空）时，若候选电影既在用户历史偏好集合中（收藏/点赞/浏览）
        # 且类型与偏好命中，则把它推到更靠前的位置（不排除重复推荐）。
        fav_norm: set[str] = set()
        for x in favorite_movies or []:
            if isinstance(x, str) and x.strip():
                fav_norm.add(_norm_title_for_dedupe(x.strip()))
        liked_norm: set[str] = set()
        for x in liked_titles or []:
            if isinstance(x, str) and x.strip():
                liked_norm.add(_norm_title_for_dedupe(x.strip()))
        hist_view: dict[str, int] = {}
        for it in history_movies or []:
            if isinstance(it, str):
                nm = it.strip()
                vc = 1
            elif isinstance(it, dict):
                nm = str(it.get("movie_name") or "").strip()
                try:
                    vc = int(it.get("view_count") or 1)
                except Exception:
                    vc = 1
            else:
                continue
            if not nm:
                continue
            nk = _norm_title_for_dedupe(nm)
            if not nk:
                continue
            hist_view[nk] = max(int(hist_view.get(nk) or 0), max(1, int(vc)))

        def _movie_genre_tokens_cn(m: dict) -> set[str]:
            # 优先用更"片库侧"的 genres_hint / tmdb genres
            gtxt = ""
            if isinstance(m.get("rag_genres_hint"), str) and m.get("rag_genres_hint"):
                gtxt = str(m.get("rag_genres_hint") or "")
            elif isinstance(m.get("genres"), str) and m.get("genres"):
                gtxt = str(m.get("genres") or "")
            if gtxt.strip():
                return _recent_genre_tokens_cn(gtxt)
            # 兜底：从 KG / 豆瓣映射取类型
            try:
                return set(get_movie_genres(str(m.get("name") or "")) or [])
            except Exception:
                return set()

        if pref_genres:
            for m in final_movies:
                title = (m.get("display") or m.get("name") or "").strip()
                if not title:
                    continue
                nk = _norm_title_for_dedupe(title)
                if not nk:
                    continue
                gset = _movie_genre_tokens_cn(m)
                genre_hit = bool(gset & pref_genres) if gset else False
                if not genre_hit:
                    continue

                # 收藏：类型命中时强推
                if nk in fav_norm:
                    m["weight"] = float(m.get("weight") or 0.0) + 0.35

                # 点赞：在已有 +0.2 基础上，再按类型命中额外加权
                if nk in liked_norm:
                    m["weight"] = float(m.get("weight") or 0.0) + 0.25

                # 浏览：次数越高加权越大（对数增长，避免压制其它来源）
                if nk in hist_view:
                    vc = int(hist_view.get(nk) or 1)
                    m["weight"] = float(m.get("weight") or 0.0) + min(
                        0.30, 0.10 + 0.06 * math.log1p(max(1, vc))
                    )

        for movie in final_movies:
            movie_genres = get_movie_genres(movie["name"])
            for w in watched_items or []:
                hist_genre_parts = [
                    x.strip() for x in (w.get("genres") or "").split("/") if x.strip()
                ]
                common_genres = set(movie_genres) & set(hist_genre_parts)
                if common_genres:
                    movie["weight"] += 0.35

        final_movies = [
            m
            for m in final_movies
            if m.get("name") not in exclude_titles
            and m.get("name") not in exclude_entities
            and (m.get("display") or "").strip() not in exclude_titles
            and (m.get("display") or "").strip() not in blocked_titles
            and (m.get("display") or "").strip() not in disliked_titles
        ]

        # 喜欢轻微加权（不改变主逻辑，只做"产品化"偏好增强）
        for m in final_movies:
            disp = (m.get("display") or "").strip()
            if disp and disp in liked_titles:
                m["weight"] += 0.2

        if os.getenv("KG_WEIGHT_JITTER", "1").strip().lower() not in ("0", "false", "no", "off"):
            for m in final_movies:
                try:
                    m["weight"] = float(m.get("weight") or 0.0) + random.uniform(0, 0.09)
                except (TypeError, ValueError):
                    pass

        final_movies.sort(key=lambda x: x["weight"], reverse=True)

        movies_before_filter = list(final_movies)
        filtered_out: list[dict] = []
        llm_filter_text = ""
        llm_filter_error = ""

        # 规则层预过滤：剔除明显非电影噪声实体（TV serial/电视剧/书籍/音乐等）
        _noise_removed = [m for m in final_movies if _is_noise_movie(m)]
        if _noise_removed:
            filtered_out.extend(_noise_removed)
            final_movies = [m for m in final_movies if not _is_noise_movie(m)]

        pipeline.append(
            {
                "id": "merge_pre",
                "title": "三路合并与偏好加权（初榜 · KG + RAG·LLM + 稍后可附 TMDB 最近）",
                "status": "ok",
                "message": (
                    f"初榜共 {len(movies_before_filter)} 条（已排除看过/屏蔽/不喜欢）；"
                    "来源：图谱 Multi_MoE、片库 RAG（检索+LLM）、定榜后再可追加 TMDB 最近上映池。"
                    "随后大模型审核与截断定榜，再统一补全海报与卡片字段。"
                ),
                "elapsed_ms": int((time.time() - t_step) * 1000),
            }
        )
        t_step = time.time()

        # 噪声过滤已合并到定榜步骤（llm_finalize_single_lane），无需单独调用
        pipeline.append(
            {
                "id": "llm_filter",
                "title": "大模型审核过滤（规则层）",
                "call_kind": "llm",
                "status": "skip",
                "message": "已合并到定榜步骤：噪声过滤与 top-K 挑选在一次 LLM 调用中完成。",
                "elapsed_ms": 0,
            }
        )

        # 定榜：KG + 片库(RAG 等) + 同偏好他人收藏 分路定榜；peer_fav 不占 topk_rag
        _kk = max(0, int(topk_kg))
        _kr = max(0, int(topk_rag))
        t_merge = time.time()

        final_movies.sort(key=lambda x: float(x.get("weight") or 0), reverse=True)
        kg_pool = [m for m in final_movies if str(m.get("source") or "").strip() == "kg"]
        rag_lib_pool = [
            m
            for m in final_movies
            if str(m.get("source") or "").strip() not in ("kg", "peer_fav")
        ]
        peer_pool = [m for m in final_movies if str(m.get("source") or "").strip() == "peer_fav"]
        _k_peer = 0
        if peer_pool:
            try:
                _k_peer = int((os.getenv("MOVIEHUB_PEER_FAV_TOPK") or "3").strip())
            except ValueError:
                _k_peer = 3
            _k_peer = max(0, min(8, _k_peer))
        _cap_final = max(1, _kk + _kr + _k_peer)

        # 定榜：KG / 片库 / 他人收藏 分路调用 LLM；fast_llm 或无 llm_client 时仅用代码分路
        _use_llm_fin = bool(
            not fast_llm and not defer_optional_llm and llm_client
        )
        merged_base: list[dict] = []
        llm_fin_note = ""
        llm_fin_ms = 0
        llm_fin_used = False
        if _use_llm_fin:
            _peer_fin_active = bool(_k_peer > 0 and peer_pool)
            _progress(
                8,
                "大模型定榜挑选（图谱 + 片库"
                + (" + 他人收藏" if _peer_fin_active else "")
                + " 并行）",
            )
            _nw = 3 if _peer_fin_active else 2
            with ThreadPoolExecutor(max_workers=_nw) as ex:
                f_kg_fin = ex.submit(
                    llm_finalize_single_lane,
                    (user_input or "")[:1800], genre_hints, kg_pool, _kk, "kg",
                    list(exclude_display_titles or [])[:32], must_constraints, soft_constraints,
                )
                f_rag_fin = ex.submit(
                    llm_finalize_single_lane,
                    (user_input or "")[:1800], genre_hints, rag_lib_pool, _kr, "library",
                    list(exclude_display_titles or [])[:32], must_constraints, soft_constraints,
                )
                f_peer_fin = None
                if _peer_fin_active:
                    f_peer_fin = ex.submit(
                        llm_finalize_single_lane,
                        (user_input or "")[:1800], genre_hints, peer_pool, _k_peer, "peer_fav",
                        list(exclude_display_titles or [])[:32], must_constraints, soft_constraints,
                    )
                kg_fin = f_kg_fin.result()
                rag_fin = f_rag_fin.result()
                peer_fin = (
                    f_peer_fin.result()
                    if f_peer_fin is not None
                    else {"ok": True, "ms": 0, "picks": [], "note": ""}
                )
            llm_fin_ms = max(
                int(kg_fin.get("ms") or 0),
                int(rag_fin.get("ms") or 0),
                int(peer_fin.get("ms") or 0),
            )
            note_parts = []
            if kg_fin.get("note"):
                note_parts.append(f"图谱：{kg_fin['note']}")
            if rag_fin.get("note"):
                note_parts.append(f"片库：{rag_fin['note']}")
            if peer_fin.get("note") and _peer_fin_active:
                note_parts.append(f"他人收藏：{peer_fin['note']}")
            llm_fin_note = "；".join(note_parts)

            kg_picks = kg_fin.get("picks") or []
            rag_picks = rag_fin.get("picks") or []
            peer_picks = peer_fin.get("picks") or []
            if kg_picks or rag_picks or peer_picks:
                kg_by_title = {_movie_display_key(m): m for m in kg_pool if _movie_display_key(m)}
                rag_by_title = {
                    _movie_display_key(m): m for m in rag_lib_pool if _movie_display_key(m)
                }
                peer_by_title = {_movie_display_key(m): m for m in peer_pool if _movie_display_key(m)}
                seen_pick: set[str] = set()

                def _take(title: str, bucket: dict) -> None:
                    if title in bucket:
                        m = bucket[title]
                        k = _movie_display_key(m)
                        if k and k not in seen_pick:
                            merged_base.append(m)
                            seen_pick.add(k)

                for t in kg_picks:
                    _take(t, kg_by_title)
                for t in rag_picks:
                    _take(t, rag_by_title)
                for t in peer_picks:
                    _take(t, peer_by_title)
                llm_fin_used = bool(merged_base)

            if not merged_base:
                llm_fin_note = (llm_fin_note + " " if llm_fin_note else "") + (
                    "模型返回片名与候选未对齐，已回退代码分路。"
                )
        if not merged_base:
            merged_base = _stratified_core_pick(final_movies, _kk, _kr, _k_peer)

        final_movies = _quota_pad_to_cap(
            merged_base,
            movies_before_filter,
            _cap_final,
            _kk,
            _kr,
            llm_drop_norm,
            _k_peer,
        )

        n_main_kg_rag = len(final_movies)
        t_recent_extra = time.time()

        def _row_title_key(mm: dict) -> str:
            return (mm.get("display") or mm.get("name") or "").strip()

        _main_norm_keys = {
            _norm_title_for_dedupe(_row_title_key(m))
            for m in final_movies
            if _row_title_key(m)
        }
        recent_extra_movies: list[dict] = []
        for rm in extra_recent_movies:
            disp = _row_title_key(rm)
            if not disp:
                continue
            nk = _norm_title_for_dedupe(disp)
            if nk in _main_norm_keys:
                continue
            recent_extra_movies.append(rm)
            _main_norm_keys.add(nk)

        if recent_extra_movies:
            final_movies = final_movies + recent_extra_movies

        if recent_pool is not None:
            pipeline.append(
                {
                    "id": "recent_extra",
                    "title": "最近上映 / 即将上映（额外补充）",
                    "status": "ok" if recent_extra_movies else "skip",
                    "message": recent_extra_pipeline_message(
                        cap_final=_cap_final,
                        appended=len(recent_extra_movies),
                        used_recent=used_recent,
                        matched_recent=matched_recent,
                        has_candidates=bool(candidates),
                    ),
                    "elapsed_ms": int((time.time() - t_recent_extra) * 1000),
                }
            )

        if _use_llm_fin:
            _fmsg_parts = []
            if llm_fin_used:
                if llm_fin_note:
                    _fmsg_parts.append(llm_fin_note[:200])
                _fmsg_parts.append("不足条数已按「片库→图谱→任意」从初榜补足。")
            else:
                _fmsg_parts.append(llm_fin_note[:200] if llm_fin_note else "定榜模型调用失败，已用代码分路。")
            pipeline.append(
                {
                    "id": "llm_finalize",
                    "title": "大模型定榜挑选（图谱 / 片库 / 他人收藏）",
                    "call_kind": "llm",
                    "status": "ok" if llm_fin_used else "warn",
                    "message": " ".join(_fmsg_parts)[:360],
                    "elapsed_ms": llm_fin_ms,
                }
            )

        _short = _cap_final - n_main_kg_rag
        _fin_line = (
            "定榜由大模型在候选内挑选后，代码按配额补足。"
            if (_use_llm_fin and llm_fin_used)
            else "定榜由代码按权重分路挑选并补足。"
        )
        _peer_quota_note = (
            f"、同偏好他人收藏≤{_k_peer}（另路定榜，不占片库 topk_rag）"
            if _k_peer > 0
            else ""
        )
        pipeline.append(
            {
                "id": "merge_final",
                "title": "定榜（合并排序 + 配额截断）",
                "call_kind": "code",
                "status": "warn" if _short > 0 else "ok",
                "message": (
                    f"定榜 {n_main_kg_rag} 条（目标 图谱+片库+他人收藏={_cap_final}"
                    f"{f'，缺 {_short} 条（初榜可用人选已用尽或均被 drop）' if _short > 0 else ''}）；"
                    f"硬配额：图谱≤{_kk}、片库(RAG/豆瓣/TMDB 等，不含 peer_fav)≤{_kr}{_peer_quota_note}；"
                    f"不含「最近上映」附加条；"
                    f"代码补足顺序：先片库配额、再图谱、再他人收藏，最后任意来源。"
                    f"{_fin_line} 随后补全海报与卡片字段。"
                ),
                "elapsed_ms": int((time.time() - t_merge) * 1000),
            }
        )
        t_step = time.time()

        rec_text = (
            "【定榜推荐清单】以下条目由系统合并知识图谱（Multi_MoE）、片库 RAG（向量证据+LLM 生成）"
            + (
                "与同偏好他人收藏（弱协同）"
                if _k_peer > 0
                else ""
            )
            + "结果，在排除「已看过」及负反馈影片后，经加权排序与大模型审核得到，按优先级列出：\n"
        )
        for i, movie in enumerate(final_movies[:n_main_kg_rag], 1):
            rec_text += f"{i}. {movie['display']} (来源: {movie['source']})\n"
        if len(final_movies) > n_main_kg_rag:
            rec_text += (
                "\n【最近上映补充】以下条目为 TMDB 最近/即将上映池单独追加，"
                "不占图谱与片库定榜名额：\n"
            )
            for j, movie in enumerate(final_movies[n_main_kg_rag:], 1):
                rec_text += f"{j}. {movie['display']} (来源: {movie['source']})\n"

        if verbose:
            print(
                f"📊 [推荐] KG推荐: {len(kg_movies)} 部, 有效: {len([m for m in kg_movies if m in movie_entities])} 部"
            )
            print(f"🌱 [推荐] 种子电影: {seed_movies}")
            print(
                f"📊 [推荐] 偏好类型: {genre_hints[:5] if genre_hints else (history_genres or [])[:5]}"
            )

        _progress(9, "补全推荐卡片（海报/简介等）")
        t_card = time.time()
        try:
            _cap = _recommend_card_enrich_cap()
            enrich_final_movie_cards(final_movies[:_cap], allow_remote_poster=True)
            pipeline.append(
                {
                    "id": "card_blurbs",
                    "title": "推荐卡片信息（海报/类型/评分/简介）",
                    "status": "ok",
                    "message": "已为定榜列表补全海报、类型、评分与简介。",
                    "elapsed_ms": int((time.time() - t_card) * 1000),
                }
            )
        except Exception as ex:
            pipeline.append(
                {
                    "id": "card_blurbs",
                    "title": "推荐卡片信息（海报/类型/评分/简介）",
                    "status": "warn",
                    "message": str(ex)[:180],
                    "elapsed_ms": int((time.time() - t_card) * 1000),
                }
            )

        llm_explanation = ""
        llm_explanation_error = ""
        # 解读按需生成：用户点击按钮后通过 /api/recommend/explain/jobs 单独触发
        pipeline.append(
            {
                "id": "llm_explain",
                "title": "大模型辅助解读（按需）",
                "call_kind": "llm",
                "status": "skip",
                "message": "按需步骤：点击「生成解读」按钮将单独请求大模型。",
                "elapsed_ms": 0,
            }
        )

        llm_summary = ""
        llm_summary_error = ""
        sum_res: dict = {"ok": False, "ms": 0}
        # 总结按需生成：用户点击按钮后通过 /api/recommend/summary/jobs 单独触发
        pipeline.append(
            {
                "id": "llm_summary",
                "title": "大模型总结推荐（面向用户 · 按需）",
                "call_kind": "llm",
                "status": "skip",
                "message": "按需步骤：点击「生成推荐总结」按钮将单独请求大模型。",
                "elapsed_ms": 0,
            }
        )

        elapsed = time.time() - start
        print(f"✅ [推荐] 推荐完成，耗时 {elapsed:.2f}s")

        kg_final_entity_names = [
            (m.get("name") or "").strip()
            for m in final_movies
            if isinstance(m, dict)
            and (m.get("source") or "").strip() == "kg"
            and (m.get("name") or "").strip()
        ]
        pref_preview = _public_decompose_preview(decompose_data) if decompose.get("ok") else {}
        llm_rows = _llm_invocation_rows_from_pipeline(pipeline)

        return {
            "success": True,
            "movies": final_movies,
            "recent_extra_movies": recent_extra_movies,
            "movies_before_filter": movies_before_filter,
            "movies_filtered_out": filtered_out,
            "llm_filter_text": llm_filter_text,
            "llm_filter_error": llm_filter_error,
            "kg_movies": kg_movies,
            "kg_final_entity_names": kg_final_entity_names,
            "rag_movies": rag_movies,
            "peer_fav_movies": peer_fav_movies,
            "seed_movies": seed_movies,
            "genre_hints": genre_hints,
            "watched_titles": watched_names,
            "recommend_text": rec_text,
            "elapsed_ms": int(elapsed * 1000),
            "pipeline": pipeline,
            "preference_decompose": pref_preview,
            "llm_invocations": llm_rows,
            "llm_explanation": llm_explanation,
            "llm_explanation_error": llm_explanation_error,
            "llm_summary": llm_summary,
            "llm_summary_error": llm_summary_error,
            "recommend_phase": "complete",
            "filter_pending": False,
            "kg_model_meta": {
                "method": "Multi_MoE.forward — 四分支平均（尾/头双向 max 聚合）",
                "relations_used": (kg_moe_meta or {}).get("relations_used", []),
                "preferred_relations": (kg_moe_meta or {}).get("preferred_relations") or [],
                "relation_weights": (kg_moe_meta or {}).get("relation_weights") or {},
                "genre_boost": (kg_moe_meta or {}).get("genre_boost", 1.0),
                "max_relations": (kg_moe_meta or {}).get("max_relations", 10),
                "note": kg_model_note,
                "flow_summary": (
                    "主链路：偏好分解 LLM → 片库向量种子 + 标准 RAG（检索→LLM 出片）→ Multi_MoE 召回 → "
                    "初榜合并（KG+RAG·LLM）→ 审核 LLM（仅 drop）→ 定榜 LLM（在初榜候选内按 KG/非图谱配额挑选）"
                    "→ 代码按配额从初榜补足 → 可追加 TMDB 最近上映（recent_pool，API 工具结果）"
                    "→ 海报/卡片补全；解读与总结不重排。"
                ),
                "candidate_stage": "定榜（先审核截断，再补全卡片）",
            },
        }

    except Exception as e:
        print(f"❌ [推荐] 推荐失败: {str(e)[:120]}")
        return {"success": False, "error": str(e)}


