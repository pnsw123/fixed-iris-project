'use client';

import { useEffect, useRef } from 'react';
import rough from 'roughjs';

interface RoughIconProps {
    color?: string;
    size?: number;
    show?: boolean;
    animate?: boolean;
    animationDuration?: number;
    animationDelay?: number;
}

// Helper to animate paths
const animatePaths = (svg: SVGSVGElement, duration: number, delay: number) => {
    const paths = svg.querySelectorAll('path');
    paths.forEach((path) => {
        const length = path.getTotalLength();
        path.style.strokeDasharray = `${length}`;
        path.style.strokeDashoffset = `${length}`;
        path.style.animation = `drawLine ${duration}ms ease-out forwards ${delay}ms`;
    });
};

// Accent strokes - sparkle/starburst 4-pointed star (scribble doodle style)
export function RoughAccentStrokes({
    color = '#a78bfa',
    size = 30,
    show = false,
    animate = true,
    animationDuration = 400,
    animationDelay = 0
}: RoughIconProps) {
    const svgRef = useRef<SVGSVGElement>(null);

    useEffect(() => {
        if (!svgRef.current) return;

        const svg = svgRef.current;
        svg.innerHTML = '';

        const rc = rough.svg(svg);

        // More complex "twiggy" snake-like path with multiple loops
        const curvePath = `M ${size * 0.05} ${size * 0.4}
                          C ${size * 0.1} ${size * 0.1}, ${size * 0.9} ${size * 0.1}, ${size * 0.7} ${size * 0.5}
                          S ${size * 0.2} ${size * 0.9}, ${size * 0.6} ${size * 0.8}
                          S ${size * 1.1} ${size * 1.1}, ${size * 0.95} ${size * 0.6}`;

        svg.appendChild(rc.path(curvePath, {
            stroke: color,
            strokeWidth: 3, // Thicker stroke
            fill: 'none',
            roughness: 1.8, // More sketchy
        }));

        // Arrow head at the end
        const arrowX = size * 0.95;
        const arrowY = size * 0.6;
        svg.appendChild(rc.line(arrowX, arrowY, arrowX + size * 0.15, arrowY - size * 0.15, {
            stroke: color,
            strokeWidth: 2.5,
            roughness: 1.0,
        }));
        svg.appendChild(rc.line(arrowX, arrowY, arrowX - size * 0.05, arrowY + size * 0.2, {
            stroke: color,
            strokeWidth: 2.5,
            roughness: 1.0,
        }));

        if (animate && show) animatePaths(svg, animationDuration, animationDelay);
    }, [color, size, animate, animationDuration, animationDelay, show]);

    return (
        <svg
            ref={svgRef}
            width={size}
            height={size}
            className="inline-block"
            style={{
                overflow: 'visible',
                opacity: show ? 1 : 0,
                transition: 'opacity 0.5s ease-out'
            }}
        />
    );
}

// Flashlight icon - centered in square SVG
export function RoughFlashlight({
    color = '#a78bfa',
    size = 24,
    show = true,
    animate = true,
    animationDuration = 350,
    animationDelay = 0
}: RoughIconProps) {
    const svgRef = useRef<SVGSVGElement>(null);

    useEffect(() => {
        if (!svgRef.current) return;

        const svg = svgRef.current;
        svg.innerHTML = '';

        const rc = rough.svg(svg);
        const s = size;

        // Flashlight body (horizontal)
        // Main body
        svg.appendChild(rc.rectangle(s * 0.4, s * 0.35, s * 0.5, s * 0.3, {
            stroke: color, strokeWidth: 1.5, roughness: 1, fill: 'none',
        }));

        // Front head
        svg.appendChild(rc.rectangle(s * 0.2, s * 0.25, s * 0.2, s * 0.5, {
            stroke: color, strokeWidth: 1.5, roughness: 1, fill: 'none',
        }));

        // Light rays
        const rayStart = s * 0.15;
        const rayEnd = 0;
        const dashLen = s * 0.1;

        svg.appendChild(rc.line(rayStart, s * 0.5, rayEnd, s * 0.5, {
            stroke: color, strokeWidth: 1.5, roughness: 0.5, strokeLineDash: [dashLen, dashLen],
        }));
        svg.appendChild(rc.line(rayStart, s * 0.35, rayEnd, s * 0.25, {
            stroke: color, strokeWidth: 1.5, roughness: 0.5, strokeLineDash: [dashLen, dashLen],
        }));
        svg.appendChild(rc.line(rayStart, s * 0.65, rayEnd, s * 0.75, {
            stroke: color, strokeWidth: 1.5, roughness: 0.5, strokeLineDash: [dashLen, dashLen],
        }));

        if (animate) animatePaths(svg, animationDuration, animationDelay);
    }, [color, size, show, animate, animationDuration, animationDelay]);

    return <svg ref={svgRef} width={size} height={size} className="inline-block" style={{ overflow: 'visible', marginLeft: '78px' }} />;
}

