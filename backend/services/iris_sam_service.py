"""Iris-SAM service for iris segmentation using Segment Anything Model."""

import logging
import torch
import numpy as np
from PIL import Image
import cv2
from typing import Tuple, Optional
import sys
import os

logger = logging.getLogger(__name__)

# Add iris_sam to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'iris_sam'))

from segment_anything import sam_model_registry, SamPredictor


class IrisSAMService:
    """Service for iris segmentation using Iris-SAM (SAM fine-tuned for iris)."""
    
    # Quality thresholds
    MIN_SAM_CONFIDENCE = 0.65  # Relaxed - we'll validate by size instead
    
    # Size thresholds - target the IRIS specifically
    # In a typical eye crop, iris is roughly 8-22% of the image
    IDEAL_SIZE_MIN = 0.06   # 6% minimum
    IDEAL_SIZE_MAX = 0.25   # 25% maximum
    IDEAL_SIZE_TARGET = 0.14  # ~14% is ideal
    
    # Absolute bounds (only reject if way outside)
    MIN_SIZE_RATIO = 0.02   # Below 2% is definitely wrong
    MAX_SIZE_RATIO = 0.45   # Above 45% is definitely wrong

    def __init__(self, model_path: str, sam_checkpoint: str, device: str = "mps"):
        """Initialize Iris-SAM model."""
        self.device = torch.device(device)
        logger.info("Initializing on device: %s", device)

        logger.info("Loading Iris-SAM fine-tuned weights from %s", model_path)
        checkpoint = torch.load(model_path, map_location=self.device)

        if isinstance(checkpoint, dict) and 'model' in checkpoint:
            state_dict = checkpoint['model']
        else:
            state_dict = checkpoint

        model_type = self._infer_model_type(state_dict)
        logger.info("Using SAM backbone '%s'", model_type)

        use_checkpoint = None
        if sam_checkpoint and os.path.exists(sam_checkpoint):
            if model_type in sam_checkpoint:
                use_checkpoint = sam_checkpoint

        sam = sam_model_registry[model_type](checkpoint=use_checkpoint)
        sam.to(device=self.device)

        missing, unexpected = sam.load_state_dict(state_dict, strict=False)
        if missing:
            logger.warning("Missing keys in state_dict: %d", len(missing))

        sam.eval()
        self.model = sam
        self.predictor = SamPredictor(sam)
        logger.info("Model loaded successfully")

    def segment_iris(
        self,
        image: np.ndarray,
        use_bounding_box: bool = True,
        iris_center: Optional[Tuple[float, float]] = None,
        iris_radius: Optional[float] = None
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """
        Segment iris from eye crop image using SAM directly.
        
        Ensures we get the IRIS (colored part) not the PUPIL (small dark center).
        """
        if len(image.shape) != 3 or image.shape[2] != 3:
            raise ValueError("Image must be RGB (H, W, 3)")

        h, w = image.shape[:2]
        
        # Determine center point for SAM prompt
        if iris_center is not None:
            cx, cy = iris_center
            if not (0 <= cx < w and 0 <= cy < h):
                cx, cy = w / 2, h / 2
        else:
            cx, cy = w / 2, h / 2

        logger.debug("Segmenting iris at (%.1f, %.1f) in %dx%d image", cx, cy, w, h)

        try:
            with torch.no_grad():
                self.predictor.set_image(image)
                
                # Get all 3 masks from SAM
                point_coords = np.array([[cx, cy]], dtype=np.float32)
                point_labels = np.array([1], dtype=np.int32)
                
                masks, scores, _ = self.predictor.predict(
                    point_coords=point_coords,
                    point_labels=point_labels,
                    multimask_output=True,
                )

                if masks is None or len(masks) == 0:
                    raise RuntimeError("SAM failed to generate masks")

                # ============================================
                # SELECT THE RIGHT MASK (iris, not pupil, not whole eye)
                # Strategy: Pick the mask closest to ideal iris size
                # ============================================
                best_mask = None
                best_score = 0
                best_area = 0
                best_size_diff = float('inf')
                
                image_area = h * w
                
                for i, (mask, score) in enumerate(zip(masks, scores)):
                    binary = (mask > 0.5).astype(np.uint8) * 255
                    
                    # Check if mask covers the center point
                    if binary[int(cy), int(cx)] == 0:
                        binary = 255 - binary
                    
                    # Find contours and get largest
                    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    if not contours:
                        continue
                    
                    largest = max(contours, key=cv2.contourArea)
                    area = cv2.contourArea(largest)
                    size_ratio = area / image_area
                    diameter = np.sqrt(4 * area / np.pi)
                    
                    logger.debug("Mask %d: size=%.1f%%, diameter=%.0fpx, score=%.3f", i + 1, size_ratio * 100, diameter, score)
                    
                    # Skip if way outside absolute bounds
                    if size_ratio < self.MIN_SIZE_RATIO:
                        logger.debug("  -> Skip: too small (pupil?)")
                        continue
                    if size_ratio > self.MAX_SIZE_RATIO:
                        logger.debug("  -> Skip: too large (whole eye?)")
                        continue
                    
                    # Calculate how close this is to ideal iris size
                    size_diff = abs(size_ratio - self.IDEAL_SIZE_TARGET)
                    
                    # Select mask closest to ideal size
                    if size_diff < best_size_diff:
                        best_size_diff = size_diff
                        best_mask = binary
                        best_area = area
                        best_score = float(score)
                        logger.debug("  -> BEST so far (closest to ideal %.0f%%)", self.IDEAL_SIZE_TARGET * 100)

                if best_mask is None:
                    raise ValueError("Could not find iris. Ensure your eye is fully visible and in focus.")

                mask = best_mask
                size_ratio = best_area / image_area
                diameter = np.sqrt(4 * best_area / np.pi)
                
                logger.debug("Selected: size=%.1f%%, diameter=%.0fpx", size_ratio * 100, diameter)

                # Find contour again for ellipse fitting
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                largest = max(contours, key=cv2.contourArea)

                # ============================================
                # CLEAN EDGES: Fit ellipse to SAM's output
                # ============================================
                if len(largest) >= 5:
                    ellipse = cv2.fitEllipse(largest)
                    (ecx, ecy), (axis1, axis2), angle = ellipse
                    
                    mask = np.zeros((h, w), dtype=np.uint8)
                    cv2.ellipse(mask, ellipse, 255, -1, cv2.LINE_AA)
                    
                    logger.debug("Fitted ellipse: center=(%.1f, %.1f), axes=(%.1f, %.1f)", ecx, ecy, axis1 / 2, axis2 / 2)
                else:
                    (ccx, ccy), radius = cv2.minEnclosingCircle(largest)
                    mask = np.zeros((h, w), dtype=np.uint8)
                    cv2.circle(mask, (int(ccx), int(ccy)), int(radius), 255, -1, cv2.LINE_AA)

                # Slight edge softening
                mask_float = mask.astype(np.float32)
                mask_soft = cv2.GaussianBlur(mask_float, (3, 3), 0.8)
                mask = np.clip(mask_soft, 0, 255).astype(np.uint8)

                # Apply mask to image - create RGBA with transparent background
                mask_norm = mask.astype(np.float32) / 255.0
                mask_3ch = np.stack([mask_norm] * 3, axis=2)
                
                # Create RGBA image (RGB from original, Alpha from mask)
                clean_iris = np.zeros((h, w, 4), dtype=np.uint8)
                clean_iris[:, :, :3] = (image.astype(np.float32) * mask_3ch).astype(np.uint8)  # RGB
                clean_iris[:, :, 3] = mask  # Alpha channel = mask

                quality_score = best_score

                logger.info("Segmentation complete (quality: %.2f, output: RGBA)", quality_score)

                return mask, clean_iris, quality_score

        except ValueError:
            raise
        except Exception as e:
            logger.error("Segmentation error: %s", e)
            raise RuntimeError(f"Segmentation failed: {e}")

    def _infer_model_type(self, state_dict) -> str:
        """Infer SAM backbone from weights."""
        from config import settings
        if settings.sam_model_type != "auto":
            return settings.sam_model_type

        pos_embed = state_dict.get("image_encoder.pos_embed")
        if pos_embed is not None and hasattr(pos_embed, "shape"):
            embed_dim = pos_embed.shape[-1]
            if embed_dim >= 1200:
                return "vit_h"
            if embed_dim >= 950:
                return "vit_l"
            return "vit_b"
        return "vit_b"
