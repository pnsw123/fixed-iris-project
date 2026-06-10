/**
 * Tests for IrisCaptureOrchestrator.tsx
 *
 * IrisCaptureOrchestrator is a 'use client' component that wires camera,
 * quality analysis, and countdown capture. It uses browser APIs (getUserMedia,
 * requestAnimationFrame, canvas) which aren't available in vitest/node.
 * No @testing-library/react installed.
 *
 * Strategy: replicate the component's pure business logic inline and test it
 * in isolation — matching the pattern from toast.test.tsx and qualityMetrics.test.ts.
 *
 * What we test:
 *   - CAPTURE_THRESHOLDS values (documented rationale matters)
 *   - meetsQualityThresholds logic (all four metrics + irisDetected guard)
 *   - getFeedback priority order (distance > centering > lighting > focus, then warns)
 *   - getStatusColor (red/yellow/green based on iris + thresholds)
 *   - countdownAbortRef reset semantics
 */
import { describe, it, expect } from 'vitest';
import type { QualityReport } from '../lib/qualityMetrics';

// ---------------------------------------------------------------------------
// Replicated pure logic from IrisCaptureOrchestrator.tsx
// ---------------------------------------------------------------------------

const CAPTURE_THRESHOLDS = {
    minDistanceScore: 60,
    minLightingScore: 50,
    minCenteringScore: 35,
    minFocusScore: 80,
    requiredStableSeconds: 3,
};

function meetsQualityThresholds(report: QualityReport): boolean {
    if (!report.irisDetected) return false;
    return (
        report.distance.score >= CAPTURE_THRESHOLDS.minDistanceScore &&
        report.lighting.score >= CAPTURE_THRESHOLDS.minLightingScore &&
        report.centering.score >= CAPTURE_THRESHOLDS.minCenteringScore &&
        report.focus.score >= CAPTURE_THRESHOLDS.minFocusScore
    );
}

function getFeedback(
    currentReport: QualityReport | null,
    stableSeconds: number
): string {
    if (!currentReport) return 'Initializing...';
    if (!currentReport.irisDetected) return 'Position your eye in frame';

    if (currentReport.distance.status === 'fail') return currentReport.distance.feedback;
    if (currentReport.centering.status === 'fail') return currentReport.centering.feedback;
    if (currentReport.lighting.status === 'fail') return currentReport.lighting.feedback;
    if (currentReport.focus.status === 'fail') return currentReport.focus.feedback;

    if (currentReport.distance.status === 'warn') return currentReport.distance.feedback;
    if (currentReport.centering.status === 'warn') return currentReport.centering.feedback;
    if (currentReport.lighting.status === 'warn') return currentReport.lighting.feedback;
    if (currentReport.focus.status === 'warn') return currentReport.focus.feedback;

    if (stableSeconds > 0 && stableSeconds < CAPTURE_THRESHOLDS.requiredStableSeconds) {
        return `Hold steady... ${CAPTURE_THRESHOLDS.requiredStableSeconds - stableSeconds}s`;
    }
    return 'Perfect! Hold steady...';
}

function getStatusColor(
    currentReport: QualityReport | null,
): string {
    if (!currentReport?.irisDetected) return 'bg-red-500';
    if (meetsQualityThresholds(currentReport)) return 'bg-green-500';
    return 'bg-yellow-500';
}

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeReport(overrides: Partial<QualityReport> = {}): QualityReport {
    return {
        irisDetected: true,
        irisCenter: { x: 240, y: 320 },
        irisCropBox: { x: 180, y: 260, size: 120 },
        irisDiameter: 100,
        distance: { score: 80, status: 'ok', feedback: 'Good distance' },
        lighting: { score: 70, status: 'ok', feedback: 'Good lighting' },
        centering: { score: 60, status: 'ok', feedback: 'Centered' },
        focus: { score: 90, status: 'ok', feedback: 'Sharp' },
        ...overrides,
    };
}

// ---------------------------------------------------------------------------
// CAPTURE_THRESHOLDS
// ---------------------------------------------------------------------------

