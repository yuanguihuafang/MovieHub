"""
backend/api/routers/reviews.py

影评社区接口（对应前端“影评”页面）。

- 影评增删改查
- 评论/回复
- 点赞/取消点赞

管理员相关接口暂时放在这里（后续可再拆到 admin router）：
- /api/admin/reviews*
- /api/admin/review-comments*
- /api/admin/users/{user_id}/review-mute
"""

from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from backend.recommender import _cache
from backend.recommender.browse import load_tmdb_movies_data
from backend.api.deps import ensure_not_muted, get_current_admin, get_current_user, try_get_current_user
from backend.db.database import (
    DBConnection,
    admin_review_comments_list,
    admin_reviews_list,
    admin_user_clear_review_mute,
    admin_user_set_review_mute,
    review_comment_add,
    review_comment_delete,
    review_comments_list,
    review_delete,
    review_get,
    review_like_set,
    review_like_unset,
    review_get_for_user_movie,
    review_list,
    review_upsert,
)
from backend.schemas.reviews import AdminReviewMuteRequest, ReviewCommentAddRequest, ReviewLikeRequest, ReviewUpsertRequest

router = APIRouter(tags=["reviews"])


@router.get("/api/reviews/movies/search")
async def api_reviews_movie_search(
    q: str = Query("", description="关键词"),
    limit: int = Query(10, ge=1, le=30),
):
    """影评发帖选电影：从系统已加载的数据源里做轻量搜索。"""
    q = (q or "").strip()
    if not q:
        return {"success": True, "movies": []}

    movies: list[dict] = []

    # 1) Douban CSV
    try:
        df = _cache.get("douban_movies")
        if df is not None and not df.empty:
            m = df[df["title"].astype(str).str.contains(q, case=False, na=False)].head(int(limit))
            for _, r in m.iterrows():
                title = str(r.get("title") or "").strip()
                if not title:
                    continue
                types = r.get("type_simplified") or []
                g = "/".join(types) if isinstance(types, list) else str(types)
                movies.append({"movie_name": title, "display": title, "source": "douban", "genres": g})
    except Exception:
        pass

    # 2) TMDB-CSV
    try:
        if _cache.get("tmdb_movies") is None:
            load_tmdb_movies_data()
        df = _cache.get("tmdb_movies")
        if df is not None and not df.empty:
            m = df[df["title"].astype(str).str.contains(q, case=False, na=False)].head(int(limit))
            for _, r in m.iterrows():
                title = str(r.get("title") or "").strip()
                if not title:
                    continue
                types = r.get("type_simplified") or []
                g = "/".join(types) if isinstance(types, list) else str(types)
                movies.append({"movie_name": title, "display": title, "source": "tmdb_csv", "genres": g})
    except Exception:
        pass

    # 3) KG 实体（可选）
    try:
        ents = list(_cache.get("movie_entities") or [])
        ql = q.lower()
        hit: list[str] = []
        for e in ents:
            s = str(e)
            if ql in s.lower().replace("_", " "):
                hit.append(s)
            if len(hit) >= int(limit):
                break
        for e in hit:
            disp = e.replace("_", " ")
            movies.append({"movie_name": e, "display": disp, "source": "kg", "genres": ""})
    except Exception:
        pass

    # 去重（按 display）
    seen: set[str] = set()
    out: list[dict] = []
    for m in movies:
        k = (m.get("display") or m.get("movie_name") or "").strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(m)
        if len(out) >= int(limit):
            break
    return {"success": True, "movies": out}


