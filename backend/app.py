"""FastAPI application for iris processing pipeline."""

import sys
import os
import types

# =============================================================================
# CRITICAL: Fix torchvision API compatibility BEFORE any other imports
# basicsr expects functional_tensor.rgb_to_grayscale which was removed in newer torchvision
# This shim MUST run before realesrgan/basicsr are imported anywhere
# =============================================================================
try:
    from torchvision.transforms import functional as _tv_f
    if "torchvision.transforms.functional_tensor" not in sys.modules:
        sys.modules["torchvision.transforms.functional_tensor"] = types.SimpleNamespace(
            rgb_to_grayscale=_tv_f.rgb_to_grayscale
        )
except Exception as e:
    print(f"Warning: Could not apply torchvision shim: {e}")

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
from services.purchase_service import purchase_service
from app_utils.image_utils import numpy_to_base64, create_preview
from app_utils.validation import validate_image_upload
from api.session_routes import router as session_router
from api.webhook_routes import router as webhook_router
from api.download_routes import router as download_router

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Iris Heritage Platform API",
    description="Iris-SAM segmentation + Real-ESRGAN upscaling + Heritage Card Platform",
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


# Include API routers
app.include_router(session_router)
app.include_router(webhook_router)
app.include_router(download_router)


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

        logger.info("[Startup] Loading Iris-SAM model...")
        iris_sam_service = IrisSAMService(
            model_path=settings.iris_sam_model,
            sam_checkpoint=settings.sam_checkpoint,
            device=settings.device
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
        logger.info("✅ All models and services loaded successfully!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ Failed to load models: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


import asyncio

async def cleanup_expired_purchases():
    """Background task to clean up expired purchases."""
    while True:
        try:
            count = purchase_service.cleanup_expired()
            if count > 0:
                logger.info(f"[Cleanup] Removed {count} expired purchases")
        except Exception as e:
            logger.error(f"[Cleanup] Error: {e}")
        
        await asyncio.sleep(300)  # Run every 5 minutes


@app.on_event("startup")
async def start_cleanup_task():
    """Start the purchase cleanup background task."""
    asyncio.create_task(cleanup_expired_purchases())
    logger.info("[Startup] Purchase cleanup task started")


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

        # Convert numpy arrays to base64/bytes
        full_image_arr = result["upscaled_image"]
        
        # Create preview (low res + watermark)
        preview_image_arr = create_preview(full_image_arr, max_size=360)  # 360px preview with watermark
        
        # Encode images
        preview_b64 = numpy_to_base64(preview_image_arr, format='PNG')
        
        # Encode HD image to bytes for storage (not base64)
        import io
        from PIL import Image
        
        # Convert HD numpy array to PNG bytes
        if len(full_image_arr.shape) == 3 and full_image_arr.shape[2] == 4:
            hd_pil = Image.fromarray(full_image_arr.astype(np.uint8), mode='RGBA')
        else:
            hd_pil = Image.fromarray(full_image_arr.astype(np.uint8), mode='RGB')
            
        hd_byte_io = io.BytesIO()
        hd_pil.save(hd_byte_io, format='PNG')
        hd_bytes = hd_byte_io.getvalue()
        
        # Encode preview to bytes for storage too
        preview_byte_io = io.BytesIO()
        Image.fromarray(preview_image_arr.astype(np.uint8)).save(preview_byte_io, format='PNG')
        preview_bytes = preview_byte_io.getvalue()

        # Create Pending Purchase
        # Stores HD image in memory, accessible only via token
        purchase_token = purchase_service.create_purchase(
            hd_image_data=hd_bytes,
            preview_data=preview_bytes
        )
        
        response = {
            "success": True,
            "processing_time_ms": processing_time,
            "original_size": result["original_size"],
            "upscaled_size": result["upscaled_size"],
            
            # The public preview (watermarked)
            "preview_image": preview_b64,
            
            # NO HD IMAGE HERE! 
            # Replaced with token for purchasing
            "purchase_token": purchase_token,
            
            # Removed upscaled_image to prevent free download
            # "upscaled_image": ..., 
            
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
            "quality_score": quality_score
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

    # Check for SSL certificates for HTTPS (required for phone connections)
    cert_dir = os.path.join(os.path.dirname(__file__), '..', '.cert')
    ssl_keyfile = os.path.join(cert_dir, 'key.pem')
    ssl_certfile = os.path.join(cert_dir, 'cert.pem')

    if os.path.exists(ssl_keyfile) and os.path.exists(ssl_certfile):
        print(f"🔒 Starting with HTTPS (certs from {cert_dir})")
        uvicorn.run(
            "app:app",
            host=settings.host,
            port=settings.port,
            reload=settings.reload,
            log_level=settings.log_level.lower(),
            ssl_keyfile=ssl_keyfile,
            ssl_certfile=ssl_certfile
        )
    else:
        print(f"⚠️  No SSL certs found at {cert_dir}, starting with HTTP")
        uvicorn.run(
            "app:app",
            host=settings.host,
            port=settings.port,
            reload=settings.reload,
            log_level=settings.log_level.lower()
        )
