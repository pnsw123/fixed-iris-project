"""Tests for backend/config.py — CORS security rules (issue #127)."""

import re
import pytest


# ---------------------------------------------------------------------------
# Default CORS list — no private IPs
# ---------------------------------------------------------------------------

class TestDefaultCorsOrigins:
    def test_no_lan_ip_in_defaults(self):
        """Default cors_origins must NOT contain any 10.x.x.x addresses."""
        from config import settings
        for origin in settings.cors_origins:
            assert not re.search(r"10\.\d+\.\d+\.\d+", origin), (
                f"LAN IP found in default CORS: {origin}"
            )

    def test_default_contains_only_localhost(self):
        """Default cors_origins should only contain localhost entries."""
        from config import settings
        for origin in settings.cors_origins:
            assert "localhost" in origin, (
                f"Non-localhost origin in default CORS: {origin}"
            )

    def test_default_has_expected_entries(self):
        """Default list covers http and https localhost on both ports."""
        from config import settings
        expected = {
            "http://localhost:3000",
            "http://localhost:3005",
            "https://localhost:3000",
            "https://localhost:3005",
        }
        assert expected.issubset(set(settings.cors_origins))


# ---------------------------------------------------------------------------
# Validator strips LAN IPs even when provided via env/config
# ---------------------------------------------------------------------------

class TestCorsValidator:
    def test_validator_strips_lan_ip(self):
        """Validator must remove 10.x.x.x entries supplied at instantiation."""
        from config import Settings
        s = Settings(
            cors_origins=[
                "http://localhost:3000",
                "http://10.0.0.104:3000",
                "https://10.0.0.104:3005",
            ]
        )
        for origin in s.cors_origins:
            assert not re.search(r"10\.\d+\.\d+\.\d+", origin), (
                f"LAN IP survived validator: {origin}"
            )

    def test_validator_keeps_public_origins(self):
        """Validator must NOT remove legitimate public domain origins."""
        from config import Settings
        s = Settings(cors_origins=["https://app.eyedentity.com"])
        assert "https://app.eyedentity.com" in s.cors_origins

    def test_validator_strips_172_range(self):
        """Validator removes RFC-1918 172.16-31.x.x ranges too."""
        from config import Settings
        s = Settings(cors_origins=["http://172.20.0.5:3000", "http://localhost:3000"])
        for origin in s.cors_origins:
            assert not re.search(r"172\.(1[6-9]|2\d|3[01])\.\d+\.\d+", origin)


# ---------------------------------------------------------------------------
# Production guard
# ---------------------------------------------------------------------------

class TestProductionCorsGuard:
    def test_production_raises_on_dev_defaults(self):
        """assert_production_cors() must raise when ENV=production + localhost defaults."""
        from config import Settings
        s = Settings(
            env="production",
            cors_origins=["http://localhost:3000", "https://localhost:3005"],
        )
        with pytest.raises(ValueError, match="SECURITY"):
            s.assert_production_cors()

    def test_production_passes_with_real_domain(self):
        """assert_production_cors() must NOT raise when given a real domain."""
        from config import Settings
        s = Settings(
            env="production",
            cors_origins=["https://app.eyedentity.com"],
        )
        s.assert_production_cors()  # should not raise

    def test_development_no_raise_on_localhost(self):
        """assert_production_cors() must NOT raise when ENV=development."""
        from config import Settings
        s = Settings(
            env="development",
            cors_origins=["http://localhost:3000"],
        )
        s.assert_production_cors()  # should not raise
