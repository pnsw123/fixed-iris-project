'use client';

interface FaceGuideProps {
    detected: boolean;
}

export default function FaceGuide({ detected }: FaceGuideProps) {
    return (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            {/* Face Oval Guide */}
            <div className="relative">
                {/* Outer guide ellipse */}
                <svg width="280" height="360" viewBox="0 0 280 360" className="opacity-40">
                    <ellipse
                        cx="140"
                        cy="180"
                        rx="130"
                        ry="170"
                        fill="none"
                        stroke={detected ? '#10b981' : '#6b7280'}
                        strokeWidth="2"
                        strokeDasharray="8 4"
                        className="transition-colors duration-300"
                    />
                </svg>

                {/* Eye position markers */}
                <svg width="280" height="360" viewBox="0 0 280 360" className="absolute inset-0">
                    {/* Left eye guide (from user's perspective) */}
                    <circle
                        cx="85"
                        cy="160"
                        r="30"
                        fill="none"
                        stroke={detected ? '#10b981' : '#6b7280'}
                        strokeWidth="2"
                        opacity="0.6"
                        className="transition-colors duration-300"
                    />
                    
                    {/* Right eye guide (from user's perspective) */}
                    <circle
                        cx="195"
                        cy="160"
                        r="30"
                        fill="none"
                        stroke={detected ? '#10b981' : '#6b7280'}
                        strokeWidth="2"
                        opacity="0.6"
                        className="transition-colors duration-300"
                    />

                    {/* Center alignment mark */}
                    <line
                        x1="140"
                        y1="0"
                        x2="140"
                        y2="360"
                        stroke={detected ? '#10b981' : '#6b7280'}
                        strokeWidth="1"
                        opacity="0.3"
                        strokeDasharray="4 4"
                        className="transition-colors duration-300"
                    />
                </svg>

                {/* Instructional text */}
                {!detected && (
                    <div className="absolute -bottom-12 left-1/2 -translate-x-1/2 text-center">
                        <p className="text-sm text-gray-400 font-mono">
                            Align your face within the guide
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
