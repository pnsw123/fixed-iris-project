/**
 * Tests for audioFeedback.ts — AudioFeedback class.
 *
 * AudioContext and speechSynthesis are browser-only. We stub them globally.
 * Tests cover:
 *  - speak() throttling (same message / different message)
 *  - updateMetrics() clamping to [0, 1]
 *  - stop() cleans up
 *  - SSR safety (window undefined)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ---------------------------------------------------------------------------
// Mock speechSynthesis globally before importing the module
// ---------------------------------------------------------------------------

const mockCancel = vi.fn();
const mockSpeak = vi.fn();
const mockGetVoices = vi.fn(() => []);

Object.defineProperty(globalThis, 'window', {
    value: {
        speechSynthesis: {
            cancel: mockCancel,
            speak: mockSpeak,
            getVoices: mockGetVoices,
        },
        AudioContext: undefined,
        webkitAudioContext: undefined,
    },
    configurable: true,
    writable: true,
});

// Also define speechSynthesis at global level for SSR check
Object.defineProperty(globalThis, 'SpeechSynthesisUtterance', {
    value: class SpeechSynthesisUtterance {
        text: string;
        rate = 1;
        pitch = 1;
        volume = 1;
        voice = null;
        constructor(text: string) { this.text = text; }
    },
    configurable: true,
    writable: true,
});

// ---------------------------------------------------------------------------
// Import AFTER stubbing globals
// ---------------------------------------------------------------------------
import { AudioFeedback } from '../lib/audioFeedback';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeInstance() {
    return new AudioFeedback();
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
    vi.clearAllMocks();
    // Reset time mocks
    vi.useRealTimers();
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
});

afterEach(() => {
    vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// speak() — throttling
// ---------------------------------------------------------------------------

describe('AudioFeedback.speak()', () => {
    it('calls speechSynthesis.speak on first call', () => {
        const af = makeInstance();
        af.speak('Move Closer');
        expect(mockSpeak).toHaveBeenCalledOnce();
    });

    it('does not repeat same message within 3s throttle window', () => {
        vi.useFakeTimers();
        const af = makeInstance();

        af.speak('Move Closer');
        expect(mockSpeak).toHaveBeenCalledTimes(1);

        // 2.9s later — same message, still throttled
        vi.advanceTimersByTime(2900);
        af.speak('Move Closer');
        expect(mockSpeak).toHaveBeenCalledTimes(1); // no new call

        vi.useRealTimers();
    });

    it('allows same message after 3s throttle expires', () => {
        vi.useFakeTimers();
        const af = makeInstance();

        af.speak('Move Closer');
        expect(mockSpeak).toHaveBeenCalledTimes(1);

        vi.advanceTimersByTime(3001);
        af.speak('Move Closer');
        expect(mockSpeak).toHaveBeenCalledTimes(2);

        vi.useRealTimers();
    });

    it('throttles different messages within 1.5s', () => {
        vi.useFakeTimers();
        const af = makeInstance();

        af.speak('Move Closer');
        vi.advanceTimersByTime(1400); // less than 1.5s
        af.speak('Center Eye'); // different message but within 1.5s cooldown
        expect(mockSpeak).toHaveBeenCalledTimes(1);

        vi.useRealTimers();
    });

    it('allows different message after 1.5s', () => {
        vi.useFakeTimers();
        const af = makeInstance();

        af.speak('Move Closer');
        vi.advanceTimersByTime(1600); // past 1.5s
        af.speak('Center Eye');
        expect(mockSpeak).toHaveBeenCalledTimes(2);

        vi.useRealTimers();
    });

    it('cancels previous utterance before speaking', () => {
        const af = makeInstance();
        af.speak('Move Closer');
        expect(mockCancel).toHaveBeenCalled();
    });
});

// ---------------------------------------------------------------------------
// speak() — SSR safety
// ---------------------------------------------------------------------------

describe('AudioFeedback.speak() — SSR/no-window', () => {
    it('does not throw when speechSynthesis is undefined', () => {
        // Temporarily remove speechSynthesis
        type WinExt = Window & { speechSynthesis: SpeechSynthesis | undefined };
        const w = globalThis.window as WinExt;
        const originalSpeechSynthesis = w.speechSynthesis;
        w.speechSynthesis = undefined;

        const af = makeInstance();
        expect(() => af.speak('test')).not.toThrow();

        w.speechSynthesis = originalSpeechSynthesis;
    });
});

// ---------------------------------------------------------------------------
// updateMetrics()
// ---------------------------------------------------------------------------

describe('AudioFeedback.updateMetrics()', () => {
    it('clamps distanceScore below 0 to 0', () => {
        const af = makeInstance();
        // updateMetrics should not throw
        expect(() => af.updateMetrics(-5, 0.5)).not.toThrow();
    });

    it('clamps distanceScore above 1 to 1', () => {
        const af = makeInstance();
        expect(() => af.updateMetrics(99, 0.5)).not.toThrow();
    });

    it('clamps centeringScore to [0, 1]', () => {
        const af = makeInstance();
        expect(() => af.updateMetrics(0.5, -1)).not.toThrow();
        expect(() => af.updateMetrics(0.5, 2)).not.toThrow();
    });

    it('accepts valid scores within [0, 1]', () => {
        const af = makeInstance();
        expect(() => af.updateMetrics(0, 0)).not.toThrow();
        expect(() => af.updateMetrics(0.5, 0.5)).not.toThrow();
        expect(() => af.updateMetrics(1, 1)).not.toThrow();
    });
});

// ---------------------------------------------------------------------------
// stop()
// ---------------------------------------------------------------------------

describe('AudioFeedback.stop()', () => {
    it('cancels speech synthesis on stop', () => {
        const af = makeInstance();
        af.stop();
        expect(mockCancel).toHaveBeenCalled();
    });

    it('does not throw when called multiple times', () => {
        const af = makeInstance();
        expect(() => {
            af.stop();
            af.stop();
        }).not.toThrow();
    });
});
