# RuView Project Memory & Agent Directives

## 🧠 Project State Summary
**As of April 25, 2026 (Refactor Phase 2):**
RuView has transitioned its frontend from DearPyGui to **Pygame** to ensure flawless performance on all Raspberry Pi versions, as some Pi drivers struggle with DearPyGui's GPU requirements.
- **Infrastructure**: Backend `mock_service.py` is fully integrated and provides real-time data to the Pygame UI.
- **Frontend**: A custom Pygame-based Command Center mirroring the original Cyberpunk aesthetic and pixel-perfect 800x480 layout.
- **Hardware Profile**: Optimized for **800x480** Freenove DSI displays.

## 🚀 Recent Changes (April 25)
- **GUI Engine Swap**: Replaced DearPyGui with Pygame. 
    - **Implementation**: Custom UI rendering loop in `frontend/main.py` with hand-drawn panels, telemetry logs, and node status displays.
    - **Visual Fidelity**: Maintained the exact same color palette, layout, and "DensePose Reconstruction" point cloud logic.
- **Backend Sync**: Pygame loop now polls `BackendManager` at 30 FPS for telemetry and pose data.
- **Dependency Update**: Swapped `dearpygui` for `pygame` in `requirements.txt` and `requirements.md`.

## 🛠 Design Tokens & Constraints
- **Aesthetic**: Cyberpunk High-Contrast.
- **Primary**: Neon Cyan `(0, 255, 255)`
- **Accent**: Amber `(255, 200, 0)`
- **Background**: Deep Navy `(15, 17, 26)`
- **Resolution**: Pixel-perfect **800x480**. Do not exceed these dimensions.
- **Rendering**: Pygame Surface blitting with alpha support for DensePose "flicker" effect.

## 📂 Project Structure & Manifest
- **[.memory/memory.md](file:///.memory/memory.md)**: Master Agent Instruction file.
- **[backend/mock_service.py](file:///backend/mock_service.py)**: Mock API suite for frontend testing.
- **[frontend/main.py](file:///frontend/main.py)**: **Pygame** GUI application.
- **[requirements.txt](file:///requirements.txt)**: Dependency list (Pygame, etc.).
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
*Your project is now optimized for Raspberry Pi deployment while preserving its state-of-the-art look! 🚀🏛️*
