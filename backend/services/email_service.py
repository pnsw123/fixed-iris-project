"""
Email Service - Sends download links via SendGrid.

Handles:
1. JWT-signed download URLs (48h expiry)
2. Styled email templates
3. Async sending (fire and forget)
"""

import logging
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


def create_download_token(image_token: str, order_id: str, hours: int = 48) -> str:
    """
    Create a JWT-signed download token for email links.
    
    Args:
        image_token: The purchase token
        order_id: Lemon Squeezy order ID
        hours: Hours until expiry (default 48)
        
    Returns:
        JWT string
    """
    payload = {
        "image_token": image_token,
        "order_id": order_id,
        "exp": datetime.now(tz=timezone.utc) + timedelta(hours=hours)
    }
    
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def decode_download_token(token: str) -> Optional[dict]:
    """
    Decode and validate a download token.
    
    Returns:
        Decoded payload dict, or None if invalid/expired
    """
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        logger.warning("Download token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid download token: {e}")
        return None


async def send_download_email(
    to_email: str, 
    image_token: str, 
    order_id: str
) -> bool:
    """
    Send the download link email.
    
    Args:
        to_email: Recipient email
        image_token: Purchase token
        order_id: Lemon Squeezy order ID
        
    Returns:
        True if email sent successfully
    """
    if not settings.sendgrid_api_key:
        logger.warning("SENDGRID_API_KEY not configured - skipping email")
        return False

    # Create signed download URL
    download_jwt = create_download_token(image_token, order_id)
    download_url = f"{settings.base_url}/d/{download_jwt}"
    
    # Email HTML template
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background-color: #0a0a0a;
                color: #ffffff;
                margin: 0;
                padding: 40px 20px;
            }}
            .container {{
                max-width: 480px;
                margin: 0 auto;
                background: #111111;
                border-radius: 12px;
                padding: 40px;
                border: 1px solid #222;
            }}
            .logo {{
                font-size: 28px;
                font-weight: 700;
                margin-bottom: 8px;
                letter-spacing: -0.5px;
            }}
            .tagline {{
                color: #666;
                font-size: 14px;
                margin-bottom: 32px;
            }}
            h2 {{
                font-size: 20px;
                font-weight: 600;
                margin: 0 0 16px 0;
            }}
            p {{
                color: #aaa;
                line-height: 1.6;
                margin: 0 0 24px 0;
            }}
            .button {{
                display: inline-block;
                background: linear-gradient(135deg, #10b981, #059669);
                color: #ffffff !important;
                padding: 16px 32px;
                text-decoration: none;
                border-radius: 8px;
                font-weight: 600;
                font-size: 16px;
                margin: 8px 0 32px 0;
            }}
            .footer {{
                color: #555;
                font-size: 12px;
                margin-top: 32px;
                padding-top: 24px;
                border-top: 1px solid #222;
            }}
            .order-id {{
                font-family: monospace;
                background: #1a1a1a;
                padding: 2px 6px;
                border-radius: 4px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">👁️ EYEDENTITY</div>
            <div class="tagline">AI-Enhanced Iris Photography</div>
            
            <h2>Your HD Iris Image is Ready</h2>
            <p>
                Thank you for your purchase! Your enhanced iris image is ready 
                for download. Click the button below to get your high-resolution, 
                watermark-free image.
            </p>
            
            <a href="{download_url}" class="button">
                Download HD Image
            </a>
            
            <p style="font-size: 13px;">
                If the button doesn't work, copy and paste this link into your browser:<br>
                <span style="color: #10b981; word-break: break-all;">{download_url}</span>
            </p>
            
            <div class="footer">
                <p>This download link expires in 48 hours.</p>
                <p>Order ID: <span class="order-id">{order_id}</span></p>
                <p>If you have any issues, reply to this email for support.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    # Plain text fallback
    text_content = f"""
    EYEDENTITY - Your HD Iris Image is Ready
    
    Thank you for your purchase!
    
    Download your image here:
    {download_url}
    
    This link expires in 48 hours.
    Order ID: {order_id}
    
    If you have any issues, reply to this email.
    """
    
    try:
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {settings.sendgrid_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "personalizations": [{
                        "to": [{"email": to_email}]
                    }],
                    "from": {
                        "email": settings.from_email,
                        "name": "Eyedentity"
                    },
                    "subject": "Your Eyedentity HD Iris Image 👁️",
                    "content": [
                        {"type": "text/plain", "value": text_content},
                        {"type": "text/html", "value": html_content}
                    ]
                },
                timeout=10.0
            )
            
            if response.status_code == 202:
                logger.info(f"✅ Download email sent to {to_email}")
                return True
            else:
                logger.error(f"SendGrid error {response.status_code}: {response.text}")
                return False
                
    except ImportError:
        logger.error("httpx not installed - run: pip install httpx")
        return False
    except Exception as e:
        logger.exception(f"Email send error: {e}")
        return False
