# RuView | WiFi DensePose GUI

A premium, modern dashboard designed for the **Freenove 800x480 Raspberry Pi Display**. This interface serves as the command center for localized WiFi sensing and human pose reconstruction (WiFi DensePose).

## 🚀 Quick Start

Ensure you are on a Raspberry Pi (or a machine with a display server) and have Python 3.8+ installed.

```bash
# Install DearPyGui
pip install dearpygui

# Run the dashboard
python main.py
```

## 🛠 Features

- **Spatial Reconstruction Feed**: Real-time rendering of the environment including grid overlays and humanoid pose placeholders.
- **Hardware Node Manager**: Monitor status (Online/Offline) and RSSI levels for your ESP32-S3 mesh nodes.
- **Live Telemetry Stream**: Event logging for movement detection and system synchronization.
- **Cyberpunk Aesthetic**: High-contrast dark mode with neon cyan and amber accents optimized for IPS/TN panels.
- **Touch Optimized**: Large button targets and sliders designed for resistive/capacitive touch interactions.

## 📁 Project Structure

- `main.py`: The core application containing the DPG context, layout logic, and theme definitions.
- `assets/` (Optional): Place custom fonts or icons here.

## 🔧 Hardware Configuration

This UI is hard-coded for **800x480 resolution**. 
- To enable full-screen mode on Raspbian, ensures `decorated=False` is set in `dpg.create_viewport` (already configured in `main.py`).
- If using as a kiosk, use a manager like `matchbox-window-manager` to lock the window.

## 🤝 Integration Guide

To hook this up to your real ESP32 data:
1. Update the `nodes` list in `create_node_panel()` with your network discovery logic.
2. Use the `dpg.set_value()` or `dpg.configure_item()` methods within the main loop to update the `spatial_drawlist` coordinates based on your DensePose model output.

---
Built for **LA Hacks 2026** 🏛️
