# Quick Start - Iris Processing Pipeline

Get the iris capture app with Iris-SAM + Real-ESRGAN running in minutes.

## ⚡ Super Quick Start (5 minutes)

### Terminal 1: Install & Run Backend

```bash
cd /Users/yazeed/backend/

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies (takes 3-5 minutes)
pip install --upgrade pip
pip install -r requirements.txt

# Run backend
python app.py
```

Wait for output showing "✅ All models loaded successfully!"

### Terminal 2: Run Frontend

```bash
cd /Users/yazeed/

# Install frontend deps (if not already done)
npm install

# Start dev server
npm run dev
```

### Terminal 3: Test

```bash
# Open browser to app
open http://localhost:3005/mobile-capture
```

## 🎯 Test the Pipeline

1. **Capture:** Click camera icon → allow camera → align iris → auto-captures
2. **Review:** Image appears in review screen
3. **Check Status:** Look for "Backend Ready" indicator (top right)
4. **Enhance:** Click "Enhance with Iris-SAM + Real-ESRGAN"
5. **Watch:** Progress overlay shows processing
6. **Result:** Upscaled iris appears with processing times
7. **Download:** Save as PNG

## 📊 What You Should See

### Backend Console
```
[Pipeline] Stage 1: Running Iris-SAM segmentation...
[Pipeline] ✅ Iris-SAM completed in 450.5ms
[Pipeline] Stage 2: Running Real-ESRGAN upscaling...
[Pipeline] ✅ Real-ESRGAN completed in 800.2ms
[Pipeline] 🎉 Complete! Total time: 1250.7ms
```

### Frontend
- **Backend Status:** Green "Wifi" icon with "Backend Ready"
- **Processing:** Shows "Processing..." with spinner
- **Result:** Upscaled iris image displayed
- **Metadata:** Shows timing breakdown and quality score

## 🛠️ Architecture

```
📱 Frontend (Next.js)              🐍 Backend (FastAPI)
┌─────────────────────┐             ┌──────────────────┐
│ Camera Capture      │             │ Iris-SAM Layer   │
│ MediaPipe Guidance  │ ────────→   │ SAM Segmentation │
│ Eye Crop Capture    │             │ Mask Generation  │
└─────────────────────┘             └──────────────────┘
                                            │
                                            ↓
                                    ┌──────────────────┐
                                    │ Real-ESRGAN      │
                                    │ 4x Upscaling     │
                                    │ GPU Accelerated  │
                                    └──────────────────┘
                                            │
                                            ↓
                                    📸 Enhanced Iris
```

## 📁 Project Structure

```
/Users/yazeed/
├── backend/                      ← New! Python backend
│   ├── app.py                   ← FastAPI server
│   ├── config.py                ← Configuration
│   ├── requirements.txt          ← Dependencies
│   ├── models/
│   │   ├── irissammodel.pt
│   │   ├── sam_vit_b_01ec64.pth
│   │   └── RealESRGAN_x4plus.pth
│   ├── iris_sam/                ← Cloned repo
│   ├── services/
│   │   ├── iris_sam_service.py
│   │   ├── esrgan_service.py
│   │   └── pipeline_service.py
│   └── utils/
│       ├── image_utils.py
│       └── validation.py
│
├── src/
│   ├── lib/
│   │   ├── backendClient.ts     ← New! Backend API client
│   │   └── [other files]
│   └── components/
│       └── ReviewScreen.tsx      ← Updated! Uses backend
│
└── [frontend files]
```

## 🔌 API Endpoints

### Health Check
```bash
curl http://localhost:8000/health
```

### Process Iris
```bash
curl -X POST http://localhost:8000/api/v1/process-iris \
  -F "image=@iris.jpg"
```

## 🚨 Common Issues

### "Backend Offline"
- Terminal 1 not running? Start it: `cd backend && source venv/bin/activate && python app.py`
- Port 8000 already in use? Kill the process: `lsof -ti:8000 | xargs kill -9`

### "Models not loaded"
- Check models exist: `ls -lh backend/models/`
- Should see 3 files: irissammodel.pt, sam_vit_b_01ec64.pth, RealESRGAN_x4plus.pth

### Slow Processing
- First run is slower (loads models into RAM)
- Subsequent runs: 1-2 seconds
- Make sure DEVICE=mps in backend/.env

### "Import Error"
- Reinstall dependencies: `pip install -r requirements.txt`

## 📚 Detailed Guides

For more information, see:
- **Backend Setup:** [BACKEND_SETUP.md](BACKEND_SETUP.md)
- **Implementation Plan:** [.claude/plans/proud-gliding-badger.md](.claude/plans/proud-gliding-badger.md)

## 🎓 Understanding the Pipeline

### Stage 1: Iris-SAM Segmentation
- Input: Eye crop image (any size)
- Process: Uses Segment Anything Model fine-tuned for iris
- Output: Binary mask indicating iris region (white = iris, black = background)
- Quality: Circularity score (0-1, where 1 is perfect circle)

### Stage 2: Real-ESRGAN Upscaling
- Input: Clean iris image (background removed by mask)
- Process: 4x upscaling using Real-world Super-Resolution GAN
- Output: 4x larger high-quality iris image
- GPU: Apple Silicon MPS acceleration

## 🎉 Next Steps

1. ✅ Models ready (already in backend/models/)
2. ✅ Backend configured (all files in place)
3. ✅ Frontend updated (ReviewScreen.tsx ready)
4. 🎯 Run the quick start above
5. 🎯 Capture an iris image
6. 🎯 Test the full pipeline

## 💡 Tips

- **First capture:** Takes 1-2 seconds (expected, models in GPU memory)
- **Subsequent captures:** Also ~1-2 seconds
- **File sizes:**
  - Original iris crop: ~50-200KB
  - Upscaled iris (4x): ~200-800KB (PNG)
- **Quality:** Iris-SAM provides mask quality score (higher is better)

## 🔧 Customization

### Change Upscale Factor
Edit `backend/app.py`, change `scale=4` to `scale=2` for 2x upscaling.

### Use CPU Instead of GPU
Edit `backend/.env`, change `DEVICE=mps` to `DEVICE=cpu`.

### Change Server Port
Edit `backend/.env`, change `PORT=8000` to your preferred port.

---

**Enjoy your iris processing pipeline!** 🌈👁️

For issues or questions, refer to [BACKEND_SETUP.md](BACKEND_SETUP.md).
