#!/usr/bin/env python3
"""
Tribal Hierarchy V4: Complete Re-Extraction
Step 1: Page Grouping - Detect tribe boundaries and group pages
Step 2: Multi-Page Extraction - Extract full hierarchies with Vertex AI
Step 3: Tree Construction - Build nested tree with name lookup index
"""

import json
import re
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai

# ============================================================
# CONFIGURATION
# ============================================================
PROJECT_ID = "vertical-planet-478023-m7"
LOCATION = "us-central1"
MODEL = "gemini-2.5-flash"
PARALLEL_WORKERS = 100  # Maximum speed!

BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent
OCR_DATA_DIR = PROJECT_ROOT / "Data" / "ocr_output_v5"
OUTPUT_FILE = BASE_DIR / "gemini_output" / "tribal_tree_v4.json"
CHECKPOINT_FILE = BASE_DIR / "gemini_output" / "v4_checkpoint.jsonl"

# Tribe start markers
TRIBE_START_PATTERNS = [
    r"نسب\s+قبيلة\s+([\u0600-\u06FF\s]+)",
    r"^قبيلة\s+([\u0600-\u06FF]+)",
    r"^بنو\s+([\u0600-\u06FF]+)",
    r"^آل\s+([\u0600-\u06FF]+)",
    r"أصل\s+قبيلة\s+([\u0600-\u06FF]+)",
    r"ومنهم\s*:",
    r"وفروعهم\s*:",
]

# Extraction prompt
EXTRACTION_PROMPT = """أنت خبير في أنساب القبائل العربية السعودية.

مهمتك: استخراج التسلسل الهرمي الكامل من النص التالي.

## المستويات الهرمية:
1. قبيلة - القبيلة الأم (أعلى مستوى)
2. بطن - فرع رئيسي من القبيلة
3. فخذ - فرع من البطن
4. عشيرة - فرع من الفخذ
5. أسرة - عائلة صغيرة
6. فرع - أصغر وحدة

## القواعد:
- استخرج جميع الأسماء والعلاقات
- حدد المستوى والنوع لكل اسم
- اذكر الاسم الأب (المستوى الأعلى مباشرة)
- اذكر الأسماء البديلة إن وجدت (مثل: الروله = رولة)

## النص:
{text}

## أجب بـ JSON فقط بهذا الشكل:
{{
  "entities": [
    {{"name": "عنزة", "aliases": [], "type": "قبيلة", "level": 1, "parent": null}},
    {{"name": "بني وهب", "aliases": ["الوهبي"], "type": "بطن", "level": 2, "parent": "عنزة"}},
    {{"name": "الرولة", "aliases": ["الروله"], "type": "فخذ", "level": 3, "parent": "بني وهب"}}
  ]
}}
"""


def create_client():
    """Create Vertex AI client"""
    return genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)


# ============================================================
# STEP 1: PAGE GROUPING
# ============================================================
def is_tribe_start(text):
    """Check if page starts a new tribe"""
    header = text[:500]
    for pattern in TRIBE_START_PATTERNS:
        if re.search(pattern, header):
            return True
    return False


def group_pages():
    """Group pages into tribe chunks"""
    print("\n" + "="*70)
    print("📄 STEP 1: PAGE GROUPING")
    print("="*70)
    
    pages = sorted(OCR_DATA_DIR.glob("*.txt"))
    print(f"   Total pages: {len(pages):,}")
    
    chunks = []
    current_chunk = []
    
    for i, page in enumerate(pages):
        try:
            text = page.read_text(encoding='utf-8')
        except:
            continue
        
        if is_tribe_start(text) and current_chunk:
            # Save current chunk and start new one
            chunks.append(current_chunk)
            current_chunk = [(page.name, text)]
        else:
            current_chunk.append((page.name, text))
        
        # Limit chunk size to 5 pages max
        if len(current_chunk) >= 5:
            chunks.append(current_chunk)
            current_chunk = []
    
    if current_chunk:
        chunks.append(current_chunk)
    
    print(f"   Grouped into {len(chunks):,} chunks")
    print(f"   Avg pages per chunk: {sum(len(c) for c in chunks)/len(chunks):.1f}")
    
    return chunks


# ============================================================
# STEP 2: MULTI-PAGE EXTRACTION
# ============================================================
def extract_chunk(chunk):
    """Extract hierarchy from a chunk of pages"""
    # Combine all pages in chunk
    combined_text = "\n\n---\n\n".join([text for _, text in chunk])
    
    # Limit to ~6000 chars to stay within token limits
    if len(combined_text) > 6000:
        combined_text = combined_text[:6000]
    
    prompt = EXTRACTION_PROMPT.format(text=combined_text)
    
    try:
        client = create_client()
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={'temperature': 0.1, 'max_output_tokens': 4096}
        )
        
        text = response.text.strip() if response.text else ""
        
        if text:
            # Find JSON in response
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                result = json.loads(text[start:end])
                entities = result.get('entities', [])
                
                # Add source pages
                source_pages = [name for name, _ in chunk]
                for e in entities:
                    e['source_pages'] = source_pages
                
                return entities
        
        return []
        
    except Exception as e:
        return []


