#!/usr/bin/env python3
"""
Phase 12 Local: Find ancestry paths using Ollama (Qwen2.5:3b)
- Runs 100% locally on Apple Silicon
- Parallel processing (4 workers)
- No rate limits, no API issues
"""

import json
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess

# Check Ollama is running
try:
    import ollama
except ImportError:
    print("Installing ollama package...")
    subprocess.run(["pip3", "install", "ollama", "-q"])
    import ollama

# Configuration
MODEL = "qwen2.5:3b"  # Best for Arabic, fast on M2
PARALLEL_WORKERS = 8   # M2 16GB can handle 8 workers with qwen2.5:3b
TIMEOUT = 60          # seconds per request

# Paths
DATA_DIR = Path("../Data/ocr_output_v5")
OUTPUT_DIR = Path("gemini_output")
CURRENT_TREE = OUTPUT_DIR / "tribal_tree_full.json"
ORPHAN_OUTPUT = OUTPUT_DIR / "orphan_paths_local.jsonl"
PROGRESS_FILE = OUTPUT_DIR / "progress_local.json"

# Highly engineered Arabic ancestry extraction prompt
ANCESTRY_PROMPT = """أنت محلل أنساب عربية متخصص ذو خبرة عالية في قراءة كتب الأنساب العربية.

═══════════════════════════════════════════════════════════════════
📖 النص المصدر (من كتاب معجم قبائل العرب)
═══════════════════════════════════════════════════════════════════
{text}

═══════════════════════════════════════════════════════════════════
🎯 المهمة: استخراج سلسلة نسب "{name}"
═══════════════════════════════════════════════════════════════════

## التعليمات:
1. ابحث عن أي ذكر للاسم "{name}" في النص
2. استخرج السلسلة الكاملة من الجد الأكبر إلى الاسم
3. حدد نوع الكيان: قبيلة > بطن > فخذ > عشيرة > أسرة

## أنماط النسب:
- "بنو X من بني Y من قبيلة Z" → [Z, Y, X]
- "X بن Y بن Z" → [Z, Y, X]

## قواعد صارمة:
✗ لا تستخدم معلومات خارجية
✓ استخدم فقط ما في النص

أجب بـ JSON فقط:
{{
  "full_path": ["الجد_الأكبر", "جد2", "{name}"] أو null,
  "parent": "الأب المباشر أو null",
  "entity_type": "قبيلة/بطن/فخذ"
}}"""


def ensure_ollama_running():
    """Make sure Ollama server is running."""
    try:
        ollama.list()
        return True
    except:
        print("⚠️  Starting Ollama server...")
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
        return True


def load_pages_for_entity(entity: dict) -> tuple:
    """Load OCR pages where entity appears."""
    pages = entity.get("source_pages", [])
    if not pages and entity.get("source_page"):
        pages = [entity.get("source_page")]
    
    combined_text = []
    for page_num in pages[:3]:  # Limit to 3 pages for speed
        page_path = DATA_DIR / f"page_{page_num:05d}.txt"
        if page_path.exists():
            try:
                text = page_path.read_text(encoding='utf-8')[:2000]  # Limit text size
                combined_text.append(text)
            except:
                pass
    
    return pages, "\n".join(combined_text)


def find_ancestry(name: str, entity: dict) -> dict:
    """Find ancestry path using local Ollama."""
    pages, combined_text = load_pages_for_entity(entity)
    
    if not combined_text:
        return {"name": name, "found": False, "error": "no_text"}
    
    try:
        response = ollama.chat(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": ANCESTRY_PROMPT.format(text=combined_text[:3000], name=name)
            }],
            options={"num_predict": 300}
        )
        
        result_text = response["message"]["content"]
        
        # Parse JSON from response
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
                    "entity_type": data.get("entity_type"),
                    "source_pages": pages
                }
        
        return {"name": name, "found": False, "error": "no_path"}
        
    except Exception as e:
        return {"name": name, "found": False, "error": str(e)[:50]}


def run_local(limit=None):
    """Process orphans using local Ollama."""
    print("=" * 60)
    print("🏠 PHASE 12 LOCAL: OLLAMA ANCESTRY FINDER")
    print("=" * 60)
    print(f"   Model: {MODEL}")
    print(f"   Workers: {PARALLEL_WORKERS}")
    print()
    
    # Ensure Ollama is running
    ensure_ollama_running()
    
    # Load tree
    print("📦 Loading tree...")
    with open(CURRENT_TREE, 'r') as f:
        tree = json.load(f)
    
    name_index = tree["name_index"]
    
    # Find orphans
    orphans = {
        name: node for name, node in name_index.items()
        if not node.get("parent") or node.get("parent") not in name_index
    }
    print(f"   Orphans: {len(orphans)}")
    
    # Check resume
    already = set()
    if ORPHAN_OUTPUT.exists():
        with open(ORPHAN_OUTPUT, 'r') as f:
            for line in f:
                already.add(json.loads(line).get("name"))
        print(f"   Already done: {len(already)}")
    
    remaining = {n: o for n, o in orphans.items() if n not in already}
    print(f"   Remaining: {len(remaining)}")
    print()
    
    if not remaining:
        print("✅ All orphans already processed!")
        return
    
    items = list(remaining.items())
    if limit:
        items = items[:limit]
        print(f"🧪 TEST MODE: {limit} orphans")
    
    # Estimate
    est_seconds = len(items) * 3 / PARALLEL_WORKERS
    print(f"⏱️  Est. time: {est_seconds/60:.1f} minutes")
    print()
    
    # Process
    print("🔄 Processing...")
    found = 0
    processed = 0
    start = datetime.now()
    
    with open(ORPHAN_OUTPUT, 'a') as f:
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {executor.submit(find_ancestry, n, e): n for n, e in items}
            
            for future in as_completed(futures):
                result = future.result()
                processed += 1
                
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
                f.flush()
                
                if result.get("found"):
                    found += 1
                
                if processed % 10 == 0:
                    elapsed = (datetime.now() - start).total_seconds()
                    rate = processed / elapsed if elapsed > 0 else 0
                    eta = (len(items) - processed) / rate / 60 if rate > 0 else 0
                    pct = processed / len(items) * 100
                    
                    # Progress bar
                    bar_len = 30
                    filled = int(bar_len * processed / len(items))
                    bar = "█" * filled + "░" * (bar_len - filled)
                    
                    print(f"\r   [{bar}] {pct:.0f}% | {processed}/{len(items)} | "
                          f"found={found} | {rate:.1f}/s | ETA={eta:.1f}m", end='', flush=True)
                    
                    # Save progress
                    with open(PROGRESS_FILE, 'w') as pf:
                        json.dump({
                            "processed": processed,
                            "found": found,
                            "total": len(items),
                            "rate": rate
                        }, pf)
    
    print()
    print()
    print("=" * 60)
    print("✅ COMPLETE")
    print("=" * 60)
    print(f"   Processed: {processed}")
    print(f"   Found: {found} ({found/processed*100:.0f}%)")
    print(f"   Output: {ORPHAN_OUTPUT}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit orphans (for testing)")
    args = parser.parse_args()
    run_local(limit=args.limit)
