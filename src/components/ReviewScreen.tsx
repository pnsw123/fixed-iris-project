/**
 * ReviewScreen.tsx — Post-capture review, AI enhancement, and purchase/download flow.
 *
 * ## Responsibility
 * Receives a validated `CaptureData` payload from `MobileCaptureScreen`, sends it
 * to the Python backend for Iris-SAM segmentation + Real-ESRGAN 4× upscaling, and
 * manages the complete purchase-to-download lifecycle. It is the only component
 * that talks directly to the backend payment and download APIs.
 *
 * ## Key flows
 *
 * ### Enhancement flow
 * ```
 * mount → health-check backend → user taps "Enhance"
 *       → POST /api/process-iris  (Iris-SAM + ESRGAN)
 *       → receive { preview_image, purchase_token }
 *       → display watermarked 360p preview
 * ```
 *
 * ### Purchase / download state machine
 * ```
 * "Download HD" tapped
 *   → email modal (collect + validate email)
 *   → store { token, email } in localStorage (crash recovery)
 *   → LEMONSQUEEZY_CHECKOUT_URL set?
 *       YES → open Lemon Squeezy checkout in new tab
 *             downloadStatus = 'pending'
 *             user completes payment externally
 *             user returns → taps "Download" buttons
 *             → POST /api/download-demo + /api/download-original-demo
 *       NO  → demo mode: skip payment, downloadStatus = 'success'
 *             download buttons unlocked immediately
 * ```
 *
 * ### Crash-recovery flow
 * On mount, `localStorage['eyedentity_purchase']` is checked. If a previous
 * session stored a token (e.g. page was refreshed mid-checkout), the component
 * immediately retries `POST /api/download-hd` to resume the download without
 * requiring the user to re-authenticate.
 *
 * ## Non-obvious design decisions
 * - **Two-phase dual download** (`attemptDownload`): both blobs are fetched in
 *   parallel first, then both `<a>` clicks are fired within 100 ms of each other.
 *   Fetching and clicking simultaneously would trigger mobile popup-blockers;
 *   fetching first and then clicking avoids that.
 * - **`purchaseToken` is server-side session key**: the backend stores the
 *   processed image against the token. The client never holds the full HD image
 *   in memory — only a 360p watermarked preview. This prevents trivial bypass by
 *   inspecting network responses.
 * - **`emailVerified` flag** (not payment-verified): gates the download buttons
 *   on email collection only, not on confirmed payment. Actual payment enforcement
 *   happens server-side when the Lemon Squeezy webhook updates the token's status.
 * - **`BACKEND_URL` resolution**: uses `window.location.hostname` at runtime
 *   rather than a static env var so the same build works on both localhost and
 *   any remote host (e.g. an IP address on the local network during device testing).
 *
 * ## Props
 * - `captureData: CaptureData` — cropped iris image + metadata from capture screen
 * - `onRetake` — called when the user taps "Retake"; parent resets to capture screen
 */
'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Download, RotateCcw, Sparkles, Wifi, WifiOff, Mail, X, Loader2 } from 'lucide-react';
import { backendClient } from '@/lib/backendClient';
import { CaptureData } from './MobileCaptureScreen';
import AppHeader from './AppHeader';
import SpotlightBackground from './SpotlightBackground';
import { useToast } from '@/lib/toast';

interface ReviewScreenProps {
    captureData: CaptureData;
    onRetake: () => void;
}

// Lemon Squeezy configuration (set these when you have credentials)
const LEMONSQUEEZY_CHECKOUT_URL = process.env.NEXT_PUBLIC_LEMONSQUEEZY_CHECKOUT_URL || '';
const BACKEND_URL = typeof window !== 'undefined'
    ? (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1'
        ? `https://${window.location.hostname}:8000`
        : 'https://localhost:8000')
    : 'https://localhost:8000';

