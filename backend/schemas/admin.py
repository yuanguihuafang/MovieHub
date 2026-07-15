"""
backend/schemas/admin.py

管理后台相关的 Pydantic 数据模型。
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class AdminCreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "user"


class AdminSetPasswordRequest(BaseModel):
    new_password: str


class AdminSetRoleRequest(BaseModel):
    new_role: str


class AdminUpdateUserRequest(BaseModel):
    user_id: int
    new_password: Optional[str] = None
    new_role: Optional[str] = None

