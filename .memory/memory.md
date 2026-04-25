# RuView Project Memory & Agent Directives

## 🧠 Project State Summary
**As of April 25, 2026 (Refactor Phase):**
RuView is transitioning from a static mockup to a 'Plug & Play' architecture synchronized with the original RuView repository found in `.temp`.
- **Infrastructure**: Added a `backend/mock_service.py` to stub out the RuView v1 API (REST & WebSocket structures).
- **Frontend**: Refactored `frontend/main.py` with a `BackendManager` that supports live/mock switching and real-time visualization updates.
- **Hardware Profile**: Still targeted for **800x480** Freenove displays.

## 🚀 Recent Changes (April 25)
- **DensePose Stream FPS/Detail Optimization**: Tuned the MacBook -> RunPod stream for higher practical FPS by sending 512px-wide JPEG frames at quality 60, disabling WebSocket compression for already-compressed frames, adding frontend controls for send width/JPEG quality/target FPS, and running the GPU server in `mesh` mode. The `mesh` renderer overlays DensePose fine segmentation with contour lines for more detailed person surface mapping while keeping the frame payload smaller than raw video.
- **MacBook -> RunPod DensePose Stream**: Added `backend/densepose_stream_server.py`, a GPU WebSocket inference server that accepts JPEG webcam frames and returns rendered DensePose JPEG frames. Replaced the frontend's fake DensePose reconstruction panel with a MacBook GPU stream panel that captures the local webcam, sends frames to `ws://127.0.0.1:8765`, and updates a DearPyGui dynamic texture with the GPU output. This creates the development bridge for MacBook webcam now and Raspberry Pi camera later.
- **DensePose Webcam POC**: Added `backend/densepose_webcam.py`, a local webcam proof-of-concept script that runs Detectron2 DensePose on camera frames and renders either DensePose output or a white silhouette on a black background. This supports MacBook CPU development now while keeping the same input/output behavior intended for a future CUDA/RunPod deployment.
- **DensePose Mac Setup**: Installed the local Detectron2 and DensePose checkouts into `.venv-densepose` using `--no-build-isolation` so their setup scripts can import the already-installed PyTorch package. Added `.venv-densepose/` and `.cache/` to `.gitignore`; the webcam script sets `MPLCONFIGDIR` to the local cache path to avoid user-home Matplotlib cache writes.
- **RunPod Camera Streaming**: Standardized on `backend/densepose_stream_server.py`, a WebSocket server intended for RunPod/CUDA that accepts JPEG camera frames and returns processed JPEG frames with black output when no person is detected. Generalized the frontend stream panel from MacBook-only naming to a Pi camera source controlled by `DENSEPOSE_CAMERA_SOURCE`, while still using `DENSEPOSE_WS_URL` for the RunPod endpoint.
- **Tactical Minimap**: Added a Call of Duty-style minimap overlay to `frontend/main.py`. The collapsed top-right preview opens into a larger facility map window with a dedicated MINIMIZE button and floor switching controls for Levels 1-4.
- **Minimap Layout Adjustment**: Reworked the compact minimap into the dashboard's right column above Telemetry, shortening the Telemetry panel so it sits flush below the map instead of being covered by it.
- **Minimap Expansion UX**: Enlarged and centered floor-plan images, replaced minimap header text with compact neutral floor selectors, and made the expanded minimap occupy the full 800x480 viewport.
- **Map Assets**: Copied the four supplied Pauley Pavilion floor screenshots into `frontend/assets/floors/` with stable filenames so DearPyGui can load them as static textures.
- **Backend Stubbing**: Implemented `RuViewMockService` mirroring the official `pose/latest`, `system/status`, and node sensing data structures.
- **GUI Dynamism**:
    - The **Node Manager** now updates status and RSSI in real-time based on backend data.
    - The **DensePose Feed** now moves and tracks simulated detections instead of being static.
    - Added a **Settings Window** to allow toggling between Mock and Live backend modes.
- **Git Management**: Added `.temp/` to `.gitignore` to prevent tracking of the large external RuView repository while keeping it available for reference.
- **Dependency Management**: Created `requirements.txt` and `requirements.md`.

