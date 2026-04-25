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

## 🛠 Tech Stack
- **Mesh Nodes**: ESP32-S3
- **Local Host**: Raspberry Pi 4/5
- **Display**: Freenove 800x480 DSI
- **GUI Framework**: DearPyGui (Python)

## 🎨 Design Tokens
- **Primary**: Neon Cyan `(0, 255, 255)`
- **Accent**: Amber `(255, 200, 0)`
- **Background**: Deep Navy `(15, 17, 26)`
- **Resolution**: Pixel-perfect **800x480**

## 📂 Structure
- `/frontend`: DearPyGui application and assets.
- `/backend`: WiFi sensing logic and ESP32 firmware (In Progress).
- `/.memory`: Project context and AI agent instructions.
