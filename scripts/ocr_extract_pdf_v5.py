#!/usr/bin/env python3
"""
PDF OCR Extraction Script v5
Best Practice Tesseract Pipeline with OpenCV Preprocessing + Batching

Stack:
- Tesseract OCR (LSTM engine)
- Poppler + pdf2image (PDF → images)
- OpenCV (preprocessing: grayscale, denoise, binarize)
- pytesseract (Python wrapper)
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
PAGES_TO_EXTRACT = 999999  # Extract ALL pages
DPI = 300
LANG = "ara"  # Arabic only, use "ara+eng" for mixed
PAGES_PER_BATCH = 10  # Memory-safe batching


def preprocess_for_ocr(pil_img):
    """
    Convert PIL image -> OpenCV, then grayscale + adaptive threshold.
    Optimized for Arabic book pages.
    """
    # Convert PIL to numpy array
    img = np.array(pil_img)
    
    # Convert to grayscale
    img = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    
    # Optional: slight blur to reduce noise
    img = cv2.medianBlur(img, 3)
    
    # Adaptive threshold for binarization - good for varying lighting
    img = cv2.adaptiveThreshold(
        img, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 15
    )
    
    return img


def main():
    print("=" * 60)
    print("PDF OCR Extraction v5 (Tesseract + OpenCV Preprocessing)")
    print("=" * 60)
    print(f"PDF: {PDF_PATH}")
    print(f"Pages to extract: 1-{PAGES_TO_EXTRACT}")
    print(f"DPI: {DPI}")
    print(f"Language: {LANG}")
    print(f"Batch size: {PAGES_PER_BATCH}")
    print("=" * 60)
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    start_time = time.time()
    
    # Get PDF info
    info = pdfinfo_from_path(PDF_PATH)
    total_pages = min(PAGES_TO_EXTRACT, info["Pages"])
    print(f"\nFound {info['Pages']} pages in PDF, processing first {total_pages}")
    
    # Tesseract config: LSTM engine (OEM 3) + Block of text layout (PSM 6)
    tesseract_config = r"--oem 3 --psm 6"
    
    # Combined output file
    combined_file = Path(OUTPUT_DIR) / "tribe_ocr_sample_50pages.txt"
    
    all_text = []
    total_chars = 0
    
    with combined_file.open("w", encoding="utf-8") as out:
        # Process in batches for memory efficiency
        for batch_start in range(1, total_pages + 1, PAGES_PER_BATCH):
            batch_end = min(batch_start + PAGES_PER_BATCH - 1, total_pages)
            print(f"\n[BATCH] Processing pages {batch_start}–{batch_end}...")
            batch_start_time = time.time()
            
            # Convert batch of PDF pages to images
            images = convert_from_path(
                PDF_PATH,
                dpi=DPI,
                first_page=batch_start,
                last_page=batch_end,
                thread_count=4
            )
            
            # OCR each page in batch
            for i, pil_img in enumerate(images):
                page_num = batch_start + i
                print(f"      Page {page_num}/{total_pages}...", end="\r")
                
                # Preprocess image with OpenCV
                proc_img = preprocess_for_ocr(pil_img)
                
                # Run Tesseract OCR
                text = pytesseract.image_to_string(
                    proc_img,
                    lang=LANG,
                    config=tesseract_config
                )
                
                # Write to combined file
                out.write(f"\n{'='*60}\n")
                out.write(f"PAGE {page_num}\n")
                out.write(f"{'='*60}\n\n")
                out.write(text)
                out.write("\n")
                
                # Save individual page
                page_file = Path(OUTPUT_DIR) / f"page_{page_num:05d}.txt"
                with open(page_file, "w", encoding="utf-8") as pf:
                    pf.write(text)
                
                all_text.append((page_num, text))
                total_chars += len(text)
            
            batch_time = time.time() - batch_start_time
            print(f"\n      Batch completed in {batch_time:.1f}s ({batch_time/(batch_end-batch_start+1):.1f}s/page)")
    
    total_time = time.time() - start_time
    
    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE (Tesseract + OpenCV)")
    print(f"{'='*60}")
    print(f"Total time: {total_time:.1f}s ({total_time/len(all_text):.1f}s per page)")
    print(f"Total characters extracted: {total_chars:,}")
    print(f"Individual pages: {OUTPUT_DIR}/page_XXXXX.txt")
    print(f"Combined output: {combined_file}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
