# -*- coding: utf-8 -*-
"""为 DB15K 电影实体构建 ChromaDB 向量库，供 LLM 偏好分解时检索相关电影。

运行方式：cd D:\\AI\\MovieHub && python backend/scripts/build_kg_movie_rag.py
需要：DASHSCOPE_API_KEY 环境变量（与主 RAG 共用同一个 embedding 模型）。
"""
from __future__ import annotations

import json
import os
import sys
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from dotenv import load_dotenv

load_dotenv()
_root_env = os.path.join(_REPO_ROOT, ".env")
if os.path.isfile(_root_env):
    load_dotenv(_root_env, override=True)

COLLECTION_NAME = "db15k_movies"


def build_collection():
    import chromadb
    from openai import OpenAI

    api_key = (os.getenv("DASHSCOPE_API_KEY") or "").strip()
    if not api_key:
        print("错误：未设置 DASHSCOPE_API_KEY 环境变量")
        sys.exit(1)

    embed_model = (os.getenv("RAG_EMBEDDING_MODEL") or "text-embedding-v3").strip()
    chroma_dir = os.path.join(_REPO_ROOT, "backend", "data", "RAG_data", "rag_db")

    # 加载词典
    lex_path = os.path.join(_REPO_ROOT, "backend", "data", "kg", "db15k_movie_lexicon.json")
    with open(lex_path, encoding="utf-8") as f:
        lex_data = json.load(f)

    alias_map = lex_data["alias_to_entity"]

    # 构建 entity -> 中文别名列表
    entity_to_zh: dict[str, list[str]] = {}
    entity_to_en_aliases: dict[str, list[str]] = {}
    for alias, entity in alias_map.items():
        if any("一" <= c <= "鿿" for c in alias):
            entity_to_zh.setdefault(entity, []).append(alias)
        else:
            entity_to_en_aliases.setdefault(entity, []).append(alias)

    all_entities = sorted(set(alias_map.values()))
    print(f"电影实体总数: {len(all_entities)}")

    # 构建 document：实体名 + 中文别名 + 英文别名（去重、限制长度）
    ids = []
    documents = []
    for entity in all_entities:
        zh_aliases = entity_to_zh.get(entity, [])
        en_aliases = entity_to_en_aliases.get(entity, [])

        # 文档 = 实体名 + 最多5个中文别名 + 最多3个英文别名
        parts = [entity.replace("_", " ")]
        if zh_aliases:
            parts.extend(zh_aliases[:5])
        if en_aliases:
            # 只保留最短的几个英文别名
            short_en = sorted(set(en_aliases), key=len)[:3]
            parts.extend(short_en)

        doc = " | ".join(parts)
        ids.append(entity)
        documents.append(doc)

    # 初始化 embedding client
    embed_client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    # 批量生成 embedding
    print(f"正在生成 {len(documents)} 条 embedding...")
    embeddings = []
    batch_size = 64
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        resp = embed_client.embeddings.create(model=embed_model, input=batch)
        for item in resp.data:
            embeddings.append(item.embedding)
        done = min(i + batch_size, len(documents))
        print(f"  {done}/{len(documents)}")

    # 写入 ChromaDB
    client = chromadb.PersistentClient(path=chroma_dir)

    # 删除旧集合（如有）
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"已删除旧集合 {COLLECTION_NAME}")
    except Exception:
        pass

    collection = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    # 分批写入
    add_batch = 500
    for i in range(0, len(ids), add_batch):
        collection.add(
            ids=ids[i : i + add_batch],
            documents=documents[i : i + add_batch],
            embeddings=embeddings[i : i + add_batch],
        )

    print(f"\n完成！集合 {COLLECTION_NAME} 共 {collection.count()} 条记录")
    print(f"存储路径: {chroma_dir}")


if __name__ == "__main__":
    build_collection()
