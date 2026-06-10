"""
Tests for api/webhook_routes.py — verify_signature.

Regression coverage for issue #79:
  verify_signature must return bool, never raise TypeError,
  even before the .hexdigest() fix was applied.
"""

import hmac
import hashlib
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
