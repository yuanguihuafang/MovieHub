"""
backend/api/routers/movies.py

电影浏览/详情接口（对应前端“电影浏览”和“电影详情”页面）。

- GET /api/movies
- GET /api/movies/{movie_name}/detail
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
from fastapi import APIRouter, Query, Request

from backend.db.database import history_add
from backend.services.poster_service import enrich_movie_dicts, resolve_movie_poster
from backend.recommender import RELATION_ZH, _cache, get_movie_list, load_douban_data
from backend.services.tmdb_client import tmdb_genres_cn, tmdb_movie_credits, tmdb_movie_detail

router = APIRouter(tags=["movies"])


@router.get("/api/movies")
async def api_get_movies(
    page: int = Query(1, ge=1),
    page_size: int = Query(16, ge=1, le=100),
    genre: str = "",
    search: str = "",
    source: str = "douban",
):
    """获取电影列表（分页）"""
    movies, total = get_movie_list(page, page_size, genre, source=source, search=search)
    total_pages = max(1, (int(total) + int(page_size) - 1) // int(page_size))

    # 豆瓣模式：补海报（优先速度：只返回本地已缓存海报）
    src = (source or "douban").strip().lower()
    if movies and src in ("douban", ""):
        try:
            enrich_movie_dicts(movies, max_lookups=min(page_size, 32), allow_remote=False)
        except Exception:
            pass

    genres = []
    try:
        if src in ("tmdb", "tmdb_csv", "tmdb5000"):
            genres = _cache.get("tmdb_genres", []) or []
        elif src in ("tmdb_api", "api", "tmdbapi"):
            # TMDB API 首页缓存：类型仍使用固定 10 类（与推荐/豆瓣保持一致）
            genres = _cache.get("douban_genres", []) or []
        else:
            genres = _cache.get("douban_genres", []) or []
    except Exception:
        genres = []

    return {
        "success": True,
        "movies": movies,
        "genres": genres,
        "pagination": {"page": page, "page_size": page_size, "total": total, "total_pages": total_pages},
    }


@router.get("/api/movies/{movie_name}/detail")
async def api_get_movie_detail(
    request: Request,
    movie_name: str,
    source: str = "douban",
    tmdb_id: Optional[int] = None,
    track: bool = True,
):
    """
    获取电影详情。

    - source=douban：从豆瓣 CSV 缓存读取，并返回统一结构
    - source=tmdb_csv/tmdb5000：从 TMDB CSV 缓存读取（默认不返回海报，避免外网）
    - 兼容 KG 实体：回退到知识图谱 attributes 结构
    """
    src = (source or "douban").strip().lower()

    # 1) TMDB-CSV：轻量详情（不返回海报）
    if src in ("tmdb", "tmdb_csv", "tmdb5000"):
        try:
            from backend.recommender.browse import load_tmdb_movies_data

            if _cache.get("tmdb_movies") is None:
                load_tmdb_movies_data()
            df = _cache.get("tmdb_movies")
            if df is not None and not df.empty:
                match = df[df.get("title") == movie_name]
                if match is not None and not match.empty:
                    row = match.iloc[0]
                    types_list = row.get("type_simplified") or []
                    type_str = "/".join(types_list) if types_list else ""
                    overview = ""
                    try:
                        overview = str(row.get("overview") or "")
                    except Exception:
                        overview = ""
                    payload = {
                        "name": movie_name,
                        "display": movie_name,
                        "source": "tmdb_csv",
                        "poster_url": None,
                        "data": {
                            "title": movie_name,
                            "type": type_str,
                            "start_time": str(row.get("release_date") or ""),
                            "run_time": str(row.get("runtime") or ""),
                            "score": str(row.get("vote_average") or "")[:4],
                            "comment_num": str(row.get("vote_count") or ""),
                            "overview": overview,
                        },
                    }
                    # 浏览记录（如果能解析出用户）
                    if track:
                        try:
                            auth = request.headers.get("Authorization") or ""
                            if auth.lower().startswith("bearer user_"):
                                uid = int(auth.split()[-1][5:])
                                history_add(uid, movie_name, type_str)
                        except Exception:
                            pass
                    return payload
        except Exception:
            pass

        payload = {
            "name": movie_name,
            "display": movie_name,
            "source": "tmdb_csv",
            "poster_url": None,
            "data": {"title": movie_name, "type": ""},
        }
        return payload

    # 1.5) TMDB API：用于首页「正在热映/即将上映」按 tmdb_id 取详情
    if src in ("tmdb_api", "tmdb") and tmdb_id:
        d = tmdb_movie_detail(int(tmdb_id))
        if d:
            credits = tmdb_movie_credits(int(tmdb_id)) or {}
            director = ""
            try:
                crew = credits.get("crew") or []
                for c in crew:
                    if (c.get("job") or "").lower() == "director":
                        director = c.get("name") or ""
                        break
            except Exception:
                director = ""
            cast_names: list[str] = []
            try:
                cast = credits.get("cast") or []
                for c in cast[:8]:
                    n = (c.get("name") or "").strip()
                    if n:
                        cast_names.append(n)
            except Exception:
                cast_names = []

            genres_cn = tmdb_genres_cn(d.get("genres") or [])
            payload = {
                "name": movie_name,
                "display": movie_name,
                "source": "tmdb_api",
                "poster_url": d.get("poster_path") and f"https://image.tmdb.org/t/p/w500{d.get('poster_path')}",
                "data": {
                    "title": d.get("title") or d.get("original_title") or movie_name,
                    "score": str(d.get("vote_average") or "")[:4],
                    "rank": "",
                    "run_time": str(d.get("runtime") or ""),
                    "start_time": d.get("release_date") or "",
                    "type": genres_cn,
                    "director": director,
                    "actor": "、".join(cast_names),
                    "area": "/".join([x.get("name") for x in (d.get("production_countries") or []) if x.get("name")]),
                    "language": d.get("original_language") or "",
                    "comment_num": str(d.get("vote_count") or ""),
                    "overview": d.get("overview") or "",
                },
            }
            if track:
                try:
                    auth = request.headers.get("Authorization") or ""
                    if auth.lower().startswith("bearer user_"):
                        uid = int(auth.split()[-1][5:])
                        history_add(uid, (payload.get("data") or {}).get("title") or movie_name, genres_cn)
                except Exception:
                    pass
            return payload

    # 2) 豆瓣 CSV：全字段详情
    if _cache.get("douban_movies") is None:
        load_douban_data()
    douban_movies = _cache.get("douban_movies")
    if douban_movies is not None and not douban_movies.empty:
        try:
            match = douban_movies[douban_movies["title"] == movie_name]
            if match is not None and not match.empty:
                row = match.iloc[0]
                simplified_types = row.get("type_simplified", [])
                type_str = "/".join(simplified_types) if simplified_types else ""
                poster_url = resolve_movie_poster(movie_name)
                payload = {
                    "name": movie_name,
                    "display": movie_name,
                    "source": "douban",
                    "poster_url": poster_url,
                    "data": {
                        "title": row.get("title", ""),
                        "score": str(row.get("score", "")) if pd.notna(row.get("score")) else "",
                        "rank": str(row.get("rank", "")) if pd.notna(row.get("rank")) else "",
                        "run_time": row.get("run_time", "") if pd.notna(row.get("run_time")) else "",
                        "start_time": row.get("start_time", "") if pd.notna(row.get("start_time")) else "",
                        "type": type_str,
                        "director": row.get("director", "") if pd.notna(row.get("director")) else "",
                        "actor": row.get("actor", "") if pd.notna(row.get("actor")) else "",
                        "area": row.get("area", "") if pd.notna(row.get("area")) else "",
                        "language": row.get("language", "") if pd.notna(row.get("language")) else "",
                        "comment_num": row.get("comment_num", "") if pd.notna(row.get("comment_num")) else "",
                    },
                }
                if track:
                    try:
                        auth = request.headers.get("Authorization") or ""
                        if auth.lower().startswith("bearer user_"):
                            uid = int(auth.split()[-1][5:])
                            history_add(uid, movie_name, type_str)
                    except Exception:
                        pass
                return payload
        except Exception:
            pass

    # 3) KG 回退：返回 attributes 结构（用于展示实体关系）
    entity_relations = _cache.get("entity_relations", {}) or {}
    attrs = entity_relations.get(movie_name, []) or []
    disp = movie_name.replace("_", " ")
    if not attrs:
        return {"name": movie_name, "display": disp, "poster_url": resolve_movie_poster(disp), "attributes": []}

    info = {"name": movie_name, "display": disp, "poster_url": resolve_movie_poster(disp), "attributes": []}
    for r, t in attrs[:12]:
        info["attributes"].append({"relation": r, "relation_zh": RELATION_ZH.get(r, r), "value": str(t).replace("_", " ")})
    return info

