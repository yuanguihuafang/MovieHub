"""
backend/api/routers/poster_cache.py

海报本地缓存下发接口。

前端展示电影海报时，后端会把远程海报缓存到本地（`backend/data/poster_cache/`），并返回：
- /api/poster-cache/{sha256}.{ext}

该路由负责在同源下发缓存文件，避免浏览器直连外部 CDN 触发防盗链裂图。
"""

from __future__ import annotations

import base64

from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.responses import Response

from backend.services.poster_file_cache import mimetype_for_path, resolve_safe_cache_path
from backend.services.tmdb_home_poster_cache import mimetype_for_path as home_mimetype_for_path
from backend.services.tmdb_home_poster_cache import resolve_safe_home_poster_path

router = APIRouter(tags=["poster-cache"])

# 1x1 透明 PNG（缓存缺失时占位，避免前端大量 404）
_TRANSPARENT_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/erK0qkAAAAASUVORK5CYII="
)


@router.get("/api/poster-cache/{filename}")
async def api_poster_cache(filename: str):
    path = resolve_safe_cache_path(filename)
    if path is None:
        return Response(content=_TRANSPARENT_PNG, media_type="image/png")
    return FileResponse(path, media_type=mimetype_for_path(path))


@router.get("/api/tmdb-home-poster/{filename}")
async def api_tmdb_home_poster(filename: str):
    path = resolve_safe_home_poster_path(filename)
    if path is None:
        return Response(content=_TRANSPARENT_PNG, media_type="image/png")
    return FileResponse(path, media_type=home_mimetype_for_path(path))

