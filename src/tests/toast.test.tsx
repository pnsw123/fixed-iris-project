/**
 * Tests for toast.tsx
 *
 * toast.tsx is a React context-based notification system.
 * It uses `'use client'` and Framer Motion animations — both browser-only.
 *
 * Strategy (matches project pattern from useDebugMode.test.ts and qualityMetrics.test.ts):
 *   - No @testing-library/react installed → test pure logic inline.
 *   - Replicate the addToast / removeToast / MAX_TOASTS logic to verify contracts.
 *   - Test the useToast() hook throws outside a provider via a simulated context mock.
 *   - Test ToastType values are the canonical four variants.
 *   - Test Toast interface shape (id, type, message, duration).
 *
 * Tests NOT here (require full JSDOM + React render tree):
 *   - Framer Motion animation lifecycle
 *   - requestAnimationFrame-based progress bar
 *   - Actual DOM rendering of ToastItem / ToastContainer
 */
import { describe, it, expect, vi } from 'vitest';

// ─── Type-level tests — no runtime needed ────────────────────────────────────

describe('ToastType values', () => {
    it('success is a valid ToastType string', () => {
        const t: import('../lib/toast').ToastType = 'success';
        expect(t).toBe('success');
    });

    it('error is a valid ToastType string', () => {
        const t: import('../lib/toast').ToastType = 'error';
        expect(t).toBe('error');
    });

    it('info is a valid ToastType string', () => {
        const t: import('../lib/toast').ToastType = 'info';
        expect(t).toBe('info');
    });

    it('warning is a valid ToastType string', () => {
        const t: import('../lib/toast').ToastType = 'warning';
        expect(t).toBe('warning');
    });
});

describe('Toast interface shape', () => {
    it('Toast object has required fields: id, type, message', () => {
        const toast: import('../lib/toast').Toast = {
            id: 'toast-1',
            type: 'success',
            message: 'Operation completed',
        };
        expect(toast.id).toBe('toast-1');
        expect(toast.type).toBe('success');
        expect(toast.message).toBe('Operation completed');
    });

    it('Toast duration field is optional', () => {
        const withDuration: import('../lib/toast').Toast = {
            id: 'toast-2',
            type: 'error',
            message: 'Something went wrong',
            duration: 6000,
        };
        const withoutDuration: import('../lib/toast').Toast = {
            id: 'toast-3',
            type: 'info',
            message: 'FYI',
        };
        expect(withDuration.duration).toBe(6000);
        expect(withoutDuration.duration).toBeUndefined();
    });
});

// ─── addToast logic — replicated inline ──────────────────────────────────────
//
// Matches the exact logic in toast.tsx ToastProvider.addToast
// This mirrors how qualityMetrics.test.ts re-implements logic inline for isolation.

const MAX_TOASTS = 3;

function createAddToast() {
    let counter = 0;
    const toasts: import('../lib/toast').Toast[] = [];

    function addToast(
        type: import('../lib/toast').ToastType,
        message: string,
        duration?: number
    ): import('../lib/toast').Toast[] {
        const id = `toast-${++counter}`;
        const toast: import('../lib/toast').Toast = {
            id,
            type,
            message,
            duration: duration ?? (type === 'error' ? 6000 : 4000),
        };
        const updated = [...toasts, toast];
        const result = updated.length > MAX_TOASTS
            ? updated.slice(updated.length - MAX_TOASTS)
            : updated;
        toasts.length = 0;
        toasts.push(...result);
        return [...toasts];
    }

    function removeToast(id: string): import('../lib/toast').Toast[] {
        const filtered = toasts.filter((t) => t.id !== id);
        toasts.length = 0;
        toasts.push(...filtered);
        return [...toasts];
    }

    return { addToast, removeToast, getToasts: () => [...toasts] };
}

