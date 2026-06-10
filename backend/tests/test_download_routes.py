"""
Tests for api/download_routes.py — paywall download logic.

Coverage:
- POST /api/download-hd : 404 invalid token, 200+PNG immediate PAID,
  202 on 30s timeout, 410 when purchase disappears mid-poll
- GET /d/{token}        : 410 invalid/expired JWT, 404 missing purchase,
  402 unpaid purchase, 200+PNG valid paid purchase
- POST /api/update-purchase-email : 200 success, 404 unknown token
- GET /api/download-status/{token}: 200 {"ready": False} for unknown/pending,
  200 {"ready": True} for paid
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault("PURCHASE_BACKEND", "memory")

# ---------------------------------------------------------------------------
# Stub out slowapi so tests run without it installed in the test venv.
# ---------------------------------------------------------------------------
import types

def _make_slowapi_stub():
    """Return a fake slowapi module + sub-modules."""
    slowapi_mod = types.ModuleType("slowapi")

    class _FakeLimiter:
        def __init__(self, key_func=None, **kwargs):
            self._key_func = key_func

        def limit(self, rate_string):
            """Return a no-op decorator that preserves the original function."""
            def decorator(func):
                return func
            return decorator

    slowapi_mod.Limiter = _FakeLimiter

    errors_mod = types.ModuleType("slowapi.errors")
    errors_mod.RateLimitExceeded = Exception
    slowapi_mod.errors = errors_mod

    util_mod = types.ModuleType("slowapi.util")
    util_mod.get_remote_address = lambda request: "127.0.0.1"
    slowapi_mod.util = util_mod

    return slowapi_mod, errors_mod, util_mod


_slowapi, _slowapi_errors, _slowapi_util = _make_slowapi_stub()
sys.modules.setdefault("slowapi", _slowapi)
sys.modules.setdefault("slowapi.errors", _slowapi_errors)
sys.modules.setdefault("slowapi.util", _slowapi_util)

import jwt as pyjwt
from fastapi.testclient import TestClient

from services.purchase_service import PendingPurchase, PurchaseStatus


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

def _make_app():
    """Build a minimal FastAPI app with only the download router mounted."""
    from fastapi import FastAPI
    from api.download_routes import router
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture()
def client():
    app = _make_app()
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_JWT_SECRET = "test-download-routes-secret"
SAMPLE_HD = b"\x89PNG_HD_FAKE_IMAGE_DATA"
SAMPLE_PREVIEW = b"\x89PNG_PREVIEW_FAKE"
SAMPLE_ORIGINAL = b"\x89PNG_ORIGINAL_FAKE"


def _paid_purchase(token: str = "tok-paid") -> PendingPurchase:
    return PendingPurchase(
        token=token,
        image_data=SAMPLE_HD,
        preview_data=SAMPLE_PREVIEW,
        original_data=SAMPLE_ORIGINAL,
        status=PurchaseStatus.PAID,
        order_id="order-001",
        paid_at=datetime.now().timestamp(),
    )


def _pending_purchase(token: str = "tok-pending") -> PendingPurchase:
    return PendingPurchase(
        token=token,
        image_data=SAMPLE_HD,
        preview_data=SAMPLE_PREVIEW,
        original_data=SAMPLE_ORIGINAL,
        status=PurchaseStatus.PENDING,
    )


# ---------------------------------------------------------------------------
# POST /api/download-hd
# ---------------------------------------------------------------------------

class TestDownloadHd:
    def test_404_for_unknown_token(self, client):
        with patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = None
            resp = client.post("/api/download-hd", json={"token": "bad-token"})
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body

    def test_200_png_for_immediately_paid_purchase(self, client):
        """When purchase is PAID on first poll, return PNG immediately."""
        purchase = _paid_purchase("tok-immediate")
        with patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = purchase
            resp = client.post("/api/download-hd", json={"token": "tok-immediate"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content == SAMPLE_HD

    def test_200_response_has_correct_content_disposition(self, client):
        purchase = _paid_purchase("tok-cd")
        with patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = purchase
            resp = client.post("/api/download-hd", json={"token": "tok-cd"})
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "eyedentity-hd.png" in resp.headers.get("content-disposition", "")

    def test_200_response_has_no_store_cache_control(self, client):
        purchase = _paid_purchase("tok-cache")
        with patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = purchase
            resp = client.post("/api/download-hd", json={"token": "tok-cache"})
        assert "no-store" in resp.headers.get("cache-control", "")

    def test_202_when_purchase_remains_pending_throughout_poll(self, client):
        """When payment is pending, endpoint returns 202 immediately (non-blocking)."""
        purchase = _pending_purchase("tok-timeout")

        with patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = purchase
            resp = client.post("/api/download-hd", json={"token": "tok-timeout"})

        assert resp.status_code == 202
        body = resp.json()
        assert body.get("retry") is True

    def test_410_when_purchase_disappears_mid_poll(self, client):
        """If token disappears mid-poll (cleanup race), return 410."""
        pending = _pending_purchase("tok-disappear")

        call_count = {"n": 0}

        def _side_effect(token):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return pending   # first call — token exists
            return None          # subsequent calls — token gone

        with patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.side_effect = _side_effect
            resp = client.post("/api/download-hd", json={"token": "tok-disappear"})

        assert resp.status_code == 410

    def test_download_hd_requires_token_field(self, client):
        resp = client.post("/api/download-hd", json={})
        assert resp.status_code == 422

    def test_download_hd_paid_purchase_returns_hd_image_bytes(self, client):
        """Image content must exactly match what's stored in the purchase."""
        custom_hd = b"\x89PNG_CUSTOM_IMAGE_12345"
        purchase = PendingPurchase(
            token="tok-custom",
            image_data=custom_hd,
            preview_data=b"preview",
            original_data=b"orig",
            status=PurchaseStatus.PAID,
            paid_at=datetime.now().timestamp(),
        )
        with patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = purchase
            resp = client.post("/api/download-hd", json={"token": "tok-custom"})
        assert resp.content == custom_hd


