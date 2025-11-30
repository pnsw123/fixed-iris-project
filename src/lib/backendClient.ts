/**
 * Backend API Client
 * Communicates with Python backend for iris processing (Iris-SAM + Real-ESRGAN)
 */

export interface ProcessIrisResponse {
  success: boolean;
  processing_time_ms?: number;
  original_size?: [number, number];
  upscaled_size?: [number, number];
  upscaled_image?: string; // base64 data URL
  mask?: string;
  intermediate_iris?: string;
  metadata?: {
    iris_sam_time_ms: number;
    esrgan_time_ms: number;
    mask_quality_score: number;
    total_time_ms?: number;
  };
  error?: string;
  detail?: string;
}

export interface ProcessIrisOptions {
  return_mask?: boolean;
  return_intermediate?: boolean;
  upscale_factor?: 2 | 4;
  irisCoordinates?: { x: number; y: number } | null;
  cropSize?: number;
  irisRadius?: number | null;
}

class BackendClient {
  private baseUrl: string;

  constructor(baseUrl: string = 'http://localhost:8000') {
    this.baseUrl = baseUrl;
  }

  /**
   * Check if backend is available
   */
  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(5000), // 5s timeout
      });

      if (!response.ok) {
        console.warn(`[BackendClient] Health check failed with status ${response.status}`);
        return false;
      }

      const data = await response.json();
      const isHealthy = data.status === 'ok' && data.models_loaded;

      if (isHealthy) {
        console.log('[BackendClient] ✅ Backend healthy, device:', data.device);
      }

      return isHealthy;
    } catch (error) {
      console.error('[BackendClient] Health check failed:', error);
      return false;
    }
  }

  /**
   * Process iris image (segment + upscale)
   */
  async processIris(
    imageDataUrl: string,
    options: ProcessIrisOptions = {}
  ): Promise<ProcessIrisResponse> {
    const PROCESS_TIMEOUT_MS = 120000; // Allow heavy models to finish
    try {
      // Convert base64 data URL to Blob
      const blob = await this.dataUrlToBlob(imageDataUrl);

      // Create FormData
      const formData = new FormData();
      formData.append('image', blob, 'iris.jpg');

      if (options.return_mask) {
        formData.append('return_mask', 'true');
      }
      if (options.return_intermediate) {
        formData.append('return_intermediate', 'true');
      }
      if (options.upscale_factor) {
        formData.append('upscale_factor', options.upscale_factor.toString());
      }

      // Add iris coordinates and radius if available
      if (options.irisCoordinates) {
        formData.append('iris_x', options.irisCoordinates.x.toString());
        formData.append('iris_y', options.irisCoordinates.y.toString());
        formData.append('crop_size', (options.cropSize || 0).toString());
        if (options.irisRadius) {
          formData.append('iris_radius', options.irisRadius.toString());
          console.log('[BackendClient] Sending iris coordinates + radius:', options.irisCoordinates, 'radius:', options.irisRadius);
        } else {
          console.log('[BackendClient] Sending iris coordinates:', options.irisCoordinates);
        }
      } else {
        console.log('[BackendClient] No coordinates - using center fallback');
      }

      console.log('[BackendClient] Sending iris image to backend for processing...');

      // Send request
      const response = await fetch(`${this.baseUrl}/api/v1/process-iris`, {
        method: 'POST',
        body: formData,
        signal: AbortSignal.timeout(PROCESS_TIMEOUT_MS),
        // Don't set Content-Type - browser will set it with boundary
      });

      if (!response.ok) {
        const error = await response.json();
        const errorMsg = error.error || error.detail || 'Backend processing failed';
        console.error('[BackendClient] Backend error:', error);
        throw new Error(errorMsg);
      }

      const result: ProcessIrisResponse = await response.json();

      if (!result.success) {
        throw new Error(result.error || 'Processing returned success=false');
      }

      console.log('[BackendClient] ✅ Processing complete!', {
        irisSamMs: result.metadata?.iris_sam_time_ms,
        esrganMs: result.metadata?.esrgan_time_ms,
        qualityScore: result.metadata?.mask_quality_score,
      });

      return result;

    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      console.error('[BackendClient] Process failed:', errorMsg);
      throw error;
    }
  }

  /**
   * Convert base64 data URL to Blob
   */
  private async dataUrlToBlob(dataUrl: string): Promise<Blob> {
    try {
      const response = await fetch(dataUrl);
      return response.blob();
    } catch (error) {
      console.error('[BackendClient] Failed to convert data URL:', error);
      throw new Error('Failed to prepare image for upload');
    }
  }
}

// Singleton instance
export const backendClient = new BackendClient(
  process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
);
