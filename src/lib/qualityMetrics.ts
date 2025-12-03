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

    // Focus thresholds - calibrated for real-world blur detection
    // These are normalized values (variance / image_intensity) to be size-independent
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
                distance: { score: 0, status: 'fail', feedback: 'No face detected' },
                lighting: { score: 0, status: 'fail', feedback: 'No face detected' },
                centering: { score: 0, status: 'fail', feedback: 'No face detected' },
                focus: { score: 0, status: 'fail', feedback: 'No face detected' },
                rawBrightness: 0,
                centeringRatio: 1,
                landmarks: undefined,
                irisCropBox: undefined
            };
        }

        const iris = result.leftIris;

        // 1. Smooth Geometry
        const smoothedDiameter = this.diameterSMA.push(iris.diameter);
        const smoothedCenterX = this.centerXSMA.push(iris.center.x);
        const smoothedCenterY = this.centerYSMA.push(iris.center.y);

        // 2. Distance Score (based on iris size relative to frame)
        // Require users to get closer, but base thresholds on the shorter side so portrait/landscape both work.
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

        // 3. Focus / sharpness - IMPROVED
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

        // 4. Centering Score (distance from frame center)
        const frameCenterX = analysisCanvas.width / 2;
        const frameCenterY = analysisCanvas.height / 2;
        const distFromCenter = Math.hypot(smoothedCenterX - frameCenterX, smoothedCenterY - frameCenterY);
        const maxDist = Math.min(analysisCanvas.width, analysisCanvas.height) / 2;
        const centeringRatio = Math.min(1.0, distFromCenter / maxDist);

        // Convert to 0-100 score (0 = edge, 100 = center)
        const centeringScore = Math.max(0, (1 - centeringRatio) * 100);
        // VERY RELAXED thresholds - only fail if iris is way off to the edge
        const centeringStatus: 'ok' | 'warn' | 'fail' = 
            centeringScore >= 35 ? 'ok' : centeringScore >= 20 ? 'warn' : 'fail';
        const centeringFeedback = 
            centeringScore >= 35 ? 'Well centered' : 'Center your eye';

        // 5. Lighting Score (face brightness analysis)
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
                    totalLum += (0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]);
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

            landmarks: result.landmarks,
            irisCropBox: result.irisCropBox
        };
    }

    private computeVarianceOfLaplacian(imageData: ImageData): number {
        const { width, height, data } = imageData;
        const gray = new Float32Array(width * height);
        for (let i = 0; i < width * height; i++) {
            const r = data[i * 4];
            const g = data[i * 4 + 1];
            const b = data[i * 4 + 2];
            gray[i] = 0.299 * r + 0.587 * g + 0.114 * b;
        }

        let sum = 0;
        let sumSq = 0;
        let count = 0;

        for (let y = 1; y < height - 1; y++) {
            for (let x = 1; x < width - 1; x++) {
                const idx = y * width + x;
                const center = gray[idx];
                const lap =
                    4 * center -
                    gray[idx - 1] -
                    gray[idx + 1] -
                    gray[idx - width] -
                    gray[idx + width];
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
     * Improved focus scoring that combines multiple edge detection methods
     * for more accurate blur detection
     */
    private computeFocusScore(imageData: ImageData): number {
        const { width, height, data } = imageData;
        
        // Convert to grayscale
        const gray = new Float32Array(width * height);
        let totalIntensity = 0;
        
        for (let i = 0; i < width * height; i++) {
            const r = data[i * 4];
            const g = data[i * 4 + 1];
            const b = data[i * 4 + 2];
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
                const center = gray[idx];
                // 4-connected Laplacian
                const lap = 4 * center - gray[idx - 1] - gray[idx + 1] - gray[idx - width] - gray[idx + width];
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
                const gx = gray[idx + 1] - gray[idx - 1];
                // Vertical gradient
                const gy = gray[idx + width] - gray[idx - width];
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