### CSI Motion Pipeline (real hardware path)
- **Hardware**: 1× ESP32-C6 receiver + 2× ESP32-C6 senders (cyan/magenta/white LEDs), all running modified `esp-csi` example firmware. Receiver = green/yellow/red.
- **Per-sender attribution**: each sender derives a unique runtime MAC last byte from its factory MAC; receiver indexes per-sender amplitude windows by `info->mac[5]` and emits one `MOTION,<sender_id>,<score×1000>,<level>` line per sender at ~10 Hz.
- **Synced LEDs**: receiver computes max score across senders, broadcasts `[0xC0, level]` via ESP-NOW; senders mirror via `esp_now_register_recv_cb`.
- **Critical fix**: per-CSI-packet `ESP_LOGI` (200/sec at WiFi-task priority) was starving the motion task → demoted to `ESP_LOGD`. Also throttled CSI line printing (`CSI_PRINT_EVERY=50`) so MOTION telemetry isn't blocked by 1KB CSI lines on a 921600-baud UART.
- **Files added under `backend/`**:
    - `csi.py` — shared parser + per-subcarrier amplitude / motion-score helpers (used by motion_plot, motion_monitor; safe for `mock_service.py` to import).
    - `motion_plot.py` — live matplotlib dashboard (per-sender curves + CSI waterfall).
    - `motion_monitor.py` — terminal bar viewer (no GUI).
    - `firmware/csi_send/` and `firmware/csi_recv/` — modified ESP-IDF projects (build with `idf.py set-target esp32c6 && idf.py build`).
- **Cleanup (April 25 evening)**: removed unused experimental scripts from repo root: `motion_detect.py`, `presence_detect.py`, `collect_labels.py`, `train_count.py`, `demo_pi.py`, `mongo_logger.py`, plus `baseline.npz` and `.env.example`. None referenced by `backend/` or `frontend/`. requirements.txt already lean (no sklearn/pandas/pymongo).

## 🛠 Design Tokens & Constraints
- **Aesthetic**: Cyberpunk High-Contrast (unchanged).
- **Resolution**: **800x480**.
- **Agent Instruction Sync**: All files updated with the new mandatory comment: 
    > `# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.`

## 📂 Project Structure & Manifest
- **[.memory/memory.md](file:///.memory/memory.md)**: Master Agent Instruction file.
- **[backend/mock_service.py](file:///backend/mock_service.py)**: Mock API suite for frontend testing.
- **[backend/densepose_stream_server.py](file:///backend/densepose_stream_server.py)**: RunPod/GPU WebSocket inference server for streamed camera frames.
- **[backend/csi.py](file:///backend/csi.py)**: CSI parser + motion feature helpers (shared lib).
- **[backend/motion_plot.py](file:///backend/motion_plot.py)**: Live per-sender motion dashboard + CSI waterfall.
- **[backend/motion_monitor.py](file:///backend/motion_monitor.py)**: Terminal motion bar (no GUI).
- **[backend/firmware/csi_recv/](file:///backend/firmware/csi_recv)**: ESP-IDF receiver firmware (per-sender motion + LED).
- **[backend/firmware/csi_send/](file:///backend/firmware/csi_send)**: ESP-IDF sender firmware (auto unique MAC + LED mirror).
- **[frontend/main.py](file:///frontend/main.py)**: Primary GUI application with real-time pose tracking.
- **[requirements.txt](file:///requirements.txt)**: Dependency list for pip.
- **[requirements.md](file:///requirements.md)**: Human-readable dependency documentation.
- **[.temp/RuView](file:///.temp/RuView)**: Original project source (excluded from Git).

## 🤖 AI Agent Instructions (MANDATORY)
> [!IMPORTANT]
> **Before starting any task**: Read this file to understand the current state, constraints, and aesthetic of the project.
> **After completing any task**: Update this `memory.md` file with:
> 1. A summary of the changes you made.
> 2. Why you made them (design rationale).
> 3. Any new files or dependencies added.
> 4. Updated project state/milestones.

---
*Your project is now fully "agent-aware" and preserves all design choices for future collaboration! 🚀🏛️*
