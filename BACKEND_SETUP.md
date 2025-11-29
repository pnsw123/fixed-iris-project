# Backend Setup Guide - Iris Processing Pipeline

This guide walks you through setting up the backend server for the two-stage iris processing pipeline (Iris-SAM + Real-ESRGAN).

## Overview

The backend is a Python FastAPI service that runs on your MacBook (MPS GPU) and provides:

1. **Iris-SAM Segmentation** - Uses Segment Anything Model fine-tuned for iris segmentation
2. **Real-ESRGAN Upscaling** - Upscales clean iris images 4x with Real-world Super-Resolution

## Prerequisites

- **Python 3.10+** (tested on 3.12)
- **PyTorch 2.5+** with MPS support (Apple Silicon GPU)
- **macOS 12+** (Apple Silicon)

## Setup Instructions

### Step 1: Navigate to Backend Directory

```bash
cd /Users/yazeed/backend/
```

### Step 2: Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Upgrade pip

```bash
pip install --upgrade pip setuptools wheel
```

### Step 4: Install PyTorch with MPS Support

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

### Step 5: Install Backend Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- FastAPI (web framework)
- Uvicorn (ASGI server)
- PyTorch + TorchVision
- OpenCV (image processing)
- SAM (Segment Anything Model)
- Real-ESRGAN (super-resolution)
- And other dependencies

**Note:** This may take 5-10 minutes on first install.

### Step 6: Verify Model Files

Check that all model files are in place:

```bash
ls -lh models/
```

You should see:
- `IrisSAM_model.pt` (~2.4GB) - Iris-SAM checkpoint
- `sam_vit_b_01ec64.pth` (~358MB) - SAM backbone
- `RealESRGAN_x4plus.pth` (~64MB) - Real-ESRGAN weights

### Step 7: Configure Environment (Optional)

Edit `.env` if you need to change settings:

```bash
# Device: 'mps' (Apple Silicon GPU), 'cuda' (NVIDIA), 'cpu' (fallback)
DEVICE=mps

# Server port
PORT=8000

# CORS origins (for local development)
CORS_ORIGINS=http://localhost:3005,http://localhost:3000
```

## Running the Backend

### Start the Backend Server

```bash
cd /Users/yazeed/backend/
source venv/bin/activate
python app.py
```

You should see output like:

```
============================================================
🚀 Starting Iris Processing Backend
============================================================
Device: mps
[Startup] Loading Iris-SAM model...
[IrisSAM] Initializing on device: mps
[IrisSAM] Loading SAM ViT-B backbone from ./models/sam_vit_b_01ec64.pth...
[IrisSAM] Loading Iris-SAM fine-tuned weights from ./models/IrisSAM_model.pt...
[IrisSAM] Model loaded successfully!
[Startup] Loading Real-ESRGAN model...
[RealESRGAN] Initializing on device: mps
[RealESRGAN] Loading model from ./models/RealESRGAN_x4plus.pth...
[RealESRGAN] Model loaded successfully! (scale=4x)
[Startup] Initializing pipeline...
============================================================
✅ All models loaded successfully!
============================================================
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### Test Backend Health

In a new terminal:

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "ok",
  "models_loaded": true,
  "device": "mps"
}
```

### View API Documentation

Open your browser to:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

## Running Frontend + Backend Together

### Terminal 1: Backend

```bash
cd /Users/yazeed/backend/
source venv/bin/activate
python app.py
```

### Terminal 2: Frontend

```bash
cd /Users/yazeed/
npm run dev
```

### Terminal 3: Test (Optional)

```bash
open http://localhost:3005/mobile-capture
```

## End-to-End Testing

### Test Workflow

1. **Open Frontend:** http://localhost:3005/mobile-capture
2. **Capture Iris:** Use your camera to capture an eye crop
3. **Review Screen:** You should see "Backend Ready" indicator
4. **Click Enhance:** Button should read "Enhance with Iris-SAM + Real-ESRGAN"
5. **Wait for Processing:** Progress overlay shows "Iris-SAM Segmentation + Real-ESRGAN 4x"
6. **View Result:** Upscaled iris image with processing metadata
7. **Download:** Save enhanced iris as PNG

