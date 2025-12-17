'use client';

import { useRouter } from 'next/navigation';
import { ArrowLeft, Sun, Eye, Ruler } from 'lucide-react';
import ComparisonSlider from '@/components/ComparisonSlider';

export default function InstructionsPage() {
    const router = useRouter();

    const handleContinue = () => {
        router.push('/mobile-capture');
    };

    return (
        <div className="min-h-screen bg-black flex flex-col text-white">
            {/* Header */}
            <div className="px-6 py-6">
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => router.back()}
                        className="p-2 -ml-2 hover:bg-gray-900 rounded-full transition-colors"
                    >
                        <ArrowLeft className="w-5 h-5 text-gray-400" />
                    </button>
                    <span className="text-sm font-mono text-gray-400 tracking-wider">INSTRUCTIONS</span>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 px-8 py-12 sm:px-16 max-w-xl mx-auto w-full">
                <div className="space-y-10">

                    {/* Visual Guide (Slider) */}
                    <div className="space-y-4">
                        <h2 className="text-xl font-light tracking-tight">Visual Guide</h2>
                        <ComparisonSlider />
                        <p className="text-xs text-gray-500 font-mono text-center">
                            Slide to see the enhancement detail
                        </p>
                    </div>

                    {/* Steps with Icons (Visual Animations replacement) */}
                    <div className="space-y-8">
                        {/* Lighting */}
                        <div className="flex gap-5 items-start">
                            <div className="p-3 bg-gray-900 rounded-full shrink-0">
                                <Sun className="w-6 h-6 text-white" strokeWidth={1.5} />
                            </div>
                            <div className="space-y-1">
                                <h3 className="text-lg font-medium">Good Lighting</h3>
                                <p className="text-gray-400 font-light leading-relaxed">
                                    Avoid direct sunlight. Soft, even light is best for iris details.
                                </p>
                            </div>
                        </div>

                        {/* Distance */}
                        <div className="flex gap-5 items-start">
                            <div className="p-3 bg-gray-900 rounded-full shrink-0">
                                <Ruler className="w-6 h-6 text-white" strokeWidth={1.5} />
                            </div>
                            <div className="space-y-1">
                                <h3 className="text-lg font-medium">Distance</h3>
                                <p className="text-gray-400 font-light leading-relaxed">
                                    Hold phone 20cm away. The app will guide you to the perfect spot.
                                </p>
                            </div>
                        </div>

                        {/* Focus */}
                        <div className="flex gap-5 items-start">
                            <div className="p-3 bg-gray-900 rounded-full shrink-0">
                                <Eye className="w-6 h-6 text-white" strokeWidth={1.5} />
                            </div>
                            <div className="space-y-1">
                                <h3 className="text-lg font-medium">Eye Contact</h3>
                                <p className="text-gray-400 font-light leading-relaxed">
                                    Look directly at the camera lens, not the screen.
                                </p>
                            </div>
                        </div>
                    </div>

                    {/* CTA */}
                    <div className="pt-4">
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
