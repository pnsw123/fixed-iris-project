import React from 'react';

export default function SpotlightBackground() {
    return (
        <div
            className="pointer-events-none absolute inset-0 z-0"
            style={{
                background: 'radial-gradient(ellipse 80% 50% at 50% 50%, rgba(120, 119, 198, 0.25), transparent 80%)',
            }}
        />
    );
}
