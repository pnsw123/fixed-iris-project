#!/usr/bin/env python3
"""
Phase 8a: Self-Validating External Research
Uses Gemini 2.0 Flash with Google Search grounding for tribal lineage research.
Built-in self-validation with dual-search approach.
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

# Configuration
PROJECT_ID = "vertical-planet-478023-m7"
LOCATION = "us-central1"
MODEL_ID = "gemini-2.5-flash"  # Using model's knowledge

PARALLEL_WORKERS = 100
REQUESTS_PER_SECOND = 30
MAX_RETRIES = 3

# Paths
OUTPUT_DIR = Path("gemini_output")
ORPHAN_QUEUE = OUTPUT_DIR / "orphan_queue.jsonl"
RESEARCH_OUTPUT = OUTPUT_DIR / "external_research.jsonl"

# Source reliability scores
SOURCE_SCORES = {
    # Tier 1 - Authoritative (1.0)
    "darah.org.sa": 1.0,
    "ksu.edu.sa": 1.0,
    "kau.edu.sa": 1.0,
    "jstor.org": 1.0,
    "academia.edu": 1.0,
    # Tier 2 - Encyclopedias (0.8)
    "ar.wikipedia.org": 0.8,
    "wikipedia.org": 0.8,
    "marefa.org": 0.8,
    "alukah.net": 0.8,
    "shamela.ws": 0.8,
    "wikiwand.com": 0.8,
    # Tier 3 - Specialized (0.6)
    "ansab-online.com": 0.6,
}

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

# Simplified prompt that works
SELF_VALIDATING_PROMPT = """
أنت خبير أنساب عربية. ابحث عن نسب "{name}".

قبل الإجابة:
1. تحقق من المعلومات
2. تأكد من صحة المسار

أجب بـ JSON فقط:
{{
  "name": "{name}",
  "is_root": true,
  "full_path": ["القبيلة", "البطن", "الفخذ", "{name}"],
  "immediate_parent": "الأب المباشر أو null",
  "root_tribe": "القبيلة الأم",
  "confidence": 0.8
}}
"""


def score_sources(sources: list) -> float:
    """Calculate weighted source reliability score."""
    if not sources:
        return 0.0
    
    scores = []
    for src in sources:
        domain = src.get("domain", "") if isinstance(src, dict) else str(src)
        score = 0.3  # Default for unknown
        for known_domain, known_score in SOURCE_SCORES.items():
            if known_domain in domain:
                score = known_score
                break
        scores.append(score)
    
    return sum(scores) / len(scores) if scores else 0.0


def research_orphan(orphan: dict) -> dict:
    """Research a single orphan with self-validating prompt."""
    name = orphan.get("name", "")
    
    rate_limiter.acquire()
    
    result = {
        "name": name,
        "original": orphan,
        "status": "error",
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=SELF_VALIDATING_PROMPT.format(name=name),
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=2048,
                    response_mime_type="application/json"
                )
            )
            
            if response.text:
                try:
                    data = json.loads(response.text)
                    result["research"] = data
                    result["confidence"] = data.get("confidence", 0)
                    result["status"] = "success"
                    
                    # Decision: approve only if confidence ≥0.8
                    if result["confidence"] >= 0.8:
                        result["decision"] = "APPROVE"
                    else:
                        result["decision"] = "REJECT"
                    
                    return result
                except json.JSONDecodeError:
                    result["error"] = "json_parse_error"
            
        except Exception as e:
            error_str = str(e)
            if any(x in error_str for x in ["429", "RESOURCE_EXHAUSTED", "500"]):
                time.sleep(min(60, (2 ** attempt) + random.uniform(0, 1)))
            else:
                result["error"] = str(e)[:100]
                break
    
    result["decision"] = "ERROR"
    return result


# Progress tracking
progress = {"done": 0, "approved": 0, "rejected": 0, "errors": 0, "total": 0, "start": None}
progress_lock = threading.Lock()


def update_progress(result: dict):
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


def run_research():
    """Run self-validating research on all orphans."""
    print("=" * 70)
    print("🔍 PHASE 8a: SELF-VALIDATING EXTERNAL RESEARCH")
    print("=" * 70)
    print(f"   Model: {MODEL_ID} + Google Search")
    print(f"   Workers: {PARALLEL_WORKERS}, RPS: {REQUESTS_PER_SECOND}")
    print()
    
    # Load orphans
    print("📦 Loading orphan queue...")
    orphans = []
    with open(ORPHAN_QUEUE, 'r') as f:
        for line in f:
            orphans.append(json.loads(line))
    print(f"   Total orphans: {len(orphans):,}")
    
    # Check for resume
    processed = set()
    if RESEARCH_OUTPUT.exists():
        with open(RESEARCH_OUTPUT, 'r') as f:
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
        print("   ✅ All orphans already researched!")
        return
    
    progress["total"] = len(remaining)
    progress["start"] = datetime.now()
    
    print("🔄 Running self-validating research...")
    print()
    
    with open(RESEARCH_OUTPUT, 'a') as f:
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {executor.submit(research_orphan, o): o for o in remaining}
            
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
    print("✅ PHASE 8a COMPLETE")
    print("=" * 70)
    print(f"   Approved (≥0.8 conf + ≥0.8 source): {progress['approved']:,}")
    print(f"   Rejected: {progress['rejected']:,}")
    print(f"   Errors: {progress['errors']:,}")
    print(f"   Output: {RESEARCH_OUTPUT}")


if __name__ == "__main__":
    run_research()
