#!/usr/bin/env python3
"""
PDF OCR Extraction Script v5 - RESUME VERSION
Resumes from where it left off by checking existing page files
"""

import os
import time
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_path, pdfinfo_from_path

# Configuration
PDF_PATH = "/Users/yazeed/Desktop/AntiGravity_1-main/tribe.pdf"
OUTPUT_DIR = "/Users/yazeed/Desktop/AntiGravity_1-main/ocr_output_v5"
DPI = 300
LANG = "ara"
PAGES_PER_BATCH = 10


def preprocess_for_ocr(pil_img):
    """Convert PIL image -> OpenCV, then grayscale + adaptive threshold."""
    img = np.array(pil_img)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    img = cv2.medianBlur(img, 3)
    img = cv2.adaptiveThreshold(
        img, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 15
    )
    return img


def find_last_extracted_page(output_dir):
    """Find the highest page number already extracted."""
    output_path = Path(output_dir)
    existing_pages = list(output_path.glob("page_*.txt"))
    
    if not existing_pages:
        return 0
    
    page_nums = []
    for p in existing_pages:
        try:
            # Extract page number from filename like page_00123.txt
            num = int(p.stem.split("_")[1])
            page_nums.append(num)
        except:
            pass
    
    return max(page_nums) if page_nums else 0


def main():
    print("=" * 60)
    print("PDF OCR Extraction v5 - RESUME MODE")
    print("=" * 60)
    
    # Get PDF info
    info = pdfinfo_from_path(PDF_PATH)
    total_pages = info["Pages"]
    
    # Find where to resume from
    last_page = find_last_extracted_page(OUTPUT_DIR)
    start_page = last_page + 1
    
    print(f"PDF: {PDF_PATH}")
    print(f"Total pages in PDF: {total_pages}")
    print(f"Already extracted: {last_page} pages")
    print(f"Resuming from page: {start_page}")
    print(f"Pages remaining: {total_pages - last_page}")
    print("=" * 60)
    
    if start_page > total_pages:
        print("All pages already extracted!")
        return
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    start_time = time.time()
    
    tesseract_config = r"--oem 3 --psm 6"
    
    # Combined output file - append mode
    combined_file = Path(OUTPUT_DIR) / "tribe_ocr_full.txt"
    
    pages_processed = 0
    
    with combined_file.open("a", encoding="utf-8") as out:
        for batch_start in range(start_page, total_pages + 1, PAGES_PER_BATCH):
            batch_end = min(batch_start + PAGES_PER_BATCH - 1, total_pages)
            print(f"\n[BATCH] Processing pages {batch_start}–{batch_end}...")
            batch_start_time = time.time()
            
            images = convert_from_path(
                PDF_PATH,
                dpi=DPI,
                first_page=batch_start,
                last_page=batch_end,
                thread_count=4
            )
            
            for i, pil_img in enumerate(images):
                page_num = batch_start + i
                print(f"      Page {page_num}/{total_pages}...", end="\r")
                
                proc_img = preprocess_for_ocr(pil_img)
                
                text = pytesseract.image_to_string(
                    proc_img,
                    lang=LANG,
                    config=tesseract_config
                )
                
                out.write(f"\n{'='*60}\n")
                out.write(f"PAGE {page_num}\n")
                out.write(f"{'='*60}\n\n")
                out.write(text)
                out.write("\n")
                out.flush()  # Ensure data is written immediately
                
                page_file = Path(OUTPUT_DIR) / f"page_{page_num:05d}.txt"
                with open(page_file, "w", encoding="utf-8") as pf:
                    pf.write(text)
                
                pages_processed += 1
            
            batch_time = time.time() - batch_start_time
            elapsed = time.time() - start_time
            pages_remaining = total_pages - page_num
            avg_time = elapsed / pages_processed if pages_processed > 0 else 1
            eta_seconds = pages_remaining * avg_time
            eta_hours = eta_seconds / 3600
            
            print(f"\n      Batch: {batch_time:.1f}s | Total: {elapsed/60:.1f}m | ETA: {eta_hours:.1f}h")
    
    total_time = time.time() - start_time
    
    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE")
    print(f"{'='*60}")
    print(f"Pages processed this run: {pages_processed}")
    print(f"Total time: {total_time/3600:.2f} hours")
    print(f"Combined output: {combined_file}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
