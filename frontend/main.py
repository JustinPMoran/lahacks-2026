# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.
from __future__ import annotations

import asyncio
import html
import io
import math
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
import json
from pathlib import Path

import pygame
import requests

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

# Ensure backend can be imported when running from frontend/ or the repo root.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.mock_service import RuViewMockService
from backend.proximity import ESP32SerialProximityReader


WIDTH = 800
HEIGHT = 480
FPS = 30

ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "floors")
CAMERA_STREAM_WIDTH = 380
CAMERA_STREAM_HEIGHT = 214
DEFAULT_DENSEPOSE_WS_URL = os.environ.get("DENSEPOSE_WS_URL", "ws://103.196.86.92:33644")
DEFAULT_STREAM_SEND_WIDTH = int(os.environ.get("DENSEPOSE_SEND_WIDTH", "512"))
DEFAULT_STREAM_JPEG_QUALITY = int(os.environ.get("DENSEPOSE_JPEG_QUALITY", "60"))
DEFAULT_STREAM_TARGET_FPS = float(os.environ.get("DENSEPOSE_TARGET_FPS", "18"))

BG = (15, 17, 26)
PANEL_BG = (22, 25, 37)
PANEL_BORDER = (40, 45, 60)
CYAN = (0, 255, 255)
GREEN = (0, 255, 150)
AMBER = (255, 200, 0)
MUTED = (100, 120, 140)
TEXT = (190, 200, 220)
TEXT_DIM = (80, 85, 100)
RED = (255, 70, 80)


FLOOR_MAPS = [
    {"label": "LEVEL 1", "detail": "Stadium Floor", "asset": "level_1_stadium_floor.png", "color": CYAN},
    {"label": "LEVEL 2", "detail": "Lower Bowl", "asset": "level_2_lower_bowl.png", "color": GREEN},
    {"label": "LEVEL 3", "detail": "Upper Bowl", "asset": "level_3_upper_bowl.png", "color": AMBER},
    {"label": "LEVEL 4", "detail": "Concourse", "asset": "level_4_concourse_exterior.png", "color": (255, 85, 180)},
]


# --- Tactical overlay -------------------------------------------------------
# Static per-floor scenario for the minimap. Positions are normalized 0..1
# over the floor map image so they scale to whatever pixel rect we draw into.
COLOR_SELF     = (255, 230, 0)
COLOR_TEAMMATE = (0, 200, 255)
COLOR_TRAPPED  = (255, 40, 60)
COLOR_HAZARD   = (255, 120, 0)
COLOR_EVENT    = (200, 110, 255)
COLOR_NODE     = (0, 255, 200)
COLOR_LINK     = (0, 110, 95)        # faint mesh-link line
COLOR_EXIT     = (60, 255, 120)
COLOR_RESCUE   = (255, 80, 90)
COLOR_EVAC     = (60, 255, 120)
COLOR_HOP      = (255, 230, 0)       # mesh nodes used by the active rescue path
HIT_RADIUS_NORM = 0.045              # click hit-test radius, normalized

FLOOR_ENTITIES = {
    # Level 1: clean slate — just the team + you. The user demos by tagging
    # hazards / trapped / events on the map.
    "level_1_stadium_floor.png": {
        "self": {"x": 0.46, "y": 0.55, "label": "YOU"},
        "teammates": [
            {"x": 0.30, "y": 0.50, "label": "BRAVO-2", "hr": 102},
            {"x": 0.62, "y": 0.62, "label": "BRAVO-3", "hr": 96},
        ],
        "trapped": [],
        "hazards": [],
        "nodes": [
            {"x": 0.20, "y": 0.30},
            {"x": 0.80, "y": 0.70},
        ],
        "links": [(0, 1)],
        "exits": [
            {"x": 0.04, "y": 0.55, "label": "W"},
            {"x": 0.96, "y": 0.55, "label": "E"},
        ],
    },
    "level_2_lower_bowl.png": {
        "self": {"x": 0.50, "y": 0.50, "label": "YOU"},
        "teammates": [
            {"x": 0.22, "y": 0.30, "label": "BRAVO-2", "hr": 110},
            {"x": 0.78, "y": 0.70, "label": "BRAVO-3", "hr": 92},
        ],
        "trapped": [
            {"x": 0.16, "y": 0.78, "label": "VIC-1", "status": "PRONE"},
            {"x": 0.86, "y": 0.30, "label": "VIC-2", "status": "MOVING"},
        ],
        "hazards": [
            {"x": 0.10, "y": 0.50, "type": "FIRE"},
        ],
        "nodes": [
            {"x": 0.15, "y": 0.20},
            {"x": 0.85, "y": 0.20},
            {"x": 0.50, "y": 0.85},
        ],
        "links": [(0, 1), (0, 2), (1, 2)],
        "exits": [
            {"x": 0.04, "y": 0.50, "label": "W"},
            {"x": 0.96, "y": 0.50, "label": "E"},
            {"x": 0.50, "y": 0.04, "label": "N"},
        ],
    },
    "level_3_upper_bowl.png": {
        "self": {"x": 0.32, "y": 0.55, "label": "YOU"},
        "teammates": [
            {"x": 0.70, "y": 0.40, "label": "BRAVO-2", "hr": 88},
        ],
        "trapped": [
            {"x": 0.22, "y": 0.82, "label": "VIC-3", "status": "PRONE"},
        ],
        "hazards": [],
        "nodes": [
            {"x": 0.20, "y": 0.30},
            {"x": 0.80, "y": 0.70},
        ],
        "links": [(0, 1)],
        "exits": [
            {"x": 0.50, "y": 0.04, "label": "N"},
            {"x": 0.50, "y": 0.96, "label": "S"},
        ],
    },
    "level_4_concourse_exterior.png": {
        "self": {"x": 0.52, "y": 0.85, "label": "YOU"},
        "teammates": [
            {"x": 0.20, "y": 0.50, "label": "BRAVO-2", "hr": 84},
        ],
        "trapped": [
            {"x": 0.30, "y": 0.30, "label": "VIC-4", "status": "STILL"},
        ],
        "hazards": [],
        "nodes": [
            {"x": 0.20, "y": 0.50},
            {"x": 0.80, "y": 0.50},
        ],
        "links": [(0, 1)],
        "exits": [
            {"x": 0.50, "y": 0.96, "label": "MAIN"},
            {"x": 0.05, "y": 0.05, "label": "NW"},
            {"x": 0.95, "y": 0.05, "label": "NE"},
        ],
    },
}


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    action: str
    value: object | None = None


class MotionDataPoller:
    """Tail a local JSONL motion log written by backend/motion_plot.py.
    Caches the last `history_seconds` of (ts_epoch, score, level) per
    sender_id so the render loop reads from memory. No network."""

    DEFAULT_LOG_PATH = os.environ.get("RUVIEW_MOTION_LOG", "/tmp/ruview_motion.jsonl")

    def __init__(self, history_seconds: float = 30.0, poll_interval: float = 0.25,
                 log_path: str | None = None):
        self.history_seconds = history_seconds
        self.poll_interval = poll_interval
        self.log_path = log_path or self.DEFAULT_LOG_PATH
        self._data: dict[int, list[tuple[float, float, int]]] = {}
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._offset = 0
        self._partial = ""
        self.status = f"waiting on {self.log_path}"
        threading.Thread(target=self._run, daemon=True).start()

    def _ingest_line(self, line: str, buckets: dict[int, list[tuple[float, float, int]]]):
        line = line.strip()
        if not line:
            return
        try:
            doc = json.loads(line)
            sid = int(doc["sender_id"])
            ts = float(doc["ts"])
            score = float(doc.get("score", 0.0))
            level = int(doc.get("level", 0))
        except (ValueError, KeyError, TypeError):
            return
        buckets.setdefault(sid, []).append((ts, score, level))

    def _run(self):
        while not self._stopped.is_set():
            try:
                stat = os.stat(self.log_path)
            except FileNotFoundError:
                self.status = f"waiting on {self.log_path}"
                with self._lock:
                    self._data = {}
                self._offset = 0
                self._partial = ""
                time.sleep(self.poll_interval)
                continue
            except OSError as e:
                self.status = f"stat failed ({e})"
                time.sleep(self.poll_interval)
                continue

            # File was truncated/rotated → start over.
            if stat.st_size < self._offset:
                self._offset = 0
                self._partial = ""
                with self._lock:
                    self._data = {}

            try:
                with open(self.log_path, "r") as fh:
                    fh.seek(self._offset)
                    chunk = fh.read()
                    self._offset = fh.tell()
            except OSError as e:
                self.status = f"read failed ({e})"
                time.sleep(self.poll_interval)
                continue

            if chunk:
                with self._lock:
                    text = self._partial + chunk
                    lines = text.split("\n")
                    self._partial = lines.pop()  # incomplete trailing line
                    for line in lines:
                        self._ingest_line(line, self._data)

                    cutoff = time.time() - self.history_seconds
                    for sid, hist in list(self._data.items()):
                        trimmed = [pt for pt in hist if pt[0] >= cutoff]
                        if trimmed:
                            self._data[sid] = trimmed
                        else:
                            del self._data[sid]
                self.status = f"live: {self.log_path}"
            time.sleep(self.poll_interval)

    def snapshot(self) -> dict[int, list[tuple[float, float, int]]]:
        with self._lock:
            return {k: list(v) for k, v in self._data.items()}


