'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { ArrowLeft, AlertCircle } from 'lucide-react';
import { qualityAnalyzer, QualityReport } from '@/lib/qualityMetrics';
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
    const lastBlockedCountdownLogRef = useRef<number>(0);

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

    // --- Compute guidance message ---
    const computeGuidance = useCallback((report: QualityReport | null): string => {
        if (!report || !report.irisDetected) {
            return 'Align one eye in the circle';
        }

        if (!report.irisCropBox) {
            return 'Hold steady...';
        }

        // Priority-based guidance
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
                console.log(`[Capture] Camera started: ${videoRef.current.videoWidth}x${videoRef.current.videoHeight}`);
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

            setCurrentReport(report);
            setGuidanceMessage(computeGuidance(report));

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
                report.distance.status === 'ok' && // Only start countdown when user is close enough
                report.centering.status !== 'fail' &&
                report.lighting.status !== 'fail';

            if (isGoodForCountdown) {
                stableGoodFramesRef.current += 1;
            } else {
                stableGoodFramesRef.current = 0;
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
                console.log('[Capture] Starting countdown - stable & close', {
                    distance: report.distance,
                    irisDiameter: report.irisDiameter.toFixed(2),
                    cropBox: report.irisCropBox
                });
                setCountdown(3);
                let count = 3;
                countdownIntervalRef.current = setInterval(() => {
                    count--;
                    setCountdown(count);
                    console.log(`[Capture] Countdown: ${count}`);
                    if (count <= 0) {
                        if (countdownIntervalRef.current) {
                            clearInterval(countdownIntervalRef.current);
                            countdownIntervalRef.current = null;
                        }
                        setCountdown(-1); // Special value to trigger capture
                    }
                }, 1000);
            } else if (!isGoodForCountdown && countdown !== null && countdown > 0 && countdownIntervalRef.current) {
                console.log('[Capture] Aborting countdown - conditions no longer stable', {
                    distance: report.distance,
                    centering: report.centering,
                    lighting: report.lighting
                });
                if (countdownIntervalRef.current) {
                    clearInterval(countdownIntervalRef.current);
                    countdownIntervalRef.current = null;
                }
                setCountdown(null);
            } else if (!isGoodForCountdown && countdown === null && report.irisDetected) {
                const now = performance.now();
                if (now - lastBlockedCountdownLogRef.current > 1000) {
                    console.log('[Capture] Not starting countdown (needs closer/centered/light)', {
                        distance: report.distance,
                        centering: report.centering,
                        lighting: report.lighting,
                        irisDiameter: report.irisDiameter.toFixed(2)
                    });
                    lastBlockedCountdownLogRef.current = now;
                }
            }

        } catch (err) {
            console.warn('Analysis failed:', err);
        }
    }, [isDebug, countdown, computeGuidance, isCapturing]);

    const startAnalysisLoop = useCallback(() => {
        console.log('[Capture] Starting analysis loop...');
        const loop = async () => {
            if (!videoRef.current || !analysisCanvasRef.current) {
                requestRef.current = requestAnimationFrame(loop);
                return;
            }

            const now = performance.now();
            if (now - lastAnalysisTime.current >= 100) {
                lastAnalysisTime.current = now;
                await processFrame();
            }

            requestRef.current = requestAnimationFrame(loop);
        };
        requestRef.current = requestAnimationFrame(loop);
    }, [processFrame]);

    const stopAnalysisLoop = useCallback(() => {
        if (requestRef.current) {
            cancelAnimationFrame(requestRef.current);
            requestRef.current = null;
        }
    }, []);

    // --- Capture ---
    const performCapture = useCallback(() => {
        console.log('[Capture] performCapture called');
        console.log('[Capture] isCapturing:', isCapturing);
        console.log('[Capture] currentReport:', currentReport);
        
        if (!videoRef.current || !canvasRef.current || !currentReport) {
            console.warn('[Capture] Cannot capture - missing dependencies');
            console.warn('[Capture] video:', !!videoRef.current, 'canvas:', !!canvasRef.current, 'report:', !!currentReport);
            return;
        }

        if (!currentReport.irisDetected || !currentReport.irisCropBox) {
            console.warn('[Capture] No iris detected or no crop box');
            return;
        }

        console.log('[Capture] 🎯 Executing capture...');

        const video = videoRef.current;
        const canvas = canvasRef.current;
        const { x, y, size } = currentReport.irisCropBox;
        const { x: irisX_ac, y: irisY_ac } = currentReport.irisCenter;

        const analysisCanvas = analysisCanvasRef.current;
        if (!analysisCanvas) {
            console.error('[Capture] Analysis canvas is null!');
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
        let in_crop_x = irisX_video - cropX;
        let in_crop_y = irisY_video - cropY;

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

        console.log('[Capture] Scale factors:', { scaleX, scaleY, avgScale: (scaleX + scaleY) / 2 });
        console.log('[Capture] Iris diameter transformation:');
        console.log(`  Analysis canvas (640x480): ${irisDiameter_ac.toFixed(2)}px`);
        console.log(`  Video (${video.videoWidth}x${video.videoHeight}): ${irisDiameter_video.toFixed(2)}px`);
        console.log(`  Crop (${cropSize}x${cropSize}): ${irisDiameter_crop.toFixed(2)}px`);
        console.log(`  Radius for backend: ${irisRadius_crop.toFixed(2)}px`);
        console.log('[Capture] Crop dimensions:', { cropX, cropY, cropSize });
        console.log('[Capture] Iris in crop:', { in_crop_x, in_crop_y, diameter: irisDiameter_crop, radius: irisRadius_crop, isValid });

        canvas.width = cropSize;
        canvas.height = cropSize;

        const ctx = canvas.getContext('2d');
        if (!ctx) {
            console.error('[Capture] Cannot get canvas context!');
            return;
        }

        ctx.drawImage(video, cropX, cropY, cropSize, cropSize, 0, 0, cropSize, cropSize);

        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = cropSize;
        tempCanvas.height = cropSize;
        const tempCtx = tempCanvas.getContext('2d');
        if (!tempCtx) {
            console.error('[Capture] Cannot get temp canvas context!');
            return;
        }

        tempCtx.save();
        tempCtx.scale(-1, 1);
        tempCtx.drawImage(canvas, -cropSize, 0);
        tempCtx.restore();

        const imageData = tempCanvas.toDataURL('image/jpeg', 0.95);
        console.log(`[Capture] ✅ Image created: ${cropSize}x${cropSize}px`);
        console.log(`[Capture] Data URL length: ${imageData.length}`);

        // Prepare capture data with coordinates and iris radius
        const captureData: CaptureData = {
            imageData,
            irisCoordinates: isValid ? { x: in_crop_x, y: in_crop_y } : null,
            cropSize,
            irisRadius: isValid ? irisRadius_crop : null
        };

        console.log('[Capture] Capture data:', {
            hasCoordinates: !!captureData.irisCoordinates,
            coordinates: captureData.irisCoordinates,
            cropSize: captureData.cropSize,
            irisRadius: captureData.irisRadius
        });

        telemetry.logSummary();

        // Stop analysis loop and camera
        console.log('[Capture] Stopping analysis loop...');
        stopAnalysisLoop();

        console.log('[Capture] Stopping camera...');
        stopCamera();

        console.log('[Capture] Calling onCaptureComplete...');
        onCaptureComplete(captureData);

        console.log('[Capture] Capture complete!');
    }, [currentReport, stopCamera, stopAnalysisLoop, onCaptureComplete, isCapturing]);

    // Trigger capture when countdown reaches -1
    useEffect(() => {
        if (countdown === -1) {
            console.log('[Capture] Countdown finished! Triggering capture...');
            setCountdown(null);
            setIsCapturing(true); // Set flag before capture
            performCapture();
        }
    }, [countdown, performCapture]);

    // --- Initialization ---
    useEffect(() => {
        let mounted = true;

        const init = async () => {
            try {
                console.log('[Capture] Starting initialization...');
                await startCamera();
                if (!mounted) return;

                console.log('[Capture] Loading Detection Engine...');
                await qualityAnalyzer.initialize();
                console.log('[Capture] Engine Ready');

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

        init();

        return () => {
            mounted = false;
            stopCamera();
            stopAnalysisLoop();
            // Clean up countdown
            if (countdownIntervalRef.current) {
                clearInterval(countdownIntervalRef.current);
                countdownIntervalRef.current = null;
            }
            audioFeedback.stop();
        };
    }, []); // FIXED: Empty array - only run once on mount

    // --- Render ---
    if (cameraError) {
        return (
            <div className="min-h-screen bg-black flex flex-col items-center justify-center p-6 text-center">
                <AlertCircle className="w-16 h-16 text-red-500 mb-4" />
                <h2 className="text-xl font-bold text-white mb-2">Camera Error</h2>
                <p className="text-neutral-400 mb-6">{errorMessage}</p>
                <button onClick={onBack} className="px-6 py-3 bg-neutral-800 text-white rounded-full">
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
                        <button onClick={onBack} className="p-2 hover:bg-white/10 rounded-lg transition-colors">
                            <ArrowLeft className="w-5 h-5 text-white" />
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
                            <p className="text-base font-light text-white drop-shadow-lg">
                                {guidanceMessage}
                            </p>
                        </div>
                    </div>
                )}

                {/* Status Indicators at Bottom */}
                {!isInitializing && currentReport && (
                    <div className="pointer-events-none pb-8 px-6">
                        <div className="flex gap-2 justify-center">
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
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
