from pydantic_settings import BaseSettings
from pydantic import ConfigDict, field_validator
from typing import List
import logging
import re

logger = logging.getLogger(__name__)

# Patterns that indicate dev/LAN origins that must never reach production
_DEV_ORIGIN_PATTERN = re.compile(
    r"https?://(localhost|127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|192\.168\.\d+\.\d+)(:\d+)?$"
)


class Settings(BaseSettings):
    """Application settings loaded from .env"""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    reload: bool = False

    # Models
    iris_sam_model: str = "./models/IrisSAM_model.pt"
    # Base SAM checkpoint (used if compatible with the fine-tuned weights)
    sam_checkpoint: str = "./models/sam_vit_b_01ec64.pth"
    # SAM backbone to use: "auto" (detect from fine-tuned weights), or one of ["vit_b", "vit_l", "vit_h"]
    sam_model_type: str = "auto"
    esrgan_model: str = "./models/realesr-general-x4v3.pth"

    # Device
    device: str = "mps"  # mps, cuda, or cpu

    # CORS — localhost only by default (safe for local dev).
    # In production set CORS_ORIGINS env var to the real frontend origin(s), e.g.:
    #   CORS_ORIGINS='["https://app.eyedentity.com"]'
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:3005",
        "https://localhost:3000",
        "https://localhost:3005",
    ]

    # Runtime environment — set ENV=production on deployed servers
    env: str = "development"

    # Logging
    log_level: str = "INFO"

    # Redis — required when PURCHASE_BACKEND=redis
    # If unset, the image store uses in-memory storage (dev only).
    redis_url: str = ""

    # Image storage backend: "memory" (default, dev) or "redis" (production).
    # Env var kept as PURCHASE_BACKEND for deployment compatibility.
    purchase_backend: str = "memory"

    # Trusted reverse-proxy flag (issue #126).
    # Set TRUSTED_PROXY=true on Render (or any deployment where a single
    # trusted load-balancer prepends the real client IP to X-Forwarded-For).
    # When true, Starlette's ProxyHeadersMiddleware rewrites request.client
    # so rate limiting uses the real client IP instead of the LB's IP.
    # Leave false (default) for local dev and direct-access deployments.
    trusted_proxy: bool = False

    @field_validator("cors_origins")
    @classmethod
    def _no_lan_ips_in_origins(cls, origins: List[str]) -> List[str]:
        """Strip any LAN/private IP origins — they must never be in the list."""
        safe: List[str] = []
        for origin in origins:
            if re.search(r"10\.\d+\.\d+\.\d+", origin) or re.search(
                r"172\.(1[6-9]|2\d|3[01])\.\d+\.\d+", origin
            ):
                logger.warning(
                    "SECURITY: Removed private/LAN IP from CORS origins: %s. "
                    "Use CORS_ORIGINS env var with real domain(s) in production.",
                    origin,
                )
            else:
                safe.append(origin)
        return safe

    def assert_production_cors(self) -> None:
        """Call at startup when ENV=production to enforce explicit CORS config.

        Raises ValueError if cors_origins still contains only dev defaults,
        preventing accidental deployment with localhost origins.
        """
        if self.env.lower() != "production":
            return
        dev_only = all(_DEV_ORIGIN_PATTERN.match(o) for o in self.cors_origins)
        if dev_only:
            raise ValueError(
                "SECURITY: ENV=production but CORS_ORIGINS is set to dev defaults "
                "(localhost/LAN). Set CORS_ORIGINS to your real frontend origin(s)."
            )

    model_config = ConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()

# Enforce production CORS guard at import time so the server refuses to start
# with insecure defaults rather than silently serving the wrong CORS policy.
settings.assert_production_cors()
