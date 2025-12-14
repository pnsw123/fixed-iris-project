#!/usr/bin/env python3
"""
Phase 10b: Validate extractions using FREE Google AI Studio API
- Uses google-genai with API key (not Vertex AI)
- Rate limited to 15 RPM to stay within free tier
- No charges!
"""

import json
import time
import os
from pathlib import Path
from datetime import datetime

import google.generativeai as genai

# API Key from environment or direct
API_KEY = os.environ.get("GOOGLE_API_KEY", "AIzaSyDy6JuJtdZRGeoH9Nff_Nha8dAeZESdxNg")
genai.configure(api_key=API_KEY)

# Use Gemini 1.5 Flash (free tier: 15 RPM)
model = genai.GenerativeModel('gemini-1.5-flash')

# Rate limit: 14 requests per minute (safe margin under 15)
REQUESTS_PER_MINUTE = 14
SECONDS_PER_REQUEST = 60.0 / REQUESTS_PER_MINUTE

# Paths
OUTPUT_DIR = Path("gemini_output")
DATA_DIR = Path("../Data/ocr_output_v5")
EXTRACTION_FILE = OUTPUT_DIR / "ocr_extractions.jsonl"
VALIDATION_OUTPUT = OUTPUT_DIR / "validated_free.jsonl"

VALIDATOR_PROMPT = """
تحقق من صحة هذا الاستخراج:

الاسم: {name}
الأب: {parent}
الاقتباس: "{quote}"

النص الأصلي (صفحة {page}):
{text}

هل هذه المعلومات موجودة في النص؟ أجب بـ JSON:
{{"valid": true/false, "corrected_quote": "الاقتباس الصحيح إذا مختلف"}}
"""


def validate_entity(entity: dict, page_text: str) -> dict:
    """Validate a single entity."""
    try:
        response = model.generate_content(
            VALIDATOR_PROMPT.format(
                name=entity.get("name", ""),
                parent=entity.get("parent", "null"),
                quote=entity.get("quote", "")[:200],
                page=entity.get("source_page", 0),
                text=page_text[:3000]  # Limit text to stay under token limits
            ),
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=256
            )
        )
        
        # Parse response
        text = response.text
        if "{" in text and "}" in text:
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
            entity["validated"] = data.get("valid", False)
            if data.get("corrected_quote"):
                entity["quote"] = data["corrected_quote"]
        else:
            entity["validated"] = "true" in text.lower()
            
        return entity
        
    except Exception as e:
        entity["validated"] = False
        entity["error"] = str(e)[:50]
        return entity


def run_validation():
    """Run validation with rate limiting."""
    print("=" * 60)
    print("🆓 PHASE 10b: FREE VALIDATION (Google AI Studio)")
    print("=" * 60)
    print(f"   Rate limit: {REQUESTS_PER_MINUTE} requests/minute")
    print()
    
    # Load entities
    print("📦 Loading entities...")
    all_entities = []
    with open(EXTRACTION_FILE, 'r') as f:
        for line in f:
            d = json.loads(line)
            for e in d.get("entities", []):
                e["source_page"] = d.get("page")
                all_entities.append(e)
    print(f"   Total entities: {len(all_entities)}")
    
    # Check for resume
    validated = set()
    if VALIDATION_OUTPUT.exists():
        with open(VALIDATION_OUTPUT, 'r') as f:
            for line in f:
                item = json.loads(line)
                validated.add(f"{item.get('name')}_{item.get('source_page')}")
        print(f"   Already validated: {len(validated)}")
    
    remaining = [e for e in all_entities if f"{e.get('name')}_{e.get('source_page')}" not in validated]
    print(f"   Remaining: {len(remaining)}")
    print()
    
    if not remaining:
        print("   ✅ All entities already validated!")
        return
    
    # Load page texts
    print("📦 Loading OCR pages...")
    page_texts = {}
    needed_pages = set(e.get("source_page") for e in remaining)
    for page_num in needed_pages:
        page_path = DATA_DIR / f"page_{page_num:05d}.txt"
        if page_path.exists():
            try:
                page_texts[page_num] = page_path.read_text(encoding='utf-8')
            except:
                pass
    print(f"   Loaded {len(page_texts)} pages")
    print()
    
    # Estimate time
    estimated_minutes = len(remaining) / REQUESTS_PER_MINUTE
    print(f"⏱️  Estimated time: {estimated_minutes:.0f} minutes ({estimated_minutes/60:.1f} hours)")
    print()
    
    # Validate
    print("🔄 Validating...")
    valid_count = 0
    start = datetime.now()
    
    with open(VALIDATION_OUTPUT, 'a') as f:
        for i, entity in enumerate(remaining, 1):
            # Rate limit
            time.sleep(SECONDS_PER_REQUEST)
            
            page_text = page_texts.get(entity.get("source_page"), "")
            result = validate_entity(entity, page_text)
            
            if result.get("validated"):
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
                f.flush()
                valid_count += 1
            
            if i % 10 == 0:
                elapsed = (datetime.now() - start).total_seconds() / 60
                rate = i / elapsed if elapsed > 0 else 0
                eta = (len(remaining) - i) / rate if rate > 0 else 0
                print(f"\r   [{i}/{len(remaining)}] valid={valid_count} | {rate:.1f}/min | ETA: {eta:.0f}min", end='', flush=True)
    
    print()
    print()
    print("=" * 60)
    print("✅ VALIDATION COMPLETE")
    print("=" * 60)
    print(f"   Validated: {valid_count}")
    print(f"   Output: {VALIDATION_OUTPUT}")


if __name__ == "__main__":
    run_validation()
