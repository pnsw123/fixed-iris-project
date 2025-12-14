#!/usr/bin/env python3
"""
Phase 10 Complete Pipeline - Overnight Run
Runs all phases: 10a extract, 10b validate, 10c build tree
With robust checkpointing for resume capability.
"""

import json
import time
import random
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from google import genai
from google.genai import types

# Configuration
PROJECT_ID = "vertical-planet-478023-m7"
LOCATION = "us-central1"
MODEL_ID = "gemini-2.5-flash"

# Conservative settings for overnight reliability
PARALLEL_WORKERS = 30
REQUESTS_PER_SECOND = 10
MAX_RETRIES = 5

# Paths
DATA_DIR = Path("../Data/ocr_output_v5")
OUTPUT_DIR = Path("gemini_output")
EXTRACTION_OUTPUT = OUTPUT_DIR / "ocr_extractions.jsonl"
VALIDATION_OUTPUT = OUTPUT_DIR / "validated_extractions.jsonl"
FINAL_TREE = OUTPUT_DIR / "tribal_tree_cited.json"
CHECKPOINT_FILE = OUTPUT_DIR / "phase10_checkpoint.json"

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


def save_checkpoint(phase: str, data: dict):
    """Save checkpoint for resume capability."""
    checkpoint = {
        "phase": phase,
        "timestamp": datetime.now().isoformat(),
        "data": data
    }
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump(checkpoint, f, ensure_ascii=False, indent=2)
    print(f"   💾 Checkpoint saved: {phase}")


def load_checkpoint() -> dict:
    """Load checkpoint if exists."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r') as f:
            return json.load(f)
    return {}


# ============================================================================
# PHASE 10a: Extract entities from OCR
# ============================================================================

EXTRACTOR_PROMPT = """
من النص التالي، استخرج كل القبائل والعشائر مع علاقاتها الهرمية.

النص (صفحة {page}):
{text}

أجب بـ JSON فقط:
{{
  "entities": [
    {{
      "name": "اسم القبيلة",
      "parent": "اسم الأب/القبيلة الأم (أو null)",
      "type": "قبيلة/بطن/فخذ/عشيرة/أسرة",
      "quote": "اقتباس من النص يثبت العلاقة"
    }}
  ]
}}

استخرج فقط ما هو مذكور في النص. لا تضف معلومات خارجية.
"""


def extract_from_page(page_path: Path) -> dict:
    """Extract entities from a single OCR page."""
    page_num = int(page_path.stem.replace("page_", ""))
    
    try:
        text = page_path.read_text(encoding='utf-8')
    except:
        return {"page": page_num, "entities": [], "status": "read_error"}
    
    if not text or len(text) < 50:
        return {"page": page_num, "entities": [], "status": "empty"}
    
    for attempt in range(MAX_RETRIES):
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
                for e in entities:
                    e["source_page"] = page_num
                return {"page": page_num, "entities": entities, "status": "success"}
                
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(min(60, 2 ** attempt + random.uniform(0, 2)))
            else:
                break
    
    return {"page": page_num, "entities": [], "status": "error"}


def run_phase_10a():
    """Phase 10a: Extract entities from all OCR pages."""
    print("=" * 70)
    print("📖 PHASE 10a: EXTRACT ENTITIES FROM OCR")
    print("=" * 70)
    
    pages = sorted([p for p in DATA_DIR.glob("page_*.txt")])
    print(f"   Total pages: {len(pages):,}")
    
    # Check for resume
    processed = set()
    if EXTRACTION_OUTPUT.exists():
        with open(EXTRACTION_OUTPUT, 'r') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    processed.add(item.get("page"))
                except:
                    pass
        print(f"   Already processed: {len(processed):,}")
    
    remaining = [p for p in pages if int(p.stem.replace("page_", "")) not in processed]
    print(f"   Remaining: {len(remaining):,}")
    
    if not remaining:
        print("   ✅ Phase 10a already complete!")
        return True
    
    total_entities = 0
    start = datetime.now()
    
    with open(EXTRACTION_OUTPUT, 'a') as f:
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {executor.submit(extract_from_page, p): p for p in remaining}
            done = 0
            
            for future in as_completed(futures):
                result = future.result()
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
                f.flush()
                
                total_entities += len(result.get("entities", []))
                done += 1
                
                if done % 100 == 0:
                    elapsed = (datetime.now() - start).total_seconds()
                    rate = done / elapsed if elapsed > 0 else 0
                    eta = (len(remaining) - done) / rate / 60 if rate > 0 else 0
                    print(f"\r   [{done:,}/{len(remaining):,}] entities={total_entities:,} {rate:.1f}/s ETA={eta:.1f}min", end='', flush=True)
                    
                    # Save checkpoint every 500 pages
                    if done % 500 == 0:
                        save_checkpoint("10a", {"pages_done": done + len(processed), "entities": total_entities})
    
    print()
    print(f"   ✅ Phase 10a complete: {total_entities:,} entities extracted")
    save_checkpoint("10a_complete", {"total_entities": total_entities})
    return True


# ============================================================================
# PHASE 10b: Validate extractions
# ============================================================================

VALIDATOR_PROMPT = """
تحقق من صحة هذا الاستخراج:

