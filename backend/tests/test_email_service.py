"""
Tests for services/email_service.py — JWT token creation/decoding and email sending.

Coverage:
- create_download_token: round-trip, payload fields, expiry encoding
- decode_download_token: valid token, expired token, tampered token, wrong secret
- send_download_email: no API key returns False, httpx 202 returns True,
  httpx non-202 returns False, httpx exception returns False
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import jwt as pyjwt

# Patch settings before importing the module under test so the singleton
# picks up the test JWT secret.
TEST_JWT_SECRET = "test-jwt-secret-for-unit-tests"

with patch.dict(os.environ, {"JWT_SECRET_KEY": TEST_JWT_SECRET}):
    from services.email_service import (
        create_download_token,
        decode_download_token,
        send_download_email,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_secret():
    """Context manager: patch settings.jwt_secret_key to TEST_JWT_SECRET."""
    return patch("services.email_service.settings.jwt_secret_key", TEST_JWT_SECRET)


# ---------------------------------------------------------------------------
# create_download_token
# ---------------------------------------------------------------------------

class TestCreateDownloadToken:
    def test_returns_string(self):
        with _patch_secret():
            token = create_download_token("img-token-abc", "order-123")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_payload_contains_image_token(self):
        with _patch_secret():
            token = create_download_token("img-token-xyz", "order-456")
            payload = pyjwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"])
        assert payload["image_token"] == "img-token-xyz"

    def test_payload_contains_order_id(self):
        with _patch_secret():
            token = create_download_token("img-token-xyz", "order-456")
            payload = pyjwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"])
        assert payload["order_id"] == "order-456"

    def test_default_expiry_is_48_hours(self):
        before = datetime.now(tz=timezone.utc)
        with _patch_secret():
            token = create_download_token("img-t", "ord-1")
            payload = pyjwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        delta = exp - before
        # Allow 5-second slack
        assert timedelta(hours=47, seconds=55) < delta < timedelta(hours=48, seconds=5)

    def test_custom_expiry_hours(self):
        before = datetime.now(tz=timezone.utc)
        with _patch_secret():
            token = create_download_token("img-t", "ord-1", hours=24)
            payload = pyjwt.decode(token, TEST_JWT_SECRET, algorithms=["HS256"])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        delta = exp - before
        assert timedelta(hours=23, seconds=55) < delta < timedelta(hours=24, seconds=5)

    def test_each_call_can_produce_different_token(self):
        """Different inputs → different tokens (trivially true for JWT with exp)."""
        with _patch_secret():
            t1 = create_download_token("img-A", "ord-1")
            t2 = create_download_token("img-B", "ord-2")
        assert t1 != t2


# ---------------------------------------------------------------------------
# decode_download_token
# ---------------------------------------------------------------------------

class TestDecodeDownloadToken:
    def _make_token(self, image_token="img-1", order_id="ord-1", hours=48):
        payload = {
            "image_token": image_token,
            "order_id": order_id,
            "exp": datetime.now(tz=timezone.utc) + timedelta(hours=hours),
        }
        return pyjwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")

    def test_valid_token_returns_dict(self):
        token = self._make_token()
        with _patch_secret():
            result = decode_download_token(token)
        assert isinstance(result, dict)

    def test_valid_token_contains_image_token(self):
        token = self._make_token(image_token="my-img")
        with _patch_secret():
            result = decode_download_token(token)
        assert result["image_token"] == "my-img"

    def test_valid_token_contains_order_id(self):
        token = self._make_token(order_id="order-789")
        with _patch_secret():
            result = decode_download_token(token)
        assert result["order_id"] == "order-789"

    def test_expired_token_returns_none(self):
        payload = {
            "image_token": "img-exp",
            "order_id": "ord-exp",
            "exp": datetime.now(tz=timezone.utc) - timedelta(seconds=1),
        }
        token = pyjwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
        with _patch_secret():
            result = decode_download_token(token)
        assert result is None

    def test_tampered_token_returns_none(self):
        token = self._make_token()
        # Corrupt last few chars
        tampered = token[:-4] + "XXXX"
        with _patch_secret():
            result = decode_download_token(tampered)
        assert result is None

    def test_wrong_secret_returns_none(self):
        # Sign with a different secret
        payload = {
            "image_token": "img-ws",
            "order_id": "ord-ws",
            "exp": datetime.now(tz=timezone.utc) + timedelta(hours=48),
        }
        token = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")
        with _patch_secret():
            result = decode_download_token(token)
        assert result is None

    def test_garbage_string_returns_none(self):
        with _patch_secret():
            result = decode_download_token("not-a-jwt-at-all")
        assert result is None

    def test_empty_string_returns_none(self):
        with _patch_secret():
            result = decode_download_token("")
        assert result is None

    def test_roundtrip_with_create_token(self):
        """create_download_token → decode_download_token must recover original fields."""
        with _patch_secret():
            token = create_download_token("img-rt", "ord-rt")
            result = decode_download_token(token)
        assert result is not None
        assert result["image_token"] == "img-rt"
        assert result["order_id"] == "ord-rt"


# ---------------------------------------------------------------------------
# send_download_email
# ---------------------------------------------------------------------------

class TestSendDownloadEmail:
    """Tests for the async send_download_email function."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_sendgrid_key(self):
        with patch("services.email_service.settings") as mock_settings:
            mock_settings.sendgrid_api_key = ""
            mock_settings.jwt_secret_key = TEST_JWT_SECRET
            mock_settings.base_url = "https://test.example.com"
            result = await send_download_email("user@example.com", "img-1", "ord-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_sendgrid_key_is_none(self):
        with patch("services.email_service.settings") as mock_settings:
            mock_settings.sendgrid_api_key = None
            mock_settings.jwt_secret_key = TEST_JWT_SECRET
            mock_settings.base_url = "https://test.example.com"
            result = await send_download_email("user@example.com", "img-1", "ord-1")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_on_sendgrid_202(self):
        mock_response = MagicMock()
        mock_response.status_code = 202

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("services.email_service.settings") as mock_settings, \
             patch("httpx.AsyncClient", return_value=mock_client):
            mock_settings.sendgrid_api_key = "SG.test-key"
            mock_settings.jwt_secret_key = TEST_JWT_SECRET
            mock_settings.base_url = "https://test.example.com"
            mock_settings.from_email = "downloads@eyedentity.com"
            result = await send_download_email("user@example.com", "img-1", "ord-1")

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_sendgrid_400(self):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("services.email_service.settings") as mock_settings, \
             patch("httpx.AsyncClient", return_value=mock_client):
            mock_settings.sendgrid_api_key = "SG.test-key"
            mock_settings.jwt_secret_key = TEST_JWT_SECRET
            mock_settings.base_url = "https://test.example.com"
            mock_settings.from_email = "downloads@eyedentity.com"
            result = await send_download_email("user@example.com", "img-1", "ord-1")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_sendgrid_401_unauthorized(self):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("services.email_service.settings") as mock_settings, \
             patch("httpx.AsyncClient", return_value=mock_client):
            mock_settings.sendgrid_api_key = "SG.bad-key"
            mock_settings.jwt_secret_key = TEST_JWT_SECRET
            mock_settings.base_url = "https://test.example.com"
            mock_settings.from_email = "downloads@eyedentity.com"
            result = await send_download_email("user@example.com", "img-1", "ord-1")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_httpx_exception(self):
        import httpx as _httpx

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=_httpx.ConnectError("connection refused"))

        with patch("services.email_service.settings") as mock_settings, \
             patch("httpx.AsyncClient", return_value=mock_client):
            mock_settings.sendgrid_api_key = "SG.test-key"
            mock_settings.jwt_secret_key = TEST_JWT_SECRET
            mock_settings.base_url = "https://test.example.com"
            mock_settings.from_email = "downloads@eyedentity.com"
            result = await send_download_email("user@example.com", "img-1", "ord-1")

        assert result is False

    @pytest.mark.asyncio
    async def test_uses_correct_recipient_email(self):
        """Verify the post call sends to the correct email address."""
        mock_response = MagicMock()
        mock_response.status_code = 202

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("services.email_service.settings") as mock_settings, \
             patch("httpx.AsyncClient", return_value=mock_client):
            mock_settings.sendgrid_api_key = "SG.test-key"
            mock_settings.jwt_secret_key = TEST_JWT_SECRET
            mock_settings.base_url = "https://test.example.com"
            mock_settings.from_email = "downloads@eyedentity.com"
            await send_download_email("target@example.com", "img-1", "ord-1")

        call_kwargs = mock_client.post.call_args.kwargs
        to_emails = call_kwargs["json"]["personalizations"][0]["to"]
        assert any(e["email"] == "target@example.com" for e in to_emails)

    @pytest.mark.asyncio
    async def test_download_url_contains_base_url(self):
        """The download link in the email must include the configured base_url."""
        mock_response = MagicMock()
        mock_response.status_code = 202

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("services.email_service.settings") as mock_settings, \
             patch("httpx.AsyncClient", return_value=mock_client):
            mock_settings.sendgrid_api_key = "SG.test-key"
            mock_settings.jwt_secret_key = TEST_JWT_SECRET
            mock_settings.base_url = "https://custom-domain.io"
            mock_settings.from_email = "downloads@eyedentity.com"
            await send_download_email("user@example.com", "img-1", "ord-1")

        call_kwargs = mock_client.post.call_args.kwargs
        html_body = call_kwargs["json"]["content"][1]["value"]
        assert "https://custom-domain.io/d/" in html_body
