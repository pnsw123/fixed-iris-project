#!/usr/bin/env python3
"""
Phase 6: Orphan Fix Pipeline
Uses 7-page sliding window to fix orphaned entities.
Includes robust retry logic for API rate limits.
"""

import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from google import genai
from google.genai import types
import re
import time
import random

# Configuration
PROJECT_ID = "vertical-planet-478023-m7"
LOCATION = "us-central1"
MODEL_ID = "gemini-2.5-flash"
PARALLEL_WORKERS = 5  # Drastically reduced to avoid 429 (Quota limit)
MAX_RETRIES = 10  # Increased retries for safety

# Paths
DATA_DIR = Path("../Data/ocr_output_v5")
OUTPUT_DIR = Path("gemini_output")
GRAY_AREA = OUTPUT_DIR / "gray_area_paths.json"
FIXED_OUTPUT = OUTPUT_DIR / "orphans_fixed.jsonl"

# Initialize client
client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION
)

ORPHAN_FIX_PROMPT = """
أنت خبير في أنساب القبائل العربية.

المهمة: ابحث عن النسب الكامل لـ "{name}" في النص التالي.

النص يتضمن 7 صفحات متتالية من كتاب الأنساب (قبل وبعد الصفحة الأصلية):

{context}

---

أريد معرفة:
1. ما هو النسب الكامل لـ "{name}"؟ (من الجد الأكبر إلى الاسم)
2. أي قبيلة ينتمي إليها؟
3. نوع المستوى (قبيلة/بطن/فخذ/عشيرة/أسرة)

أجب بـ JSON فقط:
{{
  "name": "{name}",
  "parent": "الأب المباشر",
  "root_tribe": "القبيلة الأم",
  "full_path": "القبيلة → البطن → الفخذ → الاسم",
  "type": "نوع المستوى",
  "confidence": 0.0-1.0,
  "found": true/false
}}
"""


def get_page_context(source_page: str) -> str:
    """Get 7-page context (Current -3 to +3)."""
    match = re.search(r'page_(\d+)', source_page)
    if not match:
        return ""
    
    page_num = int(match.group(1))
    
    pages_text = []
    for offset in range(-3, 4):
        page_path = DATA_DIR / f"page_{page_num + offset:05d}.txt"
        if page_path.exists():
            try:
                text = page_path.read_text(encoding='utf-8')
                pages_text.append(f"--- صفحة {page_num + offset} ---\n{text[:2000]}")
            except:
                pass
    
    return "\n\n".join(pages_text)


def call_llm_with_retry(prompt: str) -> str:
    """Call LLM with exponential backoff retry."""
    delay = 1
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=2048,
                    response_mime_type="application/json"
                )
            )
            return response.text
            
        except Exception as e:
            last_error = e
            # Check for 429 or other retryable errors
            error_str = str(e)
            if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "500" in error_str:
                # Exponential backoff + jitter
                sleep_time = delay * (2 ** attempt) + random.uniform(0, 1)
                time.sleep(sleep_time)
            else:
                # Non-retryable error
                raise e
                
    raise last_error


def fix_orphan(entity: dict) -> dict:
    """Try to fix an orphaned entity using 7-page context."""
    name = entity.get("name", "")
    source_page = entity.get("source_page", "")
    
    if not name or not source_page:
        return entity
    
    context = get_page_context(source_page)
    if not context:
        entity["fix_status"] = "no_context"
        return entity
    
    try:
        prompt = ORPHAN_FIX_PROMPT.format(name=name, context=context)
        
        response_text = call_llm_with_retry(prompt)
        
        if response_text:
            try:
                # response_mime_type="application/json" guarantees a JSON string
                result = json.loads(response_text)
                
                if result.get("found") and result.get("parent"):
                    entity["parent"] = result.get("parent")
                    entity["root_tribe"] = result.get("root_tribe")
                    entity["full_path"] = result.get("full_path")
                    entity["type"] = result.get("type", entity.get("type"))
                    entity["fix_status"] = "fixed"
                    entity["fix_confidence"] = result.get("confidence", 0.5)
                else:
                    entity["fix_status"] = "not_found"
            except json.JSONDecodeError:
                entity["fix_status"] = "parse_error"
                entity["error_details"] = response_text[:200]
        else:
            entity["fix_status"] = "no_response"
            
    except Exception as e:
        entity["fix_status"] = f"error: {str(e)[:50]}"
        # Only print serious errors (not solved by retry)
        # print(f"Failed {name}: {e}")
    
    return entity


def run_orphan_fix():
    print("=" * 70)
    print("🔧 PHASE 6: ORPHAN FIX (7-Page Context)")
    print("=" * 70)
    print(f"   Workers: {PARALLEL_WORKERS}")
    print()
    
    # Load orphans
    if not GRAY_AREA.exists():
        print("No gray area file found.")
        return

    with open(GRAY_AREA, 'r') as f:
        data = json.load(f)
    
    orphans = data.get("entities", [])
    print(f"   Orphans to fix: {len(orphans):,}")
    print()
    
    start = datetime.now()
    fixed_count = 0
    not_found = 0
    errors = 0
    done = 0
    
    # Resume check
    processed_ids = set()
    if FIXED_OUTPUT.exists():
        with open(FIXED_OUTPUT, 'r') as f:
            for line in f:
                try:
                    res = json.loads(line)
                    # Unique key: name + source_page
                    key = f"{res.get('name')}_{res.get('source_page')}"
                    processed_ids.add(key)
                except: pass
        print(f"   Resuming from {len(processed_ids):,} processed items")
    
    orphans_to_process = [o for o in orphans if f"{o.get('name')}_{o.get('source_page')}" not in processed_ids]
    print(f"   Remaining to process: {len(orphans_to_process):,}")
    print()

    with open(FIXED_OUTPUT, 'a') as f:
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {executor.submit(fix_orphan, o): o for o in orphans_to_process}
            
            for future in as_completed(futures):
                result = future.result()
                
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
                f.flush()
                
                status = result.get("fix_status", "")
                if status == "fixed":
                    fixed_count += 1
                elif status == "not_found":
                    not_found += 1
                else:
                    errors += 1
                
                done += 1
                if done % 10 == 0:
                    elapsed = (datetime.now() - start).total_seconds()
                    rate = done / elapsed if elapsed > 0 else 0
                    eta = (len(orphans_to_process) - done) / rate / 60 if rate > 0 else 0
                    pct = done * 100 // len(orphans_to_process) if len(orphans_to_process) > 0 else 100
                    
                    print(f"\r   [{pct:>3}%] {done:,}/{len(orphans_to_process):,} | "
                          f"Fixed: {fixed_count:,} | 404: {not_found:,} | Err: {errors:,} | "
                          f"{rate:.1f}/s | ETA: {eta:.1f}min", end='')

    print()
    print("=" * 70)
    print("✅ PHASE 6 COMPLETE")


if __name__ == "__main__":
    run_orphan_fix()