@router.get("/api/reviews/board")
async def api_reviews_board(
    movie_limit: int = Query(20, ge=1, le=80),
    movie_offset: int = Query(0, ge=0),
    per_movie: int = Query(5, ge=1, le=20),
    user: Optional[dict] = Depends(try_get_current_user),
):
    """
    影评广场（按电影聚合）：
    - 电影按总点赞数排序
    - 每部电影返回前 per_movie 条影评（按点赞数排序）
    """
    with DBConnection() as (_conn, cur):
        cur.execute(
            "SELECT COUNT(DISTINCT movie_name) AS c FROM reviews WHERE TRIM(COALESCE(content, '')) <> ''"
        )
        row = cur.fetchone() or {}
        total_movies = int(row.get("c") or 0)

        cur.execute(
            """
            SELECT
              r.movie_name,
              MAX(r.movie_source) AS movie_source,
              COUNT(1) AS review_count,
              COALESCE(SUM((SELECT COUNT(1) FROM review_likes l WHERE l.target_type='review' AND l.target_id=r.id)), 0) AS total_like_count
            FROM reviews r
            WHERE TRIM(COALESCE(r.content, '')) <> ''
            GROUP BY r.movie_name
            ORDER BY total_like_count DESC, review_count DESC, MAX(r.updated_at) DESC
            LIMIT %s OFFSET %s
            """,
            (int(movie_limit), int(movie_offset)),
        )
        movies = cur.fetchall() or []

    out: list[dict] = []
    all_review_ids: list[int] = []

    for m in movies:
        name = (m.get("movie_name") or "").strip()
        if not name:
            continue
        with DBConnection() as (_conn, cur):
            cur.execute(
                """
                SELECT
                  r.id,
                  r.user_id,
                  u.username,
                  r.movie_name,
                  r.movie_source,
                  r.rating,
                  r.content,
                  r.created_at,
                  r.updated_at,
                  (SELECT COUNT(1) FROM review_comments c WHERE c.review_id=r.id) AS comment_count,
                  (SELECT COUNT(1) FROM review_likes l WHERE l.target_type='review' AND l.target_id=r.id) AS like_count,
                  COALESCE(NULLIF(ums_exact.note, ''), NULLIF(ums_any.note_any, ''), '') AS feedback_note
                FROM reviews r
                JOIN users u ON u.id=r.user_id
                LEFT JOIN user_movie_state ums_exact
                  ON ums_exact.user_id=r.user_id
                 AND ums_exact.movie_name=r.movie_name
                 AND ums_exact.movie_source=COALESCE(NULLIF(r.movie_source, ''), 'kg')
                LEFT JOIN (
                  SELECT user_id, movie_name, MAX(NULLIF(note, '')) AS note_any
                  FROM user_movie_state
                  GROUP BY user_id, movie_name
                ) ums_any
                  ON ums_any.user_id=r.user_id AND ums_any.movie_name=r.movie_name
                WHERE r.movie_name=%s AND TRIM(COALESCE(r.content, '')) <> ''
                ORDER BY like_count DESC, comment_count DESC, r.updated_at DESC
                LIMIT %s OFFSET 0
                """,
                (name, int(per_movie)),
            )
            rows = cur.fetchall() or []

        for r in rows:
            if r.get("id"):
                all_review_ids.append(int(r["id"]))

        out.append(
            {
                "movie_name": name,
                "movie_source": m.get("movie_source") or "",
                "review_count": int(m.get("review_count") or 0),
                "total_like_count": int(m.get("total_like_count") or 0),
                "reviews": rows,
            }
        )

    # 标注 my_liked（批量）
    if user and all_review_ids:
        try:
            with DBConnection() as (_conn, cur):
                cur.execute(
                    "SELECT target_id FROM review_likes WHERE target_type='review' AND user_id=%s AND target_id IN (%s)"
                    % ",".join(["%s"] * len(all_review_ids)),
                    tuple([int(user["id"])] + all_review_ids),
                )
                liked_ids = {
                    int(x.get("target_id")) for x in (cur.fetchall() or []) if x.get("target_id")
                }
            for block in out:
                for r in block.get("reviews") or []:
                    rid = int(r.get("id") or 0)
                    r["my_liked"] = bool(rid and rid in liked_ids)
        except Exception:
            for block in out:
                for r in block.get("reviews") or []:
                    r["my_liked"] = False
    else:
        for block in out:
            for r in block.get("reviews") or []:
                r["my_liked"] = False

    return {"success": True, "movies": out, "total_movies": total_movies}