class BackendManager:
    """Manages connection to the RuView API (Mock or Live)."""

    def __init__(self):
        self.mock = RuViewMockService()
        self.use_mock = True
        self.backend_url = "http://localhost:8000"
        self.last_pose = None
        self.nodes = []
        self.proximity_nodes = []
        self.status = self.mock.get_system_status()
        self.proximity_reader = None
        proximity_port = os.environ.get("RUVIEW_PROXIMITY_SERIAL")
        if proximity_port:
            self.proximity_reader = ESP32SerialProximityReader(proximity_port)
            self.proximity_reader.start()

    def update(self):
        if self.use_mock:
            self.last_pose = self.mock.get_latest_pose()
            self.status = self.mock.get_system_status()
            if self.proximity_reader:
                self.proximity_nodes = self.proximity_reader.snapshot()
                self.nodes = self._nodes_from_proximity()
            else:
                self.proximity_nodes = self.mock.get_proximity_nodes()
                self.nodes = self._nodes_from_proximity()

    def get_logs(self):
        average_fps = self.status["data"]["performance"]["average_fps"]
        online_nodes = len([node for node in self.nodes if node["status"] == "ONLINE"])
        near_nodes = len([node for node in self.proximity_nodes if node["proximity_zone"] == "near"])
        return [
            f"[SYNC] {time.strftime('%H:%M:%S')} - Model: {average_fps} FPS",
            f"[NODE] Online Count: {online_nodes}",
            f"[PROX] C6 near S3: {near_nodes}/{len(self.proximity_nodes)}",
            "[CSI] Multi-path interference low",
            "[POSE] RunPod stream target active",
        ]

    def _nodes_from_proximity(self):
        return [
            {"name": "S3_MAIN", "status": "ONLINE", "rssi": "0dBm"},
            *[
                {
                    "name": node["name"],
                    "status": node["status"],
                    "rssi": f"{node['rssi_dbm']}dBm",
                    "proximity_zone": node["proximity_zone"],
                    "estimated_distance_m": node["estimated_distance_m"],
                    "confidence": node["confidence"],
                }
                for node in self.proximity_nodes
            ],
        ]


class TwilioPatientAlert:
    """Places a phone call when patient tags change."""

    def __init__(self):
        self.account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
        self.api_key_sid = os.environ.get("TWILIO_API_KEY_SID", "").strip()
        self.api_key_secret = os.environ.get("TWILIO_API_KEY_SECRET", "").strip()
        self.from_number = os.environ.get("TWILIO_FROM_NUMBER", "").strip()
        self.to_number = os.environ.get("TWILIO_PATIENT_ALERT_TO", "+17605768000").strip()
        self.audio_url = os.environ.get("TWILIO_PATIENT_ALERT_AUDIO_URL", "").strip()
        self.cooldown_seconds = max(0.0, float(os.environ.get("TWILIO_PATIENT_ALERT_COOLDOWN_SECONDS", "0")))
        self.call_timeout_seconds = max(1.0, float(os.environ.get("TWILIO_CALL_TIMEOUT_SECONDS", "10")))
        self.last_call_monotonic = 0.0

    def _is_configured(self) -> bool:
        return all([self.account_sid, self.api_key_sid, self.api_key_secret, self.from_number, self.to_number])

    def notify_patients_changed(self, *, floor_label: str, patient_count: int) -> bool:
        if not self._is_configured():
            print(
                "twilio patient alert skipped | missing TWILIO_ACCOUNT_SID/TWILIO_API_KEY_SID/"
                "TWILIO_API_KEY_SECRET/TWILIO_FROM_NUMBER",
                flush=True,
            )
            return False

        now = time.monotonic()
        elapsed = now - self.last_call_monotonic
        if self.last_call_monotonic and elapsed < self.cooldown_seconds:
            print(
                f"twilio patient alert cooldown | {self.cooldown_seconds - elapsed:.1f}s remaining",
                flush=True,
            )
            return False

        call_text = f"RuView alert. Patients tag changed on {floor_label}. Total tagged patients: {patient_count}."
        if self.audio_url:
            twiml = f"<Response><Play>{html.escape(self.audio_url)}</Play></Response>"
        else:
            twiml = f"<Response><Say voice='alice'>{html.escape(call_text)}</Say></Response>"
        payload = {"To": self.to_number, "From": self.from_number, "Twiml": twiml}
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Calls.json"

        try:
            response = requests.post(
                url,
                data=payload,
                auth=(self.api_key_sid, self.api_key_secret),
                timeout=self.call_timeout_seconds,
            )
        except requests.RequestException as exc:
            print(f"twilio patient alert failed | {exc}", flush=True)
            return False

        if response.status_code >= 300:
            err = response.text.strip().replace("\n", " ")
            print(f"twilio patient alert rejected | status={response.status_code} | {err[:240]}", flush=True)
            return False

        call_sid = "unknown"
        try:
            call_sid = response.json().get("sid", "unknown")
        except ValueError:
            pass
        self.last_call_monotonic = now
        print(f"twilio patient alert call queued | sid={call_sid} | to={self.to_number}", flush=True)
        return True


