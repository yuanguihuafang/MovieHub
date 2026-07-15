"""
backend/api/routers/user.py

用户侧接口（对应前端页面/模块）。

- 个人中心 / 修改密码
- 片单页（收藏/已看过/反馈/片单）
- 消息中心
- 推荐记录
"""

from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.api.deps import get_current_user
from backend.db.database import (
    FEEDBACK_KEEP,
    feedback_delete,
    feedback_get,
    feedback_list,
    feedback_upsert,
    hash_password,
    log_list,
    notification_list,
    notification_mark_all_read,
    notification_mark_read,
    notification_unread_count,
    playlist_bulk_add_from_movies,
    playlist_create,
    playlist_delete,
    playlist_item_add,
    playlist_item_remove,
    playlist_items_list,
    playlist_list,
    playlist_update,
    user_update_password,
    user_update_preferred_genres,
    fav_add,
    fav_remove,
    fav_list,
    watched_add,
    watched_remove,
    watched_list,
)
from backend.services.poster_service import resolve_movie_poster_cached_only
from backend.schemas.user import (
    NotificationMarkReadRequest,
    PlaylistCreateRequest,
    PlaylistItemAddRequest,
    PlaylistUpdateRequest,
    SaveRecommendationRequest,
    UserFeedbackUpsertRequest,
    UserFavoriteAddRequest,
    UserFavoriteRemoveRequest,
    UserPreferencesRequest,
    UserUpdatePasswordRequest,
    UserWatchedAddRequest,
)

router = APIRouter(tags=["user"])


@router.get("/api/user/profile")
async def api_get_user_profile(request: Request, user: dict = Depends(get_current_user)):
    pref = (user.get("preferred_genres") or "").strip()
    pref_list = [x.strip() for x in pref.split(",") if x.strip()] if pref else []
    return {
        "success": True,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "created_at": str(user["created_at"]),
            "preferred_genres": pref_list,
            "review_muted_until": str(user.get("review_muted_until") or ""),
            "review_mute_reason": str(user.get("review_mute_reason") or ""),
        },
    }


@router.put("/api/user/preferences")
async def api_update_user_preferences(body: UserPreferencesRequest, user: dict = Depends(get_current_user)):
    seen = []
    for g in body.preferred_genres or []:
        g = (g or "").strip()
        if g and g not in seen:
            seen.append(g)
    csv = ",".join(seen)[:500]
    user_update_preferred_genres(user["id"], csv)
    return {"success": True, "preferred_genres": seen}


@router.put("/api/user/password")
async def api_update_own_password(body: UserUpdatePasswordRequest, user: dict = Depends(get_current_user)):
    if user["password"] != hash_password(body.old_password):
        raise HTTPException(status_code=400, detail="原密码错误")
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="密码至少6位")
    user_update_password(user["id"], body.new_password)
    return {"success": True, "message": "密码修改成功"}


@router.get("/api/user/favorites")
async def api_get_own_favorites(request: Request, user: dict = Depends(get_current_user)):
    rows = fav_list(user["id"])
    return {
        "success": True,
        "favorites": [
            {
                "id": r["id"],
                "movie_name": r["movie_name"],
                "movie_source": r.get("movie_source", ""),
                "tmdb_id": r.get("tmdb_id"),
                "genres": r.get("genres", ""),
                "poster_url": resolve_movie_poster_cached_only(r["movie_name"]) or "",
                "added_at": str(r["added_at"]),
            }
            for r in rows
        ],
    }


@router.post("/api/user/favorites")
async def api_add_own_favorite(body: UserFavoriteAddRequest, user: dict = Depends(get_current_user)):
    ok = fav_add(
        user["id"],
        body.movie_name.strip(),
        body.genres or "",
        (body.movie_source or "kg").strip() or "kg",
        tmdb_id=body.tmdb_id,
    )
    if ok:
        return {"success": True, "message": "已收藏"}
    raise HTTPException(status_code=400, detail="已在收藏列表中")


@router.delete("/api/user/favorites")
async def api_remove_own_favorite(body: UserFavoriteRemoveRequest, user: dict = Depends(get_current_user)):
    ok = fav_remove(user["id"], body.movie_name.strip())
    if ok:
        return {"success": True, "message": "已取消收藏"}
    raise HTTPException(status_code=404, detail="未找到该收藏")


