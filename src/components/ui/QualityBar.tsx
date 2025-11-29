'use client';

interface QualityBarProps {
    label: string;
    score: number; // 0-100
    status: 'ok' | 'warn' | 'fail';
    feedback: string;
}

export default function QualityBar({ label, score, status, feedback }: QualityBarProps) {
    const getBarColor = () => {
        switch (status) {
            case 'ok':
                return 'bg-emerald-500';
            case 'warn':
                return 'bg-yellow-500';
            case 'fail':
                return 'bg-red-500';
        }
    };

    const getTextColor = () => {
        switch (status) {
            case 'ok':
                return 'text-emerald-400';
            case 'warn':
                return 'text-yellow-400';
            case 'fail':
                return 'text-red-400';
        }
    };

    return (
        <div className="space-y-1">
            {/* Label and Feedback */}
            <div className="flex items-center justify-between text-[10px]">
                <span className="font-mono uppercase tracking-wider text-gray-500">{label}</span>
                <span className={`font-medium ${getTextColor()} transition-colors`}>{feedback}</span>
            </div>
            
            {/* Progress Bar */}
            <div className="h-1 bg-gray-900/60 rounded-full overflow-hidden">
                <div
                    className={`h-full ${getBarColor()} transition-all duration-300 ease-out`}
                    style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
                />
            </div>
        </div>
    );
}
