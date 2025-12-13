#!/usr/bin/env python3
"""
V6 Phase 1: Location Enrichment - Hybrid Approach
Uses regex to find obvious locations + LLM for verification and enrichment.
"""

import json
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from google import genai
from google.genai import types

# Configuration
PROJECT_ID = "vertical-planet-478023-m7"
LOCATION = "us-central1"
MODEL_ID = "gemini-2.5-flash"
PARALLEL_WORKERS = 200

# Paths
DATA_DIR = Path("../Data/ocr_output_v5")
OUTPUT_DIR = Path("gemini_output")
CHECKPOINT_FILE = OUTPUT_DIR / "v6_locations_hybrid.jsonl"

# Initialize Vertex AI
client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location=LOCATION
)

# Countries to search for
COUNTRIES = {
    "السعودية": "السعودية",
    "المملكة العربية السعودية": "السعودية",
    "الكويت": "الكويت",
    "اليمن": "اليمن",
    "مصر": "مصر",
    "الأردن": "الأردن",
    "فلسطين": "فلسطين",
    "العراق": "العراق",
    "الإمارات": "الإمارات",
    "البحرين": "البحرين",
    "قطر": "قطر",
    "عُمان": "عمان",
    "عمان": "عمان",
    "ليبيا": "ليبيا",
    "سوريا": "سوريا",
    "لبنان": "لبنان",
    "السودان": "السودان",
    "المغرب": "المغرب",
    "تونس": "تونس",
    "الجزائر": "الجزائر",
}

# Regions and their likely countries
REGIONS = {
    "الحجاز": "السعودية",
    "نجد": "السعودية",
    "الأحساء": "السعودية",
    "عسير": "السعودية",
    "تهامة": "السعودية",
    "القصيم": "السعودية",
    "الجوف": "السعودية",
    "تبوك": "السعودية",
    "حائل": "السعودية",
    "جيزان": "السعودية",
    "المدينة": "السعودية",
    "مكة": "السعودية",
    "مكة المكرمة": "السعودية",
    "المدينة المنورة": "السعودية",
    "الرياض": "السعودية",
    "جدة": "السعودية",
    "الدمام": "السعودية",
    "حضرموت": "اليمن",
    "مأرب": "اليمن",
    "صنعاء": "اليمن",
    "عدن": "اليمن",
    "تعز": "اليمن",
    "سيناء": "مصر",
    "الصعيد": "مصر",
    "القاهرة": "مصر",
    "العقبة": "الأردن",
    "غزة": "فلسطين",
    "الشام": "سوريا/لبنان",
    "البادية": "المنطقة العربية",
    "بادية الشام": "سوريا",
    "الموصل": "العراق",
    "بغداد": "العراق",
    "البصرة": "العراق",
}

# Tribal patterns to extract
TRIBE_PATTERNS = [
    r'قبيلة\s+([^\s،,\.]+)',
    r'بني\s+([^\s،,\.]+)',
    r'بنو\s+([^\s،,\.]+)',
    r'آل\s+([^\s،,\.]+)',
    r'عشيرة\s+([^\s،,\.]+)',
    r'فخذ\s+([^\s،,\.]+)',
    r'بطن\s+([^\s،,\.]+)',
]


def extract_with_regex(text: str) -> dict:
    """Fast regex extraction of locations and tribes."""
    # Find countries
    countries_found = []
    for pattern, normalized in COUNTRIES.items():
        if pattern in text:
            if normalized not in countries_found:
                countries_found.append(normalized)
    
    # Find regions and infer countries
    regions_found = []
    for region, country in REGIONS.items():
        if region in text:
            regions_found.append({"region": region, "country": country})
            if country not in countries_found and "/" not in country:
                countries_found.append(country)
    
    # Find tribes
    tribes_found = set()
    for pattern in TRIBE_PATTERNS:
        matches = re.findall(pattern, text)
        for m in matches:
            if len(m) > 1 and len(m) < 30:  # Reasonable name length
                tribes_found.add(m)
    
    return {
        "countries": countries_found,
        "regions": regions_found,
        "tribes": list(tribes_found)
    }