@router.get("/api/user/watched")
async def api_get_watched(
    request: Request,
    limit: int = Query(200, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    rows = watched_list(user["id"], limit)
    return {
        "success": True,
        "watched": [
            {
                "id": r["id"],
                "movie_name": r["movie_name"],
                "movie_source": r.get("movie_source", ""),
                "tmdb_id": r.get("tmdb_id"),
                "genres": r.get("genres", ""),
                "poster_url": resolve_movie_poster_cached_only(r["movie_name"]) or "",
                "watched_at": str(r["watched_at"]),
            }
            for r in rows
        ],
    }


@router.post("/api/user/watched")
async def api_add_watched(body: UserWatchedAddRequest, user: dict = Depends(get_current_user)):
    watched_add(
        user["id"],
        body.movie_name.strip(),
        body.genres or "",
        movie_source=(body.movie_source or "kg"),
        tmdb_id=body.tmdb_id,
    )
    return {"success": True, "message": "已标记为看过"}


@router.delete("/api/user/watched")
async def api_remove_watched(
    movie_name: str = Query(..., description="与 watched_movies.movie_name 一致"),
    user: dict = Depends(get_current_user),
):
    ok = watched_remove(user["id"], movie_name.strip())
    if ok:
        return {"success": True, "message": "已取消标记"}
    raise HTTPException(status_code=404, detail="未找到该记录")


@router.get("/api/user/recommend-logs")
async def api_get_own_recommend_logs(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
):
    rows = log_list(user["id"], limit)
    out = []
    for r in rows or []:
        # 推荐快照：与消息中心 recommend_done payload 同结构（简版，供个人中心直接复用前端弹窗）
        final_movies = []
        try:
            import json

            fm_raw = r.get("final_movies")
            if isinstance(fm_raw, str) and fm_raw.strip():
                fm = json.loads(fm_raw)
                if isinstance(fm, list):
                    for x in fm[:48]:
                        if isinstance(x, str) and x.strip():
                            final_movies.append({"display": x.strip(), "name": x.strip(), "source": ""})
                        elif isinstance(x, dict):
                            nm = str(x.get("name") or "").strip()
                            if not nm:
                                continue
                            final_movies.append(
                                {
                                    "name": nm,
                                    "display": str(x.get("display") or nm).strip(),
                                    "source": str(x.get("source") or "").strip(),
                                }
                            )
        except Exception:
            final_movies = []

        payload = {
            "snapshot_version": 1,
            "recommend_text": str(r.get("recommend_text") or ""),
            "final_movies": final_movies,
            "kg_movies": [],
            "rag_movies": [],
            "elapsed_ms": int(r.get("elapsed_ms") or 0),
            "user_input": str(r.get("user_input") or "")[:1200],
        }
        out.append(
            {
                "id": r.get("id"),
                "user_input": r.get("user_input") or "",
                "created_at": str(r.get("created_at") or ""),
                "snapshot_payload": payload,
            }
        )
    return {"success": True, "logs": out}


@router.get("/api/user/feedback")
async def api_get_user_feedback(
    vote: Optional[str] = Query(None, description="like/dislike"),
    blocked: Optional[bool] = Query(None, description="true/false"),
    limit: int = Query(200, ge=1, le=500),
    user: dict = Depends(get_current_user),
):
    rows = feedback_list(user["id"], vote=vote, blocked=blocked, limit=limit)
    return {"success": True, "feedback": rows}


@router.put("/api/user/feedback")
async def api_upsert_user_feedback(body: UserFeedbackUpsertRequest, user: dict = Depends(get_current_user)):
    movie_name = (body.movie_name or "").strip()
    if not movie_name:
        raise HTTPException(status_code=400, detail="movie_name 不能为空")
    if body.vote is not None and body.vote not in ("like", "dislike"):
        raise HTTPException(status_code=400, detail="vote 只能是 like/dislike 或 null")
    if body.note is not None and len(body.note) > 500:
        raise HTTPException(status_code=400, detail="短评最多 500 字")

    payload = body.dict(exclude_unset=True)
    src = (payload.get("movie_source") or body.movie_source or "kg") if isinstance(payload, dict) else (body.movie_source or "kg")
    feedback_upsert(
        user["id"],
        movie_name,
        movie_source=src,
        tmdb_id=(payload.get("tmdb_id", body.tmdb_id) if isinstance(payload, dict) else body.tmdb_id),
        vote=payload["vote"] if "vote" in payload else FEEDBACK_KEEP,
        blocked=payload["blocked"] if "blocked" in payload else FEEDBACK_KEEP,
        note=payload["note"] if "note" in payload else FEEDBACK_KEEP,
    )
    row = feedback_get(user["id"], movie_name, movie_source=src)
    return {"success": True, "feedback": row}


@router.delete("/api/user/feedback")
async def api_delete_user_feedback(
    movie_name: str = Query(..., description="电影名"),
    user: dict = Depends(get_current_user),
):
    ok = feedback_delete(user["id"], (movie_name or "").strip())
    if ok:
        return {"success": True}
    raise HTTPException(status_code=404, detail="未找到该反馈记录")


@router.get("/api/user/playlists")
async def api_get_playlists(user: dict = Depends(get_current_user)):
    rows = playlist_list(user["id"])
    return {"success": True, "playlists": rows}


@router.post("/api/user/playlists")
async def api_create_playlist(body: PlaylistCreateRequest, user: dict = Depends(get_current_user)):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name 不能为空")
    pid = playlist_create(user["id"], name, body.description or "")
    return {"success": True, "id": pid}


@router.put("/api/user/playlists/{playlist_id}")
async def api_update_playlist(
    playlist_id: int,
    body: PlaylistUpdateRequest,
    user: dict = Depends(get_current_user),
):
    ok = playlist_update(user["id"], int(playlist_id), body.name, body.description)
    if ok:
        return {"success": True}
    raise HTTPException(status_code=404, detail="片单不存在")


@router.delete("/api/user/playlists/{playlist_id}")
async def api_delete_playlist(playlist_id: int, user: dict = Depends(get_current_user)):
    ok = playlist_delete(user["id"], int(playlist_id))
    if ok:
        return {"success": True}
    raise HTTPException(status_code=404, detail="片单不存在")


@router.get("/api/user/playlists/{playlist_id}/items")
async def api_get_playlist_items(playlist_id: int, user: dict = Depends(get_current_user)):
    rows = playlist_items_list(user["id"], int(playlist_id))
    return {"success": True, "items": rows}


@router.post("/api/user/playlists/{playlist_id}/items")
async def api_add_playlist_item(
    playlist_id: int,
    body: PlaylistItemAddRequest,
    user: dict = Depends(get_current_user),
):
    movie_name = (body.movie_name or "").strip()
    if not movie_name:
        raise HTTPException(status_code=400, detail="movie_name 不能为空")
    ok, _ins = playlist_item_add(
        user["id"],
        int(playlist_id),
        movie_name,
        movie_source=(body.movie_source or ""),
        tmdb_id=body.tmdb_id,
        genres=(body.genres or ""),
        poster_url=(body.poster_url or ""),
        genres_str=(body.genres_str or ""),
        score_str=(body.score_str or ""),
        short_review=(body.short_review or ""),
    )
    if ok:
        return {"success": True}
    raise HTTPException(status_code=404, detail="片单不存在或无权限")


@router.delete("/api/user/playlists/{playlist_id}/items")
async def api_remove_playlist_item(
    playlist_id: int,
    movie_name: str = Query(..., description="电影名"),
    user: dict = Depends(get_current_user),
):
    ok = playlist_item_remove(user["id"], int(playlist_id), (movie_name or "").strip())
    if ok:
        return {"success": True}
    raise HTTPException(status_code=404, detail="未找到该条目")


@router.post("/api/user/playlists/{playlist_id}/save-recommendation")
async def api_save_recommendation_to_playlist(
    playlist_id: int,
    body: SaveRecommendationRequest,
    user: dict = Depends(get_current_user),
):
    movies = []
    for it in body.movies or []:
        if not isinstance(it, dict):
            continue
        nm = (it.get("name") or "").strip()
        if not nm:
            continue
        movies.append(
            {
                "name": nm,
                "source": (it.get("source") or ""),
                "tmdb_id": it.get("tmdb_id"),
                "genres": (it.get("genres") or ""),
                "poster_url": (it.get("poster_url") or ""),
                "genres_str": (it.get("genres_str") or ""),
                "score_str": (it.get("score_str") or ""),
                "short_review": (it.get("short_review") or ""),
            }
        )
    if not movies:
        raise HTTPException(status_code=400, detail="movies 不能为空")
    res = playlist_bulk_add_from_movies(user["id"], int(playlist_id), movies)
    return {"success": True, **res}


@router.get("/api/user/notifications")
async def api_user_notifications_list(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: dict = Depends(get_current_user),
):
    rows = notification_list(int(user["id"]), limit=limit, offset=offset)
    return {"success": True, "notifications": rows}


@router.get("/api/user/notifications/unread-count")
async def api_user_notifications_unread_count(user: dict = Depends(get_current_user)):
    n = notification_unread_count(int(user["id"]))
    return {"success": True, "unread": int(n)}


@router.post("/api/user/notifications/read")
async def api_user_notifications_mark_read(
    body: NotificationMarkReadRequest,
    user: dict = Depends(get_current_user),
):
    if body.mark_all:
        n = notification_mark_all_read(int(user["id"]))
        return {"success": True, "updated": int(n)}
    n = notification_mark_read(int(user["id"]), list(body.ids or []))
    return {"success": True, "updated": int(n)}

