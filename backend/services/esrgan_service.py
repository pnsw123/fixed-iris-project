"""Real-ESRGAN service for iris upscaling (supports PyTorch .pth and ONNX)."""

import logging
import numpy as np
import cv2
from typing import Optional
import torch
import onnxruntime as ort
import sys
import types
import os

logger = logging.getLogger(__name__)

# Shim for torchvision API changes: basicsr expects functional_tensor.rgb_to_grayscale
try:
    from torchvision.transforms import functional as _tv_f
    if "torchvision.transforms.functional_tensor" not in sys.modules:
        sys.modules["torchvision.transforms.functional_tensor"] = types.SimpleNamespace(
            rgb_to_grayscale=_tv_f.rgb_to_grayscale
        )
except Exception:
    pass

from realesrgan import RealESRGANer
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan.archs.srvgg_arch import SRVGGNetCompact


class RealESRGANService:
    """Service for real-world super-resolution using Real-ESRGAN."""

    def __init__(self, model_path: str, device: str = "mps", scale: int = 4):
        """
        Initialize Real-ESRGAN model.

        Args:
            model_path: Path to RealESRGAN model (.pth for PyTorch, .onnx for ONNX)
            device: 'mps' (Apple Silicon), 'cuda', or 'cpu'
            scale: Upscale factor (2 or 4, default 4)
        """
        self.scale = scale
        self.device = device
        self.model_path = model_path

        is_onnx = model_path.lower().endswith(".onnx")
        self.mode = "onnx" if is_onnx else "torch"

        if is_onnx:
            self._init_onnx(model_path, device, scale)
        else:
            self._init_torch(model_path, device, scale)

    def _init_torch(self, model_path: str, device: str, scale: int) -> None:
        """Initialize PyTorch Real-ESRGAN."""
        # Resolve device
        torch_device = torch.device("cpu")
        if device == "cuda" and torch.cuda.is_available():
            torch_device = torch.device("cuda")
        elif device == "mps" and torch.backends.mps.is_available():
            torch_device = torch.device("mps")

        half_precision = torch_device.type == "cuda"

        logger.info("Initializing PyTorch model on device: %s (half=%s)", torch_device, half_precision)
        logger.info("Loading model from %s", model_path)

        # Choose architecture based on checkpoint name
        model_basename = os.path.basename(model_path).lower()
        if "realesr-general-x4v3" in model_basename:
            # General v3 uses compact VGG-style network
            model = SRVGGNetCompact(
                num_in_ch=3,
                num_out_ch=3,
                num_feat=64,
                num_conv=32,
                upscale=scale,
                act_type="prelu",
            )
        else:
            # Default RRDBNet backbone used by Real-ESRGAN x4
            model = RRDBNet(
                num_in_ch=3,
                num_out_ch=3,
                num_feat=64,
                num_block=23,
                num_grow_ch=32,
                scale=scale,
            )

        self.upsampler = RealESRGANer(
            scale=scale,
            model_path=model_path,
            model=model,
            tile=0,
            tile_pad=10,
            pre_pad=0,
            half=half_precision,
            device=torch_device
        )

        logger.info("Model loaded successfully (scale=%dx, mode=PyTorch)", scale)

    def _init_onnx(self, model_path: str, device: str, scale: int) -> None:
        """Initialize ONNX Real-ESRGAN (legacy support)."""
        self.mode = "onnx"

        logger.info("Initializing ONNX model on device: %s", device)
        logger.info("Loading model from %s", model_path)

        providers = []
        if device == "cuda":
            providers.append("CUDAExecutionProvider")
        elif device == "mps":
            providers.append("CoreMLExecutionProvider")

        providers.append("CPUExecutionProvider")

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.session = ort.InferenceSession(
            model_path,
            sess_options=sess_options,
            providers=providers
        )

        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

        actual_provider = self.session.get_providers()[0]
        logger.info("Model loaded successfully (scale=%dx, provider=%s, mode=ONNX)", scale, actual_provider)

    def upscale(self, image: np.ndarray) -> np.ndarray:
        """
        Upscale image using Real-ESRGAN.

        Args:
            image: RGB numpy array (H, W, 3), values 0-255

        Returns:
            Upscaled RGB numpy array (H*scale, W*scale, 3)
        """
        if len(image.shape) != 3 or image.shape[2] != 3:
            raise ValueError("Image must be RGB (H, W, 3)")

        try:
            if self.mode == "onnx":
                return self._upscale_onnx(image)
            return self._upscale_torch(image)

        except Exception as e:
            logger.error("Error during upscaling: %s", e, exc_info=True)
            # Return original image if upscaling fails
            return image

    def _upscale_torch(self, image: np.ndarray) -> np.ndarray:
        """Upscale using PyTorch Real-ESRGANer (expects BGR)."""
        # RealESRGANer expects BGR np.uint8
        bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        output, _ = self.upsampler.enhance(bgr, outscale=self.scale)
        rgb_out = cv2.cvtColor(output, cv2.COLOR_BGR2RGB)
        return rgb_out

    def _upscale_onnx(self, image: np.ndarray) -> np.ndarray:
        """Upscale using ONNX Runtime (legacy)."""
        input_array = image.astype(np.float32) / 255.0
        input_array = np.transpose(input_array, (2, 0, 1))  # HWC -> CHW
        input_array = np.expand_dims(input_array, 0)  # Add batch dimension

        outputs = self.session.run(
            [self.output_name],
            {self.input_name: input_array}
        )

        output_array = outputs[0][0]  # Remove batch dimension
        output_array = np.transpose(output_array, (1, 2, 0))  # CHW -> HWC
        output_array = np.clip(output_array * 255.0, 0, 255).astype(np.uint8)
        return output_array

    def get_scale(self) -> int:
        """Get the upscale factor."""
        return self.scale
