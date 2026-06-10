import { telemetry } from './telemetry';

/**
 * captureStages.ts — Linear 4-stage state machine for guided iris capture.
 *
 * Overview:
 * The user must satisfy each stage in order before the capture fires.
 * Stages are one-directional forward (distance → eyebrows → final_checks → ready)
 * but can regress via returnToStage() if quality drops during the final countdown.
 *
 * Stage map:
 *   1. distance      — iris must be in the 7-12% of frame-height size band for ≥ 800 ms
 *   2. eyebrows      — user raises eyebrows and holds for ≥ 30 sustained frames (~2 s at 15 fps)
 *                      Acts as a liveness check: a printed photo cannot raise eyebrows.
 *   3. final_checks  — centering, sharpness, and brightness all pass simultaneously for ≥ 800 ms
 *   4. ready         — terminal state; signals the capture component to fire the shutter
 *
 * Stability windows (800 ms) prevent momentary glitches from advancing the stage prematurely.
 * Hysteresis margins prevent the stage from yo-yoing when a metric is right at the threshold.
 *
 * Telemetry is tracked for each condition failure to support product analytics on where
 * users most commonly struggle in the funnel.
 */

export type CaptureStage =
    | 'distance'
    | 'eyebrows'
    | 'final_checks'
    | 'ready';

export interface StageState {
    current: CaptureStage;
    progress: number; // 0-100 for current stage
    message: string;
    canAdvance: boolean;
    stageNumber: number; // 1-4
    totalStages: number; // Always 4
}

export interface StageRequirements {
    distance: {
        irisDiameter: number; // Eye diameter in pixels (normalized to 1080p)
    };
    eyebrows: {
        isRaised: boolean;
        displacement: number;
    };
    angle: {
        beta: number | null;
        available: boolean; // Always false for front camera
    };
    flashlight: {
        torchOn: boolean; // Always false for front camera
    };
    finalChecks: {
        centeringRatio: number; // 0.0 - 1.0
        sharpness: number; // 0 - 100
        brightness: number; // 0 - 255
    };
}

const STAGE_ORDER: CaptureStage[] = ['distance', 'eyebrows', 'final_checks', 'ready'];

const STAGE_MESSAGES = {
    distance: {
        tooFar: 'Move Closer',
        tooClose: 'Move Back',
        perfect: 'Perfect Distance',
    },
    eyebrows: {
        notRaised: 'Raise Your Eyebrows',
        holding: 'Hold Them Raised...',
        good: 'Good! Keep Going',
    },
    finalChecks: {
        centerEye: 'Center Your Eye',
        tapFocus: 'Tap to Focus',
        checkLighting: 'Move to Better Light',
        almostReady: 'Almost Ready...',
    },
    ready: {
        countdown: 'Hold Still!',
    },
};

type EyebrowState = 'not_raised' | 'raised' | 'confirmed';

export class StageManager {
    private currentStage: CaptureStage = 'distance';
    private stageStartTime: number = Date.now();
    private distanceStableTime: number = 0;
    private eyebrowState: EyebrowState = 'not_raised';
    private eyebrowSustainedFrames: number = 0;
    private finalChecksStableTime: number = 0;

    /**
     * THRESHOLDS — calibrated for front-camera selfie capture at 720p/1080p.
     *
     * distance.minPercent / maxPercent:
     *   Iris diameter expressed as a fraction of the reference frame height (1080 px).
     *   8% → iris too small (user too far away, not enough texture detail for matching).
     *   12% → iris too large (user too close; eyelid occlusion, barrel distortion).
     *   Pixel equivalents: 720p ≈ 58-86 px, 1080p ≈ 86-130 px.
     *
     * eyebrows.sustainedFrames = 30:
     *   At roughly 15 FPS inference rate, 30 frames ≈ 2 seconds of continuous raising.
     *   Chosen long enough that a brief surprised blink won't accidentally pass the check,
     *   but short enough not to tire the user.
     *
     * eyebrows.displacementThreshold = -15 px:
     *   Negative because Y increases downward in canvas coordinates.  A raised eyebrow
     *   has a smaller (more negative) Y than the neutral position.  Not currently used
     *   in StageManager (isRaised comes from qualityMetrics), but kept for documentation.
     *
     * final.maxCenteringRatio = 0.3:
     *   The iris centre may be at most 30% of the half-short-side away from frame centre.
     *   Allows for the natural offset of a single eye in a selfie.
     *
     * final.minSharpness = 8:
     *   Lower floor than the qualityMetrics FOCUS_THRESHOLD_WARN (50) because
     *   captureStages uses the raw QualityReport.focus.score which is already
     *   on the same scale; 8 is intentionally lenient here.
     *
     * final.minBrightness / maxBrightness (60–200):
     *   Luma range on 0-255 scale.  Tighter than qualityMetrics ideal (100-180)
     *   to give the UI more room before hitting a hard FAIL.
     */
    private readonly THRESHOLDS = {
        distance: {
            minPercent: 0.08, // 8% of frame height
            maxPercent: 0.12, // 12% of frame height
            // For 720p: 58-86px
            // For 1080p: 86-130px
        },
        eyebrows: {
            sustainedFrames: 30, // ~2 seconds at 15 FPS
            displacementThreshold: -15 // pixels (negative = raised, canvas Y-down coords)
        },
        final: {
            maxCenteringRatio: 0.3, // 30% from center
            minSharpness: 8,
            minBrightness: 60, // 0-255 scale (luma)
            maxBrightness: 200
        }
    };

