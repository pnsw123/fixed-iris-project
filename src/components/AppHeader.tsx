'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { DotLottieReact } from '@lottiefiles/dotlottie-react';
import { ArrowLeft } from 'lucide-react';

interface AppHeaderProps {
    /** Label shown next to the logo */
    title?: string;
    /** Show back button to the left of the logo */
    showBack?: boolean;
    /** Optional right-side slot (e.g. backend status indicator) */
    rightSlot?: React.ReactNode;
}

/**
 * Iris SVG fallback shown while DotLottie fetches from CDN.
 * Matches brand palette — instant render, zero network deps.
 */
function IrisFallback() {
    return (
        <svg
            width={32}
            height={32}
            viewBox="0 0 32 32"
            fill="none"
            aria-hidden="true"
        >
            {/* Outer ring */}
            <circle cx="16" cy="16" r="14" stroke="#6366f1" strokeWidth="1.5" />
            {/* Mid iris ring */}
            <circle cx="16" cy="16" r="9" stroke="#818cf8" strokeWidth="1" opacity="0.7" />
            {/* Pupil */}
            <circle cx="16" cy="16" r="4.5" fill="#a5b4fc" opacity="0.9" />
            {/* Specular highlight */}
            <circle cx="18.5" cy="13.5" r="1.5" fill="white" opacity="0.6" />
        </svg>
    );
}

/**
 * Shared header used across all app screens.
 * Renders DotLottie brand mark; shows static iris SVG until Lottie loads.
 */
export default function AppHeader({ title = 'IRIS CAPTURE', showBack = false, rightSlot }: AppHeaderProps) {
    const router = useRouter();
    const [lottieLoaded, setLottieLoaded] = useState(false);

    return (
        <div className="px-6 py-6 relative z-10">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    {showBack && (
                        <button
                            onClick={() => router.back()}
                            className="p-2 -ml-2 hover:bg-gray-900 rounded-full transition-colors mr-1"
                            aria-label="Go back"
                        >
                            <ArrowLeft className="w-5 h-5 text-gray-400" />
                        </button>
                    )}
                    {/* Logo container — fixed 32×32 so layout never shifts */}
                    <div className="relative w-8 h-8 flex-shrink-0">
                        {/* Static fallback — visible until Lottie ready */}
                        <span
                            className="absolute inset-0 flex items-center justify-center transition-opacity duration-500"
                            style={{ opacity: lottieLoaded ? 0 : 1, pointerEvents: 'none' }}
                            aria-hidden="true"
                        >
                            <IrisFallback />
                        </span>
                        {/* DotLottie — fades in on load */}
                        <span
                            className="absolute inset-0 flex items-center justify-center transition-opacity duration-500"
                            style={{ opacity: lottieLoaded ? 1 : 0 }}
                        >
                            <DotLottieReact
                                src="https://lottie.host/265c2c96-b73d-48dd-a60d-d5f8fb10f7d8/7yPHcgKqNe.lottie"
                                loop
                                autoplay
                                onLoad={() => setLottieLoaded(true)}
                                style={{ width: 32, height: 32 }}
                            />
                        </span>
                    </div>
                    <span className="text-sm font-mono text-gray-400 tracking-wider">{title}</span>
                </div>
                {rightSlot && (
                    <div className="flex items-center gap-2">
                        {rightSlot}
                    </div>
                )}
            </div>
        </div>
    );
}
