#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JWT Security Module for Iris Heritage Platform.

Provides:
- JWT token creation and verification
- Session management with credits
- Secure password hashing (future use)
"""

import os
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from jose import jwt, JWTError, ExpiredSignatureError
from pydantic import BaseModel

# Configure logging
logger = logging.getLogger(__name__)

# JWT Configuration - Production values should come from environment
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "iris-heritage-dev-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_DAYS = 30  # Token valid for 30 days
JWT_ISSUER = "iris-heritage-platform"


class SessionPayload(BaseModel):
    """JWT payload structure for session tokens."""
    sub: str  # Session ID (UUID)
    credits_remaining: int = 3  # Default: 3 captures per package
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    tribe_id: Optional[str] = None
    tribe_name: Optional[str] = None
    tribe_confidence: Optional[int] = None
    tribe_hierarchy: Optional[str] = None
    iat: Optional[datetime] = None  # Issued at
    exp: Optional[datetime] = None  # Expiration
    jti: Optional[str] = None  # JWT ID for tracking


@dataclass
class SessionInfo:
    """Decoded session information."""
    session_id: str
    credits_remaining: int
    first_name: Optional[str]
    last_name: Optional[str]
    tribe_id: Optional[str]
    tribe_name: Optional[str]
    tribe_confidence: Optional[int]
    tribe_hierarchy: Optional[str]
    issued_at: datetime
    expires_at: datetime
    jwt_id: str
    is_valid: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "credits_remaining": self.credits_remaining,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "tribe_id": self.tribe_id,
            "tribe_name": self.tribe_name,
            "tribe_confidence": self.tribe_confidence,
            "tribe_hierarchy": self.tribe_hierarchy,
            "issued_at": self.issued_at.isoformat() if self.issued_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_valid": self.is_valid
        }


def create_session_token(
    credits: int = 3,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    tribe_id: Optional[str] = None,
    tribe_name: Optional[str] = None,
    tribe_confidence: Optional[int] = None,
    tribe_hierarchy: Optional[str] = None
) -> Tuple[str, SessionInfo]:
    """
    Create a new JWT session token.
    
    Args:
        credits: Number of capture credits (default 3)
        first_name: User's first name
        last_name: User's last name (family name)
        tribe_id: Matched tribe ID
        tribe_name: Matched tribe canonical name
        tribe_confidence: Match confidence (0-100)
        tribe_hierarchy: Tribal hierarchy path
    
    Returns:
        Tuple of (token_string, SessionInfo)
    """
    logger.info(f"[JWT] Creating new session token with {credits} credits")
    
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=JWT_ACCESS_TOKEN_EXPIRE_DAYS)
    jti = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    
    payload = {
        "sub": session_id,
        "credits_remaining": credits,
        "first_name": first_name,
        "last_name": last_name,
        "tribe_id": tribe_id,
        "tribe_name": tribe_name,
        "tribe_confidence": tribe_confidence,
        "tribe_hierarchy": tribe_hierarchy,
        "iat": now,
        "exp": expires,
        "jti": jti,
        "iss": JWT_ISSUER
    }
    
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    
    session_info = SessionInfo(
        session_id=session_id,
        credits_remaining=credits,
        first_name=first_name,
        last_name=last_name,
        tribe_id=tribe_id,
        tribe_name=tribe_name,
        tribe_confidence=tribe_confidence,
        tribe_hierarchy=tribe_hierarchy,
        issued_at=now,
        expires_at=expires,
        jwt_id=jti,
        is_valid=True
    )
    
    logger.info(f"[JWT] ✅ Session created: {session_id[:8]}... expires {expires.date()}")
    return token, session_info


def verify_session_token(token: str) -> Optional[SessionInfo]:
    """
    Verify and decode a JWT session token.
    
    Args:
        token: JWT token string
    
    Returns:
        SessionInfo if valid, None if invalid/expired
    """
    logger.debug(f"[JWT] Verifying token: {token[:20]}...")
    
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": True}
        )
        
        # JWT library returns iat/exp as Unix timestamps (int), convert to datetime
        iat_value = payload.get("iat")
        exp_value = payload.get("exp")
        
        if isinstance(iat_value, int):
            issued_at = datetime.fromtimestamp(iat_value, tz=timezone.utc)
        elif isinstance(iat_value, datetime):
            issued_at = iat_value
        else:
            issued_at = datetime.now(timezone.utc)
            
        if isinstance(exp_value, int):
            expires_at = datetime.fromtimestamp(exp_value, tz=timezone.utc)
        elif isinstance(exp_value, datetime):
            expires_at = exp_value
        else:
            expires_at = datetime.now(timezone.utc)
        
        session_info = SessionInfo(
            session_id=payload.get("sub", ""),
            credits_remaining=payload.get("credits_remaining", 0),
            first_name=payload.get("first_name"),
            last_name=payload.get("last_name"),
            tribe_id=payload.get("tribe_id"),
            tribe_name=payload.get("tribe_name"),
            tribe_confidence=payload.get("tribe_confidence"),
            tribe_hierarchy=payload.get("tribe_hierarchy"),
            issued_at=issued_at,
            expires_at=expires_at,
            jwt_id=payload.get("jti", ""),
            is_valid=True
        )
        
        logger.info(f"[JWT] ✅ Token valid for session {session_info.session_id[:8]}...")
        return session_info
        
    except ExpiredSignatureError:
        logger.warning("[JWT] ❌ Token expired")
        return None
        
    except JWTError as e:
        logger.warning(f"[JWT] ❌ Invalid token: {e}")
        return None


def update_session_token(
    current_token: str,
    credits_remaining: Optional[int] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    tribe_id: Optional[str] = None,
    tribe_name: Optional[str] = None,
    tribe_confidence: Optional[int] = None,
    tribe_hierarchy: Optional[str] = None
) -> Optional[Tuple[str, SessionInfo]]:
    """
    Update an existing session token with new data.
    
    Only provided fields are updated; None values keep existing values.
    
    Args:
        current_token: Current valid JWT token
        credits_remaining: Updated credit count (None = keep existing)
        first_name: Updated first name
        last_name: Updated last name
        tribe_id: Updated tribe ID
        tribe_name: Updated tribe name
        tribe_confidence: Updated match confidence
        tribe_hierarchy: Updated hierarchy
    
    Returns:
        Tuple of (new_token, SessionInfo) or None if current token invalid
    """
    logger.info("[JWT] Updating session token...")
    
    # Verify current token
    current_session = verify_session_token(current_token)
    if not current_session:
        logger.warning("[JWT] ❌ Cannot update - current token invalid")
        return None
    
    # Merge values (keep existing if not provided)
    new_credits = credits_remaining if credits_remaining is not None else current_session.credits_remaining
    new_first_name = first_name if first_name is not None else current_session.first_name
    new_last_name = last_name if last_name is not None else current_session.last_name
    new_tribe_id = tribe_id if tribe_id is not None else current_session.tribe_id
    new_tribe_name = tribe_name if tribe_name is not None else current_session.tribe_name
    new_tribe_conf = tribe_confidence if tribe_confidence is not None else current_session.tribe_confidence
    new_tribe_hier = tribe_hierarchy if tribe_hierarchy is not None else current_session.tribe_hierarchy
    
    # Create updated payload (keep same session ID, issue new token)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=JWT_ACCESS_TOKEN_EXPIRE_DAYS)
    jti = str(uuid.uuid4())
    
    payload = {
        "sub": current_session.session_id,  # Keep same session ID
        "credits_remaining": new_credits,
        "first_name": new_first_name,
        "last_name": new_last_name,
        "tribe_id": new_tribe_id,
        "tribe_name": new_tribe_name,
        "tribe_confidence": new_tribe_conf,
        "tribe_hierarchy": new_tribe_hier,
        "iat": now,
        "exp": expires,
        "jti": jti,
        "iss": JWT_ISSUER
    }
    
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    
    session_info = SessionInfo(
        session_id=current_session.session_id,
        credits_remaining=new_credits,
        first_name=new_first_name,
        last_name=new_last_name,
        tribe_id=new_tribe_id,
        tribe_name=new_tribe_name,
        tribe_confidence=new_tribe_conf,
        tribe_hierarchy=new_tribe_hier,
        issued_at=now,
        expires_at=expires,
        jwt_id=jti,
        is_valid=True
    )
    
    logger.info(f"[JWT] ✅ Token updated for session {current_session.session_id[:8]}...")
    return token, session_info


def use_credit(current_token: str) -> Optional[Tuple[str, SessionInfo]]:
    """
    Use one capture credit from the session.
    
    Decrements credits_remaining by 1 and issues a new token.
    Returns None if no credits remaining or invalid token.
    
    Args:
        current_token: Current valid JWT token
    
    Returns:
        Tuple of (new_token, SessionInfo) or None if failed
    """
    logger.info("[JWT] Using capture credit...")
    
    # Verify current token
    current_session = verify_session_token(current_token)
    if not current_session:
        logger.warning("[JWT] ❌ Cannot use credit - token invalid")
        return None
    
    if current_session.credits_remaining <= 0:
        logger.warning(f"[JWT] ❌ No credits remaining for session {current_session.session_id[:8]}...")
        return None
    
    # Decrement credit and create new token
    new_credits = current_session.credits_remaining - 1
    logger.info(f"[JWT] Credit used: {current_session.credits_remaining} → {new_credits}")
    
    return update_session_token(current_token, credits_remaining=new_credits)


# =============================================================================
# FastAPI Dependency
# =============================================================================

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer(auto_error=False)


async def get_current_session(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[SessionInfo]:
    """
    FastAPI dependency to extract and verify session from Bearer token.
    
    Usage:
        @app.get("/protected")
        async def protected_route(session: SessionInfo = Depends(get_current_session)):
            ...
    """
    if not credentials:
        logger.debug("[JWT] No credentials provided")
        return None
    
    token = credentials.credentials
    session = verify_session_token(token)
    
    if not session:
        logger.warning("[JWT] Invalid or expired token in request")
        return None
    
    return session


async def require_session(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> SessionInfo:
    """
    FastAPI dependency that REQUIRES a valid session.
    
    Raises 401 Unauthorized if no valid session.
    
    Usage:
        @app.get("/protected")
        async def protected_route(session: SessionInfo = Depends(require_session)):
            ...
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = credentials.credentials
    session = verify_session_token(token)
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return session


async def require_credits(
    session: SessionInfo = Depends(require_session)
) -> SessionInfo:
    """
    FastAPI dependency that REQUIRES a valid session WITH credits.
    
    Raises 402 Payment Required if no credits remaining.
    
    Usage:
        @app.post("/capture")
        async def capture(session: SessionInfo = Depends(require_credits)):
            # Will only reach here if credits > 0
            ...
    """
    if session.credits_remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="No capture credits remaining. Please purchase more credits."
        )
    
    return session
