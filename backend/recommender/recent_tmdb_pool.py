"""
推荐链路第三路：TMDB「最近 / 即将上映」工具池（recent_pool）

**定位（与 KG、片库 RAG·LLM 并列）**

- **第一路**：知识图谱 Multi_MoE（DB15K 种子 + 链路预测）。
- **第二路**：片库标准 RAG（Chroma 向量证据 → 主链路 LLM 出片；另有「仅向量+豆瓣」供图谱种子）。
- **第三路（本模块）**：由 **TMDB API**（或首页同源缓存）提供的 **正在上映 / 即将上映** 候选列表，
  在 **定榜（图谱 + 片库名额）完成之后** 再追加 **0～3 部**，**不计入** ``topk_kg`` / ``topk_rag``。
  语义上相当于把「拉最近片单」当作 **工具调用结果**：前端/API 把 ``recent_pool`` 传给
  ``recommend_for_user(..., recent_pool=...)``；若未传则服务端可在路由层调用
  ``recent_pool_for_recommend()`` 自动填充。

**数据来源优先级**（与原先 ``api.routers.recommend`` 一致）

1. 磁盘 ``tmdb_home_cache.json`` 中的 ``now_playing`` / ``upcoming`` 块；
2. 进程内 ``common._cache`` 中首页已拉取的 TMDB 列表；
3. 配置了 ``TMDB_API_KEY`` 时直连 ``now_playing_movies`` / ``upcoming_movies``。

**合并规则**（实现在 ``recommend.py``）

- 按用户偏好类型优先匹配池内条目，否则按分数/顺序补位；
- 与定榜主列表 **片名去重** 后再追加。

环境变量：``TMDB_API_KEY``、代理相关见 ``backend.services.tmdb_client``。
"""

from __future__ import annotations

def rows_to_recent_pool(rows: list) -> list[dict]:
    """将首页/TMDB 行数据规范为推荐用 ``recent_pool`` 项（按片名去重）。"""
    out: list[dict] = []
    seen: set[str] = set()
    for m in rows or []:
        if not isinstance(m, dict):
            continue
        nm = (m.get("name") or m.get("display") or m.get("title") or "").strip()
        if not nm or nm in seen:
            continue
        seen.add(nm)
        tid = m.get("tmdb_id")
        try:
            tid_i = int(tid) if tid is not None and str(tid).strip() else 0
        except Exception:
            tid_i = 0
        out.append(
            {
                "name": nm,
                "tmdb_id": tid_i or None,
                "score": m.get("score"),
                "source": str(m.get("source") or ""),
                "genres": str(m.get("genres") or ""),
                "poster_url": m.get("poster_url"),
            }
        )
    return out


def recent_pool_for_recommend() -> list[dict]:
    """
    构建「最近上映 / 即将上映」候选池（供定榜后第三路追加）。

    顺序：磁盘首页缓存 → 进程内首页缓存 → 直连 TMDB（需密钥）。
    """
    chunks: list = []
    from backend.services.tmdb_home_cache import read_cache

    disk = read_cache() or {}
    if isinstance(disk, dict):
        for sec in ("now_playing", "upcoming"):
            chunks.extend(disk.get(sec) or [])
    pool = rows_to_recent_pool(chunks)
    if pool:
        return pool
    try:
        from backend.recommender.common import _cache

        mem: list = []
        for key in ("tmdb_home_now_playing", "tmdb_home_upcoming"):
            mem.extend(_cache.get(key) or [])
        pool = rows_to_recent_pool(mem)
        if pool:
            return pool
    except Exception:
        pass
    try:
        from backend.recommender.home import _tmdb_row_to_home_item
        from backend.services.tmdb_client import (
            now_playing_movies,
            tmdb_configured,
            upcoming_movies,
        )

        if not tmdb_configured():
            return []
        live: list[dict] = []
        for r in now_playing_movies(12):
            x = _tmdb_row_to_home_item(r)
            if x:
                live.append(x)
        for r in upcoming_movies(12):
            x = _tmdb_row_to_home_item(r)
            if x:
                live.append(x)
        return rows_to_recent_pool(live)
    except Exception:
        return []


def recent_extra_pipeline_message(
    *,
    cap_final: int,
    appended: int,
    used_recent: int,
    matched_recent: int,
    has_candidates: bool,
) -> str:
    """
    ``recommend.py`` 中 ``pipeline`` 步骤 ``recent_extra`` 的说明文案（第三路 TMDB 工具池）。
    """
    if appended > 0:
        return (
            f"第三路（TMDB API 工具池 recent_pool）：定榜（图谱+片库 {cap_final} 条）之后追加 "
            f"{appended} 条，不占 KG/片库 RAG·LLM 配额"
            f"（池内选用 {used_recent} 条，类型命中 {matched_recent} 条）。"
        )
    if not has_candidates:
        return "未追加：无可用候选（请配置 TMDB_API_KEY 或打开首页缓存以填充 recent_pool）。"
    return "未追加：与定榜结果同片名去重后无剩余，或候选被排除。"
