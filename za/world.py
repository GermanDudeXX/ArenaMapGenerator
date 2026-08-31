"""Arena-Layout, Autotiling und Deko-Objekte."""
import random

import pygame

from . import assetlib as A
from . import mapgen
from .settings import (
    TILE, MAP_W, MAP_H, VOID, WALL, FLOOR, GATE,
    ARENA_X0, ARENA_Y0, ARENA_X1, ARENA_Y1,
    SAFE_X0, SAFE_Y0, SAFE_X1, SAFE_Y1, GATE_X, GATE_Y0, GATE_Y1,
)

# Der Tileset-Block bei Spalte 1..5 / Zeile 1..5 ist ein 3x3-Autotile:
# der Ring ist Mauer, der 3x3-Kern (Spalte 2..4, Zeile 2..4) ist Boden.
# Welches Tile wo hinkommt, entscheidet mapgen.atlas_map() - hier wird
# nur noch geblittet.


def build_fill_tile(band):
    """Eine Zeile aus dem oberen Randtile zu einem vollen Tile strecken.

    Auch der Godot-Export braucht genau dieses Bild, deshalb steht es
    frei und nicht in einer Methode.
    """
    fill = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
    for y in range(TILE):
        fill.blit(band, (0, y), (0, TILE - mapgen.FILL_ROW, TILE, 1))
    return fill


