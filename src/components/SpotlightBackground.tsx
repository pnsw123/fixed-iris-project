import React from 'react';

interface SpotlightBackgroundProps {
    /** Spotlight color as an rgba() string. Defaults to indigo. */
    color?: string;
}

export default function SpotlightBackground({
    color = 'rgba(120, 119, 198, 0.25)',
}: SpotlightBackgroundProps) {
    return (
        <div
            className="pointer-events-none absolute inset-0 z-0"
            style={{
                background: `radial-gradient(ellipse 80% 50% at 50% 50%, ${color}, transparent 80%)`,
            }}
        />
    );
}
