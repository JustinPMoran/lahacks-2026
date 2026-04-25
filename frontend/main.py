# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.
import dearpygui.dearpygui as dpg
import asyncio
import random
import math
import time
import sys
import os
import threading

# Ensure backend can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.mock_service import RuViewMockService

# Configuration for the 5/7 inch screen (800x480)
WIDTH = 800
HEIGHT = 480
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "floors")
CAMERA_STREAM_WIDTH = 380
CAMERA_STREAM_HEIGHT = 214
DEFAULT_DENSEPOSE_WS_URL = os.environ.get(
    "DENSEPOSE_WS_URL",
    "wss://q39bcrtj15v9tr-8765.proxy.runpod.net",
)
DEFAULT_STREAM_SEND_WIDTH = int(os.environ.get("DENSEPOSE_SEND_WIDTH", "512"))
DEFAULT_STREAM_JPEG_QUALITY = int(os.environ.get("DENSEPOSE_JPEG_QUALITY", "60"))
DEFAULT_STREAM_TARGET_FPS = float(os.environ.get("DENSEPOSE_TARGET_FPS", "18"))

FLOOR_MAPS = [
    {
        "label": "LEVEL 1",
        "detail": "Stadium Floor",
        "asset": "level_1_stadium_floor.png",
        "texture_tag": "floor_map_level_1",
        "color": (0, 255, 255),
    },
    {
        "label": "LEVEL 2",
        "detail": "Lower Bowl",
        "asset": "level_2_lower_bowl.png",
        "texture_tag": "floor_map_level_2",
        "color": (0, 255, 150),
    },
    {
        "label": "LEVEL 3",
        "detail": "Upper Bowl",
        "asset": "level_3_upper_bowl.png",
        "texture_tag": "floor_map_level_3",
        "color": (255, 200, 0),
    },
    {
        "label": "LEVEL 4",
        "detail": "Concourse",
        "asset": "level_4_concourse_exterior.png",
        "texture_tag": "floor_map_level_4",
        "color": (255, 85, 180),
    },
]

active_floor_index = 0

