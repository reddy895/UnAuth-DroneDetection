"""
utils.py
========
Utility helpers: directory creation, VideoWriter builder, frame resize.
"""

import cv2
import os
import numpy as np


def ensure_dir(path: str):
    """Create directory (and parents) if it doesn't exist."""
    if path:
        os.makedirs(path, exist_ok=True)


def build_writer(path: str, fps: float, width: int, height: int) -> cv2.VideoWriter:
    """Create a cv2.VideoWriter, trying mp4v then XVID codec as fallback."""
    ensure_dir(os.path.dirname(path) or ".")
    for codec in ("mp4v", "avc1", "XVID"):
        fourcc = cv2.VideoWriter_fourcc(*codec)
        writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
        if writer.isOpened():
            print(f"[WRITER] Codec: {codec}  →  {path}")
            return writer
        writer.release()
    raise RuntimeError(f"Could not open VideoWriter for: {path}")


def resize_frame(frame: np.ndarray, target_width: int) -> np.ndarray:
    """Resize frame preserving aspect ratio."""
    h, w = frame.shape[:2]
    if w <= target_width:
        return frame.copy()
    scale  = target_width / w
    new_h  = int(h * scale)
    return cv2.resize(frame, (target_width, new_h), interpolation=cv2.INTER_LINEAR)


def sharpen(img: np.ndarray, strength: float = 0.6) -> np.ndarray:
    """Apply unsharp mask sharpening."""
    blur   = cv2.GaussianBlur(img, (0,0), 3)
    return cv2.addWeighted(img, 1 + strength, blur, -strength, 0)


def iou(a, b) -> float:
    """Compute IoU between two bboxes (x1,y1,x2,y2)."""
    ax1,ay1,ax2,ay2 = a
    bx1,by1,bx2,by2 = b
    ix1,iy1 = max(ax1,bx1), max(ay1,by1)
    ix2,iy2 = min(ax2,bx2), min(ay2,by2)
    inter   = max(0,ix2-ix1) * max(0,iy2-iy1)
    union   = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
    return inter / (union + 1e-6)