<!-- After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task. -->
# RuView | WiFi DensePose Architecture

**RuView** is a real-time WiFi sensing and human pose reconstruction system. By analyzing signal disruptions across an ESP32-S3 mesh network, RuView reconstructs presence and spatial data without using cameras, privacy-preserving by design.

---

## 🗒 Project Memory
> [!IMPORTANT]
> Detailed design choices, layout constraints (800x480), and implementation logic are stored in:
> **[.memory/memory.md](file:///.memory/memory.md)**

---

## 🚀 Quick Start
```bash
cd frontend
pip install -r requirements.txt
python main.py
```

## RunPod + Raspberry Pi Camera Stream

The intended live path is:

```text
Raspberry Pi camera/frontend -> WebSocket JPEG frames -> RunPod GPU DensePose server -> processed JPEG frames -> frontend texture
```

On the RunPod GPU machine:

```bash
cd lahacks-2026
python3.11 -m venv .venv-densepose
source .venv-densepose/bin/activate
python -m pip install -U pip setuptools wheel
python -m pip install torch torchvision opencv-python websockets av scipy pycocotools matplotlib
python -m pip install -e ./detectron2 --no-build-isolation
python -m pip install -e ./detectron2/projects/DensePose --no-deps --no-build-isolation
python backend/densepose_stream_server.py --host 0.0.0.0 --port 8765 --device cuda --mode mesh
```

Expose port `8765` from RunPod. Use the generated RunPod WebSocket proxy URL as `DENSEPOSE_WS_URL`, for example:

```bash
export DENSEPOSE_WS_URL="wss://<pod-id>-8765.proxy.runpod.net"
```

On the Raspberry Pi display/frontend:

```bash
cd lahacks-2026
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export DENSEPOSE_CAMERA_SOURCE=0
export DENSEPOSE_WS_URL="wss://<pod-id>-8765.proxy.runpod.net"
python frontend/main.py
```

If the Pi camera is exposed as a video device, `DENSEPOSE_CAMERA_SOURCE=0` or `/dev/video0` should work. The frontend sends one compressed frame, waits for the processed frame, and displays the returned DensePose-only/black output.

The frontend uses Pygame instead of DearPyGui so it can run on Raspberry Pi OS. Set `RUVIEW_FULLSCREEN=1` for kiosk-style display output.

## 🛠 Tech Stack
- **Mesh Nodes**: ESP32-S3
- **Local Host**: Raspberry Pi 4/5
- **Display**: Freenove 800x480 DSI
- **GUI Framework**: Pygame (Python)

## 🎨 Design Tokens
- **Primary**: Neon Cyan `(0, 255, 255)`
- **Accent**: Amber `(255, 200, 0)`
- **Background**: Deep Navy `(15, 17, 26)`
- **Resolution**: Pixel-perfect **800x480**

## 📂 Structure
- `/frontend`: Pygame command-center application and assets.
- `/backend`: WiFi sensing logic and ESP32 firmware (In Progress).
- `/.memory`: Project context and AI agent instructions.
