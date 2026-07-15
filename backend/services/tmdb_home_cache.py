# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional


def _backend_dir() -> Path:
    # 当前文件在 backend/services 下
    return Path(__file__).resolve().parents[1]


def cache_path() -> Path:
    # 外层 backend/data 下落盘
    return (_backend_dir() / "data" / "tmdb_home_cache.json").resolve()


def read_cache() -> Optional[dict[str, Any]]:
    p = cache_path()
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None


def write_cache(payload: dict[str, Any]) -> bool:
    p = cache_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
        return True
    except Exception:
        return False


def is_fresh(updated_at: Optional[int], ttl_seconds: int) -> bool:
    if not updated_at:
        return False
    try:
        return (int(time.time()) - int(updated_at)) <= max(1, int(ttl_seconds))
    except Exception:
        return False


def min_refresh_seconds() -> int:
    """
    TMDB「正在上映 / 即将上映」最少间隔多久才再次请求外网更新（秒）。
    默认 43200（12 小时）；可用 TMDB_HOME_MIN_REFRESH_SEC 覆盖。
    """
    raw = (os.getenv("TMDB_HOME_MIN_REFRESH_SEC") or "43200").strip()
    try:
        return max(300, int(raw))
    except ValueError:
        return 43200

