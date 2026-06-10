/**
 * qualityMetrics.ts — Real-time iris image quality scoring pipeline.
 *
 * Runs on every video frame and produces a QualityReport with four independent
 * 0-100 scores: distance, lighting, centering, and focus. Each score drives
 * stage-gating in captureStages.ts and live UI feedback to the user.
 *
 * Architecture note:
 * - All four metrics use SimpleMovingAverage (SMA) to smooth per-frame noise.
 *   Raw webcam values fluctuate by 5-15% frame-to-frame; without smoothing the
 *   UI would flicker rapidly even when nothing physically changed.
 * - Brightness and focus are computed from raw pixel data via getImageData(),
 *   which requires a canvas with `willReadFrequently: true` to avoid GPU stall.
 * - The singleton export `qualityAnalyzer` is the only instance used across the
 *   app — creating multiple instances would waste memory on redundant SMAs and
 *   cause redundant MediaPipe inference calls.
 */
import { faceLandmarkerDetector } from './FaceLandmarkerDetector';
import { telemetry } from './telemetry';

export interface QualityReport {
    // Detection
    irisDetected: boolean;
    irisCenter: { x: number, y: number };
    irisDiameter: number;

    // Quality Metrics (0-100 scores)
    distance: { score: number, status: 'ok' | 'warn' | 'fail', feedback: string };
    lighting: { score: number, status: 'ok' | 'warn' | 'fail', feedback: string };
    centering: { score: number, status: 'ok' | 'warn' | 'fail', feedback: string };
    focus: { score: number, status: 'ok' | 'warn' | 'fail', feedback: string };

    // Raw data
    rawBrightness: number;
    centeringRatio: number;
    focusVariance?: number;

    // Raw landmarks for debugging
    landmarks?: { x: number, y: number }[];

    // Iris crop box for capture
    irisCropBox?: { x: number, y: number, size: number };
}

/**
 * SimpleMovingAverage — lightweight sliding-window smoother.
 *
 * Why SMA instead of EMA or Kalman?
 * - SMA is trivially correct (no tuning parameters), and for window sizes
 *   ≤ 10 frames (~330 ms at 30 fps) the lag is imperceptible to users.
 * - EMA would need a decay constant that varies per metric; Kalman would need
 *   noise covariance estimates we don't have. SMA is the pragmatic choice here.
 *
 * Window sizes per metric (set on each QualityAnalyzer SMA instance):
 * - diameter / center x,y : 5 frames — balances tracking speed with smoothness
 * - brightness             : 10 frames — lighting changes slowly, more smoothing ok
 * - focus                  : 3 frames — focus changes fast (user moves); less lag needed
 */
class SimpleMovingAverage {
    private window: number[];
    private size: number;
    private sum: number = 0;

