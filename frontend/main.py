# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.
import dearpygui.dearpygui as dpg
import random
import math
import time
import sys
import os

# Ensure backend can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.mock_service import RuViewMockService

# Configuration for the 5/7 inch screen (800x480)
WIDTH = 800
HEIGHT = 480

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

backend = BackendManager()

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

def create_radar_canvas():
    with dpg.child_window(tag="radar_container", border=True, width=400, height=390):
        dpg.add_text("DENSEPOSE RECONSTRUCTION", color=(0, 255, 255))
        with dpg.drawlist(width=380, height=330, tag="spatial_drawlist"):
            # Grid
            for i in range(0, 371, 30):
                dpg.draw_line((i, 0), (i, 360), color=(30, 35, 50, 255))
                dpg.draw_line((0, i), (370, i), color=(30, 35, 50, 255))
            
            # Base Radar Rings
            center = [185, 180]
            for r in range(60, 240, 60):
                dpg.draw_circle(center, r, color=(0, 180, 216, 40), thickness=1)
            
            # THE DENSE POSE
            draw_dense_pose(200, 130)
            
            dpg.draw_text((235, 105), "ID: ALPHA_01", color=(0, 255, 255))
            dpg.draw_text((235, 120), "MODEL: DensePose-RCNN", color=(100, 120, 140))
            dpg.draw_text((235, 135), "CONF: 94.2%", color=(0, 255, 150))

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

def create_event_log():
    with dpg.child_window(tag="event_log", border=True, width=175, height=390):
        dpg.add_text("TELEMETRY", color=(255, 200, 0))
        with dpg.child_window(height=340, border=False):
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


def main():
    dpg.create_context()
    
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
            create_event_log()

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
        
        # 3. Render Pose from Backend Data
        dpg.delete_item("spatial_drawlist", children_only=True)
        
        # Redraw static grid/rings (or keep them out of children_only if tagged differently)
        # For simplicity, we just redraw the pose on top of the existing list if we don't clear,
        # but to move it, we must clear.
        # Let's move the GRID/RINGS to a static layer or just redraw them:
        
        # Grid
        for i in range(0, 371, 30):
            dpg.draw_line((i, 0), (i, 360), color=(30, 35, 50, 255), parent="spatial_drawlist")
            dpg.draw_line((0, i), (370, i), color=(30, 35, 50, 255), parent="spatial_drawlist")
        # Rings
        for r in range(60, 240, 60):
            dpg.draw_circle((185, 180), r, color=(0, 180, 216, 40), thickness=1, parent="spatial_drawlist")

        if backend.last_pose:
            person = backend.last_pose["data"]["persons"][0]
            center = person["center"]
            draw_dense_pose(center["x"], center["y"])
            
            dpg.draw_text((235, 105), f"ID: {person['track_id']}", color=(0, 255, 255), parent="spatial_drawlist")
            dpg.draw_text((235, 120), "MODEL: DensePose-RCNN", color=(100, 120, 140), parent="spatial_drawlist")
            dpg.draw_text((235, 135), f"CONF: {int(person['confidence'] * 100)}%", color=(0, 255, 150), parent="spatial_drawlist")
        
        dpg.render_dearpygui_frame()
        
    dpg.destroy_context()

if __name__ == "__main__":
    main()
