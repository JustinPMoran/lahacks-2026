import random
import time
import json
import math

# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.

class RuViewMockService:
    """
    Simulation service that mimics the RuView v1 API structure.
    Allows for 'Plug and Play' frontend development without the Caffe2/Linux dependency.
    """
    
    def __init__(self):
        self.session_id = f"mock_session_{random.randint(1000, 9999)}"
        self.start_time = time.time()
        self.is_running = True
        
    def get_system_status(self):
        """Mimics GET /api/v1/system/status"""
        uptime = int(time.time() - self.start_time)
        return {
            "success": True,
            "data": {
                "status": "running" if self.is_running else "stopped",
                "session_id": self.session_id,
                "uptime_seconds": uptime,
                "performance": {
                    "average_fps": round(29.8 + random.uniform(-0.5, 0.5), 1),
                    "cpu_usage": round(45.0 + random.uniform(-5, 5), 1),
                    "gpu_usage": round(62.0 + random.uniform(-2, 2), 1)
                },
                "components": {
                    "csi_processor": {"status": "healthy"},
                    "neural_network": {"status": "healthy"},
                    "tracker": {"status": "healthy"}
                }
            }
        }

    def get_latest_pose(self):
        """Mimics GET /api/v1/pose/latest"""
        t = time.time()
        # Simulate a person moving in a circle
        px = 200 + 50 * math.cos(t * 0.5)
        py = 150 + 30 * math.sin(t * 0.5)
        
        return {
            "success": True,
            "data": {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                "frame_id": int(t * 30),
                "persons": [
                    {
                        "person_id": 1,
                        "track_id": 101,
                        "confidence": 0.94,
                        "center": {"x": px, "y": py},
                        "pose_type": "standing",
                        "dense_pose": self._generate_mock_iuv(px, py)
                    }
                ]
            }
        }

    def _generate_mock_iuv(self, x, y):
        """Internal helper to generate point cloud data clusters"""
        # This matches our draw_dense_pose logic in the frontend
        return {
            "root_x": x,
            "root_y": y,
            "jitter": random.uniform(0.8, 1.2)
        }

    def get_nodes(self):
        """Mimics the sensing/backend node discovery"""
        return [
            {"name": "GATEWAY", "status": "ONLINE", "rssi": f"-{random.randint(40, 45)}dBm"},
            {"name": "NODE_ALPHA", "status": "ONLINE", "rssi": f"-{random.randint(50, 60)}dBm"},
            {"name": "NODE_BETA", "status": "OFFLINE" if random.random() < 0.05 else "ONLINE", "rssi": "-65dBm"}
        ]
