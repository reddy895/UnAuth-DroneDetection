# Real-Time UAV Tracking & Threat Detection System

A high-performance Python-based computer vision application designed to detect, track, and alert on UAVs (unmanned aerial vehicles/drones) in real-time. The system integrates state-of-the-art **YOLOv8** object detection with a customized **ByteTrack-style IoU tracker**, **Kalman-style trajectory smoothing**, a **military-inspired head-up display (HUD)**, and a **real-time WhatsApp Alert Bot** for instantaneous threat notification with live screenshots.

---

## 🚀 Key Features

*   **Real-Time UAV Detection & Tracking**: Powered by Ultralytics **YOLOv8** (`yolov8n.pt`) and a custom, lightweight multi-object tracking algorithm based on **ByteTrack** (IoU association).
*   **Kalman-style Box Smoothing & Prediction**: Applies Exponential Moving Average (EMA) smoothing to eliminate bounding-box jitter and utilizes a velocity vector to predict trajectories during temporary occlusions.
*   **Military-Grade HUD Visualization**: A custom green telemetry overlay featuring:
    *   **Dynamic Reticles & Corner Bounding Boxes**: Lock indicators and precise spatial coordinates.
    *   **Trajectory Trails & Velocity Arrows**: Visual history of motion and instant velocity vector projection.
    *   **Seeker Zoom Inset**: A high-contrast, sharpened, and CCTV-tinted zoom view of the primary target (the UAV detected with the highest confidence).
    *   **Telemetry Status Panels**: Displaying real-time target counts, coordinate feedback, processing FPS, timestamp logs, and system details.
*   **Anti-Tampering & Playback Filtering**: High-fidelity filtering rules that reject detections overlapping with mobile screens (to prevent camera spoofing/playback malpractice) and screen overlays (like the seeker zoom inset itself) to ensure authentic threat identification.
*   **Headless WhatsApp Alert Bot Integration**:
    *   Runs as a headless **Node.js** microservice (using `whatsapp-web.js` and Express).
    *   Authentication via a quick QR-code terminal scan that links your phone to the bot.
    *   Saves login session locally so that linking is a one-time step.
    *   Dispatches alerts asynchronously in separate Python threads to keep tracking playback smooth.
    *   Attaches live HUD screenshots compressed, base64-encoded, and sent directly to your phone.
    *   Applies a rate-limiting cooldown and track-age filter to avoid phone alert spamming.
*   **Interactive Input Selector**: Offers a native Windows File Explorer file picker dialog or live camera/webcam indexing if no command line source is supplied.
*   **Live Preview Displays**: Renders HUD overlays to the screen with key interaction support (Spacebar to pause/resume playback, Q to quit).

---

## 🛠️ Setup & Installation

### Prerequisites
*   Python 3.11, 3.12, 3.13, or 3.14
*   Node.js (v18+) and npm installed

### 1. Configure the Alert Settings
Open [config.py](file:///c:/Users/prave/Downloads/Real-Time-UAV-Tracking-System-main/UAV-detection/config.py) and configure your variables:
*   Set `ENABLE_WHATSAPP = True`
*   Set `WHATSAPP_TO_NUMBER` to your personal phone number (including country code, e.g. `"919876543210"`).

### 2. Start the WhatsApp Bot Microservice
Open a new terminal window, navigate to the `whatsapp_bot` directory, and run:
```sh
cd UAV-detection/whatsapp_bot
npm install
npm start
```
On its first run, it will print a QR code. Open WhatsApp on your phone, go to **Settings > Linked Devices > Link a Device**, and scan the QR code.

### 3. Run the UAV Tracker
Run the tracker script:
```sh
python main.py
```
If you omit the `--source` parameter, an interactive prompt will appear. Select Option `2` to open the Windows File Explorer and choose one of the sample videos.

---

## 🎹 Keyboard Controls (Live Display)
When the tracking window is active:
*   `[Spacebar]`: Pause or resume tracking.
*   `[Q]`: Stop tracking and save the processed video.
