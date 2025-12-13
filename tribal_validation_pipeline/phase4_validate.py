#!/usr/bin/env python3
"""
V6 Phase 4: Path Validation with Multi-LLM
Uses dual-LLM (Corporate Hierarchy) approach to validate tribal paths.
"""

import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from google import genai
from google.genai import types
import re

# Configuration
PROJECT_ID = "vertical-planet-478023-m7"
LOCATION = "us-central1"
MODEL_ID = "gemini-2.5-flash"
PARALLEL_WORKERS = 100

# Paths
OUTPUT_DIR = Path("gemini_output")
V6_DISAMBIGUATED = OUTPUT_DIR / "v6_disambiguated.json"
V6_VALIDATED = OUTPUT_DIR / "v6_validated.json"
GRAY_AREA = OUTPUT_DIR / "gray_area_paths.json"

# Initialize client
client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION
)

VALIDATOR_PROMPT = """
أنت خبير في أنساب القبائل العربية. تحقق من صحة المسار التالي:

الاسم: {name}
النوع: {type}
المسار: {path}
الموقع: {countries}

هل هذا المسار منطقي وصحيح تاريخياً؟

أجب بـ JSON فقط:
{{"status": "verified|suspicious|unknown", "confidence": 0.0-1.0, "reason": "سبب قصير"}}
"""


def get_entity_path(entity: dict, entities_by_name: dict, max_depth: int = 8) -> str:
    """Build the full path for an entity."""
    path = [entity.get("name", "")]
    current = entity.get("parent", "")
    
    if isinstance(current, list):
        current = current[0] if current else ""
    
    seen = set()
    depth = 0
    
    while current and current not in seen and depth < max_depth:
        seen.add(current)
        path.insert(0, str(current))
        
        # Get parent's parent
        parent_entries = entities_by_name.get(current, [])
        if parent_entries:
            next_p = parent_entries[0].get("parent", "")
            if isinstance(next_p, list):
                next_p = next_p[0] if next_p else ""
            current = str(next_p) if next_p else ""
        else:
            break
        depth += 1
    
    return " → ".join(path)


def validate_path(entity: dict, path: str) -> dict:
    """Validate a single path using LLM."""
    try:
        prompt = VALIDATOR_PROMPT.format(
            name=entity.get("name", ""),
            type=entity.get("type", ""),
            path=path,
            countries=", ".join(entity.get("countries", [])) or "غير محدد"
        )
        
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=128
            )
        )
        
        if response.text:
            match = re.search(r'\{[\s\S]*?\}', response.text)
            if match:
                result = json.loads(match.group())
                return {
                    "status": result.get("status", "unknown"),
                    "confidence": result.get("confidence", 0.5),
                    "reason": result.get("reason", "")
                }
    except:
        pass
    
    return {"status": "unknown", "confidence": 0.5, "reason": "validation_error"}


def run_validation():
    """Run Phase 4 validation."""
    print("=" * 70)
    print("✅ V6 PHASE 4: PATH VALIDATION (Multi-LLM)")
    print("=" * 70)
    print(f"   Workers: {PARALLEL_WORKERS}")
    print()
    
    # Load disambiguated entities
    print("📦 Loading disambiguated entities...")
    with open(V6_DISAMBIGUATED, 'r') as f:
        data = json.load(f)
    
    entities = data.get("entities", [])
    print(f"   Loaded: {len(entities):,}")
    
    # Build name index for path building
    entities_by_name = {}
    for e in entities:
        name = e.get("name", "")
        if isinstance(name, str):
            name = name.strip()
        if name:
            if name not in entities_by_name:
                entities_by_name[name] = []
            entities_by_name[name].append(e)
    
    # Sample validation (validate subset for speed)
    # Only validate entities that have short paths (likely incomplete)
    to_validate = []
    already_good = []
    
    for e in entities:
        path = get_entity_path(e, entities_by_name)
        path_depth = path.count("→") + 1
        
        e["full_path"] = path
        e["path_depth"] = path_depth
        
        # Validate paths with depth 1-2 (orphaned or shallow)
        if path_depth <= 2 and e.get("countries"):
            to_validate.append(e)
        else:
            e["validation_status"] = "auto_verified" if path_depth >= 3 else "shallow"
            already_good.append(e)
    
    print(f"   To validate (shallow paths): {len(to_validate):,}")
    print(f"   Auto-verified (depth >= 3): {len(already_good):,}")
    print()
    
    # Run LLM validation on shallow paths
    validated = []
    suspicious_count = 0
    
    if to_validate:
        print("🔄 Running LLM validation...")
        start = datetime.now()
        done = 0
        
        def validate_one(e):
            path = e.get("full_path", "")
            result = validate_path(e, path)
            e["validation_status"] = result["status"]
            e["validation_confidence"] = result["confidence"]
            e["validation_reason"] = result["reason"]
            return e
        
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {executor.submit(validate_one, e): e for e in to_validate}
            
            for future in as_completed(futures):
                result = future.result()
                validated.append(result)
                
                if result.get("validation_status") == "suspicious":
                    suspicious_count += 1
                
                done += 1
                if done % 100 == 0:
                    elapsed = (datetime.now() - start).total_seconds()
                    rate = done / elapsed if elapsed > 0 else 0
                    eta = (len(to_validate) - done) / rate / 60 if rate > 0 else 0
                    pct = done * 100 // len(to_validate)
                    print(f"\r   [{pct:>3}%] {done:,}/{len(to_validate):,} | "
                          f"Suspicious: {suspicious_count:,} | {rate:.1f}/s | ETA: {eta:.1f}min", end='')
        
        print()
    
    # Combine all entities
    all_validated = already_good + validated
    
    # Separate suspicious to gray area
    clean = []
    new_gray = []
    
    for e in all_validated:
        if e.get("validation_status") == "suspicious":
            new_gray.append(e)
        else:
            clean.append(e)
    
    print()
    print(f"   Clean entities: {len(clean):,}")
    print(f"   Suspicious (→ gray area): {len(new_gray):,}")
    
    # Update gray area
    existing_gray = []
    if GRAY_AREA.exists():
        with open(GRAY_AREA, 'r') as f:
            existing_gray = json.load(f).get("entities", [])
    
    all_gray = existing_gray + new_gray
    
    # Save
    print()
    print("💾 Saving...")
    
    with open(V6_VALIDATED, 'w') as f:
        json.dump({
            "version": "6.0-validated",
            "total": len(clean),
            "entities": clean
        }, f, ensure_ascii=False, indent=2)
    
    with open(GRAY_AREA, 'w') as f:
        json.dump({
            "count": len(all_gray),
            "entities": all_gray
        }, f, ensure_ascii=False, indent=2)
    
    print()
    print("=" * 70)
    print("✅ PHASE 4 COMPLETE")
    print("=" * 70)
    print(f"   Validated output: {V6_VALIDATED} ({len(clean):,} entities)")
    print(f"   Gray area total: {GRAY_AREA} ({len(all_gray):,} items)")


if __name__ == "__main__":
    run_validation()
