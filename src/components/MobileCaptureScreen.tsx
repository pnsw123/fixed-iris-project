/**
 * MobileCaptureScreen.tsx — Primary iris capture screen; orchestrates camera,
 * real-time quality analysis, focus-lock, and auto-capture countdown.
 *
 * ## Responsibility
 * This component is the single entry point for all iris image acquisition.
 * It owns the full lifecycle from camera permission request through to a
 * validated, cropped CaptureData payload handed to the parent.
 *
 * ## Capture state machine
 * ```
 * init → camera-start → analysis-loop ──► focus-lock (800 ms)
 *                                                │
 *                                      ┌─── conditions good? ───┐
 *                                      │  (focus + distance +   │
 *                                      │   centering + light)   │
 *                                      ▼                        │
 *                              countdown 3-2-1                  │ (conditions
 *                                      │                        │  degrade)
 *                                      ▼                  abort countdown ◄┘
 *                              capture & stop camera
 * ```
 * Countdown aborts immediately if any quality condition degrades — prevents
 * blurry captures when the user blinks or moves mid-countdown.
 *
 * ## Non-obvious design decisions
 * - **Focus lock via ref, not state**: `focusLockAccumRef` accumulates elapsed
 *   milliseconds instead of frame counts so the threshold is time-stable across
 *   devices with different rAF rates. Using a ref (not state) avoids triggering
 *   a re-render on every frame tick.
 * - **Analysis capped at 10 fps** (100 ms gate inside a `requestAnimationFrame`
 *   loop): balances MediaPipe accuracy against battery/thermal on mobile.
 * - **Coordinate mapping**: iris center is detected on a downscaled analysis
 *   canvas (480×640 or 640×480 depending on orientation). Coordinates are mapped
 *   back through three transforms — analysis → native video → CSS display —
 *   and then mirrored horizontally to match the `scaleX(-1)` front-camera CSS.
 * - **Separate analysis canvas** (`analysisCanvasRef`): never shown in DOM;
 *   created with `{ willReadFrequently: true }` to keep `getImageData` on the
 *   CPU path and avoid GPU readback stalls.
 * - **Debug mode** (via `useDebugMode` hook / `?debug=1` URL param): renders a
 *   lime dot at the iris center and a red rectangle around the crop box directly
 *   on the analysis canvas, visible as a picture-in-picture overlay.
 *
 * ## Props
 * - `onBack` — called when the user taps the back arrow; parent returns to landing
 * - `onCaptureComplete(captureData: CaptureData)` — called once after a successful
 *   capture; payload contains base-64 cropped image, iris coordinates, crop size,
 *   and iris radius for downstream AI processing
 */
'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ArrowLeft, AlertCircle } from 'lucide-react';
import { qualityAnalyzer, QualityReport } from '@/lib/qualityMetrics';
import { initializePhoneAngle, getAngleState, stopPhoneAngle } from '@/lib/phoneAngle';
import { audioFeedback } from '@/lib/audioFeedback';
import { telemetry } from '@/lib/telemetry';
import { useDebugMode } from '@/hooks/useDebugMode';
import IrisTarget from '@/components/ui/IrisTarget';
import StatusIndicator from '@/components/ui/StatusIndicator';

type CameraErrorState = 'permission_denied' | 'no_device' | 'generic_error' | null;

export interface CaptureData {
    imageData: string;
    irisCoordinates: { x: number; y: number } | null;
    cropSize: number;
    irisRadius: number | null;
}