class CameraDensePoseStream:
    """Streams a local camera source to a GPU DensePose WebSocket server."""

    def __init__(self):
        self.ws_url = DEFAULT_DENSEPOSE_WS_URL
        self.camera_source = os.environ.get(
            "DENSEPOSE_CAMERA_SOURCE",
            os.environ.get("DENSEPOSE_CAMERA_INDEX", "0"),
        )
        self.send_width = DEFAULT_STREAM_SEND_WIDTH
        self.jpeg_quality = DEFAULT_STREAM_JPEG_QUALITY
        self.target_fps = DEFAULT_STREAM_TARGET_FPS
        self.thread = None
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        self.status = "idle | press START when GPU server is ready"
        self.latest_frame = None
        self.last_fps = 0.0
        self.frame_count = 0
        self.latest_frame_path = os.environ.get("RUVIEW_LATEST_FRAME_PATH", "/tmp/ruview_frontend_latest.jpg")

    def start(self):
        if self.is_running():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_thread, name="camera-densepose-stream", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self._set_status("stopping camera stream")

    def toggle(self):
        if self.is_running():
            self.stop()
        else:
            self.start()

    def is_running(self):
        return self.thread is not None and self.thread.is_alive()

    def consume_frame(self):
        with self.lock:
            frame = self.latest_frame
            self.latest_frame = None
        return frame

    def _set_status(self, status):
        with self.lock:
            if status != self.status:
                print(status, flush=True)
                self.status = status

    def _publish_frame(self, frame_bytes):
        self.frame_count += 1
        try:
            with open(self.latest_frame_path, "wb") as frame_file:
                frame_file.write(frame_bytes)
        except OSError:
            pass
        if self.frame_count % 5 == 0:
            print(f"received processed frame {self.frame_count}", flush=True)
        with self.lock:
            self.latest_frame = bytes(frame_bytes)

    def _run_thread(self):
        try:
            asyncio.run(self._stream_loop())
        except Exception as exc:
            self._set_status(f"stream error | {exc}")
        finally:
            if self.stop_event.is_set():
                self._set_status("stopped | camera stream idle")

    def _opencv_camera_source(self):
        return int(self.camera_source) if str(self.camera_source).isdigit() else self.camera_source

    async def _stream_loop(self):
        try:
            import websockets
        except ImportError as exc:
            self._set_status(f"missing dependency | pip install {exc.name}")
            return

        if self.camera_source.lower() in {"rpicam", "libcamera"}:
            await self._rpicam_stream_loop(websockets)
            return

        try:
            import cv2
        except ImportError:
            await self._rpicam_stream_loop(websockets)
            return

        capture = cv2.VideoCapture(self._opencv_camera_source())
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.send_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.send_width * 9 / 16))
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not capture.isOpened():
            self._set_status(f"camera error | could not open {self.camera_source}")
            return

        try:
            self._set_status(f"connecting | {self.ws_url}")
            async with websockets.connect(
                self.ws_url,
                max_size=8_000_000,
                compression=None,
                ping_interval=20,
                ping_timeout=20,
            ) as websocket:
                self._set_status(f"connected | {self.ws_url}")
                last_frame_time = time.perf_counter()

                while not self.stop_event.is_set():
                    loop_started = time.perf_counter()
                    ok, frame = capture.read()
                    if not ok:
                        self._set_status("camera error | frame read failed")
                        break

                    frame = cv2.flip(frame, 1)
                    if frame.shape[1] != self.send_width:
                        send_height = max(1, int(frame.shape[0] * self.send_width / frame.shape[1]))
                        frame = cv2.resize(frame, (self.send_width, send_height), interpolation=cv2.INTER_AREA)

                    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
                    if not ok:
                        self._set_status("encode error | could not compress camera frame")
                        continue

                    await websocket.send(encoded.tobytes())
                    response = await asyncio.wait_for(websocket.recv(), timeout=15)
                    if isinstance(response, str):
                        self._set_status(response)
                        continue

                    if not response:
                        self._set_status("decode error | empty GPU response frame")
                        continue

                    self._publish_frame(response)
                    now = time.perf_counter()
                    fps = 1.0 / max(now - last_frame_time, 1e-6)
                    self.last_fps = 0.85 * self.last_fps + 0.15 * fps if self.last_fps else fps
                    last_frame_time = now
                    self._set_status(
                        f"streaming | GPU DensePose {self.last_fps:.1f} FPS | "
                        f"{self.send_width}px q{self.jpeg_quality}"
                    )

                    sleep_for = (1.0 / self.target_fps) - (time.perf_counter() - loop_started)
                    if sleep_for > 0:
                        await asyncio.sleep(sleep_for)
        finally:
            capture.release()

    async def _rpicam_stream_loop(self, websockets):
        height = max(1, int(self.send_width * 9 / 16))
        command = [
            "rpicam-vid",
            "--nopreview",
            "--width",
            str(self.send_width),
            "--height",
            str(height),
            "--framerate",
            str(max(1, int(self.target_fps))),
            "--timeout",
            "0",
            "--codec",
            "mjpeg",
            "--quality",
            str(self.jpeg_quality),
            "--segment",
            "1",
            "--output",
            "-",
        ]

        self._set_status("opencv unavailable | using RF Sensor stream")
        process = None
        try:
            async with websockets.connect(
                self.ws_url,
                max_size=8_000_000,
                compression=None,
                ping_interval=20,
                ping_timeout=20,
            ) as websocket:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,
                )
                self._set_status(f"connected via RF sensor | {self.ws_url}")
                last_frame_time = time.perf_counter()
                jpeg_buffer = bytearray()

                while not self.stop_event.is_set():
                    loop_started = time.perf_counter()
                    if process.poll() is not None:
                        self._set_status(f"RF sensor exited | code {process.returncode}")
                        break

                    frame = self._read_mjpeg_frame(process, jpeg_buffer)
                    if frame is None:
                        await asyncio.sleep(1.0)
                        continue

                    await websocket.send(frame)
                    response = await asyncio.wait_for(websocket.recv(), timeout=20)
                    if isinstance(response, str):
                        self._set_status(response)
                        continue

                    self._publish_frame(response)
                    now = time.perf_counter()
                    fps = 1.0 / max(now - last_frame_time, 1e-6)
                    self.last_fps = 0.85 * self.last_fps + 0.15 * fps if self.last_fps else fps
                    last_frame_time = now
                    self._set_status(
                        f"streaming | RF sensor GPU DensePose {self.last_fps:.1f} FPS | "
                        f"{self.send_width}px q{self.jpeg_quality}"
                    )

                    sleep_for = (1.0 / self.target_fps) - (time.perf_counter() - loop_started)
                    if sleep_for > 0:
                        await asyncio.sleep(sleep_for)
        except Exception as exc:
            self._set_status(f"stream error | {exc}")
        finally:
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()

    def _read_mjpeg_frame(self, process, jpeg_buffer):
        if process.stdout is None:
            return None

        while not self.stop_event.is_set():
            chunk = process.stdout.read(4096)
            if not chunk:
                return None
            jpeg_buffer.extend(chunk)
            start = jpeg_buffer.find(b"\xff\xd8")
            end = jpeg_buffer.find(b"\xff\xd9", start + 2 if start >= 0 else 0)

            if start < 0:
                del jpeg_buffer[:-1]
                continue
            if end < 0:
                if start > 0:
                    del jpeg_buffer[:start]
                continue

            frame = bytes(jpeg_buffer[start : end + 2])
            del jpeg_buffer[: end + 2]
            return frame
        return None


