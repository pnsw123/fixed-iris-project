#!/usr/bin/env python3
"""
Phase 9b: Location Enrichment and Country Grouping
- Enriches intermediate nodes with derived country data
- Groups tree by country
- Creates v10 tree with complete location data
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Paths
OUTPUT_DIR = Path("gemini_output")
V9_TREE = OUTPUT_DIR / "tribal_tree_v9.json"
LOCATION_VALIDATION = OUTPUT_DIR / "location_validation.jsonl"
V10_TREE = OUTPUT_DIR / "tribal_tree_v10.json"


def enrich_intermediate_nodes(name_index: dict) -> int:
    """
    Enriches newly added intermediate nodes with location data
    derived from their children.
    """
    enriched = 0
    
    # Find nodes without countries but with children
    for name, node in name_index.items():
        if node.get("countries"):
            continue  # Already has countries
        
        children = node.get("children", [])
        if not children:
            continue  # No children to derive from
        
        # Collect countries from children
        derived_countries = set()
        for child_name in children:
            child = name_index.get(child_name, {})
            child_countries = child.get("countries", [])
            derived_countries.update(child_countries)
        
        if derived_countries:
            node["countries"] = list(derived_countries)
            node["countries_derived"] = True
            enriched += 1
    
    return enriched


def revert_different_tribes(name_index: dict, validation_results: list) -> int:
    """
    Reverts parent assignments for tribes that LLM confirmed are different.
    """
    reverted = 0
    
    for result in validation_results:
        if result.get("decision") != "different":
            continue
        
        name = result.get("name")
        if name in name_index:
            # Revert to orphan
            name_index[name]["parent"] = None
            name_index[name]["full_path"] = None
            name_index[name]["root_tribe"] = None
            name_index[name]["validation_status"] = "reverted_location_mismatch"
            reverted += 1
    
    return reverted


def build_country_index(name_index: dict) -> dict:
    """
    Builds a comprehensive country -> tribes mapping.
    """
    country_index = defaultdict(list)
    
    for name, node in name_index.items():
        countries = node.get("countries", [])
        for country in countries:
            tribe_info = {
                "name": name,
                "type": node.get("type", ""),
                "parent": node.get("parent"),
                "children_count": len(node.get("children", []))
            }
            country_index[country].append(tribe_info)
    
    # Sort by children count (most important first)
    for country in country_index:
        country_index[country].sort(key=lambda x: -x["children_count"])
    
    return dict(country_index)


def run_enrichment():
    """Run location enrichment and grouping."""
    print("=" * 70)
    print("🌍 PHASE 9b: LOCATION ENRICHMENT & COUNTRY GROUPING")
    print("=" * 70)
    print()
    
    # Load v9 tree
    print("📦 Loading tribal_tree_v9.json...")
    with open(V9_TREE, 'r') as f:
        tree = json.load(f)
    
    name_index = tree.get("name_index", {})
    print(f"   Current nodes: {len(name_index):,}")
    
    # Load validation results
    validation_results = []
    if LOCATION_VALIDATION.exists():
        print("📦 Loading location validation results...")
        with open(LOCATION_VALIDATION, 'r') as f:
            for line in f:
                validation_results.append(json.loads(line))
        print(f"   Validation results: {len(validation_results)}")
    
    # Count stats before
    nodes_without_countries = sum(1 for n in name_index.values() if not n.get("countries"))
    print(f"   Nodes without countries: {nodes_without_countries}")
    print()
    
    # Revert different tribes
    print("🔧 Reverting different tribe assignments...")
    reverted = revert_different_tribes(name_index, validation_results)
    print(f"   Reverted: {reverted}")
    
    # Enrich intermediate nodes
    print("🔧 Enriching intermediate nodes with derived locations...")
    enriched = enrich_intermediate_nodes(name_index)
    print(f"   Enriched: {enriched}")
    
    # Second pass - in case new nodes can now derive from enriched parents
    enriched2 = enrich_intermediate_nodes(name_index)
    if enriched2:
        print(f"   Second pass: {enriched2} more")
    
    # Build country index
    print("🔧 Building country index...")
    country_index = build_country_index(name_index)
    
    print("   Countries with tribes:")
    for country, tribes in sorted(country_index.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"      {country}: {len(tribes):,} tribes")
    
    # Rebuild children_of index
    print("🔧 Rebuilding indices...")
    children_of = defaultdict(list)
    for name, node in name_index.items():
        parent = node.get("parent")
        if parent and parent in name_index:
            if name not in children_of[parent]:
                children_of[parent].append(name)
    
    for name, node in name_index.items():
        node["children"] = children_of.get(name, [])
    
    # Stats
    orphans = sum(1 for n in name_index.values() if not n.get("parent") and not n.get("is_confirmed_root"))
    verified = sum(1 for n in name_index.values() if n.get("validation_status") in 
                   ["external_research_verified", "triple_llm_verified", "retry_verified"])
    confirmed_roots = sum(1 for n in name_index.values() if n.get("is_confirmed_root"))
    nodes_with_countries = sum(1 for n in name_index.values() if n.get("countries"))
    
    # Build v10 tree
    print("🌳 Building v10 tree...")
    v10_tree = {
        "version": "10.0-location-enriched",
        "generated": datetime.now().isoformat(),
        "stats": {
            "total_nodes": len(name_index),
            "verified_nodes": verified,
            "confirmed_roots": confirmed_roots,
            "remaining_orphans": orphans,
            "nodes_with_countries": nodes_with_countries,
            "intermediate_nodes_enriched": enriched + enriched2,
            "countries": len(country_index),
            "max_depth": tree["stats"].get("max_depth", 0),
        },
        "countries": tree.get("countries", {}),
        "country_index": country_index,
        "name_index": name_index,
        "alias_index": tree.get("alias_index", {}),
        "children_of": dict(children_of),
        "roots": [n for n, node in name_index.items() 
                  if not node.get("parent") or node.get("is_confirmed_root")][:500]
    }
    
    # Save
    print("💾 Saving...")
    with open(V10_TREE, 'w') as f:
        json.dump(v10_tree, f, ensure_ascii=False, indent=2)
    
    file_size = V10_TREE.stat().st_size / (1024 * 1024)
    
    print()
    print("=" * 70)
    print("✅ V10 TREE COMPLETE!")
    print("=" * 70)
    print(f"   Output: {V10_TREE}")
    print(f"   Size: {file_size:.1f} MB")
    print(f"   Total nodes: {len(name_index):,}")
    print(f"   Nodes with countries: {nodes_with_countries:,}")
    print(f"   Countries indexed: {len(country_index)}")
    print(f"   Remaining orphans: {orphans:,}")


if __name__ == "__main__":
    run_enrichment()
