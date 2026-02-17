# ============================================================
# AI PATHFINDER - PART 2: Pygame GUI
# GOOD PERFORMANCE TIME APP
# ============================================================
# HOW TO RUN:
#   pip install pygame
#   Make sure pathfinder_part1.py is in the SAME folder as this file
#   Then run:  python pathfinder_part2.py
#
# CONTROLS:
#   Left-click  on a cell  → toggle wall
#   Right-click on a cell  → drag to place walls quickly
#   Buttons on the right panel:
#     [BFS] [DFS] [UCS] [DLS] [IDDFS] [Bidir] → run that algorithm
#     [Reset Grid]  → clear the grid back to defaults
#     [Speed +/-]   → change animation speed
#     [Step Mode]   → toggle auto-play vs manual stepping
#     [Next Step]   → advance one step (Step Mode only)
#
# This file contains:
#   - Pygame event loop
#   - Drawing routines
#   - Button / UI panel
#   - Re-planning logic when a dynamic obstacle blocks the current path
# ============================================================

import pygame
import sys
import time

# import everything from Part 1
from pathfinder_part1 import (
    Grid, ALGORITHMS, EMPTY, WALL, START, TARGET,
    ROWS, COLS, OBSTACLE_PROB
)

# ──────────────────────────────────────────────
# WINDOW & LAYOUT CONSTANTS
# ──────────────────────────────────────────────
CELL_SIZE    = 46          # pixels per grid cell
PANEL_WIDTH  = 220         # right-side control panel width
MARGIN_TOP   = 60          # space above the grid for the title bar
MARGIN_LEFT  = 10
MARGIN_BOT   = 40          # space below grid for status bar

GRID_PX_W    = COLS * CELL_SIZE
GRID_PX_H    = ROWS * CELL_SIZE
WIN_W        = GRID_PX_W + PANEL_WIDTH + MARGIN_LEFT * 2
WIN_H        = GRID_PX_H + MARGIN_TOP + MARGIN_BOT

# ──────────────────────────────────────────────
# COLOUR PALETTE
# ──────────────────────────────────────────────
C_BG         = (15,  17,  26)   # very dark navy – window background
C_GRID_LINE  = (35,  40,  60)   # subtle grid lines
C_CELL_EMPTY = (25,  30,  45)   # empty cell colour
C_WALL       = (50,  55,  70)   # static wall
C_DYN_WALL   = (180, 60,  20)   # dynamic obstacle (orange-red)
C_START      = (30, 180, 100)   # green – Start
C_TARGET     = (220, 80,  50)   # red-orange – Target
C_FRONTIER   = (60, 120, 220)   # blue – in queue/stack
C_EXPLORED   = (60,  80, 130)   # dim blue – already visited
C_PATH       = (255, 210,  50)  # bright yellow – final path
C_PANEL      = (20,  22,  35)   # panel background
C_BTN        = (40,  50,  80)   # button normal
C_BTN_HOV    = (60,  75, 120)   # button hover
C_BTN_ACT    = (80, 130, 220)   # button active (algorithm running)
C_BTN_TEXT   = (200, 210, 230)  # button text
C_TITLE      = (200, 215, 255)  # title text colour
C_STATUS     = (160, 175, 200)  # status bar text
C_WHITE      = (255, 255, 255)
C_FOUND      = ( 80, 220, 120)  # success green
C_FAIL       = (220,  80,  80)  # failure red

# ──────────────────────────────────────────────
# BUTTON CLASS
# ──────────────────────────────────────────────
class Button:
    """A simple rectangular clickable button."""

    def __init__(self, x, y, w, h, label, color=C_BTN):
        self.rect   = pygame.Rect(x, y, w, h)
        self.label  = label
        self.color  = color
        self.active = False          # True when this algo is selected

    def draw(self, surface, font, mouse_pos):
        # pick colour based on state
        if self.active:
            col = C_BTN_ACT
        elif self.rect.collidepoint(mouse_pos):
            col = C_BTN_HOV
        else:
            col = self.color

        pygame.draw.rect(surface, col, self.rect, border_radius=6)
        pygame.draw.rect(surface, C_GRID_LINE, self.rect,
                         width=1, border_radius=6)

        text_surf = font.render(self.label, True, C_BTN_TEXT)
        tx = self.rect.centerx - text_surf.get_width()  // 2
        ty = self.rect.centery - text_surf.get_height() // 2
        surface.blit(text_surf, (tx, ty))

    def is_clicked(self, event):
        return (event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and self.rect.collidepoint(event.pos))


