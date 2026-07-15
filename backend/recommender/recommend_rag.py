"""
RAG 片库一路（与 common 缓存、建库脚本共用 Chroma 路径与集合名）。

- **图谱种子**：``rag_retrieve_for_kg_seeds`` — 向量 + 豆瓣补位，对齐 DB15K 种子（不调主 LLM）。
- **标准 RAG**：``rag_llm_recommend`` — 证据 → 主链路 LLM 选片；失败时向量直出 / ``douban_fallback``。
- **一次向量查询**：``rag_fetch_shared_vector_rows`` + ``rag_combined_chroma_n_results``，同一批结果传给种子与 RAG·LLM，避免重复 ``query``。

嵌入仍走 DashScope ``text-embedding-v3``，与 ``build_rag_database.py`` 一致。
证据块截断长度：``RAG_LLM_EVIDENCE_SNIPPET_CHARS``（默认 800）。
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, List, Optional, Tuple

import pandas as pd

from backend.recommender.common import (
    ALLOWED_GENRES,
    CHROMA_DIR,
    COLLECTION_NAME,
    DEFAULT_LLM_MODEL,
    DASHSCOPE_API_KEY,
    RAG_EMBEDDING_MODEL,
    _cache,
    embedding_client,
    llm_client,
)


def chroma_first_embedding_list(sample: dict[str, Any]) -> Optional[list[float]]:
    """
    将 ``collection.get(..., include=['embeddings'])`` 的返回规范为 ``list[float]``。
    Chroma 可能返回 list、或 numpy ndarray；不可用 ``not embs`` 判断 ndarray（会触发歧义报错）。
    """
    embs = sample.get("embeddings") if isinstance(sample, dict) else None
    if embs is None:
        return None
    try:
        import numpy as np

        if isinstance(embs, np.ndarray):
            if embs.size == 0:
                return None
            if embs.ndim == 1:
                return [float(x) for x in embs]
            return [float(x) for x in embs[0]]
    except Exception:
        pass
    if isinstance(embs, (list, tuple)) and len(embs) > 0:
        first = embs[0]
        if first is None:
            return None
        try:
            import numpy as np

            if isinstance(first, np.ndarray):
                flat = first.reshape(-1)
                return [float(x) for x in flat]
        except Exception:
            pass
        if isinstance(first, (list, tuple)):
            return [float(x) for x in first]
    return None


def load_rag_db():
    """
    加载 Chroma 向量库（须先运行 backend/data/RAG_data/build_rag_database.py 建库）。
    与建库脚本共用 ``common.CHROMA_DIR``、``common.COLLECTION_NAME``、``metadata hnsw:space=cosine``。
    """
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
    os.environ.setdefault("CHROMA_TELEMETRY", "false")

    try:
        import chromadb
    except ImportError:
        print("⚠️  [RAG] 未安装 chromadb，跳过向量库加载（pip install chromadb）")
        _cache["chroma_collection"] = None
        return True

    rag_path = os.path.abspath(os.path.normpath(CHROMA_DIR))

    try:
        start = time.time()
        print("📦 [RAG] 正在加载向量数据库...")

        if not os.path.exists(rag_path):
            print(f"⚠️  [RAG] 目录不存在，跳过加载: {rag_path}")
            _cache["chroma_collection"] = None
            return True

        try:
            try:
                from chromadb.config import Settings
            except ImportError:
                try:
                    from chromadb import Settings  # type: ignore
                except ImportError:
                    Settings = None  # type: ignore
            _settings = Settings(anonymized_telemetry=False) if Settings is not None else None
            chroma_client = (
                chromadb.PersistentClient(path=rag_path, settings=_settings)
                if _settings is not None
                else chromadb.PersistentClient(path=rag_path)
            )
            try:
                collection = chroma_client.get_collection(COLLECTION_NAME)
            except Exception as e_get:
                print(
                    f"❌ [RAG] 未找到集合「{COLLECTION_NAME}」或无法打开: {e_get}\n"
                    f"   请在目录 {rag_path} 下先执行 build_rag_database.py 全量建库。"
                )
                _cache["chroma_collection"] = None
                return True

            try:
                movie_count = collection.count()
                probe = collection.get(limit=1, include=["embeddings"])
                vec = chroma_first_embedding_list(probe)
                if not vec:
                    raise RuntimeError("无法读取任意一条 embedding，向量检索不可用")
                k = min(120, max(2, min(movie_count, 24))) if movie_count else 2
                collection.query(
                    query_embeddings=[vec],
                    n_results=max(1, min(k, movie_count)),
                    include=["metadatas", "distances"],
                )
            except Exception as e_probe:
                print(
                    f"❌ [RAG] 向量索引校验失败（HNSW 可能损坏或未写完）: {e_probe}\n"
                    f"   请停后端后删除目录 {rag_path} 再运行 build_rag_database.py 全量建库。"
                )
                _cache["chroma_collection"] = None
                return True

            _cache["chroma_collection"] = collection
        except Exception as e:
            print(f"❌ [RAG] 索引加载失败（可能是版本不兼容或损坏）: {e}")
            print("   跳过 RAG 向量检索，图谱与其它片库仍可工作")
            _cache["chroma_collection"] = None
            return True

        try:
            elapsed = time.time() - start
            print(f"✅ [RAG] 向量库已加载：{movie_count} 部电影，耗时 {elapsed:.2f}s")
        except Exception as e:
            _cache["chroma_collection"] = None
            print(f"❌ [RAG] 向量库已损坏或与本机 Chroma 版本不兼容：{e}")
            return True

        return True

    except Exception as e:
        print(f"❌ [RAG] 加载失败: {str(e)}")
        _cache["chroma_collection"] = None
        return True


def get_query_embedding(query: str):
    """使用 DashScope 兼容接口将查询文本转换为 embedding（与建库一致）。"""
    if not embedding_client or not DASHSCOPE_API_KEY:
        print("⚠️  [RAG] 未配置 DASHSCOPE_API_KEY，无法生成 query embedding")
        return None

    try:
        response = embedding_client.embeddings.create(
            model=RAG_EMBEDDING_MODEL,
            input=query,
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"❌ [RAG] 生成 query embedding 失败: {str(e)[:120]}")
        return None


def _allowed_genre_subset(hints: Optional[list]) -> List[str]:
    if not hints:
        return []
    out: List[str] = []
    for h in hints:
        s = str(h).strip()
        if s in ALLOWED_GENRES and s not in out:
            out.append(s)
    return out


def _rag_meta_genre_boost(meta: dict, hints: List[str]) -> float:
    if not hints or not meta:
        return 0.0
    gtxt = (
        str(meta.get("genres") or "")
        + str(meta.get("genre") or "")
        + str(meta.get("type") or "")
    )
    gtxt = gtxt.replace("、", "/").replace(" ", "").replace(",", "/")
    hit = 0
    for h in hints:
        if h and (h in gtxt):
            hit += 1
    return min(0.45, hit * 0.15)


def _rag_rescore_vector_item(item: dict, hints: List[str]) -> float:
    base = max(0.0, min(1.0, float(item.get("similarity") or 0.0)))
    meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    b = _rag_meta_genre_boost(meta, hints)
    return min(1.0, base * (1.0 + b))


def _recommend_from_douban(
    query: str, topk: int = 6, genre_hints: Optional[list] = None
):
    df = _cache.get("douban_movies")
    if df is None or df.empty:
        return []

    matched_genres: List[str] = []
    for genre in ALLOWED_GENRES:
        if genre in query:
            matched_genres.append(genre)
    for g in _allowed_genre_subset(genre_hints):
        if g not in matched_genres:
            matched_genres.append(g)

    filtered = df

    if matched_genres:
        mask = filtered["type_simplified"].apply(
            lambda x: any(g in x for g in matched_genres)
        )
        filtered = filtered[mask]

    if filtered.empty:
        filtered = df

    rows_scored = []
    for _, row in filtered.head(max(topk * 6, 24)).iterrows():
        types_list = row["type_simplified"] or []
        try:
            sc = float(row["score"]) if pd.notna(row.get("score")) else 0.0
        except Exception:
            sc = 0.0
        overlap = 0
        if matched_genres and isinstance(types_list, list):
            overlap = sum(1 for g in matched_genres if g in types_list)
        combined = sc / 10.0 + overlap * 0.28
        rows_scored.append((combined, row))

    rows_scored.sort(key=lambda x: -x[0])

    results = []
    for _, row in rows_scored[: max(topk * 3, 12)]:
        types_list = row["type_simplified"]
        genres = "/".join(types_list) if types_list else "未知"

        results.append(
            {
                "name": row["title"],
                "source": "douban",
                "similarity": 1.0,
                "metadata": {
                    "title": row["title"],
                    "score": row["score"],
                    "genres": genres,
                    "director": row["director"] if pd.notna(row["director"]) else "未知",
                },
            }
        )

    return results


def _env_int_rag(name: str, default: int, *, min_v: int, max_v: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        v = default
    else:
        try:
            v = int(raw)
        except ValueError:
            v = default
    return max(min_v, min(max_v, v))


def rag_combined_chroma_n_results(max_candidates: int) -> int:
    """
    单次 Chroma query 应请求的条数：覆盖「图谱种子池」与「RAG·LLM 证据条数」二者的较大值。
    """
    try:
        mc = max(8, min(64, int(max_candidates)))
    except (TypeError, ValueError):
        mc = 28
    n_seed = min(120, max(mc * 3, 32))
    n_llm = _env_int_rag("RAG_LLM_EVIDENCE_TOPK", 36, min_v=8, max_v=80)
    return max(n_seed, n_llm)


def rag_fetch_shared_vector_rows(
    query: str,
    *,
    n_results: int,
) -> Tuple[list[dict], dict]:
    """
    对同一 ``query`` 只打一次 embedding、一次 ``collection.query``。
    返回的列表项含 ``_doc``，请先拷贝再传给 ``rag_retrieve_for_kg_seeds``（内部会 ``pop`` 掉 ``_doc``）。
    """
    diag: dict = {
        "chroma_available": bool(_cache.get("chroma_collection")),
        "n_vector": 0,
        "vector_error": None,
        "purpose": "shared_chroma_query",
        "n_results_requested": n_results,
        "single_embedding_query": True,
    }
    rows, _err = _vector_query_raw(query, n_results, diag)
    diag["n_vector"] = len(rows)
    diag["chroma_available"] = bool(_cache.get("chroma_collection"))
    return rows, diag


def _vector_query_raw(
    query: str, n_fetch: int, diag: dict
) -> Tuple[list[dict], Optional[str]]:
    """返回向量命中列表（name/source/similarity/metadata），失败时 vector_error。"""
    collection = _cache.get("chroma_collection")
    if not collection:
        diag["vector_error"] = "Chroma 集合未加载（跳过向量检索）"
        return [], diag.get("vector_error")

    out: list[dict] = []
    for attempt in range(2):
        collection = _cache.get("chroma_collection")
        if not collection:
            diag["vector_error"] = "Chroma 集合未加载（跳过向量检索）"
            return [], diag["vector_error"]
        try:
            qe = get_query_embedding(query)
            if qe is None:
                diag["vector_error"] = "查询向量编码失败（跳过向量检索）"
                return [], diag["vector_error"]
            results = collection.query(
                query_embeddings=[qe],
                n_results=n_fetch,
                include=["documents", "metadatas", "distances"],
            )
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                if not isinstance(meta, dict):
                    meta = {}
                out.append(
                    {
                        "name": meta.get("title", meta.get("movie_name", "未知")),
                        "source": str(meta.get("source", "unknown")),
                        "similarity": max(0.0, min(1.0, 1.0 - float(dist))),
                        "metadata": meta,
                        "_doc": str(doc or "")[:2400],
                    }
                )
            return out, None
        except Exception as e:
            err = str(e)
            low = err.lower()
            if attempt == 0 and (
                "header" in low
                or "cannot open" in low
                or "hnsw" in low
                or "corrupt" in low
            ):
                print(f"⚠️  [RAG] 向量检索异常，重载重试: {str(err)[:120]}")
                _cache["chroma_collection"] = None
                load_rag_db()
                out = []
                continue
            diag["vector_error"] = err
            print(f"❌ [RAG] 向量检索失败: {str(err)[:120]}")
            return [], err
    return out, diag.get("vector_error")


def rag_retrieve_for_kg_seeds(
    query: str,
    *,
    genre_hints: Optional[list] = None,
    max_candidates: int = 28,
    shared_vector_rows: Optional[list[dict]] = None,
    fetch_diag: Optional[dict] = None,
) -> Tuple[list[dict], dict]:
    """
    仅用于 **图谱 MoE 种子**：Chroma 向量 + 豆瓣类型库融合，取一批候选片名（不调主链路 LLM）。

    若已由 ``rag_fetch_shared_vector_rows`` 取好 ``shared_vector_rows``，传入此处可避免重复向量查询；
    函数内部会对行做拷贝后再 ``pop`` 元数据，不影响传给 ``rag_llm_recommend`` 的原始列表。
    """
    hints = _allowed_genre_subset(genre_hints)
    try:
        mc = max(8, min(64, int(max_candidates)))
    except (TypeError, ValueError):
        mc = 28

    base = fetch_diag if isinstance(fetch_diag, dict) else {}
    diag: dict = {
        "chroma_available": base.get("chroma_available", bool(_cache.get("chroma_collection"))),
        "n_vector": 0,
        "vector_error": base.get("vector_error"),
        "n_douban_raw": 0,
        "purpose": "kg_seeds",
        "shared_chroma_query": bool(shared_vector_rows is not None),
    }

    if shared_vector_rows is not None:
        vector_results = [{**r} for r in shared_vector_rows]
        diag["n_vector"] = len(vector_results)
    else:
        n_fetch = min(120, max(mc * 3, 32))
        vector_results, _ = _vector_query_raw(query, n_fetch, diag)
        diag["chroma_available"] = bool(_cache.get("chroma_collection"))
        diag["n_vector"] = len(vector_results)

    for mv in vector_results:
        mv.pop("_doc", None)
        mv["_rag_rank_score"] = _rag_rescore_vector_item(mv, hints)

    vector_results.sort(
        key=lambda m: float(m.get("_rag_rank_score") or 0.0), reverse=True
    )
    diag["n_vector"] = len(vector_results)

    douban_results = _recommend_from_douban(query, mc, genre_hints=genre_hints)
    diag["n_douban_raw"] = len(douban_results)

    pool: List[Tuple[float, dict]] = []
    for m in vector_results:
        sc = float(m.get("_rag_rank_score") or 0.0)
        pool.append((sc, m))
    for m in douban_results:
        meta = m.get("metadata") if isinstance(m.get("metadata"), dict) else {}
        base = 0.78
        b = _rag_meta_genre_boost(meta, hints)
        sc = min(1.0, base * (1.0 + b))
        pool.append((sc, m))

    pool.sort(key=lambda x: -x[0])
    seen = set()
    final_results = []
    for sc, movie in pool:
        nm = (movie.get("name") or "").strip()
        if not nm or nm in seen:
            continue
        seen.add(nm)
        movie.pop("_rag_rank_score", None)
        final_results.append(movie)
        if len(final_results) >= mc:
            break

    return final_results, diag


def _parse_llm_json_obj(raw: str) -> dict:
    txt = (raw or "").strip()
    if "```" in txt:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", txt, re.I)
        if m:
            txt = m.group(1).strip()
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        a, b = txt.find("{"), txt.rfind("}")
        if a >= 0 and b > a:
            return json.loads(txt[a : b + 1])
        raise


def _env_int(name: str, default: int, *, min_v: int, max_v: int) -> int:
    return _env_int_rag(name, default, min_v=min_v, max_v=max_v)


def rag_llm_recommend(
    query: str,
    topk: int = 6,
    *,
    genre_hints: Optional[list] = None,
    exclude_titles: Optional[set[str]] = None,
    fast_llm: bool = False,
    shared_vector_rows: Optional[list[dict]] = None,
    fetch_diag: Optional[dict] = None,
) -> Tuple[list[dict], dict]:
    """
    **标准 RAG**：Chroma 证据 → 主链路 LLM 按编号选片并写理由。

    成功时 ``source`` 为 ``rag_llm``；回退时向量直出亦为 ``rag_llm``（``rag_fallback_kind=vector_top``），
    豆瓣补位为 ``douban_fallback``。可传入 ``shared_vector_rows`` 避免与种子路径重复 ``query``。
    """
    # --- RAG 结果缓存（query+类型不变时 1 小时内直接返回）---
    from backend.services.redis_cache import get as _rag_get, set as _rag_set
    import hashlib as _hl
    _hints_sig = ",".join(sorted(_allowed_genre_subset(genre_hints)))
    _rag_raw = f"rag:{query}:{_hints_sig}:{topk}:{fast_llm}"
    _rag_key = "rag_rec:" + _hl.md5(_rag_raw.encode()).hexdigest()
    _rag_cached = _rag_get(_rag_key)
    if _rag_cached is not None:
        return _rag_cached.get("movies", []), _rag_cached.get("diag", {})

    hints = _allowed_genre_subset(genre_hints)
    excl = {str(x).strip() for x in (exclude_titles or []) if str(x).strip()}
    n_evidence = _env_int("RAG_LLM_EVIDENCE_TOPK", 36, min_v=8, max_v=80)
    snippet_chars = _env_int_rag("RAG_LLM_EVIDENCE_SNIPPET_CHARS", 800, min_v=400, max_v=4000)
    try:
        tk = max(1, min(24, int(topk)))
    except (TypeError, ValueError):
        tk = 6

    base_fd = fetch_diag if isinstance(fetch_diag, dict) else {}
    diag: dict = {
        "chroma_available": base_fd.get("chroma_available", bool(_cache.get("chroma_collection"))),
        "n_retrieved": 0,
        "n_vector": 0,
        "vector_error": base_fd.get("vector_error"),
        "llm_ok": False,
        "rag_llm_fallback": None,
        "purpose": "rag_llm",
        "shared_chroma_query": bool(shared_vector_rows is not None),
    }

    if shared_vector_rows is not None:
        vector_rows = [{**r} for r in shared_vector_rows]
        if len(vector_rows) > n_evidence:
            vector_rows = vector_rows[:n_evidence]
    else:
        qdiag: dict = {
            "chroma_available": bool(_cache.get("chroma_collection")),
            "vector_error": None,
        }
        vector_rows, _ = _vector_query_raw(query, n_evidence, qdiag)
        diag["vector_error"] = qdiag.get("vector_error")
        diag["chroma_available"] = bool(_cache.get("chroma_collection"))

    diag["n_vector"] = len(vector_rows)

    evidence: list[dict] = []
    for i, row in enumerate(vector_rows):
        doc = str(row.pop("_doc", "") or "")
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        title = str(meta.get("title") or row.get("name") or "").strip() or "未知"
        evidence.append(
            {
                "idx": i,
                "title": title,
                "doc": doc,
                "meta": meta,
                "similarity": float(row.get("similarity") or 0.0),
                "source": str(row.get("source") or meta.get("source") or "unknown"),
            }
        )

    diag["n_retrieved"] = len(evidence)

    def _fallback_vector_top() -> list[dict]:
        out: list[dict] = []
        for row in sorted(evidence, key=lambda x: -x["similarity"])[:tk]:
            meta = dict(row["meta"])
            nm = str(meta.get("title") or row["title"] or "").strip()
            if not nm or nm in excl:
                continue
            out.append(
                {
                    "name": nm,
                    "source": "rag_llm",
                    "similarity": row["similarity"],
                    "metadata": meta,
                    "rag_llm_reason": "（检索直出：未调用生成模型）",
                    "rag_evidence_idx": row["idx"],
                    "rag_llm_fallback": True,
                    "rag_fallback_kind": "vector_top",
                }
            )
            if len(out) >= tk:
                break
        for m in _recommend_from_douban(query, tk, genre_hints=genre_hints):
            nm = (m.get("name") or "").strip()
            if not nm or nm in excl:
                continue
            if any((x.get("name") or "").strip() == nm for x in out):
                continue
            meta = m.get("metadata") if isinstance(m.get("metadata"), dict) else {}
            out.append(
                {
                    "name": nm,
                    "source": "douban_fallback",
                    "similarity": 0.72,
                    "metadata": meta,
                    "rag_llm_reason": "（豆瓣补位：向量未命中或未加载）",
                    "rag_evidence_idx": None,
                    "rag_llm_fallback": True,
                    "rag_fallback_kind": "douban",
                }
            )
            if len(out) >= tk:
                break
        return out[:tk]

    if fast_llm or not llm_client:
        diag["rag_llm_fallback"] = "fast_llm_or_no_llm_client"
        return _fallback_vector_top(), diag

    if not evidence:
        diag["rag_llm_fallback"] = "no_evidence"
        return _fallback_vector_top(), diag

    genre_line = "、".join(hints[:8]) if hints else "（无额外类型约束）"
    excl_line = "、".join(sorted(excl)[:40]) if excl else "（无）"
    block_lines = []
    for e in evidence:
        snippet = (e["doc"] or "").replace("\r", " ").replace("\n", " ")[:snippet_chars]
        block_lines.append(f"[{e['idx']}] 片名：{e['title']} | {snippet}")
    evidence_block = "\n".join(block_lines)

    user_msg = (
        f"【用户查询与偏好】\n{query[:2000]}\n\n"
        f"【偏好类型提示】{genre_line}\n"
        f"【不要推荐的片名】{excl_line}\n\n"
        f"【片库证据（仅允许从下编号中选片）】\n{evidence_block}\n\n"
        f"请输出 JSON 对象，格式严格为："
        f'{{"picks":[{{"idx":<0到{len(evidence)-1}的整数>,"reason":"<一句中文理由>"}},...]}}，'
        f"最多 {tk} 条，按推荐优先级排序；idx 必须对应上表编号，不得编造未出现的片名。"
    )

    model = (os.getenv("RAG_LLM_MODEL") or DEFAULT_LLM_MODEL or "").strip()
    if not model:
        diag["rag_llm_fallback"] = "no_model"
        return _fallback_vector_top(), diag

    t0 = time.time()
    try:
        base_kwargs: dict = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是电影推荐助手。你只根据用户消息中的【片库证据】编号选择影片，"
                        "理由须与证据中的类型/简介/导演等信息一致。禁止推荐证据块中未出现的片名。"
                        "只输出合法 JSON，不要其它文字。"
                    ),
                },
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.25,
        }
        try:
            resp = llm_client.chat.completions.create(
                **base_kwargs, response_format={"type": "json_object"}
            )
        except Exception:
            resp = llm_client.chat.completions.create(**base_kwargs)
        raw = (resp.choices[0].message.content or "").strip()
        obj = _parse_llm_json_obj(raw)
        picks = obj.get("picks") if isinstance(obj, dict) else None
        if not isinstance(picks, list):
            picks = []
    except Exception as e:
        diag["llm_error"] = str(e)[:400]
        diag["rag_llm_fallback"] = f"llm_error:{type(e).__name__}"
        diag["llm_ms"] = int((time.time() - t0) * 1000)
        return _fallback_vector_top(), diag

    diag["llm_ms"] = int((time.time() - t0) * 1000)

    by_idx = {e["idx"]: e for e in evidence}
    final: list[dict] = []
    seen_names: set[str] = set()

    for p in picks:
        if not isinstance(p, dict):
            continue
        try:
            idx = int(p.get("idx"))
        except (TypeError, ValueError):
            continue
        if idx not in by_idx:
            continue
        reason = str(p.get("reason") or "").strip() or "与检索证据相符。"
        row = by_idx[idx]
        meta = dict(row["meta"])
        nm = str(meta.get("title") or row["title"] or "").strip()
        if not nm or nm in excl or nm in seen_names:
            continue
        seen_names.add(nm)
        b = _rag_meta_genre_boost(meta, hints)
        sim = min(1.0, float(row["similarity"]) * (1.0 + 0.08 * min(3, b * 10)))
        final.append(
            {
                "name": nm,
                "source": "rag_llm",
                "similarity": sim,
                "metadata": meta,
                "rag_llm_reason": reason[:400],
                "rag_evidence_idx": idx,
                "rag_llm_fallback": False,
            }
        )
        if len(final) >= tk:
            break

    if not final:
        diag["rag_llm_fallback"] = "empty_picks"
        fb = _fallback_vector_top()
        try:
            _rag_set(_rag_key, {"movies": fb, "diag": diag}, ttl=3600)
        except Exception:
            pass
        return fb, diag

    diag["llm_ok"] = True
    try:
        _rag_set(_rag_key, {"movies": final, "diag": diag}, ttl=3600)
    except Exception:
        pass
    return final, diag


def rag_recommend(
    query: str,
    topk: int = 6,
    *,
    genre_hints: Optional[list] = None,
    exclude_titles: Optional[set[str]] = None,
    fast_llm: bool = False,
    shared_vector_rows: Optional[list[dict]] = None,
    fetch_diag: Optional[dict] = None,
):
    """兼容旧名：等价于 ``rag_llm_recommend``。"""
    return rag_llm_recommend(
        query,
        topk,
        genre_hints=genre_hints,
        exclude_titles=exclude_titles,
        fast_llm=fast_llm,
        shared_vector_rows=shared_vector_rows,
        fetch_diag=fetch_diag,
    )
