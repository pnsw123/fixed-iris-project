'use client';

interface GuidanceBarProps {
    message: string;
}

export default function GuidanceBar({ message }: GuidanceBarProps) {
    if (!message) return null;

    return (
        <div className="absolute top-0 left-0 right-0 z-20 border-b border-gray-800 bg-black/80 backdrop-blur-sm">
            <div className="px-6 py-4">
                <p className="text-white text-sm font-light tracking-wide text-center">
                    {message}
                </p>
            </div>
        </div>
    );
}