export default function ReviewScreen({ captureData, onRetake }: ReviewScreenProps) {
    const { imageData: irisCrop, irisCoordinates, cropSize, irisRadius } = captureData;
    const { toast } = useToast();

    // Image states
    const [previewImage, setPreviewImage] = useState<string | null>(null);
    const [purchaseToken, setPurchaseToken] = useState<string | null>(null);

    // UI states
    const [isEnhancing, setIsEnhancing] = useState(false);
    const [backendAvailable, setBackendAvailable] = useState<boolean | null>(null);
    const [irisImageLoaded, setIrisImageLoaded] = useState(false);

    // Payment flow states
    const [showEmailModal, setShowEmailModal] = useState(false);
    const [userEmail, setUserEmail] = useState('');
    const [emailError, setEmailError] = useState<string | null>(null);
    const [isDownloading, setIsDownloading] = useState(false);
    const [downloadPending, setDownloadPending] = useState(false);
    const [emailVerified, setEmailVerified] = useState(false);  // Unlocks download buttons

    // Check backend availability on mount — intentional empty deps, runs once on mount
    /* eslint-disable react-hooks/exhaustive-deps */
    useEffect(() => {
        const checkBackend = async () => {
            const available = await backendClient.healthCheck();
            setBackendAvailable(available);
        };
        void checkBackend();

        // Check for pending purchase in localStorage (recovery after page refresh)
        const storedPurchase = localStorage.getItem('eyedentity_purchase');
        if (storedPurchase) {
            try {
                const { token, email } = JSON.parse(storedPurchase) as { token: string; email?: string };
                setPurchaseToken(token);
                setUserEmail(email ?? '');
                // Try to recover download
                void attemptRecoveryDownload(token);
            } catch {
                localStorage.removeItem('eyedentity_purchase');
            }
        }
    }, []);
    /* eslint-enable react-hooks/exhaustive-deps */

    const attemptRecoveryDownload = async (token: string) => {
        try {
            const response = await fetch(`${BACKEND_URL}/api/download-hd`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token })
            });

            if (response.ok) {
                const blob = await response.blob();
                downloadBlobReliable(blob, 'eyedentity-hd.png');
                localStorage.removeItem('eyedentity_purchase');
                toast.success('Download recovered! Check your downloads folder.');
            }
        } catch {
            // Silent fail - user can try again
        }
    };

    const handleEnhance = async () => {
        setIsEnhancing(true);

        try {
            console.log('[ReviewScreen] Sending to backend for Iris-SAM + ESRGAN processing...');

            const result = await backendClient.processIris(irisCrop, {
                return_mask: false,
                return_intermediate: false,
                upscale_factor: 4,
                irisCoordinates: irisCoordinates,
                cropSize: cropSize,
                irisRadius: irisRadius,
            });

            if (result.success && result.preview_image && result.purchase_token) {
                setPreviewImage(result.preview_image);
                setPurchaseToken(result.purchase_token);
                console.log('[ReviewScreen] ✅ Backend processing complete!');
                toast.success('Enhancement complete — HD preview ready!');
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

    const handleDownloadHDClick = () => {
        // Show email collection modal
        setShowEmailModal(true);
        setEmailError(null);
    };

    const validateEmail = (email: string): boolean => {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    };

    const handleEmailSubmit = async () => {
        if (!validateEmail(userEmail)) {
            setEmailError('Please enter a valid email address');
            return;
        }

        // Store in localStorage for recovery
        localStorage.setItem('eyedentity_purchase', JSON.stringify({
            token: purchaseToken,
            email: userEmail,
            timestamp: Date.now()
        }));

        // Update backend with email
        try {
            await fetch(`${BACKEND_URL}/api/update-purchase-email`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: purchaseToken, email: userEmail }),
            });
        } catch {
            // Non-critical - continue anyway
        }

        setShowEmailModal(false);
        setEmailVerified(true);  // Unlock download buttons

        // Check if Lemon Squeezy is configured
        if (LEMONSQUEEZY_CHECKOUT_URL) {
            // Open Lemon Squeezy checkout
            const checkoutUrl = new URL(LEMONSQUEEZY_CHECKOUT_URL);
            checkoutUrl.searchParams.set('checkout[custom][image_token]', purchaseToken || '');
            checkoutUrl.searchParams.set('checkout[custom][user_email]', userEmail);
            checkoutUrl.searchParams.set('checkout[email]', userEmail);

            window.open(checkoutUrl.toString(), '_blank');

            setDownloadPending(true);
            toast.info('Complete payment in the new tab, then tap the download buttons below.', 8000);
        } else {
            // Demo mode - downloads are ready, no auto-download
            setDownloadPending(false);
            toast.success('Your images are ready! Tap each button below to download.');
        }

        // Scroll to download buttons after a brief delay
        setTimeout(() => {
            const downloadSection = document.getElementById('download-buttons');
            if (downloadSection) {
                downloadSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }, 100);
    };

    const attemptDownload = async () => {
        if (!purchaseToken) return;

        setIsDownloading(true);
        toast.info('Fetching your images...');

        try {
            // STEP 1: Fetch BOTH images first (before triggering any downloads)
            const [hdResponse, originalResponse] = await Promise.all([
                fetch(`${BACKEND_URL}/api/download-demo`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token: purchaseToken })
                }),
                fetch(`${BACKEND_URL}/api/download-original-demo`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token: purchaseToken })
                })
            ]);

            if (!hdResponse.ok) {
                const data = await hdResponse.json().catch(() => ({}));
                throw new Error(data.error || 'Failed to fetch HD image');
            }

            if (!originalResponse.ok) {
                const data = await originalResponse.json().catch(() => ({}));
                throw new Error(data.error || 'Failed to fetch original image');
            }

            // STEP 2: Convert both to blobs
            const [hdBlob, originalBlob] = await Promise.all([
                hdResponse.blob(),
                originalResponse.blob()
            ]);

            // STEP 3: Trigger both downloads (nearly simultaneously)
            // Download HD first
            downloadBlobReliable(hdBlob, 'eyedentity-hd.png');

            // Tiny delay then download original
            await new Promise(resolve => setTimeout(resolve, 100));
            downloadBlobReliable(originalBlob, 'eyedentity-original.png');

            localStorage.removeItem('eyedentity_purchase');
            setDownloadPending(false);
            toast.success('Both images downloaded! Check your downloads folder.');

        } catch (error) {
            console.error('[Download] Error:', error);
            toast.error(error instanceof Error ? error.message : 'Download failed. Please try again.');
        } finally {
            setIsDownloading(false);
        }
    };

    // Individual download function - handles one image at a time (for mobile reliability)
    const downloadImage = async (type: 'hd' | 'original') => {
        if (!purchaseToken) return;

        setIsDownloading(true);
        toast.info(`Downloading ${type === 'hd' ? 'HD Enhanced' : 'Original'}...`);

        try {
            const endpoint = type === 'hd'
                ? `${BACKEND_URL}/api/download-demo`
                : `${BACKEND_URL}/api/download-original-demo`;

            const filename = type === 'hd'
                ? 'eyedentity-hd.png'
                : 'eyedentity-original.png';

            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: purchaseToken })
            });

            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.error || `Failed to download ${type} image`);
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
        // Create object URL
        const url = URL.createObjectURL(blob);

        // Create and configure link element
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        link.style.display = 'none';

        // Append to body (more reliable on mobile)
        document.body.appendChild(link);

        // Click to trigger download
        link.click();

        // Clean up after a short delay
        setTimeout(() => {
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        }, 1000);
    };

    return (
        <div className="min-h-screen bg-black flex flex-col relative overflow-hidden">
            <SpotlightBackground />

            {/* Page entry: whole screen slides up + fades in */}
            <motion.div
                className="flex flex-col flex-1"
                initial={{ opacity: 0, y: 28 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
            >

            {/* Header with Backend Status */}
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

            {/* Main Content */}
            <div className="flex-1 flex flex-col items-center justify-center px-8 py-16 sm:px-16 relative z-10">
                <div className="max-w-4xl w-full space-y-8">
                    {/* Image Preview — staggered entrance */}
                    <motion.div
                        className="flex flex-col items-center"
                        initial={{ opacity: 0, scale: 0.96 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: 0.12, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
                    >
                        <div className="bg-gray-900 border border-gray-800 p-4 flex items-center justify-center relative aspect-[4/3] w-full overflow-hidden">
                            <AnimatePresence mode="wait">
                                {previewImage ? (
                                    /* Enhanced preview — iris unveil: circular mask expand + glitch + bloom + shimmer */
                                    <motion.div
                                        key="enhanced"
                                        className="relative"
                                        initial={{
                                            opacity: 0,
                                            scale: 0.88,
                                            clipPath: 'circle(0% at 50% 50%)',
                                        }}
                                        animate={{
                                            opacity: 1,
                                            scale: 1,
                                            clipPath: 'circle(75% at 50% 50%)',
                                        }}
                                        exit={{ opacity: 0, scale: 0.95 }}
                                        transition={{
                                            duration: 0.85,
                                            ease: [0.22, 1, 0.36, 1],
                                        }}
                                    >
                                        <motion.img
                                            src={previewImage}
                                            alt="Enhanced iris"
                                            className="max-w-full h-auto"
                                            style={{ imageRendering: 'crisp-edges' }}
                                        />

                                        {/* Glitch flicker overlay — rapid opacity pulses on reveal */}
                                        <motion.div
                                            className="pointer-events-none absolute inset-0 bg-emerald-400/20 mix-blend-screen"
                                            initial={{ opacity: 0 }}
                                            animate={{
                                                opacity: [0, 0.55, 0, 0.35, 0, 0.18, 0],
                                            }}
                                            transition={{
                                                duration: 0.38,
                                                delay: 0.08,
                                                ease: 'linear',
                                            }}
                                        />

                                        {/* Radial bloom ring — expands outward from iris center */}
                                        <motion.div
                                            className="pointer-events-none absolute inset-0"
                                            initial={{ opacity: 0.75, scale: 0.25 }}
                                            animate={{ opacity: 0, scale: 1.7 }}
                                            transition={{
                                                duration: 0.8,
                                                delay: 0.04,
                                                ease: 'easeOut',
                                            }}
                                            style={{
                                                background:
                                                    'radial-gradient(circle, rgba(52,211,153,0.4) 0%, transparent 65%)',
                                            }}
                                        />

                                        {/* Shimmer sweep — fires after mask settle */}
                                        <motion.div
                                            className="pointer-events-none absolute inset-0"
                                            initial={{ x: '-100%', opacity: 0.7 }}
                                            animate={{ x: '200%', opacity: 0 }}
                                            transition={{ duration: 1.1, ease: 'easeInOut', delay: 0.5 }}
                                            style={{
                                                background:
                                                    'linear-gradient(105deg, transparent 30%, rgba(255,255,255,0.28) 50%, transparent 70%)',
                                            }}
                                        />

                                        {/* "Enhancement Complete" badge — flashes once then fades */}
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
                                    /* Original capture */
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

                            {/* Loading Skeleton — shown while original iris image loads */}
                            <AnimatePresence>
                                {!irisImageLoaded && !previewImage && !isEnhancing && (
                                    <motion.div
                                        key="skeleton"
                                        className="absolute inset-0 flex items-center justify-center"
                                        initial={{ opacity: 1 }}
                                        exit={{ opacity: 0 }}
                                        transition={{ duration: 0.25 }}
                                    >
                                        {/* Pulsing skeleton circle mimicking iris shape */}
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

                            {/* Enhancement Progress Overlay */}
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

                            {/* Watermark indicator — delayed so it doesn't compete with reveal */}
                            <AnimatePresence>
                                {previewImage && (
                                    <motion.div
                                        key="watermark"
                                        className="absolute bottom-2 right-2 bg-black/70 px-2 py-1 rounded text-xs font-mono text-gray-400"
                                        initial={{ opacity: 0, y: 6 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        transition={{ delay: 1.4, duration: 0.35 }}
                                    >
                                        Preview 360p (Watermarked)
                                    </motion.div>
                                )}
                            </AnimatePresence>
                        </div>
                    </motion.div>

                    {/* Enhance Button — premium brand CTA with shimmer + glow pulse */}
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
                                opacity: 1,
                                scale: 1,
                                y: 0,
                                boxShadow: backendAvailable
                                    ? [
                                        '0 8px 32px -4px rgba(139,92,246,0.35)',
                                        '0 8px 40px -4px rgba(139,92,246,0.65)',
                                        '0 8px 32px -4px rgba(139,92,246,0.35)',
                                      ]
                                    : '0 4px 16px -4px rgba(0,0,0,0.3)',
                            }}
                            exit={{ opacity: 0, scale: 0.9, y: 12 }}
                            transition={{
                                opacity: { delay: 0.35, duration: 0.45, ease: [0.22, 1, 0.36, 1] },
                                scale:   { delay: 0.35, duration: 0.45, ease: [0.22, 1, 0.36, 1] },
                                y:       { delay: 0.35, duration: 0.45, ease: [0.22, 1, 0.36, 1] },
                                boxShadow: { duration: 2.4, repeat: Infinity, ease: 'easeInOut' },
                            }}
                            whileHover={{
                                scale: backendAvailable ? 1.02 : 1,
                                boxShadow: '0 12px 48px -4px rgba(139,92,246,0.75)',
                            }}
                            whileTap={{ scale: backendAvailable ? 0.97 : 1 }}
                        >
                            {/* Shimmer sweep — animates on loop when enabled */}
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
                                {backendAvailable
                                    ? 'Enhance My Iris'
                                    : 'Backend Server Required'}
                            </span>
                        </motion.button>
                    )}
                    </AnimatePresence>

                    {/* Pending payment indicator */}
                    {downloadPending && (
                        <div className="bg-blue-950/40 border border-blue-800/40 rounded-lg p-3 flex items-center gap-3">
                            <Loader2 className="w-4 h-4 text-blue-400 animate-spin shrink-0" />
                            <div className="flex-1 min-w-0">
                                <p className="text-blue-300 text-sm">Waiting for payment confirmation</p>
                                <button
                                    onClick={() => { void attemptDownload(); }}
                                    disabled={isDownloading}
                                    className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] mt-1 px-3 py-2.5 rounded-md text-sm font-medium text-blue-300 bg-blue-900/30 border border-blue-700/40 hover:bg-blue-900/50 hover:text-blue-200 hover:border-blue-600/60 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1 focus-visible:ring-offset-transparent"
                                >
                                    {isDownloading ? 'Checking...' : 'Already paid? Check now'}
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
                    </div>

                    {/* Download Buttons - Show after enhancement */}
                    {previewImage && purchaseToken && (
                        <div id="download-buttons" className="space-y-3">
                            {/* Before email: Show single "Unlock HD" button */}
                            {!emailVerified && (
                                <>
                                    <button
                                        onClick={handleDownloadHDClick}
                                        disabled={isDownloading}
                                        className="w-full bg-gradient-to-r from-amber-600 to-amber-500
                                         text-white font-medium py-4 px-6
                                         hover:from-amber-500 hover:to-amber-400
                                         disabled:opacity-50 disabled:cursor-not-allowed
                                         transition-all flex items-center justify-center gap-3
                                         shadow-lg shadow-amber-900/50"
                                    >
                                        <Download className="w-5 h-5" />
                                        Unlock HD Images - $2.99
                                    </button>
                                    <p className="text-center text-xs text-gray-400">
                                        Get full resolution, watermark-free images
                                    </p>
                                </>
                            )}

                            {/* After email: Show two download buttons */}
                            {emailVerified && (
                                <>
                                    {/* Download HD Enhanced */}
                                    <button
                                        onClick={() => { void downloadImage('hd'); }}
                                        disabled={isDownloading}
                                        className="w-full bg-gradient-to-r from-amber-600 to-amber-500
                                         text-white font-medium py-4 px-6
                                         hover:from-amber-500 hover:to-amber-400
                                         disabled:opacity-50 disabled:cursor-not-allowed
                                         transition-all flex items-center justify-center gap-3
                                         shadow-lg shadow-amber-900/50"
                                    >
                                        {isDownloading ? (
                                            <Loader2 className="w-5 h-5 animate-spin" />
                                        ) : (
                                            <Download className="w-5 h-5" />
                                        )}
                                        Download HD Enhanced
                                    </button>

                                    {/* Download Original */}
                                    <button
                                        onClick={() => { void downloadImage('original'); }}
                                        disabled={isDownloading}
                                        className="w-full border border-gray-600 bg-gray-800/50
                                         text-gray-300 font-medium py-3 px-6
                                         hover:bg-gray-700 hover:text-white
                                         disabled:opacity-50 disabled:cursor-not-allowed
                                         transition-all flex items-center justify-center gap-3"
                                    >
                                        <Download className="w-4 h-4" />
                                        Download Original Capture
                                    </button>

                                    <p className="text-center text-xs text-gray-500">
                                        Tap each button to download both images
                                    </p>
                                </>
                            )}
                        </div>
                    )}
                </div>
            </div>

            </motion.div>{/* end page entry wrapper */}

            {/* Email Collection Modal */}
            {showEmailModal && (
                <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                    <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-md w-full">
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-xl font-semibold text-white">Almost there!</h3>
                            <button
                                onClick={() => setShowEmailModal(false)}
                                className="text-gray-500 hover:text-gray-300"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        </div>

                        <p className="text-gray-400 text-sm mb-6">
                            Enter your email to receive your HD iris image. We&apos;ll also send a backup download link.
                        </p>

                        <div className="space-y-4">
                            <div>
                                <div className="flex items-center gap-2 bg-gray-800 border border-gray-600 rounded-lg px-4 py-3">
                                    <Mail className="w-5 h-5 text-gray-500" />
                                    <input
                                        type="email"
                                        value={userEmail}
                                        onChange={(e) => {
                                            setUserEmail(e.target.value);
                                            setEmailError(null);
                                        }}
                                        placeholder="your@email.com"
                                        className="flex-1 bg-transparent text-white placeholder-gray-500 outline-none"
                                        autoFocus
                                    />
                                </div>
                                {emailError && (
                                    <p className="text-red-400 text-xs mt-1">{emailError}</p>
                                )}
                            </div>

                            <button
                                onClick={() => { void handleEmailSubmit(); }}
                                className="w-full bg-gradient-to-r from-emerald-600 to-emerald-500
                                 text-white font-medium py-3 rounded-lg
                                 hover:from-emerald-500 hover:to-emerald-400
                                 transition-all"
                            >
                                Continue to Payment ($2.99)
                            </button>

                            <p className="text-gray-500 text-xs text-center">
                                Your HD image will be available immediately after payment.
                            </p>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
