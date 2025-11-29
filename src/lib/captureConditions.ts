/**
 * Capture Condition Definitions
 * 
 * Defines all 7 conditions that must be met for successful iris capture,
 * including thresholds with hysteresis to prevent flickering.
 */

export type ConditionState = 'pass' | 'fail' | 'unknown';

export interface ConditionResult {
    state: ConditionState;
    value: number;
    message?: string;
}

export interface CaptureConditions {
    faceDetected: ConditionResult;
    distanceOk: ConditionResult;
    eyeCentered: ConditionResult;
    focusSharp: ConditionResult;
    lightingAdequate: ConditionResult;
    eyebrowsRaised: ConditionResult;
    phoneAngleOk: ConditionResult;
}

/**
 * Thresholds for each condition with hysteresis
 * Hysteresis prevents flickering by having different thresholds for entering/exiting pass state
 */
export const CONDITION_THRESHOLDS = {
    // Condition 1: Face Detected (iris landmarks visible)
    faceDetected: {
        // Binary condition - either detected or not
        required: true,
    },

    // Condition 2: Distance OK (iris diameter in pixels)
    // Target: 20cm distance = ~200-280px iris diameter
    distance: {
        min: 200,          // Too far if below this
        max: 280,          // Too close if above this
        hysteresis: 20,    // Allow ±20px buffer before changing state
        // Pass range: 200-280
        // Once passing, stays passing until: <180 or >300
    },

    // Condition 3: Eye Centered (distance from frame center)
    // Allow 30% deviation from center
    centering: {
        maxDeviationPercent: 0.30,  // 30% of min(width, height)
        hysteresis: 0.05,           // 5% buffer for stability
        // Pass if: distance < 30% of frame
        // Once passing, stays passing until: distance > 35%
    },

    // Condition 4: Focus Sharp (edge detection score)
    // Based on Laplacian variance / edge detection
    focus: {
        sharpThreshold: 15,      // Sharp if edge score > 15
        acceptableThreshold: 8,  // Acceptable if > 8
        blurryThreshold: 5,      // Blurry if < 5
        hysteresis: 2,           // Buffer for stability
    },

    // Condition 5: Lighting Adequate (average brightness)
    lighting: {
        minBrightness: 50,       // Dark if below
        maxBrightness: 200,      // Too bright if above
        perfectMin: 80,          // Perfect range
        perfectMax: 180,
        hysteresis: 10,          // Buffer for stability
    },

    // Condition 6: Eyebrows Raised
    // Detected via eyebrow landmark displacement
    eyebrows: {
        // Vertical displacement threshold (pixels)
        // If eyebrow landmarks are N pixels higher than neutral, they're "raised"
        raisedThreshold: 10,     // Must be 10px above neutral position
        hysteresis: 3,           // 3px buffer
        // Once confirmed raised, state becomes persistent (never reverts)
    },

    // Condition 7: Phone Angle OK (flashlight aimed at hairline)
    // Using device orientation beta (front-to-back tilt)
    phoneAngle: {
        // Optimal angle: phone tilted ~30-45° back (flashlight points up toward hairline)
        minAngle: 25,            // degrees
        maxAngle: 50,            // degrees
        optimalAngle: 35,
        hysteresis: 5,           // Buffer for stability
    },
} as const;

/**
 * Stability requirements to prevent flickering
 */
export const STABILITY_CONFIG = {
    // All conditions must stay PASS for this duration before countdown starts
    stabilityWindowMs: 800,

    // Minimum time between showing the same guidance message (voice or text)
    messageCooldownMs: 2500,

    // Countdown duration (existing)
    countdownDurationMs: 3000,
} as const;

/**
 * Priority order for guidance messages
 * When multiple conditions fail, show the highest priority failure
 */
export const CONDITION_PRIORITY = [
    'eyebrowsRaised',     // 1. Most important for user action
    'phoneAngleOk',        // 2. Phone positioning
    'distanceOk',          // 3. Distance adjustment
    'eyeCentered',         // 4. Centering
    'lightingAdequate',    // 5. Lighting (usually auto-handled by torch)
    'focusSharp',          // 6. Focus (tap to focus)
    'faceDetected',        // 7. Basic detection (usually always passes if user is there)
] as const;

/**
 * Guidance messages for each condition failure
 */
export const GUIDANCE_MESSAGES = {
    eyebrowsRaised: 'Raise Your Eyebrows',
    phoneAngleOk: 'Aim Light at Hairline',
    distanceOk: {
        tooFar: 'Move Closer',
        tooClose: 'Move Back',
        perfect: 'Perfect Distance',
    },
    eyeCentered: 'Center Your Eye',
    lightingAdequate: {
        dark: 'More Light Needed',
        tooBright: 'Too Much Light',
        perfect: 'Good Lighting',
    },
    focusSharp: 'Tap to Focus',
    faceDetected: 'Position Your Face',
    allPass: 'Hold Still',
} as const;

/**
 * Helper function to apply hysteresis to a numeric condition
 * Prevents flickering by requiring value to cross threshold + hysteresis buffer
 */
export function applyHysteresis(
    value: number,
    min: number,
    max: number,
    hysteresis: number,
    currentState: ConditionState
): ConditionState {
    if (currentState === 'pass') {
        // Currently passing - need to go outside min/max + hysteresis to fail
        if (value < min - hysteresis || value > max + hysteresis) {
            return 'fail';
        }
        return 'pass';
    } else {
        // Currently failing - need to get inside min/max range to pass
        if (value >= min && value <= max) {
            return 'pass';
        }
        return 'fail';
    }
}
