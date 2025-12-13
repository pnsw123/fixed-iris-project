#!/usr/bin/env python3
"""
PDF OCR Extraction Script v3
Uses Arabic-Nougat model for state-of-the-art Arabic book OCR
Outputs structured Markdown text
"""

import os
import time
from pathlib import Path

import torch
from PIL import Image
from pdf2image import convert_from_path
from transformers import VisionEncoderDecoderModel, NougatProcessor

# Configuration
PDF_PATH = "/Users/yazeed/Desktop/AntiGravity_1-main/tribe.pdf"
OUTPUT_DIR = "/Users/yazeed/Desktop/AntiGravity_1-main/ocr_output_v3"
PAGES_TO_EXTRACT = 50  # First 50 pages as sample
MODEL_NAME = "MohamedRashad/arabic-small-nougat"  # Using small model for faster inference

# Device setup - prefer MPS (Apple Silicon), fallback to CUDA or CPU
if torch.backends.mps.is_available():
    DEVICE = torch.device("mps")
    print("Using MPS (Apple Silicon GPU)")
elif torch.cuda.is_available():
    DEVICE = torch.device("cuda")
    print("Using CUDA GPU")
else:
    DEVICE = torch.device("cpu")
    print("Using CPU (will be slow)")


def main():
    print("=" * 60)
    print("PDF OCR Extraction v3 (Arabic-Nougat)")
    print("=" * 60)
    print(f"PDF: {PDF_PATH}")
    print(f"Pages to extract: 1-{PAGES_TO_EXTRACT}")
    print(f"Model: {MODEL_NAME}")
    print(f"Device: {DEVICE}")
    print("=" * 60)
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    start_time = time.time()
    
    # Step 1: Load the model and processor
    print(f"\n[1/4] Loading Arabic-Nougat model...")
    model_start = time.time()
    
    processor = NougatProcessor.from_pretrained(MODEL_NAME)
    model = VisionEncoderDecoderModel.from_pretrained(MODEL_NAME)
    model = model.to(DEVICE)
    model.eval()
    
    print(f"      Model loaded in {time.time() - model_start:.1f}s")
    
    # Step 2: Convert PDF pages to images
    print(f"\n[2/4] Converting PDF pages to images...")
    convert_start = time.time()
    
    images = convert_from_path(
        PDF_PATH,
        dpi=200,  # Nougat works well at 200 DPI
        first_page=1,
        last_page=PAGES_TO_EXTRACT,
        thread_count=4
    )
    print(f"      Converted {len(images)} pages in {time.time() - convert_start:.1f}s")
    
    # Step 3: Run OCR on each page
    print(f"\n[3/4] Running Arabic-Nougat OCR...")
    ocr_start = time.time()
    
    all_text = []
    for i, image in enumerate(images, start=1):
        print(f"      Processing page {i}/{len(images)}...", end="\r")
        
        # Prepare image for model
        pixel_values = processor(image, return_tensors="pt").pixel_values.to(DEVICE)
        
        # Generate text
        with torch.no_grad():
            outputs = model.generate(
                pixel_values,
                max_new_tokens=2048,
                bad_words_ids=[[processor.tokenizer.unk_token_id]],
                do_sample=False,
            )
        
        # Decode output
        text = processor.batch_decode(outputs, skip_special_tokens=True)[0]
        
        # Post-process (remove repetitions if any)
        text = processor.post_process_generation(text, fix_markdown=False)
        
        all_text.append((i, text))
        
        # Save individual page
        page_file = Path(OUTPUT_DIR) / f"page_{i:05d}.md"
        with open(page_file, "w", encoding="utf-8") as f:
            f.write(text)
    
    print(f"\n      OCR completed in {time.time() - ocr_start:.1f}s")
    print(f"      Average: {(time.time() - ocr_start) / len(images):.1f}s per page")
    
    # Step 4: Save combined output
    print(f"\n[4/4] Saving combined output...")
    combined_file = Path(OUTPUT_DIR) / "tribe_ocr_sample_50pages.md"
    with open(combined_file, "w", encoding="utf-8") as f:
        for page_num, text in all_text:
            f.write(f"\n{'='*60}\n")
            f.write(f"# PAGE {page_num}\n")
            f.write(f"{'='*60}\n\n")
            f.write(text)
            f.write("\n")
    
    total_time = time.time() - start_time
    total_chars = sum(len(t) for _, t in all_text)
    
    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE (Arabic-Nougat)")
    print(f"{'='*60}")
    print(f"Total time: {total_time:.1f}s ({total_time/len(all_text):.1f}s per page)")
    print(f"Total characters extracted: {total_chars:,}")
    print(f"Individual pages: {OUTPUT_DIR}/page_XXXXX.md")
    print(f"Combined output: {combined_file}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
