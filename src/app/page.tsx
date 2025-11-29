'use client';

import { useState } from 'react';
import IntroScreen from '@/components/IntroScreen';
import MobileCaptureScreen, { CaptureData } from '@/components/MobileCaptureScreen';
import ReviewScreen from '@/components/ReviewScreen';

type AppState = 'intro' | 'capture' | 'review' | 'processing';

export default function Home() {
  const [appState, setAppState] = useState<AppState>('intro');
  const [captureData, setCaptureData] = useState<CaptureData | null>(null);

  const handleStartCapture = () => {
    setAppState('capture');
  };

  const handleCaptureComplete = async (data: CaptureData) => {
    console.log('[MobileApp] ✅ Capture complete!');
    console.log('[MobileApp] Image data length:', data.imageData.length);
    console.log('[MobileApp] Has iris coordinates:', !!data.irisCoordinates);
    if (data.irisCoordinates) {
      console.log('[MobileApp] Iris coordinates:', data.irisCoordinates);
    }
    console.log('[MobileApp] Setting captured data and switching to review...');
    setCaptureData(data);
    setAppState('review');
    console.log('[MobileApp] State changed to: review');
    // Note: Enhancement happens in mobile-capture route
  };

  const handleRetake = () => {
    setCaptureData(null);
    setAppState('capture');
  };

  const handleBackToIntro = () => {
    setAppState('intro');
  };

  console.log('[MobileApp] Current state:', appState);
  console.log('[MobileApp] Captured data:', captureData ? `image: ${captureData.imageData.substring(0, 50)}..., coords: ${JSON.stringify(captureData.irisCoordinates)}` : 'none');

  if (appState === 'intro') {
    console.log('[MobileApp] Rendering IntroScreen');
    return <IntroScreen onStart={handleStartCapture} />;
  }

  if (appState === 'capture') {
    console.log('[MobileApp] Rendering MobileCaptureScreen');
    return (
      <MobileCaptureScreen
        onBack={handleBackToIntro}
        onCaptureComplete={handleCaptureComplete}
      />
    );
  }

  if (appState === 'review' && captureData) {
    console.log('[MobileApp] Rendering ReviewScreen');
    return (
      <ReviewScreen
        captureData={captureData}
        onRetake={handleRetake}
      />
    );
  }

  console.log('[MobileApp] No state matched, returning null');
  return null;
}
