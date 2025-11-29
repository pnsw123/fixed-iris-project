"""FastAPI application for iris processing pipeline."""

import sys
import os

# Ensure backend directory is in Python path (ahead of site-packages)
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import numpy as np
from PIL import Image
import io
import base64
import time
from typing import Optional
import logging

from config import settings
from services.iris_sam_service import IrisSAMService
from services.esrgan_service import RealESRGANService
from services.pipeline_service import IrisPipelineService
from app_utils.image_utils import numpy_to_base64
from app_utils.validation import validate_image_upload

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Iris Processing API",
    description="Iris-SAM segmentation + Real-ESRGAN upscaling pipeline",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global service instances (loaded on startup)
iris_sam_service: Optional[IrisSAMService] = None
esrgan_service: Optional[RealESRGANService] = None
pipeline_service: Optional[IrisPipelineService] = None


@app.on_event("startup")
async def startup_event():
    """Load models on server startup."""
    global iris_sam_service, esrgan_service, pipeline_service

    logger.info("=" * 60)
    logger.info("🚀 Starting Iris Processing Backend")
    logger.info("=" * 60)

    try:
        logger.info(f"Device: {settings.device}")
        logger.info(f"Iris-SAM model: {settings.iris_sam_model}")
        logger.info(f"SAM checkpoint: {settings.sam_checkpoint}")
        logger.info(f"ESRGAN model: {settings.esrgan_model}")
        logger.info(f"Strict iris mask mode: {settings.strict_iris_mask}")

        logger.info("[Startup] Loading Iris-SAM model...")
        iris_sam_service = IrisSAMService(
            model_path=settings.iris_sam_model,
            sam_checkpoint=settings.sam_checkpoint,
            device=settings.device,
            strict_mode=settings.strict_iris_mask
        )

        logger.info("[Startup] Loading Real-ESRGAN model...")
        esrgan_service = RealESRGANService(
            model_path=settings.esrgan_model,
            device=settings.device,
            scale=4
        )

        logger.info("[Startup] Initializing pipeline...")
        pipeline_service = IrisPipelineService(iris_sam_service, esrgan_service)

        logger.info("=" * 60)
        logger.info("✅ All models loaded successfully!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Failed to load models: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "models_loaded": all([iris_sam_service, esrgan_service, pipeline_service]),
        "device": settings.device
    }


@app.post("/api/v1/process-iris")
async def process_iris(
    image: UploadFile = File(...),
    return_mask: bool = Form(False),
    return_intermediate: bool = Form(False),
    upscale_factor: int = Form(4),
    iris_x: Optional[float] = Form(None),
    iris_y: Optional[float] = Form(None),
    crop_size: Optional[float] = Form(None),
    iris_radius: Optional[float] = Form(None)
):
    """
    Main endpoint: Segment iris with Iris-SAM + upscale with Real-ESRGAN.

    Parameters:
        image: Eye crop image file (JPEG, PNG, etc.)
        return_mask: Include segmentation mask in response
        return_intermediate: Include pre-upscaled iris in response
        upscale_factor: Upscale factor (currently fixed at 4x)
        iris_x: Optional X coordinate of iris center in cropped image
        iris_y: Optional Y coordinate of iris center in cropped image
        crop_size: Optional size of the crop for validation

    Returns:
        JSON response with upscaled image and metadata
    """
    if not pipeline_service:
        logger.error("Pipeline not initialized")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Models not loaded"}
        )

    try:
        logger.info(f"📸 Processing request: {image.filename}")

        # Read and validate uploaded image
        contents = await image.read()
        img_array = validate_image_upload(contents)

        logger.info(f"   Image size: {img_array.shape}")

        # Prepare iris_center tuple if coordinates provided
        iris_center = None
        if iris_x is not None and iris_y is not None:
            iris_center = (iris_x, iris_y)
            if iris_radius is not None:
                logger.info(f"   Iris coordinates + radius provided: ({iris_x:.1f}, {iris_y:.1f}), radius={iris_radius:.1f}px")
            else:
                logger.info(f"   Iris coordinates provided: ({iris_x:.1f}, {iris_y:.1f})")
        else:
            logger.info(f"   No iris coordinates - using center fallback")

        # Process through pipeline
        t0 = time.time()
        result = pipeline_service.process(
            img_array,
            return_mask=return_mask,
            return_intermediate=return_intermediate,
            iris_center=iris_center,
            iris_radius=iris_radius
        )
        processing_time = (time.time() - t0) * 1000

        if not result.get("success"):
            logger.error(f"   Pipeline failed: {result.get('error')}")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "error": result.get("error"),
                    "detail": "Pipeline processing failed"
                }
            )

        # Convert numpy arrays to base64 data URLs
        response = {
            "success": True,
            "processing_time_ms": processing_time,
            "original_size": result["original_size"],
            "upscaled_size": result["upscaled_size"],
            "upscaled_image": numpy_to_base64(result["upscaled_image"], format='PNG'),
            "metadata": result["metadata"]
        }

        # Optional: include mask
        if return_mask and "mask" in result:
            response["mask"] = numpy_to_base64(result["mask"], format='PNG')

        # Optional: include intermediate iris
        if return_intermediate and "intermediate_iris" in result:
            response["intermediate_iris"] = numpy_to_base64(
                result["intermediate_iris"],
                format='PNG'
            )

        logger.info(
            f"   ✅ Success! "
            f"Iris-SAM: {result['metadata']['iris_sam_time_ms']:.0f}ms, "
            f"ESRGAN: {result['metadata']['esrgan_time_ms']:.0f}ms, "
            f"Quality: {result['metadata']['mask_quality_score']:.2f}"
        )

        return response

    except ValueError as e:
        logger.warning(f"   Validation error: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": str(e),
                "detail": "Invalid image or request parameters"
            }
        )

    except Exception as e:
        logger.error(f"   Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e),
                "detail": "Internal server error during processing"
            }
        )


@app.post("/api/v1/segment-iris")
async def segment_iris_only(image: UploadFile = File(...)):
    """
    Debug endpoint: Iris segmentation only (no upscaling).

    Parameters:
        image: Eye crop image file

    Returns:
        JSON response with segmentation mask and clean iris
    """
    if not iris_sam_service:
        logger.error("Iris-SAM service not initialized")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Iris-SAM not loaded"}
        )

    try:
        logger.info(f"🔍 Segmentation-only request: {image.filename}")

        contents = await image.read()
        img_array = validate_image_upload(contents)

        t0 = time.time()
        mask, clean_iris, quality_score = iris_sam_service.segment_iris(img_array)
        processing_time = (time.time() - t0) * 1000

        logger.info(
            f"   ✅ Segmentation complete in {processing_time:.1f}ms "
            f"(quality: {quality_score:.2f})"
        )

        return {
            "success": True,
            "processing_time_ms": processing_time,
            "mask": numpy_to_base64(mask, format='PNG'),
            "clean_iris": numpy_to_base64(clean_iris, format='PNG'),
            "quality_score": quality_score,
            "quality_raw": getattr(iris_sam_service, "last_quality_raw", None),
            "mask_area_ratio": getattr(iris_sam_service, "last_mask_area_ratio", None),
            "mask_mode": getattr(iris_sam_service, "mask_mode", "default")
        }

    except ValueError as e:
        logger.warning(f"   Validation error: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(e)}
        )

    except Exception as e:
        logger.error(f"   Error: {str(e)}")
        import traceback
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Iris Processing API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower()
    )
