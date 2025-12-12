#!/usr/bin/env python3
"""
FAST RESUME: Complete remaining ~9,000 pages
- 200 parallel workers
- Skip already processed pages
- Append to existing checkpoint
"""

import json
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai

# ============================================================
# CONFIGURATION
# ============================================================
PROJECT_ID = "vertical-planet-478023-m7"
LOCATION = "us-central1"
MODEL = "gemini-2.5-flash"
PARALLEL_WORKERS = 200

BASE_DIR = Path(__file__).parent
PROJECT_ROOT = BASE_DIR.parent
OCR_DATA_DIR = PROJECT_ROOT / "Data" / "ocr_output_v5"
CHECKPOINT_FILE = BASE_DIR / "gemini_output" / "v5_checkpoint.jsonl"

# ============================================================
# EXPERT PROMPT
# ============================================================
EXTRACTION_PROMPT = """# ROLE
You are the world's foremost expert on Arabian tribal genealogy (أنساب القبائل العربية).

# TASK
Extract EVERY tribal entity and relationship from the Arabic text below. Be EXHAUSTIVE.

# HIERARCHY LEVELS (8)
1. قبيلة (Tribe)
2. شعب/عمارة (Division)
3. بطن (Batn)
4. فخذ (Fakhdh)
5. عشيرة (Ashira)
6. فصيلة (Fasila)
7. أسرة/عائلة/بيت (Family)
8. فرع/ذرية (Branch)

# EXTRACTION RULES
1. Extract EVERY name after: "منهم", "ومن فروعهم", "أبناء", "ذرية", "آل", "بنو/بني"
2. For "ومن X: أ، ب، ج" → extract أ, ب, ج all with parent X
3. One parent can have MANY children - extract ALL
4. Record aliases (الروله = الرولة = رولة)

# TEXT
```
{text}
```

# OUTPUT (JSON ONLY)
{{
  "entities": [
    {{"name": "عنزة", "type": "قبيلة", "level": 1, "parent": null, "aliases": []}},
    {{"name": "ضنا مسلم", "type": "شعب", "level": 2, "parent": "عنزة", "aliases": []}}
  ]
}}"""


def create_client():
    return genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)


def extract_from_page(page_path):
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


def get_processed_pages():
    """Get set of already processed pages"""
    processed = set()
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        e = json.loads(line)
                        if 'source_page' in e:
                            processed.add(e['source_page'])
                    except:
                        pass
    return processed


def run_resume():
    print("\n" + "="*70)
    print("🚀 FAST RESUME: COMPLETING EXTRACTION")
    print("="*70)
    print(f"   Model: {MODEL}")
    print(f"   Workers: {PARALLEL_WORKERS}")
    print()
    
    # Get processed pages
    processed = get_processed_pages()
    print(f"   Already processed: {len(processed):,} pages")
    
    # Get remaining pages
    all_pages = sorted(OCR_DATA_DIR.glob("*.txt"))
    remaining = [p for p in all_pages if p.name not in processed]
    total = len(remaining)
    print(f"   Remaining: {total:,} pages")
    print()
    
    if total == 0:
        print("   ✅ All pages already processed!")
        return 0
    
    all_entities = []
    completed = 0
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        future_to_page = {executor.submit(extract_from_page, page): page for page in remaining}
        
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
    
    print(f"\n   ✅ Extracted {len(all_entities):,} new entities")
    return len(all_entities)


def main():
    start_time = time.time()
    
    new_entities = run_resume()
    
    total_time = time.time() - start_time
    
    print("\n" + "="*70)
    print("🎉 RESUME COMPLETE!")
    print("="*70)
    print(f"""
📊 RESULTS:
   New entities:    {new_entities:,}
   Time:            {total_time/60:.1f} minutes

💡 NEXT: Run build_tree.py to rebuild the final tree
""")


if __name__ == "__main__":
    main()
