"""
Download Routes - Serves HD images after payment verification.

Endpoints:
1. POST /api/download-hd  - In-browser download; returns 202 + Retry-After if
                            payment not yet confirmed.  Callers should poll
                            GET /api/download-status/{token} (preferred) and
                            retry once ready == true.
2. GET  /api/download-status/{token} - Non-blocking status check (preferred
                                        polling mechanism).
3. GET  /d/{token} - Email link download (JWT-verified)
"""

import logging
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel, EmailStr, Field

from services.purchase_service import purchase_service, PurchaseStatus
from services.email_service import decode_download_token
from rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["downloads"])


_UUID_V4_PATTERN = r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'


class DownloadRequest(BaseModel):
    """Request body for download endpoint."""
    token: str = Field(
        min_length=36,
        max_length=36,
        pattern=_UUID_V4_PATTERN,
        description="UUID v4 purchase token",
    )


@router.post("/api/download-hd")
@limiter.limit("10/minute")
async def download_hd(request: Request, body: DownloadRequest):
    """
    Download HD image after payment.

    Returns 200 + PNG immediately if payment is already confirmed.
    Returns 202 Accepted with a ``Retry-After`` hint if the webhook has not
    arrived yet — the caller should poll ``GET /api/download-status/{token}``
    (the preferred mechanism) and retry this endpoint once ``ready`` is true.

    Preferred polling flow (non-blocking):
        1. POST /api/download-hd  → 202 if pending
        2. GET  /api/download-status/{token}  → poll until {"ready": true}
        3. POST /api/download-hd  → 200 + image

    Returns:
        - 200 + PNG image if payment confirmed
        - 202 Accepted + Retry-After header if payment not yet confirmed
        - 404 if token not found
    """
    token = body.token

    # Check if token exists
    purchase = purchase_service.get_purchase(token)
    if not purchase:
        logger.warning(f"Download attempt with invalid token: {token[:8] if len(token) > 8 else token}...")
        return JSONResponse(
            {"error": "Invalid or expired token"},
            status_code=404
        )

    # Fast path: payment already confirmed — serve image immediately.
    if purchase.status == PurchaseStatus.PAID:
        logger.info(f"✅ Serving HD download: {token[:8]}...")
        return Response(
            content=purchase.image_data,
            media_type="image/png",
            headers={
                "Content-Disposition": "attachment; filename=eyedentity-hd.png",
                "Cache-Control": "no-store",
            }
        )

    # Payment not yet confirmed — return immediately so the HTTP connection
    # is not held open.  The frontend should poll GET /api/download-status/{token}
    # and retry this endpoint once ready == true.
    logger.info(f"⏳ Payment pending for {token[:8]}..., returning 202")
    return JSONResponse(
        {
            "error": "Payment verification pending",
            "message": (
                "Your payment is being confirmed. Poll GET /api/download-status/{token} "
                "until ready is true, then retry this endpoint. "
                "A download link has also been sent to your email."
            ),
            "poll_url": f"/api/download-status/{token}",
            "retry": True,
        },
        status_code=202,
        headers={"Retry-After": "2"},
    )


@router.get("/api/download-status/{token}")
@limiter.limit("20/minute")
async def check_download_status(request: Request, token: str):
    """
    Check if a purchase is ready for download.
    Frontend can poll this while showing a loading state.

    Returns only {"ready": bool} to avoid leaking purchase existence,
    email presence, or internal timing state to unauthenticated callers.
    """
    purchase = purchase_service.get_purchase(token)

    if not purchase:
        # Return same shape as found-but-not-ready to prevent token enumeration.
        return JSONResponse({"ready": False}, status_code=200)

    return {"ready": purchase.status == PurchaseStatus.PAID}


