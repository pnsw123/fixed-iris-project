#!/usr/bin/env python3
"""
PDF OCR Extraction Script
Uses Tesseract + pytesseract + pdf2image to extract text from tribe.pdf
"""

import os
import sys
from pathlib import Path
from pdf2image import convert_from_path
import pytesseract
from concurrent.futures import ThreadPoolExecutor
import time

# Configuration
PDF_PATH = "/Users/yazeed/Desktop/AntiGravity_1-main/tribe.pdf"
OUTPUT_DIR = "/Users/yazeed/Desktop/AntiGravity_1-main/ocr_output"
PAGES_TO_EXTRACT = 50  # First 50 pages as sample
DPI = 300  # Higher DPI = better OCR accuracy
LANG = "ara+eng"  # Arabic + English

def extract_page(args):
    """Extract text from a single page image."""
    page_num, image = args
    try:
        text = pytesseract.image_to_string(image, lang=LANG)
        return page_num, text
    except Exception as e:
        return page_num, f"[ERROR extracting page {page_num}: {e}]"

def main():
    print(f"=" * 60)
    print(f"PDF OCR Extraction")
    print(f"=" * 60)
    print(f"PDF: {PDF_PATH}")
    print(f"Pages to extract: 1-{PAGES_TO_EXTRACT}")
    print(f"DPI: {DPI}")
    print(f"Languages: {LANG}")
    print(f"=" * 60)
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    start_time = time.time()
    
    # Convert PDF pages to images
    print(f"\n[1/3] Converting PDF pages to images...")
    images = convert_from_path(
        PDF_PATH,
        dpi=DPI,
        first_page=1,
        last_page=PAGES_TO_EXTRACT,
        thread_count=4
    )
    print(f"      Converted {len(images)} pages in {time.time() - start_time:.1f}s")
    
    # Run OCR on each page
    print(f"\n[2/3] Running OCR on {len(images)} pages...")
    ocr_start = time.time()
    
    all_text = []
    for i, image in enumerate(images, 1):
        page_num = i
        print(f"      Processing page {page_num}/{len(images)}...", end="\r")
        text = pytesseract.image_to_string(image, lang=LANG)
        all_text.append((page_num, text))
        
        # Save individual page
        page_file = Path(OUTPUT_DIR) / f"page_{page_num:05d}.txt"
        with open(page_file, "w", encoding="utf-8") as f:
            f.write(text)
    
    print(f"\n      OCR completed in {time.time() - ocr_start:.1f}s")
    
    # Save combined output
    print(f"\n[3/3] Saving combined output...")
    combined_file = Path(OUTPUT_DIR) / "tribe_ocr_sample_50pages.txt"
    with open(combined_file, "w", encoding="utf-8") as f:
        for page_num, text in all_text:
            f.write(f"\n{'='*60}\n")
            f.write(f"PAGE {page_num}\n")
            f.write(f"{'='*60}\n\n")
            f.write(text)
            f.write("\n")
    
    total_time = time.time() - start_time
    total_chars = sum(len(t) for _, t in all_text)
    
    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE")
    print(f"{'='*60}")
    print(f"Total time: {total_time:.1f}s ({total_time/len(images):.1f}s per page)")
    print(f"Total characters extracted: {total_chars:,}")
    print(f"Individual pages saved to: {OUTPUT_DIR}/page_XXXXX.txt")
    print(f"Combined output: {combined_file}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
