# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.
from __future__ import annotations

import math
import re
import threading
import time
from dataclasses import dataclass


CSI_DATA_RE = re.compile(r"^CSI_DATA,\d+,([0-9a-fA-F:]{17}),(-?\d+),")


@dataclass
class ProximityReading:
    node_id: str
    mac: str
    rssi_dbm: int
    timestamp: float


class ESP32ProximityTracker:
    """Turns C6 -> S3 RSSI readings into stable proximity zones."""

    def __init__(self, stale_after_seconds=3.0, smoothing_alpha=0.25):
        self.stale_after_seconds = stale_after_seconds
        self.smoothing_alpha = smoothing_alpha
        self._nodes = {}

    def update_rssi(self, mac, rssi_dbm, timestamp=None):
        timestamp = timestamp or time.time()
        mac = mac.lower()
        node_id = f"C6_{mac[-2:].upper()}"
        node = self._nodes.get(mac)

        if node is None:
            smoothed_rssi = float(rssi_dbm)
            node = {
                "node_id": node_id,
                "name": node_id,
                "mac": mac,
                "floor": 0,
                "map_position": self._default_map_position(mac),
            }
        else:
            smoothed_rssi = (
                self.smoothing_alpha * float(rssi_dbm)
                + (1.0 - self.smoothing_alpha) * node["smoothed_rssi_dbm"]
            )

        node.update(
            {
                "rssi_dbm": int(rssi_dbm),
                "smoothed_rssi_dbm": smoothed_rssi,
                "last_seen": timestamp,
            }
        )
        node.update(self._classify(smoothed_rssi))
        self._nodes[mac] = node
        return node

    def update_from_csi_line(self, line, timestamp=None):
        match = CSI_DATA_RE.match(line.strip())
        if not match:
            return None

        mac, rssi = match.groups()
        return self.update_rssi(mac, int(rssi), timestamp)

    def snapshot(self):
        now = time.time()
        nodes = []
        for node in self._nodes.values():
            age = now - node["last_seen"]
            snapshot_node = dict(node)
            snapshot_node["last_seen_age_ms"] = int(age * 1000)
            if age > self.stale_after_seconds:
                snapshot_node["status"] = "LOST"
                snapshot_node["proximity_zone"] = "lost"
                snapshot_node["confidence"] = 0.0
            else:
                snapshot_node["status"] = "ONLINE"
            nodes.append(snapshot_node)
        return sorted(nodes, key=lambda item: item["node_id"])

    def _classify(self, rssi):
        if rssi >= -50:
            zone = "near"
            confidence = 0.9
        elif rssi >= -65:
            zone = "medium"
            confidence = 0.72
        else:
            zone = "far"
            confidence = 0.55

        return {
            "proximity_zone": zone,
            "estimated_distance_m": self._estimate_distance_m(rssi),
            "confidence": confidence,
        }

    def _estimate_distance_m(self, rssi, tx_power_at_1m=-45, path_loss_exponent=2.2):
        # This is only a rough indoor estimate; the zone is the stronger signal.
        exponent = (tx_power_at_1m - rssi) / (10 * path_loss_exponent)
        return round(max(0.4, min(30.0, math.pow(10, exponent))), 1)

    def _default_map_position(self, mac):
        seed = int(mac[-2:], 16)
        return {
            "x": 0.24 + (seed % 5) * 0.13,
            "y": 0.28 + ((seed // 5) % 4) * 0.14,
        }


class ESP32SerialProximityReader:
    """Background reader for S3 UART output containing CSI_DATA lines."""

    def __init__(self, port, baudrate=921600):
        self.port = port
        self.baudrate = baudrate
        self.tracker = ESP32ProximityTracker()
        self.thread = None
        self.stop_event = threading.Event()
        self.status = "idle"

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._read_loop, name="esp32-proximity-reader", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def snapshot(self):
        return self.tracker.snapshot()

    def _read_loop(self):
        try:
            import serial
        except ImportError:
            self.status = "missing pyserial"
            return

        try:
            with serial.Serial(self.port, self.baudrate, timeout=1) as serial_port:
                self.status = f"listening on {self.port}"
                while not self.stop_event.is_set():
                    raw_line = serial_port.readline()
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if self.tracker.update_from_csi_line(line):
                        self.status = "receiving proximity RSSI"
        except Exception as exc:
            self.status = f"serial error: {exc}"
