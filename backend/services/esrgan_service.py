"""Real-ESRGAN service for iris upscaling using ONNX Runtime."""

import numpy as np
import cv2
from typing import Optional
import onnxruntime as ort


class RealESRGANService:
    """Service for real-world super-resolution using Real-ESRGAN ONNX model."""

    def __init__(self, model_path: str, device: str = "mps", scale: int = 4):
        """
        Initialize Real-ESRGAN ONNX model.

        Args:
            model_path: Path to RealESRGAN ONNX model (e.g., realesrgan_x4.onnx)
            device: 'mps' (Apple Silicon), 'cuda', or 'cpu'
            scale: Upscale factor (2 or 4, default 4)
        """
        self.scale = scale
        self.device = device

        print(f"[RealESRGAN] Initializing ONNX model on device: {device}")
        print(f"[RealESRGAN] Loading model from {model_path}...")

        # Set up providers based on device
        providers = []
        if device == "cuda":
            providers.append("CUDAExecutionProvider")
        elif device == "mps":
            # ONNX Runtime doesn't support MPS yet, fallback to CoreML or CPU
            providers.append("CoreMLExecutionProvider")
        
        providers.append("CPUExecutionProvider")

        # Create ONNX Runtime session
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        
        try:
            self.session = ort.InferenceSession(
                model_path,
                sess_options=sess_options,
                providers=providers
            )
            
            # Get model input/output info
            self.input_name = self.session.get_inputs()[0].name
            self.output_name = self.session.get_outputs()[0].name
            
            actual_provider = self.session.get_providers()[0]
            print(f"[RealESRGAN] Model loaded successfully! (scale={scale}x, provider={actual_provider})")
            
        except Exception as e:
            print(f"[RealESRGAN] Error loading model: {str(e)}")
            raise

    def upscale(self, image: np.ndarray) -> np.ndarray:
        """
        Upscale image using Real-ESRGAN ONNX model.

        Args:
            image: RGB numpy array (H, W, 3), values 0-255

        Returns:
            Upscaled RGB numpy array (H*scale, W*scale, 3)
        """
        if len(image.shape) != 3 or image.shape[2] != 3:
            raise ValueError("Image must be RGB (H, W, 3)")

        try:
            # Preprocess: normalize to [0, 1] and convert to CHW format
            input_array = image.astype(np.float32) / 255.0
            input_array = np.transpose(input_array, (2, 0, 1))  # HWC -> CHW
            input_array = np.expand_dims(input_array, 0)  # Add batch dimension

            # Run inference
            outputs = self.session.run(
                [self.output_name],
                {self.input_name: input_array}
            )

            # Postprocess: convert back to HWC and denormalize
            output_array = outputs[0][0]  # Remove batch dimension
            output_array = np.transpose(output_array, (1, 2, 0))  # CHW -> HWC
            output_array = np.clip(output_array * 255.0, 0, 255).astype(np.uint8)

            return output_array

        except Exception as e:
            print(f"[RealESRGAN] Error during upscaling: {str(e)}")
            import traceback
            traceback.print_exc()
            # Return original image if upscaling fails
            return image

    def get_scale(self) -> int:
        """Get the upscale factor."""
        return self.scale
