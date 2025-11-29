'use client';

import { useState } from 'react';
import MobileCaptureScreen from '@/components/MobileCaptureScreen';
import ReviewScreen from '@/components/ReviewScreen';

type AppState = 'capture' | 'review';

export default function MobileCapturePage() {
    const [appState, setAppState] = useState<AppState>('capture');
    const [capturedImage, setCapturedImage] = useState<string>('');

    const handleCaptureComplete = (imageData: string) => {
        console.log('[MobileCapturePage] ✅ Capture complete!');
        console.log('[MobileCapturePage] Image data length:', imageData.length);
        setCapturedImage(imageData);
        setAppState('review');
    };

    const handleRetake = () => {
        setCapturedImage('');
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

    if (appState === 'review') {
        return (
            <ReviewScreen
                irisCrop={capturedImage}
                onRetake={handleRetake}
            />
        );
    }

    return null;
}
