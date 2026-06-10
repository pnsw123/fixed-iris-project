#!/usr/bin/env bash
# download_models.sh — Download publicly available model weights for Eyedentity.
#
# Downloads:
#   - sam_vit_b_01ec64.pth   (Meta SAM ViT-B base checkpoint)
#   - realesr-general-x4v3.pth  (Real-ESRGAN x4 upscaler)
#
# NOT downloaded (not yet publicly released):
#   - IrisSAM_model.pt — contact the maintainer or train your own.
#     See README.md § "3. Download AI Model Weights" for details.

set -euo pipefail

MODELS_DIR="$(cd "$(dirname "$0")/.." && pwd)/backend/models"

echo "→ Creating models directory at: $MODELS_DIR"
mkdir -p "$MODELS_DIR"

# ---------------------------------------------------------------------------
# 1. SAM ViT-B base checkpoint (Meta / Facebook Research)
#    Source: https://github.com/facebookresearch/segment-anything#model-checkpoints
# ---------------------------------------------------------------------------
SAM_URL="https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth"
SAM_FILE="$MODELS_DIR/sam_vit_b_01ec64.pth"

if [ -f "$SAM_FILE" ]; then
  echo "✓ sam_vit_b_01ec64.pth already exists — skipping."
else
  echo "↓ Downloading sam_vit_b_01ec64.pth (~375 MB) ..."
  curl -L --progress-bar -o "$SAM_FILE" "$SAM_URL"
  echo "✓ sam_vit_b_01ec64.pth downloaded."
fi

# ---------------------------------------------------------------------------
# 2. Real-ESRGAN x4v3 upscaler (xinntao)
#    Source: https://github.com/xinntao/Real-ESRGAN/releases
# ---------------------------------------------------------------------------
ESRGAN_URL="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth"
ESRGAN_FILE="$MODELS_DIR/realesr-general-x4v3.pth"

if [ -f "$ESRGAN_FILE" ]; then
  echo "✓ realesr-general-x4v3.pth already exists — skipping."
else
  echo "↓ Downloading realesr-general-x4v3.pth (~67 MB) ..."
  curl -L --progress-bar -o "$ESRGAN_FILE" "$ESRGAN_URL"
  echo "✓ realesr-general-x4v3.pth downloaded."
fi

# ---------------------------------------------------------------------------
# 3. IrisSAM fine-tuned weights (private — fetched only if a URL is provided)
#    Set IRIS_SAM_MODEL_URL to a reachable URL (e.g. a signed S3/R2 link) to
#    have the private weight downloaded automatically — used by the Render build
#    so the deployed backend can actually run the segmentation step.
# ---------------------------------------------------------------------------
IRIS_FILE="$MODELS_DIR/IrisSAM_model.pt"
if [ -f "$IRIS_FILE" ]; then
  echo "✓ IrisSAM_model.pt already exists — skipping."
elif [ -n "${IRIS_SAM_MODEL_URL:-}" ]; then
  echo "↓ Downloading IrisSAM_model.pt from IRIS_SAM_MODEL_URL ..."
  curl -L --fail --progress-bar -o "$IRIS_FILE" "$IRIS_SAM_MODEL_URL"
  echo "✓ IrisSAM_model.pt downloaded."
else
  echo "⚠  IRIS_SAM_MODEL_URL not set — IrisSAM_model.pt NOT downloaded."
  echo "   The backend will start but report unhealthy until this weight is present."
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Done. Models directory contents:"
ls -lh "$MODELS_DIR"
