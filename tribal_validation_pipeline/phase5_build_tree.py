#!/usr/bin/env python3
"""
V6 Phase 5: Final Tree Build
Builds the final tribal_tree_v6.json with location-aware structure.
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Paths
OUTPUT_DIR = Path("gemini_output")
V6_VALIDATED = OUTPUT_DIR / "v6_validated_augmented.json"
FINAL_TREE = OUTPUT_DIR / "tribal_tree_v6.json"


def build_tree():
    """Build the final V6 tree."""
    print("=" * 70)
    print("🌳 V6 PHASE 5: FINAL TREE BUILD")
    print("=" * 70)
    print()
    
    # Load validated entities
    print("📦 Loading validated entities...")
    with open(V6_VALIDATED, 'r') as f:
        data = json.load(f)
    
    entities = data.get("entities", [])
    print(f"   Loaded: {len(entities):,}")
    
    # Build indices
    print("🔧 Building indices...")
    
    name_index = {}  # name -> node info
    alias_index = defaultdict(list)  # alias -> [names]
    children_of = defaultdict(list)  # parent -> [children]
    by_country = defaultdict(list)  # country -> [names]
    
    for e in entities:
        name = e.get("name", "")
        if isinstance(name, str):
            name = name.strip()
        if not name:
            continue
        
        parent = e.get("parent", "")
        if isinstance(parent, list):
            parent = parent[0] if parent else ""
        parent = str(parent).strip() if parent else ""
        
        countries = e.get("countries", [])
        regions = e.get("regions", [])
        
        # Build node
        node = {
            "name": name,
            "type": e.get("type", ""),
            "parent": parent,
            "countries": countries,
            "regions": regions if isinstance(regions, list) else [],
            "path": e.get("full_path", ""),
            "path_depth": e.get("path_depth", 0),
            "disambiguated_name": e.get("disambiguated_name", ""),
            "validation_status": e.get("validation_status", ""),
        }
        
        # Add to indices
        if name not in name_index:
            name_index[name] = node
        
        if parent:
            children_of[parent].append(name)
        
        for c in countries:
            if name not in by_country[c]:
                by_country[c].append(name)
        
        # Handle aliases
        for alias in e.get("aliases", []):
            if isinstance(alias, str):
                alias_index[alias].append(name)
    
    # Add children to each node
    for name, node in name_index.items():
        node["children"] = children_of.get(name, [])
    
    # Find root nodes (no parent or parent not in index)
    roots = []
    for name, node in name_index.items():
        parent = node.get("parent", "")
        if not parent or parent not in name_index:
            roots.append(name)
    
    # Stats
    print()
    print(f"   Unique nodes: {len(name_index):,}")
    print(f"   Root tribes: {len(roots):,}")
    print(f"   Countries: {len(by_country):,}")
    
    # Build final structure
    print()
    print("🌳 Building tree structure...")
    
    tree = {
        "version": "6.0-location-aware",
        "generated": datetime.now().isoformat(),
        "stats": {
            "total_nodes": len(name_index),
            "root_tribes": len(roots),
            "countries": len(by_country),
            "max_depth": max((n.get("path_depth", 0) for n in name_index.values()), default=0)
        },
        "countries": {
            country: {
                "tribe_count": len(names),
                "tribes": names[:50]  # Top 50 per country
            }
            for country, names in sorted(by_country.items())
        },
        "name_index": name_index,
        "alias_index": dict(alias_index),
        "children_of": dict(children_of),
        "roots": roots[:500]  # Top 500 roots
    }
    
    # Save
    print("💾 Saving...")
    with open(FINAL_TREE, 'w') as f:
        json.dump(tree, f, ensure_ascii=False, indent=2)
    
    file_size = FINAL_TREE.stat().st_size / (1024 * 1024)
    
    print()
    print("=" * 70)
    print("✅ V6 TREE BUILD COMPLETE!")
    print("=" * 70)
    print(f"   Output: {FINAL_TREE}")
    print(f"   Size: {file_size:.1f} MB")
    print(f"   Nodes: {len(name_index):,}")
    print(f"   Countries: {list(by_country.keys())[:5]}...")
    print()
    
    # Sample output
    print("📍 Sample entries by country:")
    for country in list(by_country.keys())[:3]:
        tribes = by_country[country][:3]
        print(f"   {country}: {', '.join(tribes)}")


if __name__ == "__main__":
    build_tree()
