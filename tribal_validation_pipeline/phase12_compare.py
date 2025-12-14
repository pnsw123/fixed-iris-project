#!/usr/bin/env python3
"""
Phase 12 Comparison: DeepSeek-R1 vs Qwen2.5 for Arabic Ancestry Extraction
- Tests both models on same orphans
- Uses engineered prompts optimized for each model
- Measures: speed, accuracy, path depth
"""

import json
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess

try:
    import ollama
except ImportError:
    subprocess.run(["pip3", "install", "ollama", "-q"])
    import ollama

# Paths
DATA_DIR = Path("../Data/ocr_output_v5")
OUTPUT_DIR = Path("gemini_output")
CURRENT_TREE = OUTPUT_DIR / "tribal_tree_full.json"

# Highly engineered Arabic ancestry extraction prompt
ENGINEERED_PROMPT = """أنت محلل أنساب عربية متخصص ذو خبرة عالية في قراءة كتب الأنساب العربية.

═══════════════════════════════════════════════════════════════════
📖 النص المصدر (من كتاب معجم قبائل العرب)
═══════════════════════════════════════════════════════════════════
{text}

═══════════════════════════════════════════════════════════════════
🎯 المهمة: استخراج سلسلة نسب "{name}"
═══════════════════════════════════════════════════════════════════

## التعليمات الدقيقة:

1. **ابحث في النص** عن أي ذكر للاسم "{name}"
2. **استخرج السلسلة الكاملة** من الجد الأكبر إلى الاسم المطلوب
3. **حدد نوع الكيان**: قبيلة (أكبر) > بطن > فخذ > عشيرة > أسرة (أصغر)
4. **استخرج الموقع** إذا ذُكر (السعودية، اليمن، مصر، الشام، العراق، إلخ)

## أنماط النسب العربية الشائعة:
- "بنو X من بني Y من قبيلة Z" → المسار: [Z, Y, X]
- "X بن Y بن Z" → المسار: [Z, Y, X]
- "من فروع قبيلة X" → الجذر: X
- "ينتسبون إلى X" → الجذر: X

## قواعد صارمة:
✗ لا تستخدم أي معلومات خارجية أو من الإنترنت
✗ لا تخترع أسماء غير موجودة في النص
✓ استخدم فقط ما هو مكتوب في النص أعلاه
✓ إذا لم تجد معلومة، اكتب null

## صيغة الإجابة (JSON فقط):
```json
{{
  "found_in_text": true/false,
  "full_path": ["الجد_الأكبر", "جد2", "جد3", "الأب", "{name}"],
  "parent": "الأب المباشر",
  "root_tribe": "القبيلة الأم (أول عنصر)",
  "entity_type": "قبيلة/بطن/فخذ/عشيرة/أسرة",
  "location": "الموقع الجغرافي أو null",
  "evidence": "اقتباس مباشر من النص يثبت النسب",
  "confidence": 0.0 إلى 1.0
}}
```

أجب بـ JSON فقط، بدون أي نص إضافي."""


def load_pages_for_entity(entity: dict) -> tuple:
    """Load OCR pages where entity appears."""
    pages = entity.get("source_pages", [])
    if not pages and entity.get("source_page"):
        pages = [entity.get("source_page")]
    
    combined_text = []
    for page_num in pages[:3]:
        page_path = DATA_DIR / f"page_{page_num:05d}.txt"
        if page_path.exists():
            try:
                text = page_path.read_text(encoding='utf-8')[:2500]
                combined_text.append(f"[صفحة {page_num}]\n{text}")
            except:
                pass
    
    return pages, "\n\n".join(combined_text)


