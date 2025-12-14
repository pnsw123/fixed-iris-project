#!/usr/bin/env python3
"""
Phase 12: Find full 9-level ancestry paths for orphans using Groq
- For each orphan, search all OCR pages where it appears
- Ask Groq to extract the COMPLETE ancestry chain from the book text
- Store full path with page citations
"""

import json
import time
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from groq import Groq

# Configuration
API_KEY = "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"
MODEL = "llama-3.3-70b-versatile"

# Rate limiting: 30 RPM max - use 5 RPM for RELIABLE execution
PARALLEL_WORKERS = 1  # Single worker to avoid rate limits
SECONDS_PER_REQUEST = 12.0  # 5 RPM (very conservative)
MAX_RETRIES = 15  # More retries with longer backoff

# Paths
DATA_DIR = Path("../Data/ocr_output_v5")
OUTPUT_DIR = Path("gemini_output")
CURRENT_TREE = OUTPUT_DIR / "tribal_tree_full.json"
ORPHAN_OUTPUT = OUTPUT_DIR / "orphan_paths.jsonl"
CHECKPOINT_FILE = OUTPUT_DIR / "phase12_checkpoint.json"

# Initialize client
client = Groq(api_key=API_KEY)

# Rate limiter
class RateLimiter:
    def __init__(self, seconds_per_request: float = 2.5):
        self.lock = threading.Lock()
        self.last_request = 0.0
        self.interval = seconds_per_request
    
    def acquire(self):
        with self.lock:
            now = time.time()
            wait = self.last_request + self.interval - now
            if wait > 0:
                time.sleep(wait)
            self.last_request = time.time()

rate_limiter = RateLimiter(SECONDS_PER_REQUEST)

# Prompt for full ancestry extraction with location
ANCESTRY_PROMPT = """
أنت محلل أنساب عربية متخصص. مهمتك استخراج معلومات النسب من النص بدقة تامة.

═══════════════════════════════════════════════════
النص المصدر (من كتاب الأنساب، صفحات: {pages}):
═══════════════════════════════════════════════════
{text}

═══════════════════════════════════════════════════
المطلوب: استخراج معلومات "{name}"
═══════════════════════════════════════════════════

استخرج المعلومات التالية من النص فقط:

1. سلسلة النسب الكاملة (من الجد الأكبر إلى الاسم)
2. الموقع/البلد إذا ذُكر (السعودية، اليمن، مصر، الأردن، إلخ)
3. نوع الكيان (قبيلة، بطن، فخذ، عشيرة، أسرة)
4. اقتباس مباشر من النص يثبت النسب

أجب بـ JSON فقط:
{{
  "full_path": ["الجد_الأكبر", "جد2", "جد3", "...", "{name}"],
  "parent": "الأب المباشر أو null",
  "root_tribe": "القبيلة الأم (أول عنصر في السلسلة)",
  "countries": ["السعودية", "اليمن"],
  "regions": ["نجد", "الحجاز"],
  "entity_type": "قبيلة/بطن/فخذ/عشيرة/أسرة",
  "quote": "النص الحرفي من الكتاب",
  "confidence": 0.9
}}

═══════════════════════════════════════════════════
قواعد صارمة:
═══════════════════════════════════════════════════
1. استخدم فقط المعلومات الموجودة في النص أعلاه
2. لا تستخدم أي معرفة خارجية أو من الإنترنت
3. إذا لم تجد معلومة، اكتب null
4. الاقتباس يجب أن يكون نصاً حرفياً من المصدر
5. إذا لم تجد سلسلة النسب، أجب: {{"full_path": null}}
"""


def load_pages_for_entity(entity: dict) -> tuple:
    """Load all OCR pages where this entity appears."""
    pages = entity.get("source_pages", [])
    combined_text = []
    
    for page_num in pages[:5]:  # Limit to 5 pages
        page_path = DATA_DIR / f"page_{page_num:05d}.txt"
        if page_path.exists():
            try:
                text = page_path.read_text(encoding='utf-8')
                combined_text.append(f"--- صفحة {page_num} ---\n{text}")
            except:
                pass
    
    return pages, "\n\n".join(combined_text)


