import pygame
import sys
import math
import random
import asyncio

# --- Constants ---
SCREEN_W, SCREEN_H = 800, 500
HUD_HEIGHT = 60
MAZE_H = SCREEN_H - HUD_HEIGHT
TILE = 20
COLS = SCREEN_W // TILE   # 40
ROWS = MAZE_H // TILE     # 22

BLACK  = (0, 0, 0)
BLUE   = (33, 33, 255)
LBLUE  = (100, 100, 255)
YELLOW = (255, 255, 0)
WHITE  = (255, 255, 255)
RED    = (255, 0, 0)
PINK   = (255, 184, 255)
CYAN   = (0, 255, 255)
ORANGE = (255, 184, 81)
SCARED = (0, 0, 200)
DOT_C  = (255, 185, 175)
DGRAY  = (40, 40, 40)

FPS           = 60
PACMAN_SPEED  = 2
GHOST_SPEED   = 1
FRIGHTEN_TICKS = 7 * FPS

WALL   = 0
DOT    = 1
PELLET = 2
EMPTY  = 3

def _make_maze():
    rows = []
    for r in range(ROWS):
        if r == 0 or r == ROWS - 1:
            rows.append(['#'] * COLS)
            continue
        row = []
        for c in range(COLS):
            if c == 0 or c == COLS - 1:
                row.append('#')
            else:
                row.append('.')
        rows.append(row)

    def wall_rect(r1, c1, r2, c2):
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                if 0 <= r < ROWS and 0 <= c < COLS:
                    rows[r][c] = '#'

    wall_rect(2, 2, 4, 4);   wall_rect(2, 6, 4, 11)
    wall_rect(2, 13, 4, 17); wall_rect(2, 19, 4, 20)
    wall_rect(2, 22, 4, 26); wall_rect(2, 28, 4, 33)
    wall_rect(2, 35, 4, 37)
    wall_rect(6, 2, 7, 4);   wall_rect(6, 6, 7, 8)
    wall_rect(6, 10, 7, 14); wall_rect(6, 16, 7, 23)
    wall_rect(6, 25, 7, 29); wall_rect(6, 31, 7, 33)
    wall_rect(6, 35, 7, 37)
    wall_rect(9, 0, 17, 4);  wall_rect(9, 35, 17, 39)
    wall_rect(9, 6, 10, 14); wall_rect(9, 25, 10, 33)
    wall_rect(11, 16, 14, 23)
    for r in range(12, 14):
        for c in range(17, 23):
            rows[r][c] = ' '
    for c in range(18, 22):
        rows[11][c] = ' '
    wall_rect(17, 2, 18, 4);  wall_rect(17, 6, 18, 11)
    wall_rect(17, 13, 18, 17); wall_rect(17, 22, 18, 26)
    wall_rect(17, 28, 18, 33); wall_rect(17, 35, 18, 37)

    rows[1][1]        = 'o'
    rows[1][COLS - 2] = 'o'
    rows[ROWS - 2][1]        = 'o'
    rows[ROWS - 2][COLS - 2] = 'o'

    return [''.join(r) for r in rows]


MAZE_TEMPLATE = _make_maze()


def build_maze(template):
    grid = []
    dots = 0
    for row_str in template:
        row = []
        for ch in row_str:
            if ch == '#':
                row.append(WALL)
            elif ch == 'o':
                row.append(PELLET)
                dots += 1
            elif ch == '.':
                row.append(DOT)
                dots += 1
            else:
                row.append(EMPTY)
        grid.append(row)
    return grid, dots


def draw_tile(surface, r, c, tile):
    x = c * TILE
    y = r * TILE
    rect = pygame.Rect(x, y, TILE, TILE)
    if tile == WALL:
        pygame.draw.rect(surface, BLUE, rect)
        pygame.draw.rect(surface, LBLUE, rect, 1)
    elif tile == DOT:
        pygame.draw.rect(surface, BLACK, rect)
        pygame.draw.circle(surface, DOT_C, rect.center, 2)
    elif tile == PELLET:
        pygame.draw.rect(surface, BLACK, rect)
        pygame.draw.circle(surface, WHITE, rect.center, 5)
    else:
        pygame.draw.rect(surface, BLACK, rect)


