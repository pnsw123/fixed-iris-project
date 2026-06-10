'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import type { CaptureData } from '@/components/MobileCaptureScreen';
import ReviewScreen from '@/components/ReviewScreen';

// Lazy-load MobileCaptureScreen (and its MediaPipe WASM dependency) only when
// the mobile-capture route is actually visited — keeps MediaPipe out of the
// initial bundle for all other pages.
const MobileCaptureScreen = dynamic(
    () => import('@/components/MobileCaptureScreen'),
    { ssr: false }
);

type AppState = 'capture' | 'review';

export default function MobileCapturePage() {
    const router = useRouter();
    const [appState, setAppState] = useState<AppState>('capture');
    const [captureData, setCaptureData] = useState<CaptureData | null>(null);

    const handleCaptureComplete = (data: CaptureData) => {
        setCaptureData(data);
        setAppState('review');
    };

    const handleRetake = () => {
        setCaptureData(null);
        setAppState('capture');
    };

    const handleBack = () => {
        router.push('/');
    };

    if (appState === 'capture') {
        return (
            <MobileCaptureScreen
                onBack={handleBack}
                onCaptureComplete={handleCaptureComplete}
            />
        );
    }

    if (appState === 'review' && captureData) {
        return (
            <ReviewScreen
                captureData={captureData}
                onRetake={handleRetake}
            />
        );
    }

    return null;
}
