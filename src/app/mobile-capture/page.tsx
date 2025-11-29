'use client';

import { useState } from 'react';
import MobileCaptureScreen, { CaptureData } from '@/components/MobileCaptureScreen';
import ReviewScreen from '@/components/ReviewScreen';

type AppState = 'capture' | 'review';

export default function MobileCapturePage() {
    const [appState, setAppState] = useState<AppState>('capture');
    const [captureData, setCaptureData] = useState<CaptureData | null>(null);

    const handleCaptureComplete = (data: CaptureData) => {
        console.log('[MobileCapturePage] ✅ Capture complete!');
        console.log('[MobileCapturePage] Image data length:', data.imageData.length);
        setCaptureData(data);
        setAppState('review');
    };

    const handleRetake = () => {
        setCaptureData(null);
        setAppState('capture');
    };

    const handleBack = () => {
        window.location.href = '/';
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
