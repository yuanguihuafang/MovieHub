"""
backend/api/routers/home.py

首页相关接口（对应前端“首页”页面）。

- GET /api/home/feed   首页聚合分区数据（轮播/近期/高分等，来自缓存/本地数据）
- GET /api/home/vedio  首页轮播视频列表（backend/data/vedio 下的本地视频）
"""

from __future__ import annotations

import os

from fastapi import APIRouter

from backend.services.poster_service import enrich_home_feed_posters
from backend.recommender import get_home_feed

router = APIRouter(tags=["home"])


@router.get("/api/home/feed")
async def api_home_feed():
    """
    首页分区：轮播、高分、近年上映、热议/定档、每日推荐（无需登录）。

    注意：为保证首屏速度，只补充“本地已缓存”的海报地址（不会在接口内同步触发外网下载）。
    """
    data = get_home_feed()
    try:
        enrich_home_feed_posters(data, max_lookups=80, allow_remote=False)
    except Exception:
        # 海报补全失败不影响主要数据返回
        pass
    return {"success": True, **(data or {})}


@router.get("/api/home/vedio")
async def api_home_vedio():
    """
    首页轮播视频列表（backend/data/vedio 下的 mp4/webm/ogg），按文件名排序。

    前端会把返回的 `url` 直接作为视频地址使用（由 `backend/main.py` 静态挂载 `/api/vedio` 提供文件）。
    """
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # backend/
    vedio_dir = os.path.join(backend_dir, "data", "vedio")
    if not os.path.isdir(vedio_dir):
        return {"success": True, "videos": []}

    rows: list[dict] = []
    for fn in sorted(os.listdir(vedio_dir)):
        low = fn.lower()
        if not (low.endswith(".mp4") or low.endswith(".webm") or low.endswith(".ogg")):
            continue
        rows.append({"name": fn, "url": f"/api/vedio/{fn}"})
    return {"success": True, "videos": rows}

