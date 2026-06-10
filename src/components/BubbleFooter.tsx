'use client';

import { motion } from 'motion/react';

const CHIPS = [
    { label: 'On-device only', icon: true },
    { label: 'Zero cloud', icon: true },
    { label: `© ${new Date().getFullYear()}`, icon: false },
] as const;

/** Tiny iris-ring SVG icon used as chip leading decoration */
function IrisDot() {
    return (
        <svg
            width="12"
            height="12"
            viewBox="0 0 12 12"
            fill="none"
            aria-hidden="true"
            className="shrink-0"
        >
            <circle cx="6" cy="6" r="5" stroke="#a78bfa" strokeWidth="1.2" />
            <circle cx="6" cy="6" r="2.5" fill="#a78bfa" opacity="0.6" />
        </svg>
    );
}

export default function BubbleFooter() {
    return (
        <footer className="px-6 py-4 mt-auto relative z-10">
            <div className="flex justify-center items-center gap-3 flex-wrap">
                {CHIPS.map(({ label, icon }, i) => (
                    <motion.span
                        key={label}
                        className="flex items-center gap-1.5 text-xs font-mono text-gray-400 border border-white/10 bg-white/5 backdrop-blur-sm rounded-full px-3 py-1.5"
                        initial={{ opacity: 0, y: 8 }}
                        animate={{
                            opacity: 1,
                            y: [0, -3, 0],
                        }}
                        transition={{
                            opacity: { duration: 0.4, delay: i * 0.12 },
                            y: {
                                delay: i * 0.12 + 0.4,
                                duration: 3 + i * 0.4,
                                repeat: Infinity,
                                ease: 'easeInOut',
                            },
                        }}
                    >
                        {icon && <IrisDot />}
                        {label}
                    </motion.span>
                ))}
            </div>
        </footer>
    );
}
