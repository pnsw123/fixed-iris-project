"""Image conversion utilities for base64 and numpy array handling."""

import numpy as np
import cv2
from PIL import Image
import base64
import io
from typing import Union


def numpy_to_base64(img_array: np.ndarray, format: str = 'PNG') -> str:
    """
    Convert numpy array to base64 data URL.

    Args:
        img_array: Numpy array (H, W) for grayscale or (H, W, 3) for RGB
        format: Image format 'PNG' or 'JPEG'

    Returns:
        Base64 data URL string (e.g., "data:image/png;base64,...")
    """
    # Handle grayscale vs RGB
    if len(img_array.shape) == 2:
        # Grayscale
        img = Image.fromarray(img_array, mode='L')
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
