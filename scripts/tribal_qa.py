#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tribal Data Quality Assurance Framework
7-Phase Validation Pipeline for ~52K lines of Arabic tribal data

Phases:
1. Data Profiling & Baseline Metrics
2. Automated Data Quality Checks
3. Cross-Source Validation
4. Semantic Validation
5. Manual Stratified Sampling
6. Deduplication & Merging
7. Final Verification & Export
"""

import json
import re
import sys
import statistics
import unicodedata
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, List, Set, Tuple, Any
from datetime import datetime
import random
import math


class TribalDataQA:
    """7-Phase Quality Assurance Framework for Tribal Data"""
    
    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent
        self.data_dir = Path(data_dir)
        self.qa_dir = self.data_dir / 'qa_reports'
        self.qa_dir.mkdir(exist_ok=True)
        
        # Source files
        self.source_files = [
            'tribes.txt',
            'tribes2.txt',
            'tribes2_normalized.txt'
        ]
        
        # Tribal database
        self.tribe_brain_path = self.data_dir / 'tribe_brain.json'
        
        # Arabic patterns
        self.PATTERNS = {
            'section_markers': r'\[\+\]',
            'tribal_prefixes': [
                r'بنو\s+',
                r'بني\s+',
                r'آل\s+',
                r'عشيرة\s+',
                r'فخذ\s+',
                r'بطن\s+',
                r'قبيلة\s+'
            ],
            'artifacts': [
                r'\d{3,}',              # Page numbers (3+ digits)
                r'https?://',           # URLs
                r'www\.',               # Web addresses
                r'[\u200E\u200F]',      # LTR/RTL markers
                r'\s{3,}',              # Multiple spaces
                r'[A-Za-z]{5,}'         # English text blocks
            ]
        }
    
    # =========================================================================
    # PHASE 1: Data Profiling & Baseline Metrics
    # =========================================================================
    
    def phase1_data_profiling(self) -> Dict:
        """Generate baseline statistics for all source files"""
        print("=" * 60)
        print("PHASE 1: Data Profiling & Baseline Metrics")
        print("=" * 60)
        
        results = {}
        
        for filename in self.source_files:
            filepath = self.data_dir / filename
            if not filepath.exists():
                print(f"  ⚠️  {filename} not found, skipping")
                continue
            
            print(f"\n📊 Profiling {filename}...")
            stats = self._profile_file(filepath)
            results[filename] = stats
            
            # Print summary
            print(f"   Total lines: {stats['total_lines']:,}")
            print(f"   Unique lines: {stats['unique_lines']:,}")
            print(f"   Arabic lines: {stats['arabic_lines']:,}")
            print(f"   Artifact lines: {stats['artifact_lines']:,}")
            print(f"   Duplicates: {stats['duplicates']:,}")
            print(f"   Avg line length: {stats['avg_line_length']:.1f}")
        
        # Save report
        report_path = self.qa_dir / 'phase1_baseline_stats.json'
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Saved: {report_path}")
        
        return results
    
    def _profile_file(self, filepath: Path) -> Dict:
        """Generate detailed statistics for a single file"""
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        unique_lines = len(set(lines))
        duplicates = total_lines - unique_lines
        
        arabic_lines = 0
        artifact_lines = 0
        line_lengths = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            line_lengths.append(len(line))
            
            # Check if line contains Arabic
            if re.search(r'[\u0600-\u06FF]', line):
                arabic_lines += 1
            
            # Check for artifacts
            has_artifact = any(
                re.search(pattern, line) 
                for pattern in self.PATTERNS['artifacts']
            )
            if has_artifact:
                artifact_lines += 1
        
        return {
            'total_lines': total_lines,
            'unique_lines': unique_lines,
            'arabic_lines': arabic_lines,
            'artifact_lines': artifact_lines,
            'duplicates': duplicates,
            'encoding': 'UTF-8',
            'avg_line_length': statistics.mean(line_lengths) if line_lengths else 0,
            'min_line_length': min(line_lengths) if line_lengths else 0,
            'max_line_length': max(line_lengths) if line_lengths else 0
        }
    
    def _analyze_patterns(self, filepath: Path) -> Dict:
        """Analyze pattern frequencies in a file"""
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
        
        # Normalize for pattern matching
        text = unicodedata.normalize('NFKC', text)
        
        pattern_counts = {}
        
        # Section markers
        pattern_counts['section_markers'] = len(re.findall(self.PATTERNS['section_markers'], text))
        
        # Tribal prefixes
        for prefix in self.PATTERNS['tribal_prefixes']:
            matches = len(re.findall(prefix, text))
            pattern_counts[prefix.replace(r'\s+', ' ').strip()] = matches
        
        return pattern_counts
    
    # =========================================================================
    # PHASE 2: Automated Data Quality Checks
    # =========================================================================
    
    def phase2_automated_checks(self) -> Dict:
        """Run comprehensive automated quality tests on tribe_brain.json"""
        print("\n" + "=" * 60)
        print("PHASE 2: Automated Data Quality Checks")
        print("=" * 60)
        
        # Load tribal database
        with open(self.tribe_brain_path, 'r', encoding='utf-8') as f:
            db = json.load(f)
        
        tribes = db.get('tribes', {})
        index = db.get('index', {})
        
        issues = {
            'critical': [],
            'warnings': [],
            'info': []
        }
        
        # Test A: Character Integrity
        print("\n🔍 Test A: Character Integrity...")
        char_issues = self._test_character_integrity(tribes)
        issues['critical'].extend(char_issues['critical'])
        issues['warnings'].extend(char_issues['warnings'])
        print(f"   Found {len(char_issues['critical'])} critical, {len(char_issues['warnings'])} warnings")
        
        # Test B: Structural Anomalies
        print("🔍 Test B: Structural Anomalies...")
        struct_issues = self._test_structural_anomalies(tribes)
        issues['warnings'].extend(struct_issues)
        print(f"   Found {len(struct_issues)} anomalies")
        
        # Test C: Hierarchy Integrity
        print("🔍 Test C: Hierarchy Integrity...")
        hier_issues = self._test_hierarchy_integrity(tribes, index)
        issues['critical'].extend(hier_issues['orphans'])
        issues['warnings'].extend(hier_issues['other'])
        print(f"   Orphans: {len(hier_issues['orphans'])}, Other: {len(hier_issues['other'])}")
        
        # Test D: Level Consistency
        print("🔍 Test D: Level Consistency...")
        level_issues = self._test_level_consistency(tribes, index)
        issues['warnings'].extend(level_issues)
        print(f"   Found {len(level_issues)} level mismatches")
        
        # Test E: Exact Duplicates
        print("🔍 Test E: Exact Duplicates...")
        exact_dupes = self._find_exact_duplicates(tribes, index)
        issues['warnings'].extend(exact_dupes)
        print(f"   Found {len(exact_dupes)} exact duplicates")
        
        # Test F: Fuzzy Duplicates
        print("🔍 Test F: Fuzzy Duplicates...")
        fuzzy_dupes = self._find_fuzzy_duplicates(tribes, threshold=90)
        issues['info'].extend(fuzzy_dupes[:50])  # Cap at 50 to avoid noise
        print(f"   Found {len(fuzzy_dupes)} potential fuzzy duplicates")
        
        # Test G: Name Format Validation
        print("🔍 Test G: Name Format Validation...")
        name_issues = self._test_name_formats(tribes)
        issues['warnings'].extend(name_issues)
        print(f"   Found {len(name_issues)} format issues")
        
        # Test H: Statistical Outliers
        print("🔍 Test H: Statistical Outliers...")
        outliers = self._detect_outliers(tribes)
        issues['info'].extend(outliers)
        print(f"   Found {len(outliers)} outliers")
        
        # Generate report
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_tribes': len(tribes),
            'total_index_entries': len(index),
            'tests_run': 8,
            'issues_found': {
                'critical': len(issues['critical']),
                'warnings': len(issues['warnings']),
                'info': len(issues['info'])
            },
            'issues': issues
        }
        
        report_path = self.qa_dir / 'phase2_automated_checks.json'
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Saved: {report_path}")
        
        # Summary
        print("\n" + "-" * 40)
        print("PHASE 2 SUMMARY:")
        print(f"  Critical issues: {len(issues['critical'])}")
        print(f"  Warnings: {len(issues['warnings'])}")
        print(f"  Info: {len(issues['info'])}")
        
        return report
    
    def _test_character_integrity(self, tribes: Dict) -> Dict:
        """Check for invalid characters in tribe names"""
        issues = {'critical': [], 'warnings': []}
        
        # Valid Unicode ranges for Arabic tribal names
        valid_ranges = [
            (0x0600, 0x06FF),  # Arabic
            (0x0750, 0x077F),  # Arabic Supplement
            (0x08A0, 0x08FF),  # Arabic Extended-A
            (0x0020, 0x007F),  # Basic Latin (spaces, punctuation)
        ]
        
        for name, data in tribes.items():
            for char in name:
                code = ord(char)
                is_valid = any(start <= code <= end for start, end in valid_ranges)
                if not is_valid and not char.isspace():
                    issues['warnings'].append({
                        'type': 'invalid_character',
                        'tribe': name,
                        'char': char,
                        'code_point': hex(code)
                    })
                    break
        
        return issues
    
    def _test_structural_anomalies(self, tribes: Dict) -> List:
        """Detect structural problems in names"""
        issues = []
        
        for name, data in tribes.items():
            # Check for suspiciously long names (50+ chars without space)
            if re.search(r'\S{50,}', name):
                issues.append({
                    'type': 'missing_spaces',
                    'tribe': name
                })
            
            # Check for repeated characters
            if re.search(r'(.)\1{4,}', name):
                issues.append({
                    'type': 'repeated_chars',
                    'tribe': name
                })
            
            # Check for names that are only numbers
            if re.match(r'^\d+$', name):
                issues.append({
                    'type': 'only_numbers',
                    'tribe': name
                })
        
        return issues
    
    def _test_hierarchy_integrity(self, tribes: Dict, index: Dict) -> Dict:
        """Verify parent-child relationships are valid"""
        issues = {'orphans': [], 'other': []}
        
        all_names = set(tribes.keys()) | set(index.keys())
        
        for name, data in index.items():
            # Check if parent exists
            main_tribe = data.get('main_tribe')
            if main_tribe and main_tribe not in tribes:
                issues['orphans'].append({
                    'type': 'orphaned_subfamily',
                    'tribe': name,
                    'missing_parent': main_tribe
                })
            
            # Check path validity
            path = data.get('path', [])
            if path:
                for ancestor in path[:-1]:  # Exclude self
                    if ancestor not in tribes and ancestor not in index:
                        issues['other'].append({
                            'type': 'invalid_path_element',
                            'tribe': name,
                            'missing_ancestor': ancestor
                        })
                        break
        
        return issues
    
    def _test_level_consistency(self, tribes: Dict, index: Dict) -> List:
        """Check if level assignments match hierarchy depth"""
        issues = []
        
        for name, data in index.items():
            path = data.get('path', [])
            depth = len(path)
            
            # Subfamilies should have depth > 1
            if data.get('type') == 'subfamily' and depth < 2:
                issues.append({
                    'type': 'level_mismatch',
                    'tribe': name,
                    'expected_depth': '>= 2',
                    'actual_depth': depth
                })
        
        return issues
    
    def _find_exact_duplicates(self, tribes: Dict, index: Dict) -> List:
        """Find tribes with identical normalized names"""
        issues = []
        
        # Normalize all names
        def normalize(name):
            name = unicodedata.normalize('NFKC', name)
            name = re.sub('[إأٱآا]', 'ا', name)
            name = re.sub('ى', 'ي', name)
            name = re.sub('ة', 'ه', name)
            name = re.sub(r'[\u064B-\u0652]', '', name)
            return name.strip()
        
        all_names = list(tribes.keys()) + list(index.keys())
        normalized_to_original = defaultdict(list)
        
        for name in all_names:
            norm = normalize(name)
            normalized_to_original[norm].append(name)
        
        for norm, originals in normalized_to_original.items():
            if len(originals) > 1:
                issues.append({
                    'type': 'exact_duplicate',
                    'normalized': norm,
                    'variants': originals
                })
        
        return issues
    
    def _find_fuzzy_duplicates(self, tribes: Dict, threshold: int = 90) -> List:
        """Find tribes with similar names (potential duplicates)"""
        issues = []
        
        names = list(tribes.keys())
        
        # Sample for performance (full O(n²) too slow for large datasets)
        if len(names) > 500:
            names = random.sample(names, 500)
        
        for i, name1 in enumerate(names):
            for name2 in names[i+1:]:
                similarity = self._similarity(name1, name2)
                if similarity >= threshold:
                    issues.append({
                        'type': 'fuzzy_duplicate',
                        'tribe1': name1,
                        'tribe2': name2,
                        'similarity': similarity
                    })
        
        return issues
    
    def _similarity(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein similarity percentage"""
        if not s1 or not s2:
            return 0
        
        m, n = len(s1), len(s2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i-1] == s2[j-1]:
                    dp[i][j] = dp[i-1][j-1]
                else:
                    dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
        
        distance = dp[m][n]
        max_len = max(m, n)
        return int((1 - distance / max_len) * 100)
    
    def _test_name_formats(self, tribes: Dict) -> List:
        """Check if names follow expected Arabic patterns"""
        issues = []
        
        for name, data in tribes.items():
            # Check for embedded URLs
            if re.search(r'https?://|www\.|\.com', name):
                issues.append({
                    'type': 'url_in_name',
                    'tribe': name
                })
            
            # Check for embedded page numbers
            if re.search(r'[\u0600-\u06FF]+\d{2,}[\u0600-\u06FF]+', name):
                issues.append({
                    'type': 'page_number_embedded',
                    'tribe': name
                })
            
            # Check for incomplete words (ends with connector)
            if name.endswith(('و', 'ا', 'ل')) and len(name) > 1:
                # This is often valid, so just log as info
                pass
        
        return issues
    
    def _detect_outliers(self, tribes: Dict) -> List:
        """Use statistics to find unusual entries"""
        issues = []
        
        # Name lengths
        lengths = [len(name) for name in tribes.keys()]
        if len(lengths) > 10:
            mean_len = statistics.mean(lengths)
            std_len = statistics.stdev(lengths)
            
            for name, data in tribes.items():
                name_len = len(name)
                if std_len > 0:
                    z_score = (name_len - mean_len) / std_len
                    if abs(z_score) > 3:
                        issues.append({
                            'type': 'outlier_length',
                            'tribe': name,
                            'length': name_len,
                            'z_score': round(z_score, 2)
                        })
        
        # Children counts
        child_counts = [len(data.get('subfamilies', [])) for name, data in tribes.items()]
        if child_counts:
            for name, data in tribes.items():
                count = len(data.get('subfamilies', []))
                if count > 50:
                    issues.append({
                        'type': 'many_children',
                        'tribe': name,
                        'children_count': count
                    })
        
        return issues
    
    # =========================================================================
    # PHASE 3-7: Additional phases (stubs for now)
    # =========================================================================
    
    def run_full_qa(self):
        """Run complete 7-phase QA pipeline"""
        print("\n" + "=" * 60)
        print("TRIBAL DATA QUALITY ASSURANCE")
        print("7-Phase Validation Pipeline")
        print("=" * 60)
        
        results = {}
        
        # Phase 1
        results['phase1'] = self.phase1_data_profiling()
        
        # Phase 2
        results['phase2'] = self.phase2_automated_checks()
        
        # Phases 3-7 (to be implemented)
        print("\n⚠️  Phases 3-7 require additional implementation")
        
        # Generate summary dashboard
        self._generate_dashboard(results)
        
        return results
    
    def _generate_dashboard(self, results: Dict):
        """Generate QA summary dashboard"""
        print("\n" + "=" * 60)
        print("QA DASHBOARD SUMMARY")
        print("=" * 60)
        
        # Phase 1 stats
        if 'phase1' in results:
            total_lines = sum(
                stats.get('total_lines', 0) 
                for stats in results['phase1'].values()
            )
            print(f"\n📊 Data Profiling:")
            print(f"   Total lines processed: {total_lines:,}")
        
        # Phase 2 stats
        if 'phase2' in results:
            p2 = results['phase2']
            print(f"\n🔍 Automated Checks:")
            print(f"   Total tribes: {p2.get('total_tribes', 0):,}")
            print(f"   Critical issues: {p2['issues_found']['critical']}")
            print(f"   Warnings: {p2['issues_found']['warnings']}")
            print(f"   Info: {p2['issues_found']['info']}")
        
        print("\n" + "=" * 60)


def main():
    qa = TribalDataQA()
    qa.run_full_qa()


if __name__ == '__main__':
    main()
