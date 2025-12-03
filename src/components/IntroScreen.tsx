'use client';

import { useRouter } from 'next/navigation';
import { Eye } from 'lucide-react';
import ComparisonSlider from '@/components/ComparisonSlider';

interface IntroScreenProps {
    onStart?: () => void;
}

export default function IntroScreen({ onStart }: IntroScreenProps) {
    const router = useRouter();

    const handleStartCamera = () => {
        if (onStart) {
            onStart(); // Let parent handle state change
        } else {
            router.push('/mobile-capture'); // Fallback for standalone use
        }
    };

    return (
        <div className="min-h-screen bg-black flex flex-col">
            {/* Header */}
            <div className="border-b border-gray-800 px-6 py-4">
                <div className="flex items-center gap-2">
                    <Eye className="w-5 h-5 text-gray-400" strokeWidth={1.5} />
                    <span className="text-sm font-mono text-gray-400 tracking-wider">IRIS CAPTURE</span>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 flex items-center justify-center px-6 py-12">
                <div className="max-w-lg w-full">
                    <div className="space-y-12">
                        {/* Title */}
                        <div className="space-y-3">
                            <h1 className="text-5xl font-light text-white tracking-tight">
                                High-Resolution<br />Iris Imaging
                            </h1>
                            <p className="text-gray-400 text-lg font-light">
                                Capture detailed iris scans using your device camera
                            </p>
                        </div>

                        {/* Instructions */}
                        <div className="space-y-4">
                            <div className="flex gap-4">
                                <div className="text-gray-500 font-mono text-sm pt-1">01</div>
                                <div>
                                    <p className="text-gray-300 leading-relaxed">
                                        Position your face in front of the camera
                                    </p>
                                </div>
                            </div>

                            <div className="flex gap-4">
                                <div className="text-gray-500 font-mono text-sm pt-1">02</div>
                                <div>
                                    <p className="text-gray-300 leading-relaxed">
                                        Align one eye within the target circle
                                    </p>
                                </div>
                            </div>

                            <div className="flex gap-4">
                                <div className="text-gray-500 font-mono text-sm pt-1">03</div>
                                <div>
                                    <p className="text-gray-300 leading-relaxed">
                                        Hold steady — capture is automatic
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* Comparison Slider */}
                        <ComparisonSlider />

                        {/* CTA */}
                        <button
                            onClick={handleStartCamera}
                            className="w-full bg-white text-black font-medium text-base py-4 px-6 hover:bg-gray-100 transition-colors"
                        >
                            Begin Capture
                        </button>

                        {/* Footer note */}
                        <p className="text-gray-600 text-sm font-mono">
                            All processing occurs on-device. No data is transmitted.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
