"""
backend/api/deps.py

FastAPI 依赖项（Depends）工具集合。

- 认证：解析 `Authorization: Bearer user_<id>`，并从数据库加载用户
- 授权：管理员校验
- 可选认证：允许匿名访问（用于非必须登录的接口）
- 风控：影评禁言保护（禁言时禁止发布/评论/回复）
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request

from backend.db.database import user_get, user_review_mute_info


def get_current_user(request: Request):
    """从请求头 Authorization 解析 token 并获取用户"""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        scheme, token = auth_header.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="无效的认证格式")
        if not token.startswith("user_"):
            raise HTTPException(status_code=401, detail="无效的token")
        user_id = int(token[5:])
    except (ValueError, IndexError):
        raise HTTPException(status_code=401, detail="无效的token")

    user = user_get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


def get_current_admin(request: Request):
    """获取当前管理员用户（权限验证）"""
    user = get_current_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def try_get_current_user(request: Request) -> Optional[dict]:
    """可选认证：用于非必须登录的接口。"""
    try:
        return get_current_user(request)
    except Exception:
        return None


def ensure_not_muted(user_id: int):
    """影评禁言保护：禁言时禁止发布/评论/回复。"""
    info = user_review_mute_info(int(user_id)) or {}
    until = (info.get("review_muted_until") or "").__str__().strip()
    reason = (info.get("review_mute_reason") or "").__str__().strip()
    if until:
        msg = f"你已被禁言，至 {until}"
        if reason:
            msg += f"。原因：{reason}"
        raise HTTPException(status_code=403, detail=msg)
    # 兼容：如果数据库里只写了原因但未写截止时间，也应禁止发言并给出提示
    if reason:
        raise HTTPException(status_code=403, detail=f"你已被禁言。原因：{reason}")

