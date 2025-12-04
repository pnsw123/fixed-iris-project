#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tribal Name Matcher
3-layer matching system for finding tribes regardless of how users write the name.

Layer 1: Input Normalization
  - Remove ال prefix
  - Remove nisba suffixes (ي, ية, اني, انية)
  - Character normalization

Layer 2: Variant Pre-computation
  - Generate all possible written forms for each tribe
  - Store in lookup table for O(1) matching

Layer 3: Fuzzy Matching (Safety Net)
  - Levenshtein distance with 85% threshold
  - Confidence scoring
"""

import re
import json
import unicodedata
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class TribeNameMatcher:
    """3-layer matching system for Arabic tribal names."""
    
    def __init__(self, tribe_brain_path: str = None):
        """
        Initialize the matcher with the tribe database.
        
        Args:
            tribe_brain_path: Path to tribe_brain.json. If None, uses default location.
        """
        if tribe_brain_path is None:
            tribe_brain_path = Path(__file__).parent.parent / 'tribe_brain.json'
        
        with open(tribe_brain_path, 'r', encoding='utf-8') as f:
            self.db = json.load(f)
        
        # Get tribes (main_tribes key or tribes key depending on version)
        self.main_tribes = self.db.get('tribes', self.db.get('main_tribes', {}))
        self.search_index = self.db.get('index', self.db.get('search_index', {}))
        
        # Build variant lookup table
        self.variant_to_canonical: Dict[str, str] = {}
        self._build_variant_table()
    
    # =========================================================================
    # LAYER 1: Input Normalization
    # =========================================================================
    
    def normalize_input(self, user_input: str) -> str:
        """
        Normalize user input by removing ال and nisba suffixes.
        
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
        text = self._normalize_arabic(text)
        
        return text
    
    def _normalize_arabic(self, text: str) -> str:
        """Normalize Arabic character variants."""
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
        for tribe_name in self.main_tribes:
            variants = self._generate_variants(tribe_name)
            for variant in variants:
                normalized = self.normalize_input(variant)
                # Map normalized variant → canonical name
                if normalized not in self.variant_to_canonical:
                    self.variant_to_canonical[normalized] = tribe_name
        
        # Also add subfamilies from search index
        for subfamily_name in self.search_index:
            normalized = self.normalize_input(subfamily_name)
            if normalized not in self.variant_to_canonical:
                self.variant_to_canonical[normalized] = subfamily_name
    
    def _generate_variants(self, tribe_name: str) -> List[str]:
        """
        Generate all possible written forms of a tribe name.
        
        Rules:
        - Nisba adds ي (masculine) or ية (feminine)
        - Some tribes use اني/انية for nisba
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
        # Simple nisba: add ي/ية
        nisba_m = base + 'ي'
        nisba_f = base + 'ية'
        variants.extend([nisba_m, nisba_f, 'ال' + nisba_m, 'ال' + nisba_f])
        
        # Extended nisba for some names: add اني/انية
        nisba_m_ext = base + 'اني'
        nisba_f_ext = base + 'انية'
        variants.extend([nisba_m_ext, nisba_f_ext, 'ال' + nisba_m_ext, 'ال' + nisba_f_ext])
        
        return variants
    
    # =========================================================================
    # LAYER 3: Fuzzy Matching
    # =========================================================================
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein (edit) distance between two strings."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
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
    
    def _similarity_score(self, s1: str, s2: str) -> float:
        """Calculate similarity score (0.0 to 1.0) between two strings."""
        if not s1 or not s2:
            return 0.0
        
        distance = self._levenshtein_distance(s1, s2)
        max_len = max(len(s1), len(s2))
        return 1.0 - (distance / max_len)
    
    def _fuzzy_match(self, normalized_input: str, threshold: float = 0.85) -> Optional[Tuple[str, float]]:
        """
        Find best fuzzy match for normalized input.
        
        Returns:
            Tuple of (canonical_name, confidence) if match found, else None
        """
        best_match = None
        best_score = 0.0
        
        for normalized_variant, canonical in self.variant_to_canonical.items():
            score = self._similarity_score(normalized_input, normalized_variant)
            if score > best_score and score >= threshold:
                best_score = score
                best_match = canonical
        
        if best_match:
            return (best_match, best_score)
        return None
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    def match(self, user_input: str) -> Dict:
        """
        Match user input to a tribe in the database.
        
        Returns:
            {
                'matched': True/False,
                'canonical_name': str,  # The tribe's database name
                'confidence': float,    # 0.0-1.0
                'match_type': str,      # 'exact', 'variant', 'fuzzy', or 'none'
                'tribe_data': dict      # Full tribe data if found
            }
        """
        # Step 1: Try exact match (user typed canonical name)
        if user_input in self.main_tribes:
            return {
                'matched': True,
                'canonical_name': user_input,
                'confidence': 1.0,
                'match_type': 'exact',
                'tribe_data': self.main_tribes[user_input]
            }
        
        if user_input in self.search_index:
            return {
                'matched': True,
                'canonical_name': user_input,
                'confidence': 1.0,
                'match_type': 'exact',
                'tribe_data': self.search_index[user_input]
            }
        
        # Step 2: Normalize and try variant lookup
        normalized = self.normalize_input(user_input)
        
        if normalized in self.variant_to_canonical:
            canonical = self.variant_to_canonical[normalized]
            tribe_data = self.main_tribes.get(canonical) or self.search_index.get(canonical, {})
            return {
                'matched': True,
                'canonical_name': canonical,
                'confidence': 0.95,
                'match_type': 'variant',
                'tribe_data': tribe_data
            }
        
        # Step 3: Fuzzy matching (safety net)
        fuzzy_result = self._fuzzy_match(normalized, threshold=0.85)
        if fuzzy_result:
            canonical, score = fuzzy_result
            tribe_data = self.main_tribes.get(canonical) or self.search_index.get(canonical, {})
            return {
                'matched': True,
                'canonical_name': canonical,
                'confidence': score * 0.9,  # Reduce confidence for fuzzy matches
                'match_type': 'fuzzy',
                'tribe_data': tribe_data
            }
        
        return {
            'matched': False,
            'canonical_name': None,
            'confidence': 0.0,
            'match_type': 'none',
            'tribe_data': {}
        }
    
    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Search for tribes matching query (prefix search + fuzzy).
        
        Returns list of matches sorted by confidence.
        """
        results = []
        normalized_query = self.normalize_input(query)
        
        # Prefix matching
        for variant, canonical in self.variant_to_canonical.items():
            if variant.startswith(normalized_query):
                tribe_data = self.main_tribes.get(canonical) or self.search_index.get(canonical, {})
                results.append({
                    'canonical_name': canonical,
                    'confidence': 0.9,
                    'tribe_data': tribe_data
                })
        
        # Sort by confidence and deduplicate
        seen = set()
        unique_results = []
        for r in sorted(results, key=lambda x: -x['confidence']):
            if r['canonical_name'] not in seen:
                seen.add(r['canonical_name'])
                unique_results.append(r)
        
        return unique_results[:limit]


# =============================================================================
# CLI for testing
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Tribal Name Matcher')
    parser.add_argument('query', help='Name to match')
    parser.add_argument('--db', help='Path to tribe_brain.json')
    args = parser.parse_args()
    
    matcher = TribeNameMatcher(args.db)
    result = matcher.match(args.query)
    
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
