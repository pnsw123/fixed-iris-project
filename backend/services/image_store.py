"""
Image Store - Holds processed iris images for free token-based download.

When ``/api/v1/process-iris`` finishes, it stores three image blobs (HD,
preview, original) under an opaque token and returns that token to the
frontend.  The browser then downloads the HD and original images freely via
``/api/download-hd`` and ``/api/download-original`` using the token.

The token keeps the multi-megabyte HD bytes out of the JSON response and lets
the server expire stored images after a TTL so memory/Redis does not grow
unbounded.  There is no payment, account, or email step — downloads are free.

Storage backends:
- MemoryImageStore — default, dev only; lost on restart.
- RedisImageStore  — production; survives restarts and is shared across workers.

Select via PURCHASE_BACKEND env var: "memory" (default) or "redis".
REDIS_URL must also be set when using the Redis backend.
"""

import json
import logging
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------

@dataclass
class StoredImage:
    """A processed capture held for download, keyed by an opaque token."""

    token: str
    hd_data: bytes          # HD enhanced image (PNG bytes)
    preview_data: bytes     # Downscaled preview (PNG bytes)
    original_data: bytes    # Original capture before enhancement (PNG bytes)
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())

    # Images are kept for one hour after processing, then evicted.
    EXPIRY_SECONDS = 3600

    @property
    def is_expired(self) -> bool:
        return (datetime.now().timestamp() - self.created_at) > self.EXPIRY_SECONDS

    @property
    def time_remaining(self) -> float:
        expiry_time = self.created_at + self.EXPIRY_SECONDS
        return max(0.0, expiry_time - datetime.now().timestamp())

    def ttl_seconds(self) -> int:
        """TTL in whole seconds (minimum 1) for use as a Redis EXPIRE."""
        return max(1, int(self.time_remaining))


# ---------------------------------------------------------------------------
# Serialization helpers (Redis backend)
# ---------------------------------------------------------------------------

def _meta_to_dict(image: StoredImage) -> dict:
    return {"token": image.token, "created_at": image.created_at}


def _image_from_parts(meta: dict, hd: bytes, preview: bytes, original: bytes) -> StoredImage:
    return StoredImage(
        token=meta["token"],
        hd_data=hd,
        preview_data=preview,
        original_data=original,
        created_at=float(meta["created_at"]),
    )


# ---------------------------------------------------------------------------
# Abstract store interface
# ---------------------------------------------------------------------------

class ImageStoreBackend(ABC):
    """Interface implemented by both the memory and Redis backends."""

    @abstractmethod
    def store(self, hd_data: bytes, preview_data: bytes, original_data: bytes) -> str:
        ...

    @abstractmethod
    def get(self, token: str) -> Optional[StoredImage]:
        ...

    @abstractmethod
    def cleanup_expired(self) -> int:
        ...

    @abstractmethod
    def get_stats(self) -> dict:
        ...


# ---------------------------------------------------------------------------
# In-memory backend (dev / fallback)
# ---------------------------------------------------------------------------

class MemoryImageStore(ImageStoreBackend):
    """In-memory store. Fast for dev; lost on any restart."""

    def __init__(self) -> None:
        self._images: Dict[str, StoredImage] = {}
        self._lock = threading.Lock()
        logger.warning(
            "ImageStore using IN-MEMORY storage. Images are lost on restart. "
            "Set PURCHASE_BACKEND=redis and REDIS_URL for production."
        )

    def store(self, hd_data: bytes, preview_data: bytes, original_data: bytes) -> str:
        with self._lock:
            token = str(uuid.uuid4())
            self._images[token] = StoredImage(
                token=token,
                hd_data=hd_data,
                preview_data=preview_data,
                original_data=original_data,
            )
            logger.info(f"Stored image: {token[:8]}...")
            return token

    def get(self, token: str) -> Optional[StoredImage]:
        image = self._images.get(token)
        if image is None:
            return None
        if image.is_expired:
            with self._lock:
                self._images.pop(token, None)
            logger.info(f"Evicted expired image on read: {token[:8]}...")
            return None
        return image

    def cleanup_expired(self) -> int:
        with self._lock:
            expired = [t for t, img in self._images.items() if img.is_expired]
            for t in expired:
                del self._images[t]
                logger.info(f"Cleaned up expired image: {t[:8]}...")
            return len(expired)

    def get_stats(self) -> dict:
        return {"total": len(self._images), "backend": "memory"}


# ---------------------------------------------------------------------------
# Redis backend (production)
# ---------------------------------------------------------------------------

