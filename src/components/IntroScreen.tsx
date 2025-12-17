'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useRef } from 'react';
import { DotLottieReact } from '@lottiefiles/dotlottie-react';
import BubbleFooter from './BubbleFooter';
import WordListSwap from './WordListSwap';

interface IntroScreenProps {
    onStart?: () => void;
}

export default function IntroScreen({ onStart }: IntroScreenProps) {
    const router = useRouter();
    const titleRef = useRef<HTMLHeadingElement>(null);

    // Anime.js Effect 9 - Bouncy letter animation (faster version)
    useEffect(() => {
        const runAnimation = async () => {
            if (!titleRef.current) return;

            const textWrapper = titleRef.current.querySelector('.letters');
            if (!textWrapper || !textWrapper.textContent) return;

            // Split into letters
            textWrapper.innerHTML = textWrapper.textContent.replace(
                /\S/g,
                "<span class='letter' style='display:inline-block;transform-origin:50% 100%;line-height:1em;opacity:0;'>$&</span>"
            );

            // Dynamic import to avoid SSR issues
            const anime = await import('animejs');
            const letters = titleRef.current.querySelectorAll('.letter');

            anime.animate(letters, {
                opacity: [0, 1],
                scale: [0, 1],
                duration: 800,  // Faster: was 1500
                ease: 'spring(1, 100, 12, 0)',  // Snappier spring
                delay: anime.stagger(25)  // Faster: was 45
            });
        };

        runAnimation();
    }, []);

    const handleStartCamera = () => {
        if (onStart) {
            onStart();
        } else {
            router.push('/mobile-capture');
        }
    };

    return (
        <div className="min-h-screen bg-black flex flex-col relative overflow-hidden">
            {/* Full-page Spotlight */}
            <div
                className="pointer-events-none absolute inset-0"
                style={{
                    background: 'radial-gradient(ellipse 80% 50% at 50% 50%, rgba(120, 119, 198, 0.25), transparent 80%)',
                }}
            />

            {/* Header */}
            <div className="px-6 py-6 relative z-10">
                <div className="flex items-center gap-2">
                    <DotLottieReact
                        src="https://lottie.host/265c2c96-b73d-48dd-a60d-d5f8fb10f7d8/7yPHcgKqNe.lottie"
                        loop
                        autoplay
                        style={{ width: 32, height: 32 }}
                    />
                    <span className="text-sm font-mono text-gray-400 tracking-wider">IRIS CAPTURE</span>
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 flex items-center justify-center px-8 py-16 sm:px-16 relative z-10">
                <div className="max-w-xl w-full">
                    <div className="space-y-12 text-center">
                        {/* Animated Title */}
                        <div className="space-y-6">
                            <h1
                                ref={titleRef}
                                className="text-4xl sm:text-5xl font-light text-white tracking-tight overflow-hidden"
                            >
                                <span className="text-wrapper" style={{ position: 'relative', display: 'inline-block', paddingTop: '0.2em', paddingRight: '0.05em', paddingBottom: '0.1em' }}>
                                    <span className="letters">Eyedentity</span>
                                </span>
                            </h1>
                            <p className="text-gray-400 text-lg font-light flex items-center justify-center gap-2">
                                <span>See yourself</span>
                                <WordListSwap
                                    texts={[
                                        "differently",
                                        "clearly",
                                        "beautifully",
                                        "uniquely",
                                        "truly",
                                        "closer",
                                        "deeply",
                                        "anew",
                                        "reflected",
                                        "revealed",
                                        "sharply",
                                        "vividly",
                                        "honestly",
                                        "purely",
                                        "boldly",
                                        "freshly",
                                        "completely",
                                        "naturally",
                                        "authentically",
                                        "distinctly",
                                        "precisely",
                                        "intimately",
                                        "brilliantly",
                                        "fully",
                                        "wonderfully",
                                        "perfectly",
                                        "genuinely",
                                        "radiantly",
                                        "magnified",
                                        "illuminated",
                                    ]}
                                    mainClassName="text-white font-medium bg-indigo-500/80 px-2 py-0.5 rounded-md"
                                    staggerFrom="last"
                                    initial={{ y: "100%", opacity: 0 }}
                                    animate={{ y: 0, opacity: 1 }}
                                    exit={{ y: "-120%", opacity: 0 }}
                                    staggerDuration={0.02}
                                    splitLevelClassName="overflow-hidden"
                                    transition={{ type: "spring", damping: 30, stiffness: 400 }}
                                    rotationInterval={2500}
                                />
                            </p>
                        </div>

                        {/* CTA */}
                        <button
                            onClick={() => router.push('/instructions')}
                            className="bg-white text-black font-medium text-base py-4 px-12 hover:bg-gray-100 transition-colors"
                        >
                            Get Started
                        </button>
                    </div>
                </div>
            </div>

            {/* Animated Footer */}
            <BubbleFooter />
        </div>
    );
}
