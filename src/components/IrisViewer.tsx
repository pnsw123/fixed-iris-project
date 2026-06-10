'use client';

import React, { useState, useRef } from 'react';
import { ZoomIn, ZoomOut, Maximize2, Download, Sparkles } from 'lucide-react';

interface IrisViewerProps {
    imageUrl: string;
    originalUrl?: string;
}

export default function IrisViewer({ imageUrl, originalUrl }: IrisViewerProps) {
    const [zoom, setZoom] = useState(1);
    const [position, setPosition] = useState({ x: 0, y: 0 });
    const [isDragging, setIsDragging] = useState(false);
    const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
    const [showComparison, setShowComparison] = useState(false);

    const containerRef = useRef<HTMLDivElement>(null);

    const handleZoomIn = () => setZoom(prev => Math.min(prev + 0.5, 4));
    const handleZoomOut = () => setZoom(prev => Math.max(prev - 0.5, 1));
    const handleReset = () => {
        setZoom(1);
        setPosition({ x: 0, y: 0 });
    };

    const handleDownload = () => {
        const link = document.createElement('a');
        link.href = imageUrl;
        link.download = 'enhanced-iris.png';
        link.click();
    };

    const handleMouseDown = (e: React.MouseEvent) => {
        if (zoom > 1) {
            setIsDragging(true);
            setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
        }
    };

    const handleMouseMove = (e: React.MouseEvent) => {
        if (isDragging && zoom > 1) {
            setPosition({
                x: e.clientX - dragStart.x,
                y: e.clientY - dragStart.y
            });
        }
    };

    const handleMouseUp = () => {
        setIsDragging(false);
    };

    return (
        <div className="w-full h-full flex flex-col bg-gradient-to-br from-neutral-900 via-neutral-800 to-neutral-900">
            {/* Controls Bar */}
            <div className="flex items-center justify-between gap-2 p-4 bg-black/30 backdrop-blur-md border-b border-white/10">
                <div className="flex items-center gap-2">
                    <Sparkles className="text-green-400" size={20} />
                    <span className="text-sm font-medium text-white">AI Enhanced Iris</span>
                </div>

                <div className="flex gap-2">
                    <button
                        onClick={handleZoomOut}
                        disabled={zoom <= 1}
                        className="p-2 rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                        title="Zoom Out"
                    >
                        <ZoomOut size={18} className="text-white" />
                    </button>
                    <button
                        onClick={handleZoomIn}
                        disabled={zoom >= 4}
                        className="p-2 rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                        title="Zoom In"
                    >
                        <ZoomIn size={18} className="text-white" />
                    </button>
                    <button
                        onClick={handleReset}
                        className="p-2 rounded-lg bg-white/10 hover:bg-white/20 transition-all"
                        title="Reset View"
                    >
                        <Maximize2 size={18} className="text-white" />
                    </button>
                    <button
                        onClick={handleDownload}
                        className="p-2 rounded-lg bg-green-600/80 hover:bg-green-600 transition-all"
                        title="Download Enhanced Image"
                    >
                        <Download size={18} className="text-white" />
                    </button>
                    {originalUrl && (
                        <button
                            onClick={() => setShowComparison(!showComparison)}
                            className={`px-3 py-2 rounded-lg transition-all text-sm font-medium ${showComparison
                                    ? 'bg-blue-600 text-white'
                                    : 'bg-white/10 text-white hover:bg-white/20'
                                }`}
                        >
                            {showComparison ? 'Hide Compare' : 'Compare'}
                        </button>
                    )}
                </div>
            </div>

            {/* Image Display Area */}
            <div
                ref={containerRef}
                className={`flex-1 relative overflow-hidden ${zoom > 1 ? 'cursor-move' : 'cursor-default'}`}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
            >
                {showComparison && originalUrl ? (
                    // Comparison Mode: Side by Side
                    <div className="flex h-full gap-1">
                        <div className="flex-1 relative bg-neutral-950 flex items-center justify-center">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                                src={originalUrl}
                                alt="Original Iris"
                                className="max-w-full max-h-full object-contain"
                                draggable={false}
                            />
                            <div className="absolute bottom-4 left-4 bg-black/80 px-3 py-1.5 rounded-lg text-xs font-medium text-white border border-white/20">
                                Original
                            </div>
                        </div>
                        <div className="flex-1 relative bg-neutral-950 flex items-center justify-center">
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img
                                src={imageUrl}
                                alt="AI Enhanced Iris"
                                className="max-w-full max-h-full object-contain transition-transform duration-200"
                                style={{
                                    transform: `scale(${zoom}) translate(${position.x / zoom}px, ${position.y / zoom}px)`,
                                    transformOrigin: 'center'
                                }}
                                draggable={false}
                            />
                            <div className="absolute bottom-4 left-4 bg-green-600/90 px-3 py-1.5 rounded-lg text-xs font-medium text-white border border-green-400/30 flex items-center gap-1.5">
                                <Sparkles size={12} />
                                AI Enhanced
                            </div>
                        </div>
                    </div>
                ) : (
                    // Single Image Mode
                    <div className="w-full h-full flex items-center justify-center bg-neutral-950">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                            src={imageUrl}
                            alt="AI Enhanced Iris"
                            className="max-w-full max-h-full object-contain transition-transform duration-200"
                            style={{
                                transform: `scale(${zoom}) translate(${position.x / zoom}px, ${position.y / zoom}px)`,
                                transformOrigin: 'center'
                            }}
                            draggable={false}
                        />
                    </div>
                )}
            </div>

            {/* Info Panel */}
            <div className="p-4 bg-black/30 backdrop-blur-md border-t border-white/10">
                <div className="flex justify-between items-center text-sm">
                    <div className="flex items-center gap-4">
                        <span className="text-neutral-400">
                            Zoom: <span className="text-white font-medium">{(zoom * 100).toFixed(0)}%</span>
                        </span>
                        {zoom > 1 && (
                            <span className="text-neutral-500 text-xs">
                                Drag to pan
                            </span>
                        )}
                    </div>
                    <div className="flex items-center gap-2 text-green-400">
                        <Sparkles size={14} />
                        <span className="text-xs font-medium">AI Super-Resolution Applied</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
