#!/usr/bin/env python3
"""
PDF OCR Extraction Script v2
Uses OCRmyPDF + pdfplumber for faster, multi-core OCR extraction
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path

import pdfplumber

# Configuration
PDF_PATH = "/Users/yazeed/Desktop/AntiGravity_1-main/tribe.pdf"
OUTPUT_DIR = "/Users/yazeed/Desktop/AntiGravity_1-main/ocr_output_v2"
PAGES_TO_EXTRACT = 50  # First 50 pages as sample
LANG = "ara+eng"  # Arabic + English

def main():
    print("=" * 60)
    print("PDF OCR Extraction v2 (OCRmyPDF + pdfplumber)")
    print("=" * 60)
    print(f"PDF: {PDF_PATH}")
    print(f"Pages to extract: 1-{PAGES_TO_EXTRACT}")
    print(f"Languages: {LANG}")
    print("=" * 60)
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    start_time = time.time()
    
    # Step 1: Extract first 50 pages to a temp PDF
    print(f"\n[1/4] Extracting first {PAGES_TO_EXTRACT} pages...")
    temp_input = Path(OUTPUT_DIR) / "temp_input_50pages.pdf"
    
    # Use pdftk or qpdf to extract pages - try qpdf first (usually available with poppler)
    try:
        subprocess.run([
            "qpdf", PDF_PATH,
            "--pages", PDF_PATH, f"1-{PAGES_TO_EXTRACT}", "--",
            str(temp_input)
        ], check=True, capture_output=True)
        print(f"      Extracted pages using qpdf in {time.time() - start_time:.1f}s")
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback: use pikepdf 
        print("      qpdf not found, using pikepdf...")
        import pikepdf
        with pikepdf.open(PDF_PATH) as pdf:
            new_pdf = pikepdf.Pdf.new()
            for i in range(min(PAGES_TO_EXTRACT, len(pdf.pages))):
                new_pdf.pages.append(pdf.pages[i])
            new_pdf.save(str(temp_input))
        print(f"      Extracted pages using pikepdf in {time.time() - start_time:.1f}s")
    
    # Step 2: Run OCRmyPDF on the extracted pages
    print(f"\n[2/4] Running OCRmyPDF (multi-core OCR)...")
    ocr_start = time.time()
    ocr_output_pdf = Path(OUTPUT_DIR) / "tribe_50pages_ocr.pdf"
    
    import ocrmypdf
    result = ocrmypdf.ocr(
        str(temp_input),
        str(ocr_output_pdf),
        language=LANG,
        force_ocr=True,      # Treat all pages as images
        deskew=True,         # Straighten crooked pages
        optimize=1,          # Light compression
        jobs=4,              # Use 4 parallel workers
        skip_text=False,     # OCR even if text exists
    )
    print(f"      OCRmyPDF completed in {time.time() - ocr_start:.1f}s")
    print(f"      Result: {result}")
    
    # Step 3: Extract text with pdfplumber
    print(f"\n[3/4] Extracting text with pdfplumber...")
    extract_start = time.time()
    
    all_text = []
    with pdfplumber.open(str(ocr_output_pdf)) as pdf:
        total_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            print(f"      Processing page {i}/{total_pages}...", end="\r")
            text = page.extract_text() or ""
            all_text.append((i, text))
            
            # Save individual page
            page_file = Path(OUTPUT_DIR) / f"page_{i:05d}.txt"
            with open(page_file, "w", encoding="utf-8") as f:
                f.write(text)
    
    print(f"\n      Text extraction completed in {time.time() - extract_start:.1f}s")
    
    # Step 4: Save combined output
    print(f"\n[4/4] Saving combined output...")
    combined_file = Path(OUTPUT_DIR) / "tribe_ocr_sample_50pages.txt"
    with open(combined_file, "w", encoding="utf-8") as f:
        for page_num, text in all_text:
            f.write(f"\n{'='*60}\n")
            f.write(f"PAGE {page_num}\n")
            f.write(f"{'='*60}\n\n")
            f.write(text)
            f.write("\n")
    
    # Cleanup temp file
    if temp_input.exists():
        temp_input.unlink()
    
    total_time = time.time() - start_time
    total_chars = sum(len(t) for _, t in all_text)
    
    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE (OCRmyPDF + pdfplumber)")
    print(f"{'='*60}")
    print(f"Total time: {total_time:.1f}s ({total_time/len(all_text):.1f}s per page)")
    print(f"Total characters extracted: {total_chars:,}")
    print(f"OCR'd PDF: {ocr_output_pdf}")
    print(f"Individual pages: {OUTPUT_DIR}/page_XXXXX.txt")
    print(f"Combined output: {combined_file}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
