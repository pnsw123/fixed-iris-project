/**
 * Camera Resolution Checker
 * Detects the maximum resolution of the front camera and validates minimum requirements.
 * 
 * 12MP = 12,000,000 pixels (e.g., 4032 x 3024 = 12,192,768)
 */

export interface CameraCapabilities {
    maxWidth: number;
    maxHeight: number;
    megapixels: number;
    deviceLabel: string;
    meetsRequirement: boolean;
}

const MIN_MEGAPIXELS = 12;
const MIN_PIXELS = MIN_MEGAPIXELS * 1_000_000; // 12 million pixels

/**
 * Check if the front camera meets the minimum resolution requirement.
 * Returns camera capabilities including whether it meets the 12MP minimum.
 */
export async function checkCameraResolution(): Promise<CameraCapabilities> {
    try {
        // Request camera access with maximum resolution
        const stream = await navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: 'user',
                width: { ideal: 9999 },
                height: { ideal: 9999 }
            }
        });

        const track = stream.getVideoTracks()[0];
        const settings = track.getSettings();
        const capabilities = track.getCapabilities?.() || {};

        // Get the actual maximum resolution
        const maxWidth = capabilities.width?.max || settings.width || 0;
        const maxHeight = capabilities.height?.max || settings.height || 0;
        const deviceLabel = track.label || 'Unknown Camera';

        // Stop the stream
        stream.getTracks().forEach(t => t.stop());

        const totalPixels = maxWidth * maxHeight;
        const megapixels = totalPixels / 1_000_000;
        const meetsRequirement = totalPixels >= MIN_PIXELS;

        console.log(`[CameraCheck] Device: ${deviceLabel}`);
        console.log(`[CameraCheck] Max Resolution: ${maxWidth}x${maxHeight}`);
        console.log(`[CameraCheck] Megapixels: ${megapixels.toFixed(1)}MP`);
        console.log(`[CameraCheck] Meets ${MIN_MEGAPIXELS}MP requirement: ${meetsRequirement}`);

        return {
            maxWidth,
            maxHeight,
            megapixels,
            deviceLabel,
            meetsRequirement
        };
    } catch (error) {
        console.error('[CameraCheck] Failed to check camera:', error);
        // If we can't check, assume it doesn't meet requirements
        return {
            maxWidth: 0,
            maxHeight: 0,
            megapixels: 0,
            deviceLabel: 'Camera Access Denied',
            meetsRequirement: false
        };
    }
}

export { MIN_MEGAPIXELS };
