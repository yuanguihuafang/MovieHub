from __future__ import annotations
# python backend/eval/recommend_eval.py          # 中文表格 + 生成 md
# python backend/eval/recommend_eval.py --json    # JSON 输出 + 生成 md
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable

# 允许直接运行本文件：python backend/eval/recommend_eval.py
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:  # pragma: no cover
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from backend.db.database import get_conn
from backend.eval.metrics import (
    TopKMetrics,
    evaluate_topk,
    expand_title_aliases,
    load_env,
    norm_title,
    parse_dt,
    parse_json_list,
    round_floats,
)


@dataclass(frozen=True)
class RecommendEvalConfig:
    """
    基于 recommend_logs + 用户后续反馈 的离线评估配置。

    评估口径：对每条 recommend_logs 视为一次推荐"曝光"，在曝光后的时间窗内，
    将用户对推荐电影产生的正反馈视为 ground truth。
    """

    k: int = 10
    lookahead_days: int = 14  # <=0 表示不限制时间窗
    min_logs: int = 30
    max_logs: int = 2000

    include_favorite: bool = True
    include_watched: bool = True
    include_like_vote: bool = True
    include_review: bool = True


# ==========================
# 手动配置区（直接运行文件用）
# ==========================
MANUAL_CFG = RecommendEvalConfig(
    k=10,
    lookahead_days=14,
    min_logs=30,
    max_logs=3000,
    include_favorite=True,
    include_watched=True,
    include_like_vote=True,
    include_review=True,
)

MANUAL_KS = "3,5,10,15"


def _parse_ks(s: str | None) -> list[int]:
    if not s:
        return []
    out: list[int] = []
    for part in str(s).split(","):
        p = part.strip()
        if not p:
            continue
        try:
            k = int(p)
        except ValueError:
            continue
        if k > 0 and k not in out:
            out.append(k)
    return out


