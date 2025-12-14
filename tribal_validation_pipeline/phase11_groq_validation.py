#!/usr/bin/env python3
"""
Phase 11: Validate remaining OCR entities using Groq FREE tier
- Uses Llama 3.3 70B via Groq
- 30 RPM limit with 10 parallel workers
- Extracts hierarchy ONLY from raw OCR text, no internet knowledge
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

# Rate limiting: 30 RPM = 2 seconds per request minimum
PARALLEL_WORKERS = 10
SECONDS_PER_REQUEST = 2.5  # Safe margin

# Paths
DATA_DIR = Path("../Data/ocr_output_v5")
OUTPUT_DIR = Path("gemini_output")
EXTRACTION_FILE = OUTPUT_DIR / "ocr_extractions.jsonl"
CURRENT_TREE = OUTPUT_DIR / "tribal_tree_full.json"
VALIDATION_OUTPUT = OUTPUT_DIR / "groq_validated.jsonl"
CHECKPOINT_FILE = OUTPUT_DIR / "phase11_checkpoint.json"

# Initialize Groq client
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

# Prompt - extracts ONLY from provided OCR text
VALIDATION_PROMPT = """
أنت محلل نصوص. اقرأ النص التالي واستخرج معلومات القبيلة.

النص (من صفحة {page}):
{text}

الاسم المطلوب التحقق منه: {name}

مهمتك:
1. هل هذا الاسم موجود في النص؟
2. إذا نعم، ما هي القبيلة الأم (parent) المذكورة في النص؟
3. ما هو المسار الكامل (full path) إذا مذكور؟

أجب بـ JSON فقط:
{{
  "exists": true/false,
  "parent": "اسم الأب من النص أو null",
  "full_path": ["جد1", "جد2", "الاسم"] أو null,
  "quote": "اقتباس من النص يثبت ذلك"
}}

مهم: استخدم فقط المعلومات الموجودة في النص. لا تستخدم معلومات خارجية.
"""


def load_page_text(page_num: int) -> str:
    """Load raw OCR text from a page."""
    page_path = DATA_DIR / f"page_{page_num:05d}.txt"
    if page_path.exists():
        try:
            return page_path.read_text(encoding='utf-8')
        except:
            pass
    return ""


def validate_entity(entity: dict) -> dict:
    """Validate a single entity against OCR text using Groq."""
    name = entity.get("name", "")
    page_num = entity.get("source_page")
    
    # Load raw OCR text
    page_text = load_page_text(page_num)
    if not page_text:
        entity["validated"] = False
        entity["error"] = "no_page_text"
        return entity
    
    rate_limiter.acquire()
    
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{
                "role": "user",
                "content": VALIDATION_PROMPT.format(
                    page=page_num,
                    text=page_text[:4000],  # Limit text size
                    name=name
                )
            }],
            max_tokens=500,
            temperature=0.1
        )
        
        result_text = response.choices[0].message.content
        
        # Parse JSON response
        if "{" in result_text and "}" in result_text:
            start = result_text.index("{")
            end = result_text.rindex("}") + 1
            data = json.loads(result_text[start:end])
            
            entity["validated"] = data.get("exists", False)
            if data.get("parent"):
                entity["parent"] = data["parent"]
            if data.get("full_path"):
                entity["full_path"] = " → ".join(data["full_path"])
            if data.get("quote"):
                entity["source_quote"] = data["quote"]
            
            return entity
            
    except Exception as e:
        entity["validated"] = False
        entity["error"] = str(e)[:50]
    
    return entity


def save_checkpoint(processed: int, valid: int):
    """Save progress checkpoint."""
    checkpoint = {
        "processed": processed,
        "valid": valid,
        "timestamp": datetime.now().isoformat()
    }
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(checkpoint, f)


def run_validation():
    """Run Phase 11 validation."""
    print("=" * 70)
    print("📖 PHASE 11: GROQ VALIDATION (FREE TIER)")
    print("=" * 70)
    print(f"   Model: {MODEL}")
    print(f"   Workers: {PARALLEL_WORKERS}")
    print(f"   Rate: {60/SECONDS_PER_REQUEST:.0f} requests/min")
    print()
    
    # Load current tree to know what we already have
    print("📦 Loading current tree...")
    with open(CURRENT_TREE, 'r') as f:
        tree = json.load(f)
    existing_names = set(tree["name_index"].keys())
    print(f"   Already in tree: {len(existing_names)}")
    
    # Load all extractions
    print("📦 Loading OCR extractions...")
    all_entities = []
    with open(EXTRACTION_FILE, 'r') as f:
        for line in f:
            d = json.loads(line)
            for e in d.get("entities", []):
                e["source_page"] = d.get("page")
                # Only process if not already in tree
                if e.get("name") and e.get("name") not in existing_names:
                    all_entities.append(e)
    print(f"   New entities to validate: {len(all_entities)}")
    
    # Check for resume
    already_validated = set()
    if VALIDATION_OUTPUT.exists():
        with open(VALIDATION_OUTPUT, 'r') as f:
            for line in f:
                item = json.loads(line)
                already_validated.add(f"{item.get('name')}_{item.get('source_page')}")
        print(f"   Already validated: {len(already_validated)}")
    
    remaining = [e for e in all_entities if f"{e.get('name')}_{e.get('source_page')}" not in already_validated]
    print(f"   Remaining: {len(remaining)}")
    print()
    
    if not remaining:
        print("   ✅ All entities already validated!")
        return
    
    # Estimate time
    estimated_minutes = len(remaining) * SECONDS_PER_REQUEST / 60
    print(f"⏱️  Estimated time: {estimated_minutes:.0f} min ({estimated_minutes/60:.1f} hours)")
    print()
    
    # Validate with parallel workers
    print("🔄 Validating...")
    valid_count = 0
    processed = 0
    start = datetime.now()
    
    with open(VALIDATION_OUTPUT, 'a') as f:
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {executor.submit(validate_entity, e): e for e in remaining}
            
            for future in as_completed(futures):
                result = future.result()
                processed += 1
                
                if result.get("validated"):
                    f.write(json.dumps(result, ensure_ascii=False) + '\n')
                    f.flush()
                    valid_count += 1
                
                if processed % 20 == 0:
                    elapsed = (datetime.now() - start).total_seconds() / 60
                    rate = processed / elapsed if elapsed > 0 else 0
                    eta = (len(remaining) - processed) / rate if rate > 0 else 0
                    print(f"\r   [{processed:,}/{len(remaining):,}] valid={valid_count:,} | "
                          f"{rate:.1f}/min | ETA: {eta:.0f}min", end='', flush=True)
                    
                    # Checkpoint every 100
                    if processed % 100 == 0:
                        save_checkpoint(processed, valid_count)
    
    print()
    print()
    print("=" * 70)
    print("✅ PHASE 11 COMPLETE")
    print("=" * 70)
    print(f"   Validated: {valid_count}")
    print(f"   Output: {VALIDATION_OUTPUT}")


if __name__ == "__main__":
    run_validation()
