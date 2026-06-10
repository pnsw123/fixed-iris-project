'use client';

import { Eye, Lightbulb, Target, Focus, Smartphone } from 'lucide-react';

interface StatusIndicatorProps {
    type: 'distance' | 'centering' | 'lighting' | 'focus' | 'angle';
    status: 'ok' | 'warn' | 'fail';
}

export default function StatusIndicator({ type, status }: StatusIndicatorProps) {
    const getIcon = () => {
        switch (type) {
            case 'distance':
                return <Eye className="w-4 h-4 shrink-0" />;
            case 'centering':
                return <Target className="w-4 h-4 shrink-0" />;
            case 'lighting':
                return <Lightbulb className="w-4 h-4 shrink-0" />;
            case 'focus':
                return <Focus className="w-4 h-4 shrink-0" />;
            case 'angle':
                return <Smartphone className="w-4 h-4 shrink-0" />;
        }
    };

    const getLabel = () => {
        switch (type) {
            case 'distance':
                return 'Distance';
            case 'centering':
                return 'Centered';
            case 'lighting':
                return 'Light';
            case 'focus':
                return 'Focus';
            case 'angle':
                return 'Angle';
        }
    };

    const getColor = () => {
        switch (status) {
            case 'ok':
                return 'text-emerald-400 border-emerald-400/30 bg-emerald-400/5';
            case 'warn':
                return 'text-amber-400 border-amber-400/30 bg-amber-400/5';
            case 'fail':
                return 'text-gray-500 border-gray-700/30 bg-gray-900/20';
        }
    };

    const getStatusLabel = () => {
        switch (status) {
            case 'ok':
                return 'good';
            case 'warn':
                return 'warning';
            case 'fail':
                return 'poor';
        }
    };

    return (
        <div
            role="status"
            aria-live="polite"
            aria-label={`${getLabel()}: ${getStatusLabel()}`}
            className={`flex items-center gap-2 px-3 py-2 min-h-[36px] border rounded-full backdrop-blur-sm transition-all duration-300 ${getColor()}`}
        >
            {getIcon()}
            <span className="text-xs font-medium uppercase tracking-wide leading-none">{getLabel()}</span>
        </div>
    );
}
