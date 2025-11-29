import { telemetry } from './telemetry';

/**
 * Capture Stages Management (Front-Camera Selfie Mode)
 * 
 * Sequential workflow for iris capture:
 * Distance → Eyebrows → Final Checks → Ready
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

    // Thresholds (Front-Camera Selfie Mode)
    // Resolution-aware: Eye diameter as % of frame height
    // Assumes 1280x720 (720p) → 8-12% of 720 = 58-86px
    private readonly THRESHOLDS = {
        distance: {
            minPercent: 0.08, // 8% of frame height
            maxPercent: 0.12, // 12% of frame height
            // For 720p: 58-86px
            // For 1080p: 86-130px
        },
        eyebrows: {
            sustainedFrames: 30, // ~2 seconds at 15 FPS
            displacementThreshold: -15 // pixels (negative = raised)
        },
        final: {
            maxCenteringRatio: 0.3, // 30% from center
            minSharpness: 8,
            minBrightness: 60, // 0-255 scale (luma)
            maxBrightness: 200
        }
    };

    // Hysteresis margins (to prevent flicker)
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

    private processDistanceStage(distance: StageRequirements['distance'], now: number) {
        const { irisDiameter } = distance;

        // Convert to percentage of frame height (assuming normalized to 1080p)
        const frameHeight = 1080; // Reference height
        const diameterPercent = irisDiameter / frameHeight;

        const { minPercent, maxPercent } = this.THRESHOLDS.distance;

        // Hysteresis: If already stable, widen the window
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

    private processEyebrowsStage(eyebrows: StageRequirements['eyebrows'], now: number) {
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

    private advanceStage() {
        const currentIndex = STAGE_ORDER.indexOf(this.currentStage);
        if (currentIndex < STAGE_ORDER.length - 1) {
            this.currentStage = STAGE_ORDER[currentIndex + 1];
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

    private getProgress(requirements: StageRequirements): number {
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