class RedisImageStore(ImageStoreBackend):
    """
    Redis-backed store. Images survive restarts and are shared across workers.

    Key layout (all keys prefixed with "eyedentity:"):
      eyedentity:image:{token}:meta       STRING  JSON metadata, TTL = time_remaining
      eyedentity:image:{token}:hd         STRING  raw bytes,     TTL = time_remaining
      eyedentity:image:{token}:preview    STRING  raw bytes,     TTL = time_remaining
      eyedentity:image:{token}:original   STRING  raw bytes,     TTL = time_remaining
      eyedentity:image:index              SET     active tokens  (for cleanup/stats)
    """

    _PREFIX = "eyedentity"

    def __init__(self, redis_url: str) -> None:
        try:
            import redis as redis_lib
        except ImportError as exc:
            raise RuntimeError(
                "redis package not installed. Add redis>=5.0.0 to requirements.txt."
            ) from exc

        self._redis = redis_lib.from_url(redis_url, decode_responses=False)
        self._redis.ping()
        logger.info(f"RedisImageStore connected to Redis ({redis_url.split('@')[-1]})")

    def _key(self, *parts: str) -> str:
        return ":".join([self._PREFIX] + list(parts))

    def _meta_key(self, token: str) -> str:
        return self._key("image", token, "meta")

    def _blob_key(self, token: str, kind: str) -> str:
        return self._key("image", token, kind)

    def _index_key(self) -> str:
        return self._key("image", "index")

    def _load(self, token: str) -> Optional[StoredImage]:
        meta_raw = self._redis.get(self._meta_key(token))
        if meta_raw is None:
            return None
        meta = json.loads(meta_raw.decode("utf-8"))
        hd = self._redis.get(self._blob_key(token, "hd")) or b""
        preview = self._redis.get(self._blob_key(token, "preview")) or b""
        original = self._redis.get(self._blob_key(token, "original")) or b""
        return _image_from_parts(meta, hd, preview, original)

    def _save(self, image: StoredImage) -> None:
        ttl = image.ttl_seconds()
        meta_json = json.dumps(_meta_to_dict(image)).encode("utf-8")
        pipe = self._redis.pipeline()
        pipe.setex(self._meta_key(image.token), ttl, meta_json)
        pipe.setex(self._blob_key(image.token, "hd"), ttl, image.hd_data)
        pipe.setex(self._blob_key(image.token, "preview"), ttl, image.preview_data)
        pipe.setex(self._blob_key(image.token, "original"), ttl, image.original_data)
        pipe.sadd(self._index_key(), image.token)
        pipe.execute()

    def _delete(self, token: str) -> None:
        pipe = self._redis.pipeline()
        pipe.delete(self._meta_key(token))
        pipe.delete(self._blob_key(token, "hd"))
        pipe.delete(self._blob_key(token, "preview"))
        pipe.delete(self._blob_key(token, "original"))
        pipe.srem(self._index_key(), token)
        pipe.execute()

    def store(self, hd_data: bytes, preview_data: bytes, original_data: bytes) -> str:
        token = str(uuid.uuid4())
        image = StoredImage(
            token=token,
            hd_data=hd_data,
            preview_data=preview_data,
            original_data=original_data,
        )
        self._save(image)
        logger.info(f"Stored image in Redis: {token[:8]}...")
        return token

    def get(self, token: str) -> Optional[StoredImage]:
        image = self._load(token)
        if image is None:
            return None
        if image.is_expired:
            self._delete(token)
            logger.info(f"Evicted expired image on read: {token[:8]}...")
            return None
        return image

    def cleanup_expired(self) -> int:
        tokens = self._redis.smembers(self._index_key())
        cleaned = 0
        for raw_token in tokens:
            token = raw_token.decode("utf-8") if isinstance(raw_token, bytes) else raw_token
            image = self._load(token)
            if image is None:
                self._redis.srem(self._index_key(), token)
                cleaned += 1
            elif image.is_expired:
                self._delete(token)
                logger.info(f"Cleaned up expired image from Redis: {token[:8]}...")
                cleaned += 1
        return cleaned

    def get_stats(self) -> dict:
        tokens = self._redis.smembers(self._index_key())
        total = sum(
            1
            for raw in tokens
            if self._redis.exists(
                self._meta_key(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            )
        )
        return {"total": total, "backend": "redis"}


# ---------------------------------------------------------------------------
# ImageStore — thin facade over the chosen backend
# ---------------------------------------------------------------------------

class ImageStore:
    """
    Public API for processed-image storage.

    Delegates to MemoryImageStore or RedisImageStore depending on the
    PURCHASE_BACKEND env var ("memory" | "redis").
    """

    def __init__(self) -> None:
        backend = settings.purchase_backend.strip().lower()
        if backend == "redis":
            if not settings.redis_url:
                raise RuntimeError(
                    "PURCHASE_BACKEND=redis but REDIS_URL is not set. "
                    "Add REDIS_URL to your environment variables."
                )
            self._store: ImageStoreBackend = RedisImageStore(settings.redis_url)
            logger.info("ImageStore initialized with Redis backend")
        else:
            self._store = MemoryImageStore()
            logger.info("ImageStore initialized with in-memory backend")

    def store(self, hd_data: bytes, preview_data: bytes, original_data: bytes) -> str:
        return self._store.store(hd_data, preview_data, original_data)

    def get(self, token: str) -> Optional[StoredImage]:
        return self._store.get(token)

    def cleanup_expired(self) -> int:
        return self._store.cleanup_expired()

    def get_stats(self) -> dict:
        return self._store.get_stats()


# ---------------------------------------------------------------------------
# Singleton instance
# ---------------------------------------------------------------------------

image_store = ImageStore()
