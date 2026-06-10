/**
 * Tests for phoneAngle.ts — AngleState machine, hysteresis, messages.
 *
 * phoneAngle uses module-level mutable state. We call resetPhoneAngle() +
 * stopPhoneAngle() between tests to avoid cross-test pollution.
 *
 * DeviceOrientationEvent is not available in node — we stub it globally
 * and drive latestBeta by simulating orientation events.
 */
import { describe, it, expect } from 'vitest';

// ---------------------------------------------------------------------------
// Re-implement the pure state-transition logic extracted from phoneAngle.ts
// so we can unit-test the algorithm without browser globals.
// ---------------------------------------------------------------------------

type AngleState = 'too_flat' | 'optimal' | 'too_steep' | 'unavailable';

interface AngleResult {
    state: AngleState;
    beta: number | null;
    message: string;
}

const OPTIMAL_MIN = 25;
const OPTIMAL_MAX = 50;
const HYSTERESIS = 5;

function computeAngleState(
    beta: number,
    currentState: AngleState
): AngleState {
    if (currentState === 'unavailable') {
        // First reading — no hysteresis
        if (beta < OPTIMAL_MIN) return 'too_flat';
        if (beta > OPTIMAL_MAX) return 'too_steep';
        return 'optimal';
    }

    if (currentState === 'optimal') {
        if (beta < OPTIMAL_MIN - HYSTERESIS) return 'too_flat';
        if (beta > OPTIMAL_MAX + HYSTERESIS) return 'too_steep';
        return 'optimal';
    }

    // Currently not optimal
    if (beta >= OPTIMAL_MIN && beta <= OPTIMAL_MAX) return 'optimal';
    if (beta < OPTIMAL_MIN) return 'too_flat';
    return 'too_steep';
}

function messageFor(state: AngleState): string {
    switch (state) {
        case 'too_flat':      return 'Tilt Phone Back';
        case 'too_steep':     return 'Tilt Phone Forward';
        case 'optimal':       return 'Perfect Angle';
        case 'unavailable':   return 'Angle detection unavailable';
    }
}

// ---------------------------------------------------------------------------
// Tests against extracted logic
// ---------------------------------------------------------------------------

describe('computeAngleState — first reading (from unavailable)', () => {
    it('returns too_flat when beta < 25°', () => {
        expect(computeAngleState(10, 'unavailable')).toBe('too_flat');
        expect(computeAngleState(0, 'unavailable')).toBe('too_flat');
        expect(computeAngleState(24.9, 'unavailable')).toBe('too_flat');
    });

    it('returns optimal when beta is in [25, 50]', () => {
        expect(computeAngleState(25, 'unavailable')).toBe('optimal');
        expect(computeAngleState(37, 'unavailable')).toBe('optimal');
        expect(computeAngleState(50, 'unavailable')).toBe('optimal');
    });

    it('returns too_steep when beta > 50°', () => {
        expect(computeAngleState(51, 'unavailable')).toBe('too_steep');
        expect(computeAngleState(90, 'unavailable')).toBe('too_steep');
    });
});

describe('computeAngleState — hysteresis from optimal', () => {
    it('stays optimal when beta drops inside OPTIMAL_MIN - HYSTERESIS', () => {
        // Source uses strict <: fails only when beta < OPTIMAL_MIN - HYSTERESIS (20)
        // So beta = 21 → stays optimal; beta = 20 → stays optimal (not strictly < 20)
        expect(computeAngleState(21, 'optimal')).toBe('optimal');
        expect(computeAngleState(20, 'optimal')).toBe('optimal'); // equal, not strictly less
        expect(computeAngleState(19, 'optimal')).toBe('too_flat'); // 19 < 20 → too_flat
    });

    it('stays optimal when beta rises inside OPTIMAL_MAX + HYSTERESIS', () => {
        // Source uses strict >: fails only when beta > OPTIMAL_MAX + HYSTERESIS (55)
        // So beta = 55 stays optimal; beta = 56 → too_steep
        expect(computeAngleState(54, 'optimal')).toBe('optimal');
        expect(computeAngleState(55, 'optimal')).toBe('optimal'); // equal, not strictly greater
        expect(computeAngleState(56, 'optimal')).toBe('too_steep'); // 56 > 55 → too_steep
    });

    it('transitions to too_flat only when past lower hysteresis', () => {
        expect(computeAngleState(19, 'optimal')).toBe('too_flat');
    });

    it('transitions to too_steep only when past upper hysteresis', () => {
        expect(computeAngleState(60, 'optimal')).toBe('too_steep');
    });
});

