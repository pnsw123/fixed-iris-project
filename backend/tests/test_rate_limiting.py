"""
Tests for rate limiting on GPU-intensive and download endpoints.

Validates that SlowAPI limits are wired correctly:
  - POST /api/v1/process-iris — 5/minute per IP
  - POST /api/download-hd   — 10/minute per IP

These are unit-level tests that monkey-patch the pipeline and purchase
service so no real GPU/model code runs.

Security note (issue #126):
    Rate limiting uses ``request.client.host`` (TCP peer), NOT
    ``X-Forwarded-For``.  Tests control the peer address via
    Starlette TestClient's ``client=(host, port)`` constructor arg,
    not via HTTP headers.  This mirrors the real security model:
    headers are ignored; only the real TCP connection matters.
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# App import — must happen after monkey-patching heavy services
# ---------------------------------------------------------------------------

def _make_app():
    """Import fastapi app with GPU services stubbed out."""
    with (
        patch("app.IrisSAMService"),
        patch("app.RealESRGANService"),
        patch("app.IrisPipelineService"),
    ):
        from app import app as fastapi_app  # noqa: PLC0415
        return fastapi_app


@pytest.fixture()
def client():
    """TestClient with default peer 1.2.3.4."""
    app = _make_app()
    with TestClient(app, raise_server_exceptions=False, client=("1.2.3.4", 12345)) as c:
        yield c


def _client_for_ip(ip: str) -> TestClient:
    """Return a TestClient whose TCP peer is set to ``ip``."""
    app = _make_app()
    return TestClient(app, raise_server_exceptions=False, client=(ip, 12345))


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

        # Pipeline service is not started (models not loaded), so we'll get 500,
        # but SlowAPI injects rate-limit headers even on error responses.
        resp = client.post(
            "/api/v1/process-iris",
            files={"image": ("eye.png", fake_png, "image/png")},
            data={"return_mask": "false"},
            # No X-Forwarded-For — rate key comes from TCP peer set in fixture.
        )
        # 429 = rate limited, 500 = models not loaded — both are acceptable here
        assert resp.status_code in (200, 422, 429, 500)
        # SlowAPI injects the header even on error responses
        assert "x-ratelimit-limit" in resp.headers or resp.status_code == 429

    def test_sixth_request_returns_429(self):
        """6th request from same TCP peer within a minute must be rejected 429."""
        fake_png = _make_fake_image_bytes()

        with _client_for_ip("10.0.0.1") as c:
            responses = []
            for _ in range(6):
                r = c.post(
                    "/api/v1/process-iris",
                    files={"image": ("eye.png", fake_png, "image/png")},
                    data={"return_mask": "false"},
                )
                responses.append(r.status_code)

        # At least one of the 6 requests must have been rate-limited
        assert 429 in responses, (
            f"Expected 429 after 5 requests but got statuses: {responses}"
        )

    def test_different_ips_not_shared(self):
        """Rate limit is per-IP — different TCP peers must not share quota."""
        fake_png = _make_fake_image_bytes()

        # Exhaust IP A's quota
        with _client_for_ip("192.168.1.1") as c_a:
            for _ in range(6):
                c_a.post(
                    "/api/v1/process-iris",
                    files={"image": ("eye.png", fake_png, "image/png")},
                    data={},
                )

        # IP B's first request must not be 429
        with _client_for_ip("192.168.1.2") as c_b:
            r = c_b.post(
                "/api/v1/process-iris",
                files={"image": ("eye.png", fake_png, "image/png")},
                data={},
            )
        assert r.status_code != 429, (
            "Rate limit of IP A must not bleed into IP B"
        )

    def test_x_forwarded_for_header_ignored(self):
        """Spoofed X-Forwarded-For must NOT affect the rate-limit key.

        All 6 requests come from the same TCP peer and must be rate-limited
        regardless of what X-Forwarded-For claims.
        """
        fake_png = _make_fake_image_bytes()

        with _client_for_ip("10.0.0.99") as c:
            responses = []
            for i in range(6):
                # Rotate the X-Forwarded-For header on each request —
                # if the old code were in place, each would be a "new" IP;
                # with the fix, the TCP peer (10.0.0.99) is always the key.
                r = c.post(
                    "/api/v1/process-iris",
                    files={"image": ("eye.png", fake_png, "image/png")},
                    data={"return_mask": "false"},
                    headers={"X-Forwarded-For": f"5.5.5.{i}"},
                )
                responses.append(r.status_code)

        # Rate limit must still fire despite rotating headers
        assert 429 in responses, (
            "X-Forwarded-For rotation must NOT bypass rate limiting. "
            f"Got statuses: {responses}"
        )


# ---------------------------------------------------------------------------
# /api/download-hd — rate limit: 10/minute
# ---------------------------------------------------------------------------

class TestDownloadHdRateLimit:
    """Rate-limit guard on the 30-second polling download endpoint."""

    def test_eleventh_request_returns_429(self):
        """11th download request from same TCP peer within a minute must be 429."""
        with _client_for_ip("10.0.0.2") as c:
            responses = []
            for _ in range(11):
                r = c.post(
                    "/api/download-hd",
                    json={"token": "fake-token-does-not-exist"},
                )
                responses.append(r.status_code)

        # Tokens don't exist → 404, but 11th must be 429
        assert 429 in responses, (
            f"Expected 429 after 10 requests but got statuses: {responses}"
        )

    def test_rate_limit_does_not_fire_within_quota(self):
        """First 10 requests must not return 429."""
        with _client_for_ip("10.0.0.3") as c:
            responses = []
            for _ in range(10):
                r = c.post(
                    "/api/download-hd",
                    json={"token": "no-such-token"},
                )
                responses.append(r.status_code)

        assert 429 not in responses, (
            f"Should not rate-limit within quota. Got: {responses}"
        )