def llm_enhance(text: str, regex_result: dict) -> dict:
    """LLM validation and enhancement of regex extraction."""
    # Only call LLM if regex found something OR text is substantial
    if not regex_result["countries"] and not regex_result["tribes"] and len(text) < 500:
        return regex_result
    
    prompt = f"""
النص التالي يتحدث عن قبائل عربية. تحقق من الاستخراج وأضف أي معلومات مفقودة.

الاستخراج الأولي:
- الدول: {regex_result['countries']}
- المناطق: {[r['region'] for r in regex_result['regions']]}
- القبائل: {regex_result['tribes'][:10]}

النص (مختصر):
{text[:2000]}

أجب بـ JSON فقط مع أي إضافات:
{{"countries_to_add": [], "tribes_to_add": [], "validated": true}}
"""
    
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=256
            )
        )
        
        if response.text:
            match = re.search(r'\{[\s\S]*?\}', response.text)
            if match:
                enhancement = json.loads(match.group())
                # Merge
                for c in enhancement.get("countries_to_add", []):
                    if c and c not in regex_result["countries"]:
                        regex_result["countries"].append(c)
                for t in enhancement.get("tribes_to_add", []):
                    if t and t not in regex_result["tribes"]:
                        regex_result["tribes"].append(t)
                regex_result["llm_validated"] = True
    except:
        regex_result["llm_validated"] = False
    
    return regex_result


def process_page(page_path: Path) -> dict:
    """Process a single page with hybrid regex + LLM approach."""
    page_name = page_path.stem
    
    try:
        text = page_path.read_text(encoding='utf-8')
        if len(text.strip()) < 50:
            return {"page": page_name, "countries": [], "regions": [], "tribes": []}
        
        # Step 1: Fast regex extraction
        result = extract_with_regex(text)
        
        # Step 2: LLM enhancement (only if needed)
        if result["countries"] or result["tribes"] or len(text) > 1000:
            result = llm_enhance(text, result)
        
        result["page"] = page_name
        result["has_data"] = bool(result["countries"] or result["tribes"])
        
        return result
        
    except Exception as e:
        return {"page": page_name, "error": str(e), "countries": [], "regions": [], "tribes": []}


def run_hybrid_extraction():
    """Run hybrid regex + LLM extraction."""
    print("=" * 70)
    print("🌍 V6 PHASE 1: LOCATION ENRICHMENT (Hybrid: Regex + LLM)")
    print("=" * 70)
    print(f"   Strategy: Regex first, LLM validates & enhances")
    print(f"   Workers: {PARALLEL_WORKERS}")
    print()
    
    pages = sorted(DATA_DIR.glob("page_*.txt"))
    print(f"   Total pages: {len(pages):,}")
    
    # Check checkpoint
    processed = set()
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        processed.add(json.loads(line).get("page"))
                    except:
                        pass
        print(f"   Already processed: {len(processed):,}")
    
    remaining = [p for p in pages if p.stem not in processed]
    print(f"   Remaining: {len(remaining):,}")
    print()
    
    if not remaining:
        print("   ✅ All pages processed!")
        return
    
    start = datetime.now()
    done = 0
    countries_total = 0
    tribes_total = 0
    pages_with_data = 0
    
    with open(CHECKPOINT_FILE, 'a') as f:
        with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
            futures = {executor.submit(process_page, p): p for p in remaining}
            
            for future in as_completed(futures):
                result = future.result()
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
                f.flush()
                
                done += 1
                countries_total += len(result.get("countries", []))
                tribes_total += len(result.get("tribes", []))
                if result.get("has_data"):
                    pages_with_data += 1
                
                if done % 100 == 0:
                    elapsed = (datetime.now() - start).total_seconds()
                    rate = done / elapsed if elapsed > 0 else 0
                    eta = (len(remaining) - done) / rate / 60 if rate > 0 else 0
                    pct = done * 100 // len(remaining)
                    bar = '█' * (pct // 2) + '░' * (50 - pct // 2)
                    
                    print(f"\r[{bar}] {pct}% | {done:,}/{len(remaining):,} | "
                          f"Countries: {countries_total:,} | Tribes: {tribes_total:,} | "
                          f"Pages w/data: {pages_with_data:,} | {rate:.1f}/s", end='')
    
    print()
    print()
    print("=" * 70)
    print("✅ PHASE 1 COMPLETE (Hybrid)")
    print("=" * 70)
    print(f"   Pages processed: {done:,}")
    print(f"   Countries found: {countries_total:,}")
    print(f"   Tribes found: {tribes_total:,}")
    print(f"   Pages with data: {pages_with_data:,}")


if __name__ == "__main__":
    run_hybrid_extraction()
