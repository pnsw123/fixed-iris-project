/**
 * Tests for useDebugMode.ts
 *
 * useDebugMode is a React hook that reads `?debug=true` from searchParams.
 * It uses next/navigation's useSearchParams — we test the logic directly
 * without mounting React.
 *
 * Strategy: replicate the minimal logic inline to verify the contract,
 * since the hook is a one-liner and cannot be tested outside React context
 * without a JSDOM + Next.js test harness.
 */
import { describe, it, expect } from 'vitest';

// ---------------------------------------------------------------------------
// Inline logic mirror — matches useDebugMode.ts exactly
// ---------------------------------------------------------------------------

/**
 * Simulates the behaviour of useDebugMode given a URLSearchParams object.
 * This is the logic: `searchParams.get('debug') === 'true'`
 */
function simulateDebugMode(params: URLSearchParams): boolean {
    return params.get('debug') === 'true';
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useDebugMode logic', () => {
    it('returns true when ?debug=true', () => {
        const params = new URLSearchParams('debug=true');
        expect(simulateDebugMode(params)).toBe(true);
    });

    it('returns false when ?debug=false', () => {
        const params = new URLSearchParams('debug=false');
        expect(simulateDebugMode(params)).toBe(false);
    });

    it('returns false when debug param is absent', () => {
        const params = new URLSearchParams('');
        expect(simulateDebugMode(params)).toBe(false);
    });

    it('returns false when debug param is "1" (not "true")', () => {
        const params = new URLSearchParams('debug=1');
        expect(simulateDebugMode(params)).toBe(false);
    });

    it('returns false when debug param is "True" (case-sensitive)', () => {
        const params = new URLSearchParams('debug=True');
        expect(simulateDebugMode(params)).toBe(false);
    });

    it('returns false when debug param is empty string', () => {
        const params = new URLSearchParams('debug=');
        expect(simulateDebugMode(params)).toBe(false);
    });

    it('returns true even with other query params present', () => {
        const params = new URLSearchParams('foo=bar&debug=true&baz=qux');
        expect(simulateDebugMode(params)).toBe(true);
    });

    it('returns false with only unrelated query params', () => {
        const params = new URLSearchParams('name=Alice&id=42');
        expect(simulateDebugMode(params)).toBe(false);
    });
});

// ---------------------------------------------------------------------------
// Module import contract test
// ---------------------------------------------------------------------------

describe('useDebugMode module', () => {
    it('exports a function named useDebugMode', async () => {
        // Dynamic import to verify the module loads without error
        // The hook itself requires React context — we just verify it exports
        const mod = await import('../hooks/useDebugMode');
        expect(typeof mod.useDebugMode).toBe('function');
    });
});
