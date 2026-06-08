"""
Real-Time UAV Tracking System
==============================
Fixed for Python 3.11 / 3.12 / 3.13 / 3.14 virtual environments.

Usage:
    python main.py --source video.mp4
    python main.py --source video.mp4 --output outputs/output.mp4
"""

# ══════════════════════════════════════════════════════════════════
#  AUTO-INSTALL + SELF-RESTART
# ══════════════════════════════════════════════════════════════════
import subprocess, sys, os

_FLAG = "__UAV_READY__"

def _pip(*pkgs, **kw):
    """pip install with visible output so errors are clear."""
    cmd = [sys.executable, "-m", "pip", "install",
           "--no-warn-script-location", *pkgs]
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0 and not kw.get("optional"):
        print(f"[WARN] pip returned non-zero for: {pkgs} — continuing anyway")

if _FLAG not in os.environ:
    print("╔══════════════════════════════════════════════════════╗")
    print("║   UAV TRACKER — Installing packages, please wait...  ║")
    print("╚══════════════════════════════════════════════════════╝")

    py = sys.version_info
    print(f"[INFO] Python {py.major}.{py.minor}.{py.micro}  →  {sys.executable}\n")

    # 1. opencv + requests (always safe)
    print("[1/3] Installing opencv-python + scipy + requests...")
    _pip("opencv-python", "scipy", "requests", "-q")

    # 2. ultralytics pulls in torch automatically at the right version
    print("[2/3] Installing ultralytics (auto-installs compatible torch)...")
    _pip("ultralytics", "-q")

    # 3. verify torch imports cleanly; if not, try upgrading
    print("[3/3] Verifying torch + numpy compatibility...")
    check = subprocess.run(
        [sys.executable, "-c", "import torch, numpy; print('OK', torch.__version__, numpy.__version__)"],
        capture_output=True, text=True
    )
    if "OK" in check.stdout:
        print(f"      torch + numpy: {check.stdout.strip()}")
    else:
        print(f"      [WARN] {check.stderr.strip()[:200]}")
        print("      Trying: pip install --upgrade torch numpy ultralytics...")
        _pip("--upgrade", "torch", "numpy", "ultralytics", "-q", optional=True)

    print("\n[OK] Setup complete — restarting with clean environment...\n")
    env = os.environ.copy()
    env[_FLAG] = "1"
    sys.exit(subprocess.run([sys.executable] + sys.argv, env=env).returncode)

# ══════════════════════════════════════════════════════════════════
#  REAL IMPORTS
# ══════════════════════════════════════════════════════════════════
import warnings
warnings.filterwarnings("ignore")

import cv2
import argparse
import time

from tracker import UAVTracker
from ui      import HUDRenderer
from utils   import ensure_dir, build_writer, resize_frame
import config


def send_whatsapp_alert(target_count, frame=None):
    if not config.ENABLE_WHATSAPP:
        return
    try:
        import requests
        import cv2
        import base64
        
        # Verify number isn't placeholder
        if "your_recipient_number" in config.WHATSAPP_TO_NUMBER:
            print("\n[WARN] Recipient number is not configured in config.py. Skipping WhatsApp alert.")
            return

        payload = {
            "to": config.WHATSAPP_TO_NUMBER,
            "message": f"⚠️ UAV/Drone Alert! {target_count} drone(s) detected in real-time tracker."
        }
        
        if frame is not None:
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ret:
                img_base64 = base64.b64encode(buffer).decode('utf-8')
                payload["image"] = f"data:image/jpeg;base64,{img_base64}"
                
        response = requests.post(config.WHATSAPP_SERVER_URL, json=payload, timeout=5)
        if response.status_code == 200:
            print(f"\n[WHATSAPP] Alert message sent successfully to {config.WHATSAPP_TO_NUMBER}!")
        else:
            print(f"\n[WHATSAPP_ERROR] Server returned status code {response.status_code}: {response.text}")
    except Exception as e:
        print(f"\n[WHATSAPP_ERROR] Failed to send WhatsApp message: {e}")


