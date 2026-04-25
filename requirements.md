# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.

## RuView Dependencies

The following packages are required to run the Command Center GUI and connect to the backend services.

### Core GUI
- `pygame`: High-performance 2D architecture, better compatibility with Raspberry Pi hardware.

### Networking (Live Mode)
- `requests`: Required for REST API communication (System status, settings).
- `websockets`: Required for high-frequency real-time DensePose streaming.

### Installation
You can install all dependencies using:
```bash
pip install -r requirements.txt
```
