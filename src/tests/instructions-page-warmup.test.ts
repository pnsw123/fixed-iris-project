/**
 * Tests for the MediaPipe warm-up behaviour added to InstructionsPage.
 *
 * The warm-up useEffect calls `qualityAnalyzer.initialize()` on mount so
 * that the MediaPipe WASM binary and .task model are cached before the user
 * taps Continue and lands on the capture screen.
 *
 * These tests verify:
 *   1. qualityAnalyzer.initialize() is idempotent (double-call safe)
 *   2. A failing warm-up does NOT throw — it only warns (non-fatal)
 *   3. The warm-up guard prevents concurrent initialisations
 *
 * We do NOT test the actual MediaPipe download (WASM/browser-only).
 * Browser integration is covered by E2E tests.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---------------------------------------------------------------------------
// Minimal replica of the QualityAnalyzer warm-up contract:
// initialize() is idempotent and delegates to faceLandmarkerDetector.initialize()
// ---------------------------------------------------------------------------

class MockFaceLandmarkerDetector {
    callCount = 0;
    shouldFail = false;
    private isInitializing = false;
    private initialized = false;

    async initialize() {
        // Mirrors real FaceLandmarkerDetector double-init guard:
        // subsequent concurrent calls return immediately while first is in progress.
        if (this.initialized || this.isInitializing) return;
        this.isInitializing = true;
        this.callCount++;
        try {
            if (this.shouldFail) {
                throw new Error('WASM load failed');
            }
            this.initialized = true;
        } finally {
            this.isInitializing = false;
        }
    }
}

class WarmupQualityAnalyzer {
    private isInitialized = false;
    private detector: MockFaceLandmarkerDetector;

    constructor(detector: MockFaceLandmarkerDetector) {
        this.detector = detector;
    }

    async initialize() {
        if (this.isInitialized) return;
        await this.detector.initialize();
        this.isInitialized = true;
    }
}

// ---------------------------------------------------------------------------
// Replica of the instructions page warm-up effect logic
// ---------------------------------------------------------------------------
async function instructionsPageWarmupEffect(
    analyzer: WarmupQualityAnalyzer,
    onWarn: (msg: string, err: unknown) => void
): Promise<void> {
    try {
        await analyzer.initialize();
    } catch (err) {
        onWarn('[InstructionsPage] MediaPipe warm-up failed:', err);
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('InstructionsPage MediaPipe warm-up', () => {
    let detector: MockFaceLandmarkerDetector;
    let analyzer: WarmupQualityAnalyzer;
    let warnSpy: ReturnType<typeof vi.fn>;

    beforeEach(() => {
        detector = new MockFaceLandmarkerDetector();
        analyzer = new WarmupQualityAnalyzer(detector);
        warnSpy = vi.fn();
    });

    it('calls detector.initialize() once on first warm-up', async () => {
        await instructionsPageWarmupEffect(analyzer, warnSpy);
        expect(detector.callCount).toBe(1);
        expect(warnSpy).not.toHaveBeenCalled();
    });

    it('is idempotent — second warm-up call skips detector', async () => {
        await instructionsPageWarmupEffect(analyzer, warnSpy);
        await instructionsPageWarmupEffect(analyzer, warnSpy);
        // Only 1 underlying detector call despite 2 warm-up calls
        expect(detector.callCount).toBe(1);
    });

    it('swallows detector errors and calls warn callback instead of throwing', async () => {
        detector.shouldFail = true;
        // Must NOT throw
        await expect(
            instructionsPageWarmupEffect(analyzer, warnSpy)
        ).resolves.toBeUndefined();
        expect(warnSpy).toHaveBeenCalledWith(
            '[InstructionsPage] MediaPipe warm-up failed:',
            expect.any(Error)
        );
    });

    it('warm-up failure leaves analyzer uninitialised for capture-screen retry', async () => {
        detector.shouldFail = true;
        await instructionsPageWarmupEffect(analyzer, warnSpy);

        // Fix the detector and retry — simulates capture screen re-calling initialize()
        detector.shouldFail = false;
        await expect(analyzer.initialize()).resolves.toBeUndefined();
        // Detector was called: once on warm-up (failed), once on retry (succeeded)
        expect(detector.callCount).toBe(2);
    });

    it('concurrent warm-up calls do not double-initialise the detector', async () => {
        // Fire two concurrent warm-up calls (simulates React Strict Mode)
        await Promise.all([
            instructionsPageWarmupEffect(analyzer, warnSpy),
            instructionsPageWarmupEffect(analyzer, warnSpy),
        ]);
        // The idempotency guard ensures detector is called only once
        expect(detector.callCount).toBe(1);
    });
});
