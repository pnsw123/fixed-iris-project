/**
 * IrisCaptureOrchestrator.tsx — Legacy iris-capture component; superseded by
 * MobileCaptureScreen. Retained as a lean reference implementation.
 *
 * ## Active component vs this file
 * `MobileCaptureScreen` is the component used in the live user flow
 * (`/capture` and `/mobile-capture` routes). That component adds:
 *   - Motion animations (Framer Motion)
 *   - Audio feedback (`audioFeedback` lib)
 *   - Telemetry (`telemetry` lib)
 *   - Iris-target overlay (`IrisTarget` UI component)
 *   - Structured `CaptureData` payload (cropped image, iris coords, crop size,
 *     iris radius) for downstream AI processing
 *
 * `IrisCaptureOrchestrator` predates all of the above. It emits a raw
 * base-64 JPEG string via `onCaptureComplete(image: string)` and has no
 * overlay animations. It is **not imported by any route** and should not be
 * used in new code.
 *
 * ## CAPTURE_THRESHOLDS — value rationale
 * ```
 * minDistanceScore:  60   Eye must be close enough for iris texture detail.
 *                         Below 60 the iris occupies too few pixels for reliable
 *                         feature extraction.
 * minLightingScore:  50   Permissive floor — accepts typical indoor ambient
 *                         light. Lower would accept silhouettes; higher would
 *                         reject fluorescent offices.
 * minCenteringScore: 35   Intentionally low: the oval guide is decorative, so
 *                         requiring strict centering frustrates users. The iris
 *                         detector tolerates off-centre placement well.
 * minFocusScore:     80   Highest bar in the set. Blur is the primary cause of
 *                         failed downstream AI matches — a sharp image at 60
 *                         distance beats a blurry image at 80 distance every
 *                         time.
 * requiredStableSeconds: 3  Three consecutive seconds where every metric stays
 *                            above its threshold. Prevents accidental captures
 *                            from momentary spikes in quality scores.
 * ```
 *
 * ## countdownAbortRef — abort mechanism
 * `countdownAbortRef` is a `useRef<boolean>` (not state) that acts as an
 * escape hatch for the async `performCapture` countdown loop.
 *
 * Problem: `performCapture` is an `async` function that drives a 3-2-1
 * countdown with `await new Promise(setTimeout, 100)` checks. If the
 * continuous quality-analysis loop (running in a separate `requestAnimationFrame`
 * cycle) detects that quality has dropped, it cannot cancel the awaited promise
 * by setting React state — state updates are batched and won't be observed
 * synchronously inside an already-running async function.
 *
 * Solution: the quality loop sets `countdownAbortRef.current = true`.
 * `performCapture` polls this ref every 100 ms inside its countdown loop and
 * returns early (abandoning the capture) as soon as the flag is raised. This
 * guarantees sub-100 ms abort latency without introducing a shared mutable
 * state race condition.
 *
 * Reset points: `countdownAbortRef.current` is cleared to `false` at the start
 * of every new `performCapture` call and in `handleRetake`, so a stale abort
 * flag never blocks the next capture attempt.
 *
 * ## performCapture flow
 * 1. Guard: skip if already capturing.
 * 2. Set `isCapturing = true`, initialise countdown at 3.
 * 3. For each countdown tick (3 → 1): wait 1 s in 100 ms sub-steps, checking
 *    `countdownAbortRef` and re-running quality analysis each sub-step.
 *    Abort if flag raised or quality drops.
 * 4. Draw final frame to `canvasRef`, run one last quality check.
 * 5. Export JPEG via `canvas.toDataURL`, call `onCaptureComplete`.
 *
 * @param onCaptureComplete - Called once with a base-64 JPEG data-URL after a
 *   successful, quality-validated capture.
 */
'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { Camera, RefreshCw, AlertCircle } from 'lucide-react';
import { qualityAnalyzer, QualityReport } from '@/lib/qualityMetrics';
import { useDebugMode } from '@/hooks/useDebugMode';

// Minimum thresholds for capture - all must pass for 3 consecutive seconds
const CAPTURE_THRESHOLDS = {
    minDistanceScore: 60,
    minLightingScore: 50,
    minCenteringScore: 35,
    minFocusScore: 80,
    requiredStableSeconds: 3,  // Must be stable for 3 seconds
};

