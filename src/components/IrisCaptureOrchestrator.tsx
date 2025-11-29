'use client';

import { useState, useRef, useEffect } from 'react';
import { Camera, RefreshCw, Check, AlertCircle } from 'lucide-react';
import { qualityAnalyzer, QualityReport } from '@/lib/qualityMetrics';

export default function IrisCaptureOrchestrator({
    onCaptureComplete
}: {
    onCaptureComplete: (image: string) => void;
}) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [isInitializing, setIsInitializing] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [capturedImage, setCapturedImage] = useState<string | null>(null);

    useEffect(() => {
        let mounted = true;

        const init = async () => {
            try {
                // Initialize Detector
                await qualityAnalyzer.initialize();

                // Start Camera (Front Camera Only)
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: 'user', width: { ideal: 1920 }, height: { ideal: 1080 } }
                });


                if (videoRef.current && mounted) {
                    videoRef.current.srcObject = stream;
                    setIsInitializing(false);
                }
            } catch (err) {
                console.error("Init failed:", err);
                if (mounted) setError("Failed to start camera or AI engine.");
            }
        };

        init();

        return () => {
            mounted = false;
            // Cleanup stream
            if (videoRef.current?.srcObject) {
                const stream = videoRef.current.srcObject as MediaStream;
                stream.getTracks().forEach(t => t.stop());
            }
        };
    }, []);

    const handleCapture = async () => {
        if (!videoRef.current || !canvasRef.current) return;

        const video = videoRef.current;
        const canvas = canvasRef.current;

        // Draw full frame
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        ctx.drawImage(video, 0, 0);

        // Optional: Run analysis on capture to verify
        // const report = await qualityAnalyzer.analyze(canvas, canvas);
        // console.log("Capture Report:", report);

        const imageData = canvas.toDataURL('image/jpeg', 0.95);
        setCapturedImage(imageData);
        onCaptureComplete(imageData);
    };

    if (error) {
        return (
            <div className="p-6 text-center text-red-500">
                <AlertCircle className="mx-auto mb-2" />
                {error}
            </div>
        );
    }

    return (
        <div className="relative w-full h-screen bg-black">
            <video
                ref={videoRef}
                autoPlay
                playsInline
                className="w-full h-full object-cover"
            />
            <canvas ref={canvasRef} className="hidden" />

            <div className="absolute bottom-10 left-0 right-0 flex justify-center gap-4">
                {capturedImage ? (
                    <button
                        onClick={() => setCapturedImage(null)}
                        className="p-4 bg-white rounded-full text-black"
                    >
                        <RefreshCw />
                    </button>
                ) : (
                    <button
                        onClick={handleCapture}
                        disabled={isInitializing}
                        className="p-6 bg-white rounded-full text-black disabled:opacity-50"
                    >
                        <Camera size={32} />
                    </button>
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
