"""File-based tile caching system.

Provides a simple cache for map tiles with TTL-based expiration.
Directory structure: cache_dir/{provider}/{z}/{x}/{y}.{ext}
"""

import json
import time
from pathlib import Path
from typing import NamedTuple


class CachedTile(NamedTuple):
    """Cached tile data."""

    content: bytes
    content_type: str
    headers: dict[str, str]


class TileCache:
    """File-based tile cache with directory structure: style_source/z/x/y.ext"""

    def __init__(self, cache_dir: Path, default_ttl: int = 86400):
        """Initialize tile cache.

        Args:
            cache_dir: Root directory for cache files
            default_ttl: Default time-to-live in seconds (default: 24 hours)
        """
        self.cache_dir = cache_dir
        self.default_ttl = default_ttl
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(
        self, cache_key: str, z: int, x: int, y: int, ext: str
    ) -> Path:
        """Get cache file path: cache_dir/cache_key/z/x/y.ext"""
        return self.cache_dir / cache_key / str(z) / str(x) / f"{y}.{ext}"

    def _get_meta_path(self, cache_path: Path) -> Path:
        """Get metadata file path for headers."""
        return cache_path.with_suffix(cache_path.suffix + ".meta")

    def get(
        self, cache_key: str, z: int, x: int, y: int, ext: str
    ) -> CachedTile | None:
        """Get tile from cache if exists and not expired.

        Args:
            cache_key: Cache key (e.g., "maptiler-outdoor_maptiler_planet")
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate
            ext: File extension (pbf, png, webp)

        Returns:
            CachedTile or None if not found/expired
        """
        cache_path = self._get_cache_path(cache_key, z, x, y, ext)
        meta_path = self._get_meta_path(cache_path)

        if not cache_path.exists():
            return None

        # Check TTL via mtime
        age = time.time() - cache_path.stat().st_mtime
        ttl = self.default_ttl

        # Load metadata if exists
        headers = {}
        content_type = "application/octet-stream"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                headers = meta.get("headers", {})
                content_type = meta.get("content_type", content_type)
                ttl = meta.get("ttl", ttl)
            except (json.JSONDecodeError, OSError):
                pass  # Use defaults if meta is corrupted

        if age > ttl:
            return None  # Expired

        try:
            content = cache_path.read_bytes()
            return CachedTile(
                content=content,
                content_type=content_type,
                headers=headers,
            )
        except OSError:
            return None

    def put(
        self,
        cache_key: str,
        z: int,
        x: int,
        y: int,
        ext: str,
        content: bytes,
        content_type: str,
        headers: dict[str, str] | None = None,
        ttl: int | None = None,
    ) -> None:
        """Store tile in cache.

        Args:
            cache_key: Cache key
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate
            ext: File extension
            content: Tile content bytes
            content_type: MIME type
            headers: Optional response headers to cache
            ttl: Optional TTL override
        """
        cache_path = self._get_cache_path(cache_key, z, x, y, ext)
        meta_path = self._get_meta_path(cache_path)

        # Create directory structure
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        # Write tile data
        cache_path.write_bytes(content)

        # Write metadata
        meta = {
            "content_type": content_type,
            "headers": headers or {},
            "ttl": ttl or self.default_ttl,
            "cached_at": time.time(),
        }
        meta_path.write_text(json.dumps(meta))

    def invalidate(self, cache_key: str | None = None) -> int:
        """Invalidate cache entries.

        Args:
            cache_key: Specific cache key to invalidate, or None for all

        Returns:
            Count of deleted files
        """
        import shutil

        count = 0
        if cache_key:
            key_dir = self.cache_dir / cache_key
            if key_dir.exists():
                count = sum(1 for f in key_dir.rglob("*") if f.is_file())
                shutil.rmtree(key_dir)
        else:
            for key_dir in self.cache_dir.iterdir():
                if key_dir.is_dir():
                    count += sum(1 for f in key_dir.rglob("*") if f.is_file())
                    shutil.rmtree(key_dir)
        return count

    def stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dict with total_size_mb, total_files, and by_key breakdown
        """
        total_size = 0
        file_count = 0
        by_key: dict[str, dict] = {}

        if not self.cache_dir.exists():
            return {
                "total_size_mb": 0,
                "total_files": 0,
                "by_key": {},
            }

        for key_dir in self.cache_dir.iterdir():
            if key_dir.is_dir():
                key_size = 0
                key_count = 0
                for f in key_dir.rglob("*"):
                    if f.is_file() and not f.suffix == ".meta":
                        key_size += f.stat().st_size
                        key_count += 1
                by_key[key_dir.name] = {
                    "size_mb": round(key_size / 1024 / 1024, 2),
                    "file_count": key_count,
                }
                total_size += key_size
                file_count += key_count

        return {
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "total_files": file_count,
            "by_key": by_key,
        }
