#!/usr/bin/env python3
"""
Tribal Hierarchy V5: EXPERT Extraction
- 500 parallel workers (maximum throughput)
- Expert-crafted prompt for complete Arabic tribal hierarchy extraction
"""

import json
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
PARALLEL_WORKERS = 200  # High throughput

BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent
OCR_DATA_DIR = PROJECT_ROOT / "Data" / "ocr_output_v5"
OUTPUT_FILE = BASE_DIR / "gemini_output" / "tribal_tree_v5.json"
CHECKPOINT_FILE = BASE_DIR / "gemini_output" / "v5_checkpoint.jsonl"

# ============================================================
# EXPERT EXTRACTION PROMPT
# ============================================================
EXTRACTION_PROMPT = """# ROLE
You are the world's foremost expert on Arabian tribal genealogy (أنساب القبائل العربية) with 50 years of experience studying Saudi, Gulf, and Levantine tribal structures. You have memorized the complete works of Ibn Hazm, Al-Qalqashandi, and modern genealogists.

# TASK
Extract EVERY tribal entity and relationship from the Arabic text below. Your extraction must be EXHAUSTIVE - do not skip any name, family, clan, or tribal unit mentioned.

# ARABIAN TRIBAL HIERARCHY (8 LEVELS)
The Arabian tribal system has these hierarchical levels (من الأعلى إلى الأسفل):

| Level | Arabic Term | English | Description |
|-------|------------|---------|-------------|
| 1 | قبيلة | Tribe | Major tribe (عنزة، قحطان، حرب، شمر، عتيبة، مطير) |
| 2 | شعب / عمارة | Division | Major division of a tribe |
| 3 | بطن | Batn | Main branch |
| 4 | فخذ | Fakhdh | Sub-branch |
| 5 | عشيرة | Ashira | Clan/extended family group |
| 6 | فصيلة | Fasila | Sub-clan |
| 7 | أسرة / عائلة / بيت | Family | Single family/household |
| 8 | فرع / ذرية | Branch | Smallest unit/descendants |

# CRITICAL EXTRACTION RULES

1. **EXTRACT EVERYTHING**: Every name that appears after words like:
   - "منهم" (from them)
   - "ومن فروعهم" (and from their branches)
   - "يتفرعون إلى" (they branch into)
   - "أبناء" (sons of)
   - "ذرية" (descendants of)
   - "آل" (family of)
   - "بنو/بني" (sons of)
   - "ومنهم أيضاً" (and from them also)

2. **PARENT-CHILD RELATIONSHIPS**: When text says "ومن X: أ، ب، ج" extract:
   - Entity "أ" with parent "X"
   - Entity "ب" with parent "X"  
   - Entity "ج" with parent "X"

3. **MULTIPLE CHILDREN**: One parent can have MANY children (10, 20, 50+). Extract ALL of them.

4. **NESTED STRUCTURES**: When text shows deeper nesting, follow it:
   - "من قبيلة عنزة: بني وهب، ومنهم: الرولة، ومن الرولة: الفرجان"
   - This gives: عنزة → بني وهب → الرولة → الفرجان

5. **ALIASES**: Same entity may have multiple spellings:
   - الروله = الرولة = رولة
   - Record all variants

6. **TYPE INFERENCE**: Determine type from context:
   - "قبيلة X" → type: قبيلة
   - "بطن X" → type: بطن
   - "آل X" → usually type: أسرة
   - "بني/بنو X" → usually type: بطن or فخذ

# TEXT TO ANALYZE
```
{text}
```

# OUTPUT FORMAT
Respond with ONLY valid JSON. No explanation, no markdown, just JSON:

{{
  "entities": [
    {{
      "name": "عنزة",
      "type": "قبيلة",
      "level": 1,
      "parent": null,
      "aliases": []
    }},
    {{
      "name": "ضنا مسلم",
      "type": "شعب",
      "level": 2,
      "parent": "عنزة",
      "aliases": []
    }},
    {{
      "name": "بني وهب",
      "type": "بطن",
      "level": 3,
      "parent": "ضنا مسلم",
      "aliases": ["الوهبة", "وهب"]
    }},
    {{
      "name": "الرولة",
      "type": "فخذ",
      "level": 4,
      "parent": "بني وهب",
      "aliases": ["الروله", "رولة"]
    }},
    {{
      "name": "الفرجان",
      "type": "عشيرة",
      "level": 5,
      "parent": "الرولة",
      "aliases": []
    }},
    {{
      "name": "آل فهد",
      "type": "أسرة",
      "level": 7,
      "parent": "الفرجان",
      "aliases": []
    }}
  ]
}}

# REMEMBER
- Extract EVERY name. Miss nothing.
- Every entity needs: name, type, level, parent, aliases
- If unsure about level, estimate based on context
- parent is null only for top-level tribes
- Output ONLY JSON, nothing else"""


def create_client():
    """Create Vertex AI client"""
    return genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)


def extract_from_page(page_path):
    """Extract hierarchies from a single page"""
    try:
        text = page_path.read_text(encoding='utf-8')
    except:
        return [], page_path.name
    
    if len(text) < 50:
        return [], page_path.name
    
    prompt = EXTRACTION_PROMPT.format(text=text[:10000])
    
    try:
        client = create_client()
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={'temperature': 0.0, 'max_output_tokens': 8192}
        )
        
        resp_text = response.text.strip() if response.text else ""
        
        if resp_text:
            start = resp_text.find('{')
            end = resp_text.rfind('}') + 1
            if start >= 0 and end > start:
                result = json.loads(resp_text[start:end])
                entities = result.get('entities', [])
                
                for e in entities:
                    e['source_page'] = page_path.name
                
                return entities, page_path.name
        
        return [], page_path.name
        
    except:
        return [], page_path.name


