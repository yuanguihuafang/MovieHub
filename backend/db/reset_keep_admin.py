"""
清空业务数据，仅保留 users 表中用户名为 admin 的账号；将 admin 的 id 置为 1；
各表 AUTO_INCREMENT 与当前最大 id 对齐（空表从 1 开始）。

用法（配置 MYSQL_* 或 .env 后）:
  python -m backend.db.reset_keep_admin --dry-run
  python -m backend.db.reset_keep_admin

说明:
  - admin 按不区分大小写匹配用户名（LOWER(username)='admin'）。
  - 若不存在任何 admin 用户，脚本退出并报错（不修改数据库）。
"""
from __future__ import annotations

import argparse
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_REPO_ROOT, ".env"))
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

import mysql.connector

# 与 repair_autoincrement 一致：含 AUTO_INCREMENT 主键 id 的表（先清空、后改 AI）
TABLES_WITH_AI = [
    "user_notifications",
    "review_likes",
    "review_comments",
    "reviews",
    "playlist_items",
    "playlists",
    "recommend_logs",
    "browse_history",
    "user_movie_state",
    "users",
]


def connect():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "moviehub"),
        charset="utf8mb4",
    )


def _sync_auto_increment(cur, conn) -> None:
    for t in TABLES_WITH_AI:
        cur.execute(f"SELECT COALESCE(MAX(id), 0) AS m FROM `{t}`")
        row = cur.fetchone()
        m = int((row or [0])[0])
        next_ai = max(1, m + 1)
        cur.execute(f"ALTER TABLE `{t}` AUTO_INCREMENT = %s", (next_ai,))


def main() -> None:
    ap = argparse.ArgumentParser(description="Reset DB: keep only admin user, renumber ids.")
    ap.add_argument("--dry-run", action="store_true", help="Print plan only.")
    args = ap.parse_args()

    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, username, role FROM users WHERE LOWER(username)=%s",
            ("admin",),
        )
        admins = cur.fetchall() or []
        if not admins:
            print("错误: 未找到用户名为 admin 的账号，已中止（未修改数据库）。")
            sys.exit(1)
        if len(admins) > 1:
            print("错误: 存在多条 admin 用户名记录，已中止。")
            sys.exit(1)

        admin_id = int(admins[0][0])
        admin_name = admins[0][1]

        if args.dry_run:
            print(
                f"[dry-run] 将 DELETE 清空除 users 外的业务表；"
                f"DELETE 其他用户；保留 admin={admin_name!r} (当前 id={admin_id})，并将其 id 设为 1；"
                f"同步各表 AUTO_INCREMENT。"
            )
            return

        cur.execute("SET FOREIGN_KEY_CHECKS=0")

        # 使用 DELETE 而非 TRUNCATE，以便在同一事务中可回滚（TRUNCATE 会隐式提交）
        for t in TABLES_WITH_AI:
            if t == "users":
                continue
            cur.execute(f"DELETE FROM `{t}`")

        cur.execute("DELETE FROM users WHERE LOWER(username) <> %s", ("admin",))

        cur.execute("SELECT id FROM users WHERE LOWER(username)=%s", ("admin",))
        row = cur.fetchone()
        if not row:
            conn.rollback()
            print("错误: 删除后未找到 admin 用户。")
            sys.exit(1)

        cur_id = int(row[0])
        if cur_id != 1:
            cur.execute("UPDATE users SET id=1 WHERE LOWER(username)=%s LIMIT 1", ("admin",))

        _sync_auto_increment(cur, conn)

        cur.execute("SET FOREIGN_KEY_CHECKS=1")
        conn.commit()
        print("完成: 仅保留 admin，已清空其余数据，admin.id=1，AUTO_INCREMENT 已同步。")
    except Exception as e:
        conn.rollback()
        print(f"失败: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
