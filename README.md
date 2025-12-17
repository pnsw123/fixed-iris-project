# 👁️ Eyedentity - AI Iris Enhancement Platform

Transform your iris into stunning, high-resolution art using AI-powered segmentation and upscaling.

## ✨ Features

- **Real-time Iris Detection** - MediaPipe-powered eye tracking with quality guidance
- **AI Segmentation** - Iris-SAM (Segment Anything Model fine-tuned for iris)
- **4x AI Upscaling** - Real-ESRGAN for crystal-clear enhancement
- **Mobile-First UX** - Optimized for phone cameras with auto-capture
- **Payment Integration** - Lemon Squeezy for HD image purchases

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | Next.js 14, TypeScript, TailwindCSS |
| Backend | FastAPI, Python 3.12 |
| AI Models | Iris-SAM, Real-ESRGAN |
| Detection | MediaPipe Face Mesh |
| Payments | Lemon Squeezy |

## 🚀 Quick Start

### Prerequisites
- Node.js 18+
- Python 3.12+
- GPU recommended (MPS/CUDA)

### Frontend
```bash
npm install
npm run dev
```
Open [https://localhost:3000](https://localhost:3000)

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```
API runs on [https://localhost:8000](https://localhost:8000)

## 📁 Project Structure

```
├── src/                    # Next.js frontend
│   ├── app/               # Pages (instructions, capture, result)
│   ├── components/        # React components
│   └── lib/               # Utilities (quality metrics, audio)
├── backend/               # FastAPI backend
│   ├── api/              # API routes (webhooks, downloads)
│   ├── services/         # AI services (Iris-SAM, ESRGAN)
│   └── models/           # AI model weights
└── .cert/                 # SSL certificates for HTTPS
```

## 🔧 Environment Variables

Create `.env` in project root:
```env
# Lemon Squeezy Payment
LEMONSQUEEZY_API_KEY=your_api_key
LEMONSQUEEZY_STORE_ID=your_store_id
LEMONSQUEEZY_WEBHOOK_SECRET=your_webhook_secret
```

## 📱 User Flow

1. **Instructions** → Learn how to position eye
2. **Capture** → AI guides positioning, auto-captures when ready
3. **Enhance** → Iris-SAM segments, ESRGAN upscales 4x
4. **Download** → Preview (360p watermarked) or HD ($2.99)

## 🔒 Security

- GPU semaphore prevents concurrent request OOM
- Thread-safe purchase storage
- HMAC webhook signature verification
- HTTPS-only with SSL certificates

## 📄 License

Private repository - All rights reserved.
