#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arabic Tribe Extractor
Extracts tribal hierarchies from موسوعة القبائل العربية using multi-pass regex extraction
with Arabic normalization and rigorous validation.
"""

import re
import json
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict


class ArabicNormalizer:
    """Handles Arabic text normalization for consistent matching."""
    
    @staticmethod
    def normalize(text: str) -> str:
        """
        Normalize Arabic text by handling character variants.
        Critical for matching tribe names with different spellings.
        """
        # Normalize unicode characters (handles presentation forms like ﻟ -> ل)
        text = unicodedata.normalize('NFKC', text)
        
        # Alef variants → single form
        text = re.sub('[إأٱآا]', 'ا', text)
        
        # Ya / Alef maksura
        text = re.sub('ى', 'ي', text)
        
        # Ta marbuta → ha (optional but helps with matching)
        text = re.sub('ة', 'ه', text)
        
        # Remove all diacritics (fatha, kasra, damma, sukun, shadda, tanwin)
        text = re.sub('[\u064B-\u0652]', '', text)
        
        # Remove tatweel/kashida (decorative stretching)
        text = re.sub('ـ', '', text)
        
        return text
    
    @staticmethod
    def clean_artifacts(text: str) -> str:
        """Remove page numbers, URLs, and formatting artifacts."""
        # Remove URLs
        text = re.sub(r'https?://[^\s]+', '', text)
        
        # Remove page numbers (e.g., "Page 1 of 298")
        text = re.sub(r'Page \d+ of \d+', '', text)
        
        # Remove LTR/RTL markers (including embeddings)
        text = re.sub('[\u200E\u200F\u202A\u202B\u202C\u202D\u202E]', '', text)
        
        # Remove form feed characters
        text = re.sub('\f', '', text)
        
        # Remove copyright symbol and other common OCR artifacts in tribes2
        text = re.sub(r'[©®]', '', text)
        
        # Remove Private Use Area characters (E000-F8FF)
        # These are often used for custom glyphs in PDFs
        text = re.sub(r'[\ue000-\uf8ff]', '', text)
        
        return text


class TribalExtractor:
    """Multi-pass extraction engine for tribal hierarchies."""
    
    def __init__(self, text: str):
        self.original_text = text
        self.normalized_text = ArabicNormalizer.normalize(
            ArabicNormalizer.clean_artifacts(text)
        )
        self.lines = self.normalized_text.split('\n')
        
        # Results storage
        self.main_tribes: Dict[str, Dict] = {}
        self.subfamilies: Dict[str, List[str]] = defaultdict(list)
        self.current_tribe: str = None
        
        # Validation tracking
        self.processed_lines: Set[int] = set()
        self.flagged_lines: List[Tuple[int, str]] = []
        
    def extract_all(self) -> Dict:
        """Run all extraction passes and build hierarchy."""
        print("🔍 Starting multi-pass extraction...", file=sys.stderr)
        
        # Pass 1: Strict patterns
        self._pass1_strict()
        
        # Pass 2: List parsing (New)
        self._pass_list_parsing()
        
        # Pass 3: Relaxed patterns
        self._pass2_relaxed()
        
        # Pass 4: Dictionary lookup
        self._pass3_dictionary()
        
        # Pass 5: Contextual phrases
        self._pass4_contextual()
        
        # Pass 6: Encyclopedia Style (Tribes 2.0)
        self._pass_encyclopedia(self.lines)
        
        # Build hierarchy
        hierarchy = self._build_hierarchy()
        
        # Generate validation report
        self._generate_validation_report()
        
        return hierarchy
    
    def _pass1_strict(self):
        """Pass 1: High-precision patterns with explicit markers."""
        print("  Pass 1: Strict patterns...", file=sys.stderr)
        
        patterns = [
            # Main tribes with [+] markers at END of line
            # Matches: (URL) Tribe Name - 1 [+] OR (URL) (Tribe Name) (1) [+]
            # We skip garbage at start, capture Arabic text, handle optional number formats
            (r'(?:.*?)([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)*)\s*(?:(?:[-–]\s*\d+)|(?:\(\d+\)))?\s*\[\+\]', 'main_tribe'),
            
            # Banu families
            (r'بنو\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)', 'subfamily'),
            (r'بني\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)', 'subfamily'),
            
            # Al families (آل)
            (r'آل\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)', 'subfamily'),
            
            # Al families (definite article ال)
            (r'(?:^|\s)ال([\u0600-\u06FF]{3,})', 'subfamily'),
            
            # Sections (فخذ)
            (r'فخذ\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)', 'subfamily'),
            
            # Sub-tribes (بطن)
            (r'بطن\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)', 'subfamily'),
            
            # Clans (عشيرة)
            (r'عشيره\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)', 'subfamily'),
            
            # Families (عائلة)
            (r'عائله\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)', 'subfamily'),
            
            # Children of (أولاد)
            (r'اولاد\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)', 'subfamily'),
            
            # People of (ذوي)
            (r'ذوي\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)', 'subfamily'),
            
            # Numbered lists (common in the file)
            (r'[-‪]\s*\d+\s*[-‪]\s*([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)', 'subfamily'),
        ]
        
        for line_num, line in enumerate(self.lines):
            for pattern, entity_type in patterns:
                matches = re.finditer(pattern, line)
                for match in matches:
                    # Extract name from appropriate group
                    if entity_type == 'subfamily' and match.lastindex >= 2:
                        name = match.group(2).strip()  # For numbered lists
                    else:
                        name = match.group(1).strip()
                    
                    # Clean up the name
                    name = re.sub(r'[\u200E\u200F\u202A\u202B\u202C\u202D\u202E]', '', name)  # Remove RTL markers
                    name = name.strip()
                    
                    if name and len(name) > 1 and not name.isdigit():  # Filter out single characters and numbers
                        if entity_type == 'main_tribe':
                            self.current_tribe = name
                            self.main_tribes[name] = {
                                'name': name,
                                'source_line': line_num,
                                'subfamilies': []
                            }
                        elif entity_type == 'subfamily' and self.current_tribe:
                            self.subfamilies[self.current_tribe].append(name)
                        
                        self.processed_lines.add(line_num)

    def _pass_list_parsing(self):
        """Pass 2: Extract names from list-like lines (e.g. separated by URLs or numbers)."""
        print("  Pass 2: List parsing...", file=sys.stderr)
        
        # Pattern for Name- Number (e.g. بشر- ١)
        # Matches: Name - Number
        name_dash_num = r'([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)*)\s*[-–]\s*\d+'
        
        for line_num, line in enumerate(self.lines):
            if line_num in self.processed_lines:
                continue
            
            # Check for Name- Number format
            matches = re.finditer(name_dash_num, line)
            found = False
            for match in matches:
                name = match.group(1).strip()
                if name and len(name) > 1 and self.current_tribe:
                    self.subfamilies[self.current_tribe].append(name)
                    found = True
            
            if found:
                self.processed_lines.add(line_num)
                continue
            
            # Clean artifacts first
            line = ArabicNormalizer.clean_artifacts(line)
            
            if 135 <= line_num <= 145:
                print(f"DEBUG Line {line_num}: {line}", file=sys.stderr)
            
            if line_num == 141:
                print(f"DEBUG Line 141: {line}", file=sys.stderr)
                print(f"DEBUG Line 141 hex: {line.encode('utf-8').hex()}", file=sys.stderr)
            
            # Look for "Name: Description" pattern
            if ':' in line:
                parts = line.split(':', 1)
                name_part = parts[0].strip()
                desc_part = parts[1].strip()
                
                # Filter out common non-tribe headers
                if name_part.startswith(('ومن ', 'من ', 'فمن ', 'اما ', 'ثانيا', 'ثالثا', 'رابعا', 'خامسا', 'سادسا', 'سابعا', 'ثامنا', 'تاسعا', 'عاشرا', 'و ', 'في ', 'اولا', 'فروع')):
                    continue
                
                # Filter out long sentences (likely descriptions)
                if len(name_part.split()) > 5:
                    continue
                    
                # Clean name (remove "Banou", "Al" if needed, but keep for now)
                clean_name = ArabicNormalizer.normalize(name_part)
                
                if line_num == 141:
                    print(f"DEBUG Line 141 clean_name: {clean_name}", file=sys.stderr)
                    print(f"DEBUG Line 141 clean_name hex: {clean_name.encode('utf-8').hex()}", file=sys.stderr)
                
                if "احامد" in clean_name:
                    print(f"DEBUG: Normalized name: '{clean_name}' from '{name_part}'", file=sys.stderr)
                
                # Check if it's a valid name (at least 2 chars)
                if len(clean_name) < 2:
                    continue
                
                # Parse parent from description (normalize first to handle diacritics)
                normalized_desc = ArabicNormalizer.normalize(desc_part)
                parent = self._parse_lineage(normalized_desc)
                
                self.current_tribe = clean_name
                self.main_tribes[clean_name] = {
                    'name': clean_name,
                    'source_line': line_num,
                    'description': desc_part,
                    'parent': parent,
                    'subfamilies': []
                }
                self.processed_lines.add(line_num)
                continue
            # Check for names between parentheses (likely URLs removed)
            # If line has multiple ( ) groups, treat as list
            if line.count('(') > 1:
                # Split by ( or )
                parts = re.split(r'[()]+', line)
                for part in parts:
                    part = part.strip()
                    # If part is Arabic text
                    if re.match(r'^[\u0600-\u06FF\s]+$', part):
                        name = part.strip()
                        if name and len(name) > 1 and self.current_tribe:
                            self.subfamilies[self.current_tribe].append(name)
                            self.processed_lines.add(line_num)
    
    def _pass2_relaxed(self):
        """Pass 3: Broader patterns with deNormalization."""
        print("  Pass 3: Relaxed patterns...", file=sys.stderr)
        
        patterns = [
            # Banu/Bani variants (deNormalized)
            (r'بن[وي]\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)', 'subfamily'),
            
            # Multi-word tribe names
            (r'قبيله\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)', 'subfamily'),
            
            # Hierarchical terms in any position
            (r'(فخذ|بطن|عشيره|قبيله)\s+([\u0600-\u06FF]+)', 'subfamily'),
        ]
        
        for line_num, line in enumerate(self.lines):
            if line_num in self.processed_lines:
                continue
                
            for pattern, entity_type in patterns:
                matches = re.finditer(pattern, line)
                for match in matches:
                    # Extract the name (might be in group 1 or 2 depending on pattern)
                    name = match.group(2) if match.lastindex >= 2 else match.group(1)
                    name = name.strip()
                    
                    if name and len(name) > 1 and self.current_tribe:
                        self.subfamilies[self.current_tribe].append(name)
                        self.processed_lines.add(line_num)
    
    def _pass3_dictionary(self):
        """Pass 3: Known name lookup from extracted entities."""
        print("  Pass 3: Dictionary lookup...", file=sys.stderr)
        
        # Build dictionary of all known names
        known_names = set()
        for tribe_data in self.main_tribes.values():
            known_names.add(tribe_data['name'])
        for subfamilies in self.subfamilies.values():
            known_names.update(subfamilies)
        
        # Scan for these names in any context
        for line_num, line in enumerate(self.lines):
            if line_num in self.processed_lines:
                continue
                
            for name in known_names:
                if name in line and len(name) > 2:
                    self.processed_lines.add(line_num)
                    break
    
    def _pass4_contextual(self):
        """Pass 4: Pattern phrases indicating hierarchy."""
        print("  Pass 4: Contextual phrases...", file=sys.stderr)
        
        contextual_patterns = [
            # "and from them" - signals subfamily following
            (r'ومنهم\s*:?\s*([\u0600-\u06FF\s,،]+)', 'list'),
            
            # "divides into" - signals branch enumeration
            (r'ينقسم\s+الي\s*:?\s*([\u0600-\u06FF\s,،]+)', 'list'),
            
            # "they are a sub-tribe of" - explicit relationship
            (r'وهم\s+بطن\s+من\s+([\u0600-\u06FF]+)', 'parent'),
        ]
        
        for line_num, line in enumerate(self.lines):
            for pattern, context_type in contextual_patterns:
                match = re.search(pattern, line)
                if match:
                    if context_type == 'list':
                        # Extract comma-separated list
                        items = match.group(1).split('،')
                        for item in items:
                            item = item.strip()
                            if item and len(item) > 1 and self.current_tribe:
                                self.subfamilies[self.current_tribe].append(item)
                    
                    self.processed_lines.add(line_num)

    def _pass_encyclopedia(self, lines):
        """
        Pass 5: Encyclopedia Style (Tribes 2.0)
        Pattern:
        Name: Description...
        Minhum: Sub1, Sub2... OR 1- Sub1 2- Sub2...
        """
        current_entry = None
        
        # Regex for "Name:" at start of line (handling RTL/garbage)
        # Matches: (garbage) Name (colon) Description
        re_entry = re.compile(r'^(?:[^\w\u0600-\u06FF]*)([\u0600-\u06FF\s]+)(?:\s*:\s*)(.+)', re.UNICODE)
        
        # Regex for "Minhum" (From them)
        re_minhum = re.compile(r'منهم\s*[:\s](.+)', re.UNICODE)
        
        # Regex for numbered list items "1- Name" or "-1 Name"
        re_numbered = re.compile(r'(?:^|\s)(?:[-–]?\d+[-–]|\d+\))\s*([\u0600-\u06FF\s]+)(?=(?:[-–]?\d+[-–]|\d+\))|$)', re.UNICODE)

        for i, line in enumerate(lines):
            line = ArabicNormalizer.clean_artifacts(line).strip()
            if not line:
                continue

            # Check for new Entry "Name: ..."
            match_entry = re_entry.match(line)
            if match_entry:
                name_part = match_entry.group(1).strip()
                desc_part = match_entry.group(2).strip()
                
                # Filter out noise (must be reasonable length)
                if len(name_part) > 50 or len(name_part) < 2:
                    continue
                
                # Filter out common non-tribe headers
                if name_part.startswith(('ومن ', 'من ', 'فمن ', 'اما ', 'ثانيا', 'ثالثا', 'رابعا', 'خامسا', 'سادسا', 'سابعا', 'ثامنا', 'تاسعا', 'عاشرا', 'و ', 'في ', 'اولا', 'فروع')):
                    continue
                
                # Filter out long sentences (likely descriptions)
                if len(name_part.split()) > 5:
                    continue
                    
                # Clean name (remove "Banou", "Al" if needed, but keep for now)
                clean_name = ArabicNormalizer.normalize(name_part)
                
                # Parse parent from description (normalize first to handle diacritics)
                normalized_desc = ArabicNormalizer.normalize(desc_part)
                parent = self._parse_lineage(normalized_desc)
                
                # Create new entry
                if clean_name not in self.main_tribes:
                    self.main_tribes[clean_name] = {
                        'name': clean_name,
                        'origin': parent if parent else "Unknown",
                        'description': desc_part,
                        'source_line': i
                    }
                current_entry = clean_name # Store name as current entry identifier
                self.processed_lines.add(i)
                
                # Check if "Minhum" is on the SAME line
                match_minhum_inline = re_minhum.search(desc_part)
                if match_minhum_inline:
                    list_content = match_minhum_inline.group(1)
                    self._extract_list_items(list_content, current_entry)
                
                continue

            # If we are inside an entry, look for "Minhum" or list items
            if current_entry:
                # Check for "Minhum" start
                match_minhum = re_minhum.search(line)
                if match_minhum:
                    list_content = match_minhum.group(1)
                    self._extract_list_items(list_content, current_entry)
                    self.processed_lines.add(i)
                    continue
                
                # Check for numbered list continuation
                # If line starts with number or dash-number
                if re.match(r'^(?:[-–]?\d+[-–]|\d+\))', line):
                    self._extract_list_items(line, current_entry)
                    self.processed_lines.add(i)
                    continue

    def _extract_list_items(self, text, parent_name):
        """Helper to extract names from a list string (comma or number separated)"""
        # Strategy 1: Numbered list
        # We split by numbers
        parts = re.split(r'(?:[-–]?\d+[-–]|\d+\))', text)
        if len(parts) > 1:
            for p in parts:
                p = p.strip()
                # Remove punctuation
                p = re.sub(r'[،,.-]', '', p).strip()
                if p and len(p) > 2:
                     # Normalize
                    clean_sub = ArabicNormalizer.normalize(p)
                    if clean_sub not in self.subfamilies[parent_name]:
                        self.subfamilies[parent_name].append(clean_sub)
            return

        # Strategy 2: Comma/Dash separated
        # Split by commas or dashes (if not numbered)
        parts = re.split(r'[،,]', text)
        for p in parts:
            p = p.strip()
            if p and len(p) > 2:
                clean_sub = ArabicNormalizer.normalize(p)
                if clean_sub not in self.subfamilies[parent_name]:
                    self.subfamilies[parent_name].append(clean_sub)
    
    def _pass_dictionary_style(self):
        """Pass 6: Dictionary style entries (e.g. Name : Description)."""
        print("  Pass 6: Dictionary style...", file=sys.stderr)
        
        # Pattern: (Start of line) (Mandatory garbage/marker) Name : Description
        # Matches: © Name : Description, 9 Name : Description
        # Group 1: Name
        # Group 2: Description (rest of line)
        pattern = r'^\s*[\d9©®\-\.]+\s*([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)*)\s*:\s*(.+)$'
        
        for line_num, line in enumerate(self.lines):
            if line_num in self.processed_lines:
                continue
            
            match = re.match(pattern, line)
            if match:
                name = match.group(1).strip()
                description = match.group(2).strip()
                
                # Clean name
                clean_name = self.normalizer.normalize(name)
                
                if line_num == 141:
                    print(f"DEBUG Pass 1 Line 141: name='{name}', clean='{clean_name}'", file=sys.stderr)
                
                # Filter out common non-tribe headers
                if name.startswith(('ومن ', 'من ', 'فمن ', 'اما ', 'ثانيا', 'ثالثا', 'رابعا', 'خامسا', 'سادسا', 'سابعا', 'ثامنا', 'تاسعا', 'عاشرا', 'و ', 'في ', 'اولا', 'فروع')):
                    continue
                
                if name and len(name) > 1:
                    # Parse lineage from description
                    parent = self._parse_lineage(description)
                    
                    self.current_tribe = name
                    self.main_tribes[name] = {
                        'name': name,
                        'source_line': line_num,
                        'description': description,
                        'parent': parent,
                        'subfamilies': []
                    }
                    self.processed_lines.add(line_num)

    def _parse_lineage(self, text: str) -> str:
        """Extract parent tribe from description text."""
        # Common lineage markers
        markers = [
            r'فرع من\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)',
            r'فخذ من\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)',
            r'بطن من\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)',
            r'من عشائر\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)',
            r'من قبيلة\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)',
            r'من بني\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)',
            r'من آل\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)',
            r'يرجعون الى\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)',
            r'من\s+([\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)'
        ]
        
        for marker in markers:
            match = re.search(marker, text)
            if match:
                parent = match.group(1).strip()
                # Clean up parent name
                parent = re.sub(r'[\u200E\u200F\u202A\u202B\u202C\u202D\u202E]', '', parent)
                # Take only the first 2-3 words to avoid capturing full sentences
                words = parent.split()
                if len(words) > 3:
                    parent = ' '.join(words[:3])
                if len(parent) > 2:
                    return parent
        
        return None
    
    def _build_hierarchy(self) -> Dict:
        """Build final hierarchical structure."""
        print("🏗️  Building hierarchy...", file=sys.stderr)
        
        result = {}
        
        for tribe_name, tribe_data in self.main_tribes.items():
            # Get unique subfamilies
            unique_subfamilies = list(set(self.subfamilies.get(tribe_name, [])))
            
            result[tribe_name] = {
                'name_ar': tribe_name,
                'name_normalized': tribe_name,
                'subfamilies': unique_subfamilies,
                'source_line': tribe_data['source_line'],
                'description': tribe_data.get('description', ''),
                'parent': tribe_data.get('parent', None),
                'subfamily_count': len(unique_subfamilies)
            }
        
        return result
    
    def _generate_validation_report(self):
        """Generate validation metrics and residual analysis."""
        print("\n📊 Validation Report:", file=sys.stderr)
        print(f"  Total lines: {len(self.lines)}", file=sys.stderr)
        print(f"  Processed lines: {len(self.processed_lines)}", file=sys.stderr)
        print(f"  Unprocessed lines: {len(self.lines) - len(self.processed_lines)}", file=sys.stderr)
        
        # Check for potential missed content
        kinship_keywords = ['بنو', 'بني', 'آل', 'فخذ', 'بطن', 'عشيره', 'قبيله', 'اولاد', 'ذوي']
        missed_lines = []
        
        for line_num, line in enumerate(self.lines):
            if line_num not in self.processed_lines:
                # Check if line contains kinship keywords
                if any(keyword in line for keyword in kinship_keywords):
                    missed_lines.append((line_num, line[:100]))  # First 100 chars
        
        if missed_lines:
            print(f"\n⚠️  Found {len(missed_lines)} lines with kinship keywords that weren't processed:", file=sys.stderr)
            for line_num, preview in missed_lines[:10]:  # Show first 10
                print(f"    Line {line_num}: {preview}...", file=sys.stderr)
        else:
            print("\n✅ No missed lines with kinship keywords!", file=sys.stderr)
        
        # Character count reconciliation
        original_chars = len(self.original_text)
        print(f"\n  Original character count: {original_chars:,}", file=sys.stderr)


def main():
    """Main extraction workflow."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract tribal hierarchies from text file.')
    parser.add_argument('input_file', nargs='?', help='Path to input text file')
    args = parser.parse_args()
    
    # Determine input file
    if args.input_file:
        tribes_file = Path(args.input_file)
    else:
        # Default to tribes.txt in parent directory
        tribes_file = Path(__file__).parent.parent / 'tribes.txt'
    
    if not tribes_file.exists():
        print(f"❌ Error: {tribes_file} not found!", file=sys.stderr)
        sys.exit(1)
    
    print(f"📖 Reading {tribes_file}...", file=sys.stderr)
    with open(tribes_file, 'r', encoding='utf-8') as f:
        text = f.read()
    
    # Extract
    extractor = TribalExtractor(text)
    hierarchy = extractor.extract_all()
    
    # Output results
    print(f"\n✅ Extraction complete!", file=sys.stderr)
    print(f"  Main tribes found: {len(hierarchy)}", file=sys.stderr)
    total_subfamilies = sum(data['subfamily_count'] for data in hierarchy.values())
    print(f"  Total subfamilies: {total_subfamilies}", file=sys.stderr)
    
    # Output JSON to stdout for subprocess consumption
    print("\n" + "="*50, file=sys.stderr) # Summary separator to stderr
    print(json.dumps(hierarchy, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