@router.get("/api/reviews/by-movie")
async def api_reviews_by_movie(
    movie_name: str = Query(...),
    sort: str = Query("like_count", description="like_count|recent"),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
    has_text_only: bool = Query(
        False,
        description="为 true 时仅返回含短评正文的条目（影评广场/列表）；为 false 时包含仅评分记录",
    ),
    user: Optional[dict] = Depends(try_get_current_user),
):
    name = (movie_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="movie_name 不能为空")
    order_by = "like_count DESC, comment_count DESC, r.updated_at DESC"
    if sort == "recent":
        order_by = "r.updated_at DESC"

    text_clause = " AND TRIM(COALESCE(r.content, '')) <> ''" if has_text_only else ""

    with DBConnection() as (_conn, cur):
        cur.execute(
            f"""
            SELECT
              r.id,
              r.user_id,
              u.username,
              r.movie_name,
              r.movie_source,
              r.rating,
              r.content,
              r.created_at,
              r.updated_at,
              (SELECT COUNT(1) FROM review_comments c WHERE c.review_id=r.id) AS comment_count,
              (SELECT COUNT(1) FROM review_likes l WHERE l.target_type='review' AND l.target_id=r.id) AS like_count,
              COALESCE(NULLIF(ums_exact.note, ''), NULLIF(ums_any.note_any, ''), '') AS feedback_note
            FROM reviews r
            JOIN users u ON u.id=r.user_id
            LEFT JOIN user_movie_state ums_exact
              ON ums_exact.user_id=r.user_id
             AND ums_exact.movie_name=r.movie_name
             AND ums_exact.movie_source=COALESCE(NULLIF(r.movie_source, ''), 'kg')
            LEFT JOIN (
              SELECT user_id, movie_name, MAX(NULLIF(note, '')) AS note_any
              FROM user_movie_state
              GROUP BY user_id, movie_name
            ) ums_any
              ON ums_any.user_id=r.user_id AND ums_any.movie_name=r.movie_name
            WHERE r.movie_name=%s{text_clause}
            ORDER BY {order_by}
            LIMIT %s OFFSET %s
            """,
            (name, int(limit), int(offset)),
        )
        rows = cur.fetchall() or []

    if user and rows:
        try:
            ids = [int(r.get("id") or 0) for r in rows if int(r.get("id") or 0) > 0]
            liked_ids = set()
            if ids:
                with DBConnection() as (_conn, cur):
                    cur.execute(
                        "SELECT target_id FROM review_likes WHERE target_type='review' AND user_id=%s AND target_id IN (%s)"
                        % ",".join(["%s"] * len(ids)),
                        tuple([int(user["id"])] + ids),
                    )
                    liked_ids = {int(x.get("target_id")) for x in (cur.fetchall() or []) if x.get("target_id")}
            for r in rows:
                rid = int(r.get("id") or 0)
                r["my_liked"] = bool(rid and rid in liked_ids)
        except Exception:
            for r in rows:
                r["my_liked"] = False
    else:
        for r in rows:
            r["my_liked"] = False

    return {"success": True, "reviews": rows}


