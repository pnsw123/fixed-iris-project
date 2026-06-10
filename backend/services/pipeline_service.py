"""Pipeline service that orchestrates Iris-SAM and Real-ESRGAN."""

import logging
import numpy as np
from typing import Dict, Any, Optional, Tuple
import time

logger = logging.getLogger(__name__)

from .iris_sam_service import IrisSAMService
from .esrgan_service import RealESRGANService


class IrisPipelineService:
    """Two-stage pipeline: Iris-SAM segmentation → Real-ESRGAN upscaling."""

    def __init__(
        self,
        iris_sam: IrisSAMService,
        esrgan: RealESRGANService
    ):
        """
        Initialize pipeline with services.

        Args:
            iris_sam: IrisSAMService instance
            esrgan: RealESRGANService instance
        """
        self.iris_sam = iris_sam
        self.esrgan = esrgan

    def process(
        self,
        image: np.ndarray,
        return_mask: bool = False,
        return_intermediate: bool = False,
        iris_center: Optional[Tuple[float, float]] = None,
        iris_radius: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Full pipeline: Iris-SAM segmentation → Real-ESRGAN upscaling.

        Args:
            image: RGB numpy array (H, W, 3), values 0-255
            return_mask: Include segmentation mask in response
            return_intermediate: Include pre-upscaled clean iris in response
            iris_center: Optional (x, y) tuple of iris center in pixel coordinates

        Returns:
            Dictionary containing:
                - success: Boolean indicating success
                - upscaled_image: Final upscaled iris image
                - original_size: [height, width] of input
                - upscaled_size: [height, width] of output
                - metadata: Timing and quality information
                - mask: (optional) Binary segmentation mask
                - intermediate_iris: (optional) Clean iris before upscaling
        """
        result = {
            "success": True,
            "metadata": {}
        }

        try:
            # Validate input
            if len(image.shape) != 3 or image.shape[2] != 3:
                raise ValueError("Image must be RGB (H, W, 3)")

            original_h, original_w = image.shape[:2]
            result["original_size"] = [original_h, original_w]

            # ============================================================
            # Stage 1: Iris Segmentation with Iris-SAM
            # ============================================================
            logger.info("Stage 1: Running Iris-SAM segmentation")
            if iris_center:
                if iris_radius:
                    logger.debug("Using iris center prompt: (%.1f, %.1f), radius=%.1fpx", iris_center[0], iris_center[1], iris_radius)
                else:
                    logger.debug("Using iris center prompt: (%.1f, %.1f)", iris_center[0], iris_center[1])
            t0 = time.time()

            mask, clean_iris, quality_score = self.iris_sam.segment_iris(
                image,
                iris_center=iris_center,
                iris_radius=iris_radius
            )

            iris_sam_time_ms = (time.time() - t0) * 1000
            logger.info("Iris-SAM completed in %.1fms", iris_sam_time_ms)

            result["metadata"]["iris_sam_time_ms"] = iris_sam_time_ms
            result["metadata"]["mask_quality_score"] = quality_score

            # Optional: return mask
            if return_mask:
                result["mask"] = mask

            # Optional: return intermediate clean iris
            if return_intermediate:
                result["intermediate_iris"] = clean_iris

            # ============================================================
            # Stage 2: Upscaling with Real-ESRGAN
            # ============================================================
            logger.info("Stage 2: Running Real-ESRGAN upscaling")
            t0 = time.time()

            # Handle RGBA images (4 channels) - upscale RGB and alpha separately
            if clean_iris.shape[2] == 4:
                logger.debug("Detected RGBA image, handling alpha channel separately")
                rgb = clean_iris[:, :, :3]
                alpha = clean_iris[:, :, 3]
                
                # Upscale RGB
                upscaled_rgb = self.esrgan.upscale(rgb)
                
                # Upscale alpha channel (convert to 3-channel, upscale, take one channel)
                alpha_3ch = np.stack([alpha, alpha, alpha], axis=2)
                upscaled_alpha_3ch = self.esrgan.upscale(alpha_3ch)
                upscaled_alpha = upscaled_alpha_3ch[:, :, 0]
                
                # Combine back to RGBA
                upscaled_h, upscaled_w = upscaled_rgb.shape[:2]
                upscaled = np.zeros((upscaled_h, upscaled_w, 4), dtype=np.uint8)
                upscaled[:, :, :3] = upscaled_rgb
                upscaled[:, :, 3] = upscaled_alpha
                logger.debug("RGBA upscaling complete: %dx%d", upscaled_h, upscaled_w)
            else:
                upscaled = self.esrgan.upscale(clean_iris)

            esrgan_time_ms = (time.time() - t0) * 1000
            logger.info("Real-ESRGAN completed in %.1fms", esrgan_time_ms)

            result["metadata"]["esrgan_time_ms"] = esrgan_time_ms

            # ============================================================
            # Results
            # ============================================================
            upscaled_h, upscaled_w = upscaled.shape[:2]
            result["upscaled_size"] = [upscaled_h, upscaled_w]
            result["upscaled_image"] = upscaled

            total_time_ms = iris_sam_time_ms + esrgan_time_ms
            result["metadata"]["total_time_ms"] = total_time_ms

            logger.info(
                "Pipeline complete. Total: %.1fms | Input: %dx%d | Output: %dx%d | Quality: %.2f",
                total_time_ms, original_h, original_w, upscaled_h, upscaled_w, quality_score
            )

            return result

        except Exception as e:
            logger.error("Pipeline error: %s", e, exc_info=True)

            return {
                "success": False,
                "error": str(e),
                "metadata": {}
            }
