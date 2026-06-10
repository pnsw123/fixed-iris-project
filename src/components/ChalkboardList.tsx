'use client';

import { useEffect, useState } from 'react';
import { RoughNotation } from 'react-rough-notation';
import { RoughFlashlight, RoughFocusBrackets, RoughGetCloser, RoughEye } from './RoughIcons';

interface ChalkboardItem {
    number: number;
    title: string;
    description: string;
    iconType?: 'flashlight' | 'focus' | 'getcloser' | 'eye';
}

interface ChalkboardListProps {
    items: ChalkboardItem[];
    arrowColor?: string;
}

export default function ChalkboardList({
    items,
    arrowColor = '#a78bfa',
}: ChalkboardListProps) {
    // Animation states for each item: [circleShow, underlineShow, iconShow]
    const [animationStates, setAnimationStates] = useState<{ circle: boolean; underline: boolean; icon: boolean }[]>(
        items.map(() => ({ circle: false, underline: false, icon: false }))
    );

    // Animation timing - SEQUENTIAL (each row waits for previous row to finish)
    const INITIAL_DELAY = 450;
    const CIRCLE_DURATION = 450;
    const UNDERLINE_DURATION = 350;
    const ICON_DURATION = 350;
    const UNDERLINE_DELAY = 250;     // Delay after circle before underline
    const ICON_DELAY = 200;          // Delay after underline before icon
    const NEXT_ROW_DELAY = 250;      // Delay after icon before next row's circle

    // Total time for one complete row animation
    const ROW_TOTAL_TIME = CIRCLE_DURATION + UNDERLINE_DELAY + UNDERLINE_DURATION + ICON_DELAY + ICON_DURATION + NEXT_ROW_DELAY;

    // Trigger SEQUENTIAL animations
    // ROW_TOTAL_TIME is derived from local constants — intentionally excluded from deps
    /* eslint-disable react-hooks/exhaustive-deps */
    useEffect(() => {
        items.forEach((_, index) => {
            // Each row starts after all previous rows complete
            const rowStart = INITIAL_DELAY + (ROW_TOTAL_TIME * index);

            // 1. Show circle
            setTimeout(() => {
                setAnimationStates(prev => {
                    const next = [...prev];
                    next[index] = { ...next[index]!, circle: true };
                    return next;
                });
            }, rowStart);

            // 2. Show underline (after circle finishes)
            setTimeout(() => {
                setAnimationStates(prev => {
                    const next = [...prev];
                    next[index] = { ...next[index]!, underline: true };
                    return next;
                });
            }, rowStart + CIRCLE_DURATION + UNDERLINE_DELAY);

            // 3. Show icon (after underline finishes) - THIS MUST FINISH BEFORE NEXT ROW STARTS
            setTimeout(() => {
                setAnimationStates(prev => {
                    const next = [...prev];
                    next[index] = { ...next[index]!, icon: true };
                    return next;
                });
            }, rowStart + CIRCLE_DURATION + UNDERLINE_DELAY + UNDERLINE_DURATION + ICON_DELAY);
        });
    }, [items]);
    /* eslint-enable react-hooks/exhaustive-deps */

    return (
        <div className="space-y-8 pl-4">
            {items.map((item, index) => (
                <div key={index} className="flex gap-5 items-start">
                    {/* Number with hand-drawn circle */}
                    <div className="shrink-0 w-10 h-10 flex items-center justify-center text-lg font-semibold text-white">
                        <RoughNotation
                            type="circle"
                            show={animationStates[index]?.circle || false}
                            color={arrowColor}
                            strokeWidth={2}
                            padding={8}
                            animationDuration={CIRCLE_DURATION}
                        >
                            <span>{item.number}</span>
                        </RoughNotation>
                    </div>

                    {/* Content */}
                    <div className="space-y-1">
                        {/* Title with underline + Icon */}
                        <div className="flex items-center gap-3">
                            <RoughNotation
                                type="underline"
                                show={animationStates[index]?.underline || false}
                                color={arrowColor}
                                strokeWidth={2}
                                padding={2}
                                animationDuration={UNDERLINE_DURATION}
                            >
                                <h3 className="text-lg text-gray-300 font-medium">
                                    {item.title}
                                </h3>
                            </RoughNotation>

                            {/* Icon */}
                            <div
                                className="flex items-center ml-4"
                                style={{
                                    opacity: animationStates[index]?.icon ? 1 : 0,
                                    transition: 'opacity 0.4s ease-out'
                                }}
                            >
                                {item.iconType === 'flashlight' && (
                                    <RoughFlashlight
                                        color={arrowColor}
                                        size={20}
                                        show={true}
                                        animate={false}
                                        animationDuration={ICON_DURATION}
                                    />
                                )}
                                {item.iconType === 'focus' && (
                                    <RoughFocusBrackets
                                        color={arrowColor}
                                        size={20}
                                        show={true}
                                        animate={false}
                                        animationDuration={ICON_DURATION}
                                    />
                                )}
                                {item.iconType === 'getcloser' && (
                                    <RoughGetCloser
                                        color={arrowColor}
                                        size={30}
                                        show={true}
                                        animate={false}
                                        animationDuration={ICON_DURATION}
                                    />
                                )}
                                {item.iconType === 'eye' && (
                                    <RoughEye
                                        color={arrowColor}
                                        size={22}
                                        show={true}
                                        animate={false}
                                        animationDuration={ICON_DURATION}
                                    />
                                )}
                            </div>
                        </div>

                        {/* Description */}
                        <p className="text-sm text-gray-500 font-light leading-relaxed">
                            {item.description}
                        </p>
                    </div>
                </div>
            ))}
        </div>
    );
}
