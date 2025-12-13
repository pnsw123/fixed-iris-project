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
        """
        logger.info("[TribalMatcher] Initializing service...")
        start_time = datetime.now()
        
        backend_dir = Path(__file__).parent.parent
        
        # Load tribe_brain_v3.json
        if tribe_brain_path is None:
            tribe_brain_path = backend_dir / 'tribe_brain_v3.json'
        
        self.nodes = {}
        self.normalized_index = {}  # normalized_name -> original_name (canonical)
        self.variant_index = {}      # normalized_variant -> original_name (canonical)
        
        # Load new extraction if available
        try:
            with open(tribe_brain_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if 'tribes' in data:
                self.nodes = data['tribes']
            else:
                self.nodes = data
            
            # Ensure all nodes have IDs
            for key, node in self.nodes.items():
                if 'id' not in node:
                    node['id'] = key
            
            logger.info(f"[TribalMatcher] ✅ Loaded tribe_brain_v3: {len(self.nodes)} tribes")
        except FileNotFoundError:
            logger.warning(f"[TribalMatcher] New extraction not found at {tribe_brain_path}")
        
        # Build indices
        self._build_indices()
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"[TribalMatcher] ✅ Initialization complete in {elapsed:.2f}s")

    def _build_indices(self):
        """Build normalized indices for fast lookup."""
        count = 0
        for original_name, node in self.nodes.items():
            # 1. Index Canonical Name
            normalized = self.normalize_arabic_name(original_name)
            self.normalized_index[normalized] = original_name
            
            # 2. Index Variants
            # Generate variants from the name
            variants = self._generate_variants(original_name)
            
            # Add any pre-existing variants from node data
            if 'variants' in node:
                variants.extend(node['variants'])
                
            for variant in set(variants):
                norm_variant = self.normalize_arabic_name(variant)
                self.variant_index[norm_variant] = original_name
            
            count += 1
        
        logger.info(f"[TribalMatcher] Built index: {len(self.normalized_index)} normalized names, {len(self.variant_index)} variants")

    @staticmethod
    @lru_cache(maxsize=10000)
    def normalize_arabic_name(text: str) -> str:
        """
        PRODUCTION-GRADE normalization function.
        Handles: letter spacing, Al- removal, alef variants, nisba suffixes.
        """
        if not text:
            return ""
        
        # Fix letter spacing first (OCR artifacts)
        text = TribalMatcherService._fix_letter_spacing(text)
        
        # Unicode normalization
        text = unicodedata.normalize('NFKC', text)
        
        # Special case: آل (Aal) - Check BEFORE Alef normalization
        # If it starts with آل, we treat it as "Al" but preserve it (don't strip it later)
        is_aal = False
        if text.startswith('آل '): # Aal followed by space usually
             is_aal = True
        elif text.startswith('آل'):
             is_aal = True

        # Remove diacritics
        text = re.sub(r'[\u064B-\u065F\u0670]', '', text)
        
        # Remove tatweel
        text = text.replace('\u0640', '')
        
        # Normalize Alef variants: أ إ آ ٱ -> ا
        text = re.sub(r'[أإآٱ]', 'ا', text)
        
        # Normalize Teh Marbuta: ة → ه
        text = text.replace('ة', 'ه')
        
        # Normalize Ya: ى → ي
        text = text.replace('ى', 'ي')
        
        if is_aal:
             # Ensure it starts with 'ال' after normalization
             if not text.startswith('ال'):
                 text = 'ال' + text[2:]
             return text # Don't remove this ال
        
        # Remove definite article "ال"
        text = re.sub(r'^ال+', '', text)
        
        # Remove common prefixes: و (Wa-) only. 
        # Removing 'ب' (Bi-) and 'ف' (Fa-) is too aggressive for names like 'بلي', 'فهد'.
        if text.startswith('و') and len(text) > 3:
            text = text[1:]
        
        # Remove nisba suffixes: ي، ية، ون، ين
        # Note: ة is already ه, so we check for يه
        text = re.sub(r'(?:ي|يه|ون|ين)$', '', text)
        
        # Clean whitespace
        text = ' '.join(text.split())
        
        return text.strip()

    @staticmethod
    def _fix_letter_spacing(text: str) -> str:
        """Remove spaces between single Arabic letters (OCR fix)"""
        # Detect if this looks like letter-spaced OCR output
        if not TribalMatcherService._has_letter_spacing(text):
            return text
        
        # NFKC normalization first
        text = unicodedata.normalize('NFKC', text)
        
        # Remove spaces between single Arabic letters
        pattern = r'(?<=[\u0600-\u06FF])\s+(?=[\u0600-\u06FF](?:\s|$))'
        text = re.sub(pattern, '', text)
        
        return text

    @staticmethod
    def _has_letter_spacing(text: str) -> bool:
        """Quick check: does text have letter-level spacing?"""
        # Use lookarounds to avoid consuming characters so we can count overlapping patterns
        # e.g. "ح ر ب" has 2 spaces, both between letters
        matches = re.findall(r'(?<=[\u0600-\u06FF])\s+(?=[\u0600-\u06FF])', text)
        # Relaxed threshold: 2 spaces is enough for 3-letter words like "ح ر ب"
        return len(matches) >= 2

    def _generate_variants(self, name: str) -> List[str]:
        """Generate common spelling variants."""
        variants = set()
        variants.add(name)
        
        # With/without ال
        if name.startswith('ال'):
            variants.add(name[2:])
        else:
            variants.add('ال' + name)
        
        # With nisba suffixes
        variants.add(name + 'ي')
        variants.add(name + 'ية')
        
        return list(variants)

    def match(self, user_input: str, confidence_threshold: int = 70) -> Optional[TribeMatch]:
        """
        Match user input to tribe using 3-layer strategy.
        """
        logger.info(f"[TribalMatcher] Matching: '{user_input}'")
        
        if not user_input or len(user_input) < 2:
            return None

        # If input contains spaces (full name), try the full name first, then last word
        words = user_input.strip().split()
        inputs_to_try = [user_input]
        if len(words) > 1:
            inputs_to_try.append(words[-1])
        
        for input_to_match in inputs_to_try:
            result = self._match_single(input_to_match, confidence_threshold)
            if result:
                return result
        
        return None

    def _match_single(self, user_input: str, confidence_threshold: int = 70) -> Optional[TribeMatch]:
        """Match a single input string."""
        # Normalize input
        normalized_input = self.normalize_arabic_name(user_input)
        
        matched_node_id = None
        match_type = MatchType.NO_MATCH
        confidence = 0
        matched_variant = user_input
        
        # Layer 1: Exact Match (Normalized)
        if normalized_input in self.normalized_index:
            original_name = self.normalized_index[normalized_input]
            matched_node_id = self.nodes[original_name]['id']
            match_type = MatchType.EXACT
            confidence = 100
            matched_variant = original_name
            
        # Layer 2: Variant Match (Normalized)
        elif normalized_input in self.variant_index:
            original_name = self.variant_index[normalized_input]
            matched_node_id = self.nodes[original_name]['id']
            match_type = MatchType.VARIANT
            confidence = 95
            matched_variant = original_name
            
        # Layer 3: Fuzzy Match (Levenshtein)
        else:
            best_score = 0
            best_name = None
            
            # Check against normalized index
            for norm_name, original_name in self.normalized_index.items():
                score = self._similarity_score(normalized_input, norm_name)
                if score > best_score and score >= (confidence_threshold / 100.0):
                    best_score = score
                    best_name = original_name
            
            if best_name:
                matched_node_id = self.nodes[best_name]['id']
                confidence = int(best_score * 100)
                match_type = MatchType.FUZZY_HIGH if best_score >= 0.9 else MatchType.FUZZY_MED
                matched_variant = best_name

        if matched_node_id:
            node = self.nodes[matched_node_id]
            
            # Construct hierarchy path
            path_list = self._get_hierarchy_path(node)
            hierarchy_path = " > ".join(path_list)
            
            return TribeMatch(
                tribe_id=node.get('id'),
                canonical_name=node.get('name_ar'),
                confidence=confidence,
                match_type=match_type,
                matched_variant=matched_variant,
                hierarchy_path=hierarchy_path,
                origin="",
                description=node.get('source_text', ''),
                subfamilies=[]
            )
            
        return None

    def _get_hierarchy_path(self, node: dict) -> List[str]:
        """Get full hierarchy path list."""
        path = [node.get('name_ar')]
        current_node = node
        
        # Traverse up to 5 levels to prevent infinite loops
        for _ in range(5):
            parent_name = current_node.get('parent')
            if not parent_name or parent_name not in self.nodes:
                break
            
            # Avoid cycles
            if parent_name in path:
                break
                
            path.insert(0, parent_name)
            current_node = self.nodes[parent_name]
            
        return path

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

    def search(self, query: str, limit: int = 10) -> List[TribeMatch]:
        """Search for tribes matching query."""
        # Reuse match logic for single result, but could be expanded for multiple
        match = self.match(query)
        return [match] if match else []


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
