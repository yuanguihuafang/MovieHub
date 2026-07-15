# -*- coding: utf-8 -*-
"""浏览 / 片单页：豆瓣 CSV / TMDB CSV 加载与分页列表。"""
import ast
import os
import json

import pandas as pd

from backend.recommender.common import (
    ALLOWED_GENRES,
    GENRE_MAPPING,
    PROJECT_ROOT,
    _cache,
)

TMDB_MOVIES_CSV = os.path.join(PROJECT_ROOT, "backend", "data", "RAG_data", "movies", "tmdb_5000_movies.csv")

# TMDB genres（英文）归一到系统 10 类中文
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


def load_douban_data():
    """加载豆瓣电影数据"""
    if _cache.get("douban_movies") is not None:
        return

    csv_path = os.path.join(
        PROJECT_ROOT, "backend", "data", "RAG_data", "movies", "douban_movies.csv"
    )

    if not os.path.exists(csv_path):
        print(f"⚠️  豆瓣CSV文件不存在: {csv_path}")
        _cache["douban_movies"] = pd.DataFrame()
        _cache["douban_genres"] = ALLOWED_GENRES.copy()
        return

    try:
        df = pd.read_csv(csv_path, encoding="utf-8-sig")

        def simplify_genres(types_str):
            if pd.isna(types_str):
                return ["剧情"]
            try:
                types_list = (
                    ast.literal_eval(types_str) if isinstance(types_str, str) else []
                )
                simplified = []
                for t in types_list:
                    if t in ALLOWED_GENRES:
                        if t not in simplified:
                            simplified.append(t)
                    elif t in GENRE_MAPPING:
                        mapped = GENRE_MAPPING[t]
                        if mapped not in simplified:
                            simplified.append(mapped)
                return simplified if simplified else ["剧情"]
            except Exception:
                return ["剧情"]

        df["type_simplified"] = df["type"].apply(simplify_genres)
        _cache["douban_movies"] = df
        print(f"✅ [豆瓣] 已加载 {len(df)} 部电影")

        _cache["douban_genres"] = ALLOWED_GENRES.copy()
        print(f"   类型: {len(ALLOWED_GENRES)} 种")
    except Exception as e:
        print(f"❌ [豆瓣] 加载失败: {e}")
        _cache["douban_movies"] = pd.DataFrame()
        _cache["douban_genres"] = ALLOWED_GENRES.copy()


def load_tmdb_movies_data():
    """加载 TMDB 5000 movies 数据（片库/详情用，加载时只保留必要列以节省内存）。"""
    if _cache.get("tmdb_movies") is not None:
        return

    if not os.path.exists(TMDB_MOVIES_CSV):
        print(f"⚠️  TMDB movies CSV 不存在: {TMDB_MOVIES_CSV}")
        _cache["tmdb_movies"] = pd.DataFrame()
        _cache["tmdb_genres"] = ALLOWED_GENRES.copy()
        return

    try:
        # 只读必要列，避免把大字段整表塞进内存
        usecols = [
            "id",
            "title",
            "original_title",
            "genres",
            "release_date",
            "runtime",
            "vote_average",
            "vote_count",
            "overview",
        ]
        df = pd.read_csv(TMDB_MOVIES_CSV, encoding="utf-8", usecols=lambda c: c in usecols)

        def parse_genres_cell(v):
            # genres 列通常是 JSON 字符串：[{"id":18,"name":"Drama"}, ...]
            if pd.isna(v):
                return ["剧情"]
            if isinstance(v, list):
                arr = v
            else:
                s = str(v)
                try:
                    arr = json.loads(s)
                except Exception:
                    try:
                        arr = ast.literal_eval(s)
                    except Exception:
                        arr = []

            out = []
            for g in arr or []:
                name = None
                if isinstance(g, dict):
                    name = g.get("name")
                elif isinstance(g, str):
                    name = g
                if not name:
                    continue
                cn = TMDB_GENRE_TO_CN.get(str(name).strip())
                if cn and cn in ALLOWED_GENRES and cn not in out:
                    out.append(cn)
            return out if out else ["剧情"]

        df["type_simplified"] = df.get("genres", pd.Series([None] * len(df))).apply(parse_genres_cell)
        # 统一字段：title
        if "title" not in df.columns and "original_title" in df.columns:
            df["title"] = df["original_title"]

        # 轻量化：overview 截断（避免长文本占用过多内存）
        if "overview" in df.columns:
            def _trim_overview(v):
                if pd.isna(v):
                    return ""
                s = str(v)
                return s[:280]  # 轻量详情足够
            df["overview"] = df["overview"].apply(_trim_overview)

        _cache["tmdb_movies"] = df
        _cache["tmdb_genres"] = ALLOWED_GENRES.copy()
        print(f"✅ [TMDB] 已加载 {len(df)} 部电影")
    except Exception as e:
        print(f"❌ [TMDB] 加载失败: {e}")
        _cache["tmdb_movies"] = pd.DataFrame()
        _cache["tmdb_genres"] = ALLOWED_GENRES.copy()


