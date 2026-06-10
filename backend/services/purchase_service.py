"""
Purchase Service - Manages pending purchases for payment flow.

This module handles the lifecycle of image purchases:
1. Create pending purchase when user enhances image
2. Mark as paid when webhook confirms payment
3. Serve HD image on verified download
4. Cleanup expired purchases

Storage backends:
- MemoryPurchaseStore  — default, dev only; lost on restart
- RedisPurchaseStore   — production; persists across restarts/deploys

Select via PURCHASE_BACKEND env var: "memory" (default) or "redis".
REDIS_URL must also be set when using the Redis backend.
"""

import os
import uuid
import json
import logging
import threading
import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Set
from enum import Enum

from config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------

class PurchaseStatus(Enum):
    """Status of a pending purchase."""
    PENDING = "PENDING"  # Created, waiting for payment
    PAID = "PAID"        # Payment confirmed via webhook
    EXPIRED = "EXPIRED"  # Timed out without payment


@dataclass
class PendingPurchase:
    """
    Represents a pending purchase.

    Lifecycle:
    - Created when user clicks "Enhance" (status=PENDING)
    - Updated when webhook confirms payment (status=PAID)
    - Deleted after expiry (1h unpaid, 48h paid)
    """
    token: str
    image_data: bytes           # HD enhanced image
    preview_data: bytes         # Watermarked preview
    original_data: bytes        # Original capture (before enhancement)
    status: PurchaseStatus = PurchaseStatus.PENDING
    user_email: Optional[str] = None
    order_id: Optional[str] = None
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    paid_at: Optional[float] = None

    # Expiry times in seconds
    UNPAID_EXPIRY = 3600      # 1 hour
    PAID_EXPIRY = 48 * 3600   # 48 hours

    @property
    def is_expired(self) -> bool:
        """Check if this purchase has expired."""
        now = datetime.now().timestamp()
        if self.status == PurchaseStatus.PAID:
            return (now - (self.paid_at or self.created_at)) > self.PAID_EXPIRY
        else:
            return (now - self.created_at) > self.UNPAID_EXPIRY

    @property
    def time_remaining(self) -> float:
        """Get seconds until expiry."""
        now = datetime.now().timestamp()
        if self.status == PurchaseStatus.PAID:
            expiry_time = (self.paid_at or self.created_at) + self.PAID_EXPIRY
        else:
            expiry_time = self.created_at + self.UNPAID_EXPIRY
        return max(0, expiry_time - now)

    def ttl_seconds(self) -> int:
        """Return TTL in whole seconds (minimum 1, for use as Redis EXPIRE)."""
        return max(1, int(self.time_remaining))


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _purchase_to_meta_dict(purchase: PendingPurchase) -> dict:
    """Serialize PendingPurchase metadata (no binary blobs) to a JSON-safe dict."""
    return {
        "token": purchase.token,
        "status": purchase.status.value,
        "user_email": purchase.user_email,
        "order_id": purchase.order_id,
        "created_at": purchase.created_at,
        "paid_at": purchase.paid_at,
    }


def _purchase_from_parts(meta: dict, hd: bytes, preview: bytes, original: bytes) -> PendingPurchase:
    """Reconstruct a PendingPurchase from serialized parts."""
    return PendingPurchase(
        token=meta["token"],
        image_data=hd,
        preview_data=preview,
        original_data=original,
        status=PurchaseStatus(meta["status"]),
        user_email=meta.get("user_email"),
        order_id=meta.get("order_id"),
        created_at=float(meta["created_at"]),
        paid_at=float(meta["paid_at"]) if meta.get("paid_at") is not None else None,
    )


# ---------------------------------------------------------------------------
# Abstract store interface
# ---------------------------------------------------------------------------

class PurchaseStore(ABC):
    """Interface that both memory and Redis backends implement."""

    @abstractmethod
    def create_purchase(
        self,
        hd_image_data: bytes,
        preview_data: bytes,
        original_data: bytes,
        user_email: Optional[str] = None,
    ) -> str:
        ...

    @abstractmethod
    def get_purchase(self, token: str) -> Optional[PendingPurchase]:
        ...

    @abstractmethod
    def mark_as_paid(
        self,
        token: str,
        order_id: str,
        user_email: Optional[str] = None,
    ) -> bool:
        ...

    @abstractmethod
    def update_email(self, token: str, email: str) -> bool:
        ...

    @abstractmethod
    def is_webhook_processed(self, event_id: str) -> bool:
        ...

    @abstractmethod
    def mark_webhook_processed(self, event_id: str) -> None:
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