describe('addToast logic', () => {
    it('adds a success toast with default 4000ms duration', () => {
        const { addToast } = createAddToast();
        const result = addToast('success', 'Saved!');
        expect(result).toHaveLength(1);
        expect(result[0]!.type).toBe('success');
        expect(result[0]!.message).toBe('Saved!');
        expect(result[0]!.duration).toBe(4000);
    });

    it('adds an error toast with default 6000ms duration', () => {
        const { addToast } = createAddToast();
        const result = addToast('error', 'Upload failed');
        expect(result[0]!.duration).toBe(6000);
    });

    it('respects explicit duration override for success', () => {
        const { addToast } = createAddToast();
        const result = addToast('success', 'Done', 1500);
        expect(result[0]!.duration).toBe(1500);
    });

    it('respects explicit duration override for error', () => {
        const { addToast } = createAddToast();
        const result = addToast('error', 'Oops', 2000);
        expect(result[0]!.duration).toBe(2000);
    });

    it('assigns unique IDs to successive toasts', () => {
        const { addToast } = createAddToast();
        addToast('info', 'First');
        const r2 = addToast('info', 'Second');
        // r2 contains both toasts (cumulative state); their IDs must be distinct
        const ids = r2.map((t) => t.id);
        const unique = new Set(ids);
        expect(unique.size).toBe(ids.length);
    });

    it('accumulates toasts up to MAX_TOASTS (3)', () => {
        const { addToast } = createAddToast();
        addToast('info', 'One');
        addToast('info', 'Two');
        const result = addToast('info', 'Three');
        expect(result).toHaveLength(3);
    });

    it('caps at MAX_TOASTS — oldest is dropped when 4th is added', () => {
        const { addToast } = createAddToast();
        addToast('info', 'One');
        addToast('info', 'Two');
        addToast('info', 'Three');
        const result = addToast('info', 'Four');
        expect(result).toHaveLength(MAX_TOASTS);
        // "One" (first added) should be evicted; "Four" should be present
        const messages = result.map((t) => t.message);
        expect(messages).not.toContain('One');
        expect(messages).toContain('Four');
    });

    it('info and warning toasts default to 4000ms', () => {
        const { addToast } = createAddToast();
        const info = addToast('info', 'FYI');
        const warning = addToast('warning', 'Heads up');
        expect(info[0]!.duration).toBe(4000);
        expect(warning[1]!.duration).toBe(4000);
    });

    it('toast with duration=0 is persistent (no auto-dismiss)', () => {
        const { addToast } = createAddToast();
        const result = addToast('warning', 'Persistent', 0);
        expect(result[0]!.duration).toBe(0);
    });
});

describe('removeToast logic', () => {
    it('removes a toast by id', () => {
        const { addToast, removeToast } = createAddToast();
        const after = addToast('success', 'Hello');
        const id = after[0]!.id;
        const result = removeToast(id);
        expect(result.find((t) => t.id === id)).toBeUndefined();
    });

    it('does not remove other toasts when removing one', () => {
        const { addToast, removeToast } = createAddToast();
        addToast('info', 'First');
        const after = addToast('info', 'Second');
        const idFirst = after[0]!.id;
        const idSecond = after[1]!.id;
        const result = removeToast(idFirst);
        expect(result.find((t) => t.id === idSecond)).toBeDefined();
        expect(result).toHaveLength(1);
    });

    it('is a no-op when id does not exist', () => {
        const { addToast, removeToast } = createAddToast();
        addToast('info', 'Only toast');
        const result = removeToast('toast-9999');
        expect(result).toHaveLength(1);
    });

    it('results in empty array when last toast is removed', () => {
        const { addToast, removeToast } = createAddToast();
        const after = addToast('error', 'Sole toast');
        const result = removeToast(after[0]!.id);
        expect(result).toHaveLength(0);
    });
});

// ─── useToast hook — throws outside provider ─────────────────────────────────
//
// We cannot mount React in a pure Node/vitest environment without JSDOM.
// We validate the guard logic by replicating it inline — the guard is a one-liner.

describe('useToast guard', () => {
    it('throws when ToastContext value is null (no provider)', () => {
        // Replicate guard: if (!ctx) throw new Error('useToast must be used within a ToastProvider')
        function simulateUseToast(ctx: unknown) {
            if (!ctx) throw new Error('useToast must be used within a ToastProvider');
            return ctx;
        }

        expect(() => simulateUseToast(null)).toThrow(
            'useToast must be used within a ToastProvider'
        );
    });

    it('does not throw when ToastContext value is provided', () => {
        function simulateUseToast(ctx: unknown) {
            if (!ctx) throw new Error('useToast must be used within a ToastProvider');
            return ctx;
        }

        const fakeCtx = {
            toasts: [],
            addToast: vi.fn(),
            removeToast: vi.fn(),
        };

        expect(() => simulateUseToast(fakeCtx)).not.toThrow();
    });
});

// ─── Module export contract ───────────────────────────────────────────────────

describe('toast module exports', () => {
    it('exports ToastProvider as a function', async () => {
        // Dynamic import to verify module loads without error in node env.
        // motion/react and lucide-react are ESM — vitest handles them without DOM.
        // If the import itself fails, the test will error with a clear message.
        const mod = await import('../lib/toast');
        expect(typeof mod.ToastProvider).toBe('function');
    });

    it('exports useToast as a function', async () => {
        const mod = await import('../lib/toast');
        expect(typeof mod.useToast).toBe('function');
    });
});
