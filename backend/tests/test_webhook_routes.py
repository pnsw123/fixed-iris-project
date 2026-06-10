"""
Tests for api/webhook_routes.py — verify_signature.

Regression coverage for issue #79:
  verify_signature must return bool, never raise TypeError,
  even before the .hexdigest() fix was applied.

Regression coverage for issue #119:
  Webhook handler must parse JSON from the already-read body bytes
  (json.loads(body)) not via request.json(), ensuring the same bytes
  used for HMAC verification are parsed — no silent divergence.
"""

import hmac
import hashlib
import inspect
import json
import pytest
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.webhook_routes import verify_signature


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SECRET = "test-webhook-secret-abc123"
PAYLOAD = b'{"meta":{"event_name":"order_created"}}'


def _make_signature(payload: bytes, secret: str) -> str:
    """Compute correct HMAC-SHA256 hex signature matching Lemon Squeezy format."""
    return hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()


# ---------------------------------------------------------------------------
# Core: return type and no TypeError (regression for #79)
# ---------------------------------------------------------------------------

class TestVerifySignatureReturnType:
    """verify_signature must always return bool — never raise TypeError."""

    def test_returns_bool_for_correct_signature(self):
        sig = _make_signature(PAYLOAD, SECRET)
        with patch("api.webhook_routes.settings") as mock_settings:
            mock_settings.lemonsqueezy_webhook_secret = SECRET
            result = verify_signature(PAYLOAD, sig)
        assert isinstance(result, bool), f"Expected bool, got {type(result)}"

    def test_returns_bool_for_wrong_signature(self):
        with patch("api.webhook_routes.settings") as mock_settings:
            mock_settings.lemonsqueezy_webhook_secret = SECRET
            result = verify_signature(PAYLOAD, "deadbeef" * 8)
        assert isinstance(result, bool), f"Expected bool, got {type(result)}"

    def test_does_not_raise_type_error(self):
        """
        Regression: before .hexdigest() fix, hmac.compare_digest(str, HMAC)
        raised TypeError. Verify no exception is raised at all.
        """
        sig = _make_signature(PAYLOAD, SECRET)
        with patch("api.webhook_routes.settings") as mock_settings:
            mock_settings.lemonsqueezy_webhook_secret = SECRET
            try:
                verify_signature(PAYLOAD, sig)
            except TypeError as exc:
                pytest.fail(
                    f"verify_signature raised TypeError — .hexdigest() missing? {exc}"
                )


# ---------------------------------------------------------------------------
# Correct signature → True
# ---------------------------------------------------------------------------

class TestVerifySignatureCorrect:
    def test_accepts_valid_signature(self):
        sig = _make_signature(PAYLOAD, SECRET)
        with patch("api.webhook_routes.settings") as mock_settings:
            mock_settings.lemonsqueezy_webhook_secret = SECRET
            assert verify_signature(PAYLOAD, sig) is True

    def test_accepts_valid_signature_for_different_payload(self):
        payload2 = b'{"meta":{"event_name":"subscription_created"}}'
        sig = _make_signature(payload2, SECRET)
        with patch("api.webhook_routes.settings") as mock_settings:
            mock_settings.lemonsqueezy_webhook_secret = SECRET
            assert verify_signature(payload2, sig) is True

    def test_accepts_valid_signature_for_empty_payload(self):
        sig = _make_signature(b"", SECRET)
        with patch("api.webhook_routes.settings") as mock_settings:
            mock_settings.lemonsqueezy_webhook_secret = SECRET
            assert verify_signature(b"", sig) is True


# ---------------------------------------------------------------------------
# Wrong signature → False
# ---------------------------------------------------------------------------

class TestVerifySignatureWrong:
    def test_rejects_wrong_signature(self):
        with patch("api.webhook_routes.settings") as mock_settings:
            mock_settings.lemonsqueezy_webhook_secret = SECRET
            assert verify_signature(PAYLOAD, "wrong" * 8) is False

    def test_rejects_empty_signature(self):
        with patch("api.webhook_routes.settings") as mock_settings:
            mock_settings.lemonsqueezy_webhook_secret = SECRET
            assert verify_signature(PAYLOAD, "") is False

    def test_rejects_signature_for_different_secret(self):
        sig_other = _make_signature(PAYLOAD, "other-secret")
        with patch("api.webhook_routes.settings") as mock_settings:
            mock_settings.lemonsqueezy_webhook_secret = SECRET
            assert verify_signature(PAYLOAD, sig_other) is False

    def test_rejects_signature_for_different_payload(self):
        sig = _make_signature(b"different-payload", SECRET)
        with patch("api.webhook_routes.settings") as mock_settings:
            mock_settings.lemonsqueezy_webhook_secret = SECRET
            assert verify_signature(PAYLOAD, sig) is False

    def test_rejects_signature_with_extra_whitespace(self):
        sig = _make_signature(PAYLOAD, SECRET)
        with patch("api.webhook_routes.settings") as mock_settings:
            mock_settings.lemonsqueezy_webhook_secret = SECRET
            assert verify_signature(PAYLOAD, sig + " ") is False


