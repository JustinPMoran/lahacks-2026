# RuView Project Memory & Agent Directives

## 🧠 Project State Summary
**As of April 2026:**
RuView is a real-time WiFi sensing and human pose reconstruction system for LA Hacks 2026.
- **Master Master Context**: Documenting the goal, ESP32-S3 mesh architecture, and the pixel-perfect 800x480 design constraints.
- **Frontend**: A sleek Cyberpunk/Guardian DearPyGui dashboard optimized for 800x480 Freenove displays.
- **Hardware**: ESP32-S3 (Mesh Nodes), Raspberry Pi (Host), DSI Display.

## 🛠 Design Tokens & Constraints
- **Primary**: Neon Cyan `(0, 255, 255)`
- **Accent**: Amber `(255, 200, 0)`
- **Background**: Deep Navy `(15, 17, 26)`
- **Resolution**: Pixel-perfect **800x480**. Do not exceed these dimensions.
- **Rounding**: 0px for main windows, 6px for internal panels.
- **Padding/Spacing**: 10px consistent.

## 📂 Project Structure & Manifest
- **[.memory/memory.md](file:///.memory/memory.md)**: Design tokens, hardware specs, and implementation criticals.
- **[README.md](file:///README.md)**: Root project status and AI instructions.
- **[frontend/main.py](file:///frontend/main.py)**: DearPyGui application logic.
- **[.gitignore](file:///.gitignore)**: Mandatory exclusions.
- **[backend/README.md](file:///backend/README.md)**: Placeholder for firmware logic.

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
