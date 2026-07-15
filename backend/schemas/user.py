"""
backend/schemas/user.py

用户侧接口的 Pydantic 数据模型：
- 个人中心/偏好/改密
- 收藏/已看过/反馈
- 片单与消息中心
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    created_at: str


class UserUpdatePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UserFavoriteAddRequest(BaseModel):
    movie_name: str
    genres: Optional[str] = ""
    movie_source: str = "kg"
    tmdb_id: Optional[int] = None


class UserFavoriteRemoveRequest(BaseModel):
    movie_name: str


class UserWatchedAddRequest(BaseModel):
    movie_name: str
    genres: Optional[str] = ""
    movie_source: Optional[str] = "kg"
    tmdb_id: Optional[int] = None


class UserPreferencesRequest(BaseModel):
    preferred_genres: list[str] = Field(default_factory=list)


class UserFeedbackUpsertRequest(BaseModel):
    movie_name: str = Field(..., description="电影名（系统内的 movie_name）")
    movie_source: Optional[str] = Field(default="kg", description="影片来源（douban_csv/tmdb_csv/tmdb_api/kg）")
    tmdb_id: Optional[int] = Field(default=None, description="TMDB ID（仅 tmdb_api 可能有）")
    vote: Optional[str] = Field(default=None, description="like/dislike/None")
    blocked: Optional[bool] = Field(default=None, description="是否屏蔽（不再推荐）")
    note: Optional[str] = Field(default=None, description="短评（<=500）")


class PlaylistCreateRequest(BaseModel):
    name: str
    description: Optional[str] = ""


class PlaylistUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class PlaylistItemAddRequest(BaseModel):
    movie_name: str
    movie_source: Optional[str] = ""
    tmdb_id: Optional[int] = None
    genres: Optional[str] = ""
    poster_url: Optional[str] = ""
    genres_str: Optional[str] = ""
    score_str: Optional[str] = ""
    short_review: Optional[str] = ""


class SaveRecommendationRequest(BaseModel):
    movies: List[Dict[str, Any]] = Field(default_factory=list)


class NotificationMarkReadRequest(BaseModel):
    ids: Optional[List[int]] = None
    mark_all: bool = False

