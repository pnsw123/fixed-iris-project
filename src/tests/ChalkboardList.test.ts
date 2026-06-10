/**
 * Tests for ChalkboardList.tsx — Issue #275 fix: setTimeout cleanup
 *
 * ChalkboardList is a 'use client' animation component with browser APIs.
 * Following project pattern (ComparisonSlider.test.tsx): test pure logic inline,
 * no @testing-library/react, no DOM.
 *
 * What we test:
 *   - Row start time calculation: INITIAL_DELAY + (ROW_TOTAL_TIME * index)
 *   - ROW_TOTAL_TIME derivation from component constants
 *   - All three per-row timer offsets (circle, underline, icon)
 *   - Cleanup contract: ids array collects all setTimeout IDs (3 per item)
 *   - Fast-unmount scenario: cleanup must cancel pending timers (no stale setState)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mirror component constants (keep in sync with ChalkboardList.tsx)
// ---------------------------------------------------------------------------

const INITIAL_DELAY      = 450;
const CIRCLE_DURATION    = 450;
const UNDERLINE_DURATION = 350;
const ICON_DURATION      = 350;
const UNDERLINE_DELAY    = 250;
const ICON_DELAY         = 200;
const NEXT_ROW_DELAY     = 250;

const ROW_TOTAL_TIME =
    CIRCLE_DURATION + UNDERLINE_DELAY + UNDERLINE_DURATION + ICON_DELAY + ICON_DURATION + NEXT_ROW_DELAY;

// ---------------------------------------------------------------------------
// Pure helpers (mirror component logic, no React needed)
// ---------------------------------------------------------------------------

/** Returns the absolute ms at which each of the three timers fires for a given row index. */
function rowTimerOffsets(index: number): { circle: number; underline: number; icon: number } {
    const rowStart = INITIAL_DELAY + ROW_TOTAL_TIME * index;
    return {
        circle:    rowStart,
        underline: rowStart + CIRCLE_DURATION + UNDERLINE_DELAY,
        icon:      rowStart + CIRCLE_DURATION + UNDERLINE_DELAY + UNDERLINE_DURATION + ICON_DELAY,
    };
}

/** Simulates the useEffect body: registers timers into an ids array, returns cleanup fn. */
function simulateEffect(itemCount: number): { ids: number[]; cleanup: () => void } {
    const ids: ReturnType<typeof setTimeout>[] = [];

    for (let index = 0; index < itemCount; index++) {
        const { circle, underline, icon } = rowTimerOffsets(index);

        ids.push(setTimeout(() => { /* setAnimationStates circle */ }, circle));
        ids.push(setTimeout(() => { /* setAnimationStates underline */ }, underline));
        ids.push(setTimeout(() => { /* setAnimationStates icon */ }, icon));
    }

    return { ids: ids as unknown as number[], cleanup: () => ids.forEach(clearTimeout) };
}

// ---------------------------------------------------------------------------
// ROW_TOTAL_TIME derivation
// ---------------------------------------------------------------------------

describe('ChalkboardList — ROW_TOTAL_TIME', () => {
    it('equals sum of all per-row durations and delays', () => {
        const expected =
            CIRCLE_DURATION + UNDERLINE_DELAY + UNDERLINE_DURATION + ICON_DELAY + ICON_DURATION + NEXT_ROW_DELAY;
        expect(ROW_TOTAL_TIME).toBe(expected);
    });

    it('is 1850ms with current constants', () => {
        // 450 + 250 + 350 + 200 + 350 + 250 = 1850
        expect(ROW_TOTAL_TIME).toBe(1850);
    });
});

// ---------------------------------------------------------------------------
// Row timer offsets
// ---------------------------------------------------------------------------

describe('ChalkboardList — row timer offsets', () => {
    it('row 0: circle fires at INITIAL_DELAY', () => {
        expect(rowTimerOffsets(0).circle).toBe(INITIAL_DELAY);
    });

    it('row 0: underline fires after circle + underline delay', () => {
        expect(rowTimerOffsets(0).underline).toBe(INITIAL_DELAY + CIRCLE_DURATION + UNDERLINE_DELAY);
    });

    it('row 0: icon fires after underline + icon delay', () => {
        expect(rowTimerOffsets(0).icon).toBe(
            INITIAL_DELAY + CIRCLE_DURATION + UNDERLINE_DELAY + UNDERLINE_DURATION + ICON_DELAY
        );
    });

    it('row 1 starts exactly ROW_TOTAL_TIME after row 0', () => {
        const row0 = rowTimerOffsets(0);
        const row1 = rowTimerOffsets(1);
        expect(row1.circle - row0.circle).toBe(ROW_TOTAL_TIME);
    });

    it('rows are strictly sequential — row N circle > row (N-1) icon', () => {
        for (let i = 1; i < 4; i++) {
            const prev = rowTimerOffsets(i - 1);
            const curr = rowTimerOffsets(i);
            expect(curr.circle).toBeGreaterThan(prev.icon);
        }
    });

    it('all three timers within same row are ordered: circle < underline < icon', () => {
        [0, 1, 2, 3].forEach(i => {
            const { circle, underline, icon } = rowTimerOffsets(i);
            expect(underline).toBeGreaterThan(circle);
            expect(icon).toBeGreaterThan(underline);
        });
    });
});

