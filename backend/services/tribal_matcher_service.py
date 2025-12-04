#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tribal Matcher Service for FastAPI
Production-grade service with comprehensive logging and in-memory caching.
Based on scripts/tribe_matcher.py
"""

import re
import json
import unicodedata
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from functools import lru_cache
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)


class MatchType(str, Enum):
    """Match type classification for tribal matching"""
    EXACT = "exact"           # 100% - Direct match on canonical name
    VARIANT = "variant"       # 95% - Match after normalization/variant lookup  
    FUZZY_HIGH = "fuzzy_high" # 90+ - High confidence fuzzy match
    FUZZY_MED = "fuzzy_med"   # 85-90% - Medium confidence fuzzy
    NO_MATCH = "no_match"     # <85% - No acceptable match


@dataclass
class TribeMatch:
    """Structured match result"""
    tribe_id: str
    canonical_name: str
    confidence: int  # 0-100
    match_type: MatchType
    matched_variant: str
    hierarchy_path: str = ""
    origin: str = ""
    description: str = ""
    subfamilies: List[str] = None
    
    def __post_init__(self):
        if self.subfamilies is None:
            self.subfamilies = []
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "tribe_id": self.tribe_id,
            "canonical_name": self.canonical_name,
            "confidence": self.confidence,
            "match_type": self.match_type.value,
            "matched_variant": self.matched_variant,
            "hierarchy_path": self.hierarchy_path,
            "origin": self.origin,
            "description": self.description,
            "subfamilies": self.subfamilies
        }


class TribalMatcherService:
    """
    Production-grade tribal name matching service.
    
    Features:
    - 3-layer matching: exact → variant → fuzzy
    - LRU cache for repeated queries
    - Comprehensive logging
    - Arabic text normalization
    """
    
    def __init__(self, tribe_brain_path: str = None):
        """
        Initialize the matcher with the tribe database.
        
        Args:
            tribe_brain_path: Path to tribe_brain.json. If None, uses default location.
        """
        logger.info("[TribalMatcher] Initializing service...")
        start_time = datetime.now()
        
        if tribe_brain_path is None:
            # Try to find tribe_brain.json relative to backend directory
            backend_dir = Path(__file__).parent.parent.parent
            tribe_brain_path = backend_dir / 'tribe_brain.json'
            logger.info(f"[TribalMatcher] Using default path: {tribe_brain_path}")
        
        try:
            with open(tribe_brain_path, 'r', encoding='utf-8') as f:
                self.db = json.load(f)
            logger.info(f"[TribalMatcher] ✅ Loaded tribe_brain.json successfully")
        except FileNotFoundError:
            logger.error(f"[TribalMatcher] ❌ tribe_brain.json not found at {tribe_brain_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"[TribalMatcher] ❌ Invalid JSON in tribe_brain.json: {e}")
            raise
        
        # Get tribes (supports both old and new schema)
        self.main_tribes = self.db.get('tribes', self.db.get('main_tribes', {}))
        self.search_index = self.db.get('index', self.db.get('search_index', {}))
        
        logger.info(f"[TribalMatcher] Found {len(self.main_tribes)} main tribes")
        logger.info(f"[TribalMatcher] Found {len(self.search_index)} indexed entries")
        
        # Build variant lookup table
        self.variant_to_canonical: Dict[str, str] = {}
        self._build_variant_table()
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"[TribalMatcher] ✅ Initialization complete in {elapsed:.2f}s")
        logger.info(f"[TribalMatcher] Total variants indexed: {len(self.variant_to_canonical)}")
    
    # =========================================================================
    # LAYER 1: Input Normalization
    # =========================================================================
    
    @staticmethod
    @lru_cache(maxsize=10000)
    def normalize_input(user_input: str) -> str:
        """
        Normalize user input by removing ال and nisba suffixes.
        
        LRU cached for performance on repeated queries.
        
        Steps:
        1. NFKC normalization (handle presentation forms)
        2. Remove definite article ال from start
        3. Remove nisba suffixes from end
        4. Character normalization (alef variants, etc.)
        
        Examples:
            البلوي → بل
            الهاشمي → هاشم
            الغباني → غبان
        """
        text = user_input.strip()
        if not text:
            return ""
        
        # Step 1: NFKC normalization
        text = unicodedata.normalize('NFKC', text)
        
        # Step 2: Remove ال prefix
        if text.startswith('ال'):
            text = text[2:]
        
        # Step 3: Remove nisba suffixes (order matters - longer first)
        nisba_suffixes = ['انية', 'اني', 'ية', 'ي']
        for suffix in nisba_suffixes:
            if text.endswith(suffix) and len(text) > len(suffix) + 1:
                text = text[:-len(suffix)]
                break
        
        # Step 4: Character normalization
        text = TribalMatcherService._normalize_arabic_static(text)
        
        return text
    
    @staticmethod
    def _normalize_arabic_static(text: str) -> str:
        """Normalize Arabic character variants (static for caching)."""
        # Alef variants → ا
        text = re.sub('[إأٱآا]', 'ا', text)
        
        # Ya / Alef maksura
        text = re.sub('ى', 'ي', text)
        
        # Ta marbuta → ha
        text = re.sub('ة', 'ه', text)
        
        # Remove diacritics
        text = re.sub('[\u064B-\u0652]', '', text)
        
        # Remove tatweel
        text = re.sub('ـ', '', text)
        
        return text
    
    # =========================================================================
    # LAYER 2: Variant Pre-computation
    # =========================================================================
    
    def _build_variant_table(self):
        """
        Pre-compute all variant forms for each tribe.
        
        For each tribe, generate:
        - Base form: بلي
        - With ال: البلي
        - Nisba masculine: بلوي, البلوي
        - Nisba feminine: بلوية, البلوية
        """
        logger.debug("[TribalMatcher] Building variant lookup table...")
        
        for tribe_name in self.main_tribes:
            variants = self._generate_variants(tribe_name)
            for variant in variants:
                normalized = self.normalize_input(variant)
                if normalized and normalized not in self.variant_to_canonical:
                    self.variant_to_canonical[normalized] = tribe_name
        
        # Also add subfamilies from search index
        for subfamily_name in self.search_index:
            normalized = self.normalize_input(subfamily_name)
            if normalized and normalized not in self.variant_to_canonical:
                self.variant_to_canonical[normalized] = subfamily_name
        
        logger.debug(f"[TribalMatcher] Variant table built with {len(self.variant_to_canonical)} entries")
    
    def _generate_variants(self, tribe_name: str) -> List[str]:
        """
        Generate all possible written forms of a tribe name.
        
        Rules:
        - Nisba adds ي (masculine) or ية (feminine)
        - Some tribes use اني/انية for nisba
        - Some tribes insert و before nisba (بلي → بلوي)
        - ال can be prefixed to any form
        """
        variants = [tribe_name]
        
        # Clean name for variant generation
        base = tribe_name
        if base.startswith('ال'):
            base = base[2:]
        
        # Generate without ال
        variants.append(base)
        
        # With ال
        variants.append('ال' + base)
        
        # Nisba forms (apply to base)
        # Standard nisba: add ي/ية
        nisba_m = base + 'ي'
        nisba_f = base + 'ية'
        variants.extend([nisba_m, nisba_f, 'ال' + nisba_m, 'ال' + nisba_f])
        
        # Nisba with و insertion (common pattern: بلي → بلوي)
        # Remove trailing ي if present, then add وي/وية
        if base.endswith('ي') or base.endswith('ى'):
            base_stripped = base[:-1]
            nisba_m_waw = base_stripped + 'وي'
            nisba_f_waw = base_stripped + 'وية'
            variants.extend([nisba_m_waw, nisba_f_waw, 'ال' + nisba_m_waw, 'ال' + nisba_f_waw])
        
        # Extended nisba for some names: add اني/انية
        nisba_m_ext = base + 'اني'
        nisba_f_ext = base + 'انية'
        variants.extend([nisba_m_ext, nisba_f_ext, 'ال' + nisba_m_ext, 'ال' + nisba_f_ext])
        
        return variants
    
    # =========================================================================
    # LAYER 3: Fuzzy Matching
    # =========================================================================
    
    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        """Calculate Levenshtein (edit) distance between two strings."""
        if len(s1) < len(s2):
            return TribalMatcherService._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    @staticmethod
    def _similarity_score(s1: str, s2: str) -> float:
        """Calculate similarity score (0.0 to 1.0) between two strings."""
        if not s1 or not s2:
            return 0.0
        
        distance = TribalMatcherService._levenshtein_distance(s1, s2)
        max_len = max(len(s1), len(s2))
        return 1.0 - (distance / max_len)
    
    def _fuzzy_match(self, normalized_input: str, threshold: float = 0.85) -> Optional[Tuple[str, str, float]]:
        """
        Find best fuzzy match for normalized input.
        
        Returns:
            Tuple of (canonical_name, matched_variant, similarity_score) if match found, else None
        """
        best_match = None
        best_variant = None
        best_score = 0.0
        
        for normalized_variant, canonical in self.variant_to_canonical.items():
            score = self._similarity_score(normalized_input, normalized_variant)
            if score > best_score and score >= threshold:
                best_score = score
                best_match = canonical
                best_variant = normalized_variant
        
        if best_match:
            return (best_match, best_variant, best_score)
        return None
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def _get_hierarchy_path(self, name: str) -> str:
        """
        Get the full hierarchy path for a tribe/subfamily name.
        
        Always looks up in search_index first since it contains the proper
        path array (e.g., ['عنزة', 'آل جعفر'] for a subfamily).
        
        Args:
            name: The canonical tribe or subfamily name
            
        Returns:
            Formatted hierarchy string like "عنزة > آل جعفر"
        """
        # First check search_index - it has the authoritative path data
        if name in self.search_index:
            index_data = self.search_index[name]
            path = index_data.get('path', [])
            if isinstance(path, list) and path:
                return " > ".join(path)
        
        # Fallback: check main_tribes
        if name in self.main_tribes:
            # Main tribes are roots, so path is just the name itself
            return name
        
        # Final fallback
        return name

    def match(self, user_input: str, confidence_threshold: int = 70) -> Optional[TribeMatch]:
        """
        Match user input to a tribe in the database.
        
        Args:
            user_input: User's last name (Arabic or transliterated)
            confidence_threshold: Minimum acceptable confidence (0-100)
        
        Returns:
            TribeMatch object or None if no match found
        """
        logger.info(f"[TribalMatcher] Matching: '{user_input}'")
        
        if not user_input or len(user_input) < 2:
            logger.warning(f"[TribalMatcher] Input too short: '{user_input}'")
            return None

        # Step 1: Try exact match (user typed canonical name)
        if user_input in self.main_tribes:
            tribe_data = self.main_tribes[user_input]
            hierarchy_path = self._get_hierarchy_path(user_input)
            logger.info(f"[TribalMatcher] ✅ EXACT match: '{user_input}' -> path: '{hierarchy_path}'")
            return TribeMatch(
                tribe_id=user_input,
                canonical_name=user_input,
                confidence=100,
                match_type=MatchType.EXACT,
                matched_variant=user_input,
                hierarchy_path=hierarchy_path,
                origin=tribe_data.get('origin', ''),
                description=tribe_data.get('description', ''),
                subfamilies=tribe_data.get('subfamilies', [])
            )
        
        if user_input in self.search_index:
            search_data = self.search_index[user_input]
            hierarchy_path = self._get_hierarchy_path(user_input)
            # Get additional data from main_tribe if this is a subfamily
            main_tribe_name = search_data.get('main_tribe', '')
            main_tribe_data = self.main_tribes.get(main_tribe_name, {})
            logger.info(f"[TribalMatcher] ✅ EXACT match in index: '{user_input}' -> path: '{hierarchy_path}'")
            return TribeMatch(
                tribe_id=user_input,
                canonical_name=user_input,
                confidence=100,
                match_type=MatchType.EXACT,
                matched_variant=user_input,
                hierarchy_path=hierarchy_path,
                origin=main_tribe_data.get('origin', ''),
                description=main_tribe_data.get('description', ''),
                subfamilies=[]
            )
        
        # Step 2: Normalize and try variant lookup
        normalized = self.normalize_input(user_input)
        logger.debug(f"[TribalMatcher] Normalized input: '{user_input}' → '{normalized}'")
        
        if normalized in self.variant_to_canonical:
            canonical = self.variant_to_canonical[normalized]
            hierarchy_path = self._get_hierarchy_path(canonical)
            
            # Get tribe data for additional fields
            tribe_data = self.main_tribes.get(canonical, {})
            if not tribe_data:
                # It's a subfamily - get main tribe data for origin/description
                index_data = self.search_index.get(canonical, {})
                main_tribe_name = index_data.get('main_tribe', '')
                tribe_data = self.main_tribes.get(main_tribe_name, {})
            
            logger.info(f"[TribalMatcher] ✅ VARIANT match: '{user_input}' → '{canonical}' -> path: '{hierarchy_path}'")
            return TribeMatch(
                tribe_id=canonical,
                canonical_name=canonical,
                confidence=95,
                match_type=MatchType.VARIANT,
                matched_variant=normalized,
                hierarchy_path=hierarchy_path,
                origin=tribe_data.get('origin', '') if isinstance(tribe_data, dict) else '',
                description=tribe_data.get('description', '') if isinstance(tribe_data, dict) else '',
                subfamilies=tribe_data.get('subfamilies', []) if isinstance(tribe_data, dict) else []
            )
        
        # Step 3: Fuzzy matching (safety net)
        fuzzy_result = self._fuzzy_match(normalized, threshold=confidence_threshold / 100.0)
        if fuzzy_result:
            canonical, matched_variant, score = fuzzy_result
            confidence = int(score * 100)
            
            if confidence >= confidence_threshold:
                hierarchy_path = self._get_hierarchy_path(canonical)
                
                # Get tribe data for additional fields
                tribe_data = self.main_tribes.get(canonical, {})
                if not tribe_data:
                    # It's a subfamily - get main tribe data for origin/description
                    index_data = self.search_index.get(canonical, {})
                    main_tribe_name = index_data.get('main_tribe', '')
                    tribe_data = self.main_tribes.get(main_tribe_name, {})
                
                match_type = MatchType.FUZZY_HIGH if score >= 0.90 else MatchType.FUZZY_MED
                logger.info(f"[TribalMatcher] ✅ FUZZY match ({confidence}%): '{user_input}' → '{canonical}' -> path: '{hierarchy_path}'")
                
                return TribeMatch(
                    tribe_id=canonical,
                    canonical_name=canonical,
                    confidence=confidence,
                    match_type=match_type,
                    matched_variant=matched_variant,
                    hierarchy_path=hierarchy_path,
                    origin=tribe_data.get('origin', '') if isinstance(tribe_data, dict) else '',
                    description=tribe_data.get('description', '') if isinstance(tribe_data, dict) else '',
                    subfamilies=tribe_data.get('subfamilies', []) if isinstance(tribe_data, dict) else []
                )
        
        logger.info(f"[TribalMatcher] ❌ No match found for: '{user_input}'")
        return None
    
    def search(self, query: str, limit: int = 10) -> List[TribeMatch]:
        """
        Search for tribes matching query (prefix search + fuzzy).
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
        
        Returns:
            List of TribeMatch objects sorted by confidence (descending)
        """
        logger.info(f"[TribalMatcher] Searching: '{query}' (limit={limit})")
        
        if not query or len(query) < 2:
            logger.warning(f"[TribalMatcher] Query too short: '{query}'")
            return []
        
        results = []
        normalized_query = self.normalize_input(query)
        logger.debug(f"[TribalMatcher] Normalized query: '{query}' → '{normalized_query}'")
        
        # Prefix matching
        for variant, canonical in self.variant_to_canonical.items():
            if variant.startswith(normalized_query):
                hierarchy_path = self._get_hierarchy_path(canonical)
                
                # Get tribe data for additional fields
                tribe_data = self.main_tribes.get(canonical, {})
                if not tribe_data:
                    index_data = self.search_index.get(canonical, {})
                    main_tribe_name = index_data.get('main_tribe', '')
                    tribe_data = self.main_tribes.get(main_tribe_name, {})
                
                results.append(TribeMatch(
                    tribe_id=canonical,
                    canonical_name=canonical,
                    confidence=90,
                    match_type=MatchType.VARIANT,
                    matched_variant=variant,
                    hierarchy_path=hierarchy_path,
                    origin=tribe_data.get('origin', '') if isinstance(tribe_data, dict) else '',
                    description=tribe_data.get('description', '') if isinstance(tribe_data, dict) else '',
                    subfamilies=tribe_data.get('subfamilies', []) if isinstance(tribe_data, dict) else []
                ))
        
        # Sort by confidence and deduplicate
        seen = set()
        unique_results = []
        for r in sorted(results, key=lambda x: -x.confidence):
            if r.canonical_name not in seen:
                seen.add(r.canonical_name)
                unique_results.append(r)
        
        final_results = unique_results[:limit]
        logger.info(f"[TribalMatcher] ✅ Search returned {len(final_results)} results")
        
        return final_results


# =============================================================================
# Singleton instance
# =============================================================================

_matcher_instance: Optional[TribalMatcherService] = None


def get_tribal_matcher() -> TribalMatcherService:
    """Get or create singleton matcher instance."""
    global _matcher_instance
    
    if (_matcher_instance is None):
        logger.info("[TribalMatcher] Creating singleton instance...")
        _matcher_instance = TribalMatcherService()
    
    return _matcher_instance


def initialize_tribal_matcher(tribe_brain_path: str = None) -> TribalMatcherService:
    """
    Initialize the tribal matcher service with optional custom path.
    
    Call this at startup to pre-load the database.
    """
    global _matcher_instance
    
    logger.info("[TribalMatcher] Explicit initialization requested...")
    _matcher_instance = TribalMatcherService(tribe_brain_path)
    
    return _matcher_instance
