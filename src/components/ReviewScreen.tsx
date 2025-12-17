'use client';

import { useState, useEffect } from 'react';
import { Download, RotateCcw, Sparkles, Wifi, WifiOff, Mail, X, Loader2 } from 'lucide-react';
import { backendClient } from '@/lib/backendClient';
import { CaptureData } from './MobileCaptureScreen';

interface ReviewScreenProps {
    captureData: CaptureData;
    userData?: {
        firstName: string;
        lastName: string;
        tribe: any;
    };
    onRetake: () => void;
}

// Lemon Squeezy configuration (set these when you have credentials)
const LEMONSQUEEZY_CHECKOUT_URL = process.env.NEXT_PUBLIC_LEMONSQUEEZY_CHECKOUT_URL || '';
const BACKEND_URL = typeof window !== 'undefined'
    ? (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1'
        ? `https://${window.location.hostname}:8000`
        : 'https://localhost:8000')
    : 'https://localhost:8000';

export default function ReviewScreen({ captureData, userData, onRetake }: ReviewScreenProps) {
    const { imageData: irisCrop, irisCoordinates, cropSize, irisRadius } = captureData;

    // Image states
    const [previewImage, setPreviewImage] = useState<string | null>(null);
    const [purchaseToken, setPurchaseToken] = useState<string | null>(null);

    // UI states
    const [isEnhancing, setIsEnhancing] = useState(false);
    const [enhancementError, setEnhancementError] = useState<string | null>(null);
    const [backendAvailable, setBackendAvailable] = useState<boolean | null>(null);
    const [processingMetadata, setProcessingMetadata] = useState<any>(null);

    // Payment flow states
    const [showEmailModal, setShowEmailModal] = useState(false);
    const [userEmail, setUserEmail] = useState('');
    const [emailError, setEmailError] = useState<string | null>(null);
    const [isDownloading, setIsDownloading] = useState(false);
    const [downloadStatus, setDownloadStatus] = useState<'idle' | 'pending' | 'success' | 'error'>('idle');
    const [downloadMessage, setDownloadMessage] = useState<string | null>(null);

    // Check backend availability on mount
    useEffect(() => {
        const checkBackend = async () => {
            const available = await backendClient.healthCheck();
            setBackendAvailable(available);
        };
        checkBackend();

        // Check for pending purchase in localStorage (recovery after page refresh)
        const storedPurchase = localStorage.getItem('eyedentity_purchase');
        if (storedPurchase) {
            try {
                const { token, email } = JSON.parse(storedPurchase);
                setPurchaseToken(token);
                setUserEmail(email || '');
                // Try to recover download
                attemptRecoveryDownload(token);
            } catch (e) {
                localStorage.removeItem('eyedentity_purchase');
            }
        }
    }, []);

    const attemptRecoveryDownload = async (token: string) => {
        try {
            const response = await fetch(`${BACKEND_URL}/api/download-hd`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token })
            });

            if (response.ok) {
                const blob = await response.blob();
                downloadBlob(blob, 'eyedentity-hd.png');
                localStorage.removeItem('eyedentity_purchase');
                setDownloadStatus('success');
                setDownloadMessage('Download recovered! Check your downloads folder.');
            }
        } catch {
            // Silent fail - user can try again
        }
    };

    const handleEnhance = async () => {
        setIsEnhancing(true);
        setEnhancementError(null);

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
                setProcessingMetadata(result.metadata);
                console.log('[ReviewScreen] ✅ Backend processing complete!');
                console.log('Purchase token:', result.purchase_token);
            } else {
                throw new Error(result.error || 'Enhancement failed');
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
            await fetch(`${BACKEND_URL}/api/update-purchase-email?token=${purchaseToken}&email=${encodeURIComponent(userEmail)}`, {
                method: 'POST'
            });
        } catch {
            // Non-critical - continue anyway
        }

        setShowEmailModal(false);

        // Check if Lemon Squeezy is configured
        if (LEMONSQUEEZY_CHECKOUT_URL) {
            // Open Lemon Squeezy checkout
            const checkoutUrl = new URL(LEMONSQUEEZY_CHECKOUT_URL);
            checkoutUrl.searchParams.set('checkout[custom][image_token]', purchaseToken || '');
            checkoutUrl.searchParams.set('checkout[custom][user_email]', userEmail);
            checkoutUrl.searchParams.set('checkout[email]', userEmail);

            window.open(checkoutUrl.toString(), '_blank');

            setDownloadStatus('pending');
            setDownloadMessage('Complete payment in the new tab. Your download will start automatically, and a backup link will be sent to your email.');
        } else {
            // Demo mode - attempt download directly (for testing without LS)
            setDownloadStatus('pending');
            setDownloadMessage('Payment system not configured yet. In production, you would be redirected to checkout.');

            // For demo: try to download anyway (will fail unless manually marked as paid)
            setTimeout(() => {
                attemptDownload();
            }, 2000);
        }
    };

    const attemptDownload = async () => {
        if (!purchaseToken) return;

        setIsDownloading(true);

        try {
            // Use demo endpoint for testing (bypasses payment check)
            // Change to /api/download-hd when payment is live
            const response = await fetch(`${BACKEND_URL}/api/download-demo`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: purchaseToken })
            });

            if (response.ok) {
                const blob = await response.blob();
                downloadBlob(blob, 'eyedentity-hd.png');

                localStorage.removeItem('eyedentity_purchase');
                setDownloadStatus('success');
                setDownloadMessage('Download complete! (Demo mode - no payment required)');
            } else if (response.status === 202) {
                // Payment still processing
                setDownloadStatus('pending');
                setDownloadMessage('Payment verification in progress. Check your email for the download link.');
            } else {
                const data = await response.json();
                setDownloadStatus('error');
                setDownloadMessage(data.error || data.message || 'Download failed.');
            }
        } catch (error) {
            setDownloadStatus('error');
            setDownloadMessage('Download failed. Please try again.');
        } finally {
            setIsDownloading(false);
        }
    };

    const downloadBlob = (blob: Blob, filename: string) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        link.click();
        URL.revokeObjectURL(url);
    };

    const getPrideMessage = () => {
        if (!userData || !previewImage || isEnhancing) return null;

        const tribe = userData.tribe;
        const hierarchyText = tribe?.hierarchy_path || tribe?.canonical_name || userData.lastName;

        return (
            <div className="mt-8 text-center space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-1000">
                <p className="text-xs font-mono text-gray-500 uppercase tracking-[0.2em]">
                    The Pride of
                </p>
                <h2 className="text-xl md:text-2xl font-light text-white tracking-wide leading-relaxed px-4">
                    {hierarchyText}
                </h2>
                {tribe && (
                    <div className="flex items-center justify-center gap-2 mt-2">
                        <div className="h-px w-8 bg-emerald-900/50"></div>
                        <p className="text-xs font-mono text-emerald-500/80 uppercase tracking-wider">
                            Verified Heritage
                        </p>
                        <div className="h-px w-8 bg-emerald-900/50"></div>
                    </div>
                )}
            </div>
        );
    };

    return (
        <div className="min-h-screen bg-black flex flex-col">
            {/* Header with Backend Status */}
            <div className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
                <h1 className="text-sm font-mono text-gray-400 tracking-wider">IRIS CAPTURE REVIEW</h1>
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
                    <div className="flex flex-col items-center">
                        <div className="bg-gray-900 border border-gray-800 p-8 flex items-center justify-center relative min-h-[400px] w-full">
                            <img
                                src={previewImage || irisCrop}
                                alt="Iris capture"
                                className="max-w-full h-auto"
                                style={{ imageRendering: previewImage ? 'crisp-edges' : 'auto' }}
                            />

                            {/* Enhancement Progress Overlay */}
                            {isEnhancing && (
                                <div className="absolute inset-0 bg-black/90 backdrop-blur-sm flex items-center justify-center">
                                    <div className="text-center space-y-4">
                                        <Sparkles className="w-12 h-12 text-emerald-500 mx-auto animate-pulse" />
                                        <div className="space-y-1">
                                            <p className="text-base font-medium text-white">Processing...</p>
                                            <p className="text-sm font-mono text-gray-400">AI Enhancement in progress</p>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Watermark indicator */}
                            {previewImage && (
                                <div className="absolute bottom-2 right-2 bg-black/70 px-2 py-1 rounded text-xs font-mono text-gray-400">
                                    Preview (Watermarked)
                                </div>
                            )}
                        </div>
                    </div>

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

                    {/* Pride Message */}
                    {getPrideMessage()}

                    {/* Enhance Button - Only show if not enhanced yet */}
                    {!previewImage && !isEnhancing && (
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

                    {/* Download Status Message */}
                    {downloadMessage && (
                        <div className={`rounded-lg p-4 ${downloadStatus === 'success' ? 'bg-emerald-900/20 border border-emerald-900/50' :
                            downloadStatus === 'error' ? 'bg-red-900/20 border border-red-900/50' :
                                'bg-blue-900/20 border border-blue-900/50'
                            }`}>
                            <p className={`text-sm ${downloadStatus === 'success' ? 'text-emerald-400' :
                                downloadStatus === 'error' ? 'text-red-400' :
                                    'text-blue-400'
                                }`}>
                                {downloadMessage}
                            </p>
                            {downloadStatus === 'pending' && (
                                <button
                                    onClick={attemptDownload}
                                    disabled={isDownloading}
                                    className="mt-2 text-sm text-blue-400 underline hover:text-blue-300"
                                >
                                    {isDownloading ? 'Checking...' : 'Check download status'}
                                </button>
                            )}
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

                    {/* Download HD Button - Only show after enhancement */}
                    {previewImage && purchaseToken && (
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
                            {isDownloading ? (
                                <Loader2 className="w-5 h-5 animate-spin" />
                            ) : (
                                <Download className="w-5 h-5" />
                            )}
                            Download HD (No Watermark) - $2.99
                        </button>
                    )}
                </div>
            </div>

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
                            Enter your email to receive your HD iris image. We'll also send a backup download link.
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
                                onClick={handleEmailSubmit}
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
