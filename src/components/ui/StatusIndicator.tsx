'use client';

import { Eye, Lightbulb, Target, Focus } from 'lucide-react';

interface StatusIndicatorProps {
    type: 'distance' | 'centering' | 'lighting' | 'focus';
    status: 'ok' | 'warn' | 'fail';
}

export default function StatusIndicator({ type, status }: StatusIndicatorProps) {
    const getIcon = () => {
        switch (type) {
            case 'distance':
                return <Eye className="w-3.5 h-3.5" />;
            case 'centering':
                return <Target className="w-3.5 h-3.5" />;
            case 'lighting':
                return <Lightbulb className="w-3.5 h-3.5" />;
            case 'focus':
                return <Focus className="w-3.5 h-3.5" />;
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

    return (
        <div className={`flex items-center gap-1.5 px-2.5 py-1.5 border rounded-full backdrop-blur-sm transition-all duration-300 ${getColor()}`}>
            {getIcon()}
            <span className="text-[10px] font-medium uppercase tracking-wide">{getLabel()}</span>
        </div>
    );
}
