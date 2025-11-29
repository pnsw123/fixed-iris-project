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

    // Raw data
    rawBrightness: number;
    centeringRatio: number;

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
    private isInitialized = false;

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

            return {
                irisDetected: false,
                irisCenter: { x: 0, y: 0 },
                irisDiameter: 0,
                distance: { score: 0, status: 'fail', feedback: 'No face detected' },
                lighting: { score: 0, status: 'fail', feedback: 'No face detected' },
                centering: { score: 0, status: 'fail', feedback: 'No face detected' },
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
        // More permissive so users can capture without being too close.
        const targetDiameterMin = analysisCanvas.height * 0.06; // 6% of frame height
        const targetDiameterMax = analysisCanvas.height * 0.18; // 18% of frame height
        const targetDiameterIdeal = (targetDiameterMin + targetDiameterMax) / 2;

        let distanceScore = 0;
        let distanceStatus: 'ok' | 'warn' | 'fail' = 'fail';
        let distanceFeedback = '';

        if (smoothedDiameter >= targetDiameterMin && smoothedDiameter <= targetDiameterMax) {
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

        // 3. Centering Score (distance from frame center)
        const frameCenterX = analysisCanvas.width / 2;
        const frameCenterY = analysisCanvas.height / 2;
        const distFromCenter = Math.hypot(smoothedCenterX - frameCenterX, smoothedCenterY - frameCenterY);
        const maxDist = Math.min(analysisCanvas.width, analysisCanvas.height) / 2;
        const centeringRatio = Math.min(1.0, distFromCenter / maxDist);

        // Convert to 0-100 score (0 = edge, 100 = center)
        const centeringScore = Math.max(0, (1 - centeringRatio) * 100);
        const centeringStatus: 'ok' | 'warn' | 'fail' = 
            centeringScore >= 60 ? 'ok' : centeringScore >= 40 ? 'warn' : 'fail'; // RELAXED: 70/50 → 60/40
        const centeringFeedback = 
            centeringScore >= 60 ? 'Well centered' : 'Center your eye';

        // 4. Lighting Score (face brightness analysis)
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

            rawBrightness: smoothedBrightness,
            centeringRatio,

            landmarks: result.landmarks,
            irisCropBox: result.irisCropBox
        };
    }
}

// Export singleton
export const qualityAnalyzer = new QualityAnalyzer();
