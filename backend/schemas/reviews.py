"""
backend/schemas/reviews.py

影评社区相关的 Pydantic 数据模型：
- 发布/更新影评
- 评论/回复
- 点赞
- 管理员禁言参数
"""

from __future__ import annotations

from typing import Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class ReviewUpsertRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    movie_name: str = Field(validation_alias=AliasChoices("movie_name", "movieName"))
    movie_source: Optional[str] = Field(
        default="",
        validation_alias=AliasChoices("movie_source", "movieSource"),
    )
    rating: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("rating", "rate", "score"),
        description="1-10，可选，可为小数",
    )
    content: str = Field(default="", validation_alias=AliasChoices("content", "text"))

    @field_validator("rating", mode="before")
    @classmethod
    def _coerce_rating(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return None
            try:
                return float(s)
            except ValueError:
                return v
        return v


class ReviewCommentAddRequest(BaseModel):
    content: str
    parent_id: Optional[int] = None


class ReviewLikeRequest(BaseModel):
    target_type: str  # review | comment
    target_id: int


class AdminReviewMuteRequest(BaseModel):
    duration_hours: Optional[int] = None
    until: Optional[str] = None  # ISO string
    reason: Optional[str] = ""

