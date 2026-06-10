"""Tests for services/pipeline_service.py — IrisPipelineService.process().

Strategy:
- iris_sam and esrgan are injected as MagicMocks (real __init__ never called).
- Covers: happy path, mask/intermediate optionals, RGBA branch, error handling,
  metadata keys, original/upscaled size recording.
- numpy is NOT mocked — real arrays flow through to test shape/dtype contracts.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rgb_image(h: int = 64, w: int = 64) -> np.ndarray:
    rng = np.random.default_rng(99)
    return rng.integers(0, 255, (h, w, 3), dtype=np.uint8)


def _rgba_image(h: int = 64, w: int = 64) -> np.ndarray:
    rng = np.random.default_rng(99)
    return rng.integers(0, 255, (h, w, 4), dtype=np.uint8)


def _upscaled(h: int = 256, w: int = 256) -> np.ndarray:
    rng = np.random.default_rng(1)
    return rng.integers(0, 255, (h, w, 3), dtype=np.uint8)


def _make_pipeline(
    clean_iris_channels: int = 4,
    in_h: int = 64,
    in_w: int = 64,
    out_h: int = 256,
    out_w: int = 256,
    quality: float = 0.88,
):
    """Build IrisPipelineService with fully mocked dependencies."""
    from services.pipeline_service import IrisPipelineService

    mock_mask = np.zeros((in_h, in_w), dtype=np.uint8)
    mock_mask[20:40, 20:40] = 255

    if clean_iris_channels == 4:
        mock_clean = _rgba_image(in_h, in_w)
    else:
        mock_clean = _rgb_image(in_h, in_w)

    iris_sam = MagicMock()
    iris_sam.segment_iris.return_value = (mock_mask, mock_clean, quality)

    esrgan = MagicMock()
    esrgan.upscale.return_value = _upscaled(out_h, out_w)

    pipeline = IrisPipelineService(iris_sam=iris_sam, esrgan=esrgan)
    return pipeline, iris_sam, esrgan, mock_mask, mock_clean


# ---------------------------------------------------------------------------
# Happy-path
# ---------------------------------------------------------------------------

class TestProcessHappyPath:
    def test_returns_dict(self):
        pipeline, _, _, _, _ = _make_pipeline()
        result = pipeline.process(_rgb_image())
        assert isinstance(result, dict)

    def test_success_is_true(self):
        pipeline, _, _, _, _ = _make_pipeline()
        result = pipeline.process(_rgb_image())
        assert result["success"] is True

    def test_contains_upscaled_image(self):
        pipeline, _, _, _, _ = _make_pipeline()
        result = pipeline.process(_rgb_image())
        assert "upscaled_image" in result
        assert isinstance(result["upscaled_image"], np.ndarray)

    def test_upscaled_image_has_4_channels_when_clean_iris_is_rgba(self):
        # Default pipeline returns RGBA clean_iris → RGBA output
        pipeline, _, _, _, _ = _make_pipeline(clean_iris_channels=4)
        result = pipeline.process(_rgb_image())
        assert result["upscaled_image"].shape[2] == 4

    def test_upscaled_image_has_3_channels_when_clean_iris_is_rgb(self):
        pipeline, _, _, _, _ = _make_pipeline(clean_iris_channels=3)
        result = pipeline.process(_rgb_image())
        assert result["upscaled_image"].shape[2] == 3

    def test_original_size_recorded(self):
        h, w = 80, 120
        pipeline, _, _, _, _ = _make_pipeline(in_h=h, in_w=w)
        result = pipeline.process(_rgb_image(h, w))
        assert result["original_size"] == [h, w]

    def test_upscaled_size_recorded(self):
        out_h, out_w = 320, 480
        pipeline, _, _, _, _ = _make_pipeline(out_h=out_h, out_w=out_w)
        result = pipeline.process(_rgb_image())
        assert result["upscaled_size"] == [out_h, out_w]

    def test_metadata_contains_iris_sam_time_ms(self):
        pipeline, _, _, _, _ = _make_pipeline()
        result = pipeline.process(_rgb_image())
        assert "iris_sam_time_ms" in result["metadata"]

    def test_metadata_contains_esrgan_time_ms(self):
        pipeline, _, _, _, _ = _make_pipeline()
        result = pipeline.process(_rgb_image())
        assert "esrgan_time_ms" in result["metadata"]

    def test_metadata_contains_total_time_ms(self):
        pipeline, _, _, _, _ = _make_pipeline()
        result = pipeline.process(_rgb_image())
        assert "total_time_ms" in result["metadata"]

    def test_total_time_is_sum_of_stage_times(self):
        pipeline, _, _, _, _ = _make_pipeline()
        result = pipeline.process(_rgb_image())
        meta = result["metadata"]
        expected = meta["iris_sam_time_ms"] + meta["esrgan_time_ms"]
        assert meta["total_time_ms"] == pytest.approx(expected, abs=1.0)

    def test_metadata_contains_mask_quality_score(self):
        pipeline, _, _, _, _ = _make_pipeline(quality=0.77)
        result = pipeline.process(_rgb_image())
        assert result["metadata"]["mask_quality_score"] == pytest.approx(0.77, abs=0.01)


# ---------------------------------------------------------------------------
# Optional return flags
# ---------------------------------------------------------------------------

class TestReturnMaskFlag:
    def test_mask_absent_by_default(self):
        pipeline, _, _, _, _ = _make_pipeline()
        result = pipeline.process(_rgb_image())
        assert "mask" not in result

    def test_mask_present_when_flag_true(self):
        pipeline, _, _, mask, _ = _make_pipeline()
        result = pipeline.process(_rgb_image(), return_mask=True)
        assert "mask" in result
        np.testing.assert_array_equal(result["mask"], mask)

    def test_mask_is_ndarray(self):
        pipeline, _, _, _, _ = _make_pipeline()
        result = pipeline.process(_rgb_image(), return_mask=True)
        assert isinstance(result["mask"], np.ndarray)


class TestReturnIntermediateFlag:
    def test_intermediate_absent_by_default(self):
        pipeline, _, _, _, _ = _make_pipeline()
        result = pipeline.process(_rgb_image())
        assert "intermediate_iris" not in result

    def test_intermediate_present_when_flag_true(self):
        pipeline, _, _, _, clean = _make_pipeline()
        result = pipeline.process(_rgb_image(), return_intermediate=True)
        assert "intermediate_iris" in result
        np.testing.assert_array_equal(result["intermediate_iris"], clean)

    def test_intermediate_is_ndarray(self):
        pipeline, _, _, _, _ = _make_pipeline()
        result = pipeline.process(_rgb_image(), return_intermediate=True)
        assert isinstance(result["intermediate_iris"], np.ndarray)

    def test_both_flags_true_simultaneously(self):
        pipeline, _, _, _, _ = _make_pipeline()
        result = pipeline.process(_rgb_image(), return_mask=True, return_intermediate=True)
        assert "mask" in result
        assert "intermediate_iris" in result


# ---------------------------------------------------------------------------
# RGBA branch (clean_iris has 4 channels)
# ---------------------------------------------------------------------------

class TestRGBABranch:
    def test_rgba_clean_iris_triggers_two_upscale_calls(self):
        """RGBA path must upscale RGB and alpha separately → 2 calls."""
        pipeline, _, esrgan, _, _ = _make_pipeline(clean_iris_channels=4)
        pipeline.process(_rgb_image())
        assert esrgan.upscale.call_count == 2

    def test_rgba_output_has_4_channels(self):
        """RGBA input → output must also be RGBA (4 channels)."""
        pipeline, _, esrgan, _, _ = _make_pipeline(clean_iris_channels=4)
        # Both RGB and alpha upscale return (256, 256, 3) arrays
        esrgan.upscale.return_value = _upscaled(256, 256)
        result = pipeline.process(_rgb_image())
        assert result["upscaled_image"].shape[2] == 4

    def test_rgb_clean_iris_triggers_one_upscale_call(self):
        """Non-RGBA clean iris → single upscale call."""
        pipeline, _, esrgan, _, _ = _make_pipeline(clean_iris_channels=3)
        pipeline.process(_rgb_image())
        assert esrgan.upscale.call_count == 1

    def test_rgba_alpha_channel_is_uint8(self):
        pipeline, _, esrgan, _, _ = _make_pipeline(clean_iris_channels=4)
        esrgan.upscale.return_value = _upscaled(256, 256)
        result = pipeline.process(_rgb_image())
        alpha = result["upscaled_image"][:, :, 3]
        assert alpha.dtype == np.uint8

    def test_rgba_rgb_channels_sourced_from_esrgan(self):
        """RGB channels of RGBA output must come from esrgan.upscale (first call)."""
        h_out, w_out = 128, 128
        pipeline, _, esrgan, _, _ = _make_pipeline(clean_iris_channels=4,
                                                   out_h=h_out, out_w=w_out)

        sentinel_rgb = np.full((h_out, w_out, 3), 42, dtype=np.uint8)
        esrgan.upscale.return_value = sentinel_rgb  # both calls return same for simplicity

        result = pipeline.process(_rgb_image())
        np.testing.assert_array_equal(result["upscaled_image"][:, :, :3], sentinel_rgb)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_non_3channel_image_returns_failure(self):
        pipeline, _, _, _, _ = _make_pipeline()
        gray = np.zeros((64, 64), dtype=np.uint8)
        result = pipeline.process(gray)
        assert result["success"] is False

    def test_failure_result_contains_error_key(self):
        pipeline, _, _, _, _ = _make_pipeline()
        gray = np.zeros((64, 64), dtype=np.uint8)
        result = pipeline.process(gray)
        assert "error" in result

    def test_single_channel_3d_image_fails(self):
        pipeline, _, _, _, _ = _make_pipeline()
        ch1 = np.zeros((64, 64, 1), dtype=np.uint8)
        result = pipeline.process(ch1)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_iris_sam_exception_returns_failure(self):
        from services.pipeline_service import IrisPipelineService

        iris_sam = MagicMock()
        iris_sam.segment_iris.side_effect = RuntimeError("SAM crashed")
        esrgan = MagicMock()

        pipeline = IrisPipelineService(iris_sam=iris_sam, esrgan=esrgan)
        result = pipeline.process(_rgb_image())

        assert result["success"] is False
        assert "SAM crashed" in result["error"]

    def test_esrgan_exception_returns_failure(self):
        from services.pipeline_service import IrisPipelineService

        mask = np.zeros((64, 64), dtype=np.uint8)
        clean = _rgba_image(64, 64)

        iris_sam = MagicMock()
        iris_sam.segment_iris.return_value = (mask, clean, 0.9)

        esrgan = MagicMock()
        esrgan.upscale.side_effect = RuntimeError("ESRGAN OOM")

        pipeline = IrisPipelineService(iris_sam=iris_sam, esrgan=esrgan)
        result = pipeline.process(_rgb_image())

        assert result["success"] is False

    def test_failure_result_has_empty_metadata(self):
        from services.pipeline_service import IrisPipelineService

        iris_sam = MagicMock()
        iris_sam.segment_iris.side_effect = ValueError("bad input")
        esrgan = MagicMock()

        pipeline = IrisPipelineService(iris_sam=iris_sam, esrgan=esrgan)
        result = pipeline.process(_rgb_image())

        assert result["success"] is False
        assert isinstance(result["metadata"], dict)

    def test_failure_does_not_raise(self):
        from services.pipeline_service import IrisPipelineService

        iris_sam = MagicMock()
        iris_sam.segment_iris.side_effect = Exception("unknown")
        esrgan = MagicMock()

        pipeline = IrisPipelineService(iris_sam=iris_sam, esrgan=esrgan)
        # Must not propagate exception
        try:
            result = pipeline.process(_rgb_image())
        except Exception as exc:
            pytest.fail(f"process() raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# iris_center / iris_radius forwarding
# ---------------------------------------------------------------------------

class TestIrisCenterForwarding:
    def test_iris_center_forwarded_to_segment_iris(self):
        pipeline, iris_sam, _, _, _ = _make_pipeline()
        center = (30.5, 45.0)
        pipeline.process(_rgb_image(), iris_center=center)

        call_kwargs = iris_sam.segment_iris.call_args[1]
        assert call_kwargs.get("iris_center") == center

    def test_iris_radius_forwarded_to_segment_iris(self):
        pipeline, iris_sam, _, _, _ = _make_pipeline()
        pipeline.process(_rgb_image(), iris_center=(30.0, 40.0), iris_radius=12.5)

        call_kwargs = iris_sam.segment_iris.call_args[1]
        assert call_kwargs.get("iris_radius") == pytest.approx(12.5)

    def test_none_iris_center_forwarded_as_none(self):
        pipeline, iris_sam, _, _, _ = _make_pipeline()
        pipeline.process(_rgb_image(), iris_center=None)

        call_kwargs = iris_sam.segment_iris.call_args[1]
        assert call_kwargs.get("iris_center") is None

    def test_segment_iris_called_exactly_once(self):
        pipeline, iris_sam, _, _, _ = _make_pipeline()
        pipeline.process(_rgb_image())
        iris_sam.segment_iris.assert_called_once()
