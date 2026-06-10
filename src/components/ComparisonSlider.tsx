'use client';

import { useEffect, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import Image from 'next/image';
import { ChevronsLeftRight } from 'lucide-react';
import { useDebugMode } from '@/hooks/useDebugMode';
import { useInView } from 'motion/react';

interface ComparisonSliderProps {
    compact?: boolean;
}

export default function ComparisonSlider({ compact = false }: ComparisonSliderProps) {
    const isDebug = useDebugMode();

    const sliderRef = useRef<HTMLDivElement>(null);
    const draggingRef = useRef(false);
    const animatingRef = useRef(true);
    const animationFrameRef = useRef<number | null>(null);
    const animationStartRef = useRef<number | null>(null);
    const [percent, setPercent] = useState(0);
    const [containerWidth, setContainerWidth] = useState<number>(0);

    // Only start auto-animation once slider is visible in viewport
    const isInView = useInView(sliderRef, { once: true, margin: '-80px' });

    const updateFromClientX = (clientX: number) => {
        const slider = sliderRef.current;
        if (!slider) return;
        const rect = slider.getBoundingClientRect();
        const offset = Math.min(Math.max(clientX - rect.left, 0), rect.width);
        setPercent((offset / rect.width) * 100);
    };

    // Global pointer event listeners for drag
    useEffect(() => {
        const handleMove = (event: PointerEvent) => {
            if (!draggingRef.current) return;
            updateFromClientX(event.clientX);
        };

        const stopDrag = () => {
            draggingRef.current = false;
        };

        window.addEventListener('pointermove', handleMove);
        window.addEventListener('pointerup', stopDrag);
        window.addEventListener('pointercancel', stopDrag);

        return () => {
            window.removeEventListener('pointermove', handleMove);
            window.removeEventListener('pointerup', stopDrag);
            window.removeEventListener('pointercancel', stopDrag);
        };
    }, []);

    // Auto-animation: fires only once slider enters viewport, then waits 400ms before starting
    useEffect(() => {
        if (!isInView) return;

        const initialDelay = 400; // Short delay after viewport entry
        const duration = 2000; // Slower, smoother animation
        const targetPercent = 80; // Stop at 80% instead of 100%

        // Easing function for smooth animation (ease-in-out)
        const easeInOutCubic = (t: number): number => {
            return t < 0.5
                ? 4 * t * t * t
                : 1 - Math.pow(-2 * t + 2, 3) / 2;
        };

        const timeoutId = setTimeout(() => {
            const step = (timestamp: number) => {
                if (!animationStartRef.current) {
                    animationStartRef.current = timestamp;
                }
                const elapsed = timestamp - animationStartRef.current;
                const progress = Math.min(elapsed / duration, 1);
                const easedProgress = easeInOutCubic(progress);
                const next = targetPercent * easedProgress;

                if (animatingRef.current) {
                    setPercent(next);
                }

                if (progress < 1 && animatingRef.current) {
                    animationFrameRef.current = requestAnimationFrame(step);
                } else {
                    animationFrameRef.current = null;
                    animatingRef.current = false;
                }
            };

            animationFrameRef.current = requestAnimationFrame(step);
        }, initialDelay);

        return () => {
            clearTimeout(timeoutId);
            if (animationFrameRef.current) {
                cancelAnimationFrame(animationFrameRef.current);
            }
        };
    }, [isInView]);

    // Track container width for proper image alignment
    useEffect(() => {
        const updateWidth = () => {
            if (sliderRef.current) {
                setContainerWidth(sliderRef.current.offsetWidth);
            }
        };

        updateWidth();
        window.addEventListener('resize', updateWidth);

        return () => {
            window.removeEventListener('resize', updateWidth);
        };
    }, []);

    const startDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
        // Cancel animation instantly on user interaction
        if (animationFrameRef.current) {
            cancelAnimationFrame(animationFrameRef.current);
            animationFrameRef.current = null;
        }
        animatingRef.current = false;
        draggingRef.current = true;
        updateFromClientX(event.clientX);
    };

    const handleClick = (event: ReactPointerEvent<HTMLDivElement>) => {
        // Cancel animation on click
        if (animationFrameRef.current) {
            cancelAnimationFrame(animationFrameRef.current);
            animationFrameRef.current = null;
        }
        animatingRef.current = false;
        updateFromClientX(event.clientX);
    };

    const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
        if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
        event.preventDefault();
        // Cancel animation on keyboard interaction
        if (animationFrameRef.current) {
            cancelAnimationFrame(animationFrameRef.current);
            animationFrameRef.current = null;
        }
        animatingRef.current = false;
        const delta = event.key === 'ArrowRight' || event.key === 'ArrowUp' ? 5 : -5;
        setPercent(prev => Math.min(100, Math.max(0, prev + delta)));
    };

    const overlayWidth = `${percent}%`;
    const handleLeft = `${percent}%`;

    return (
        <div className="space-y-3">
            <span className="text-xs uppercase tracking-[0.18em] text-gray-500">
                See example result
            </span>
            <div
                className="relative w-full overflow-hidden rounded-2xl border border-white/10 bg-black/30 shadow-[0_24px_60px_rgba(0,0,0,0.55)]"
                style={{ height: compact ? '160px' : '280px' }}
            >
                <div
                    ref={sliderRef}
                    className="relative h-full w-full touch-none select-none cursor-ew-resize"
                    onPointerDown={startDrag}
                    onClick={handleClick}
                    aria-label="Comparison slider"
                >
                    {/* Before image (base layer) */}
                    <Image
                        src="/before.webp"
                        alt="Before"
                        fill
                        priority
                        sizes="(max-width: 768px) 100vw, 800px"
                        className="object-cover object-center pointer-events-none"
                        draggable={false}
                    />

                    {/* After image (overlay layer) - clipped horizontally */}
                    <div
                        className="absolute inset-0 overflow-hidden"
                        style={{ width: overlayWidth }}
                    >
                        <Image
                            src={isDebug ? "/before.webp" : "/after.webp"}
                            alt="After"
                            fill
                            priority
                            sizes="(max-width: 768px) 100vw, 800px"
                            className="object-cover object-center pointer-events-none"
                            style={{
                                width: containerWidth ? `${containerWidth}px` : '100%',
                                maxWidth: 'none'
                            }}
                            draggable={false}
                        />
                    </div>

                    {/* Vertical divider line */}
                    <div
                        className="absolute top-0 h-full w-0.5 bg-white/35 pointer-events-none"
                        style={{ left: handleLeft, transform: 'translateX(-50%)' }}
                    />

                    {/* Circular handle */}
                    <div
                        className="absolute top-1/2 w-8 h-8 rounded-full bg-white shadow-[0_12px_28px_rgba(0,0,0,0.35),0_0_0_1px_rgba(0,0,0,0.15)] border border-white/30 cursor-ew-resize touch-none flex items-center justify-center text-black text-sm transition-shadow duration-200 hover:shadow-[0_12px_28px_rgba(0,0,0,0.35),0_0_0_1px_rgba(90,165,255,0.7)] focus-visible:outline-2 focus-visible:outline-[#5aa5ff] focus-visible:outline-offset-2"
                        style={{
                            left: handleLeft,
                            transform: 'translate(-50%, -50%)'
                        }}
                        role="slider"
                        aria-valuemin={0}
                        aria-valuemax={100}
                        aria-valuenow={Math.round(percent)}
                        aria-label="Adjust comparison"
                        tabIndex={0}
                        onKeyDown={handleKeyDown}
                    >
                        <ChevronsLeftRight aria-hidden="true" size={20} />
                    </div>
                </div>
            </div>
        </div>
    );
}