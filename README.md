# Eyedentity — AI Iris Enhancement

> Capture your iris with your camera. AI segments it and upscales it 4× to reveal the detail your phone blurs away.

**[Live showcase →](https://pnsw123.github.io/fixed-iris-project/)** · interactive before/after, how it works, tech.

![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)
![CI](https://github.com/pnsw123/fixed-iris-project/actions/workflows/ci.yml/badge.svg)

---

## What it does

A 4-stage guided system (distance → liveness → focus → lighting) auto-captures a sharp iris on-device with MediaPipe. The crop goes to a FastAPI service where **Iris-SAM** segments the iris and **Real-ESRGAN** upscales it 4×. Both the HD result and your original download for free — no account, no watermark.

| Layer | Stack |
|---|---|
| Front end | Next.js 16 · TypeScript · TailwindCSS · MediaPipe Face Mesh |
| AI back end | FastAPI · Python 3.12 · Iris-SAM (Segment Anything) · Real-ESRGAN x4v3 |

---

## Run it locally

**Prereqs:** Node 18+, Python 3.12+, [`mkcert`](https://github.com/FiloSottile/mkcert) (the camera API requires HTTPS, even on localhost).

```bash
# 1. Clone + install front end
git clone https://github.com/pnsw123/fixed-iris-project.git eyedentity && cd eyedentity
npm install

# 2. Back end
cd backend && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. Model weights — SAM + Real-ESRGAN download automatically
bash ../scripts/download_models.sh          # see note on IrisSAM below
cd ..

# 4. Local HTTPS certs (camera needs HTTPS)
mkcert -install
mkdir -p .cert && mkcert -key-file .cert/localhost-key.pem -cert-file .cert/localhost.pem localhost 127.0.0.1 ::1

# 5. Run both (two terminals)
cd backend && source venv/bin/activate && python app.py     # API on https://localhost:8000
npm run dev:https                                           # app on https://localhost:3005
```

Open **https://localhost:3005** → **Get Started** → guided capture → enhance → download.

Front-end env — `.env.local`:
```env
NEXT_PUBLIC_BACKEND_URL=https://localhost:8000
```
Back-end env — `backend/.env` (optional): `DEVICE=mps` (Apple Silicon) · `cuda` (NVIDIA) · `cpu`.

> **Weights:** `sam_vit_b` and `realesr-general-x4v3` are public and auto-download. `IrisSAM_model.pt` (the fine-tuned segmenter) is **not public** — request it, or set `IRIS_SAM_MODEL_URL` to a private link before step 3. Without it the backend starts but reports unhealthy at `/health` (capture still works; the enhance step needs it).

---

## How it works

```
Browser (MediaPipe guided capture)
   │  iris crop + center/radius
   ▼
FastAPI  ──►  Iris-SAM  ──►  Real-ESRGAN ×4  ──►  HD download (by token)
```

Tokens hold the HD + original images server-side (1 h TTL, memory or Redis) so the large bytes stay out of the JSON response. Per-IP rate limiting; GPU work serialised by a semaphore.

---

## Tests

```bash
cd backend && pytest        # 159 tests, mocked ML deps — no weights needed
npm test                    # front-end unit tests (Vitest)
```

---

## Deploy

- **Front end** → Vercel (`next.config` already sets the COEP/COOP headers MediaPipe needs).
- **Back end** → Render via `backend/render.yaml` (set `IRIS_SAM_MODEL_URL` + `CORS_ORIGINS`; needs ≥2 GB RAM for the models).

## License

MIT
