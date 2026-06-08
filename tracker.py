"""
tracker.py
==========
YOLOv8 detection  +  lightweight ByteTrack-style IoU tracker
with Kalman-filter smoothing to eliminate jitter.
"""

import numpy as np
from collections import defaultdict
from scipy.optimize import linear_sum_assignment
from ultralytics import YOLO

# ── COCO classes likely to contain drones / UAVs ─────────────────
# 0=person(placeholder), 4=airplane, 14=bird, 33=kite, 35=skis
# We detect ALL classes by default and let the user filter —
# but for a drone-specific model the YOLO weights handle it.
_UAV_FALLBACK_CLASSES = None   # None = all classes

_IOU_THRESHOLD   = 0.20
_MAX_MISSING     = 30          # frames before track is dropped
_SMOOTH_ALPHA    = 0.55        # EMA for bbox smoothing (higher = snappier)


# ══════════════════════════════════════════════════════════════════
#  KALMAN-STYLE EXPONENTIAL SMOOTHER
# ══════════════════════════════════════════════════════════════════
class BBoxSmoother:
    def __init__(self, alpha=_SMOOTH_ALPHA):
        self.alpha = alpha
        self.state = None

    def update(self, bbox):
        bbox = np.array(bbox, dtype=np.float32)
        if self.state is None:
            self.state = bbox.copy()
        else:
            self.state = self.alpha * bbox + (1 - self.alpha) * self.state
        return tuple(self.state.astype(int))


