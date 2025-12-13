#!/usr/bin/env python3
"""
Phase 8 Retry: Retry failed research with conservative settings.
Only processes items that had ERROR status.
"""

import json
import re
import time
import random
import threading
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from google import genai
from google.genai import types

# Conservative configuration
PROJECT_ID = "vertical-planet-478023-m7"
LOCATION = "us-central1"
MODEL_ID = "gemini-2.5-flash"

PARALLEL_WORKERS = 30  # Reduced from 100
REQUESTS_PER_SECOND = 10  # Reduced from 30
MAX_RETRIES = 5  # Increased from 3

# Paths
OUTPUT_DIR = Path("gemini_output")
RESEARCH_OUTPUT = OUTPUT_DIR / "external_research.jsonl"
RETRY_OUTPUT = OUTPUT_DIR / "retry_research.jsonl"

# Initialize client
client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION
)

# Rate limiter
class RateLimiter:
    def __init__(self, rps: float = 10):
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

# Prompt
PROMPT = """
أنت خبير أنساب عربية. ابحث عن نسب "{name}".

أجب بـ JSON فقط:
{{
  "name": "{name}",
  "is_root": false,
  "full_path": ["القبيلة", "البطن", "الفخذ", "{name}"],
  "immediate_parent": "الأب المباشر",
  "root_tribe": "القبيلة الأم",
  "confidence": 0.9
}}

إذا كان هذا جذر قبيلة رئيسية (مثل عنزة، قحطان، حرب)، اجعل is_root = true و immediate_parent = null.
"""


def parse_json_safe(text):
    """Parse JSON with fallback for malformed responses."""
    if not text:
        return None
    
    # Try direct parse
    try:
        return json.loads(text)
    except:
        pass
    
    # Try to extract JSON from text
    try:
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            return json.loads(match.group())
    except:
        pass
    
    return None


def research_orphan(item: dict) -> dict:
    """Research a single orphan."""
    name = item.get("name", "")
    
    result = {
        "name": name,
        "original": item.get("original", {}),
        "status": "error",
    }
    
    for attempt in range(MAX_RETRIES):
        rate_limiter.acquire()
        
        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=PROMPT.format(name=name),
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=1024,
                    response_mime_type="application/json"
                )
            )
            
            if response.text:
                data = parse_json_safe(response.text)
                if data:
                    result["research"] = data
                    result["confidence"] = data.get("confidence", 0)
                    result["status"] = "success"
                    
                    if result["confidence"] >= 0.8:
                        result["decision"] = "APPROVE"
                    else:
                        result["decision"] = "REJECT"
                    
                    return result
                else:
                    result["error"] = "json_parse_error"
            else:
                result["error"] = "empty_response"
            
            # Wait before retry
            time.sleep(1 + random.uniform(0, 1))
            
        except Exception as e:
            error_str = str(e)
            if any(x in error_str for x in ["429", "RESOURCE_EXHAUSTED", "500"]):
                # Rate limited - back off
                time.sleep(min(60, (2 ** attempt) + random.uniform(0, 2)))
            else:
                result["error"] = str(e)[:100]
                if attempt == MAX_RETRIES - 1:
                    break
    
    result["decision"] = "ERROR"
    return result


# Progress
progress = {"done": 0, "approved": 0, "rejected": 0, "errors": 0, "total": 0, "start": None}
progress_lock = threading.Lock()


def update_progress(result):
    with progress_lock:
        progress["done"] += 1
        if result.get("decision") == "APPROVE":
            progress["approved"] += 1
        elif result.get("decision") == "REJECT":
            progress["rejected"] += 1
        else:
            progress["errors"] += 1


def print_progress():
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
            rate, eta = 0, 0
        
        pct = done * 100 // total if total > 0 else 0
        bar = '█' * (pct // 2) + '░' * (50 - pct // 2)
        
        print(f"\r[{bar}] {pct}% | {done:,}/{total:,} | "
              f"✅ {approved:,} | ❌ {rejected:,} | ⚠️ {errors:,} | "
              f"{rate:.1f}/s | ETA: {eta:.1f}min", end='', flush=True)


def run_retry():
    """Retry failed research."""
    print("=" * 70)
    print("🔄 PHASE 8 RETRY: Conservative Settings")
    print("=" * 70)
    print(f"   Model: {MODEL_ID}")
    print(f"   Workers: {PARALLEL_WORKERS}, RPS: {REQUESTS_PER_SECOND}")
    print()
    
    # Load errors from previous run
    print("📦 Loading previous errors...")
    errors_to_retry = []
    
    with open(RESEARCH_OUTPUT, 'r') as f:
        for line in f:
            item = json.loads(line)
            if item.get("decision") == "ERROR":
                errors_to_retry.append(item)
    
    print(f"   Errors to retry: {len(errors_to_retry):,}")
    
    # Check for resume
    processed = set()
    if RETRY_OUTPUT.exists():
        with open(RETRY_OUTPUT, 'r') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    processed.add(item.get("name"))
                except:
                    pass
        print(f"   Already retried: {len(processed):,}")
    
    remaining = [e for e in errors_to_retry if e["name"] not in processed]
    print(f"   Remaining: {len(remaining):,}")
    print()
    
    if not remaining:
        print("   ✅ All errors already retried!")
        return
    
    progress["total"] = len(remaining)
    progress["start"] = datetime.now()
    
    print("🔄 Retrying with conservative settings...")
    print()
    
    with open(RETRY_OUTPUT, 'a') as f:
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {executor.submit(research_orphan, e): e for e in remaining}
            
            for future in as_completed(futures):
                result = future.result()
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
                f.flush()
                
                update_progress(result)
                
                if progress["done"] % 10 == 0:
                    print_progress()
    
    print()
    print()
    print("=" * 70)
    print("✅ RETRY COMPLETE")
    print("=" * 70)
    print(f"   New approvals: {progress['approved']:,}")
    print(f"   Rejected: {progress['rejected']:,}")
    print(f"   Still erroring: {progress['errors']:,}")
    print(f"   Output: {RETRY_OUTPUT}")


if __name__ == "__main__":
    run_retry()
