# Eyedentity — AI Iris Enhancement Platform

> Capture your iris through your camera. AI segments and upscales it 4x. Download HD.

![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)
![CI](https://github.com/pnsw123/fixed-iris-project/actions/workflows/ci.yml/badge.svg)

---

## What It Does

Point your phone camera at your eye. A 4-stage guided system checks distance, liveness (eyebrow raise), focus, and lighting before auto-capturing. The iris crop is sent to a FastAPI backend — Iris-SAM segments it, Real-ESRGAN upscales it 4x — and both the HD enhanced and original images download for free.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, TypeScript, TailwindCSS, Framer Motion |
| AI Backend | FastAPI 0.115, Python 3.12, Uvicorn |
| Iris Detection | MediaPipe Face Mesh |
| Segmentation | Iris-SAM (fine-tuned Segment Anything Model) |
| Upscaling | Real-ESRGAN x4v3 |
| Deployment | Vercel (frontend) · Render (backend) |

---

## Quick Start

### 1. Clone and install frontend

```bash
git clone https://github.com/pnsw123/fixed-iris-project.git eyedentity
cd eyedentity
npm install
```

### 2. Install backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Download AI model weights

Place these files in `backend/models/`:

| File | Source |
|---|---|
| `IrisSAM_model.pt` | Contact maintainer — not yet public |
| `sam_vit_b_01ec64.pth` | [Meta SAM releases](https://github.com/facebookresearch/segment-anything#model-checkpoints) |
| `realesr-general-x4v3.pth` | [Real-ESRGAN releases](https://github.com/xinntao/Real-ESRGAN/releases) |

```bash
bash scripts/download_models.sh   # downloads sam + esrgan automatically
```

### 4. Set up local HTTPS (required for camera API)

```bash
brew install mkcert
mkcert -install
mkdir -p .cert
mkcert -key-file .cert/localhost-key.pem -cert-file .cert/localhost.pem localhost 127.0.0.1 ::1
```

### 5. Configure environment

`.env.local` (frontend):
```env
NEXT_PUBLIC_BACKEND_URL=https://localhost:8000
```

`backend/.env`:
```env
DEVICE=mps        # mps (Apple Silicon) | cuda (NVIDIA) | cpu
LOG_LEVEL=INFO
```

### 6. Run

```bash
# Backend
cd backend && source venv/bin/activate && python app.py

# Frontend (separate terminal)
npm run dev
```

Open [https://localhost:3000](https://localhost:3000).

---

## Project Structure

```
src/                    Next.js frontend (App Router)
  app/                  Pages: instructions, capture, result
  components/           React components
  lib/                  Utilities: quality metrics, audio feedback
backend/
  api/                  Routes: process-iris, download
  services/             AI services: Iris-SAM, ESRGAN
  models/               Model weights (gitignored — download manually)
  app.py                FastAPI entry point
.cert/                  Local SSL certs (gitignored)
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Camera permission denied | Must run on HTTPS — never `http://localhost` |
| Backend crashes on startup | Model weights missing or named incorrectly in `backend/models/` |
| CORS error in browser | Add your frontend port to `CORS_ORIGINS` in `backend/.env` |
| SSL certificate not trusted | Run `mkcert -install`, regenerate certs, restart browser |

---

## License

MIT
