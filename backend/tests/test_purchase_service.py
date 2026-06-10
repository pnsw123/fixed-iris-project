"""Tests for services/purchase_service.py — token lifecycle.

Tests run against the in-memory backend (PURCHASE_BACKEND=memory) so they
require no external Redis. The PurchaseService public API is identical
regardless of backend — these tests validate the contract, not the backend.
"""

import time
import pytest
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

# Force memory backend for unit tests — no Redis required
os.environ.setdefault("PURCHASE_BACKEND", "memory")

from services.purchase_service import (
    PurchaseService,
    MemoryPurchaseStore,
    PurchaseStatus,
    PendingPurchase,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def service() -> PurchaseService:
    """Fresh PurchaseService instance per test (always memory backend)."""
    # Ensure memory backend regardless of env var in the outer process
    svc = PurchaseService.__new__(PurchaseService)
    svc._store = MemoryPurchaseStore()
    return svc


SAMPLE_HD = b'hd_image_data'
SAMPLE_PREVIEW = b'preview_data'
SAMPLE_ORIGINAL = b'original_data'


# ---------------------------------------------------------------------------
# create_purchase
# ---------------------------------------------------------------------------

class TestCreatePurchase:
    def test_returns_string_token(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_each_create_returns_unique_token(self, service: PurchaseService):
        t1 = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        t2 = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        assert t1 != t2

    def test_purchase_starts_as_pending(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        purchase = service.get_purchase(token)
        assert purchase is not None
        assert purchase.status == PurchaseStatus.PENDING

    def test_stores_hd_image_data(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        purchase = service.get_purchase(token)
        assert purchase.image_data == SAMPLE_HD

    def test_stores_preview_data(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        purchase = service.get_purchase(token)
        assert purchase.preview_data == SAMPLE_PREVIEW

    def test_stores_original_data(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        purchase = service.get_purchase(token)
        assert purchase.original_data == SAMPLE_ORIGINAL

    def test_stores_user_email_when_provided(self, service: PurchaseService):
        token = service.create_purchase(
            SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL, user_email='user@example.com'
        )
        purchase = service.get_purchase(token)
        assert purchase.user_email == 'user@example.com'

    def test_user_email_is_none_when_not_provided(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        purchase = service.get_purchase(token)
        assert purchase.user_email is None


# ---------------------------------------------------------------------------
# get_purchase
# ---------------------------------------------------------------------------

class TestGetPurchase:
    def test_returns_none_for_unknown_token(self, service: PurchaseService):
        result = service.get_purchase('non-existent-token')
        assert result is None

    def test_returns_purchase_for_valid_token(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        result = service.get_purchase(token)
        assert result is not None
        assert result.token == token


# ---------------------------------------------------------------------------
# mark_as_paid
# ---------------------------------------------------------------------------

class TestMarkAsPaid:
    def test_marks_purchase_as_paid(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        result = service.mark_as_paid(token, order_id='order-123')
        assert result is True
        purchase = service.get_purchase(token)
        assert purchase.status == PurchaseStatus.PAID

    def test_sets_order_id(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        service.mark_as_paid(token, order_id='order-456')
        purchase = service.get_purchase(token)
        assert purchase.order_id == 'order-456'

    def test_sets_paid_at_timestamp(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        before = time.time()
        service.mark_as_paid(token, order_id='order-789')
        after = time.time()
        purchase = service.get_purchase(token)
        assert purchase.paid_at is not None
        assert before <= purchase.paid_at <= after

    def test_returns_false_for_unknown_token(self, service: PurchaseService):
        result = service.mark_as_paid('unknown-token', order_id='order-000')
        assert result is False

    def test_idempotent_when_already_paid(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        service.mark_as_paid(token, order_id='order-1')
        result = service.mark_as_paid(token, order_id='order-2')  # duplicate call
        assert result is True
        # Status stays PAID, order_id stays original
        purchase = service.get_purchase(token)
        assert purchase.status == PurchaseStatus.PAID

    def test_updates_email_when_provided(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        service.mark_as_paid(token, order_id='order-999', user_email='webhook@example.com')
        purchase = service.get_purchase(token)
        assert purchase.user_email == 'webhook@example.com'


# ---------------------------------------------------------------------------
# update_email
# ---------------------------------------------------------------------------

class TestUpdateEmail:
    def test_updates_email_on_existing_purchase(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        result = service.update_email(token, 'new@example.com')
        assert result is True
        purchase = service.get_purchase(token)
        assert purchase.user_email == 'new@example.com'

    def test_returns_false_for_unknown_token(self, service: PurchaseService):
        result = service.update_email('ghost-token', 'x@example.com')
        assert result is False


# ---------------------------------------------------------------------------
# Webhook idempotency
# ---------------------------------------------------------------------------

class TestWebhookIdempotency:
    def test_not_processed_initially(self, service: PurchaseService):
        assert service.is_webhook_processed('evt-001') is False

    def test_processed_after_marking(self, service: PurchaseService):
        service.mark_webhook_processed('evt-001')
        assert service.is_webhook_processed('evt-001') is True

    def test_different_event_ids_tracked_independently(self, service: PurchaseService):
        service.mark_webhook_processed('evt-A')
        assert service.is_webhook_processed('evt-A') is True
        assert service.is_webhook_processed('evt-B') is False

    def test_marking_same_event_twice_is_idempotent(self, service: PurchaseService):
        """Duplicate calls must not raise and must not double-count."""
        service.mark_webhook_processed('evt-dup')
        service.mark_webhook_processed('evt-dup')
        assert service.is_webhook_processed('evt-dup') is True
        stats = service.get_stats()
        assert stats['webhook_ids_tracked'] == 1

    def test_bounded_set_evicts_oldest_entries(self, service: PurchaseService):
        """Set must not grow beyond _MAX_WEBHOOK_IDS; oldest entries evicted."""
        store: MemoryPurchaseStore = service._store  # type: ignore[assignment]
        cap = store._MAX_WEBHOOK_IDS

        # Fill to cap
        for i in range(cap):
            store.mark_webhook_processed(f'evt-{i}')

        assert len(store._processed_webhook_ids) == cap

        # The very first event should still be present (at cap, not yet evicted)
        assert store.is_webhook_processed('evt-0') is True

        # Adding one more should evict the oldest (evt-0)
        store.mark_webhook_processed(f'evt-{cap}')
        assert len(store._processed_webhook_ids) == cap
        assert store.is_webhook_processed('evt-0') is False
        assert store.is_webhook_processed(f'evt-{cap}') is True

    def test_bounded_set_never_exceeds_cap(self, service: PurchaseService):
        """Inserting 2x cap entries must keep set at exactly cap."""
        store: MemoryPurchaseStore = service._store  # type: ignore[assignment]
        cap = store._MAX_WEBHOOK_IDS

        for i in range(cap * 2):
            store.mark_webhook_processed(f'overflow-evt-{i}')

        assert len(store._processed_webhook_ids) == cap


# ---------------------------------------------------------------------------
# cleanup_expired
# ---------------------------------------------------------------------------

class TestCleanupExpired:
    def test_cleanup_returns_zero_when_nothing_expired(self, service: PurchaseService):
        service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        cleaned = service.cleanup_expired()
        assert cleaned == 0

    def test_cleanup_removes_expired_unpaid_purchase(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)

        # Mock created_at to be way in the past (2 hours ago)
        purchase = service.get_purchase(token)
        purchase.created_at = time.time() - 7200  # 2 hours ago, > 1h expiry

        cleaned = service.cleanup_expired()
        assert cleaned == 1
        assert service.get_purchase(token) is None

    def test_cleanup_removes_expired_paid_purchase(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        service.mark_as_paid(token, order_id='order-exp')

        # Fake paid_at to be 49 hours ago
        purchase = service.get_purchase(token)
        purchase.paid_at = time.time() - (49 * 3600)

        cleaned = service.cleanup_expired()
        assert cleaned == 1
        assert service.get_purchase(token) is None

    def test_cleanup_does_not_remove_valid_paid_purchase(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        service.mark_as_paid(token, order_id='order-valid')

        cleaned = service.cleanup_expired()
        assert cleaned == 0
        assert service.get_purchase(token) is not None


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

class TestGetStats:
    def test_stats_empty_service(self, service: PurchaseService):
        stats = service.get_stats()
        assert stats['total'] == 0
        assert stats['pending'] == 0
        assert stats['paid'] == 0

    def test_stats_with_pending_purchase(self, service: PurchaseService):
        service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        stats = service.get_stats()
        assert stats['total'] == 1
        assert stats['pending'] == 1
        assert stats['paid'] == 0

    def test_stats_with_paid_purchase(self, service: PurchaseService):
        token = service.create_purchase(SAMPLE_HD, SAMPLE_PREVIEW, SAMPLE_ORIGINAL)
        service.mark_as_paid(token, order_id='x')
        stats = service.get_stats()
        assert stats['total'] == 1
        assert stats['pending'] == 0
        assert stats['paid'] == 1

    def test_stats_webhook_ids_tracked(self, service: PurchaseService):
        service.mark_webhook_processed('evt-1')
        service.mark_webhook_processed('evt-2')
        stats = service.get_stats()
        assert stats['webhook_ids_tracked'] == 2


# ---------------------------------------------------------------------------
# PendingPurchase.is_expired / time_remaining
# ---------------------------------------------------------------------------

class TestPendingPurchaseExpiry:
    def _make_purchase(self, **kwargs) -> PendingPurchase:
        return PendingPurchase(
            token='test-token',
            image_data=SAMPLE_HD,
            preview_data=SAMPLE_PREVIEW,
            original_data=SAMPLE_ORIGINAL,
            **kwargs
        )

    def test_fresh_purchase_is_not_expired(self):
        p = self._make_purchase()
        assert p.is_expired is False

    def test_unpaid_purchase_expires_after_1_hour(self):
        p = self._make_purchase(created_at=time.time() - 3601)
        assert p.is_expired is True

    def test_paid_purchase_expires_after_48_hours(self):
        p = self._make_purchase(
            status=PurchaseStatus.PAID,
            paid_at=time.time() - (48 * 3600 + 1)
        )
        assert p.is_expired is True

    def test_paid_purchase_not_expired_within_48_hours(self):
        p = self._make_purchase(
            status=PurchaseStatus.PAID,
            paid_at=time.time() - 3600  # Only 1 hour ago
        )
        assert p.is_expired is False

    def test_time_remaining_is_positive_for_fresh_purchase(self):
        p = self._make_purchase()
        assert p.time_remaining > 0

    def test_time_remaining_is_zero_for_expired_purchase(self):
        p = self._make_purchase(created_at=time.time() - 7200)
        assert p.time_remaining == 0
