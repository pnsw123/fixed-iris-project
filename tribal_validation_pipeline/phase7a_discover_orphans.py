#!/usr/bin/env python3
"""
Phase 7a: Orphan Discovery
Identifies orphan nodes from v6 tree that need parent resolution.
"""

import json
from pathlib import Path
from datetime import datetime

# Paths
OUTPUT_DIR = Path("gemini_output")
V6_TREE = OUTPUT_DIR / "tribal_tree_v6.json"
ORPHAN_QUEUE = OUTPUT_DIR / "orphan_queue.jsonl"

# Major tribes that are genuine roots (no parent needed)
KNOWN_ROOT_TRIBES = {
    # Major قبيلة level tribes
    "عنزة", "قحطان", "حرب", "شمر", "عتيبة", "مطير", "الدواسر", "بني خالد",
    "سبيع", "بني تميم", "بني هاجر", "العجمان", "آل مرة", "الظفير", "بني رشيد",
    "جهينة", "بلي", "حويطات", "بني عطية", "الشرارات", "عنيزة",
    # Historical confederations
    "قضاعة", "مضر", "ربيعة", "نزار", "كهلان", "حمير", "قريش",
    "هوازن", "غطفان", "أسد", "طيء", "تميم", "بكر", "تغلب",
    # Regional major tribes
    "الأزد", "كندة", "مذحج", "همدان", "خولان", "يافع", "ذي رعين",
}


def discover_orphans():
    """Find all orphan nodes that need parent resolution."""
    print("=" * 70)
    print("🔍 PHASE 7a: ORPHAN DISCOVERY")
    print("=" * 70)
    print()
    
    # Load v6 tree
    print("📦 Loading tribal_tree_v6.json...")
    with open(V6_TREE, 'r') as f:
        tree = json.load(f)
    
    name_index = tree.get("name_index", {})
    print(f"   Total nodes: {len(name_index):,}")
    
    # Find orphans
    orphans = []
    true_roots = []
    
    for name, node in name_index.items():
        parent = node.get("parent")
        
        # Check if this is an orphan
        if not parent or parent == "" or parent == "null" or parent is None:
            # Is it a known root tribe?
            if name in KNOWN_ROOT_TRIBES:
                true_roots.append(name)
            else:
                orphans.append({
                    "name": name,
                    "type": node.get("type", ""),
                    "countries": node.get("countries", []),
                    "regions": node.get("regions", []),
                    "path": node.get("path", ""),
                    "children_count": len(node.get("children", [])),
                })
    
    print(f"   True root tribes (excluded): {len(true_roots):,}")
    print(f"   Orphans needing resolution: {len(orphans):,}")
    print()
    
    # Sort orphans by children count (prioritize important ones)
    orphans.sort(key=lambda x: x["children_count"], reverse=True)
    
    # Save to queue
    print("💾 Saving orphan queue...")
    with open(ORPHAN_QUEUE, 'w') as f:
        for orphan in orphans:
            f.write(json.dumps(orphan, ensure_ascii=False) + '\n')
    
    print(f"   Saved: {ORPHAN_QUEUE}")
    print()
    
    # Stats
    print("📊 Top 10 orphans by importance (children count):")
    for i, o in enumerate(orphans[:10], 1):
        print(f"   {i:2}. {o['name']} ({o['children_count']} children)")
    
    print()
    print("=" * 70)
    print("✅ PHASE 7a COMPLETE")
    print("=" * 70)
    print(f"   Output: {ORPHAN_QUEUE}")
    print(f"   Orphans to process: {len(orphans):,}")
    
    return orphans


if __name__ == "__main__":
    discover_orphans()
