# -*- coding: utf-8 -*-
"""
海报解析：优先豆瓣 subject_suggest（国内可访问），其次 TMDB（需 TMDB_API_KEY）。
首页「最近上映 / 即将上映」可合并 TMDB 本周趋势条目（与豆瓣列表去重）。
"""

from __future__ import annotations

import os
from typing import Any, Optional, Sequence

import requests

from backend.services.tmdb_client import search_movie_poster, trending_movies_week, tmdb_configured
from backend.services.poster_file_cache import (
    poster_file_cache_enabled,
    poster_cache_eager_download,
    try_local_cached_url_any,
    download_remote_to_cache,
    schedule_download_remote_to_cache,
)

DOUBAN_SUGGEST = "https://movie.douban.com/j/subject_suggest"

REQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Referer": "https://movie.douban.com/",
    "Accept": "application/json",
}

_douban_poster_cache: dict[str, Optional[str]] = {}


def douban_suggest_poster(title: str) -> Optional[str]:
    """豆瓣联想接口返回第一条结果的小海报图（国内一般可直连）。"""
    t = (title or "").strip()
    if not t:
        return None
    if t in _douban_poster_cache:
        return _douban_poster_cache[t]
    try:
        r = requests.get(DOUBAN_SUGGEST, params={"q": t[:48]}, headers=REQ_HEADERS, timeout=2.8)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list) or not data:
            _douban_poster_cache[t] = None
            return None
        first = data[0]
        pic = first.get("img") or first.get("pic") or first.get("cover_url")
        if isinstance(pic, str) and pic.startswith("http"):
            pic = pic.replace("/s_poster/", "/s_ratio_poster/")
            _douban_poster_cache[t] = pic
            return pic
        _douban_poster_cache[t] = None
        return None
    except Exception:
        _douban_poster_cache[t] = None
        return None


def _poster_cache_candidate_titles(
    primary: str, cache_aliases: Optional[Sequence[str]]
) -> list[str]:
    """本地缓存与远程回退时共用的片名候选（去重保序，含尾部标点变体）。"""
    out: list[str] = []
    seen: set[str] = set()
    for raw in (primary,) + tuple(cache_aliases or ()):
        t = (raw or "").strip()
        for v in (t, t.rstrip("!！?.． ") if t else ""):
            if v and v not in seen:
                out.append(v)
                seen.add(v)
    return out


def resolve_movie_poster_cached_only(
    title: str, cache_aliases: Optional[Sequence[str]] = None
) -> Optional[str]:
    """仅返回已缓存的本地海报 URL；不进行任何外网请求。"""
    t = (title or "").strip()
    if not t or not poster_file_cache_enabled():
        return None
    return try_local_cached_url_any(*_poster_cache_candidate_titles(t, cache_aliases))


def resolve_movie_poster(
    title: str, cache_aliases: Optional[Sequence[str]] = None
) -> Optional[str]:
    """
    豆瓣优先，失败再尝试 TMDB（较长超时）。
    默认写入本地磁盘缓存并返回 /api/poster-cache/...，避免浏览器直连 CDN 防盗链裂图。
    关闭：环境变量 POSTER_FILE_CACHE=0

    cache_aliases：额外片名（如豆瓣 CSV 主标题、RAG 元数据中的中文名），用于命中本地 poster_cache。
    """
    t = (title or "").strip()
    if not t:
        return None
    cands = _poster_cache_candidate_titles(t, cache_aliases)
    if poster_file_cache_enabled():
        hit = try_local_cached_url_any(*cands)
        if hit:
            return hit
    u = douban_suggest_poster(t)
    if not u and cache_aliases:
        for a in cands[1:]:
            u = douban_suggest_poster(a)
            if u:
                break
    if not u and tmdb_configured():
        u = search_movie_poster(t, timeout=10.0, log_errors=False)
    if not u and tmdb_configured() and len(cands) > 1:
        for a in cands[1:]:
            u = search_movie_poster(a, timeout=10.0, log_errors=False)
            if u:
                break
    if not u:
        return None
    if poster_file_cache_enabled():
        if poster_cache_eager_download():
            cached = download_remote_to_cache(t, u)
            if cached:
                return cached
        else:
            schedule_download_remote_to_cache(t, u)
    return u


def enrich_movie_dicts(movies: list[dict], max_lookups: int, allow_remote: bool = True) -> int:
    """为 {name, display, ...} 列表就地写入 poster_url；返回本次发起的远程请求次数。"""
    used = 0
    for m in movies:
        if used >= max_lookups:
            break
        if m.get("poster_url"):
            continue
        title = m.get("name") or m.get("display") or ""
        if not title:
            m["poster_url"] = None
            continue
        if allow_remote:
            m["poster_url"] = resolve_movie_poster(str(title))
            used += 1
        else:
            m["poster_url"] = resolve_movie_poster_cached_only(str(title))
    return used


def _materialize_http_posters(movies: list[dict], budget: list[int]) -> None:
    """(保留占位) 旧版同步落盘逻辑已停用，避免接口阻塞。"""
    return


def enrich_home_feed_posters(data: dict[str, Any], max_lookups: int = 56, allow_remote: bool = True) -> None:
    n = 0
    for key in ("carousel", "high_rated", "recent", "upcoming", "daily"):
        n += enrich_movie_dicts(data.get(key) or [], max(0, max_lookups - n), allow_remote=allow_remote)
        if n >= max_lookups:
            break


def merge_tmdb_trending_into_recent_and_upcoming(data: dict[str, Any]) -> None:
    """
    将 TMDB 本周趋势影片追加到「即将上映/热议」「最近上映」滑轨末尾（与豆瓣去重）。
    无 TMDB 或请求失败时不修改。
    """
    if os.getenv("TMDB_TRENDING_MERGE", "0").strip().lower() not in ("1", "true", "yes", "on"):
        return
    if not tmdb_configured():
        return
    rows = trending_movies_week(18)
    if not rows:
        return

    seen: set[str] = set()
    for sec in ("carousel", "high_rated", "recent", "upcoming", "daily"):
        for m in data.get(sec) or []:
            n = (m.get("name") or m.get("display") or "").strip()
            if n:
                seen.add(n)

    def to_home_item(r: dict[str, Any]) -> Optional[dict[str, Any]]:
        title = (r.get("title") or "").strip()
        if not title or title in seen:
            return None
        seen.add(title)
        return {
            "name": title,
            "display": title,
            "genres": "全球热播",
            "score": str(r.get("vote_average") or "")[:4],
            "directors": "TMDB",
            "start_time": r.get("release_date") or "",
            "poster_url": r.get("poster_url"),
            "from_tmdb_trending": True,
        }

    up = data.get("upcoming") or []
    re_ = data.get("recent") or []
    pool: list[dict[str, Any]] = []
    for r in rows:
        item = to_home_item(r)
        if item:
            pool.append(item)
        if len(pool) >= 12:
            break
    extra_up = pool[:6]
    extra_re = pool[6:12]

    if extra_up:
        data["upcoming"] = up + extra_up
    if extra_re:
        data["recent"] = re_ + extra_re
    note = (data.get("upcoming_note") or "").strip()
    if (extra_up or extra_re) and "TMDB" not in note:
        suffix = "含 TMDB 本周全球趋势片单（与豆瓣去重展示）。"
        data["upcoming_note"] = f"{note} {suffix}".strip() if note else suffix

