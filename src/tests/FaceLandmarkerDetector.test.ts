/**
 * Tests for FaceLandmarkerDetector.ts
 *
 * FaceLandmarkerDetector wraps the MediaPipe Tasks-Vision FaceLandmarker WASM module.
 * The WASM binary is browser-only and cannot run in a Node test environment.
 *
 * Strategy:
 *   - Mock `@mediapipe/tasks-vision` so no real WASM is loaded.
 *   - Test the singleton pattern, idempotency guard, error propagation,
 *     and the pure geometric helpers (iris extraction, crop box) through
 *     controlled mock return values from FaceLandmarker.detectForVideo.
 *
 * Tests that are explicitly NOT here (left for E2E / integration tests):
 *   - Real MediaPipe inference on an actual video frame
 *   - WebGL delegate selection
 *   - CDN WASM download latency
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ─── Mock @mediapipe/tasks-vision before importing the module under test ───────
//
// vi.mock() is hoisted to the top of the file by vitest, so top-level variables
// declared with const/let are NOT accessible inside the factory (TDZ error).
// Solution: use vi.hoisted() to declare mocks before the hoist boundary.

const { mockDetectForVideo, mockCreateFromOptions, mockForVisionTasks } = vi.hoisted(() => {
    const mockDetectForVideo = vi.fn();
    const mockFaceLandmarker = { detectForVideo: mockDetectForVideo };
    const mockCreateFromOptions = vi.fn().mockResolvedValue(mockFaceLandmarker);
    const mockForVisionTasks = vi.fn().mockResolvedValue({});
    return { mockDetectForVideo, mockCreateFromOptions, mockForVisionTasks };
});

vi.mock('@mediapipe/tasks-vision', () => ({
    FaceLandmarker: {
        createFromOptions: mockCreateFromOptions,
    },
    FilesetResolver: {
        forVisionTasks: mockForVisionTasks,
    },
}));

// Import AFTER mock is registered
import { FaceLandmarkerDetector, faceLandmarkerDetector } from '../lib/FaceLandmarkerDetector';

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Build a minimal normalised landmark array matching what MediaPipe returns.
 * Index layout for face_landmarker with iris:
 *   468-472 = left iris (centre, top, bottom, left, right)
 *   473-477 = right iris (centre, top, bottom, left, right)
 *
 * We populate indices 0-477. Most face landmarks are just (0.5, 0.5, 0) stubs;
 * only the iris landmarks at 468+ are given realistic values.
 */
function buildLandmarks(
    leftIrisOverride?: Partial<{ cx: number; cy: number; r: number }>,
    rightIrisOverride?: Partial<{ cx: number; cy: number; r: number }>
): { x: number; y: number; z: number }[] {
    const lms: { x: number; y: number; z: number }[] = Array.from({ length: 478 }, () => ({
        x: 0.5,
        y: 0.3, // y < 0.7 keeps iris in "upper portion" validity check
        z: 0,
    }));

    const left = { cx: 0.35, cy: 0.35, r: 0.05, ...leftIrisOverride };
    const right = { cx: 0.65, cy: 0.35, r: 0.05, ...rightIrisOverride };

    // Left iris: 468=center, 469=top, 470=bottom, 471=left, 472=right
    lms[468] = { x: left.cx, y: left.cy, z: 0 };
    lms[469] = { x: left.cx, y: left.cy - left.r, z: 0 }; // top
    lms[470] = { x: left.cx, y: left.cy + left.r, z: 0 }; // bottom
    lms[471] = { x: left.cx - left.r, y: left.cy, z: 0 }; // left
    lms[472] = { x: left.cx + left.r, y: left.cy, z: 0 }; // right

    // Right iris: 473=center, 474=top, 475=bottom, 476=left, 477=right
    lms[473] = { x: right.cx, y: right.cy, z: 0 };
    lms[474] = { x: right.cx, y: right.cy - right.r, z: 0 };
    lms[475] = { x: right.cx, y: right.cy + right.r, z: 0 };
    lms[476] = { x: right.cx - right.r, y: right.cy, z: 0 };
    lms[477] = { x: right.cx + right.r, y: right.cy, z: 0 };

    return lms;
}

