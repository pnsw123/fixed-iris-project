#!/usr/bin/env python3
"""
Phase 7b: Source Search
Searches raw OCR pages for orphan names and extracts 21-page context.
Uses inverted index for fast lookup.
"""

import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# Paths
DATA_DIR = Path("../Data/ocr_output_v5")
OUTPUT_DIR = Path("gemini_output")
ORPHAN_QUEUE = OUTPUT_DIR / "orphan_queue.jsonl"
SOURCE_MATCHES = OUTPUT_DIR / "source_matches.jsonl"

CONTEXT_PAGES = 10  # Pages before and after (21 total)


def normalize_arabic(text: str) -> str:
    """Normalize Arabic text for matching."""
    # Remove diacritics
    text = re.sub(r'[\u064B-\u065F\u0670]', '', text)
    # Normalize alef variants
    text = text.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    # Normalize ya/alef maqsura
    text = text.replace('ى', 'ي')
    # Normalize ta marbuta
    text = text.replace('ة', 'ه')
    return text.strip()


def build_inverted_index(pages: list) -> dict:
    """Build word -> page_numbers index for fast search."""
    print("🔧 Building inverted index...")
    index = defaultdict(set)
    
    for page_num, page_path in enumerate(pages):
        try:
            text = page_path.read_text(encoding='utf-8')
            normalized = normalize_arabic(text)
            # Split into words
            words = set(re.findall(r'[\u0600-\u06FF]+', normalized))
            for word in words:
                if len(word) >= 2:  # Skip single letters
                    index[word].add(page_num)
        except:
            pass
    
    print(f"   Indexed {len(index):,} unique words")
    return index


def search_orphan(orphan: dict, index: dict, pages: list) -> dict:
    """Search for orphan in index and get context."""
    name = orphan.get("name", "")
    normalized_name = normalize_arabic(name)
    
    # Search for exact match or parts
    matched_pages = set()
    
    # Try exact name
    if normalized_name in index:
        matched_pages.update(index[normalized_name])
    
    # Try without common prefixes
    for prefix in ["ال", "بني", "بنو", "آل"]:
        if normalized_name.startswith(prefix):
            base = normalized_name[len(prefix):]
            if base in index:
                matched_pages.update(index[base])
    
    if not matched_pages:
        return {
            "name": name,
            "status": "not_found",
            "matched_pages": [],
            "context": ""
        }
    
    # Get best match (prefer central pages)
    matched_list = sorted(matched_pages)
    best_page = matched_list[len(matched_list) // 2]  # Middle occurrence
    
    # Get context (±10 pages)
    context_pages = []
    start = max(0, best_page - CONTEXT_PAGES)
    end = min(len(pages), best_page + CONTEXT_PAGES + 1)
    
    context_text = []
    for i in range(start, end):
        try:
            text = pages[i].read_text(encoding='utf-8')
            page_num = int(pages[i].stem.replace("page_", ""))
            context_text.append(f"--- صفحة {page_num} ---\n{text[:3000]}")
            context_pages.append(page_num)
        except:
            pass
    
    return {
        "name": name,
        "status": "found",
        "matched_pages": matched_list[:10],  # Top 10 matches
        "best_page": int(pages[best_page].stem.replace("page_", "")),
        "context_pages": context_pages,
        "context": "\n\n".join(context_text),
        "original_data": orphan
    }


def run_source_search():
    """Run source search for all orphans."""
    print("=" * 70)
    print("🔍 PHASE 7b: SOURCE SEARCH (21-Page Context)")
    print("=" * 70)
    print()
    
    # Load orphan queue
    print("📦 Loading orphan queue...")
    orphans = []
    with open(ORPHAN_QUEUE, 'r') as f:
        for line in f:
            orphans.append(json.loads(line))
    print(f"   Orphans to search: {len(orphans):,}")
    
    # Check for resume
    processed = set()
    if SOURCE_MATCHES.exists():
        with open(SOURCE_MATCHES, 'r') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    processed.add(item.get("name"))
                except:
                    pass
        print(f"   Already processed: {len(processed):,}")
    
    remaining = [o for o in orphans if o["name"] not in processed]
    print(f"   Remaining: {len(remaining):,}")
    print()
    
    if not remaining:
        print("   ✅ All orphans already searched!")
        return
    
    # Load pages
    print("📂 Loading OCR pages...")
    pages = sorted(DATA_DIR.glob("page_*.txt"))
    print(f"   Pages: {len(pages):,}")
    
    # Build index
    index = build_inverted_index(pages)
    print()
    
    # Search
    print("🔍 Searching for orphans...")
    start = datetime.now()
    found = 0
    not_found = 0
    done = 0
    
    with open(SOURCE_MATCHES, 'a') as f:
        for orphan in remaining:
            result = search_orphan(orphan, index, pages)
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
            f.flush()
            
            if result["status"] == "found":
                found += 1
            else:
                not_found += 1
            
            done += 1
            if done % 100 == 0:
                elapsed = (datetime.now() - start).total_seconds()
                rate = done / elapsed if elapsed > 0 else 0
                eta = (len(remaining) - done) / rate if rate > 0 else 0
                pct = done * 100 // len(remaining)
                
                print(f"\r   [{pct:3}%] {done:,}/{len(remaining):,} | "
                      f"Found: {found:,} | 404: {not_found:,} | "
                      f"{rate:.0f}/s | ETA: {eta:.0f}s", end='')
    
    print()
    print()
    print("=" * 70)
    print("✅ PHASE 7b COMPLETE")
    print("=" * 70)
    print(f"   Orphans found in source: {found:,}")
    print(f"   Orphans not found: {not_found:,}")
    print(f"   Output: {SOURCE_MATCHES}")


if __name__ == "__main__":
    run_source_search()
