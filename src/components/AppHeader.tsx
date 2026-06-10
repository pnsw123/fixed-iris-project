'use client';

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
 * Shared header used across all app screens.
 * Always renders the DotLottie brand mark for visual consistency.
 */
export default function AppHeader({ title = 'IRIS CAPTURE', showBack = false, rightSlot }: AppHeaderProps) {
    const router = useRouter();

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
                    <DotLottieReact
                        src="https://lottie.host/265c2c96-b73d-48dd-a60d-d5f8fb10f7d8/7yPHcgKqNe.lottie"
                        loop
                        autoplay
                        style={{ width: 32, height: 32 }}
                    />
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
