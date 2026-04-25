import dearpygui.dearpygui as dpg
import random
import math
import time

# Configuration for the 5/7 inch screen (800x480)
WIDTH = 800
HEIGHT = 480

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

def create_radar_canvas():
    with dpg.child_window(tag="radar_container", border=True, width=400, height=390):
        dpg.add_text("WIFI SPATIAL FEED", color=(0, 255, 255))
        with dpg.drawlist(width=380, height=330, tag="spatial_drawlist"):
            # Grid
            for i in range(0, 371, 30):
                dpg.draw_line((i, 0), (i, 360), color=(30, 35, 50, 255))
                dpg.draw_line((0, i), (370, i), color=(30, 35, 50, 255))
            
            # Base Radar Rings
            center = [185, 180]
            for r in range(60, 240, 60):
                dpg.draw_circle(center, r, color=(0, 180, 216, 40), thickness=1)
            
            # Scanning Sweep Line (Static for now)
            dpg.draw_line(center, (center[0] + 150, center[1] - 80), color=(0, 255, 255, 100), thickness=2)
            
            # THE POSE (Mock DensePose style)
            # Head
            dpg.draw_circle((200, 120), 8, color=(0, 255, 150), fill=(0, 255, 150, 50))
            # Torso
            dpg.draw_line((200, 128), (200, 180), color=(0, 255, 150), thickness=3)
            # Arms
            dpg.draw_line((200, 140), (180, 160), color=(0, 255, 150), thickness=2)
            dpg.draw_line((200, 140), (220, 160), color=(0, 255, 150), thickness=2)
            # Legs
            dpg.draw_line((200, 180), (185, 220), color=(0, 255, 150), thickness=2)
            dpg.draw_line((200, 180), (215, 220), color=(0, 255, 150), thickness=2)
            
            dpg.draw_text((230, 110), "ID: ALPHA_01", color=(0, 255, 150))
            dpg.draw_text((230, 125), "CONF: 94.2%", color=(0, 255, 150, 150))

def create_node_panel():
    with dpg.child_window(tag="node_panel", border=True, width=175, height=390):
        dpg.add_text("NODES", color=(0, 255, 180))
        dpg.add_spacer(height=5)
        
        nodes = [
            {"name": "GATEWAY", "ip": "192.168.1.45", "status": "ONLINE", "rssi": "-42dBm"},
            {"name": "NODE_ALPHA", "ip": "192.168.1.46", "status": "ONLINE", "rssi": "-56dBm"},
            {"name": "NODE_BETA", "ip": "192.168.1.47", "status": "OFFLINE", "rssi": "N/A"},
        ]
        
        for node in nodes:
            with dpg.group():
                status_color = (0, 255, 150) if node["status"] == "ONLINE" else (255, 50, 50)
                dpg.add_text(node["name"], color=(200, 210, 255))
                with dpg.group(horizontal=True, indent=10):
                    dpg.add_text("●", color=status_color)
                    dpg.add_text(node["status"], color=status_color)
                dpg.add_text(f"RSSI: {node['rssi']}", color=(100, 100, 120), indent=10)
                dpg.add_spacer(height=4)
                dpg.add_separator()

        dpg.add_spacer(height=10)
        dpg.add_button(label="SCAN MESH", width=-1, height=35)
        dpg.add_button(label="SYSTEM REBOOT", width=-1, height=35)

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
            dpg.add_text("| COMMAND CENTER v1.0", color=(80, 85, 100))
            
        dpg.add_separator()
        dpg.add_spacer(height=10)
        
        # Main Dashboard Layout
        with dpg.group(horizontal=True):
            create_node_panel()
            create_radar_canvas()
            create_event_log()

    dpg.set_primary_window("Primary Window", True)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    
    # Main Loop
    # dpg.start_dearpygui() # Standard approach
    
    # Custom loop for potential animation updates
    while dpg.is_dearpygui_running():
        # Update simulation/data here
        # Example: Pulse the detected entity
        t = time.time()
        alpha = int(127 + 127 * math.sin(t * 4))
        # dpg.configure_item("detected_entity", fill=(255, 50, 50, alpha)) # Example update
        
        dpg.render_dearpygui_frame()
        
    dpg.destroy_context()

if __name__ == "__main__":
    main()