def query_model(model: str, name: str, text: str) -> dict:
    """Query a model and parse response."""
    start = time.time()
    
    try:
        response = ollama.chat(
            model=model,
            messages=[{
                "role": "user",
                "content": ENGINEERED_PROMPT.format(text=text[:4000], name=name)
            }],
            options={"num_predict": 500, "temperature": 0.1}
        )
        
        elapsed = time.time() - start
        result_text = response["message"]["content"]
        
        # Parse JSON
        if "{" in result_text and "}" in result_text:
            start_idx = result_text.index("{")
            end_idx = result_text.rindex("}") + 1
            data = json.loads(result_text[start_idx:end_idx])
            
            return {
                "success": True,
                "found": data.get("found_in_text", False) and data.get("full_path"),
                "data": data,
                "time": elapsed,
                "path_depth": len(data.get("full_path", [])) if data.get("full_path") else 0
            }
        
        return {"success": False, "error": "no_json", "time": elapsed}
        
    except Exception as e:
        return {"success": False, "error": str(e)[:50], "time": time.time() - start}


def run_comparison(limit: int = 10):
    """Run comparison between models."""
    print("=" * 70)
    print("🔬 MODEL COMPARISON: DeepSeek-R1 vs Qwen2.5")
    print("=" * 70)
    print()
    
    # Check models
    models = ["deepseek-r1:7b", "qwen2.5:3b"]
    try:
        available = [m.model for m in ollama.list().models]
    except:
        available = []
    
    for model in models:
        if model not in available and model.split(":")[0] not in [m.split(":")[0] for m in available]:
            print(f"⚠️  {model} not found. Pulling...")
            subprocess.run(["ollama", "pull", model])
    
    # Load tree
    print("📦 Loading tree...")
    with open(CURRENT_TREE, 'r') as f:
        tree = json.load(f)
    
    name_index = tree["name_index"]
    orphans = {n: o for n, o in name_index.items() 
               if not o.get("parent") or o.get("parent") not in name_index}
    
    # Sample orphans
    sample = list(orphans.items())[:limit]
    print(f"📊 Testing {len(sample)} orphans per model")
    print()
    
    # Results
    results = {model: {"found": 0, "total_time": 0, "depths": []} for model in models}
    
    print("=" * 70)
    for i, (name, entity) in enumerate(sample, 1):
        pages, text = load_pages_for_entity(entity)
        
        if not text:
            print(f"[{i}/{limit}] {name[:20]:20} - ❌ No text")
            continue
        
        print(f"[{i}/{limit}] {name[:20]:20}", end="", flush=True)
        
        for model in models:
            result = query_model(model, name, text)
            results[model]["total_time"] += result["time"]
            
            if result.get("found"):
                results[model]["found"] += 1
                results[model]["depths"].append(result.get("path_depth", 0))
                marker = "✅"
            else:
                marker = "❌"
            
            model_short = model.split(":")[0][:8]
            print(f" | {model_short}:{marker}{result['time']:.1f}s", end="", flush=True)
        
        print()
    
    # Summary
    print()
    print("=" * 70)
    print("📊 RESULTS SUMMARY")
    print("=" * 70)
    print()
    print(f"{'Model':<20} {'Found':<12} {'Accuracy':<12} {'Avg Time':<12} {'Avg Depth'}")
    print("-" * 70)
    
    for model in models:
        r = results[model]
        found = r["found"]
        accuracy = f"{found}/{limit} ({found/limit*100:.0f}%)"
        avg_time = f"{r['total_time']/limit:.1f}s"
        avg_depth = f"{sum(r['depths'])/len(r['depths']):.1f}" if r['depths'] else "N/A"
        
        print(f"{model:<20} {found:<12} {accuracy:<12} {avg_time:<12} {avg_depth}")
    
    print()
    
    # Winner
    ds = results["deepseek-r1:7b"]
    qw = results["qwen2.5:3b"]
    
    if ds["found"] > qw["found"]:
        print("🏆 WINNER: DeepSeek-R1 (better accuracy)")
    elif qw["found"] > ds["found"]:
        print("🏆 WINNER: Qwen2.5 (better accuracy)")
    else:
        if ds["total_time"] < qw["total_time"]:
            print("🏆 WINNER: DeepSeek-R1 (faster)")
        else:
            print("🏆 WINNER: Qwen2.5 (faster)")
    
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10, help="Orphans to test")
    args = parser.parse_args()
    run_comparison(limit=args.limit)
