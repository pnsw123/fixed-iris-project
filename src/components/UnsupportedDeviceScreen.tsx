'use client';

import { ArrowLeft } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { CameraCapabilities, MIN_MEGAPIXELS } from '@/lib/cameraCheck';
import BubbleFooter from './BubbleFooter';
import SpotlightBackground from './SpotlightBackground';

interface UnsupportedDeviceScreenProps {
    cameraInfo?: CameraCapabilities;
}

export default function UnsupportedDeviceScreen({ cameraInfo }: UnsupportedDeviceScreenProps) {
    const router = useRouter();
    const detectedMP = cameraInfo?.megapixels?.toFixed(1) || '0';

    return (
        <div className="min-h-screen bg-black flex flex-col relative overflow-hidden text-white">
            {/* Full-page Spotlight matching Home screen */}
            <SpotlightBackground />

            {/* Header - Aligned with Home screen */}
            <div className="px-6 py-6 relative z-10">
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => router.push('/')}
                        className="p-2 -ml-2 hover:bg-white/10 rounded-full transition-colors"
                    >
                        <ArrowLeft className="w-5 h-5 text-gray-400" />
                    </button>
                    <span className="text-sm font-mono text-gray-400 tracking-wider">IRIS CAPTURE</span>
                </div>
            </div>

            {/* Main Content - Exact spacing from IntroScreen */}
            <div className="flex-1 flex items-center justify-center px-8 py-16 sm:px-16 relative z-10">
                <div className="max-w-xl w-full">
                    <div className="space-y-12 text-center">
                        {/* Title - Same size and position as Eyedentity */}
                        <div className="space-y-6">
                            <h1 className="text-4xl sm:text-5xl font-light text-white tracking-tight">
                                Camera Not Supported
                            </h1>

                            <p className="text-gray-400 text-lg font-light leading-relaxed max-w-md mx-auto">
                                Eyedentity requires at least {MIN_MEGAPIXELS}MP for high-fidelity capture.
                                Your device reported <span className="text-white font-medium">{detectedMP}MP</span>.
                            </p>
                        </div>

                        {/* Button - Exact metrics as Get Started */}
                        <button
                            onClick={() => router.push('/')}
                            className="bg-white text-black font-medium text-base py-4 px-12 hover:bg-gray-100 transition-colors"
                        >
                            Back to Home
                        </button>
                    </div>
                </div>
            </div>

            {/* Animated Footer matching Home screen */}
            <BubbleFooter />
        </div>
    );
}
