"""
ui.py
=====
Military-style green HUD renderer.
Draws: crosshair reticle, bounding box, labels, trajectory,
       seeker zoom inset, telemetry panels, scan animation.
"""

import cv2
import numpy as np
import math
import datetime
from collections import deque

# ── Palette ───────────────────────────────────────────────────────
G_BRIGHT  = ( 57, 255,  20)   # neon green  (BGR)
G_MED     = ( 40, 180,  14)
G_DIM     = ( 20,  90,   7)
G_ACCENT  = (100, 255,  80)
BLACK     = (  0,   0,   0)
WHITE     = (255, 255, 255)
RED_LOCK  = (  0,  40, 220)   # BGR red-ish for "LOCKED" flash

_TRAJ_LEN = 60    # trajectory tail frames

# ── Font ──────────────────────────────────────────────────────────
FONT      = cv2.FONT_HERSHEY_SIMPLEX
FONT_MONO = cv2.FONT_HERSHEY_PLAIN


class HUDRenderer:
    def __init__(self, width: int, height: int, fps: float):
        self.w   = width
        self.h   = height
        self.fps = fps
        self.trajs: dict[int, deque] = {}   # track_id → deque of centers
        self._scan_angle = 0.0              # rotating scan line angle
        self._lock_flash = 0               # flash counter

    # ══════════════════════════════════════════════════════════════
    #  PUBLIC ENTRY
    # ══════════════════════════════════════════════════════════════
    def render(self, frame: np.ndarray, tracks: list,
               fidx: int, fps_live: float) -> np.ndarray:

        # darken frame slightly for CCTV feel
        frame = cv2.convertScaleAbs(frame, alpha=0.88, beta=-8)

        # green vignette overlay
        frame = self._vignette(frame)

        # update trajectories
        active_ids = {t["id"] for t in tracks}
        for tid in list(self.trajs.keys()):
            if tid not in active_ids:
                del self.trajs[tid]
        for t in tracks:
            if t["id"] not in self.trajs:
                self.trajs[t["id"]] = deque(maxlen=_TRAJ_LEN)
            self.trajs[t["id"]].append(t["center"])

        # pick primary target (highest conf)
        primary = max(tracks, key=lambda x: x["conf"]) if tracks else None

        # ── layers (back to front) ────────────────────────────────
        self._draw_grid(frame)
        self._draw_global_crosshair(frame)
        self._draw_scan_ring(frame, primary, fidx)

        for t in tracks:
            self._draw_trajectory(frame, t)
            self._draw_target_box(frame, t, primary)
            self._draw_reticle(frame, t)
            self._draw_target_label(frame, t)

        self._draw_left_panel(frame, primary, tracks, fidx)
        self._draw_right_panel(frame, fps_live, fidx)
        self._draw_bottom_bar(frame, primary, tracks)

        if primary:
            self._draw_seeker_inset(frame, frame.copy(), primary)

        self._draw_border(frame)
        self._scan_angle += 1.2

        return frame

    # ══════════════════════════════════════════════════════════════
    #  GRID BACKGROUND
    # ══════════════════════════════════════════════════════════════
    def _draw_grid(self, frame):
        step = 80
        for x in range(0, self.w, step):
            cv2.line(frame, (x,0), (x,self.h), G_DIM, 1)
        for y in range(0, self.h, step):
            cv2.line(frame, (0,y), (self.w,y), G_DIM, 1)
        # centre crosshair lines (full frame)
        cx, cy = self.w//2, self.h//2
        cv2.line(frame, (0,cy), (self.w,cy), (*G_DIM[:2], 25), 1)
        cv2.line(frame, (cx,0), (cx,self.h), (*G_DIM[:2], 25), 1)

    # ══════════════════════════════════════════════════════════════
    #  GLOBAL CROSSHAIR (thin, full-width)
    # ══════════════════════════════════════════════════════════════
    def _draw_global_crosshair(self, frame):
        cx, cy = self.w//2, self.h//2
        # dashed horizontal
        for x in range(0, self.w, 20):
            if (x // 20) % 2 == 0:
                cv2.line(frame, (x, cy), (min(x+14, self.w), cy), G_MED, 1)
        # dashed vertical
        for y in range(0, self.h, 20):
            if (y // 20) % 2 == 0:
                cv2.line(frame, (cx, y), (cx, min(y+14, self.h)), G_MED, 1)
        # centre dot
        cv2.circle(frame, (cx,cy), 3, G_BRIGHT, -1)

    # ══════════════════════════════════════════════════════════════
    #  SCAN / SEARCH RING  (rotates when no lock)
    # ══════════════════════════════════════════════════════════════
    def _draw_scan_ring(self, frame, primary, fidx):
        if primary:
            return   # hide when locked
        cx, cy = self.w//2, self.h//2
        r = min(self.w, self.h) // 4
        # faint base circle
        cv2.circle(frame, (cx,cy), r, G_DIM, 1)
        # rotating arc
        start = int(self._scan_angle) % 360
        cv2.ellipse(frame, (cx,cy), (r,r), 0, start, start+90, G_MED, 2)
        # SEARCHING text
        self._text(frame, "SEARCHING...", (cx-55, cy+r+20), G_MED, 0.42)

    # ══════════════════════════════════════════════════════════════
    #  TRAJECTORY TAIL
    # ══════════════════════════════════════════════════════════════
    def _draw_trajectory(self, frame, t):
        tid = t["id"]
        pts = list(self.trajs.get(tid, []))
        if len(pts) < 2:
            return
        for i in range(1, len(pts)):
            alpha = i / len(pts)
            col   = tuple(int(c*alpha) for c in G_BRIGHT)
            cv2.line(frame, pts[i-1], pts[i], col, 1, cv2.LINE_AA)
        # velocity arrow
        vx, vy = t["velocity"]
        if abs(vx) + abs(vy) > 0.5:
            cx, cy = t["center"]
            ex = int(cx + vx * 6)
            ey = int(cy + vy * 6)
            cv2.arrowedLine(frame, (cx,cy), (ex,ey), G_ACCENT, 1,
                            tipLength=0.4, line_type=cv2.LINE_AA)

    # ══════════════════════════════════════════════════════════════
    #  BOUNDING BOX  (corner-bracket style)
    # ══════════════════════════════════════════════════════════════
    def _draw_target_box(self, frame, t, primary):
        x1,y1,x2,y2 = t["bbox"]
        col  = G_BRIGHT if (primary and t["id"]==primary["id"]) else G_MED
        b    = max(12, (x2-x1)//4)

        # corner brackets
        for (cx,cy),(sx,sy) in [
            ((x1,y1),(1,1)),((x2,y1),(-1,1)),
            ((x1,y2),(1,-1)),((x2,y2),(-1,-1))
        ]:
            cv2.line(frame,(cx,cy),(cx+sx*b,cy),col,2,cv2.LINE_AA)
            cv2.line(frame,(cx,cy),(cx,cy+sy*b),col,2,cv2.LINE_AA)

        # faint full box
        overlay = frame.copy()
        cv2.rectangle(overlay,(x1,y1),(x2,y2),col,1)
        cv2.addWeighted(overlay,0.35,frame,0.65,0,frame)

        # size tick marks on sides
        mx, my = (x1+x2)//2, (y1+y2)//2
        cv2.line(frame,(mx-4,y1),(mx+4,y1),col,1)
        cv2.line(frame,(mx-4,y2),(mx+4,y2),col,1)
        cv2.line(frame,(x1,my-4),(x1,my+4),col,1)
        cv2.line(frame,(x2,my-4),(x2,my+4),col,1)

    # ══════════════════════════════════════════════════════════════
    #  RETICLE  (crosshair locked to target centre)
    # ══════════════════════════════════════════════════════════════
    def _draw_reticle(self, frame, t):
        cx, cy = t["center"]
        r_out, r_in = 22, 8

        # outer circle
        cv2.circle(frame,(cx,cy),r_out, G_BRIGHT, 1, cv2.LINE_AA)
        # inner gap cross
        for dx,dy in [(r_in,0),(- r_in,0),(0,r_in),(0,-r_in)]:
            ex = cx + (r_out-2)*np.sign(dx+dy*0.001) if dx!=0 else cx
            ey = cy + (r_out-2)*np.sign(dy+dx*0.001) if dy!=0 else cy
            sx = cx + dx; sy = cy + dy
            cv2.line(frame,(int(sx),int(sy)),(int(ex),int(ey)),G_BRIGHT,1,cv2.LINE_AA)

        # four outer tick lines
        for angle_deg in [0,90,180,270]:
            rad = math.radians(angle_deg)
            ix  = int(cx + math.cos(rad)*(r_out+2))
            iy  = int(cy + math.sin(rad)*(r_out+2))
            ox  = int(cx + math.cos(rad)*(r_out+12))
            oy  = int(cy + math.sin(rad)*(r_out+12))
            cv2.line(frame,(ix,iy),(ox,oy),G_BRIGHT,2,cv2.LINE_AA)

        # centre dot
        cv2.circle(frame,(cx,cy),2,G_BRIGHT,-1)

    # ══════════════════════════════════════════════════════════════
    #  TARGET LABEL
    # ══════════════════════════════════════════════════════════════
    def _draw_target_label(self, frame, t):
        x1,y1,x2,y2 = t["bbox"]
        tid   = t["id"]
        conf  = t["conf"]
        label = f"UAV {tid:02d} | {conf*100:.0f}%"

        lx = x1
        ly = y1 - 8
        if ly < 16:
            ly = y2 + 16

        (tw,th),_ = cv2.getTextSize(label, FONT, 0.44, 1)
        cv2.rectangle(frame,(lx-2,ly-th-3),(lx+tw+4,ly+2),(0,0,0),-1)
        cv2.rectangle(frame,(lx-2,ly-th-3),(lx+tw+4,ly+2),G_MED,1)
        cv2.putText(frame, label, (lx+1,ly-1), FONT, 0.44, G_BRIGHT, 1, cv2.LINE_AA)

        # coord tag below box
        cx,cy = t["center"]
        coord = f"XY {cx},{cy}"
        self._text(frame, coord, (x1, y2+14), G_MED, 0.36)

    # ══════════════════════════════════════════════════════════════
    #  LEFT TELEMETRY PANEL
    # ══════════════════════════════════════════════════════════════
    def _draw_left_panel(self, frame, primary, tracks, fidx):
        x0, y0 = 10, 10
        pw, ph  = 220, 140
        self._panel(frame, x0, y0, pw, ph)

        n_tgt = len(tracks)
        conf_str = f"{primary['conf']*100:.0f}%" if primary else "--"
        size_str = "--"
        pos_str  = "--"
        if primary:
            bx1,by1,bx2,by2 = primary["bbox"]
            size_str = f"{bx2-bx1}x{by2-by1}px"
            cx,cy    = primary["center"]
            pos_str  = f"{cx},{cy}"

        lines = [
            ("TARGET SELECTOR",  G_BRIGHT, 0.38, True),
            (f"Targets : {n_tgt:02d}", G_ACCENT, 0.38, False),
            ("", None, 0, False),
            ("TARGET TRACKING",  G_BRIGHT, 0.38, True),
            (f"ID      : {primary['id']:02d}" if primary else "ID      : --", G_ACCENT, 0.38, False),
            (f"Conf    : {conf_str}",  G_ACCENT, 0.38, False),
            (f"Size    : {size_str}",  G_ACCENT, 0.38, False),
            (f"Pos XY  : {pos_str}",   G_ACCENT, 0.38, False),
        ]

        yy = y0 + 14
        for text, col, scale, bold in lines:
            if text == "":
                yy += 4
                continue
            if col:
                t = 1 if not bold else 1
                cv2.putText(frame, text, (x0+8, yy), FONT, scale, col, t, cv2.LINE_AA)
            yy += 16

    # ══════════════════════════════════════════════════════════════
    #  RIGHT TELEMETRY PANEL
    # ══════════════════════════════════════════════════════════════
    def _draw_right_panel(self, frame, fps_live, fidx):
        pw, ph = 210, 130
        x0     = self.w - pw - 10
        y0     = 10
        self._panel(frame, x0, y0, pw, ph)

        now     = datetime.datetime.utcnow()
        ts      = now.strftime("%H:%M:%S UTC")
        elapsed = fidx / max(self.fps, 1)

        lines = [
            f"Source   : VIDEO",
            f"Seeker   : EO",
            f"Tracker  : ByteTrack",
            f"Model    : YOLOv8n",
            f"",
            f"TRACKED  FPS",
            f"FPS      : {fps_live:5.1f}",
            f"Time     : {ts}",
        ]

        yy = y0 + 14
        for line in lines:
            if line == "":
                yy += 4; continue
            col = G_BRIGHT if "FPS" in line or "Time" in line else G_ACCENT
            cv2.putText(frame, line, (x0+8, yy), FONT, 0.36, col, 1, cv2.LINE_AA)
            yy += 16

    # ══════════════════════════════════════════════════════════════
    #  BOTTOM STATUS BAR
    # ══════════════════════════════════════════════════════════════
    def _draw_bottom_bar(self, frame, primary, tracks):
        bh  = 28
        y0  = self.h - bh
        overlay = frame.copy()
        cv2.rectangle(overlay, (0,y0), (self.w,self.h), (0,0,0), -1)
        cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)
        cv2.line(frame, (0,y0), (self.w,y0), G_MED, 1)

        status = "SENSOR MODE: EO"
        cv2.putText(frame, status, (self.w//2-70, y0+17),
                    FONT, 0.44, G_BRIGHT, 1, cv2.LINE_AA)

        # lock status left
        lock_str = "[ STATUS: LOCKED ]" if primary else "[ STATUS: SEARCHING ]"
        lock_col = G_BRIGHT if primary else G_MED
        cv2.putText(frame, lock_str, (12, y0+17), FONT, 0.40, lock_col, 1, cv2.LINE_AA)

        # keys right
        keys = "Target:Q | Lock:C | Cancel:V | Mode:H"
        cv2.putText(frame, keys, (self.w-310, y0+17), FONT, 0.36, G_DIM, 1, cv2.LINE_AA)

    # ══════════════════════════════════════════════════════════════
    #  SEEKER ZOOM INSET  (bottom-right)
    # ══════════════════════════════════════════════════════════════
    def _draw_seeker_inset(self, frame, src_frame, primary):
        iw, ih = 300, 200
        ix     = self.w - iw - 12
        iy     = self.h - ih - 35

        x1,y1,x2,y2 = primary["bbox"]
        pad  = max(20, (x2-x1)//3)
        sx1  = max(0, x1-pad); sy1 = max(0, y1-pad)
        sx2  = min(self.w-1, x2+pad); sy2 = min(self.h-1, y2+pad)

        crop = src_frame[sy1:sy2, sx1:sx2]
        if crop.size == 0:
            return

        # resize to inset
        crop = cv2.resize(crop, (iw, ih), interpolation=cv2.INTER_LINEAR)

        # sharpen
        kernel = np.array([[0,-0.5,0],[-0.5,3,-0.5],[0,-0.5,0]], dtype=np.float32)
        crop   = cv2.filter2D(crop, -1, kernel)

        # green tint
        tint = np.zeros_like(crop)
        tint[:,:,1] = 25
        crop = cv2.add(crop, tint)

        # paste
        frame[iy:iy+ih, ix:ix+iw] = crop

        # inset border + label
        cv2.rectangle(frame, (ix-1,iy-1), (ix+iw+1,iy+ih+1), G_BRIGHT, 2)
        # corner brackets on inset
        b = 10
        for (cx,cy),(sx,sy) in [
            ((ix,iy),(1,1)),((ix+iw,iy),(-1,1)),
            ((ix,iy+ih),(1,-1)),((ix+iw,iy+ih),(-1,-1))
        ]:
            cv2.line(frame,(cx,cy),(cx+sx*b,cy),G_BRIGHT,2)
            cv2.line(frame,(cx,cy),(cx,cy+sy*b),G_BRIGHT,2)

        # reticle centre on inset
        mcx, mcy = ix+iw//2, iy+ih//2
        cv2.circle(frame,(mcx,mcy),12,G_BRIGHT,1)
        cv2.line(frame,(mcx-18,mcy),(mcx-13,mcy),G_BRIGHT,1)
        cv2.line(frame,(mcx+13,mcy),(mcx+18,mcy),G_BRIGHT,1)
        cv2.line(frame,(mcx,mcy-18),(mcx,mcy-13),G_BRIGHT,1)
        cv2.line(frame,(mcx,mcy+13),(mcx,mcy+18),G_BRIGHT,1)
        cv2.circle(frame,(mcx,mcy),2,G_BRIGHT,-1)

        # label above inset
        lbl_y = iy - 6
        self._panel_line(frame, "SEEKER VIEW", ix, lbl_y, G_BRIGHT, 0.42)

    # ══════════════════════════════════════════════════════════════
    #  BORDER / FRAME DECORATION
    # ══════════════════════════════════════════════════════════════
    def _draw_border(self, frame):
        bw = 3
        cv2.rectangle(frame,(0,0),(self.w-1,self.h-1), G_DIM, bw)
        # corner L-brackets (outer)
        b = 30
        for (cx,cy),(sx,sy) in [
            ((0,0),(1,1)),((self.w-1,0),(-1,1)),
            ((0,self.h-1),(1,-1)),((self.w-1,self.h-1),(-1,-1))
        ]:
            cv2.line(frame,(cx,cy),(cx+sx*b,cy),G_BRIGHT,2)
            cv2.line(frame,(cx,cy),(cx,cy+sy*b),G_BRIGHT,2)

    # ══════════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════════
    def _panel(self, frame, x, y, w, h):
        overlay = frame.copy()
        cv2.rectangle(overlay,(x,y),(x+w,y+h),(0,0,0),-1)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
        cv2.rectangle(frame,(x,y),(x+w,y+h),G_MED,1)
        b = 8
        for (cx,cy),(sx,sy) in [
            ((x,y),(1,1)),((x+w,y),(-1,1)),
            ((x,y+h),(1,-1)),((x+w,y+h),(-1,-1))
        ]:
            cv2.line(frame,(cx,cy),(cx+sx*b,cy),G_BRIGHT,1)
            cv2.line(frame,(cx,cy),(cx,cy+sy*b),G_BRIGHT,1)

    def _vignette(self, frame):
        h,w = frame.shape[:2]
        Y,X = np.ogrid[:h,:w]
        cx,cy = w//2, h//2
        mask = 1.0 - 0.55*((X-cx)**2/(cx**2) + (Y-cy)**2/(cy**2)).clip(0,1)
        mask = mask[:,:,None].astype(np.float32)
        return (frame.astype(np.float32) * mask).clip(0,255).astype(np.uint8)

    def _text(self, frame, text, pos, col, scale=0.40):
        cv2.putText(frame, text, pos, FONT, scale, col, 1, cv2.LINE_AA)

    def _panel_line(self, frame, text, x, y, col, scale):
        (tw,th),_ = cv2.getTextSize(text, FONT, scale, 1)
        cv2.rectangle(frame,(x-1,y-th-3),(x+tw+3,y+2),(0,0,0),-1)
        cv2.rectangle(frame,(x-1,y-th-3),(x+tw+3,y+2),G_MED,1)
        cv2.putText(frame, text, (x+1,y-1), FONT, scale, col, 1, cv2.LINE_AA)