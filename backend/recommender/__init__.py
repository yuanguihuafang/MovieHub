# -*- coding: utf-8 -*-
"""
推荐引擎包：按前端界面对应的后端能力分模块（browse / home / recommend），
共用 ``common`` 中的路径、缓存与映射。对外 API 保持不变。
"""
from backend.recommender.common import PROJECT_ROOT, RELATION_ZH, _cache

print(f"📁 MovieHub 项目根目录: {PROJECT_ROOT}\r")

from backend.recommender.browse import get_movie_list, load_douban_data
from backend.recommender.home import get_home_feed
from backend.recommender.recommend_rag import (
    get_query_embedding,
    load_rag_db,
    rag_combined_chroma_n_results,
    rag_fetch_shared_vector_rows,
    rag_llm_recommend,
    rag_recommend,
    rag_retrieve_for_kg_seeds,
)
from backend.recommender.recommend import (
    generate_recommend_card_blurbs,
    generate_recommend_summary,
    get_movie_display_name,
    get_movie_genres,
    llm_explain_recommendation,
    load_kg_model,
    moe_link_prediction_recommend,
    recommend_for_user,
)

__all__ = [
    "PROJECT_ROOT",
    "_cache",
    "RELATION_ZH",
    "load_douban_data",
    "get_movie_list",
    "get_home_feed",
    "load_kg_model",
    "load_rag_db",
    "recommend_for_user",
    "moe_link_prediction_recommend",
    "rag_recommend",
    "rag_llm_recommend",
    "rag_retrieve_for_kg_seeds",
    "rag_fetch_shared_vector_rows",
    "rag_combined_chroma_n_results",
    "get_query_embedding",
    "get_movie_display_name",
    "get_movie_genres",
    "llm_explain_recommendation",
    "generate_recommend_card_blurbs",
    "generate_recommend_summary",
]
