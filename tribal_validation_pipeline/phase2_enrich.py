#!/usr/bin/env python3
"""
V6 Phase 2: Enrich V5 entities with location data from Phase 1.
Cross-references V5 entities with page locations to add country/region tags.
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Paths
OUTPUT_DIR = Path("gemini_output")
V5_CHECKPOINT = OUTPUT_DIR / "v5_checkpoint.jsonl"
LOCATIONS_FILE = OUTPUT_DIR / "v6_locations_hybrid.jsonl"
V6_ENRICHED = OUTPUT_DIR / "v6_entities_enriched.jsonl"


def load_page_locations():
    """Load location data from Phase 1, indexed by page."""
    page_locations = {}
    
    with open(LOCATIONS_FILE, 'r') as f:
        for line in f:
            if line.strip():
                try:
                    data = json.loads(line)
                    page = data.get("page", "")
                    page_locations[page] = {
                        "countries": data.get("countries", []),
                        "regions": data.get("regions", []),
                        "tribes": data.get("tribes", [])
                    }
                except:
                    pass
    
    return page_locations


def load_v5_entities():
    """Load V5 entities."""
    entities = []
    with open(V5_CHECKPOINT, 'r') as f:
        for line in f:
            if line.strip():
                try:
                    entities.append(json.loads(line))
                except:
                    pass
    return entities


def enrich_entity(entity: dict, page_locations: dict) -> dict:
    """Enrich a single entity with location data from its source page."""
    source_page = entity.get("source_page", "")
    
    # Normalize page key - remove .txt extension if present
    if isinstance(source_page, str):
        page_key = source_page.replace(".txt", "")
    elif isinstance(source_page, int):
        page_key = f"page_{source_page:05d}"
    else:
        page_key = str(source_page)
    
    # Try to match
    location_data = page_locations.get(page_key)
    
    if location_data:
        entity["countries"] = location_data.get("countries", [])
        entity["regions"] = [r.get("region") if isinstance(r, dict) else r for r in location_data.get("regions", [])]
        entity["location_source"] = "page_context"
    else:
        entity["countries"] = []
        entity["regions"] = []
        entity["location_source"] = "none"
    
    return entity


def run_enrichment():
    """Enrich all V5 entities with location data."""
    print("=" * 70)
    print("🔄 V6 PHASE 2: ENTITY ENRICHMENT")
    print("=" * 70)
    print()
    
    # Load location data
    print("📍 Loading Phase 1 location data...")
    page_locations = load_page_locations()
    print(f"   Loaded locations for {len(page_locations):,} pages")
    
    # Load V5 entities
    print("📦 Loading V5 entities...")
    entities = load_v5_entities()
    print(f"   Loaded {len(entities):,} entities")
    print()
    
    # Enrichment stats
    enriched_count = 0
    country_assignments = 0
    no_location = 0
    
    print("🔗 Enriching entities with locations...")
    start = datetime.now()
    
    with open(V6_ENRICHED, 'w') as f:
        for i, entity in enumerate(entities):
            enriched = enrich_entity(entity, page_locations)
            
            if enriched.get("countries"):
                enriched_count += 1
                country_assignments += len(enriched["countries"])
            else:
                no_location += 1
            
            f.write(json.dumps(enriched, ensure_ascii=False) + '\n')
            
            if (i + 1) % 5000 == 0:
                pct = (i + 1) * 100 // len(entities)
                print(f"   [{pct:>3}%] {i+1:,}/{len(entities):,} - "
                      f"With location: {enriched_count:,} | No location: {no_location:,}")
    
    elapsed = (datetime.now() - start).total_seconds()
    
    print()
    print("=" * 70)
    print("✅ PHASE 2 COMPLETE")
    print("=" * 70)
    print(f"   Total entities: {len(entities):,}")
    print(f"   With location data: {enriched_count:,} ({enriched_count*100//len(entities)}%)")
    print(f"   Country assignments: {country_assignments:,}")
    print(f"   No location: {no_location:,}")
    print(f"   Time: {elapsed:.1f}s")
    print(f"   Output: {V6_ENRICHED}")


if __name__ == "__main__":
    run_enrichment()