    /**
     * HYSTERESIS — prevents stage regression/flicker when a metric hovers near its threshold.
     *
     * When a stability timer has been running (isStable = true), thresholds are
     * widened by the hysteresis margin.  This means a metric must move *further past*
     * the threshold to reset the timer, preventing rapid oscillation for users who
     * are just marginally satisfying a condition.
     *
     * distance ±2%: small margin; distance changes relatively slowly.
     * centering ±5%: slightly larger; head micro-movements affect centering more.
     * brightness ±10 units: light fluctuations of 10 luma units are imperceptible.
     */
    private readonly HYSTERESIS = {
        distance: 0.02, // ±2% margin when stable
        centering: 0.05, // ±5% margin
        brightness: 10 // ±10 units
    };

    constructor() {
        this.reset();
    }

    /**
     * Reset stage manager to initial state
     */
    reset() {
        this.currentStage = 'distance';
        this.stageStartTime = Date.now();
        this.distanceStableTime = 0;
        this.eyebrowState = 'not_raised';
        this.eyebrowSustainedFrames = 0;
        this.finalChecksStableTime = 0;
    }

    /**
     * Disable eyebrow stage (auto-skip)
     */
    disableEyebrows() {
        // Not used for front camera, but keep for compatibility
    }

    /**
     * Disable angle stage (auto-skip)
     */
    disableAngle() {
        // Not used for front camera, but keep for compatibility
    }

    /**
     * Update stage based on current requirements
     * Returns new stage state
     */
    update(requirements: StageRequirements): StageState {
        const now = Date.now();

        // Process current stage
        switch (this.currentStage) {
            case 'distance':
                this.processDistanceStage(requirements.distance, now);
                break;
            case 'eyebrows':
                this.processEyebrowsStage(requirements.eyebrows, now);
                break;
            case 'final_checks':
                this.processFinalChecksStage(requirements.finalChecks, now);
                break;
            case 'ready':
                // Stay in ready state
                break;
        }

        return this.getState(requirements);
    }

    /**
     * Force return to a specific stage (for regression during countdown)
     */
    returnToStage(stage: CaptureStage) {
        this.currentStage = stage;
        this.stageStartTime = Date.now();
        // Reset stability timers
        this.distanceStableTime = 0;
        this.finalChecksStableTime = 0;
    }

    /**
     * processDistanceStage — gate 1: user must hold correct distance for 800 ms.
     *
     * Transition trigger:
     *   iris diameter ∈ [minPercent - hysteresis, maxPercent + hysteresis] of 1080 px
     *   for a continuous 800 ms window → advance to 'eyebrows'.
     *
     * The 800 ms window ensures the user has physically settled at the distance
     * rather than passing through it while moving the phone/head.  It is measured
     * with a monotonic timestamp (`distanceStableTime`) that resets to 0 whenever
     * the diameter leaves the range.
     *
     * Hysteresis only applies once the timer has started (`isStable = true`): after
     * the user enters the range the effective band widens slightly, preventing a
     * single frame of micro-movement from resetting the 800 ms clock.
     */
    private processDistanceStage(distance: StageRequirements['distance'], now: number) {
        const { irisDiameter } = distance;

        // Normalise to percentage of 1080-pixel reference height for device-agnostic comparison.
        const frameHeight = 1080; // Reference height
        const diameterPercent = irisDiameter / frameHeight;

        const { minPercent, maxPercent } = this.THRESHOLDS.distance;

        // After the first in-range frame, widen the band by the hysteresis margin
        // so minor fluctuations don't restart the 800 ms clock.
        const isStable = this.distanceStableTime > 0;
        const margin = isStable ? this.HYSTERESIS.distance : 0;

        const isInRange = diameterPercent >= (minPercent - margin) && diameterPercent <= (maxPercent + margin);

        if (isInRange) {
            if (this.distanceStableTime === 0) {
                this.distanceStableTime = now;
            }
            // Stability window: 800ms
            if (now - this.distanceStableTime >= 800) {
                this.advanceStage();
            }
        } else {
            this.distanceStableTime = 0;
            telemetry.trackConditionFailure('distance');
        }
    }

