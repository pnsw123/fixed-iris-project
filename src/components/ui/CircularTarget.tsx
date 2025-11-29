'use client';

import { CaptureState } from '@/types/captureState';

interface CircularTargetProps {
    state: CaptureState;
    progress: number; // 0-1 for countdown
    x: number;
    y: number;
    radius: number;
}

export default function CircularTarget({ state, progress, x, y, radius }: CircularTargetProps) {
    const getColors = () => {
        switch (state) {
            case 'scanning':
                return { stroke: 'rgba(128, 128, 128, 0.4)', fill: 'rgba(128, 128, 128, 0.05)' };
            case 'guiding':
                return { stroke: 'rgba(234, 179, 8, 0.6)', fill: 'rgba(234, 179, 8, 0.05)' }; // Yellow
            case 'readying':
            case 'countdown':
                return { stroke: 'rgba(156, 163, 175, 0.8)', fill: 'rgba(156, 163, 175, 0.05)' }; // Gray
            case 'captured':
                return { stroke: 'rgba(156, 163, 175, 0.8)', fill: 'rgba(156, 163, 175, 0.1)' };
            default:
                return { stroke: 'rgba(128, 128, 128, 0.4)', fill: 'rgba(128, 128, 128, 0.05)' };
        }
    };

    const colors = getColors();
    const circumference = 2 * Math.PI * radius;
    const strokeDashoffset = circumference * (1 - progress);

    return (
        <div
            className="absolute pointer-events-none"
            style={{
                left: x - radius,
                top: y - radius,
                width: radius * 2,
                height: radius * 2,
            }}
        >
            <svg
                width={radius * 2}
                height={radius * 2}
                viewBox={`0 0 ${radius * 2} ${radius * 2}`}
                className="absolute inset-0"
            >
                {/* Background circle */}
                <circle
                    cx={radius}
                    cy={radius}
                    r={radius - 2}
                    fill={colors.fill}
                    stroke={colors.stroke}
                    strokeWidth="1.5"
                />

                {/* Countdown progress ring */}
                {state === 'countdown' && (
                    <circle
                        cx={radius}
                        cy={radius}
                        r={radius - 2}
                        fill="none"
                        stroke="rgba(255, 255, 255, 0.8)"
                        strokeWidth="2"
                        strokeDasharray={circumference}
                        strokeDashoffset={strokeDashoffset}
                        strokeLinecap="round"
                        transform={`rotate(-90 ${radius} ${radius})`}
                        className="transition-all duration-300"
                    />
                )}
            </svg>

            {/* Center text for scanning state */}
            {state === 'scanning' && (
                <div className="absolute inset-0 flex items-center justify-center">
                    <p className="text-gray-400 text-xs font-mono uppercase tracking-wider text-center px-4">
                        Align Eye
                    </p>
                </div>
            )}
        </div>
    );
}
