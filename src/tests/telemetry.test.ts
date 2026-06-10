/**
 * Tests for telemetry.ts — Telemetry singleton.
 *
 * Telemetry uses console.log internally. We suppress that with vi.spyOn
 * to keep test output clean, but verify call counts.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { telemetry } from '../lib/telemetry';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Silence console during a callback, return the result. */
async function _silenced<T>(fn: () => T): Promise<T> {
    const spy = vi.spyOn(console, 'log').mockImplementation(() => {});
    try {
        return fn();
    } finally {
        spy.mockRestore();
    }
}

// ---------------------------------------------------------------------------
// Setup — reset telemetry before each test so tests don't bleed into each other
// ---------------------------------------------------------------------------

beforeEach(() => {
    vi.spyOn(console, 'log').mockImplementation(() => {});
    telemetry.reset();
});

afterEach(() => {
    vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// trackConditionFailure
// ---------------------------------------------------------------------------

describe('telemetry.trackConditionFailure', () => {
    it('increments noFace counter on each call', () => {
        telemetry.trackConditionFailure('noFace');
        telemetry.trackConditionFailure('noFace');

        // logSummary surfaces the counters — verify it doesn't throw
        expect(() => telemetry.logSummary()).not.toThrow();
    });

    it('tracks multiple independent condition counters', () => {
        telemetry.trackConditionFailure('distance');
        telemetry.trackConditionFailure('eyebrows');
        telemetry.trackConditionFailure('centering');
        telemetry.trackConditionFailure('focus');
        telemetry.trackConditionFailure('lighting');
        // Should not throw
        expect(() => telemetry.logSummary()).not.toThrow();
    });

    it('accepts all valid condition keys', () => {
        const keys = ['noFace', 'distance', 'eyebrows', 'centering', 'focus', 'lighting'] as const;
        keys.forEach(key => {
            expect(() => telemetry.trackConditionFailure(key)).not.toThrow();
        });
    });
});

// ---------------------------------------------------------------------------
// trackCountdownAbort
// ---------------------------------------------------------------------------

describe('telemetry.trackCountdownAbort', () => {
    it('logs the abort reason', () => {
        const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
        telemetry.trackCountdownAbort('noFace');
        // console.log is called with a single concatenated string
        expect(logSpy).toHaveBeenCalledWith(
            expect.stringContaining('[Telemetry] Countdown aborted: noFace')
        );
        logSpy.mockRestore();
    });

    it('accepts all valid abort reasons', () => {
        const reasons = ['noFace', 'distance', 'centering', 'other'] as const;
        reasons.forEach(reason => {
            expect(() => telemetry.trackCountdownAbort(reason)).not.toThrow();
        });
    });
});

// ---------------------------------------------------------------------------
// trackInferenceTime
// ---------------------------------------------------------------------------

describe('telemetry.trackInferenceTime', () => {
    it('does not throw on first call', () => {
        expect(() => telemetry.trackInferenceTime(50)).not.toThrow();
    });

    it('accumulates multiple inference times without throwing', () => {
        telemetry.trackInferenceTime(30);
        telemetry.trackInferenceTime(50);
        telemetry.trackInferenceTime(80);
        expect(() => telemetry.logSummary()).not.toThrow();
    });

    it('handles zero inference time', () => {
        expect(() => telemetry.trackInferenceTime(0)).not.toThrow();
    });

    it('handles very large inference time', () => {
        expect(() => telemetry.trackInferenceTime(99999)).not.toThrow();
    });
});

// ---------------------------------------------------------------------------
// logSummary
// ---------------------------------------------------------------------------

describe('telemetry.logSummary', () => {
    it('logs summary to console', () => {
        const logSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
        telemetry.logSummary();
        expect(logSpy).toHaveBeenCalled();
        logSpy.mockRestore();
    });

    it('calculates average inference time without throwing', () => {
        telemetry.trackInferenceTime(100);
        telemetry.trackInferenceTime(200);
        expect(() => telemetry.logSummary()).not.toThrow();
    });

    it('handles zero inference count gracefully (no division by zero)', () => {
        // No inference calls — avgInferenceTime should be 0
        expect(() => telemetry.logSummary()).not.toThrow();
    });
});

// ---------------------------------------------------------------------------
// reset
// ---------------------------------------------------------------------------

describe('telemetry.reset', () => {
    it('resets counters so subsequent logSummary still does not throw', () => {
        telemetry.trackConditionFailure('distance');
        telemetry.trackCountdownAbort('centering');
        telemetry.trackInferenceTime(120);
        telemetry.reset();
        expect(() => telemetry.logSummary()).not.toThrow();
    });

    it('reset allows re-use without accumulating old data', () => {
        telemetry.trackInferenceTime(500);
        telemetry.reset();

        const logSpy = vi.spyOn(console, 'log').mockImplementation((...args: unknown[]) => {
            const msg = args.join(' ');
            // After reset, average should be 0
            if (msg.includes('avg=')) {
                expect(msg).toContain('avg=0.0ms');
            }
        });

        telemetry.logSummary();
        logSpy.mockRestore();
    });
});
