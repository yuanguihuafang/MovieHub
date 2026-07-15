# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, Optional

import mimetypes
import requests

from backend.services.tmdb_home_cache import cache_path
from backend.services.tmdb_client import tmdb_movie_detail, tmdb_configured


_FILENAME_RE = re.compile(r"^tmdb_\d+\.(jpe?g|png|webp)$", re.I)

_MAGIC_JPG = b"\xff\xd8\xff"
_MAGIC_PNG = b"\x89PNG\r\n\x1a\n"
_MAGIC_RIFF = b"RIFF"
_MAGIC_WEBP = b"WEBP"


def home_poster_dir() -> Path:
    # 统一落盘到 backend/data/tmdb_image（与其它 data 文件隔离）
    return (cache_path().parent / "tmdb_image").resolve()


def _legacy_home_poster_dir() -> Path:
    # 兼容旧版本：曾落盘在 backend/data 根目录
    return cache_path().parent.resolve()


def public_home_poster_url(tmdb_id: int, ext: str) -> str:
    tid = int(tmdb_id)
    e = (ext or ".jpg").lower()
    if e not in (".jpg", ".jpeg", ".png", ".webp"):
        e = ".jpg"
    if e == ".jpeg":
        e = ".jpg"
    return f"/api/tmdb-home-poster/tmdb_{tid}{e}"


