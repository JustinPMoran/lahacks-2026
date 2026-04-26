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
        self._c6_nodes = [
            {
                "node_id": "C6_ALPHA",
                "name": "C6_ALPHA",
                "mac": "1a:00:00:00:00:a1",
                "base_rssi": -46,
                "phase": 0.0,
                "floor": 0,
                "map_position": {"x": 0.42, "y": 0.48},
            },
            {
                "node_id": "C6_BRAVO",
                "name": "C6_BRAVO",
                "mac": "1a:00:00:00:00:b2",
                "base_rssi": -58,
                "phase": 1.7,
                "floor": 0,
                "map_position": {"x": 0.67, "y": 0.36},
            },
            {
                "node_id": "C6_CHARLIE",
                "name": "C6_CHARLIE",
                "mac": "1a:00:00:00:00:c3",
                "base_rssi": -70,
                "phase": 3.2,
                "floor": 1,
                "map_position": {"x": 0.30, "y": 0.64},
            },
        ]
        
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
        proximity_nodes = self.get_proximity_nodes()
        return [
            {"name": "GATEWAY", "status": "ONLINE", "rssi": f"-{random.randint(40, 45)}dBm"},
            *[
                {
                    "name": node["name"],
                    "status": node["status"],
                    "rssi": f"{node['rssi_dbm']}dBm",
                    "proximity_zone": node["proximity_zone"],
                    "estimated_distance_m": node["estimated_distance_m"],
                    "confidence": node["confidence"],
                }
                for node in proximity_nodes
            ],
        ]

    def get_proximity_nodes(self):
        """Mimics C6 proximity readings observed by the main S3 board."""
        t = time.time() - self.start_time
        nodes = []
        for node in self._c6_nodes:
            rssi = int(node["base_rssi"] + 4 * math.sin(t * 0.55 + node["phase"]) + random.uniform(-1.5, 1.5))
            proximity = self._classify_proximity(rssi)
            nodes.append(
                {
                    "node_id": node["node_id"],
                    "name": node["name"],
                    "mac": node["mac"],
                    "status": "ONLINE" if random.random() > 0.02 else "LOST",
                    "rssi_dbm": rssi,
                    "smoothed_rssi_dbm": rssi,
                    "floor": node["floor"],
                    "map_position": node["map_position"],
                    "last_seen_age_ms": random.randint(20, 180),
                    **proximity,
                }
            )
        return nodes

    def _classify_proximity(self, rssi):
        if rssi >= -50:
            zone = "near"
            confidence = 0.9
        elif rssi >= -65:
            zone = "medium"
            confidence = 0.72
        else:
            zone = "far"
            confidence = 0.55

        estimated_distance = round(max(0.4, min(30.0, math.pow(10, (-45 - rssi) / 22))), 1)
        return {
            "proximity_zone": zone,
            "estimated_distance_m": estimated_distance,
            "confidence": confidence,
        }
