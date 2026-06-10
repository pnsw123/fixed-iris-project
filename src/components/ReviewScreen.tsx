'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Download, RotateCcw, Sparkles, Wifi, WifiOff, Loader2 } from 'lucide-react';
import { backendClient } from '@/lib/backendClient';
import { CaptureData } from './MobileCaptureScreen';
import AppHeader from './AppHeader';
import SpotlightBackground from './SpotlightBackground';
import { useToast } from '@/lib/toast';

interface ReviewScreenProps {
    captureData: CaptureData;
    onRetake: () => void;
}

const BACKEND_URL = typeof window !== 'undefined'
    ? (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1'
        ? `https://${window.location.hostname}:8000`
        : 'https://localhost:8000')
    : 'https://localhost:8000';

export default function ReviewScreen({ captureData, onRetake }: ReviewScreenProps) {
    const { imageData: irisCrop, irisCoordinates, cropSize, irisRadius } = captureData;
    const { toast } = useToast();

    const [previewImage, setPreviewImage] = useState<string | null>(null);
    const [sessionToken, setSessionToken] = useState<string | null>(null);

    const [isEnhancing, setIsEnhancing] = useState(false);
    const [isDownloading, setIsDownloading] = useState(false);
    const [backendAvailable, setBackendAvailable] = useState<boolean | null>(null);
    const [irisImageLoaded, setIrisImageLoaded] = useState(false);

    // Check backend on mount
    /* eslint-disable react-hooks/exhaustive-deps */
    useEffect(() => {
        const checkBackend = async () => {
            const available = await backendClient.healthCheck();
            setBackendAvailable(available);
        };
        void checkBackend();
    }, []);
    /* eslint-enable react-hooks/exhaustive-deps */

    const handleEnhance = async () => {
        setIsEnhancing(true);
        try {
            const result = await backendClient.processIris(irisCrop, {
                return_mask: false,
                return_intermediate: false,
                upscale_factor: 4,
                irisCoordinates,
                cropSize,
                irisRadius,
            });

            if (result.success && result.preview_image && result.download_token) {
                setPreviewImage(result.preview_image);
                setSessionToken(result.download_token);
                toast.success('Enhancement complete — ready to download!');
            } else {
                throw new Error(result.error || 'Enhancement failed');
            }
        } catch (err) {
            console.error('[ReviewScreen] Backend processing failed:', err);
            toast.error(
                err instanceof Error
                    ? err.message
                    : 'AI enhancement failed. Check backend connection.'
            );
        } finally {
            setIsEnhancing(false);
        }
    };

    const downloadImage = async (type: 'hd' | 'original') => {
        if (!sessionToken) return;
        setIsDownloading(true);
        toast.info(`Downloading ${type === 'hd' ? 'HD Enhanced' : 'Original'}...`);

        try {
            const endpoint = type === 'hd'
                ? `${BACKEND_URL}/api/download-hd`
                : `${BACKEND_URL}/api/download-original`;

            const filename = type === 'hd'
                ? 'eyedentity-hd.png'
                : 'eyedentity-original.png';

            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: sessionToken }),
            });

            if (!response.ok) {
                const data = await response.json().catch(() => ({})) as { error?: string };
                throw new Error(data.error ?? `Failed to download ${type} image`);
            }

            const blob = await response.blob();
            downloadBlobReliable(blob, filename);
            toast.success(`${type === 'hd' ? 'HD Enhanced' : 'Original'} downloaded!`);
        } catch (error) {
            console.error(`[Download ${type}] Error:`, error);
            toast.error(error instanceof Error ? error.message : 'Download failed.');
        } finally {
            setIsDownloading(false);
        }
    };

    const downloadBlobReliable = (blob: Blob, filename: string) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        setTimeout(() => {
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        }, 1000);
    };

    return (
        <div className="min-h-screen bg-black flex flex-col relative overflow-hidden">
            <SpotlightBackground color="rgba(251, 191, 36, 0.20)" />

            <motion.div
                className="flex flex-col flex-1"
                initial={{ opacity: 0, y: 28 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
            >

            <AppHeader
                title="IRIS CAPTURE REVIEW"
                showBack
                rightSlot={
                    <>
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
                    </>
                }
            />

            <div className="flex-1 flex flex-col items-center justify-center px-8 py-16 sm:px-16 relative z-10">
                <div className="max-w-4xl w-full space-y-8">

                    {/* Image Preview */}
                    <motion.div
                        className="flex flex-col items-center"
                        initial={{ opacity: 0, scale: 0.96 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: 0.12, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
                    >
                        <div className="bg-gray-900 border border-gray-800 p-4 flex items-center justify-center relative aspect-[4/3] w-full overflow-hidden">
                            <AnimatePresence mode="wait">
                                {previewImage ? (
                                    <motion.div
                                        key="enhanced"
                                        className="relative"
                                        initial={{ opacity: 0, scale: 0.88, clipPath: 'circle(0% at 50% 50%)' }}
                                        animate={{ opacity: 1, scale: 1, clipPath: 'circle(75% at 50% 50%)' }}
                                        exit={{ opacity: 0, scale: 0.95 }}
                                        transition={{ duration: 0.85, ease: [0.22, 1, 0.36, 1] }}
                                    >
                                        <motion.img
                                            src={previewImage}
                                            alt="Enhanced iris"
                                            className="max-w-full h-auto"
                                            style={{ imageRendering: 'crisp-edges' }}
                                        />

                                        {/* Glitch flicker */}
                                        <motion.div
                                            className="pointer-events-none absolute inset-0 bg-emerald-400/20 mix-blend-screen"
                                            initial={{ opacity: 0 }}
                                            animate={{ opacity: [0, 0.55, 0, 0.35, 0, 0.18, 0] }}
                                            transition={{ duration: 0.38, delay: 0.08, ease: 'linear' }}
                                        />

                                        {/* Radial bloom */}
                                        <motion.div
                                            className="pointer-events-none absolute inset-0"
                                            initial={{ opacity: 0.75, scale: 0.25 }}
                                            animate={{ opacity: 0, scale: 1.7 }}
                                            transition={{ duration: 0.8, delay: 0.04, ease: 'easeOut' }}
                                            style={{ background: 'radial-gradient(circle, rgba(52,211,153,0.4) 0%, transparent 65%)' }}
                                        />

                                        {/* Shimmer sweep */}
                                        <motion.div
                                            className="pointer-events-none absolute inset-0"
                                            initial={{ x: '-100%', opacity: 0.7 }}
                                            animate={{ x: '200%', opacity: 0 }}
                                            transition={{ duration: 1.1, ease: 'easeInOut', delay: 0.5 }}
                                            style={{ background: 'linear-gradient(105deg, transparent 30%, rgba(255,255,255,0.28) 50%, transparent 70%)' }}
                                        />

                                        {/* Enhancement Complete badge */}
                                        <motion.div
                                            className="pointer-events-none absolute inset-0 flex items-center justify-center"
                                            initial={{ opacity: 0 }}
                                            animate={{ opacity: [0, 1, 1, 0] }}
                                            transition={{ duration: 1.9, delay: 0.6, ease: 'easeInOut' }}
                                        >
                                            <motion.div
                                                className="bg-black/60 backdrop-blur-sm border border-emerald-500/60 px-4 py-2 rounded-full flex items-center gap-2"
                                                initial={{ scale: 0.75, y: 10 }}
                                                animate={{ scale: [0.75, 1.06, 1, 0.9], y: [10, 0, 0, 5] }}
                                                transition={{ duration: 1.9, delay: 0.6, ease: 'easeInOut' }}
                                            >
                                                <Sparkles className="w-4 h-4 text-emerald-400" />
                                                <span className="text-xs font-mono text-emerald-300 tracking-widest uppercase">
                                                    Enhancement Complete
                                                </span>
                                            </motion.div>
                                        </motion.div>
                                    </motion.div>
                                ) : (
                                    <motion.img
                                        key="original"
                                        src={irisCrop}
                                        alt="Iris capture"
                                        className="max-w-full h-auto"
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: irisImageLoaded ? 1 : 0 }}
                                        exit={{ opacity: 0 }}
                                        transition={{ duration: 0.3 }}
                                        style={{ imageRendering: 'auto' }}
                                        onLoad={() => setIrisImageLoaded(true)}
                                    />
                                )}
                            </AnimatePresence>

                            {/* Loading skeleton */}
                            <AnimatePresence>
                                {!irisImageLoaded && !previewImage && !isEnhancing && (
                                    <motion.div
                                        key="skeleton"
                                        className="absolute inset-0 flex items-center justify-center"
                                        initial={{ opacity: 1 }}
                                        exit={{ opacity: 0 }}
                                        transition={{ duration: 0.25 }}
                                    >
                                        <div className="relative flex items-center justify-center w-full h-full">
                                            <div className="w-2/3 aspect-square rounded-full bg-gray-800 animate-pulse" />
                                            <div className="absolute w-1/2 aspect-square rounded-full bg-gray-700/60 animate-pulse" style={{ animationDelay: '150ms' }} />
                                            <div className="absolute w-1/3 aspect-square rounded-full bg-gray-600/40 animate-pulse" style={{ animationDelay: '300ms' }} />
                                            <div className="absolute bottom-4 left-0 right-0 flex justify-center">
                                                <div className="h-2 w-24 rounded bg-gray-700 animate-pulse" />
                                            </div>
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>

                            {/* Enhancement progress overlay */}
                            <AnimatePresence>
                                {isEnhancing && (
                                    <motion.div
                                        key="enhancing-overlay"
                                        className="absolute inset-0 bg-black/90 backdrop-blur-sm flex items-center justify-center"
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        exit={{ opacity: 0 }}
                                        transition={{ duration: 0.3 }}
                                    >
                                        <div className="text-center space-y-4">
                                            <Sparkles className="w-12 h-12 text-emerald-500 mx-auto animate-pulse" />
                                            <div className="space-y-1">
                                                <p className="text-base font-medium text-white">Processing...</p>
                                                <p className="text-sm font-mono text-gray-400">AI Enhancement in progress</p>
                                            </div>
                                        </div>
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    </motion.div>

                    {/* Enhance button */}
                    <AnimatePresence>
                    {!previewImage && !isEnhancing && (
                        <motion.button
                            onClick={() => { void handleEnhance(); }}
                            disabled={!backendAvailable}
                            className={[
                                'relative w-full overflow-hidden',
                                'bg-gradient-to-r from-indigo-600 via-violet-600 to-purple-600',
                                'text-white font-semibold py-4 px-6',
                                'disabled:from-gray-700 disabled:via-gray-700 disabled:to-gray-600',
                                'disabled:cursor-not-allowed',
                                'flex items-center justify-center gap-3',
                                'rounded-lg',
                                'ring-1 ring-violet-400/25',
                                'shadow-lg shadow-violet-900/50',
                            ].join(' ')}
                            initial={{ opacity: 0, scale: 0.9, y: 18 }}
                            animate={{
                                opacity: 1, scale: 1, y: 0,
                                boxShadow: backendAvailable
                                    ? ['0 8px 32px -4px rgba(139,92,246,0.35)', '0 8px 40px -4px rgba(139,92,246,0.65)', '0 8px 32px -4px rgba(139,92,246,0.35)']
                                    : '0 4px 16px -4px rgba(0,0,0,0.3)',
                            }}
                            exit={{ opacity: 0, scale: 0.9, y: 12 }}
                            transition={{
                                opacity:    { delay: 0.35, duration: 0.45, ease: [0.22, 1, 0.36, 1] },
                                scale:      { delay: 0.35, duration: 0.45, ease: [0.22, 1, 0.36, 1] },
                                y:          { delay: 0.35, duration: 0.45, ease: [0.22, 1, 0.36, 1] },
                                boxShadow:  { duration: 2.4, repeat: Infinity, ease: 'easeInOut' },
                            }}
                            whileHover={{ scale: backendAvailable ? 1.02 : 1, boxShadow: '0 12px 48px -4px rgba(139,92,246,0.75)' }}
                            whileTap={{ scale: backendAvailable ? 0.97 : 1 }}
                        >
                            {backendAvailable && (
                                <motion.span
                                    aria-hidden
                                    className="pointer-events-none absolute inset-0 w-1/3 bg-gradient-to-r from-transparent via-white/20 to-transparent skew-x-[-20deg]"
                                    animate={{ x: ['-120%', '320%'] }}
                                    transition={{ duration: 2.8, repeat: Infinity, repeatDelay: 1.6, ease: 'easeInOut' }}
                                />
                            )}
                            <Sparkles className="w-5 h-5 relative z-10" />
                            <span className="relative z-10">
                                {backendAvailable ? 'Enhance My Iris' : 'Backend Server Required'}
                            </span>
                        </motion.button>
                    )}
                    </AnimatePresence>

                    {/* Action buttons */}
                    <div className="flex gap-4">
                        <button
                            onClick={onRetake}
                            className="flex-1 border border-gray-700 text-white font-medium py-4 px-6 hover:bg-gray-900 transition-colors flex items-center justify-center gap-2"
                        >
                            <RotateCcw className="w-5 h-5" />
                            Retake
                        </button>
                    </div>

                    {/* Download buttons — shown immediately after enhancement, no gate */}
                    {previewImage && sessionToken && (
                        <div id="download-buttons" className="space-y-3">
                            <button
                                onClick={() => { void downloadImage('hd'); }}
                                disabled={isDownloading}
                                className="w-full bg-gradient-to-r from-emerald-600 to-emerald-500
                                 text-white font-medium py-4 px-6
                                 hover:from-emerald-500 hover:to-emerald-400
                                 disabled:opacity-50 disabled:cursor-not-allowed
                                 transition-all flex items-center justify-center gap-3
                                 shadow-lg shadow-emerald-900/50 rounded-lg"
                            >
                                {isDownloading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Download className="w-5 h-5" />}
                                Download HD Enhanced — Free
                            </button>

                            <button
                                onClick={() => { void downloadImage('original'); }}
                                disabled={isDownloading}
                                className="w-full border border-gray-600 bg-gray-800/50
                                 text-gray-300 font-medium py-3 px-6
                                 hover:bg-gray-700 hover:text-white
                                 disabled:opacity-50 disabled:cursor-not-allowed
                                 transition-all flex items-center justify-center gap-3 rounded-lg"
                            >
                                <Download className="w-4 h-4" />
                                Download Original Capture
                            </button>

                            <p className="text-center text-xs text-gray-500">
                                Both images are free — no account needed
                            </p>
                        </div>
                    )}
                </div>
            </div>

            </motion.div>
        </div>
    );
}
