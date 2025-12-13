#!/usr/bin/env python3
"""
Phase 8c: Tree Integration
Integrates validated research into the tribal tree.
Adds missing ancestors and updates orphan parents.
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Paths
OUTPUT_DIR = Path("gemini_output")
V7_TREE = OUTPUT_DIR / "tribal_tree_v7.json"
RESEARCH_OUTPUT = OUTPUT_DIR / "external_research.jsonl"  # Changed from validated
V8_TREE = OUTPUT_DIR / "tribal_tree_v8.json"
CONFIRMED_ROOTS = OUTPUT_DIR / "confirmed_roots.json"


def integrate_tree():
    """Integrate validated research into the tree."""
    print("=" * 70)
    print("🌳 PHASE 8c: TREE INTEGRATION")
    print("=" * 70)
    print()
    
    # Load v7 tree
    print("📦 Loading tribal_tree_v7.json...")
    with open(V7_TREE, 'r') as f:
        tree = json.load(f)
    
    name_index = tree.get("name_index", {})
    print(f"   Current nodes: {len(name_index):,}")
    
    # Load research results (approved only)
    print("📦 Loading research results...")
    approved = []
    roots = []
    
    with open(RESEARCH_OUTPUT, 'r') as f:
        for line in f:
            item = json.loads(line)
            decision = item.get("decision")
            research = item.get("research", {})
            
            if decision == "APPROVE":
                # Check if marked as root
                if research.get("is_root"):
                    roots.append(item)
                else:
                    approved.append(item)
    
    print(f"   Approved (need parents): {len(approved):,}")
    print(f"   Confirmed roots: {len(roots):,}")
    print()
    
    # Process approved - add paths
    print("🔧 Integrating approved paths...")
    updated = 0
    added = 0
    
    for item in approved:
        name = item.get("name")
        research = item.get("research", {})
        
        # Simplified format: fields directly on research
        full_path = research.get("full_path", [])
        parent = research.get("immediate_parent")
        root_tribe = research.get("root_tribe")
        
        if not parent or not name:
            continue
        
        # Add missing intermediate nodes
        for i, node_name in enumerate(full_path[:-1]):
            next_node = full_path[i + 1] if i + 1 < len(full_path) else None
            
            if node_name and node_name not in name_index:
                # Add new intermediate node
                name_index[node_name] = {
                    "name": node_name,
                    "type": "",
                    "parent": full_path[i - 1] if i > 0 else None,
                    "children": [next_node] if next_node else [],
                    "validation_status": "external_research",
                    "full_path": " → ".join(full_path[:i+1])
                }
                added += 1
            elif node_name in name_index:
                # Update children
                if next_node and next_node not in name_index[node_name].get("children", []):
                    if "children" not in name_index[node_name]:
                        name_index[node_name]["children"] = []
                    name_index[node_name]["children"].append(next_node)
        
        # Update the orphan itself
        if name in name_index:
            name_index[name]["parent"] = parent
            name_index[name]["full_path"] = " → ".join(full_path) if full_path else ""
            name_index[name]["root_tribe"] = root_tribe or (full_path[0] if full_path else None)
            name_index[name]["validation_status"] = "external_research_verified"
            updated += 1
    
    print(f"   Updated orphans: {updated:,}")
    print(f"   Added intermediate nodes: {added:,}")
    
    # Process confirmed roots - mark them properly
    print("🔧 Marking confirmed roots...")
    root_names = []
    for item in roots:
        name = item.get("name")
        if name in name_index:
            name_index[name]["is_confirmed_root"] = True
            name_index[name]["validation_status"] = "confirmed_root"
            root_names.append(name)
    
    print(f"   Confirmed roots marked: {len(root_names):,}")
    
    # Save confirmed roots list
    with open(CONFIRMED_ROOTS, 'w') as f:
        json.dump({"confirmed_roots": root_names}, f, ensure_ascii=False, indent=2)
    
    # Rebuild children_of index
    print("🔧 Rebuilding indices...")
    children_of = defaultdict(list)
    for name, node in name_index.items():
        parent = node.get("parent")
        if parent and parent in name_index:
            if name not in children_of[parent]:
                children_of[parent].append(name)
    
    # Update children lists
    for name, node in name_index.items():
        node["children"] = children_of.get(name, [])
    
    # Stats
    orphans = sum(1 for n in name_index.values() if not n.get("parent") and not n.get("is_confirmed_root"))
    verified = sum(1 for n in name_index.values() if n.get("validation_status") in ["external_research_verified", "triple_llm_verified"])
    confirmed_root_count = sum(1 for n in name_index.values() if n.get("is_confirmed_root"))
    
    # Build v8 tree
    print("🌳 Building v8 tree...")
    v8_tree = {
        "version": "8.0-external-validated",
        "generated": datetime.now().isoformat(),
        "stats": {
            "total_nodes": len(name_index),
            "verified_nodes": verified,
            "confirmed_roots": confirmed_root_count,
            "remaining_orphans": orphans,
            "countries": tree["stats"].get("countries", 0),
            "max_depth": tree["stats"].get("max_depth", 0),
            "nodes_added_in_v8": added,
            "nodes_updated_in_v8": updated
        },
        "countries": tree.get("countries", {}),
        "name_index": name_index,
        "alias_index": tree.get("alias_index", {}),
        "children_of": dict(children_of),
        "roots": [n for n, node in name_index.items() 
                  if not node.get("parent") or node.get("is_confirmed_root")][:500]
    }
    
    # Save
    print("💾 Saving...")
    with open(V8_TREE, 'w') as f:
        json.dump(v8_tree, f, ensure_ascii=False, indent=2)
    
    file_size = V8_TREE.stat().st_size / (1024 * 1024)
    
    print()
    print("=" * 70)
    print("✅ PHASE 8c COMPLETE!")
    print("=" * 70)
    print(f"   Output: {V8_TREE}")
    print(f"   Size: {file_size:.1f} MB")
    print(f"   Total nodes: {len(name_index):,}")
    print(f"   Verified: {verified:,}")
    print(f"   Confirmed roots: {confirmed_root_count:,}")
    print(f"   Remaining orphans: {orphans:,}")


if __name__ == "__main__":
    integrate_tree()