class BackendManager:
    """Manages connection to the RuView API (Mock or Live)"""
    def __init__(self):
        self.mock = RuViewMockService()
        self.use_mock = True
        self.backend_url = "http://localhost:8000"
        self.last_pose = None
        self.nodes = []
        self.logs = []

    def update(self):
        if self.use_mock:
            self.last_pose = self.mock.get_latest_pose()
            self.nodes = self.mock.get_nodes()
            self.status = self.mock.get_system_status()
        # Live implementation would fetch from self.backend_url via requests/websockets here

    def get_logs(self):
        # Placeholder for telemetry sync
        return [
            f"[SYNC] {time.strftime('%H:%M:%S')} - Model: {self.status['data']['performance']['average_fps']} FPS",
            f"[NODE] Online Count: {len([n for n in self.nodes if n['status'] == 'ONLINE'])}"
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
        self.status = "idle | start camera stream when GPU server is ready"
        self.latest_texture_data = None
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

    def is_running(self):
        return self.thread is not None and self.thread.is_alive()

    def set_url(self, ws_url):
        self.ws_url = ws_url.strip() or DEFAULT_DENSEPOSE_WS_URL

    def set_camera_source(self, camera_source):
        self.camera_source = str(camera_source).strip() or "0"

    def configure_stream(self, send_width, jpeg_quality, target_fps):
        self.send_width = max(256, min(960, int(send_width)))
        self.jpeg_quality = max(35, min(90, int(jpeg_quality)))
        self.target_fps = max(1.0, min(30.0, float(target_fps)))

    def consume_texture_data(self):
        with self.lock:
            texture_data = self.latest_texture_data
            self.latest_texture_data = None
        return texture_data

    def _set_status(self, status):
        with self.lock:
            self.status = status

    def _publish_frame(self, frame, cv2):
        resized = cv2.resize(frame, (CAMERA_STREAM_WIDTH, CAMERA_STREAM_HEIGHT), interpolation=cv2.INTER_AREA)
        rgba = cv2.cvtColor(resized, cv2.COLOR_BGR2RGBA).astype("float32") / 255.0
        with self.lock:
            self.latest_texture_data = rgba.ravel().tolist()

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

                    ok, encoded = cv2.imencode(
                        ".jpg",
                        frame,
                        [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality],
                    )
                    if not ok:
                        self._set_status("encode error | could not compress webcam frame")
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

                    frame_budget = 1.0 / self.target_fps
                    sleep_for = frame_budget - (time.perf_counter() - loop_started)
                    if sleep_for > 0:
                        await asyncio.sleep(sleep_for)
        finally:
            capture.release()

backend = BackendManager()
camera_stream = CameraDensePoseStream()

def load_floor_map_textures():
    with dpg.texture_registry(show=False):
        for floor in FLOOR_MAPS:
            image_path = os.path.join(ASSET_DIR, floor["asset"])
            width, height, channels, data = dpg.load_image(image_path)
            floor["width"] = width
            floor["height"] = height
            floor["channels"] = channels
            dpg.add_static_texture(width, height, data, tag=floor["texture_tag"])
        blank_frame = [0.0, 0.0, 0.0, 1.0] * CAMERA_STREAM_WIDTH * CAMERA_STREAM_HEIGHT
        dpg.add_dynamic_texture(
            CAMERA_STREAM_WIDTH,
            CAMERA_STREAM_HEIGHT,
            blank_frame,
            tag="camera_stream_texture",
        )

def selected_floor():
    return FLOOR_MAPS[active_floor_index]

def fit_map_size(floor, max_width, max_height):
    scale = min(max_width / floor["width"], max_height / floor["height"])
    return int(floor["width"] * scale), int(floor["height"] * scale)

def configure_map_item(item_tag, floor, max_width, max_height, group_tag=None, container_width=None):
    width, height = fit_map_size(floor, max_width, max_height)
    dpg.configure_item(item_tag, texture_tag=floor["texture_tag"], width=width, height=height)
    if group_tag and container_width and dpg.does_item_exist(group_tag):
        dpg.configure_item(group_tag, indent=max(0, (container_width - width) // 2))

def bind_floor_button_theme(button_tag, floor_index):
    state = "active" if floor_index == active_floor_index else "idle"
    dpg.bind_item_theme(button_tag, f"floor_button_{floor_index}_{state}_theme")

def set_active_floor(index):
    global active_floor_index
    active_floor_index = index
    floor = selected_floor()

    if dpg.does_item_exist("minimap_preview_button"):
        configure_map_item("minimap_preview_button", floor, 155, 92, "minimap_image_group", 155)
    if dpg.does_item_exist("expanded_floor_image"):
        configure_map_item("expanded_floor_image", floor, 760, 375, "expanded_map_image_group", 780)

    for floor_index in range(len(FLOOR_MAPS)):
        for prefix in ("minimap_floor_selector", "expanded_floor_selector"):
            button_tag = f"{prefix}_{floor_index}"
            if dpg.does_item_exist(button_tag):
                bind_floor_button_theme(button_tag, floor_index)

def show_expanded_minimap():
    dpg.hide_item("Minimap Window")
    dpg.show_item("Expanded Minimap Window")
    dpg.focus_item("Expanded Minimap Window")

def hide_expanded_minimap():
    dpg.hide_item("Expanded Minimap Window")
    dpg.show_item("Minimap Window")

def setup_theme():
    with dpg.theme() as global_theme:
        with dpg.theme_component(dpg.mvAll):
            # Window & Panels
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (15, 17, 26, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (22, 25, 37, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Border, (40, 45, 60, 255))
            
            # Text
            dpg.add_theme_color(dpg.mvThemeCol_Text, (180, 190, 210, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, (80, 85, 100, 255))
            
            # Buttons (Neon Cyan)
            dpg.add_theme_color(dpg.mvThemeCol_Button, (0, 180, 216, 100))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (0, 180, 216, 200))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (0, 180, 216, 255))
            
            # Frame Backgrounds
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (32, 36, 52, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (42, 46, 62, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (52, 56, 72, 255))
            
            # Headers & Tabs
            dpg.add_theme_color(dpg.mvThemeCol_Header, (0, 180, 216, 80))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (0, 180, 216, 150))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (0, 180, 216, 200))
            
            # Sliders/Checkboxes
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark, (0, 255, 180, 255))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (0, 180, 216, 255))
            dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (0, 255, 255, 255))

            # Styling
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 0) # Hard edges look more 'pro' on small screens
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 6)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 4)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 10, 10)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 10, 10)

    dpg.bind_theme(global_theme)