@router.get("/api/reviews")
async def api_reviews_list(
    sort: str = Query("comment_count", description="comment_count|like_count|recent"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    request: Request = None,
    user: Optional[dict] = Depends(try_get_current_user),
):
    rows = review_list(sort=sort, limit=limit, offset=offset)
    # 标注当前用户是否点赞
    if user and rows:
        try:
            ids = [int(r.get("id") or 0) for r in rows if int(r.get("id") or 0) > 0]
            liked_ids = set()
            if ids:
                with DBConnection() as (conn, cur):
                    cur.execute(
                        "SELECT target_id FROM review_likes WHERE target_type='review' AND user_id=%s AND target_id IN (%s)"
                        % ",".join(["%s"] * len(ids)),
                        tuple([int(user["id"])] + ids),
                    )
                    liked_ids = {int(x.get("target_id")) for x in (cur.fetchall() or []) if x.get("target_id")}
            for r in rows:
                rid = int(r.get("id") or 0)
                r["my_liked"] = bool(rid and rid in liked_ids)
        except Exception:
            for r in rows:
                r["my_liked"] = False
    else:
        for r in rows:
            r["my_liked"] = False
    return {"success": True, "reviews": rows}


@router.get("/api/reviews/mine")
async def api_reviews_mine_for_movie(
    movie_name: str = Query(..., description="电影名（与 reviews 表中一致）"),
    user: dict = Depends(get_current_user),
):
    """当前登录用户对某影片的一条影评记录（含仅评分、短评），用于「看过」弹窗回填。"""
    name = (movie_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="movie_name 不能为空")
    r = review_get_for_user_movie(int(user["id"]), name)
    return {"success": True, "review": r}


@router.get("/api/reviews/{review_id}")
async def api_reviews_detail(review_id: int, user: Optional[dict] = Depends(try_get_current_user)):
    r = review_get(int(review_id))
    if not r:
        raise HTTPException(status_code=404, detail="影评不存在")
    comments = review_comments_list(int(review_id))
    review_like_count = 0
    try:
        with DBConnection() as (conn, cur):
            cur.execute(
                "SELECT COUNT(1) AS c FROM review_likes WHERE target_type='review' AND target_id=%s",
                (int(review_id),),
            )
            row = cur.fetchone() or {}
            review_like_count = int(row.get("c") or 0)
    except Exception:
        review_like_count = 0
    my_likes = set()
    if user:
        try:
            with DBConnection() as (conn, cur):
                cur.execute(
                    "SELECT target_type, target_id FROM review_likes WHERE user_id=%s AND ((target_type='review' AND target_id=%s) OR (target_type='comment' AND target_id IN (SELECT id FROM review_comments WHERE review_id=%s)))",
                    (user["id"], int(review_id), int(review_id)),
                )
                for row in cur.fetchall() or []:
                    my_likes.add(f"{row['target_type']}:{row['target_id']}")
        except Exception:
            my_likes = set()
    return {
        "success": True,
        "review": r,
        "review_like_count": review_like_count,
        "comments": comments,
        "my_likes": list(my_likes),
    }


@router.put("/api/reviews")
async def api_review_upsert(body: dict = Body(...), user: dict = Depends(get_current_user)):
    ensure_not_muted(user["id"])
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")

    raw_name = body.get("movie_name", None)
    if raw_name is None:
        raw_name = body.get("movieName", None)
    name = (raw_name or "").strip() if isinstance(raw_name, str) else str(raw_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="movie_name 不能为空")

    raw_source = body.get("movie_source", None)
    if raw_source is None:
        raw_source = body.get("movieSource", None)
    movie_source = (raw_source or "").strip() if isinstance(raw_source, str) else str(raw_source or "").strip()

    raw_content = body.get("content", "")
    if raw_content is None:
        raw_content = ""
    content = (raw_content or "").strip() if isinstance(raw_content, str) else str(raw_content).strip()

    raw_rating = body.get("rating", None)
    if raw_rating in ("", " ", "null"):
        raw_rating = None
    rating: Optional[float] = None
    if raw_rating is not None:
        try:
            rating = float(raw_rating) if isinstance(raw_rating, str) else float(raw_rating)
        except Exception:
            raise HTTPException(status_code=400, detail="rating 必须是 1-10 的数字或为空")

    if len(content) > 800:
        raise HTTPException(status_code=400, detail="内容最多 800 字")
    if rating is not None and (rating < 1 or rating > 10):
        raise HTTPException(status_code=400, detail="评分范围 1-10（可为小数），或不评分")
    rid = review_upsert(user["id"], name, movie_source, rating, content)
    return {"success": True, "id": rid}


@router.delete("/api/reviews/{review_id}")
async def api_review_delete(review_id: int, user: dict = Depends(get_current_user)):
    ok = review_delete(user["id"], int(review_id), as_admin=False)
    if ok:
        return {"success": True}
    raise HTTPException(status_code=404, detail="未找到或无权限")


@router.post("/api/reviews/{review_id}/comments")
async def api_review_comment_add(review_id: int, body: ReviewCommentAddRequest, user: dict = Depends(get_current_user)):
    ensure_not_muted(user["id"])
    if not (body.content or "").strip():
        raise HTTPException(status_code=400, detail="内容不能为空")
    if len(body.content) > 800:
        raise HTTPException(status_code=400, detail="内容最多 800 字")
    cid = review_comment_add(user["id"], int(review_id), body.content, body.parent_id)
    if cid:
        return {"success": True, "id": cid}
    raise HTTPException(status_code=400, detail="评论失败")


@router.delete("/api/reviews/comments/{comment_id}")
async def api_review_comment_delete(comment_id: int, user: dict = Depends(get_current_user)):
    ok = review_comment_delete(user["id"], int(comment_id), as_admin=False)
    if ok:
        return {"success": True}
    raise HTTPException(status_code=404, detail="未找到或无权限")


@router.post("/api/reviews/likes")
async def api_review_like_set(body: ReviewLikeRequest, user: dict = Depends(get_current_user)):
    ok = review_like_set(user["id"], body.target_type, int(body.target_id))
    if ok:
        return {"success": True}
    raise HTTPException(status_code=400, detail="点赞失败")


@router.delete("/api/reviews/likes")
async def api_review_like_unset(
    target_type: str = Query(...),
    target_id: int = Query(...),
    user: dict = Depends(get_current_user),
):
    ok = review_like_unset(user["id"], target_type, int(target_id))
    if ok:
        return {"success": True}
    raise HTTPException(status_code=404, detail="未点赞")


# ==============================
# Admin moderation (reviews)
# ==============================


@router.get("/api/admin/reviews")
async def api_admin_reviews(
    limit: int = Query(100, ge=1, le=300),
    offset: int = Query(0, ge=0),
    user_id: Optional[int] = Query(None),
    movie_name: Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin),
):
    rows = admin_reviews_list(limit=limit, offset=offset, user_id=user_id, movie_name=movie_name)
    return {"success": True, "reviews": rows}