class MemoryPurchaseStore(PurchaseStore):
    """In-memory store. Fast for dev; lost on any restart."""

    def __init__(self) -> None:
        self._purchases: Dict[str, PendingPurchase] = {}
        self._processed_webhook_ids: Set[str] = set()
        self._lock = threading.Lock()
        logger.warning(
            "PurchaseService using IN-MEMORY storage. "
            "Purchases are lost on restart. "
            "Set PURCHASE_BACKEND=redis and REDIS_URL for production."
        )

    def create_purchase(
        self,
        hd_image_data: bytes,
        preview_data: bytes,
        original_data: bytes,
        user_email: Optional[str] = None,
    ) -> str:
        with self._lock:
            token = str(uuid.uuid4())
            purchase = PendingPurchase(
                token=token,
                image_data=hd_image_data,
                preview_data=preview_data,
                original_data=original_data,
                user_email=user_email,
            )
            self._purchases[token] = purchase
            logger.info(f"Created pending purchase: {token[:8]}... (email: {user_email or 'not provided'})")
            return token

    def get_purchase(self, token: str) -> Optional[PendingPurchase]:
        return self._purchases.get(token)

    def mark_as_paid(
        self,
        token: str,
        order_id: str,
        user_email: Optional[str] = None,
    ) -> bool:
        purchase = self._purchases.get(token)
        if not purchase:
            logger.warning(f"Attempted to mark unknown token as paid: {token[:8]}...")
            return False
        if purchase.status == PurchaseStatus.PAID:
            logger.info(f"Purchase already marked as paid: {token[:8]}...")
            return True
        purchase.status = PurchaseStatus.PAID
        purchase.order_id = order_id
        purchase.paid_at = datetime.now().timestamp()
        if user_email:
            purchase.user_email = user_email
        logger.info(f"Marked purchase as PAID: {token[:8]}... (Order: {order_id})")
        return True

    def update_email(self, token: str, email: str) -> bool:
        purchase = self._purchases.get(token)
        if not purchase:
            return False
        purchase.user_email = email
        return True

    def is_webhook_processed(self, event_id: str) -> bool:
        return event_id in self._processed_webhook_ids

    def mark_webhook_processed(self, event_id: str) -> None:
        with self._lock:
            self._processed_webhook_ids.add(event_id)

    def cleanup_expired(self) -> int:
        with self._lock:
            expired = [t for t, p in self._purchases.items() if p.is_expired]
            for t in expired:
                del self._purchases[t]
                logger.info(f"Cleaned up expired purchase: {t[:8]}...")
            return len(expired)

    def get_stats(self) -> dict:
        total = len(self._purchases)
        pending = sum(1 for p in self._purchases.values() if p.status == PurchaseStatus.PENDING)
        paid = sum(1 for p in self._purchases.values() if p.status == PurchaseStatus.PAID)
        return {
            "total": total,
            "pending": pending,
            "paid": paid,
            "webhook_ids_tracked": len(self._processed_webhook_ids),
            "backend": "memory",
        }


# ---------------------------------------------------------------------------
# Redis backend (production)
# ---------------------------------------------------------------------------

