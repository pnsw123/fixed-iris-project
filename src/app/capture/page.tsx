'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import MobileCaptureScreen, { CaptureData } from '@/components/MobileCaptureScreen';

export default function CapturePage() {
    const router = useRouter();
    const [isMounted, setIsMounted] = useState(false);

    useEffect(() => {
        const timer = setTimeout(() => setIsMounted(true), 0);
        return () => clearTimeout(timer);
    }, []);

    const handleBack = () => {
        router.back();
    };

    const handleCaptureComplete = (data: CaptureData) => {
        // Store capture data
        sessionStorage.setItem('heritage_capture', JSON.stringify(data));
        router.push('/result');
    };

    if (!isMounted) return null;

    return (
        <MobileCaptureScreen
            onBack={handleBack}
            onCaptureComplete={handleCaptureComplete}
        />
    );
}
