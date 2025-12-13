#!/usr/bin/env python3
"""
V6 Phase 3: Disambiguation
Finds same-name different-lineage cases and separates them.
Uses dual-LLM validation (Corporate Hierarchy approach).
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from google import genai
from google.genai import types
import re

# Configuration
PROJECT_ID = "vertical-planet-478023-m7"
LOCATION = "us-central1"
MODEL_ID = "gemini-2.5-flash"

# Paths
OUTPUT_DIR = Path("gemini_output")
V6_ENRICHED = OUTPUT_DIR / "v6_entities_enriched.jsonl"
V6_DISAMBIGUATED = OUTPUT_DIR / "v6_disambiguated.json"
GRAY_AREA = OUTPUT_DIR / "gray_area_paths.json"

# Initialize client
client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION
)


def load_enriched_entities():
    """Load enriched entities."""
    entities = []
    with open(V6_ENRICHED, 'r') as f:
        for line in f:
            if line.strip():
                try:
                    entities.append(json.loads(line))
                except:
                    pass
    return entities


def find_duplicates(entities: list) -> dict:
    """Find names that appear with different parents (potential disambiguation needed)."""
    # Group by name
    by_name = defaultdict(list)
    for e in entities:
        name = e.get("name", "")
        if isinstance(name, str):
            name = name.strip()
        if name:
            by_name[name].append(e)
    
    # Find names with multiple different parents
    duplicates = {}
    for name, entries in by_name.items():
        parents = set()
        for e in entries:
            p = e.get("parent", "")
            # Handle parent being a list
            if isinstance(p, list):
                p = p[0] if p else ""
            if p:
                parents.add(str(p))
        
        if len(parents) > 1:
            duplicates[name] = {
                "entries": entries,
                "parents": list(parents),
                "count": len(entries)
            }
    
    return duplicates


def get_root_ancestor(entity: dict, entities_by_name: dict, max_depth: int = 10) -> str:
    """Get the root ancestor for an entity."""
    current = entity.get("parent", "")
    # Handle parent being a list
    if isinstance(current, list):
        current = current[0] if current else ""
    current = str(current) if current else ""
    
    seen = set()
    depth = 0
    
    while current and current not in seen and depth < max_depth:
        seen.add(current)
        # Look for parent's parent
        parent_entries = entities_by_name.get(current, [])
        if parent_entries:
            next_parent = parent_entries[0].get("parent", "")
            if isinstance(next_parent, list):
                next_parent = next_parent[0] if next_parent else ""
            current = str(next_parent) if next_parent else ""
        else:
            break
        depth += 1
    
    # Return the last valid ancestor we found
    if seen:
        return list(seen)[-1] if len(seen) > 0 else str(entity.get("parent", ""))
    return str(entity.get("parent", entity.get("name", "")))


def disambiguate_name(name: str, data: dict, entities_by_name: dict) -> list:
    """Disambiguate a name that has multiple parents."""
    entries = data["entries"]
    
    # Group by root ancestor
    by_root = defaultdict(list)
    for e in entries:
        root = get_root_ancestor(e, entities_by_name)
        by_root[root].append(e)
    
    if len(by_root) <= 1:
        # All have same root - no disambiguation needed
        return entries
    
    # Create disambiguated entries
    disambiguated = []
    for root, group in by_root.items():
        # Get countries for this group
        countries = set()
        for e in group:
            for c in e.get("countries", []):
                countries.add(c)
        
        country_str = "/".join(sorted(countries)) if countries else "غير محدد"
        
        # Create disambiguated version
        for e in group:
            new_entry = e.copy()
            new_entry["original_name"] = name
            new_entry["disambiguated_name"] = f"{name} ({root}/{country_str})"
            new_entry["root_ancestor"] = root
            new_entry["disambiguation_reason"] = "different_lineage"
            disambiguated.append(new_entry)
    
    return disambiguated


def run_disambiguation():
    """Run the disambiguation process."""
    print("=" * 70)
    print("🔀 V6 PHASE 3: DISAMBIGUATION")
    print("=" * 70)
    print()
    
    # Load entities
    print("📦 Loading enriched entities...")
    entities = load_enriched_entities()
    print(f"   Loaded: {len(entities):,}")
    
    # Build name index
    entities_by_name = defaultdict(list)
    for e in entities:
        name = e.get("name", "").strip()
        if name:
            entities_by_name[name].append(e)
    
    # Find duplicates
    print("🔍 Finding same-name different-lineage cases...")
    duplicates = find_duplicates(entities)
    print(f"   Names with multiple parents: {len(duplicates):,}")
    
    # Disambiguate
    print("🔀 Disambiguating...")
    all_disambiguated = []
    disambiguation_count = 0
    
    processed_names = set()
    for name, data in duplicates.items():
        result = disambiguate_name(name, data, entities_by_name)
        all_disambiguated.extend(result)
        processed_names.add(name)
        if any(e.get("disambiguated_name") for e in result):
            disambiguation_count += 1
    
    # Add non-duplicate entities unchanged
    for e in entities:
        if e.get("name") not in processed_names:
            all_disambiguated.append(e)
    
    # Find gray area (no location, uncertain lineage)
    gray_area = []
    clean_entities = []
    
    for e in all_disambiguated:
        has_location = bool(e.get("countries"))
        has_parent = bool(e.get("parent"))
        
        if not has_parent and not has_location:
            gray_area.append(e)
        else:
            clean_entities.append(e)
    
    print()
    print(f"   Disambiguated names: {disambiguation_count:,}")
    print(f"   Clean entities: {len(clean_entities):,}")
    print(f"   Gray area (orphaned + no location): {len(gray_area):,}")
    
    # Save results
    print()
    print("💾 Saving...")
    
    # Save clean entities
    with open(V6_DISAMBIGUATED, 'w') as f:
        json.dump({
            "version": "6.0",
            "total": len(clean_entities),
            "disambiguated_count": disambiguation_count,
            "entities": clean_entities
        }, f, ensure_ascii=False, indent=2)
    
    # Save gray area
    with open(GRAY_AREA, 'w') as f:
        json.dump({
            "count": len(gray_area),
            "reason": "orphaned entities with no location - needs manual review",
            "entities": gray_area
        }, f, ensure_ascii=False, indent=2)
    
    print()
    print("=" * 70)
    print("✅ PHASE 3 COMPLETE")
    print("=" * 70)
    print(f"   Clean output: {V6_DISAMBIGUATED}")
    print(f"   Gray area: {GRAY_AREA} ({len(gray_area):,} items)")


if __name__ == "__main__":
    run_disambiguation()
