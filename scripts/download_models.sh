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
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "Done. Models directory contents:"
ls -lh "$MODELS_DIR"
echo ""
echo "⚠  IrisSAM_model.pt is NOT publicly available and was NOT downloaded."
echo "   See README.md § '3. Download AI Model Weights' for how to obtain it."
