import os
import mysql.connector
from mysql.connector import pooling
import hashlib
import secrets
import time
import json
from typing import Optional, Any, Dict, List

FEEDBACK_KEEP = object()

_pool = None

def normalize_movie_source(src: str) -> str:
    """
    统一 movie_source 取值，便于 user_movie_state 唯一键稳定。
    约定输出：douban_csv / tmdb_csv / tmdb_api / kg
    """
    s = (src or "").strip().lower()
    if not s:
        return "kg"
    if s in ("douban", "douban_csv"):
        return "douban_csv"
    if s in ("tmdb", "tmdb5000", "tmdb_csv"):
        return "tmdb_csv"
    if s in ("tmdb_api", "tmdb_api_v3"):
        return "tmdb_api"
    if s in ("kg", "graph"):
        return "kg"
    return s[:32]


def _ums_cleanup_if_empty(cur, user_id: int, movie_name: str, movie_source: str) -> None:
    """策略B：当状态全空时删除整行。"""
    cur.execute(
        """
        DELETE FROM user_movie_state
        WHERE user_id=%s AND movie_name=%s AND movie_source=%s
          AND is_favorite=0 AND is_watched=0 AND vote='' AND blocked=0 AND note=''
        """,
        (int(user_id), movie_name, movie_source),
    )


def _alloc_next_seq(cur, table: str) -> int:
    """
    分配连续“展示序号” seq：始终为当前最大 seq + 1（删除会重排为 1..N）。
    调用方应在同一连接内对目标表加写锁，避免并发分配重复 seq。
    """
    cur.execute(f"SELECT COALESCE(MAX(seq), 0) AS m FROM {table}")
    row = cur.fetchone()
    if isinstance(row, dict):
        m = int(row.get("m") or 0)
    else:
        m = int((row[0] if row else 0) or 0)
    return m + 1

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def get_pool():
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="moviehub_pool",
            pool_size=10,
            pool_reset_session=True,
            host=os.getenv("MYSQL_HOST", "localhost"),
            port=int(os.getenv("MYSQL_PORT", 3306)),
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            database=os.getenv("MYSQL_DATABASE", "moviehub"),
            charset="utf8mb4",
            autocommit=True,
        )
    return _pool


def get_conn():
    return get_pool().get_connection()


class DBConnection:
    def __init__(self):
        self.conn = None
        self.cur = None

    def __enter__(self):
        self.conn = get_conn()
        self.cur = self.conn.cursor(dictionary=True)
        return self.conn, self.cur

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.cur:
            try:
                self.cur.close()
            except:
                pass
        if self.conn:
            try:
                self.conn.close()
            except:
                pass
        return False


