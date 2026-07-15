"""
backend/api/routers/auth.py

认证相关接口（登录/注册页面）。

- POST /api/auth/register
- POST /api/auth/login
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.db.database import user_create, user_login
from backend.schemas.auth import LoginRequest, RegisterRequest

router = APIRouter(tags=["auth"])


@router.post("/api/auth/register")
async def api_register(body: RegisterRequest):
    username = (body.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if len(username) > 64:
        raise HTTPException(status_code=400, detail="用户名最多 64 字")
    if len(body.password or "") < 6:
        raise HTTPException(status_code=400, detail="密码至少6位")
    if body.password != body.confirm_password:
        raise HTTPException(status_code=400, detail="两次密码不一致")
    ok, msg = user_create(username, body.password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg or "注册失败")
    # 注册成功后直接返回用户信息（用于前端“注册即登录”）
    user, _ = user_login(username, body.password)
    return {"success": True, "message": "注册成功", "user": user}


@router.post("/api/auth/login")
async def api_login(body: LoginRequest):
    username = (body.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    user, msg = user_login(username, body.password)
    if not user:
        raise HTTPException(status_code=400, detail=msg or "登录失败")
    return {"success": True, "message": "登录成功", "user": user}

