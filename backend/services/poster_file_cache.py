# -*- coding: utf-8 -*-
"""
将远程海报拉取到本地磁盘，通过 /api/poster-cache/{sha256}.{ext} 同源下发，
避免浏览器直连豆瓣/TMDB CDN 时的防盗链导致裂图，并持久复用。

默认目录：backend/data/poster_cache/
自定义：环境变量 POSTER_CACHE_DIR（绝对路径或相对 backend）。
关闭落盘：POSTER_FILE_CACHE=0
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

_FILENAME_RE = re.compile(r"^[a-f0-9]{64}\.(jpe?g|png|webp)$", re.I)

_MAGIC_JPG = b"\xff\xd8\xff"
_MAGIC_PNG = b"\x89PNG\r\n\x1a\n"
_MAGIC_RIFF = b"RIFF"
_MAGIC_WEBP = b"WEBP"


def _looks_like_image(path: Path) -> bool:
    """简单校验：避免把防盗链返回的 HTML/JS 当成 .jpg 缓存导致前端裂图。"""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
        if head.startswith(_MAGIC_JPG):
            return True
        if head.startswith(_MAGIC_PNG):
            return True
        # WEBP: RIFF....WEBP
        if head.startswith(_MAGIC_RIFF) and _MAGIC_WEBP in head:
            return True
        return False
    except Exception:
        return False


def _backend_dir() -> Path:
    # 当前文件在 backend/services 下
    return Path(__file__).resolve().parents[1]


def _outer_backend_dir() -> Path:
    """
    解析「真正的」backend 目录。
    若误出现 .../X/X/backend（连续重复路径段），折叠为 .../X/backend，
    避免海报缓存落到嵌套副本目录（与仓库根文件夹名无关）。
    """
    backend = _backend_dir().resolve()
    parts = backend.parts
    if (
        len(parts) >= 3
        and parts[-1].lower() == "backend"
        and parts[-2] == parts[-3]
    ):
        collapsed = parts[:-3] + parts[-2:]
        try:
            return Path(*collapsed)
        except (TypeError, ValueError):
            pass
    return backend


def _cache_root() -> Path:
    """
    默认：外层 backend/data/poster_cache。
    可用环境变量 POSTER_CACHE_DIR 指定绝对路径，或相对「backend 目录」的相对路径。
    """
    override = os.getenv("POSTER_CACHE_DIR", "").strip()
    if override:
        p = Path(override).expanduser()
        if not p.is_absolute():
            p = (_outer_backend_dir() / p).resolve()
        return p.resolve()
    return (_outer_backend_dir() / "data" / "poster_cache").resolve()


def poster_cache_root() -> Path:
    return _cache_root()


def poster_file_cache_enabled() -> bool:
    return os.getenv("POSTER_FILE_CACHE", "1").strip().lower() not in ("0", "false", "no", "off")


def poster_cache_eager_download() -> bool:
    """
    是否在接口返回前同步落盘下载海报。
    默认关闭（0），避免首页/片库列表请求被外网图片下载阻塞。
    """
    return os.getenv("POSTER_CACHE_EAGER_DOWNLOAD", "0").strip().lower() in ("1", "true", "yes", "on")


def _title_key(title: str) -> str:
    return hashlib.sha256(title.strip().encode("utf-8")).hexdigest()


def _guess_ext(url: str, content_type: str) -> str:
    ct = (content_type or "").lower()
    if "webp" in ct:
        return ".webp"
    if "png" in ct:
        return ".png"
    path = urlparse(url).path.lower()
    if path.endswith(".webp"):
        return ".webp"
    if path.endswith(".png"):
        return ".png"
    return ".jpg"


def _image_fetch_headers(url: str) -> dict[str, str]:
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    host = urlparse(url).netloc.lower()
    if "douban" in host:
        ref = "https://movie.douban.com/"
    elif "tmdb" in host or "themoviedb" in host:
        ref = "https://www.themoviedb.org/"
    else:
        ref = "https://movie.douban.com/"
    return {
        "User-Agent": ua,
        "Referer": ref,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }


def ensure_poster_cache_dir() -> None:
    _cache_root().mkdir(parents=True, exist_ok=True)


def find_cached_filename(title: str) -> Optional[str]:
    """若磁盘上已有该片名对应缓存，返回文件名（不含路径）。"""
    if not poster_file_cache_enabled():
        return None
    ensure_poster_cache_dir()
    key = _title_key(title)
    root = _cache_root()
    if not root.is_dir():
        return None
    for p in root.glob(f"{key}.*"):
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            return p.name
    return None


def public_cache_url(filename: str) -> str:
    return f"/api/poster-cache/{filename}"


def try_local_cached_url(title: str) -> Optional[str]:
    fn = find_cached_filename(title)
    return public_cache_url(fn) if fn else None


def try_local_cached_url_any(*titles: str) -> Optional[str]:
    """
    按多个候选片名依次查本地 poster_cache（sha256 键）。
    用于：推荐展示名与片库缓存时用的豆瓣中文名不一致时仍能命中。
    """
    if not poster_file_cache_enabled():
        return None
    seen: set[str] = set()
    for raw in titles:
        t = (raw or "").strip()
        for v in (t, t.rstrip("!！?.． ") if t else ""):
            if not v or v in seen:
                continue
            seen.add(v)
            u = try_local_cached_url(v)
            if u:
                return u
    return None


_dl_pool: ThreadPoolExecutor | None = None


def _pool() -> ThreadPoolExecutor:
    global _dl_pool
    if _dl_pool is None:
        # 轻量后台下载，避免阻塞请求；并发不要太大
        _dl_pool = ThreadPoolExecutor(max_workers=int(os.getenv("POSTER_CACHE_WORKERS", "6")))
    return _dl_pool


def schedule_download_remote_to_cache(title: str, remote_url: str) -> None:
    """后台异步落盘（失败自动忽略）。"""
    if not poster_file_cache_enabled():
        return
    if try_local_cached_url(title):
        return
    try:
        _pool().submit(download_remote_to_cache, title, remote_url)
    except Exception:
        return


def download_remote_to_cache(title: str, remote_url: str) -> Optional[str]:
    """
    将 remote_url 对应图片写入 poster_cache，成功返回 /api/poster-cache/...；
    失败返回 None（调用方可回退为直连 remote_url）。
    """
    if not poster_file_cache_enabled() or not remote_url.startswith("http"):
        return None
    key = _title_key(title)
    root = _cache_root()
    ensure_poster_cache_dir()
    for p in root.glob(f"{key}.*"):
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            if _looks_like_image(p):
                return public_cache_url(p.name)
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
            break

    ext = ".jpg"
    tmp = root / f"{key}.download.tmp"
    max_bytes = int(os.getenv("POSTER_CACHE_MAX_BYTES", str(4 * 1024 * 1024)))
    try:
        r = requests.get(remote_url, headers=_image_fetch_headers(remote_url), timeout=15, stream=True)
        r.raise_for_status()
        ct = (r.headers.get("Content-Type", "") or "").lower()
        if ct and not ct.startswith("image/"):
            raise ValueError(f"unexpected content-type: {ct}")
        ext = _guess_ext(remote_url, r.headers.get("Content-Type", ""))
        final = root / f"{key}{ext}"
        total = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("image too large")
                f.write(chunk)
        if total < 256:
            raise ValueError("image too small")
        if not _looks_like_image(tmp):
            raise ValueError("not an image payload")
        tmp.replace(final)
        return public_cache_url(final.name)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def validate_cache_filename(filename: str) -> bool:
    return bool(_FILENAME_RE.match(filename))


def resolve_safe_cache_path(filename: str) -> Optional[Path]:
    if not validate_cache_filename(filename):
        return None
    root = _cache_root().resolve()
    cand = (root / filename).resolve()
    try:
        cand.relative_to(root)
    except ValueError:
        return None
    if cand.is_file():
        return cand

    # 兼容：历史版本可能把缓存落在 backend/data/poster_cache
    try:
        alt_root = (_backend_dir() / "data" / "poster_cache").resolve()
        alt = (alt_root / filename).resolve()
        alt.relative_to(alt_root)
        if alt.is_file():
            return alt
    except Exception:
        pass
    return None


def mimetype_for_path(path: Path) -> str:
    mt, _ = mimetypes.guess_type(path.name)
    return mt or "application/octet-stream"

