# Fix #46: Add Test Infrastructure

## Goal
Add minimum viable test suite so /test-stack gate can pass.

## Files to Create
- src/tests/cn.test.ts — establishes vitest infrastructure
- src/tests/qualityMetrics.test.ts — score thresholds for SimpleMovingAverage + scoring logic
- src/tests/captureStages.test.ts — StageManager state transitions
- backend/tests/__init__.py — makes tests a package
- backend/tests/test_validation.py — validate_image_upload edge cases
- backend/tests/test_purchase_service.py — token lifecycle

## Files to Modify
- package.json — add vitest + @vitest/ui devDeps, add "test" script
- backend/requirements-dev.txt — create with pytest + httpx

## Complexity: 4/10 (well-defined, no UI)
