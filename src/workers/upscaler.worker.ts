/// <reference lib="webworker" />

/*
 * Real-ESRGAN ONNX Runtime Web Worker
 * Replaces broken UpscalerJS with direct ONNX model inference
 * Privacy-first: 100% local processing, no API calls
 */

import * as ort from 'onnxruntime-web';

// Configure ONNX Runtime to use correct WASM paths with absolute URL
// In worker context, we need to resolve relative to the origin
ort.env.wasm.wasmPaths = `${self.location.origin}/wasm/`;

// Worker context
const ctx: DedicatedWorkerGlobalScope = self as DedicatedWorkerGlobalScope;

// Configuration - Use absolute URL for model path in worker context
const MODEL_PATH = `${self.location.origin}/models/iris-esrgan/realesrgan_x4.onnx`;

// State
let session: ort.InferenceSession | null = null;
let ready = false;

/**
 * Initialize ONNX Runtime session
 */
async function init() {
    try {
        console.log('[worker] Initializing ONNX Runtime...');
        console.log('[worker] Loading model from:', MODEL_PATH);

        // Create inference session with execution providers
        // WebGL for GPU acceleration, fallback to WASM
        session = await ort.InferenceSession.create(MODEL_PATH, {
            executionProviders: ['webgl', 'wasm'],
        });

        console.log('[worker] ONNX session created successfully');
        console.log('[worker] Model inputs:', session.inputNames);
        console.log('[worker] Model outputs:', session.outputNames);
        console.log('[worker] Execution providers:', session.inputNames);

        ready = true;
        ctx.postMessage({ type: 'READY' });

    } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        console.error('[worker] FATAL_INIT_ERROR:', errorMessage);

        ctx.postMessage({
            type: 'FATAL_INIT_ERROR',
            error: errorMessage,
        });
    }
}

/**
 * Convert RGBA Uint8ClampedArray to NCHW Float32Array (0-1 range)
 * 
 * Input: RGBA interleaved [r,g,b,a, r,g,b,a, ...]
 * Output: NCHW planar [all_R, all_G, all_B]
 */
function rgbaToNchwFloat32(
    data: Uint8ClampedArray,
    width: number,
    height: number
): Float32Array {
    const [C, H, W] = [3, height, width];
    const out = new Float32Array(1 * C * H * W); // N=1

    // NCHW strides
    const strideC = H * W;
    const strideH = W;

    for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
            const rgbaIdx = (y * W + x) * 4;

            // Normalize to 0-1 range
            const r = data[rgbaIdx] / 255;
            const g = data[rgbaIdx + 1] / 255;
            const b = data[rgbaIdx + 2] / 255;

            // NCHW layout: [batch, channel, height, width]
            const base = y * strideH + x;
            out[0 * strideC + base] = r; // R channel
            out[1 * strideC + base] = g; // G channel
            out[2 * strideC + base] = b; // B channel
        }
    }

    return out;
}

/**
 * Convert NCHW Float32Array to RGBA Uint8ClampedArray
 * 
 * Input: NCHW planar [all_R, all_G, all_B]
 * Output: RGBA interleaved [r,g,b,a, r,g,b,a, ...]
 */
function nchwFloat32ToRgba(
    outData: Float32Array,
    outWidth: number,
    outHeight: number
): Uint8ClampedArray {
    const [, H, W] = [3, outHeight, outWidth]; // C is always 3 for RGB
    const rgba = new Uint8ClampedArray(W * H * 4);

    // NCHW strides
    const strideC = H * W;
    const strideH = W;

    for (let y = 0; y < H; y++) {
        for (let x = 0; x < W; x++) {
            const base = y * strideH + x;

            // Extract and clamp RGB values
            let r = outData[0 * strideC + base];
            let g = outData[1 * strideC + base];
            let b = outData[2 * strideC + base];

            // Clamp to [0, 1] range (model might output slightly out of range)
            r = Math.min(Math.max(r, 0), 1);
            g = Math.min(Math.max(g, 0), 1);
            b = Math.min(Math.max(b, 0), 1);

            // Denormalize to 0-255 and set RGBA
            const idx = (y * W + x) * 4;
            rgba[idx] = r * 255;
            rgba[idx + 1] = g * 255;
            rgba[idx + 2] = b * 255;
            rgba[idx + 3] = 255; // Full opacity
        }
    }

    return rgba;
}

/**
 * Message handler
 */
ctx.addEventListener('message', async (event) => {
    const msg = event.data;

    if (msg.type === 'UPSCALE') {
        // Check if worker is ready
        if (!ready || !session) {
            console.error('[worker] Session not ready');
            ctx.postMessage({
                type: 'ERROR',
                error: 'SESSION_NOT_READY',
                requestId: msg.requestId,
            });
            return;
        }

        const { width, height, buffer, requestId } = msg;

        try {
            console.log(`[worker] Processing upscale request ${requestId}`);
            console.log(`[worker] Input size: ${width}×${height}`);

            const t0 = performance.now();

            // Convert input buffer to NCHW tensor
            const rgba = new Uint8ClampedArray(buffer);
            const inputData = rgbaToNchwFloat32(rgba, width, height);

            console.log(`[worker] Input tensor shape: [1, 3, ${height}, ${width}]`);

            // Create ONNX tensor
            const inputTensor = new ort.Tensor('float32', inputData, [1, 3, height, width]);

            // Prepare feeds (use actual input name from model)
            const inputName = session.inputNames[0];
            const feeds: Record<string, ort.Tensor> = {
                [inputName]: inputTensor,
            };

            // Run inference
            console.log('[worker] Running inference...');
            const results = await session.run(feeds);

            const inferenceTime = performance.now() - t0;
            console.log(`[worker] Inference completed in ${inferenceTime.toFixed(0)}ms`);

            // Extract output tensor
            const outputName = session.outputNames[0];
            const outputTensor = results[outputName];
            const [n, c, outH, outW] = outputTensor.dims;
            const outData = outputTensor.data as Float32Array;

            console.log(`[worker] Output tensor shape: [${n}, ${c}, ${outH}, ${outW}]`);

            // Convert back to RGBA
            const outRgba = nchwFloat32ToRgba(outData, outW, outH);

            const totalTime = performance.now() - t0;
            console.log(`[worker] Total processing time: ${totalTime.toFixed(0)}ms`);

            // Send result with transferable buffer
            ctx.postMessage(
                {
                    type: 'UPSCALE_DONE',
                    width: outW,
                    height: outH,
                    buffer: outRgba.buffer,
                    requestId,
                },
                [outRgba.buffer] // Transfer ownership to avoid copying
            );

        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : String(error);
            console.error('[worker] UPSCALE_ERROR:', errorMessage, error);

            ctx.postMessage({
                type: 'ERROR',
                error: errorMessage,
                requestId: msg.requestId,
            });
        }
    }
});

// Initialize on worker load
console.log('[worker] Real-ESRGAN worker script loaded');
init();
