"""Pipeline service that orchestrates Iris-SAM and Real-ESRGAN."""

import numpy as np
from typing import Dict, Any, Optional, Tuple
import time

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
            print("[Pipeline] Stage 1: Running Iris-SAM segmentation...")
            if iris_center:
                if iris_radius:
                    print(f"[Pipeline] Using iris center prompt: ({iris_center[0]:.1f}, {iris_center[1]:.1f}), radius={iris_radius:.1f}px")
                else:
                    print(f"[Pipeline] Using iris center prompt: ({iris_center[0]:.1f}, {iris_center[1]:.1f})")
            t0 = time.time()

            mask, clean_iris, quality_score = self.iris_sam.segment_iris(
                image,
                iris_center=iris_center,
                iris_radius=iris_radius
            )

            iris_sam_time_ms = (time.time() - t0) * 1000
            print(f"[Pipeline] ✅ Iris-SAM completed in {iris_sam_time_ms:.1f}ms")

            result["metadata"]["iris_sam_time_ms"] = iris_sam_time_ms
            result["metadata"]["mask_quality_score"] = quality_score
            # Add auxiliary telemetry if present
            result["metadata"]["mask_quality_raw"] = getattr(self.iris_sam, "last_quality_raw", None)
            result["metadata"]["mask_area_ratio"] = getattr(self.iris_sam, "last_mask_area_ratio", None)
            result["metadata"]["mask_mode"] = getattr(self.iris_sam, "mask_mode", "default")

            # Optional: return mask
            if return_mask:
                result["mask"] = mask

            # Optional: return intermediate clean iris
            if return_intermediate:
                result["intermediate_iris"] = clean_iris

            # ============================================================
            # Stage 2: Upscaling with Real-ESRGAN
            # ============================================================
            print("[Pipeline] Stage 2: Running Real-ESRGAN upscaling...")
            t0 = time.time()

            upscaled = self.esrgan.upscale(clean_iris)

            esrgan_time_ms = (time.time() - t0) * 1000
            print(f"[Pipeline] ✅ Real-ESRGAN completed in {esrgan_time_ms:.1f}ms")

            result["metadata"]["esrgan_time_ms"] = esrgan_time_ms

            # ============================================================
            # Results
            # ============================================================
            upscaled_h, upscaled_w = upscaled.shape[:2]
            result["upscaled_size"] = [upscaled_h, upscaled_w]
            result["upscaled_image"] = upscaled

            total_time_ms = iris_sam_time_ms + esrgan_time_ms
            result["metadata"]["total_time_ms"] = total_time_ms

            print(f"[Pipeline] 🎉 Complete! Total time: {total_time_ms:.1f}ms")
            print(f"[Pipeline]    Input: {original_h}x{original_w}")
            print(f"[Pipeline]    Output: {upscaled_h}x{upscaled_w}")
            print(f"[Pipeline]    Quality score: {quality_score:.2f}")

            return result

        except Exception as e:
            print(f"[Pipeline] ❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()

            return {
                "success": False,
                "error": str(e),
                "metadata": {}
            }