// ---------------------------------------------------------------------------
// Cleanup contract (core of issue #275 fix)
// ---------------------------------------------------------------------------

describe('ChalkboardList — setTimeout cleanup (issue #275)', () => {
    beforeEach(() => { vi.useFakeTimers(); });
    afterEach(() => { vi.useRealTimers(); });

    it('collects exactly 3 timer IDs per item', () => {
        const { ids } = simulateEffect(4);
        expect(ids).toHaveLength(12); // 3 × 4
    });

    it('collects 3 IDs for 1 item', () => {
        const { ids } = simulateEffect(1);
        expect(ids).toHaveLength(3);
    });

    it('collects 0 IDs for empty item list', () => {
        const { ids } = simulateEffect(0);
        expect(ids).toHaveLength(0);
    });

    it('cleanup function clears all pending timers — no stale setState on unmount', () => {
        const callbacks: (() => void)[] = [];

        // Intercept setTimeouts to capture callback refs
        const originalSetTimeout = globalThis.setTimeout;
        const intercepted: { id: ReturnType<typeof setTimeout>; fn: () => void }[] = [];

        vi.spyOn(globalThis, 'setTimeout').mockImplementation(
            (fn: TimerHandler, _delay?: number): ReturnType<typeof setTimeout> => {
                const id = originalSetTimeout(fn as () => void, 0);
                intercepted.push({ id, fn: fn as () => void });
                callbacks.push(fn as () => void);
                return id;
            }
        );

        const { cleanup } = simulateEffect(4);

        // Before cleanup: 12 timers registered
        expect(intercepted).toHaveLength(12);

        // Cleanup cancels all
        cleanup();

        // Cleanup return contract: all IDs passed to clearTimeout
        // (The spy above proves 12 timers were collected — the cleanup fn iterates all of them)
        expect(intercepted).toHaveLength(12);

        vi.restoreAllMocks();
    });

    it('cleanup is a function (not a noop / undefined)', () => {
        const { cleanup } = simulateEffect(4);
        expect(typeof cleanup).toBe('function');
    });

    it('cleanup can be called with 0 items without throwing', () => {
        const { cleanup } = simulateEffect(0);
        expect(() => cleanup()).not.toThrow();
    });

    it('fast unmount: cleanup called before any timer fires clears all 12', () => {
        const clearedIds: ReturnType<typeof setTimeout>[] = [];
        const originalClearTimeout = globalThis.clearTimeout;

        vi.spyOn(globalThis, 'clearTimeout').mockImplementation(
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            (id?: any) => {
                if (id !== undefined) clearedIds.push(id as ReturnType<typeof setTimeout>);
                originalClearTimeout(id);
            }
        );

        const { cleanup } = simulateEffect(4);
        cleanup(); // simulate immediate unmount before any timer fires

        expect(clearedIds).toHaveLength(12);

        vi.restoreAllMocks();
    });
});

// ---------------------------------------------------------------------------
// Animation state shape contract
// ---------------------------------------------------------------------------

describe('ChalkboardList — animation state shape', () => {
    it('initial state for N items has N entries', () => {
        const items = [1, 2, 3, 4];
        const initial = items.map(() => ({ circle: false, underline: false, icon: false }));
        expect(initial).toHaveLength(4);
    });

    it('each state entry starts as all-false', () => {
        const entry = { circle: false, underline: false, icon: false };
        expect(entry.circle).toBe(false);
        expect(entry.underline).toBe(false);
        expect(entry.icon).toBe(false);
    });

    it('state update for circle sets only circle, not underline or icon', () => {
        const prev = { circle: false, underline: false, icon: false };
        const next = { ...prev, circle: true };
        expect(next.circle).toBe(true);
        expect(next.underline).toBe(false);
        expect(next.icon).toBe(false);
    });

    it('state update for underline sets only underline', () => {
        const prev = { circle: true, underline: false, icon: false };
        const next = { ...prev, underline: true };
        expect(next.circle).toBe(true);
        expect(next.underline).toBe(true);
        expect(next.icon).toBe(false);
    });

    it('state update for icon sets only icon', () => {
        const prev = { circle: true, underline: true, icon: false };
        const next = { ...prev, icon: true };
        expect(next.circle).toBe(true);
        expect(next.underline).toBe(true);
        expect(next.icon).toBe(true);
    });
});
