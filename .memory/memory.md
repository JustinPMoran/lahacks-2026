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

## 🛠 Design Tokens & Constraints
- **Aesthetic**: Cyberpunk High-Contrast (unchanged).
- **Resolution**: **800x480**.
- **Agent Instruction Sync**: All files updated with the new mandatory comment: 
    > `# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.`

## 📂 Project Structure & Manifest
- **[.memory/memory.md](file:///.memory/memory.md)**: Master Agent Instruction file.
- **[backend/mock_service.py](file:///backend/mock_service.py)**: Mock API suite for frontend testing.
- **[frontend/main.py](file:///frontend/main.py)**: Primary GUI application with real-time pose tracking.
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
