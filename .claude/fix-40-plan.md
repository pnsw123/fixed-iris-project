# Fix #40 Plan — README Expansion

## Complexity: 4/10
## Route: FAST_PATH (docs-only, no code)

## Files Changed
- `README.md` — full rewrite/expansion

## Changes Required

### 1. Complete env var table
Backend vars (from `backend/config.py` + service files):
| Variable | Source | Required | Default |
|---|---|---|---|
| `LEMONSQUEEZY_WEBHOOK_SECRET` | webhook_routes.py | Yes | — |
| `SENDGRID_API_KEY` | email_service.py | Yes (email) | — |
| `JWT_SECRET_KEY` | email_service.py | Yes (prod) | `dev-secret-key-change-in-production` |
| `BASE_URL` | email_service.py | No | `https://localhost:3000` |
| `FROM_EMAIL` | email_service.py | No | `downloads@eyedentity.com` |
| `DEVICE` | config.py | No | `mps` |
| `CORS_ORIGINS` | config.py | No | `[list]` |
| `LOG_LEVEL` | config.py | No | `INFO` |
| `HOST` | config.py | No | `0.0.0.0` |
| `PORT` | config.py | No | `8000` |
| `IRIS_SAM_MODEL` | config.py | No | `./models/IrisSAM_model.pt` |
| `SAM_CHECKPOINT` | config.py | No | `./models/sam_vit_b_01ec64.pth` |
| `ESRGAN_MODEL` | config.py | No | `./models/realesr-general-x4v3.pth` |

Frontend vars:
| Variable | Required | Default |
|---|---|---|
| `NEXT_PUBLIC_BACKEND_URL` | Yes | — |
| `NEXT_PUBLIC_LEMONSQUEEZY_CHECKOUT_URL` | Yes | — |

Note: `LEMONSQUEEZY_API_KEY` and `LEMONSQUEEZY_STORE_ID` referenced in old README but NOT found in any source file. Drop them.

### 2. Model weights section
Weights excluded via .gitignore (`*.pt`, `*.pth`, `*.onnx`, `backend/models/**`)
Must document:
- IrisSAM_model.pt — where to get
- sam_vit_b_01ec64.pth — where to get  
- realesr-general-x4v3.pth — where to get
- Place all in `backend/models/`

### 3. Deployment section
- Frontend → Vercel (env vars, build command)
- Backend → Docker + Railway/Render options
- SSL cert setup for local dev (mkcert)
