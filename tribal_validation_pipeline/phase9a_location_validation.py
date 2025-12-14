#!/usr/bin/env python3
"""
Phase 9a: Location Cross-Validation
Validates that discovered tribal paths are geographically consistent.
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

PARALLEL_WORKERS = 30
REQUESTS_PER_SECOND = 10

# Paths
OUTPUT_DIR = Path("gemini_output")
RETRY_OUTPUT = OUTPUT_DIR / "retry_research.jsonl"
EXTERNAL_OUTPUT = OUTPUT_DIR / "external_research.jsonl"
LOCATION_VALIDATION_OUTPUT = OUTPUT_DIR / "location_validation.jsonl"

# Known tribal regions
TRIBE_REGIONS = {
    'قحطان': ['السعودية', 'اليمن', 'الإمارات', 'قطر', 'عمان', 'الكويت', 'البحرين'],
    'عدنان': ['السعودية', 'العراق', 'الأردن', 'الكويت', 'سوريا'],
    'عنزة': ['السعودية', 'العراق', 'الأردن', 'سوريا', 'الكويت'],
    'حرب': ['السعودية'],
    'شمر': ['السعودية', 'العراق', 'سوريا'],
    'عتيبة': ['السعودية'],
    'مطير': ['السعودية', 'الكويت'],
    'تميم': ['السعودية', 'الكويت', 'قطر'],
    'قريش': ['السعودية', 'الحجاز'],
    'هوازن': ['السعودية'],
}

# Known valid migration patterns
VALID_MIGRATIONS = {
    'قحطان': ['السودان', 'مصر', 'المغرب', 'تونس', 'الجزائر', 'ليبيا', 'موريتانيا'],
    'عدنان': ['مصر', 'المغرب', 'تونس', 'ليبيا', 'الجزائر', 'السودان'],
    'قريش': ['مصر', 'السودان', 'المغرب', 'تونس'],
    'بني هلال': ['تونس', 'الجزائر', 'ليبيا', 'المغرب'],
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

VALIDATION_PROMPT = """
أنت خبير أنساب عربية. تحقق من هذه المعلومات:

الاسم: {name}
الموقع الأصلي: {country}
النسب المكتشف: {path}
القبيلة الأم: {root}

السؤال: هل قبيلة "{name}" الموجودة في {country} ترجع فعلاً إلى {root}؟
أم أنها قبيلة مختلفة لها نفس الاسم؟

أجب بـ JSON:
{{
  "decision": "same" أو "different" أو "unknown",
  "reasoning": "شرح موجز",
  "migration_valid": true أو false,
  "confidence": 0.9
}}

- "same": نفس القبيلة، هاجرت تاريخياً
- "different": قبيلة مختلفة بنفس الاسم
- "unknown": غير متأكد
"""


def check_migration(original_countries, root_tribe, full_path):
    """Check if this is a known valid migration pattern."""
    root = full_path[0] if full_path else root_tribe
    
    # Check if root has known migrations
    if root in VALID_MIGRATIONS:
        valid_destinations = VALID_MIGRATIONS[root]
        for country in original_countries:
            if country in valid_destinations:
                return True
    
    # Check if any ancestor in path has known migrations
    for ancestor in full_path:
        if ancestor in VALID_MIGRATIONS:
            valid_destinations = VALID_MIGRATIONS[ancestor]
            for country in original_countries:
                if country in valid_destinations:
                    return True
    
    return False


def validate_location(item: dict) -> dict:
    """Validate location consistency with LLM."""
    name = item['name']
    original = item.get('original', {})
    research = item.get('research', {})
    
    original_countries = original.get('countries', [])
    full_path = research.get('full_path', [])
    root_tribe = research.get('root_tribe', '')
    
    result = {
        'name': name,
        'original_countries': original_countries,
        'full_path': full_path,
        'root_tribe': root_tribe,
    }
    
    # First check known valid migrations
    if check_migration(original_countries, root_tribe, full_path):
        result['decision'] = 'valid_migration'
        result['reasoning'] = 'Known historical migration pattern'
        result['llm_called'] = False
        return result
    
    # Need LLM validation
    rate_limiter.acquire()
    
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=VALIDATION_PROMPT.format(
                name=name,
                country=', '.join(original_countries),
                path=' → '.join(full_path),
                root=root_tribe
            ),
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=512,
                response_mime_type="application/json"
            )
        )
        
        if response.text:
            data = json.loads(response.text)
            result['decision'] = data.get('decision', 'unknown')
            result['reasoning'] = data.get('reasoning', '')
            result['confidence'] = data.get('confidence', 0)
            result['llm_called'] = True
            return result
            
    except Exception as e:
        result['decision'] = 'error'
        result['error'] = str(e)[:100]
        result['llm_called'] = True
    
    return result


def find_mismatches():
    """Find all potential location mismatches."""
    mismatches = []
    
    # Load both research files
    for filepath in [EXTERNAL_OUTPUT, RETRY_OUTPUT]:
        if not filepath.exists():
            continue
        
        with open(filepath, 'r') as f:
            for line in f:
                item = json.loads(line)
                if item.get('decision') != 'APPROVE':
                    continue
                
                original = item.get('original', {})
                research = item.get('research', {})
                
                original_countries = original.get('countries', [])
                full_path = research.get('full_path', [])
                root_from_path = full_path[0] if full_path else ''
                
                # Check if potential mismatch
                if root_from_path in TRIBE_REGIONS:
                    expected = TRIBE_REGIONS[root_from_path]
                    if original_countries and not any(c in expected for c in original_countries):
                        mismatches.append(item)
    
    return mismatches


def run_validation():
    """Run location validation."""
    print("=" * 70)
    print("🌍 PHASE 9a: LOCATION CROSS-VALIDATION")
    print("=" * 70)
    print()
    
    # Find mismatches
    print("📦 Finding potential location mismatches...")
    mismatches = find_mismatches()
    print(f"   Potential mismatches: {len(mismatches)}")
    print()
    
    if not mismatches:
        print("   ✅ No mismatches to validate!")
        return
    
    # Validate
    print("🔄 Validating with LLM...")
    valid_migrations = 0
    same_tribe = 0
    different_tribe = 0
    unknown = 0
    errors = 0
    
    start = datetime.now()
    
    with open(LOCATION_VALIDATION_OUTPUT, 'w') as f:
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {executor.submit(validate_location, m): m for m in mismatches}
            
            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
                f.flush()
                
                decision = result.get('decision')
                if decision == 'valid_migration':
                    valid_migrations += 1
                elif decision == 'same':
                    same_tribe += 1
                elif decision == 'different':
                    different_tribe += 1
                elif decision == 'unknown':
                    unknown += 1
                else:
                    errors += 1
                
                if i % 10 == 0:
                    elapsed = (datetime.now() - start).total_seconds()
                    print(f"\r   [{i}/{len(mismatches)}] valid_mig={valid_migrations} same={same_tribe} diff={different_tribe} unk={unknown}", end='', flush=True)
    
    print()
    print()
    print("=" * 70)
    print("✅ PHASE 9a COMPLETE")
    print("=" * 70)
    print(f"   Valid migrations: {valid_migrations}")
    print(f"   Same tribe (LLM confirmed): {same_tribe}")
    print(f"   Different tribe (revert): {different_tribe}")
    print(f"   Unknown: {unknown}")
    print(f"   Errors: {errors}")


if __name__ == "__main__":
    run_validation()
