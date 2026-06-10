/**
 * Tests for captureConditions.ts
 *
 * Tests: CONDITION_THRESHOLDS constants, STABILITY_CONFIG, CONDITION_PRIORITY,
 * GUIDANCE_MESSAGES, and the applyHysteresis pure function.
 */
import { describe, it, expect } from 'vitest';
import {
    CONDITION_THRESHOLDS,
    STABILITY_CONFIG,
    CONDITION_PRIORITY,
    GUIDANCE_MESSAGES,
    applyHysteresis,
    type ConditionState,
} from '../lib/captureConditions';

// ---------------------------------------------------------------------------
// applyHysteresis — core pure function
// ---------------------------------------------------------------------------

describe('applyHysteresis', () => {
    const min = 200;
    const max = 280;
    const hysteresis = 20;

    // ---- currently failing ------------------------------------------------

    it('returns pass when value enters [min, max] while failing', () => {
        expect(applyHysteresis(200, min, max, hysteresis, 'fail')).toBe('pass');
        expect(applyHysteresis(240, min, max, hysteresis, 'fail')).toBe('pass');
        expect(applyHysteresis(280, min, max, hysteresis, 'fail')).toBe('pass');
    });

    it('stays fail when value is still below min while failing', () => {
        expect(applyHysteresis(199, min, max, hysteresis, 'fail')).toBe('fail');
        expect(applyHysteresis(50, min, max, hysteresis, 'fail')).toBe('fail');
    });

    it('stays fail when value is still above max while failing', () => {
        expect(applyHysteresis(281, min, max, hysteresis, 'fail')).toBe('fail');
        expect(applyHysteresis(500, min, max, hysteresis, 'fail')).toBe('fail');
    });

    // ---- currently passing ------------------------------------------------

    it('stays pass while value stays inside [min - hysteresis, max + hysteresis]', () => {
        // Passes as long as value >= min - hysteresis (180) and <= max + hysteresis (300)
        expect(applyHysteresis(180, min, max, hysteresis, 'pass')).toBe('pass'); // at lower bound
        expect(applyHysteresis(300, min, max, hysteresis, 'pass')).toBe('pass'); // at upper bound
        expect(applyHysteresis(240, min, max, hysteresis, 'pass')).toBe('pass'); // middle
    });

    it('fails when value drops below min - hysteresis while passing', () => {
        expect(applyHysteresis(179, min, max, hysteresis, 'pass')).toBe('fail');
        expect(applyHysteresis(0, min, max, hysteresis, 'pass')).toBe('fail');
    });

    it('fails when value exceeds max + hysteresis while passing', () => {
        expect(applyHysteresis(301, min, max, hysteresis, 'pass')).toBe('fail');
        expect(applyHysteresis(1000, min, max, hysteresis, 'pass')).toBe('fail');
    });

    // ---- unknown state ----------------------------------------------------

    it('treats unknown state like fail (does not pass until inside [min, max])', () => {
        expect(applyHysteresis(240, min, max, hysteresis, 'unknown')).toBe('pass');
        expect(applyHysteresis(199, min, max, hysteresis, 'unknown')).toBe('fail');
    });
});

// ---------------------------------------------------------------------------
// applyHysteresis — zero hysteresis (no buffer)
// ---------------------------------------------------------------------------

describe('applyHysteresis with zero hysteresis', () => {
    it('fails immediately on leaving range when hysteresis=0', () => {
        expect(applyHysteresis(99, 100, 200, 0, 'pass')).toBe('fail');
        expect(applyHysteresis(201, 100, 200, 0, 'pass')).toBe('fail');
    });

    it('passes on entering range when hysteresis=0', () => {
        expect(applyHysteresis(100, 100, 200, 0, 'fail')).toBe('pass');
        expect(applyHysteresis(200, 100, 200, 0, 'fail')).toBe('pass');
    });
});

// ---------------------------------------------------------------------------
// CONDITION_THRESHOLDS — constant values
// ---------------------------------------------------------------------------

