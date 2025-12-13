#!/usr/bin/env python3
"""
Phase 7d: Tree Integration
Merges approved extractions into the tribal tree to create v7.
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Paths
OUTPUT_DIR = Path("gemini_output")
V6_TREE = OUTPUT_DIR / "tribal_tree_v6.json"
APPROVED_FILE = OUTPUT_DIR / "approved_extractions.jsonl"
V7_TREE = OUTPUT_DIR / "tribal_tree_v7.json"


def integrate_approved():
    """Integrate approved extractions into the tree."""
    print("=" * 70)
    print("🌳 PHASE 7d: TREE INTEGRATION")
    print("=" * 70)
    print()
    
    # Load v6 tree
    print("📦 Loading tribal_tree_v6.json...")
    with open(V6_TREE, 'r') as f:
        tree = json.load(f)
    
    name_index = tree.get("name_index", {})
    print(f"   Current nodes: {len(name_index):,}")
    
    # Load approved extractions
    print("📦 Loading approved extractions...")
    approved = []
    if APPROVED_FILE.exists():
        with open(APPROVED_FILE, 'r') as f:
            for line in f:
                try:
                    item = json.loads(line)
                    if item.get("decision") == "APPROVE":
                        approved.append(item)
                except:
                    pass
    
    print(f"   Approved extractions: {len(approved):,}")
    print()
    
    if not approved:
        print("   ⚠️ No approved extractions to integrate.")
        return
    
    # Apply updates
    print("🔧 Applying updates...")
    updated = 0
    new_nodes = 0
    
    for item in approved:
        name = item.get("name")
        extraction = item.get("extraction", {})
        
        if not name or not extraction:
            continue
        
        parent = extraction.get("parent")
        if not parent:
            continue
        
        if name in name_index:
            # Update existing node
            name_index[name]["parent"] = parent
            name_index[name]["full_path"] = extraction.get("full_path", "")
            name_index[name]["root_tribe"] = extraction.get("root_tribe", "")
            name_index[name]["validation_status"] = "triple_llm_verified"
            name_index[name]["confidence"] = item.get("combined_confidence", 0)
            updated += 1
        else:
            # Add new node
            name_index[name] = {
                "name": name,
                "type": extraction.get("type", ""),
                "parent": parent,
                "full_path": extraction.get("full_path", ""),
                "root_tribe": extraction.get("root_tribe", ""),
                "location": extraction.get("location", ""),
                "validation_status": "triple_llm_verified",
                "confidence": item.get("combined_confidence", 0),
                "children": []
            }
            new_nodes += 1
    
    print(f"   Updated: {updated:,}")
    print(f"   New: {new_nodes:,}")
    
    # Rebuild children_of index
    print("🔧 Rebuilding indices...")
    children_of = defaultdict(list)
    for name, node in name_index.items():
        parent = node.get("parent")
        if parent and parent in name_index:
            children_of[parent].append(name)
    
    # Update children lists in nodes
    for name, node in name_index.items():
        node["children"] = children_of.get(name, [])
    
    # Rebuild alias index
    alias_index = tree.get("alias_index", {})
    
    # Count new stats
    orphans = sum(1 for n in name_index.values() if not n.get("parent"))
    verified = sum(1 for n in name_index.values() if n.get("validation_status") == "triple_llm_verified")
    
    # Build v7 tree
    print("🌳 Building v7 tree...")
    v7_tree = {
        "version": "7.0-triple-llm-verified",
        "generated": datetime.now().isoformat(),
        "stats": {
            "total_nodes": len(name_index),
            "root_tribes": orphans,
            "countries": tree["stats"].get("countries", 0),
            "max_depth": tree["stats"].get("max_depth", 0),
            "triple_llm_verified": verified,
            "v6_nodes_updated": updated,
            "new_nodes_added": new_nodes
        },
        "countries": tree.get("countries", {}),
        "name_index": name_index,
        "alias_index": alias_index,
        "children_of": dict(children_of),
        "roots": [n for n, node in name_index.items() if not node.get("parent")][:500]
    }
    
    # Save
    print("💾 Saving...")
    with open(V7_TREE, 'w') as f:
        json.dump(v7_tree, f, ensure_ascii=False, indent=2)
    
    file_size = V7_TREE.stat().st_size / (1024 * 1024)
    
    print()
    print("=" * 70)
    print("✅ PHASE 7d COMPLETE!")
    print("=" * 70)
    print(f"   Output: {V7_TREE}")
    print(f"   Size: {file_size:.1f} MB")
    print(f"   Total nodes: {len(name_index):,}")
    print(f"   Triple-LLM verified: {verified:,}")
    print(f"   Remaining orphans: {orphans:,}")


if __name__ == "__main__":
    integrate_approved()
