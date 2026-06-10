"""
Tests for api/download_routes.py — free token-based download.

Coverage:
- POST /api/download-hd       : 404 unknown token, 200 + PNG HD bytes,
                                content-disposition + no-store headers, 422 missing token
- POST /api/download-original : 404 unknown token, 200 + PNG original bytes
"""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault("PURCHASE_BACKEND", "memory")


# ---------------------------------------------------------------------------
# Stub out slowapi so tests run without it installed in the test venv.
# ---------------------------------------------------------------------------

def _make_slowapi_stub():
    slowapi_mod = types.ModuleType("slowapi")

    class _FakeLimiter:
        def __init__(self, key_func=None, **kwargs):
            self._key_func = key_func

        def limit(self, rate_string):
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

from fastapi.testclient import TestClient
from unittest.mock import patch

from services.image_store import StoredImage


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

SAMPLE_HD = b"\x89PNG_HD_FAKE_IMAGE_DATA"
SAMPLE_PREVIEW = b"\x89PNG_PREVIEW_FAKE"
SAMPLE_ORIGINAL = b"\x89PNG_ORIGINAL_FAKE"


def _stored(token: str = "tok-1", hd: bytes = SAMPLE_HD, original: bytes = SAMPLE_ORIGINAL) -> StoredImage:
    return StoredImage(
        token=token,
        hd_data=hd,
        preview_data=SAMPLE_PREVIEW,
        original_data=original,
    )


# ---------------------------------------------------------------------------
# POST /api/download-hd
# ---------------------------------------------------------------------------

class TestDownloadHd:
    def test_404_for_unknown_token(self, client):
        with patch("api.download_routes.image_store") as mock_store:
            mock_store.get.return_value = None
            resp = client.post("/api/download-hd", json={"token": "no-such-token"})
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_200_png_for_known_token(self, client):
        with patch("api.download_routes.image_store") as mock_store:
            mock_store.get.return_value = _stored("tok-hd")
            resp = client.post("/api/download-hd", json={"token": "tok-hd"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content == SAMPLE_HD

    def test_200_response_has_correct_content_disposition(self, client):
        with patch("api.download_routes.image_store") as mock_store:
            mock_store.get.return_value = _stored("tok-cd")
            resp = client.post("/api/download-hd", json={"token": "tok-cd"})
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert "eyedentity-hd.png" in cd

    def test_200_response_has_no_store_cache_control(self, client):
        with patch("api.download_routes.image_store") as mock_store:
            mock_store.get.return_value = _stored("tok-cache")
            resp = client.post("/api/download-hd", json={"token": "tok-cache"})
        assert "no-store" in resp.headers.get("cache-control", "")

    def test_returns_exact_hd_bytes(self, client):
        custom_hd = b"\x89PNG_CUSTOM_IMAGE_12345"
        with patch("api.download_routes.image_store") as mock_store:
            mock_store.get.return_value = _stored("tok-custom", hd=custom_hd)
            resp = client.post("/api/download-hd", json={"token": "tok-custom"})
        assert resp.content == custom_hd

    def test_download_hd_requires_token_field(self, client):
        resp = client.post("/api/download-hd", json={})
        assert resp.status_code == 422

    def test_download_hd_rejects_empty_token(self, client):
        resp = client.post("/api/download-hd", json={"token": ""})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/download-original
# ---------------------------------------------------------------------------

class TestDownloadOriginal:
    def test_404_for_unknown_token(self, client):
        with patch("api.download_routes.image_store") as mock_store:
            mock_store.get.return_value = None
            resp = client.post("/api/download-original", json={"token": "no-such-token"})
        assert resp.status_code == 404
        assert "error" in resp.json()

    def test_200_png_for_known_token(self, client):
        with patch("api.download_routes.image_store") as mock_store:
            mock_store.get.return_value = _stored("tok-orig")
            resp = client.post("/api/download-original", json={"token": "tok-orig"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.content == SAMPLE_ORIGINAL

    def test_200_response_has_correct_content_disposition(self, client):
        with patch("api.download_routes.image_store") as mock_store:
            mock_store.get.return_value = _stored("tok-orig-cd")
            resp = client.post("/api/download-original", json={"token": "tok-orig-cd"})
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert "eyedentity-original.png" in cd

    def test_returns_exact_original_bytes(self, client):
        custom_orig = b"\x89PNG_ORIGINAL_CUSTOM_99"
        with patch("api.download_routes.image_store") as mock_store:
            mock_store.get.return_value = _stored("tok-o", original=custom_orig)
            resp = client.post("/api/download-original", json={"token": "tok-o"})
        assert resp.content == custom_orig

    def test_download_original_requires_token_field(self, client):
        resp = client.post("/api/download-original", json={})
        assert resp.status_code == 422
