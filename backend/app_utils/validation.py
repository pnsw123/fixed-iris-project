"""Input validation utilities."""

import numpy as np
from PIL import Image
import io


def validate_image_upload(file_contents: bytes, max_size_mb: int = 50) -> np.ndarray:
    """
    Validate and load image from bytes.

    Args:
        file_contents: Raw file bytes
        max_size_mb: Maximum file size in MB

    Returns:
        Numpy array (H, W, 3) in RGB format

    Raises:
        ValueError: If image is invalid
    """
    # Check file size
    file_size_mb = len(file_contents) / (1024 * 1024)
    if file_size_mb > max_size_mb:
        raise ValueError(f"File size {file_size_mb:.1f}MB exceeds limit of {max_size_mb}MB")

    try:
        # Load image
        img = Image.open(io.BytesIO(file_contents)).convert('RGB')
        img_array = np.array(img)

        # Validate dimensions
        if len(img_array.shape) != 3 or img_array.shape[2] != 3:
            raise ValueError("Image must be RGB (3-channel)")

        if min(img_array.shape[:2]) < 64:
            raise ValueError("Image too small (minimum 64x64 pixels)")

        if max(img_array.shape[:2]) > 4096:
            raise ValueError("Image too large (maximum 4096x4096 pixels)")

        return img_array

    except Image.UnidentifiedImageError:
        raise ValueError("Invalid image format. Supported: JPEG, PNG, etc.")
    except Exception as e:
        raise ValueError(f"Failed to load image: {str(e)}")