# ---------------------------------------------------------------------------
# GET /d/{download_token}  — email link download
# ---------------------------------------------------------------------------

class TestDownloadFromEmailLink:
    def test_410_html_for_invalid_jwt(self, client):
        with patch("api.download_routes.decode_download_token", return_value=None):
            resp = client.get("/d/not-a-valid-jwt")
        assert resp.status_code == 410
        assert "text/html" in resp.headers["content-type"]

    def test_410_html_mentions_expired(self, client):
        with patch("api.download_routes.decode_download_token", return_value=None):
            resp = client.get("/d/expired-token")
        # HTML should mention link expiry
        assert "xpir" in resp.text or "invalid" in resp.text.lower()

    def test_404_html_when_purchase_not_found(self, client):
        payload = {"image_token": "tok-missing", "order_id": "ord-x"}
        with patch("api.download_routes.decode_download_token", return_value=payload), \
             patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = None
            resp = client.get("/d/valid-jwt")
        assert resp.status_code == 404
        assert "text/html" in resp.headers["content-type"]

    def test_404_html_contains_order_id(self, client):
        payload = {"image_token": "tok-missing", "order_id": "ORDER-XYZ-9999"}
        with patch("api.download_routes.decode_download_token", return_value=payload), \
             patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = None
            resp = client.get("/d/valid-jwt")
        assert "ORDER-XYZ-9999" in resp.text

    def test_402_html_for_unpaid_purchase(self, client):
        payload = {"image_token": "tok-pending-email", "order_id": "ord-y"}
        purchase = _pending_purchase("tok-pending-email")
        with patch("api.download_routes.decode_download_token", return_value=payload), \
             patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = purchase
            resp = client.get("/d/valid-jwt")
        assert resp.status_code == 402
        assert "text/html" in resp.headers["content-type"]

    def test_200_png_for_valid_paid_purchase(self, client):
        payload = {"image_token": "tok-paid-email", "order_id": "ord-z"}
        purchase = _paid_purchase("tok-paid-email")
        with patch("api.download_routes.decode_download_token", return_value=payload), \
             patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = purchase
            resp = client.get("/d/valid-jwt")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content == SAMPLE_HD

    def test_200_response_has_correct_content_disposition(self, client):
        payload = {"image_token": "tok-paid-cd", "order_id": "ord-cd"}
        purchase = _paid_purchase("tok-paid-cd")
        with patch("api.download_routes.decode_download_token", return_value=payload), \
             patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = purchase
            resp = client.get("/d/valid-jwt")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "eyedentity-hd.png" in resp.headers.get("content-disposition", "")

    def test_200_response_has_no_store_cache_control(self, client):
        payload = {"image_token": "tok-paid-nocache", "order_id": "ord-nc"}
        purchase = _paid_purchase("tok-paid-nocache")
        with patch("api.download_routes.decode_download_token", return_value=payload), \
             patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = purchase
            resp = client.get("/d/valid-jwt")
        assert "no-store" in resp.headers.get("cache-control", "")


