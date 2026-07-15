"""首页：轮播、高分、正在上映、即将上映、每日推荐分区。"""
import ast
import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from backend.recommender.browse import load_douban_data
from backend.recommender.common import _cache
from backend.services.tmdb_home_cache import read_cache, write_cache, is_fresh, min_refresh_seconds
from backend.services.tmdb_home_poster_cache import materialize_home_posters_for_sections
from backend.services.tmdb_client import (
    now_playing_movies,
    upcoming_movies,
    tmdb_configured,
    tmdb_genres_cn_from_ids,
)


def _parse_first_date(start_time) -> Optional[datetime]:
    if start_time is None or (isinstance(start_time, float) and pd.isna(start_time)):
        return None
    s = str(start_time)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _parse_tmdb_release_date(v) -> Optional[datetime]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _parse_comment_num(val) -> int:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0
    m = re.search(r"(\d+)", str(val))
    return int(m.group(1)) if m else 0


def _row_to_home_movie(row) -> dict:
    try:
        types_list = row.get("type_simplified")
        if types_list is None or (
            isinstance(types_list, float) and pd.isna(types_list)
        ):
            types_list = []
        if isinstance(types_list, str):
            try:
                types_list = (
                    ast.literal_eval(types_list) if types_list.startswith("[") else []
                )
            except Exception:
                types_list = []
        genres = "/".join(types_list) if types_list else "未知"
    except Exception:
        genres = "未知"
    return {
        "name": row["title"],
        "display": row["title"],
        "genres": genres,
        "directors": row["director"] if pd.notna(row.get("director")) else "未知",
        "score": str(row["score"]) if pd.notna(row.get("score")) else "0",
        "rank": str(row["rank"]) if pd.notna(row.get("rank")) else "",
        "start_time": str(row["start_time"])
        if pd.notna(row.get("start_time"))
        else "",
    }