# ──────────────────────────────────────────────
# MAIN APPLICATION CLASS
# ──────────────────────────────────────────────
class PathfinderApp:
    """
    Manages the Pygame window, user interaction, and the search loop.
    """

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIN_W, WIN_H))
        pygame.display.set_caption("GOOD PERFORMANCE TIME APP")

        # fonts
        self.font_title  = pygame.font.SysFont("consolas", 20, bold=True)
        self.font_btn    = pygame.font.SysFont("consolas", 14, bold=True)
        self.font_status = pygame.font.SysFont("consolas", 13)
        self.font_cell   = pygame.font.SysFont("consolas", 11)

        self.grid = Grid(ROWS, COLS)

        # search state
        self.generator    = None   # current algorithm generator
        self.frontier     = set()
        self.explored     = set()
        self.path         = []
        self.found        = False
        self.failed       = False
        self.running      = False  # is the algorithm actively stepping?
        self.message      = "Select an algorithm and click its button."
        self.algo_name    = ""

        # dynamic walls that appeared this run (for recoloring)
        self.dynamic_walls = set()

        # speed: steps per second
        self.speed   = 8
        self.last_t  = 0

        # step mode: if True, user must press "Next Step" manually
        self.step_mode = False

        # re-plan counter
        self.replan_count = 0

        # build UI buttons
        self._build_buttons()

        self.clock = pygame.time.Clock()

    # ── build all buttons ────────────────────────────────
    def _build_buttons(self):
        px = GRID_PX_W + MARGIN_LEFT * 2 + 10   # left edge of panel
        py = MARGIN_TOP + 10                      # top of panel
        bw = PANEL_WIDTH - 20                     # button width
        bh = 36                                   # button height
        gap = 8

        self.algo_buttons = {}
        for name in ALGORITHMS:
            btn = Button(px, py, bw, bh, name)
            self.algo_buttons[name] = btn
            py += bh + gap

        py += 10  # extra gap before utility buttons

        self.btn_reset = Button(px, py, bw, bh, "Reset Grid", C_BTN)
        py += bh + gap

        self.btn_speed_up = Button(px, py, bw // 2 - 2, bh, "Speed +")
        self.btn_speed_dn = Button(px + bw // 2 + 2, py, bw // 2 - 2, bh, "Speed -")
        py += bh + gap

        self.btn_step = Button(px, py, bw, bh, "Step Mode: OFF")
        py += bh + gap

        self.btn_next = Button(px, py, bw, bh, "Next Step")
        py += bh + gap

        self.info_y = py + 10   # where to draw the legend / info text

    # ──────────────────────────────────────────────────────
    # GRID → pixel helpers
    # ──────────────────────────────────────────────────────
    def cell_rect(self, row, col):
        """Return the pygame.Rect for a given grid cell."""
        x = MARGIN_LEFT + col * CELL_SIZE
        y = MARGIN_TOP  + row * CELL_SIZE
        return pygame.Rect(x, y, CELL_SIZE, CELL_SIZE)

    def pixel_to_cell(self, px, py):
        """Convert a screen pixel position to (row, col), or None."""
        col = (px - MARGIN_LEFT) // CELL_SIZE
        row = (py - MARGIN_TOP)  // CELL_SIZE
        if 0 <= row < ROWS and 0 <= col < COLS:
            return (row, col)
        return None

    # ──────────────────────────────────────────────────────
    # DRAWING
    # ──────────────────────────────────────────────────────
    def draw(self):
        self.screen.fill(C_BG)
        self._draw_title_bar()
        self._draw_grid()
        self._draw_panel()
        self._draw_status_bar()
        pygame.display.flip()

    def _draw_title_bar(self):
        title = "  GOOD PERFORMANCE TIME APP  –  AI Grid Pathfinder"
        surf  = self.font_title.render(title, True, C_TITLE)
        self.screen.blit(surf, (10, 14))

        # show algorithm name and speed
        info = f"Algorithm: {self.algo_name or '—'}   |   Speed: {self.speed} steps/s   |   Re-plans: {self.replan_count}"
        isurf = self.font_status.render(info, True, C_STATUS)
        self.screen.blit(isurf, (10, 38))

    def _draw_grid(self):
        for row in range(ROWS):
            for col in range(COLS):
                rect = self.cell_rect(row, col)
                pos  = (row, col)
                val  = self.grid.grid[row][col]

                # ── choose fill colour ──
                if val == WALL:
                    if pos in self.dynamic_walls:
                        color = C_DYN_WALL
                    else:
                        color = C_WALL
                elif pos == self.grid.start:
                    color = C_START
                elif pos == self.grid.target:
                    color = C_TARGET
                elif pos in self.path:
                    color = C_PATH
                elif pos in self.frontier:
                    color = C_FRONTIER
                elif pos in self.explored:
                    color = C_EXPLORED
                else:
                    color = C_CELL_EMPTY

                pygame.draw.rect(self.screen, color, rect)
                pygame.draw.rect(self.screen, C_GRID_LINE, rect, 1)

                # ── cell labels ──
                if pos == self.grid.start:
                    self._draw_cell_label(rect, "S", C_BG)
                elif pos == self.grid.target:
                    self._draw_cell_label(rect, "T", C_BG)
                elif val == WALL:
                    self._draw_cell_label(rect, "■", C_BG)

    def _draw_cell_label(self, rect, text, color):
        surf = self.font_btn.render(text, True, color)
        self.screen.blit(surf,
                         (rect.centerx - surf.get_width()  // 2,
                          rect.centery - surf.get_height() // 2))

    def _draw_panel(self):
        # panel background
        panel_rect = pygame.Rect(
            GRID_PX_W + MARGIN_LEFT * 2, MARGIN_TOP,
            PANEL_WIDTH, GRID_PX_H
        )
        pygame.draw.rect(self.screen, C_PANEL, panel_rect)
        pygame.draw.rect(self.screen, C_GRID_LINE, panel_rect, 1)

        mouse = pygame.mouse.get_pos()

        # algo buttons
        for name, btn in self.algo_buttons.items():
            btn.draw(self.screen, self.font_btn, mouse)

        # utility buttons
        self.btn_reset.draw(self.screen, self.font_btn, mouse)
        self.btn_speed_up.draw(self.screen, self.font_btn, mouse)
        self.btn_speed_dn.draw(self.screen, self.font_btn, mouse)
        self.btn_step.draw(self.screen, self.font_btn, mouse)
        self.btn_next.draw(self.screen, self.font_btn, mouse)

        # colour legend
        self._draw_legend()

    def _draw_legend(self):
        x  = GRID_PX_W + MARGIN_LEFT * 2 + 12
        y  = self.info_y
        fs = self.font_cell

        items = [
            (C_START,    "Start (S)"),
            (C_TARGET,   "Target (T)"),
            (C_WALL,     "Static Wall"),
            (C_DYN_WALL, "Dynamic Wall"),
            (C_FRONTIER, "Frontier"),
            (C_EXPLORED, "Explored"),
            (C_PATH,     "Final Path"),
        ]
        for color, label in items:
            pygame.draw.rect(self.screen, color,
                             pygame.Rect(x, y, 14, 14), border_radius=2)
            surf = fs.render(label, True, C_STATUS)
            self.screen.blit(surf, (x + 20, y))
            y += 20

        # hint
        y += 8
        hints = [
            "Left-click: toggle wall",
            "Right-drag: paint walls",
            "Click an algo to start",
        ]
        for h in hints:
            s = fs.render(h, True, (100, 110, 140))
            self.screen.blit(s, (x, y))
            y += 18

    def _draw_status_bar(self):
        # bottom status bar
        rect  = pygame.Rect(0, WIN_H - MARGIN_BOT, WIN_W, MARGIN_BOT)
        pygame.draw.rect(self.screen, C_PANEL, rect)
        pygame.draw.rect(self.screen, C_GRID_LINE, rect, 1)

        color = C_FOUND if self.found else (C_FAIL if self.failed else C_STATUS)
        surf  = self.font_status.render(self.message, True, color)
        self.screen.blit(surf, (12, WIN_H - MARGIN_BOT + 10))

    # ──────────────────────────────────────────────────────
    # START AN ALGORITHM
    # ──────────────────────────────────────────────────────
    def start_algorithm(self, name):
        """Reset search state and start the chosen algorithm generator."""
        # clear previous results
        self.frontier      = set()
        self.explored      = set()
        self.path          = []
        self.found         = False
        self.failed        = False
        self.dynamic_walls = set()
        self.replan_count  = 0
        self.algo_name     = name
        self.message       = f"Running {name}…"

        # deactivate all buttons; activate selected
        for btn in self.algo_buttons.values():
            btn.active = False
        self.algo_buttons[name].active = True

        # create a fresh generator
        algo_fn       = ALGORITHMS[name]
        self.generator = algo_fn(self.grid)
        self.running   = True
        self.last_t    = time.time()

    # ──────────────────────────────────────────────────────
    # ADVANCE ONE STEP
    # ──────────────────────────────────────────────────────
    def step(self):
        """Pull the next frame from the generator and update state."""
        if self.generator is None or not self.running:
            return

        try:
            state = next(self.generator)
        except StopIteration:
            self.running = False
            return

        self.frontier = state["frontier"]
        self.explored = state["explored"]
        self.path     = state["path"]
        self.found    = state["found"]
        self.failed   = state["failed"]
        self.message  = state["message"]

        # ── record any new dynamic walls ──
        for r in range(ROWS):
            for c in range(COLS):
                pos = (r, c)
                if (self.grid.grid[r][c] == WALL
                        and pos not in self.dynamic_walls
                        and pos != self.grid.start
                        and pos != self.grid.target):
                    # we'll mark ALL new walls since last reset as dynamic
                    # (the grid class adds them; we track them here for colour)
                    pass  # handled below

        # detect if the planned path was blocked by a dynamic obstacle
        if self.path and not self.found:
            for pos in self.path:
                if self.grid.grid[pos[0]][pos[1]] == WALL:
                    # re-plan: restart the same algorithm
                    self.replan_count += 1
                    self.message = (f"⚠ Path blocked! Re-planning… "
                                    f"(#{self.replan_count})")
                    algo_fn        = ALGORITHMS[self.algo_name]
                    self.generator = algo_fn(self.grid)
                    break

        if self.found or self.failed:
            self.running = False
            for btn in self.algo_buttons.values():
                btn.active = False

    # ──────────────────────────────────────────────────────
    # RESET
    # ──────────────────────────────────────────────────────
    def reset(self):
        self.grid.reset()
        self.generator     = None
        self.frontier      = set()
        self.explored      = set()
        self.path          = []
        self.found         = False
        self.failed        = False
        self.running       = False
        self.message       = "Grid reset. Choose an algorithm."
        self.algo_name     = ""
        self.dynamic_walls = set()
        self.replan_count  = 0
        for btn in self.algo_buttons.values():
            btn.active = False

    # ──────────────────────────────────────────────────────
    # MAIN LOOP
    # ──────────────────────────────────────────────────────
    def run(self):
        dragging_wall = False   # for right-click drag painting

        while True:
            self.clock.tick(60)   # cap at 60 FPS

            # ── events ──────────────────────────────────────
            for event in pygame.event.get():

                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                # ── keyboard shortcuts ──
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        self.reset()
                    elif event.key == pygame.K_SPACE and self.step_mode:
                        self.step()

                # ── mouse button down ──
                if event.type == pygame.MOUSEBUTTONDOWN:

                    # LEFT click – toggle wall
                    if event.button == 1:
                        cell = self.pixel_to_cell(*event.pos)
                        if cell:
                            r, c = cell
                            if not self.running:
                                self.grid.toggle_wall(r, c)

                    # RIGHT click – start drag-painting walls
                    if event.button == 3:
                        dragging_wall = True

                    # ── button clicks ──
                    for name, btn in self.algo_buttons.items():
                        if btn.is_clicked(event):
                            self.reset()              # clear previous run
                            self.start_algorithm(name)

                    if self.btn_reset.is_clicked(event):
                        self.reset()

                    if self.btn_speed_up.is_clicked(event):
                        self.speed = min(self.speed + 2, 60)

                    if self.btn_speed_dn.is_clicked(event):
                        self.speed = max(self.speed - 2, 1)

                    if self.btn_step.is_clicked(event):
                        self.step_mode = not self.step_mode
                        self.btn_step.label = (
                            "Step Mode: ON"
                            if self.step_mode
                            else "Step Mode: OFF"
                        )

                    if self.btn_next.is_clicked(event):
                        if self.step_mode:
                            self.step()

                if event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 3:
                        dragging_wall = False

                if event.type == pygame.MOUSEMOTION and dragging_wall:
                    cell = self.pixel_to_cell(*event.pos)
                    if cell:
                        r, c = cell
                        if (not self.running
                                and (r, c) != self.grid.start
                                and (r, c) != self.grid.target):
                            self.grid.grid[r][c] = WALL

            # ── auto-step ───────────────────────────────────
            if self.running and not self.step_mode:
                now = time.time()
                if now - self.last_t >= 1.0 / self.speed:
                    self.step()
                    self.last_t = now

            # ── draw ────────────────────────────────────────
            self.draw()


# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  GOOD PERFORMANCE TIME APP  –  AI Grid Pathfinder")
    print("=" * 55)
    print("Controls:")
    print("  Click an algo button  → start that algorithm")
    print("  Left-click on grid    → toggle wall")
    print("  Right-drag on grid    → paint walls")
    print("  [Reset Grid]          → clear everything")
    print("  [Speed +/-]           → change animation speed")
    print("  [Step Mode]           → manual stepping")
    print("  [Next Step]           → one step at a time")
    print("  R key                 → reset")
    print("  Space key             → next step (in Step Mode)")
    print("=" * 55)

    app = PathfinderApp()
    app.run()