@router.delete("/api/admin/reviews/{review_id}")
async def api_admin_review_delete(review_id: int, admin: dict = Depends(get_current_admin)):
    ok = review_delete(admin["id"], int(review_id), as_admin=True)
    if ok:
        return {"success": True}
    raise HTTPException(status_code=404, detail="未找到")


@router.get("/api/admin/review-comments")
async def api_admin_review_comments(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user_id: Optional[int] = Query(None),
    review_id: Optional[int] = Query(None),
    admin: dict = Depends(get_current_admin),
):
    rows = admin_review_comments_list(limit=limit, offset=offset, user_id=user_id, review_id=review_id)
    return {"success": True, "comments": rows}


@router.delete("/api/admin/review-comments/{comment_id}")
async def api_admin_review_comment_delete(comment_id: int, admin: dict = Depends(get_current_admin)):
    ok = review_comment_delete(admin["id"], int(comment_id), as_admin=True)
    if ok:
        return {"success": True}
    raise HTTPException(status_code=404, detail="未找到")


@router.put("/api/admin/users/{user_id}/review-mute")
async def api_admin_user_review_mute(
    user_id: int, body: AdminReviewMuteRequest, admin: dict = Depends(get_current_admin)
):
    until = None
    reason = (body.reason or "").strip()
    if body.until:
        until = body.until
    elif body.duration_hours is not None:
        try:
            hours = int(body.duration_hours)
            if hours <= 0:
                until = None
            else:
                until = (datetime.datetime.now() + datetime.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            until = None
    ok = admin_user_set_review_mute(int(user_id), until, reason)
    return {"success": bool(ok), "muted_until": until, "reason": reason}


@router.delete("/api/admin/users/{user_id}/review-mute")
async def api_admin_user_review_unmute(user_id: int, admin: dict = Depends(get_current_admin)):
    ok = admin_user_clear_review_mute(int(user_id))
    return {"success": bool(ok)}

