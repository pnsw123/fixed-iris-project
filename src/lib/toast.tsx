'use client';

/**
 * toast.tsx — Global toast notification system.
 *
 * Provides a React context-based toast provider with Framer Motion animations.
 * Toasts slide in from the bottom, auto-dismiss, and support manual close.
 *
 * Usage:
 *   1. Wrap app with <ToastProvider> in layout.tsx
 *   2. Call `const { toast } = useToast()` in any component
 *   3. `toast.success('Downloaded!')`, `toast.error('Upload failed')`, etc.
 */

import {
    createContext,
    useCallback,
    useContext,
    useRef,
    useState,
    useEffect,
} from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-react';

// ─── Types ────────────────────────────────────────────────────────────────────

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface Toast {
    id: string;
    type: ToastType;
    message: string;
    duration?: number; // ms, 0 = persistent
}

interface ToastContextValue {
    toasts: Toast[];
    addToast: (type: ToastType, message: string, duration?: number) => void;
    removeToast: (id: string) => void;
}

// ─── Context ──────────────────────────────────────────────────────────────────

const ToastContext = createContext<ToastContextValue | null>(null);

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useToast() {
    const ctx = useContext(ToastContext);
    if (!ctx) throw new Error('useToast must be used within a ToastProvider');

    const toast = {
        success: (message: string, duration?: number) =>
            ctx.addToast('success', message, duration),
        error: (message: string, duration?: number) =>
            ctx.addToast('error', message, duration ?? 6000),
        info: (message: string, duration?: number) =>
            ctx.addToast('info', message, duration),
        warning: (message: string, duration?: number) =>
            ctx.addToast('warning', message, duration),
    };

    return { toast, toasts: ctx.toasts, removeToast: ctx.removeToast };
}

// ─── Toast Item ───────────────────────────────────────────────────────────────

const TOAST_STYLES: Record<ToastType, { bg: string; border: string; text: string; icon: string }> = {
    success: {
        bg: 'bg-emerald-950/95',
        border: 'border-emerald-700/60',
        text: 'text-emerald-300',
        icon: 'text-emerald-400',
    },
    error: {
        bg: 'bg-red-950/95',
        border: 'border-red-700/60',
        text: 'text-red-300',
        icon: 'text-red-400',
    },
    info: {
        bg: 'bg-blue-950/95',
        border: 'border-blue-700/60',
        text: 'text-blue-300',
        icon: 'text-blue-400',
    },
    warning: {
        bg: 'bg-amber-950/95',
        border: 'border-amber-700/60',
        text: 'text-amber-300',
        icon: 'text-amber-400',
    },
};

const TOAST_ICONS: Record<ToastType, React.ReactNode> = {
    success: <CheckCircle className="w-4 h-4 shrink-0" />,
    error: <AlertCircle className="w-4 h-4 shrink-0" />,
    info: <Info className="w-4 h-4 shrink-0" />,
    warning: <AlertTriangle className="w-4 h-4 shrink-0" />,
};

interface ToastItemProps {
    toast: Toast;
    onRemove: (id: string) => void;
}

function ToastItem({ toast, onRemove }: ToastItemProps) {
    const styles = TOAST_STYLES[toast.type];
    const duration = toast.duration ?? 4000;

    // Progress bar
    const [progress, setProgress] = useState(100);
    const startTime = useRef<number>(0);
    const rafRef = useRef<number | null>(null);

    useEffect(() => {
        if (duration === 0) return;

        startTime.current = Date.now();

        const tick = () => {
            const elapsed = Date.now() - startTime.current;
            const remaining = Math.max(0, 1 - elapsed / duration) * 100;
            setProgress(remaining);

            if (elapsed < duration) {
                rafRef.current = requestAnimationFrame(tick);
            } else {
                onRemove(toast.id);
            }
        };

        rafRef.current = requestAnimationFrame(tick);

        return () => {
            if (rafRef.current) cancelAnimationFrame(rafRef.current);
        };
    }, [toast.id, duration, onRemove]);

    return (
        <motion.div
            layout
            initial={{ opacity: 0, y: 24, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            className={`
                relative flex items-start gap-3 min-w-[280px] max-w-[360px]
                rounded-xl border px-4 py-3 shadow-2xl
                backdrop-blur-md overflow-hidden
                ${styles.bg} ${styles.border}
            `}
            role="alert"
            aria-live="polite"
        >
            {/* Icon */}
            <span className={`mt-0.5 ${styles.icon}`}>
                {TOAST_ICONS[toast.type]}
            </span>

            {/* Message */}
            <p className={`flex-1 text-sm font-medium leading-snug ${styles.text}`}>
                {toast.message}
            </p>

            {/* Close Button */}
            <button
                onClick={() => onRemove(toast.id)}
                className={`mt-0.5 shrink-0 opacity-60 hover:opacity-100 transition-opacity ${styles.text}`}
                aria-label="Dismiss notification"
            >
                <X className="w-3.5 h-3.5" />
            </button>

            {/* Progress bar — only shown when auto-dismissing */}
            {duration > 0 && (
                <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-white/10 overflow-hidden">
                    <div
                        className={`h-full transition-none ${
                            toast.type === 'success' ? 'bg-emerald-500/60' :
                            toast.type === 'error' ? 'bg-red-500/60' :
                            toast.type === 'warning' ? 'bg-amber-500/60' :
                            'bg-blue-500/60'
                        }`}
                        style={{ width: `${progress}%` }}
                    />
                </div>
            )}
        </motion.div>
    );
}

// ─── Toast Container ──────────────────────────────────────────────────────────

interface ToastContainerProps {
    toasts: Toast[];
    removeToast: (id: string) => void;
}

function ToastContainer({ toasts, removeToast }: ToastContainerProps) {
    return (
        <div
            className="fixed bottom-6 right-4 sm:right-6 z-[9999] flex flex-col items-end gap-2 pointer-events-none"
            aria-label="Notifications"
        >
            <AnimatePresence mode="sync">
                {toasts.map((t) => (
                    <div key={t.id} className="pointer-events-auto">
                        <ToastItem toast={t} onRemove={removeToast} />
                    </div>
                ))}
            </AnimatePresence>
        </div>
    );
}

// ─── Provider ─────────────────────────────────────────────────────────────────

const MAX_TOASTS = 3;

export function ToastProvider({ children }: { children: React.ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);
    const counterRef = useRef(0);

    const removeToast = useCallback((id: string) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    const addToast = useCallback(
        (type: ToastType, message: string, duration?: number) => {
            const id = `toast-${++counterRef.current}`;
            const toast: Toast = {
                id,
                type,
                message,
                duration: duration ?? (type === 'error' ? 6000 : 4000),
            };

            setToasts((prev) => {
                const updated = [...prev, toast];
                // Cap at MAX_TOASTS — drop oldest
                return updated.length > MAX_TOASTS
                    ? updated.slice(updated.length - MAX_TOASTS)
                    : updated;
            });
        },
        []
    );

    return (
        <ToastContext.Provider value={{ toasts, addToast, removeToast }}>
            {children}
            <ToastContainer toasts={toasts} removeToast={removeToast} />
        </ToastContext.Provider>
    );
}