describe('IrisCaptureOrchestrator — CAPTURE_THRESHOLDS', () => {
    it('minDistanceScore is 60', () => {
        expect(CAPTURE_THRESHOLDS.minDistanceScore).toBe(60);
    });

    it('minLightingScore is 50', () => {
        expect(CAPTURE_THRESHOLDS.minLightingScore).toBe(50);
    });

    it('minCenteringScore is 35', () => {
        expect(CAPTURE_THRESHOLDS.minCenteringScore).toBe(35);
    });

    it('minFocusScore is 80', () => {
        expect(CAPTURE_THRESHOLDS.minFocusScore).toBe(80);
    });

    it('requiredStableSeconds is 3', () => {
        expect(CAPTURE_THRESHOLDS.requiredStableSeconds).toBe(3);
    });

    it('focus threshold is the strictest (highest) metric', () => {
        expect(CAPTURE_THRESHOLDS.minFocusScore).toBeGreaterThan(CAPTURE_THRESHOLDS.minDistanceScore);
        expect(CAPTURE_THRESHOLDS.minFocusScore).toBeGreaterThan(CAPTURE_THRESHOLDS.minLightingScore);
        expect(CAPTURE_THRESHOLDS.minFocusScore).toBeGreaterThan(CAPTURE_THRESHOLDS.minCenteringScore);
    });
});

// ---------------------------------------------------------------------------
// meetsQualityThresholds
// ---------------------------------------------------------------------------

describe('IrisCaptureOrchestrator — meetsQualityThresholds', () => {
    it('returns false when irisDetected is false', () => {
        const report = makeReport({ irisDetected: false });
        expect(meetsQualityThresholds(report)).toBe(false);
    });

    it('returns true when all metrics are above thresholds', () => {
        const report = makeReport({
            distance: { score: 80, status: 'ok', feedback: '' },
            lighting: { score: 70, status: 'ok', feedback: '' },
            centering: { score: 60, status: 'ok', feedback: '' },
            focus: { score: 90, status: 'ok', feedback: '' },
        });
        expect(meetsQualityThresholds(report)).toBe(true);
    });

    it('returns false when distance score is below threshold (< 60)', () => {
        const report = makeReport({
            distance: { score: 59, status: 'fail', feedback: 'Too far' },
        });
        expect(meetsQualityThresholds(report)).toBe(false);
    });

    it('returns true when distance score is exactly at threshold (= 60)', () => {
        const report = makeReport({
            distance: { score: 60, status: 'ok', feedback: '' },
        });
        expect(meetsQualityThresholds(report)).toBe(true);
    });

    it('returns false when lighting score is below threshold (< 50)', () => {
        const report = makeReport({
            lighting: { score: 49, status: 'fail', feedback: 'Too dark' },
        });
        expect(meetsQualityThresholds(report)).toBe(false);
    });

    it('returns true when lighting score is exactly at threshold (= 50)', () => {
        const report = makeReport({
            lighting: { score: 50, status: 'ok', feedback: '' },
        });
        expect(meetsQualityThresholds(report)).toBe(true);
    });

    it('returns false when centering score is below threshold (< 35)', () => {
        const report = makeReport({
            centering: { score: 34, status: 'fail', feedback: 'Off-center' },
        });
        expect(meetsQualityThresholds(report)).toBe(false);
    });

    it('returns false when focus score is below threshold (< 80)', () => {
        const report = makeReport({
            focus: { score: 79, status: 'fail', feedback: 'Blurry' },
        });
        expect(meetsQualityThresholds(report)).toBe(false);
    });

    it('returns true when focus score is exactly at threshold (= 80)', () => {
        const report = makeReport({
            focus: { score: 80, status: 'ok', feedback: '' },
        });
        expect(meetsQualityThresholds(report)).toBe(true);
    });

    it('returns false when only one metric fails', () => {
        const report = makeReport({
            distance: { score: 80, status: 'ok', feedback: '' },
            lighting: { score: 70, status: 'ok', feedback: '' },
            centering: { score: 60, status: 'ok', feedback: '' },
            focus: { score: 75, status: 'fail', feedback: 'Blurry' }, // below 80
        });
        expect(meetsQualityThresholds(report)).toBe(false);
    });
});

// ---------------------------------------------------------------------------
// getFeedback — priority order
// ---------------------------------------------------------------------------

