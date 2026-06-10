"""
conftest.py — session-scoped sys.modules stubs for heavy ML packages.

Problem (issue #148):
    Importing ``app.py`` triggers the ML import chain:
        esrgan_service → realesrgan → basicsr → scipy
    On machines where scipy/numpy ABI versions differ this raises:
        ValueError: numpy.dtype size changed, may indicate binary incompatibility

    unittest.mock.patch() resolves its target *after* the module is imported,
    so by the time ``_make_app()`` patches ``app.IrisSAMService`` the damage is
    already done — scipy has already tried and failed to load.

Fix:
    Insert lightweight ``MagicMock`` stubs into ``sys.modules`` for every heavy
    ML package *before* pytest collects any test file that imports ``app``.
    conftest.py at the package root is the earliest possible hook.

Limiter reset (issue #148 / #126):
    ``rate_limit.limiter`` is a module-level singleton backed by ``MemoryStorage``.
    Rate-hit counts from one test bleed into subsequent tests in the same
    session.  The autouse fixture below calls ``limiter.reset()`` before each
    test so every test starts from a clean slate.
"""

import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub out heavy ML packages before any test (or app module) imports them.
# This block runs at collection time, before any test file is imported.
# ---------------------------------------------------------------------------

_ML_STUBS: list[str] = [
    # OpenCV
    "cv2",
    # PyTorch
    "torch",
    "torch.nn",
    "torch.nn.functional",
    "torch.cuda",
    "torch.optim",
    "torch.utils",
    "torch.utils.data",
    # Torchvision
    "torchvision",
    "torchvision.transforms",
    "torchvision.transforms.functional",
    "torchvision.transforms.functional_tensor",
    # ONNX Runtime
    "onnxruntime",
    # Segment Anything
    "segment_anything",
    "segment_anything.modeling",
    # basicsr (used by realesrgan)
    "basicsr",
    "basicsr.archs",
    "basicsr.archs.rrdbnet_arch",
    "basicsr.utils",
    "basicsr.utils.registry",
    # Real-ESRGAN
    "realesrgan",
    "realesrgan.archs",
    "realesrgan.archs.srvgg_arch",
]

for _mod in _ML_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# ---------------------------------------------------------------------------
# Autouse fixture — reset the rate-limiter before every test.
# ---------------------------------------------------------------------------

import pytest  # noqa: E402 (import after sys.modules manipulation)
from rate_limit import limiter  # noqa: E402


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset in-memory rate-limit counters before each test.

    Without this, counts accumulated in one test (e.g. the 6-request quota
    exhaustion test) bleed into subsequent tests and cause spurious 429s.
    """
    limiter.reset()
    yield
    # No teardown needed — next test resets again before running.
