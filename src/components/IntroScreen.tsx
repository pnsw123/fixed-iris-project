'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { DotLottieReact } from '@lottiefiles/dotlottie-react';
import rough from 'roughjs';
import BubbleFooter from './BubbleFooter';
import WordListSwap from './WordListSwap';
import SpotlightBackground from './SpotlightBackground';

// Helper to animate paths
const animatePaths = (svg: SVGSVGElement, duration: number, delay: number) => {
    const paths = svg.querySelectorAll('path, line');
    paths.forEach((path: any) => {
        const length = path.getTotalLength ? path.getTotalLength() : 100;
        path.style.strokeDasharray = `${length}`;
        path.style.strokeDashoffset = `${length}`;
        path.style.animation = `drawLine ${duration}ms ease-out forwards ${delay}ms`;
    });
};

// Replaced ZigzagDoodle with a hand-drawn star with radiating lines
function StarDoodle({ show, color = '#a78bfa', size = 120 }: { show: boolean, color?: string, size?: number }) {
    const svgRef = useRef<SVGSVGElement>(null);

    useEffect(() => {
        if (!svgRef.current || !show) return;
        const svg = svgRef.current;
        svg.innerHTML = '';
        const rc = rough.svg(svg);
        const s = size;
        const p = (x: number, y: number) => `${x * s / 100} ${y * s / 100}`;

        // 5-pointed star path
        const starPath = `
            M ${p(50, 15)} 
            L ${p(60, 40)} L ${p(85, 40)} 
            L ${p(65, 55)} L ${p(75, 80)} 
            L ${p(50, 65)} 
            L ${p(25, 80)} L ${p(35, 55)} 
            L ${p(15, 40)} L ${p(40, 40)} 
            Z
        `;

        // Draw star with a tilt
        const starNode = rc.path(starPath, {
            stroke: color, strokeWidth: 2, roughness: 1.5, fill: 'none', bowing: 1
        });

        // Apply rotation to the star node itself around the center
        // 110 degrees visual tilt (approx -20deg relative to upright)
        starNode.setAttribute('transform', `rotate(-20, ${size / 2}, ${size / 2})`);
        svg.appendChild(starNode);

        // Radiating lines (sparkles) - aligned with the "valleys" (inner vertices)
        // Star inner vertices were: (60,40), (65,55), (50,65), (35,55), (40,40)
        // We project lines outward from these directions relative to center (50,50)

        // 1. Top-Right Valley (60,40) -> Direction approx (1, -1)
        // 2. Right-Bottom Valley (65,55) -> Direction approx (1, 0.3)
        // 3. Bottom Valley (50,65) -> Direction (0, 1)
        // 4. Left-Bottom Valley (35,55) -> Direction (-1, 0.3)
        // 5. Top-Left Valley (40,40) -> Direction (-1, -1)

        const lines = [
            // Top-Right
            { x1: 72, y1: 30, x2: 80, y2: 22 },
            // Right (low)
            { x1: 85, y1: 55, x2: 95, y2: 58 },
            // Bottom
            { x1: 50, y1: 80, x2: 50, y2: 92 },
            // Left (low)
            { x1: 15, y1: 55, x2: 5, y2: 58 },
            // Top-Left
            { x1: 28, y1: 30, x2: 20, y2: 22 },
        ];

        // Draw lines
        const lineNodes: SVGElement[] = [];
        lines.forEach(line => {
            const node = rc.line(
                line.x1 * s / 100, line.y1 * s / 100,
                line.x2 * s / 100, line.y2 * s / 100,
                { stroke: color, strokeWidth: 2, roughness: 1 }
            );
            // Rotate lines to match star tilt
            node.setAttribute('transform', `rotate(-20, ${size / 2}, ${size / 2})`);
            svg.appendChild(node);
            lineNodes.push(node);
        });

        // ANIMATION SEQUENCING
        // 1. Animate Star (1500ms - Slower)
        // Cast to any because RoughJS types might imply generic SVGElement
        const starLength = (starNode as any).getTotalLength ? (starNode as any).getTotalLength() : 100;
        starNode.style.strokeDasharray = `${starLength}`;
        starNode.style.strokeDashoffset = `${starLength}`;
        starNode.style.animation = `drawLine 1500ms ease-out forwards 0ms`;

        // 2. Animate Lines (burst after star finishes)
        lineNodes.forEach(node => {
            const pathNode = node.querySelector('path') || node;
            if (pathNode instanceof SVGPathElement || pathNode instanceof SVGLineElement) {
                // @ts-ignore
                const len = pathNode.getTotalLength ? pathNode.getTotalLength() : 20;
                pathNode.style.strokeDasharray = `${len}`;
                pathNode.style.strokeDashoffset = `${len}`;
                // Delay = 1500ms (star duration)
                pathNode.style.animation = `drawLine 800ms ease-out forwards 1500ms`;
            }
        });

    }, [show, color, size]);

    return (
        <svg
            ref={svgRef}
            width={size}
            height={size}
            style={{
                overflow: 'visible',
                pointerEvents: 'none',
                opacity: show ? 1 : 0,
                transition: 'opacity 0.6s ease-out'
            }}
        />
    );
}

interface IntroScreenProps {
    onStart?: () => void;
}

export default function IntroScreen({ onStart }: IntroScreenProps) {
    const router = useRouter();
    const titleRef = useRef<HTMLHeadingElement>(null);
    const [showUnderline, setShowUnderline] = useState(false);

    // Trigger underline animation after mount
    useEffect(() => {
        const timer = setTimeout(() => setShowUnderline(true), 500);
        return () => clearTimeout(timer);
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
            <SpotlightBackground />

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
            <div className="flex-1 flex flex-col items-center justify-center px-8 py-16 sm:px-16 relative z-10">
                <div className="max-w-xl w-full text-center">
                    {/* Giant Title with doodle */}
                    <h1
                        ref={titleRef}
                        className="text-6xl sm:text-7xl font-light text-white tracking-tight mb-6"
                    >
                        <span className="relative inline-block">
                            {/* Star doodle absolutely positioned top-left of the E, closer and smaller */}
                            <span className="absolute -top-6 -left-6 z-0">
                                <StarDoodle
                                    show={showUnderline}
                                    size={35}
                                    color="#a78bfa"
                                />
                            </span>
                            <span className="relative z-10">E</span>
                        </span>
                        <span>yedentity</span>
                    </h1>

                    {/* Tagline */}
                    <p className="text-gray-400 text-lg font-light flex items-center justify-center gap-2 mb-10">
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

                    {/* CTA */}
                    <button
                        onClick={() => router.push('/instructions')}
                        className="bg-white text-black font-medium text-base py-4 px-12 hover:bg-gray-100 transition-colors"
                    >
                        Get Started
                    </button>
                </div>
            </div>

            {/* Animated Footer */}
            <BubbleFooter />
        </div>
    );
}
