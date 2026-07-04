"""Hardware detection and model-tier recommendation."""

import os


def detect_device():
    """Returns (device, compute_type) for the CTranslate2 backend.
    NVIDIA GPU -> ("cuda", "float16"); otherwise CPU with int8 quantization
    (fastest CPU mode with negligible accuracy impact)."""
    override = os.environ.get("SHABD_DEVICE", "").strip().lower()
    if override in ("cuda", "cpu"):
        return ("cuda", "float16") if override == "cuda" else ("cpu", "int8")
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return ("cuda", "float16")
    except Exception:
        pass
    return ("cpu", "int8")


def cpu_threads():
    return max(1, os.cpu_count() or 4)


def recommend_tier():
    """Best default accuracy tier this machine can run at a tolerable speed."""
    device, _ = detect_device()
    if device == "cuda":
        return "max"
    if cpu_threads() >= 4:
        return "high"
    return "balanced"


def describe():
    device, compute = detect_device()
    if device == "cuda":
        return "NVIDIA GPU detected — using GPU (float16). All tiers are fast."
    return ("Running on CPU with %d threads (int8). Higher tiers are more "
            "accurate but slower." % cpu_threads())
