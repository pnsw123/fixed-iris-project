/*
 * Super Resolution Service
 * Service layer for Real-ESRGAN ONNX Runtime worker
 * Manages worker lifecycle, message passing, and request tracking
 */

type UpscaleResult = {
    width: number;
    height: number;
    rgba: Uint8ClampedArray;
};

type MessageHandler = {
    resolve: (value: UpscaleResult) => void;
    reject: (reason: any) => void;
};

export class SuperResService {
    private static instance: SuperResService;
    private worker: Worker | null = null;
    private readyPromise: Promise<void> | null = null;
    private resolvers = new Map<string, MessageHandler>();
    private nextId = 0;

    private constructor() { }

    public static getInstance(): SuperResService {
        if (!SuperResService.instance) {
            SuperResService.instance = new SuperResService();
        }
        return SuperResService.instance;
    }

    /**
     * Initialize worker and wait for READY signal
     */
    public async initialize(): Promise<void> {
        if (this.worker && this.readyPromise) {
            return this.readyPromise; // Already initializing or initialized
        }

        console.log('[SuperResService] Initializing ONNX Runtime worker...');

        this.readyPromise = new Promise((resolve, reject) => {
            // Create worker
            this.worker = new Worker(
                new URL('../workers/upscaler.worker.ts', import.meta.url)
            );

            // Set up message handler
            this.worker.onmessage = (ev: MessageEvent) => {
                const msg = ev.data;

                if (msg.type === 'READY') {
                    console.log('[SuperResService] Worker is READY');
                    resolve();
                } else if (msg.type === 'FATAL_INIT_ERROR') {
                    console.error('[SuperResService] Worker failed to initialize:', msg.error);
                    reject(new Error(`Worker initialization failed: ${msg.error}`));
                } else if (msg.type === 'UPSCALE_DONE') {
                    const { requestId, width, height, buffer } = msg;
                    const handler = this.resolvers.get(requestId);

                    if (handler) {
                        this.resolvers.delete(requestId);
                        handler.resolve({
                            width,
                            height,
                            rgba: new Uint8ClampedArray(buffer),
                        });
                    }
                } else if (msg.type === 'ERROR') {
                    const { requestId, error } = msg;
                    const handler = this.resolvers.get(requestId);

                    if (handler) {
                        this.resolvers.delete(requestId);
                        handler.reject(new Error(error));
                    }
                }
            };

            // Handle worker errors
            this.worker.onerror = (error) => {
                console.error('[SuperResService] Worker error:', error);
                reject(new Error('Worker crashed'));
            };
        });

        await this.readyPromise;
        console.log('[SuperResService] Initialization complete');
    }

    /**
     * Upscale a canvas using Real-ESRGAN
     */
    public async upscaleCanvas(canvas: HTMLCanvasElement): Promise<UpscaleResult> {
        // Ensure worker is initialized
        if (!this.worker || !this.readyPromise) {
            await this.initialize();
        }

        if (!this.worker) {
            throw new Error('Worker not initialized');
        }

        const width = canvas.width;
        const height = canvas.height;

        console.log(`[SuperResService] Upscaling ${width}×${height} image...`);

        // Extract RGBA data from canvas
        const ctx = canvas.getContext('2d');
        if (!ctx) {
            throw new Error('Failed to get 2D context');
        }

        const imageData = ctx.getImageData(0, 0, width, height);
        const rgba = imageData.data; // Uint8ClampedArray

        // Generate unique request ID
        const requestId = `req-${this.nextId++}`;

        // Create promise for this request
        const resultPromise = new Promise<UpscaleResult>((resolve, reject) => {
            this.resolvers.set(requestId, { resolve, reject });

            // Send upscale request with transferable buffer
            this.worker!.postMessage(
                {
                    type: 'UPSCALE',
                    width,
                    height,
                    buffer: rgba.buffer,
                    requestId,
                },
                [rgba.buffer] // Transfer buffer to worker
            );
        });

        return resultPromise;
    }

    /**
     * Legacy API - kept for compatibility
     * Now just wraps upscaleCanvas
     */
    public async enhance(input: HTMLCanvasElement | string): Promise<string | null> {
        try {
            const canvas = typeof input === 'string'
                ? await this.loadImageToCanvas(input)
                : input;

            const result = await this.upscaleCanvas(canvas);

            // Convert result to data URL
            const outputCanvas = document.createElement('canvas');
            outputCanvas.width = result.width;
            outputCanvas.height = result.height;

            const ctx = outputCanvas.getContext('2d');
            if (!ctx) return null;

            const outputImageData = new ImageData(
                new Uint8ClampedArray(result.rgba),
                result.width,
                result.height
            );
            ctx.putImageData(outputImageData, 0, 0);

            return outputCanvas.toDataURL('image/png');
        } catch (error) {
            console.error('[SuperResService] Enhancement failed:', error);
            return null;
        }
    }

    /**
     * Legacy API - multi-stage support removed (ONNX does single pass)
     */
    public async enhanceMultiStage(
        input: HTMLCanvasElement | string,
        stages: number = 1,
        onProgress?: (stage: number, total: number) => void
    ): Promise<string | null> {
        // Ignore stages parameter - ONNX does single inference
        if (onProgress) {
            onProgress(1, 1);
        }
        return this.enhance(input);
    }

    /**
     * Helper: Load image from data URL to canvas
     */
    private async loadImageToCanvas(dataUrl: string): Promise<HTMLCanvasElement> {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => {
                const canvas = document.createElement('canvas');
                canvas.width = img.width;
                canvas.height = img.height;
                const ctx = canvas.getContext('2d');
                if (!ctx) {
                    reject(new Error('Failed to get context'));
                    return;
                }
                ctx.drawImage(img, 0, 0);
                resolve(canvas);
            };
            img.onerror = () => reject(new Error('Failed to load image'));
            img.src = dataUrl;
        });
    }

    /**
     * Cleanup
     */
    public destroy() {
        if (this.worker) {
            this.worker.terminate();
            this.worker = null;
            this.readyPromise = null;
            this.resolvers.clear();
        }
    }
}

// Singleton instance
const srService = SuperResService.getInstance();
export default srService;
