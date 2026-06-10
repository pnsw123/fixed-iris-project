"""
Download Routes - Serves processed iris images for free, by token.

After ``/api/v1/process-iris`` returns a ``download_token``, the frontend
fetches the two images with that token:

  POST /api/download-hd        -> HD enhanced PNG
  POST /api/download-original  -> original capture PNG

Both endpoints return 200 + PNG when the token is found, or 404 once it has
expired (images are kept for one hour). There is no payment or account step.
"""

import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services.image_store import image_store
from rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["downloads"])


class DownloadRequest(BaseModel):
    """Request body for the download endpoints."""

    token: str = Field(
        min_length=1,
        max_length=128,
        description="Opaque download token returned by /api/v1/process-iris",
    )


def _png_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="image/png",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Cache-Control": "no-store",
        },
    )


@router.post("/api/download-hd")
@limiter.limit("10/minute")
async def download_hd(request: Request, body: DownloadRequest):
    """Return the HD enhanced image for a token, or 404 if it has expired."""
    image = image_store.get(body.token)
    if not image:
        return JSONResponse({"error": "Invalid or expired token"}, status_code=404)
    logger.info(f"Serving HD download: {body.token[:8]}...")
    return _png_response(image.hd_data, "eyedentity-hd.png")


@router.post("/api/download-original")
@limiter.limit("10/minute")
async def download_original(request: Request, body: DownloadRequest):
    """Return the original capture image for a token, or 404 if it has expired."""
    image = image_store.get(body.token)
    if not image:
        return JSONResponse({"error": "Invalid or expired token"}, status_code=404)
    logger.info(f"Serving original download: {body.token[:8]}...")
    return _png_response(image.original_data, "eyedentity-original.png")
