/**
 * Phone Angle Detection using Device Orientation API
 * 
 * Detects phone tilt to ensure flashlight is aimed at hairline
 * for optimal iris illumination without direct reflections.
 */

export type AngleState = 'too_flat' | 'optimal' | 'too_steep' | 'unavailable';

export interface AngleResult {
    state: AngleState;
    beta: number | null; // Front-to-back tilt in degrees
    message: string;
}

// Optimal angle range: 25-50° (flashlight aimed upward at hairline)
const OPTIMAL_MIN = 25;
const OPTIMAL_MAX = 50;
const HYSTERESIS = 5;

let currentState: AngleState = 'unavailable';
let isListening = false;
let latestBeta: number | null = null;
let orientationHandler: ((event: DeviceOrientationEvent) => void) | null = null;

/**
 * Initialize phone angle detection
 * Requests permission on iOS 13+ and starts listening to orientation events
 */
export async function initializePhoneAngle(): Promise<boolean> {
    if (isListening) {
        console.log('[PhoneAngle] Already initialized');
        return true;
    }

    // Check if DeviceOrientationEvent exists
    if (typeof DeviceOrientationEvent === 'undefined') {
        console.warn('[PhoneAngle] DeviceOrientationEvent not available');
        currentState = 'unavailable';
        return false;
    }

    // Request permission on iOS 13+
    if (typeof (DeviceOrientationEvent as any).requestPermission === 'function') {
        try {
            console.log('[PhoneAngle] Requesting permission (iOS)...');
            const permission = await (DeviceOrientationEvent as any).requestPermission();
            if (permission !== 'granted') {
                console.warn('[PhoneAngle] Permission denied');
                currentState = 'unavailable';
                return false;
            }
            console.log('[PhoneAngle] Permission granted');
        } catch (error) {
            console.error('[PhoneAngle] Permission request failed:', error);
            currentState = 'unavailable';
            return false;
        }
    }

    // Start listening to orientation events
    orientationHandler = (event: DeviceOrientationEvent) => {
        // Beta: front-to-back tilt (-180 to 180)
        // When phone is flat: beta ≈ 0
        // When phone tilted back (flashlight up): beta > 0
        if (event.beta !== null) {
            latestBeta = event.beta;
        }
    };

    window.addEventListener('deviceorientation', orientationHandler);
    isListening = true;
    console.log('[PhoneAngle] Listening to device orientation');

    return true;
}

/**
 * Get current phone angle state
 * Applies hysteresis to prevent flickering
 */
export function getAngleState(): AngleResult {
    if (!isListening || latestBeta === null) {
        return {
            state: 'unavailable',
            beta: null,
            message: 'Angle detection unavailable'
        };
    }

    const beta = latestBeta;
    let newState: AngleState = currentState;

    // Determine state based on current state (hysteresis)
    if (currentState === 'unavailable') {
        // First reading - no hysteresis
        if (beta < OPTIMAL_MIN) {
            newState = 'too_flat';
        } else if (beta > OPTIMAL_MAX) {
            newState = 'too_steep';
        } else {
            newState = 'optimal';
        }
    } else if (currentState === 'optimal') {
        // Currently optimal - need to go outside range + hysteresis to change
        if (beta < OPTIMAL_MIN - HYSTERESIS) {
            newState = 'too_flat';
        } else if (beta > OPTIMAL_MAX + HYSTERESIS) {
            newState = 'too_steep';
        }
    } else {
        // Currently not optimal - need to get inside range to pass
        if (beta >= OPTIMAL_MIN && beta <= OPTIMAL_MAX) {
            newState = 'optimal';
        } else if (beta < OPTIMAL_MIN) {
            newState = 'too_flat';
        } else {
            newState = 'too_steep';
        }
    }

    currentState = newState;

    // Generate message
    let message = '';
    switch (newState) {
        case 'too_flat':
            message = 'Tilt Phone Back';
            break;
        case 'too_steep':
            message = 'Tilt Phone Forward';
            break;
        case 'optimal':
            message = 'Perfect Angle';
            break;
        case 'unavailable':
            message = 'Angle unavailable';
            break;
    }

    // Debug log occasionally
    if (Math.random() < 0.05) {
        console.log('[PhoneAngle] Beta:', beta.toFixed(1), '° | State:', newState);
    }

    return {
        state: newState,
        beta,
        message
    };
}

/**
 * Stop listening to orientation events
 */
export function stopPhoneAngle() {
    if (orientationHandler) {
        window.removeEventListener('deviceorientation', orientationHandler);
        orientationHandler = null;
    }
    isListening = false;
    latestBeta = null;
    currentState = 'unavailable';
    console.log('[PhoneAngle] Stopped listening');
}

/**
 * Reset state (for testing)
 */
export function resetPhoneAngle() {
    currentState = 'unavailable';
    latestBeta = null;
    console.log('[PhoneAngle] State reset');
}
