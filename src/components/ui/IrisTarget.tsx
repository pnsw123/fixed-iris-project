'use client';

import { AnimatePresence, motion } from 'motion/react';

interface IrisTargetProps {
    detected: boolean;
    centered: boolean;
    distanceGood: boolean;
    lightingGood: boolean;
    isReady: boolean;
    countdown: number | null;
    irisPosition?: { x: number; y: number };
    irisDiameter?: number;
}

export default function IrisTarget({
    detected,
    centered,
    distanceGood,
    lightingGood,
    isReady,
    countdown,
    irisPosition,
    irisDiameter
}: IrisTargetProps) {
    // Determine ring color based on state
    const getRingColor = () => {
        if (!detected) return 'rgba(156, 163, 175, 0.4)'; // gray-400
        if (countdown !== null) return 'rgba(16, 185, 129, 0.8)'; // emerald-500
        if (isReady) return 'rgba(16, 185, 129, 0.6)'; // emerald-500
        if (!centered || !distanceGood) return 'rgba(251, 191, 36, 0.5)'; // amber-400
        if (!lightingGood) return 'rgba(251, 191, 36, 0.5)'; // amber-400
        return 'rgba(156, 163, 175, 0.4)'; // gray-400
    };

    // Calculate target size and position
    const targetSize = irisDiameter ? irisDiameter * 1.8 : 120;
    const targetX = irisPosition?.x || window.innerWidth / 2;
    const targetY = irisPosition?.y || window.innerHeight / 2;

    return (
        <div className="absolute inset-0 pointer-events-none" style={{ willChange: 'transform' }}>
            <svg className="w-full h-full" style={{ willChange: 'transform' }}>
                {/* Main target circle */}
                <circle
                    cx={targetX}
                    cy={targetY}
                    r={targetSize / 2}
                    fill="none"
                    stroke={getRingColor()}
                    strokeWidth="2"
                    className="transition-all duration-500 ease-out"
                    style={{
                        filter: isReady || countdown !== null ? 'drop-shadow(0 0 8px rgba(16, 185, 129, 0.4))' : 'none'
                    }}
                />

                {/* Countdown progress ring */}
                {countdown !== null && countdown > 0 && (
                    <circle
                        cx={targetX}
                        cy={targetY}
                        r={targetSize / 2}
                        fill="none"
                        stroke="rgba(16, 185, 129, 1)"
                        strokeWidth="3"
                        strokeDasharray={`${Math.PI * targetSize} ${Math.PI * targetSize}`}
                        strokeDashoffset={Math.PI * targetSize * (countdown / 3)}
                        className="transition-all duration-1000 ease-linear origin-center"
                        style={{
                            transform: `rotate(-90deg)`,
                            transformOrigin: 'center',
                            transformBox: 'fill-box'
                        }}
                    />
                )}

                {/* Center dot when ready */}
                {isReady && !countdown && (
                    <circle
                        cx={targetX}
                        cy={targetY}
                        r="3"
                        fill="rgba(16, 185, 129, 0.8)"
                        className="animate-pulse"
                    />
                )}

                {/* Crosshair when not detected */}
                {!detected && (
                    <>
                        <line
                            x1={targetX - 20}
                            y1={targetY}
                            x2={targetX - 6}
                            y2={targetY}
                            stroke="rgba(156, 163, 175, 0.3)"
                            strokeWidth="1"
                        />
                        <line
                            x1={targetX + 6}
                            y1={targetY}
                            x2={targetX + 20}
                            y2={targetY}
                            stroke="rgba(156, 163, 175, 0.3)"
                            strokeWidth="1"
                        />
                        <line
                            x1={targetX}
                            y1={targetY - 20}
                            x2={targetX}
                            y2={targetY - 6}
                            stroke="rgba(156, 163, 175, 0.3)"
                            strokeWidth="1"
                        />
                        <line
                            x1={targetX}
                            y1={targetY + 6}
                            x2={targetX}
                            y2={targetY + 20}
                            stroke="rgba(156, 163, 175, 0.3)"
                            strokeWidth="1"
                        />
                    </>
                )}
            </svg>

            {/* Countdown number */}
            <div
                className="absolute"
                style={{
                    left: `${targetX}px`,
                    top: `${targetY}px`,
                    transform: 'translate(-50%, -50%)',
                    willChange: 'transform'
                }}
            >
                <AnimatePresence mode="wait">
                    {countdown !== null && countdown > 0 && (
                        <motion.span
                            key={countdown}
                            initial={{ scale: 2, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.5, opacity: 0 }}
                            transition={{ type: 'spring', stiffness: 300, damping: 20 }}
                            className="block text-4xl font-light text-white"
                            style={{ willChange: 'transform, opacity' }}
                        >
                            {countdown}
                        </motion.span>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}
