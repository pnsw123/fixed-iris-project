#!/usr/bin/env python3
"""
Multi-PDF OCR Extraction Script
Processes multiple PDFs with Tesseract + OpenCV preprocessing
Each PDF gets its own output folder
"""

import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_path, pdfinfo_from_path

# Configuration
BASE_DIR = "/Users/yazeed/Desktop/AntiGravity_1-main/Data"
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
    if not output_path.exists():
        return 0
    existing_pages = list(output_path.glob("page_*.txt"))
    if not existing_pages:
        return 0
    page_nums = []
    for p in existing_pages:
        try:
            num = int(p.stem.split("_")[1])
            page_nums.append(num)
        except:
            pass
    return max(page_nums) if page_nums else 0


def extract_pdf(pdf_path, output_dir):
    """Extract text from a PDF file."""
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    
    print(f"\n{'='*60}")
    print(f"Processing: {pdf_path.name}")
    print(f"Output: {output_dir}")
    print(f"{'='*60}")
    
    # Get PDF info
    info = pdfinfo_from_path(str(pdf_path))
    total_pages = info["Pages"]
    
    # Find where to resume from
    last_page = find_last_extracted_page(output_dir)
    start_page = last_page + 1
    
    print(f"Total pages: {total_pages}")
    print(f"Already extracted: {last_page}")
    print(f"Starting from page: {start_page}")
    
    if start_page > total_pages:
        print("All pages already extracted! Skipping.")
        return
    
    os.makedirs(output_dir, exist_ok=True)
    start_time = time.time()
    
    tesseract_config = r"--oem 3 --psm 6"
    
    # Combined output file
    combined_file = output_dir / f"{pdf_path.stem}_ocr_full.txt"
    mode = "a" if start_page > 1 else "w"
    
    pages_processed = 0
    
    with combined_file.open(mode, encoding="utf-8") as out:
        for batch_start in range(start_page, total_pages + 1, PAGES_PER_BATCH):
            batch_end = min(batch_start + PAGES_PER_BATCH - 1, total_pages)
            print(f"\n[BATCH] Pages {batch_start}–{batch_end}...", end="")
            batch_start_time = time.time()
            
            try:
                images = convert_from_path(
                    str(pdf_path),
                    dpi=DPI,
                    first_page=batch_start,
                    last_page=batch_end,
                    thread_count=4
                )
            except Exception as e:
                print(f" ERROR: {e}")
                continue
            
            for i, pil_img in enumerate(images):
                page_num = batch_start + i
                
                try:
                    proc_img = preprocess_for_ocr(pil_img)
                    text = pytesseract.image_to_string(proc_img, lang=LANG, config=tesseract_config)
                except Exception as e:
                    text = f"[ERROR: {e}]"
                
                out.write(f"\n{'='*60}\n")
                out.write(f"PAGE {page_num}\n")
                out.write(f"{'='*60}\n\n")
                out.write(text)
                out.write("\n")
                out.flush()
                
                page_file = output_dir / f"page_{page_num:05d}.txt"
                with open(page_file, "w", encoding="utf-8") as pf:
                    pf.write(text)
                
                pages_processed += 1
            
            batch_time = time.time() - batch_start_time
            print(f" {batch_time:.1f}s")
    
    total_time = time.time() - start_time
    print(f"\n✓ Completed {pdf_path.name}: {pages_processed} pages in {total_time/60:.1f}m")
    return pages_processed


def main():
    # PDFs to process with their output folders
    pdf_configs = [
        ("tribe3.pdf", "ocr_tribe3"),
        ("tribe4.pdf", "ocr_tribe4"),
        ("tribes2.pdf", "ocr_tribes2"),
        ("tribes6.pdf", "ocr_tribes6"),
    ]
    
    print("=" * 60)
    print("Multi-PDF OCR Extraction")
    print("=" * 60)
    
    for pdf_name, output_folder in pdf_configs:
        pdf_path = Path(BASE_DIR).parent / pdf_name
        output_dir = Path(BASE_DIR) / output_folder
        
        if not pdf_path.exists():
            print(f"⚠ Skipping {pdf_name} - file not found")
            continue
        
        extract_pdf(pdf_path, output_dir)
    
    print("\n" + "=" * 60)
    print("ALL PDFs PROCESSED!")
    print("=" * 60)


if __name__ == "__main__":
    main()
