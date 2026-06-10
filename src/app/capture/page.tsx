'use client';

import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import type { CaptureData } from '@/components/MobileCaptureScreen';

// Lazy-load MobileCaptureScreen (and its MediaPipe WASM dependency) only when
// the capture route is actually visited — keeps MediaPipe out of the initial
// bundle for all other pages.
const MobileCaptureScreen = dynamic(
    () => import('@/components/MobileCaptureScreen'),
    { ssr: false }
);

export default function CapturePage() {
    const router = useRouter();

    const handleBack = () => {
        router.back();
    };

    const handleCaptureComplete = (data: CaptureData) => {
        // Store capture data
        sessionStorage.setItem('heritage_capture', JSON.stringify(data));
        router.push('/result');
    };

    return (
        <MobileCaptureScreen
            onBack={handleBack}
            onCaptureComplete={handleCaptureComplete}
        />
    );
}
