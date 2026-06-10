# Capture Stages — Guided Iris Acquisition State Machine

Source of truth: [`src/lib/captureStages.ts`](../../src/lib/captureStages.ts)

---

## Overview

The iris capture flow is a **linear 4-stage state machine**. The user must satisfy
each gate in order before the shutter fires. Stages advance forward only; regression
is limited to `returnToStage()` calls during the final countdown if quality drops.

```
distance  ──►  eyebrows  ──►  final_checks  ──►  ready
  (1/4)          (2/4)           (3/4)            (4/4)
```

---

## Stages

### Stage 1 — `distance`

**Goal:** Ensure the iris fills enough of the frame to yield sufficient texture
detail for AI segmentation, without being so close that eyelid occlusion or barrel
distortion corrupts the image.

| Threshold | Value | Pixel range |
|-----------|-------|-------------|
| Too far (min) | < 8 % of 1080 px reference height | < 86 px at 1080p, < 58 px at 720p |
| Sweet spot | 8 – 12 % | 86 – 130 px at 1080p |
| Too close (max) | > 12 % | > 130 px at 1080p |

**Stability window:** 800 ms of continuous in-range frames required before advancing.
Hysteresis of ±2 % applied once the timer starts, so micro-movements near the edge
of the band don't reset the clock.

**UI messages:**

| Condition | Message shown |
|-----------|---------------|
| Diameter < min | "Move Closer" |
| Diameter > max | "Move Back" |
| In range | "Perfect Distance" |

---

### Stage 2 — `eyebrows`

**Goal:** Liveness check. A printed photo or replay attack cannot raise eyebrows.
Requiring a sustained raise eliminates a single surprised blink as a false positive.

**Inner state machine:**

```
not_raised  ──►  raised  ──►  confirmed
                    │
                    └─ (isRaised drops) ──► not_raised (counter resets)
```

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Sustained frames | 30 | ~2 s at 15 fps inference; ~1 s at 30 fps |
| Displacement threshold | −15 px | Negative Y = raised in canvas coords; supplied by qualityMetrics |

Once `confirmed`, the stage is **irreversible** — even if the user lowers their
eyebrows the check does not regress. This prevents frustrating re-prompts after the
liveness gate has already been satisfied.

**UI messages:**

| State | Message shown |
|-------|---------------|
| not_raised | "Raise Your Eyebrows" |
| raised (< 50 % of frames) | "Hold Them Raised..." |
| raised (≥ 50 % of frames) | "Good! Keep Going" |
| confirmed | "Good! Keep Going" |

---

### Stage 3 — `final_checks`

**Goal:** Guarantee centering, sharpness, and lighting all pass simultaneously for
long enough to rule out coincidental single-frame agreement.

All three conditions must hold at the same time. Any single failure resets the 800 ms
clock.

| Metric | Pass threshold | Notes |
|--------|---------------|-------|
| Centering | centeringRatio ≤ 0.30 | Iris centre ≤ 30 % of the half-short-side from frame centre |
| Sharpness | Laplacian variance ≥ 8 | Lenient floor — hard focus gate lives in `qualityMetrics.ts` |
| Brightness (min) | luma ≥ 60 / 255 | Below this: too dark for reliable feature matching |
| Brightness (max) | luma ≤ 200 / 255 | Above this: blown highlights wash out iris texture |

**Stability window:** 800 ms.

**Hysteresis:** ±5 % on centering, ±10 luma units on brightness.

**Failure priority for UI feedback (most to least actionable):**
1. Centering — user can reposition camera immediately
2. Focus — "tap to focus" or hold steady
3. Lighting — requires environment change, least actionable

**UI messages:**

| Failing condition | Message shown |
|-------------------|---------------|
| Centering | "Center Your Eye" |
| Focus | "Tap to Focus" |
| Lighting | "Move to Better Light" |
| All passing | "Almost Ready..." |

---

### Stage 4 — `ready`

**Goal:** Terminal state. Signals the capture component to fire the shutter.

No further conditions evaluated. The parent (`MobileCaptureScreen`) initiates the
6-frame burst capture and picks the sharpest frame using a per-frame Laplacian
variance score.

**UI message:** "Hold Still!"

---

## Regression

`returnToStage(stage)` resets `currentStage`, clears stability timers
(`distanceStableTime`, `finalChecksStableTime`), and resets `stageStartTime`.

Called by the parent when countdown aborts mid-flight because quality dropped (e.g.
user blinked or moved). Can only move backward, never skip forward.

---

## Progress Calculation

Each stage reports `progress` as 0–100 for the current stage's stability window:

| Stage | Progress formula |
|-------|-----------------|
| distance | `(now - distanceStableTime) / 800 ms × 100` |
| eyebrows | `(sustainedFrames / 30) × 100` |
| final_checks | `(now - finalChecksStableTime) / 800 ms × 100` |
| ready | Always 100 |

Progress is used by the UI to render a per-stage fill bar.

---

## Telemetry

Every failed condition call in a stage increments a telemetry counter via
`telemetry.trackConditionFailure(condition)`. Counters tracked:

- `distance` — emitted on each frame where iris diameter is out of range
- `eyebrows` — emitted on each frame where `isRaised` is false during stage 2
- `centering` — emitted in stage 3 when centering fails
- `focus` — emitted in stage 3 when sharpness fails
- `lighting` — emitted in stage 3 when brightness fails

These counters surface in `telemetry.logSummary()` (called after successful capture)
and are used for product analytics to identify where users most commonly get stuck.

---

## Related Files

| File | Role |
|------|------|
| `src/lib/captureStages.ts` | `StageManager` class — full state machine implementation |
| `src/lib/qualityMetrics.ts` | Per-frame quality scoring; supplies `QualityReport` to `StageManager.update()` |
| `src/components/MobileCaptureScreen.tsx` | Orchestrates camera, calls `StageManager.update()` every frame, drives UI |
| `src/lib/telemetry.ts` | Failure counter sink |
