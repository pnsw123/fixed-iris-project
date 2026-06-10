# Fix #35: update_purchase_email query param leak

## Problem
`POST /api/update-purchase-email?token=...&email=user@example.com`
Both `token` and `email` are FastAPI query params → logged in server access logs, browser history, CDN/proxy logs, referrer headers.

## Fix
1. **Backend**: Replace `(token: str, email: str)` query params with Pydantic body model `UpdatePurchaseEmailRequest` using `EmailStr` validation.
2. **Frontend**: Change fetch call to send JSON body instead of query string.
3. **Deps**: Add `email-validator` to `requirements.txt` (required by `pydantic[email]` / `EmailStr`).

## Files changed
- `backend/api/download_routes.py` — new body model, update route signature
- `backend/requirements.txt` — add `email-validator`
- `src/components/ReviewScreen.tsx` — send JSON body, add Content-Type header

## Complexity: 2/10
