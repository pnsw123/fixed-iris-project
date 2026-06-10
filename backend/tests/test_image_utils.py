"""Tests for app_utils/image_utils.py — numpy_to_base64, create_preview, add_watermark."""

import base64
import sys
import os
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

# ---------------------------------------------------------------------------
# Path bootstrap — ensure backend/ is importable when running from project root
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from app_utils.image_utils import numpy_to_base64, create_preview, add_watermark


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_rgb_array(width: int = 200, height: int = 200) -> np.ndarray:
    """Solid-colour RGB numpy array."""
    return np.full((height, width, 3), fill_value=[120, 80, 40], dtype=np.uint8)


def make_rgba_array(width: int = 200, height: int = 200) -> np.ndarray:
    """Solid-colour RGBA numpy array with full opacity."""
    return np.full((height, width, 4), fill_value=[120, 80, 40, 255], dtype=np.uint8)


def make_gray_array(width: int = 100, height: int = 100) -> np.ndarray:
    """Grayscale (H, W) numpy array."""
    return np.full((height, width), fill_value=128, dtype=np.uint8)


# ---------------------------------------------------------------------------
# numpy_to_base64
# ---------------------------------------------------------------------------

class TestNumpyToBase64:
    def test_returns_string(self):
        result = numpy_to_base64(make_rgb_array())
        assert isinstance(result, str)

    def test_png_data_url_prefix(self):
        result = numpy_to_base64(make_rgb_array(), format='PNG')
        assert result.startswith('data:image/png;base64,')

    def test_jpeg_data_url_prefix(self):
        result = numpy_to_base64(make_rgb_array(), format='JPEG')
        assert result.startswith('data:image/jpeg;base64,')

    def test_base64_payload_is_decodable(self):
        result = numpy_to_base64(make_rgb_array())
        _, payload = result.split(',', 1)
        decoded = base64.b64decode(payload)
        assert len(decoded) > 0

    def test_round_trip_rgb(self):
        """Encode then decode should produce same-shape array."""
        original = make_rgb_array(100, 100)
        data_url = numpy_to_base64(original, format='PNG')
        _, payload = data_url.split(',', 1)
        img = Image.open(__import__('io').BytesIO(base64.b64decode(payload)))
        assert img.size == (100, 100)

    def test_grayscale_array(self):
        """2D (H, W) array should produce valid PNG data URL."""
        result = numpy_to_base64(make_gray_array(), format='PNG')
        assert result.startswith('data:image/png;base64,')

    def test_rgba_array(self):
        """RGBA (H, W, 4) array should produce valid PNG data URL."""
        result = numpy_to_base64(make_rgba_array(), format='PNG')
        assert result.startswith('data:image/png;base64,')
        _, payload = result.split(',', 1)
        decoded = base64.b64decode(payload)
        assert len(decoded) > 0


# ---------------------------------------------------------------------------
# add_watermark
# ---------------------------------------------------------------------------

class TestAddWatermark:
    def test_rgb_input_returns_array(self):
        result = add_watermark(make_rgb_array())
        assert isinstance(result, np.ndarray)

    def test_rgba_input_returns_array(self):
        result = add_watermark(make_rgba_array())
        assert isinstance(result, np.ndarray)

    def test_rgb_output_shape_height_width_preserved(self):
        """Output H and W must match input H and W."""
        arr = make_rgb_array(200, 150)
        result = add_watermark(arr)
        assert result.shape[0] == 150
        assert result.shape[1] == 200

    def test_rgba_output_shape_height_width_preserved(self):
        arr = make_rgba_array(200, 150)
        result = add_watermark(arr)
        assert result.shape[0] == 150
        assert result.shape[1] == 200

    def test_output_has_4_channels(self):
        """add_watermark always returns RGBA (4-channel) due to alpha_composite."""
        result = add_watermark(make_rgb_array())
        assert result.shape[2] == 4

    def test_custom_text(self):
        result = add_watermark(make_rgb_array(), text="PREVIEW")
        assert result.shape[2] == 4

    def test_font_missing_fallback(self):
        """If DejaVuSans.ttf is not found, function must fall back to default font without raising."""
        import app_utils.image_utils as iu
        with patch.object(iu, '_BUNDLED_FONT', Path('/nonexistent/DejaVuSans.ttf')):
            result = add_watermark(make_rgb_array())
        assert isinstance(result, np.ndarray)
        assert result.shape[2] == 4

    def test_small_image_does_not_raise(self):
        """Tiny images (16x16) should not crash add_watermark."""
        tiny = np.full((16, 16, 3), fill_value=200, dtype=np.uint8)
        result = add_watermark(tiny)
        assert result.shape[0] == 16
        assert result.shape[1] == 16


# ---------------------------------------------------------------------------
# create_preview
# ---------------------------------------------------------------------------

class TestCreatePreview:
    def test_rgb_input_returns_array(self):
        result = create_preview(make_rgb_array(400, 400))
        assert isinstance(result, np.ndarray)

    def test_rgba_input_returns_array(self):
        result = create_preview(make_rgba_array(400, 400))
        assert isinstance(result, np.ndarray)

    def test_output_max_dimension_at_most_max_size(self):
        """Largest side of the output must not exceed max_size."""
        result = create_preview(make_rgb_array(800, 600), max_size=150)
        h, w = result.shape[:2]
        assert max(h, w) <= 150

    def test_portrait_image_respects_max_size(self):
        result = create_preview(make_rgb_array(300, 600), max_size=150)
        h, w = result.shape[:2]
        assert max(h, w) <= 150

    def test_landscape_image_respects_max_size(self):
        result = create_preview(make_rgb_array(600, 300), max_size=150)
        h, w = result.shape[:2]
        assert max(h, w) <= 150

    def test_very_small_image_clamped_to_64(self):
        """Images whose computed dimension would fall below 64px are clamped to 64."""
        # 10x10 → scale to max_size 150; new_w = max(10*(150/10), 64) = 150; new_h = 150
        # so output H,W both >= 64 after clamp
        tiny = np.full((10, 10, 3), fill_value=50, dtype=np.uint8)
        result = create_preview(tiny, max_size=150)
        h, w = result.shape[:2]
        assert h >= 64
        assert w >= 64

    def test_output_dtype_is_uint8(self):
        result = create_preview(make_rgb_array())
        assert result.dtype == np.uint8

    def test_includes_watermark_4_channels(self):
        """create_preview calls add_watermark → output is RGBA (4 channels)."""
        result = create_preview(make_rgb_array(400, 400))
        assert result.shape[2] == 4

    def test_rgba_input_alpha_channel_handled(self):
        """RGBA path through quantize/alpha split should not raise."""
        rgba = make_rgba_array(400, 400)
        result = create_preview(rgba)
        assert isinstance(result, np.ndarray)

    def test_square_image_output_dimensions(self):
        """Square 400x400 → output square with side == max_size."""
        result = create_preview(make_rgb_array(400, 400), max_size=150)
        h, w = result.shape[:2]
        assert h == 150
        assert w == 150

    def test_custom_max_size(self):
        result = create_preview(make_rgb_array(300, 300), max_size=80)
        h, w = result.shape[:2]
        assert max(h, w) <= 80

    def test_font_missing_does_not_raise(self):
        """Missing font should still produce a preview via default font fallback."""
        import app_utils.image_utils as iu
        with patch.object(iu, '_BUNDLED_FONT', Path('/nonexistent/DejaVuSans.ttf')):
            result = create_preview(make_rgb_array(400, 400))
        assert isinstance(result, np.ndarray)
