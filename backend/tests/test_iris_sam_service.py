"""Tests for services/iris_sam_service.py — IrisSAMService.segment_iris().

Strategy:
- Bypass __init__ (no real model weights). Build instances with __new__.
- Mock self.predictor to return controlled masks / scores.
- Mock cv2.* calls to exercise mask-selection, ellipse, circle branches.
- All heavy ML packages (torch, cv2, segment_anything) stubbed by conftest.py.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rgb_image(h: int = 100, w: int = 100) -> np.ndarray:
    rng = np.random.default_rng(7)
    return rng.integers(0, 255, (h, w, 3), dtype=np.uint8)


def _make_service() -> "IrisSAMService":  # noqa: F821
    """Build an IrisSAMService without loading any model files."""
    from services.iris_sam_service import IrisSAMService

    svc = IrisSAMService.__new__(IrisSAMService)
    svc.device = MagicMock()
    svc.model = MagicMock()
    svc.predictor = MagicMock()
    return svc


def _make_mask_covering_center(h: int, w: int, cx: int, cy: int) -> np.ndarray:
    """Binary float mask (H,W) with 1.0 in a 20x20 area around (cx, cy)."""
    mask = np.zeros((h, w), dtype=np.float32)
    r = 10
    y0, y1 = max(0, cy - r), min(h, cy + r)
    x0, x1 = max(0, cx - r), min(w, cx + r)
    mask[y0:y1, x0:x1] = 1.0
    return mask


def _setup_predictor(svc, masks_f: list, scores: list):
    """Configure svc.predictor.predict to return (masks, scores, _)."""
    import numpy as np

    masks_arr = np.stack(masks_f, axis=0)  # (N, H, W)
    scores_arr = np.array(scores, dtype=np.float32)
    svc.predictor.predict.return_value = (masks_arr, scores_arr, None)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestSegmentIrisInputValidation:
    def test_raises_on_grayscale(self):
        svc = _make_service()
        gray = np.zeros((100, 100), dtype=np.uint8)
        with pytest.raises(ValueError, match="RGB"):
            svc.segment_iris(gray)

    def test_raises_on_4channel(self):
        svc = _make_service()
        rgba = np.zeros((100, 100, 4), dtype=np.uint8)
        with pytest.raises(ValueError, match="RGB"):
            svc.segment_iris(rgba)

    def test_raises_on_1channel(self):
        svc = _make_service()
        ch1 = np.zeros((100, 100, 1), dtype=np.uint8)
        with pytest.raises(ValueError, match="RGB"):
            svc.segment_iris(ch1)


# ---------------------------------------------------------------------------
# Default center behavior
# ---------------------------------------------------------------------------

class TestDefaultCenterBehavior:
    def test_uses_image_center_when_no_iris_center(self):
        """When iris_center=None, predictor called with center-of-image point."""
        import cv2

        svc = _make_service()
        h, w = 100, 100
        img = _rgb_image(h, w)

        cx, cy = w // 2, h // 2
        mask_f = _make_mask_covering_center(h, w, cx, cy)
        _setup_predictor(svc, [mask_f], [0.9])

        # Patch cv2 helpers
        binary = (mask_f > 0.5).astype(np.uint8) * 255
        fake_contour = np.zeros((10, 1, 2), dtype=np.int32)
        fake_contour[:, 0, 0] = np.linspace(cx - 5, cx + 5, 10).astype(np.int32)
        fake_contour[:, 0, 1] = np.linspace(cy - 5, cy + 5, 10).astype(np.int32)

        with patch("cv2.findContours", return_value=([fake_contour], None)), \
             patch("cv2.contourArea", return_value=float(h * w * 0.14)), \
             patch("cv2.fitEllipse", return_value=((cx, cy), (20.0, 20.0), 0.0)), \
             patch("cv2.ellipse"), \
             patch("cv2.GaussianBlur", return_value=binary.astype(np.float32)), \
             patch("numpy.zeros", side_effect=np.zeros):
            svc.segment_iris(img)

        # predictor.predict must have been called with center point
        call_args = svc.predictor.predict.call_args
        kw_coords = call_args[1].get("point_coords")
        coords = kw_coords if kw_coords is not None else call_args[0][0]
        assert coords[0][0] == pytest.approx(cx, abs=1)
        assert coords[0][1] == pytest.approx(cy, abs=1)

    def test_respects_provided_iris_center(self):
        import cv2

        svc = _make_service()
        h, w = 100, 100
        img = _rgb_image(h, w)
        custom_cx, custom_cy = 30.0, 40.0

        mask_f = _make_mask_covering_center(h, w, int(custom_cx), int(custom_cy))
        _setup_predictor(svc, [mask_f], [0.85])

        fake_contour = np.zeros((10, 1, 2), dtype=np.int32)

        with patch("cv2.findContours", return_value=([fake_contour], None)), \
             patch("cv2.contourArea", return_value=float(h * w * 0.12)), \
             patch("cv2.fitEllipse", return_value=((custom_cx, custom_cy), (18.0, 18.0), 0.0)), \
             patch("cv2.ellipse"), \
             patch("cv2.GaussianBlur", return_value=mask_f * 255):
            svc.segment_iris(img, iris_center=(custom_cx, custom_cy))

        call_args = svc.predictor.predict.call_args
        kw_coords = call_args[1].get("point_coords")
        coords = kw_coords if kw_coords is not None else call_args[0][0]
        assert coords[0][0] == pytest.approx(custom_cx, abs=1)
        assert coords[0][1] == pytest.approx(custom_cy, abs=1)

    def test_falls_back_to_center_when_iris_center_out_of_bounds(self):
        import cv2

        svc = _make_service()
        h, w = 100, 100
        img = _rgb_image(h, w)

        mask_f = _make_mask_covering_center(h, w, 50, 50)
        _setup_predictor(svc, [mask_f], [0.8])

        fake_contour = np.zeros((10, 1, 2), dtype=np.int32)

        with patch("cv2.findContours", return_value=([fake_contour], None)), \
             patch("cv2.contourArea", return_value=float(h * w * 0.12)), \
             patch("cv2.fitEllipse", return_value=((50, 50), (18.0, 18.0), 0.0)), \
             patch("cv2.ellipse"), \
             patch("cv2.GaussianBlur", return_value=mask_f * 255):
            # Out-of-bounds center → should silently fall back to image center
            svc.segment_iris(img, iris_center=(200.0, 200.0))

        call_args = svc.predictor.predict.call_args
        kw_coords = call_args[1].get("point_coords")
        coords = kw_coords if kw_coords is not None else call_args[0][0]
        # Fallback = image center
        assert coords[0][0] == pytest.approx(w / 2, abs=1)
        assert coords[0][1] == pytest.approx(h / 2, abs=1)


# ---------------------------------------------------------------------------
# Mask selection logic
# ---------------------------------------------------------------------------

class TestMaskSelection:
    def test_raises_when_all_masks_too_small(self):
        """All masks below MIN_SIZE_RATIO → ValueError with user-friendly message."""
        from services.iris_sam_service import IrisSAMService

        svc = _make_service()
        h, w = 100, 100
        img = _rgb_image(h, w)

        tiny_mask = np.zeros((h, w), dtype=np.float32)
        _setup_predictor(svc, [tiny_mask], [0.9])

        with patch("cv2.findContours", return_value=([], None)):
            with pytest.raises(ValueError, match="iris"):
                svc.segment_iris(img)

    def test_raises_when_all_masks_too_large(self):
        """All masks above MAX_SIZE_RATIO → should eventually raise."""
        svc = _make_service()
        h, w = 100, 100
        img = _rgb_image(h, w)

        # Mask covering entire image
        full_mask = np.ones((h, w), dtype=np.float32)
        _setup_predictor(svc, [full_mask], [0.9])

        fake_contour = np.zeros((10, 1, 2), dtype=np.int32)

        with patch("cv2.findContours", return_value=([fake_contour], None)), \
             patch("cv2.contourArea", return_value=float(h * w * 0.9)):  # 90% — too large
            with pytest.raises((ValueError, RuntimeError)):
                svc.segment_iris(img)

    def test_selects_mask_closest_to_ideal_size(self):
        """Among valid masks, the one closest to IDEAL_SIZE_TARGET wins.

        cv2.contourArea is called twice per mask in the loop (once inside max(),
        once explicitly) plus once after the loop for the final ellipse re-contour.
        Call sequence: [max_a, area_a, max_b, area_b, final_max].
        We return area_a for mask_a calls and area_b for mask_b calls so that
        mask_b (13%, closer to 14% ideal) wins over mask_a (8%).
        """
        from services.iris_sam_service import IrisSAMService

        svc = _make_service()
        h, w = 100, 100
        img = _rgb_image(h, w)

        image_area = h * w

        # mask_a: 8% (farther from 14%)
        # mask_b: 13% (closer to 14%) — should be selected
        cx, cy = 50, 50
        mask_a = np.zeros((h, w), dtype=np.float32)
        mask_b = np.zeros((h, w), dtype=np.float32)
        mask_a[45:55, 45:55] = 1.0  # covers center
        mask_b[43:57, 43:57] = 1.0  # covers center

        _setup_predictor(svc, [mask_a, mask_b], [0.7, 0.8])

        area_a = image_area * 0.08   # 8%
        area_b = image_area * 0.13   # 13%

        # Deterministic per-call return values matching the call order:
        # call 0: max() for mask_a → area_a
        # call 1: contourArea(largest) for mask_a → area_a
        # call 2: max() for mask_b → area_b
        # call 3: contourArea(largest) for mask_b → area_b
        # call 4: max() in final re-contour → area_b (irrelevant, reuses best)
        area_sequence = [area_a, area_a, area_b, area_b, area_b]
        area_iter = iter(area_sequence)

        fake_contour = np.zeros((10, 1, 2), dtype=np.int32)

        with patch("cv2.findContours", return_value=([fake_contour], None)), \
             patch("cv2.contourArea", side_effect=lambda _: next(area_iter)), \
             patch("cv2.fitEllipse", return_value=((cx, cy), (14.0, 14.0), 0.0)), \
             patch("cv2.ellipse"), \
             patch("cv2.GaussianBlur", return_value=np.zeros((h, w), dtype=np.float32)):
            mask_out, clean_iris, quality = svc.segment_iris(img)

        # quality score = best_score, captured from the winning mask's SAM score
        assert quality == pytest.approx(0.8, abs=0.05)

    def test_no_masks_returned_raises_runtime_error(self):
        svc = _make_service()
        img = _rgb_image(50, 50)
        svc.predictor.predict.return_value = (None, None, None)

        with pytest.raises(RuntimeError, match="[Ss]egmentation"):
            svc.segment_iris(img)

    def test_empty_masks_array_raises_runtime_error(self):
        svc = _make_service()
        img = _rgb_image(50, 50)
        svc.predictor.predict.return_value = (
            np.zeros((0, 50, 50), dtype=np.float32),
            np.array([]),
            None,
        )

        with pytest.raises(RuntimeError, match="[Ss]egmentation"):
            svc.segment_iris(img)


# ---------------------------------------------------------------------------
# Ellipse vs circle branch
# ---------------------------------------------------------------------------

class TestEllipseVsCircleBranch:
    def _run_with_contour_size(self, contour_len: int):
        """Run segment_iris with a contour of given length."""
        svc = _make_service()
        h, w = 100, 100
        img = _rgb_image(h, w)

        cx, cy = 50, 50
        mask_f = _make_mask_covering_center(h, w, cx, cy)
        _setup_predictor(svc, [mask_f], [0.85])

        fake_contour = np.zeros((contour_len, 1, 2), dtype=np.int32)
        fake_contour[:, 0, 0] = cx
        fake_contour[:, 0, 1] = cy

        image_area = h * w
        valid_area = image_area * 0.12

        # Track which branch was taken
        calls = {"ellipse": 0, "circle": 0}

        def _fake_ellipse_fit(contour):
            return ((cx, cy), (20.0, 18.0), 5.0)

        def _fake_circle(contour):
            return (cx, cy), 15.0

        with patch("cv2.findContours", return_value=([fake_contour], None)), \
             patch("cv2.contourArea", return_value=valid_area), \
             patch("cv2.fitEllipse", side_effect=lambda c: (calls.__setitem__("ellipse", calls["ellipse"] + 1) or _fake_ellipse_fit(c))), \
             patch("cv2.ellipse"), \
             patch("cv2.minEnclosingCircle", side_effect=lambda c: (calls.__setitem__("circle", calls["circle"] + 1) or _fake_circle(c))), \
             patch("cv2.circle"), \
             patch("cv2.GaussianBlur", return_value=np.zeros((h, w), dtype=np.float32)):
            svc.segment_iris(img)

        return calls

    def test_ellipse_branch_taken_when_5_or_more_contour_points(self):
        calls = self._run_with_contour_size(5)
        assert calls["ellipse"] >= 1
        assert calls["circle"] == 0

    def test_ellipse_branch_taken_when_many_contour_points(self):
        calls = self._run_with_contour_size(20)
        assert calls["ellipse"] >= 1
        assert calls["circle"] == 0

    def test_circle_branch_taken_when_fewer_than_5_contour_points(self):
        calls = self._run_with_contour_size(4)
        assert calls["circle"] >= 1
        assert calls["ellipse"] == 0

    def test_circle_branch_taken_when_3_contour_points(self):
        calls = self._run_with_contour_size(3)
        assert calls["circle"] >= 1
        assert calls["ellipse"] == 0


# ---------------------------------------------------------------------------
# Return values
# ---------------------------------------------------------------------------

class TestSegmentIrisReturnValues:
    def _run_basic(self, h: int = 80, w: int = 80):
        svc = _make_service()
        img = _rgb_image(h, w)
        cx, cy = w // 2, h // 2

        mask_f = _make_mask_covering_center(h, w, cx, cy)
        _setup_predictor(svc, [mask_f], [0.87])

        fake_contour = np.zeros((10, 1, 2), dtype=np.int32)
        image_area = h * w

        with patch("cv2.findContours", return_value=([fake_contour], None)), \
             patch("cv2.contourArea", return_value=float(image_area * 0.12)), \
             patch("cv2.fitEllipse", return_value=((cx, cy), (16.0, 14.0), 0.0)), \
             patch("cv2.ellipse"), \
             patch("cv2.GaussianBlur", return_value=np.zeros((h, w), dtype=np.float32)):
            return svc.segment_iris(img), (h, w)

    def test_returns_three_values(self):
        result, _ = self._run_basic()
        assert len(result) == 3

    def test_mask_is_2d_uint8(self):
        (mask, clean, quality), (h, w) = self._run_basic()
        assert isinstance(mask, np.ndarray)
        assert mask.ndim == 2
        assert mask.dtype == np.uint8

    def test_mask_has_correct_spatial_dimensions(self):
        (mask, clean, quality), (h, w) = self._run_basic()
        assert mask.shape == (h, w)

    def test_clean_iris_is_rgba(self):
        (mask, clean, quality), (h, w) = self._run_basic()
        assert isinstance(clean, np.ndarray)
        assert clean.ndim == 3
        assert clean.shape[2] == 4

    def test_clean_iris_spatial_matches_input(self):
        (mask, clean, quality), (h, w) = self._run_basic()
        assert clean.shape[:2] == (h, w)

    def test_quality_score_is_float(self):
        (mask, clean, quality), _ = self._run_basic()
        assert isinstance(quality, float)

    def test_quality_score_between_0_and_1(self):
        (mask, clean, quality), _ = self._run_basic()
        assert 0.0 <= quality <= 1.0


# ---------------------------------------------------------------------------
# SAM predictor call contract
# ---------------------------------------------------------------------------

class TestSAMPredictorCallContract:
    def test_set_image_called_before_predict(self):
        svc = _make_service()
        h, w = 60, 60
        img = _rgb_image(h, w)

        call_order = []

        def _set_image(image):
            call_order.append("set_image")

        def _predict(**kwargs):
            call_order.append("predict")
            mask = np.zeros((1, h, w), dtype=np.float32)
            scores = np.array([0.8], dtype=np.float32)
            return mask, scores, None

        svc.predictor.set_image = MagicMock(side_effect=_set_image)
        svc.predictor.predict = MagicMock(side_effect=_predict)

        fake_contour = np.zeros((10, 1, 2), dtype=np.int32)

        with patch("cv2.findContours", return_value=([fake_contour], None)), \
             patch("cv2.contourArea", return_value=float(h * w * 0.12)), \
             patch("cv2.fitEllipse", return_value=((30, 30), (14.0, 14.0), 0.0)), \
             patch("cv2.ellipse"), \
             patch("cv2.GaussianBlur", return_value=np.zeros((h, w), dtype=np.float32)):
            svc.segment_iris(img)

        assert call_order == ["set_image", "predict"]

    def test_predict_called_with_multimask_output_true(self):
        svc = _make_service()
        h, w = 60, 60
        img = _rgb_image(h, w)

        mask_f = _make_mask_covering_center(h, w, 30, 30)
        _setup_predictor(svc, [mask_f], [0.8])

        fake_contour = np.zeros((10, 1, 2), dtype=np.int32)

        with patch("cv2.findContours", return_value=([fake_contour], None)), \
             patch("cv2.contourArea", return_value=float(h * w * 0.12)), \
             patch("cv2.fitEllipse", return_value=((30, 30), (14.0, 14.0), 0.0)), \
             patch("cv2.ellipse"), \
             patch("cv2.GaussianBlur", return_value=np.zeros((h, w), dtype=np.float32)):
            svc.segment_iris(img)

        _, call_kwargs = svc.predictor.predict.call_args
        assert call_kwargs.get("multimask_output") is True
