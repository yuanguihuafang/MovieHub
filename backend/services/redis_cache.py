# -*- coding: utf-8 -*-
"""
Redis 缓存工具层。

- 优先使用 Redis（需配置 MOVIEHUB_REDIS_URL）
- 未配置或连接失败时自动降级为内存字典缓存
- 提供 get / set / delete / clear 操作，支持过期时间
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

_redis_client = None
_memory_cache: dict[str, tuple[Any, float]] = {}  # key -> (value, expire_ts)
_initialized = False
_use_redis = False


def _init():
    global _redis_client, _initialized, _use_redis
    if _initialized:
        return
    _initialized = True

    url = (os.getenv("MOVIEHUB_REDIS_URL") or "").strip()
    if not url:
        _use_redis = False
        return

    try:
        import redis
        _redis_client = redis.from_url(url, decode_responses=True)
        _redis_client.ping()
        _use_redis = True
        print(f"✅ [Redis] 已连接")
    except Exception as e:
        _use_redis = False
        print(f"⚠️  [Redis] 连接失败，降级为内存缓存: {str(e)[:80]}")


def get(key: str) -> Optional[Any]:
    """获取缓存值，不存在返回 None"""
    _init()

    if _use_redis:
        try:
            raw = _redis_client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            return None

    # 内存缓存
    item = _memory_cache.get(key)
    if item is None:
        return None
    value, expire_ts = item
    if expire_ts > 0 and time.time() > expire_ts:
        _memory_cache.pop(key, None)
        return None
    return value


def set(key: str, value: Any, ttl: int = 3600):
    """
    设置缓存。
    ttl: 过期时间（秒），默认 3600（1 小时）。0 表示不过期。
    """
    _init()

    if _use_redis:
        try:
            raw = json.dumps(value, ensure_ascii=False)
            if ttl > 0:
                _redis_client.setex(key, ttl, raw)
            else:
                _redis_client.set(key, raw)
        except Exception:
            pass
        return

    # 内存缓存
    expire_ts = time.time() + ttl if ttl > 0 else 0
    _memory_cache[key] = (value, expire_ts)


def delete(key: str):
    """删除指定缓存"""
    _init()

    if _use_redis:
        try:
            _redis_client.delete(key)
        except Exception:
            pass
        return

    _memory_cache.pop(key, None)


def clear(prefix: str = ""):
    """清空缓存。prefix 非空时只清匹配前缀的 key"""
    _init()

    if _use_redis:
        try:
            if prefix:
                keys = _redis_client.keys(f"{prefix}*")
                if keys:
                    _redis_client.delete(*keys)
            else:
                _redis_client.flushdb()
        except Exception:
            pass
        return

    if prefix:
        to_del = [k for k in _memory_cache if k.startswith(prefix)]
        for k in to_del:
            _memory_cache.pop(k, None)
    else:
        _memory_cache.clear()


def is_redis() -> bool:
    """当前是否使用 Redis（而非内存降级）"""
    _init()
    return _use_redis


def stats() -> dict:
    """返回缓存状态信息"""
    _init()
    if _use_redis:
        try:
            info = _redis_client.info("memory")
            return {
                "backend": "redis",
                "url": os.getenv("MOVIEHUB_REDIS_URL", ""),
                "used_memory": info.get("used_memory_human", "?"),
            }
        except Exception:
            return {"backend": "redis", "error": "无法获取信息"}
    return {
        "backend": "memory",
        "keys": len(_memory_cache),
    }
