# -*- coding: utf-8 -*-
"""
The Movie Database (TMDB) v3：全球热播、海报图、按片名搜索。
需在环境变量中配置 TMDB_API_KEY（免费注册：https://www.themoviedb.org/settings/api ）。
默认 **使用系统代理**（读取 HTTP_PROXY / HTTPS_PROXY 等，与 Clash 等一致）。
若环境变量里配置了代理但本机代理未开导致报错，可设 **TMDB_IGNORE_SYSTEM_PROXY=1** 强制直连。
也可用 TMDB_USE_SYSTEM_PROXY=0 关闭、=1 强制开启（不设置则按 requests 默认走环境）。
国际链路或代理较慢时，默认连接约 28s、读取约 55s；仍超时可设 TMDB_CONNECT_TIMEOUT / TMDB_READ_TIMEOUT。
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.services import redis_cache

TMDB_API_KEY = (os.getenv("TMDB_API_KEY") or "").strip()
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w342"

_poster_cache: dict[str, Optional[str]] = {}
_search_first_cache: dict[str, Optional[dict[str, Any]]] = {}

_tmdb_http: Optional[requests.Session] = None


def _tmdb_trust_env() -> bool:
    """
    是否让 requests 使用系统环境里的代理变量。
    默认 True；TMDB_IGNORE_SYSTEM_PROXY=1 或 TMDB_USE_SYSTEM_PROXY=0 时关闭。
    """
    if (os.getenv("TMDB_IGNORE_SYSTEM_PROXY") or "").strip().lower() in ("1", "true", "yes", "on"):
        return False
    raw = (os.getenv("TMDB_USE_SYSTEM_PROXY") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return True


def _tmdb_http_timeout() -> tuple[float, float] | float:
    """
    TMDB 请求超时：默认 (连接 28s, 读取 55s)，走代理时 TLS 握手常需更久。
    - TMDB_CONNECT_TIMEOUT / TMDB_READ_TIMEOUT：分别指定（秒）
    - TMDB_TIMEOUT：单一数值时同时作为连接与读取超时
    """
    tc_raw = (os.getenv("TMDB_CONNECT_TIMEOUT") or "").strip()
    tr_raw = (os.getenv("TMDB_READ_TIMEOUT") or "").strip()
    if tc_raw or tr_raw:
        try:
            c = float(tc_raw or "28")
            r = float(tr_raw or "55")
            return (max(3.0, min(90.0, c)), max(5.0, min(180.0, r)))
        except ValueError:
            pass
    single = (os.getenv("TMDB_TIMEOUT") or "").strip()
    if single:
        try:
            t = max(5.0, min(120.0, float(single)))
            return t
        except ValueError:
            pass
    return (28.0, 55.0)


def _tmdb_session() -> requests.Session:
    """TMDB 请求 Session；是否走系统代理由 _tmdb_trust_env() 决定（默认走代理）。"""
    global _tmdb_http
    if _tmdb_http is None:
        s = requests.Session()
        s.trust_env = _tmdb_trust_env()
        retry = Retry(
            total=5,
            connect=5,
            read=2,
            backoff_factor=0.9,
            status_forcelist=(502, 503, 504),
            allowed_methods=("GET", "HEAD"),
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _tmdb_http = s
        if TMDB_API_KEY:
            print(f"🌐 [TMDB] 代理模式: trust_env={s.trust_env}")
    return _tmdb_http


def tmdb_configured() -> bool:
    return bool(TMDB_API_KEY)


def _poster_url_from_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return f"{TMDB_IMG_BASE}{path}"


def _parse_ymd(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None


def _tmdb_title_search_variants(title: str) -> list[str]:
    """片名搜索变体：去尾部标点等，缓解 zh-CN 下英文片名/符号导致无结果。"""
    t = (title or "").strip()
    if not t:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for v in (t, t.rstrip("!！?.． "), t.strip("!！?.．")):
        v = (v or "").strip()
        if v and v not in seen:
            out.append(v)
            seen.add(v)
    return out


def _tmdb_search_movie_results(
    query: str, *, language: str, timeout: float
) -> list[dict[str, Any]]:
    if not TMDB_API_KEY or not (query or "").strip():
        return []
    r = _tmdb_session().get(
        "https://api.themoviedb.org/3/search/movie",
        params={"api_key": TMDB_API_KEY, "query": query.strip(), "language": language},
        timeout=timeout,
    )
    r.raise_for_status()
    raw = r.json().get("results") or []
    return [x for x in raw if isinstance(x, dict)]


def search_movie_poster(title: str, timeout: float = 3.5, log_errors: bool = True) -> Optional[str]:
    """按片名搜索 TMDB，返回第一张海报 URL（带简单内存缓存）。"""
    if not TMDB_API_KEY or not (title or "").strip():
        return None
    t = title.strip()
    if t in _poster_cache:
        return _poster_cache[t]
    hit = search_movie_first(t, timeout=max(float(timeout), 5.0), log_errors=log_errors)
    url = _poster_url_from_path((hit or {}).get("poster_path")) if hit else None
    _poster_cache[t] = url
    return url


def search_movie_first(title: str, timeout: float = 5.0, log_errors: bool = False) -> Optional[dict[str, Any]]:
    """
    按片名搜索 TMDB，返回第一条结果（原始 dict，含 id/poster_path/genre_ids 等）。
    依次尝试：片名变体 × zh-CN / en-US，缓解英文片名在 zh-CN 下无结果或海报缺失。
    """
    if not TMDB_API_KEY or not (title or "").strip():
        return None
    t = title.strip()
    if t in _search_first_cache:
        return _search_first_cache[t]
    last_err: Optional[Exception] = None
    for q in _tmdb_title_search_variants(t):
        for lang in ("zh-CN", "en-US"):
            try:
                results = _tmdb_search_movie_results(q, language=lang, timeout=timeout)
                if results:
                    _search_first_cache[t] = results[0]
                    return results[0]
            except Exception as e:
                last_err = e
    if log_errors and last_err:
        print(f"⚠️  [TMDB] 搜索失败: {title!r} — {str(last_err)[:80]}")
    _search_first_cache[t] = None
    return None


def trending_movies_week(limit: int = 20) -> list[dict[str, Any]]:
    """本周全球趋势影片（适合「当前热播」工具调用）。"""
    if not TMDB_API_KEY:
        return []
    cache_key = f"tmdb:trending_week:{limit}"
    cached = redis_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        r = _tmdb_session().get(
            "https://api.themoviedb.org/3/trending/movie/week",
            params={"api_key": TMDB_API_KEY, "language": "zh-CN"},
            timeout=_tmdb_http_timeout(),
        )
        r.raise_for_status()
        out: list[dict[str, Any]] = []
        for m in (r.json().get("results") or [])[: max(1, limit)]:
            out.append(
                {
                    "title": m.get("title") or m.get("original_title") or "",
                    "overview": ((m.get("overview") or "")[:280] + "…")
                    if len(m.get("overview") or "") > 280
                    else (m.get("overview") or ""),
                    "vote_average": m.get("vote_average"),
                    "release_date": m.get("release_date") or "",
                    "poster_url": _poster_url_from_path(m.get("poster_path")),
                }
            )
        redis_cache.set(cache_key, out, ttl=1800)  # 30 分钟
        return out
    except Exception as e:
        print(f"⚠️  [TMDB] 热门电影获取失败: {str(e)[:80]}")
        return []


def trending_movies_day(limit: int = 20) -> list[dict[str, Any]]:
    """今日趋势影片（TMDB trending/movie/day）。"""
    if not TMDB_API_KEY:
        return []
    try:
        r = _tmdb_session().get(
            "https://api.themoviedb.org/3/trending/movie/day",
            params={"api_key": TMDB_API_KEY, "language": "zh-CN"},
            timeout=_tmdb_http_timeout(),
        )
        r.raise_for_status()
        out: list[dict[str, Any]] = []
        for m in (r.json().get("results") or [])[: max(1, limit)]:
            out.append(
                {
                    "title": m.get("title") or m.get("original_title") or "",
                    "overview": ((m.get("overview") or "")[:280] + "…")
                    if len(m.get("overview") or "") > 280
                    else (m.get("overview") or ""),
                    "vote_average": m.get("vote_average"),
                    "release_date": m.get("release_date") or "",
                    "poster_url": _poster_url_from_path(m.get("poster_path")),
                }
            )
        return out
    except Exception as e:
        print(f"⚠️  [TMDB] 今日热门获取失败: {str(e)[:80]}")
        return []


def now_playing_movies(limit: int = 20) -> list[dict[str, Any]]:
    """正在上映（TMDB movie/now_playing）。"""
    if not TMDB_API_KEY:
        return []
    cache_key = f"tmdb:now_playing:{limit}"
    cached = redis_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        r = _tmdb_session().get(
            "https://api.themoviedb.org/3/movie/now_playing",
            params={"api_key": TMDB_API_KEY, "language": "zh-CN", "page": 1},
            timeout=_tmdb_http_timeout(),
        )
        r.raise_for_status()
        out: list[dict[str, Any]] = []
        today = datetime.now().date()
        for m in (r.json().get("results") or []):
            if len(out) >= max(1, limit):
                break
            rd = (m.get("release_date") or "").strip()
            d = _parse_ymd(rd)
            if d and d.date() > today:
                continue
            out.append(
                {
                    "id": m.get("id"),
                    "title": m.get("title") or m.get("original_title") or "",
                    "overview": ((m.get("overview") or "")[:280] + "…")
                    if len(m.get("overview") or "") > 280
                    else (m.get("overview") or ""),
                    "vote_average": m.get("vote_average"),
                    "release_date": rd,
                    "genre_ids": m.get("genre_ids") or [],
                    "poster_url": _poster_url_from_path(m.get("poster_path")),
                }
            )
        redis_cache.set(cache_key, out, ttl=1800)  # 30 分钟
        return out
    except Exception as e:
        print(f"⚠️  [TMDB] 正在上映获取失败: {str(e)[:80]}")
        return []


def upcoming_movies(limit: int = 20) -> list[dict[str, Any]]:
    """即将上映（TMDB movie/upcoming）。按页请求，某一页超时则保留已成功的页。"""
    if not TMDB_API_KEY:
        return []
    out: list[dict[str, Any]] = []
    today = datetime.now().date()
    to = _tmdb_http_timeout()
    for page in (1, 2, 3):
        if len(out) >= max(1, limit):
            break
        if page > 1:
            time.sleep(0.25)
        try:
            r = _tmdb_session().get(
                "https://api.themoviedb.org/3/movie/upcoming",
                params={"api_key": TMDB_API_KEY, "language": "zh-CN", "page": page},
                timeout=to,
            )
            r.raise_for_status()
            for m in (r.json().get("results") or []):
                if len(out) >= max(1, limit):
                    break
                rd = (m.get("release_date") or "").strip()
                d = _parse_ymd(rd)
                if not d:
                    continue
                if d.date() <= today:
                    continue
                out.append(
                    {
                        "id": m.get("id"),
                        "title": m.get("title") or m.get("original_title") or "",
                        "overview": ((m.get("overview") or "")[:280] + "…")
                        if len(m.get("overview") or "") > 280
                        else (m.get("overview") or ""),
                        "vote_average": m.get("vote_average"),
                        "release_date": rd,
                        "genre_ids": m.get("genre_ids") or [],
                        "poster_url": _poster_url_from_path(m.get("poster_path")),
                    }
                )
        except Exception as e:
            print(f"⚠️  [TMDB] 即将上映获取失败(p{page}): {str(e)[:80]}")
            break
    return out


TMDB_GENRE_TO_CN = {
    "Drama": "剧情",
    "Comedy": "喜剧",
    "Romance": "爱情",
    "Action": "动作",
    "Science Fiction": "科幻",
    "Mystery": "悬疑",
    "Thriller": "悬疑",
    "Crime": "悬疑",
    "Horror": "悬疑",
    "Animation": "动画",
    "Documentary": "纪录片",
    "War": "战争",
    "Fantasy": "奇幻",
    "Adventure": "奇幻",
    "Western": "奇幻",
    "History": "战争",
    "Family": "剧情",
    "Music": "剧情",
    "TV Movie": "剧情",
}

# TMDB movie genre id -> English name（用于列表接口返回的 genre_ids）
TMDB_GENRE_ID_TO_EN: dict[int, str] = {
    28: "Action",
    12: "Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    14: "Fantasy",
    36: "History",
    27: "Horror",
    10402: "Music",
    9648: "Mystery",
    10749: "Romance",
    878: "Science Fiction",
    10770: "TV Movie",
    53: "Thriller",
    10752: "War",
    37: "Western",
}


def tmdb_movie_detail(movie_id: int, timeout: float = 4.5) -> Optional[dict[str, Any]]:
    """按 TMDB id 获取电影详情（含类型/简介等）。"""
    if not TMDB_API_KEY or not movie_id:
        return None
    cache_key = f"tmdb:detail:{movie_id}"
    cached = redis_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        r = _tmdb_session().get(
            f"https://api.themoviedb.org/3/movie/{int(movie_id)}",
            params={"api_key": TMDB_API_KEY, "language": "zh-CN"},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        redis_cache.set(cache_key, data, ttl=3600)  # 1 小时
        return data
    except Exception as e:
        print(f"⚠️  [TMDB] 电影详情获取失败: {str(e)[:80]}")
        return None


def tmdb_movie_credits(movie_id: int, timeout: float = 4.5) -> Optional[dict[str, Any]]:
    """按 TMDB id 获取演职员信息。"""
    if not TMDB_API_KEY or not movie_id:
        return None
    cache_key = f"tmdb:credits:{movie_id}"
    cached = redis_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        r = _tmdb_session().get(
            f"https://api.themoviedb.org/3/movie/{int(movie_id)}/credits",
            params={"api_key": TMDB_API_KEY, "language": "zh-CN"},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        redis_cache.set(cache_key, data, ttl=3600)  # 1 小时
        return data
    except Exception as e:
        print(f"⚠️  [TMDB] 演职信息获取失败: {str(e)[:80]}")
        return None


def tmdb_genres_cn(genres: Any) -> str:
    """将 TMDB genres（列表）映射为 10 类中文，无法映射则保留英文名。"""
    if not genres:
        return ""
    out: list[str] = []
    for g in genres or []:
        name = ""
        if isinstance(g, dict):
            name = (g.get("name") or "").strip()
        elif isinstance(g, str):
            name = g.strip()
        if not name:
            continue
        cn = TMDB_GENRE_TO_CN.get(name) or name
        if cn not in out:
            out.append(cn)
    return "/".join(out)


def tmdb_genres_cn_from_ids(genre_ids: Any) -> str:
    """将 TMDB genre_ids（int 列表）映射为中文类型串（尽量对齐 ALLOWED_GENRES）。"""
    if not genre_ids:
        return ""
    names: list[str] = []
    for x in genre_ids or []:
        try:
            gid = int(x)
        except Exception:
            continue
        en = TMDB_GENRE_ID_TO_EN.get(gid)
        if en:
            names.append(en)
    return tmdb_genres_cn(names)


def attach_poster_url(movies: list[dict], title_key: str = "name", out_key: str = "poster_url", max_lookups: int = 36) -> None:
    """为片单字典列表就地补充 poster_url（限制 TMDB 调用次数）。"""
    n = 0
    for m in movies:
        if n >= max_lookups:
            m.setdefault(out_key, None)
            continue
        if m.get(out_key):
            continue
        title = m.get(title_key) or m.get("display") or ""
        if not title:
            m[out_key] = None
            continue
        m[out_key] = search_movie_poster(str(title))
        if m[out_key]:
            n += 1


def enrich_home_feed_sections(data: dict, max_lookups: int = 42) -> None:
    """为首页各分区中的影片字典补充 poster_url。"""
    keys = ("carousel", "high_rated", "recent", "upcoming", "daily")
    n = 0
    for key in keys:
        for m in data.get(key) or []:
            if n >= max_lookups:
                return
            if m.get("poster_url"):
                continue
            title = m.get("name") or m.get("display") or ""
            m["poster_url"] = search_movie_poster(str(title)) if title else None
            if m["poster_url"]:
                n += 1

