"""
Tests for services/image_store.py — free token-based image storage (memory backend).

Coverage:
- store() returns a unique token; get() round-trips the three blobs
- get() returns None for unknown tokens
- expired images are evicted on read and by cleanup_expired()
- get_stats() reports the live count
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault("PURCHASE_BACKEND", "memory")

from services.image_store import MemoryImageStore, StoredImage


HD = b"\x89PNG_HD"
PREVIEW = b"\x89PNG_PREVIEW"
ORIGINAL = b"\x89PNG_ORIGINAL"


def _store() -> MemoryImageStore:
    return MemoryImageStore()


class TestStoreAndGet:
    def test_store_returns_token(self):
        s = _store()
        token = s.store(HD, PREVIEW, ORIGINAL)
        assert isinstance(token, str)
        assert len(token) >= 16

    def test_tokens_are_unique(self):
        s = _store()
        t1 = s.store(HD, PREVIEW, ORIGINAL)
        t2 = s.store(HD, PREVIEW, ORIGINAL)
        assert t1 != t2

    def test_get_round_trips_all_blobs(self):
        s = _store()
        token = s.store(HD, PREVIEW, ORIGINAL)
        image = s.get(token)
        assert image is not None
        assert image.hd_data == HD
        assert image.preview_data == PREVIEW
        assert image.original_data == ORIGINAL

    def test_get_unknown_token_returns_none(self):
        s = _store()
        assert s.get("does-not-exist") is None


class TestExpiry:
    def test_expired_image_evicted_on_read(self):
        s = _store()
        token = s.store(HD, PREVIEW, ORIGINAL)
        # Force expiry by backdating created_at well past the TTL.
        s._images[token].created_at -= (StoredImage.EXPIRY_SECONDS + 10)
        assert s.get(token) is None
        # Eviction on read removes it from the backing dict.
        assert token not in s._images

    def test_cleanup_expired_removes_only_expired(self):
        s = _store()
        fresh = s.store(HD, PREVIEW, ORIGINAL)
        stale = s.store(HD, PREVIEW, ORIGINAL)
        s._images[stale].created_at -= (StoredImage.EXPIRY_SECONDS + 10)
        removed = s.cleanup_expired()
        assert removed == 1
        assert s.get(fresh) is not None
        assert s.get(stale) is None

    def test_is_expired_property(self):
        img = StoredImage(token="t", hd_data=HD, preview_data=PREVIEW, original_data=ORIGINAL)
        assert img.is_expired is False
        img.created_at -= (StoredImage.EXPIRY_SECONDS + 1)
        assert img.is_expired is True

    def test_ttl_seconds_at_least_one(self):
        img = StoredImage(token="t", hd_data=HD, preview_data=PREVIEW, original_data=ORIGINAL)
        assert img.ttl_seconds() >= 1


class TestStats:
    def test_stats_reports_count_and_backend(self):
        s = _store()
        s.store(HD, PREVIEW, ORIGINAL)
        s.store(HD, PREVIEW, ORIGINAL)
        stats = s.get_stats()
        assert stats["total"] == 2
        assert stats["backend"] == "memory"
