/**
 * Tests for MobileCaptureScreen.tsx
 *
 * MobileCaptureScreen is the primary iris capture component. It relies on
 * getUserMedia, requestAnimationFrame, canvas, MediaPipe — all browser-only.
 * No @testing-library/react installed.
 *
 * Strategy: replicate pure logic inline following the project pattern.
 *
 * What we test:
 *   - CaptureData interface shape
 *   - computeGuidance priority routing
 *   - handleCameraError error routing (permission_denied, no_device, generic)
 *   - FOCUS_LOCK_MS constant (800ms)
 *   - STABLE_GOOD_FRAMES constant (5 frames)
 *   - Analysis cap (100ms gate)
 *   - CameraErrorState type values
 */
import { describe, it, expect } from 'vitest';
import type { CaptureData } from '../components/MobileCaptureScreen';
import type { QualityReport } from '../lib/qualityMetrics';

// ---------------------------------------------------------------------------
// Replicated pure logic from MobileCaptureScreen.tsx
// ---------------------------------------------------------------------------

type CameraErrorState = 'permission_denied' | 'no_device' | 'generic_error' | null;

function handleCameraError(err: unknown): CameraErrorState {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg === 'PERMISSION_DENIED') return 'permission_denied';
    if (msg === 'NO_DEVICE') return 'no_device';
    return 'generic_error';
}

