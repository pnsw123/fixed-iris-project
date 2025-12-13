
import json
from pathlib import Path
from google import genai
from google.genai import types
import re

PROJECT_ID = "vertical-planet-478023-m7"
LOCATION = "us-central1"
MODEL_ID = "gemini-2.5-flash"
DATA_DIR = Path("../Data/ocr_output_v5")
GRAY_AREA = Path("gemini_output/gray_area_paths.json")

client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

def get_page_context(source_page: str) -> str:
    match = re.search(r'page_(\d+)', source_page)
    if not match: return ""
    page_num = int(match.group(1))
    pages_text = []
    for offset in range(-3, 4):
        page_path = DATA_DIR / f"page_{page_num + offset:05d}.txt"
        if page_path.exists():
            try:
                text = page_path.read_text(encoding='utf-8')
                pages_text.append(f"--- صفحة {page_num + offset} ---\n{text[:2000]}")
            except: pass
    return "\n\n".join(pages_text)

def test_single():
    with open(GRAY_AREA, 'r') as f:
        data = json.load(f)
    orphan = data["entities"][0]
    print(f"Testing orphan: {orphan['name']} from {orphan['source_page']}")
    
    context = get_page_context(orphan['source_page'])
    print(f"Context size: {len(context)} chars")
    
    prompt = f"TEST PROMPT\nContext:\n{context}\n\nTask: Find parent for {orphan['name']}"
    
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=512)
        )
        print("SUCCESS!")
        if response.text:
            print(response.text)
        else:
            print("TEXT IS NONE")
            print(response.candidates)
    except Exception as e:
        print("FAILURE!")
        print(e)

if __name__ == "__main__":
    test_single()
