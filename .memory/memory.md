# RuView Project Memory & Agent Directives

## 🧠 Project State Summary
**As of April 25, 2026 (Refactor Phase 2):**
RuView has transitioned its frontend from DearPyGui to **Pygame** to ensure flawless performance on all Raspberry Pi versions.
- **Infrastructure**: Backend `mock_service.py` provides real-time data to the Pygame UI.
- **Frontend**: A custom Pygame-based Command Center mirroring the original Cyberpunk aesthetic and pixel-perfect 800x480 layout.
- **Layout**: Features a Node Manager (Left), DensePose Feed (Center), **Architectural Live Map (Top-Right)**, and a condensed Telemetry panel (Bottom-Right).

## 🚀 Recent Changes (April 25)
- **Map Fidelity Upgrade**: Enhanced the Live Map with actual building architectural footprints (modeled after a simplified UCLA campus) and a structured road network.
    - **Implementation**: Uses `pygame.draw.polygon` for filled building masses and structured road grids instead of random lines.
- **Live Map Integration**: Added a "GraphHopper" inspired Live Map in the gap above Telemetry.
- **GUI Engine Swap**: Migrated from DearPyGui to Pygame for Pi performance optimization.
- **Telemetry Layout Tweak**: Adjusted the Telemetry card to be half-height and anchored to the bottom right.

## 🛠 Design Tokens & Constraints
- **Aesthetic**: Cyberpunk High-Contrast.
- **Primary**: Neon Cyan `(0, 255, 255)`
- **Accent**: Amber `(255, 200, 0)`
- **Background**: Deep Navy `(15, 17, 26)`
- **Resolution**: Pixel-perfect **800x480**. Do not exceed these dimensions.
- **Live Map**: Positioned at `(615, 70)` with dimensions `(175, 190)`. Contains building footprints in `(25, 30, 45)` with `(60, 75, 95)` outlines.

## 📂 Project Structure & Manifest
- **[.memory/memory.md](file:///.memory/memory.md)**: Master Agent Instruction file.
- **[backend/mock_service.py](file:///backend/mock_service.py)**: Mock API suite for frontend testing.
- **[frontend/main.py](file:///frontend/main.py)**: Pygame GUI application with architectural Live Map.
- **[requirements.txt](file:///requirements.txt)**: Dependency list.
- **[requirements.md](file:///requirements.md)**: Dependency documentation.

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
