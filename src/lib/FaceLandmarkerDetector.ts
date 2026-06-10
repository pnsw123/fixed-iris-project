/**
 * FaceLandmarkerDetector.ts — Singleton wrapper around MediaPipe Tasks-Vision FaceLandmarker.
 *
 * Design decisions:
 *
 * 1. Lazy initialisation (not loaded at module parse time)
 *    MediaPipe Tasks-Vision downloads a WASM binary and a .task model file from a CDN.
 *    Both are browser-only resources.  In a Next.js project the module is evaluated
 *    during Server-Side Rendering (SSR) where `window`, `HTMLVideoElement`, and
 *    WebAssembly are unavailable.  Deferring init to the first `initialize()` call
 *    (which only happens in a browser event handler) avoids SSR crashes.
 *
 * 2. Double-init guard (`isInitializing` flag)
 *    React 18 Strict Mode double-invokes effects in development.  Without the guard,
 *    two concurrent callers could both see `faceLandmarker === null` and start two
 *    parallel downloads/inits, wasting bandwidth and potentially corrupting internal
 *    MediaPipe state.  The flag ensures only the first caller proceeds; subsequent
 *    callers return immediately and rely on the shared result.
 *
 * 3. GPU delegate
 *    `delegate: 'GPU'` routes inference through WebGL, reducing per-frame cost from
 *    ~40 ms (CPU) to ~5-10 ms on modern hardware.  MediaPipe silently falls back to
 *    CPU if WebGL is unavailable, so this is safe to specify unconditionally.
 *
 * 4. Singleton export (`faceLandmarkerDetector`)
 *    A single instance is shared across the app so the model is loaded once.
 *    Re-creating the detector would re-download the 30 MB model and re-compile shaders.
 */
import { FaceLandmarker, FilesetResolver, NormalizedLandmark } from '@mediapipe/tasks-vision';

export interface DetectionResult {
    detected: boolean;
    leftIris: { center: { x: number, y: number }, diameter: number, landmarks?: { x: number, y: number }[] } | null;
    rightIris: { center: { x: number, y: number }, diameter: number, landmarks?: { x: number, y: number }[] } | null;
    eyebrows: { leftHeight: number, rightHeight: number, areRaised: boolean } | null;
    faceBounds: { x: number, y: number, width: number, height: number } | null;
    landmarks?: { x: number, y: number }[]; // Raw landmarks for debugging
    irisCropBox?: { x: number, y: number, size: number }; // Crop box for iris capture
}

// MediaPipe Iris Landmarker provides 5 landmarks per iris:
// Index 0: Center of the iris
// Index 1-4: Points on the iris boundary (top, bottom, left, right)
const IRIS_LANDMARKS = {
    CENTER: 0,
    TOP: 1,
    BOTTOM: 2,
    LEFT: 3,
    RIGHT: 4
};

export class FaceLandmarkerDetector {
    /** Null until initialize() completes successfully. */
    private faceLandmarker: FaceLandmarker | null = null;

    /**
     * Guards against concurrent initialisation.
     * Set to true as soon as the first initialize() call begins, preventing any
     * subsequent call (e.g. from React Strict Mode's double-effect) from starting
     * a second parallel load.  Cleared in the finally block so that a retry is
     * possible if init throws.
     */
    private isInitializing = false;