def create_floor_button_themes():
    for index in range(len(FLOOR_MAPS)):
        for state, alpha, border in (("idle", 120, 0), ("active", 255, 255)):
            with dpg.theme(tag=f"floor_button_{index}_{state}_theme"):
                with dpg.theme_component(dpg.mvButton):
                    dpg.add_theme_color(dpg.mvThemeCol_Button, (55, 62, 78, alpha))
                    dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (90, 100, 120, 220))
                    dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (130, 140, 160, 255))
                    dpg.add_theme_color(dpg.mvThemeCol_Text, (220, 225, 235, 255))
                    dpg.add_theme_color(dpg.mvThemeCol_Border, (255, 255, 255, border))
                    dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 8)
                    dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 1 if border else 0)

def draw_dense_pose(center_x, center_y):
    # Faking DensePose UV/Part points
    # Each part is a cluster of points with a specific color logic
    parts = [
        {"name": "torso", "color": (0, 255, 255), "spread_x": 20, "spread_y": 40, "offset_y": 30, "count": 25},
        {"name": "head", "color": (255, 200, 0), "spread_x": 12, "spread_y": 12, "offset_y": -15, "count": 12},
        {"name": "l_arm", "color": (0, 255, 150), "spread_x": 8, "spread_y": 30, "offset_x": -25, "offset_y": 45, "count": 15},
        {"name": "r_arm", "color": (0, 255, 150), "spread_x": 8, "spread_y": 30, "offset_x": 25, "offset_y": 45, "count": 15},
        {"name": "l_leg", "color": (0, 150, 255), "spread_x": 10, "spread_y": 40, "offset_x": -12, "offset_y": 105, "count": 20},
        {"name": "r_leg", "color": (0, 150, 255), "spread_x": 10, "spread_y": 40, "offset_x": 12, "offset_y": 105, "count": 20},
    ]
    
    for part in parts:
        for _ in range(part.get("count", 10)):
            # Random jitter for 'cloud' effect
            px = center_x + part.get("offset_x", 0) + (random.random() - 0.5) * part["spread_x"] * 2
            py = center_y + part.get("offset_y", 0) + (random.random() - 0.5) * part["spread_y"] * 2
            
            # Draw point with slight transparency
            alpha = random.randint(100, 200)
            dpg.draw_circle((px, py), 1.5, color=(*part["color"], alpha), fill=(*part["color"], alpha // 2), parent="spatial_drawlist")

def start_camera_stream():
    if dpg.does_item_exist("camera_stream_url_input"):
        camera_stream.set_url(dpg.get_value("camera_stream_url_input"))
    if dpg.does_item_exist("camera_source_input"):
        camera_stream.set_camera_source(dpg.get_value("camera_source_input"))
    if all(
        dpg.does_item_exist(tag)
        for tag in ("camera_send_width", "camera_jpeg_quality", "camera_target_fps")
    ):
        camera_stream.configure_stream(
            dpg.get_value("camera_send_width"),
            dpg.get_value("camera_jpeg_quality"),
            dpg.get_value("camera_target_fps"),
        )
    camera_stream.start()

def stop_camera_stream():
    camera_stream.stop()

def update_camera_stream_ui():
    texture_data = camera_stream.consume_texture_data()
    if texture_data and dpg.does_item_exist("camera_stream_texture"):
        dpg.set_value("camera_stream_texture", texture_data)

    if dpg.does_item_exist("camera_stream_status"):
        dpg.set_value("camera_stream_status", camera_stream.status)

def create_radar_canvas():
    with dpg.child_window(tag="radar_container", border=True, width=400, height=390):
        dpg.add_text("RPI CAMERA GPU DENSEPOSE STREAM", color=(0, 255, 255))
        dpg.add_image("camera_stream_texture", width=CAMERA_STREAM_WIDTH, height=CAMERA_STREAM_HEIGHT)
        dpg.add_text(
            "Pi camera -> RunPod GPU -> DensePose-only processed output",
            color=(100, 120, 140),
            wrap=380,
        )
        dpg.add_text(camera_stream.status, tag="camera_stream_status", color=(0, 255, 150), wrap=380)
        with dpg.group(horizontal=True):
            dpg.add_button(label="START CAMERA STREAM", width=180, height=32, callback=start_camera_stream)
            dpg.add_button(label="STOP", width=80, height=32, callback=stop_camera_stream)
        with dpg.group(horizontal=True):
            dpg.add_input_int(
                label="WIDTH",
                tag="camera_send_width",
                default_value=camera_stream.send_width,
                min_value=256,
                max_value=960,
                width=92,
                step=64,
            )
            dpg.add_input_int(
                label="JPG",
                tag="camera_jpeg_quality",
                default_value=camera_stream.jpeg_quality,
                min_value=35,
                max_value=90,
                width=82,
                step=5,
            )
        dpg.add_slider_float(
            label="TARGET FPS",
            tag="camera_target_fps",
            default_value=camera_stream.target_fps,
            min_value=1,
            max_value=30,
            width=245,
        )
        dpg.add_input_text(
            label="CAM",
            tag="camera_source_input",
            default_value=camera_stream.camera_source,
            width=120,
        )
        dpg.add_input_text(
            label="GPU WS",
            tag="camera_stream_url_input",
            default_value=camera_stream.ws_url,
            width=280,
        )

def create_node_panel():
    with dpg.child_window(tag="node_panel", border=True, width=175, height=390):
        dpg.add_text("NODES", color=(0, 255, 180))
        dpg.add_spacer(height=5)
        
        with dpg.group(tag="node_list_container"):
            pass # Updated dynamically

        dpg.add_spacer(height=10)
        dpg.add_button(label="SCAN MESH", width=-1, height=35)
        dpg.add_button(label="SYSTEM REBOOT", width=-1, height=35)

def update_dynamic_ui():
    # Update nodes
    dpg.delete_item("node_list_container", children_only=True)
    with dpg.group(parent="node_list_container"):
        for node in backend.nodes:
            status_color = (0, 255, 150) if node["status"] == "ONLINE" else (255, 50, 50)
            dpg.add_text(node["name"], color=(200, 210, 255))
            with dpg.group(horizontal=True, indent=10):
                dpg.add_text("●", color=status_color)
                dpg.add_text(node["status"], color=status_color)
            dpg.add_text(f"RSSI: {node['rssi']}", color=(100, 100, 120), indent=10)
            dpg.add_separator()
    
    # Update status text in header
    dpg.set_value("status_text", f"| {backend.status['data']['status'].upper()} | {backend.status['data']['performance']['average_fps']} FPS")

def create_event_log(height=220):
    log_height = max(115, height - 125)

    with dpg.child_window(tag="event_log", border=True, width=175, height=height):
        dpg.add_text("TELEMETRY", color=(255, 200, 0))
        with dpg.child_window(height=log_height, border=False):
            logs = [
                "[12:04] Mesh Sync Complete",
                "[12:05] Movement in Sector 4",
                "[12:06] Multi-path interference low",
                "[12:07] Pose Decoded: Standing",
                "[12:08] Tracking Alpha_01",
            ]
            for log in logs:
                dpg.add_text(log, wrap=170, color=(140, 145, 160))
        
        dpg.add_spacer(height=5)
        dpg.add_text("GAIN CONTROL", color=(100, 100, 120))
        dpg.add_slider_float(default_value=0.75, max_value=1.0, width=-1)
        dpg.add_spacer(height=2)
        dpg.add_button(label="EXPORT DATA", width=-1, height=30)

def create_minimap_panel():
    floor = selected_floor()
    preview_width, preview_height = fit_map_size(floor, 155, 92)

    with dpg.child_window(
        tag="Minimap Window",
        border=True,
        width=175,
        height=160,
        no_scrollbar=True,
    ):
        with dpg.group(horizontal=True, indent=34):
            for index in range(len(FLOOR_MAPS)):
                button_tag = f"minimap_floor_selector_{index}"
                dpg.add_button(
                    label=str(index + 1),
                    tag=button_tag,
                    width=16,
                    height=16,
                    callback=lambda sender, app_data, user_data: set_active_floor(user_data),
                    user_data=index,
                )
                bind_floor_button_theme(button_tag, index)

        dpg.add_spacer(height=1)
        with dpg.group(tag="minimap_image_group", indent=max(0, (155 - preview_width) // 2)):
            dpg.add_image_button(
                floor["texture_tag"],
                tag="minimap_preview_button",
                width=preview_width,
                height=preview_height,
                background_color=(0, 180, 216, 80),
                callback=show_expanded_minimap,
            )

def create_expanded_minimap_window():
    floor = selected_floor()
    map_width, map_height = fit_map_size(floor, 760, 375)

    with dpg.window(
        tag="Expanded Minimap Window",
        show=False,
        no_title_bar=True,
        no_move=True,
        no_resize=True,
        no_collapse=True,
        no_close=True,
        no_scrollbar=True,
        width=WIDTH,
        height=HEIGHT,
        pos=(0, 0),
    ):
        with dpg.group(horizontal=True, indent=276):
            for index in range(len(FLOOR_MAPS)):
                button_tag = f"expanded_floor_selector_{index}"
                dpg.add_button(
                    label=str(index + 1),
                    tag=button_tag,
                    width=22,
                    height=22,
                    callback=lambda sender, app_data, user_data: set_active_floor(user_data),
                    user_data=index,
                )
                bind_floor_button_theme(button_tag, index)
            dpg.add_spacer(width=170)
            dpg.add_button(label="MINIMIZE", width=105, height=32, callback=hide_expanded_minimap)

        with dpg.group(tag="expanded_map_image_group", indent=max(0, (780 - map_width) // 2)):
            dpg.add_image(floor["texture_tag"], tag="expanded_floor_image", width=map_width, height=map_height)


def main():
    dpg.create_context()
    load_floor_map_textures()
    
    # Setup for full-screen borderless appearance on the Pi
    dpg.create_viewport(
        title='RUVIEW COMMAND CENTER',
        width=WIDTH,
        height=HEIGHT,
        resizable=False,
        decorated=False,
        clear_color=(15, 17, 26, 255)
    )
    
    setup_theme()
    create_floor_button_themes()
    
    with dpg.window(tag="Primary Window", no_title_bar=True, no_move=True, no_resize=True):
        # Header
        with dpg.group(horizontal=True):
            dpg.add_text("RUVIEW SYSTEM", color=(0, 255, 255))
            dpg.add_text("| COMMAND CENTER v1.0", color=(80, 85, 100), tag="status_text")
            dpg.add_spacer(width=200)
            dpg.add_button(label="SETTINGS", callback=lambda: dpg.show_item("Settings Window"))
            
        dpg.add_separator()
        dpg.add_spacer(height=10)
        
        # Main Dashboard Layout
        with dpg.group(horizontal=True):
            create_node_panel()
            create_radar_canvas()
            with dpg.group():
                create_minimap_panel()
                create_event_log()

    create_expanded_minimap_window()

    # Settings Window (Hidden by default)
    with dpg.window(label="System Settings", tag="Settings Window", show=False, width=300, height=200, pos=(250, 100)):
        dpg.add_text("Backend Configuration")
        dpg.add_checkbox(label="Use Mock Service", default_value=True, callback=lambda s, a: setattr(backend, 'use_mock', a))
        dpg.add_input_text(label="API URL", default_value="http://localhost:8000")
        dpg.add_separator()
        dpg.add_button(label="Apply", callback=lambda: dpg.hide_item("Settings Window"))

    dpg.set_primary_window("Primary Window", True)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    
    # Main Loop
    while dpg.is_dearpygui_running():
        # 1. Update Backend Data
        backend.update()
        
        # 2. Update HUD & Node List
        update_dynamic_ui()
        
        # 3. Render the latest GPU DensePose frame returned from the RunPod stream server.
        update_camera_stream_ui()
        
        dpg.render_dearpygui_frame()
        
    camera_stream.stop()
    dpg.destroy_context()

if __name__ == "__main__":
    main()