// Focus brackets icon - centered in square SVG
export function RoughFocusBrackets({
    color = '#a78bfa',
    size = 24,
    show = true,
    animate = true,
    animationDuration = 350,
    animationDelay = 0
}: RoughIconProps) {
    const svgRef = useRef<SVGSVGElement>(null);

    useEffect(() => {
        if (!svgRef.current) return;

        const svg = svgRef.current;
        svg.innerHTML = '';

        const rc = rough.svg(svg);
        const s = size;
        const corner = s * 0.3;
        const m = s * 0.1;

        // Brackets
        svg.appendChild(rc.line(m, m, m, m + corner, { stroke: color, strokeWidth: 1.5, roughness: 0.8 }));
        svg.appendChild(rc.line(m, m, m + corner, m, { stroke: color, strokeWidth: 1.5, roughness: 0.8 }));
        svg.appendChild(rc.line(s - m, m, s - m, m + corner, { stroke: color, strokeWidth: 1.5, roughness: 0.8 }));
        svg.appendChild(rc.line(s - m, m, s - m - corner, m, { stroke: color, strokeWidth: 1.5, roughness: 0.8 }));
        svg.appendChild(rc.line(m, s - m, m, s - m - corner, { stroke: color, strokeWidth: 1.5, roughness: 0.8 }));
        svg.appendChild(rc.line(m, s - m, m + corner, s - m, { stroke: color, strokeWidth: 1.5, roughness: 0.8 }));
        svg.appendChild(rc.line(s - m, s - m, s - m, s - m - corner, { stroke: color, strokeWidth: 1.5, roughness: 0.8 }));
        svg.appendChild(rc.line(s - m, s - m, s - m - corner, s - m, { stroke: color, strokeWidth: 1.5, roughness: 0.8 }));

        // Center plus
        const c = s / 2;
        const ps = s * 0.15;
        svg.appendChild(rc.line(c - ps, c, c + ps, c, { stroke: color, strokeWidth: 1.5, roughness: 0.6 }));
        svg.appendChild(rc.line(c, c - ps, c, c + ps, { stroke: color, strokeWidth: 1.5, roughness: 0.6 }));

        if (animate) animatePaths(svg, animationDuration, animationDelay);
    }, [color, size, show, animate, animationDuration, animationDelay]);

    return <svg ref={svgRef} width={size} height={size} className="inline-block" style={{ overflow: 'visible', marginLeft: '124px' }} />;
}