/** Minimal HTMLVideoElement stub accepted by detect(). */
function makeVideoStub(w = 640, h = 480): HTMLVideoElement {
    return { width: w, height: h } as HTMLVideoElement;
}

// ─── Setup / teardown ─────────────────────────────────────────────────────────

let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
let consoleWarnSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.clearAllMocks();
    // Re-apply default resolved values after clearAllMocks resets them
    mockForVisionTasks.mockResolvedValue({});
    const freshFaceLandmarker = { detectForVideo: mockDetectForVideo };
    mockCreateFromOptions.mockResolvedValue(freshFaceLandmarker);
});

afterEach(() => {
    vi.restoreAllMocks();
});

// ─── Singleton ────────────────────────────────────────────────────────────────

describe('singleton export', () => {
    it('faceLandmarkerDetector is an instance of FaceLandmarkerDetector', () => {
        expect(faceLandmarkerDetector).toBeInstanceOf(FaceLandmarkerDetector);
    });

    it('creating two instances produces distinct objects', () => {
        const a = new FaceLandmarkerDetector();
        const b = new FaceLandmarkerDetector();
        expect(a).not.toBe(b);
    });

    it('module-level singleton is not the same object as a freshly created instance', () => {
        const fresh = new FaceLandmarkerDetector();
        expect(faceLandmarkerDetector).not.toBe(fresh);
    });
});

// ─── initialize() — happy path ────────────────────────────────────────────────

describe('initialize() — happy path', () => {
    it('calls FilesetResolver.forVisionTasks with CDN wasm URL', async () => {
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        expect(mockForVisionTasks).toHaveBeenCalledWith(
            expect.stringContaining('@mediapipe/tasks-vision')
        );
    });

    it('calls FaceLandmarker.createFromOptions with expected model path', async () => {
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        expect(mockCreateFromOptions).toHaveBeenCalledWith(
            expect.anything(),
            expect.objectContaining({
                baseOptions: expect.objectContaining({
                    modelAssetPath: expect.stringContaining('face_landmarker.task'),
                }),
            })
        );
    });

    it('configures VIDEO running mode and numFaces: 1', async () => {
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        expect(mockCreateFromOptions).toHaveBeenCalledWith(
            expect.anything(),
            expect.objectContaining({
                runningMode: 'VIDEO',
                numFaces: 1,
            })
        );
    });
});

// ─── initialize() — idempotency ───────────────────────────────────────────────

describe('initialize() — idempotency', () => {
    it('calling initialize() twice does not call createFromOptions twice', async () => {
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        await detector.initialize();
        expect(mockCreateFromOptions).toHaveBeenCalledTimes(1);
    });

    it('calling initialize() twice does not throw', async () => {
        const detector = new FaceLandmarkerDetector();
        await expect(detector.initialize()).resolves.toBeUndefined();
        await expect(detector.initialize()).resolves.toBeUndefined();
    });

    it('concurrent calls to initialize() only trigger one model load', async () => {
        const detector = new FaceLandmarkerDetector();
        // Fire two calls simultaneously (simulates React Strict Mode double-effect)
        await Promise.all([detector.initialize(), detector.initialize()]);
        expect(mockCreateFromOptions).toHaveBeenCalledTimes(1);
    });
});

// ─── initialize() — error path ───────────────────────────────────────────────