def _fmt_num(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        s = f"{v:.2f}".rstrip("0").rstrip(".")
        return s if s else "0"
    return str(v)


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    cols = len(headers)
    widths = [len(h) for h in headers]
    for r in rows:
        for i in range(cols):
            widths[i] = max(widths[i], len(r[i]))

    def line(sep: str = "-") -> str:
        return "+".join([sep * (w + 2) for w in widths]).join(["+", "+"])

    def fmt_row(r: list[str]) -> str:
        parts = []
        for i in range(cols):
            parts.append(" " + r[i].ljust(widths[i]) + " ")
        return "|" + "|".join(parts) + "|"

    out = [line("="), fmt_row(headers), line("=")]
    for r in rows:
        out.append(fmt_row(r))
        out.append(line("-"))
    return "\n".join(out)


def render_human_report(res: dict[str, Any]) -> str:
    cfg = res.get("config") or {}
    note = str(res.get("note") or "")
    warn = str(res.get("warning") or "").strip()
    samples = res.get("samples")
    gt_rate = res.get("gt_nonempty_rate")
    empty_final = res.get("empty_final_movies")
    timing_ms = res.get("timing_ms")

    lines: list[str] = []
    lines.append("【MovieHub 推荐系统离线评估（曝光→反馈）】")
    if note:
        lines.append(note)
    lines.append("")
    lines.append("【配置】")
    lines.append(
        f"- K={_fmt_num(cfg.get('k'))}；额外K={os.getenv('MOVIEHUB_EVAL_KS') or '-'}；"
        f"时间窗={_fmt_num(cfg.get('lookahead_days'))}天"
    )
    lines.append(
        f"- 正反馈：收藏={_fmt_num(cfg.get('include_favorite'))} / 看过={_fmt_num(cfg.get('include_watched'))} / "
        f"点赞={_fmt_num(cfg.get('include_like_vote'))} / 影评={_fmt_num(cfg.get('include_review'))}"
    )
    lines.append("")
    lines.append("【样本概况】")
    lines.append(
        f"- 样本数={_fmt_num(samples)}；GT非空率={_fmt_num(gt_rate)}；空推荐条数={_fmt_num(empty_final)}；耗时={_fmt_num(timing_ms)}ms"
    )
    if warn:
        lines.append(f"- 提示：{warn}")

    def _rows_from(block: dict[str, Any], *, include_samples: bool) -> list[list[str]]:
        rows: list[list[str]] = []
        for k in sorted(block.keys(), key=lambda x: int(str(x))):
            d = block.get(k) or {}
            row = [str(k)]
            if include_samples:
                row.append(_fmt_num(d.get("samples")))
            row += [
                _fmt_num(d.get("precision@k")),
                _fmt_num(d.get("recall@k")),
                _fmt_num(d.get("hit_rate@k")),
                _fmt_num(d.get("mrr")),
                _fmt_num(d.get("ndcg@k")),
                _fmt_num(d.get("coverage")),
            ]
            rows.append(row)
        return rows

    by_k = res.get("metrics_by_k") or {}
    by_k_nonempty = res.get("metrics_on_nonempty_gt_by_k") or {}

    lines.append("")
    lines.append("【全部推荐记录】")
    headers = ["K", "Precision", "Recall", "HitRate", "MRR", "NDCG", "Coverage"]
    lines.append(_render_table(headers, _rows_from(by_k, include_samples=False)))

    lines.append("")
    lines.append("【有正反馈的用户】")
    headers2 = ["K", "样本数", "Precision", "Recall", "HitRate", "MRR", "NDCG", "Coverage"]
    lines.append(_render_table(headers2, _rows_from(by_k_nonempty, include_samples=True)))

    return "\n".join(lines)


def _fetch_recent_recommend_logs(conn, limit: int) -> list[dict[str, Any]]:
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(
            """
            SELECT id, user_id, final_movies, created_at
            FROM recommend_logs
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (int(limit),),
        )
        return list(cur.fetchall() or [])
    finally:
        cur.close()


def _fetch_ground_truth_for_log(
    conn,
    *,
    user_id: int,
    movie_names: Iterable[str],
    start: datetime,
    end: datetime,
    cfg: RecommendEvalConfig,
) -> set[str]:
    expanded: list[str] = []
    for x in movie_names:
        for a in expand_title_aliases(str(x)):
            if a not in expanded:
                expanded.append(a)
        if len(expanded) >= 400:
            break
    names = [str(x) for x in expanded if str(x)]
    if not names:
        return set()

    cur = conn.cursor(dictionary=True)
    try:
        ors: list[str] = []
        if cfg.include_favorite:
            ors.append("(is_favorite=1 AND fav_at IS NOT NULL)")
        if cfg.include_watched:
            ors.append("(is_watched=1 AND watched_at IS NOT NULL)")
        if cfg.include_like_vote:
            ors.append("(vote='like')")
        cond = " OR ".join(ors) if ors else "0"

        hits: set[str] = set()
        in_params = ",".join(["%s"] * len(names))

        cur.execute(
            f"""
            SELECT movie_name, vote, blocked,
                   is_favorite, fav_at,
                   is_watched, watched_at,
                   updated_at, created_at
            FROM user_movie_state
            WHERE user_id=%s
              AND movie_name IN ({in_params})
              AND blocked=0
              AND ({cond})
            """,
            tuple([int(user_id)] + names),
        )
        for r in cur.fetchall() or []:
            nm = str((r or {}).get("movie_name") or "")
            if not nm:
                continue
            nm_key = norm_title(nm) or nm

            if cfg.include_favorite and int((r or {}).get("is_favorite") or 0) == 1:
                ts = parse_dt((r or {}).get("updated_at")) or parse_dt((r or {}).get("created_at"))
                if ts is not None and start <= ts <= end:
                    hits.add(nm_key)

            if cfg.include_watched and int((r or {}).get("is_watched") or 0) == 1:
                ts = parse_dt((r or {}).get("updated_at")) or parse_dt((r or {}).get("created_at"))
                if ts is not None and start <= ts <= end:
                    hits.add(nm_key)

            if cfg.include_like_vote and str((r or {}).get("vote") or "").strip().lower() == "like":
                ts = parse_dt((r or {}).get("updated_at")) or parse_dt((r or {}).get("created_at"))
                if ts is not None and start <= ts <= end:
                    hits.add(nm_key)

        if cfg.include_review:
            cur.execute(
                f"""
                SELECT movie_name, created_at
                FROM reviews
                WHERE user_id=%s
                  AND movie_name IN ({in_params})
                """,
                tuple([int(user_id)] + names),
            )
            for r in cur.fetchall() or []:
                nm = str((r or {}).get("movie_name") or "")
                ts = parse_dt((r or {}).get("created_at"))
                if not nm or ts is None:
                    continue
                if start <= ts <= end:
                    hits.add(norm_title(nm) or nm)

        return hits
    finally:
        cur.close()


def evaluate_recommend_system(cfg: RecommendEvalConfig) -> dict[str, Any]:
    load_env()
    t0 = time.time()

    try:
        conn = get_conn()
    except Exception as ex:
        return {
            "config": asdict(cfg),
            "success": False,
            "error": f"无法连接数据库：{ex}",
            "timing_ms": int((time.time() - t0) * 1000),
        }

    try:
        logs = _fetch_recent_recommend_logs(conn, cfg.max_logs)
    except Exception as ex:
        conn.close()
        return {
            "config": asdict(cfg),
            "success": False,
            "error": f"无法读取 recommend_logs：{ex}",
            "timing_ms": int((time.time() - t0) * 1000),
        }

    ranked_lists: list[list[str]] = []
    gt_lists: list[list[str]] = []
    ranked_lists_nonempty_gt: list[list[str]] = []
    gt_lists_nonempty_gt: list[list[str]] = []
    used = 0
    gt_nonempty = 0
    empty_final_movies = 0

    for r in logs:
        uid = int((r or {}).get("user_id") or 0)
        created = parse_dt((r or {}).get("created_at"))
        if uid <= 0 or created is None:
            continue

        ranked = parse_json_list((r or {}).get("final_movies"))
        if not ranked:
            empty_final_movies += 1
            continue

        if int(cfg.lookahead_days) <= 0:
            start = datetime.min
            end = datetime.max
        else:
            start = created
            end = created + timedelta(days=max(1, int(cfg.lookahead_days)))

        gt = _fetch_ground_truth_for_log(
            conn,
            user_id=uid,
            movie_names=ranked[: max(1, int(cfg.k))],
            start=start,
            end=end,
            cfg=cfg,
        )
        ranked_norm = []
        for it in ranked:
            nn = norm_title(it)
            ranked_norm.append(nn or str(it))
        ranked_lists.append(ranked_norm)
        gtl = sorted({norm_title(x) or str(x) for x in gt if str(x)})
        gt_lists.append(gtl)
        if gtl:
            gt_nonempty += 1
            ranked_lists_nonempty_gt.append(ranked_norm)
            gt_lists_nonempty_gt.append(gtl)
        used += 1

    conn.close()

    ks = [int(cfg.k)]
    extra_ks = _parse_ks(os.getenv("MOVIEHUB_EVAL_KS"))
    for k in extra_ks:
        if k not in ks:
            ks.append(k)
    ks = sorted({max(1, int(k)) for k in ks})

    metrics_by_k: dict[str, Any] = {}
    metrics_nonempty_by_k: dict[str, Any] = {}
    for k in ks:
        m: TopKMetrics = evaluate_topk(ranked_lists, gt_lists, k=k)
        mn: TopKMetrics = evaluate_topk(
            ranked_lists_nonempty_gt, gt_lists_nonempty_gt, k=k
        )
        metrics_by_k[str(k)] = {
            "precision@k": m.precision_at_k,
            "recall@k": m.recall_at_k,
            "hit_rate@k": m.hit_rate_at_k,
            "mrr": m.mrr,
            "ndcg@k": m.ndcg_at_k,
            "coverage": m.coverage,
        }
        metrics_nonempty_by_k[str(k)] = {
            "samples": mn.samples,
            "precision@k": mn.precision_at_k,
            "recall@k": mn.recall_at_k,
            "hit_rate@k": mn.hit_rate_at_k,
            "mrr": mn.mrr,
            "ndcg@k": mn.ndcg_at_k,
            "coverage": mn.coverage,
        }

    metrics: dict[str, Any] = metrics_by_k.get(str(int(cfg.k))) or metrics_by_k[str(ks[0])]
    metrics_nonempty: dict[str, Any] = metrics_nonempty_by_k.get(str(int(cfg.k))) or metrics_nonempty_by_k[
        str(ks[0])
    ]

    out = {
        "config": asdict(cfg),
        "samples": int(min(len(ranked_lists), len(gt_lists))),
        "note": "该评估以 recommend_logs 为曝光点，在时间窗内统计用户对推荐电影的正反馈命中情况。",
        "gt_nonempty_rate": (gt_nonempty / used) if used else 0.0,
        "empty_final_movies": int(empty_final_movies),
        "metrics": metrics,
        "metrics_on_nonempty_gt": metrics_nonempty,
        "metrics_by_k": metrics_by_k,
        "metrics_on_nonempty_gt_by_k": metrics_nonempty_by_k,
        "timing_ms": int((time.time() - t0) * 1000),
    }
    if used < cfg.min_logs:
        out["warning"] = f"样本量偏少：仅 {used} 条 recommend_logs 可用于评估（min_logs={cfg.min_logs}）。"
    return round_floats(out)


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--lookahead-days", type=int, default=14)
    ap.add_argument("--max-logs", type=int, default=2000)
    ap.add_argument("--min-logs", type=int, default=30)
    ap.add_argument("--ks", type=str, default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if len(sys.argv) <= 1:
        if str(MANUAL_KS or "").strip():
            os.environ["MOVIEHUB_EVAL_KS"] = str(MANUAL_KS).strip()
        cfg = MANUAL_CFG
    else:
        if str(args.ks or "").strip():
            os.environ["MOVIEHUB_EVAL_KS"] = str(args.ks).strip()
        cfg = RecommendEvalConfig(
            k=int(args.k),
            lookahead_days=int(args.lookahead_days),
            max_logs=int(args.max_logs),
            min_logs=int(args.min_logs),
        )

    res = evaluate_recommend_system(cfg)

    if bool(args.json):
        report = json.dumps(res, ensure_ascii=False, indent=2)
    else:
        report = render_human_report(res)
    print(report)

    # 保存报告到 md 文件
    md_path = os.path.join(os.path.dirname(__file__), "eval_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print(f"\n报告已保存到: {md_path}")


if __name__ == "__main__":
    main()