def _norm_kw(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _row_matches_search(row, kw: str) -> bool:
    """
    关键词：片名模糊（子串、忽略空格）；类型模糊（命中任一已归一中文类型，或拼接串子串）。
    """
    if not kw:
        return True
    title = str(row.get("title") or "").strip().lower()
    title_compact = title.replace(" ", "")
    kw_compact = kw.replace(" ", "")
    if kw in title or (kw_compact and kw_compact in title_compact):
        return True
    types_list = row.get("type_simplified") or []
    if not isinstance(types_list, list):
        types_list = []
    joined = "/".join(str(x) for x in types_list if x).lower()
    if kw in joined:
        return True
    for g in types_list:
        if not isinstance(g, str):
            continue
        gl = g.strip().lower()
        if not gl:
            continue
        if kw in gl or gl in kw:
            return True
        gc = gl.replace(" ", "")
        if kw_compact and (kw_compact in gc or gc in kw_compact):
            return True
    return False


def get_movie_list(
    page: int = 1,
    page_size: int = 16,
    genre: str = "",
    source: str = "douban",
    search: str = "",
):
    """获取电影列表（分页）。source=douban|tmdb|tmdb_api"""
    kw = _norm_kw(search)
    src = (source or "douban").strip().lower()

    # TMDB API（首页正在热映/即将上映落盘缓存）：作为“片库数据源”展示
    if src in ("tmdb_api", "api", "tmdbapi"):
        try:
            from backend.services.tmdb_home_cache import read_cache

            disk = read_cache() or {}
            np = disk.get("now_playing") or []
            up = disk.get("upcoming") or []
            pool: list[dict] = []
            seen: set[str] = set()
            for sec in (np, up):
                for m in sec or []:
                    if not isinstance(m, dict):
                        continue
                    tid = m.get("tmdb_id")
                    try:
                        tid_i = int(tid) if tid is not None and str(tid).strip() else 0
                    except Exception:
                        tid_i = 0
                    key = str(tid_i) if tid_i > 0 else (m.get("name") or m.get("display") or "")
                    key = str(key).strip()
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    pool.append(m)

            # genre filter
            if genre and genre.strip():
                g = genre.strip()
                pool = [
                    m
                    for m in pool
                    if g
                    in str(m.get("genres") or "")
                    .replace("、", "/")
                    .split("/")
                ]

            # keyword filter (title / genres)
            if kw:
                kwl = kw.lower()
                out = []
                for m in pool:
                    title = str(m.get("name") or m.get("display") or "").strip()
                    genres = str(m.get("genres") or "").strip()
                    blob = (title + " " + genres).lower().replace(" ", "")
                    if kwl in blob or kwl.replace(" ", "") in blob:
                        out.append(m)
                pool = out

            total = len(pool)
            start = (page - 1) * page_size
            end = start + page_size
            page_items = pool[start:end]
            movies: list[dict] = []
            for m in page_items:
                title = str(m.get("name") or m.get("display") or "").strip()
                poster = str(m.get("poster_url") or "").strip()
                # 若缓存里还是旧的 .webp（文件可能已被清理），但同 id 已落盘 .jpg，则改写为可用地址
                if poster.startswith("/api/tmdb-home-poster/") and str(m.get("tmdb_id") or "").strip():
                    try:
                        from backend.services.tmdb_home_poster_cache import download_tmdb_poster_to_home_cache

                        poster = download_tmdb_poster_to_home_cache(int(m.get("tmdb_id")), poster) or poster
                    except Exception:
                        pass
                movies.append(
                    {
                        "name": title,
                        "display": title,
                        "genres": str(m.get("genres") or "").strip(),
                        "directors": "",
                        "score": str(m.get("score") or "").strip(),
                        "rank": "",
                        "run_time": "",
                        "start_time": str(m.get("start_time") or "").strip(),
                        "area": "",
                        "language": "",
                        "comment_num": "",
                        "actor": "",
                        "poster_url": poster or m.get("poster_url"),
                        "tmdb_id": m.get("tmdb_id"),
                        "source": "tmdb_api",
                    }
                )
            return movies, total
        except Exception:
            return [], 0

    if src in ("tmdb", "tmdb_csv", "tmdb5000"):
        if _cache.get("tmdb_movies") is None:
            load_tmdb_movies_data()
        df = _cache.get("tmdb_movies")
        if df is None or df.empty:
            return [], 0

        if genre and genre.strip():
            g = genre.strip()
            mask = df["type_simplified"].apply(lambda x: g in x if isinstance(x, list) else False)
            df = df[mask]

        if kw:
            df = df[df.apply(lambda r: _row_matches_search(r, kw), axis=1)]

        total = len(df)
        start = (page - 1) * page_size
        end = start + page_size
        df_page = df.iloc[start:end]

        movies = []
        for _, row in df_page.iterrows():
            types_list = row.get("type_simplified") or []
            genres = "/".join(types_list) if types_list else "未知"
            title = row.get("title") or ""
            movies.append(
                {
                    "name": str(title),
                    "display": str(title),
                    "genres": genres,
                    "source": "tmdb_csv",
                    "tmdb_id": int(row.get("id")) if row.get("id") is not None and str(row.get("id")).strip() != "" else None,
                }
            )
        return movies, total

    # 默认：豆瓣
    if _cache.get("douban_movies") is None:
        load_douban_data()

    df = _cache.get("douban_movies")
    if df is None or df.empty:
        return [], 0

    if genre and genre.strip():
        mask = df["type_simplified"].apply(
            lambda x: genre in x if isinstance(x, list) else False
        )
        df = df[mask]

    if kw:
        df = df[df.apply(lambda r: _row_matches_search(r, kw), axis=1)]

    total = len(df)

    start = (page - 1) * page_size
    end = start + page_size
    df_page = df.iloc[start:end]

    movies = []
    for _, row in df_page.iterrows():
        try:
            types_list = row["type_simplified"]
            genres = "/".join(types_list) if types_list else "未知"
        except Exception as e:
            print(f"⚠️  解析类型失败: {str(e)[:80]}")
            genres = "未知"

        movies.append(
            {
                "name": row["title"],
                "display": row["title"],
                "genres": genres,
                "directors": row["director"] if pd.notna(row["director"]) else "未知",
                "score": str(row["score"]) if pd.notna(row["score"]) else "0",
                "rank": str(row["rank"]) if pd.notna(row["rank"]) else "",
                "run_time": row["run_time"] if pd.notna(row["run_time"]) else "",
                "start_time": row["start_time"] if pd.notna(row["start_time"]) else "",
                "area": row["area"] if pd.notna(row["area"]) else "",
                "language": row["language"] if pd.notna(row["language"]) else "",
                "comment_num": row["comment_num"]
                if pd.notna(row["comment_num"])
                else "",
                "actor": row["actor"] if pd.notna(row["actor"]) else "",
            }
        )

    return movies, total
