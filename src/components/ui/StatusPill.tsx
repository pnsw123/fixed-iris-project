'use client';

export type PillState = 'pass' | 'warn' | 'fail';

interface StatusPillProps {
    label: string;
    state: PillState;
}

export default function StatusPill({ label, state }: StatusPillProps) {
    const getStyles = () => {
        switch (state) {
            case 'pass':
                return {
                    border: 'border-gray-700',
                    text: 'text-gray-400',
                    dot: 'bg-gray-500',
                };
            case 'warn':
                return {
                    border: 'border-yellow-900/50',
                    text: 'text-yellow-600',
                    dot: 'bg-yellow-600',
                };
            case 'fail':
                return {
                    border: 'border-red-900/50',
                    text: 'text-red-500',
                    dot: 'bg-red-500',
                };
        }
    };

    const styles = getStyles();

    return (
        <div className={`flex items-center gap-2 px-3 py-2 border ${styles.border} bg-black/40 backdrop-blur-sm transition-all`}>
            <div className={`w-1.5 h-1.5 rounded-full ${styles.dot}`} />
            <span className={`text-xs font-mono uppercase tracking-wider ${styles.text}`}>{label}</span>
        </div>
    );
}
