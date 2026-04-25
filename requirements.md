# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.

## RuView Dependencies

The following packages are required to run the Command Center GUI and connect to the backend services.

### Core GUI
- `dearpygui`: High-performance GPU-accelerated GUI framework.

### Networking (Live Mode)
- `requests`: Required for REST API communication (System status, settings).
- `websockets`: Required for high-frequency real-time DensePose streaming.

### Camera Streaming
- `opencv-python`: Captures the MacBook webcam, JPEG-encodes frames for the GPU, and decodes rendered DensePose frames for the frontend texture.

### Installation
You can install all dependencies using:
```bash
pip install -r requirements.txt
```