# ---------------------------------------------------------------------------
# POST /api/update-purchase-email
# ---------------------------------------------------------------------------

class TestUpdatePurchaseEmail:
    def test_200_on_successful_update(self, client):
        with patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.update_email.return_value = True
            resp = client.post(
                "/api/update-purchase-email",
                json={"token": "tok-upd", "email": "user@example.com"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"

    def test_404_when_token_not_found(self, client):
        with patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.update_email.return_value = False
            resp = client.post(
                "/api/update-purchase-email",
                json={"token": "ghost-token", "email": "x@example.com"},
            )
        assert resp.status_code == 404

    def test_422_on_invalid_email_format(self, client):
        resp = client.post(
            "/api/update-purchase-email",
            json={"token": "tok-x", "email": "not-an-email"},
        )
        assert resp.status_code == 422

    def test_422_when_missing_token(self, client):
        resp = client.post(
            "/api/update-purchase-email",
            json={"email": "user@example.com"},
        )
        assert resp.status_code == 422

    def test_422_when_missing_email(self, client):
        resp = client.post(
            "/api/update-purchase-email",
            json={"token": "tok-x"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/download-status/{token}
# ---------------------------------------------------------------------------

class TestDownloadStatus:
    """
    Note: endpoint intentionally returns 200 + {"ready": False} for unknown tokens
    (anti-enumeration design — prevents leaking whether a token exists).
    """

    def test_200_ready_false_for_unknown_token(self, client):
        """Unknown tokens return 200 with ready=False (anti-enumeration)."""
        with patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = None
            resp = client.get("/api/download-status/unknown-tok")
        assert resp.status_code == 200
        assert resp.json()["ready"] is False

    def test_200_ready_false_for_pending_purchase(self, client):
        purchase = _pending_purchase("tok-status-pending")
        with patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = purchase
            resp = client.get("/api/download-status/tok-status-pending")
        assert resp.status_code == 200
        assert resp.json()["ready"] is False

    def test_200_ready_true_for_paid_purchase(self, client):
        purchase = _paid_purchase("tok-status-paid")
        with patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = purchase
            resp = client.get("/api/download-status/tok-status-paid")
        assert resp.status_code == 200
        assert resp.json()["ready"] is True

    def test_response_only_contains_ready_field(self, client):
        """Endpoint must NOT leak status, email, or timing info (anti-enumeration)."""
        purchase = _paid_purchase("tok-anti-enum")
        with patch("api.download_routes.purchase_service") as mock_svc:
            mock_svc.get_purchase.return_value = purchase
            resp = client.get("/api/download-status/tok-anti-enum")
        body = resp.json()
        # Only "ready" should be present — no status, has_email, time_remaining
        assert set(body.keys()) == {"ready"}