class Pacman:
    def __init__(self):
        self.reset()

    def reset(self):
        self.col = COLS // 2
        self.row = ROWS - 4
        self.px = float(self.col * TILE + TILE // 2)
        self.py = float(self.row * TILE + TILE // 2)
        self.dir = (0, 0)
        self.next_dir = (1, 0)
        self.mouth_angle = 30.0
        self.mouth_dir = 1
        self.radius = TILE // 2 - 2

    def handle_key(self, key):
        if key == pygame.K_LEFT:  self.next_dir = (-1, 0)
        if key == pygame.K_RIGHT: self.next_dir = (1, 0)
        if key == pygame.K_UP:    self.next_dir = (0, -1)
        if key == pygame.K_DOWN:  self.next_dir = (0, 1)

    def update(self, maze):
        cx = self.col * TILE + TILE // 2
        cy = self.row * TILE + TILE // 2
        if abs(self.px - cx) <= PACMAN_SPEED and abs(self.py - cy) <= PACMAN_SPEED:
            ndc, ndr = self.next_dir
            nc = self.col + ndc
            nr = self.row + ndr
            if 0 <= nr < ROWS and 0 <= nc < COLS and maze[nr][nc] != WALL:
                if self.next_dir != self.dir:
                    self.px = float(cx)
                    self.py = float(cy)
                self.dir = self.next_dir
        dc, dr = self.dir
        if dc != 0 or dr != 0:
            new_px = self.px + dc * PACMAN_SPEED
            new_py = self.py + dr * PACMAN_SPEED
            new_col = int(new_px) // TILE
            new_row = int(new_py) // TILE
            if 0 <= new_row < ROWS and 0 <= new_col < COLS and maze[new_row][new_col] != WALL:
                self.px = new_px
                self.py = new_py
            else:
                self.px = float(cx)
                self.py = float(cy)
        if self.px < 0:         self.px = SCREEN_W - 1.0
        if self.px >= SCREEN_W: self.px = 0.0
        self.col = max(0, min(COLS - 1, int(self.px) // TILE))
        self.row = max(0, min(ROWS - 1, int(self.py) // TILE))
        self.mouth_angle += 3 * self.mouth_dir
        if self.mouth_angle >= 45: self.mouth_dir = -1
        if self.mouth_angle <= 0:  self.mouth_dir = 1

    def draw(self, surface):
        ix, iy = int(self.px), int(self.py)
        pygame.draw.circle(surface, YELLOW, (ix, iy), self.radius)
        if self.dir != (0, 0):
            angle = math.atan2(self.dir[1], self.dir[0])
            half = math.radians(self.mouth_angle / 2)
            r = self.radius + 1
            p1 = (ix + r * math.cos(angle - half), iy + r * math.sin(angle - half))
            p2 = (ix + r * math.cos(angle + half), iy + r * math.sin(angle + half))
            pygame.draw.polygon(surface, BLACK, [(ix, iy), p1, p2])


class Ghost:
    def __init__(self, col, row, color, scatter_target):
        self.start_col = col
        self.start_row = row
        self.color = color
        self.scatter_target = scatter_target
        self.reset()

    def reset(self):
        self.col = self.start_col
        self.row = self.start_row
        self.px = float(self.col * TILE + TILE // 2)
        self.py = float(self.row * TILE + TILE // 2)
        self.dir = (0, -1)
        self.mode = 'scatter'
        self.frighten_timer = 0
        self.radius = TILE // 2 - 2
        self.flash_timer = 0

    def frighten(self):
        if self.mode != 'eaten':
            self.mode = 'frightened'
            self.frighten_timer = FRIGHTEN_TICKS

    def _is_aligned(self):
        cx = self.col * TILE + TILE // 2
        cy = self.row * TILE + TILE // 2
        return abs(self.px - cx) < GHOST_SPEED + 1 and abs(self.py - cy) < GHOST_SPEED + 1

    def _choose_dir(self, maze, pacman):
        DIRS = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        reverse = (-self.dir[0], -self.dir[1])
        if self.mode == 'eaten':
            target = (COLS // 2, ROWS // 2)
        elif self.mode == 'frightened':
            options = [d for d in DIRS
                       if d != reverse
                       and 0 <= self.row + d[1] < ROWS
                       and 0 <= self.col + d[0] < COLS
                       and maze[self.row + d[1]][self.col + d[0]] != WALL]
            if options:
                self.dir = random.choice(options)
            return
        elif self.mode == 'scatter':
            target = self.scatter_target
        else:
            target = (pacman.col, pacman.row)
            if self.color == PINK:
                dc, dr = pacman.dir
                target = (pacman.col + 4 * dc, pacman.row + 4 * dr)
        best_dir = None
        best_dist = float('inf')
        for d in DIRS:
            if d == reverse:
                continue
            nc = self.col + d[0]
            nr = self.row + d[1]
            if not (0 <= nr < ROWS and 0 <= nc < COLS):
                continue
            if maze[nr][nc] == WALL:
                continue
            dist = (nc - target[0]) ** 2 + (nr - target[1]) ** 2
            if dist < best_dist:
                best_dist = dist
                best_dir = d
        if best_dir:
            self.dir = best_dir

    def update(self, maze, pacman):
        if self.mode == 'frightened':
            self.frighten_timer -= 1
            if self.frighten_timer <= 0:
                self.mode = 'chase'
        if self.mode == 'eaten':
            hx = COLS // 2 * TILE + TILE // 2
            hy = ROWS // 2 * TILE + TILE // 2
            if abs(self.px - hx) < TILE and abs(self.py - hy) < TILE:
                self.mode = 'scatter'
        speed = GHOST_SPEED * 2 if self.mode == 'eaten' else GHOST_SPEED
        if self._is_aligned():
            old_dir = self.dir
            self._choose_dir(maze, pacman)
            if self.dir != old_dir:
                self.px = float(self.col * TILE + TILE // 2)
                self.py = float(self.row * TILE + TILE // 2)
        dc, dr = self.dir
        new_px = self.px + dc * speed
        new_py = self.py + dr * speed
        nc = int(new_px) // TILE
        nr = int(new_py) // TILE
        if 0 <= nr < ROWS and 0 <= nc < COLS and maze[nr][nc] != WALL:
            self.px = new_px
            self.py = new_py
        else:
            self.px = float(self.col * TILE + TILE // 2)
            self.py = float(self.row * TILE + TILE // 2)
        self.col = max(0, min(COLS - 1, int(self.px) // TILE))
        self.row = max(0, min(ROWS - 1, int(self.py) // TILE))

    def draw(self, surface):
        if self.mode == 'eaten':
            ix, iy = int(self.px), int(self.py)
            r = self.radius
            pygame.draw.circle(surface, WHITE, (ix - r // 3, iy - r // 4), r // 4)
            pygame.draw.circle(surface, WHITE, (ix + r // 3, iy - r // 4), r // 4)
            pygame.draw.circle(surface, CYAN,  (ix - r // 3, iy - r // 4), r // 8)
            pygame.draw.circle(surface, CYAN,  (ix + r // 3, iy - r // 4), r // 8)
            return
        if self.mode == 'frightened':
            flash = self.frighten_timer < 2 * FPS and (self.frighten_timer // 15) % 2 == 0
            color = WHITE if flash else SCARED
        else:
            color = self.color
        ix, iy = int(self.px), int(self.py)
        r = self.radius
        pygame.draw.rect(surface, color, (ix - r, iy, r * 2, r))
        pygame.draw.circle(surface, color, (ix, iy), r)
        for i in range(3):
            bx = ix - r + i * (r * 2 // 3) + r // 3
            pygame.draw.circle(surface, BLACK, (bx, iy + r), r // 3)
        if self.mode not in ('frightened',):
            pygame.draw.circle(surface, WHITE, (ix - r // 3, iy - r // 4), r // 4)
            pygame.draw.circle(surface, WHITE, (ix + r // 3, iy - r // 4), r // 4)
            pygame.draw.circle(surface, BLUE,  (ix - r // 3, iy - r // 4), r // 8)
            pygame.draw.circle(surface, BLUE,  (ix + r // 3, iy - r // 4), r // 8)


class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption('Pacman')
        self.clock = pygame.time.Clock()
        self.font_big   = pygame.font.Font(None, 56)
        self.font_small = pygame.font.Font(None, 28)
        self.reset()

    def reset(self):
        self.maze, self.total_dots = build_maze(MAZE_TEMPLATE)
        self.dots_remaining = self.total_dots
        self.score = 0
        self.lives = 3
        self.state = 'start'
        self.pacman = Pacman()
        self.ghosts = [
            Ghost(18, 12, RED,    (COLS - 1, 0)),
            Ghost(21, 12, PINK,   (0, 0)),
            Ghost(18, 13, CYAN,   (COLS - 1, ROWS - 1)),
            Ghost(21, 13, ORANGE, (0, ROWS - 1)),
        ]
        self.bg = self._build_bg()
        self.global_mode = 'scatter'
        self.mode_timer = 7 * FPS
        self.dying_timer = 0
        self.eaten_streak = 0

    def _build_bg(self):
        surf = pygame.Surface((SCREEN_W, SCREEN_H))
        surf.fill(BLACK)
        for r in range(ROWS):
            for c in range(COLS):
                draw_tile(surf, r, c, self.maze[r][c])
        pygame.draw.line(surf, BLUE, (0, MAZE_H), (SCREEN_W, MAZE_H), 2)
        return surf

    def _reset_positions(self):
        self.pacman.reset()
        for g in self.ghosts:
            g.reset()

    def _pacman_killed(self):
        self.lives -= 1
        self.dying_timer = int(1.5 * FPS)
        self.state = 'dying'

    def _check_dots(self):
        c, r = self.pacman.col, self.pacman.row
        if not (0 <= r < ROWS and 0 <= c < COLS):
            return
        tile = self.maze[r][c]
        if tile == DOT:
            self.maze[r][c] = EMPTY
            draw_tile(self.bg, r, c, EMPTY)
            self.score += 10
            self.dots_remaining -= 1
        elif tile == PELLET:
            self.maze[r][c] = EMPTY
            draw_tile(self.bg, r, c, EMPTY)
            self.score += 50
            self.dots_remaining -= 1
            self.eaten_streak = 0
            for g in self.ghosts:
                g.frighten()

    def _check_ghosts(self):
        for g in self.ghosts:
            dist = math.hypot(g.px - self.pacman.px, g.py - self.pacman.py)
            if dist < self.pacman.radius + g.radius - 2:
                if g.mode == 'frightened':
                    g.mode = 'eaten'
                    self.eaten_streak += 1
                    self.score += 200 * (2 ** (self.eaten_streak - 1))
                elif g.mode not in ('eaten',):
                    self._pacman_killed()
                    return

    def _update_global_mode(self):
        self.mode_timer -= 1
        if self.mode_timer <= 0:
            if self.global_mode == 'scatter':
                self.global_mode = 'chase'
                self.mode_timer = 20 * FPS
            else:
                self.global_mode = 'scatter'
                self.mode_timer = 7 * FPS
            for g in self.ghosts:
                if g.mode not in ('frightened', 'eaten'):
                    g.mode = self.global_mode

    def _draw_hud(self):
        y = MAZE_H + 5
        pygame.draw.rect(self.screen, DGRAY, (0, MAZE_H, SCREEN_W, HUD_HEIGHT))
        score_surf = self.font_small.render(f'SCORE  {self.score:>6}', True, WHITE)
        self.screen.blit(score_surf, (10, y + 10))
        label = self.font_small.render('PACMAN', True, YELLOW)
        self.screen.blit(label, (SCREEN_W // 2 - label.get_width() // 2, y + 10))
        for i in range(self.lives):
            cx = SCREEN_W - 20 - i * 26
            cy = y + 22
            pygame.draw.circle(self.screen, YELLOW, (cx, cy), 10)
            pygame.draw.polygon(self.screen, BLACK, [(cx, cy), (cx + 10, cy - 5), (cx + 10, cy + 5)])

    def _draw_overlay(self, lines):
        panel = pygame.Surface((360, 30 + len(lines) * 55), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 190))
        self.screen.blit(panel, (SCREEN_W // 2 - 180, 160))
        for i, (text, color, big) in enumerate(lines):
            font = self.font_big if big else self.font_small
            surf = font.render(text, True, color)
            self.screen.blit(surf, (SCREEN_W // 2 - surf.get_width() // 2, 175 + i * 55))

    async def run(self):
        while True:
            self.clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    raise SystemExit
                if event.type == pygame.KEYDOWN:
                    if self.state == 'playing':
                        self.pacman.handle_key(event.key)
                    elif self.state in ('start', 'game_over', 'win'):
                        if event.key == pygame.K_SPACE:
                            self.reset()
                            self.state = 'playing'

            if self.state == 'playing':
                self.pacman.update(self.maze)
                self._update_global_mode()
                for g in self.ghosts:
                    g.update(self.maze, self.pacman)
                self._check_dots()
                self._check_ghosts()
                if self.dots_remaining <= 0:
                    self.state = 'win'
            elif self.state == 'dying':
                self.dying_timer -= 1
                if self.dying_timer <= 0:
                    if self.lives <= 0:
                        self.state = 'game_over'
                    else:
                        self._reset_positions()
                        self.state = 'playing'

            self.screen.blit(self.bg, (0, 0))
            if self.state != 'dying' or (self.dying_timer // 8) % 2 == 0:
                self.pacman.draw(self.screen)
            for g in self.ghosts:
                g.draw(self.screen)
            self._draw_hud()

            if self.state == 'start':
                self._draw_overlay([
                    ('PACMAN', YELLOW, True),
                    ('Press SPACE to start', WHITE, False),
                ])
            elif self.state == 'game_over':
                self._draw_overlay([
                    ('GAME OVER', RED, True),
                    (f'Score: {self.score}', WHITE, False),
                    ('Press SPACE to retry', WHITE, False),
                ])
            elif self.state == 'win':
                self._draw_overlay([
                    ('YOU WIN!', YELLOW, True),
                    (f'Score: {self.score}', WHITE, False),
                    ('Press SPACE to play again', WHITE, False),
                ])

            pygame.display.flip()
            await asyncio.sleep(0)


async def main():
    pygame.init()
    await Game().run()


asyncio.run(main())
