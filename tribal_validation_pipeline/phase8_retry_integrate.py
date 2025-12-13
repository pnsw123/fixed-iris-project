#!/usr/bin/env python3
"""
Phase 8 Retry Integration: Integrate retry results into v9 tree.
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Paths
OUTPUT_DIR = Path("gemini_output")
V8_TREE = OUTPUT_DIR / "tribal_tree_v8.json"
RETRY_OUTPUT = OUTPUT_DIR / "retry_research.jsonl"
V9_TREE = OUTPUT_DIR / "tribal_tree_v9.json"


def integrate_retry():
    """Integrate retry results into the tree."""
    print("=" * 70)
    print("🌳 PHASE 8 RETRY INTEGRATION → V9")
    print("=" * 70)
    print()
    
    # Load v8 tree
    print("📦 Loading tribal_tree_v8.json...")
    with open(V8_TREE, 'r') as f:
        tree = json.load(f)
    
    name_index = tree.get("name_index", {})
    print(f"   Current nodes: {len(name_index):,}")
    
    # Load retry results
    print("📦 Loading retry results...")
    approved = []
    roots = []
    
    with open(RETRY_OUTPUT, 'r') as f:
        for line in f:
            item = json.loads(line)
            decision = item.get("decision")
            research = item.get("research", {})
            
            if decision == "APPROVE":
                if research.get("is_root"):
                    roots.append(item)
                else:
                    approved.append(item)
    
    print(f"   New approvals (need parents): {len(approved):,}")
    print(f"   New confirmed roots: {len(roots):,}")
    print()
    
    # Process approved
    print("🔧 Integrating approved paths...")
    updated = 0
    added = 0
    
    for item in approved:
        name = item.get("name")
        research = item.get("research", {})
        
        full_path = research.get("full_path", [])
        parent = research.get("immediate_parent")
        root_tribe = research.get("root_tribe")
        
        if not parent or not name:
            continue
        
        # Add missing intermediate nodes
        for i, node_name in enumerate(full_path[:-1]):
            next_node = full_path[i + 1] if i + 1 < len(full_path) else None
            
            if node_name and node_name not in name_index:
                name_index[node_name] = {
                    "name": node_name,
                    "type": "",
                    "parent": full_path[i - 1] if i > 0 else None,
                    "children": [next_node] if next_node else [],
                    "validation_status": "retry_research",
                    "full_path": " → ".join(full_path[:i+1])
                }
                added += 1
            elif node_name in name_index:
                if next_node and next_node not in name_index[node_name].get("children", []):
                    if "children" not in name_index[node_name]:
                        name_index[node_name]["children"] = []
                    name_index[node_name]["children"].append(next_node)
        
        # Update the orphan
        if name in name_index:
            name_index[name]["parent"] = parent
            name_index[name]["full_path"] = " → ".join(full_path) if full_path else ""
            name_index[name]["root_tribe"] = root_tribe or (full_path[0] if full_path else None)
            name_index[name]["validation_status"] = "retry_verified"
            updated += 1
    
    print(f"   Updated orphans: {updated:,}")
    print(f"   Added intermediate nodes: {added:,}")
    
    # Mark roots
    print("🔧 Marking new roots...")
    new_roots = 0
    for item in roots:
        name = item.get("name")
        if name in name_index:
            name_index[name]["is_confirmed_root"] = True
            name_index[name]["validation_status"] = "confirmed_root"
            new_roots += 1
    
    print(f"   New roots marked: {new_roots:,}")
    
    # Rebuild indices
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
    verified = sum(1 for n in name_index.values() if n.get("validation_status") in ["external_research_verified", "triple_llm_verified", "retry_verified"])
    confirmed_root_count = sum(1 for n in name_index.values() if n.get("is_confirmed_root"))
    
    # Build v9 tree
    print("🌳 Building v9 tree...")
    v9_tree = {
        "version": "9.0-retry-validated",
        "generated": datetime.now().isoformat(),
        "stats": {
            "total_nodes": len(name_index),
            "verified_nodes": verified,
            "confirmed_roots": confirmed_root_count,
            "remaining_orphans": orphans,
            "countries": tree["stats"].get("countries", 0),
            "max_depth": tree["stats"].get("max_depth", 0),
            "nodes_added_in_v9": added,
            "nodes_updated_in_v9": updated
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
    with open(V9_TREE, 'w') as f:
        json.dump(v9_tree, f, ensure_ascii=False, indent=2)
    
    file_size = V9_TREE.stat().st_size / (1024 * 1024)
    
    print()
    print("=" * 70)
    print("✅ V9 TREE COMPLETE!")
    print("=" * 70)
    print(f"   Output: {V9_TREE}")
    print(f"   Size: {file_size:.1f} MB")
    print(f"   Total nodes: {len(name_index):,}")
    print(f"   Verified: {verified:,}")
    print(f"   Confirmed roots: {confirmed_root_count:,}")
    print(f"   Remaining orphans: {orphans:,}")


if __name__ == "__main__":
    integrate_retry()
