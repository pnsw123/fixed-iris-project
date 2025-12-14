#!/usr/bin/env python3
"""
Phase 12 Alternative: Search OCR text directly for parent relationships
NO LLM NEEDED - Just text pattern matching
"""

import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Paths
DATA_DIR = Path("../Data/ocr_output_v5")
OUTPUT_DIR = Path("gemini_output")
TREE_FILE = OUTPUT_DIR / "tribal_tree_full.json"
OUTPUT_FILE = OUTPUT_DIR / "parent_search_results.jsonl"

# Arabic patterns for parent relationships
PARENT_PATTERNS = [
    r"من\s+(قبيلة|بني|بنو|آل|ذوي|أولاد)\s+(\w+)",  # من قبيلة X, من بني X
    r"(قبيلة|بطن|فخذ|عشيرة)\s+من\s+(\w+)",  # قبيلة من X
    r"ينتسبون?\s+إلى\s+(\w+)",  # ينتسب إلى X
    r"يرجعون?\s+إلى\s+(\w+)",  # يرجع إلى X
    r"من\s+ذرية\s+(\w+)",  # من ذرية X
    r"من\s+نسل\s+(\w+)",  # من نسل X
    r"من\s+ولد\s+(\w+)",  # من ولد X
    r"فرع\s+من\s+(\w+)",  # فرع من X
]


def load_page_text(page_num: int) -> str:
    """Load raw OCR text from a page."""
    page_path = DATA_DIR / f"page_{page_num:05d}.txt"
    if page_path.exists():
        try:
            return page_path.read_text(encoding='utf-8')
        except:
            pass
    return ""


def search_for_parent(name: str, pages: list, name_index: dict) -> dict:
    """Search OCR pages for parent relationship mentions."""
    result = {
        "name": name,
        "found": False,
        "parent": None,
        "source_pages": pages,
        "quotes": []
    }
    
    # Load and combine page texts
    for page_num in pages[:10]:  # Check up to 10 pages
        text = load_page_text(page_num)
        if not text:
            continue
        
        # Search for name mentions with context
        name_pattern = re.escape(name)
        
        # Find all occurrences of the name
        for match in re.finditer(name_pattern, text):
            start = max(0, match.start() - 200)
            end = min(len(text), match.end() + 200)
            context = text[start:end]
            
            # Check for parent patterns in context
            for pattern in PARENT_PATTERNS:
                parent_match = re.search(f"{name_pattern}.*?{pattern}", context)
                if parent_match:
                    # Extract potential parent name
                    groups = parent_match.groups()
                    for g in groups:
                        if g and g in name_index and g != name:
                            result["found"] = True
                            result["parent"] = g
                            result["source_page"] = page_num
                            result["quotes"].append(context.strip()[:150])
                            return result
                
                # Try reverse pattern (parent mentioned before name)
                parent_match = re.search(f"{pattern}.*?{name_pattern}", context)
                if parent_match:
                    groups = parent_match.groups()
                    for g in groups:
                        if g and g in name_index and g != name:
                            result["found"] = True
                            result["parent"] = g
                            result["source_page"] = page_num
                            result["quotes"].append(context.strip()[:150])
                            return result
    
    return result


def run_search():
    """Search for parent relationships in OCR data."""
    print("=" * 60)
    print("🔍 PHASE 12: SEARCH OCR TEXT FOR PARENT RELATIONSHIPS")
    print("=" * 60)
    print("   Method: Direct text pattern matching (NO LLM)")
    print()
    
    # Load tree
    print("📦 Loading tree...")
    with open(TREE_FILE, 'r') as f:
        tree = json.load(f)
    
    name_index = tree["name_index"]
    print(f"   Total nodes: {len(name_index)}")
    
    # Find orphans
    orphans = {
        name: node for name, node in name_index.items()
        if not node.get("parent") or node.get("parent") not in name_index
    }
    print(f"   Orphans: {len(orphans)}")
    print()
    
    # Search for parents
    print("🔄 Searching OCR text...")
    found_count = 0
    start = datetime.now()
    
    with open(OUTPUT_FILE, 'w') as f:
        for i, (name, node) in enumerate(orphans.items(), 1):
            pages = node.get("source_pages", [])
            result = search_for_parent(name, pages, name_index)
            
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
            
            if result.get("found"):
                found_count += 1
            
            if i % 100 == 0:
                elapsed = (datetime.now() - start).total_seconds()
                rate = i / elapsed if elapsed > 0 else 0
                print(f"\r   [{i:,}/{len(orphans):,}] found={found_count:,} | {rate:.0f}/s", end='', flush=True)
    
    print()
    print()
    print("=" * 60)
    print("✅ SEARCH COMPLETE")
    print("=" * 60)
    print(f"   Parents found: {found_count}")
    print(f"   Not found: {len(orphans) - found_count}")
    print(f"   Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    run_search()
