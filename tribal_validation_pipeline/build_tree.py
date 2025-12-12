#!/usr/bin/env python3
"""
Build tree from extracted entities (non-recursive)
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

BASE_DIR = Path(__file__).parent
CHECKPOINT_FILE = BASE_DIR / "gemini_output" / "v4_checkpoint.jsonl"
OUTPUT_FILE = BASE_DIR / "gemini_output" / "tribal_tree_v4.json"


def build_tree():
    """Build nested tree structure with name lookup index"""
    print("\n" + "="*70)
    print("🌳 BUILDING TREE FROM EXTRACTED ENTITIES")
    print("="*70)
    
    # Load entities from checkpoint
    print("\n📂 Loading extracted entities...")
    entities = []
    with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    entities.append(json.loads(line))
                except:
                    pass
    
    print(f"   Loaded {len(entities):,} entities")
    
    # Build parent-child relationships
    print("\n   Building relationships...")
    nodes = {}
    children_of = defaultdict(set)
    
    for e in entities:
        name = e.get('name', '').strip()
        if not name:
            continue
        
        # Create or update node
        if name not in nodes:
            nodes[name] = {
                'name': name,
                'aliases': list(set(e.get('aliases', []))),
                'type': e.get('type', 'Unknown'),
                'level': e.get('level', 0),
                'source_pages': list(set(e.get('source_pages', []))),
            }
        else:
            # Merge aliases and source pages
            nodes[name]['aliases'] = list(set(nodes[name]['aliases'] + e.get('aliases', [])))
            nodes[name]['source_pages'] = list(set(nodes[name]['source_pages'] + e.get('source_pages', [])))
        
        # Track parent-child (avoid self-reference)
        parent = e.get('parent', '').strip()
        if parent and parent != name:
            children_of[parent].add(name)
    
    print(f"   Unique nodes: {len(nodes):,}")
    print(f"   Parent-child relations: {sum(len(v) for v in children_of.values()):,}")
    
    # Find root nodes (no parent references)
    all_children = set()
    for children in children_of.values():
        all_children.update(children)
    
    root_names = [name for name in nodes if name not in all_children]
    print(f"   Root nodes: {len(root_names):,}")
    
    # Build tree using iteration (not recursion)
    print("\n   Building tree structure...")
    
    def build_subtree(node_name, visited, depth=0):
        """Build subtree iteratively to avoid recursion issues"""
        if depth > 10 or node_name in visited:
            return None
        
        visited.add(node_name)
        
        if node_name not in nodes:
            return None
        
        node = nodes[node_name].copy()
        children = children_of.get(node_name, set())
        
        if children:
            child_nodes = []
            for child_name in children:
                if child_name not in visited and child_name in nodes:
                    child_tree = build_subtree(child_name, visited.copy(), depth + 1)
                    if child_tree:
                        child_nodes.append(child_tree)
            if child_nodes:
                node['children'] = child_nodes
        
        return node
    
    trees = []
    for root_name in root_names[:500]:  # Limit to avoid memory issues
        tree = build_subtree(root_name, set())
        if tree:
            trees.append(tree)
    
    print(f"   Built {len(trees):,} trees")
    
    # Build name lookup index (flat, non-recursive)
    print("\n   Building name lookup index...")
    name_index = {}
    alias_index = {}
    
    for name, node in nodes.items():
        name_index[name] = {
            'type': node['type'],
            'level': node['level'],
            'source_pages': node['source_pages'][:3]  # Limit pages
        }
        for alias in node.get('aliases', []):
            alias_index[alias] = name
    
    print(f"   Name index entries: {len(name_index):,}")
    print(f"   Alias index entries: {len(alias_index):,}")
    
    # Save output
    print("\n💾 Saving output...")
    
    output = {
        'version': '4.0',
        'created': datetime.now().isoformat(),
        'statistics': {
            'total_entities': len(entities),
            'unique_nodes': len(nodes),
            'root_trees': len(trees),
            'indexed_names': len(name_index),
            'indexed_aliases': len(alias_index)
        },
        'name_index': name_index,
        'alias_index': alias_index,
        'tribes': trees
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    size_mb = OUTPUT_FILE.stat().st_size / 1024 / 1024
    print(f"   Saved: {OUTPUT_FILE.name} ({size_mb:.1f} MB)")
    
    # Summary
    print("\n" + "="*70)
    print("🎉 V4 TREE CONSTRUCTION COMPLETE!")
    print("="*70)
    print(f"""
📊 RESULTS:
   Total entities:     {len(entities):,}
   Unique nodes:       {len(nodes):,}
   Root trees:         {len(trees):,}
   Indexed names:      {len(name_index):,}
   Indexed aliases:    {len(alias_index):,}

💾 Output: {OUTPUT_FILE.name}

🔍 NAME LOOKUP READY:
   Search by last name → get tribal info
""")


if __name__ == "__main__":
    build_tree()
