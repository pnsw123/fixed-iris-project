'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import ReviewScreen from '@/components/ReviewScreen';
import { CaptureData } from '@/components/MobileCaptureScreen';

export default function ResultPage() {
    const router = useRouter();
    const [captureData, setCaptureData] = useState<CaptureData | null>(null);
    const [userData, setUserData] = useState<any>(null);

    useEffect(() => {
        const storedCapture = sessionStorage.getItem('heritage_capture');
        const storedUser = sessionStorage.getItem('heritage_user');

        if (storedCapture && storedUser) {
            setCaptureData(JSON.parse(storedCapture));
            setUserData(JSON.parse(storedUser));
        } else {
            router.replace('/name-input');
        }
    }, [router]);

    const handleRetake = () => {
        sessionStorage.removeItem('heritage_capture');
        router.push('/capture');
    };

    if (!captureData || !userData) return null;

    return (
        <ReviewScreen
            captureData={captureData}
            userData={userData}
            onRetake={handleRetake}
        />
    );
}
