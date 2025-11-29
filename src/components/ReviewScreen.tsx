'use client';

import { useState, useEffect } from 'react';
import { Download, RotateCcw, Sparkles, SlidersHorizontal, Wifi, WifiOff } from 'lucide-react';
import { backendClient } from '@/lib/backendClient';
import { CaptureData } from './MobileCaptureScreen';

interface ReviewScreenProps {
    captureData: CaptureData;
    onRetake: () => void;
}

type ViewMode = 'single' | 'comparison';

export default function ReviewScreen({ captureData, onRetake }: ReviewScreenProps) {
    const { imageData: irisCrop, irisCoordinates, cropSize, irisRadius } = captureData;
    const [viewMode, setViewMode] = useState<ViewMode>('single');
    const [showOriginal, setShowOriginal] = useState(true);
    const [enhancedImage, setEnhancedImage] = useState<string | null>(null);
    const [isEnhancing, setIsEnhancing] = useState(false);
    const [enhancementError, setEnhancementError] = useState<string | null>(null);
    const [backendAvailable, setBackendAvailable] = useState<boolean | null>(null);
    const [processingMetadata, setProcessingMetadata] = useState<any>(null);

    // Check backend availability on mount
    useEffect(() => {
        const checkBackend = async () => {
            const available = await backendClient.healthCheck();
            setBackendAvailable(available);

            if (!available) {
                setEnhancementError(
                    'Backend server not available. Please start the backend with: cd backend && source venv/bin/activate && python app.py'
                );
            }
        };

        checkBackend();
    }, []);

    const handleEnhance = async () => {
        setIsEnhancing(true);
        setEnhancementError(null);

        try {
            console.log('[ReviewScreen] Sending to backend for Iris-SAM + ESRGAN processing...');
            console.log('[ReviewScreen] Iris coordinates:', irisCoordinates);

            const result = await backendClient.processIris(irisCrop, {
                return_mask: false,
                return_intermediate: false,
                upscale_factor: 4,
                irisCoordinates: irisCoordinates,
                cropSize: cropSize,
                irisRadius: irisRadius,
            });

            if (result.success && result.upscaled_image) {
                setEnhancedImage(result.upscaled_image);
                setProcessingMetadata(result.metadata);
                setShowOriginal(false); // Auto-switch to enhanced view
                console.log('[ReviewScreen] ✅ Backend processing complete!');
                console.log('Processing time:', result.processing_time_ms, 'ms');
                console.log('Iris-SAM quality:', result.metadata?.mask_quality_score);
            } else {
                throw new Error(result.error || 'Enhancement returned null');
            }
        } catch (err) {
            console.error('[ReviewScreen] Backend processing failed:', err);
            setEnhancementError(
                err instanceof Error
                    ? err.message
                    : 'AI enhancement failed. Check backend connection.'
            );
        } finally {
            setIsEnhancing(false);
        }
    };

    const handleDownload = (imageData: string, filename: string) => {
        const link = document.createElement('a');
        link.href = imageData;
        link.download = filename;
        link.click();
    };

    return (
        <div className="min-h-screen bg-black flex flex-col">
            {/* Header with Backend Status */}
            <div className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
                <h1 className="text-sm font-mono text-gray-400 tracking-wider">IRIS CAPTURE REVIEW</h1>

                {/* Backend Status Indicator */}
                <div className="flex items-center gap-2">
                    {backendAvailable === true && (
                        <>
                            <Wifi className="w-4 h-4 text-emerald-500" />
                            <span className="text-xs font-mono text-emerald-500">Backend Ready</span>
                        </>
                    )}
                    {backendAvailable === false && (
                        <>
                            <WifiOff className="w-4 h-4 text-red-500" />
                            <span className="text-xs font-mono text-red-500">Backend Offline</span>
                        </>
                    )}
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 flex flex-col items-center justify-center px-6 py-12">
                <div className="max-w-4xl w-full space-y-8">
                    {/* Image Preview */}
                    {viewMode === 'single' ? (
                        <div className="bg-gray-900 border border-gray-800 p-8 flex items-center justify-center relative min-h-[400px]">
                            <img
                                src={showOriginal ? irisCrop : (enhancedImage || irisCrop)}
                                alt="Iris capture"
                                className="max-w-full h-auto"
                                style={{ imageRendering: showOriginal ? 'auto' : 'crisp-edges' }}
                            />
                            
                            {/* Enhancement Progress Overlay */}
                            {isEnhancing && (
                                <div className="absolute inset-0 bg-black/90 backdrop-blur-sm flex items-center justify-center">
                                    <div className="text-center space-y-4">
                                        <Sparkles className="w-12 h-12 text-emerald-500 mx-auto animate-pulse" />
                                        <div className="space-y-1">
                                            <p className="text-base font-medium text-white">Processing...</p>
                                            <p className="text-sm font-mono text-gray-400">Iris-SAM Segmentation + Real-ESRGAN 4x</p>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    ) : (
                        /* Side-by-Side Comparison */
                        <div className="grid grid-cols-2 gap-4">
                            {/* Original */}
                            <div className="bg-gray-900 border border-gray-800 p-6 flex flex-col">
                                <div className="text-xs font-mono text-gray-500 mb-3 text-center uppercase tracking-wider">
                                    Original
                                </div>
                                <div className="flex-1 flex items-center justify-center">
                                    <img
                                        src={irisCrop}
                                        alt="Original iris"
                                        className="max-w-full h-auto"
                                        style={{ imageRendering: 'auto' }}
                                    />
                                </div>
                            </div>

                            {/* Enhanced */}
                            <div className="bg-gray-900 border border-emerald-800/50 p-6 flex flex-col">
                                <div className="text-xs font-mono text-emerald-500 mb-3 text-center uppercase tracking-wider">
                                    Enhanced (Iris-SAM + ESRGAN)
                                </div>
                                <div className="flex-1 flex items-center justify-center">
                                    {enhancedImage ? (
                                        <img
                                            src={enhancedImage}
                                            alt="Enhanced iris"
                                            className="max-w-full h-auto"
                                            style={{ imageRendering: 'crisp-edges' }}
                                        />
                                    ) : (
                                        <div className="text-center text-gray-600">
                                            <Sparkles className="w-8 h-8 mx-auto mb-2 opacity-50" />
                                            <p className="text-xs font-mono">Not enhanced yet</p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Processing Metadata Display */}
                    {processingMetadata && (
                        <div className="bg-gray-900 border border-gray-800 p-4 rounded font-mono text-xs">
                            <div className="grid grid-cols-2 gap-3 text-gray-400">
                                <div>
                                    <span className="text-gray-500">Iris-SAM:</span>{' '}
                                    <span className="text-emerald-400">
                                        {processingMetadata.iris_sam_time_ms?.toFixed(0)}ms
                                    </span>
                                </div>
                                <div>
                                    <span className="text-gray-500">Real-ESRGAN:</span>{' '}
                                    <span className="text-emerald-400">
                                        {processingMetadata.esrgan_time_ms?.toFixed(0)}ms
                                    </span>
                                </div>
                                <div>
                                    <span className="text-gray-500">Mask Quality:</span>{' '}
                                    <span className="text-emerald-400">
                                        {(processingMetadata.mask_quality_score * 100)?.toFixed(1)}%
                                    </span>
                                </div>
                                <div>
                                    <span className="text-gray-500">Total:</span>{' '}
                                    <span className="text-emerald-400">
                                        {((processingMetadata.iris_sam_time_ms || 0) +
                                          (processingMetadata.esrgan_time_ms || 0))?.toFixed(0)}ms
                                    </span>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* View Mode Controls */}
                    <div className="flex items-center justify-between text-sm font-mono">
                        {viewMode === 'single' && (
                            <span className="text-gray-400">
                                {showOriginal ? 'Original Crop' : 'Enhanced (Iris-SAM + ESRGAN)'}
                            </span>
                        )}
                        
                        <div className="flex items-center gap-3 ml-auto">
                            {/* Single View Toggle */}
                            {viewMode === 'single' && enhancedImage && !isEnhancing && (
                                <button
                                    onClick={() => setShowOriginal(!showOriginal)}
                                    className="text-emerald-400 underline hover:text-emerald-300 transition-colors"
                                >
                                    {showOriginal ? 'View Enhanced' : 'View Original'}
                                </button>
                            )}
                            
                            {/* Comparison Mode Button */}
                            {enhancedImage && !isEnhancing && (
                                <button
                                    onClick={() => setViewMode(viewMode === 'single' ? 'comparison' : 'single')}
                                    className="flex items-center gap-2 px-3 py-1.5 border border-gray-700 text-gray-400 hover:text-white hover:border-gray-600 transition-colors rounded"
                                >
                                    <SlidersHorizontal className="w-4 h-4" />
                                    {viewMode === 'single' ? 'Compare' : 'Single View'}
                                </button>
                            )}
                        </div>
                    </div>

                    {/* Enhance Button - Only show if not enhanced yet */}
                    {!enhancedImage && !isEnhancing && (
                        <button
                            onClick={handleEnhance}
                            disabled={!backendAvailable}
                            className="w-full bg-gradient-to-r from-emerald-600 to-emerald-500
                             text-white font-medium py-4 px-6
                             hover:from-emerald-500 hover:to-emerald-400
                             disabled:from-gray-700 disabled:to-gray-600
                             disabled:cursor-not-allowed
                             transition-all flex items-center justify-center gap-3
                             shadow-lg shadow-emerald-900/50"
                        >
                            <Sparkles className="w-5 h-5" />
                            {backendAvailable
                                ? 'Enhance with Iris-SAM + Real-ESRGAN'
                                : 'Backend Server Required'}
                        </button>
                    )}

                    {/* Error Message */}
                    {enhancementError && (
                        <div className="bg-red-900/20 border border-red-900/50 rounded-lg p-4">
                            <div className="flex items-center justify-between">
                                <p className="text-red-400 text-sm">{enhancementError}</p>
                                <button
                                    onClick={handleEnhance}
                                    className="text-red-400 underline hover:text-red-300 text-sm"
                                >
                                    Retry
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Action Buttons */}
                    <div className="flex gap-4">
                        <button
                            onClick={onRetake}
                            className="flex-1 border border-gray-700 text-white font-medium py-4 px-6 hover:bg-gray-900 transition-colors flex items-center justify-center gap-2"
                        >
                            <RotateCcw className="w-5 h-5" />
                            Retake
                        </button>

                        <button
                            onClick={() => handleDownload(irisCrop, 'iris-original.jpg')}
                            className="flex-1 bg-white text-black font-medium py-4 px-6 hover:bg-gray-100 transition-colors flex items-center justify-center gap-2"
                        >
                            <Download className="w-5 h-5" />
                            Download Original
                        </button>
                    </div>

                    {/* Download Enhanced - Only show after enhancement */}
                    {enhancedImage && (
                        <button
                            onClick={() => handleDownload(enhancedImage, 'iris-enhanced.png')}
                            className="w-full border border-emerald-900/50 bg-emerald-900/10 text-emerald-400 font-mono text-sm py-3 hover:bg-emerald-900/20 transition-colors flex items-center justify-center gap-2"
                        >
                            <Sparkles className="w-4 h-4" />
                            Download Enhanced (Iris-SAM + ESRGAN)
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}
