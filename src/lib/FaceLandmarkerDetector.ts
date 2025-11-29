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
    private faceLandmarker: FaceLandmarker | null = null;
    private isInitializing = false;

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
                    delegate: 'GPU',
                },
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

            // Get iris center by averaging all iris landmarks (more stable than center alone)
            const centerX = irisPixels.reduce((s, p) => s + p.x, 0) / irisPixels.length;
            const centerY = irisPixels.reduce((s, p) => s + p.y, 0) / irisPixels.length;

            // Calculate diameter from boundary points
            const top = irisPixels[IRIS_LANDMARKS.TOP].y;
            const bottom = irisPixels[IRIS_LANDMARKS.BOTTOM].y;
            const left = irisPixels[IRIS_LANDMARKS.LEFT].x;
            const right = irisPixels[IRIS_LANDMARKS.RIGHT].x;

            const verticalDiameter = Math.abs(bottom - top);
            const horizontalDiameter = Math.abs(right - left);
            let diameter = (verticalDiameter + horizontalDiameter) / 2;

            // VALIDATION: Iris dimensions should be reasonable, but do not drop detections.
            // We clamp instead of rejecting so the UI can still show a target and ask the user to adjust.
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
