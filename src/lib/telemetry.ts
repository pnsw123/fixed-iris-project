/**
 * Simple Telemetry for Iris Capture
 * Tracks condition failures, abort reasons, and performance metrics
 */

interface TelemetryData {
    conditionFailures: {
        noFace: number;
        distance: number;
        eyebrows: number;
        centering: number;
        focus: number;
        lighting: number;
    };
    countdownAborts: {
        noFace: number;
        distance: number;
        centering: number;
        other: number;
    };
    performance: {
        inferenceTimeSum: number;
        inferenceTimeCount: number;
        inferenceTimeMax: number;
    };
}

class Telemetry {
    private data: TelemetryData = {
        conditionFailures: {
            noFace: 0,
            distance: 0,
            eyebrows: 0,
            centering: 0,
            focus: 0,
            lighting: 0,
        },
        countdownAborts: {
            noFace: 0,
            distance: 0,
            centering: 0,
            other: 0,
        },
        performance: {
            inferenceTimeSum: 0,
            inferenceTimeCount: 0,
            inferenceTimeMax: 0,
        },
    };

    private lastLogTime = 0;
    private readonly LOG_INTERVAL = 10000; // Log every 10 seconds

    /**
     * Track a condition failure
     */
    trackConditionFailure(condition: keyof TelemetryData['conditionFailures']) {
        this.data.conditionFailures[condition]++;
        this.maybeLog();
    }

    /**
     * Track a countdown abort
     */
    trackCountdownAbort(reason: keyof TelemetryData['countdownAborts']) {
        this.data.countdownAborts[reason]++;
        console.log(`[Telemetry] Countdown aborted: ${reason}`);
    }

    /**
     * Track inference time
     */
    trackInferenceTime(ms: number) {
        this.data.performance.inferenceTimeSum += ms;
        this.data.performance.inferenceTimeCount++;
        if (ms > this.data.performance.inferenceTimeMax) {
            this.data.performance.inferenceTimeMax = ms;
        }
        this.maybeLog();
    }

    /**
     * Log telemetry data periodically
     */
    private maybeLog() {
        const now = Date.now();
        if (now - this.lastLogTime >= this.LOG_INTERVAL) {
            this.lastLogTime = now;
            this.logSummary();
        }
    }

    /**
     * Log telemetry summary
     */
    logSummary() {
        const avgInferenceTime =
            this.data.performance.inferenceTimeCount > 0
                ? this.data.performance.inferenceTimeSum / this.data.performance.inferenceTimeCount
                : 0;

        console.log('[Telemetry] === Summary ===');
        console.log('[Telemetry] Condition Failures:', this.data.conditionFailures);
        console.log('[Telemetry] Countdown Aborts:', this.data.countdownAborts);
        console.log(
            `[Telemetry] Inference Time: avg=${avgInferenceTime.toFixed(1)}ms, max=${this.data.performance.inferenceTimeMax.toFixed(1)}ms`
        );
    }

    /**
     * Reset telemetry data
     */
    reset() {
        this.data = {
            conditionFailures: {
                noFace: 0,
                distance: 0,
                eyebrows: 0,
                centering: 0,
                focus: 0,
                lighting: 0,
            },
            countdownAborts: {
                noFace: 0,
                distance: 0,
                centering: 0,
                other: 0,
            },
            performance: {
                inferenceTimeSum: 0,
                inferenceTimeCount: 0,
                inferenceTimeMax: 0,
            },
        };
    }
}

export const telemetry = new Telemetry();
