# Fix #39 Plan — Dead code cleanup

## Complexity: 2/10

## Files to delete
- `backend/core/__init__.py` — only file in core/, never imported, empty scaffold
- `backend/core/` — directory itself
- `test.py` — Shamela Arabic library API test, unrelated to Eyedentity

## Verification
- `rg` confirms no imports of `backend.core` or `core` anywhere in backend/
- `test.py` tests external API (shamela.ws) — zero relation to this project

## Action
1. Delete `test.py`
2. Delete `backend/core/__init__.py` + directory
3. Commit + close issue
