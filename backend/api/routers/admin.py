"""
backend/api/routers/admin.py

管理员接口（对应前端“管理后台”页面）。

- 用户管理：/api/admin/users*
- 收藏管理：/api/admin/favorites*
- 推荐日志：/api/admin/recommend-logs
- 浏览历史：/api/admin/browse-history*
- 系统概览：/api/admin/model-stats, /api/admin/overview
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.deps import get_current_admin
from backend.db.database import (
    fav_delete_admin,
    fav_list_all,
    fav_list_by_user_admin,
    history_delete_admin,
    history_list_admin,
    overview_counts,
    rec_log_list,
    rec_log_delete,
    recommend_log_latency_stats,
    user_create,
    user_delete,
    user_get,
    user_list,
    user_update_password,
    user_update_role,
)
from backend.schemas.admin import (
    AdminCreateUserRequest,
    AdminSetPasswordRequest,
    AdminSetRoleRequest,
)
from backend.services.poster_file_cache import poster_file_cache_enabled
from backend.services.poster_file_cache import poster_cache_root
from backend.recommender import _cache
from backend.services.tmdb_client import tmdb_configured
from backend.services.tmdb_home_cache import min_refresh_seconds, read_cache as tmdb_home_read_cache
from backend.eval import RecommendEvalConfig, evaluate_recommend_system

router = APIRouter(tags=["admin"])


def _kg_eval_display_json_path() -> Path:
    """与 MovieHub 一同部署的模型评估指标 JSON 路径。"""
    return Path(__file__).resolve().parents[2] / "data" / "eval" / "kg_eval_display.json"


def _admin_system_snapshot() -> dict:
    """系统概览：片库 CSV 条数、RAG 向量条数、TMDB 首页缓存刷新时间等。"""
    from datetime import datetime

    from backend.recommender.browse import load_douban_data, load_tmdb_movies_data

    douban_n = 0
    tmdb_csv_n = 0
    try:
        load_douban_data()
        df_d = _cache.get("douban_movies")
        if df_d is not None and hasattr(df_d, "__len__"):
            douban_n = int(len(df_d))
    except Exception:
        pass
    try:
        load_tmdb_movies_data()
        df_t = _cache.get("tmdb_movies")
        if df_t is not None and hasattr(df_t, "__len__"):
            tmdb_csv_n = int(len(df_t))
    except Exception:
        pass

    rag_n = 0
    try:
        col = _cache.get("chroma_collection")
        if col is not None:
            rag_n = int(col.count())
    except Exception:
        pass

    uat = None
    uat_disp = ""
    try:
        disk = tmdb_home_read_cache() or {}
        uat = disk.get("updated_at")
        if uat is None:
            uat = _cache.get("tmdb_home_updated_at")
        if uat is not None:
            uat = int(uat)
            uat_disp = datetime.fromtimestamp(uat).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    try:
        sec = int(min_refresh_seconds())
    except Exception:
        sec = 43200
    hours = round(sec / 3600.0, 2)
    return {
        "douban_movie_count": douban_n,
        "tmdb_csv_movie_count": tmdb_csv_n,
        "rag_document_count": rag_n,
        "tmdb_home_last_refresh_ts": uat,
        "tmdb_home_last_refresh_display": uat_disp or "",
        "tmdb_home_min_refresh_sec": sec,
        "tmdb_home_min_refresh_hours": hours,
        "tmdb_home_note": "最小更新间隔约 12 小时。",
    }


def _admin_dt_display(v) -> str:
    """管理后台时间展示：避免 ISO 中的 ``T``，统一为 ``YYYY-MM-DD HH:MM:SS``。"""
    if v is None:
        return ""
    if hasattr(v, "strftime"):
        try:
            return v.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    s = str(v).strip().replace("T", " ")
    if not s:
        return ""
    if s.endswith("Z"):
        s = s[:-1].strip()
    dot = s.find(".")
    if dot == 19 or (0 < dot < 19 and s[4:5] == "-" and s[7:8] == "-"):
        s = s[:dot]
    plus = s.find("+")
    if plus > 0 and s[4:5] == "-" and s[7:8] == "-":
        s = s[:plus].strip()
    return s[:19] if len(s) >= 19 else s


@router.get("/api/admin/users")
async def api_get_users(admin: dict = Depends(get_current_admin)):
    rows = user_list()
    for u in rows or []:
        if isinstance(u, dict):
            u["created_at"] = _admin_dt_display(u.get("created_at"))
            u["review_muted_until"] = _admin_dt_display(u.get("review_muted_until"))
    return {"success": True, "users": rows}


@router.post("/api/admin/users")
async def api_create_user(body: AdminCreateUserRequest, admin: dict = Depends(get_current_admin)):
    ok, msg = user_create((body.username or "").strip(), body.password or "", body.role or "user")
    if ok:
        return {"success": True, "message": msg}
    raise HTTPException(status_code=400, detail=msg or "创建失败")


@router.put("/api/admin/users/{user_id}/password")
async def api_update_user_password(
    user_id: int, body: AdminSetPasswordRequest, admin: dict = Depends(get_current_admin)
):
    if not body.new_password:
        raise HTTPException(status_code=400, detail="密码不能为空")
    user_update_password(int(user_id), body.new_password)
    return {"success": True}


@router.put("/api/admin/users/{user_id}/role")
async def api_update_user_role(user_id: int, body: AdminSetRoleRequest, admin: dict = Depends(get_current_admin)):
    user_update_role(int(user_id), body.new_role)
    return {"success": True}


@router.delete("/api/admin/users/{user_id}")
async def api_delete_user(user_id: int, admin: dict = Depends(get_current_admin)):
    target = user_get(int(user_id))
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if (target.get("role") or "") == "admin":
        raise HTTPException(status_code=400, detail="不能删除管理员账号")
    if int(user_id) == int(admin.get("id") or 0):
        raise HTTPException(status_code=400, detail="不能删除当前登录的管理员")
    ok = user_delete(int(user_id))
    if ok:
        return {"success": True}
    raise HTTPException(status_code=400, detail="删除失败")


@router.get("/api/admin/favorites")
async def api_get_all_favorites(
    user_id: Optional[int] = Query(None),
    username: Optional[str] = Query(None),
    admin: dict = Depends(get_current_admin),
):
    if user_id is not None and int(user_id) > 0:
        rows = fav_list_by_user_admin(int(user_id))
    else:
        u = (username or "").strip()
        rows = fav_list_all(username=u if u else None)
    for r in rows or []:
        if isinstance(r, dict):
            r["added_at"] = _admin_dt_display(r.get("added_at"))
    return {"success": True, "favorites": rows}


@router.delete("/api/admin/favorites/{fav_id}")
async def api_delete_favorite_admin(fav_id: int, admin: dict = Depends(get_current_admin)):
    fav_delete_admin(int(fav_id))
    return {"success": True}


@router.get("/api/admin/recommend-logs")
async def api_get_recommend_logs(
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(get_current_admin),
):
    rows = rec_log_list(int(limit))
    # 兼容旧前端：把 json 字段解析为 list
    for r in rows or []:
        try:
            r["kg_movies"] = json.loads(r.get("kg_movies") or "[]")
        except Exception:
            r["kg_movies"] = []
        try:
            r["rag_movies"] = json.loads(r.get("rag_movies") or "[]")
        except Exception:
            r["rag_movies"] = []
        try:
            r["final_movies"] = json.loads(r.get("final_movies") or "[]")
        except Exception:
            r["final_movies"] = []
        raw_inf = r.get("inference_meta")
        if raw_inf is None or (isinstance(raw_inf, str) and not str(raw_inf).strip()):
            r["inference_meta"] = None
        else:
            try:
                r["inference_meta"] = (
                    json.loads(raw_inf) if isinstance(raw_inf, str) else raw_inf
                )
            except Exception:
                r["inference_meta"] = None
        r["created_at"] = _admin_dt_display(r.get("created_at"))
    return {"success": True, "logs": rows}


@router.get("/api/admin/recommend-eval")
async def api_admin_recommend_eval(
    k: int = Query(10, ge=1, le=50),
    lookahead_days: int = Query(14, ge=1, le=90),
    max_logs: int = Query(2000, ge=50, le=10000),
    admin: dict = Depends(get_current_admin),
):
    """
    离线推荐评估（基于 recommend_logs → 之后的收藏/看过/点赞/影评命中）。
    说明：该指标反映“推荐后转化命中”，需要系统里有足够的真实交互数据才有意义。
    """
    cfg = RecommendEvalConfig(k=int(k), lookahead_days=int(lookahead_days), max_logs=int(max_logs))
    return {"success": True, "result": evaluate_recommend_system(cfg)}


@router.delete("/api/admin/recommend-logs/{log_id}")
async def api_delete_recommend_log(log_id: int, admin: dict = Depends(get_current_admin)):
    ok = rec_log_delete(int(log_id))
    if ok:
        return {"success": True}
    raise HTTPException(status_code=404, detail="日志不存在")


@router.get("/api/admin/browse-history")
async def api_admin_browse_history(
    limit: int = Query(200, ge=1, le=500),
    user_id: Optional[int] = Query(None),
    admin: dict = Depends(get_current_admin),
):
    rows = history_list_admin(int(limit), filter_user_id=int(user_id) if user_id is not None else None)
    for r in rows or []:
        if isinstance(r, dict):
            r["viewed_at"] = _admin_dt_display(r.get("viewed_at"))
    return {"success": True, "history": rows}


@router.delete("/api/admin/browse-history/{record_id}")
async def api_admin_delete_browse_history(record_id: int, admin: dict = Depends(get_current_admin)):
    ok = history_delete_admin(int(record_id))
    if ok:
        return {"success": True}
    raise HTTPException(status_code=404, detail="记录不存在")


@router.get("/api/admin/kg-eval-display")
async def api_admin_kg_eval_display(admin: dict = Depends(get_current_admin)):
    """
    读取 backend/data/eval/kg_eval_display.json，在管理后台展示模型评估指标。
    不加载 PyTorch；更新数据时编辑 JSON 即可。
    """
    p = _kg_eval_display_json_path()
    if not p.is_file():
        return {
            "success": True,
            "configured": False,
            "message": "未找到 kg_eval_display.json。请在 backend/data/eval/ 目录创建该文件。",
            "payload": None,
        }
    try:
        text = p.read_text(encoding="utf-8")
        payload: dict[str, Any] = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("根节点须为 JSON 对象")
        return {"success": True, "configured": True, "payload": payload, "file": str(p)}
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"kg_eval_display.json 格式错误：{e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取 kg_eval_display.json 失败：{e}") from e


@router.get("/api/admin/model-stats")
async def api_get_model_stats(admin: dict = Depends(get_current_admin)):
    row = recommend_log_latency_stats() or {}
    logs = rec_log_list(30)
    recent_logs = []
    for r in logs or []:
        recent_logs.append(
            {
                "created_at": _admin_dt_display(r.get("created_at")),
                "username": r.get("username", ""),
                "call_type": "推荐请求",
                "elapsed_ms": int(r.get("elapsed_ms") or 0),
                "input_summary": (r.get("user_input") or "")[:80],
            }
        )

    return {
        "success": True,
        "stats": [
            {"call_type": "推荐记录总数", "count": int(row.get("total") or 0), "avg_ms": float(row.get("avg_ms") or 0.0)},
            {"call_type": "产生推荐记录的用户数", "count": int(row.get("users") or 0), "avg_ms": 0.0},
        ],
        "recent_logs": recent_logs,
    }


@router.get("/api/admin/overview")
async def api_admin_overview(admin: dict = Depends(get_current_admin)):
    counts = overview_counts()
    return {
        "success": True,
        "counts": counts,
        "runtime": {
            "tmdb_configured": bool(tmdb_configured()),
            "poster_cache_enabled": bool(poster_file_cache_enabled()),
            "poster_cache_root": poster_cache_root(),
            "kg_loaded": bool(_cache.get("entity_relations") or _cache.get("entity2id")),
            "rag_loaded": bool(_cache.get("chroma_collection")),
        },
        "system": _admin_system_snapshot(),
    }

