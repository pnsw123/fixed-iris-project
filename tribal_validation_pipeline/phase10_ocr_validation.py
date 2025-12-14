#!/usr/bin/env python3
"""
Phase 10: Dual-LLM OCR-Only Validation
- LLM #1: Extracts paths from OCR text
- LLM #2: Validates extraction exists in OCR text
- All paths cite source pages + quotes
"""

import json
import time
import random
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from google import genai
from google.genai import types

# Configuration
PROJECT_ID = "vertical-planet-478023-m7"
LOCATION = "us-central1"
MODEL_ID = "gemini-2.5-flash"

PARALLEL_WORKERS = 50
REQUESTS_PER_SECOND = 15
MAX_RETRIES = 3

# Paths
DATA_DIR = Path("../Data/ocr_output_v5")
OUTPUT_DIR = Path("gemini_output")
TREE_FILE = OUTPUT_DIR / "tribal_tree_v9.json"
EXTRACTION_OUTPUT = OUTPUT_DIR / "ocr_extractions.jsonl"

# Initialize client
client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION
)

# Rate limiter
class RateLimiter:
    def __init__(self, rps: float = 15):
        self.semaphore = threading.Semaphore(int(rps))
        self.interval = 1.0 / rps
        self.lock = threading.Lock()
        self.last = 0.0
    
    def acquire(self):
        self.semaphore.acquire()
        with self.lock:
            wait = self.last + self.interval - time.time()
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
        self.semaphore.release()

rate_limiter = RateLimiter(REQUESTS_PER_SECOND)

# LLM #1: Extractor prompt
EXTRACTOR_PROMPT = """
من النص التالي، استخرج كل القبائل والعشائر مع علاقاتها الهرمية.

النص (صفحة {page}):
{text}

أجب بـ JSON فقط:
{{
  "entities": [
    {{
      "name": "اسم القبيلة أو العشيرة",
      "parent": "اسم الأب/القبيلة الأم (أو null إذا غير مذكور)",
      "type": "قبيلة/بطن/فخذ/عشيرة/أسرة",
      "quote": "اقتباس من النص يثبت العلاقة"
    }}
  ]
}}

قواعد مهمة:
1. استخرج فقط ما هو مذكور صراحة في النص
2. لا تضف معلومات من خارج النص
3. الاقتباس يجب أن يكون من النص بالضبط
"""

# LLM #2: Validator prompt
VALIDATOR_PROMPT = """
تحقق من صحة هذا الاستخراج مقارنة بالنص الأصلي:

الاستخراج:
الاسم: {name}
الأب: {parent}
الاقتباس: {quote}

النص الأصلي (صفحة {page}):
{text}

أسئلة:
1. هل الاسم موجود في النص؟
2. هل علاقة الأب صحيحة ومذكورة في النص؟
3. هل الاقتباس موجود في النص؟

أجب بـ JSON:
{{
  "name_exists": true/false,
  "parent_correct": true/false,
  "quote_exists": true/false,
  "valid": true/false,
  "corrected_quote": "الاقتباس الصحيح من النص إذا كان مختلفاً"
}}
"""


def load_page(page_path: Path) -> str:
    """Load OCR page text."""
    try:
        return page_path.read_text(encoding='utf-8')
    except:
        return ""


def extract_from_page(page_path: Path) -> dict:
    """LLM #1: Extract entities from a single OCR page."""
    page_num = int(page_path.stem.replace("page_", ""))
    text = load_page(page_path)
    
    if not text or len(text) < 50:
        return {"page": page_num, "entities": [], "status": "empty"}
    
    rate_limiter.acquire()
    
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=EXTRACTOR_PROMPT.format(page=page_num, text=text[:8000]),
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=2048,
                response_mime_type="application/json"
            )
        )
        
        if response.text:
            data = json.loads(response.text)
            entities = data.get("entities", [])
            
            # Add page info to each entity
            for e in entities:
                e["source_page"] = page_num
            
            return {
                "page": page_num,
                "entities": entities,
                "status": "success"
            }
    except Exception as e:
        return {"page": page_num, "entities": [], "status": "error", "error": str(e)[:100]}
    
    return {"page": page_num, "entities": [], "status": "error"}