def run_extraction():
    """Run comprehensive extraction"""
    print("\n" + "="*70)
    print("🚀 TRIBAL HIERARCHY V5: EXPERT EXTRACTION")
    print("="*70)
    print(f"   Model: {MODEL}")
    print(f"   Workers: {PARALLEL_WORKERS} (MAXIMUM)")
    print(f"   Source: {OCR_DATA_DIR}")
    print()
    
    pages = sorted(OCR_DATA_DIR.glob("*.txt"))
    total = len(pages)
    print(f"   Total pages: {total:,}")
    print()
    
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
    
    all_entities = []
    completed = 0
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        future_to_page = {executor.submit(extract_from_page, page): page for page in pages}
        
        for future in as_completed(future_to_page):
            try:
                entities, page_name = future.result()
                all_entities.extend(entities)
                
                if entities:
                    with open(CHECKPOINT_FILE, 'a', encoding='utf-8') as f:
                        for e in entities:
                            f.write(json.dumps(e, ensure_ascii=False) + "\n")
                
                completed += 1
                
                if completed % 100 == 0 or completed == total:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed if elapsed > 0 else 0
                    eta = (total - completed) / rate if rate > 0 else 0
                    pct = completed / total * 100
                    
                    bar = '█' * int(40 * pct / 100) + '░' * (40 - int(40 * pct / 100))
                    print(f"[{bar}] {pct:.0f}% | {completed}/{total} | "
                          f"Entities: {len(all_entities):,} | {rate:.1f}/s | ETA: {eta/60:.1f}min")
                    
            except:
                completed += 1
    
    print(f"\n   ✅ Extracted {len(all_entities):,} total entities")
    return all_entities


def build_and_save(entities):
    """Build tree and save"""
    print("\n" + "="*70)
    print("🌳 BUILDING TREE STRUCTURE")
    print("="*70)
    
    nodes = {}
    children_of = defaultdict(set)
    
    for e in entities:
        name = e.get('name', '')
        if not name or not isinstance(name, str):
            continue
        name = name.strip()
        if not name:
            continue
        
        parent = e.get('parent')
        if parent and isinstance(parent, str):
            parent = parent.strip()
        else:
            parent = None
        
        if name not in nodes:
            nodes[name] = {
                'name': name,
                'aliases': [],
                'type': e.get('type', 'Unknown'),
                'level': e.get('level', 0),
                'source_pages': []
            }
        
        nodes[name]['aliases'] = list(set(nodes[name]['aliases'] + (e.get('aliases') or [])))
        if e.get('source_page'):
            nodes[name]['source_pages'].append(e['source_page'])
        
        if parent and parent != name:
            children_of[parent].add(name)
    
    for node in nodes.values():
        node['source_pages'] = list(set(node['source_pages']))[:5]
    
    print(f"   Unique nodes: {len(nodes):,}")
    
    all_children = set()
    for children in children_of.values():
        all_children.update(children)
    root_names = [name for name in nodes if name not in all_children]
    
    print(f"   Root nodes: {len(root_names):,}")
    print(f"   Parent-child links: {sum(len(v) for v in children_of.values()):,}")
    
    # Build indices
    name_index = {}
    alias_index = {}
    
    for name, node in nodes.items():
        parent = None
        for p, children in children_of.items():
            if name in children:
                parent = p
                break
        
        name_index[name] = {
            'type': node['type'],
            'level': node['level'],
            'aliases': node['aliases'],
            'parent': parent,
            'children': list(children_of.get(name, []))
        }
        
        for alias in node['aliases']:
            alias_index[alias] = name
    
    print(f"   Name index: {len(name_index):,}")
    
    # Save
    print("\n💾 Saving output...")
    
    output = {
        'version': '5.0',
        'created': datetime.now().isoformat(),
        'statistics': {
            'total_entities': len(entities),
            'unique_nodes': len(nodes),
            'root_tribes': len(root_names),
            'indexed_names': len(name_index),
            'indexed_aliases': len(alias_index),
            'parent_child_links': sum(len(v) for v in children_of.values())
        },
        'name_index': name_index,
        'alias_index': alias_index,
        'nodes': nodes
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    size_mb = OUTPUT_FILE.stat().st_size / 1024 / 1024
    print(f"   Saved: {OUTPUT_FILE.name} ({size_mb:.1f} MB)")
    
    return nodes, children_of


def main():
    start_time = time.time()
    
    entities = run_extraction()
    nodes, children_of = build_and_save(entities)
    
    total_time = time.time() - start_time
    
    print("\n" + "="*70)
    print("🎉 V5 EXTRACTION COMPLETE!")
    print("="*70)
    print(f"""
📊 RESULTS:
   Total entities:        {len(entities):,}
   Unique tribal nodes:   {len(nodes):,}
   Parent-child links:    {sum(len(v) for v in children_of.values()):,}
   
⏱️  Total time:          {total_time/60:.1f} minutes
💾 Output:               {OUTPUT_FILE.name}
""")


if __name__ == "__main__":
    main()