INIT_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(64)  NOT NULL UNIQUE,
    password    VARCHAR(256) NOT NULL,
    role        VARCHAR(32)  NOT NULL DEFAULT 'user',
    preferred_genres VARCHAR(512) NOT NULL DEFAULT '',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_movie_state (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT          NOT NULL,
    movie_name   VARCHAR(256) NOT NULL,
    movie_source VARCHAR(32)  NOT NULL DEFAULT 'kg',
    tmdb_id      INT NULL,
    genres       VARCHAR(256) NOT NULL DEFAULT '',
    is_favorite  TINYINT(1)   NOT NULL DEFAULT 0,
    is_watched   TINYINT(1)   NOT NULL DEFAULT 0,
    vote         VARCHAR(16)  NOT NULL DEFAULT '',
    blocked      TINYINT(1)   NOT NULL DEFAULT 0,
    note         VARCHAR(500) NOT NULL DEFAULT '',
    fav_at       DATETIME NULL,
    watched_at   DATETIME NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_movie (user_id, movie_name, movie_source),
    INDEX idx_user_fav (user_id, is_favorite, fav_at),
    INDEX idx_user_watched (user_id, is_watched, watched_at),
    INDEX idx_user_blocked (user_id, blocked, updated_at),
    INDEX idx_user_vote (user_id, vote, updated_at),
    INDEX idx_tmdb (tmdb_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS browse_history (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    movie_name  VARCHAR(256) NOT NULL,
    genres      VARCHAR(256) DEFAULT '',
    view_count  INT DEFAULT 1,
    viewed_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_movie (user_id, movie_name),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS recommend_logs (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    user_input  TEXT,
    kg_movies   TEXT,
    rag_movies  TEXT,
    final_movies TEXT,
    recommend_text TEXT,
    elapsed_ms  INT DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS playlists (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    name        VARCHAR(64) NOT NULL,
    description VARCHAR(200) NOT NULL DEFAULT '',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS playlist_items (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    playlist_id INT NOT NULL,
    movie_name  VARCHAR(256) NOT NULL,
    movie_source VARCHAR(32) NOT NULL DEFAULT '',
    tmdb_id     INT NULL,
    genres      VARCHAR(256) NOT NULL DEFAULT '',
    poster_url  VARCHAR(512) NOT NULL DEFAULT '',
    genres_str  VARCHAR(128) NOT NULL DEFAULT '',
    score_str   VARCHAR(32) NOT NULL DEFAULT '',
    short_review VARCHAR(600) NOT NULL DEFAULT '',
    added_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_list_movie (playlist_id, movie_name),
    INDEX idx_list (playlist_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS reviews (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    movie_name  VARCHAR(256) NOT NULL,
    movie_source VARCHAR(32) NOT NULL DEFAULT '',
    rating      DECIMAL(3,1) DEFAULT NULL,
    content     VARCHAR(800) NOT NULL DEFAULT '',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_movie (user_id, movie_name),
    INDEX idx_movie (movie_name),
    INDEX idx_user (user_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS review_comments (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    review_id   INT NOT NULL,
    user_id     INT NOT NULL,
    parent_id   INT DEFAULT NULL,
    content     VARCHAR(800) NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_review (review_id),
    INDEX idx_user (user_id),
    INDEX idx_parent (parent_id),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS review_likes (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    target_type VARCHAR(16) NOT NULL,
    target_id   INT NOT NULL,
    user_id     INT NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_like (target_type, target_id, user_id),
    INDEX idx_target (target_type, target_id),
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_notifications (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    kind        VARCHAR(32) NOT NULL,
    title       VARCHAR(300) NOT NULL,
    detail      VARCHAR(600) NOT NULL DEFAULT '',
    payload     JSON NULL,
    is_read     TINYINT(1) NOT NULL DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_unread (user_id, is_read, created_at),
    INDEX idx_user_created (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

def init_db():
    db_name = os.getenv("MYSQL_DATABASE", "moviehub")
    conn = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        charset="utf8mb4",
    )
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    conn.close()

    conn = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=db_name,
        charset="utf8mb4",
    )
    cur = conn.cursor()
    for stmt in INIT_SQL.split(";"):
        stmt = stmt.strip()
        if stmt:
            cur.execute(stmt)
    conn.commit()
    cur.close(); conn.close()
    migrate_schema()


def migrate_schema():
    """为已有数据库补充新列（可重复执行）。"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "ALTER TABLE users ADD COLUMN preferred_genres VARCHAR(512) NOT NULL DEFAULT ''"
            )
            conn.commit()
        except mysql.connector.Error as e:
            if e.errno != 1060:
                raise

        # recommend_logs: 追加列（用于管理员查看“最终推荐了哪些电影”）
        for stmt in (
            "ALTER TABLE recommend_logs ADD COLUMN final_movies TEXT",
            "ALTER TABLE recommend_logs ADD COLUMN recommend_text TEXT",
            "ALTER TABLE recommend_logs ADD COLUMN elapsed_ms INT DEFAULT 0",
            "ALTER TABLE recommend_logs ADD COLUMN inference_meta LONGTEXT NULL COMMENT '推荐推理流水线与图谱元信息 JSON'",
        ):
            try:
                cur.execute(stmt)
                conn.commit()
            except mysql.connector.Error as e:
                if e.errno != 1060:
                    raise

        # users：影评禁言字段
        for stmt in (
            "ALTER TABLE users ADD COLUMN review_muted_until DATETIME NULL",
            "ALTER TABLE users ADD COLUMN review_mute_reason VARCHAR(200) NOT NULL DEFAULT ''",
        ):
            try:
                cur.execute(stmt)
                conn.commit()
            except mysql.connector.Error as e:
                if e.errno != 1060:
                    raise

        # reviews：评分允许小数（DECIMAL(3,1)）
        try:
            cur.execute("ALTER TABLE reviews MODIFY COLUMN rating DECIMAL(3,1) NULL")
            conn.commit()
        except mysql.connector.Error:
            # 兼容：老库可能没有 reviews 表或权限问题；忽略不阻塞启动
            pass

        # playlist_items：保存 TMDB 影片的 tmdb_id（用于从片单打开详情）
        try:
            cur.execute("ALTER TABLE playlist_items ADD COLUMN tmdb_id INT NULL")
            conn.commit()
        except mysql.connector.Error as e:
            if e.errno != 1060:
                raise

        # playlist_items：保存推荐卡片字段（海报/类型/评分/短评），用于片单内还原推荐卡片
        for stmt in (
            "ALTER TABLE playlist_items ADD COLUMN poster_url VARCHAR(512) NOT NULL DEFAULT ''",
            "ALTER TABLE playlist_items ADD COLUMN genres_str VARCHAR(128) NOT NULL DEFAULT ''",
            "ALTER TABLE playlist_items ADD COLUMN score_str VARCHAR(32) NOT NULL DEFAULT ''",
            "ALTER TABLE playlist_items ADD COLUMN short_review VARCHAR(600) NOT NULL DEFAULT ''",
        ):
            try:
                cur.execute(stmt)
                conn.commit()
            except mysql.connector.Error as e:
                if e.errno != 1060:
                    raise

        # browse_history：用于管理端“连续序号”的展示字段（不作为主键）
        for stmt in (
            "ALTER TABLE browse_history ADD COLUMN seq INT NOT NULL DEFAULT 0",
            "CREATE INDEX idx_hist_seq ON browse_history(seq)",
        ):
            try:
                cur.execute(stmt)
                conn.commit()
            except mysql.connector.Error as e:
                # 1060: Duplicate column; 1061: Duplicate key name
                if e.errno not in (1060, 1061):
                    raise

        # 合并表：user_movie_state（老库升级/可重复执行）
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_movie_state (
                id           INT AUTO_INCREMENT PRIMARY KEY,
                user_id      INT          NOT NULL,
                movie_name   VARCHAR(256) NOT NULL,
                movie_source VARCHAR(32)  NOT NULL DEFAULT 'kg',
                tmdb_id      INT NULL,
                genres       VARCHAR(256) NOT NULL DEFAULT '',
                is_favorite  TINYINT(1)   NOT NULL DEFAULT 0,
                is_watched   TINYINT(1)   NOT NULL DEFAULT 0,
                vote         VARCHAR(16)  NOT NULL DEFAULT '',
                blocked      TINYINT(1)   NOT NULL DEFAULT 0,
                note         VARCHAR(500) NOT NULL DEFAULT '',
                fav_at       DATETIME NULL,
                watched_at   DATETIME NULL,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uk_user_movie (user_id, movie_name, movie_source),
                INDEX idx_user_fav (user_id, is_favorite, fav_at),
                INDEX idx_user_watched (user_id, is_watched, watched_at),
                INDEX idx_user_blocked (user_id, blocked, updated_at),
                INDEX idx_user_vote (user_id, vote, updated_at),
                INDEX idx_tmdb (tmdb_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        conn.commit()

        # playlists/playlist_items：可重复执行（用于老库升级）
        for stmt in (
            """
            CREATE TABLE IF NOT EXISTS playlists (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                user_id     INT NOT NULL,
                name        VARCHAR(64) NOT NULL,
                description VARCHAR(200) NOT NULL DEFAULT '',
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS playlist_items (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                playlist_id INT NOT NULL,
                movie_name  VARCHAR(256) NOT NULL,
                movie_source VARCHAR(32) NOT NULL DEFAULT '',
                tmdb_id     INT NULL,
                genres      VARCHAR(256) NOT NULL DEFAULT '',
                poster_url  VARCHAR(512) NOT NULL DEFAULT '',
                genres_str  VARCHAR(128) NOT NULL DEFAULT '',
                score_str   VARCHAR(32) NOT NULL DEFAULT '',
                short_review VARCHAR(600) NOT NULL DEFAULT '',
                added_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uk_list_movie (playlist_id, movie_name),
                INDEX idx_list (playlist_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
        ):
            cur.execute(stmt)
            conn.commit()

        # 影评/评论/点赞表：老库升级
        for stmt in (
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                user_id     INT NOT NULL,
                movie_name  VARCHAR(256) NOT NULL,
                movie_source VARCHAR(32) NOT NULL DEFAULT '',
                rating      TINYINT DEFAULT NULL,
                content     VARCHAR(800) NOT NULL DEFAULT '',
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uk_user_movie (user_id, movie_name),
                INDEX idx_movie (movie_name),
                INDEX idx_user (user_id),
                INDEX idx_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS review_comments (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                review_id   INT NOT NULL,
                user_id     INT NOT NULL,
                parent_id   INT DEFAULT NULL,
                content     VARCHAR(800) NOT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_review (review_id),
                INDEX idx_user (user_id),
                INDEX idx_parent (parent_id),
                INDEX idx_created (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            """
            CREATE TABLE IF NOT EXISTS review_likes (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                target_type VARCHAR(16) NOT NULL,
                target_id   INT NOT NULL,
                user_id     INT NOT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uk_like (target_type, target_id, user_id),
                INDEX idx_target (target_type, target_id),
                INDEX idx_user (user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
        ):
            cur.execute(stmt)
            conn.commit()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS user_notifications (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                user_id     INT NOT NULL,
                kind        VARCHAR(32) NOT NULL,
                title       VARCHAR(300) NOT NULL,
                detail      VARCHAR(600) NOT NULL DEFAULT '',
                payload     JSON NULL,
                is_read     TINYINT(1) NOT NULL DEFAULT 0,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_unread (user_id, is_read, created_at),
                INDEX idx_user_created (user_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"⚠️  [DB] 数据库迁移异常: {str(e)[:100]}")


def user_username(uid: int) -> str:
    with DBConnection() as (conn, cur):
        cur.execute("SELECT username FROM users WHERE id=%s", (int(uid),))
        r = cur.fetchone()
    return (r or {}).get("username") or "用户"


def _payload_json(payload: Optional[Dict[str, Any]]) -> Optional[str]:
    if not payload:
        return None
    return json.dumps(payload, ensure_ascii=False)


def _parse_payload_row(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="ignore")
    if isinstance(raw, str):
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def notification_add(
    user_id: int,
    kind: str,
    title: str,
    detail: str = "",
    payload: Optional[Dict[str, Any]] = None,
):
    try:
        pj = _payload_json(payload)
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO user_notifications(user_id, kind, title, detail, payload)
            VALUES (%s, %s, %s, %s, CAST(%s AS JSON))
            """,
            (
                int(user_id),
                (kind or "")[:32],
                (title or "")[:300],
                (detail or "")[:600],
                pj if pj is not None else json.dumps({}, ensure_ascii=False),
            ),
        )
        cur.close()
        conn.close()
    except Exception as e:
        print(f"⚠️  [DB] 通知写入失败: {str(e)[:100]}")


def notification_list(user_id: int, limit: int = 50, offset: int = 0) -> List[dict]:
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT id, user_id, kind, title, detail, payload, is_read, created_at
        FROM user_notifications
        WHERE user_id=%s
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (int(user_id), int(limit), int(offset)),
    )
    rows = cur.fetchall() or []
    cur.close()
    conn.close()
    for r in rows:
        r["payload"] = _parse_payload_row(r.get("payload"))
        r["is_read"] = bool(r.get("is_read"))
        r["created_at"] = str(r.get("created_at") or "")
    return rows


def notification_unread_count(user_id: int) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(1) FROM user_notifications WHERE user_id=%s AND is_read=0",
        (int(user_id),),
    )
    n = int((cur.fetchone() or [0])[0])
    cur.close()
    conn.close()
    return n


def notification_mark_read(user_id: int, ids: List[int]) -> int:
    if not ids:
        return 0
    ids = [int(x) for x in ids if int(x) > 0]
    if not ids:
        return 0
    conn = get_conn()
    cur = conn.cursor()
    ph = ",".join(["%s"] * len(ids))
    cur.execute(
        f"UPDATE user_notifications SET is_read=1 WHERE user_id=%s AND id IN ({ph})",
        tuple([int(user_id)] + ids),
    )
    n = cur.rowcount
    cur.close()
    conn.close()
    return int(n)


def notification_mark_all_read(user_id: int) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE user_notifications SET is_read=1 WHERE user_id=%s AND is_read=0",
        (int(user_id),),
    )
    n = cur.rowcount
    cur.close()
    conn.close()
    return int(n)


def user_login(username: str, password: str):
    with DBConnection() as (conn, cur):
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        row = cur.fetchone()
    if not row:
        return None, "用户不存在"
    if row["password"] != hash_password(password):
        return None, "密码错误"
    return row, "登录成功"

def user_create(username: str, password: str, role: str = "user"):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users(username,password,role) VALUES(%s,%s,%s)",
            (username, hash_password(password), role),
        )
        return True, "注册成功"
    except mysql.connector.IntegrityError:
        return False, "用户名已存在"
    finally:
        cur.close(); conn.close()

def user_update_role(uid: int, role: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET role=%s WHERE id=%s", (role, uid))
    cur.close(); conn.close()

def user_get(uid: int):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id,username,password,role,created_at,preferred_genres FROM users WHERE id=%s",
        (uid,),
    )
    row = cur.fetchone()
    cur.close(); conn.close()
    return row

def user_update_password(uid: int, new_password: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET password=%s WHERE id=%s", (hash_password(new_password), uid))
    cur.close(); conn.close()
    notification_add(
        int(uid),
        "password_change",
        "你已成功修改登录密码",
        detail="如非本人操作，请尽快联系管理员。",
    )


def user_update_preferred_genres(uid: int, genres_csv: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET preferred_genres=%s WHERE id=%s",
        ((genres_csv or "")[: 500], uid),
    )
    cur.close(); conn.close()


def user_list():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id,username,role,created_at,review_muted_until,review_mute_reason FROM users ORDER BY id"
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def user_delete(uid: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM user_movie_state WHERE user_id=%s", (uid,))
    cur.execute("DELETE FROM browse_history WHERE user_id=%s", (uid,))
    cur.execute("DELETE FROM recommend_logs WHERE user_id=%s", (uid,))
    cur.execute("DELETE FROM users WHERE id=%s", (uid,))
    ok = cur.rowcount > 0
    cur.close(); conn.close()
    return ok

def fav_add(
    user_id: int,
    movie_name: str,
    genres: str = "",
    source: str = "kg",
    tmdb_id: Optional[int] = None,
):
    conn = get_conn()
    cur = conn.cursor()
    try:
        ms = normalize_movie_source(source)
        g = (genres or "")[:256]
        cur.execute(
            """
            INSERT INTO user_movie_state(user_id, movie_name, movie_source, tmdb_id, genres, is_favorite, fav_at)
            VALUES (%s, %s, %s, %s, %s, 1, NOW())
            ON DUPLICATE KEY UPDATE
              is_favorite=1,
              fav_at=NOW(),
              tmdb_id=COALESCE(VALUES(tmdb_id), user_movie_state.tmdb_id),
              genres=IF(VALUES(genres)<>'' AND (user_movie_state.genres='' OR LENGTH(VALUES(genres))>LENGTH(user_movie_state.genres)), VALUES(genres), user_movie_state.genres)
            """,
            (int(user_id), movie_name, ms, int(tmdb_id) if tmdb_id is not None else None, g),
        )
        notification_add(
            int(user_id),
            "favorite_add",
            f"收藏了影片《{movie_name}》",
            payload={"movie_name": movie_name, "movie_source": ms},
        )
        return True
    finally:
        cur.close(); conn.close()

def fav_remove(user_id: int, movie_name: str):
    conn = get_conn()
    cur = conn.cursor()
    # 兼容旧调用：未传 movie_source 时，对该用户该片名的所有来源一并取消收藏
    cur.execute(
        """
        UPDATE user_movie_state
        SET is_favorite=0, fav_at=NULL
        WHERE user_id=%s AND movie_name=%s AND is_favorite=1
        """,
        (int(user_id), movie_name),
    )
    ok = cur.rowcount > 0
    if ok:
        cur.execute(
            "DELETE FROM user_movie_state WHERE user_id=%s AND movie_name=%s AND is_favorite=0 AND is_watched=0 AND vote='' AND blocked=0 AND note=''",
            (int(user_id), movie_name),
        )
    cur.close(); conn.close()
    return ok

def fav_list(user_id: int):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT id, user_id, movie_name, movie_source, tmdb_id, genres,
               COALESCE(fav_at, updated_at, created_at) AS added_at
        FROM user_movie_state
        WHERE user_id=%s AND is_favorite=1
        ORDER BY fav_at DESC, id DESC
        """,
        (int(user_id),),
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def fav_list_all(username: Optional[str] = None):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    extra_sql = ""
    params: tuple = ()
    u = (username or "").strip()
    if u:
        extra_sql = " AND u.username LIKE %s"
        params = (f"%{u}%",)
    cur.execute(
        f"""
        SELECT s.id, s.user_id, u.username, s.movie_name, s.movie_source, s.tmdb_id, s.genres,
               COALESCE(s.fav_at, s.updated_at, s.created_at) AS added_at
        FROM user_movie_state s
        JOIN users u ON s.user_id = u.id
        WHERE s.is_favorite=1{extra_sql}
        ORDER BY s.fav_at DESC, s.id DESC
        """,
        params,
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def fav_delete_admin(fav_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, movie_name, movie_source FROM user_movie_state WHERE id=%s LIMIT 1", (int(fav_id),))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        return False
    user_id = int(row[0]) if not isinstance(row, dict) else int(row.get("user_id") or 0)
    movie_name = row[1] if not isinstance(row, dict) else (row.get("movie_name") or "")
    movie_source = row[2] if not isinstance(row, dict) else (row.get("movie_source") or "kg")
    cur.execute(
        "UPDATE user_movie_state SET is_favorite=0, fav_at=NULL WHERE id=%s AND is_favorite=1",
        (int(fav_id),),
    )
    ok = cur.rowcount > 0
    if ok:
        _ums_cleanup_if_empty(cur, user_id, movie_name, movie_source)
    cur.close(); conn.close()
    return ok

def fav_list_by_user_admin(user_id: int):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT s.id, s.user_id, u.username, s.movie_name, s.movie_source, s.tmdb_id, s.genres,
               COALESCE(s.fav_at, s.updated_at, s.created_at) AS added_at
        FROM user_movie_state s
        JOIN users u ON s.user_id = u.id
        WHERE s.user_id=%s AND s.is_favorite=1
        ORDER BY s.fav_at DESC, s.id DESC
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def watched_add(
    user_id: int,
    movie_name: str,
    genres: str = "",
    movie_source: str = "kg",
    tmdb_id: Optional[int] = None,
):
    conn = get_conn()
    cur = conn.cursor()
    ms = normalize_movie_source(movie_source)
    cur.execute(
        """
        INSERT INTO user_movie_state(user_id, movie_name, movie_source, tmdb_id, genres, is_watched, watched_at)
        VALUES (%s, %s, %s, %s, %s, 1, NOW())
        ON DUPLICATE KEY UPDATE
          is_watched=1,
          watched_at=NOW(),
          tmdb_id=COALESCE(VALUES(tmdb_id), user_movie_state.tmdb_id),
          genres=IF(VALUES(genres)<>'' AND (user_movie_state.genres='' OR LENGTH(VALUES(genres))>LENGTH(user_movie_state.genres)), VALUES(genres), user_movie_state.genres)
        """,
        (int(user_id), movie_name, ms, int(tmdb_id) if tmdb_id is not None else None, genres or ""),
    )
    inserted = cur.rowcount in (1, 2)
    cur.close()
    conn.close()
    if inserted:
        notification_add(
            int(user_id),
            "watched_add",
            f"标记已看过《{movie_name}》",
            payload={"movie_name": movie_name},
        )
    return True


def watched_remove(user_id: int, movie_name: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE user_movie_state
        SET is_watched=0, watched_at=NULL
        WHERE user_id=%s AND movie_name=%s AND is_watched=1
        """,
        (int(user_id), movie_name),
    )
    ok = cur.rowcount > 0
    if ok:
        cur.execute(
            "DELETE FROM user_movie_state WHERE user_id=%s AND movie_name=%s AND is_favorite=0 AND is_watched=0 AND vote='' AND blocked=0 AND note=''",
            (int(user_id), movie_name),
        )
    cur.close()
    conn.close()
    return ok


def watched_list(user_id: int, limit: int = 200):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT id, user_id, movie_name, movie_source, tmdb_id, genres,
               COALESCE(watched_at, updated_at, created_at) AS watched_at
        FROM user_movie_state
        WHERE user_id=%s AND is_watched=1
        ORDER BY watched_at DESC, id DESC
        LIMIT %s
        """,
        (user_id, limit),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def history_add(user_id: int, movie_name: str, genres: str = ""):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("LOCK TABLES browse_history WRITE")
        cur.execute(
            "SELECT id, view_count FROM browse_history WHERE user_id=%s AND movie_name=%s",
            (int(user_id), movie_name),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE browse_history SET genres=%s, view_count=view_count+1, viewed_at=NOW() WHERE user_id=%s AND movie_name=%s",
                (genres, int(user_id), movie_name),
            )
        else:
            new_seq = _alloc_next_seq(cur, "browse_history")
            cur.execute(
                """
                INSERT INTO browse_history(user_id, movie_name, genres, view_count, viewed_at, seq)
                VALUES (%s, %s, %s, 1, NOW(), %s)
                """,
                (int(user_id), movie_name, genres, int(new_seq)),
            )
    finally:
        try:
            cur.execute("UNLOCK TABLES")
        except Exception:
            pass
        cur.close(); conn.close()

def history_list(user_id: int, limit: int = 50):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT * FROM browse_history
        WHERE user_id=%s
        ORDER BY viewed_at DESC
        LIMIT %s
    """, (user_id, limit))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def history_get_movies_with_count(user_id: int, limit: int = 20):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT movie_name, genres, SUM(view_count) AS view_count
        FROM browse_history
        WHERE user_id=%s
        GROUP BY movie_name, genres
        ORDER BY view_count DESC
        LIMIT %s
    """, (user_id, limit))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def history_recent_genres(user_id: int, limit: int = 10):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT genres, SUM(view_count) as weight
        FROM browse_history
        WHERE user_id=%s AND genres != ''
        GROUP BY genres
        ORDER BY weight DESC
        LIMIT %s
    """, (user_id, limit))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def history_remove(user_id: int, movie_name: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM browse_history WHERE user_id=%s AND movie_name=%s",
        (user_id, movie_name),
    )
    ok = cur.rowcount > 0
    cur.close(); conn.close()
    return ok


def history_list_admin(limit: int = 200, filter_user_id: Optional[int] = None):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    if filter_user_id:
        cur.execute(
            """
            SELECT h.*, u.username
            FROM browse_history h
            JOIN users u ON h.user_id = u.id
            WHERE h.user_id=%s
            ORDER BY h.seq DESC, h.viewed_at DESC
            LIMIT %s
            """,
            (filter_user_id, limit),
        )
    else:
        cur.execute(
            """
            SELECT h.*, u.username
            FROM browse_history h
            JOIN users u ON h.user_id = u.id
            ORDER BY h.seq DESC, h.viewed_at DESC
            LIMIT %s
            """,
            (limit,),
        )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def history_delete_admin(record_id: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("LOCK TABLES browse_history WRITE")
        cur.execute("SELECT seq FROM browse_history WHERE id=%s", (int(record_id),))
        row = cur.fetchone()
        seq = None
        if row:
            seq = int(row[0]) if not isinstance(row, dict) else int(row.get("seq") or 0)
        cur.execute("DELETE FROM browse_history WHERE id=%s", (int(record_id),))
        ok = cur.rowcount > 0
        if ok and seq:
            cur.execute("UPDATE browse_history SET seq=seq-1 WHERE seq>%s", (int(seq),))
        return ok
    finally:
        try:
            cur.execute("UNLOCK TABLES")
        except Exception:
            pass
        cur.close(); conn.close()

def log_add(
    user_id: int,
    user_input: str,
    kg_movies: list,
    rag_movies: list,
    final_movies: Optional[list] = None,
    recommend_text: str = "",
    elapsed_ms: int = 0,
    inference_meta: Optional[Dict[str, Any]] = None,
):
    conn = get_conn()
    cur = conn.cursor()
    inf_json = None
    if inference_meta is not None:
        try:
            inf_json = json.dumps(inference_meta, ensure_ascii=False)
            if len(inf_json) > 1_500_000:
                inference_meta = {"_truncated": True, "pipeline": (inference_meta or {}).get("pipeline", [])[:20]}
                inf_json = json.dumps(inference_meta, ensure_ascii=False)
        except (TypeError, ValueError):
            inf_json = None
    cur.execute(
        "INSERT INTO recommend_logs(user_id,user_input,kg_movies,rag_movies,final_movies,recommend_text,elapsed_ms,inference_meta) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            user_id,
            user_input,
            json.dumps(kg_movies, ensure_ascii=False),
            json.dumps(rag_movies, ensure_ascii=False),
            json.dumps(final_movies or [], ensure_ascii=False),
            (recommend_text or "")[:4000],
            int(elapsed_ms or 0),
            inf_json,
        ),
    )
    cur.close(); conn.close()

def log_list(user_id: int, limit: int = 20):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM recommend_logs WHERE user_id=%s ORDER BY created_at DESC LIMIT %s", (user_id, limit))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def rec_log_list(limit: int = 100):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT r.*, u.username
        FROM recommend_logs r
        JOIN users u ON r.user_id = u.id
        ORDER BY r.created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def rec_log_delete(log_id: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM recommend_logs WHERE id=%s", (int(log_id),))
    ok = cur.rowcount > 0
    cur.close(); conn.close()
    return ok

def model_log_list(limit: int = 100):
    return rec_log_list(limit)

def model_log_add(user_id: int, user_input: str, kg_movies: list, rag_movies: list):
    return log_add(user_id, user_input, kg_movies, rag_movies)

def rec_log_add(
    user_id: int,
    user_input: str,
    kg_movies: list,
    rag_movies: list,
    final_movies: Optional[list] = None,
    recommend_text: str = "",
    elapsed_ms: int = 0,
    inference_meta: Optional[Dict[str, Any]] = None,
):
    return log_add(
        user_id,
        user_input,
        kg_movies,
        rag_movies,
        final_movies=final_movies,
        recommend_text=recommend_text,
        elapsed_ms=elapsed_ms,
        inference_meta=inference_meta,
    )


def recommend_log_latency_stats() -> dict:
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT COUNT(*) AS total, COUNT(DISTINCT user_id) AS users, AVG(elapsed_ms) AS avg_ms FROM recommend_logs"
    )
    row = cur.fetchone() or {}
    cur.close(); conn.close()
    return row


# ==========================
# User feedback (like/dislike/block/note)
# ==========================

def feedback_list(
    user_id: int,
    vote: Optional[str] = None,
    blocked: Optional[bool] = None,
    limit: int = 200,
):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    q = """
    SELECT id, user_id, movie_name, movie_source, tmdb_id, vote, blocked, note,
           COALESCE(updated_at, created_at) AS updated_at
    FROM user_movie_state
    WHERE user_id=%s
    """
    ps = [int(user_id)]
    if vote is not None:
        q += " AND vote=%s"
        ps.append((vote or "")[:16])
    if blocked is not None:
        q += " AND blocked=%s"
        ps.append(1 if blocked else 0)
    q += " ORDER BY updated_at DESC, id DESC LIMIT %s"
    ps.append(int(limit))
    cur.execute(q, tuple(ps))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def feedback_get(user_id: int, movie_name: str, movie_source: Optional[str] = None):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    if movie_source:
        ms = normalize_movie_source(movie_source)
        cur.execute(
            """
            SELECT id, user_id, movie_name, movie_source, tmdb_id, vote, blocked, note,
                   COALESCE(updated_at, created_at) AS updated_at
            FROM user_movie_state
            WHERE user_id=%s AND movie_name=%s AND movie_source=%s
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (int(user_id), movie_name, ms),
        )
    else:
        cur.execute(
            """
            SELECT id, user_id, movie_name, movie_source, tmdb_id, vote, blocked, note,
                   COALESCE(updated_at, created_at) AS updated_at
            FROM user_movie_state
            WHERE user_id=%s AND movie_name=%s
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (int(user_id), movie_name),
        )
    row = cur.fetchone()
    cur.close(); conn.close()
    return row


def feedback_upsert(
    user_id: int,
    movie_name: str,
    movie_source: str = "kg",
    tmdb_id: Optional[int] = None,
    vote: object = FEEDBACK_KEEP,
    blocked: object = FEEDBACK_KEEP,
    note: object = FEEDBACK_KEEP,
):
    """
    Upsert 一条反馈记录。
    - vote: 'like'/'dislike'/None(清空)；若不想更新 vote，请传入 KEEP
    - blocked: True/False；若不想更新 blocked，请传入 KEEP
    - note: str/None(清空为'')；若不想更新 note，请传入 KEEP
    """
    row0 = feedback_get(user_id, movie_name, movie_source=movie_source)
    old_vote = (row0 or {}).get("vote")
    update_vote = vote is not FEEDBACK_KEEP
    update_blocked = blocked is not FEEDBACK_KEEP
    update_note = note is not FEEDBACK_KEEP

    # vote 允许 like/dislike/None(清空)
    v = vote if vote in ("like", "dislike") else None
    b = 1 if blocked is True else 0 if blocked is False else 0
    if update_note:
        n = "" if note is None else (str(note) or "")[:500]
    else:
        n = ""
    ms = normalize_movie_source(movie_source)
    conn = get_conn()
    cur = conn.cursor()
    # 先确保存在（默认 movie_source='kg'）
    cur.execute(
        """
        INSERT INTO user_movie_state(user_id, movie_name, movie_source, tmdb_id, vote, blocked, note)
        VALUES(%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE updated_at=updated_at
        """,
        (
            int(user_id),
            movie_name,
            ms,
            int(tmdb_id) if tmdb_id is not None else None,
            v or "",
            int(b),
            n,
        ),
    )
    sets = []
    ps = []
    if update_vote:
        sets.append("vote=%s")
        ps.append(v or "")
    if update_blocked:
        sets.append("blocked=%s")
        ps.append(int(b))
    if update_note:
        sets.append("note=%s")
        ps.append(n)
    if sets:
        cur.execute(
            "UPDATE user_movie_state SET "
            + ", ".join(sets)
            + ", tmdb_id=COALESCE(%s, tmdb_id), updated_at=CURRENT_TIMESTAMP WHERE user_id=%s AND movie_name=%s AND movie_source=%s",
            tuple(ps + [int(tmdb_id) if tmdb_id is not None else None, int(user_id), movie_name, ms]),
        )
        _ums_cleanup_if_empty(cur, int(user_id), movie_name, ms)
    cur.close(); conn.close()
    if update_vote and v == "like" and old_vote != "like":
        notification_add(
            int(user_id),
            "feedback_like",
            f"喜欢了影片《{movie_name}》",
            payload={"movie_name": movie_name},
        )


def feedback_delete(user_id: int, movie_name: str, movie_source: Optional[str] = None) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    if movie_source:
        ms = normalize_movie_source(movie_source)
        cur.execute(
            "UPDATE user_movie_state SET vote='', blocked=0, note='' WHERE user_id=%s AND movie_name=%s AND movie_source=%s",
            (int(user_id), movie_name, ms),
        )
        ok = cur.rowcount > 0
        if ok:
            _ums_cleanup_if_empty(cur, int(user_id), movie_name, ms)
    else:
        # 兼容旧调用：未传 movie_source 时，对该用户该片名的所有来源一并清空反馈
        cur.execute(
            "UPDATE user_movie_state SET vote='', blocked=0, note='' WHERE user_id=%s AND movie_name=%s",
            (int(user_id), movie_name),
        )
        ok = cur.rowcount > 0
        if ok:
            cur.execute(
                "DELETE FROM user_movie_state WHERE user_id=%s AND movie_name=%s AND is_favorite=0 AND is_watched=0 AND vote='' AND blocked=0 AND note=''",
                (int(user_id), movie_name),
            )
    cur.close(); conn.close()
    return ok


# ==========================
# Playlists
# ==========================

def playlist_list(user_id: int):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT * FROM playlists WHERE user_id=%s ORDER BY created_at DESC",
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def playlist_create(user_id: int, name: str, description: str = "") -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO playlists(user_id,name,description) VALUES(%s,%s,%s)",
        (user_id, (name or "")[:64], (description or "")[:200]),
    )
    pid = int(cur.lastrowid)
    cur.close(); conn.close()
    nm = (name or "")[:64]
    notification_add(
        int(user_id),
        "playlist_create",
        f"新建了片单「{nm}」",
        payload={"playlist_id": pid, "name": nm},
    )
    return pid


def playlist_update(user_id: int, playlist_id: int, name: Optional[str], description: Optional[str]) -> bool:
    old = None
    try:
        with DBConnection() as (conn, cur):
            cur.execute(
                "SELECT name, description FROM playlists WHERE id=%s AND user_id=%s",
                (int(playlist_id), int(user_id)),
            )
            old = cur.fetchone()
    except Exception:
        old = None
    sets = []
    ps = []
    if name is not None:
        sets.append("name=%s")
        ps.append((name or "")[:64])
    if description is not None:
        sets.append("description=%s")
        ps.append((description or "")[:200])
    if not sets:
        return True
    conn = get_conn()
    cur = conn.cursor()
    q = "UPDATE playlists SET " + ", ".join(sets) + " WHERE id=%s AND user_id=%s"
    ps.extend([int(playlist_id), int(user_id)])
    cur.execute(q, tuple(ps))
    changed = cur.rowcount > 0
    cur.close(); conn.close()
    if changed and old:
        old_name = (old.get("name") or "") if isinstance(old, dict) else ""
        new_name = (name or old_name) if name is not None else old_name
        old_name = (old_name or "")[:64]
        new_name = (new_name or "")[:64]
        if name is not None and new_name and new_name != old_name:
            notification_add(
                int(user_id),
                "playlist_rename",
                f"将片单「{old_name}」重命名为「{new_name}」",
                payload={"playlist_id": int(playlist_id), "old_name": old_name, "new_name": new_name},
            )
        else:
            notification_add(
                int(user_id),
                "playlist_update",
                f"更新了片单「{new_name or old_name}」",
                payload={"playlist_id": int(playlist_id), "name": new_name or old_name},
            )
    return True


def playlist_delete(user_id: int, playlist_id: int) -> bool:
    pname = ""
    try:
        with DBConnection() as (conn, cur):
            cur.execute(
                "SELECT name FROM playlists WHERE id=%s AND user_id=%s",
                (int(playlist_id), int(user_id)),
            )
            row = cur.fetchone() or {}
            pname = (row.get("name") or "")[:64] if isinstance(row, dict) else ""
    except Exception:
        pname = ""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM playlist_items WHERE playlist_id=%s", (playlist_id,))
    cur.execute("DELETE FROM playlists WHERE id=%s AND user_id=%s", (playlist_id, user_id))
    ok = cur.rowcount > 0
    cur.close(); conn.close()
    if ok:
        notification_add(
            int(user_id),
            "playlist_delete",
            f"删除了片单「{pname or playlist_id}」",
            payload={"playlist_id": int(playlist_id), "name": pname},
        )
    return ok


def playlist_items_list(user_id: int, playlist_id: int):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT i.*
        FROM playlist_items i
        JOIN playlists p ON p.id=i.playlist_id
        WHERE p.user_id=%s AND p.id=%s
        ORDER BY i.added_at DESC
        """,
        (user_id, playlist_id),
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def playlist_item_add(
    user_id: int,
    playlist_id: int,
    movie_name: str,
    movie_source: str = "",
    tmdb_id: Optional[int] = None,
    genres: str = "",
    poster_url: str = "",
    genres_str: str = "",
    score_str: str = "",
    short_review: str = "",
    *,
    skip_item_notification: bool = False,
) -> tuple[bool, bool]:
    """Returns (allowed, inserted_new_row)."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id, name FROM playlists WHERE id=%s AND user_id=%s",
        (playlist_id, user_id),
    )
    prow = cur.fetchone()
    if not prow:
        cur.close(); conn.close()
        return (False, False)
    plist_name = (prow.get("name") or "")[:64]
    try:
        cur.execute(
            """
            INSERT INTO playlist_items(playlist_id, movie_name, movie_source, tmdb_id, genres, poster_url, genres_str, score_str, short_review)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                playlist_id,
                (movie_name or "")[:256],
                (movie_source or "")[:32],
                int(tmdb_id) if tmdb_id is not None else None,
                (genres or "")[:256],
                (poster_url or "")[:512],
                (genres_str or "")[:128],
                (score_str or "")[:32],
                (short_review or "")[:600],
            ),
        )
        inserted = True
    except mysql.connector.IntegrityError:
        inserted = False
    cur.close(); conn.close()
    if inserted and not skip_item_notification:
        mn = (movie_name or "")[:256]
        notification_add(
            int(user_id),
            "playlist_add_item",
            f"将《{mn}》加入片单「{plist_name}」",
            payload={
                "movie_name": mn,
                "playlist_id": int(playlist_id),
                "playlist_name": plist_name,
                "movie_source": (movie_source or "")[:32],
            },
        )
    return (True, inserted)


def playlist_item_remove(user_id: int, playlist_id: int, movie_name: str) -> bool:
    pname = ""
    try:
        with DBConnection() as (conn, cur):
            cur.execute(
                "SELECT name FROM playlists WHERE id=%s AND user_id=%s",
                (int(playlist_id), int(user_id)),
            )
            row = cur.fetchone() or {}
            pname = (row.get("name") or "")[:64] if isinstance(row, dict) else ""
    except Exception:
        pname = ""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        DELETE i FROM playlist_items i
        JOIN playlists p ON p.id=i.playlist_id
        WHERE p.user_id=%s AND p.id=%s AND i.movie_name=%s
        """,
        (user_id, playlist_id, movie_name),
    )
    ok = cur.rowcount > 0
    cur.close(); conn.close()
    if ok:
        mn = (movie_name or "")[:256]
        notification_add(
            int(user_id),
            "playlist_remove_item",
            f"将《{mn}》从片单「{pname}」移除",
            payload={"movie_name": mn, "playlist_id": int(playlist_id), "playlist_name": pname},
        )
    return ok


def playlist_bulk_add_from_movies(user_id: int, playlist_id: int, movies: list[dict]) -> dict:
    added = 0
    skipped = 0
    for m in movies or []:
        nm = (m.get("name") or "").strip()
        if not nm:
            continue
        ok, inserted = playlist_item_add(
            user_id,
            playlist_id,
            nm,
            movie_source=(m.get("source") or "")[:32],
            tmdb_id=m.get("tmdb_id"),
            genres=(m.get("genres") or "")[:256],
            poster_url=(m.get("poster_url") or "")[:512],
            genres_str=(m.get("genres_str") or "")[:128],
            score_str=(m.get("score_str") or "")[:32],
            short_review=(m.get("short_review") or "")[:600],
            skip_item_notification=True,
        )
        if not ok:
            skipped += 1
        elif inserted:
            added += 1
        else:
            skipped += 1
    if added > 0:
        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT name FROM playlists WHERE id=%s AND user_id=%s",
            (int(playlist_id), int(user_id)),
        )
        prow = cur.fetchone()
        cur.close(); conn.close()
        pname = (prow or {}).get("name") or ""
        notification_add(
            int(user_id),
            "playlist_bulk_add",
            f"批量将 {added} 部影片加入片单「{pname}」",
            payload={"playlist_id": int(playlist_id), "playlist_name": pname, "count": added},
        )
    return {"added": added, "skipped": skipped}


# ==========================
# Reviews community
# ==========================

def user_review_mute_info(user_id: int) -> dict:
    with DBConnection() as (conn, cur):
        cur.execute(
            "SELECT review_muted_until, review_mute_reason FROM users WHERE id=%s",
            (user_id,),
        )
        row = cur.fetchone() or {}
    return row


def review_upsert(
    user_id: int,
    movie_name: str,
    movie_source: str = "",
    rating: Optional[float] = None,
    content: str = "",
) -> int:
    movie_name = (movie_name or "").strip()[:256]
    movie_source = (movie_source or "").strip()[:32]
    content = (content or "").strip()[:800]
    if rating is not None:
        try:
            rating = float(rating)
        except Exception:
            rating = None
    if rating is not None and (rating < 1 or rating > 10):
        rating = None
    if rating is not None:
        # 统一保留 1 位小数，适配 DECIMAL(3,1)
        rating = round(float(rating), 1)

    has_rating = rating is not None
    has_content = bool(content)
    if not has_rating and not has_content:
        # 不写新行、不删已有行：保持数据库原状
        prev = review_get_for_user_movie(int(user_id), movie_name)
        return int(prev["id"]) if prev and prev.get("id") else 0

    existed = review_get_for_user_movie(int(user_id), movie_name) is not None

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO reviews(user_id, movie_name, movie_source, rating, content)
        VALUES(%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            movie_source=VALUES(movie_source),
            rating=VALUES(rating),
            content=VALUES(content),
            updated_at=CURRENT_TIMESTAMP
        """,
        (user_id, movie_name, movie_source, rating, content),
    )
    rid = int(cur.lastrowid) if cur.lastrowid else 0
    # 若是更新，取 id
    if rid == 0:
        cur.execute("SELECT id FROM reviews WHERE user_id=%s AND movie_name=%s", (user_id, movie_name))
        r = cur.fetchone()
        rid = int(r[0]) if r else 0
    cur.close(); conn.close()
    if rid and has_content:
        if existed:
            notification_add(
                int(user_id),
                "review_update",
                f"更新了影评《{movie_name}》",
                payload={"movie_name": movie_name, "review_id": rid, "movie_source": movie_source},
            )
        else:
            notification_add(
                int(user_id),
                "review_create",
                f"发表了影评《{movie_name}》",
                payload={"movie_name": movie_name, "review_id": rid, "movie_source": movie_source},
            )
    return rid


def review_delete(user_id: int, review_id: int, as_admin: bool = False) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    if as_admin:
        cur.execute("SELECT id FROM reviews WHERE id=%s", (review_id,))
    else:
        cur.execute("SELECT id FROM reviews WHERE id=%s AND user_id=%s", (review_id, user_id))
    if not cur.fetchone():
        cur.close(); conn.close()
        return False
    # 删除关联：评论与点赞
    cur.execute("DELETE FROM review_likes WHERE target_type='review' AND target_id=%s", (review_id,))
    cur.execute("SELECT id FROM review_comments WHERE review_id=%s", (review_id,))
    cids = [int(r[0]) for r in (cur.fetchall() or [])]
    if cids:
        cur.execute(
            "DELETE FROM review_likes WHERE target_type='comment' AND target_id IN (%s)"
            % ",".join(["%s"] * len(cids)),
            tuple(cids),
        )
    cur.execute("DELETE FROM review_comments WHERE review_id=%s", (review_id,))
    cur.execute("DELETE FROM reviews WHERE id=%s", (review_id,))
    ok = cur.rowcount > 0
    cur.close(); conn.close()
    return ok


def review_list(sort: str = "comment_count", limit: int = 50, offset: int = 0) -> list[dict]:
    sort = (sort or "").strip()
    order_by = "comment_count DESC, like_count DESC, r.updated_at DESC"
    if sort == "like_count":
        order_by = "like_count DESC, comment_count DESC, r.updated_at DESC"
    elif sort == "recent":
        order_by = "r.updated_at DESC"
    with DBConnection() as (conn, cur):
        cur.execute(
            f"""
            SELECT
              r.id,
              r.user_id,
              u.username,
              r.movie_name,
              r.movie_source,
              r.rating,
              r.content,
              r.created_at,
              r.updated_at,
              (SELECT COUNT(1) FROM review_comments c WHERE c.review_id=r.id) AS comment_count,
              (SELECT COUNT(1) FROM review_likes l WHERE l.target_type='review' AND l.target_id=r.id) AS like_count,
              COALESCE(NULLIF(ums_exact.note, ''), NULLIF(ums_any.note_any, ''), '') AS feedback_note
            FROM reviews r
            JOIN users u ON u.id=r.user_id
            LEFT JOIN user_movie_state ums_exact
              ON ums_exact.user_id=r.user_id
             AND ums_exact.movie_name=r.movie_name
             AND ums_exact.movie_source=COALESCE(NULLIF(r.movie_source, ''), 'kg')
            LEFT JOIN (
              SELECT user_id, movie_name, MAX(NULLIF(note, '')) AS note_any
              FROM user_movie_state
              GROUP BY user_id, movie_name
            ) ums_any
              ON ums_any.user_id=r.user_id AND ums_any.movie_name=r.movie_name
            WHERE TRIM(COALESCE(r.content, '')) <> ''
            ORDER BY {order_by}
            LIMIT %s OFFSET %s
            """,
            (int(limit), int(offset)),
        )
        rows = cur.fetchall() or []
    return rows


def review_get(review_id: int) -> Optional[dict]:
    with DBConnection() as (conn, cur):
        cur.execute(
            """
            SELECT
              r.id,
              r.user_id,
              u.username,
              r.movie_name,
              r.movie_source,
              r.rating,
              r.content,
              r.created_at,
              r.updated_at,
              COALESCE(NULLIF(ums_exact.note, ''), NULLIF(ums_any.note_any, ''), '') AS feedback_note
            FROM reviews r
            JOIN users u ON u.id=r.user_id
            LEFT JOIN user_movie_state ums_exact
              ON ums_exact.user_id=r.user_id
             AND ums_exact.movie_name=r.movie_name
             AND ums_exact.movie_source=COALESCE(NULLIF(r.movie_source, ''), 'kg')
            LEFT JOIN (
              SELECT user_id, movie_name, MAX(NULLIF(note, '')) AS note_any
              FROM user_movie_state
              GROUP BY user_id, movie_name
            ) ums_any
              ON ums_any.user_id=r.user_id AND ums_any.movie_name=r.movie_name
            WHERE r.id=%s
            """,
            (review_id,),
        )
        row = cur.fetchone()
    return row


def review_get_for_user_movie(user_id: int, movie_name: str) -> Optional[dict]:
    """当前用户对某片的影评（若有），用于短评同步时保留已有评分等字段。"""
    movie_name = (movie_name or "").strip()[:256]
    with DBConnection() as (conn, cur):
        cur.execute(
            """
            SELECT id, user_id, movie_name, movie_source, rating, content
            FROM reviews
            WHERE user_id=%s AND movie_name=%s
            LIMIT 1
            """,
            (int(user_id), movie_name),
        )
        row = cur.fetchone()
    return row


def _notify_new_review_comment(
    actor_id: int,
    review_id: int,
    parent_id: Optional[int],
    comment_id: int,
    content: str,
):
    rev = review_get(int(review_id))
    if not rev:
        return
    movie = (rev.get("movie_name") or "").strip()
    actor = user_username(int(actor_id))
    body = (content or "").strip()
    snippet = body[:120] + ("…" if len(body) > 120 else "")
    target_uid: Optional[int] = None
    kind = "review_comment"
    if parent_id:
        with DBConnection() as (conn, cur):
            cur.execute(
                "SELECT user_id FROM review_comments WHERE id=%s LIMIT 1",
                (int(parent_id),),
            )
            pr = cur.fetchone()
        if pr:
            target_uid = int(pr["user_id"])
            kind = "review_reply"
    else:
        target_uid = int(rev["user_id"])
    if not target_uid or target_uid == int(actor_id):
        return
    title = f"{actor} 回复了你的评论" if kind == "review_reply" else f"{actor} 评论了你的影评"
    notification_add(
        int(target_uid),
        kind,
        title,
        detail=snippet,
        payload={
            "movie_name": movie,
            "review_id": int(review_id),
            "comment_id": int(comment_id),
            "parent_id": int(parent_id) if parent_id else None,
            "from_user": actor,
            "from_user_id": int(actor_id),
        },
    )


def _notify_review_like(actor_id: int, target_type: str, target_id: int):
    target_type = (target_type or "").strip()
    owner_id: Optional[int] = None
    movie_name = ""
    review_id: Optional[int] = None
    if target_type == "review":
        r = review_get(int(target_id))
        if r:
            owner_id = int(r["user_id"])
            movie_name = (r.get("movie_name") or "").strip()
            review_id = int(target_id)
    elif target_type == "comment":
        with DBConnection() as (conn, cur):
            cur.execute(
                """
                SELECT c.user_id, c.review_id, r.movie_name
                FROM review_comments c
                JOIN reviews r ON r.id=c.review_id
                WHERE c.id=%s
                LIMIT 1
                """,
                (int(target_id),),
            )
            row = cur.fetchone()
        if row:
            owner_id = int(row["user_id"])
            movie_name = (row.get("movie_name") or "").strip()
            review_id = int(row["review_id"])
    if not owner_id or owner_id == int(actor_id):
        return
    actor = user_username(int(actor_id))
    title = f"{actor} 赞了你的影评" if target_type == "review" else f"{actor} 赞了你的评论"
    notification_add(
        int(owner_id),
        "review_like",
        title,
        payload={
            "movie_name": movie_name,
            "review_id": int(review_id or 0),
            "target_type": target_type,
            "target_id": int(target_id),
            "from_user": actor,
            "from_user_id": int(actor_id),
        },
    )


def review_comments_list(review_id: int) -> list[dict]:
    with DBConnection() as (conn, cur):
        cur.execute(
            """
            SELECT
              c.id,
              c.review_id,
              c.user_id,
              u.username,
              c.parent_id,
              c.content,
              c.created_at,
              (SELECT COUNT(1) FROM review_likes l WHERE l.target_type='comment' AND l.target_id=c.id) AS like_count
            FROM review_comments c
            JOIN users u ON u.id=c.user_id
            WHERE c.review_id=%s
            ORDER BY c.created_at ASC
            """,
            (review_id,),
        )
        rows = cur.fetchall() or []
    return rows


def review_comment_add(user_id: int, review_id: int, content: str, parent_id: Optional[int] = None) -> int:
    content = (content or "").strip()[:800]
    if not content:
        return 0
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO review_comments(review_id,user_id,parent_id,content) VALUES(%s,%s,%s,%s)",
        (review_id, user_id, parent_id, content),
    )
    cid = int(cur.lastrowid)
    cur.close(); conn.close()
    _notify_new_review_comment(int(user_id), int(review_id), parent_id, cid, content)
    return cid


def review_comment_delete(user_id: int, comment_id: int, as_admin: bool = False) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    if as_admin:
        cur.execute("SELECT id FROM review_comments WHERE id=%s", (comment_id,))
    else:
        cur.execute("SELECT id FROM review_comments WHERE id=%s AND user_id=%s", (comment_id, user_id))
    if not cur.fetchone():
        cur.close(); conn.close()
        return False
    cur.execute("DELETE FROM review_likes WHERE target_type='comment' AND target_id=%s", (comment_id,))
    cur.execute("DELETE FROM review_comments WHERE id=%s", (comment_id,))
    ok = cur.rowcount > 0
    cur.close(); conn.close()
    return ok


def review_like_set(user_id: int, target_type: str, target_id: int) -> bool:
    target_type = (target_type or "").strip()
    if target_type not in ("review", "comment"):
        return False
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO review_likes(target_type,target_id,user_id) VALUES(%s,%s,%s)",
            (target_type, int(target_id), int(user_id)),
        )
        is_new = True
    except mysql.connector.IntegrityError:
        is_new = False
    cur.close(); conn.close()
    if is_new:
        _notify_review_like(int(user_id), target_type, int(target_id))
    return True


def review_like_unset(user_id: int, target_type: str, target_id: int) -> bool:
    target_type = (target_type or "").strip()
    if target_type not in ("review", "comment"):
        return False
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM review_likes WHERE target_type=%s AND target_id=%s AND user_id=%s",
        (target_type, int(target_id), int(user_id)),
    )
    ok = cur.rowcount > 0
    cur.close(); conn.close()
    return ok


def admin_reviews_list(limit: int = 100, offset: int = 0, user_id: Optional[int] = None, movie_name: Optional[str] = None):
    q = """
      SELECT r.*, u.username
      FROM reviews r
      JOIN users u ON u.id=r.user_id
      WHERE 1=1
    """
    ps = []
    if user_id is not None:
        q += " AND r.user_id=%s"
        ps.append(int(user_id))
    if movie_name:
        q += " AND r.movie_name LIKE %s"
        ps.append(f"%{movie_name}%")
    q += " ORDER BY r.updated_at DESC LIMIT %s OFFSET %s"
    ps.extend([int(limit), int(offset)])
    with DBConnection() as (conn, cur):
        cur.execute(q, tuple(ps))
        rows = cur.fetchall() or []
    return rows


def admin_review_comments_list(limit: int = 200, offset: int = 0, user_id: Optional[int] = None, review_id: Optional[int] = None):
    q = """
      SELECT c.*, u.username
      FROM review_comments c
      JOIN users u ON u.id=c.user_id
      WHERE 1=1
    """
    ps = []
    if user_id is not None:
        q += " AND c.user_id=%s"
        ps.append(int(user_id))
    if review_id is not None:
        q += " AND c.review_id=%s"
        ps.append(int(review_id))
    q += " ORDER BY c.created_at DESC LIMIT %s OFFSET %s"
    ps.extend([int(limit), int(offset)])
    with DBConnection() as (conn, cur):
        cur.execute(q, tuple(ps))
        rows = cur.fetchall() or []
    return rows


def admin_user_set_review_mute(user_id: int, muted_until: Optional[str], reason: str = "") -> bool:
    reason = (reason or "")[:200]
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET review_muted_until=%s, review_mute_reason=%s WHERE id=%s",
        (muted_until, reason, int(user_id)),
    )
    changed = cur.rowcount > 0
    cur.close(); conn.close()
    if changed:
        try:
            if muted_until:
                notification_add(
                    int(user_id),
                    "review_mute",
                    "你已被限制影评互动",
                    detail=f"直至 {muted_until}" + (f"。原因：{reason}" if reason else ""),
                    payload={"until": str(muted_until), "reason": reason},
                )
            else:
                notification_add(
                    int(user_id),
                    "review_unmute",
                    "你的影评互动限制已解除",
                    detail="可正常发布影评、评论与回复。",
                )
        except Exception as e:
            print(f"⚠️  [DB] 禁言通知失败: {str(e)[:100]}")
    return True


def admin_user_clear_review_mute(user_id: int) -> bool:
    return admin_user_set_review_mute(int(user_id), None, "")


def overview_counts() -> dict:
    """管理员概览：若部分表为空也应返回 0。"""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) AS c FROM users")
    users = int((cur.fetchone() or {}).get("c") or 0)
    cur.execute("SELECT COUNT(*) AS c FROM user_movie_state WHERE is_favorite=1")
    favorites = int((cur.fetchone() or {}).get("c") or 0)
    cur.execute("SELECT COUNT(*) AS c FROM user_movie_state WHERE is_watched=1")
    watched = int((cur.fetchone() or {}).get("c") or 0)
    cur.execute("SELECT COUNT(*) AS c FROM browse_history")
    browse = int((cur.fetchone() or {}).get("c") or 0)
    cur.execute("SELECT COUNT(*) AS c FROM recommend_logs")
    rec_logs = int((cur.fetchone() or {}).get("c") or 0)
    cur.close(); conn.close()
    return {
        "users": users,
        "favorites": favorites,
        "watched": watched,
        "browse_history": browse,
        "recommend_logs": rec_logs,
    }

def model_log_stats():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT COUNT(*) as total, COUNT(DISTINCT user_id) as users FROM recommend_logs")
    row = cur.fetchone()
    cur.close(); conn.close()
    return row

def get_movie_list(page: int = 1, page_size: int = 16, genre: str = ""):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    offset = (page - 1) * page_size
    if genre:
        cur.execute("SELECT * FROM movies WHERE genres LIKE %s ORDER BY id LIMIT %s OFFSET %s", (f"%{genre}%", page_size, offset))
    else:
        cur.execute("SELECT * FROM movies ORDER BY id LIMIT %s OFFSET %s", (page_size, offset))
    rows = cur.fetchall()
    cur.execute("SELECT COUNT(*) as total FROM movies" + (" WHERE genres LIKE %s" if genre else ""), (f"%{genre}%",) if genre else ())
    total = cur.fetchone()["total"]
    cur.close(); conn.close()
    return rows, total

def get_movie_detail(movie_name: str):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM movies WHERE name=%s OR display=%s LIMIT 1", (movie_name, movie_name))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row

def movie_search(keyword: str, limit: int = 20):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT * FROM movies WHERE name LIKE %s OR display LIKE %s OR description LIKE %s LIMIT %s",
        (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit)
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def movie_get_genres():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT DISTINCT genres FROM movies")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows
