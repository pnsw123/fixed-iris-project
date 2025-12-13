#!/usr/bin/env python3
"""
Phase 7c: Triple-LLM Validation Pipeline
Three-stage LLM validation: Extractor → Validator → Supervisor
"""

import json
import re
import time
import random
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from typing import Optional, List, Literal

from google import genai
from google.genai import types

# Configuration
PROJECT_ID = "vertical-planet-478023-m7"
LOCATION = "us-central1"
MODEL_ID = "gemini-2.5-flash"

PARALLEL_WORKERS = 50
REQUESTS_PER_SECOND = 15
MAX_RETRIES = 10

# Paths
OUTPUT_DIR = Path("gemini_output")
SOURCE_MATCHES = OUTPUT_DIR / "source_matches.jsonl"
LLM_EXTRACTIONS = OUTPUT_DIR / "llm_extractions.jsonl"
APPROVED_FILE = OUTPUT_DIR / "approved_extractions.jsonl"
REJECTED_FILE = OUTPUT_DIR / "rejected_extractions.jsonl"

# Initialize client
client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION
)

# Rate limiter
class RateLimiter:
    def __init__(self, rps: float = 15):
        self.interval = 1.0 / rps
        self.semaphore = threading.Semaphore(rps)
        self.lock = threading.Lock()
        self.last_request = 0.0
    
    def acquire(self):
        self.semaphore.acquire()
        with self.lock:
            now = time.time()
            wait = self.last_request + self.interval - now
            if wait > 0:
                time.sleep(wait)
            self.last_request = time.time()
        self.semaphore.release()

rate_limiter = RateLimiter(REQUESTS_PER_SECOND)

# ============================================================
# LLM PROMPTS
# ============================================================

EXTRACTOR_PROMPT = """أنت خبير في أنساب القبائل العربية مع خبرة 50 سنة.

المهمة: استخرج النسب الكامل لـ "{name}" من النص التالي.

النص (21 صفحة من كتاب الأنساب):

{context}

---

استخرج:
1. الأب المباشر (parent)
2. القبيلة الأم (root_tribe)
3. المسار الكامل من القبيلة الأم إلى الاسم
4. نوع المستوى (قبيلة/شعب/بطن/فخذ/عشيرة/أسرة)
5. الموقع الجغرافي إن وُجد

أجب بـ JSON فقط:
{{
  "name": "{name}",
  "parent": "الأب المباشر",
  "root_tribe": "القبيلة الأم",
  "full_path": "القبيلة → البطن → الفخذ → الاسم",
  "type": "نوع المستوى",
  "location": "الموقع",
  "confidence": 0.0-1.0,
  "found": true/false,
  "evidence": "اقتباس من النص يثبت ذلك"
}}"""

VALIDATOR_PROMPT = """أنت مدقق متخصص في التحقق من صحة بيانات الأنساب العربية.

المهمة: تحقق من صحة الاستخراج التالي.

الاستخراج:
{extraction}

النص الأصلي (مختصر):
{context_summary}

---

تحقق من:
1. هل الاسم "{name}" موجود فعلاً في النص؟
2. هل العلاقة الأبوية صحيحة ومذكورة في النص؟
3. هل المسار منطقي حسب تقاليد الأنساب العربية؟
4. هل الموقع متسق مع القبيلة؟

أجب بـ JSON فقط:
{{
  "extraction_valid": true/false,
  "checks": {{
    "name_found": true/false,
    "parent_confirmed": true/false,
    "path_logical": true/false,
    "location_consistent": true/false
  }},
  "confidence": 0.0-1.0,
  "issues": ["أي مشاكل وُجدت"],
  "notes": "ملاحظات إضافية"
}}"""

SUPERVISOR_PROMPT = """أنت المشرف النهائي على جودة بيانات الأنساب.

المهمة: قرر ما إذا كان يجب اعتماد هذا الاستخراج.

الاستخراج:
{extraction}

نتيجة التحقق:
{validation}

---

قرر:
- APPROVE: الاستخراج صحيح ويمكن إضافته للشجرة
- REJECT: الاستخراج خاطئ أو غير مؤكد
- RETRY: يحتاج إعادة استخراج مع توضيح

أجب بـ JSON فقط:
{{
  "decision": "APPROVE/REJECT/RETRY",
  "combined_confidence": 0.0-1.0,
  "reason": "سبب القرار",
  "ready_for_tree": true/false
}}"""


def call_llm(prompt: str) -> str:
    """Call LLM with retry logic."""
    rate_limiter.acquire()
    
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
            error_str = str(e)
            if any(x in error_str for x in ["429", "RESOURCE_EXHAUSTED", "500", "503"]):
                delay = min(60, (2 ** attempt) + random.uniform(0, 1))
                time.sleep(delay)
            else:
                raise e
    return ""


def parse_json(text: str) -> dict:
    """Parse JSON from LLM response."""
    try:
        return json.loads(text)
    except:
        # Try to find JSON in text
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
    return {}


