"""
backend/schemas/recommend.py

推荐接口相关的 Pydantic 数据模型。
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class RecommendRequest(BaseModel):
    user_id: int
    user_input: str
    topk_kg: int = 6  # KG 路定榜条数（最终展示名额）
    topk_rag: int = 10  # 片库/RAG 路定榜条数上限（最终展示名额）
    selected_favorites: Optional[list[str]] = None
    with_llm_explain: bool = False
    use_recent: bool = False
    fast_llm: bool = False
    # 本轮推荐需避开的展示片名（如上一手定榜结果），用于换一批
    exclude_titles: Optional[list[str]] = None


class RecommendCardBlurbsJobRequest(BaseModel):
    user_input: str = ""
    movies: list[dict]


class RecommendSummaryJobRequest(BaseModel):
    user_input: str = ""
    movies: list[dict]


class RecommendExplainJobRequest(BaseModel):
    user_input: str = ""
    favorite_movies: list[str] = []
    watched_titles: list[str] = []
    seed_movies: list = []
    kg_movies: list = []
    rag_movies: list = []
    genre_hints: list[str] = []
    # 定榜后真正展示的影片（解读应主要围绕这些，勿把 KG 长召回当最终清单逐一点评）
    final_titles: list[str] = []

