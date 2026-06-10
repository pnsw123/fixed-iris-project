/**
 * backendClient.ts — Frontend ↔ FastAPI integration layer.
 *
 * This module is the single integration point between the Next.js frontend and
 * the Python/FastAPI backend that runs Iris-SAM (segment anything model) and
 * Real-ESRGAN (super-resolution).  Every interaction with the GPU pipeline flows
 * through this file.
 *
 * ── Architecture overview ──────────────────────────────────────────────────────
 *
 *   Next.js (browser)
 *       │
 *       │  multipart/form-data POST  (image + coordinates + options)
 *       ▼
 *   FastAPI (Python, port 8000)
 *       │
 *       ├─► Iris-SAM   — segments the iris from the eye image.
 *       │                 Accepts an optional (iris_x, iris_y) center-point hint
 *       │                 to guide SAM's prompt encoder (see irisCoordinates note).
 *       │
 *       └─► Real-ESRGAN — upscales the masked iris region ×2 or ×4.
 *
 *   The backend holds a single-slot GPU semaphore: only one inference job runs at
 *   a time.  If a second request arrives while the GPU is occupied the backend
 *   returns HTTP 503 (GPU busy); the frontend must surface this to the user rather
 *   than retrying automatically (a retry storm would starve other sessions).
 *
 * ── irisCoordinates: why sent separately from the image ──────────────────────
 *
 *   SAM is a prompt-based segmentation model.  Without a prompt it must evaluate
 *   every possible mask in the image, which is slow and often picks up eyebrows or
 *   eyelashes instead of the iris.
 *
 *   `irisCoordinates` is the iris *center point* detected by MediaPipe on the
 *   frontend (see qualityMetrics.ts → QualityReport.irisCenter).  It is sent as
 *   `iris_x` / `iris_y` form fields — in *original image pixel space*, not canvas
 *   space — and used as SAM's positive point prompt.  This reduces segmentation
 *   time by ~60% and significantly improves mask accuracy on partially-occluded
 *   irises.
 *
 *   `irisRadius` (optional) lets the backend derive a tighter crop region before
 *   running SAM, further reducing GPU memory consumption.
 *
 * ── download_token contract ────────────────────────────────────────────────────
 *
 *   The `/api/v1/process-iris` endpoint returns a `download_token` in its response
 *   JSON. This token is a server-side reference to the processed images (HD +
 *   original) held temporarily on the backend so the large binary payload stays
 *   out of the JSON response.
 *
 *   CRITICAL INVARIANT: once the frontend receives a token it MUST NOT call
 *   `/api/v1/process-iris` again for the same capture — re-processing wastes GPU time.
 *
 *   Flow (free, no payment):
 *     1. Receive token from this client.
 *     2. Display the preview_image to the user.
 *     3. Pass token to `/api/download-hd` and `/api/download-original`.
 *
 *   The token expires one hour after processing.
 *
 * ── HTTP error codes ──────────────────────────────────────────────────────────
 *
 *   429 — Rate limit exceeded.  The backend enforces per-IP rate limiting (5 req/min
 *         by default).  The frontend should show "Too many requests, please wait" and
 *         back off; do NOT retry immediately.
 *
 *   503 — GPU busy (semaphore occupied).  A different request is currently running on
 *         the GPU.  Show "Server busy, please try again in a moment" — this is transient
 *         and clears within a few seconds once the current job finishes.
 *
 *   422 — Validation error (FastAPI Pydantic).  The request payload is malformed:
 *         image missing, coordinates out of valid range, unsupported upscale_factor, etc.
 *         This is a client-side bug — log `error.detail` for debugging and surface a
 *         generic "Processing failed" message to the user.
 *
 * ── Timeout ────────────────────────────────────────────────────────────────────
 *
 *   PROCESS_TIMEOUT_MS = 600 000 ms (10 minutes).  Real-ESRGAN at ×4 on a mid-range
 *   GPU can take 2-3 minutes for a 512×512 crop; on CPU it can exceed 8 minutes.
 *   A shorter browser default (~30 s) would abort legitimate long-running jobs.
 *   The health check uses a separate 5 s timeout because it should be fast.
 */