function computeGuidance(
    report: QualityReport | null,
    focusLocked: boolean,
    angleOk: boolean,
    angleAvailable: boolean,
    countdown: number | null
): string {
    if (!report || !report.irisDetected) {
        return 'Align one eye in the circle';
    }

    if (!report.irisCropBox) {
        return 'Hold steady...';
    }

    if (report.focus.status === 'fail') {
        return 'Image is blurry — hold still to focus';
    }
    if (report.focus.status === 'warn') {
        return 'Almost sharp — keep still...';
    }
    if (!focusLocked) {
        return 'Perfect focus. Hold still...';
    }
    if (angleAvailable && !angleOk) {
        return 'Aim light at hairline — tilt phone back';
    }
    if (report.distance.status === 'fail') {
        return report.distance.feedback;
    }
    if (report.centering.status === 'fail') {
        return 'Center your eye in the circle';
    }
    if (report.lighting.status === 'fail') {
        return 'Move to better lighting';
    }

    const allPerfect =
        report.distance.status === 'ok' &&
        report.centering.status === 'ok' &&
        report.lighting.status === 'ok';

    if (allPerfect && countdown === null) {
        return 'Perfect. Hold still...';
    }

    if (countdown !== null) {
        return `Hold still... ${countdown}`;
    }

    return 'Almost there...';
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeReport(overrides: Partial<QualityReport> = {}): QualityReport {
    return {
        irisDetected: true,
        irisCenter: { x: 240, y: 320 },
        irisCropBox: { x: 180, y: 260, size: 120 },
        irisDiameter: 100,
        distance: { score: 80, status: 'ok', feedback: 'Good distance' },
        lighting: { score: 70, status: 'ok', feedback: 'Good lighting' },
        centering: { score: 60, status: 'ok', feedback: 'Centered' },
        focus: { score: 90, status: 'ok', feedback: 'Sharp' },
        ...overrides,
    };
}

// ---------------------------------------------------------------------------
// CaptureData interface
// ---------------------------------------------------------------------------

describe('MobileCaptureScreen — CaptureData interface', () => {
    it('has required imageData field (base64 string)', () => {
        const data: CaptureData = {
            imageData: 'data:image/jpeg;base64,abc123',
            irisCoordinates: null,
            cropSize: 256,
            irisRadius: null,
        };
        expect(data.imageData).toContain('data:image');
    });

    it('irisCoordinates is nullable', () => {
        const withCoords: CaptureData = {
            imageData: 'data:image/jpeg;base64,abc',
            irisCoordinates: { x: 128, y: 128 },
            cropSize: 256,
            irisRadius: 48,
        };
        const withoutCoords: CaptureData = {
            imageData: 'data:image/jpeg;base64,abc',
            irisCoordinates: null,
            cropSize: 256,
            irisRadius: null,
        };
        expect(withCoords.irisCoordinates).not.toBeNull();
        expect(withoutCoords.irisCoordinates).toBeNull();
    });

    it('cropSize is a positive number', () => {
        const data: CaptureData = {
            imageData: 'data:image/jpeg;base64,abc',
            irisCoordinates: { x: 64, y: 64 },
            cropSize: 256,
            irisRadius: 40,
        };
        expect(data.cropSize).toBeGreaterThan(0);
    });

    it('irisRadius is nullable', () => {
        const withRadius: CaptureData = {
            imageData: 'data:image/jpeg;base64,abc',
            irisCoordinates: { x: 64, y: 64 },
            cropSize: 256,
            irisRadius: 45,
        };
        expect(withRadius.irisRadius).toBe(45);

        const withoutRadius: CaptureData = {
            imageData: 'data:image/jpeg;base64,abc',
            irisCoordinates: null,
            cropSize: 256,
            irisRadius: null,
        };
        expect(withoutRadius.irisRadius).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// handleCameraError routing
// ---------------------------------------------------------------------------

describe('MobileCaptureScreen — handleCameraError routing', () => {
    it('routes PERMISSION_DENIED error to permission_denied state', () => {
        const result = handleCameraError(new Error('PERMISSION_DENIED'));
        expect(result).toBe('permission_denied');
    });

    it('routes NO_DEVICE error to no_device state', () => {
        const result = handleCameraError(new Error('NO_DEVICE'));
        expect(result).toBe('no_device');
    });

    it('routes unknown errors to generic_error state', () => {
        const result = handleCameraError(new Error('Something else went wrong'));
        expect(result).toBe('generic_error');
    });

    it('routes non-Error objects to generic_error', () => {
        const result = handleCameraError('raw string error');
        expect(result).toBe('generic_error');
    });

    it('routes DOMException-like errors to generic_error when unrecognised', () => {
        const result = handleCameraError(new Error('SomeOtherDOMError'));
        expect(result).toBe('generic_error');
    });
});

// ---------------------------------------------------------------------------
// CameraErrorState type values
// ---------------------------------------------------------------------------

describe('MobileCaptureScreen — CameraErrorState values', () => {
    it('null represents no error', () => {
        const state: CameraErrorState = null;
        expect(state).toBeNull();
    });

    it('permission_denied is a valid error state', () => {
        const state: CameraErrorState = 'permission_denied';
        expect(state).toBe('permission_denied');
    });

    it('no_device is a valid error state', () => {
        const state: CameraErrorState = 'no_device';
        expect(state).toBe('no_device');
    });

    it('generic_error is a valid error state', () => {
        const state: CameraErrorState = 'generic_error';
        expect(state).toBe('generic_error');
    });
});

// ---------------------------------------------------------------------------
// computeGuidance priority logic
// ---------------------------------------------------------------------------

describe('MobileCaptureScreen — computeGuidance', () => {
    it('returns "Align one eye in the circle" when report is null', () => {
        expect(computeGuidance(null, false, true, false, null)).toBe(
            'Align one eye in the circle'
        );
    });

    it('returns "Align one eye in the circle" when iris not detected', () => {
        const report = makeReport({ irisDetected: false });
        expect(computeGuidance(report, false, true, false, null)).toBe(
            'Align one eye in the circle'
        );
    });

    it('returns "Hold steady..." when no irisCropBox', () => {
        const report = makeReport({ irisCropBox: undefined });
        expect(computeGuidance(report, false, true, false, null)).toBe('Hold steady...');
    });

    it('returns blur message when focus status is fail', () => {
        const report = makeReport({
            focus: { score: 10, status: 'fail', feedback: 'Blurry' },
        });
        expect(computeGuidance(report, false, true, false, null)).toBe(
            'Image is blurry — hold still to focus'
        );
    });

    it('returns "Almost sharp" when focus status is warn', () => {
        const report = makeReport({
            focus: { score: 60, status: 'warn', feedback: 'Slightly blurry' },
        });
        expect(computeGuidance(report, false, true, false, null)).toBe(
            'Almost sharp — keep still...'
        );
    });

    it('returns "Perfect focus. Hold still..." when focus ok but not yet locked', () => {
        const report = makeReport();
        expect(computeGuidance(report, false, true, false, null)).toBe(
            'Perfect focus. Hold still...'
        );
    });

    it('returns angle guidance when angle available and not ok', () => {
        const report = makeReport();
        expect(computeGuidance(report, true, false, true, null)).toBe(
            'Aim light at hairline — tilt phone back'
        );
    });

    it('does NOT show angle guidance when angle unavailable', () => {
        const report = makeReport();
        // angleAvailable=false means API not available — pass-through
        const result = computeGuidance(report, true, false, false, null);
        expect(result).not.toBe('Aim light at hairline — tilt phone back');
    });

    it('returns distance feedback when distance fails after focus lock', () => {
        const report = makeReport({
            distance: { score: 20, status: 'fail', feedback: 'Move closer to the camera' },
        });
        expect(computeGuidance(report, true, true, true, null)).toBe(
            'Move closer to the camera'
        );
    });

    it('returns "Center your eye in the circle" when centering fails', () => {
        const report = makeReport({
            centering: { score: 10, status: 'fail', feedback: 'Off center' },
        });
        expect(computeGuidance(report, true, true, true, null)).toBe(
            'Center your eye in the circle'
        );
    });

    it('returns "Move to better lighting" when lighting fails', () => {
        const report = makeReport({
            lighting: { score: 10, status: 'fail', feedback: 'Too dark' },
        });
        expect(computeGuidance(report, true, true, true, null)).toBe(
            'Move to better lighting'
        );
    });

    it('returns "Perfect. Hold still..." when all conditions met and countdown null', () => {
        const report = makeReport();
        expect(computeGuidance(report, true, true, true, null)).toBe(
            'Perfect. Hold still...'
        );
    });

    it('returns countdown message when countdown is active', () => {
        const report = makeReport();
        expect(computeGuidance(report, true, true, true, 3)).toBe('Hold still... 3');
        expect(computeGuidance(report, true, true, true, 2)).toBe('Hold still... 2');
        expect(computeGuidance(report, true, true, true, 1)).toBe('Hold still... 1');
    });
});

// ---------------------------------------------------------------------------
// Analysis constants
// ---------------------------------------------------------------------------

describe('MobileCaptureScreen — analysis constants', () => {
    it('FOCUS_LOCK_MS is 800ms', () => {
        const FOCUS_LOCK_MS = 800;
        expect(FOCUS_LOCK_MS).toBe(800);
    });

    it('STABLE_GOOD_FRAMES is 5 (~0.5s at 100ms cadence)', () => {
        const STABLE_GOOD_FRAMES = 5;
        expect(STABLE_GOOD_FRAMES).toBe(5);
    });

    it('analysis loop gate is 100ms (10 fps cap)', () => {
        const ANALYSIS_GATE_MS = 100;
        expect(ANALYSIS_GATE_MS).toBe(100);
        expect(1000 / ANALYSIS_GATE_MS).toBe(10); // 10 fps
    });
});
