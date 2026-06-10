/**
 * Tests for cameraCheck.ts
 *
 * checkCameraResolution() requires navigator.mediaDevices (browser-only).
 * We mock it to test:
 *  1. The megapixel calculation logic (pure math)
 *  2. The meetsRequirement threshold (≥ 12MP)
 *  3. The error fallback path
 *
 * The pure MIN_MEGAPIXELS constant is tested directly.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { checkCameraResolution, MIN_MEGAPIXELS } from '../lib/cameraCheck';

// ---------------------------------------------------------------------------
// Helpers — build mock track objects
// ---------------------------------------------------------------------------

function makeMockTrack(options: {
    widthMax?: number | undefined;
    heightMax?: number | undefined;
    settingsWidth?: number | undefined;
    settingsHeight?: number | undefined;
    label?: string | undefined;
    hasCapabilities?: boolean | undefined;
}) {
    const {
        widthMax,
        heightMax,
        settingsWidth = 1920,
        settingsHeight = 1080,
        label = 'Front Camera',
        hasCapabilities = true,
    } = options;

    return {
        label,
        getSettings: () => ({ width: settingsWidth, height: settingsHeight }),
        getCapabilities: hasCapabilities
            ? () => ({
                  width: widthMax !== undefined ? { max: widthMax } : undefined,
                  height: heightMax !== undefined ? { max: heightMax } : undefined,
              })
            : undefined,
        stop: vi.fn(),
    };
}

function makeMockStream(track: ReturnType<typeof makeMockTrack>) {
    return {
        getVideoTracks: () => [track],
        getTracks: () => [track],
    };
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

let consoleLogSpy: ReturnType<typeof vi.spyOn>;
let consoleErrorSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
    consoleLogSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
    vi.restoreAllMocks();
    // @ts-expect-error restore global
    delete globalThis.navigator;
});

// ---------------------------------------------------------------------------
// Pure constant tests (no mocking needed)
// ---------------------------------------------------------------------------

describe('MIN_MEGAPIXELS constant', () => {
    it('is 12', () => {
        expect(MIN_MEGAPIXELS).toBe(12);
    });
});

// ---------------------------------------------------------------------------
// Megapixel math (pure logic, replicated from source)
// ---------------------------------------------------------------------------

describe('megapixel calculation logic', () => {
    it('4032x3024 ≈ 12.19MP meets requirement', () => {
        const totalPixels = 4032 * 3024;
        const megapixels = totalPixels / 1_000_000;
        const meetsRequirement = totalPixels >= 12 * 1_000_000;
        expect(megapixels).toBeCloseTo(12.19, 0);
        expect(meetsRequirement).toBe(true);
    });

    it('1920x1080 ≈ 2.07MP does not meet requirement', () => {
        const totalPixels = 1920 * 1080;
        const meetsRequirement = totalPixels >= 12 * 1_000_000;
        expect(meetsRequirement).toBe(false);
    });

    it('4000x3000 = 12MP exactly meets requirement', () => {
        const totalPixels = 4000 * 3000;
        const meetsRequirement = totalPixels >= 12 * 1_000_000;
        expect(meetsRequirement).toBe(true);
    });

    it('3999x3000 < 12MP does not meet requirement', () => {
        const totalPixels = 3999 * 3000;
        const meetsRequirement = totalPixels >= 12 * 1_000_000;
        expect(meetsRequirement).toBe(false);
    });
});

// ---------------------------------------------------------------------------
// checkCameraResolution with mocked navigator
// ---------------------------------------------------------------------------

describe('checkCameraResolution — success paths', () => {
    it('returns meetsRequirement=true for 12MP camera via capabilities', async () => {
        const track = makeMockTrack({ widthMax: 4032, heightMax: 3024 });
        const stream = makeMockStream(track);

        Object.defineProperty(globalThis, 'navigator', {
            value: {
                mediaDevices: {
                    getUserMedia: vi.fn().mockResolvedValue(stream),
                },
            },
            configurable: true,
            writable: true,
        });

        const result = await checkCameraResolution();

        expect(result.meetsRequirement).toBe(true);
        expect(result.megapixels).toBeGreaterThanOrEqual(12);
        expect(result.maxWidth).toBe(4032);
        expect(result.maxHeight).toBe(3024);
        expect(result.deviceLabel).toBe('Front Camera');
        expect(track.stop).toHaveBeenCalled();
    });

    it('returns meetsRequirement=false for 2MP camera via capabilities', async () => {
        const track = makeMockTrack({ widthMax: 1920, heightMax: 1080 });
        const stream = makeMockStream(track);

        Object.defineProperty(globalThis, 'navigator', {
            value: {
                mediaDevices: {
                    getUserMedia: vi.fn().mockResolvedValue(stream),
                },
            },
            configurable: true,
            writable: true,
        });

        const result = await checkCameraResolution();

        expect(result.meetsRequirement).toBe(false);
        expect(result.megapixels).toBeLessThan(12);
    });

    it('falls back to settings when getCapabilities returns empty object', async () => {
        const track = makeMockTrack({
            hasCapabilities: true,
            widthMax: undefined,
            heightMax: undefined,
            settingsWidth: 4032,
            settingsHeight: 3024,
        });
        const stream = makeMockStream(track);

        Object.defineProperty(globalThis, 'navigator', {
            value: {
                mediaDevices: {
                    getUserMedia: vi.fn().mockResolvedValue(stream),
                },
            },
            configurable: true,
            writable: true,
        });

        const result = await checkCameraResolution();

        // Falls back to settings.width/height
        expect(result.maxWidth).toBe(4032);
        expect(result.maxHeight).toBe(3024);
    });

    it('falls back to settings when getCapabilities is undefined', async () => {
        const track = makeMockTrack({
            hasCapabilities: false,
            settingsWidth: 1920,
            settingsHeight: 1080,
        });
        const stream = makeMockStream(track);

        Object.defineProperty(globalThis, 'navigator', {
            value: {
                mediaDevices: {
                    getUserMedia: vi.fn().mockResolvedValue(stream),
                },
            },
            configurable: true,
            writable: true,
        });

        const result = await checkCameraResolution();

        expect(result.maxWidth).toBe(1920);
        expect(result.maxHeight).toBe(1080);
    });
});

describe('checkCameraResolution — error paths', () => {
    it('returns zero megapixels and meetsRequirement=false on permission denied', async () => {
        Object.defineProperty(globalThis, 'navigator', {
            value: {
                mediaDevices: {
                    getUserMedia: vi.fn().mockRejectedValue(new DOMException('Permission denied', 'NotAllowedError')),
                },
            },
            configurable: true,
            writable: true,
        });

        const result = await checkCameraResolution();

        expect(result.meetsRequirement).toBe(false);
        expect(result.megapixels).toBe(0);
        expect(result.maxWidth).toBe(0);
        expect(result.maxHeight).toBe(0);
        expect(result.deviceLabel).toBe('Camera Access Denied');
    });

    it('returns zero megapixels on generic error', async () => {
        Object.defineProperty(globalThis, 'navigator', {
            value: {
                mediaDevices: {
                    getUserMedia: vi.fn().mockRejectedValue(new Error('Hardware failure')),
                },
            },
            configurable: true,
            writable: true,
        });

        const result = await checkCameraResolution();

        expect(result.meetsRequirement).toBe(false);
        expect(result.maxWidth).toBe(0);
        expect(result.maxHeight).toBe(0);
    });
});
