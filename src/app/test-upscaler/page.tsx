'use client';

import { useEffect, useRef, useState } from 'react';
import srService from '@/lib/superRes';

export default function TestUpscalerPage() {
    const [status, setStatus] = useState('Loading...');
    const [originalUrl, setOriginalUrl] = useState<string | null>(null);
    const [upscaledUrl, setUpscaledUrl] = useState<string | null>(null);
    const [processingTime, setProcessingTime] = useState<number>(0);
    const [dimensions, setDimensions] = useState({ input: '', output: '' });

    const originalCanvasRef = useRef<HTMLCanvasElement>(null);
    const upscaledCanvasRef = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        runTest();
    }, []);

    const runTest = async () => {
        try {
            setStatus('Loading test image...');

            // Load the sharp test iris image
            const img = new Image();
            img.crossOrigin = 'anonymous';

            // Use the generated test image
            img.src = '/test_iris_sharp.png';

            await new Promise((resolve, reject) => {
                img.onload = resolve;
                img.onerror = () => reject(new Error('Failed to load test image'));
            });

            setStatus('Creating 512×512 test canvas...');

            // Create 512×512 canvas with the image
            const canvas = document.createElement('canvas');
            canvas.width = 512;
            canvas.height = 512;
            const ctx = canvas.getContext('2d');
            if (!ctx) throw new Error('Failed to get context');

            ctx.drawImage(img, 0, 0, 512, 512);

            // Save original as data URL
            const originalDataUrl = canvas.toDataURL('image/png');
            setOriginalUrl(originalDataUrl);
            setDimensions(prev => ({ ...prev, input: '512×512' }));

            // Draw to visible canvas
            if (originalCanvasRef.current) {
                const visibleCtx = originalCanvasRef.current.getContext('2d');
                if (visibleCtx) {
                    visibleCtx.drawImage(canvas, 0, 0);
                }
            }

            setStatus('Running AI upscaling (this may take 1-2 minutes)...');

            // Initialize SR service
            await srService.initialize();

            // Measure performance
            const t0 = performance.now();
            const result = await srService.upscaleCanvas(canvas);
            const duration = performance.now() - t0;

            setProcessingTime(duration);
            setDimensions(prev => ({ ...prev, output: `${result.width}×${result.height}` }));

            setStatus('Creating output canvas...');

            // Create upscaled canvas
            const upscaledCanvas = document.createElement('canvas');
            upscaledCanvas.width = result.width;
            upscaledCanvas.height = result.height;
            const upscaledCtx = upscaledCanvas.getContext('2d');

            if (!upscaledCtx) throw new Error('Failed to create upscaled context');

            const imageData = new ImageData(
                new Uint8ClampedArray(result.rgba),
                result.width,
                result.height
            );
            upscaledCtx.putImageData(imageData, 0, 0);

            // Save as data URL
            const upscaledDataUrl = upscaledCanvas.toDataURL('image/png');
            setUpscaledUrl(upscaledDataUrl);

            // Draw to visible canvas (scaled down to fit)
            if (upscaledCanvasRef.current) {
                const visibleCtx = upscaledCanvasRef.current.getContext('2d');
                if (visibleCtx) {
                    // Scale down 2048→512 for display
                    visibleCtx.imageSmoothingEnabled = false; // Nearest neighbor to see pixels
                    visibleCtx.drawImage(upscaledCanvas, 0, 0, 512, 512);
                }
            }

            setStatus(`✅ Complete! AI upscaling took ${(duration / 1000).toFixed(1)}s`);

        } catch (error) {
            console.error('Test failed:', error);
            setStatus(`❌ Error: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
    };

    return (
        <div className="min-h-screen bg-black text-white p-8">
            <div className="max-w-7xl mx-auto">
                {/* Header */}
                <div className="mb-8">
                    <h1 className="text-4xl font-bold mb-2">AI Upscaling Test Harness</h1>
                    <p className="text-neutral-400">Testing Real-ESRGAN with sharp input image</p>
                    <p className="text-sm text-blue-400 mt-2">{status}</p>
                </div>

                {/* Stats */}
                {processingTime > 0 && (
                    <div className="mb-8 p-4 bg-neutral-900 rounded-lg border border-neutral-800">
                        <h2 className="text-xl font-semibold mb-3">Results</h2>
                        <div className="grid grid-cols-3 gap-4 text-sm">
                            <div>
                                <p className="text-neutral-400">Input Size</p>
                                <p className="text-2xl font-bold text-blue-400">{dimensions.input}</p>
                            </div>
                            <div>
                                <p className="text-neutral-400">Output Size</p>
                                <p className="text-2xl font-bold text-green-400">{dimensions.output}</p>
                            </div>
                            <div>
                                <p className="text-neutral-400">Processing Time</p>
                                <p className="text-2xl font-bold text-purple-400">
                                    {(processingTime / 1000).toFixed(1)}s
                                </p>
                            </div>
                        </div>
                    </div>
                )}

                {/* Comparison */}
                <div className="grid grid-cols-2 gap-8">
                    {/* Original */}
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <h2 className="text-2xl font-semibold">Original (512×512)</h2>
                            {originalUrl && (
                                <a
                                    href={originalUrl}
                                    download="original_512.png"
                                    className="px-4 py-2 bg-blue-500/20 border border-blue-400/30 text-blue-200 rounded-lg hover:bg-blue-500/30 transition-colors text-sm"
                                >
                                    Download
                                </a>
                            )}
                        </div>
                        <div className="relative">
                            <canvas
                                ref={originalCanvasRef}
                                width={512}
                                height={512}
                                className="w-full border border-neutral-700 rounded-lg"
                            />
                            <p className="text-xs text-neutral-500 mt-2">
                                Displayed at actual size
                            </p>
                        </div>
                    </div>

                    {/* Upscaled */}
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <h2 className="text-2xl font-semibold">AI Upscaled (2048×2048)</h2>
                            {upscaledUrl && (
                                <a
                                    href={upscaledUrl}
                                    download="upscaled_2048.png"
                                    className="px-4 py-2 bg-green-500/20 border border-green-400/30 text-green-200 rounded-lg hover:bg-green-500/30 transition-colors text-sm"
                                >
                                    Download
                                </a>
                            )}
                        </div>
                        <div className="relative">
                            <canvas
                                ref={upscaledCanvasRef}
                                width={512}
                                height={512}
                                className="w-full border border-neutral-700 rounded-lg"
                            />
                            <p className="text-xs text-neutral-500 mt-2">
                                Scaled down to 512×512 for display (4× larger internally)
                            </p>
                        </div>
                    </div>
                </div>

                {/* Instructions */}
                <div className="mt-8 p-6 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                    <h3 className="text-xl font-semibold mb-3 text-yellow-200">
                        📋 How to Compare
                    </h3>
                    <ol className="space-y-2 text-sm text-neutral-300">
                        <li>1. Download both images using the buttons above</li>
                        <li>2. Open them in an image viewer (Preview, Photoshop, etc.)</li>
                        <li>3. Zoom to 200-400% to see the difference</li>
                        <li>4. The AI version should show sharper edges and finer texture details</li>
                    </ol>
                </div>

                {/* Back Button */}
                <div className="mt-8">
                    <a
                        href="/"
                        className="px-6 py-3 bg-white/10 border border-white/20 text-white rounded-lg hover:bg-white/20 transition-colors inline-block"
                    >
                        ← Back to Iris Capture
                    </a>
                </div>
            </div>
        </div>
    );
}
