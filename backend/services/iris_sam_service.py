"""Iris-SAM service for iris segmentation using Segment Anything Model."""

import torch
import numpy as np
from PIL import Image
import cv2
from typing import Tuple, Optional
import sys
import os

# Add iris_sam to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'iris_sam'))

from segment_anything import sam_model_registry, SamPredictor


class IrisSAMService:
    """Service for iris segmentation using Iris-SAM (SAM fine-tuned for iris)."""

    def __init__(self, model_path: str, sam_checkpoint: str, device: str = "mps"):
        """
        Initialize Iris-SAM model.

        Args:
            model_path: Path to IrisSAM_model.pt (fine-tuned weights)
            sam_checkpoint: Path to sam_vit_b_01ec64.pth (SAM backbone)
            device: 'mps' (Apple Silicon GPU), 'cuda', or 'cpu'
        """
        self.device = torch.device(device)
        print(f"[IrisSAM] Initializing on device: {device}")

        # Load Iris-SAM fine-tuned weights first so we can infer backbone size
        print(f"[IrisSAM] Loading Iris-SAM fine-tuned weights from {model_path}...")
        checkpoint = torch.load(model_path, map_location=self.device)

        # Handle different checkpoint formats
        if isinstance(checkpoint, dict) and 'model' in checkpoint:
            state_dict = checkpoint['model']
        else:
            state_dict = checkpoint

        # Infer backbone type from the fine-tuned weights if configured to auto-detect
        model_type = self._infer_model_type(state_dict)
        if sam_checkpoint and sam_checkpoint.strip():
            print(f"[IrisSAM] Using SAM backbone '{model_type}' (auto-detected from weights)")
        else:
            print(f"[IrisSAM] Using SAM backbone '{model_type}'")

        # Only use a base checkpoint if it exists and matches the inferred backbone;
        # otherwise build the model architecture and rely on the fine-tuned weights.
        use_checkpoint = None
        if sam_checkpoint and os.path.exists(sam_checkpoint):
            if model_type in sam_checkpoint:
                use_checkpoint = sam_checkpoint
            else:
                print(f"[IrisSAM] Warning: base checkpoint '{sam_checkpoint}' does not match backbone '{model_type}', skipping.")
        elif sam_checkpoint:
            print(f"[IrisSAM] Warning: base checkpoint not found at {sam_checkpoint}, proceeding without it.")

        sam = sam_model_registry[model_type](checkpoint=use_checkpoint)
        sam.to(device=self.device)

        # Load fine-tuned weights (strict=False in case some keys are missing)
        missing, unexpected = sam.load_state_dict(state_dict, strict=False)
        if missing:
            print(f"[IrisSAM] Warning: missing keys when loading fine-tuned weights: {missing}")
        if unexpected:
            print(f"[IrisSAM] Warning: unexpected keys when loading fine-tuned weights: {unexpected}")

        sam.eval()

        self.model = sam
        self.predictor = SamPredictor(sam)

        print(f"[IrisSAM] Model loaded successfully!")

    def segment_iris(
        self,
        image: np.ndarray,
        use_bounding_box: bool = True,
        iris_center: Optional[Tuple[float, float]] = None,
        iris_radius: Optional[float] = None
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """
        Segment iris from eye crop image using Iris-SAM.

        Args:
            image: RGB numpy array (H, W, 3), values 0-255
            use_bounding_box: Whether to use bounding box prompt (default True, deprecated)
            iris_center: Optional (x, y) tuple of iris center in pixel coordinates

        Returns:
            Tuple of:
                - mask: Binary mask (H, W), values 0 or 255
                - clean_iris: Masked RGB image (H, W, 3)
                - quality_score: Mask quality confidence (0-1)
        """
        # Validate input
        if len(image.shape) != 3 or image.shape[2] != 3:
            raise ValueError("Image must be RGB (H, W, 3)")

        original_h, original_w = image.shape[:2]

        try:
            with torch.no_grad():
                # Set image for the predictor
                self.predictor.set_image(image)

                # Determine point prompt coordinates
                if iris_center is not None:
                    # Validate coordinates are within image bounds
                    x, y = iris_center
                    if 0 <= x < original_w and 0 <= y < original_h:
                        # Use provided coordinates
                        iris_x, iris_y = x, y
                        prompt_type = "precise"
                    else:
                        # Invalid coordinates, fall back to center
                        iris_x, iris_y = original_w / 2, original_h / 2
                        prompt_type = "center_fallback"
                else:
                    # No coordinates provided, use image center
                    iris_x, iris_y = original_w / 2, original_h / 2
                    prompt_type = "center_default"

                # If radius provided, build a tight box prompt around the iris to prevent over-segmentation.
                box_prompt = None
                if iris_radius is not None and iris_radius > 0:
                    half_side = min(max(iris_radius * 1.2, 16), min(original_w, original_h) * 0.45)
                    x0 = max(0, iris_x - half_side)
                    y0 = max(0, iris_y - half_side)
                    x1 = min(original_w, iris_x + half_side)
                    y1 = min(original_h, iris_y + half_side)
                    box_prompt = np.array([x0, y0, x1, y1], dtype=np.float32)

                # Optimization 3: Add negative prompt to exclude eyelid
                # Positive point: iris center (foreground)
                # Negative point: above iris (background - likely eyelid)
                eyelid_offset = original_h * 0.20  # 20% above iris center
                eyelid_y = max(0, iris_y - eyelid_offset)

                point_coords = np.array([
                    [iris_x, iris_y],      # Positive: iris center
                    [iris_x, eyelid_y]     # Negative: eyelid region
                ])
                point_labels = np.array([1, 0])  # 1 = foreground, 0 = background

                # Log for debugging
                print(f"[IrisSAM] SAM prompt type: {prompt_type}")
                print(f"[IrisSAM]   Positive (iris): ({point_coords[0][0]:.1f}, {point_coords[0][1]:.1f})")
                print(f"[IrisSAM]   Negative (eyelid): ({point_coords[1][0]:.1f}, {point_coords[1][1]:.1f})")

                # Optimization 1: Enable multi-mask output (SAM generates 3 masks)
                masks, scores, logits = self.predictor.predict(
                    point_coords=point_coords,
                    point_labels=point_labels,
                    box=box_prompt,
                    multimask_output=True,  # Changed from False
                )

                # Extract the best mask
                if masks is not None and len(masks) > 0:
                    # Select best mask based on quality score
                    best_mask_idx = self._select_best_mask(masks, scores, image.shape[:2])
                    mask_pred = masks[best_mask_idx]  # Shape: (H, W)

                    print(f"[IrisSAM] Selected mask {best_mask_idx+1}/3 (score: {scores[best_mask_idx]:.3f})")

                    # Convert to binary mask (0 or 255)
                    mask = (mask_pred > 0.5).astype(np.uint8) * 255

                    # Debug: Check if mask needs inversion (iris should be white/255)
                    mask_center_value = mask[original_h // 2, original_w // 2]
                    print(f"[IrisSAM] Mask center pixel value: {mask_center_value}")

                    # If center is black (0) but we're expecting iris there, invert the mask
                    if mask_center_value == 0:
                        print(f"[IrisSAM] ⚠️  Mask appears inverted - fixing...")
                        mask = 255 - mask

                    # Refine SAM output: minimal morphology + circle fitting to SAM segmentation
                    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close, iterations=1)

                    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    if contours:
                        largest_contour = max(contours, key=cv2.contourArea)
                        (circle_x, circle_y), radius = cv2.minEnclosingCircle(largest_contour)

                        mask = np.zeros_like(mask)
                        cv2.circle(mask, (int(circle_x), int(circle_y)), int(radius), 255, -1)

                        print(f"[IrisSAM] Fitted circle from SAM mask: center=({circle_x:.1f}, {circle_y:.1f}), radius={radius:.1f}px")
                    else:
                        print("[IrisSAM] ⚠️  No contours found after SAM; using raw SAM mask without circle fitting")

                    # Step 3: Anti-aliased edge for professional smoothness
                    # Keep soft edges (no hard threshold) so upscaling blends naturally.
                    mask_soft = cv2.GaussianBlur(mask.astype(np.float32), (5, 5), 1.2)
                    mask_soft = np.clip(mask_soft, 0, 255).astype(np.uint8)

                    # Apply mask to get clean iris
                    clean_iris = self._apply_mask(image, mask_soft)

                    # Compute quality score based on circularity
                    binary_for_quality = (mask_soft > 127).astype(np.uint8) * 255
                    quality_score = self._compute_quality(binary_for_quality)

                    return mask_soft, clean_iris, quality_score
                else:
                    raise RuntimeError("SAM failed to generate masks")

        except Exception as e:
            print(f"[IrisSAM] Error during segmentation: {str(e)}")
            # Return fallback: whole image as mask
            mask = np.ones((original_h, original_w), dtype=np.uint8) * 255
            clean_iris = image.copy()
            return mask, clean_iris, 0.5

    def _select_best_mask(
        self,
        masks: np.ndarray,
        scores: np.ndarray,
        image_shape: Tuple[int, int]
    ) -> int:
        """
        Select the best mask from SAM's multi-mask output.

        Strategy:
        1. Compute circularity score for each mask
        2. Combine with SAM's confidence scores
        3. Select mask with highest combined score

        Args:
            masks: Array of masks (N, H, W)
            scores: SAM confidence scores (N,)
            image_shape: (height, width) of image

        Returns:
            Index of best mask
        """
        if len(masks) == 1:
            return 0

        best_score = -1
        best_idx = 0

        for i, (mask, sam_score) in enumerate(zip(masks, scores)):
            # Convert to binary
            binary_mask = (mask > 0.5).astype(np.uint8) * 255

            # Compute circularity
            circularity = self._compute_quality(binary_mask)

            # Compute size ratio (prefer masks that are ~5-30% of image area to avoid whole-eye masks)
            mask_area = np.sum(binary_mask > 0)
            image_area = image_shape[0] * image_shape[1]
            size_ratio = mask_area / image_area
            size_penalty = 1.0 if 0.05 <= size_ratio <= 0.30 else 0.25

            # Combined score: SAM confidence (60%) + circularity (30%) + size penalty (10%)
            combined_score = (
                sam_score * 0.6 +
                circularity * 0.3 +
                size_penalty * 0.1
            )

            print(f"[IrisSAM] Mask {i+1}: SAM={sam_score:.3f}, circ={circularity:.3f}, size={size_ratio:.2f}, combined={combined_score:.3f}")

            if combined_score > best_score:
                best_score = combined_score
                best_idx = i

        return best_idx

    def _apply_mask(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """
        Apply binary mask to image.

        Args:
            image: RGB numpy array (H, W, 3)
            mask: Binary mask (H, W), values 0-255

        Returns:
            Masked image (H, W, 3)
        """
        # Ensure mask matches image dimensions
        if mask.shape[:2] != image.shape[:2]:
            mask = cv2.resize(mask, (image.shape[1], image.shape[0]))

        # Normalize mask to 0-1
        mask_normalized = mask.astype(np.float32) / 255.0

        # Apply mask to all channels
        if len(image.shape) == 3:
            mask_3ch = np.stack([mask_normalized] * 3, axis=2)
            masked_image = (image.astype(np.float32) * mask_3ch).astype(np.uint8)
        else:
            masked_image = (image.astype(np.float32) * mask_normalized).astype(np.uint8)

        return masked_image

    def _compute_quality(self, mask: np.ndarray) -> float:
        """
        Compute mask quality score based on circularity.

        Circularity ranges from 0 to 1, where 1 is a perfect circle.
        Formula: 4π × area / perimeter²

        Args:
            mask: Binary mask (H, W), values 0-255

        Returns:
            Quality score (0-1)
        """
        try:
            # Find contours
            contours, _ = cv2.findContours(
                mask.astype(np.uint8),
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            if not contours:
                return 0.0

            # Get largest contour (iris region)
            largest_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)
            perimeter = cv2.arcLength(largest_contour, True)

            # Avoid division by zero
            if perimeter == 0 or area == 0:
                return 0.0

            # Circularity = 4π × area / perimeter²
            circularity = (4 * np.pi * area) / (perimeter ** 2)

            # Clamp to [0, 1]
            return min(max(circularity, 0.0), 1.0)

        except Exception as e:
            print(f"[IrisSAM] Error computing quality score: {str(e)}")
            return 0.5

    def _infer_model_type(self, state_dict) -> str:
        """Infer SAM backbone from fine-tuned weights, falling back to config."""
        # Respect explicit config override if provided
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

        # Default
        return "vit_b"
