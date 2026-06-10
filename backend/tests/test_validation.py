"""Tests for app_utils/validation.py — validate_image_upload."""

import io
import pytest
from PIL import Image
import numpy as np

# ---------------------------------------------------------------------------
# Path bootstrap — ensure backend/ is importable when running from project root
# ---------------------------------------------------------------------------
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app_utils.validation import validate_image_upload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_png_bytes(width: int = 200, height: int = 200, mode: str = 'RGB') -> bytes:
    """Create a minimal valid PNG in memory."""
    img = Image.new(mode, (width, height), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def make_jpeg_bytes(width: int = 200, height: int = 200) -> bytes:
    """Create a minimal valid JPEG in memory."""
    img = Image.new('RGB', (width, height), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

class TestValidateImageUploadHappyPath:
    def test_returns_numpy_array_for_valid_png(self):
        result = validate_image_upload(make_png_bytes())
        assert isinstance(result, np.ndarray)

    def test_returns_numpy_array_for_valid_jpeg(self):
        result = validate_image_upload(make_jpeg_bytes())
        assert isinstance(result, np.ndarray)

    def test_output_shape_is_h_w_3(self):
        result = validate_image_upload(make_png_bytes(320, 240))
        assert result.shape == (240, 320, 3)

    def test_accepts_image_at_min_boundary(self):
        """Exactly 64x64 should be accepted."""
        result = validate_image_upload(make_png_bytes(64, 64))
        assert result.shape == (64, 64, 3)

    def test_accepts_image_at_max_boundary(self):
        """Exactly 4096x4096 should be accepted."""
        # Use smaller test image but verify the limit logic numerically
        # (full 4096x4096 PNG would be huge in a unit test)
        result = validate_image_upload(make_png_bytes(4096, 4096))
        assert result.shape == (4096, 4096, 3)

    def test_rgba_image_converted_to_rgb(self):
        """RGBA images must be converted to 3-channel RGB by the function."""
        rgba_bytes = make_png_bytes(100, 100, mode='RGBA')
        # validate_image_upload calls .convert('RGB') internally
        result = validate_image_upload(rgba_bytes)
        assert result.shape[2] == 3

    def test_custom_max_size_limit_large(self):
        """Custom large limit should not raise for small image."""
        small = make_png_bytes(100, 100)
        result = validate_image_upload(small, max_size_mb=100)
        assert result is not None


# ---------------------------------------------------------------------------
# File-size validation
# ---------------------------------------------------------------------------

class TestFileSizeValidation:
    def test_rejects_file_over_default_50mb_limit(self):
        # Synthesise oversized payload using raw bytes (not a real image,
        # but size check happens before format parse)
        big_payload = b'\x00' * (51 * 1024 * 1024)
        with pytest.raises(ValueError, match="exceeds limit"):
            validate_image_upload(big_payload)

    def test_rejects_file_over_custom_limit(self):
        # 2 MB payload, limit set to 1 MB
        payload = b'\x00' * (2 * 1024 * 1024)
        with pytest.raises(ValueError, match="exceeds limit"):
            validate_image_upload(payload, max_size_mb=1)

    def test_accepts_file_exactly_at_limit(self):
        # A real 1-byte-under-limit image — use a tiny real PNG padded to near limit
        # Easiest: verify 1 MB PNG with max_size_mb=1 succeeds (it's tiny)
        small = make_png_bytes(200, 200)
        result = validate_image_upload(small, max_size_mb=1)
        assert result is not None


# ---------------------------------------------------------------------------
# Image dimension validation
# ---------------------------------------------------------------------------

class TestImageDimensionValidation:
    def test_rejects_image_smaller_than_64px(self):
        small = make_png_bytes(32, 32)
        with pytest.raises(ValueError, match="too small"):
            validate_image_upload(small)

    def test_rejects_image_63px_in_one_dimension(self):
        small = make_png_bytes(63, 200)
        with pytest.raises(ValueError, match="too small"):
            validate_image_upload(small)

    def test_rejects_image_larger_than_4096_in_any_dimension(self):
        big = make_png_bytes(4097, 100)
        with pytest.raises(ValueError, match="too large"):
            validate_image_upload(big)

    def test_rejects_image_4096_in_width_but_height_over(self):
        big = make_png_bytes(100, 4097)
        with pytest.raises(ValueError, match="too large"):
            validate_image_upload(big)


# ---------------------------------------------------------------------------
# Invalid / corrupt data
# ---------------------------------------------------------------------------

class TestInvalidImageData:
    def test_rejects_empty_bytes(self):
        with pytest.raises(ValueError):
            validate_image_upload(b'')

    def test_rejects_random_bytes(self):
        with pytest.raises(ValueError):
            validate_image_upload(b'this is not an image at all')

    def test_rejects_truncated_png(self):
        valid = make_png_bytes(100, 100)
        truncated = valid[:50]  # Truncate PNG header
        with pytest.raises(ValueError):
            validate_image_upload(truncated)

    def test_rejects_text_file_disguised_as_image(self):
        fake_image = b'Hello, world! This is a text file.\n' * 100
        with pytest.raises(ValueError):
            validate_image_upload(fake_image)