def process_orphan(match: dict) -> dict:
    """Run triple-LLM validation on a single orphan."""
    name = match.get("name", "")
    context = match.get("context", "")
    
    if match.get("status") != "found" or not context:
        return {
            "name": name,
            "decision": "SKIP",
            "reason": "no_source_context"
        }
    
    result = {
        "name": name,
        "source_pages": match.get("matched_pages", []),
        "best_page": match.get("best_page"),
    }
    
    try:
        # Stage 1: Extractor
        extractor_prompt = EXTRACTOR_PROMPT.format(name=name, context=context[:50000])
        extraction_text = call_llm(extractor_prompt)
        extraction = parse_json(extraction_text)
        result["extraction"] = extraction
        
        if not extraction.get("found") or not extraction.get("parent"):
            result["decision"] = "REJECT"
            result["reason"] = "extraction_not_found"
            return result
        
        # Stage 2: Validator
        context_summary = context[:10000]  # Shorter for validator
        validator_prompt = VALIDATOR_PROMPT.format(
            extraction=json.dumps(extraction, ensure_ascii=False),
            context_summary=context_summary,
            name=name
        )
        validation_text = call_llm(validator_prompt)
        validation = parse_json(validation_text)
        result["validation"] = validation
        
        if not validation.get("extraction_valid"):
            result["decision"] = "REJECT"
            result["reason"] = "validation_failed"
            return result
        
        # Stage 3: Supervisor
        supervisor_prompt = SUPERVISOR_PROMPT.format(
            extraction=json.dumps(extraction, ensure_ascii=False),
            validation=json.dumps(validation, ensure_ascii=False)
        )
        supervisor_text = call_llm(supervisor_prompt)
        supervisor = parse_json(supervisor_text)
        result["supervisor"] = supervisor
        
        result["decision"] = supervisor.get("decision", "REJECT")
        result["combined_confidence"] = supervisor.get("combined_confidence", 0)
        result["ready_for_tree"] = supervisor.get("ready_for_tree", False)
        
    except Exception as e:
        result["decision"] = "ERROR"
        result["reason"] = str(e)[:100]
    
    return result


# Progress tracking
progress = {"done": 0, "approved": 0, "rejected": 0, "errors": 0, "total": 0, "start": None}
progress_lock = threading.Lock()


def update_progress(result: dict):
    """Update progress counters."""
    with progress_lock:
        progress["done"] += 1
        if result.get("decision") == "APPROVE":
            progress["approved"] += 1
        elif result.get("decision") in ["REJECT", "SKIP"]:
            progress["rejected"] += 1
        else:
            progress["errors"] += 1


def print_progress():
    """Print progress bar."""
    with progress_lock:
        done = progress["done"]
        total = progress["total"]
        approved = progress["approved"]
        rejected = progress["rejected"]
        errors = progress["errors"]
        
        if progress["start"]:
            elapsed = (datetime.now() - progress["start"]).total_seconds()
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate / 60 if rate > 0 else 0
        else:
            rate = 0
            eta = 0
        
        pct = done * 100 // total if total > 0 else 0
        bar = '█' * (pct // 2) + '░' * (50 - pct // 2)
        
        print(f"\r[{bar}] {pct}% | {done:,}/{total:,} | "
              f"✅ {approved:,} | ❌ {rejected:,} | ⚠️ {errors:,} | "
              f"{rate:.1f}/s | ETA: {eta:.1f}min", end='', flush=True)


def run_triple_llm():
    """Run triple-LLM validation pipeline."""
    print("=" * 70)
    print("🧠 PHASE 7c: TRIPLE-LLM VALIDATION")
    print("=" * 70)
    print(f"   Config: {PARALLEL_WORKERS} workers, {REQUESTS_PER_SECOND} RPS")
    print()
    
    # Load source matches
    print("📦 Loading source matches...")
    matches = []
    with open(SOURCE_MATCHES, 'r') as f:
        for line in f:
            matches.append(json.loads(line))
    
    found_matches = [m for m in matches if m.get("status") == "found"]
    print(f"   Total matches: {len(matches):,}")
    print(f"   With source context: {len(found_matches):,}")
    
    # Check for resume
    processed = set()
    if LLM_EXTRACTIONS.exists():
        with open(LLM_EXTRACTIONS, 'r') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    processed.add(item.get("name"))
                except:
                    pass
        print(f"   Already processed: {len(processed):,}")
    
    remaining = [m for m in found_matches if m["name"] not in processed]
    print(f"   Remaining: {len(remaining):,}")
    print()
    
    if not remaining:
        print("   ✅ All matches already processed!")
        return
    
    # Initialize progress
    progress["total"] = len(remaining)
    progress["start"] = datetime.now()
    
    print("🔄 Running triple-LLM pipeline...")
    print()
    
    with open(LLM_EXTRACTIONS, 'a') as f_all, \
         open(APPROVED_FILE, 'a') as f_approved, \
         open(REJECTED_FILE, 'a') as f_rejected:
        
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {executor.submit(process_orphan, m): m for m in remaining}
            
            for future in as_completed(futures):
                result = future.result()
                
                # Save to appropriate files
                f_all.write(json.dumps(result, ensure_ascii=False) + '\n')
                f_all.flush()
                
                if result.get("decision") == "APPROVE":
                    f_approved.write(json.dumps(result, ensure_ascii=False) + '\n')
                    f_approved.flush()
                else:
                    f_rejected.write(json.dumps(result, ensure_ascii=False) + '\n')
                    f_rejected.flush()
                
                update_progress(result)
                
                if progress["done"] % 10 == 0:
                    print_progress()
    
    print()
    print()
    print("=" * 70)
    print("✅ PHASE 7c COMPLETE")
    print("=" * 70)
    print(f"   Approved: {progress['approved']:,}")
    print(f"   Rejected: {progress['rejected']:,}")
    print(f"   Errors: {progress['errors']:,}")
    print(f"   Output: {APPROVED_FILE}")


if __name__ == "__main__":
    run_triple_llm()
