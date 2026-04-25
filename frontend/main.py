# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from dataclasses import dataclass

import pygame

# Ensure backend can be imported when running from frontend/ or the repo root.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.mock_service import RuViewMockService


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


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    action: str
    value: object | None = None


class BackendManager:
    """Manages connection to the RuView API (Mock or Live)."""

    def __init__(self):
        self.mock = RuViewMockService()
        self.use_mock = True
        self.backend_url = "http://localhost:8000"
        self.last_pose = None
        self.nodes = []
        self.status = self.mock.get_system_status()

    def update(self):
        if self.use_mock:
            self.last_pose = self.mock.get_latest_pose()
            self.nodes = self.mock.get_nodes()
            self.status = self.mock.get_system_status()

    def get_logs(self):
        average_fps = self.status["data"]["performance"]["average_fps"]
        online_nodes = len([node for node in self.nodes if node["status"] == "ONLINE"])
        return [
            f"[SYNC] {time.strftime('%H:%M:%S')} - Model: {average_fps} FPS",
            f"[NODE] Online Count: {online_nodes}",
            "[CSI] Multi-path interference low",
            "[POSE] RunPod stream target active",
            "[TRACK] Awaiting processed DensePose frame",
        ]


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
            self.status = status

    def _publish_frame(self, frame, cv2):
        resized = cv2.resize(frame, (CAMERA_STREAM_WIDTH, CAMERA_STREAM_HEIGHT), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        with self.lock:
            self.latest_frame = rgb.copy()

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
            import cv2
            import numpy as np
            import websockets
        except ImportError as exc:
            self._set_status(f"missing dependency | pip install {exc.name}")
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

                    output = cv2.imdecode(np.frombuffer(response, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if output is None:
                        self._set_status("decode error | bad GPU response frame")
                        continue

                    self._publish_frame(output, cv2)
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


class RuViewApp:
    def __init__(self):
        pygame.init()
        fullscreen = os.environ.get("RUVIEW_FULLSCREEN", "0") == "1"
        flags = pygame.FULLSCREEN if fullscreen else 0
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
        pygame.display.set_caption("RUVIEW COMMAND CENTER")
        pygame.mouse.set_visible(not fullscreen)
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
        if key == pygame.K_SPACE:
            self.camera_stream.toggle()
        elif key == pygame.K_m:
            self.expanded_minimap = not self.expanded_minimap
        elif pygame.K_1 <= key <= pygame.K_4:
            self.active_floor_index = key - pygame.K_1
        return True

    def handle_click(self, pos):
        for button in self.buttons:
            if button.rect.collidepoint(pos):
                if button.action == "toggle_stream":
                    self.camera_stream.toggle()
                elif button.action == "stop_stream":
                    self.camera_stream.stop()
                elif button.action == "floor":
                    self.active_floor_index = int(button.value)
                elif button.action == "toggle_minimap":
                    self.expanded_minimap = not self.expanded_minimap
                return

    def update_camera_surface(self):
        frame = self.camera_stream.consume_frame()
        if frame is None:
            return
        self.camera_surface = pygame.image.frombuffer(
            frame.tobytes(),
            (frame.shape[1], frame.shape[0]),
            "RGB",
        ).copy()

    def render(self):
        self.buttons = []
        self.screen.fill(BG)
        if self.expanded_minimap:
            self.draw_expanded_minimap()
            return

        self.draw_header()
        self.draw_node_panel(pygame.Rect(10, 70, 175, 390))
        self.draw_stream_panel(pygame.Rect(200, 70, 400, 390))
        self.draw_minimap_panel(pygame.Rect(615, 70, 175, 160))
        self.draw_telemetry_panel(pygame.Rect(615, 240, 175, 220))

    def draw_header(self):
        self.draw_text(self.screen, "RUVIEW SYSTEM", (12, 14), CYAN, self.large_font)
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
        y = rect.y + 42
        for node in self.backend.nodes:
            status_color = GREEN if node["status"] == "ONLINE" else RED
            self.draw_text(self.screen, node["name"], (rect.x + 10, y), TEXT)
            self.draw_text(self.screen, f"* {node['status']}", (rect.x + 18, y + 20), status_color, self.small_font)
            self.draw_text(self.screen, f"RSSI: {node['rssi']}", (rect.x + 18, y + 38), MUTED, self.small_font)
            pygame.draw.line(self.screen, PANEL_BORDER, (rect.x + 10, y + 60), (rect.right - 10, y + 60))
            y += 72

        self.draw_button(pygame.Rect(rect.x + 10, rect.bottom - 78, rect.width - 20, 28), "SCAN MESH", "noop")
        self.draw_button(pygame.Rect(rect.x + 10, rect.bottom - 40, rect.width - 20, 28), "SYSTEM REBOOT", "noop")

    def draw_stream_panel(self, rect):
        self.draw_panel(rect, "RPI CAMERA GPU DENSEPOSE STREAM", CYAN)
        image_rect = pygame.Rect(rect.x + 10, rect.y + 40, CAMERA_STREAM_WIDTH, CAMERA_STREAM_HEIGHT)
        pygame.draw.rect(self.screen, (0, 0, 0), image_rect)
        self.screen.blit(self.camera_surface, image_rect)
        pygame.draw.rect(self.screen, (0, 180, 216), image_rect, 1)

        y = image_rect.bottom + 12
        self.draw_text(self.screen, "Pi camera -> RunPod GPU -> DensePose-only output", (rect.x + 10, y), MUTED, self.small_font)
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
        self.draw_text(self.screen, "SPACE start/stop | 1-4 floors | M map | Q quit", (rect.x + 10, rect.bottom - 102), TEXT_DIM, self.small_font)

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
        pygame.draw.rect(self.screen, (0, 180, 216), scaled_rect, 1)
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
        self.draw_button(pygame.Rect(665, 14, 110, 30), "MINIMIZE", "toggle_minimap")
        scaled, scaled_rect = self.fit_surface(self.floor_surfaces[self.active_floor_index], 760, 390)
        scaled_rect.center = (WIDTH // 2, 265)
        self.screen.blit(scaled, scaled_rect)
        pygame.draw.rect(self.screen, PANEL_BORDER, scaled_rect, 1)

    def fit_surface(self, surface, max_width, max_height):
        width, height = surface.get_size()
        scale = min(max_width / width, max_height / height)
        size = (max(1, int(width * scale)), max(1, int(height * scale)))
        scaled = pygame.transform.smoothscale(surface, size)
        return scaled, scaled.get_rect()

    def draw_button(self, rect, label, action, value=None, compact=False):
        active = action == "floor" and value == self.active_floor_index
        fill = (0, 180, 216) if active else (55, 62, 78)
        pygame.draw.rect(self.screen, fill, rect, border_radius=5)
        pygame.draw.rect(self.screen, CYAN if active else PANEL_BORDER, rect, 1, border_radius=5)
        font = self.small_font if compact else self.font
        text_surface = font.render(label, True, TEXT)
        self.screen.blit(text_surface, text_surface.get_rect(center=rect.center))
        if action != "noop":
            self.buttons.append(Button(rect, label, action, value))

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