# ══════════════════════════════════════════════════════════════════
#  TRACK OBJECT
# ══════════════════════════════════════════════════════════════════
class Track:
    _id_counter = 1

    def __init__(self, bbox, conf, cls_name, frame_idx):
        self.track_id   = Track._id_counter
        Track._id_counter += 1
        self.cls_name   = cls_name
        self.conf       = conf
        self.missing    = 0
        self.age        = 0
        self.frame_first = frame_idx
        self.smoother   = BBoxSmoother()
        self.bbox       = self.smoother.update(bbox)   # smoothed
        self.raw_bbox   = bbox
        self.velocity   = np.zeros(2, dtype=np.float32)
        self._prev_center = self._center(bbox)

    def update(self, bbox, conf, frame_idx):
        self.conf     = conf
        self.missing  = 0
        self.age     += 1
        self.raw_bbox = bbox
        self.bbox     = self.smoother.update(bbox)
        new_c = self._center(self.bbox)
        self.velocity = 0.7 * self.velocity + 0.3 * (np.array(new_c) - np.array(self._prev_center))
        self._prev_center = new_c

    def predict(self):
        """Predict next position using velocity (for occlusion bridging)."""
        if self.missing > 0 and self.missing <= _MAX_MISSING:
            x1,y1,x2,y2 = self.bbox
            dx,dy = int(self.velocity[0]), int(self.velocity[1])
            self.bbox = (x1+dx, y1+dy, x2+dx, y2+dy)
        self.missing += 1

    @staticmethod
    def _center(bbox):
        return ((bbox[0]+bbox[2])//2, (bbox[1]+bbox[3])//2)

    @property
    def center(self):
        return self._center(self.bbox)

    @property
    def dwell_frames(self):
        return self.age


# ══════════════════════════════════════════════════════════════════
#  IoU HELPER
# ══════════════════════════════════════════════════════════════════
def _iou(a, b):
    ax1,ay1,ax2,ay2 = a
    bx1,by1,bx2,by2 = b
    ix1,iy1 = max(ax1,bx1), max(ay1,by1)
    ix2,iy2 = min(ax2,bx2), min(ay2,by2)
    inter = max(0,ix2-ix1) * max(0,iy2-iy1)
    ua    = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
    return inter / (ua + 1e-6)


# ══════════════════════════════════════════════════════════════════
#  UAV TRACKER
# ══════════════════════════════════════════════════════════════════
class UAVTracker:
    def __init__(self, conf=0.25, class_filter=None, src_w=None, src_h=None):
        print("[TRACKER] Loading YOLOv8n model...")
        self.model        = YOLO("yolov8n.pt")
        self.conf         = conf
        # Default to detecting airplane (4), bird (14), kite (33), and cell phone (67)
        self.class_filter = class_filter if class_filter is not None else [4, 14, 33, 67]
        self.tracks: dict[int, Track] = {}
        self.src_w        = src_w
        self.src_h        = src_h

    # ── detection ─────────────────────────────────────────────────
    def _detect(self, frame):
        # Ensure cell phone (67) is included for anti-tamper malpractice screening
        cf = self.class_filter
        if cf is not None and 67 not in cf:
            cf = list(cf) + [67]

        results = self.model(frame, verbose=False, conf=self.conf,
                             classes=cf)
        raw_dets = []
        phones = []
        for r in results:
            for box in r.boxes:
                x1,y1,x2,y2 = map(int, box.xyxy[0])
                conf  = float(box.conf[0])
                cls_i = int(box.cls[0])
                name  = self.model.names.get(cls_i, f"obj{cls_i}")
                h, w  = frame.shape[:2]
                x1,y1 = max(0,x1), max(0,y1)
                x2,y2 = min(w-1,x2), min(h-1,y2)
                
                if x2 > x1+4 and y2 > y1+4:
                    if cls_i == 67:
                        phones.append((x1, y1, x2, y2))
                    else:
                        raw_dets.append({"bbox":(x1,y1,x2,y2),"conf":conf,"cls":name})

        # Anti-Tampering: Filter out drone candidates that overlap with cell phone screens (malpractice)
        # Also filter out detections inside the seeker zoom window (bottom-right corner) to prevent double detection
        dets = []
        h, w = frame.shape[:2]
        
        # Calculate seeker inset coordinates in resized frame if original dimensions are known
        ix_min, iy_min, ix_max, iy_max = -1, -1, -1, -1
        if self.src_w and self.src_h:
            ix_min = w - int(312 * w / self.src_w)
            iy_min = h - int(235 * h / self.src_h)
            ix_max = w - int(12 * w / self.src_w)
            iy_max = h - int(35 * h / self.src_h)

        for d in raw_dets:
            dx1, dy1, dx2, dy2 = d["bbox"]
            
            # Check cell phone malpractice
            is_malpractice = False
            for px1, py1, px2, py2 in phones:
                # Calculate bounding box overlap intersection
                ix1 = max(dx1, px1)
                iy1 = max(dy1, py1)
                ix2 = min(dx2, px2)
                iy2 = min(dy2, py2)
                if ix2 > ix1 and iy2 > iy1:
                    inter_area = (ix2 - ix1) * (iy2 - iy1)
                    drone_area = (dx2 - dx1) * (dy2 - dy1)
                    # If more than 20% of the drone bbox area overlaps the phone screen, reject it!
                    if inter_area / (drone_area + 1e-6) > 0.20:
                        is_malpractice = True
                        break
            
            if is_malpractice:
                print("\n[ANTI-TAMPER] Rejecting target: Mobile phone screen / playback malpractice detected!")
                continue # Skip this detection entirely (does not track)

            # Check overlap with seeker inset (zoom window)
            if ix_min != -1:
                ix1 = max(dx1, ix_min)
                iy1 = max(dy1, iy_min)
                ix2 = min(dx2, ix_max)
                iy2 = min(dy2, iy_max)
                
                # Check center of detection box
                cx = (dx1 + dx2) // 2
                cy = (dy1 + dy2) // 2
                is_inside_seeker = (ix_min <= cx <= ix_max) and (iy_min <= cy <= iy_max)
                
                if (ix2 > ix1 and iy2 > iy1) or is_inside_seeker:
                    inter_area = max(0, ix2 - ix1) * max(0, iy2 - iy1)
                    drone_area = (dx2 - dx1) * (dy2 - dy1)
                    # Reject if center is inside or if overlap area is > 30% of the drone bbox
                    if is_inside_seeker or (inter_area / (drone_area + 1e-6) > 0.30):
                        continue
                
            dets.append(d)
        return dets

    # ── tracking step ─────────────────────────────────────────────
    def update(self, frame, frame_idx):
        dets = self._detect(frame)

        # predict all existing tracks
        for t in self.tracks.values():
            t.predict()

        active = [t for t in self.tracks.values() if t.missing <= 1]

        if dets and active:
            cost = np.ones((len(active), len(dets)))
            for i, t in enumerate(active):
                for j, d in enumerate(dets):
                    cost[i,j] = 1.0 - _iou(t.bbox, d["bbox"])

            ri, ci = linear_sum_assignment(cost)
            matched_t, matched_d = set(), set()
            for r, c in zip(ri, ci):
                if cost[r,c] < (1.0 - _IOU_THRESHOLD):
                    active[r].update(dets[c]["bbox"], dets[c]["conf"], frame_idx)
                    matched_t.add(active[r].track_id)
                    matched_d.add(c)

            for j, d in enumerate(dets):
                if j not in matched_d:
                    t = Track(d["bbox"], d["conf"], d["cls"], frame_idx)
                    self.tracks[t.track_id] = t

        elif dets:
            for d in dets:
                t = Track(d["bbox"], d["conf"], d["cls"], frame_idx)
                self.tracks[t.track_id] = t

        # prune dead tracks
        self.tracks = {tid: t for tid, t in self.tracks.items()
                       if t.missing <= _MAX_MISSING}

        # return live tracks as list of dicts
        out = []
        for t in self.tracks.values():
            if t.missing == 0:
                out.append({
                    "id":       t.track_id,
                    "bbox":     t.bbox,
                    "conf":     t.conf,
                    "cls":      t.cls_name,
                    "center":   t.center,
                    "velocity": t.velocity.copy(),
                    "age":      t.age,
                })
        return out