    /**
     * processEyebrowsStage — gate 2: liveness check via sustained eyebrow raise.
     *
     * Inner state machine:  not_raised  →  raised  →  confirmed
     *
     *   not_raised → raised  : first frame where isRaised is true
     *   raised → confirmed   : eyebrowSustainedFrames reaches sustainedFrames (30)
     *   any state → not_raised : isRaised drops to false; counter resets
     *
     * Transition trigger:
     *   confirmed state → advance to 'final_checks'.
     *   Once confirmed the stage does not regress even if the user lowers their eyebrows
     *   (the confirmed guard at the top auto-passes on subsequent calls).
     *
     * Why a frame counter instead of a time window:
     *   Frame rate varies by device (10-30 fps).  Using `sustainedFrames = 30` gives
     *   ~2 s at 15 fps and ~1 s at 30 fps — both acceptable.  A wall-clock approach
     *   would require tracking when `raised` first transitioned, adding complexity.
     */
    private processEyebrowsStage(eyebrows: StageRequirements['eyebrows'], _now: number) {
        // Eyebrow State Machine: not_raised → raised → confirmed

        if (this.eyebrowState === 'confirmed') {
            // Already confirmed, auto-pass
            this.advanceStage();
            return;
        }

        const { isRaised } = eyebrows;

        if (isRaised) {
            this.eyebrowSustainedFrames++;

            if (this.eyebrowState === 'not_raised') {
                this.eyebrowState = 'raised';
            }

            if (this.eyebrowSustainedFrames >= this.THRESHOLDS.eyebrows.sustainedFrames) {
                this.eyebrowState = 'confirmed';
                this.advanceStage();
            }
        } else {
            // Reset if they drop it
            this.eyebrowSustainedFrames = 0;
            if (this.eyebrowState === 'raised') {
                this.eyebrowState = 'not_raised';
            }
            telemetry.trackConditionFailure('eyebrows');
        }
    }

    /**
     * processFinalChecksStage — gate 3: centering, sharpness, and brightness all pass for 800 ms.
     *
     * All three conditions must be true simultaneously; any single failure resets the 800 ms clock.
     * Hysteresis is applied to brightness (±10 luma) and centering (±5%) after the timer starts,
     * preventing minor fluctuations from restarting the countdown right at the end.
     *
     * Failure priority for UI feedback (getMessage):
     *   1. Centering — most actionable: user can immediately reposition camera
     *   2. Focus     — second most actionable: "tap to focus" or hold steady
     *   3. Lighting  — least actionable: requires environment change
     *
     * Transition trigger:
     *   All three pass simultaneously for 800 ms → advance to 'ready'.
     */
    private processFinalChecksStage(finalChecks: StageRequirements['finalChecks'], now: number) {
        const { centeringRatio, sharpness, brightness } = finalChecks;
        const { maxCenteringRatio, minSharpness, minBrightness, maxBrightness } = this.THRESHOLDS.final;

        // Hysteresis for brightness
        const isStable = this.finalChecksStableTime > 0;
        const brightMargin = isStable ? this.HYSTERESIS.brightness : 0;
        const centerMargin = isStable ? this.HYSTERESIS.centering : 0;

        const centered = centeringRatio <= (maxCenteringRatio + centerMargin);
        const focused = sharpness >= minSharpness;
        const litWell = brightness >= (minBrightness - brightMargin) && brightness <= (maxBrightness + brightMargin);

        if (centered && focused && litWell) {
            if (this.finalChecksStableTime === 0) {
                this.finalChecksStableTime = now;
            }
            // Stability window: 800ms
            if (now - this.finalChecksStableTime >= 800) {
                this.advanceStage();
            }
        } else {
            this.finalChecksStableTime = 0;
            if (!centered) telemetry.trackConditionFailure('centering');
            if (!focused) telemetry.trackConditionFailure('focus');
            if (!litWell) telemetry.trackConditionFailure('lighting');
        }
    }

