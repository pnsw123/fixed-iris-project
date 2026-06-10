# Fix #37 — Create backend/.env.example

## Complexity: 1/10 (FAST_PATH)

## Problem
No `.env.example` file. Secrets used by backend undocumented for deployment.

## Secrets Found (from source scan)

| Variable | File | Purpose | Required |
|---|---|---|---|
| `LEMONSQUEEZY_WEBHOOK_SECRET` | `api/webhook_routes.py` | HMAC-SHA256 webhook signature verification | YES — rejects all webhooks if missing |
| `JWT_SECRET_KEY` | `services/email_service.py` | Signs JWT download URLs (48h expiry) | YES — defaults to insecure dev value |
| `SENDGRID_API_KEY` | `services/email_service.py` | Sends download emails via SendGrid | YES — email sending fails without it |
| `BASE_URL` | `services/email_service.py` | Base URL for download links in emails | YES — defaults to localhost |
| `FROM_EMAIL` | `services/email_service.py` | Sender address for download emails | Recommended — defaults to downloads@eyedentity.com |

## Other config vars in config.py (non-secret, but useful to document)
- `HOST`, `PORT`, `WORKERS`, `RELOAD`
- `DEVICE` (mps/cuda/cpu)
- `CORS_ORIGINS`
- `LOG_LEVEL`
- Model paths: `IRIS_SAM_MODEL`, `SAM_CHECKPOINT`, `SAM_MODEL_TYPE`, `ESRGAN_MODEL`

## Action
Create `backend/.env.example` with all vars, comments explaining each, and placeholder values.