def main():
    ap = argparse.ArgumentParser(description="Real-Time UAV Tracking System")
    ap.add_argument("--source",  default=None,  help="Input video path or camera index (optional)")
    ap.add_argument("--output",  default="outputs/output.mp4")
    ap.add_argument("--conf",    type=float, default=0.20)
    ap.add_argument("--width",   type=int,   default=640)
    ap.add_argument("--classes", nargs="+",  type=int, default=None)
    args = ap.parse_args()

    # ── resolve video path ────────────────────────────────────────
    src = args.source
    is_live = False
    
    if src is None:
        print("╔══════════════════════════════════════════════════════════╗")
        print("║               SELECT INPUT SOURCE MODE                   ║")
        print("╠══════════════════════════════════════════════════════════╣")
        print("║  [1] Live Camera Stream (OpenCV Webcam)                  ║")
        print("║  [2] Select Video File (Windows File Explorer)           ║")
        print("╚══════════════════════════════════════════════════════════╝")
        
        while True:
            choice = input("  Select option (1 or 2): ").strip()
            if choice == "1":
                is_live = True
                cam_idx = input("  Enter camera index [default 0]: ").strip()
                src = int(cam_idx) if cam_idx.isdigit() else 0
                break
            elif choice == "2":
                print("\n  [INFO] Opening Windows File Explorer. Please select a video file...")
                try:
                    import tkinter as tk
                    from tkinter import filedialog
                    
                    root = tk.Tk()
                    root.withdraw()          # Hide empty Tkinter root window
                    root.attributes('-topmost', True)  # Bring dialog window to front
                    
                    file_path = filedialog.askopenfilename(
                        title="Select UAV Input Video File",
                        filetypes=[
                            ("Video Files", "*.mp4 *.avi *.mov *.mkv"),
                            ("All Files", "*.*")
                        ]
                    )
                    if file_path:
                        src = file_path
                        break
                    else:
                        print("  [WARN] No file selected. Please choose option 1 or 2 again.")
                except Exception as e:
                    print(f"  [ERROR] Failed to open file dialog: {e}")
                    src = input("  Enter video path manually: ").strip()
                    if src:
                        break

    script_dir = os.path.dirname(os.path.abspath(__file__))
    resolved = None
    if not is_live:
        # Check if the source is a camera index entered via CLI
        if str(src).isdigit():
            is_live = True
            src = int(src)
            resolved = src
        else:
            candidates = [
                src,
                os.path.join(script_dir, src),
                os.path.join(os.getcwd(), src),
            ]
            for c in candidates:
                if os.path.exists(c):
                    resolved = os.path.abspath(c)
                    break

            if resolved is None:
                print(f"\n[ERROR] Video not found: '{src}'")
                print(f"  Script folder: {script_dir}")
                print(f"  Files there  : {os.listdir(script_dir)}")
                print(f"\n  Make sure your video file is in the same folder as main.py")
                print(f"  Then run:  python main.py --source video.mp4\n")
                sys.exit(1)

    ensure_dir(os.path.dirname(args.output) or "outputs")

    cap = cv2.VideoCapture(resolved if resolved is not None else src)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open source: {resolved if resolved is not None else src}")
        sys.exit(1)

    # Read first frame to get actual dimensions (cap.get can be unreliable)
    ret, first_frame = cap.read()
    if ret:
        src_h, src_w = first_frame.shape[:2]
        # Reset to beginning
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    else:
        src_w   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        src_h   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total < 0:
        total = 0

    writer = build_writer(args.output, src_fps, src_w, src_h)

    src_name = "Live Camera Stream" if is_live else os.path.basename(resolved)
    print("╔══════════════════════════════════════════════════════════╗")
    print("║          REAL-TIME UAV TRACKING SYSTEM v1.0              ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║  Source  : {src_name:<46}║")
    print(f"║  Output  : {args.output:<46}║")
    print(f"║  Size    : {src_w}x{src_h} @ {src_fps:.1f} fps{'':<27}║")
    print(f"║  Frames  : {str(total):<46}║")
    print("╚══════════════════════════════════════════════════════════╝\n")

    tracker  = UAVTracker(conf=args.conf, class_filter=args.classes, src_w=src_w, src_h=src_h)
    renderer = HUDRenderer(src_w, src_h, src_fps)

    fidx        = 0
    t_prev      = time.time()
    fps_display = src_fps
    last_alert_time = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        proc    = resize_frame(frame, args.width) if src_w > args.width else frame.copy()
        scale_x = src_w / proc.shape[1]
        scale_y = src_h / proc.shape[0]

        tracks = tracker.update(proc, fidx)

        for t in tracks:
            x1,y1,x2,y2 = t["bbox"]
            t["bbox"]   = (int(x1*scale_x), int(y1*scale_y),
                           int(x2*scale_x), int(y2*scale_y))
            t["center"] = (int(t["center"][0]*scale_x),
                           int(t["center"][1]*scale_y))

        now         = time.time()
        fps_display = 0.85*fps_display + 0.15/max(now-t_prev, 1e-4)
        t_prev      = now

        out_frame = renderer.render(frame.copy(), tracks, fidx, fps_display)

        # --- WhatsApp Alert Trigger ---
        if len(tracks) > 0 and config.ENABLE_WHATSAPP:
            alert_targets = [t for t in tracks if t.get("age", 0) >= config.ALERT_MIN_TRACK_AGE]
            if alert_targets and (now - last_alert_time > config.ALERT_COOLDOWN_SECONDS):
                import threading
                # Pass the annotated frame copy (containing HUD graphics)
                t_alert = threading.Thread(
                    target=send_whatsapp_alert, 
                    args=(len(tracks), out_frame.copy())
                )
                t_alert.daemon = True
                t_alert.start()
                last_alert_time = now

        writer.write(out_frame)
        fidx += 1

        # Real-time display preview with space pause / Q exit controls
        try:
            cv2.imshow("Real-Time UAV Tracking HUD", out_frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == ord('Q'):
                print("\n[INFO] Tracking stopped by user (Q pressed). Saving output...")
                break
            elif key == ord(' '):
                print("\n[INFO] Paused. Press spacebar to resume...")
                while True:
                    key2 = cv2.waitKey(30) & 0xFF
                    if key2 == ord(' '):
                        break
                    elif key2 == ord('q') or key2 == ord('Q'):
                        key = ord('q')
                        break
                if key == ord('q'):
                    print("\n[INFO] Tracking stopped by user (Q pressed). Saving output...")
                    break
        except Exception:
            pass

        if fidx % 15 == 0:
            if is_live:
                print(f"\r  [LIVE]  frame {fidx:>5}  FPS:{fps_display:4.1f}  targets:{len(tracks)}",
                      end="", flush=True)
            else:
                pct = fidx / max(total, 1) * 100
                bar = "█"*int(pct/5) + "░"*(20-int(pct/5))
                print(f"\r  [{bar}] {pct:5.1f}%  frame {fidx:>5}/{total}"
                      f"  FPS:{fps_display:4.1f}  targets:{len(tracks)}",
                      end="", flush=True)

    cap.release()
    writer.release()
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass
    print(f"\n\n[DONE] → {os.path.abspath(args.output)}\n")


if __name__ == "__main__":
    main()