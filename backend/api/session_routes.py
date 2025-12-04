#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Session Routes - API endpoints for session management.

Endpoints:
- POST /api/session/create - Create new session (after payment)
- GET /api/session/check - Check session validity
- POST /api/session/update - Update session with name/tribe data
- POST /api/session/use-credit - Use one capture credit
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends, Header
from pydantic import BaseModel, Field

from core.security import (
    create_session_token,
    verify_session_token,
    update_session_token,
    use_credit,
    get_current_session,
    require_session,
    SessionInfo
)

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/session", tags=["session"])


# =============================================================================
# Request/Response Models
# =============================================================================

class CreateSessionRequest(BaseModel):
    """Request body for creating a new session."""
    credits: int = Field(default=3, ge=1, le=100, description="Number of capture credits")
    payment_id: Optional[str] = Field(default=None, description="Optional payment reference ID")


class CreateSessionResponse(BaseModel):
    """Response for session creation."""
    success: bool
    token: str
    session: dict


class UpdateSessionRequest(BaseModel):
    """Request body for updating session data."""
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    tribe_id: Optional[str] = Field(default=None)
    tribe_name: Optional[str] = Field(default=None)
    tribe_confidence: Optional[int] = Field(default=None, ge=0, le=100)
    tribe_hierarchy: Optional[str] = Field(default=None)


class SessionResponse(BaseModel):
    """Standard session response."""
    success: bool
    session: Optional[dict] = None
    token: Optional[str] = None
    message: str = ""


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/create", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    """
    Create a new session with capture credits.
    
    This should be called after a successful payment.
    Returns a JWT token to be used for subsequent requests.
    """
    logger.info(f"[SessionRoutes] POST /create - credits={request.credits}, payment_id={request.payment_id}")
    
    try:
        token, session_info = create_session_token(credits=request.credits)
        
        logger.info(f"[SessionRoutes] ✅ Session created: {session_info.session_id[:8]}...")
        
        return CreateSessionResponse(
            success=True,
            token=token,
            session=session_info.to_dict()
        )
    
    except Exception as e:
        logger.error(f"[SessionRoutes] ❌ Failed to create session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}"
        )


@router.get("/check", response_model=SessionResponse)
async def check_session(session: Optional[SessionInfo] = Depends(get_current_session)):
    """
    Check if the current session is valid.
    
    Returns session information if valid, or success=False if no valid session.
    """
    logger.info("[SessionRoutes] GET /check")
    
    if session:
        logger.info(f"[SessionRoutes] ✅ Valid session: {session.session_id[:8]}..., credits={session.credits_remaining}")
        return SessionResponse(
            success=True,
            session=session.to_dict(),
            message="Session is valid"
        )
    else:
        logger.info("[SessionRoutes] ❌ No valid session")
        return SessionResponse(
            success=False,
            session=None,
            message="No valid session found"
        )


@router.post("/update", response_model=SessionResponse)
async def update_session(
    request: UpdateSessionRequest,
    authorization: str = Header(..., description="Bearer token")
):
    """
    Update session with user name and tribe information.
    
    Only provided fields are updated; omitted fields keep their current values.
    Returns a new token with updated data.
    """
    logger.info(f"[SessionRoutes] POST /update - {request.dict(exclude_none=True)}")
    
    # Extract token from Authorization header
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format"
        )
    
    token = authorization[7:]  # Remove "Bearer " prefix
    
    try:
        result = update_session_token(
            current_token=token,
            first_name=request.first_name,
            last_name=request.last_name,
            tribe_id=request.tribe_id,
            tribe_name=request.tribe_name,
            tribe_confidence=request.tribe_confidence,
            tribe_hierarchy=request.tribe_hierarchy
        )
        
        if result:
            new_token, session_info = result
            logger.info(f"[SessionRoutes] ✅ Session updated: {session_info.session_id[:8]}...")
            return SessionResponse(
                success=True,
                session=session_info.to_dict(),
                token=new_token,
                message="Session updated successfully"
            )
        else:
            logger.warning("[SessionRoutes] ❌ Token invalid or expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SessionRoutes] ❌ Failed to update session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update session: {str(e)}"
        )


@router.post("/use-credit", response_model=SessionResponse)
async def use_capture_credit(authorization: str = Header(..., description="Bearer token")):
    """
    Use one capture credit from the session.
    
    Decrements credits_remaining by 1.
    Returns 402 Payment Required if no credits remaining.
    """
    logger.info("[SessionRoutes] POST /use-credit")
    
    # Extract token from Authorization header
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format"
        )
    
    token = authorization[7:]
    
    # First verify the token
    session = verify_session_token(token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    if session.credits_remaining <= 0:
        logger.warning(f"[SessionRoutes] ❌ No credits remaining for session {session.session_id[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="No capture credits remaining. Please purchase more credits."
        )
    
    try:
        result = use_credit(token)
        
        if result:
            new_token, session_info = result
            logger.info(f"[SessionRoutes] ✅ Credit used: now {session_info.credits_remaining} remaining")
            return SessionResponse(
                success=True,
                session=session_info.to_dict(),
                token=new_token,
                message=f"Credit used. {session_info.credits_remaining} credits remaining."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to use credit"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[SessionRoutes] ❌ Failed to use credit: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to use credit: {str(e)}"
        )


@router.get("/status")
async def session_service_status():
    """Health check for session service."""
    return {
        "status": "healthy",
        "service": "session_management",
        "jwt_algorithm": "HS256",
        "token_expiry_days": 30
    }