def _looks_like_image(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(16)
        if head.startswith(_MAGIC_JPG):
            return True
        if head.startswith(_MAGIC_PNG):
            return True
        if head.startswith(_MAGIC_RIFF) and _MAGIC_WEBP in head:
            return True
        return False
    except Exception:
        return False


def _guess_ext(url: str, content_type: str) -> str:
    ct = (content_type or "").lower()
    if "webp" in ct:
        return ".webp"
    if "png" in ct:
        return ".png"
    u = (url or "").lower()
    if u.endswith(".webp"):
        return ".webp"
    if u.endswith(".png"):
        return ".png"
    return ".jpg"


def _image_fetch_headers(url: str) -> dict[str, str]:
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    return {
        "User-Agent": ua,
        "Referer": "https://www.themoviedb.org/",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }


def validate_home_poster_filename(filename: str) -> bool:
    return bool(_FILENAME_RE.match(filename or ""))


def resolve_safe_home_poster_path(filename: str) -> Optional[Path]:
    if not validate_home_poster_filename(filename):
        return None
    root = home_poster_dir().resolve()
    root.mkdir(parents=True, exist_ok=True)
    cand = (root / filename).resolve()
    try:
        cand.relative_to(root)
    except ValueError:
        return None
    if cand.is_file():
        return cand
    # 兼容：旧目录可能还残留文件
    try:
        legacy = _legacy_home_poster_dir().resolve()
        alt = (legacy / filename).resolve()
        alt.relative_to(legacy)
        if alt.is_file():
            return alt
    except Exception:
        pass
    return None


def mimetype_for_path(path: Path) -> str:
    mt, _ = mimetypes.guess_type(path.name)
    return mt or "application/octet-stream"


def _expected_filenames_for_items(items: Iterable[dict]) -> set[str]:
    out: set[str] = set()
    for m in items or []:
        if not isinstance(m, dict):
            continue
        try:
            tid = int(m.get("tmdb_id") or 0)
        except Exception:
            tid = 0
        if tid <= 0:
            continue
        pu = str(m.get("poster_url") or "")
        if pu.startswith("/api/tmdb-home-poster/"):
            fn = pu.rsplit("/", 1)[-1]
            if validate_home_poster_filename(fn):
                out.add(fn)
    return out


def purge_stale_home_posters(keep_filenames: set[str]) -> None:
    """
    删除同目录下历史 tmdb_*.jpg/png/webp，但保留本次仍在使用文件名集合。
    """
    keep = set(keep_filenames or set())
    for root in (home_poster_dir(), _legacy_home_poster_dir()):
        try:
            root.mkdir(parents=True, exist_ok=True)
        except Exception:
            continue
        if not root.is_dir():
            continue
        for p in root.iterdir():
            try:
                if not p.is_file():
                    continue
                if not validate_home_poster_filename(p.name):
                    continue
                if p.name in keep:
                    continue
                p.unlink(missing_ok=True)
            except Exception:
                continue


def download_tmdb_poster_to_home_cache(tmdb_id: int, remote_url: str) -> Optional[str]:
    """
    下载 TMDB CDN 海报到 tmdb_home_cache.json 同目录，并返回同源 URL：
    /api/tmdb-home-poster/tmdb_{id}.{ext}
    """
    tid = int(tmdb_id)
    if tid <= 0:
        return None
    ru = (remote_url or "").strip()
    if not ru.startswith("http"):
        return None

    root = home_poster_dir()
    root.mkdir(parents=True, exist_ok=True)

    # 先探测是否已有可用文件（任意扩展名）
    for ext in (".webp", ".jpg", ".png"):
        p = root / f"tmdb_{tid}{ext}"
        if p.is_file() and _looks_like_image(p):
            return public_home_poster_url(tid, ext)

    max_bytes = int(os.getenv("TMDB_HOME_POSTER_MAX_BYTES", str(4 * 1024 * 1024)))
    tmp = root / f"tmdb_{tid}.download.tmp"
    try:
        r = requests.get(ru, headers=_image_fetch_headers(ru), timeout=20, stream=True)
        r.raise_for_status()
        ct = (r.headers.get("Content-Type", "") or "").lower()
        if ct and not ct.startswith("image/"):
            raise ValueError(f"unexpected content-type: {ct}")
        ext = _guess_ext(ru, r.headers.get("Content-Type", ""))
        final = root / f"tmdb_{tid}{ext}"
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
        return public_home_poster_url(tid, ext)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def materialize_home_posters_for_tmdb_items(items: list[dict], *, purge: bool = True) -> set[str]:
    """
    就地更新 items 的 poster_url：
    - 成功：写入 /api/tmdb-home-poster/...
    - 失败：保留原始 http(s)（若存在），避免首页完全无图
    """
    expected: set[str] = set()
    for m in items or []:
        if not isinstance(m, dict):
            continue
        try:
            tid = int(m.get("tmdb_id") or m.get("id") or 0)
        except Exception:
            tid = 0
        if tid <= 0:
            continue
        m["tmdb_id"] = tid
        ru = str(m.get("poster_url") or "").strip()

        # 若缓存里是本地同源 URL，但文件已被清理/不存在：用 tmdb_id 回源补 poster_path 再下载
        if ru.startswith("/api/tmdb-home-poster/"):
            # 计算期望文件名并检查是否存在
            fn0 = ru.rsplit("/", 1)[-1]
            if validate_home_poster_filename(fn0) and resolve_safe_home_poster_path(fn0) is None:
                if tmdb_configured():
                    try:
                        d = tmdb_movie_detail(tid, timeout=6.5) or {}
                        pp = (d.get("poster_path") or "").strip()
                        if pp:
                            ru = f"https://image.tmdb.org/t/p/w500{pp}"
                    except Exception:
                        pass

        local = download_tmdb_poster_to_home_cache(tid, ru)
        if local:
            m["poster_url"] = local
            fn = local.rsplit("/", 1)[-1]
            if validate_home_poster_filename(fn):
                expected.add(fn)
        else:
            # 下载失败：若我们已经拿到了可用的 TMDB CDN URL（detail 回源），则回退为直连，避免首页白块
            if ru.startswith("http"):
                m["poster_url"] = ru
            # 若已有历史落盘文件，也计入保留集合，避免误删
            for ext in (".webp", ".jpg", ".png"):
                p = home_poster_dir() / f"tmdb_{tid}{ext}"
                if p.is_file() and _looks_like_image(p):
                    expected.add(p.name)
                    break

    # 清理：删除目录里不在本次期望集合中的 tmdb_*.ext
    if purge:
        purge_stale_home_posters(expected)

    return expected


def materialize_home_posters_for_sections(now_playing: list[dict], upcoming: list[dict]) -> None:
    """
    首页两个分区的海报落盘与清理必须“一次性”做，否则会出现：
    - 先处理 now_playing 并 purge
    - 再处理 upcoming 并 purge
    第二次 purge 会把第一组的海报删掉，导致 now_playing 变成透明占位。
    """
    keep: set[str] = set()
    try:
        keep |= materialize_home_posters_for_tmdb_items(now_playing, purge=False)
    except Exception:
        pass
    try:
        keep |= materialize_home_posters_for_tmdb_items(upcoming, purge=False)
    except Exception:
        pass
    purge_stale_home_posters(keep)