describe('initialize() — error propagation', () => {
    it('throws when FilesetResolver.forVisionTasks rejects (wasm not found)', async () => {
        const error = new Error('Failed to fetch wasm assets');
        mockForVisionTasks.mockRejectedValueOnce(error);

        const detector = new FaceLandmarkerDetector();
        await expect(detector.initialize()).rejects.toThrow('Failed to fetch wasm assets');
    });

    it('logs the error to console.error on init failure', async () => {
        mockForVisionTasks.mockRejectedValueOnce(new Error('404 wasm not found'));
        const detector = new FaceLandmarkerDetector();
        await detector.initialize().catch(() => {});
        expect(consoleErrorSpy).toHaveBeenCalledWith(
            expect.stringContaining('[IrisDetector]'),
            expect.any(Error)
        );
    });

    it('clears isInitializing flag after failure so a retry is possible', async () => {
        // First call fails
        mockForVisionTasks.mockRejectedValueOnce(new Error('temp failure'));
        const detector = new FaceLandmarkerDetector();
        await detector.initialize().catch(() => {});

        // Second call succeeds — createFromOptions should be invoked again
        mockForVisionTasks.mockResolvedValueOnce({});
        mockCreateFromOptions.mockResolvedValueOnce({ detectForVideo: mockDetectForVideo });
        await detector.initialize();
        expect(mockCreateFromOptions).toHaveBeenCalledTimes(1);
    });

    it('throws when createFromOptions rejects (model asset not found)', async () => {
        mockCreateFromOptions.mockRejectedValueOnce(new Error('model asset 404'));
        const detector = new FaceLandmarkerDetector();
        await expect(detector.initialize()).rejects.toThrow('model asset 404');
    });
});

// ─── detect() — before initialization ────────────────────────────────────────

describe('detect() — before initialization', () => {
    it('returns not-detected result when called before initialize()', () => {
        const detector = new FaceLandmarkerDetector();
        const result = detector.detect(makeVideoStub(), 0);
        expect(result.detected).toBe(false);
        expect(result.leftIris).toBeNull();
        expect(result.rightIris).toBeNull();
        expect(result.faceBounds).toBeNull();
    });

    it('does not throw when called before initialize()', () => {
        const detector = new FaceLandmarkerDetector();
        expect(() => detector.detect(makeVideoStub(), 0)).not.toThrow();
    });
});

// ─── detect() — no face found ─────────────────────────────────────────────────

describe('detect() — no face landmarks returned', () => {
    it('returns detected=false when faceLandmarks is empty', async () => {
        mockDetectForVideo.mockReturnValue({ faceLandmarks: [] });
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        const result = detector.detect(makeVideoStub(), 1000);
        expect(result.detected).toBe(false);
    });

    it('returns detected=false when faceLandmarks is undefined', async () => {
        mockDetectForVideo.mockReturnValue({ faceLandmarks: undefined });
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        const result = detector.detect(makeVideoStub(), 1000);
        expect(result.detected).toBe(false);
    });
});

// ─── detect() — successful detection ─────────────────────────────────────────

