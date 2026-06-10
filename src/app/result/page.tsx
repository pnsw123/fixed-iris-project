'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import ReviewScreen from '@/components/ReviewScreen';
import { CaptureData } from '@/components/MobileCaptureScreen';

export default function ResultPage() {
    const router = useRouter();
    const [captureData, setCaptureData] = useState<CaptureData | null>(null);

    useEffect(() => {
        const storedCapture = sessionStorage.getItem('heritage_capture');

        if (storedCapture) {
            // Defer to avoid calling setState synchronously in effect
            const parsed = JSON.parse(storedCapture) as typeof captureData;
            setTimeout(() => setCaptureData(parsed), 0);
        } else {
            void router.replace('/mobile-capture');
        }
    }, [router]);

    const handleRetake = () => {
        sessionStorage.removeItem('heritage_capture');
        router.push('/mobile-capture');
    };

    if (!captureData) return null;

    return (
        <ReviewScreen
            captureData={captureData}
            onRetake={handleRetake}
        />
    );
}