### Expected Timing

- **Iris-SAM:** 400-600ms (on Apple Silicon MPS)
- **Real-ESRGAN:** 600-1000ms (4x upscaling)
- **Total:** 1-2 seconds end-to-end

## API Endpoints

### 1. Health Check
```http
GET /health
```

### 2. Process Iris (Main Pipeline)
```http
POST /api/v1/process-iris
Content-Type: multipart/form-data

image: File (JPEG/PNG)
return_mask: boolean (optional)
return_intermediate: boolean (optional)
```

### 3. Segment Iris Only (Debug)
```http
POST /api/v1/segment-iris
Content-Type: multipart/form-data

image: File
```

## Troubleshooting

### "Models not loaded" error

**Check:** Are all .pt and .pth files in `backend/models/`?

```bash
ls -lh backend/models/
```

If missing, move them from elsewhere:
```bash
cp /path/to/irissammodel.pt backend/models/
cp /path/to/sam_vit_b_01ec64.pth backend/models/
```

### "Backend Offline" on Frontend

**Check:** Is the backend running?

```bash
# In new terminal
curl http://localhost:8000/health

# If not running, start it:
cd backend && source venv/bin/activate && python app.py
```

### "CUDA out of memory" (if using NVIDIA GPU)

The DEVICE is set to `mps` by default. If you're seeing CUDA errors:

```bash
# Edit .env
DEVICE=cpu

# Restart backend
python app.py
```

### "ImportError: segment_anything not found"

```bash
# Reinstall dependencies
pip install -r requirements.txt

# Or manually install SAM
pip install git+https://github.com/facebookresearch/segment-anything.git
```

### Slow Performance

**Performance expectations on Apple Silicon:**
- First run loads models into memory (~5-10s)
- Subsequent runs: 1-2 seconds

**To improve:**
1. Use GPU (already using MPS by default)
2. Reduce input image size (currently supports up to 4096x4096)
3. Check Activity Monitor for RAM usage

## Model Information

### Iris-SAM
- **Source:** https://github.com/ParisaFarmanifard/Iris-SAM
- **Base Model:** Meta's Segment Anything Model (SAM)
- **Fine-tuned for:** Iris segmentation
- **Input:** Eye crop (any size)
- **Output:** Binary iris mask + quality score

### Real-ESRGAN
- **Source:** https://github.com/xinntao/Real-ESRGAN
- **Model:** RealESRGAN_x4plus
- **Scale:** 4x upscaling
- **Input:** RGB image
- **Output:** 4x upscaled RGB image

## Advanced Configuration

### Change Upscale Factor

In `backend/app.py`, modify the scale parameter:
```python
esrgan_service = RealESRGANService(
    model_path=settings.esrgan_model,
    device=settings.device,
    scale=2  # Change to 2 for 2x upscaling
)
```

### Use CPU Only

Edit `.env`:
```
DEVICE=cpu
```

No GPU required, but slower (5-10 seconds per image).

### Change CORS Origins

Edit `.env`:
```
CORS_ORIGINS=http://localhost:3005,http://localhost:3000,http://192.168.1.100:3005
```

## Deployment Notes

For production deployment:
1. Use a WSGI server (Gunicorn, uWSGI)
2. Set `RELOAD=false` in `.env`
3. Add authentication/API keys
4. Use HTTPS/SSL
5. Implement rate limiting
6. Monitor GPU/memory usage

Example production command:
```bash
gunicorn app:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## Support

If you encounter issues:

1. Check the console output for detailed error messages
2. Verify all model files exist and are not corrupted
3. Ensure Python 3.10+ is being used
4. Check available disk space (need ~3GB for models)
5. Verify GPU/device availability

## Next Steps

1. ✅ Backend setup complete
2. ✅ Frontend integration done
3. 🎯 Start both backend and frontend
4. 🎯 Capture an iris image
5. 🎯 Test the full pipeline

Enjoy your iris processing pipeline!
