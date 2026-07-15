# -*- coding: utf-8 -*-
"""
将豆瓣 Top250 + TMDB CSV 去重后写入 Chroma，作为「片库标准 RAG」的检索语料：
每条 document 由 ``build_movie_document`` 生成，运行时 ``rag_llm_recommend`` 按向量拉取若干条作为
【证据编号】供主链路 LLM 选片；``rag_retrieve_for_kg_seeds`` 仅用向量+豆瓣对齐图谱种子，不调该 LLM。

嵌入须与查询侧一致：``backend.recommender.common.RAG_EMBEDDING_MODEL``（默认 text-embedding-v3）+
 ``DASHSCOPE_API_KEY``。

运行：在 ``backend/data/RAG_data`` 下执行 ``python build_rag_database.py``。
依赖：``pip install chromadb pandas openai httpx python-dotenv``。

主要可选环境变量：RAG_EMBED_API_BATCH、RAG_CHROMA_ADD_BATCH、RAG_CHROMA_* 落盘等待、RAG_TMDB_MIN_VOTE_AVERAGE、
RAG_EMBED_CACHE_DIR、CHROMA_PERSIST_DIR（见 common.CHROMA_DIR）。建库与 ``main.py`` 须同 chromadb 版本；
换 chromadb 大版本请删 ``rag_db`` 全量重建；Windows 下 HNSW 未完成落盘时勿并行开后端。

终端 **HNSW/落盘进度**：长等待会按 ``RAG_CHROMA_HNSW_TICK_SEC``（默认 10s）打点；索引与 count 对齐阶段
按 ``RAG_CHROMA_INDEX_LOG_SEC``（默认 15s）输出 count（Chroma 无官方 HNSW 百分比 API，此为近似进度）。
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
import re
import sys
import time
from typing import Any

import httpx
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI


class RagBuildAbort(Exception):
    """嵌入 API 额度/计费类错误，重试无效，应中止建库。"""


def _persistent_client_close(client: Any, *, warn: bool = False) -> None:
    """Chroma 1.x 的 PersistentClient 有 close()；0.5.x 多数无此方法，依赖进程退出刷盘。"""
    close_fn = getattr(client, "close", None)
    if not callable(close_fn):
        return
    try:
        close_fn()
    except Exception as e:
        if warn:
            print(f"  close() 提示：{e}")


_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", "..", ".."))

load_dotenv()
_root_env = os.path.join(_REPO_ROOT, ".env")
if os.path.isfile(_root_env):
    load_dotenv(_root_env, override=True)

if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# 在任意 chromadb 导入之前（与 main.py 一致），减轻 posthog 3.x 与 Chroma 遥测不兼容日志
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("CHROMA_TELEMETRY", "false")

from backend.recommender.common import (
    CHROMA_DIR,
    COLLECTION_NAME,
    RAG_EMBEDDING_MODEL,
)
from backend.recommender.recommend_rag import chroma_first_embedding_list

_dashscope_key = (os.getenv("DASHSCOPE_API_KEY") or "").strip()
_dashscope_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _is_embedding_quota_exhausted(exc: BaseException) -> bool:
    s = str(exc)
    if "FreeTierOnly" in s or "AllocationQuota" in s:
        return True
    low = s.lower()
    return "free tier" in low and "exhausted" in low


def _raise_if_embedding_quota(exc: BaseException) -> None:
    if not _is_embedding_quota_exhausted(exc):
        return
    print(
        "\n【DashScope 嵌入不可用】当前错误表示：免费额度用尽，或账号勾选了「仅限免费额度」且额度已用完。"
        f"\n  当前模型：{RAG_EMBEDDING_MODEL}"
    )
    raise RagBuildAbort("嵌入 API 额度不足，已中止建库（重试无效）。") from exc


# DashScope OpenAI 兼容模式：单次 input 列表长度上限（超出返回 400，与模型版本无关时仍适用）
DASHSCOPE_EMBEDDING_API_MAX_BATCH = 10


def _env_int(name: str, default: int, *, min_v: int | None = None, max_v: int | None = None) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        v = default
    else:
        try:
            v = int(raw)
        except ValueError:
            v = default
    if min_v is not None:
        v = max(min_v, v)
    if max_v is not None:
        v = min(max_v, v)
    return v


def _env_float(name: str, default: float, *, min_v: float | None = None, max_v: float | None = None) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        v = default
    else:
        try:
            v = float(raw)
        except ValueError:
            v = default
    if min_v is not None:
        v = max(min_v, v)
    if max_v is not None:
        v = min(max_v, v)
    return v


def _embedding_trust_env() -> bool:
    raw = (os.getenv("EMBEDDING_HTTP_TRUST_ENV") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return False


_embedding_http = httpx.Client(
    trust_env=_embedding_trust_env(),
    timeout=httpx.Timeout(120.0, connect=45.0),
)

embedding_client = (
    OpenAI(
        api_key=_dashscope_key,
        base_url=_dashscope_base,
        http_client=_embedding_http,
    )
    if _dashscope_key
    else None
)


def _embed_one(text: str) -> list[float] | None:
    if embedding_client is None:
        return None
    try:
        r = embedding_client.embeddings.create(model=RAG_EMBEDDING_MODEL, input=text)
        return r.data[0].embedding
    except Exception as e:
        _raise_if_embedding_quota(e)
        msg = str(e).strip() or type(e).__name__
        print(f"  Embedding 失败：{msg}")
        if "Connection" in type(e).__name__ or "connection" in msg.lower():
            print(
                "  提示：若需走系统代理，设 EMBEDDING_HTTP_TRUST_ENV=1 并确保代理已开。"
            )
        return None


def _embed_batch(texts: list[str], *, max_retry: int) -> list[list[float] | None]:
    """单次 API 多文本（条数不超过 DASHSCOPE_EMBEDDING_API_MAX_BATCH）；失败则对该批逐条请求。"""
    if not texts:
        return []
    if embedding_client is None:
        return [None] * len(texts)

    cap = DASHSCOPE_EMBEDDING_API_MAX_BATCH
    if len(texts) > cap:
        out: list[list[float] | None] = []
        for i in range(0, len(texts), cap):
            out.extend(_embed_batch(texts[i : i + cap], max_retry=max_retry))
        return out

    for attempt in range(max_retry):
        try:
            r = embedding_client.embeddings.create(model=RAG_EMBEDDING_MODEL, input=texts)
            by_idx: dict[int, list[float]] = {}
            for item in r.data:
                by_idx[item.index] = item.embedding
            out: list[list[float] | None] = []
            dim0: int | None = None
            for i in range(len(texts)):
                vec = by_idx.get(i)
                if vec is None:
                    out.append(None)
                    continue
                if dim0 is None:
                    dim0 = len(vec)
                elif len(vec) != dim0:
                    print(f"  严重：同批 embedding 维度不一致（{len(vec)} vs {dim0}），请检查模型。")
                    return [None] * len(texts)
                out.append(vec)
            if all(x is not None for x in out):
                return out
        except Exception as e:
            _raise_if_embedding_quota(e)
            msg = str(e).strip() or type(e).__name__
            wait = min(8.0, 1.5 * (attempt + 1))
            print(f"  批量 Embedding 失败（{msg}），{wait:.1f}s 后重试 ({attempt + 1}/{max_retry})…")
            time.sleep(wait)

    print("  批量 Embedding 仍失败，改为逐条请求该批…")
    return [_embed_one(t) for t in texts]


def _embed_content_key(doc_text: str) -> str:
    """同一模型 + 同一文档文本 → 同一 key；换模型自动失效。"""
    return hashlib.sha256(
        f"{RAG_EMBEDDING_MODEL}\0{doc_text}".encode("utf-8", errors="ignore")
    ).hexdigest()


def _embed_cache_base_dir() -> str:
    raw = (os.getenv("RAG_EMBED_CACHE_DIR") or "").strip()
    if raw:
        return os.path.abspath(os.path.normpath(raw))
    return os.path.join(_SCRIPT_DIR, "embedding_cache")


def _embed_cache_path(content_key: str) -> str:
    return os.path.join(_embed_cache_base_dir(), f"{content_key}.json")


def _embed_cache_disabled() -> bool:
    return (os.getenv("RAG_EMBED_CACHE_DISABLE") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _embed_cache_read(content_key: str) -> list[float] | None:
    if _embed_cache_disabled():
        return None
    p = _embed_cache_path(content_key)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            o = json.load(f)
        if o.get("model") != RAG_EMBEDDING_MODEL:
            return None
        v = o.get("embedding")
        if not isinstance(v, list) or not v:
            return None
        return [float(x) for x in v]
    except Exception:
        return None


def _embed_cache_write(content_key: str, vec: list[float]) -> None:
    if _embed_cache_disabled():
        return
    try:
        d = _embed_cache_base_dir()
        os.makedirs(d, exist_ok=True)
        p = _embed_cache_path(content_key)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"model": RAG_EMBEDDING_MODEL, "embedding": vec},
                f,
                ensure_ascii=False,
            )
        os.replace(tmp, p)
    except Exception as ex:
        print(f"  提示：写入嵌入缓存失败（可忽略）：{ex}")


def _embed_batch_cached(
    texts: list[str],
    *,
    max_retry: int,
    stats: dict[str, int] | None = None,
) -> list[list[float] | None]:
    """
    先查本地缓存，仅对未命中条目调用 DashScope，避免反复删 rag_db 时重复付 token。
    """
    if not texts:
        return []
    out: list[list[float] | None] = [None] * len(texts)
    need_idx: list[int] = []
    need_texts: list[str] = []
    for i, t in enumerate(texts):
        k = _embed_content_key(t)
        v = _embed_cache_read(k)
        if v is not None:
            out[i] = v
            if stats is not None:
                stats["cache_hits"] = stats.get("cache_hits", 0) + 1
        else:
            need_idx.append(i)
            need_texts.append(t)
    if not need_texts:
        return out
    if stats is not None:
        stats["api_texts"] = stats.get("api_texts", 0) + len(need_texts)
    got = _embed_batch(need_texts, max_retry=max_retry)
    for pos, vec in enumerate(got):
        idx = need_idx[pos]
        out[idx] = vec
        if vec is not None:
            _embed_cache_write(_embed_content_key(texts[idx]), vec)
    return out


def _clean_csv_title(raw: Any) -> str:
    """片名过短、NaN、占位符视为脏数据，不入库。"""
    if raw is None:
        return ""
    try:
        if pd.isna(raw):
            return ""
    except Exception:
        pass
    s = str(raw).strip()
    if len(s) < 2:
        return ""
    low = s.lower()
    if low in ("nan", "none", "null", "#n/a", "n/a"):
        return ""
    return s


def normalize_title(title: str) -> str:
    if not title:
        return ""
    title = title.lower().strip()
    title = re.sub(r"[\(\[]?\d{4}[\)\]]?", "", title)
    title = re.sub(r"[^\w\u4e00-\u9fff]", "", title)
    return title


def build_movie_document(movie: dict, source: str) -> str:
    parts: list[str] = []
    title = movie.get("title", "") or movie.get("name", "")
    if title:
        parts.append("电影：" + str(title))

    en_title = movie.get("en_title", "") or movie.get("original_title", "")
    if en_title and en_title != title:
        parts.append("英文名：" + str(en_title))

    year = movie.get("year", "") or movie.get("release_date", "")
    if year:
        parts.append("年份：" + str(year)[:4])

    directors = movie.get("directors", "") or movie.get("director", "")
    if directors:
        parts.append("导演：" + str(directors))

    actors = movie.get("actors", "") or movie.get("cast", "")
    if actors:
        actor_str = str(actors)
        if len(actor_str) > 100:
            actor_str = actor_str[:100] + "..."
        parts.append("主演：" + actor_str)

    genres = movie.get("genres", "") or movie.get("genre", "")
    if genres:
        parts.append("类型：" + str(genres))

    country = movie.get("country", "") or movie.get("production_countries", "")
    if country:
        parts.append("国家/地区：" + str(country))

    rating = movie.get("rating", "") or movie.get("vote_average", "")
    if rating:
        parts.append("评分：" + str(rating))

    intro = (
        movie.get("intro", "") or movie.get("overview", "") or movie.get("tagline", "")
    )
    if intro:
        intro_str = str(intro)
        if len(intro_str) > 300:
            intro_str = intro_str[:300] + "..."
        parts.append("简介：" + intro_str)

    quote = movie.get("quote", "")
    if quote:
        parts.append("一句话评价：" + str(quote))

    parts.append("数据来源：" + source)
    return "\n".join(parts)


def load_douban_data() -> list[dict[str, Any]]:
    movies: list[dict[str, Any]] = []
    abs_path = os.path.join(_SCRIPT_DIR, "movies", "douban_movies.csv")
    if not os.path.exists(abs_path):
        print(f"  豆瓣数据文件不存在：{abs_path}")
        return movies
    try:
        df = pd.read_csv(abs_path, encoding="utf-8-sig")
        skipped = 0
        for _, row in df.iterrows():
            m = row.to_dict()
            t = _clean_csv_title(m.get("title"))
            if not t:
                skipped += 1
                continue
            m["title"] = t
            m["source"] = "douban"
            movies.append(m)
        print(f"  加载豆瓣数据：{len(movies)} 部（跳过无片名/脏行 {skipped} 条）")
    except Exception as e:
        print(f"  加载豆瓣数据失败：{e}")
    return movies


def load_tmdb_data() -> list[dict[str, Any]]:
    movies: list[dict[str, Any]] = []
    abs_movies = os.path.join(_SCRIPT_DIR, "movies", "tmdb_5000_movies.csv")
    abs_credits = os.path.join(_SCRIPT_DIR, "movies", "tmdb_5000_credits.csv")
    if not os.path.exists(abs_movies):
        print(f"  TMDB 数据文件不存在：{abs_movies}")
        return movies
    try:
        df_movies = pd.read_csv(abs_movies)
        if os.path.exists(abs_credits):
            df_credits = pd.read_csv(abs_credits)

            def get_director(crew_str: str) -> str:
                try:
                    crew = json.loads(crew_str)
                    directors = [p["name"] for p in crew if p.get("job") == "Director"]
                    return " / ".join(directors[:3])
                except Exception:
                    return ""

            def get_cast(cast_str: str) -> str:
                try:
                    cast = json.loads(cast_str)
                    actors = [p["name"] for p in cast[:5]]
                    return " / ".join(actors)
                except Exception:
                    return ""

            df_credits["directors"] = df_credits["crew"].apply(get_director)
            df_credits["actors"] = df_credits["cast"].apply(get_cast)
            df_movies = df_movies.merge(
                df_credits[["movie_id", "directors", "actors"]],
                left_on="id",
                right_on="movie_id",
                how="left",
            )

        def get_genres(genres_str: str) -> str:
            try:
                genres = json.loads(genres_str)
                return " / ".join([g["name"] for g in genres])
            except Exception:
                return str(genres_str)

        def get_countries(countries_str: str) -> str:
            try:
                countries = json.loads(countries_str)
                return " / ".join([c["name"] for c in countries])
            except Exception:
                return str(countries_str)

        df_movies["genres_str"] = df_movies["genres"].apply(get_genres)
        countries_col = df_movies.get("production_countries", pd.Series(dtype=object))
        df_movies["countries_str"] = countries_col.apply(
            lambda x: get_countries(x) if pd.notna(x) else ""
        )

        min_vote = _env_float("RAG_TMDB_MIN_VOTE_AVERAGE", 4.0, min_v=0.0, max_v=10.0)
        if "vote_average" in df_movies.columns:
            va = pd.to_numeric(df_movies["vote_average"], errors="coerce")
            before_n = len(df_movies)
            df_movies = df_movies.assign(_va=va)
            df_movies = df_movies[df_movies["_va"] >= min_vote].drop(columns=["_va"])
            print(
                f"  TMDB vote_average ≥ {min_vote}：保留 {len(df_movies)} / {before_n} 行"
            )
        else:
            print("  警告：TMDB CSV 无 vote_average 列，未按评分过滤")

        tmdb_skipped = 0
        for _, row in df_movies.iterrows():
            title_raw = row.get("title", "")
            t_clean = _clean_csv_title(title_raw)
            if not t_clean:
                tmdb_skipped += 1
                continue
            mid = row.get("id")
            try:
                tmdb_id = int(mid) if pd.notna(mid) else None
            except (TypeError, ValueError):
                tmdb_id = None
            movies.append(
                {
                    "title": t_clean,
                    "en_title": row.get("original_title", ""),
                    "year": str(row.get("release_date", ""))[:4],
                    "rating": str(row.get("vote_average", "")),
                    "directors": row.get("directors", ""),
                    "actors": row.get("actors", ""),
                    "genres": row.get("genres_str", ""),
                    "country": row.get("countries_str", ""),
                    "intro": row.get("overview", ""),
                    "tagline": row.get("tagline", ""),
                    "source": "tmdb",
                    "tmdb_id": tmdb_id,
                }
            )
        print(
            f"  加载 TMDB 数据：{len(movies)} 部（无片名跳过 {tmdb_skipped} 条）"
        )
    except Exception as e:
        print(f"  加载 TMDB 数据失败：{e}")
    return movies


def score_movie_info(movie: dict) -> int:
    score = 0
    if movie.get("title"):
        score += 1
    if movie.get("year"):
        score += 1
    if movie.get("directors"):
        score += 3
    if movie.get("actors"):
        score += 3
    if movie.get("genres"):
        score += 2
    if movie.get("intro") and len(str(movie.get("intro", ""))) > 50:
        score += 2
    if movie.get("rating"):
        score += 1
    if movie.get("tmdb_id"):
        score += 2
    return score


def _merge_movie_ids(en: dict, other: dict) -> None:
    """合并去重时从另一条记录补全 tmdb_id / en_title。"""
    if not en.get("tmdb_id") and other.get("tmdb_id"):
        en["tmdb_id"] = other["tmdb_id"]
    oet = str(other.get("en_title") or "").strip()
    if oet and not str(en.get("en_title") or "").strip():
        en["en_title"] = oet


def deduplicate_movies(all_movies: list[dict]) -> tuple[list[dict], int]:
    unique_movies: dict[str, dict] = {}
    skipped = 0
    for movie in all_movies:
        title = movie.get("title", "")
        year = str(movie.get("year", ""))[:4] if movie.get("year") else ""
        norm_title = normalize_title(str(title))
        if not norm_title:
            skipped += 1
            continue
        dedup_key = f"{norm_title}_{year}" if year else norm_title

        if dedup_key in unique_movies:
            existing = unique_movies[dedup_key]
            if score_movie_info(movie) > score_movie_info(existing):
                merged = dict(movie)
                _merge_movie_ids(merged, existing)
                unique_movies[dedup_key] = merged
            else:
                _merge_movie_ids(existing, movie)
            skipped += 1
        else:
            unique_movies[dedup_key] = movie
    return list(unique_movies.values()), skipped


def _stable_doc_id(doc_text: str, source: str, title: str) -> str:
    """同一 source/title/正文 稳定映射为同一 Chroma id（重建库时便于与缓存对齐，无随机后缀）。"""
    h = hashlib.sha256(
        f"{source}\0{title}\0{doc_text[:2000]}".encode("utf-8", errors="ignore")
    ).hexdigest()
    return f"m_{h}"


def _sleep_with_hnsw_progress(total_sec: float, label: str, *, tick_sec: float) -> None:
    """
    将长 sleep 拆成多段并在终端打点。Chroma 不暴露 HNSW 构建百分比，此处用「已等待时长/设定总时长」作近似进度。
    """
    if total_sec <= 0:
        return
    deadline = time.time() + total_sec
    t_start = time.time()
    step = max(1.0, min(120.0, tick_sec))
    print(
        f"  [HNSW] 阶段：{label}，计划等待约 {total_sec:.0f}s，每 {step:.0f}s 输出一次进度"
    )
    while True:
        now = time.time()
        remain = deadline - now
        if remain <= 0:
            break
        time.sleep(min(step, remain))
        elapsed = time.time() - t_start
        pct = min(100.0, 100.0 * elapsed / total_sec) if total_sec > 0 else 100.0
        left = max(0.0, deadline - time.time())
        print(
            f"  [HNSW] {label} … 已过 {elapsed:.0f}s / 计划 {total_sec:.0f}s（约 {pct:.0f}%），剩余约 {left:.0f}s"
        )
    print(f"  [HNSW] 阶段结束：{label}（本阶段累计 {time.time() - t_start:.0f}s）")


def _wait_collection_count_stable(
    collection,
    expected: int,
    *,
    timeout_sec: float,
    poll_sec: float,
    stable_rounds: int,
    progress_log_sec: float,
) -> bool:
    deadline = time.time() + timeout_sec
    ok_streak = 0
    last_n: int | None = None
    last_log = 0.0
    log_iv = max(5.0, min(120.0, progress_log_sec))
    t_wait0 = time.time()
    print(
        f"  [HNSW] 等待 Chroma 内部索引与 count() 对齐（目标 {expected}，轮询 {poll_sec:.0f}s，状态约每 {log_iv:.0f}s 一条）"
    )
    while time.time() < deadline:
        try:
            n = int(collection.count())
        except Exception as ex:
            print(f"  count() 暂不可用：{ex}，{poll_sec:.0f}s 后重试…")
            time.sleep(poll_sec)
            continue
        if n == expected:
            ok_streak += 1
            if ok_streak >= stable_rounds:
                print(
                    f"  [HNSW] count() 已连续 {stable_rounds} 次为 {expected}，条数已稳定"
                    f"（本阶段耗时 {time.time() - t_wait0:.0f}s）。"
                )
                return True
        else:
            ok_streak = 0
        now = time.time()
        if n != last_n or (now - last_log) >= log_iv:
            elapsed = now - t_wait0
            print(
                f"  [HNSW] 索引/队列 … count()={n}，目标 {expected}，"
                f"已等待 {elapsed:.0f}s / 超时上限 {timeout_sec:.0f}s"
            )
            last_n = n
            last_log = now
        time.sleep(poll_sec)
    print(f"  超时：{int(timeout_sec)}s 内 count() 未稳定在 {expected}。")
    return False


def _preclose_warm_hnsw(collection, *, n_docs: int) -> None:
    """关库前用本集合里一条向量做一次 query，促使 HNSW 在当前进程内完整构建后再 close。"""
    try:
        sample = collection.get(limit=1, include=["embeddings"])
        vec = chroma_first_embedding_list(sample)
        if not vec:
            print("  query 预热跳过：未取到 embeddings。")
            return
        k = min(2, max(1, n_docs))
        collection.query(
            query_embeddings=[vec],
            n_results=k,
            include=["metadatas", "distances"],
        )
        print("  已在关库前执行 query 预热 HNSW。")
    except Exception as ex:
        print(f"  query 预热跳过：{ex}")


def build_vector_database(movies: list[dict]) -> bool:
    try:
        import chromadb
    except ImportError:
        print("请安装 chromadb：pip install chromadb")
        return False
    try:
        from chromadb.config import Settings
    except ImportError:
        try:
            from chromadb import Settings  # type: ignore
        except ImportError:
            Settings = None  # type: ignore

    if not movies:
        print("错误：电影列表为空。")
        return False

    embed_api_batch = _env_int(
        "RAG_EMBED_API_BATCH",
        DASHSCOPE_EMBEDDING_API_MAX_BATCH,
        min_v=1,
        max_v=DASHSCOPE_EMBEDDING_API_MAX_BATCH,
    )
    chroma_add_batch = _env_int("RAG_CHROMA_ADD_BATCH", 32, min_v=8, max_v=256)
    inter_add = _env_float("RAG_CHROMA_INTER_ADD_SEC", 0.25, min_v=0.0, max_v=5.0)
    max_retry = _env_int("RAG_EMBED_MAX_RETRY", 4, min_v=1, max_v=12)

    wait_sec = _env_float("RAG_CHROMA_QUEUE_WAIT_SEC", 14400.0, min_v=600.0, max_v=86400.0)
    poll_sec = _env_float("RAG_CHROMA_COUNT_POLL_SEC", 12.0, min_v=5.0, max_v=120.0)
    stable_rounds = _env_int("RAG_CHROMA_COUNT_STABLE_ROUNDS", 3, min_v=2, max_v=10)
    settle = _env_float("RAG_CHROMA_SETTLE_SEC", 450.0, min_v=30.0, max_v=3600.0)
    pre_close = _env_float("RAG_CHROMA_PRE_CLOSE_SLEEP_SEC", 60.0, min_v=5.0, max_v=300.0)
    post_close_sleep = _env_float(
        "RAG_CHROMA_POST_CLOSE_SLEEP_SEC", 90.0, min_v=0.0, max_v=600.0
    )
    cold_max_tries = _env_int("RAG_CHROMA_COLD_MAX_TRIES", 6, min_v=1, max_v=20)
    cold_retry_sleep = _env_float(
        "RAG_CHROMA_COLD_RETRY_SLEEP_SEC", 60.0, min_v=5.0, max_v=300.0
    )
    hnsw_tick = _env_float("RAG_CHROMA_HNSW_TICK_SEC", 10.0, min_v=3.0, max_v=120.0)
    index_log_sec = _env_float("RAG_CHROMA_INDEX_LOG_SEC", 15.0, min_v=5.0, max_v=120.0)

    print(f"\n开始构建向量库：{len(movies)} 条去重影片")
    print(f"  嵌入缓存目录：{_embed_cache_base_dir()}（设 RAG_EMBED_CACHE_DISABLE=1 可强制全量走 API）")
    print(f"  Chroma 目录：{os.path.abspath(CHROMA_DIR)}")
    try:
        print(f"  ChromaDB 版本：{getattr(chromadb, '__version__', '?')}")
    except Exception:
        pass
    print(
        f"  参数：embed 批量={embed_api_batch}，Chroma add 批量={chroma_add_batch}，"
        f"add 间隔={inter_add}s，嵌入重试={max_retry}；"
        f"HNSW 打点间隔={hnsw_tick:.0f}s（RAG_CHROMA_HNSW_TICK_SEC），"
        f"索引状态间隔={index_log_sec:.0f}s（RAG_CHROMA_INDEX_LOG_SEC）"
    )

    _rag_path = os.path.abspath(os.path.normpath(CHROMA_DIR))
    print(f"  持久化路径（绝对路径）：{_rag_path}")

    if Settings is not None:
        _settings = Settings(anonymized_telemetry=False)
        chroma_client = chromadb.PersistentClient(path=_rag_path, settings=_settings)
    else:
        _settings = None
        chroma_client = chromadb.PersistentClient(path=_rag_path)

    try:
        chroma_client.delete_collection(COLLECTION_NAME)
        print("  已删除旧集合")
    except Exception:
        pass

    collection = chroma_client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    embed_dim: int | None = None
    success_count = 0
    skip_count = 0
    embed_stats: dict[str, int] = {"cache_hits": 0, "api_texts": 0}

    pending_docs: list[str] = []
    pending_ids: list[str] = []
    pending_emb: list[list[float]] = []
    pending_meta: list[dict] = []

    def flush_chroma_batch() -> bool:
        nonlocal pending_docs, pending_ids, pending_emb, pending_meta, embed_dim
        if not pending_docs:
            return True
        try:
            collection.add(
                documents=pending_docs,
                embeddings=pending_emb,
                ids=pending_ids,
                metadatas=pending_meta,
            )
        except Exception as e:
            print(f"\n严重：collection.add 失败：{e}")
            return False
        pending_docs = []
        pending_ids = []
        pending_emb = []
        pending_meta = []
        time.sleep(inter_add)
        return True

    i = 0
    while i < len(movies):
        chunk = movies[i : i + embed_api_batch]
        i += len(chunk)

        texts: list[str] = []
        rows: list[tuple[dict, str, str]] = []
        for movie in chunk:
            title = movie.get("title", "") or movie.get("name", "")
            if not str(title).strip():
                skip_count += 1
                continue
            source = str(movie.get("source", "unknown"))
            doc_text = build_movie_document(movie, source)
            texts.append(doc_text)
            rows.append((movie, source, str(title)))

        if not texts:
            continue

        vectors = _embed_batch_cached(
            texts, max_retry=max_retry, stats=embed_stats
        )
        for (movie, source, title), vec, doc_text in zip(rows, vectors, texts):
            if vec is None:
                skip_count += 1
                continue
            if embed_dim is None:
                embed_dim = len(vec)
            elif len(vec) != embed_dim:
                print(f"\n严重：embedding 维度不一致（{len(vec)} vs {embed_dim}），停止。")
                _persistent_client_close(chroma_client)
                return False

            meta_row = {
                "title": title,
                "source": source,
                "year": str(movie.get("year", "")),
                "rating": str(movie.get("rating", "")),
                "genres": str(movie.get("genres", "")),
                "country": str(movie.get("country", "")),
            }
            tmid = movie.get("tmdb_id")
            if tmid is not None:
                try:
                    meta_row["tmdb_id"] = str(int(tmid))
                except (TypeError, ValueError):
                    pass
            en_t = str(movie.get("en_title") or "").strip()
            if en_t:
                meta_row["en_title"] = en_t

            pending_docs.append(doc_text)
            pending_ids.append(_stable_doc_id(doc_text, source, title))
            pending_emb.append(vec)
            pending_meta.append(meta_row)
            success_count += 1

            if len(pending_docs) >= chroma_add_batch:
                if not flush_chroma_batch():
                    _persistent_client_close(chroma_client)
                    return False
                print(
                    f"  进度：已入库约 {success_count} 条，跳过 {skip_count}…"
                )

    if not flush_chroma_batch():
        _persistent_client_close(chroma_client)
        return False

    print(
        f"  嵌入阶段结束：成功 {success_count}，跳过 {skip_count}；"
        f"缓存命中 {embed_stats.get('cache_hits', 0)} 条文本，"
        f"实际调用 API {embed_stats.get('api_texts', 0)} 条文本"
    )

    if success_count == 0:
        print("错误：没有任何向量入库。")
        _persistent_client_close(chroma_client)
        return False

    print(
        "\n  写入完成。等待 Chroma 内部索引与 count() 一致（请勿中断、勿同时开 main.py）；"
        "终端将打印 [HNSW] 行作为近似进度。"
    )
    try:
        collection.get(limit=1, include=["metadatas"])
    except Exception:
        pass

    if not _wait_collection_count_stable(
        collection,
        success_count,
        timeout_sec=wait_sec,
        poll_sec=poll_sec,
        stable_rounds=stable_rounds,
        progress_log_sec=index_log_sec,
    ):
        print(
            "\n严重：count 未在时限内稳定。可提高 RAG_CHROMA_QUEUE_WAIT_SEC，"
            "删除 rag_db 后重跑；确认无其它进程占用该目录。"
        )
        _persistent_client_close(chroma_client)
        return False

    print(f"\n  count 已稳定；进入 RAG_CHROMA_SETTLE_SEC（{settle:.0f}s）以便 HNSW/磁盘落盘…")
    _sleep_with_hnsw_progress(
        settle, "RAG_CHROMA_SETTLE_SEC（落盘缓冲）", tick_sec=hnsw_tick
    )

    try:
        n = collection.count()
        if n != success_count:
            print(f"  警告：settle 后 count()={n}，与入库 {success_count} 不一致。")
        else:
            print(f"  当前进程校验：count()={n}。")
    except Exception as e:
        print(f"\n严重：count() 失败：{e}")
        _persistent_client_close(chroma_client)
        return False

    _preclose_warm_hnsw(collection, n_docs=success_count)

    print(f"  close 前 RAG_CHROMA_PRE_CLOSE_SLEEP_SEC（{pre_close:.0f}s）…")
    _sleep_with_hnsw_progress(
        pre_close, "RAG_CHROMA_PRE_CLOSE_SLEEP_SEC（关库前）", tick_sec=hnsw_tick
    )

    _persistent_client_close(chroma_client, warn=True)

    gc.collect()
    print(
        f"  close 后 RAG_CHROMA_POST_CLOSE_SLEEP_SEC（{post_close_sleep:.0f}s）再冷启动校验…"
    )
    _sleep_with_hnsw_progress(
        post_close_sleep,
        "RAG_CHROMA_POST_CLOSE_SLEEP_SEC（关库后刷盘）",
        tick_sec=hnsw_tick,
    )

    n_cold: int | None = None
    last_cold_err: Exception | None = None
    for cold_i in range(cold_max_tries):
        try:
            chroma_client2 = (
                chromadb.PersistentClient(path=_rag_path, settings=_settings)
                if _settings is not None
                else chromadb.PersistentClient(path=_rag_path)
            )
            col2 = chroma_client2.get_collection(COLLECTION_NAME)
            n_cold = col2.count()
            if n_cold and n_cold > 0:
                sample_c = col2.get(limit=1, include=["embeddings"])
                vec_c = chroma_first_embedding_list(sample_c)
                if not vec_c:
                    raise RuntimeError("冷启动无法读取任意一条 embedding")
                col2.query(
                    query_embeddings=[vec_c],
                    n_results=max(1, min(2, n_cold)),
                    include=["metadatas", "distances"],
                )
            _persistent_client_close(chroma_client2)
            last_cold_err = None
            if cold_i > 0:
                print(f"  冷启动校验在第 {cold_i + 1} 次尝试时成功。")
            break
        except Exception as e:
            last_cold_err = e
            print(f"\n  冷启动失败（{cold_i + 1}/{cold_max_tries}）：{e}")
            if cold_i + 1 < cold_max_tries:
                print(f"  {cold_retry_sleep:.0f}s 后重试（带进度打点）…")
                _sleep_with_hnsw_progress(
                    cold_retry_sleep,
                    f"冷启动重试间隔（第 {cold_i + 1}/{cold_max_tries} 次）",
                    tick_sec=hnsw_tick,
                )

    if last_cold_err is not None or n_cold is None:
        print("\n严重：冷启动打开向量库仍失败（HNSW 未就绪或环境与 Chroma 不兼容）。")
        print(
            "  建议依次尝试："
            "\n  1) 增大 RAG_CHROMA_SETTLE_SEC（如 600）、RAG_CHROMA_POST_CLOSE_SLEEP_SEC（如 180）；"
            "\n  2) 删除 rag_db 后单独重跑本脚本（不要同时开后端）；"
            "\n  3) 确认 pip 中 chromadb 与 requirements.txt 一致；1.x 与 0.5.x 不得共用同一 rag_db；"
            "\n  4) chromadb 0.5.x：勿混装冲突的 hnswlib，按该版本依赖重装；Windows 编译失败需装 C++ Build Tools；"
            "\n  5) 暂时关闭杀毒/同步软件对 rag_db 目录的实时扫描。"
        )
        return False

    if n_cold != success_count:
        print(f"  警告：冷启动 count={n_cold}，与入库 {success_count} 不一致。")
    else:
        print(f"  冷启动校验通过：count()={n_cold}，且向量 query 成功")

    print(f"\n完成。路径：{os.path.abspath(CHROMA_DIR)}")
    print("后端从 recommender.common.CHROMA_DIR 加载同一 rag_db。")
    return True


def main() -> int:
    print("=" * 60)
    print("RAG 知识库构建")
    print("=" * 60)
    print(f"  嵌入模型：{RAG_EMBEDDING_MODEL}（须与查询侧一致）")

    if embedding_client is None:
        print("\n错误：未配置 DASHSCOPE_API_KEY。")
        return 1

    print("\n[1] 加载 CSV…")
    douban = load_douban_data()
    tmdb = load_tmdb_data()
    all_movies = douban + tmdb
    if not all_movies:
        print("\n未找到数据。需要：movies/douban_movies.csv、movies/tmdb_5000_movies.csv")
        return 1

    print(f"\n  原始：豆瓣 {len(douban)} + TMDB {len(tmdb)} = {len(all_movies)}")

    print("\n[2] 去重…")
    unique, dup_skipped = deduplicate_movies(all_movies)
    print(f"  去重后 {len(unique)} 部（合并丢弃 {dup_skipped} 条重复）")

    print("\n[3] 写入 Chroma…")
    try:
        ok = build_vector_database(unique)
    except RagBuildAbort:
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        try:
            _embedding_http.close()
        except Exception:
            pass
