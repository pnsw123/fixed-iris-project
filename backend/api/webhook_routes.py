"""
Webhook Routes - Handles Lemon Squeezy payment webhooks.

This is the SOURCE OF TRUTH for payment confirmations.
Never trust client-side payment events.
"""

import os
import hmac
import hashlib
import asyncio
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from services.purchase_service import purchase_service
from services.email_service import send_download_email

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhooks"])

# Lemon Squeezy webhook signing secret
# Set this in .env after configuring webhook in LS dashboard
WEBHOOK_SECRET = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET", "")


def verify_signature(payload: bytes, signature: str) -> bool:
    """
    Verify Lemon Squeezy webhook signature.
    
    LS signs webhooks with HMAC-SHA256 using the webhook secret.
    """
    if not WEBHOOK_SECRET:
        logger.warning("LEMONSQUEEZY_WEBHOOK_SECRET not configured - skipping verification")
        # In development, allow without verification
        # TODO: Make this strict in production
        return True
    
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected)


@router.post("/api/webhooks/lemon-squeezy")
async def lemon_squeezy_webhook(request: Request):
    """
    Handle Lemon Squeezy webhook events.
    
    Supported events:
    - order_created: Payment completed
    
    Security:
    - Verifies HMAC signature
    - Tracks event IDs for idempotency
    - Handles all error cases gracefully
    """
    
    # 1. Get signature from header
    signature = request.headers.get("X-Signature", "")
    event_id = request.headers.get("X-Event-Id", "")
    
    # 2. Read raw body for signature verification
    body = await request.body()
    
    # 3. Verify signature
    if not verify_signature(body, signature):
        logger.warning(f"Webhook signature verification failed (event: {event_id})")
        return JSONResponse(
            {"error": "Invalid signature"},
            status_code=401
        )
    
    # 4. Check idempotency
    if event_id and purchase_service.is_webhook_processed(event_id):
        logger.info(f"Webhook already processed: {event_id}")
        return {"status": "already_processed"}
    
    # 5. Parse JSON payload
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook JSON: {e}")
        return JSONResponse(
            {"error": "Invalid JSON payload"},
            status_code=400
        )
    
    # 6. Extract event type
    try:
        meta = data.get("meta", {})
        event_name = meta.get("event_name", "unknown")
        
        logger.info(f"Received webhook: {event_name} (event_id: {event_id})")
        
        # Only process order_created events
        if event_name != "order_created":
            logger.info(f"Ignoring event type: {event_name}")
            return {"status": "ignored", "event": event_name}
        
        # 7. Extract payment data
        attributes = data.get("data", {}).get("attributes", {})
        order_id = str(data.get("data", {}).get("id", ""))
        status = attributes.get("status", "")
        
        # Custom data passed through checkout URL
        custom_data = meta.get("custom_data", {})
        image_token = custom_data.get("image_token", "")
        user_email = custom_data.get("user_email", "") or attributes.get("user_email", "")
        
        # 8. Validate required fields
        if not image_token:
            logger.error(f"Webhook missing image_token (order: {order_id})")
            # Return 200 to prevent retries for malformed webhooks
            return {"status": "error", "message": "Missing image_token"}
        
        if not order_id:
            logger.error("Webhook missing order_id")
            return {"status": "error", "message": "Missing order_id"}
        
        # 9. Process payment
        if status == "paid":
            success = purchase_service.mark_as_paid(
                token=image_token,
                order_id=order_id,
                user_email=user_email
            )
            
            if success:
                logger.info(f"✅ Payment confirmed: {image_token[:8]}... (Order: {order_id})")
                
                # 10. Send email backup (fire and forget)
                if user_email:
                    asyncio.create_task(
                        send_download_email(user_email, image_token, order_id)
                    )
                    logger.info(f"Triggered download email to {user_email}")
                else:
                    logger.warning(f"No email for order {order_id} - skipping email backup")
            else:
                logger.error(f"Failed to mark as paid - token not found: {image_token[:8]}...")
        else:
            logger.info(f"Order status is '{status}', not 'paid' - no action taken")
        
        # 11. Mark webhook as processed (idempotency)
        if event_id:
            purchase_service.mark_webhook_processed(event_id)
        
        return {"status": "success"}
        
    except KeyError as e:
        logger.error(f"Webhook payload missing key: {e}")
        return JSONResponse(
            {"error": f"Missing key: {e}"},
            status_code=400
        )
    except Exception as e:
        logger.exception(f"Webhook processing error: {e}")
        return JSONResponse(
            {"error": "Server error"},
            status_code=500
        )


@router.get("/api/webhooks/health")
async def webhook_health():
    """Health check for webhook endpoint."""
    stats = purchase_service.get_stats()
    return {
        "status": "ok",
        "webhook_secret_configured": bool(WEBHOOK_SECRET),
        "purchases": stats
    }