def get_home_feed():
    """
    首页分区数据：轮播、高分、近年上映、定档/热议、每日推荐。
    片单多为历史数据时，「即将上映」可能由高讨论度影片补足。
    """
    if _cache.get("douban_movies") is None:
        load_douban_data()
    df = _cache.get("douban_movies")
    if df is None or df.empty:
        return {
            "carousel": [],
            "high_rated": [],
            "recent": [],
            "upcoming": [],
            "daily": [],
        }

    df = df.copy()
    df["_score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0)
    df["_rank"] = pd.to_numeric(df["rank"], errors="coerce").fillna(99999)
    df["_date"] = df["start_time"].apply(_parse_first_date)
    df["_comments"] = df["comment_num"].apply(_parse_comment_num)

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    car_df = df.nsmallest(7, "_rank")
    carousel = [_row_to_home_movie(r) for _, r in car_df.iterrows()]

    high_sorted = df.sort_values("_score", ascending=False).head(12)
    high_rated = [_row_to_home_movie(r) for _, r in high_sorted.iterrows()]

    # ======== 正在上映 / 即将上映：TMDB API（后台缓存） ========
    recent = []
    upcoming = []

    use_tmdb_api = os.getenv("TMDB_HOME_API", "1").strip().lower() in ("1", "true", "yes", "on")
    if use_tmdb_api and tmdb_configured():
        recent = _cache.get("tmdb_home_now_playing") or []
        upcoming = _cache.get("tmdb_home_upcoming") or []
        # 内存为空时始终读落盘缓存（无代理/断网也能显示上次成功结果；不按 TTL 丢弃）
        if not recent or not upcoming:
            disk = read_cache() or {}
            if isinstance(disk, dict):
                recent = recent or (disk.get("now_playing") or [])
                upcoming = upcoming or (disk.get("upcoming") or [])
                ua = disk.get("updated_at")
                if ua is not None and _cache.get("tmdb_home_updated_at") is None:
                    try:
                        _cache["tmdb_home_updated_at"] = int(ua)
                    except Exception:
                        pass
            if recent:
                _cache["tmdb_home_now_playing"] = recent
            if upcoming:
                _cache["tmdb_home_upcoming"] = upcoming

    # 每日推荐：保持原逻辑（豆瓣高分池轮换）
    top_pool = df.sort_values("_score", ascending=False).head(30).reset_index(drop=True)
    daily = []
    if len(top_pool) > 0:
        n = len(top_pool)
        day0 = datetime.now().timetuple().tm_yday
        seen = set()
        for i in range(20):
            idx = (day0 + i * 7) % n
            m = _row_to_home_movie(top_pool.iloc[idx])
            if m["name"] not in seen:
                seen.add(m["name"])
                daily.append(m)
            if len(daily) >= 8:
                break

    return {
        "carousel": carousel,
        "high_rated": high_rated,
        "recent": recent,
        "upcoming": upcoming,
        "daily": daily,
    }


def _tmdb_row_to_home_item(r: dict) -> Optional[dict]:
    title = (r.get("title") or "").strip()
    if not title:
        return None
    gids = r.get("genre_ids") or []
    genres = ""
    try:
        if isinstance(gids, list) and gids:
            genres = tmdb_genres_cn_from_ids(gids)
    except Exception:
        genres = ""
    try:
        tid = int(r.get("id") or 0)
    except Exception:
        tid = 0
    return {
        "name": title,
        "display": title,
        # 列表页尽量使用 TMDB discover 自带的 genre_ids，避免额外 detail 请求
        "genres": genres or "",
        "directors": "",
        "score": str(r.get("vote_average") or "")[:4],
        "start_time": r.get("release_date") or "",
        "poster_url": r.get("poster_url"),
        "tmdb_id": tid or r.get("id"),
        "source": "tmdb_api",
    }


_tmdb_home_thread_started = False


def hydrate_tmdb_home_from_disk() -> None:
    """启动时把上次落盘的正在/即将上映灌回内存，无代理也能立刻有数据。"""
    if os.getenv("TMDB_HOME_API", "1").strip().lower() not in ("1", "true", "yes", "on"):
        return
    if not tmdb_configured():
        return
    disk = read_cache() or {}
    if not isinstance(disk, dict):
        return
    np = disk.get("now_playing") or []
    up = disk.get("upcoming") or []
    if np:
        _cache["tmdb_home_now_playing"] = np
    if up:
        _cache["tmdb_home_upcoming"] = up
    ua = disk.get("updated_at")
    if ua is not None:
        try:
            _cache["tmdb_home_updated_at"] = int(ua)
        except Exception:
            pass
    if np or up:
        print(
            f"✅ [TMDB] 本地缓存恢复：正在 {len(np)} / 即将 {len(up)}，"
            f"刷新间隔 {min_refresh_seconds() // 3600}h"
        )


def start_tmdb_home_updater() -> None:
    """后台按「至少一天」间隔尝试更新 TMDB 首页分区；平时用内存/落盘即可。"""
    global _tmdb_home_thread_started
    if _tmdb_home_thread_started:
        return
    _tmdb_home_thread_started = True

    hydrate_tmdb_home_from_disk()

    def run():
        wake = int(os.getenv("TMDB_HOME_REFRESH_SEC", "1800"))
        ttl = min_refresh_seconds()
        while True:
            try:
                on = os.getenv("TMDB_HOME_API", "1").strip().lower() in ("1", "true", "yes", "on")
                if on and tmdb_configured():
                    uat = _cache.get("tmdb_home_updated_at")
                    if uat is None:
                        d = read_cache() or {}
                        if isinstance(d, dict) and d.get("updated_at") is not None:
                            try:
                                uat = int(d.get("updated_at"))
                            except Exception:
                                uat = None
                    # 未满最小刷新间隔且有数据：不请求外网
                    if is_fresh(uat, ttl) and (
                        (_cache.get("tmdb_home_now_playing") or [])
                        or (_cache.get("tmdb_home_upcoming") or [])
                    ):
                        time.sleep(max(60, wake))
                        continue

                    np_rows = now_playing_movies(12)
                    up_rows = upcoming_movies(12)
                    now_items = [x for x in (_tmdb_row_to_home_item(r) for r in np_rows) if x]
                    up_items = [x for x in (_tmdb_row_to_home_item(r) for r in up_rows) if x]

                    # 外网全空时不覆盖已有缓存（避免代理关掉把列表刷没）
                    if not now_items and not up_items:
                        _cache["tmdb_home_error"] = "empty_response"
                        time.sleep(max(60, wake))
                        continue

                    if not now_items:
                        now_items = list(_cache.get("tmdb_home_now_playing") or [])
                        if not now_items and isinstance(read_cache() or {}, dict):
                            now_items = list((read_cache() or {}).get("now_playing") or [])
                    if not up_items:
                        up_items = list(_cache.get("tmdb_home_upcoming") or [])
                        if not up_items and isinstance(read_cache() or {}, dict):
                            up_items = list((read_cache() or {}).get("upcoming") or [])

                    # 将 TMDB CDN 海报落盘到 tmdb_home_cache.json 同目录，并“统一清理”旧文件
                    # 注意：不能对 now/up 分别 purge，否则会互相删对方海报导致列表变白块
                    try:
                        materialize_home_posters_for_sections(now_items, up_items)
                    except Exception:
                        pass

                    _cache["tmdb_home_now_playing"] = now_items
                    _cache["tmdb_home_upcoming"] = up_items
                    _cache["tmdb_home_updated_at"] = int(time.time())
                    _cache["tmdb_home_error"] = ""
                    write_cache(
                        {
                            "updated_at": _cache["tmdb_home_updated_at"],
                            "now_playing": now_items,
                            "upcoming": up_items,
                        }
                    )
            except Exception as e:
                _cache["tmdb_home_error"] = type(e).__name__
            time.sleep(max(60, wake))

    t = threading.Thread(target=run, name="tmdb-home-updater", daemon=True)
    t.start()