def validate_extraction(entity: dict, page_text: str) -> dict:
    """LLM #2: Validate extraction against original text."""
    rate_limiter.acquire()
    
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=VALIDATOR_PROMPT.format(
                name=entity.get("name", ""),
                parent=entity.get("parent", ""),
                quote=entity.get("quote", ""),
                page=entity.get("source_page", 0),
                text=page_text[:4000]
            ),
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=512,
                response_mime_type="application/json"
            )
        )
        
        if response.text:
            validation = json.loads(response.text)
            entity["validated"] = validation.get("valid", False)
            entity["validation_details"] = validation
            return entity
    except Exception as e:
        entity["validated"] = False
        entity["validation_error"] = str(e)[:100]
    
    return entity


# Progress tracking
progress = {"pages_done": 0, "entities_found": 0, "validated": 0, "total_pages": 0, "start": None}
progress_lock = threading.Lock()


def print_progress():
    with progress_lock:
        pages = progress["pages_done"]
        total = progress["total_pages"]
        entities = progress["entities_found"]
        validated = progress["validated"]
        
        if progress["start"]:
            elapsed = (datetime.now() - progress["start"]).total_seconds()
            rate = pages / elapsed if elapsed > 0 else 0
            eta = (total - pages) / rate / 60 if rate > 0 else 0
        else:
            rate, eta = 0, 0
        
        pct = pages * 100 // total if total > 0 else 0
        bar = '█' * (pct // 2) + '░' * (50 - pct // 2)
        
        print(f"\r[{bar}] {pct}% | {pages:,}/{total:,} pages | "
              f"Entities: {entities:,} | Validated: {validated:,} | "
              f"{rate:.1f}/s | ETA: {eta:.1f}min", end='', flush=True)


def run_validation():
    """Run dual-LLM OCR validation."""
    print("=" * 70)
    print("📖 PHASE 10: DUAL-LLM OCR-ONLY VALIDATION")
    print("=" * 70)
    print(f"   Model: {MODEL_ID}")
    print(f"   Workers: {PARALLEL_WORKERS}, RPS: {REQUESTS_PER_SECOND}")
    print()
    
    # Load OCR pages
    print("📦 Loading OCR pages...")
    pages = sorted([p for p in DATA_DIR.glob("page_*.txt")])
    print(f"   Total pages: {len(pages):,}")
    
    # Check for resume
    processed_pages = set()
    if EXTRACTION_OUTPUT.exists():
        with open(EXTRACTION_OUTPUT, 'r') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    processed_pages.add(item.get("page"))
                except:
                    pass
        print(f"   Already processed: {len(processed_pages):,}")
    
    remaining = [p for p in pages if int(p.stem.replace("page_", "")) not in processed_pages]
    print(f"   Remaining: {len(remaining):,}")
    print()
    
    if not remaining:
        print("   ✅ All pages already processed!")
        return
    
    progress["total_pages"] = len(remaining)
    progress["start"] = datetime.now()
    
    print("🔄 Phase 1: Extracting entities from OCR...")
    print()
    
    all_entities = []
    
    with open(EXTRACTION_OUTPUT, 'a') as f:
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {executor.submit(extract_from_page, p): p for p in remaining}
            
            for future in as_completed(futures):
                result = future.result()
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
                f.flush()
                
                with progress_lock:
                    progress["pages_done"] += 1
                    progress["entities_found"] += len(result.get("entities", []))
                    all_entities.extend(result.get("entities", []))
                
                if progress["pages_done"] % 50 == 0:
                    print_progress()
    
    print()
    print()
    print(f"   Pages processed: {progress['pages_done']:,}")
    print(f"   Entities extracted: {len(all_entities):,}")
    print()
    print("=" * 70)
    print("✅ PHASE 10 EXTRACTION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    run_validation()