@router.get("/d/{download_token}")
async def download_from_email_link(download_token: str):
    """
    Handle downloads from email links.
    
    The download_token is a JWT containing:
    - image_token: The purchase token
    - order_id: Lemon Squeezy order ID
    - exp: Expiration timestamp (48 hours)
    """
    
    # Decode and validate JWT
    payload = decode_download_token(download_token)
    
    if not payload:
        # Token is invalid or expired
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Download Expired - Eyedentity</title>
            <style>
                body {
                    font-family: -apple-system, sans-serif;
                    background: #0a0a0a;
                    color: #fff;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    margin: 0;
                    padding: 20px;
                }
                .container {
                    text-align: center;
                    max-width: 400px;
                }
                h1 { font-size: 24px; margin-bottom: 16px; }
                p { color: #888; line-height: 1.6; }
                a { color: #10b981; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>⏰ Download Link Expired</h1>
                <p>
                    This download link has expired or is invalid.
                    Links are valid for 48 hours after purchase.
                </p>
                <p>
                    Please contact support with your order confirmation 
                    email and we'll send you a new link.
                </p>
            </div>
        </body>
        </html>
        """, status_code=410)
    
    # Extract token and order info
    image_token = payload.get("image_token")
    order_id = payload.get("order_id", "unknown")
    
    # Get the purchase
    purchase = purchase_service.get_purchase(image_token)
    
    if not purchase:
        logger.warning(f"Email link download for missing purchase: {image_token[:8] if image_token else 'none'}...")
        return HTMLResponse(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Download Not Found - Eyedentity</title>
            <style>
                body {{
                    font-family: -apple-system, sans-serif;
                    background: #0a0a0a;
                    color: #fff;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    margin: 0;
                    padding: 20px;
                }}
                .container {{
                    text-align: center;
                    max-width: 400px;
                }}
                h1 {{ font-size: 24px; margin-bottom: 16px; }}
                p {{ color: #888; line-height: 1.6; }}
                code {{
                    background: #1a1a1a;
                    padding: 2px 8px;
                    border-radius: 4px;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>😕 Download Not Found</h1>
                <p>
                    This image is no longer available on our servers.
                    Downloads are kept for 48 hours after purchase.
                </p>
                <p>
                    Please contact support with your Order ID:<br>
                    <code>{order_id}</code>
                </p>
            </div>
        </body>
        </html>
        """, status_code=404)
    
    # Check payment status
    if purchase.status != PurchaseStatus.PAID:
        logger.warning(f"Email link download for unpaid purchase: {image_token[:8] if image_token else 'none'}...")
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Payment Pending - Eyedentity</title>
            <style>
                body {
                    font-family: -apple-system, sans-serif;
                    background: #0a0a0a;
                    color: #fff;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    margin: 0;
                    padding: 20px;
                }
                .container {
                    text-align: center;
                    max-width: 400px;
                }
                h1 { font-size: 24px; margin-bottom: 16px; }
                p { color: #888; line-height: 1.6; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>⏳ Payment Pending</h1>
                <p>
                    We haven't received payment confirmation yet.
                    Please try again in a few minutes.
                </p>
                <p>
                    If you've already paid, please contact support.
                </p>
            </div>
        </body>
        </html>
        """, status_code=402)
    
    # Success - serve the HD image
    logger.info(f"✅ Email link download: {image_token[:8]}... (Order: {order_id})")
    
    return Response(
        content=purchase.image_data,
        media_type="image/png",
        headers={
            "Content-Disposition": "attachment; filename=eyedentity-hd.png",
            "Cache-Control": "no-store"
        }
    )


class UpdatePurchaseEmailRequest(BaseModel):
    """Request body for update-purchase-email endpoint."""
    token: str = Field(
        min_length=36,
        max_length=36,
        pattern=_UUID_V4_PATTERN,
        description="UUID v4 purchase token",
    )
    email: EmailStr


@router.post("/api/update-purchase-email")
@limiter.limit("5/minute")
async def update_purchase_email(request: Request, body: UpdatePurchaseEmailRequest):
    """
    Update the email for a pending purchase.
    Called when user enters email before checkout.

    Accepts JSON body (token + email) — never query params, to prevent
    sensitive data appearing in server logs, browser history, and CDN/proxy logs.

    Rate-limited to 5 requests/minute per IP to prevent:
    - Token brute-force (UUID enumeration at high rate)
    - Email enumeration via 404 vs 200 response distinction
    - Hostile email registration against valid tokens
    """
    success = purchase_service.update_email(body.token, body.email)

    if not success:
        return JSONResponse(
            {"error": "Purchase not found"},
            status_code=404
        )

    return {"status": "updated"}


@router.post("/api/download-demo")
async def download_demo(request: DownloadRequest):
    """
    DEMO MODE: Download HD image without payment verification.
    This is for testing only - remove in production!
    """
    token = request.token
    
    purchase = purchase_service.get_purchase(token)
    if not purchase:
        return JSONResponse(
            {"error": "Invalid or expired token"},
            status_code=404
        )
    
    # Serve the HD image regardless of payment status (DEMO ONLY)
    logger.info(f"🧪 DEMO download: {token[:8]}... (bypassing payment)")
    
    return Response(
        content=purchase.image_data,
        media_type="image/png",
        headers={
            "Content-Disposition": "attachment; filename=eyedentity-hd.png",
            "Cache-Control": "no-store"
        }
    )


@router.post("/api/download-original-demo")
async def download_original_demo(request: DownloadRequest):
    """
    DEMO MODE: Download original capture image without payment verification.
    This is for testing only - remove in production!
    """
    token = request.token
    
    purchase = purchase_service.get_purchase(token)
    if not purchase:
        return JSONResponse(
            {"error": "Invalid or expired token"},
            status_code=404
        )
    
    # Serve the original image regardless of payment status (DEMO ONLY)
    logger.info(f"🧪 DEMO original download: {token[:8]}... (bypassing payment)")
    
    return Response(
        content=purchase.original_data,
        media_type="image/png",
        headers={
            "Content-Disposition": "attachment; filename=eyedentity-original.png",
            "Cache-Control": "no-store"
        }
    )
