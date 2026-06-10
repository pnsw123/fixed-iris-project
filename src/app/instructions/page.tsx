'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import { Loader2 } from 'lucide-react';
import AppHeader from '@/components/AppHeader';
import ComparisonSlider from '@/components/ComparisonSlider';
import UnsupportedDeviceScreen from '@/components/UnsupportedDeviceScreen';
import { checkCameraResolution, CameraCapabilities } from '@/lib/cameraCheck';
import SpotlightBackground from '@/components/SpotlightBackground';

// Dynamic import to avoid SSR issues with RoughJS
const ChalkboardList = dynamic(() => import('@/components/ChalkboardList'), {
    ssr: false,
    loading: () => <div className="h-64 animate-pulse bg-gray-900 rounded-lg" />,
});


type GateState = 'checking' | 'supported' | 'unsupported';

const instructionItems = [
    {
        number: 1,
        title: 'Bright Light',
        description: 'Get close to a lamp or use your flashlight.',
        iconType: 'flashlight' as const,
    },
    {
        number: 2,
        title: 'Get Close',
        description: 'Move in until the indicator turns green.',
        iconType: 'getcloser' as const,
    },
    {
        number: 3,
        title: 'Look Straight',
        description: 'Look at the camera, not the screen.',
        iconType: 'eye' as const,
    },
    {
        number: 4,
        title: 'Focus',
        description: 'Make sure the image is sharp, not blurry.',
        iconType: 'focus' as const,
    },
];


export default function InstructionsPage() {
    const router = useRouter();
    const [gateState, setGateState] = useState<GateState>('checking');
    const [cameraInfo, setCameraInfo] = useState<CameraCapabilities | null>(null);
    const lightSectionRef = useRef<HTMLDivElement>(null);

    // TODO: RE-ENABLE CAMERA CHECK - Temporarily disabled for desktop testing
    useEffect(() => {
        // TEMPORARILY BYPASSED - set to 'supported' directly
        setGateState('supported');

        // Original camera check code (uncomment to re-enable):
        // const checkCamera = async () => {
        //     const result = await checkCameraResolution();
        //     setCameraInfo(result);
        //     setGateState(result.meetsRequirement ? 'supported' : 'unsupported');
        // };
        // checkCamera();
    }, []);

    // Auto-scroll to "Light Reveals Everything" section after animations complete
    // 4 items × ~1850ms each = ~7400ms, plus buffer = 8000ms
    useEffect(() => {
        if (gateState === 'supported') {
            const scrollTimer = setTimeout(() => {
                lightSectionRef.current?.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }, 8000);
            return () => clearTimeout(scrollTimer);
        }
    }, [gateState]);

    const handleContinue = () => {
        router.push('/mobile-capture');
    };

    // Loading state while checking camera
    if (gateState === 'checking') {
        return (
            <div className="min-h-screen bg-black flex flex-col items-center justify-center text-white">
                <Loader2 className="w-10 h-10 text-white animate-spin mb-4" />
                <p className="text-gray-400 font-light">Checking camera compatibility...</p>
            </div>
        );
    }

    // Camera doesn't meet requirements
    if (gateState === 'unsupported') {
        return <UnsupportedDeviceScreen cameraInfo={cameraInfo || undefined} />;
    }

    // Camera meets requirements - show instructions
    return (
        <div className="min-h-screen bg-black flex flex-col text-white relative overflow-hidden">
            <SpotlightBackground />
            {/* Header */}
            <AppHeader title="INSTRUCTIONS" showBack />

            {/* Main Content */}
            <div className="flex-1 px-8 py-16 sm:px-16 max-w-xl mx-auto w-full relative z-10">
                <div className="space-y-8">

                    {/* Instructions First - "How to Capture" */}
                    <div className="space-y-6">
                        <h2 className="text-3xl sm:text-4xl font-light text-white tracking-tight">How to Capture</h2>
                        <ChalkboardList items={instructionItems} arrowColor="#a78bfa" />
                    </div>

                    {/* Result Preview Second */}
                    <div ref={lightSectionRef} className="space-y-3">
                        <h2 className="text-3xl sm:text-4xl font-light text-white tracking-tight">Light Reveals Everything</h2>
                        <p className="text-sm text-gray-400">Point a light directly at your face—yes, really close. Trust us.</p>
                        <ComparisonSlider compact />
                        <p className="text-xs text-gray-500 font-mono text-center">
                            Iris before and after enough light
                        </p>
                    </div>

                    {/* CTA */}
                    <div className="pt-2">
                        <button
                            onClick={handleContinue}
                            className="w-full bg-white text-black font-medium text-base py-4 px-6 hover:bg-gray-100 transition-colors"
                        >
                            Continue
                        </button>
                    </div>
                </div>
            </div>

        </div>
    );
}