# ---------------------------------------------------------------------------
# Secret not configured → False (security: reject if misconfigured)
# ---------------------------------------------------------------------------

class TestVerifySignatureNoSecret:
    def test_returns_false_when_secret_is_none(self):
        with patch("api.webhook_routes.settings") as mock_settings:
            mock_settings.lemonsqueezy_webhook_secret = None
            assert verify_signature(PAYLOAD, "any-sig") is False

    def test_returns_false_when_secret_is_empty_string(self):
        with patch("api.webhook_routes.settings") as mock_settings:
            mock_settings.lemonsqueezy_webhook_secret = ""
            assert verify_signature(PAYLOAD, "any-sig") is False


# ---------------------------------------------------------------------------
# Timing-safe: compare_digest used (not ==)
# ---------------------------------------------------------------------------

class TestTimingSafety:
    def test_uses_compare_digest_not_equality(self):
        """
        Confirm verify_signature uses hmac.compare_digest for constant-time
        comparison, preventing timing attacks. We verify indirectly by checking
        the function signature calls compare_digest (code review) and that
        correct + incorrect diverge as expected.
        """
        import inspect
        import api.webhook_routes as mod
        source = inspect.getsource(mod.verify_signature)
        assert "compare_digest" in source, (
            "verify_signature must use hmac.compare_digest for timing-safe comparison"
        )
        assert ".hexdigest()" in source, (
            "verify_signature must call .hexdigest() on hmac.new() — "
            "without it, compare_digest receives an HMAC object not a str, "
            "raising TypeError (regression #79)"
        )


# ---------------------------------------------------------------------------
# Regression #119: webhook handler parses JSON from body bytes, not
# request.json(), so HMAC-verified bytes == parsed bytes (no divergence).
# ---------------------------------------------------------------------------

class TestWebhookBodyParseRegression:
    """
    Regression for issue #119.

    lemon_squeezy_webhook() must use json.loads(body) — not request.json() —
    so that the bytes verified by HMAC are identical to the bytes parsed.
    request.json() re-reads independently and can fail silently if the
    content-type is absent or encoding differs from UTF-8.
    """

    def test_handler_uses_json_loads_not_request_json(self):
        """Source must call json.loads(body), not await request.json()."""
        import api.webhook_routes as mod
        source = inspect.getsource(mod.lemon_squeezy_webhook)
        assert "json.loads(body)" in source, (
            "lemon_squeezy_webhook must parse JSON via json.loads(body) "
            "(same bytes used for HMAC) — not request.json() (regression #119)"
        )
        assert "await request.json()" not in source, (
            "lemon_squeezy_webhook must NOT use await request.json() — "
            "it re-reads body independently and can diverge from HMAC bytes "
            "(regression #119)"
        )

    def test_json_loads_parses_valid_body_correctly(self):
        """json.loads on the body bytes returns correct dict."""
        payload = b'{"meta":{"event_name":"order_created"},"data":{"id":"99","attributes":{"status":"paid"}}}'
        result = json.loads(payload)
        assert result["meta"]["event_name"] == "order_created"
        assert result["data"]["id"] == "99"
        assert result["data"]["attributes"]["status"] == "paid"

    def test_json_loads_raises_on_non_utf8_body(self):
        """
        json.loads raises ValueError for invalid JSON / bad encoding —
        making the error explicit rather than silent (unlike request.json()
        which can silently swallow encoding errors in some FastAPI versions).
        """
        bad_body = b"\xff\xfe not valid utf-8 json"
        with pytest.raises((json.JSONDecodeError, UnicodeDecodeError)):
            json.loads(bad_body)

    def test_import_json_present_in_module(self):
        """Module must import stdlib json (required for json.loads)."""
        import api.webhook_routes as mod
        source = inspect.getsource(mod)
        assert "import json" in source, (
            "webhook_routes.py must import json at module level (regression #119)"
        )