describe('CONDITION_THRESHOLDS constants', () => {
    it('distance.min < distance.max', () => {
        expect(CONDITION_THRESHOLDS.distance.min).toBeLessThan(CONDITION_THRESHOLDS.distance.max);
    });

    it('distance has positive hysteresis', () => {
        expect(CONDITION_THRESHOLDS.distance.hysteresis).toBeGreaterThan(0);
    });

    it('centering.maxDeviationPercent is between 0 and 1', () => {
        expect(CONDITION_THRESHOLDS.centering.maxDeviationPercent).toBeGreaterThan(0);
        expect(CONDITION_THRESHOLDS.centering.maxDeviationPercent).toBeLessThan(1);
    });

    it('focus thresholds are ordered: blurry < acceptable < sharp', () => {
        expect(CONDITION_THRESHOLDS.focus.blurryThreshold)
            .toBeLessThan(CONDITION_THRESHOLDS.focus.acceptableThreshold);
        expect(CONDITION_THRESHOLDS.focus.acceptableThreshold)
            .toBeLessThan(CONDITION_THRESHOLDS.focus.sharpThreshold);
    });

    it('lighting ideal range is inside min/max range', () => {
        expect(CONDITION_THRESHOLDS.lighting.perfectMin)
            .toBeGreaterThanOrEqual(CONDITION_THRESHOLDS.lighting.minBrightness);
        expect(CONDITION_THRESHOLDS.lighting.perfectMax)
            .toBeLessThanOrEqual(CONDITION_THRESHOLDS.lighting.maxBrightness);
    });

    it('phoneAngle.minAngle < phoneAngle.optimalAngle < phoneAngle.maxAngle', () => {
        expect(CONDITION_THRESHOLDS.phoneAngle.minAngle)
            .toBeLessThan(CONDITION_THRESHOLDS.phoneAngle.optimalAngle);
        expect(CONDITION_THRESHOLDS.phoneAngle.optimalAngle)
            .toBeLessThan(CONDITION_THRESHOLDS.phoneAngle.maxAngle);
    });
});

// ---------------------------------------------------------------------------
// STABILITY_CONFIG
// ---------------------------------------------------------------------------

describe('STABILITY_CONFIG', () => {
    it('stabilityWindowMs is positive', () => {
        expect(STABILITY_CONFIG.stabilityWindowMs).toBeGreaterThan(0);
    });

    it('countdownDurationMs is positive', () => {
        expect(STABILITY_CONFIG.countdownDurationMs).toBeGreaterThan(0);
    });

    it('messageCooldownMs is positive', () => {
        expect(STABILITY_CONFIG.messageCooldownMs).toBeGreaterThan(0);
    });
});

// ---------------------------------------------------------------------------
// CONDITION_PRIORITY
// ---------------------------------------------------------------------------

describe('CONDITION_PRIORITY', () => {
    it('has 7 conditions', () => {
        expect(CONDITION_PRIORITY).toHaveLength(7);
    });

    it('eyebrowsRaised is highest priority (index 0)', () => {
        expect(CONDITION_PRIORITY[0]).toBe('eyebrowsRaised');
    });

    it('faceDetected is lowest priority (last)', () => {
        expect(CONDITION_PRIORITY[CONDITION_PRIORITY.length - 1]).toBe('faceDetected');
    });

    it('contains all expected condition keys', () => {
        const expected = [
            'eyebrowsRaised',
            'phoneAngleOk',
            'distanceOk',
            'eyeCentered',
            'lightingAdequate',
            'focusSharp',
            'faceDetected',
        ] as const;
        expected.forEach(key => {
            expect(CONDITION_PRIORITY).toContain(key);
        });
    });
});

// ---------------------------------------------------------------------------
// GUIDANCE_MESSAGES
// ---------------------------------------------------------------------------

describe('GUIDANCE_MESSAGES', () => {
    it('has message for eyebrowsRaised', () => {
        expect(typeof GUIDANCE_MESSAGES.eyebrowsRaised).toBe('string');
        expect(GUIDANCE_MESSAGES.eyebrowsRaised.length).toBeGreaterThan(0);
    });

    it('distanceOk has tooFar, tooClose, perfect sub-messages', () => {
        expect(GUIDANCE_MESSAGES.distanceOk.tooFar).toBeTruthy();
        expect(GUIDANCE_MESSAGES.distanceOk.tooClose).toBeTruthy();
        expect(GUIDANCE_MESSAGES.distanceOk.perfect).toBeTruthy();
    });

    it('lightingAdequate has dark, tooBright, perfect sub-messages', () => {
        expect(GUIDANCE_MESSAGES.lightingAdequate.dark).toBeTruthy();
        expect(GUIDANCE_MESSAGES.lightingAdequate.tooBright).toBeTruthy();
        expect(GUIDANCE_MESSAGES.lightingAdequate.perfect).toBeTruthy();
    });

    it('allPass message is non-empty', () => {
        expect(GUIDANCE_MESSAGES.allPass).toBeTruthy();
    });
});

// ---------------------------------------------------------------------------
// ConditionState type contract
// ---------------------------------------------------------------------------

describe('ConditionState type', () => {
    it('valid states are pass, fail, unknown', () => {
        const states: ConditionState[] = ['pass', 'fail', 'unknown'];
        expect(states).toHaveLength(3);
    });
});
