# RuView Project Memory & Agent Directives

## 🧠 Project State Summary
**As of April 25, 2026 (Refactor Phase):**
RuView is transitioning from a static mockup to a 'Plug & Play' architecture synchronized with the original RuView repository found in `.temp`.
- **Infrastructure**: Added a `backend/mock_service.py` to stub out the RuView v1 API (REST & WebSocket structures).
- **Frontend**: Refactored `frontend/main.py` with a `BackendManager` that supports live/mock switching and real-time visualization updates.
- **Hardware Profile**: Still targeted for **800x480** Freenove displays.

## 🚀 Recent Changes (April 25)
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
