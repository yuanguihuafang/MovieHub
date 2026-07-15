"""
backend/schemas/auth.py

认证相关的 Pydantic 数据模型（登录/注册）。
"""

from __future__ import annotations

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    confirm_password: str

