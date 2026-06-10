"""Image conversion utilities for base64 and numpy array handling."""

import logging
import numpy as np
import cv2
from PIL import Image
import base64
import io
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

# Bundled font — works on all platforms (macOS, Linux, Windows)
_FONTS_DIR = Path(__file__).parent / "fonts"
_BUNDLED_FONT = _FONTS_DIR / "DejaVuSans.ttf"


def numpy_to_base64(img_array: np.ndarray, format: str = 'PNG') -> str:
    """
    Convert numpy array to base64 data URL.

    Args:
        img_array: Numpy array (H, W) for grayscale or (H, W, 3) for RGB
        format: Image format 'PNG' or 'JPEG'

    Returns:
        Base64 data URL string (e.g., "data:image/png;base64,...")
    """
    # Handle grayscale vs RGB vs RGBA
    if len(img_array.shape) == 2:
        # Grayscale
        img = Image.fromarray(img_array, mode='L')
    elif img_array.shape[2] == 4:
        # RGBA (transparent)
        img = Image.fromarray(img_array.astype(np.uint8), mode='RGBA')
    else:
        # RGB
        img = Image.fromarray(img_array.astype(np.uint8), mode='RGB')

    # Encode to bytes
    buffer = io.BytesIO()
    img.save(buffer, format=format)
    buffer.seek(0)

    # Convert to base64
    img_base64 = base64.b64encode(buffer.read()).decode('utf-8')

    # Create data URL
    mime_type = 'image/png' if format.upper() == 'PNG' else 'image/jpeg'
    return f"data:{mime_type};base64,{img_base64}"


def base64_to_numpy(data_url: str) -> np.ndarray:
    """
    Convert base64 data URL to numpy array (RGB).

    Args:
        data_url: Base64 data URL string

    Returns:
        Numpy array (H, W, 3) in RGB format
    """
    # Remove data URL prefix
    if ',' in data_url:
        data_url = data_url.split(',')[1]

    # Decode base64
    img_bytes = base64.b64decode(data_url)

    # Load as PIL Image and convert to RGB
    img = Image.open(io.BytesIO(img_bytes)).convert('RGB')

    # Convert to numpy
    return np.array(img)


def resize_image(
    img: np.ndarray,
    target_size: int = 1024,
    interpolation: int = cv2.INTER_LANCZOS4
) -> tuple:
    """
    Resize image to target size maintaining aspect ratio.

    Args:
        img: Input image array
        target_size: Target size (will be target_size x target_size)
        interpolation: OpenCV interpolation method

    Returns:
        Tuple of (resized_image, scale_factor)
    """
    h, w = img.shape[:2]
    scale = target_size / max(h, w)
    new_h, new_w = int(h * scale), int(w * scale)

    resized = cv2.resize(img, (new_w, new_h), interpolation=interpolation)

    # Pad to target_size x target_size
    padded = np.zeros((target_size, target_size, 3), dtype=np.uint8)
    y_offset = (target_size - new_h) // 2
    x_offset = (target_size - new_w) // 2
    padded[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized

    return padded, scale


def add_watermark(img_array: np.ndarray, text: str = "EYEDENTITY") -> np.ndarray:
    """
    Add a single centered semi-transparent watermark using layer composition.
    This ensures true transparency.
    """
    from PIL import ImageDraw, ImageFont
    
    h, w = img_array.shape[:2]
    
    # 1. Ensure Base Image is RGBA
    if len(img_array.shape) == 3 and img_array.shape[2] == 4:
        base = Image.fromarray(img_array.astype(np.uint8), mode='RGBA')
    else:
        base = Image.fromarray(img_array.astype(np.uint8), mode='RGB')
        base = base.convert('RGBA')
    
    # 2. Create a separate transparent layer for text
    txt_layer = Image.new('RGBA', base.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    # 3. Font Config
    # Make it even smaller: 1/8 of width for better fit
    font_size = max(w // 8, 10)
    
    try:
        font = ImageFont.truetype(str(_BUNDLED_FONT), font_size)
    except Exception:
        font = ImageFont.load_default()
    
    # 4. Measure Text to Center
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    x = (w - text_w) // 2
    y = (h - text_h) // 2
    
    # 5. Draw Text onto Transparent Layer
    # White text with VERY low alpha (50/255 ~= 20%)
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 50))
    
    # 6. Composite the text layer over the base image
    # This renders the semi-transparent pixels correctly
    watermarked = Image.alpha_composite(base, txt_layer)
    
    return np.array(watermarked)


def create_preview(img_array: np.ndarray, max_size: int = 150) -> np.ndarray:
    """
    Create a very low-quality preview.
    Uses pixelation and color quantization to degrade quality.
    """
    from PIL import ImageFilter
    
    h, w = img_array.shape[:2]
    
    # 1. Calculate extremely small size (max 150px)
    if h > w:
        new_h = max_size
        new_w = int(w * (max_size / h))
    else:
        new_w = max_size
        new_h = int(h * (max_size / w))
    
    # Ensure sane minimum
    new_w = max(new_w, 64)
    new_h = max(new_h, 64)
    
    # 2. Load Image
    if len(img_array.shape) == 3 and img_array.shape[2] == 4:
        img = Image.fromarray(img_array.astype(np.uint8), mode='RGBA')
    else:
        img = Image.fromarray(img_array.astype(np.uint8), mode='RGB')
    
    # 3. Resize Down (Bilinear is usually blurry, Nearest is pixelated)
    # Using Bilinear to get it small
    preview = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
    
    # 4. Apply Blur
    preview = preview.filter(ImageFilter.GaussianBlur(radius=1.5))
    
    # 5. Quantize Colors (Reduces color depth -> looks lower quality/gif-like)
    # We must convert to P (palette, quantized) then back to RGBA
    # This introduces dithering/banding artifacts
    if preview.mode == 'RGBA':
        # Split alpha, quantize RGB, put alpha back
        alpha = preview.split()[3]
        rgb = preview.convert('RGB').quantize(colors=32)
        preview = rgb.convert('RGBA')
        preview.putalpha(alpha)
    else:
        preview = preview.quantize(colors=32).convert('RGB')

    
    preview_array = np.array(preview)
    
    # 6. Add Watermark to the degraded image
    watermarked = add_watermark(preview_array)
    
    logger.debug("Created degraded %dx%d preview (quantized+blurred)", new_w, new_h)
    
    return watermarked
