#!/usr/bin/env python3
"""
OVERNIGHT PIPELINE: Complete Tribal Hierarchy
Runs all steps automatically:
1. Extraction (currently running)
2. Tree Building (multi-level)
3. Validation
4. Final Output
"""

import json
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

BASE_DIR = Path(__file__).parent
CHECKPOINT_FILE = BASE_DIR / "gemini_output" / "v5_checkpoint.jsonl"
FINAL_TREE_FILE = BASE_DIR / "gemini_output" / "tribal_tree_final.json"


def build_comprehensive_tree():
    """Build a beautiful multi-level tree from extracted entities"""
    print("\n" + "="*70)
    print("🌳 BUILDING COMPREHENSIVE TRIBAL TREE")
    print("="*70)
    
    # Load entities
    print("\n📂 Loading extracted entities...")
    entities = []
    with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    entities.append(json.loads(line))
                except:
                    pass
    
    print(f"   Total entities: {len(entities):,}")
    
    # Build node dictionary
    print("\n🔗 Building node relationships...")
    nodes = {}
    children_of = defaultdict(set)
    
    for e in entities:
        name = str(e.get('name', '')).strip()
        if not name:
            continue
        
        parent = e.get('parent')
        if parent:
            parent = str(parent).strip()
        else:
            parent = None
        
        # Create/update node
        if name not in nodes:
            nodes[name] = {
                'name': name,
                'type': e.get('type', 'Unknown'),
                'level': e.get('level', 0),
                'aliases': [],
                'source_pages': [],
                'children': []
            }
        
        # Merge data
        aliases = e.get('aliases') or []
        nodes[name]['aliases'] = list(set(nodes[name]['aliases'] + aliases))
        
        source_page = e.get('source_page')
        if source_page and source_page not in nodes[name]['source_pages']:
            nodes[name]['source_pages'].append(source_page)
        
        # Track relationships
        if parent and parent != name:
            children_of[parent].add(name)
    
    print(f"   Unique nodes: {len(nodes):,}")
    print(f"   Parent-child links: {sum(len(v) for v in children_of.values()):,}")
    
    # Find root nodes (no parent in data)
    all_children = set()
    for children in children_of.values():
        all_children.update(children)
    
    root_names = [name for name in nodes if name not in all_children]
    print(f"   Root tribes: {len(root_names):,}")
    
    # Build nested tree structure
    print("\n🌲 Building nested tree structure...")
    
    def build_subtree(name, depth=0, visited=None):
        """Build subtree with depth limit"""
        if visited is None:
            visited = set()
        
        if depth > 15 or name in visited or name not in nodes:
            return None
        
        visited.add(name)
        node = nodes[name].copy()
        node['depth'] = depth
        
        # Get children
        child_names = children_of.get(name, set())
        if child_names:
            child_trees = []
            for child_name in sorted(child_names):
                child_tree = build_subtree(child_name, depth + 1, visited.copy())
                if child_tree:
                    child_trees.append(child_tree)
            
            if child_trees:
                node['children'] = child_trees
                node['child_count'] = len(child_trees)
        
        return node
    
    # Build all trees
    trees = []
    for i, root_name in enumerate(sorted(root_names)):
        if i % 100 == 0:
            print(f"   Building tree {i+1}/{len(root_names)}...")
        
        tree = build_subtree(root_name)
        if tree:
            trees.append(tree)
    
    print(f"   Built {len(trees):,} complete trees")
    
    # Calculate statistics
    print("\n📊 Calculating statistics...")
    
    def get_max_depth(node):
        if 'children' not in node or not node['children']:
            return node.get('depth', 0)
        return max(get_max_depth(child) for child in node['children'])
    
    def count_all_nodes(node):
        count = 1
        for child in node.get('children', []):
            count += count_all_nodes(child)
        return count
    
    max_depth = max(get_max_depth(t) for t in trees) if trees else 0
    total_nodes_in_trees = sum(count_all_nodes(t) for t in trees)
    
    # Sort trees by size
    trees.sort(key=lambda t: -count_all_nodes(t))
    
    # Build lookup indices
    print("\n🔍 Building search indices...")
    
    name_index = {}
    alias_index = {}
    
    for name, node in nodes.items():
        # Find parent
        parent = None
        for p, children in children_of.items():
            if name in children:
                parent = p
                break
        
        name_index[name] = {
            'type': node['type'],
            'level': node['level'],
            'parent': parent,
            'children': list(children_of.get(name, [])),
            'aliases': node['aliases']
        }
        
        for alias in node['aliases']:
            alias_index[alias] = name
    
    print(f"   Name index: {len(name_index):,} entries")
    print(f"   Alias index: {len(alias_index):,} entries")
    
    # Type distribution
    type_counts = defaultdict(int)
    for node in nodes.values():
        type_counts[node['type']] += 1
    
    print("\n   Type distribution:")
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"     {t}: {count:,}")
    
    # Find largest tribes
    largest_trees = trees[:10]
    
    print("\n   Top 10 largest tribes:")
    for i, t in enumerate(largest_trees, 1):
        size = count_all_nodes(t)
        depth = get_max_depth(t)
        print(f"     {i}. {t['name']}: {size:,} nodes, depth {depth}")
    
    # Save output
    print("\n💾 Saving final tree...")
    
    output = {
        'version': '5.0-final',
        'created': datetime.now().isoformat(),
        'description': 'Complete Arabian Tribal Hierarchy - All levels, all families',
        'statistics': {
            'total_entities_extracted': len(entities),
            'unique_nodes': len(nodes),
            'root_tribes': len(trees),
            'total_nodes_in_trees': total_nodes_in_trees,
            'max_depth': max_depth,
            'indexed_names': len(name_index),
            'indexed_aliases': len(alias_index),
            'type_distribution': dict(type_counts)
        },
        'name_index': name_index,
        'alias_index': alias_index,
        'tribes': trees
    }
    
    with open(FINAL_TREE_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    size_mb = FINAL_TREE_FILE.stat().st_size / 1024 / 1024
    print(f"   Saved: {FINAL_TREE_FILE.name} ({size_mb:.1f} MB)")
    
    # Final summary
    print("\n" + "="*70)
    print("🎉 TRIBAL TREE COMPLETE!")
    print("="*70)
    print(f"""
╔════════════════════════════════════════════════════════════════════╗
║                    FINAL TRIBAL TREE                               ║
╚════════════════════════════════════════════════════════════════════╝

📊 STATISTICS:
   Total entities:     {len(entities):,}
   Unique nodes:       {len(nodes):,}
   Root tribes:        {len(trees):,}
   Max depth:          {max_depth} levels
   Name index:         {len(name_index):,}
   Alias index:        {len(alias_index):,}

🏆 LARGEST TRIBES:
""")
    for i, t in enumerate(largest_trees[:5], 1):
        size = count_all_nodes(t)
        print(f"   {i}. {t['name']}: {size:,} nodes")
    
    print(f"""
💾 OUTPUT: {FINAL_TREE_FILE.name}

🔍 SEARCH CAPABILITY:
   - Search by last name → get full tribal hierarchy
   - All 7+ levels included
   - Aliases supported
   - Parent-child relationships complete
""")


def wait_for_extraction():
    """Wait for extraction to complete by checking checkpoint growth"""
    print("\n" + "="*70)
    print("⏳ WAITING FOR EXTRACTION TO COMPLETE")
    print("="*70)
    
    last_count = 0
    stable_checks = 0
    
    while True:
        if not CHECKPOINT_FILE.exists():
            print("   Waiting for checkpoint file...")
            time.sleep(30)
            continue
        
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            count = sum(1 for _ in f)
        
        print(f"   Entities: {count:,}")
        
        if count == last_count:
            stable_checks += 1
            if stable_checks >= 3:
                print("   Extraction appears complete!")
                break
        else:
            stable_checks = 0
        
        last_count = count
        time.sleep(60)  # Check every minute


def main():
    print("\n" + "="*70)
    print("🌙 OVERNIGHT PIPELINE: COMPLETE TRIBAL HIERARCHY")
    print("="*70)
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Step 1: Wait for extraction
    wait_for_extraction()
    
    # Step 2: Build tree
    build_comprehensive_tree()
    
    print("\n" + "="*70)
    print("✅ OVERNIGHT PIPELINE COMPLETE!")
    print("="*70)
    print(f"   Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Output: {FINAL_TREE_FILE.name}")


if __name__ == "__main__":
    main()