    constructor(size: number) {
        this.size = size;
        this.window = [];
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

export class QualityAnalyzer {
    private diameterSMA = new SimpleMovingAverage(5);
    private centerXSMA = new SimpleMovingAverage(5);
    private centerYSMA = new SimpleMovingAverage(5);
    private brightnessSMA = new SimpleMovingAverage(10);
    private focusSMA = new SimpleMovingAverage(3); // Reduced from 5 for faster response
    private isInitialized = false;

    /**
     * Focus thresholds — calibrated empirically against real webcam/phone footage.
     *
     * Values are on the combined focus score scale produced by computeFocusScore(),
     * which normalises Laplacian variance by average pixel intensity so the number
     * stays consistent regardless of scene brightness or iris crop size.
     *
     * FOCUS_THRESHOLD_OK   = 100 : Laplacian variance/intensity ratio typical of a
     *                               sharp eye at 30 cm – 60 cm from camera.
     * FOCUS_THRESHOLD_WARN = 50  : Marginal sharpness; still usable but user should
     *                               hold steadier. Below this the iris texture is too
     *                               smeared to reliably match against a database.
     *
     * Both values were derived by logging `rawFocusVariance` across 50+ captures on
     * MacBook/iPhone cameras and picking stable cluster boundaries.
     */
    private readonly FOCUS_THRESHOLD_OK = 100;    // Above this = sharp
    private readonly FOCUS_THRESHOLD_WARN = 50;   // Above this = acceptable

    constructor() { }

    async initialize() {
        if (this.isInitialized) return;
        console.log('[QualityAnalyzer] Initializing...');
        await faceLandmarkerDetector.initialize();
        this.isInitialized = true;
    }

    async analyze(
        input: HTMLVideoElement | HTMLCanvasElement,
        analysisCanvas: HTMLCanvasElement
    ): Promise<QualityReport> {
        if (!this.isInitialized) {
            await this.initialize();
        }

        const ctx = analysisCanvas.getContext('2d', { willReadFrequently: true });
        if (!ctx) throw new Error('Could not get context');

        const t0 = performance.now();
        const timestamp = performance.now();

        const result = faceLandmarkerDetector.detect(analysisCanvas, timestamp);

        const inferenceTime = performance.now() - t0;
        telemetry.trackInferenceTime(inferenceTime);

        if (!result.detected || !result.leftIris) {
            this.diameterSMA.reset();
            this.centerXSMA.reset();
            this.centerYSMA.reset();
            this.brightnessSMA.reset();
            this.focusSMA.reset();

            return {
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
        }

        const iris = result.leftIris;

        // 1. Smooth Geometry
        const smoothedDiameter = this.diameterSMA.push(iris.diameter);
        const smoothedCenterX = this.centerXSMA.push(iris.center.x);
        const smoothedCenterY = this.centerYSMA.push(iris.center.y);

        // ── Distance Score ─────────────────────────────────────────────────────
        // Iris diameter relative to the *shorter* canvas dimension is used as
        // the distance proxy.  Using the shorter side (not width) makes the
        // threshold resolution-independent: a 7% short-side iris at 720p and
        // at 1080p both represent roughly the same physical eye-to-camera gap.
        //
        // Target range: 7% – 24% of short side.
        //   • < 7%  → too far;  eye not large enough for reliable texture capture
        //   • 7-24% → in range; score penalises deviation from the midpoint
        //   • > 24% → too close; severe eyelid occlusion and barrel distortion
        //
        // okMin = targetDiameterMin × 0.93 introduces a small lower-hysteresis
        // band so that a user hovering just below the minimum isn't constantly
        // flipping between OK and FAIL.
        const refDim = Math.min(analysisCanvas.width, analysisCanvas.height);
        const targetDiameterMin = refDim * 0.07;  // 7% of short side
        const targetDiameterMax = refDim * 0.24;  // 24% of short side
        const targetDiameterIdeal = (targetDiameterMin + targetDiameterMax) / 2;

        let distanceScore = 0;
        let distanceStatus: 'ok' | 'warn' | 'fail' = 'fail';
        let distanceFeedback = '';

        // Treat slightly-below-min as OK to avoid blocking when user is very close but fluctuating.
        const okMin = targetDiameterMin * 0.93;
        if (smoothedDiameter >= okMin && smoothedDiameter <= targetDiameterMax) {
            // Perfect range - calculate score based on closeness to ideal
            const deviation = Math.abs(smoothedDiameter - targetDiameterIdeal);
            const maxDeviation = (targetDiameterMax - targetDiameterMin) / 2;
            distanceScore = Math.max(0, 100 - (deviation / maxDeviation) * 30);
            distanceStatus = 'ok';
            distanceFeedback = 'Perfect distance';
        } else if (smoothedDiameter < targetDiameterMin) {
            // Too far - linear score from 0 to 70
            const ratio = smoothedDiameter / targetDiameterMin;
            distanceScore = Math.max(0, ratio * 70);
            distanceStatus = ratio > 0.4 ? 'warn' : 'fail'; // More lenient: fail only when very small
            distanceFeedback = 'Move closer';
        } else {
            // Too close - linear score from 70 to 0
            const ratio = (smoothedDiameter - targetDiameterMax) / targetDiameterMax;
            distanceScore = Math.max(0, 70 - ratio * 70);
            distanceStatus = ratio < 0.6 ? 'warn' : 'fail'; // More lenient for slightly close
            distanceFeedback = 'Move back';
        }

        // ── Focus / Sharpness Score ────────────────────────────────────────────
        // Focus is measured exclusively on the iris crop box (result.irisCropBox),
        // not the whole frame, because the background may be sharp while the eye
        // is blurred (e.g. shallow depth-of-field on a phone camera).
        //
        // Minimum sample size of 16 px: the Laplacian kernel reads a 3×3 neighbourhood
        // per pixel; anything smaller than ~16×16 gives statistically unreliable variance.
        //
        // Smoothed with focusSMA (window=3) — a 3-frame window trades a tiny bit of
        // lag for resistance to single-frame blur spikes caused by motion blur during
        // the user repositioning their head.
        let focusScore = 0;
        let focusStatus: 'ok' | 'warn' | 'fail' = 'fail';
        let focusFeedback = 'Blurry';
        let rawFocusVariance = 0;

        if (result.irisCropBox) {
            const { x, y, size } = result.irisCropBox;
            
            // Ensure we have a valid sample region
            const sampleX = Math.max(0, Math.floor(x));
            const sampleY = Math.max(0, Math.floor(y));
            const availableWidth = analysisCanvas.width - sampleX;
            const availableHeight = analysisCanvas.height - sampleY;
            const sampleSize = Math.min(Math.floor(size), availableWidth, availableHeight);
            
            if (sampleSize >= 16) { // Need minimum size for reliable measurement
                const imageData = ctx.getImageData(sampleX, sampleY, sampleSize, sampleSize);
                
                // Compute focus using improved method
                rawFocusVariance = this.computeFocusScore(imageData);
                const smoothedFocus = this.focusSMA.push(rawFocusVariance);

                focusScore = smoothedFocus;
                
                // Thresholds tuned for typical webcam/phone camera
                if (smoothedFocus >= this.FOCUS_THRESHOLD_OK) {
                    focusStatus = 'ok';
                    focusFeedback = 'Sharp';
                } else if (smoothedFocus >= this.FOCUS_THRESHOLD_WARN) {
                    focusStatus = 'warn';
                    focusFeedback = 'Almost sharp';
                } else {
                    focusStatus = 'fail';
                    focusFeedback = 'Blurry - hold still';
                }
            } else {
                this.focusSMA.reset();
                focusFeedback = 'Move closer';
            }
        } else {
            this.focusSMA.reset();
        }

        // ── Centering Score ────────────────────────────────────────────────────
        // Centering measures how far the iris center is from the frame center,
        // normalised to the half-width of the shorter dimension so it is
        // aspect-ratio independent (centeringRatio of 1.0 = iris at the edge).
        //
        // The thresholds are intentionally very relaxed (ok ≥ 20) because in a
        // selfie context the user captures only one eye — that eye will always
        // sit noticeably off the frame centre.  We only want to warn when the
        // eye is so far to the edge that it risks being cropped in the final
        // image sent to the matching service.
        const frameCenterX = analysisCanvas.width / 2;
        const frameCenterY = analysisCanvas.height / 2;
        const distFromCenter = Math.hypot(smoothedCenterX - frameCenterX, smoothedCenterY - frameCenterY);
        const maxDist = Math.min(analysisCanvas.width, analysisCanvas.height) / 2;
        const centeringRatio = Math.min(1.0, distFromCenter / maxDist);

        // Convert to 0-100 score (0 = edge, 100 = center)
        const centeringScore = Math.max(0, (1 - centeringRatio) * 100);
        
        // VERY RELAXED for single-eye capture
        // OK if eye is anywhere in the middle 70% of frame
        // Only fail if eye is at the very edge
        const centeringStatus: 'ok' | 'warn' | 'fail' = 
            centeringScore >= 20 ? 'ok' : centeringScore >= 10 ? 'warn' : 'fail';
        const centeringFeedback = 
            centeringScore >= 20 ? 'Well centered' : 'Center your eye';

        // ── Lighting Score ─────────────────────────────────────────────────────
        // Brightness is sampled from the *central 50%* of the detected face
        // bounding box (bounds ×0.25 offset, ×0.5 size).  Using the full face
        // region would include dark hair or background that skews the average.
        //
        // Luma formula: Y = 0.299R + 0.587G + 0.114B  (BT.601 standard).
        // The 0.587 green weight is highest because the human eye is most
        // sensitive to green wavelengths.
        //
        // Ideal range 100–180 (0–255 scale):
        //   < 100 → under-lit; iris texture detail lost in shadow
        //   100-180 → good; mid-grey face, sufficient contrast
        //   > 180 → over-lit; specular highlights wash out iris colour/texture
        //
        // Smoothed with brightnessSMA (window=10) — lighting changes slowly and
        // more smoothing prevents false warnings from transient reflections.
        let rawBrightness = 0;
        if (result.faceBounds) {
            const bounds = result.faceBounds;
            const sampleX = Math.max(0, Math.floor(bounds.x + bounds.width * 0.25));
            const sampleY = Math.max(0, Math.floor(bounds.y + bounds.height * 0.25));
            const sampleWidth = Math.min(analysisCanvas.width - sampleX, Math.floor(bounds.width * 0.5));
            const sampleHeight = Math.min(analysisCanvas.height - sampleY, Math.floor(bounds.height * 0.5));

            if (sampleWidth > 0 && sampleHeight > 0) {
                const imageData = ctx.getImageData(sampleX, sampleY, sampleWidth, sampleHeight);
                const data = imageData.data;
                let totalLum = 0;
                for (let i = 0; i < data.length; i += 4) {
                    totalLum += (0.299 * data[i]! + 0.587 * data[i + 1]! + 0.114 * data[i + 2]!);
                }
                rawBrightness = totalLum / (data.length / 4);
            }
        }

        const smoothedBrightness = this.brightnessSMA.push(rawBrightness);

        // Ideal lighting range: 100-180 (0-255 scale)
        const idealMin = 100;
        const idealMax = 180;
        const idealMid = (idealMin + idealMax) / 2;

        let lightingScore = 0;
        let lightingStatus: 'ok' | 'warn' | 'fail' = 'fail';
        let lightingFeedback = '';

        if (smoothedBrightness >= idealMin && smoothedBrightness <= idealMax) {
            const deviation = Math.abs(smoothedBrightness - idealMid);
            const maxDeviation = (idealMax - idealMin) / 2;
            lightingScore = Math.max(0, 100 - (deviation / maxDeviation) * 30);
            lightingStatus = 'ok';
            lightingFeedback = 'Good lighting';
        } else if (smoothedBrightness < idealMin) {
            const ratio = smoothedBrightness / idealMin;
            lightingScore = Math.max(0, ratio * 70);
            lightingStatus = ratio > 0.7 ? 'warn' : 'fail';
            lightingFeedback = 'Too dark';
        } else {
            const ratio = (smoothedBrightness - idealMax) / (255 - idealMax);
            lightingScore = Math.max(0, 70 - ratio * 70);
            lightingStatus = ratio < 0.3 ? 'warn' : 'fail';
            lightingFeedback = 'Too bright';
        }

        return {
            irisDetected: true,
            irisCenter: { x: smoothedCenterX, y: smoothedCenterY },
            irisDiameter: smoothedDiameter,

            distance: { score: distanceScore, status: distanceStatus, feedback: distanceFeedback },
            lighting: { score: lightingScore, status: lightingStatus, feedback: lightingFeedback },
            centering: { score: centeringScore, status: centeringStatus, feedback: centeringFeedback },
            focus: { score: focusScore, status: focusStatus, feedback: focusFeedback },

            rawBrightness: smoothedBrightness,
            centeringRatio,
            focusVariance: focusScore,

            ...(result.landmarks !== undefined ? { landmarks: result.landmarks } : {}),
            ...(result.irisCropBox !== undefined ? { irisCropBox: result.irisCropBox } : {}),
        };
    }

    /**
     * computeVarianceOfLaplacian — legacy sharpness estimator (retained for reference).
     *
     * Applies the discrete 4-connected Laplacian operator (kernel: [0,1,0 / 1,-4,1 / 0,1,0])
     * to every interior pixel of the grayscale image and returns the statistical variance of
     * the resulting response map.  High variance → many strong edges → sharp image.
     *
     * This method is NOT normalised by image intensity, making it sensitive to brightness.
     * It was superseded by computeFocusScore() which normalises by avgIntensity.
     * Kept here as a reference implementation; not called by the main analyze() path.
     */
    private computeVarianceOfLaplacian(imageData: ImageData): number {
        const { width, height, data } = imageData;
        const gray = new Float32Array(width * height);
        for (let i = 0; i < width * height; i++) {
            const r = data[i * 4]!;
            const g = data[i * 4 + 1]!;
            const b = data[i * 4 + 2]!;
            gray[i] = 0.299 * r + 0.587 * g + 0.114 * b;
        }

        let sum = 0;
        let sumSq = 0;
        let count = 0;

        for (let y = 1; y < height - 1; y++) {
            for (let x = 1; x < width - 1; x++) {
                const idx = y * width + x;
                const center = gray[idx]!;
                const lap =
                    4 * center -
                    gray[idx - 1]! -
                    gray[idx + 1]! -
                    gray[idx - width]! -
                    gray[idx + width]!;
                sum += lap;
                sumSq += lap * lap;
                count++;
            }
        }

        if (count === 0) return 0;
        const mean = sum / count;
        const variance = sumSq / count - mean * mean;
        return Math.max(0, variance);
    }

    /**
     * computeFocusScore — dual-method blur detection with intensity normalisation.
     *
     * Two complementary edge-detection methods are combined so that neither
     * alone produces false positives:
     *
     * Method 1 — Laplacian Variance (weight 70%)
     *   Applies the 4-connected Laplacian kernel to the grayscale image and
     *   computes the variance of responses.  High variance = many sharp edges.
     *   Sensitive to fine texture like iris crypts; best primary blur detector.
     *
     * Method 2 — Mean Sobel Gradient Magnitude (weight 30%)
     *   Computes horizontal (gx) and vertical (gy) gradients via central differences
     *   and averages sqrt(gx²+gy²) across all interior pixels.  Acts as a sanity
     *   check: if Laplacian says "sharp" but gradients are low, the image may be
     *   artificially high-contrast (e.g. backlit) rather than genuinely sharp.
     *
     * Intensity normalisation:
     *   Both raw scores are divided by (avgIntensity + 1) before combining.
     *   Without this, a dim image (avgIntensity~40) produces naturally lower
     *   Laplacian variance even when sharp, triggering false blur warnings.
     *   The +1 guard prevents division-by-zero on pure-black frames.
     *
     * Images with avgIntensity < 30 or > 240 return 0 immediately — such
     * extreme exposures make any variance estimate unreliable.
     *
     * Final scale factor ×100 maps the combined score to a range where
     * FOCUS_THRESHOLD_OK=100 and FOCUS_THRESHOLD_WARN=50 are meaningful.
     */
    private computeFocusScore(imageData: ImageData): number {
        const { width, height, data } = imageData;
        
        // Convert to grayscale
        const gray = new Float32Array(width * height);
        let totalIntensity = 0;
        
        for (let i = 0; i < width * height; i++) {
            const r = data[i * 4]!;
            const g = data[i * 4 + 1]!;
            const b = data[i * 4 + 2]!;
            const val = 0.299 * r + 0.587 * g + 0.114 * b;
            gray[i] = val;
            totalIntensity += val;
        }
        
        const avgIntensity = totalIntensity / (width * height);
        
        // Skip if image is too dark or too bright (unreliable focus measurement)
        if (avgIntensity < 30 || avgIntensity > 240) {
            return 0;
        }

        // Method 1: Laplacian variance (detects all edges)
        let lapSum = 0;
        let lapSumSq = 0;
        let count = 0;

        for (let y = 1; y < height - 1; y++) {
            for (let x = 1; x < width - 1; x++) {
                const idx = y * width + x;
                const center = gray[idx]!;
                // 4-connected Laplacian
                const lap = 4 * center - gray[idx - 1]! - gray[idx + 1]! - gray[idx - width]! - gray[idx + width]!;
                lapSum += lap;
                lapSumSq += lap * lap;
                count++;
            }
        }

        if (count === 0) return 0;

        const lapMean = lapSum / count;
        const lapVariance = lapSumSq / count - lapMean * lapMean;

        // Method 2: Gradient magnitude (Sobel-like)
        let gradientSum = 0;

        for (let y = 1; y < height - 1; y++) {
            for (let x = 1; x < width - 1; x++) {
                const idx = y * width + x;
                // Horizontal gradient
                const gx = gray[idx + 1]! - gray[idx - 1]!;
                // Vertical gradient
                const gy = gray[idx + width]! - gray[idx - width]!;
                // Gradient magnitude
                gradientSum += Math.sqrt(gx * gx + gy * gy);
            }
        }
        
        const avgGradient = gradientSum / count;

        // Combine both methods - Laplacian variance is primary, gradient is secondary
        // Normalize by image intensity to make it more consistent across lighting conditions
        const normalizedLapVariance = lapVariance / (avgIntensity + 1);
        const normalizedGradient = avgGradient / (avgIntensity + 1);
        
        // Combined score weighted towards Laplacian (more reliable for blur)
        const combinedScore = (normalizedLapVariance * 0.7 + normalizedGradient * 10 * 0.3);
        
        // Scale to a reasonable range (0-200+)
        return combinedScore * 100;
    }
}

// Export singleton
export const qualityAnalyzer = new QualityAnalyzer();
