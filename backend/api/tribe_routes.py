#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tribe Routes - API endpoints for tribal name matching.

Endpoints:
- POST /api/v1/tribes/match - Match single name to tribe
- POST /api/v1/tribes/search - Search tribes (autocomplete)
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from services.tribal_matcher_service import (
    get_tribal_matcher,
    TribeMatch,
    MatchType
)

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/tribes", tags=["tribes"])


# =============================================================================
# Request/Response Models
# =============================================================================

class MatchRequest(BaseModel):
    """Request body for tribe matching."""
    name: str = Field(..., min_length=2, max_length=200, description="User's last name (Arabic or English)")
    confidence_threshold: int = Field(default=70, ge=0, le=100, description="Minimum acceptable confidence")


class MatchResponse(BaseModel):
    """Response for tribe matching."""
    success: bool
    match: Optional[dict] = None
    message: str = ""


class SearchRequest(BaseModel):
    """Request body for tribe search."""
    query: str = Field(..., min_length=2, max_length=200, description="Search query")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum results to return")


class SearchResponse(BaseModel):
    """Response for tribe search."""
    success: bool
    results: List[dict] = []
    count: int = 0


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/match", response_model=MatchResponse)
async def match_tribe(request: MatchRequest) -> MatchResponse:
    """
    Match user's last name to a tribe in the database.
    
    Uses 3-layer matching:
    1. Exact match on canonical name
    2. Variant lookup after normalization
    3. Fuzzy matching with Levenshtein distance
    
    Returns:
        MatchResponse with tribe data if found, or success=False
    """
    logger.info(f"[TribeRoutes] POST /match - name='{request.name}', threshold={request.confidence_threshold}")
    print(f"\n🔍 [MATCH DEBUG] Incoming request: name='{request.name}'")
    
    try:
        matcher = get_tribal_matcher()
        print(f"🔍 [MATCH DEBUG] Matcher has {len(matcher.nodes)} nodes, {len(matcher.variant_index)} variants")
        
        result = matcher.match(request.name, confidence_threshold=request.confidence_threshold)
        
        if result:
            result_dict = result.to_dict()
            logger.info(f"[TribeRoutes] ✅ Match found: {result.canonical_name} ({result.confidence}%)")
            print(f"✅ [MATCH DEBUG] Match found:")
            print(f"   canonical_name: {result.canonical_name}")
            print(f"   hierarchy_path: '{result.hierarchy_path}'")
            print(f"   confidence: {result.confidence}")
            print(f"   match_type: {result.match_type}")
            print(f"   Full result_dict: {result_dict}")
            
            return MatchResponse(
                success=True,
                match=result_dict,
                message=f"Matched to {result.canonical_name} with {result.confidence}% confidence"
            )
        else:
            logger.info(f"[TribeRoutes] ❌ No match found for: '{request.name}'")
            print(f"❌ [MATCH DEBUG] No match found for: '{request.name}'")
            return MatchResponse(
                success=True,  # Request succeeded, just no match
                match=None,
                message="No tribal match found for this name"
            )
    
    except Exception as e:
        logger.error(f"[TribeRoutes] ❌ Error matching tribe: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to match tribe: {str(e)}"
        )


@router.post("/search", response_model=SearchResponse)
async def search_tribes(request: SearchRequest) -> SearchResponse:
    """
    Search for tribes matching a query (for autocomplete).
    
    Returns list of matches sorted by relevance (confidence descending).
    """
    logger.info(f"[TribeRoutes] POST /search - query='{request.query}', limit={request.limit}")
    
    try:
        matcher = get_tribal_matcher()
        results = matcher.search(request.query, limit=request.limit)
        
        results_dict = [r.to_dict() for r in results]
        
        logger.info(f"[TribeRoutes] ✅ Search returned {len(results_dict)} results")
        return SearchResponse(
            success=True,
            results=results_dict,
            count=len(results_dict)
        )
    
    except Exception as e:
        logger.error(f"[TribeRoutes] ❌ Error searching tribes: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search tribes: {str(e)}"
        )


@router.get("/health")
async def tribe_service_health():
    """Health check for tribal matcher service."""
    logger.debug("[TribeRoutes] GET /health")
    
    try:
        matcher = get_tribal_matcher()
        tribe_count = len(matcher.nodes)
        variant_count = len(matcher.variant_index)
        
        return {
            "status": "healthy",
            "service": "tribal_matcher",
            "stats": {
                "tribes_loaded": tribe_count,
                "variants_indexed": variant_count
            }
        }
    
    except Exception as e:
        logger.error(f"[TribeRoutes] ❌ Health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "tribal_matcher",
            "error": str(e)
        }
