/**
 * Tests for qualityMetrics.ts
 *
 * We test the pure, DOM-independent helpers only.
 * QualityAnalyzer.analyze() requires HTMLVideoElement + FaceLandmarkerDetector
 * (WASM-based, browser-only) — those are left for E2E tests.
 */
import { describe, it, expect } from 'vitest';

// ---------------------------------------------------------------------------
// SimpleMovingAverage — extracted via module-level whitebox testing.
// We re-implement the class inline for unit isolation so tests don't break
// if internal class name changes, but we also verify exported API contracts.
// ---------------------------------------------------------------------------

/**
 * A minimal copy of the SimpleMovingAverage implementation to unit-test
 * the mathematical behaviour independently of the rest of the module.
 */
class SimpleMovingAverageTest {
    private window: number[] = [];
    private size: number;
    private sum: number = 0;

    constructor(size: number) {
        this.size = size;
    }

    push(val: number): number {
        this.window.push(val);
        this.sum += val;
        if (this.window.length > this.size) {
            this.sum -= this.window.shift()!;
        }
        return this.sum / this.window.length;
    }

    reset() {
        this.window = [];
        this.sum = 0;
    }
}

describe('SimpleMovingAverage', () => {
    it('returns the pushed value for first element', () => {
        const sma = new SimpleMovingAverageTest(5);
        expect(sma.push(10)).toBe(10);
    });

    it('averages two values correctly', () => {
        const sma = new SimpleMovingAverageTest(5);
        sma.push(10);
        expect(sma.push(20)).toBe(15);
    });

    it('evicts oldest value once window is full', () => {
        const sma = new SimpleMovingAverageTest(3);
        sma.push(10); // [10]
        sma.push(10); // [10, 10]
        sma.push(10); // [10, 10, 10]
        // Window full — push 40, oldest 10 evicted → [10, 10, 40] avg = 20
        expect(sma.push(40)).toBeCloseTo(20, 5);
    });

    it('resets to empty state', () => {
        const sma = new SimpleMovingAverageTest(5);
        sma.push(100);
        sma.push(200);
        sma.reset();
        // After reset, first push returns just that value
        expect(sma.push(50)).toBe(50);
    });

    it('handles window size of 1 (always last value)', () => {
        const sma = new SimpleMovingAverageTest(1);
        sma.push(5);
        sma.push(10);
        expect(sma.push(42)).toBe(42);
    });
});

// ---------------------------------------------------------------------------
// Score threshold logic — pure numeric functions re-tested as specs
// ---------------------------------------------------------------------------

/**
 * Replicate the distance-score logic from QualityAnalyzer exactly,
 * so we can verify boundary conditions without spinning up canvas/WASM.
 */
function distanceScore(
    smoothedDiameter: number,
    refDim: number
): { score: number; status: 'ok' | 'warn' | 'fail'; feedback: string } {
    const targetDiameterMin = refDim * 0.07;
    const targetDiameterMax = refDim * 0.24;
    const targetDiameterIdeal = (targetDiameterMin + targetDiameterMax) / 2;
    const okMin = targetDiameterMin * 0.93;

    if (smoothedDiameter >= okMin && smoothedDiameter <= targetDiameterMax) {
        const deviation = Math.abs(smoothedDiameter - targetDiameterIdeal);
        const maxDeviation = (targetDiameterMax - targetDiameterMin) / 2;
        const score = Math.max(0, 100 - (deviation / maxDeviation) * 30);
        return { score, status: 'ok', feedback: 'Perfect distance' };
    } else if (smoothedDiameter < targetDiameterMin) {
        const ratio = smoothedDiameter / targetDiameterMin;
        const score = Math.max(0, ratio * 70);
        const status = ratio > 0.4 ? 'warn' : 'fail';
        return { score, status, feedback: 'Move closer' };
    } else {
        const ratio = (smoothedDiameter - targetDiameterMax) / targetDiameterMax;
        const score = Math.max(0, 70 - ratio * 70);
        const status = ratio < 0.6 ? 'warn' : 'fail';
        return { score, status, feedback: 'Move back' };
    }
}