الاسم: {name}
الأب: {parent}
الاقتباس: "{quote}"
الصفحة: {page}

النص الأصلي:
{text}

أسئلة:
1. هل الاسم "{name}" موجود في النص؟
2. هل العلاقة مع "{parent}" مذكورة في النص؟
3. هل الاقتباس صحيح؟

أجب بـ JSON:
{{
  "valid": true/false,
  "name_found": true/false,
  "parent_correct": true/false,
  "corrected_quote": "الاقتباس الصحيح إذا كان مختلفاً"
}}
"""


def validate_entity(entity: dict, page_text: str) -> dict:
    """Validate a single entity against OCR text."""
    for attempt in range(MAX_RETRIES):
        rate_limiter.acquire()
        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=VALIDATOR_PROMPT.format(
                    name=entity.get("name", ""),
                    parent=entity.get("parent", "null"),
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
                if validation.get("corrected_quote"):
                    entity["quote"] = validation["corrected_quote"]
                return entity
                
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(min(60, 2 ** attempt))
            else:
                break
    
    entity["validated"] = False
    entity["validation_error"] = "api_error"
    return entity


def run_phase_10b():
    """Phase 10b: Validate all extractions."""
    print()
    print("=" * 70)
    print("✓ PHASE 10b: VALIDATE EXTRACTIONS")  
    print("=" * 70)
    
    # Load all entities
    entities = []
    page_texts = {}
    
    print("   Loading extractions...")
    with open(EXTRACTION_OUTPUT, 'r') as f:
        for line in f:
            item = json.loads(line)
            for e in item.get("entities", []):
                entities.append(e)
    print(f"   Total entities: {len(entities):,}")
    
    # Check for resume
    validated = set()
    if VALIDATION_OUTPUT.exists():
        with open(VALIDATION_OUTPUT, 'r') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    validated.add(f"{item.get('name')}_{item.get('source_page')}")
                except:
                    pass
        print(f"   Already validated: {len(validated):,}")
    
    remaining = [e for e in entities if f"{e.get('name')}_{e.get('source_page')}" not in validated]
    print(f"   Remaining: {len(remaining):,}")
    
    if not remaining:
        print("   ✅ Phase 10b already complete!")
        return True
    
    # Load page texts as needed
    print("   Loading OCR pages for validation...")
    needed_pages = set(e.get("source_page") for e in remaining)
    for page_num in needed_pages:
        page_path = DATA_DIR / f"page_{page_num:05d}.txt"
        if page_path.exists():
            try:
                page_texts[page_num] = page_path.read_text(encoding='utf-8')
            except:
                page_texts[page_num] = ""
    print(f"   Loaded {len(page_texts):,} pages")
    
    valid_count = 0
    start = datetime.now()
    
    with open(VALIDATION_OUTPUT, 'a') as f:
        for i, entity in enumerate(remaining, 1):
            page_text = page_texts.get(entity.get("source_page"), "")
            result = validate_entity(entity, page_text)
            
            if result.get("validated"):
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
                f.flush()
                valid_count += 1
            
            if i % 100 == 0:
                elapsed = (datetime.now() - start).total_seconds()
                rate = i / elapsed if elapsed > 0 else 0
                eta = (len(remaining) - i) / rate / 60 if rate > 0 else 0
                print(f"\r   [{i:,}/{len(remaining):,}] valid={valid_count:,} {rate:.1f}/s ETA={eta:.1f}min", end='', flush=True)
                
                if i % 500 == 0:
                    save_checkpoint("10b", {"validated": i + len(validated), "valid": valid_count})
    
    print()
    print(f"   ✅ Phase 10b complete: {valid_count:,} entities validated")
    save_checkpoint("10b_complete", {"total_valid": valid_count})
    return True


# ============================================================================
# PHASE 10c: Build final tree
# ============================================================================

def run_phase_10c():
    """Phase 10c: Build final cited tree."""
    print()
    print("=" * 70)
    print("🌳 PHASE 10c: BUILD FINAL CITED TREE")
    print("=" * 70)
    
    # Load validated entities
    print("   Loading validated entities...")
    entities = []
    with open(VALIDATION_OUTPUT, 'r') as f:
        for line in f:
            entities.append(json.loads(line))
    print(f"   Total validated: {len(entities):,}")
    
    # Build name index
    name_index = {}
    for e in entities:
        name = e.get("name")
        if name not in name_index:
            name_index[name] = {
                "name": name,
                "type": e.get("type", ""),
                "parent": e.get("parent"),
                "source_pages": [e.get("source_page")],
                "source_quote": e.get("quote", ""),
                "validation_status": "ocr_verified"
            }
        else:
            # Add additional source page
            if e.get("source_page") not in name_index[name]["source_pages"]:
                name_index[name]["source_pages"].append(e.get("source_page"))
    
    print(f"   Unique entities: {len(name_index):,}")
    
    # Build children index
    from collections import defaultdict
    children_of = defaultdict(list)
    for name, node in name_index.items():
        parent = node.get("parent")
        if parent and parent in name_index:
            children_of[parent].append(name)
    
    for name, node in name_index.items():
        node["children"] = children_of.get(name, [])
    
    # Build full paths
    def get_full_path(name, visited=None):
        if visited is None:
            visited = set()
        if name in visited:
            return [name]  # Cycle detected
        visited.add(name)
        
        node = name_index.get(name)
        if not node:
            return [name]
        
        parent = node.get("parent")
        if parent and parent in name_index:
            return get_full_path(parent, visited) + [name]
        return [name]
    
    for name, node in name_index.items():
        path = get_full_path(name)
        node["full_path"] = " → ".join(path)
        node["path_depth"] = len(path)
    
    # Stats
    orphans = sum(1 for n in name_index.values() if not n.get("parent") or n.get("parent") not in name_index)
    max_depth = max((n.get("path_depth", 0) for n in name_index.values()), default=0)
    
    # Build final tree
    tree = {
        "version": "10.0-ocr-cited",
        "generated": datetime.now().isoformat(),
        "stats": {
            "total_nodes": len(name_index),
            "orphans": orphans,
            "max_depth": max_depth,
            "validation_status": "all_ocr_verified"
        },
        "name_index": name_index,
        "children_of": dict(children_of)
    }
    
    # Save
    print("   Saving final tree...")
    with open(FINAL_TREE, 'w') as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)
    
    size_mb = FINAL_TREE.stat().st_size / (1024 * 1024)
    
    print()
    print("=" * 70)
    print("✅ PHASE 10 COMPLETE!")
    print("=" * 70)
    print(f"   Output: {FINAL_TREE}")
    print(f"   Size: {size_mb:.1f} MB")
    print(f"   Nodes: {len(name_index):,}")
    print(f"   All nodes have source_pages and source_quote")
    
    save_checkpoint("complete", {"total_nodes": len(name_index)})
    return True


# ============================================================================
# Main
# ============================================================================

def main():
    print()
    print("=" * 70)
    print("🌙 PHASE 10: OVERNIGHT OCR-ONLY REBUILD")
    print("=" * 70)
    print(f"   Started: {datetime.now()}")
    print(f"   Model: {MODEL_ID}")
    print(f"   Workers: {PARALLEL_WORKERS}, RPS: {REQUESTS_PER_SECOND}")
    print()
    
    # Run all phases
    if run_phase_10a():
        if run_phase_10b():
            run_phase_10c()
    
    print()
    print(f"   Finished: {datetime.now()}")


if __name__ == "__main__":
    main()