def run_extraction(chunks):
    """Run parallel extraction on all chunks"""
    print("\n" + "="*70)
    print(f"⚡ STEP 2: MULTI-PAGE EXTRACTION ({PARALLEL_WORKERS} workers)")
    print("="*70)
    
    total = len(chunks)
    print(f"   Processing {total:,} chunks")
    print()
    
    all_entities = []
    completed = 0
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        future_to_idx = {executor.submit(extract_chunk, chunk): i for i, chunk in enumerate(chunks)}
        
        for future in as_completed(future_to_idx):
            try:
                entities = future.result()
                all_entities.extend(entities)
                
                # Save checkpoint
                with open(CHECKPOINT_FILE, 'a', encoding='utf-8') as f:
                    for e in entities:
                        f.write(json.dumps(e, ensure_ascii=False) + "\n")
                
                completed += 1
                
                # Progress every 50
                if completed % 50 == 0 or completed == total:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    eta = (total - completed) / rate if rate > 0 else 0
                    pct = completed / total * 100
                    
                    bar = '█' * int(40 * pct / 100) + '░' * (40 - int(40 * pct / 100))
                    print(f"[{bar}] {pct:.0f}% | {completed}/{total} | "
                          f"Entities: {len(all_entities):,} | {rate:.1f}/s | ETA: {eta/60:.1f}min")
                    
            except Exception as e:
                completed += 1
    
    print(f"\n   ✅ Extracted {len(all_entities):,} total entities")
    return all_entities


# ============================================================
# STEP 3: TREE CONSTRUCTION
# ============================================================
def build_tree(entities):
    """Build nested tree structure with name lookup index"""
    print("\n" + "="*70)
    print("🌳 STEP 3: TREE CONSTRUCTION")
    print("="*70)
    
    # Build parent-child relationships
    print("   Building relationships...")
    nodes = {}
    children_of = defaultdict(list)
    
    for e in entities:
        name = e.get('name', '')
        if not name:
            continue
        
        # Create or update node
        if name not in nodes:
            nodes[name] = {
                'name': name,
                'aliases': e.get('aliases', []),
                'type': e.get('type', 'Unknown'),
                'level': e.get('level', 0),
                'source_pages': e.get('source_pages', []),
                'children': []
            }
        else:
            # Merge aliases and source pages
            nodes[name]['aliases'] = list(set(nodes[name]['aliases'] + e.get('aliases', [])))
            nodes[name]['source_pages'] = list(set(nodes[name]['source_pages'] + e.get('source_pages', [])))
        
        # Track parent-child
        parent = e.get('parent')
        if parent:
            children_of[parent].append(name)
    
    # Build tree structure
    print("   Building tree structure...")
    for parent, children in children_of.items():
        if parent in nodes:
            for child in children:
                if child in nodes and child not in [c['name'] for c in nodes[parent].get('children', [])]:
                    nodes[parent]['children'].append(nodes[child])
    
    # Find root nodes (no parent references)
    all_children = set()
    for children in children_of.values():
        all_children.update(children)
    
    root_nodes = [nodes[name] for name in nodes if name not in all_children]
    
    # Sort by level
    root_nodes.sort(key=lambda x: x.get('level', 0))
    
    # Build name lookup index (for last name search)
    print("   Building name lookup index...")
    name_index = {}
    alias_index = {}
    
    def index_node(node, path=[]):
        name = node['name']
        current_path = path + [name]
        
        # Index by name
        name_index[name] = {
            'path': current_path,
            'type': node['type'],
            'level': node['level']
        }
        
        # Index by aliases
        for alias in node.get('aliases', []):
            alias_index[alias] = name
        
        # Index children
        for child in node.get('children', []):
            index_node(child, current_path)
    
    for root in root_nodes:
        index_node(root)
    
    print(f"   Total nodes: {len(nodes):,}")
    print(f"   Root tribes: {len(root_nodes):,}")
    print(f"   Name index entries: {len(name_index):,}")
    print(f"   Alias index entries: {len(alias_index):,}")
    
    return root_nodes, name_index, alias_index


# ============================================================
# MAIN
# ============================================================
def main():
    print("\n" + "="*70)
    print("🚀 TRIBAL HIERARCHY V4: COMPLETE RE-EXTRACTION")
    print("="*70)
    print(f"   Model: {MODEL}")
    print(f"   Workers: {PARALLEL_WORKERS}")
    print(f"   Source: {OCR_DATA_DIR}")
    print()
    
    start_time = time.time()
    
    # Step 1: Group pages
    chunks = group_pages()
    
    # Step 2: Extract hierarchies
    entities = run_extraction(chunks)
    
    # Step 3: Build tree
    trees, name_index, alias_index = build_tree(entities)
    
    # Save output
    print("\n" + "="*70)
    print("💾 SAVING OUTPUT")
    print("="*70)
    
    output = {
        'version': '4.0',
        'created': datetime.now().isoformat(),
        'statistics': {
            'total_entities': len(entities),
            'root_tribes': len(trees),
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
    total_time = time.time() - start_time
    
    print(f"   Saved: {OUTPUT_FILE.name} ({size_mb:.1f} MB)")
    
    # Final summary
    print("\n" + "="*70)
    print("🎉 V4 EXTRACTION COMPLETE!")
    print("="*70)
    print(f"""
📊 RESULTS:
   Total entities:     {len(entities):,}
   Root tribes:        {len(trees):,}
   Indexed names:      {len(name_index):,}
   Indexed aliases:    {len(alias_index):,}
   
⏱️  Total time:       {total_time/60:.1f} minutes
💾 Output:            {OUTPUT_FILE.name}

🔍 NAME LOOKUP READY:
   Search by last name → get full tribal path
""")


if __name__ == "__main__":
    main()
