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
            setCaptureData(JSON.parse(storedCapture));
        } else {
            router.replace('/mobile-capture');
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
