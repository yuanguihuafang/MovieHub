from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Optional, Sequence

from dotenv import load_dotenv


# ========== TopK 指标 ==========


@dataclass(frozen=True)
class TopKMetrics:
    k: int
    samples: int
    precision_at_k: float
    recall_at_k: float
    hit_rate_at_k: float
    mrr: float
    ndcg_at_k: float
    coverage: float


def _safe_div(a: float, b: float) -> float:
    if not b:
        return 0.0
    return float(a) / float(b)


def _dcg(rels: Sequence[int]) -> float:
    s = 0.0
    for i, rel in enumerate(rels, start=1):
        if not rel:
            continue
        s += float(rel) / math.log2(i + 1)
    return s


def evaluate_topk(
    ranked_lists: Sequence[Sequence[str]],
    ground_truth_lists: Sequence[Sequence[str]],
    *,
    k: int,
    item_universe: Iterable[str] | None = None,
) -> TopKMetrics:
    kk = max(1, int(k))
    n = min(len(ranked_lists), len(ground_truth_lists))
    if n <= 0:
        return TopKMetrics(
            k=kk, samples=0,
            precision_at_k=0.0, recall_at_k=0.0, hit_rate_at_k=0.0,
            mrr=0.0, ndcg_at_k=0.0, coverage=0.0,
        )

    total_p = 0.0
    total_r = 0.0
    total_hit = 0.0
    total_mrr = 0.0
    total_ndcg = 0.0
    rec_items: set[str] = set()
    uni: set[str] = set(item_universe or [])

    for i in range(n):
        ranked = [str(x) for x in (ranked_lists[i] or []) if str(x)]
        gt_set = {str(x) for x in (ground_truth_lists[i] or []) if str(x)}
        topk = ranked[:kk]
        rec_items.update(topk)
        if not item_universe:
            uni.update(ranked)
        if not gt_set:
            continue
        hits = [1 if it in gt_set else 0 for it in topk]
        hit_cnt = sum(hits)
        total_p += _safe_div(hit_cnt, kk)
        total_r += _safe_div(hit_cnt, len(gt_set))
        total_hit += 1.0 if hit_cnt > 0 else 0.0
        rr = 0.0
        for rnk, it in enumerate(ranked, start=1):
            if it in gt_set:
                rr = 1.0 / float(rnk)
                break
        total_mrr += rr
        dcg = _dcg(hits)
        idcg = _dcg(sorted(hits, reverse=True))
        total_ndcg += _safe_div(dcg, idcg)

    cov = _safe_div(len(rec_items), len(uni) if uni else 0)
    return TopKMetrics(
        k=kk, samples=n,
        precision_at_k=_safe_div(total_p, n),
        recall_at_k=_safe_div(total_r, n),
        hit_rate_at_k=_safe_div(total_hit, n),
        mrr=_safe_div(total_mrr, n),
        ndcg_at_k=_safe_div(total_ndcg, n),
        coverage=cov,
    )


# ========== 工具函数 ==========

_WS_RE = re.compile(r"\s+")

# 别名词典缓存
_lexicon: dict[str, str] | None = None


def load_env() -> None:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    load_dotenv(os.path.join(repo_root, ".env"), override=True)


def _load_lexicon() -> dict[str, str]:
    """加载 db15k_movie_lexicon.json 的 alias_to_entity 映射"""
    global _lexicon
    if _lexicon is not None:
        return _lexicon
    lexicon_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "kg", "db15k_movie_lexicon.json"
    )
    try:
        with open(lexicon_path, encoding="utf-8") as f:
            data = json.load(f)
        _lexicon = dict(data.get("alias_to_entity") or {})
    except Exception:
        _lexicon = {}
    return _lexicon


def parse_dt(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "").replace("T", " "))
    except Exception:
        return None


def parse_json_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if str(x)]
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                return [str(x) for x in arr if str(x)]
        except Exception:
            return []
    return []


def norm_title(s: str) -> str:
    t = (s or "").strip().lower()
    if not t:
        return ""
    t = t.replace("_", " ")
    for suf in ("(film)", "（电影）", "电影", "影片"):
        if t.endswith(suf):
            t = t[: -len(suf)].strip()
    t = _WS_RE.sub(" ", t)
    return t


def expand_title_aliases(title: str) -> list[str]:
    """扩展片名别名：下划线/空格、中英文映射、大词典"""
    raw = (title or "").strip()
    if not raw:
        return []
    aliases: list[str] = []
    for t in (raw, raw.replace("_", " "), norm_title(raw)):
        if t and t not in aliases:
            aliases.append(t)
    # 小词典（19条硬编码）
    try:
        from backend.recommender.common import MOVIE_NAME_MAPPING, MOVIE_NAME_REVERSE_MAPPING
        if raw in MOVIE_NAME_MAPPING:
            cn = str(MOVIE_NAME_MAPPING.get(raw) or "").strip()
            if cn and cn not in aliases:
                aliases.append(cn)
            if norm_title(cn) not in aliases:
                aliases.append(norm_title(cn))
        if raw in MOVIE_NAME_REVERSE_MAPPING:
            en = str(MOVIE_NAME_REVERSE_MAPPING.get(raw) or "").strip()
            if en and en not in aliases:
                aliases.append(en)
            if norm_title(en) not in aliases:
                aliases.append(norm_title(en))
    except Exception:
        pass
    # 大词典（4653条 alias_to_entity）
    lex = _load_lexicon()
    raw_lower = raw.lower()
    raw_norm = norm_title(raw)
    for key in (raw, raw_lower, raw_norm):
        if key in lex:
            entity = str(lex[key] or "").strip()
            if entity and entity not in aliases:
                aliases.append(entity)
            entity_norm = norm_title(entity)
            if entity_norm and entity_norm not in aliases:
                aliases.append(entity_norm)
    # 反向：检查 aliases 中的名称是否在词典里映射到实体
    for alias in list(aliases):
        alias_lower = alias.lower()
        if alias_lower in lex:
            entity = str(lex[alias_lower] or "").strip()
            if entity and entity not in aliases:
                aliases.append(entity)
            entity_norm = norm_title(entity)
            if entity_norm and entity_norm not in aliases:
                aliases.append(entity_norm)
    return [a for a in aliases if a]


def round_floats(v: Any) -> Any:
    if isinstance(v, float):
        r = round(v, 2)
        return 0.0 if r == -0.0 else r
    if isinstance(v, list):
        return [round_floats(x) for x in v]
    if isinstance(v, tuple):
        return tuple(round_floats(x) for x in v)
    if isinstance(v, dict):
        return {k: round_floats(x) for k, x in v.items()}
    return v
