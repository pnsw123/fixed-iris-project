"""Tests for services/esrgan_service.py — RealESRGANService.upscale().

Strategy:
- Never load real ML weights. Bypass __init__ via __new__ + manual attribute setup.
- Tests cover: onnx mode, torch mode, input validation, error fallback,
  ONNX preprocessing/postprocessing, scale accessor.
- cv2, torch, onnxruntime are all stubbed by conftest.py at collection time.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helper — build a RealESRGANService without hitting __init__ (no model files)
# ---------------------------------------------------------------------------

def _make_torch_service(scale: int = 4) -> "RealESRGANService":  # noqa: F821
    from services.esrgan_service import RealESRGANService

    svc = RealESRGANService.__new__(RealESRGANService)
    svc.scale = scale
    svc.device = "cpu"
    svc.model_path = "/fake/model.pth"
    svc.mode = "torch"
    svc.upsampler = MagicMock()
    return svc


def _make_onnx_service(scale: int = 4) -> "RealESRGANService":  # noqa: F821
    from services.esrgan_service import RealESRGANService

    svc = RealESRGANService.__new__(RealESRGANService)
    svc.scale = scale
    svc.device = "cpu"
    svc.model_path = "/fake/model.onnx"
    svc.mode = "onnx"

    # Mock ONNX session
    mock_session = MagicMock()
    mock_session.get_inputs.return_value = [MagicMock(name="input")]
    mock_session.get_outputs.return_value = [MagicMock(name="output")]
    svc.session = mock_session
    svc.input_name = "input"
    svc.output_name = "output"
    return svc


def _rgb_image(h: int = 32, w: int = 32) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.integers(0, 255, (h, w, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestUpscaleInputValidation:
    def test_raises_on_2d_grayscale(self):
        from services.esrgan_service import RealESRGANService

        svc = _make_torch_service()
        gray = np.zeros((32, 32), dtype=np.uint8)
        with pytest.raises(ValueError, match="RGB"):
            svc.upscale(gray)

    def test_raises_on_4channel_rgba(self):
        svc = _make_torch_service()
        rgba = np.zeros((32, 32, 4), dtype=np.uint8)
        with pytest.raises(ValueError, match="RGB"):
            svc.upscale(rgba)

    def test_raises_on_1channel_image(self):
        svc = _make_torch_service()
        ch1 = np.zeros((32, 32, 1), dtype=np.uint8)
        with pytest.raises(ValueError, match="RGB"):
            svc.upscale(ch1)


# ---------------------------------------------------------------------------
# Torch mode
# ---------------------------------------------------------------------------

class TestUpscaleTorchMode:
    def test_returns_upscaled_array(self):
        import cv2

        svc = _make_torch_service(scale=4)
        img = _rgb_image(16, 16)

        # Mock cv2.cvtColor pass-through
        bgr_fake = img.copy()
        upscaled_fake = _rgb_image(64, 64)

        cv2.cvtColor = MagicMock(side_effect=[bgr_fake, upscaled_fake])
        svc.upsampler.enhance = MagicMock(return_value=(upscaled_fake, None))

        result = svc.upscale(img)

        assert result is not None
        assert isinstance(result, np.ndarray)

    def test_calls_upsampler_enhance(self):
        import cv2

        svc = _make_torch_service(scale=4)
        img = _rgb_image(16, 16)

        bgr_fake = img.copy()
        upscaled_fake = _rgb_image(64, 64)

        cv2.cvtColor = MagicMock(side_effect=[bgr_fake, upscaled_fake])
        svc.upsampler.enhance = MagicMock(return_value=(bgr_fake, None))

        svc.upscale(img)

        svc.upsampler.enhance.assert_called_once()

    def test_enhance_called_with_correct_outscale(self):
        import cv2

        svc = _make_torch_service(scale=4)
        img = _rgb_image(16, 16)
        bgr_fake = img.copy()

        cv2.cvtColor = MagicMock(side_effect=[bgr_fake, bgr_fake])
        svc.upsampler.enhance = MagicMock(return_value=(bgr_fake, None))

        svc.upscale(img)

        _, call_kwargs = svc.upsampler.enhance.call_args
        assert call_kwargs.get("outscale") == 4

    def test_fallback_returns_original_on_exception(self):
        import cv2

        svc = _make_torch_service(scale=4)
        img = _rgb_image(16, 16)

        cv2.cvtColor = MagicMock(side_effect=RuntimeError("GPU OOM"))

        result = svc.upscale(img)
        # Must return the original image, not raise
        np.testing.assert_array_equal(result, img)


# ---------------------------------------------------------------------------
# ONNX mode
# ---------------------------------------------------------------------------

class TestUpscaleOnnxMode:
    def _make_output_array(self, h: int, w: int) -> np.ndarray:
        """Build fake ONNX output: shape (1, 3, H, W), float32, [0,1]."""
        rng = np.random.default_rng(0)
        return rng.random((1, 3, h, w)).astype(np.float32)

    def test_returns_ndarray_with_3_channels(self):
        svc = _make_onnx_service(scale=4)
        img = _rgb_image(16, 16)
        out_h, out_w = 64, 64

        svc.session.run = MagicMock(
            return_value=[self._make_output_array(out_h, out_w)]
        )

        result = svc.upscale(img)

        assert isinstance(result, np.ndarray)
        assert result.ndim == 3
        assert result.shape[2] == 3

    def test_output_dtype_is_uint8(self):
        svc = _make_onnx_service(scale=4)
        img = _rgb_image(16, 16)

        svc.session.run = MagicMock(
            return_value=[self._make_output_array(64, 64)]
        )

        result = svc.upscale(img)
        assert result.dtype == np.uint8

    def test_output_pixel_values_clipped_0_255(self):
        svc = _make_onnx_service(scale=4)
        img = _rgb_image(16, 16)

        # Make output with values outside [0,1] to test clipping
        bad = np.full((1, 3, 64, 64), 5.0, dtype=np.float32)  # > 1.0
        svc.session.run = MagicMock(return_value=[bad])

        result = svc.upscale(img)
        assert result.max() <= 255
        assert result.min() >= 0

    def test_session_run_called_with_correct_input_name(self):
        svc = _make_onnx_service(scale=4)
        svc.input_name = "images"
        img = _rgb_image(8, 8)

        svc.session.run = MagicMock(
            return_value=[self._make_output_array(32, 32)]
        )

        svc.upscale(img)

        _, call_kwargs = svc.session.run.call_args
        # session.run(output_names, input_feed) — check positional args
        call_args_pos = svc.session.run.call_args[0]
        input_feed = call_args_pos[1] if len(call_args_pos) > 1 else call_kwargs.get("input_feed", {})
        assert "images" in input_feed

    def test_onnx_fallback_on_session_error(self):
        svc = _make_onnx_service(scale=4)
        img = _rgb_image(16, 16)

        svc.session.run = MagicMock(side_effect=RuntimeError("ORT error"))

        result = svc.upscale(img)
        np.testing.assert_array_equal(result, img)

    def test_onnx_input_normalized_to_float32(self):
        """ONNX branch must normalize uint8 [0,255] → float32 [0,1]."""
        svc = _make_onnx_service(scale=4)
        img = np.full((8, 8, 3), 255, dtype=np.uint8)  # all-white

        captured = {}

        def _capture_run(output_names, input_feed):
            captured["feed"] = input_feed
            return [np.zeros((1, 3, 32, 32), dtype=np.float32)]

        svc.session.run = _capture_run
        svc.upscale(img)

        arr = captured["feed"][svc.input_name]
        assert arr.dtype == np.float32
        assert arr.max() <= 1.0 + 1e-6

    def test_onnx_input_transposed_to_chw(self):
        """ONNX branch must transpose HWC → BCHW."""
        svc = _make_onnx_service(scale=4)
        img = _rgb_image(8, 12)  # H=8, W=12

        captured = {}

        def _capture_run(output_names, input_feed):
            captured["feed"] = input_feed
            return [np.zeros((1, 3, 32, 48), dtype=np.float32)]

        svc.session.run = _capture_run
        svc.upscale(img)

        arr = captured["feed"][svc.input_name]
        # Shape must be (1, 3, 8, 12)
        assert arr.shape == (1, 3, 8, 12)


# ---------------------------------------------------------------------------
# get_scale
# ---------------------------------------------------------------------------

class TestGetScale:
    def test_returns_configured_scale(self):
        svc = _make_torch_service(scale=2)
        assert svc.get_scale() == 2

    def test_default_scale_is_4(self):
        svc = _make_torch_service()
        assert svc.get_scale() == 4