class Prop:
    """Statisches Deko-Objekt, wird nach y sortiert gezeichnet."""

    def __init__(self, surf, x, y):
        self.surf = surf
        self.x = x                      # Weltkoordinate, Fusspunkt-Mitte
        self.y = y

    def draw(self, surf, cam):
        w, h = self.surf.get_size()
        surf.blit(self.surf, (int(self.x - w // 2 - cam[0]), int(self.y - h - cam[1])))


class Torch:
    """Wandfackel mit Flammenanimation."""

    def __init__(self, frames, base, x, y, phase):
        self.frames = frames
        self.base = base
        self.x, self.y = x, y
        self.t = phase

    def update(self, dt):
        self.t += dt

    def draw(self, surf, cam):
        bw, bh = self.base.get_size()
        surf.blit(self.base, (int(self.x - bw // 2 - cam[0]), int(self.y - bh - cam[1])))
        f = self.frames[int(self.t * 12) % len(self.frames)]
        fw, fh = f.get_size()
        surf.blit(f, (int(self.x - fw // 2 - cam[0]), int(self.y - bh - fh + 4 - cam[1])))


class World:
    """Die Karte.

    `seed=None` gibt das handgesetzte Layout, ein int laesst sie
    generieren; `mode` waehlt die Art (siehe mapgen.MODES).

    Alles ab `_load_tiles()` ist identisch - das Autotiling kennt nur das
    Gitter und interessiert sich nicht dafuer, woher es kommt. Genau darum
    kostet eine neue Kartenart hier keine Zeile: sie ist ein Eintrag in
    mapgen.MODES und kein zweiter Renderpfad.
    """

    def __init__(self, seed=None, mode=None, size=None, safe_size=None,
                 safe_pos="oben links", masse=None):
        self.grid = [[VOID] * MAP_W for _ in range(MAP_H)]
        self.props = []
        self.torches = []
        self.blueprint = None
        self.spawns = []
        self.size = size
        self.safe_size = safe_size
        if size is not None:
            self._build_section(seed, mode, size)
        elif seed is None:
            self._build_grid()
        else:
            self._build_generated(seed, mode, safe_size, safe_pos, masse)
        self._load_tiles()
        self._render_ground()
        self._place_objects()
        self.door_frames = A.strip(A.load("anim", "BigDoor_S.png"), 30, 42)
        self.door_open = 0.0

    # ------------------------------------------------------------------ Aufbau
    def _build_grid(self):
        g = self.grid
        for y in range(ARENA_Y0, ARENA_Y1 + 1):
            for x in range(ARENA_X0, ARENA_X1 + 1):
                g[y][x] = FLOOR
        # Aussenmauer
        for x in range(ARENA_X0 - 1, ARENA_X1 + 2):
            g[ARENA_Y0 - 1][x] = WALL
            g[ARENA_Y1 + 1][x] = WALL
        for y in range(ARENA_Y0 - 1, ARENA_Y1 + 2):
            g[y][ARENA_X0 - 1] = WALL
            g[y][ARENA_X1 + 1] = WALL

        # Saeulen als Deckung
        self.pillars = [
            (25, 7, 3, 3), (39, 7, 4, 3), (55, 7, 3, 3),
            (25, 21, 3, 4), (55, 21, 3, 4),
            (25, 35, 3, 3), (39, 35, 4, 3), (55, 35, 3, 3),
            (8, 24, 4, 3), (8, 35, 4, 3), (16, 30, 3, 3),
            (46, 18, 3, 3), (46, 27, 3, 3), (34, 27, 3, 3), (34, 18, 3, 3),
        ]
        for (px, py, pw, ph) in self.pillars:
            for y in range(py, py + ph):
                for x in range(px, px + pw):
                    if 0 <= x < MAP_W and 0 <= y < MAP_H:
                        g[y][x] = WALL

        # Abgesperrter Bereich: eigener Raum in der oberen linken Ecke
        for x in range(ARENA_X0 - 1, GATE_X + 1):
            g[SAFE_Y1 + 1][x] = WALL
        for y in range(ARENA_Y0 - 1, SAFE_Y1 + 2):
            g[y][GATE_X] = WALL
        for y in range(SAFE_Y0, SAFE_Y1 + 1):
            for x in range(SAFE_X0, SAFE_X1 + 1):
                g[y][x] = FLOOR
        for y in range(GATE_Y0, GATE_Y1 + 1):
            g[y][GATE_X] = GATE

        self._set_bounds((SAFE_X0, SAFE_Y0, SAFE_X1, SAFE_Y1),
                         (GATE_X, GATE_Y0, GATE_Y1))
        # Spawnpunkte auch hier, damit beide Layouts dasselbe koennen und
        # die Anzeige nicht je nach Modus etwas anderes bedeutet.
        self.spawns = mapgen.spawns_for(self)

    def _build_generated(self, seed, mode=None, safe_size=None,
                         safe_pos="oben links", masse=None):
        """Gitter aus dem Generator uebernehmen statt es hinzuschreiben."""
        w, h = masse or (MAP_W, MAP_H)
        bp = mapgen.generate(seed, mode, w=w, h=h, safe_size=safe_size,
                             safe_pos=safe_pos)
        self.blueprint = bp
        self.grid = bp.grid
        self.pillars = bp.pillars
        self.spawns = bp.spawns
        # Auch hier den Blueprint mitgeben: bei eigenen Massen sind w/h
        # nicht MAP_W/MAP_H, und alles Weitere haengt daran.
        self._set_bounds(bp.safe, bp.gate, bp)

    def _build_section(self, seed, mode, size):
        """Ein Abschnitt: eigene Masse, keine Safezone, kein Tor."""
        bp = mapgen.generate_section(seed, mode, size)
        self.blueprint = bp
        self.grid = bp.grid
        self.pillars = bp.pillars
        self.spawns = bp.spawns
        self._set_bounds(bp.safe, bp.gate, bp)

    def _set_bounds(self, safe, gate, bp=None):
        """Safezone und Tor als Tiles *und* als Pixel-Rects merken.

        Beides liegt auf der Instanz, nicht in den Konstanten: der
        Generator variiert die Groesse der Safezone und die Torhoehe,
        und alles, was danach kommt, muss der Karte glauben statt
        settings.py.
        """
        self.safe = safe
        self.gate = gate
        # Dieselben Geometriefelder wie ein Blueprint. mapgen.spawns_for()
        # rechnet damit, und das handgesetzte Layout geht durch dieselbe
        # Funktion - ohne die Felder faellt es dort auf die Nase.
        if bp is None:
            self.w, self.h = MAP_W, MAP_H
            self.x0, self.y0 = ARENA_X0, ARENA_Y0
            self.x1, self.y1 = ARENA_X1, ARENA_Y1
            self.has_safe = True
        else:
            self.w, self.h = bp.w, bp.h
            self.x0, self.y0, self.x1, self.y1 = bp.x0, bp.y0, bp.x1, bp.y1
            self.has_safe = bp.has_safe

        if not self.has_safe:
            # Ein Abschnitt hat weder Safezone noch Tor - leere Rechtecke
            # statt erfundener Masse, damit der Viewer nichts umrandet,
            # was es nicht gibt.
            self.safe_rect = pygame.Rect(0, 0, 0, 0)
            self.gate_rect = pygame.Rect(0, 0, 0, 0)
            return
        sx0, sy0, sx1, sy1 = safe
        gx, gy0, gy1 = gate
        self.safe_rect = pygame.Rect(sx0 * TILE, sy0 * TILE,
                                     (sx1 - sx0 + 1) * TILE,
                                     (sy1 - sy0 + 1) * TILE)
        self.gate_rect = pygame.Rect(gx * TILE, gy0 * TILE,
                                     TILE, (gy1 - gy0 + 1) * TILE)

    def _load_tiles(self):
        sheet = A.load("tiles", "Tileset.png")
        self.tiles = {}
        for r in range(sheet.get_height() // TILE):
            for c in range(sheet.get_width() // TILE):
                self.tiles[(c, r)] = sheet.subsurface((c * TILE, r * TILE, TILE, TILE))
        # Vollflaechiges Mauerstueck fuer eingeschlossene Wandzellen (Saeulenkerne):
        # die untere Haelfte des oberen Randtiles ist reiner Mauerkoerper.
        self.wall_fill = build_fill_tile(self.tiles[mapgen.FILL_SOURCE])
        # Damit die Suche nach einer Koordinate immer etwas findet, auch
        # fuer das Stueck, das gar nicht im Atlas steht.
        self.tiles[mapgen.FILL_TILE] = self.wall_fill

    def _walkable(self, x, y):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return False
        return self.grid[y][x] in (FLOOR, GATE)

    def _render_ground(self):
        surf = pygame.Surface((self.w * TILE, self.h * TILE), pygame.SRCALPHA)
        self.atlas = mapgen.atlas_map(self.grid)
        for (x, y), coord in self.atlas.items():
            surf.blit(self.tiles[coord], (x * TILE, y * TILE))
        self.ground = surf

    # ----------------------------------------------------------------- Objekte
    def _place_objects(self):
        box = lambda n: A.load("objects", "boxes", "%d.png" % n)
        chest = A.strip(A.load("anim", "Chest1_D.png"), 16, 24)[0]
        lever = A.strip(A.load("anim", "Lever1.png"), 16, 18)[0]

        def tp(tx, ty, ox=8, oy=16):
            return tx * TILE + ox, ty * TILE + oy

        sx0, sy0, sx1, sy1 = self.safe
        gx, gy0, gy1 = self.gate

        def inside(tx, ty):
            return sx0 <= tx <= sx1 and sy0 <= ty <= sy1

        if not self.has_safe:
            # Abschnitt: keine Safezone zum Einrichten, keine Aussenmauer
            # fuer Fackeln entlang des Randes. Also nur Deckung und Licht
            # an dem, was da ist.
            self._decorate_section(box, tp)
            return

        # --- Einrichtung im abgesperrten Bereich. Relativ zu den Ecken der
        # Safezone, weil der Generator ihre Groesse variiert; was durch eine
        # kleinere Safezone hinausfaellt, entfaellt einfach.
        fixed = ((chest, sx0 + 2, sy0 + 2), (box(1), sx0 + 6, sy0 + 2),
                 (box(9), sx0 + 10, sy0 + 2), (box(11), sx1 - 1, sy0 + 2),
                 (lever, sx1 - 1, sy1 - 1))
        for surf, tx, ty in fixed:
            if inside(tx, ty):
                x, y = tp(tx, ty)
                self.props.append(Prop(surf, x, y))
        loose = ((sx0 + 1, sy1 - 1, 3), (sx0 + 2, sy1 - 1, 4),
                 (sx0 + 4, sy1 - 2, 13), (sx0 + 8, sy1 - 1, 12),
                 (sx0 + 11, sy1 - 2, 5), (sx0 + 3, sy0 + 6, 16),
                 (sx0 + 9, sy0 + 7, 2), (sx0 + 6, sy0 + 9, 6))
        for (tx, ty, n) in loose:
            if inside(tx, ty):
                x, y = tp(tx, ty)
                self.props.append(Prop(box(n), x, y))

        # --- Deckung in der Arena rund um die Saeulen
        rng = random.Random(4242)
        for (px, py, pw, ph) in self.pillars:
            for _ in range(rng.randint(1, 3)):
                tx = px + rng.randint(-2, pw + 1)
                ty = py + rng.randint(-1, ph + 1)
                if not self._walkable(tx, ty) or self.in_safe_tile(tx, ty):
                    continue
                x, y = tp(tx, ty)
                self.props.append(Prop(box(rng.choice((1, 2, 3, 4, 7, 8, 12, 13, 14))), x, y))

        # --- Fackeln entlang der Waende
        frames = A.strip(A.load("anim", "Fire1.png"), 16, 16)
        base = A.load("objects", "misc", "torch.png")
        spots = []
        for x in range(ARENA_X0 + 3, ARENA_X1 - 2, 9):
            spots.append((x, ARENA_Y0 - 1))
            spots.append((x, ARENA_Y1 + 1))
        for y in range(ARENA_Y0 + 4, ARENA_Y1 - 2, 9):
            spots.append((ARENA_X0 - 1, y))
            spots.append((ARENA_X1 + 1, y))
        for (tx, ty) in ((gx, gy0 - 4), (gx, gy1 + 4),
                         (sx0 + 3, sy0 - 1), (sx0 + 12, sy0 - 1),
                         (sx0 + 3, sy1 + 1), (sx0 + 12, sy1 + 1)):
            spots.append((tx, ty))
        for i, (tx, ty) in enumerate(spots):
            if not (0 <= tx < self.w and 0 <= ty < self.h):
                continue
            if self.grid[ty][tx] != WALL:
                continue
            self.torches.append(Torch(frames, base, tx * TILE + 8, ty * TILE + 15,
                                      i * 0.37))

    def _decorate_section(self, box, tp):
        """Deko fuer einen Abschnitt.

        Kisten an die Mauerteile, Fackeln auf Mauerzellen mit Boden davor -
        nur die haben eine sichtbare Wandflaeche, auf der eine Fackel
        sitzen kann. Mit Mindestabstand, sonst steht in einem dichten
        Dungeon in jeder zweiten Zelle eine.
        """
        rng = random.Random(4242)
        for (px, py, pw, ph) in self.pillars:
            for _ in range(rng.randint(0, 2)):
                tx = px + rng.randint(-2, pw + 1)
                ty = py + rng.randint(-1, ph + 1)
                if not self._walkable(tx, ty):
                    continue
                x, y = tp(tx, ty)
                self.props.append(
                    Prop(box(rng.choice((1, 2, 3, 4, 7, 8, 12, 13, 14))), x, y))

        frames = A.strip(A.load("anim", "Fire1.png"), 16, 16)
        base = A.load("objects", "misc", "torch.png")
        kandidaten = [(x, y) for y in range(self.h) for x in range(self.w)
                      if self.grid[y][x] == WALL and self._walkable(x, y + 1)]
        rng.shuffle(kandidaten)
        gesetzt = []
        for (tx, ty) in kandidaten:
            if len(gesetzt) >= max(3, (self.w * self.h) // 120):
                break
            if any(max(abs(tx - ox), abs(ty - oy)) < 6 for ox, oy in gesetzt):
                continue
            gesetzt.append((tx, ty))
        for i, (tx, ty) in enumerate(sorted(gesetzt, key=lambda p: (p[1], p[0]))):
            self.torches.append(
                Torch(frames, base, tx * TILE + 8, ty * TILE + 15, i * 0.37))

    # -------------------------------------------------------------- Abfragen
    def in_safe_tile(self, tx, ty):
        if not self.has_safe:
            return False
        sx0, sy0, sx1, sy1 = self.safe
        return sx0 <= tx <= sx1 and sy0 <= ty <= sy1

    def cell(self, tx, ty):
        if 0 <= tx < self.w and 0 <= ty < self.h:
            return self.grid[ty][tx]
        return VOID

    # -------------------------------------------------------------- Zeichnen
    def update(self, dt):
        for t in self.torches:
            t.update(dt)

    def draw_gate(self, surf, cam):
        idx = int(self.door_open * (len(self.door_frames) - 1) + 0.001)
        img = self.door_frames[min(idx, len(self.door_frames) - 1)]
        gx, gy0, gy1 = self.gate
        cx = gx * TILE + 8
        cy = (gy0 + gy1 + 1) * TILE / 2
        surf.blit(img, (int(cx - img.get_width() / 2 - cam[0]),
                        int(cy - img.get_height() / 2 - cam[1])))

    def draw(self, surf, cam):
        """Boden, Mauern, Deko, Fackeln und Tor - nach y sortiert."""
        surf.blit(self.ground, (-cam[0], -cam[1]))
        items = [(p.y, p.draw) for p in self.props]
        items += [(t.y - 6, t.draw) for t in self.torches]
        if self.has_safe:
            items.append(((self.gate[2] + 1) * TILE, self.draw_gate))
        items.sort(key=lambda d: d[0])
        for _, fn in items:
            fn(surf, cam)