// "Get Closer" icon - centered in square SVG
export function RoughGetCloser({
    color = '#a78bfa',
    size = 24,
    show = true,
    animate = true,
    animationDuration = 350,
    animationDelay = 0
}: RoughIconProps) {
    const svgRef = useRef<SVGSVGElement>(null);

    useEffect(() => {
        if (!svgRef.current) return;

        const svg = svgRef.current;
        svg.innerHTML = '';

        const rc = rough.svg(svg);
        const s = size; // Maintain square aspect ratio
        const cy = s * 0.5;
        const cx = s * 0.5;

        // Scale down everything to fit comfortably in the square
        const scale = 0.8;
        const hs = s * scale;
        const hcy = cy;
        const hcx = cx;

        // Left arrow →
        svg.appendChild(rc.line(hcx - hs * 0.55, hcy, hcx - hs * 0.28, hcy, { stroke: color, strokeWidth: 1.5, roughness: 0.5 }));
        svg.appendChild(rc.line(hcx - hs * 0.38, hcy - hs * 0.1, hcx - hs * 0.28, hcy, { stroke: color, strokeWidth: 1.5, roughness: 0.5 }));
        svg.appendChild(rc.line(hcx - hs * 0.38, hcy + hs * 0.1, hcx - hs * 0.28, hcy, { stroke: color, strokeWidth: 1.5, roughness: 0.5 }));

        // Center - Smiley face (larger and clearer)
        svg.appendChild(rc.circle(hcx, hcy, hs * 0.45, { stroke: color, strokeWidth: 2, roughness: 0.4, fill: 'none' }));
        // Eyes (bigger)
        svg.appendChild(rc.circle(hcx - hs * 0.1, hcy - hs * 0.06, hs * 0.08, { stroke: color, fill: color, fillStyle: 'solid', roughness: 0 }));
        svg.appendChild(rc.circle(hcx + hs * 0.1, hcy - hs * 0.06, hs * 0.08, { stroke: color, fill: color, fillStyle: 'solid', roughness: 0 }));
        // Smile (wider)
        svg.appendChild(rc.arc(hcx, hcy + hs * 0.02, hs * 0.22, hs * 0.18, 0, Math.PI, false, { stroke: color, strokeWidth: 2, roughness: 0.4 }));

        // Right arrow ←
        svg.appendChild(rc.line(hcx + hs * 0.28, hcy, hcx + hs * 0.55, hcy, { stroke: color, strokeWidth: 1.5, roughness: 0.5 }));
        svg.appendChild(rc.line(hcx + hs * 0.38, hcy - hs * 0.1, hcx + hs * 0.28, hcy, { stroke: color, strokeWidth: 1.5, roughness: 0.5 }));
        svg.appendChild(rc.line(hcx + hs * 0.38, hcy + hs * 0.1, hcx + hs * 0.28, hcy, { stroke: color, strokeWidth: 1.5, roughness: 0.5 }));

        if (animate) animatePaths(svg, animationDuration, animationDelay);
    }, [color, size, show, animate, animationDuration, animationDelay]);

    return <svg ref={svgRef} width={size} height={size} className="inline-block" style={{ overflow: 'visible', marginLeft: '88px' }} />;
}

// Eye icon - centered in square SVG, narrowed
export function RoughEye({
    color = '#a78bfa',
    size = 24,
    show = true,
    animate = true,
    animationDuration = 350,
    animationDelay = 0
}: RoughIconProps) {
    const svgRef = useRef<SVGSVGElement>(null);

    useEffect(() => {
        if (!svgRef.current) return;

        const svg = svgRef.current;
        svg.innerHTML = '';

        const rc = rough.svg(svg);
        const s = size;
        const cy = s * 0.5;
        const cx = s * 0.5;

        // Narrow almond eye shape, centered in size x size
        const w = s * 0.9; // Narrower than size to leave margin
        const xOffset = (s - w) / 2;

        // Top curve
        svg.appendChild(rc.path(`M${xOffset} ${cy} Q${cx} ${s * 0.2} ${xOffset + w} ${cy}`, {
            stroke: color, strokeWidth: 1.5, roughness: 0.4
        }));
        // Bottom curve
        svg.appendChild(rc.path(`M${xOffset} ${cy} Q${cx} ${s * 0.8} ${xOffset + w} ${cy}`, {
            stroke: color, strokeWidth: 1.5, roughness: 0.4
        }));
        // Pupil
        svg.appendChild(rc.circle(cx, cy, s * 0.2, {
            stroke: color, strokeWidth: 1.5, fill: 'none', roughness: 0.3
        }));

        if (animate) animatePaths(svg, animationDuration, animationDelay);
    }, [color, size, show, animate, animationDuration, animationDelay]);

    return <svg ref={svgRef} width={size} height={size} className="inline-block" style={{ overflow: 'visible', marginLeft: '63px' }} />;
}