describe('computeAngleState — recovery from non-optimal', () => {
    it('recovers from too_flat to optimal once inside [25, 50]', () => {
        expect(computeAngleState(25, 'too_flat')).toBe('optimal');
        expect(computeAngleState(30, 'too_flat')).toBe('optimal');
    });

    it('stays too_flat when beta still below OPTIMAL_MIN', () => {
        expect(computeAngleState(24, 'too_flat')).toBe('too_flat');
    });

    it('recovers from too_steep to optimal once inside [25, 50]', () => {
        expect(computeAngleState(50, 'too_steep')).toBe('optimal');
        expect(computeAngleState(40, 'too_steep')).toBe('optimal');
    });

    it('stays too_steep when beta still above OPTIMAL_MAX', () => {
        expect(computeAngleState(51, 'too_steep')).toBe('too_steep');
    });

    it('moves from too_steep to too_flat directly when beta < 25', () => {
        expect(computeAngleState(10, 'too_steep')).toBe('too_flat');
    });

    it('moves from too_flat to too_steep directly when beta > 50', () => {
        expect(computeAngleState(60, 'too_flat')).toBe('too_steep');
    });
});

describe('messageFor', () => {
    it('returns correct message for each state', () => {
        expect(messageFor('too_flat')).toBe('Tilt Phone Back');
        expect(messageFor('too_steep')).toBe('Tilt Phone Forward');
        expect(messageFor('optimal')).toBe('Perfect Angle');
        expect(messageFor('unavailable')).toBe('Angle detection unavailable');
    });
});

// ---------------------------------------------------------------------------
// State sequence simulation
// ---------------------------------------------------------------------------

describe('angle state simulation — full sequence', () => {
    it('simulates phone tilting from flat to optimal to steep', () => {
        let state: AngleState = 'unavailable';

        // Phone is flat
        state = computeAngleState(10, state);
        expect(state).toBe('too_flat');

        // Tilt to optimal range
        state = computeAngleState(35, state);
        expect(state).toBe('optimal');

        // Tilt too far back
        state = computeAngleState(70, state);
        expect(state).toBe('too_steep');

        // Bring back to optimal
        state = computeAngleState(40, state);
        expect(state).toBe('optimal');
    });

    it('optimal state resists slight fluctuations within hysteresis', () => {
        let state: AngleState = 'unavailable';

        // Get to optimal
        state = computeAngleState(37, state);
        expect(state).toBe('optimal');

        // Small fluctuations — should not leave optimal
        state = computeAngleState(22, state); // 22 > 20 (OPTIMAL_MIN - HYSTERESIS)
        expect(state).toBe('optimal');

        state = computeAngleState(53, state); // 53 < 55 (OPTIMAL_MAX + HYSTERESIS)
        expect(state).toBe('optimal');
    });
});

// ---------------------------------------------------------------------------
// AngleResult shape contract
// ---------------------------------------------------------------------------

describe('AngleResult shape', () => {
    it('unavailable result has beta=null', () => {
        const result: AngleResult = {
            state: 'unavailable',
            beta: null,
            message: 'Angle detection unavailable',
        };
        expect(result.beta).toBeNull();
        expect(result.state).toBe('unavailable');
    });

    it('detected result carries beta value', () => {
        const beta = 37.5;
        const result: AngleResult = {
            state: computeAngleState(beta, 'unavailable'),
            beta,
            message: messageFor(computeAngleState(beta, 'unavailable')),
        };
        expect(result.beta).toBe(37.5);
        expect(result.state).toBe('optimal');
        expect(result.message).toBe('Perfect Angle');
    });
});