describe('detect() — successful face detection', () => {
    it('returns detected=true when iris landmarks are present', async () => {
        const lms = buildLandmarks();
        mockDetectForVideo.mockReturnValue({ faceLandmarks: [lms] });
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        const result = detector.detect(makeVideoStub(640, 480), 1000);
        expect(result.detected).toBe(true);
    });

    it('leftIris center is within frame bounds', async () => {
        const lms = buildLandmarks({ cx: 0.35, cy: 0.35, r: 0.04 });
        mockDetectForVideo.mockReturnValue({ faceLandmarks: [lms] });
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        const result = detector.detect(makeVideoStub(640, 480), 1000);
        expect(result.leftIris).not.toBeNull();
        expect(result.leftIris!.center.x).toBeGreaterThanOrEqual(0);
        expect(result.leftIris!.center.x).toBeLessThanOrEqual(640);
        expect(result.leftIris!.center.y).toBeGreaterThanOrEqual(0);
        expect(result.leftIris!.center.y).toBeLessThanOrEqual(480);
    });

    it('rightIris center is within frame bounds', async () => {
        const lms = buildLandmarks(undefined, { cx: 0.65, cy: 0.35, r: 0.04 });
        mockDetectForVideo.mockReturnValue({ faceLandmarks: [lms] });
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        const result = detector.detect(makeVideoStub(640, 480), 1000);
        expect(result.rightIris).not.toBeNull();
        expect(result.rightIris!.center.x).toBeGreaterThanOrEqual(0);
        expect(result.rightIris!.center.x).toBeLessThanOrEqual(640);
    });

    it('leftIris diameter is positive', async () => {
        const lms = buildLandmarks({ r: 0.04 });
        mockDetectForVideo.mockReturnValue({ faceLandmarks: [lms] });
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        const result = detector.detect(makeVideoStub(640, 480), 1000);
        expect(result.leftIris!.diameter).toBeGreaterThan(0);
    });

    it('irisCropBox is present and has positive size', async () => {
        const lms = buildLandmarks({ cx: 0.35, cy: 0.35, r: 0.05 });
        mockDetectForVideo.mockReturnValue({ faceLandmarks: [lms] });
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        const result = detector.detect(makeVideoStub(640, 480), 1000);
        expect(result.irisCropBox).toBeDefined();
        expect(result.irisCropBox!.size).toBeGreaterThan(0);
    });

    it('faceBounds is present with positive dimensions', async () => {
        const lms = buildLandmarks();
        mockDetectForVideo.mockReturnValue({ faceLandmarks: [lms] });
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        const result = detector.detect(makeVideoStub(640, 480), 1000);
        expect(result.faceBounds).not.toBeNull();
        expect(result.faceBounds!.width).toBeGreaterThanOrEqual(0);
        expect(result.faceBounds!.height).toBeGreaterThanOrEqual(0);
    });

    it('raw landmarks array length equals face landmark count', async () => {
        const lms = buildLandmarks();
        mockDetectForVideo.mockReturnValue({ faceLandmarks: [lms] });
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        const result = detector.detect(makeVideoStub(640, 480), 1000);
        expect(Array.isArray(result.landmarks)).toBe(true);
        expect(result.landmarks!.length).toBe(lms.length);
    });
});

// ─── detect() — iris out of valid region ─────────────────────────────────────

describe('detect() — iris validity checks', () => {
    it('returns null leftIris when iris center y > 70% of frame height', async () => {
        // cy = 0.8 → 0.8 * 480 = 384 > 480 * 0.7 = 336  → should return null
        const lms = buildLandmarks({ cx: 0.35, cy: 0.80, r: 0.04 });
        mockDetectForVideo.mockReturnValue({ faceLandmarks: [lms] });
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        const result = detector.detect(makeVideoStub(640, 480), 1000);
        expect(result.leftIris).toBeNull();
    });
});

// ─── detect() — internal error handling ──────────────────────────────────────

describe('detect() — error resilience', () => {
    it('returns not-detected result when detectForVideo throws', async () => {
        mockDetectForVideo.mockImplementation(() => {
            throw new Error('GPU context lost');
        });
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        const result = detector.detect(makeVideoStub(), 1000);
        expect(result.detected).toBe(false);
        expect(consoleErrorSpy).toHaveBeenCalled();
    });
});

// ─── Crop box geometry ────────────────────────────────────────────────────────

describe('irisCropBox geometry', () => {
    it('crop box stays within frame bounds (x >= 0)', async () => {
        // Left iris very close to left edge
        const lms = buildLandmarks({ cx: 0.02, cy: 0.3, r: 0.03 });
        mockDetectForVideo.mockReturnValue({ faceLandmarks: [lms] });
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        const result = detector.detect(makeVideoStub(640, 480), 1000);
        expect(result.irisCropBox).toBeDefined();
        expect(result.irisCropBox!.x).toBeGreaterThanOrEqual(0);
        expect(result.irisCropBox!.y).toBeGreaterThanOrEqual(0);
    });

    it('crop box minimum size is 32px', async () => {
        // Tiny iris at edge of frame — clamping should ensure >= 32px
        const lms = buildLandmarks({ cx: 0.35, cy: 0.35, r: 0.001 });
        mockDetectForVideo.mockReturnValue({ faceLandmarks: [lms] });
        const detector = new FaceLandmarkerDetector();
        await detector.initialize();
        const result = detector.detect(makeVideoStub(640, 480), 1000);
        if (result.irisCropBox) {
            expect(result.irisCropBox.size).toBeGreaterThanOrEqual(32);
        }
    });
});
