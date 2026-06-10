"""
Tests for rate limiting on GPU-intensive and download endpoints.

Validates that SlowAPI limits are wired correctly:
  - POST /api/v1/process-iris — 5/minute per IP
  - POST /api/download-hd   — 10/minute per IP

These are unit-level tests that monkey-patch the pipeline and purchase
service so no real GPU/model code runs.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# App import — must happen after monkey-patching heavy services
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """Return a TestClient with models monkey-patched to avoid loading GPU code."""
    with (
        patch("app.IrisSAMService"),
        patch("app.RealESRGANService"),
        patch("app.IrisPipelineService"),
    ):
        from app import app as fastapi_app
        with TestClient(fastapi_app, raise_server_exceptions=False) as c:
            yield c


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_fake_image_bytes() -> bytes:
    """Return minimal valid PNG bytes (1×1 white pixel)."""
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# /api/v1/process-iris — rate limit: 5/minute
# ---------------------------------------------------------------------------

class TestProcessIrisRateLimit:
    """Rate-limit guard on the GPU-intensive process-iris endpoint."""

    def test_rate_limit_header_present(self, client: TestClient):
        """First request must include X-RateLimit-* headers from SlowAPI."""
        fake_png = _make_fake_image_bytes()

        # Pipeline service doesn't exist yet (not started), so we'll get 500
        # but the rate-limit headers should still be injected.
        resp = client.post(
            "/api/v1/process-iris",
            files={"image": ("eye.png", fake_png, "image/png")},
            data={"return_mask": "false"},
            headers={"X-Forwarded-For": "1.2.3.4"},
        )
        # 429 = rate limited, 500 = models not loaded — both are fine here
        assert resp.status_code in (200, 422, 429, 500)
        # SlowAPI injects the header even on error responses
        assert "x-ratelimit-limit" in resp.headers or resp.status_code == 429

    def test_sixth_request_returns_429(self, client: TestClient):
        """6th request from same IP within a minute must be rejected 429."""
        fake_png = _make_fake_image_bytes()

        responses = []
        for _ in range(6):
            r = client.post(
                "/api/v1/process-iris",
                files={"image": ("eye.png", fake_png, "image/png")},
                data={"return_mask": "false"},
                headers={"X-Forwarded-For": "10.0.0.1"},
            )
            responses.append(r.status_code)

        # At least one of the 6 requests must have been rate-limited
        assert 429 in responses, (
            f"Expected 429 after 5 requests but got statuses: {responses}"
        )

    def test_different_ips_not_shared(self, client: TestClient):
        """Rate limit is per-IP — different IPs must not share quota."""
        fake_png = _make_fake_image_bytes()

        # Exhaust IP A's quota
        for _ in range(6):
            client.post(
                "/api/v1/process-iris",
                files={"image": ("eye.png", fake_png, "image/png")},
                data={},
                headers={"X-Forwarded-For": "192.168.1.1"},
            )

        # IP B's first request must not be 429
        r = client.post(
            "/api/v1/process-iris",
            files={"image": ("eye.png", fake_png, "image/png")},
            data={},
            headers={"X-Forwarded-For": "192.168.1.2"},
        )
        assert r.status_code != 429, (
            "Rate limit of IP A must not bleed into IP B"
        )


# ---------------------------------------------------------------------------
# /api/download-hd — rate limit: 10/minute
# ---------------------------------------------------------------------------

class TestDownloadHdRateLimit:
    """Rate-limit guard on the 30-second polling download endpoint."""

    def test_eleventh_request_returns_429(self, client: TestClient):
        """11th download request from same IP within a minute must be 429."""
        responses = []
        for _ in range(11):
            r = client.post(
                "/api/download-hd",
                json={"token": "fake-token-does-not-exist"},
                headers={"X-Forwarded-For": "10.0.0.2"},
            )
            responses.append(r.status_code)

        # Tokens don't exist → 404, but 11th must be 429
        assert 429 in responses, (
            f"Expected 429 after 10 requests but got statuses: {responses}"
        )

    def test_rate_limit_does_not_fire_within_quota(self, client: TestClient):
        """First 10 requests must not return 429."""
        responses = []
        for _ in range(10):
            r = client.post(
                "/api/download-hd",
                json={"token": "no-such-token"},
                headers={"X-Forwarded-For": "10.0.0.3"},
            )
            responses.append(r.status_code)

        assert 429 not in responses, (
            f"Should not rate-limit within quota. Got: {responses}"
        )
