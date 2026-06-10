'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import { Loader2 } from 'lucide-react';
import { motion } from 'motion/react';
import AppHeader from '@/components/AppHeader';
import ComparisonSlider from '@/components/ComparisonSlider';
import UnsupportedDeviceScreen from '@/components/UnsupportedDeviceScreen';
import type { CameraCapabilities } from '@/lib/cameraCheck';
import SpotlightBackground from '@/components/SpotlightBackground';
import { qualityAnalyzer } from '@/lib/qualityMetrics';

// Skeleton matching ChalkboardList: 4 rows of [circle] + [title + description]
function ChalkboardListSkeleton() {
    return (
        <div className="space-y-8 pl-4 animate-pulse">
            {[...Array(4)].map((_, i) => (
                <div key={i} className="flex gap-5 items-start">
                    {/* Number circle placeholder */}
                    <div className="shrink-0 w-10 h-10 rounded-full bg-gray-800" />
                    {/* Text content placeholder */}
                    <div className="space-y-2 flex-1 pt-1">
                        <div className="h-5 w-32 bg-gray-800 rounded" />
                        <div className="h-3.5 w-56 bg-gray-900 rounded" />
                    </div>
                </div>
            ))}
        </div>
    );
}

// Dynamic import to avoid SSR issues with RoughJS
const ChalkboardList = dynamic(() => import('@/components/ChalkboardList'), {
    ssr: false,
    loading: () => <ChalkboardListSkeleton />,
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
    const [cameraInfo, _setCameraInfo] = useState<CameraCapabilities | null>(null);
    const lightSectionRef = useRef<HTMLDivElement>(null);

    // Warm-up MediaPipe WASM while the user reads the instructions.
    // By the time they tap Continue the WASM binary and .task model are cached
    // in the browser, eliminating the 3-8 second cold-start spinner on the
    // capture screen. qualityAnalyzer.initialize() is idempotent — safe to call
    // even if MobileCaptureScreen later calls it again.
    useEffect(() => {
        qualityAnalyzer.initialize().catch((err) => {
            // Warm-up failure is non-fatal: capture screen will retry initialize()
            // on mount and surface any real error there.
            console.warn('[InstructionsPage] MediaPipe warm-up failed:', err);
        });
    }, []);

    // TODO: RE-ENABLE CAMERA CHECK - Temporarily disabled for desktop testing
    useEffect(() => {
        // TEMPORARILY BYPASSED - deferred to next tick to satisfy react-hooks/set-state-in-effect
        const timer = setTimeout(() => {
            setGateState('supported');
        }, 0);
        return () => clearTimeout(timer);

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
        return;
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
        return <UnsupportedDeviceScreen {...(cameraInfo ? { cameraInfo } : {})} />;
    }

    // Camera meets requirements - show instructions
    return (
        <div className="min-h-screen bg-black flex flex-col text-white relative overflow-hidden">
            <SpotlightBackground color="rgba(167, 139, 250, 0.22)" />
            {/* Header */}
            <AppHeader title="INSTRUCTIONS" showBack />

            {/* Main Content */}
            <div className="flex-1 px-8 py-16 sm:px-16 max-w-xl mx-auto w-full relative z-10">
                <div className="space-y-8">

                    {/* Instructions First - "How to Capture" */}
                    <motion.div
                        className="space-y-6"
                        initial={{ opacity: 0, y: 24 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: '-60px' }}
                        transition={{ duration: 0.55, ease: [0.25, 0.46, 0.45, 0.94] }}
                    >
                        <h2 className="text-3xl sm:text-4xl font-light text-white tracking-tight">How to Capture</h2>
                        <ChalkboardList items={instructionItems} arrowColor="#a78bfa" />
                    </motion.div>

                    {/* Result Preview Second */}
                    <motion.div
                        ref={lightSectionRef}
                        className="space-y-3"
                        initial={{ opacity: 0, y: 32 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: '-80px' }}
                        transition={{ duration: 0.6, ease: [0.25, 0.46, 0.45, 0.94] }}
                    >
                        <h2 className="text-3xl sm:text-4xl font-light text-white tracking-tight">Light Reveals Everything</h2>
                        <p className="text-sm text-gray-400">Point a light directly at your face—yes, really close. Trust us.</p>
                        <ComparisonSlider compact />
                        <p className="text-xs text-gray-500 font-mono text-center">
                            Iris before and after enough light
                        </p>
                    </motion.div>

                    {/* CTA */}
                    <motion.div
                        className="pt-2"
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true, margin: '-60px' }}
                        transition={{ duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94], delay: 0.1 }}
                    >
                        <button
                            onClick={handleContinue}
                            className="w-full bg-white text-black font-medium text-base py-4 px-6 hover:bg-gray-100 transition-colors"
                        >
                            Continue
                        </button>
                    </motion.div>
                </div>
            </div>

        </div>
    );
}