export default function MobileCaptureScreen({
    onBack,
    onCaptureComplete
}: {
    onBack: () => void;
    onCaptureComplete: (captureData: CaptureData) => void;
}) {
    // --- Refs ---
    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const analysisCanvasRef = useRef<HTMLCanvasElement>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const requestRef = useRef<number | null>(null);
    const lastAnalysisTime = useRef<number>(0);
    const countdownIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const stableGoodFramesRef = useRef<number>(0);
    const focusLockAccumRef = useRef<number>(0);
    const lastFocusTimestampRef = useRef<number>(0);

    // --- State ---
    const isDebug = useDebugMode();
    const [isInitializing, setIsInitializing] = useState(true);
    const [cameraError, setCameraError] = useState<CameraErrorState>(null);
    const [errorMessage, setErrorMessage] = useState<string>('');
    const [currentReport, setCurrentReport] = useState<QualityReport | null>(null);
    const [countdown, setCountdown] = useState<number | null>(null);
    const [guidanceMessage, setGuidanceMessage] = useState<string>('Align one eye in the circle');
    const [screenIrisPosition, setScreenIrisPosition] = useState<{ x: number, y: number } | null>(null);
    const [screenIrisDiameter, setScreenIrisDiameter] = useState<number>(120);
    const [isCapturing, setIsCapturing] = useState(false); // Prevent multiple captures
    const [isFocusLocked, setIsFocusLocked] = useState(false);
    const [phoneAngleOk, setPhoneAngleOk] = useState(false);
    const [phoneAngleAvailable, setPhoneAngleAvailable] = useState(false);

    // --- Compute guidance message ---
    const computeGuidance = useCallback((
        report: QualityReport | null,
        focusLocked: boolean,
        angleOk: boolean,
        angleAvailable: boolean
    ): string => {
        if (!report || !report.irisDetected) {
            return 'Align one eye in the circle';
        }

        if (!report.irisCropBox) {
            return 'Hold steady...';
        }

        // Priority-based guidance
        if (report.focus.status === 'fail') {
            return 'Image is blurry — hold still to focus';
        }
        if (report.focus.status === 'warn') {
            return 'Almost sharp — keep still...';
        }
        if (!focusLocked) {
            return 'Perfect focus. Hold still...';
        }
        // Phone angle check: only guide if orientation API is available and angle is wrong
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

        // All good
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
    }, [countdown]);

    // --- Camera Control ---
    const startCamera = useCallback(async () => {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error('Camera API not available');
        }

        const constraints: MediaStreamConstraints = {
            video: {
                facingMode: 'user',
                width: { ideal: 1920 },
                height: { ideal: 1080 },
                frameRate: { ideal: 30 }
            },
            audio: false
        };

        try {
            const stream = await navigator.mediaDevices.getUserMedia(constraints);
            streamRef.current = stream;

            if (videoRef.current) {
                videoRef.current.srcObject = stream;
                await new Promise<void>((resolve) => {
                    if (!videoRef.current) return resolve();
                    videoRef.current.onloadedmetadata = () => {
                        videoRef.current?.play().then(resolve).catch(resolve);
                    };
                });
            }
        } catch (err) {
            if (err instanceof DOMException) {
                if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                    throw new Error('PERMISSION_DENIED');
                } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
                    throw new Error('NO_DEVICE');
                }
            }
            throw err;
        }
    }, []);

    const stopCamera = useCallback(() => {
        if (streamRef.current) {
            streamRef.current.getTracks().forEach(track => track.stop());
            streamRef.current = null;
        }
        if (videoRef.current) {
            videoRef.current.srcObject = null;
        }
    }, []);

    const handleCameraError = useCallback((err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        if (msg === 'PERMISSION_DENIED') {
            setCameraError('permission_denied');
            setErrorMessage('Camera permission denied. Please allow camera access in your browser settings.');
        } else if (msg === 'NO_DEVICE') {
            setCameraError('no_device');
            setErrorMessage('No front camera found on this device.');
        } else {
            setCameraError('generic_error');
            setErrorMessage(`Camera error: ${msg}`);
        }
    }, []);

    // --- Analysis Loop ---
    const processFrame = useCallback(async () => {
        if (!videoRef.current || !analysisCanvasRef.current) return;

        const video = videoRef.current;
        const canvas = analysisCanvasRef.current;

        if (video.readyState < 2) return;

        // Match analysis canvas orientation to the camera to avoid aspect warping on portrait.
        const baseShort = 480;
        const baseLong = 640;
        const isPortrait = video.videoHeight > video.videoWidth;
        const analysisWidth = isPortrait ? baseShort : baseLong;
        const analysisHeight = isPortrait ? baseLong : baseShort;
        const scale = Math.min(analysisWidth / video.videoWidth, analysisHeight / video.videoHeight);
        const targetWidth = Math.floor(video.videoWidth * scale);
        const targetHeight = Math.floor(video.videoHeight * scale);

        if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
            canvas.width = targetWidth;
            canvas.height = targetHeight;
        }

        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        if (!ctx) return;

        ctx.save();
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        ctx.restore();

        try {
            const report = await qualityAnalyzer.analyze(canvas, canvas);

            // Only draw debug overlays in debug mode
            if (isDebug && report.irisDetected) {
                if (report.irisCenter) {
                    ctx.fillStyle = 'lime';
                    ctx.beginPath();
                    ctx.arc(report.irisCenter.x, report.irisCenter.y, 3, 0, 2 * Math.PI);
                    ctx.fill();
                }

                if (report.irisCropBox) {
                    const { x, y, size } = report.irisCropBox;
                    ctx.strokeStyle = 'red';
                    ctx.lineWidth = 2;
                    ctx.strokeRect(x, y, size, size);
                }
            }

            // Focus lock accumulation
            const nowTs = performance.now();
            const lastTs = lastFocusTimestampRef.current || nowTs;
            const deltaMs = nowTs - lastTs;
            lastFocusTimestampRef.current = nowTs;

            if (report.focus.status === 'ok') {
                focusLockAccumRef.current += deltaMs;
            } else {
                focusLockAccumRef.current = 0;
            }

            const FOCUS_LOCK_MS = 800;
            const locked = focusLockAccumRef.current >= FOCUS_LOCK_MS;
            if (locked !== isFocusLocked) {
                setIsFocusLocked(locked);
            }

            if (!report.irisDetected) {
                focusLockAccumRef.current = 0;
                if (isFocusLocked) setIsFocusLocked(false);
            }

            // Phone angle check
            const angleResult = getAngleState();
            const isAngleOk = angleResult.state === 'optimal' || angleResult.state === 'unavailable';
            const isAngleAvailable = angleResult.state !== 'unavailable';
            setPhoneAngleOk(isAngleOk);
            setPhoneAngleAvailable(isAngleAvailable);

            setCurrentReport(report);
            setGuidanceMessage(computeGuidance(report, locked, isAngleOk, isAngleAvailable));

            // Convert iris position from analysis canvas to screen coordinates
            if (report.irisDetected && report.irisCenter && videoRef.current) {
                const video = videoRef.current;
                const rect = video.getBoundingClientRect();
                const displayWidth = rect.width;
                const displayHeight = rect.height;

                // Account for object-fit: cover cropping. Compute rendered frame size and offsets.
                const videoAspect = video.videoWidth / video.videoHeight;
                const displayAspect = displayWidth / displayHeight;
                const scaleToCover = videoAspect > displayAspect
                    ? displayHeight / video.videoHeight
                    : displayWidth / video.videoWidth;
                const renderWidth = video.videoWidth * scaleToCover;
                const renderHeight = video.videoHeight * scaleToCover;
                const offsetX = (renderWidth - displayWidth) / 2;
                const offsetY = (renderHeight - displayHeight) / 2;

                // Map analysis coords -> native video -> rendered frame -> screen
                const nativeX = report.irisCenter.x * (video.videoWidth / canvas.width);
                const nativeY = report.irisCenter.y * (video.videoHeight / canvas.height);
                const screenX = (nativeX * scaleToCover) - offsetX;
                const screenY = (nativeY * scaleToCover) - offsetY;
                const screenDiameter = report.irisDiameter * (scaleToCover * video.videoWidth / canvas.width);

                // Mirror horizontally to match the mirrored video element
                const mirroredX = displayWidth - screenX;

                // Remove aggressive camera offset that was pushing the target into hair
                setScreenIrisPosition({ x: mirroredX, y: screenY });
                setScreenIrisDiameter(screenDiameter);
            } else {
                setScreenIrisPosition(null);
            }

            // Auto-countdown when conditions are consistently good
            const isGoodForCountdown =
                report.irisDetected &&
                !!report.irisCropBox &&
                report.focus.status === 'ok' &&
                locked &&
                report.distance.status === 'ok' && // Only start countdown when user is close enough
                report.lighting.status !== 'fail' &&
                isAngleOk; // Phone angle must be correct (or unavailable = pass-through)

            if (isGoodForCountdown) {
                stableGoodFramesRef.current += 1;
            } else {
                stableGoodFramesRef.current = 0;

                // CRITICAL FIX: Immediately abort countdown if conditions are no longer good
                // This ensures closing eyes or moving away stops the countdown instantly
                if (countdownIntervalRef.current) {
                    clearInterval(countdownIntervalRef.current);
                    countdownIntervalRef.current = null;
                    setCountdown(null);
                }
            }

            // Require a few consecutive good frames to avoid flicker
            const STABLE_GOOD_FRAMES = 5; // ~0.5s at 100ms analysis cadence

            if (
                isGoodForCountdown &&
                stableGoodFramesRef.current >= STABLE_GOOD_FRAMES &&
                countdown === null &&
                !isCapturing &&
                !countdownIntervalRef.current
            ) {
                setCountdown(3);
                let count = 3;
                countdownIntervalRef.current = setInterval(() => {
                    count--;
                    setCountdown(count);
                    if (count <= 0) {
                        if (countdownIntervalRef.current) {
                            clearInterval(countdownIntervalRef.current);
                            countdownIntervalRef.current = null;
                        }
                        setCountdown(-1); // Special value to trigger capture
                    }
                }, 1000);
            }

        } catch (err) {
            console.warn('Analysis failed:', err);
        }
    }, [isDebug, countdown, computeGuidance, isCapturing, isFocusLocked, phoneAngleOk, phoneAngleAvailable]);

    const startAnalysisLoop = useCallback(() => {

        // Mutable ref allows loop and loopRef.schedule to mutually reference each other
        const loopRef = { schedule: () => {} };

        const loop = async () => {
            if (!videoRef.current || !analysisCanvasRef.current) {
                loopRef.schedule();
                return;
            }

            const now = performance.now();
            if (now - lastAnalysisTime.current >= 100) {
                lastAnalysisTime.current = now;
                await processFrame();
            }

            loopRef.schedule();
        };

        // Wraps async fn so requestAnimationFrame receives a void-returning fn
        loopRef.schedule = () => { requestRef.current = requestAnimationFrame(() => { void loop(); }); };
        loopRef.schedule();
    }, [processFrame]);

    const stopAnalysisLoop = useCallback(() => {
        if (requestRef.current) {
            cancelAnimationFrame(requestRef.current);
            requestRef.current = null;
        }
    }, []);

    // --- Capture ---
    const performCapture = useCallback(async () => {
        if (!videoRef.current || !canvasRef.current || !currentReport) {
            setIsCapturing(false);
            return;
        }

        if (!currentReport.irisDetected || !currentReport.irisCropBox) {
            console.warn('[Capture] No iris detected or no crop box');
            setIsCapturing(false);
            return;
        }

        const FOCUS_OK_THRESHOLD = 140; // Match qualityMetrics focus OK threshold
        const BURST_FRAMES = 6;
        const BURST_INTERVAL_MS = 40;


        const video = videoRef.current;
        const canvas = canvasRef.current;
        const { x, y, size } = currentReport.irisCropBox;
        const { x: irisX_ac, y: irisY_ac } = currentReport.irisCenter;

        const analysisCanvas = analysisCanvasRef.current;
        if (!analysisCanvas) {
            setIsCapturing(false);
            return;
        }

        // Map analysis crop box to native video coordinates (video.drawImage uses intrinsic size).
        const scaleX = video.videoWidth / analysisCanvas.width;
        const scaleY = video.videoHeight / analysisCanvas.height;

        // Transform iris center to video coordinates
        const irisX_video = irisX_ac * scaleX;
        const irisY_video = irisY_ac * scaleY;

        // Transform crop box to video coordinates
        let cropX = x * scaleX;
        let cropY = y * scaleY;
        let cropSize = size * ((scaleX + scaleY) / 2);

        // Clamp crop inside the video bounds and ensure minimum size
        const MIN_CROP_SIZE = 64;
        cropSize = Math.max(MIN_CROP_SIZE, cropSize);
        if (cropX < 0) cropX = 0;
        if (cropY < 0) cropY = 0;
        if (cropX + cropSize > video.videoWidth) cropX = Math.max(0, video.videoWidth - cropSize);
        if (cropY + cropSize > video.videoHeight) cropY = Math.max(0, video.videoHeight - cropSize);

        // Compute iris position within crop
        const in_crop_y = irisY_video - cropY;
        let in_crop_x = irisX_video - cropX;

        // Account for horizontal flip (selfie camera)
        in_crop_x = cropSize - in_crop_x;

        // Transform iris diameter to crop coordinates
        const irisDiameter_ac = currentReport.irisDiameter; // Analysis canvas coordinates

        // CRITICAL: MediaPipe's iris landmarks only detect inner iris boundary, not the full visible iris.
        // The visible colored iris is typically ~1.6x larger than MediaPipe's detected boundary.
        // This scale factor was determined empirically to match actual iris extent while avoiding over-large prompts.
        const IRIS_SCALE_FACTOR = 1.6;

        const irisDiameter_video = irisDiameter_ac * ((scaleX + scaleY) / 2) * IRIS_SCALE_FACTOR;
        const irisDiameter_crop = irisDiameter_video; // Same scale as crop (1:1 copy from video)
        const irisRadius_crop = irisDiameter_crop / 2;

        // Validate iris is within crop bounds (with 5% margin)
        const isValid =
            in_crop_x > cropSize * 0.05 &&
            in_crop_x < cropSize * 0.95 &&
            in_crop_y > cropSize * 0.05 &&
            in_crop_y < cropSize * 0.95;


        canvas.width = cropSize;
        canvas.height = cropSize;

        const ctx = canvas.getContext('2d');
        if (!ctx) {
            setIsCapturing(false);
            return;
        }

        const computeSharpness = (imageData: ImageData) => {
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
            for (let yy = 1; yy < height - 1; yy++) {
                for (let xx = 1; xx < width - 1; xx++) {
                    const idx = yy * width + xx;
                    const center = gray[idx]!;
                    const lap = 4 * center - gray[idx - 1]! - gray[idx + 1]! - gray[idx - width]! - gray[idx + width]!;
                    sum += lap;
                    sumSq += lap * lap;
                    count++;
                }
            }
            if (count === 0) return 0;
            const mean = sum / count;
            const variance = sumSq / count - mean * mean;
            return Math.max(0, variance);
        };

        const captureFrame = () => {
            ctx.drawImage(video, cropX, cropY, cropSize, cropSize, 0, 0, cropSize, cropSize);

            const tempCanvas = document.createElement('canvas');
            tempCanvas.width = cropSize;
            tempCanvas.height = cropSize;
            const tempCtx = tempCanvas.getContext('2d');
            if (!tempCtx) {
                throw new Error('Cannot get temp canvas context');
            }

            tempCtx.save();
            tempCtx.scale(-1, 1);
            tempCtx.drawImage(canvas, -cropSize, 0);
            tempCtx.restore();

            const imageData = tempCtx.getImageData(0, 0, cropSize, cropSize);
            const sharpness = computeSharpness(imageData);
            const imageDataUrl = tempCanvas.toDataURL('image/jpeg', 0.95);

            return { imageDataUrl, sharpness };
        };

        let bestFrame: { imageDataUrl: string; sharpness: number } | null = null;
        for (let i = 0; i < BURST_FRAMES; i++) {
            const frame = captureFrame();
            if (!bestFrame || frame.sharpness > bestFrame.sharpness) {
                bestFrame = frame;
            }
            if (i < BURST_FRAMES - 1) {
                await new Promise((resolve) => setTimeout(resolve, BURST_INTERVAL_MS));
            }
        }

        if (!bestFrame || bestFrame.sharpness < FOCUS_OK_THRESHOLD) {
            console.warn('[Capture] Burst too blurry - aborting capture', {
                bestSharpness: bestFrame?.sharpness ?? 0,
                threshold: FOCUS_OK_THRESHOLD
            });
            setCountdown(null);
            setIsCapturing(false);
            setGuidanceMessage('Too blurry — hold still to focus');
            return;
        }


        // Prepare capture data with coordinates and iris radius
        const captureData: CaptureData = {
            imageData: bestFrame.imageDataUrl,
            irisCoordinates: isValid ? { x: in_crop_x, y: in_crop_y } : null,
            cropSize,
            irisRadius: isValid ? irisRadius_crop : null
        };


        telemetry.logSummary();

        // Stop analysis loop and camera
        stopAnalysisLoop();
        stopCamera();
        onCaptureComplete(captureData);
    }, [currentReport, stopCamera, stopAnalysisLoop, onCaptureComplete]);

    // Trigger capture when countdown reaches -1
    useEffect(() => {
        if (countdown === -1) {
            setCountdown(null);
            setIsCapturing(true); // Set flag before capture
            void performCapture();
        }
    }, [countdown, performCapture]);

    // --- Initialization ---
    useEffect(() => {
        let mounted = true;

        const init = async () => {
            try {
                await startCamera();
                if (!mounted) return;

                await qualityAnalyzer.initialize();

                // Initialize phone angle detection (best-effort — graceful fail on desktop)
                await initializePhoneAngle().catch((err) => {
                    console.warn('[MobileCaptureScreen] Phone angle init failed:', err);
                });

                setIsInitializing(false);
                startAnalysisLoop();
            } catch (err) {
                console.error('Init failed:', err);
                if (mounted) {
                    handleCameraError(err);
                    setIsInitializing(false);
                }
            }
        };

        void init();

        return () => {
            mounted = false;
            stopCamera();
            stopAnalysisLoop();
            stopPhoneAngle();
            // Clean up countdown
            if (countdownIntervalRef.current) {
                clearInterval(countdownIntervalRef.current);
                countdownIntervalRef.current = null;
            }
            audioFeedback.stop();
        };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []); // Intentional: only run once on mount

    // --- Render ---
    if (cameraError) {
        return (
            <div className="min-h-screen bg-black flex flex-col items-center justify-center p-6 text-center">
                <AlertCircle className="w-16 h-16 text-red-500 mb-4" aria-hidden="true" />
                <h2 className="text-xl font-bold text-white mb-2">Camera Error</h2>
                <p id="camera-error-description" className="text-neutral-400 mb-6">{errorMessage}</p>
                <button
                    onClick={onBack}
                    aria-label="Go back to home"
                    aria-describedby="camera-error-description"
                    className="px-6 py-3 bg-neutral-800 text-white rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-black"
                >
                    Go Back
                </button>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-black relative overflow-hidden">
            {/* Video Preview (Mirrored for user comfort) */}
            <video
                ref={videoRef}
                className="absolute inset-0 w-full h-full object-cover scale-x-[-1]"
                playsInline
                muted
                autoPlay
                aria-hidden="true"
                aria-label="Live camera preview for iris capture"
            />

            {/* Iris Target Overlay - Only show when iris is detected */}
            {!isInitializing && currentReport?.irisDetected && screenIrisPosition && (
                <IrisTarget
                    detected={currentReport.irisDetected}
                    centered={currentReport.centering.status === 'ok'}
                    distanceGood={currentReport.distance.status === 'ok'}
                    lightingGood={currentReport.lighting.status === 'ok'}
                    isReady={
                        currentReport.distance.status === 'ok' &&
                        currentReport.centering.status === 'ok' &&
                        currentReport.lighting.status === 'ok'
                    }
                    countdown={countdown !== null && countdown >= 0 ? countdown : null}
                    irisPosition={screenIrisPosition}
                    irisDiameter={screenIrisDiameter}
                />
            )}

            {/* Debug Analysis Canvas */}
            {isDebug && (
                <canvas
                    ref={analysisCanvasRef}
                    className="absolute bottom-4 left-4 w-64 h-64 border-2 border-green-500 opacity-100 pointer-events-none z-50"
                />
            )}
            {!isDebug && (
                <canvas ref={analysisCanvasRef} className="hidden" />
            )}

            {/* Capture Canvas (Hidden) */}
            <canvas ref={canvasRef} className="hidden" />

            {/* UI Overlay */}
            <div className="absolute inset-0 z-10 flex flex-col pointer-events-none">
                {/* Header with Back Button */}
                <div className="bg-gradient-to-b from-black/60 to-transparent backdrop-blur-sm pointer-events-auto">
                    <div className="px-6 py-4 flex items-center justify-between">
                        <button
                            onClick={onBack}
                            aria-label="Go back"
                            className="p-2 hover:bg-white/10 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-1 focus-visible:ring-offset-black/60"
                        >
                            <ArrowLeft className="w-5 h-5 text-white" aria-hidden="true" />
                        </button>

                        {isInitializing && (
                            <div className="flex items-center gap-2">
                                <div className="animate-spin w-4 h-4 border-2 border-white/40 border-t-white rounded-full" />
                                <span className="text-sm font-light text-white/80">Loading...</span>
                            </div>
                        )}
                    </div>
                </div>

                {/* Spacer */}
                <div className="flex-1" />

                {/* Guidance Message Bar */}
                {!isInitializing && (
                    <div className="pointer-events-none pb-28 px-6">
                        <div className="text-center">
                            <AnimatePresence mode="wait">
                                <motion.p
                                    key={guidanceMessage}
                                    role="status"
                                    aria-live="polite"
                                    aria-atomic="true"
                                    className="text-base font-light text-white drop-shadow-lg"
                                    initial={{ opacity: 0, y: 4 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, y: -4 }}
                                    transition={{ duration: 0.15 }}
                                >
                                    {guidanceMessage}
                                </motion.p>
                            </AnimatePresence>
                        </div>
                    </div>
                )}

                {/* Status Indicators at Bottom */}
                {!isInitializing && currentReport && (
                    <div className="pointer-events-none pb-8 px-6">
                        <div
                            className="flex gap-2 justify-center"
                            role="region"
                            aria-label="Capture quality indicators"
                        >
                            <StatusIndicator
                                type="focus"
                                status={
                                    currentReport.focus.status === 'ok' && isFocusLocked
                                        ? 'ok'
                                        : currentReport.focus.status === 'warn'
                                            ? 'warn'
                                            : 'fail'
                                }
                            />
                            <StatusIndicator
                                type="distance"
                                status={currentReport.distance.status === 'ok' ? 'ok' : currentReport.distance.status === 'warn' ? 'warn' : 'fail'}
                            />
                            <StatusIndicator
                                type="centering"
                                status={currentReport.centering.status === 'ok' ? 'ok' : currentReport.centering.status === 'warn' ? 'warn' : 'fail'}
                            />
                            <StatusIndicator
                                type="lighting"
                                status={currentReport.lighting.status === 'ok' ? 'ok' : currentReport.lighting.status === 'warn' ? 'warn' : 'fail'}
                            />
                            {phoneAngleAvailable && (
                                <StatusIndicator
                                    type="angle"
                                    status={phoneAngleOk ? 'ok' : 'fail'}
                                />
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