    /**
     * advanceStage — move to the next stage in STAGE_ORDER.
     *
     * Stages progress strictly forward: distance→eyebrows→final_checks→ready.
     * The guard `currentIndex < STAGE_ORDER.length - 1` ensures 'ready' is terminal
     * and subsequent calls are silently ignored (idempotent).
     */
    private advanceStage() {
        const currentIndex = STAGE_ORDER.indexOf(this.currentStage);
        if (currentIndex < STAGE_ORDER.length - 1) {
            this.currentStage = STAGE_ORDER[currentIndex + 1]!;
            this.stageStartTime = Date.now();
            console.log('[StageManager] Advanced to stage:', this.currentStage);
        }
    }

    private getState(requirements: StageRequirements): StageState {
        const stageNumber = STAGE_ORDER.indexOf(this.currentStage) + 1;

        return {
            current: this.currentStage,
            progress: this.getProgress(requirements),
            message: this.getMessage(requirements),
            canAdvance: this.canAdvanceFromCurrent(requirements),
            stageNumber,
            totalStages: 4,
        };
    }

    private getProgress(_requirements: StageRequirements): number {
        const now = Date.now();

        switch (this.currentStage) {
            case 'distance':
                if (this.distanceStableTime > 0) {
                    return Math.min(100, ((now - this.distanceStableTime) / 800) * 100);
                }
                return 0;

            case 'eyebrows':
                return Math.min(100, (this.eyebrowSustainedFrames / this.THRESHOLDS.eyebrows.sustainedFrames) * 100);

            case 'final_checks':
                if (this.finalChecksStableTime > 0) {
                    return Math.min(100, ((now - this.finalChecksStableTime) / 800) * 100);
                }
                return 0;

            case 'ready':
                return 100;

            default:
                return 0;
        }
    }

    private getMessage(requirements: StageRequirements): string {
        switch (this.currentStage) {
            case 'distance': {
                const { irisDiameter } = requirements.distance;
                const frameHeight = 1080;
                const diameterPercent = irisDiameter / frameHeight;
                const { minPercent, maxPercent } = this.THRESHOLDS.distance;

                if (diameterPercent < minPercent) return STAGE_MESSAGES.distance.tooFar;
                if (diameterPercent > maxPercent) return STAGE_MESSAGES.distance.tooClose;
                return STAGE_MESSAGES.distance.perfect;
            }

            case 'eyebrows': {
                if (this.eyebrowState === 'confirmed') return STAGE_MESSAGES.eyebrows.good;
                if (!requirements.eyebrows.isRaised) return STAGE_MESSAGES.eyebrows.notRaised;
                if (this.eyebrowSustainedFrames < this.THRESHOLDS.eyebrows.sustainedFrames / 2) {
                    return STAGE_MESSAGES.eyebrows.holding;
                }
                return STAGE_MESSAGES.eyebrows.good;
            }

            case 'final_checks': {
                const { centeringRatio, sharpness, brightness } = requirements.finalChecks;
                const { maxCenteringRatio, minSharpness, minBrightness } = this.THRESHOLDS.final;

                // Priority Guidance: Centering > Focus > Lighting
                // Centering is shown first because it is the most immediately fixable
                // (user just moves camera).  Focus second (tap or hold steady).
                // Lighting last because it requires changing environment — shown only
                // when positioning and focus are already satisfied.
                if (centeringRatio > maxCenteringRatio) return STAGE_MESSAGES.finalChecks.centerEye;
                if (sharpness < minSharpness) return STAGE_MESSAGES.finalChecks.tapFocus;
                if (brightness < minBrightness) return STAGE_MESSAGES.finalChecks.checkLighting;
                return STAGE_MESSAGES.finalChecks.almostReady;
            }

            case 'ready':
                return STAGE_MESSAGES.ready.countdown;

            default: return '';
        }
    }

    private canAdvanceFromCurrent(requirements: StageRequirements): boolean {
        return this.getProgress(requirements) >= 100;
    }

    getCurrentStage(): CaptureStage {
        return this.currentStage;
    }

    isReady(): boolean {
        return this.currentStage === 'ready';
    }
}
