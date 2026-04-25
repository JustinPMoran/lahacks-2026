# After making your desired changes, update .memory/memory.md with what you did and why. Read it before each task.
import pygame
import random
import math
import time
import sys
import os

# Ensure backend can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.mock_service import RuViewMockService

# --- Configuration & Constants ---
WIDTH, HEIGHT = 800, 480
FPS = 30

# Cyberpunk Design Tokens (Identical to DearPyGui)
COLOR_BG = (15, 17, 26)
COLOR_CHILD_BG = (22, 25, 37)
COLOR_BORDER = (40, 45, 60)
COLOR_CYAN = (0, 255, 255)
COLOR_AMBER = (255, 200, 0)
COLOR_GREEN = (0, 255, 150)
COLOR_RED = (255, 50, 50)
COLOR_TEXT = (180, 190, 210)
COLOR_TEXT_DIM = (100, 100, 120)
COLOR_HEADER = (0, 180, 216)

# Layout constants
PAD = 10
SIDE_WIDTH = 175
CENTER_WIDTH = 400
PANEL_HEIGHT = 390
HEADER_HEIGHT = 60

class BackendManager:
    """Manages connection to the RuView API (Mock or Live)"""
    def __init__(self):
        self.mock = RuViewMockService()
        self.use_mock = True
        self.backend_url = "http://localhost:8000"
        self.last_pose = None
        self.nodes = []
        self.status_msg = ""
        self.fps = 0

    def update(self):
        if self.use_mock:
            self.last_pose = self.mock.get_latest_pose()
            self.nodes = self.mock.get_nodes()
            status = self.mock.get_system_status()
            self.status_msg = status['data']['status'].upper()
            self.fps = status['data']['performance']['average_fps']

backend = BackendManager()

# --- UI Components ---