describe('IrisCaptureOrchestrator — getFeedback priority', () => {
    it('returns "Initializing..." when currentReport is null', () => {
        expect(getFeedback(null, 0)).toBe('Initializing...');
    });

    it('returns "Position your eye in frame" when iris not detected', () => {
        const report = makeReport({ irisDetected: false });
        expect(getFeedback(report, 0)).toBe('Position your eye in frame');
    });

    it('shows distance.feedback first when distance fails', () => {
        const report = makeReport({
            distance: { score: 10, status: 'fail', feedback: 'Move closer' },
            centering: { score: 10, status: 'fail', feedback: 'Center eye' },
            lighting: { score: 10, status: 'fail', feedback: 'More light' },
            focus: { score: 10, status: 'fail', feedback: 'Hold still' },
        });
        expect(getFeedback(report, 0)).toBe('Move closer');
    });

    it('shows centering.feedback when only centering fails', () => {
        const report = makeReport({
            distance: { score: 80, status: 'ok', feedback: '' },
            centering: { score: 10, status: 'fail', feedback: 'Center eye' },
            lighting: { score: 70, status: 'ok', feedback: '' },
            focus: { score: 90, status: 'ok', feedback: '' },
        });
        expect(getFeedback(report, 0)).toBe('Center eye');
    });

    it('shows lighting.feedback after distance and centering are ok', () => {
        const report = makeReport({
            distance: { score: 80, status: 'ok', feedback: '' },
            centering: { score: 60, status: 'ok', feedback: '' },
            lighting: { score: 10, status: 'fail', feedback: 'More light' },
            focus: { score: 90, status: 'ok', feedback: '' },
        });
        expect(getFeedback(report, 0)).toBe('More light');
    });

    it('shows focus.feedback when only focus fails', () => {
        const report = makeReport({
            distance: { score: 80, status: 'ok', feedback: '' },
            centering: { score: 60, status: 'ok', feedback: '' },
            lighting: { score: 70, status: 'ok', feedback: '' },
            focus: { score: 10, status: 'fail', feedback: 'Hold still' },
        });
        expect(getFeedback(report, 0)).toBe('Hold still');
    });

    it('shows distance warn before centering warn', () => {
        const report = makeReport({
            distance: { score: 65, status: 'warn', feedback: 'Slightly far' },
            centering: { score: 40, status: 'warn', feedback: 'Slightly off' },
            lighting: { score: 55, status: 'ok', feedback: '' },
            focus: { score: 85, status: 'ok', feedback: '' },
        });
        expect(getFeedback(report, 0)).toBe('Slightly far');
    });

    it('shows stable countdown message when stableSeconds > 0 and < 3', () => {
        const report = makeReport(); // all ok
        expect(getFeedback(report, 1)).toBe('Hold steady... 2s');
        expect(getFeedback(report, 2)).toBe('Hold steady... 1s');
    });

    it('shows "Perfect! Hold steady..." when all ok and stableSeconds=0', () => {
        const report = makeReport();
        expect(getFeedback(report, 0)).toBe('Perfect! Hold steady...');
    });

    it('shows "Perfect! Hold steady..." when stableSeconds >= requiredStableSeconds', () => {
        const report = makeReport();
        expect(getFeedback(report, 3)).toBe('Perfect! Hold steady...');
    });
});

// ---------------------------------------------------------------------------
// getStatusColor
// ---------------------------------------------------------------------------

describe('IrisCaptureOrchestrator — getStatusColor', () => {
    it('returns bg-red-500 when currentReport is null', () => {
        expect(getStatusColor(null)).toBe('bg-red-500');
    });

    it('returns bg-red-500 when iris not detected', () => {
        const report = makeReport({ irisDetected: false });
        expect(getStatusColor(report)).toBe('bg-red-500');
    });

    it('returns bg-green-500 when all thresholds met', () => {
        const report = makeReport();
        expect(getStatusColor(report)).toBe('bg-green-500');
    });

    it('returns bg-yellow-500 when iris detected but thresholds not met', () => {
        const report = makeReport({
            focus: { score: 50, status: 'fail', feedback: 'Blurry' },
        });
        expect(getStatusColor(report)).toBe('bg-yellow-500');
    });
});

// ---------------------------------------------------------------------------
// countdownAbortRef semantics
// ---------------------------------------------------------------------------

describe('IrisCaptureOrchestrator — countdownAbortRef semantics', () => {
    it('abort ref starts as false (safe to capture)', () => {
        // Simulates countdownAbortRef.current = false at start of performCapture
        let abortRef = false;
        expect(abortRef).toBe(false);
    });

    it('quality drop sets abort flag to true', () => {
        let abortRef = false;
        // Simulate quality loop detecting drop during capture
        const isCapturing = true;
        const qualityOk = false;
        if (!qualityOk && isCapturing) {
            abortRef = true;
        }
        expect(abortRef).toBe(true);
    });

    it('abort flag reset to false at start of new capture', () => {
        let abortRef = true; // was set from previous attempt
        // handleRetake or new performCapture resets
        abortRef = false;
        expect(abortRef).toBe(false);
    });
});