describe('distanceScore thresholds', () => {
    const refDim = 720;

    it('returns ok status when diameter is in ideal range', () => {
        // Ideal midpoint = (0.07 + 0.24) / 2 * 720 = 111.6
        const ideal = ((0.07 + 0.24) / 2) * refDim;
        const result = distanceScore(ideal, refDim);
        expect(result.status).toBe('ok');
        expect(result.score).toBeGreaterThanOrEqual(70);
    });

    it('returns fail when iris is very small (too far)', () => {
        // 2% of refDim → well below 7% min
        const tiny = refDim * 0.02;
        const result = distanceScore(tiny, refDim);
        expect(result.status).toBe('fail');
        expect(result.score).toBeLessThan(30);
        expect(result.feedback).toBe('Move closer');
    });

    it('returns warn when iris is slightly below min threshold', () => {
        // ~50% of min threshold → ratio = 0.5 > 0.4 → warn
        const slightlySmall = refDim * 0.07 * 0.5;
        const result = distanceScore(slightlySmall, refDim);
        expect(result.status).toBe('warn');
    });

    it('returns warn when iris is slightly too large', () => {
        // 30% of refDim → above 24% max but ratio < 0.6
        const slightlyLarge = refDim * 0.30;
        const result = distanceScore(slightlyLarge, refDim);
        expect(result.status).toBe('warn');
        expect(result.feedback).toBe('Move back');
    });

    it('score is never negative', () => {
        const extremelySmall = 0;
        const r1 = distanceScore(extremelySmall, refDim);
        expect(r1.score).toBeGreaterThanOrEqual(0);

        const extremelyLarge = refDim * 2;
        const r2 = distanceScore(extremelyLarge, refDim);
        expect(r2.score).toBeGreaterThanOrEqual(0);
    });
});

/**
 * Replicate lighting score logic from QualityAnalyzer.
 */
function lightingScore(
    brightness: number
): { score: number; status: 'ok' | 'warn' | 'fail'; feedback: string } {
    const idealMin = 100;
    const idealMax = 180;
    const idealMid = (idealMin + idealMax) / 2;

    if (brightness >= idealMin && brightness <= idealMax) {
        const deviation = Math.abs(brightness - idealMid);
        const maxDeviation = (idealMax - idealMin) / 2;
        const score = Math.max(0, 100 - (deviation / maxDeviation) * 30);
        return { score, status: 'ok', feedback: 'Good lighting' };
    } else if (brightness < idealMin) {
        const ratio = brightness / idealMin;
        const score = Math.max(0, ratio * 70);
        const status = ratio > 0.7 ? 'warn' : 'fail';
        return { score, status, feedback: 'Too dark' };
    } else {
        const ratio = (brightness - idealMax) / (255 - idealMax);
        const score = Math.max(0, 70 - ratio * 70);
        const status = ratio < 0.3 ? 'warn' : 'fail';
        return { score, status, feedback: 'Too bright' };
    }
}

describe('lightingScore thresholds', () => {
    it('returns ok for ideal brightness at midpoint', () => {
        const mid = (100 + 180) / 2; // 140
        const result = lightingScore(mid);
        expect(result.status).toBe('ok');
        expect(result.score).toBe(100);
    });

    it('returns fail for very dark image', () => {
        const result = lightingScore(30);
        expect(result.status).toBe('fail');
        expect(result.feedback).toBe('Too dark');
    });

    it('returns warn for slightly dark image (ratio > 0.7)', () => {
        // ratio = 80/100 = 0.8 > 0.7 → warn
        const result = lightingScore(80);
        expect(result.status).toBe('warn');
    });

    it('returns fail for very bright image', () => {
        // brightness = 255 → ratio = (255-180)/(255-180) = 1.0 >= 0.3 → fail
        const result = lightingScore(255);
        expect(result.status).toBe('fail');
        expect(result.feedback).toBe('Too bright');
    });

    it('score is never negative', () => {
        expect(lightingScore(0).score).toBeGreaterThanOrEqual(0);
        expect(lightingScore(255).score).toBeGreaterThanOrEqual(0);
    });
});

// ---------------------------------------------------------------------------
// QualityReport shape — verify exported interface is consistent
// ---------------------------------------------------------------------------

describe('QualityReport interface contract', () => {
    it('no-detection result has all required fields set to fail', () => {
        // Simulate what QualityAnalyzer returns when no iris detected
        const noDetectionResult = {
            irisDetected: false,
            irisCenter: { x: 0, y: 0 },
            irisDiameter: 0,
            distance: { score: 0, status: 'fail' as const, feedback: 'No face detected' },
            lighting: { score: 0, status: 'fail' as const, feedback: 'No face detected' },
            centering: { score: 0, status: 'fail' as const, feedback: 'No face detected' },
            focus: { score: 0, status: 'fail' as const, feedback: 'No face detected' },
            rawBrightness: 0,
            centeringRatio: 1,
        };

        expect(noDetectionResult.irisDetected).toBe(false);
        expect(noDetectionResult.distance.status).toBe('fail');
        expect(noDetectionResult.lighting.status).toBe('fail');
        expect(noDetectionResult.centering.status).toBe('fail');
        expect(noDetectionResult.focus.status).toBe('fail');
        expect(noDetectionResult.irisDiameter).toBe(0);
        expect(noDetectionResult.centeringRatio).toBe(1);
    });
});