    /**
     * initialize — lazy, idempotent async factory for the FaceLandmarker model.
     *
     * Safe to call multiple times; subsequent calls are no-ops once the
     * detector is ready or while init is already in progress.
     *
     * Steps:
     *  1. FilesetResolver downloads the Tasks-Vision WASM bundle from jsDelivr CDN.
     *  2. FaceLandmarker.createFromOptions loads the bundled face_landmarker.task
     *     model (served from /public/models/ to avoid CDN latency at inference time).
     *  3. runningMode: 'VIDEO' enables temporal smoothing between frames, which
     *     reduces landmark jitter compared to IMAGE mode.
     *  4. numFaces: 1 limits detection to a single subject — the iris capture UX
     *     is inherently single-user, and limiting to 1 halves inference time.
     *  5. outputFaceBlendshapes / outputFacialTransformationMatrixes both off —
     *     we only need raw landmarks; disabling these cuts model output size.
     */
    async initialize() {
        if (this.faceLandmarker || this.isInitializing) return;
        this.isInitializing = true;

        try {
            console.log('[IrisDetector] Loading Vision Tasks...');
            const vision = await FilesetResolver.forVisionTasks(
                'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@latest/wasm'
            );

            console.log('[IrisDetector] Loading Face + Iris Landmarker model...');
            // Use Face Landmarker with iris tracking enabled
            this.faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
                baseOptions: {
                    modelAssetPath: '/models/face_landmarker.task',
                    // GPU delegate routes inference through WebGL, ~5-10 ms/frame
                    // vs ~40 ms on CPU.  Falls back to CPU automatically if WebGL
                    // is unavailable (e.g. headless test environments).
                    delegate: 'GPU',
                },
                // VIDEO mode enables inter-frame temporal smoothing on landmarks.
                runningMode: 'VIDEO',
                numFaces: 1,
                outputFaceBlendshapes: false,
                outputFacialTransformationMatrixes: false,
            });
            console.log('[IrisDetector] Ready - Iris tracking enabled');
        } catch (err) {
            console.error('[IrisDetector] Init failed:', err);
            throw err;
        } finally {
            this.isInitializing = false;
        }
    }

    detect(video: HTMLVideoElement | HTMLCanvasElement, timestamp: number): DetectionResult {
        if (!this.faceLandmarker) {
            return { detected: false, leftIris: null, rightIris: null, eyebrows: null, faceBounds: null };
        }

        try {
            const result = this.faceLandmarker.detectForVideo(video, timestamp);

            if (!result.faceLandmarks || result.faceLandmarks.length === 0) {
                return { detected: false, leftIris: null, rightIris: null, eyebrows: null, faceBounds: null };
            }

            const width = video.width;
            const height = video.height;

            // MediaPipe Face Landmarker includes iris landmarks (468-477)
            // Left iris: 468-472, Right iris: 473-477
            const landmarks = result.faceLandmarks[0];
            
            // Extract iris data directly from MediaPipe's iris landmarks
            const leftIris = this.extractIrisFromLandmarks(landmarks, 468, width, height, 'LEFT');
            const rightIris = this.extractIrisFromLandmarks(landmarks, 473, width, height, 'RIGHT');

            // Get face bounds for lighting analysis
            const faceBounds = this.extractFaceBounds(landmarks, width, height);

            // Use LEFT iris for capture (consistent with selfie UX)
            const irisCropBox = leftIris ? this.computeIrisCropBox(leftIris, width, height) : undefined;

            return {
                detected: true,
                leftIris,
                rightIris,
                eyebrows: null, // Not needed for iris capture
                faceBounds,
                landmarks: landmarks.map(l => ({ x: l.x * width, y: l.y * height })),
                irisCropBox
            };

        } catch (e) {
            console.error('[IrisDetector] Detection error:', e);
            return { detected: false, leftIris: null, rightIris: null, eyebrows: null, faceBounds: null };
        }
    }

    /**
     * Extract iris center and diameter from MediaPipe's dedicated iris landmarks
     * MediaPipe provides 5 landmarks per iris: center + 4 boundary points
     */
    private extractIrisFromLandmarks(
        landmarks: NormalizedLandmark[],
        startIndex: number,
        width: number,
        height: number,
        eye: 'LEFT' | 'RIGHT'
    ): { center: { x: number, y: number }, diameter: number, landmarks: { x: number, y: number }[] } | null {
        try {
            // Get the 5 iris landmarks
            const irisLandmarks = [
                landmarks[startIndex + 0], // Center
                landmarks[startIndex + 1], // Top
                landmarks[startIndex + 2], // Bottom
                landmarks[startIndex + 3], // Left
                landmarks[startIndex + 4]  // Right
            ];

            // Validate all landmarks exist
            if (!irisLandmarks.every(lm => lm && lm.x !== undefined && lm.y !== undefined)) {
                console.warn(`[IrisDetector] Missing ${eye} iris landmarks`);
                return null;
            }

            // Pixel-space landmarks for more accurate center/crop
            const irisPixels = irisLandmarks.map(lm => ({
                x: lm.x * width,
                y: lm.y * height
            }));

            // Use MediaPipe's dedicated centre landmark (index 0) directly.
            // Earlier versions averaged all 5 iris landmarks, but that causes a
            // systematic upward bias when the upper eyelid occludes the TOP boundary
            // landmark (index 1): the average pulls the computed centre toward the
            // visible points.  The centre landmark (index 0) is placed by the model
            // independently of the boundary points, so it remains stable even with
            // partial occlusion.
            const centerX = irisPixels[IRIS_LANDMARKS.CENTER].x;
            const centerY = irisPixels[IRIS_LANDMARKS.CENTER].y;

            // Calculate diameter from boundary points
            const top = irisPixels[IRIS_LANDMARKS.TOP].y;
            const bottom = irisPixels[IRIS_LANDMARKS.BOTTOM].y;
            const left = irisPixels[IRIS_LANDMARKS.LEFT].x;
            const right = irisPixels[IRIS_LANDMARKS.RIGHT].x;

            const verticalDiameter = Math.abs(bottom - top);
            const horizontalDiameter = Math.abs(right - left);
            
            // Use the LARGER of vertical and horizontal diameters.
            // When eyelids partially close the vertical extent (e.g. drooping lids),
            // the vertical diameter shrinks while the horizontal diameter stays constant.
            // Taking the max gives a stable diameter estimate in both cases and ensures
            // the crop box is never too small to contain the full iris.
            let diameter = Math.max(verticalDiameter, horizontalDiameter);

            // Clamp diameter to plausible range instead of dropping the detection entirely.
            // Dropping would blank the UI overlay, confusing users.  Clamping keeps the
            // target ring visible while qualityMetrics.ts reports a low distance score,
            // guiding the user to adjust.
            const frameSize = Math.min(width, height);
            const MIN_IRIS_SIZE = frameSize * 0.008; // 0.8% of shortest side (much more forgiving)
            const MAX_IRIS_SIZE = frameSize * 0.12;  // 12% of shortest side
            
            if (diameter < MIN_IRIS_SIZE) {
                console.warn(`[IrisDetector] Small ${eye} iris diameter: ${diameter.toFixed(1)}px (clamping to ${MIN_IRIS_SIZE.toFixed(1)}px)`);
                diameter = MIN_IRIS_SIZE;
            } else if (diameter > MAX_IRIS_SIZE) {
                console.warn(`[IrisDetector] Large ${eye} iris diameter: ${diameter.toFixed(1)}px (clamping to ${MAX_IRIS_SIZE.toFixed(1)}px)`);
                diameter = MAX_IRIS_SIZE;
            }

            // VALIDATION: Center should be in reasonable face region
            if (centerX < 0 || centerX > width || centerY < 0 || centerY > height) {
                console.warn(`[IrisDetector] ${eye} iris center out of bounds`);
                return null;
            }

            // VALIDATION: Iris should be in upper portion of frame (eyes, not chin)
            if (centerY > height * 0.7) {
                console.warn(`[IrisDetector] ${eye} iris too low in frame`);
                return null;
            }

            console.log(`[IrisDetector] ✅ ${eye} iris detected - center: (${centerX.toFixed(1)}, ${centerY.toFixed(1)}), diameter: ${diameter.toFixed(1)}px`);

            return {
                center: { x: centerX, y: centerY },
                diameter,
                landmarks: irisPixels
            };
        } catch (e) {
            console.error(`[IrisDetector] Failed to extract ${eye} iris:`, e);
            return null;
        }
    }

    private extractFaceBounds(landmarks: NormalizedLandmark[], width: number, height: number): { x: number, y: number, width: number, height: number } {
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const lm of landmarks) {
            const x = lm.x * width;
            const y = lm.y * height;
            if (x < minX) minX = x;
            if (x > maxX) maxX = x;
            if (y < minY) minY = y;
            if (y > maxY) maxY = y;
        }

        return {
            x: minX,
            y: minY,
            width: maxX - minX,
            height: maxY - minY
        };
    }

    /**
     * computeIrisCropBox — builds a square crop region centred on the iris.
     *
     * paddingFactor = 2.4:
     *   The raw iris bounding box exactly fits the visible iris.  A factor of 2.4
     *   adds ~70% padding on each side, ensuring the sclera and limbal border are
     *   included — both are used by iris matching algorithms.  Values below ~1.8
     *   risk clipping the outer limbus; values above ~3.0 introduce too much
     *   eyelid/skin which degrades focus scoring and wastes capture pixels.
     *
     * When all 5 iris landmarks are available the crop box is derived from the
     * actual landmark bounding box (more accurate than using diameter alone).
     * Falling back to `diameter * paddingFactor` when landmarks are absent
     * maintains compatibility with reduced-confidence detections.
     *
     * minSize = 32 px:
     *   Below 32 px the crop is too small for reliable Laplacian focus scoring
     *   (see qualityMetrics.ts computeFocusScore).  This floor is applied after
     *   the landmark-based sizing so it only activates for very distant/small iris.
     */
    private computeIrisCropBox(
        iris: { center: { x: number, y: number }, diameter: number, landmarks?: { x: number, y: number }[] },
        frameWidth: number,
        frameHeight: number,
        paddingFactor: number = 2.4
    ): { x: number, y: number, size: number } {
        const { landmarks, center, diameter } = iris;

        // If we have the 5 iris landmarks, build a generous box to capture full iris
        let size: number;
        let cx: number;
        let cy: number;

        if (landmarks && landmarks.length >= 5) {
            const xs = landmarks.map(p => p.x);
            const ys = landmarks.map(p => p.y);
            const minX = Math.min(...xs);
            const maxX = Math.max(...xs);
            const minY = Math.min(...ys);
            const maxY = Math.max(...ys);
            const w = maxX - minX;
            const h = maxY - minY;
            const bbox = Math.max(w, h);
            size = bbox * paddingFactor;
            // Ensure we capture full iris with generous padding
            size = Math.max(size, diameter * 2.4);
            cx = (minX + maxX) / 2;
            cy = (minY + maxY) / 2;
        } else {
            size = diameter * paddingFactor;
            cx = center.x;
            cy = center.y;
        }

        const minSize = 32;
        size = Math.max(minSize, size);

        let x = Math.floor(cx - size / 2);
        let y = Math.floor(cy - size / 2);

        // Clamp to frame bounds
        if (x < 0) x = 0;
        if (y < 0) y = 0;
        if (x + size > frameWidth) x = Math.max(0, frameWidth - size);
        if (y + size > frameHeight) y = Math.max(0, frameHeight - size);

        return { x, y, size: Math.floor(size) };
    }
}

export const faceLandmarkerDetector = new FaceLandmarkerDetector();