def find_ancestry(name: str, entity: dict) -> dict:
    """Find full ancestry path for an orphan using Groq with retry."""
    pages, combined_text = load_pages_for_entity(entity)
    
    if not combined_text:
        return {"name": name, "found": False, "error": "no_page_text"}
    
    for attempt in range(MAX_RETRIES):
        rate_limiter.acquire()
        
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{
                    "role": "user",
                    "content": ANCESTRY_PROMPT.format(
                        pages=", ".join(str(p) for p in pages[:5]),
                        text=combined_text[:6000],
                        name=name
                    )
                }],
                max_tokens=800,
                temperature=0.1
            )
            
            result_text = response.choices[0].message.content
            
            # Parse JSON
            if "{" in result_text and "}" in result_text:
                start = result_text.index("{")
                end = result_text.rindex("}") + 1
                data = json.loads(result_text[start:end])
                
                if data.get("full_path"):
                    return {
                        "name": name,
                        "found": True,
                        "full_path": data["full_path"],
                        "parent": data.get("parent"),
                        "root_tribe": data.get("root_tribe"),
                        "countries": data.get("countries", []),
                        "regions": data.get("regions", []),
                        "entity_type": data.get("entity_type"),
                        "quote": data.get("quote"),
                        "confidence": data.get("confidence", 0),
                        "source_pages": pages
                    }
            
            return {"name": name, "found": False, "error": "no_path_found"}
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate" in error_str.lower():
                # Rate limit - wait with longer backoff
                wait_time = 30 + (attempt * 15)  # 30s, 45s, 60s, 75s...
                print(f"\n   ⏳ Rate limited. Waiting {wait_time}s (attempt {attempt+1}/{MAX_RETRIES})...")
                time.sleep(wait_time)
                continue
            return {"name": name, "found": False, "error": error_str[:50]}
    
    return {"name": name, "found": False, "error": "max_retries_exceeded"}


def run_phase12(limit=None):
    """Find ancestry paths for all orphans."""
    print("=" * 70)
    print("🌳 PHASE 12: FIND FULL ANCESTRY PATHS FOR ORPHANS")
    print("=" * 70)
    print(f"   Model: {MODEL}")
    print(f"   Workers: {PARALLEL_WORKERS}")
    print(f"   Rate: {60/SECONDS_PER_REQUEST:.0f} requests/min")
    print()
    
    # Load tree and find orphans
    print("📦 Loading tree...")
    with open(CURRENT_TREE, 'r') as f:
        tree = json.load(f)
    
    name_index = tree["name_index"]
    
    orphans = {
        name: node for name, node in name_index.items()
        if not node.get("parent") or node.get("parent") not in name_index
    }
    print(f"   Total orphans: {len(orphans)}")
    
    # Check for resume
    already_processed = set()
    if ORPHAN_OUTPUT.exists():
        with open(ORPHAN_OUTPUT, 'r') as f:
            for line in f:
                item = json.loads(line)
                already_processed.add(item.get("name"))
        print(f"   Already processed: {len(already_processed)}")
    
    remaining = {n: o for n, o in orphans.items() if n not in already_processed}
    print(f"   Remaining: {len(remaining)}")
    print()
    
    if not remaining:
        print("   ✅ All orphans already processed!")
        return
    
    # Estimate time
    estimated_minutes = len(remaining) * SECONDS_PER_REQUEST / 60
    print(f"⏱️  Estimated time: {estimated_minutes:.0f} min ({estimated_minutes/60:.1f} hours)")
    print()
    
    # Process orphans
    print("🔄 Finding ancestry paths...")
    found_count = 0
    processed = 0
    recent_finds = []  # For live dashboard
    start = datetime.now()
    
    with open(ORPHAN_OUTPUT, 'a') as f:
        items = list(remaining.items())
        if limit:
            items = items[:limit]
            print(f"🧪 TEST MODE: Processing only {limit} orphans")
        
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {executor.submit(find_ancestry, name, entity): name 
                      for name, entity in items}
            
            for future in as_completed(futures):
                result = future.result()
                processed += 1
                
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
                f.flush()
                
                if result.get("found"):
                    found_count += 1
                    recent_finds.insert(0, {
                        "name": result["name"],
                        "path": " → ".join(result.get("full_path", [])),
                        "countries": result.get("countries", [])
                    })
                    recent_finds = recent_finds[:10]  # Keep last 10
                
                # Update progress file every 5 items
                if processed % 5 == 0:
                    elapsed = (datetime.now() - start).total_seconds() / 60
                    rate = processed / elapsed if elapsed > 0 else 0
                    progress_data = {
                        "processed": processed,
                        "found": found_count,
                        "total": len(items),
                        "rate": rate,
                        "recent": recent_finds[:5]
                    }
                    with open(OUTPUT_DIR / "progress.json", 'w') as pf:
                        json.dump(progress_data, pf)
                
                if processed % 20 == 0:
                    elapsed = (datetime.now() - start).total_seconds() / 60
                    rate = processed / elapsed if elapsed > 0 else 0
                    eta = (len(items) - processed) / rate if rate > 0 else 0
                    print(f"\r   [{processed:,}/{len(items):,}] found={found_count:,} | "
                          f"{rate:.1f}/min | ETA: {eta:.0f}min", end='', flush=True)
    
    print()
    print()
    print("=" * 70)
    print("✅ PHASE 12 COMPLETE")
    print("=" * 70)
    print(f"   Paths found: {found_count}")
    print(f"   Output: {ORPHAN_OUTPUT}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Find ancestry paths for orphans")
    parser.add_argument("--limit", type=int, default=None, help="Limit to first N orphans (for testing)")
    args = parser.parse_args()
    run_phase12(limit=args.limit)

