/**
 * Tests for captureStages.ts — StageManager state transitions.
 *
 * StageManager relies on Date.now() for timing. We use vi.useFakeTimers()
 * to control time without sleep.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { StageManager, type StageRequirements, type CaptureStage } from '../lib/captureStages';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a StageRequirements object with sensible defaults. */
function makeRequirements(overrides: Partial<{
    irisDiameter: number;
    isRaised: boolean;
    displacement: number;
    centeringRatio: number;
    sharpness: number;
    brightness: number;
}> = {}): StageRequirements {
    return {
        distance: { irisDiameter: overrides.irisDiameter ?? 94 },   // ~8.7% of 1080 → in-range
        eyebrows: {
            isRaised: overrides.isRaised ?? false,
            displacement: overrides.displacement ?? 0,
        },
        angle: { beta: null, available: false },
        flashlight: { torchOn: false },
        finalChecks: {
            centeringRatio: overrides.centeringRatio ?? 0.1,
            sharpness: overrides.sharpness ?? 20,
            brightness: overrides.brightness ?? 140,
        },
    };
}

// ---------------------------------------------------------------------------
// StageManager tests
// ---------------------------------------------------------------------------

describe('StageManager', () => {
    let manager: StageManager;

    beforeEach(() => {
        vi.useFakeTimers();
        manager = new StageManager();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    // -----------------------------------------------------------------------
    // Initial state
    // -----------------------------------------------------------------------

    it('starts in distance stage', () => {
        expect(manager.getCurrentStage()).toBe('distance');
        expect(manager.isReady()).toBe(false);
    });

    it('getState returns stageNumber=1 and totalStages=4 initially', () => {
        const state = manager.update(makeRequirements());
        expect(state.stageNumber).toBe(1);
        expect(state.totalStages).toBe(4);
        expect(state.current).toBe('distance');
    });

    // -----------------------------------------------------------------------
    // Distance stage
    // -----------------------------------------------------------------------

    it('stays in distance stage when iris too small', () => {
        // diameter = 10 → way below min (0.08 * 1080 = 86.4)
        const req = makeRequirements({ irisDiameter: 10 });
        manager.update(req);
        expect(manager.getCurrentStage()).toBe('distance');
    });

    it('stays in distance stage when iris too large', () => {
        // diameter = 200 → above max (0.12 * 1080 = 129.6)
        const req = makeRequirements({ irisDiameter: 200 });
        manager.update(req);
        expect(manager.getCurrentStage()).toBe('distance');
    });

    it('advances from distance to eyebrows after 800ms in range', () => {
        // diameter in range: 86.4 – 129.6 px → use 108 (mid)
        const req = makeRequirements({ irisDiameter: 108 });

        // First update starts the stability timer
        manager.update(req);
        expect(manager.getCurrentStage()).toBe('distance');

        // Advance time by 900ms (> 800ms required)
        vi.advanceTimersByTime(900);
        manager.update(req);

        expect(manager.getCurrentStage()).toBe('eyebrows');
    });

    it('resets stability timer when iris leaves range', () => {
        const inRange = makeRequirements({ irisDiameter: 108 });
        const outRange = makeRequirements({ irisDiameter: 10 });

        manager.update(inRange);
        vi.advanceTimersByTime(400); // partial progress
        manager.update(outRange);   // out of range — timer reset
        vi.advanceTimersByTime(500); // not enough after reset
        manager.update(inRange);

        // Timer was reset so even with 400+500ms total, not enough
        expect(manager.getCurrentStage()).toBe('distance');
    });

    // -----------------------------------------------------------------------
    // Eyebrow stage
    // -----------------------------------------------------------------------

    it('does not advance from eyebrows stage without raised eyebrows', () => {
        // Get to eyebrows stage first
        const inRange = makeRequirements({ irisDiameter: 108 });
        manager.update(inRange);
        vi.advanceTimersByTime(900);
        manager.update(inRange);
        expect(manager.getCurrentStage()).toBe('eyebrows');

        // Now update without eyebrows raised
        const notRaised = makeRequirements({ irisDiameter: 108, isRaised: false });
        manager.update(notRaised);
        expect(manager.getCurrentStage()).toBe('eyebrows');
    });

    it('advances from eyebrows after 30 consecutive raised frames', () => {
        // Get to eyebrows
        const inRange = makeRequirements({ irisDiameter: 108 });
        manager.update(inRange);
        vi.advanceTimersByTime(900);
        manager.update(inRange);
        expect(manager.getCurrentStage()).toBe('eyebrows');

        // Raise eyebrows for 30 frames
        const raised = makeRequirements({ irisDiameter: 108, isRaised: true, displacement: -20 });
        for (let i = 0; i < 30; i++) {
            manager.update(raised);
        }

        expect(manager.getCurrentStage()).toBe('final_checks');
    });

    it('resets eyebrow frame count when eyebrows drop', () => {
        // Advance to eyebrow stage
        const inRange = makeRequirements({ irisDiameter: 108 });
        manager.update(inRange);
        vi.advanceTimersByTime(900);
        manager.update(inRange);

        const raised = makeRequirements({ irisDiameter: 108, isRaised: true });
        const notRaised = makeRequirements({ irisDiameter: 108, isRaised: false });

        // 15 raised, then drop
        for (let i = 0; i < 15; i++) manager.update(raised);
        manager.update(notRaised);

        // Should still be in eyebrows (not advanced)
        expect(manager.getCurrentStage()).toBe('eyebrows');
    });

    // -----------------------------------------------------------------------
    // Final checks stage
    // -----------------------------------------------------------------------

    it('advances from final_checks to ready after conditions met for 800ms', () => {
        // Fast-forward to final_checks
        const inRange = makeRequirements({ irisDiameter: 108 });
        manager.update(inRange);
        vi.advanceTimersByTime(900);
        manager.update(inRange);

        const raised = makeRequirements({ irisDiameter: 108, isRaised: true });
        for (let i = 0; i < 30; i++) manager.update(raised);
        expect(manager.getCurrentStage()).toBe('final_checks');

        // Good final checks
        const good = makeRequirements({
            irisDiameter: 108,
            centeringRatio: 0.1,  // < 0.3 → centered
            sharpness: 20,         // > 8 → focused
            brightness: 140,       // in 60-200 → well lit
        });

        manager.update(good); // starts stability timer
        vi.advanceTimersByTime(900);
        manager.update(good);

        expect(manager.getCurrentStage()).toBe('ready');
        expect(manager.isReady()).toBe(true);
    });

    it('does not advance final_checks when centering is bad', () => {
        // Navigate to final_checks
        const inRange = makeRequirements({ irisDiameter: 108 });
        manager.update(inRange);
        vi.advanceTimersByTime(900);
        manager.update(inRange);
        const raised = makeRequirements({ irisDiameter: 108, isRaised: true });
        for (let i = 0; i < 30; i++) manager.update(raised);

        // Bad centering
        const bad = makeRequirements({
            irisDiameter: 108,
            centeringRatio: 0.9, // > 0.3 → not centered
            sharpness: 20,
            brightness: 140,
        });
        manager.update(bad);
        vi.advanceTimersByTime(900);
        manager.update(bad);

        expect(manager.getCurrentStage()).toBe('final_checks');
    });

    // -----------------------------------------------------------------------
    // Reset
    // -----------------------------------------------------------------------

    it('reset returns to distance stage', () => {
        const inRange = makeRequirements({ irisDiameter: 108 });
        manager.update(inRange);
        vi.advanceTimersByTime(900);
        manager.update(inRange);
        expect(manager.getCurrentStage()).toBe('eyebrows');

        manager.reset();
        expect(manager.getCurrentStage()).toBe('distance');
        expect(manager.isReady()).toBe(false);
    });

    // -----------------------------------------------------------------------
    // returnToStage
    // -----------------------------------------------------------------------

    it('returnToStage allows jumping back to distance', () => {
        const inRange = makeRequirements({ irisDiameter: 108 });
        manager.update(inRange);
        vi.advanceTimersByTime(900);
        manager.update(inRange);
        expect(manager.getCurrentStage()).toBe('eyebrows');

        manager.returnToStage('distance');
        expect(manager.getCurrentStage()).toBe('distance');
    });

    // -----------------------------------------------------------------------
    // Message tests
    // -----------------------------------------------------------------------

    it('shows "Move Closer" message when iris too small', () => {
        const req = makeRequirements({ irisDiameter: 10 });
        const state = manager.update(req);
        expect(state.message).toBe('Move Closer');
    });

    it('shows "Move Back" message when iris too large', () => {
        const req = makeRequirements({ irisDiameter: 200 });
        const state = manager.update(req);
        expect(state.message).toBe('Move Back');
    });

    it('shows "Perfect Distance" when in range', () => {
        const req = makeRequirements({ irisDiameter: 108 });
        const state = manager.update(req);
        expect(state.message).toBe('Perfect Distance');
    });
});

// ---------------------------------------------------------------------------
// STAGE_ORDER constants
// ---------------------------------------------------------------------------

describe('CaptureStage type values', () => {
    it('valid stage values match expected literals', () => {
        const stages: CaptureStage[] = ['distance', 'eyebrows', 'final_checks', 'ready'];
        expect(stages).toHaveLength(4);
        expect(stages[0]).toBe('distance');
        expect(stages[3]).toBe('ready');
    });
});