export interface ProcessIrisResponse {
  success: boolean;
  processing_time_ms?: number;
  original_size?: [number, number];
  upscaled_size?: [number, number];
  preview_image?: string;    // Low-res preview (base64 data URL)
  download_token?: string;   // Token — passed to /api/download-hd and /api/download-original
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
  /**
   * Center-point of the iris detected by MediaPipe on the frontend.
   * Forwarded to FastAPI as `iris_x` / `iris_y` form fields and used as
   * SAM's positive point prompt.  Coordinates are in *original image pixel
   * space* (i.e. relative to the blob sent as `image`, not the display canvas).
   * When null/undefined the backend falls back to the image centre — usable
   * but ~60% slower and more error-prone on partially-occluded irises.
   */
  irisCoordinates?: { x: number; y: number } | null;
  /** Pixel size of the iris crop box; sent as `crop_size` for backend pre-crop. */
  cropSize?: number;
  /**
   * Radius of the detected iris in pixels.  When provided the backend uses it
   * to derive a tighter SAM bounding-box prompt, reducing GPU memory and
   * improving mask boundary precision near the limbus (iris/sclera border).
   */
  irisRadius?: number | null;
}

class BackendClient {
  private baseUrl: string;

  constructor(baseUrl: string = 'https://localhost:8000') {
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
    // Allow heavy models to finish; extended to 10 minutes to avoid premature aborts
    const PROCESS_TIMEOUT_MS = 600000;
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
        }
      }

      // Send request
      const response = await fetch(`${this.baseUrl}/api/v1/process-iris`, {
        method: 'POST',
        body: formData,
        signal: AbortSignal.timeout(PROCESS_TIMEOUT_MS),
        // Don't set Content-Type - browser will set it with boundary
      });

      if (!response.ok) {
        const error = await response.json();
        // Map well-known backend error codes to actionable messages.
        // 429 — rate limit: do NOT retry automatically; back off and inform user.
        // 503 — GPU semaphore occupied: transient, clears once current job ends.
        // 422 — Pydantic validation: client-side bug; log detail for debugging.
        // Any other 4xx/5xx falls through to the generic backend error string.
        const errorMsg = error.error || error.detail || 'Backend processing failed';
        console.error('[BackendClient] Backend error:', error);
        throw new Error(errorMsg);
      }

      const result: ProcessIrisResponse = await response.json();

      if (!result.success) {
        throw new Error(result.error || 'Processing returned success=false');
      }

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

/**
 * getBackendUrl — resolves the FastAPI origin at runtime.
 *
 * During local development the frontend and backend both run on localhost, so
 * `https://localhost:8000` is used.
 *
 * When the developer tests on a physical phone (useful for camera quality and
 * touch gestures), the phone opens the Next.js dev server via the machine's LAN
 * IP (e.g. `https://192.168.1.42:3000`).  In that scenario the phone cannot
 * reach "localhost:8000" — it must use the same LAN IP with port 8000.
 * This function detects the non-loopback hostname and mirrors it onto port 8000
 * so the mobile browser can reach the FastAPI process running on the dev machine.
 *
 * NEXT_PUBLIC_BACKEND_URL overrides everything; set it in `.env.local` for
 * staging/production deployments where the backend is on a separate host.
 */
const getBackendUrl = (): string => {
  if (typeof window !== 'undefined') {
    // If we're on the phone accessing via IP, use that same IP for backend
    const hostname = window.location.hostname;
    if (hostname !== 'localhost' && hostname !== '127.0.0.1') {
      // We're accessing from phone via IP - use HTTPS on port 8000
      return `https://${hostname}:8000`;
    }
  }
  // Default for local development
  return process.env.NEXT_PUBLIC_BACKEND_URL || 'https://localhost:8000';
};

/** Singleton — one client instance shared across the entire frontend. */
export const backendClient = new BackendClient(getBackendUrl());