class RedisPurchaseStore(PurchaseStore):
    """
    Redis-backed store. Purchases survive restarts and scale across workers.

    Key layout (all keys prefixed with "eyedentity:"):
      eyedentity:purchase:{token}:meta        STRING  JSON metadata, TTL = time_remaining
      eyedentity:purchase:{token}:hd          STRING  raw bytes,     TTL = time_remaining
      eyedentity:purchase:{token}:preview     STRING  raw bytes,     TTL = time_remaining
      eyedentity:purchase:{token}:original    STRING  raw bytes,     TTL = time_remaining
      eyedentity:webhook:processed            SET     event IDs (no TTL — small, idempotency set)
      eyedentity:purchase:index               SET     active tokens  (for cleanup/stats)
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
        # Verify connection
        self._redis.ping()
        logger.info(f"RedisPurchaseStore connected to Redis ({redis_url.split('@')[-1]})")

    # --- Key helpers --------------------------------------------------------

    def _key(self, *parts: str) -> str:
        return ":".join([self._PREFIX] + list(parts))

    def _meta_key(self, token: str) -> str:
        return self._key("purchase", token, "meta")

    def _blob_key(self, token: str, kind: str) -> str:
        return self._key("purchase", token, kind)

    def _index_key(self) -> str:
        return self._key("purchase", "index")

    def _webhook_key(self) -> str:
        return self._key("webhook", "processed")

    # --- Internal helpers ---------------------------------------------------

    def _load_purchase(self, token: str) -> Optional[PendingPurchase]:
        """Load all parts of a purchase from Redis. Returns None if not found."""
        meta_raw = self._redis.get(self._meta_key(token))
        if meta_raw is None:
            return None
        meta = json.loads(meta_raw.decode("utf-8"))
        hd = self._redis.get(self._blob_key(token, "hd")) or b""
        preview = self._redis.get(self._blob_key(token, "preview")) or b""
        original = self._redis.get(self._blob_key(token, "original")) or b""
        return _purchase_from_parts(meta, hd, preview, original)

    def _save_purchase(self, purchase: PendingPurchase) -> None:
        """Persist all parts of a purchase to Redis with appropriate TTL."""
        ttl = purchase.ttl_seconds()
        meta_json = json.dumps(_purchase_to_meta_dict(purchase)).encode("utf-8")

        pipe = self._redis.pipeline()
        pipe.setex(self._meta_key(purchase.token), ttl, meta_json)
        pipe.setex(self._blob_key(purchase.token, "hd"), ttl, purchase.image_data)
        pipe.setex(self._blob_key(purchase.token, "preview"), ttl, purchase.preview_data)
        pipe.setex(self._blob_key(purchase.token, "original"), ttl, purchase.original_data)
        # Track token in the index (index entry itself expires a bit after the purchase TTL)
        pipe.sadd(self._index_key(), purchase.token)
        pipe.execute()

    def _delete_purchase(self, token: str) -> None:
        """Remove all Redis keys for a token."""
        pipe = self._redis.pipeline()
        pipe.delete(self._meta_key(token))
        pipe.delete(self._blob_key(token, "hd"))
        pipe.delete(self._blob_key(token, "preview"))
        pipe.delete(self._blob_key(token, "original"))
        pipe.srem(self._index_key(), token)
        pipe.execute()

    # --- PurchaseStore interface ---------------------------------------------

    def create_purchase(
        self,
        hd_image_data: bytes,
        preview_data: bytes,
        original_data: bytes,
        user_email: Optional[str] = None,
    ) -> str:
        token = str(uuid.uuid4())
        purchase = PendingPurchase(
            token=token,
            image_data=hd_image_data,
            preview_data=preview_data,
            original_data=original_data,
            user_email=user_email,
        )
        self._save_purchase(purchase)
        logger.info(f"Created pending purchase in Redis: {token[:8]}... (email: {user_email or 'not provided'})")
        return token

    def get_purchase(self, token: str) -> Optional[PendingPurchase]:
        purchase = self._load_purchase(token)
        if purchase is None:
            return None
        if purchase.is_expired:
            self._delete_purchase(token)
            logger.info(f"Evicted expired purchase on read: {token[:8]}...")
            return None
        return purchase

    def mark_as_paid(
        self,
        token: str,
        order_id: str,
        user_email: Optional[str] = None,
    ) -> bool:
        purchase = self._load_purchase(token)
        if not purchase:
            logger.warning(f"Attempted to mark unknown token as paid: {token[:8]}...")
            return False
        if purchase.status == PurchaseStatus.PAID:
            logger.info(f"Purchase already marked as paid: {token[:8]}...")
            return True
        purchase.status = PurchaseStatus.PAID
        purchase.order_id = order_id
        purchase.paid_at = datetime.now().timestamp()
        if user_email:
            purchase.user_email = user_email
        self._save_purchase(purchase)
        logger.info(f"Marked purchase as PAID in Redis: {token[:8]}... (Order: {order_id})")
        return True

    def update_email(self, token: str, email: str) -> bool:
        purchase = self._load_purchase(token)
        if not purchase:
            return False
        purchase.user_email = email
        self._save_purchase(purchase)
        return True

    def is_webhook_processed(self, event_id: str) -> bool:
        return bool(self._redis.sismember(self._webhook_key(), event_id))

    def mark_webhook_processed(self, event_id: str) -> None:
        self._redis.sadd(self._webhook_key(), event_id)

    def cleanup_expired(self) -> int:
        """
        Scan index set; remove tokens whose meta key has expired in Redis
        (i.e. the key is gone — Redis evicted it via TTL) or whose is_expired
        property is True (clock-based check for keys still present).
        """
        tokens = self._redis.smembers(self._index_key())
        cleaned = 0
        for raw_token in tokens:
            token = raw_token.decode("utf-8") if isinstance(raw_token, bytes) else raw_token
            purchase = self._load_purchase(token)
            if purchase is None:
                # Already TTL-expired by Redis or never existed — clean index entry
                self._redis.srem(self._index_key(), token)
                cleaned += 1
            elif purchase.is_expired:
                self._delete_purchase(token)
                logger.info(f"Cleaned up expired purchase from Redis: {token[:8]}...")
                cleaned += 1
        return cleaned

    def get_stats(self) -> dict:
        tokens = self._redis.smembers(self._index_key())
        total = 0
        pending = 0
        paid = 0
        for raw_token in tokens:
            token = raw_token.decode("utf-8") if isinstance(raw_token, bytes) else raw_token
            meta_raw = self._redis.get(self._meta_key(token))
            if meta_raw is None:
                continue
            total += 1
            meta = json.loads(meta_raw.decode("utf-8"))
            if meta.get("status") == PurchaseStatus.PENDING.value:
                pending += 1
            elif meta.get("status") == PurchaseStatus.PAID.value:
                paid += 1
        webhook_count = self._redis.scard(self._webhook_key())
        return {
            "total": total,
            "pending": pending,
            "paid": paid,
            "webhook_ids_tracked": webhook_count,
            "backend": "redis",
        }


# ---------------------------------------------------------------------------
# PurchaseService — thin facade over the chosen backend
# ---------------------------------------------------------------------------

class PurchaseService:
    """
    Public API for purchase management.

    Delegates all storage to either MemoryPurchaseStore or RedisPurchaseStore
    depending on PURCHASE_BACKEND env var ("memory" | "redis").

    For MVP/dev: PURCHASE_BACKEND=memory (default)
    For production: PURCHASE_BACKEND=redis + REDIS_URL=redis://...
    """

    def __init__(self) -> None:
        backend = os.environ.get("PURCHASE_BACKEND", "memory").strip().lower()

        if backend == "redis":
            if not settings.redis_url:
                raise RuntimeError(
                    "PURCHASE_BACKEND=redis but REDIS_URL is not set. "
                    "Add REDIS_URL to your environment variables."
                )
            self._store: PurchaseStore = RedisPurchaseStore(settings.redis_url)
            logger.info("PurchaseService initialized with Redis backend")
        else:
            self._store = MemoryPurchaseStore()
            logger.info("PurchaseService initialized with in-memory backend")

    # Delegate everything to the backend store

    def create_purchase(
        self,
        hd_image_data: bytes,
        preview_data: bytes,
        original_data: bytes,
        user_email: Optional[str] = None,
    ) -> str:
        return self._store.create_purchase(hd_image_data, preview_data, original_data, user_email)

    def get_purchase(self, token: str) -> Optional[PendingPurchase]:
        return self._store.get_purchase(token)

    def mark_as_paid(
        self,
        token: str,
        order_id: str,
        user_email: Optional[str] = None,
    ) -> bool:
        return self._store.mark_as_paid(token, order_id, user_email)

    def update_email(self, token: str, email: str) -> bool:
        return self._store.update_email(token, email)

    def is_webhook_processed(self, event_id: str) -> bool:
        return self._store.is_webhook_processed(event_id)

    def mark_webhook_processed(self, event_id: str) -> None:
        self._store.mark_webhook_processed(event_id)

    def cleanup_expired(self) -> int:
        return self._store.cleanup_expired()

    def get_stats(self) -> dict:
        return self._store.get_stats()


# ---------------------------------------------------------------------------
# Singleton instance
# ---------------------------------------------------------------------------

purchase_service = PurchaseService()
