"""
Download Routes - Serves HD images after payment verification.

Endpoints:
1. POST /api/download-hd - In-browser download (with polling for webhook race)
2. GET /d/{token} - Email link download (JWT-verified)
"""

import asyncio
import logging
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel

from services.purchase_service import purchase_service, PurchaseStatus
from services.email_service import decode_download_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["downloads"])


class DownloadRequest(BaseModel):
    """Request body for download endpoint."""
    token: str


@router.post("/api/download-hd")
async def download_hd(request: DownloadRequest):
    """
    Download HD image after payment.
    
    This endpoint handles the webhook race condition by polling
    for up to 30 seconds waiting for payment confirmation.
    
    Returns:
        - 200 + PNG image if payment confirmed
        - 202 if still waiting for payment (check email)
        - 404 if token not found
    """
    token = request.token
    
    # Check if token exists
    purchase = purchase_service.get_purchase(token)
    if not purchase:
        logger.warning(f"Download attempt with invalid token: {token[:8] if len(token) > 8 else token}...")
        return JSONResponse(
            {"error": "Invalid or expired token"},
            status_code=404
        )
    
    # Poll for payment confirmation (handles webhook race condition)
    MAX_WAIT_SECONDS = 30
    POLL_INTERVAL = 0.5
    elapsed = 0.0
    
    while elapsed < MAX_WAIT_SECONDS:
        # Refresh purchase data
        purchase = purchase_service.get_purchase(token)
        
        if not purchase:
            # Token was cleaned up while waiting
            return JSONResponse(
                {"error": "Purchase expired"},
                status_code=410
            )
        
        if purchase.status == PurchaseStatus.PAID:
            # Success! Serve the HD image
            logger.info(f"✅ Serving HD download: {token[:8]}...")
            
            return Response(
                content=purchase.image_data,
                media_type="image/png",
                headers={
                    "Content-Disposition": "attachment; filename=eyedentity-hd.png",
                    "Cache-Control": "no-store"
                }
            )
        
        # Wait and retry
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    
    # Timeout - webhook hasn't arrived yet
    logger.warning(f"Download timeout for {token[:8]}... (payment not confirmed in {MAX_WAIT_SECONDS}s)")
    
    return JSONResponse({
        "error": "Payment verification pending",
        "message": "Your download link has been sent to your email. Please check your inbox (and spam folder).",
        "retry": True
    }, status_code=202)


@router.get("/api/download-status/{token}")
async def check_download_status(token: str):
    """
    Check if a purchase is ready for download.
    Frontend can poll this while showing a loading state.
    """
    purchase = purchase_service.get_purchase(token)
    
    if not purchase:
        return JSONResponse(
            {"status": "not_found"},
            status_code=404
        )
    
    return {
        "status": purchase.status.value,
        "ready": purchase.status == PurchaseStatus.PAID,
        "has_email": bool(purchase.user_email),
        "time_remaining": purchase.time_remaining
    }


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
        logger.warning(f"Email link download for unpaid purchase: {image_token[:8]}...")
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


@router.post("/api/update-purchase-email")
async def update_purchase_email(token: str, email: str):
    """
    Update the email for a pending purchase.
    Called when user enters email before checkout.
    """
    success = purchase_service.update_email(token, email)
    
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