export default function IrisCaptureOrchestrator({
    onCaptureComplete
}: {
    onCaptureComplete: (image: string) => void;
}) {
    const isDebug = useDebugMode();

    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const analysisCanvasRef = useRef<HTMLCanvasElement>(null);
    const animationFrameRef = useRef<number | null>(null);
    const shouldCaptureRef = useRef<boolean>(false);
    const countdownAbortRef = useRef<boolean>(false);  // NEW: Flag to abort countdown
    
    const [isInitializing, setIsInitializing] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [capturedImage, setCapturedImage] = useState<string | null>(null);
    
    // Quality tracking state
    const [currentReport, setCurrentReport] = useState<QualityReport | null>(null);
    const [stableSeconds, setStableSeconds] = useState(0);
    const [isCapturing, setIsCapturing] = useState(false);
    const [countdown, setCountdown] = useState<number | null>(null);
    
    // Track when quality became stable
    const stableStartTimeRef = useRef<number | null>(null);
    const lastQualityCheckRef = useRef<boolean>(false);

    // Check if current quality meets all thresholds
    const meetsQualityThresholds = useCallback((report: QualityReport): boolean => {
        if (!report.irisDetected) return false;
        
        return (
            report.distance.score >= CAPTURE_THRESHOLDS.minDistanceScore &&
            report.lighting.score >= CAPTURE_THRESHOLDS.minLightingScore &&
            report.centering.score >= CAPTURE_THRESHOLDS.minCenteringScore &&
            report.focus.score >= CAPTURE_THRESHOLDS.minFocusScore
        );
    }, []);

    // Perform the actual capture (defined first to avoid hoisting issues)
    const performCapture = useCallback(async () => {
        if (!videoRef.current || !canvasRef.current || isCapturing) return;

        setIsCapturing(true);
        setCountdown(3);
        countdownAbortRef.current = false;  // Reset abort flag

        // Countdown with validation at each step
        for (let i = 3; i > 0; i--) {
            setCountdown(i);
            
            // Check every 100ms during the 1-second wait (10 checks per second)
            for (let check = 0; check < 10; check++) {
                await new Promise(resolve => setTimeout(resolve, 100));
                
                // Check if we should abort
                if (countdownAbortRef.current) {
                    setIsCapturing(false);
                    setCountdown(null);
                    stableStartTimeRef.current = null;
                    lastQualityCheckRef.current = false;
                    setStableSeconds(0);
                    shouldCaptureRef.current = false;
                    return;
                }
                
                // Re-check quality during countdown
                if (analysisCanvasRef.current && videoRef.current) {
                    const ctx = analysisCanvasRef.current.getContext('2d', { willReadFrequently: true });
                    if (ctx) {
                        ctx.drawImage(videoRef.current, 0, 0);
                        const checkReport = await qualityAnalyzer.analyze(videoRef.current, analysisCanvasRef.current);
                        
                        if (!meetsQualityThresholds(checkReport)) {
                            // Quality dropped during countdown - abort immediately
                            setIsCapturing(false);
                            setCountdown(null);
                            stableStartTimeRef.current = null;
                            lastQualityCheckRef.current = false;
                            setStableSeconds(0);
                            shouldCaptureRef.current = false;
                            return;
                        }
                    }
                }
            }
        }

        // Final capture
        setCountdown(0);
        
        const video = videoRef.current;
        const canvas = canvasRef.current;

        if (!video || !canvas) {
            setIsCapturing(false);
            return;
        }

        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        if (!ctx) {
            setIsCapturing(false);
            return;
        }

        ctx.drawImage(video, 0, 0);

        // Final quality check
        if (analysisCanvasRef.current) {
            const finalReport = await qualityAnalyzer.analyze(video, analysisCanvasRef.current);
            if (!meetsQualityThresholds(finalReport)) {
                setIsCapturing(false);
                setCountdown(null);
                shouldCaptureRef.current = false;
                return;
            }
        }

        const imageData = canvas.toDataURL('image/jpeg', 0.95);
        setCapturedImage(imageData);
        setIsCapturing(false);
        setCountdown(null);
        shouldCaptureRef.current = false;
        onCaptureComplete(imageData);
    }, [isCapturing, meetsQualityThresholds, onCaptureComplete]);

    // Trigger capture when shouldCaptureRef becomes true
    useEffect(() => {
        if (shouldCaptureRef.current && !isCapturing) {
            shouldCaptureRef.current = false; // Reset immediately to prevent re-trigger
            // Use setTimeout to avoid calling setState synchronously in effect
            setTimeout(() => { void performCapture(); }, 0);
        }
    }, [stableSeconds, isCapturing, performCapture]);

    // Continuous quality analysis loop
    useEffect(() => {
        if (isInitializing || capturedImage) return;

        let running = true;

        // Mutable ref allows runLoop and scheduleLoop to mutually reference each other
        const loopRef = { schedule: () => {} };

        const runLoop = async () => {
            if (!running || !videoRef.current || !analysisCanvasRef.current) {
                return;
            }

            const video = videoRef.current;
            const canvas = analysisCanvasRef.current;

            // Set canvas size to match video
            if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
            }

            const ctx = canvas.getContext('2d', { willReadFrequently: true });
            if (!ctx) {
                loopRef.schedule();
                return;
            }

            // Draw current frame
            ctx.drawImage(video, 0, 0);

            try {
                // Analyze quality
                const report = await qualityAnalyzer.analyze(video, canvas);
                if (!running) return;

                setCurrentReport(report);

                const qualityOk = meetsQualityThresholds(report);
                const now = Date.now();

                if (qualityOk) {
                    // Quality is good
                    if (!lastQualityCheckRef.current) {
                        // Just became good - start timer
                        stableStartTimeRef.current = now;
                        lastQualityCheckRef.current = true;
                    }

                    // Calculate how long quality has been stable
                    const stableDuration = stableStartTimeRef.current
                        ? Math.floor((now - stableStartTimeRef.current) / 1000)
                        : 0;
                    setStableSeconds(stableDuration);

                    // Trigger capture after required stable seconds
                    if (stableDuration >= CAPTURE_THRESHOLDS.requiredStableSeconds && !isCapturing) {
                        shouldCaptureRef.current = true;
                    }
                } else {
                    // Quality dropped - reset timer and abort any countdown
                    stableStartTimeRef.current = null;
                    lastQualityCheckRef.current = false;
                    setStableSeconds(0);
                    shouldCaptureRef.current = false;

                    // CRITICAL: Signal countdown to abort if it's running
                    if (isCapturing) {
                        countdownAbortRef.current = true;
                    }
                }
            } catch (err) {
                console.error('[QualityLoop] Error:', err);
            }

            // Continue loop
            if (running) {
                loopRef.schedule();
            }
        };

        // Assign after runLoop is defined; wraps async fn so requestAnimationFrame gets void fn
        loopRef.schedule = () => { animationFrameRef.current = requestAnimationFrame(() => { void runLoop(); }); };
        loopRef.schedule();

        return () => {
            running = false;
            if (animationFrameRef.current) {
                cancelAnimationFrame(animationFrameRef.current);
                animationFrameRef.current = null;
            }
        };
    }, [isInitializing, capturedImage, meetsQualityThresholds, isCapturing]);

    // Initialize camera
    useEffect(() => {
        let mounted = true;
        let stream: MediaStream | null = null;

        const init = async () => {
            try {
                await qualityAnalyzer.initialize();

                stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: 'user', width: { ideal: 1920 }, height: { ideal: 1080 } }
                });

                if (videoRef.current && mounted) {
                    videoRef.current.srcObject = stream;
                    await videoRef.current.play();
                    setIsInitializing(false);
                }
            } catch (err) {
                console.error("Init failed:", err);
                if (mounted) setError("Failed to start camera or AI engine.");
            }
        };

        void init();

        return () => {
            mounted = false;
            if (stream) {
                stream.getTracks().forEach(t => t.stop());
            }
        };
    }, []);

    const handleRetake = () => {
        setCapturedImage(null);
        setStableSeconds(0);
        stableStartTimeRef.current = null;
        lastQualityCheckRef.current = false;
        shouldCaptureRef.current = false;
        countdownAbortRef.current = false;
    };

    if (error) {
        return (
            <div className="p-6 text-center text-red-500">
                <AlertCircle className="mx-auto mb-2" />
                {error}
            </div>
        );
    }

    // Get feedback message - SYNCED with actual quality metrics
    const getFeedback = (): string => {
        if (!currentReport) return 'Initializing...';
        if (!currentReport.irisDetected) return 'Position your eye in frame';
        
        // Priority order: Distance > Centering > Lighting > Focus
        // Show the MOST important issue first
        if (currentReport.distance.status === 'fail') {
            return currentReport.distance.feedback;
        }
        if (currentReport.centering.status === 'fail') {
            return currentReport.centering.feedback;
        }
        if (currentReport.lighting.status === 'fail') {
            return currentReport.lighting.feedback;
        }
        if (currentReport.focus.status === 'fail') {
            return currentReport.focus.feedback;
        }
        
        // Warnings (less severe)
        if (currentReport.distance.status === 'warn') {
            return currentReport.distance.feedback;
        }
        if (currentReport.centering.status === 'warn') {
            return currentReport.centering.feedback;
        }
        if (currentReport.lighting.status === 'warn') {
            return currentReport.lighting.feedback;
        }
        if (currentReport.focus.status === 'warn') {
            return currentReport.focus.feedback;
        }
        
        // All good!
        if (stableSeconds > 0 && stableSeconds < CAPTURE_THRESHOLDS.requiredStableSeconds) {
            return `Hold steady... ${CAPTURE_THRESHOLDS.requiredStableSeconds - stableSeconds}s`;
        }
        return 'Perfect! Hold steady...';
    };

    const getStatusColor = (): string => {
        if (!currentReport?.irisDetected) return 'bg-red-500';
        if (meetsQualityThresholds(currentReport)) return 'bg-green-500';
        return 'bg-yellow-500';
    };

    return (
        <div className="relative w-full h-screen bg-black">
            <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-full object-cover"
            />
            <canvas ref={canvasRef} className="hidden" />
            <canvas ref={analysisCanvasRef} className="hidden" />

            {/* Quality indicator overlay */}
            {!capturedImage && currentReport && (
                <div className="absolute top-4 left-0 right-0 flex flex-col items-center gap-2 px-4">
                    {/* Status bar */}
                    <div className={`px-4 py-2 rounded-full ${getStatusColor()} text-white text-sm font-medium`}>
                        {getFeedback()}
                    </div>
                    
                    {/* Progress bar for stable time */}
                    {meetsQualityThresholds(currentReport) && !isCapturing && (
                        <div className="w-48 h-2 bg-gray-700 rounded-full overflow-hidden">
                            <div 
                                className="h-full bg-green-500 transition-all duration-300"
                                style={{ width: `${(stableSeconds / CAPTURE_THRESHOLDS.requiredStableSeconds) * 100}%` }}
                            />
                        </div>
                    )}

                    {/* Quality metrics (debug only) */}
                    {isDebug && (
                        <div className="flex gap-2 text-xs text-white/70">
                            <span className={currentReport.distance.status === 'ok' ? 'text-green-400' : currentReport.distance.status === 'warn' ? 'text-yellow-400' : 'text-red-400'}>
                                D:{Math.round(currentReport.distance.score)}
                            </span>
                            <span className={currentReport.lighting.status === 'ok' ? 'text-green-400' : currentReport.lighting.status === 'warn' ? 'text-yellow-400' : 'text-red-400'}>
                                L:{Math.round(currentReport.lighting.score)}
                            </span>
                            <span className={currentReport.centering.status === 'ok' ? 'text-green-400' : currentReport.centering.status === 'warn' ? 'text-yellow-400' : 'text-red-400'}>
                                C:{Math.round(currentReport.centering.score)}
                            </span>
                            <span className={currentReport.focus.status === 'ok' ? 'text-green-400' : currentReport.focus.status === 'warn' ? 'text-yellow-400' : 'text-red-400'}>
                                F:{Math.round(currentReport.focus.score)}
                            </span>
                        </div>
                    )}
                </div>
            )}

            {/* Countdown overlay */}
            {countdown !== null && countdown > 0 && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/30">
                    <div className="text-8xl font-bold text-white animate-pulse">
                        {countdown}
                    </div>
                </div>
            )}

            {/* Bottom controls */}
            <div className="absolute bottom-10 left-0 right-0 flex justify-center gap-4">
                {capturedImage ? (
                    <button
                        onClick={handleRetake}
                        className="p-4 bg-white rounded-full text-black flex items-center gap-2"
                    >
                        <RefreshCw size={20} />
                        <span className="font-medium">Retake</span>
                    </button>
                ) : (
                    <div className="text-white text-center">
                        <Camera size={32} className="mx-auto opacity-50" />
                        <p className="text-sm mt-2 opacity-70">Auto-capture when ready</p>
                    </div>
                )}
            </div>

            {isInitializing && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/50 text-white">
                    Initializing...
                </div>
            )}
        </div>
    );
}
