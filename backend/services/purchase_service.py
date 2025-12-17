"""
Purchase Service - Manages pending purchases for payment flow.

This module handles the lifecycle of image purchases:
1. Create pending purchase when user enhances image
2. Mark as paid when webhook confirms payment
3. Serve HD image on verified download
4. Cleanup expired purchases
"""

import os
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict
from enum import Enum
import threading

logger = logging.getLogger(__name__)


class PurchaseStatus(Enum):
    """Status of a pending purchase."""
    PENDING = "PENDING"  # Created, waiting for payment
    PAID = "PAID"        # Payment confirmed via webhook
    EXPIRED = "EXPIRED"  # Timed out without payment


@dataclass
class PendingPurchase:
    """
    Represents a pending purchase in memory.
    
    Lifecycle:
    - Created when user clicks "Enhance" (status=PENDING)
    - Updated when webhook confirms payment (status=PAID)
    - Deleted after expiry (1h unpaid, 48h paid)
    """
    token: str
    image_data: bytes           # HD enhanced image
    preview_data: bytes         # Watermarked preview
    original_data: bytes        # Original capture (before enhancement)
    status: PurchaseStatus = PurchaseStatus.PENDING
    user_email: Optional[str] = None
    order_id: Optional[str] = None
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    paid_at: Optional[float] = None
    
    # Expiry times in seconds
    UNPAID_EXPIRY = 3600      # 1 hour
    PAID_EXPIRY = 48 * 3600   # 48 hours
    
    @property
    def is_expired(self) -> bool:
        """Check if this purchase has expired."""
        now = datetime.now().timestamp()
        if self.status == PurchaseStatus.PAID:
            return (now - (self.paid_at or self.created_at)) > self.PAID_EXPIRY
        else:
            return (now - self.created_at) > self.UNPAID_EXPIRY
    
    @property
    def time_remaining(self) -> float:
        """Get seconds until expiry."""
        now = datetime.now().timestamp()
        if self.status == PurchaseStatus.PAID:
            expiry_time = (self.paid_at or self.created_at) + self.PAID_EXPIRY
        else:
            expiry_time = self.created_at + self.UNPAID_EXPIRY
        return max(0, expiry_time - now)


class PurchaseService:
    """
    Service for managing pending purchases.
    
    For MVP, uses in-memory storage. 
    TODO: Migrate to Redis for production scalability.
    """
    
    def __init__(self):
        # In-memory storage (dict of token -> PendingPurchase)
        self._purchases: Dict[str, PendingPurchase] = {}
        
        # Idempotency tracking for webhooks
        self._processed_webhook_ids: set = set()
        
        # Thread-safe lock for concurrent access
        self._lock = threading.Lock()
        
        logger.info("PurchaseService initialized (in-memory storage, thread-safe)")
    
    def create_purchase(
        self, 
        hd_image_data: bytes, 
        preview_data: bytes,
        original_data: bytes,
        user_email: Optional[str] = None
    ) -> str:
        """
        Create a new pending purchase.
        
        Args:
            hd_image_data: Full resolution image bytes
            preview_data: Watermarked preview image bytes
            original_data: Original capture image bytes
            user_email: User's email (collected before checkout)
            
        Returns:
            Unique token for this purchase
        """
        with self._lock:
            token = str(uuid.uuid4())
            
            purchase = PendingPurchase(
                token=token,
                image_data=hd_image_data,
                preview_data=preview_data,
                original_data=original_data,
                user_email=user_email
            )
            
            self._purchases[token] = purchase
            
            logger.info(f"Created pending purchase: {token[:8]}... (email: {user_email or 'not provided'})")
            
            return token
    
    def get_purchase(self, token: str) -> Optional[PendingPurchase]:
        """Get a purchase by token."""
        return self._purchases.get(token)
    
    def mark_as_paid(
        self, 
        token: str, 
        order_id: str, 
        user_email: Optional[str] = None
    ) -> bool:
        """
        Mark a purchase as paid.
        
        Args:
            token: Purchase token
            order_id: Lemon Squeezy order ID
            user_email: Email from payment (may override earlier email)
            
        Returns:
            True if successful, False if token not found
        """
        purchase = self._purchases.get(token)
        
        if not purchase:
            logger.warning(f"Attempted to mark unknown token as paid: {token[:8]}...")
            return False
        
        if purchase.status == PurchaseStatus.PAID:
            logger.info(f"Purchase already marked as paid: {token[:8]}...")
            return True  # Idempotent - still success
        
        purchase.status = PurchaseStatus.PAID
        purchase.order_id = order_id
        purchase.paid_at = datetime.now().timestamp()
        
        # Update email if provided (webhook email takes precedence)
        if user_email:
            purchase.user_email = user_email
        
        logger.info(f"✅ Marked purchase as PAID: {token[:8]}... (Order: {order_id})")
        
        return True
    
    def update_email(self, token: str, email: str) -> bool:
        """Update the email for a pending purchase."""
        purchase = self._purchases.get(token)
        if not purchase:
            return False
        purchase.user_email = email
        return True
    
    def is_webhook_processed(self, event_id: str) -> bool:
        """Check if a webhook event has already been processed."""
        return event_id in self._processed_webhook_ids
    
    def mark_webhook_processed(self, event_id: str) -> None:
        """Mark a webhook event as processed."""
        with self._lock:
            self._processed_webhook_ids.add(event_id)
    
    def cleanup_expired(self) -> int:
        """
        Remove expired purchases from storage.
        
        Returns:
            Number of purchases cleaned up
        """
        with self._lock:
            expired_tokens = [
                token for token, purchase in self._purchases.items()
                if purchase.is_expired
            ]
            
            for token in expired_tokens:
                del self._purchases[token]
                logger.info(f"Cleaned up expired purchase: {token[:8]}...")
            
            return len(expired_tokens)
    
    def get_stats(self) -> dict:
        """Get statistics about current purchases."""
        total = len(self._purchases)
        pending = sum(1 for p in self._purchases.values() if p.status == PurchaseStatus.PENDING)
        paid = sum(1 for p in self._purchases.values() if p.status == PurchaseStatus.PAID)
        
        return {
            "total": total,
            "pending": pending,
            "paid": paid,
            "webhook_ids_tracked": len(self._processed_webhook_ids)
        }


# Singleton instance
purchase_service = PurchaseService()
