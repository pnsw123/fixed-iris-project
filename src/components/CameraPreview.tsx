'use client';

import React, { useRef, useEffect, useState, forwardRef, useImperativeHandle } from 'react';
import { Camera, AlertCircle } from 'lucide-react';

export interface CameraPreviewHandle {
    capture: () => HTMLCanvasElement | null;
    video: HTMLVideoElement | null;
    canvas: HTMLCanvasElement | null;
}

const CameraPreview = forwardRef<CameraPreviewHandle, {}>((props, ref) => {
    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [error, setError] = useState<string | null>(null);
    const [stream, setStream] = useState<MediaStream | null>(null);

    useImperativeHandle(ref, () => ({
        capture: () => {
            if (!videoRef.current) return null;

            // Create a temporary off-screen canvas for capture
            const canvas = document.createElement('canvas');
            canvas.width = videoRef.current.videoWidth;
            canvas.height = videoRef.current.videoHeight;
            const ctx = canvas.getContext('2d');
            if (!ctx) return null;

            // Flip horizontally to match the mirrored video
            ctx.translate(canvas.width, 0);
            ctx.scale(-1, 1);
            ctx.drawImage(videoRef.current, 0, 0);
            return canvas;
        },
        video: videoRef.current,
        canvas: canvasRef.current
    }));

    useEffect(() => {
        let currentStream: MediaStream | null = null;

        const startCamera = async () => {
            try {
                const constraints = {
                    video: {
                        facingMode: 'user',
                        width: { ideal: 3840 },
                        height: { ideal: 2160 }
                    }
                };
                currentStream = await navigator.mediaDevices.getUserMedia(constraints);
                setStream(currentStream);
                if (videoRef.current) {
                    videoRef.current.srcObject = currentStream;
                }
                setError(null);
            } catch (err) {
                console.error("Error accessing camera:", err);
                setError("Could not access camera. Please ensure permissions are granted.");
            }
        };

        startCamera();

        return () => {
            if (currentStream) {
                currentStream.getTracks().forEach(track => track.stop());
            }
        };
    }, []);

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center w-full h-full bg-neutral-900 rounded-lg border border-red-900/50 p-6 text-center">
                <AlertCircle className="w-10 h-10 text-red-500 mb-2" />
                <p className="text-red-200 text-sm">{error}</p>
            </div>
        );
    }

    return (
        <div className="relative w-full h-full bg-black rounded-lg overflow-hidden border border-neutral-800 shadow-2xl">
            <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-full object-cover transform -scale-x-100"
                onLoadedMetadata={() => {
                    if (videoRef.current && canvasRef.current) {
                        canvasRef.current.width = videoRef.current.videoWidth;
                        canvasRef.current.height = videoRef.current.videoHeight;
                    }
                }}
            />
            <canvas
                id="overlay-canvas"
                ref={canvasRef}
                className="absolute inset-0 w-full h-full pointer-events-none transform -scale-x-100"
            />
            {!stream && (
                <div className="absolute inset-0 flex items-center justify-center bg-neutral-900">
                    <Camera className="w-8 h-8 text-neutral-600 animate-pulse" />
                </div>
            )}
        </div>
    );
});

CameraPreview.displayName = 'CameraPreview';

export default CameraPreview;