class PygameGUI:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.NOFRAME if os.environ.get('KONTROL_DECORATED') != '1' else 0)
        pygame.display.set_caption("RUVIEW COMMAND CENTER")
        self.clock = pygame.time.Clock()
        self.font_main = pygame.font.SysFont("Arial", 16)
        self.font_bold = pygame.font.SysFont("Arial", 18, bold=True)
        self.font_small = pygame.font.SysFont("Arial", 12)
        self.font_title = pygame.font.SysFont("Arial", 22, bold=True)
        self.running = True
        self.show_settings = False
        
        # UI State
        self.gain_val = 0.75

    def draw_rounded_rect(self, surface, rect, color, radius=6):
        pygame.draw.rect(surface, color, rect, border_radius=radius)
        pygame.draw.rect(surface, COLOR_BORDER, rect, width=1, border_radius=radius)

    def draw_header(self):
        # Header Text
        img = self.font_title.render("RUVIEW SYSTEM", True, COLOR_CYAN)
        self.screen.blit(img, (PAD, PAD))
        
        status_text = f"| {backend.status_msg} | {backend.fps} FPS"
        img_sub = self.font_main.render(status_text, True, COLOR_TEXT_DIM)
        self.screen.blit(img_sub, (img.get_width() + PAD + 10, PAD + 4))
        
        # Settings Button (Fake)
        btn_rect = pygame.Rect(WIDTH - 110, PAD, 100, 30)
        self.draw_rounded_rect(self.screen, btn_rect, (30, 40, 60))
        btn_txt = self.font_main.render("SETTINGS", True, COLOR_TEXT)
        self.screen.blit(btn_txt, (btn_rect.centerx - btn_txt.get_width()//2, btn_rect.centery - btn_txt.get_height()//2))

        pygame.draw.line(self.screen, COLOR_BORDER, (0, HEADER_HEIGHT), (WIDTH, HEADER_HEIGHT))

    def draw_node_panel(self):
        rect = pygame.Rect(PAD, HEADER_HEIGHT + PAD, SIDE_WIDTH, PANEL_HEIGHT)
        self.draw_rounded_rect(self.screen, rect, COLOR_CHILD_BG)
        
        title = self.font_bold.render("NODES", True, COLOR_GREEN)
        self.screen.blit(title, (rect.x + 10, rect.y + 10))
        
        y_off = 40
        for node in backend.nodes:
            # Node Name
            txt = self.font_main.render(node['name'], True, (200, 210, 255))
            self.screen.blit(txt, (rect.x + 10, rect.y + y_off))
            
            # Status Dot & Text
            status_color = COLOR_GREEN if node['status'] == "ONLINE" else COLOR_RED
            pygame.draw.circle(self.screen, status_color, (rect.x + 15, rect.y + y_off + 25), 4)
            st_txt = self.font_small.render(node['status'], True, status_color)
            self.screen.blit(st_txt, (rect.x + 25, rect.y + y_off + 18))
            
            # RSSI
            rssi_txt = self.font_small.render(f"RSSI: {node['rssi']}", True, COLOR_TEXT_DIM)
            self.screen.blit(rssi_txt, (rect.x + 10, rect.y + y_off + 40))
            
            pygame.draw.line(self.screen, (40, 40, 50), (rect.x + 10, rect.y + y_off + 60), (rect.right - 10, rect.y + y_off + 60))
            y_off += 70

        # Buttons
        btn_scan = pygame.Rect(rect.x + 5, rect.bottom - 80, rect.width - 10, 35)
        self.draw_rounded_rect(self.screen, btn_scan, (0, 180, 216, 100))
        t = self.font_main.render("SCAN MESH", True, COLOR_TEXT)
        self.screen.blit(t, (btn_scan.centerx - t.get_width()//2, btn_scan.centery - t.get_height()//2))

    def draw_telemetry_panel(self):
        rect = pygame.Rect(WIDTH - SIDE_WIDTH - PAD, HEADER_HEIGHT + PAD, SIDE_WIDTH, PANEL_HEIGHT)
        self.draw_rounded_rect(self.screen, rect, COLOR_CHILD_BG)
        title = self.font_bold.render("TELEMETRY", True, COLOR_AMBER)
        self.screen.blit(title, (rect.x + 10, rect.y + 10))
        
        # Mock Logs
        logs = [
            "[SYNC] Mesh Active",
            "[POSE] Tracking Alpha",
            "[SYS] GPU Load Stable",
            "[NET] Low Latency"
        ]
        y_off = 40
        for log in logs:
            l_txt = self.font_small.render(log, True, (140, 145, 160))
            self.screen.blit(l_txt, (rect.x + 10, rect.y + y_off))
            y_off += 20

        # Gain Slider
        sl_rect = pygame.Rect(rect.x + 10, rect.bottom - 60, rect.width - 20, 6)
        pygame.draw.rect(self.screen, (32, 36, 52), sl_rect)
        pygame.draw.circle(self.screen, COLOR_CYAN, (sl_rect.x + int(sl_rect.width * self.gain_val), sl_rect.centery), 8)
        self.screen.blit(self.font_small.render("GAIN CONTROL", True, COLOR_TEXT_DIM), (rect.x + 10, rect.bottom - 80))

    def draw_dense_pose(self, center_x, center_y):
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
                px = center_x + part.get("offset_x", 0) + (random.random() - 0.5) * part["spread_x"] * 2
                py = center_y + part.get("offset_y", 0) + (random.random() - 0.5) * part["spread_y"] * 2
                
                # Pygame Alpha-ready
                alpha = random.randint(100, 200)
                color = part["color"]
                s = pygame.Surface((4, 4), pygame.SRCALPHA)
                pygame.draw.circle(s, (*color, alpha), (2, 2), 2)
                self.screen.blit(s, (px - 2, py - 2))

    def draw_spatial_feed(self):
        rect = pygame.Rect(PAD + SIDE_WIDTH + PAD, HEADER_HEIGHT + PAD, CENTER_WIDTH, PANEL_HEIGHT)
        self.draw_rounded_rect(self.screen, rect, COLOR_CHILD_BG)
        
        title = self.font_main.render("DENSEPOSE RECONSTRUCTION", True, COLOR_CYAN)
        self.screen.blit(title, (rect.x + 10, rect.y + 10))
        
        # Grid
        for i in range(rect.x, rect.right, 30):
            pygame.draw.line(self.screen, (30, 35, 50), (i, rect.y + 40), (i, rect.bottom - 10))
        for j in range(rect.y + 40, rect.bottom, 30):
            pygame.draw.line(self.screen, (30, 35, 50), (rect.x + 10, j), (rect.right - 10, j))

        # Rings
        cx, cy = rect.x + 185, rect.y + 180
        for r in range(60, 240, 60):
            pygame.draw.circle(self.screen, (0, 180, 216, 40), (cx, cy), r, 1)

        # Draw Pose from backend
        if backend.last_pose:
            person = backend.last_pose["data"]["persons"][0]
            center = person["center"]
            # Map coords to feed center (The mock coordinates are relative to feed center usually)
            # In our mock, px is around 200, py is around 150.
            # We blit them relative to the panel's drawing area.
            self.draw_dense_pose(rect.x + center["x"], rect.y + center["y"])
            
            id_t = self.font_small.render(f"ID: {person['track_id']}", True, COLOR_CYAN)
            self.screen.blit(id_t, (rect.x + 235, rect.y + 105))
            conf_t = self.font_small.render(f"CONF: {int(person['confidence']*100)}%", True, COLOR_GREEN)
            self.screen.blit(conf_t, (rect.x + 235, rect.y + 135))

    def main_loop(self):
        while self.running:
            # 1. Events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False

            # 2. Update Backend
            backend.update()

            # 3. Draw
            self.screen.fill(COLOR_BG)
            self.draw_header()
            self.draw_node_panel()
            self.draw_spatial_feed()
            self.draw_telemetry_panel()

            pygame.display.flip()
            self.clock.tick(FPS)

        pygame.quit()

if __name__ == "__main__":
    gui = PygameGUI()
    gui.main_loop()
