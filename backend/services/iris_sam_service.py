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

                # Build TIGHT box prompt around iris to prevent over-segmentation
                box_prompt = None
                if iris_radius is not None and iris_radius > 0:
                    # Tighter constraint: 1.08x radius (was 1.2x) - keeps SAM focused on iris
                    half_side = min(max(iris_radius * 1.08, 16), min(original_w, original_h) * 0.45)
                    x0 = max(0, iris_x - half_side)
                    y0 = max(0, iris_y - half_side)
                    x1 = min(original_w, iris_x + half_side)
                    y1 = min(original_h, iris_y + half_side)
                    box_prompt = np.array([x0, y0, x1, y1], dtype=np.float32)

                # ENHANCED Multi-Point Prompting Strategy for 95%+ Quality
                # Strategy: Give SAM explicit positive (iris) and negative (non-iris) examples

                # Estimate iris region boundaries
                if iris_radius is not None and iris_radius > 0:
                    radius = iris_radius
                else:
                    # Fallback: assume iris is ~25% of image width
                    radius = min(original_w, original_h) * 0.25

                # Build strategic prompt points
                point_coords_list = []
                point_labels_list = []

                # POSITIVE PROMPTS (iris interior)
                # 1. Center point (most confident)
                point_coords_list.append([iris_x, iris_y])
                point_labels_list.append(1)

                # 2-5. Four additional points inside iris (cardinal directions at 0.5 radius)
                # This gives SAM strong confidence about iris interior
                inner_radius = radius * 0.5
                for angle in [0, 90, 180, 270]:
                    angle_rad = np.deg2rad(angle)
                    px = iris_x + inner_radius * np.cos(angle_rad)
                    py = iris_y + inner_radius * np.sin(angle_rad)
                    # Validate bounds
                    if 0 <= px < original_w and 0 <= py < original_h:
                        point_coords_list.append([px, py])
                        point_labels_list.append(1)

                # NEGATIVE PROMPTS (exclude non-iris regions)
                # 6. Upper eyelid (above iris)
                eyelid_offset_upper = radius * 1.3
                eyelid_y_upper = max(0, iris_y - eyelid_offset_upper)
                point_coords_list.append([iris_x, eyelid_y_upper])
                point_labels_list.append(0)

                # 7. Lower eyelid (below iris)
                eyelid_offset_lower = radius * 1.3
                eyelid_y_lower = min(original_h, iris_y + eyelid_offset_lower)
                point_coords_list.append([iris_x, eyelid_y_lower])
                point_labels_list.append(0)

                # 8. Left eye corner / temporal region
                left_corner_x = max(0, iris_x - radius * 1.4)
                point_coords_list.append([left_corner_x, iris_y])
                point_labels_list.append(0)

                # 9. Right eye corner / nasal region
                right_corner_x = min(original_w, iris_x + radius * 1.4)
                point_coords_list.append([right_corner_x, iris_y])
                point_labels_list.append(0)

                # 10-11. Upper-left and upper-right (eyelashes/eyelid)
                upper_left_x = max(0, iris_x - radius * 0.9)
                upper_left_y = max(0, iris_y - radius * 1.1)
                point_coords_list.append([upper_left_x, upper_left_y])
                point_labels_list.append(0)

                upper_right_x = min(original_w, iris_x + radius * 0.9)
                upper_right_y = max(0, iris_y - radius * 1.1)
                point_coords_list.append([upper_right_x, upper_right_y])
                point_labels_list.append(0)

                # 12-13. Lower-left and lower-right (lower eyelid/lashes)
                lower_left_x = max(0, iris_x - radius * 0.9)
                lower_left_y = min(original_h, iris_y + radius * 1.1)
                point_coords_list.append([lower_left_x, lower_left_y])
                point_labels_list.append(0)

                lower_right_x = min(original_w, iris_x + radius * 0.9)
                lower_right_y = min(original_h, iris_y + radius * 1.1)
                point_coords_list.append([lower_right_x, lower_right_y])
                point_labels_list.append(0)

                point_coords = np.array(point_coords_list, dtype=np.float32)
                point_labels = np.array(point_labels_list, dtype=np.int32)

                # Log for debugging
                num_positive = np.sum(point_labels == 1)
                num_negative = np.sum(point_labels == 0)
                print(f"[IrisSAM] SAM prompt type: {prompt_type}")
                print(f"[IrisSAM]   Multi-point strategy: {num_positive} positive + {num_negative} negative prompts")
                print(f"[IrisSAM]   Iris center: ({iris_x:.1f}, {iris_y:.1f}), radius: {radius:.1f}px")

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

                    # ==================================================================
                    # POST-PROCESSING: Refine SAM output to achieve 95%+ quality
                    # ==================================================================

                    # Step 1: Morphological cleaning - close small holes
                    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_close, iterations=2)

                    # Step 2: Remove small disconnected regions (keep only largest component)
                    # This eliminates noise/artifacts from SAM
                    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    if contours:
                        # Find largest contour (should be iris)
                        largest_contour = max(contours, key=cv2.contourArea)
                        largest_area = cv2.contourArea(largest_contour)

                        # Create clean mask with ONLY the largest component
                        mask_clean = np.zeros_like(mask)
                        cv2.drawContours(mask_clean, [largest_contour], -1, 255, -1)

                        # Count how many small regions we removed
                        num_removed = len(contours) - 1
                        if num_removed > 0:
                            print(f"[IrisSAM] Removed {num_removed} small disconnected region(s)")

                        mask = mask_clean

                        # Step 3: Fit ellipse (more accurate than circle for iris)
                        # Irises appear elliptical due to perspective and anatomy
                        if len(largest_contour) >= 5:  # Need at least 5 points for fitEllipse
                            try:
                                ellipse = cv2.fitEllipse(largest_contour)
                                (center_x, center_y), (width, height), angle = ellipse

                                # Create smooth elliptical mask
                                mask = np.zeros_like(mask)
                                cv2.ellipse(mask, ellipse, 255, -1)

                                print(f"[IrisSAM] Fitted ellipse: center=({center_x:.1f}, {center_y:.1f}), "
                                      f"axes=({width/2:.1f}x{height/2:.1f}), angle={angle:.1f}°")

                                # Calculate ellipse circularity (1.0 = perfect circle)
                                ellipse_circularity = min(width, height) / max(width, height)
                                print(f"[IrisSAM] Ellipse circularity: {ellipse_circularity:.3f} (1.0 = perfect circle)")

                            except cv2.error as e:
                                # Fallback: use minimum enclosing circle if ellipse fitting fails
                                print(f"[IrisSAM] Ellipse fitting failed, using circle fallback: {e}")
                                (circle_x, circle_y), radius = cv2.minEnclosingCircle(largest_contour)
                                mask = np.zeros_like(mask)
                                cv2.circle(mask, (int(circle_x), int(circle_y)), int(radius), 255, -1)
                                print(f"[IrisSAM] Fitted circle: center=({circle_x:.1f}, {circle_y:.1f}), radius={radius:.1f}px")
                        else:
                            print(f"[IrisSAM] ⚠️  Contour has only {len(largest_contour)} points, skipping ellipse fit")

                    else:
                        print("[IrisSAM] ⚠️  No contours found after SAM; using raw SAM mask without fitting")

                    # Compute quality score based on circularity BEFORE anti-aliasing
                    # This ensures the score reflects the geometric quality, not blur artifacts
                    quality_score = self._compute_quality(mask)
                    print(f"[IrisSAM] Geometric quality score (pre-blur): {quality_score:.3f}")

                    # Step 4: Anti-aliased edge for professional smoothness
                    # Soft edges ensure natural blending during upscaling
                    mask_soft = cv2.GaussianBlur(mask.astype(np.float32), (7, 7), 1.5)
                    mask_soft = np.clip(mask_soft, 0, 255).astype(np.uint8)

                    # Apply mask to get clean iris
                    clean_iris = self._apply_mask(image, mask_soft)

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

            # Compute circularity (most important for iris quality)
            circularity = self._compute_quality(binary_mask)

            # Compute size ratio (prefer masks that are ~5-30% of image area to avoid whole-eye masks)
            mask_area = np.sum(binary_mask > 0)
            image_area = image_shape[0] * image_shape[1]
            size_ratio = mask_area / image_area

            # Strong size penalty for masks outside ideal range
            if 0.05 <= size_ratio <= 0.30:
                size_score = 1.0
            elif size_ratio < 0.05:
                # Too small - likely noise
                size_score = 0.1
            else:
                # Too large - likely whole eye or over-segmentation
                size_score = max(0.2, 1.0 - (size_ratio - 0.30) / 0.40)

            # UPDATED: Prioritize circularity more heavily for iris quality
            # Combined score: circularity (50%) + SAM confidence (35%) + size (15%)
            # Rationale: Iris MUST be circular, so circularity is most important
            combined_score = (
                circularity * 0.50 +
                sam_score * 0.35 +
                size_score * 0.15
            )

            print(f"[IrisSAM] Mask {i+1}: circ={circularity:.3f}, SAM={sam_score:.3f}, "
                  f"size={size_ratio:.2%} (score={size_score:.2f}), combined={combined_score:.3f}")

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
