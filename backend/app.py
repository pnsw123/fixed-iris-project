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

from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.trustedhost import TrustedHostMiddleware  # noqa: F401 (unused but kept for discoverability)
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from rate_limit import limiter
import numpy as np
from PIL import Image
import io
import base64
import time
from typing import Optional
import logging
import asyncio
from contextlib import asynccontextmanager

from config import settings


def _safe_error_msg(e: Exception) -> str:
    """Return sanitised error message for API responses.

    In production, internal exception text (which can contain model paths,
    tensor shapes, or other server internals) is replaced with a generic
    message and logged server-side only.  In development the full message is
    returned as-is for easier debugging.
    """
    if settings.env.lower() == "production":
        return "Processing failed"
    return str(e)


from services.iris_sam_service import IrisSAMService
from services.esrgan_service import RealESRGANService
from services.pipeline_service import IrisPipelineService
from services.image_store import image_store
from app_utils.image_utils import numpy_to_base64, create_preview
from app_utils.validation import validate_image_upload
from api.download_routes import router as download_router

# Configure logging
logging.basicConfig(
    level=settings.log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def _cleanup_expired_images() -> None:
    """Background task: evict expired stored images every 5 minutes."""
    while True:
        try:
            count = image_store.cleanup_expired()
            if count > 0:
                logger.info(f"[Cleanup] Removed {count} expired images")
        except Exception as e:
            logger.error(f"[Cleanup] Error: {e}")
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models on startup, run the cleanup task, tear down on shutdown.

    All synchronous torch.load / RealESRGANer calls are offloaded to a thread
    via asyncio.to_thread() so health-check routes stay responsive while
    weights load.  On failure the server keeps running with models_loaded=False
    so platform readiness probes hit /health and report unhealthy instead of
    crash-looping.
    """
    global iris_sam_service, esrgan_service, pipeline_service, models_loaded

    logger.info("=" * 60)
    logger.info("Starting Iris Processing Backend")
    logger.info("=" * 60)
    logger.info(f"Device: {settings.device}")
    logger.info(f"Iris-SAM model: {settings.iris_sam_model}")
    logger.info(f"SAM checkpoint: {settings.sam_checkpoint}")
    logger.info(f"ESRGAN model: {settings.esrgan_model}")

    def _load_models() -> tuple:
        """Synchronous model initialisation — runs in a thread pool worker."""
        logger.info("[Startup] Loading Iris-SAM model...")
        _iris = IrisSAMService(
            model_path=settings.iris_sam_model,
            sam_checkpoint=settings.sam_checkpoint,
            device=settings.device,
        )
        logger.info("[Startup] Loading Real-ESRGAN model...")
        _esrgan = RealESRGANService(
            model_path=settings.esrgan_model,
            device=settings.device,
            scale=4,
        )
        logger.info("[Startup] Initializing pipeline...")
        _pipeline = IrisPipelineService(_iris, _esrgan)
        return _iris, _esrgan, _pipeline

    try:
        iris_sam_service, esrgan_service, pipeline_service = await asyncio.to_thread(
            _load_models
        )
        models_loaded = True
        logger.info("=" * 60)
        logger.info("All models and services loaded successfully")
        logger.info("=" * 60)
    except Exception as e:
        logger.error(f"Failed to load models: {str(e)}")
        import traceback
        traceback.print_exc()
        models_loaded = False

    cleanup_task = asyncio.create_task(_cleanup_expired_images())
    logger.info("[Startup] Image cleanup task started")

    try:
        yield
    finally:
        cleanup_task.cancel()


# Initialize FastAPI app
app = FastAPI(
    title="Eyedentity API",
    description="AI iris segmentation and 4x upscaling — Iris-SAM + Real-ESRGAN",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# Trusted-proxy middleware (issue #126).
# Only enabled when TRUSTED_PROXY=true (i.e. behind Render's load balancer or
# another known single-hop proxy).  It rewrites request.client.host to the
# real client IP from X-Forwarded-For so that get_client_host() in
# rate_limit.py still sees the per-user IP rather than the LB's IP.
# Without this flag the middleware is NOT added — X-Forwarded-For is ignored
# entirely, making header-based IP spoofing impossible.
if settings.trusted_proxy:
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
    logger.info("[Security] ProxyHeadersMiddleware enabled (TRUSTED_PROXY=true)")

# Global service instances (loaded on startup)
iris_sam_service: Optional[IrisSAMService] = None
esrgan_service: Optional[RealESRGANService] = None
pipeline_service: Optional[IrisPipelineService] = None

# Set to True only after all models load successfully.
# /health returns 503 while False — lets the platform start the container and
# report unhealthy rather than crash-loop when model weights are missing.
models_loaded: bool = False

# GPU access semaphore — serialises AI pipeline (SAM + ESRGAN) per worker process.
#
# Scope: this semaphore is process-local. Each Uvicorn worker process has its own
# semaphore, so N workers allow N concurrent GPU operations. On a 4 GB VRAM GPU
# with SAM+ESRGAN requiring ~4 GB combined, WORKERS must stay at 1 to avoid OOM.
#
# For multi-worker deployments: replace with a Redis-backed distributed lock
# (e.g. redis-py Lock with blocking=True) to get true global serialisation.
GPU_SEMAPHORE = asyncio.Semaphore(1)


# Include API routers
app.include_router(download_router)


@app.get("/health")
async def health_check():
    """Health check endpoint.

    Returns 503 while models are still loading (or failed to load) so that
    platform readiness probes (Render, Railway) can distinguish between
    'container starting' and 'container crashed'.  Returns 200 once all
    models are in memory and ready to serve requests.
    """
    if not models_loaded:
        return JSONResponse(
            status_code=503,
            content={
                "status": "loading",
                "models_loaded": False,
                "device": settings.device,
            }
        )
    return {
        "status": "ok",
        "models_loaded": True,
        "device": settings.device,
    }


@app.post("/api/v1/process-iris")
@limiter.limit("5/minute")
async def process_iris(
    request: Request,
    image: UploadFile = File(...),
    return_mask: bool = Form(False),
    return_intermediate: bool = Form(False),
    iris_x: Optional[float] = Form(None),
    iris_y: Optional[float] = Form(None),
    iris_radius: Optional[float] = Form(None)
):
    """
    Main endpoint: Segment iris with Iris-SAM + upscale with Real-ESRGAN.

    The upscale factor is fixed at 4× by the loaded model architecture and
    cannot be changed per-request without reloading the model.  The
    ``upscale_factor`` and ``crop_size`` parameters have been removed from
    the API to avoid a false contract where callers could set values that
    were silently ignored.

    Parameters:
        image: Eye crop image file (JPEG, PNG, etc.)
        return_mask: Include segmentation mask in response
        return_intermediate: Include pre-upscaled iris in response
        iris_x: Optional X coordinate of iris center in cropped image
        iris_y: Optional Y coordinate of iris center in cropped image
        iris_radius: Optional radius of the iris in the cropped image

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

        # Process through pipeline (serialized via GPU semaphore)
        logger.info("   Waiting for GPU access...")
        async with GPU_SEMAPHORE:
            logger.info("   GPU acquired, processing...")
            t0 = time.time()
            result = pipeline_service.process(
                img_array,
                return_mask=return_mask,
                return_intermediate=return_intermediate,
                iris_center=iris_center,
                iris_radius=iris_radius
            )
            processing_time = (time.time() - t0) * 1000
            logger.info("   GPU released.")

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
        
        # Encode original image to bytes for bundled download
        original_byte_io = io.BytesIO()
        if len(img_array.shape) == 3 and img_array.shape[2] == 4:
            original_pil = Image.fromarray(img_array.astype(np.uint8), mode='RGBA')
        elif len(img_array.shape) == 3:
            original_pil = Image.fromarray(img_array.astype(np.uint8), mode='RGB')
        else:
            original_pil = Image.fromarray(img_array.astype(np.uint8), mode='L')
        original_pil.save(original_byte_io, format='PNG')
        original_bytes = original_byte_io.getvalue()

        # Store the HD + original images under an opaque token so the large
        # binary payload stays out of this JSON response.  The frontend fetches
        # them freely via /api/download-hd and /api/download-original.
        download_token = image_store.store(
            hd_data=hd_bytes,
            preview_data=preview_bytes,
            original_data=original_bytes,
        )

        response = {
            "success": True,
            "processing_time_ms": processing_time,
            "original_size": result["original_size"],
            "upscaled_size": result["upscaled_size"],

            # Inline preview shown immediately in the browser
            "preview_image": preview_b64,

            # Token used to download the full-resolution HD and original images
            "download_token": download_token,

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
                "error": _safe_error_msg(e),
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
            content={"success": False, "error": _safe_error_msg(e)}
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
