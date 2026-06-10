"""Shared SlowAPI limiter instance — import here to avoid circular imports.

Security note (issue #126):
    ``get_remote_address`` from slowapi reads ``X-Forwarded-For``, which any
    client can spoof to rotate IPs and bypass rate limits.

    ``get_client_host`` reads ``request.client.host`` — the real TCP peer
    address negotiated by the OS.  It cannot be forged by HTTP headers.

    When the app runs behind a trusted reverse-proxy (e.g. Render's load
    balancer) and ``TRUSTED_PROXY=true`` is set in the environment, Starlette's
    ``ProxyHeadersMiddleware`` (added in ``app.py``) rewrites
    ``request.client.host`` to the value from the *first* ``X-Forwarded-For``
    entry before this function ever runs — so the correct real-client IP is
    used for rate limiting without trusting arbitrary caller-supplied headers.
"""

from starlette.requests import Request
from slowapi import Limiter


def get_client_host(request: Request) -> str:
    """Return the TCP-peer host as the rate-limit key.

    This is safe against ``X-Forwarded-For`` spoofing.  When
    ``ProxyHeadersMiddleware`` is active it has already replaced
    ``request.client.host`` with the real client IP before this runs.
    """
    if request.client is None:
        # Should never happen in practice; fall back to a sentinel so the
        # limiter still functions rather than raising AttributeError.
        return "unknown"
    return request.client.host


limiter = Limiter(key_func=get_client_host)