class RuViewApp:
    def __init__(self):
        pygame.init()
        # Default to fullscreen on the Pi panel so the OS taskbar / window chrome don't
        # eat the bottom toolbar. Override with RUVIEW_FULLSCREEN=0 for windowed dev.
        self.fullscreen = os.environ.get("RUVIEW_FULLSCREEN", "1") != "0"
        flags = pygame.FULLSCREEN if self.fullscreen else 0
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
        pygame.display.set_caption("ANGELWAR")
        pygame.mouse.set_visible(not self.fullscreen)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 20)
        self.small_font = pygame.font.Font(None, 17)
        self.large_font = pygame.font.Font(None, 28)
        self.backend = BackendManager()
        self.camera_stream = CameraDensePoseStream()
        self.active_floor_index = 0
        self.expanded_minimap = False
        self.buttons: list[Button] = []
        self.camera_surface = pygame.Surface((CAMERA_STREAM_WIDTH, CAMERA_STREAM_HEIGHT))
        self.camera_surface.fill((0, 0, 0))
        self.floor_surfaces = self.load_floor_surfaces()
        # Tactical overlay state
        self.sim_start = time.perf_counter()
        self.selected_target = None        # {"floor_idx": int, "kind": "trapped"|"teammates", "idx": int}
        self.expanded_map_rect: pygame.Rect | None = None
        self.preview_map_rect: pygame.Rect | None = None
        # User-tagged markers (per-floor). Each bucket is appended to the static seed at render time.
        self.user_tags = {
            i: {"trapped": [], "hazards": [], "events": [], "patients": []} for i in range(len(FLOOR_MAPS))
        }
        self.tag_mode: str | None = None    # None | "trapped" | "hazards" | "events" | "patients"
        self.patient_alert = TwilioPatientAlert()
        self.motion_poller = MotionDataPoller()
        self.show_motion_view = False
        if os.environ.get("RUVIEW_AUTOSTART_STREAM", "0") == "1":
            self.camera_stream.start()

    def load_floor_surfaces(self):
        surfaces = []
        for floor in FLOOR_MAPS:
            path = os.path.join(ASSET_DIR, floor["asset"])
            try:
                surfaces.append(pygame.image.load(path).convert_alpha())
            except (FileNotFoundError, pygame.error):
                placeholder = pygame.Surface((320, 180))
                placeholder.fill((30, 34, 48))
                self.draw_text(placeholder, "MAP ASSET MISSING", (20, 20), AMBER)
                surfaces.append(placeholder)
        return surfaces

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    running = self.handle_key(event.key)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(event.pos)

            self.backend.update()
            self.update_camera_surface()
            self.render()
            pygame.display.flip()
            self.clock.tick(FPS)

        self.camera_stream.stop()
        pygame.quit()

    def handle_key(self, key):
        if key in (pygame.K_ESCAPE, pygame.K_q):
            return False
        if key == pygame.K_f:
            self._toggle_fullscreen()
            return True
        if key == pygame.K_SPACE:
            self.camera_stream.toggle()
        elif key == pygame.K_m:
            self.expanded_minimap = not self.expanded_minimap
            self.selected_target = None
        elif pygame.K_1 <= key <= pygame.K_4:
            new_floor = key - pygame.K_1
            if new_floor != self.active_floor_index:
                self.selected_target = None
            self.active_floor_index = new_floor
        elif key == pygame.K_x:
            self.selected_target = None
        return True

    def handle_click(self, pos):
        for button in self.buttons:
            if button.rect.collidepoint(pos):
                if button.action == "toggle_stream":
                    self.camera_stream.toggle()
                elif button.action == "stop_stream":
                    self.camera_stream.stop()
                elif button.action == "floor":
                    new_floor = int(button.value)
                    if new_floor != self.active_floor_index:
                        self.selected_target = None
                    self.active_floor_index = new_floor
                elif button.action == "toggle_minimap":
                    self.expanded_minimap = not self.expanded_minimap
                    self.selected_target = None
                    self.tag_mode = None
                elif button.action == "unlock_target":
                    self.selected_target = None
                elif button.action == "set_tag_mode":
                    self.tag_mode = None if self.tag_mode == button.value else button.value
                elif button.action == "open_motion_view":
                    self.show_motion_view = True
                elif button.action == "close_motion_view":
                    self.show_motion_view = False
                elif button.action == "clear_tags":
                    had_patients = bool(self.user_tags[self.active_floor_index].get("patients"))
                    self.user_tags[self.active_floor_index] = {"trapped": [], "hazards": [], "events": [], "patients": []}
                    if had_patients:
                        self._notify_patients_tag_changed()
                    self.selected_target = None
                return

        # No button hit. If the expanded minimap is open and the click is on the map:
        #   - tag_mode active -> drop a marker at the click point
        #   - otherwise       -> try to lock onto the nearest trapped/teammate dot
        if self.expanded_minimap and self.expanded_map_rect and self.expanded_map_rect.collidepoint(pos):
            if self.tag_mode is not None:
                self._drop_tag(pos, self.expanded_map_rect)
                return
            hit = self.hit_test_map(pos, self.expanded_map_rect)
            self.selected_target = (
                None
                if hit is None
                else {"floor_idx": self.active_floor_index, "kind": hit[0], "idx": hit[1]}
            )

    def _drop_tag(self, pos, map_rect):
        rx = (pos[0] - map_rect.x) / map_rect.width
        ry = (pos[1] - map_rect.y) / map_rect.height
        rx = max(0.02, min(0.98, rx))
        ry = max(0.02, min(0.98, ry))
        bucket = self.user_tags[self.active_floor_index][self.tag_mode]
        n = len(bucket) + 1
        if self.tag_mode == "trapped":
            bucket.append({"x": rx, "y": ry, "label": f"VIC*{n}", "status": "DETECTED", "user": True})
        elif self.tag_mode == "hazards":
            bucket.append({"x": rx, "y": ry, "type": "TAG", "user": True})
        elif self.tag_mode == "patients":
            bucket.append({"x": rx, "y": ry, "label": f"PAT*{n}", "status": "PATIENT", "user": True})
            self._notify_patients_tag_changed()
        else:  # events
            bucket.append({"x": rx, "y": ry, "label": f"EVT*{n}", "user": True})

    def _notify_patients_tag_changed(self):
        floor_label = FLOOR_MAPS[self.active_floor_index]["label"]
        patient_count = len(self.user_tags[self.active_floor_index].get("patients", []))
        self.patient_alert.notify_patients_changed(floor_label=floor_label, patient_count=patient_count)

    def _toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        flags = pygame.FULLSCREEN if self.fullscreen else 0
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
        pygame.mouse.set_visible(not self.fullscreen)

    def update_camera_surface(self):
        frame = self.camera_stream.consume_frame()
        if frame is None:
            return
        try:
            decoded = pygame.image.load(io.BytesIO(frame)).convert()
            self.camera_surface = pygame.transform.smoothscale(
                decoded,
                (CAMERA_STREAM_WIDTH, CAMERA_STREAM_HEIGHT),
            )
        except pygame.error as exc:
            self.camera_stream._set_status(f"display decode error | {exc}")

    def render(self):
        self.buttons = []
        self.screen.fill(BG)
        if self.show_motion_view:
            self.draw_motion_view()
            return
        if self.expanded_minimap:
            self.draw_expanded_minimap()
            return

        self.draw_header()
        self.draw_node_panel(pygame.Rect(10, 70, 175, 390))
        self.draw_stream_panel(pygame.Rect(200, 70, 400, 390))
        self.draw_minimap_panel(pygame.Rect(615, 70, 175, 160))
        self.draw_telemetry_panel(pygame.Rect(615, 240, 175, 220))

    def draw_motion_view(self):
        """Full-screen motion telemetry: per-sender live cards + score-over-time
        line chart + score waterfall. Pulls from MotionDataPoller (local JSONL tail)."""
        # Header
        self.draw_text(self.screen, "MOTION TELEMETRY", (12, 14), CYAN, self.large_font)
        self.draw_text(self.screen, f"| {self.motion_poller.status}",
                       (240, 18), TEXT_DIM, self.small_font)
        self.draw_button(pygame.Rect(WIDTH - 150, 12, 90, 30), "BACK", "close_motion_view")
        pygame.draw.line(self.screen, PANEL_BORDER, (10, 52), (WIDTH - 10, 52), 1)

        snap = self.motion_poller.snapshot()
        if not snap:
            self.draw_text(self.screen,
                           "Awaiting MOTION data. Is backend/motion_plot.py running?",
                           (12, 80), MUTED)
            return

        sender_ids = sorted(snap.keys())
        now = time.time()
        SENDER_PALETTE = [(0, 200, 255), (255, 150, 60), (120, 230, 120),
                          (240, 100, 200), (200, 200, 80)]

        # ----- Per-sender live cards -----
        cards_rect = pygame.Rect(10, 62, WIDTH - 20, 110)
        n = max(1, len(sender_ids))
        card_w = (cards_rect.width - (n - 1) * 8) // n
        for i, sid in enumerate(sender_ids):
            history = snap.get(sid, [])
            if not history:
                continue
            last_t, last_s, last_lvl = history[-1]
            stale = (now - last_t) > 3.0
            level_color = GREEN if last_lvl == 0 else AMBER if last_lvl == 1 else RED
            border_color = MUTED if stale else level_color
            label = "QUIET" if last_lvl == 0 else "MOTION" if last_lvl == 1 else "BUSY"
            if stale:
                label += " (stale)"

            r = pygame.Rect(cards_rect.x + i * (card_w + 8), cards_rect.y, card_w, cards_rect.height)
            pygame.draw.rect(self.screen, PANEL_BG, r, border_radius=6)
            pygame.draw.rect(self.screen, border_color, r, 2, border_radius=6)
            self.draw_text(self.screen, f"SENDER 0x{sid:02x}", (r.x + 10, r.y + 8), level_color)
            self.draw_text(self.screen, f"{last_s:.2f}", (r.x + 10, r.y + 28), TEXT, self.large_font)
            self.draw_text(self.screen, label, (r.x + 10, r.y + 62), level_color, self.small_font)
            self.draw_text(self.screen, f"{len(history)} pts / {self.motion_poller.history_seconds:.0f}s",
                           (r.x + 10, r.y + 82), TEXT_DIM, self.small_font)

            # Sparkline
            if len(history) >= 2:
                sp = pygame.Rect(r.x + 110, r.y + 28, r.width - 120, r.height - 38)
                ymax = max(s for _, s, _ in history) * 1.15 + 0.1
                pts = [
                    (sp.x + sp.width * (j / max(1, len(history) - 1)),
                     sp.bottom - sp.height * min(1.0, s / ymax))
                    for j, (_, s, _) in enumerate(history)
                ]
                pygame.draw.line(self.screen, PANEL_BORDER, (sp.x, sp.bottom), (sp.right, sp.bottom), 1)
                if len(pts) >= 2:
                    pygame.draw.lines(self.screen, level_color, False, pts, 2)

        # ----- Combined score-over-time line chart -----
        chart_rect = pygame.Rect(10, 180, WIDTH - 20, 140)
        self.draw_panel(chart_rect, "MOTION SCORE OVER TIME (last 30s)", CYAN)
        plot = pygame.Rect(chart_rect.x + 36, chart_rect.y + 32,
                           chart_rect.width - 50, chart_rect.height - 46)
        pygame.draw.rect(self.screen, (0, 0, 0), plot)
        pygame.draw.rect(self.screen, PANEL_BORDER, plot, 1)

        all_scores = [s for hist in snap.values() for _, s, _ in hist]
        ymax = max(all_scores) * 1.15 + 0.1 if all_scores else 5.0
        tmin = now - self.motion_poller.history_seconds
        tspan = max(0.001, self.motion_poller.history_seconds)

        # Threshold guides at score=1.5 and 4.0
        for thresh, color in [(1.5, AMBER), (4.0, RED)]:
            if thresh < ymax:
                y = plot.bottom - plot.height * (thresh / ymax)
                pygame.draw.line(self.screen, (color[0] // 3, color[1] // 3, color[2] // 3),
                                 (plot.x, y), (plot.right, y), 1)

        # Y-axis labels
        for frac, lbl in [(0.0, "0"), (0.5, f"{ymax / 2:.1f}"), (1.0, f"{ymax:.1f}")]:
            y = plot.bottom - plot.height * frac
            self.draw_text(self.screen, lbl, (chart_rect.x + 6, int(y) - 6), TEXT_DIM, self.small_font)

        for i, sid in enumerate(sender_ids):
            history = snap[sid]
            if len(history) < 2:
                continue
            color = SENDER_PALETTE[i % len(SENDER_PALETTE)]
            pts = []
            for (t, s, _) in history:
                x = plot.x + plot.width * max(0.0, min(1.0, (t - tmin) / tspan))
                y = plot.bottom - plot.height * min(1.0, s / ymax)
                pts.append((x, y))
            if len(pts) >= 2:
                pygame.draw.lines(self.screen, color, False, pts, 2)
            # legend swatch
            lx = chart_rect.right - 110 + (i % 3) * 36
            ly = chart_rect.y + 12 + (i // 3) * 14
            pygame.draw.rect(self.screen, color, pygame.Rect(lx, ly, 10, 10))
            self.draw_text(self.screen, f"0x{sid:02x}", (lx + 14, ly - 2), TEXT, self.small_font)

        # ----- Score waterfall (one row per sender, color = score intensity) -----
        wf_rect = pygame.Rect(10, 328, WIDTH - 20, HEIGHT - 338)
        self.draw_panel(wf_rect, "SCORE WATERFALL — newest at right", AMBER)
        wf = pygame.Rect(wf_rect.x + 36, wf_rect.y + 32,
                         wf_rect.width - 50, wf_rect.height - 42)
        pygame.draw.rect(self.screen, (0, 0, 0), wf)
        pygame.draw.rect(self.screen, PANEL_BORDER, wf, 1)

        if sender_ids:
            row_h = wf.height / len(sender_ids)
            for ri, sid in enumerate(sender_ids):
                history = snap.get(sid, [])
                row_top = int(wf.y + ri * row_h)
                row_bot = int(wf.y + (ri + 1) * row_h)
                self.draw_text(self.screen, f"0x{sid:02x}",
                               (wf_rect.x + 4, row_top + 4), TEXT, self.small_font)
                # rasterize score → color into pixel columns
                for (t, s, _) in history:
                    col = int((t - tmin) / tspan * wf.width)
                    if not (0 <= col < wf.width):
                        continue
                    intensity = max(0.0, min(1.0, s / 6.0))
                    # green → amber → red
                    if intensity < 0.5:
                        k = intensity * 2
                        rgb = (int(255 * k), int(220), int(80 * (1 - k)))
                    else:
                        k = (intensity - 0.5) * 2
                        rgb = (255, int(220 * (1 - k * 0.7)), int(80 * (1 - k)))
                    pygame.draw.line(self.screen, rgb,
                                     (wf.x + col, row_top + 1),
                                     (wf.x + col, row_bot - 1), 1)
                if ri < len(sender_ids) - 1:
                    pygame.draw.line(self.screen, PANEL_BORDER,
                                     (wf.x, row_bot), (wf.right, row_bot), 1)

    def draw_header(self):
        self.draw_text(self.screen, "ANGELWARE", (12, 14), CYAN, self.large_font)
        status = self.backend.status["data"]
        self.draw_text(
            self.screen,
            f"| COMMAND CENTER v1.0 | {status['status'].upper()} | {status['performance']['average_fps']} FPS",
            (190, 18),
            TEXT_DIM,
        )
        pygame.draw.line(self.screen, PANEL_BORDER, (10, 52), (790, 52), 1)

    def draw_panel(self, rect, title, color):
        pygame.draw.rect(self.screen, PANEL_BG, rect, border_radius=6)
        pygame.draw.rect(self.screen, PANEL_BORDER, rect, 1, border_radius=6)
        self.draw_text(self.screen, title, (rect.x + 10, rect.y + 10), color)

    def draw_node_panel(self, rect):
        self.draw_panel(rect, "NODES", GREEN)
        y = rect.y + 38
        for node in self.backend.nodes:
            if y > rect.bottom - 96:
                break
            status_color = GREEN if node["status"] == "ONLINE" else RED
            self.draw_text(self.screen, node["name"], (rect.x + 10, y), TEXT)
            self.draw_text(self.screen, f"* {node['status']}", (rect.x + 18, y + 18), status_color, self.small_font)
            self.draw_text(self.screen, node["rssi"], (rect.x + 98, y + 18), MUTED, self.small_font)
            if "proximity_zone" in node:
                prox = node["proximity_zone"].upper()
                distance = node["estimated_distance_m"]
                self.draw_text(self.screen, f"PROX: {prox} | ~{distance}m", (rect.x + 18, y + 34), self.proximity_color(node["proximity_zone"]), self.small_font)
                separator_y = y + 50
                row_height = 58
            else:
                separator_y = y + 42
                row_height = 50
            pygame.draw.line(self.screen, PANEL_BORDER, (rect.x + 10, separator_y), (rect.right - 10, separator_y))
            y += row_height

        self.draw_button(pygame.Rect(rect.x + 10, rect.bottom - 78, rect.width - 20, 28), "SCAN MESH", "noop")
        self.draw_button(pygame.Rect(rect.x + 10, rect.bottom - 40, rect.width - 20, 28), "SYSTEM REBOOT", "noop")

    def draw_stream_panel(self, rect):
        self.draw_panel(rect, "ANGELWARE", CYAN)
        image_rect = pygame.Rect(rect.x + 10, rect.y + 40, CAMERA_STREAM_WIDTH, CAMERA_STREAM_HEIGHT)
        pygame.draw.rect(self.screen, (0, 0, 0), image_rect)
        self.screen.blit(self.camera_surface, image_rect)
        pygame.draw.rect(self.screen, (0, 180, 216), image_rect, 1)

        y = image_rect.bottom + 12
        self.draw_text(self.screen, "RF Sensor -> RunPod GPU -> DensePose-only output", (rect.x + 10, y), MUTED, self.small_font)
        self.draw_wrapped_text(self.screen, self.camera_stream.status, pygame.Rect(rect.x + 10, y + 22, 380, 42), GREEN)
        self.draw_text(
            self.screen,
            f"CAM {self.camera_stream.camera_source} | {self.camera_stream.send_width}px | JPG {self.camera_stream.jpeg_quality} | {self.camera_stream.target_fps:.0f} FPS",
            (rect.x + 10, rect.bottom - 72),
            TEXT_DIM,
            self.small_font,
        )
        label = "STOP STREAM" if self.camera_stream.is_running() else "START STREAM"
        self.draw_button(pygame.Rect(rect.x + 10, rect.bottom - 40, 150, 30), label, "toggle_stream")
        self.draw_button(pygame.Rect(rect.x + 170, rect.bottom - 40, 80, 30), "STOP", "stop_stream")
        self.draw_button(pygame.Rect(rect.x + 260, rect.bottom - 40, 90, 30), "MOTION", "open_motion_view")
        self.draw_text(self.screen, "SPACE start/stop | 1-4 floors | M map | Q quit", (rect.x + 10, rect.bottom - 102), TEXT_DIM, self.small_font)

    # ----- Tactical overlay helpers ---------------------------------------

    def _floor_entities(self, floor_index: int) -> dict:
        """Static seed + user-tagged markers, merged for rendering / hit-tests."""
        floor = FLOOR_MAPS[floor_index]
        base = FLOOR_ENTITIES.get(floor["asset"], {})
        tags = self.user_tags.get(floor_index, {})
        patient_tags = list(tags.get("patients", []))
        return {
            "self": base.get("self"),
            "teammates": base.get("teammates", []),
            "trapped": list(base.get("trapped", [])) + list(tags.get("trapped", [])) + patient_tags,
            "patients": patient_tags,
            "hazards": list(base.get("hazards", [])) + list(tags.get("hazards", [])),
            "events": list(tags.get("events", [])),
            "nodes": base.get("nodes", []),
            "links": base.get("links", []),
            "exits": base.get("exits", []),
        }

    def sim_tick(self) -> float:
        return time.perf_counter() - self.sim_start

    def _wobble(self, seed, ax, ay, freq=1.0, phase=0.0):
        t = self.sim_tick() * freq + phase + seed * 0.91
        return ax * math.sin(t), ay * math.cos(t * 1.3 + 0.7)

    def live_pos(self, entity, kind, idx):
        """Return the live (x, y) normalized position for an entity. Mesh nodes/exits are anchored."""
        bx, by = entity["x"], entity["y"]
        if kind == "trapped":
            dx, dy = self._wobble(idx + 11, 0.004, 0.004, 1.5)
        elif kind == "teammate":
            dx, dy = self._wobble(idx + 23, 0.022, 0.018, 0.55)
        elif kind == "self":
            dx, dy = self._wobble(0, 0.014, 0.011, 0.4)
        elif kind == "hazard":
            dx, dy = self._wobble(idx + 41, 0.008, 0.005, 2.4)
        else:
            dx, dy = 0.0, 0.0
        return max(0.02, min(0.98, bx + dx)), max(0.02, min(0.98, by + dy))

    def _nearest_node_index(self, nodes, point):
        if not nodes:
            return None
        px, py = point
        return min(range(len(nodes)), key=lambda i: (nodes[i]["x"] - px) ** 2 + (nodes[i]["y"] - py) ** 2)

    def compute_rescue_route(self, entities, self_xy):
        """Hop self -> nearest mesh node -> target's nearest mesh node -> target. Returns (waypoints, hop_idxs)."""
        if (
            self.selected_target is None
            or self.selected_target["floor_idx"] != self.active_floor_index
        ):
            return None, None
        kind = self.selected_target["kind"]
        targets = entities.get(kind, [])
        idx = self.selected_target["idx"]
        if idx >= len(targets):
            return None, None
        kind_singular = "trapped" if kind == "trapped" else "teammate"
        tx, ty = self.live_pos(targets[idx], kind_singular, idx)
        nodes = entities.get("nodes", [])
        pts = [self_xy]
        hops: list[int] = []
        if nodes:
            i_self = self._nearest_node_index(nodes, self_xy)
            i_target = self._nearest_node_index(nodes, (tx, ty))
            pts.append((nodes[i_self]["x"], nodes[i_self]["y"]))
            hops.append(i_self)
            if i_target != i_self:
                pts.append((nodes[i_target]["x"], nodes[i_target]["y"]))
                hops.append(i_target)
        pts.append((tx, ty))
        return pts, hops

    def compute_evac_route(self, entities, self_xy):
        exits = entities.get("exits", [])
        if not exits:
            return None
        sx, sy = self_xy
        ex = min(exits, key=lambda e: (e["x"] - sx) ** 2 + (e["y"] - sy) ** 2)
        return [self_xy, (ex["x"], ex["y"])]

    def hit_test_map(self, pos, map_rect):
        """Translate a screen-space click into normalized map coords and find the nearest dot."""
        rx = (pos[0] - map_rect.x) / map_rect.width
        ry = (pos[1] - map_rect.y) / map_rect.height
        if not (0 <= rx <= 1 and 0 <= ry <= 1):
            return None
        entities = self._floor_entities(self.active_floor_index)
        best = None
        best_d2 = HIT_RADIUS_NORM ** 2
        for kind, kind_singular in (("trapped", "trapped"), ("teammates", "teammate")):
            for i, e in enumerate(entities.get(kind, [])):
                ex, ey = self.live_pos(e, kind_singular, i)
                d2 = (ex - rx) ** 2 + (ey - ry) ** 2
                if d2 < best_d2:
                    best_d2 = d2
                    best = (kind, i)
        return best

    def _dashed_line(self, surface, color, p0, p1, width=2, dash=8):
        ax, ay = p0
        bx, by = p1
        seg_len = math.hypot(bx - ax, by - ay)
        if seg_len <= 0:
            return
        steps = max(1, int(seg_len / dash))
        for k in range(0, steps, 2):
            t0 = k / steps
            t1 = min(1.0, (k + 1) / steps)
            pygame.draw.line(
                surface, color,
                (ax + (bx - ax) * t0, ay + (by - ay) * t0),
                (ax + (bx - ax) * t1, ay + (by - ay) * t1),
                width,
            )

    def _draw_arrowhead(self, color, tip, src, size=8, width=2):
        tx, ty = tip
        sx, sy = src
        dx, dy = tx - sx, ty - sy
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        # Two side points for the arrowhead
        left = (tx - ux * size + uy * size * 0.5, ty - uy * size - ux * size * 0.5)
        right = (tx - ux * size - uy * size * 0.5, ty - uy * size + ux * size * 0.5)
        pygame.draw.polygon(self.screen, color, [tip, left, right])

    def draw_floor_overlay(self, map_rect: pygame.Rect, floor_index: int, *, detail: str = "full"):
        """Render entities + routes on top of the floor image at map_rect."""
        floor = FLOOR_MAPS[floor_index]
        entities = self._floor_entities(floor_index)
        if not entities:
            return
        full = detail == "full"
        s = 1.0 if full else 0.6

        def to_px(p):
            return (
                int(map_rect.x + p[0] * map_rect.width),
                int(map_rect.y + p[1] * map_rect.height),
            )

        # Subtle dim overlay so colored markers pop
        dim = pygame.Surface(map_rect.size, pygame.SRCALPHA)
        dim.fill((8, 12, 20, 60))
        self.screen.blit(dim, map_rect.topleft)

        # Mesh links (drawn faint, behind everything)
        nodes = entities.get("nodes", [])
        nodes_px = [to_px((n["x"], n["y"])) for n in nodes]
        for a, b in entities.get("links", []):
            if a < len(nodes_px) and b < len(nodes_px):
                pygame.draw.line(self.screen, COLOR_LINK, nodes_px[a], nodes_px[b], 1)

        # Live self position
        self_e = entities.get("self")
        self_xy = self.live_pos(self_e, "self", 0) if self_e else (0.5, 0.5)

        # Routes
        rescue_pts, rescue_hops = self.compute_rescue_route(entities, self_xy)
        evac_pts = self.compute_evac_route(entities, self_xy)

        def draw_route(pts_norm, color, *, dashed=False, label=None):
            if not pts_norm or len(pts_norm) < 2:
                return
            pts = [to_px(p) for p in pts_norm]
            thickness = 3 if full else 2
            for i in range(len(pts) - 1):
                if dashed:
                    self._dashed_line(self.screen, color, pts[i], pts[i + 1], width=thickness)
                else:
                    pygame.draw.line(self.screen, color, pts[i], pts[i + 1], thickness)
            if full:
                for p in pts[1:-1]:
                    pygame.draw.circle(self.screen, color, p, 3)
            self._draw_arrowhead(color, pts[-1], pts[-2], size=9 if full else 6)
            if full and label:
                tip = pts[-1]
                self.draw_text(self.screen, label, (tip[0] + 6, tip[1] + 6), color, self.small_font)

        if rescue_pts:
            draw_route(rescue_pts, COLOR_RESCUE, label="RESCUE")
        if evac_pts:
            draw_route(evac_pts, COLOR_EVAC, dashed=True, label="EVAC" if full else None)

        # Mesh nodes (highlight hop nodes used by the active rescue route)
        hop_set = set(rescue_hops or [])
        for i, (nx, ny) in enumerate(nodes_px):
            d = int(4 * s)
            color = COLOR_HOP if i in hop_set else COLOR_NODE
            pygame.draw.polygon(
                self.screen, color,
                [(nx, ny - d), (nx + d, ny), (nx, ny + d), (nx - d, ny)],
            )
            if full:
                self.draw_text(self.screen, f"N{i+1}", (nx + d + 2, ny - 8), color, self.small_font)

        # Exits
        for ex in entities.get("exits", []):
            x, y = to_px((ex["x"], ex["y"]))
            d = int(5 * s)
            pygame.draw.rect(self.screen, COLOR_EXIT, pygame.Rect(x - d, y - d, d * 2, d * 2))
            if full:
                self.draw_text(self.screen, ex.get("label", "X"), (x - 4, y - 8), (10, 30, 15), self.small_font)

        # Hazards (animated)
        for i, hz in enumerate(entities.get("hazards", [])):
            hx, hy = self.live_pos(hz, "hazard", i)
            x, y = to_px((hx, hy))
            d = int(6 * s)
            pygame.draw.polygon(
                self.screen, COLOR_HAZARD,
                [(x, y - d), (x - d, y + d), (x + d, y + d)],
            )
            if full:
                self.draw_text(self.screen, hz.get("type", "HAZ"), (x + d + 2, y - 6), COLOR_HAZARD, self.small_font)

        # Events (user-tagged "other" markers — purple diamond outline with "!")
        for i, ev in enumerate(entities.get("events", [])):
            x, y = to_px((ev["x"], ev["y"]))
            d = int(7 * s)
            pygame.draw.polygon(
                self.screen, COLOR_EVENT,
                [(x, y - d), (x + d, y), (x, y + d), (x - d, y)],
                2,
            )
            if full:
                self.draw_text(self.screen, "!", (x - 2, y - 7), COLOR_EVENT, self.small_font)
                self.draw_text(self.screen, ev.get("label", "EVENT"), (x + d + 3, y - 8), COLOR_EVENT, self.small_font)

        sel = self.selected_target if self.selected_target and self.selected_target["floor_idx"] == self.active_floor_index else None

        # Teammates
        for i, tm in enumerate(entities.get("teammates", [])):
            tx, ty = self.live_pos(tm, "teammate", i)
            x, y = to_px((tx, ty))
            r = int(5 * s)
            if sel and sel["kind"] == "teammates" and sel["idx"] == i:
                pygame.draw.circle(self.screen, COLOR_HOP, (x, y), r + 5, 2)
            pygame.draw.circle(self.screen, (0, 0, 0), (x, y), r + 1)
            pygame.draw.circle(self.screen, COLOR_TEAMMATE, (x, y), r)
            if full:
                self.draw_text(self.screen, tm["label"], (x + r + 3, y - 8), COLOR_TEAMMATE, self.small_font)

        # Trapped civilians
        for i, vt in enumerate(entities.get("trapped", [])):
            tx, ty = self.live_pos(vt, "trapped", i)
            x, y = to_px((tx, ty))
            outer = int(9 * s)
            inner = int(4 * s)
            if sel and sel["kind"] == "trapped" and sel["idx"] == i:
                pygame.draw.circle(self.screen, COLOR_HOP, (x, y), outer + 5, 2)
            pygame.draw.circle(self.screen, COLOR_TRAPPED, (x, y), outer, 2)
            pygame.draw.circle(self.screen, COLOR_TRAPPED, (x, y), inner)
            if full:
                self.draw_text(self.screen, vt["label"], (x + outer + 3, y - 8), COLOR_TRAPPED, self.small_font)

        # Self (yellow triangle)
        if self_e:
            x, y = to_px(self_xy)
            d = int(8 * s)
            pygame.draw.polygon(
                self.screen, COLOR_SELF,
                [(x, y - d), (x - int(d * 0.85), y + int(d * 0.7)), (x + int(d * 0.85), y + int(d * 0.7))],
            )
            if full:
                self.draw_text(self.screen, self_e["label"], (x + d + 2, y - 8), COLOR_SELF, self.small_font)

        # Legend (full only)
        if full:
            n_team = len(entities.get("teammates", []))
            n_trap = len(entities.get("trapped", []))
            n_haz = len(entities.get("hazards", []))
            n_node = len(entities.get("nodes", []))
            n_evt = len(entities.get("events", []))
            legend_rect = pygame.Rect(map_rect.x + 8, map_rect.y + 8, 178, 126)
            legend_bg = pygame.Surface(legend_rect.size, pygame.SRCALPHA)
            legend_bg.fill((8, 14, 22, 200))
            self.screen.blit(legend_bg, legend_rect.topleft)
            pygame.draw.rect(self.screen, COLOR_NODE, legend_rect, 1)
            self.draw_text(self.screen, f"{floor['label']} · LIVE MESH", (legend_rect.x + 8, legend_rect.y + 4), COLOR_NODE, self.small_font)
            rows = [
                (COLOR_TRAPPED,  f"TRAPPED    x{n_trap}"),
                (COLOR_TEAMMATE, f"TEAM       x{n_team}"),
                (COLOR_HAZARD,   f"HAZARDS    x{n_haz}"),
                (COLOR_EVENT,    f"EVENTS     x{n_evt}"),
                (COLOR_NODE,     f"MESH NODES x{n_node}"),
                (COLOR_RESCUE,   "TAP DOT TO LOCK"),
            ]
            for i, (c, label) in enumerate(rows):
                ry = legend_rect.y + 24 + i * 16
                pygame.draw.circle(self.screen, c, (legend_rect.x + 16, ry + 6), 4)
                self.draw_text(self.screen, label, (legend_rect.x + 26, ry), TEXT, self.small_font)

    def draw_target_stats_panel(self):
        """Live distance/bearing/HR/CSI panel for the locked target. Renders only when expanded."""
        sel = self.selected_target
        if sel is None or sel["floor_idx"] != self.active_floor_index:
            return
        entities = self._floor_entities(self.active_floor_index)
        targets = entities.get(sel["kind"], [])
        if sel["idx"] >= len(targets):
            self.selected_target = None
            return

        target = targets[sel["idx"]]
        kind_singular = "trapped" if sel["kind"] == "trapped" else "teammate"
        tx, ty = self.live_pos(target, kind_singular, sel["idx"])
        self_e = entities.get("self") or {"x": 0.5, "y": 0.5}
        sx, sy = self.live_pos(self_e, "self", 0)

        dx, dy = tx - sx, ty - sy
        dist_m = math.hypot(dx, dy) * 30.0  # ~30 m across the floor
        bearing = (math.degrees(math.atan2(dx, -dy)) + 360.0) % 360.0
        eta_s = max(1.0, dist_m / 1.4)
        compass = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((bearing + 22.5) % 360 // 45)]

        seed = sel["idx"] + (10 if sel["kind"] == "trapped" else 30)
        t = self.sim_tick()
        if sel["kind"] == "trapped":
            hr = int(96 + 14 * math.sin(t * 1.6 + seed) + 7 * math.sin(t * 4.2 + seed * 0.5))
        else:
            hr = int(target.get("hr", 95) + 6 * math.sin(t * 1.1 + seed))
        sig_pct = max(35, min(99, int(82 + 10 * math.sin(t * 0.9 + seed) + 6 * math.cos(t * 2.7 + seed))))

        label = target.get("label", "?")
        status = target.get("status", "—") if sel["kind"] == "trapped" else "ON MOVE"
        accent = COLOR_TRAPPED if sel["kind"] == "trapped" else COLOR_TEAMMATE
        kind_text = "CIVILIAN" if sel["kind"] == "trapped" else "FIREFIGHTER"

        # Mesh-hop summary (route description)
        nodes = entities.get("nodes", [])
        if nodes:
            i_self = self._nearest_node_index(nodes, (sx, sy))
            i_target = self._nearest_node_index(nodes, (tx, ty))
            if i_self == i_target:
                hops_str = f"YOU -> N{i_self+1} -> {label}"
            else:
                hops_str = f"YOU -> N{i_self+1} -> N{i_target+1} -> {label}"
        else:
            hops_str = "direct"

        # Panel — translucent overlay top-right of the screen so map stays visible
        panel = pygame.Rect(WIDTH - 220, 56, 210, 250)
        bg = pygame.Surface(panel.size, pygame.SRCALPHA)
        bg.fill((10, 18, 28, 230))
        self.screen.blit(bg, panel.topleft)
        pygame.draw.rect(self.screen, accent, panel, 1, border_radius=4)

        # Title bar
        self.draw_text(self.screen, f"TARGET LOCK : {label}", (panel.x + 10, panel.y + 8), accent, self.font)
        pygame.draw.line(self.screen, accent, (panel.x + 8, panel.y + 30), (panel.right - 8, panel.y + 30), 1)

        # Stat rows
        rows = [
            ("CLASS", kind_text),
            ("DIST", f"{dist_m:5.1f} m"),
            ("BEARING", f"{bearing:5.0f} deg  {compass}"),
            ("ETA", f"{eta_s:5.0f} s"),
            ("HR", f"{hr} bpm"),
            ("CSI SIG", f"{sig_pct}%"),
            ("STATE", status),
        ]
        ry = panel.y + 38
        for k, v in rows:
            self.draw_text(self.screen, f"{k:<8}", (panel.x + 10, ry), MUTED, self.small_font)
            self.draw_text(self.screen, v, (panel.x + 78, ry), TEXT, self.small_font)
            ry += 18
        pygame.draw.line(self.screen, PANEL_BORDER, (panel.x + 8, ry + 4), (panel.right - 8, ry + 4), 1)
        ry += 10
        self.draw_text(self.screen, "MESH HOPS", (panel.x + 10, ry), COLOR_NODE, self.small_font)
        self.draw_wrapped_text(
            self.screen,
            hops_str,
            pygame.Rect(panel.x + 10, ry + 16, panel.width - 20, 32),
            TEXT,
            self.small_font,
        )

        # Unlock button
        self.draw_button(pygame.Rect(panel.x + 10, panel.bottom - 32, panel.width - 20, 24), "UNLOCK", "unlock_target")

    def draw_minimap_panel(self, rect):
        self.draw_panel(rect, "FACILITY MAP", CYAN)
        for index in range(len(FLOOR_MAPS)):
            button_rect = pygame.Rect(rect.x + 36 + index * 24, rect.y + 34, 18, 18)
            self.draw_button(button_rect, str(index + 1), "floor", index, compact=True)

        floor_surface = self.floor_surfaces[self.active_floor_index]
        scaled, scaled_rect = self.fit_surface(floor_surface, rect.width - 20, 86)
        scaled_rect.centerx = rect.centerx
        scaled_rect.y = rect.y + 64
        self.screen.blit(scaled, scaled_rect)
        self.draw_floor_overlay(scaled_rect, self.active_floor_index, detail="compact")
        pygame.draw.rect(self.screen, (0, 180, 216), scaled_rect, 1)
        self.preview_map_rect = scaled_rect.copy()
        self.draw_proximity_markers(scaled_rect)
        self.buttons.append(Button(scaled_rect, "map", "toggle_minimap"))

    def draw_telemetry_panel(self, rect):
        self.draw_panel(rect, "TELEMETRY", AMBER)
        y = rect.y + 38
        for log in self.backend.get_logs():
            self.draw_wrapped_text(self.screen, log, pygame.Rect(rect.x + 10, y, rect.width - 20, 34), (140, 145, 160), self.small_font)
            y += 34
        pygame.draw.line(self.screen, PANEL_BORDER, (rect.x + 10, rect.bottom - 70), (rect.right - 10, rect.bottom - 70))
        self.draw_text(self.screen, "GAIN CONTROL", (rect.x + 10, rect.bottom - 58), MUTED, self.small_font)
        pygame.draw.rect(self.screen, (32, 36, 52), (rect.x + 10, rect.bottom - 35, rect.width - 20, 8), border_radius=4)
        pygame.draw.rect(self.screen, CYAN, (rect.x + 10, rect.bottom - 35, int((rect.width - 20) * 0.75), 8), border_radius=4)

    def draw_expanded_minimap(self):
        self.screen.fill(BG)
        floor = FLOOR_MAPS[self.active_floor_index]
        self.draw_text(self.screen, f"{floor['label']} | {floor['detail']}", (20, 16), floor["color"], self.large_font)
        for index in range(len(FLOOR_MAPS)):
            self.draw_button(pygame.Rect(285 + index * 30, 16, 22, 22), str(index + 1), "floor", index, compact=True)
        self.draw_button(pygame.Rect(625, 14, 110, 30), "MINIMIZE", "toggle_minimap")

        # Leave room for the stats panel on the right when a target is locked
        max_w = 540 if (self.selected_target and self.selected_target["floor_idx"] == self.active_floor_index) else 760
        scaled, scaled_rect = self.fit_surface(self.floor_surfaces[self.active_floor_index], max_w, 380)
        # Anchor the map to the left half so the stats panel can sit on the right.
        # Vertically: header sits at y<=44, tag toolbar starts at y=HEIGHT-36, so center between.
        scaled_rect.x = max(20, (max_w + 40 - scaled_rect.width) // 2)
        scaled_rect.y = 245 - scaled_rect.height // 2
        self.screen.blit(scaled, scaled_rect)
        self.draw_floor_overlay(scaled_rect, self.active_floor_index, detail="full")
        pygame.draw.rect(self.screen, PANEL_BORDER, scaled_rect, 1)
        self.expanded_map_rect = scaled_rect.copy()
        self.draw_proximity_markers(scaled_rect, expanded=True)

        self.draw_target_stats_panel()

        # Tag toolbar — drop hazards / trapped / events on the map
        toolbar_y = HEIGHT - 36
        self.draw_button(pygame.Rect(10, toolbar_y, 92, 26), "+ HAZARD",  "set_tag_mode", "hazards", compact=True)
        self.draw_button(pygame.Rect(108, toolbar_y, 96, 26), "+ TRAPPED", "set_tag_mode", "trapped", compact=True)
        self.draw_button(pygame.Rect(210, toolbar_y, 88, 26), "+ EVENT",   "set_tag_mode", "events",  compact=True)
        self.draw_button(pygame.Rect(304, toolbar_y, 98, 26), "+ PATIENT", "set_tag_mode", "patients", compact=True)
        self.draw_button(pygame.Rect(408, toolbar_y, 102, 26), "CLEAR TAGS", "clear_tags", compact=True)

        if self.tag_mode is not None:
            mode_label = {"trapped": "TRAPPED", "hazards": "HAZARD", "events": "EVENT", "patients": "PATIENT"}[self.tag_mode]
            mode_color = {
                "trapped": COLOR_TRAPPED,
                "hazards": COLOR_HAZARD,
                "events": COLOR_EVENT,
                "patients": GREEN,
            }[self.tag_mode]
            hint = f"{mode_label} TAG MODE | CLICK MAP TO DROP"
            self.draw_text(self.screen, hint, (520, toolbar_y + 6), mode_color, self.small_font)
        else:
            hint = "LOCK TARGET: TAP RED/CYAN DOT | X UNLOCK"
            self.draw_text(self.screen, hint, (520, toolbar_y + 6), TEXT_DIM, self.small_font)

    def fit_surface(self, surface, max_width, max_height):
        width, height = surface.get_size()
        scale = min(max_width / width, max_height / height)
        size = (max(1, int(width * scale)), max(1, int(height * scale)))
        scaled = pygame.transform.smoothscale(surface, size)
        return scaled, scaled.get_rect()

    def draw_button(self, rect, label, action, value=None, compact=False):
        active = (
            (action == "floor" and value == self.active_floor_index)
            or (action == "set_tag_mode" and value == self.tag_mode)
        )
        fill = (0, 180, 216) if active else (55, 62, 78)
        pygame.draw.rect(self.screen, fill, rect, border_radius=5)
        pygame.draw.rect(self.screen, CYAN if active else PANEL_BORDER, rect, 1, border_radius=5)
        font = self.small_font if compact else self.font
        text_surface = font.render(label, True, TEXT)
        self.screen.blit(text_surface, text_surface.get_rect(center=rect.center))
        if action != "noop":
            self.buttons.append(Button(rect, label, action, value))

    def draw_proximity_markers(self, map_rect, expanded=False):
        s3_pos = (map_rect.centerx, map_rect.centery)
        s3_radius = 6 if expanded else 4
        pygame.draw.circle(self.screen, CYAN, s3_pos, s3_radius)
        self.draw_text(self.screen, "S3", (s3_pos[0] + 7, s3_pos[1] - 7), CYAN, self.small_font)

        for node in self.backend.proximity_nodes:
            if node.get("floor", 0) != self.active_floor_index:
                continue
            position = node.get("map_position", {"x": 0.5, "y": 0.5})
            marker_pos = (
                int(map_rect.x + position["x"] * map_rect.width),
                int(map_rect.y + position["y"] * map_rect.height),
            )
            color = self.proximity_color(node["proximity_zone"])
            radius = 7 if expanded else 4
            pygame.draw.line(self.screen, color, s3_pos, marker_pos, 1)
            pygame.draw.circle(self.screen, color, marker_pos, radius)
            pygame.draw.circle(self.screen, BG, marker_pos, max(1, radius - 3))
            if expanded:
                label = f"{node['name']} {node['proximity_zone'].upper()} {node['estimated_distance_m']}m"
                self.draw_text(self.screen, label, (marker_pos[0] + 10, marker_pos[1] - 8), color, self.small_font)

    def proximity_color(self, zone):
        return {
            "near": GREEN,
            "medium": AMBER,
            "far": MUTED,
            "lost": RED,
        }.get(zone, MUTED)

    def draw_text(self, surface, text, pos, color=TEXT, font=None):
        font = font or self.font
        surface.blit(font.render(str(text), True, color), pos)

    def draw_wrapped_text(self, surface, text, rect, color=TEXT, font=None):
        font = font or self.font
        words = str(text).split()
        lines = []
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if font.size(candidate)[0] <= rect.width:
                line = candidate
            else:
                if line:
                    lines.append(line)
                line = word
        if line:
            lines.append(line)
        for index, line_text in enumerate(lines[: max(1, rect.height // font.get_height())]):
            self.draw_text(surface, line_text, (rect.x, rect.y + index * font.get_height()), color, font)


def main():
    RuViewApp().run()


if __name__ == "__main__":
    main()
