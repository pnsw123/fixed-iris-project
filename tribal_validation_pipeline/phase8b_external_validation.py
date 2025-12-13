#!/usr/bin/env python3
"""
Phase 8b: External Validation
Validates research results with a second LLM check.
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
MAX_RETRIES = 5

# Paths
OUTPUT_DIR = Path("gemini_output")
RESEARCH_OUTPUT = OUTPUT_DIR / "external_research.jsonl"
VALIDATED_OUTPUT = OUTPUT_DIR / "validated_research.jsonl"

# Known root tribes (should not have parents)
KNOWN_ROOTS = {
    "عنزة", "قحطان", "حرب", "شمر", "عتيبة", "مطير", "الدواسر",
    "قضاعة", "مضر", "ربيعة", "نزار", "كهلان", "حمير", "قريش",
    "هوازن", "غطفان", "أسد", "طيء", "تميم", "بكر", "تغلب",
    "العدنانية", "القحطانية", "همدان", "مذحج", "كندة",
}

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

VALIDATION_PROMPT = """
أنت مدقق أنساب. تحقق من هذا البحث:

الاسم: {name}
النتيجة: {result}

تحقق من:
1. هل المسار منطقي (قبيلة→بطن→فخذ→عشيرة→أسرة)؟
2. هل القبيلة الأم معروفة؟
3. هل هذا جذر (لا يحتاج أب)؟

أجب بـ JSON فقط:
{{
  "validated": true/false,
  "is_confirmed_root": true/false,
  "path_logical": true/false,
  "connects_to_known_root": true/false,
  "confidence_adjustment": 0.0,
  "notes": "ملاحظات"
}}
"""


def validate_research(item: dict) -> dict:
    """Validate a research result."""
    name = item.get("name", "")
    research = item.get("research", {})
    result = research.get("result", {})
    
    # Quick check: if already approved and research looks good
    if item.get("decision") != "APPROVE":
        return {**item, "final_decision": "REJECT", "reason": "not_approved_in_research"}
    
    # Check if it's a known root
    if name in KNOWN_ROOTS or result.get("is_root"):
        return {
            **item,
            "final_decision": "CONFIRMED_ROOT",
            "reason": "known_or_declared_root"
        }
    
    # Check path connects to known root
    full_path = result.get("full_path", [])
    root_tribe = result.get("root_tribe", "")
    
    if root_tribe in KNOWN_ROOTS or (full_path and full_path[0] in KNOWN_ROOTS):
        # Good - connects to known root
        pass
    else:
        # Unknown root - validate with LLM
        rate_limiter.acquire()
        
        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=VALIDATION_PROMPT.format(
                    name=name,
                    result=json.dumps(result, ensure_ascii=False)
                ),
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=512,
                    response_mime_type="application/json"
                )
            )
            
            if response.text:
                validation = json.loads(response.text)
                
                if validation.get("is_confirmed_root"):
                    return {**item, "final_decision": "CONFIRMED_ROOT", "validation": validation}
                
                if validation.get("validated") and validation.get("path_logical"):
                    return {**item, "final_decision": "APPROVE", "validation": validation}
                
                return {**item, "final_decision": "REJECT", "validation": validation}
                
        except Exception as e:
            return {**item, "final_decision": "ERROR", "error": str(e)[:100]}
    
    return {**item, "final_decision": "APPROVE", "reason": "connects_to_known_root"}


def run_validation():
    """Run external validation on research results."""
    print("=" * 70)
    print("✅ PHASE 8b: EXTERNAL VALIDATION")
    print("=" * 70)
    print()
    
    # Load research
    print("📦 Loading research results...")
    approved = []
    with open(RESEARCH_OUTPUT, 'r') as f:
        for line in f:
            item = json.loads(line)
            if item.get("decision") == "APPROVE":
                approved.append(item)
    
    print(f"   Approved in research: {len(approved):,}")
    
    # Check resume
    processed = set()
    if VALIDATED_OUTPUT.exists():
        with open(VALIDATED_OUTPUT, 'r') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    processed.add(item.get("name"))
                except:
                    pass
        print(f"   Already validated: {len(processed):,}")
    
    remaining = [a for a in approved if a["name"] not in processed]
    print(f"   Remaining: {len(remaining):,}")
    print()
    
    if not remaining:
        print("   ✅ All research already validated!")
        return
    
    start = datetime.now()
    confirmed_roots = 0
    final_approved = 0
    rejected = 0
    done = 0
    
    with open(VALIDATED_OUTPUT, 'a') as f:
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {executor.submit(validate_research, r): r for r in remaining}
            
            for future in as_completed(futures):
                result = future.result()
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
                f.flush()
                
                decision = result.get("final_decision")
                if decision == "CONFIRMED_ROOT":
                    confirmed_roots += 1
                elif decision == "APPROVE":
                    final_approved += 1
                else:
                    rejected += 1
                
                done += 1
                if done % 10 == 0:
                    elapsed = (datetime.now() - start).total_seconds()
                    rate = done / elapsed if elapsed > 0 else 0
                    pct = done * 100 // len(remaining)
                    print(f"\r   [{pct:3}%] {done:,}/{len(remaining):,} | "
                          f"Roots: {confirmed_roots:,} | ✅ {final_approved:,} | "
                          f"❌ {rejected:,} | {rate:.1f}/s", end='', flush=True)
    
    print()
    print()
    print("=" * 70)
    print("✅ PHASE 8b COMPLETE")
    print("=" * 70)
    print(f"   Confirmed roots: {confirmed_roots:,}")
    print(f"   Final approved: {final_approved:,}")
    print(f"   Rejected: {rejected:,}")


if __name__ == "__main__":
    run_validation()
