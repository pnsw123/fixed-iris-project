#!/usr/bin/env python3
"""
PDF OCR Extraction Script v4 (Updated)
Pipeline: PDF → PNGs (PyMuPDF) → ArabicOcr → text file
"""

import os
import time
from pathlib import Path

import fitz  # PyMuPDF
from ArabicOcr import arabicocr

# Configuration
PDF_PATH = "/Users/yazeed/Desktop/AntiGravity_1-main/tribe.pdf"
OUTPUT_DIR = "/Users/yazeed/Desktop/AntiGravity_1-main/ocr_output_v4"
PAGES_TO_EXTRACT = 50  # First 50 pages as sample
DPI = 300  # Render at 300 DPI for good OCR quality


def main():
    print("=" * 60)
    print("PDF OCR Extraction v4 (PyMuPDF + ArabicOcr)")
    print("=" * 60)
    print(f"PDF: {PDF_PATH}")
    print(f"Pages to extract: 1-{PAGES_TO_EXTRACT}")
    print(f"DPI: {DPI}")
    print("=" * 60)
    
    # Create output directories
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    images_dir = Path(OUTPUT_DIR) / "images"
    os.makedirs(images_dir, exist_ok=True)
    
    start_time = time.time()
    
    # Step 1: Convert PDF pages to PNGs using PyMuPDF
    print(f"\n[1/3] Converting PDF pages to PNGs (PyMuPDF)...")
    convert_start = time.time()
    
    doc = fitz.open(PDF_PATH)
    total_pages = min(PAGES_TO_EXTRACT, len(doc))
    
    # Calculate zoom factor for desired DPI (default is 72 DPI)
    zoom = DPI / 72
    mat = fitz.Matrix(zoom, zoom)
    
    image_paths = []
    for i in range(total_pages):
        page = doc[i]
        pix = page.get_pixmap(matrix=mat)
        img_path = images_dir / f"page_{i+1:05d}.png"
        pix.save(str(img_path))
        image_paths.append(str(img_path))
        print(f"      Page {i+1}/{total_pages}", end="\r")
    
    doc.close()
    print(f"\n      Converted {len(image_paths)} pages in {time.time() - convert_start:.1f}s")
    
    # Step 2: Run ArabicOcr on each page
    print(f"\n[2/3] Running ArabicOcr on {len(image_paths)} pages...")
    ocr_start = time.time()
    
    all_text = []
    for i, img_path in enumerate(image_paths, start=1):
        print(f"      Processing page {i}/{len(image_paths)}...", end="\r")
        
        # ArabicOcr returns list of (bbox, text, confidence) tuples
        out_image = str(images_dir / f"page_{i:05d}_ocr.png")
        results = arabicocr.arabic_ocr(img_path, out_image)
        
        # Extract just the text, preserving order (RTL reading order)
        page_text_parts = []
        for item in results:
            if len(item) >= 2:
                text = item[1]
                if text and text.strip():
                    page_text_parts.append(text)
        
        # Join text with spaces
        page_text = " ".join(page_text_parts)
        all_text.append((i, page_text))
        
        # Save individual page text
        page_file = Path(OUTPUT_DIR) / f"page_{i:05d}.txt"
        with open(page_file, "w", encoding="utf-8") as f:
            f.write(page_text)
    
    print(f"\n      OCR completed in {time.time() - ocr_start:.1f}s")
    print(f"      Average: {(time.time() - ocr_start) / len(image_paths):.1f}s per page")
    
    # Step 3: Save combined output
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
    print(f"EXTRACTION COMPLETE (PyMuPDF + ArabicOcr)")
    print(f"{'='*60}")
    print(f"Total time: {total_time:.1f}s ({total_time/len(all_text):.1f}s per page)")
    print(f"Total characters extracted: {total_chars:,}")
    print(f"Individual pages: {OUTPUT_DIR}/page_XXXXX.txt")
    print(f"Combined output: {combined_file}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
