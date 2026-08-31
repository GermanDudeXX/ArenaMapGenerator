"""Kartengenerator - sechsundzwanzig Arten, ein Geruest.

Erzeugt aus einem Seed dasselbe Zellengitter, das `World._build_grid()`
sonst von Hand hinschreibt: VOID / WALL / FLOOR / GATE. Alles danach -
Autotiling, Deko, Fackeln, Zeichnen, der Godot-Export - haengt nur am
Gitter und weiss nicht, woher es kommt.

Der Ablauf ist fuer jede Art derselbe:

    1. Grundriss   Aussenmauer, Safezone oben links, Tor nach rechts
    2. Schnitt     die Art fuellt das Feld - das Einzige, was sich unterscheidet
    3. Anbindung   ein garantierter Weg vom Tor ins Feld
    4. Reparatur   Flutfuellung vom Tor; was nicht erreichbar ist, wird Mauer
    5. Pruefung    offener Anteil, Bloecke, Spawnpunkte - sonst neuer Anlauf

Schritt 4 ist der Grund, warum die Arten so kurz sein duerfen. Ein
Hoehlengenerator muss nicht beweisen, dass er keine abgeschlossene Blase
erzeugt; er darf welche erzeugen, und sie werden hinterher zugemauert.
Was ein Generator nicht garantieren muss, muss er auch nicht koennen.

Die Safezone bleibt in jeder Art oben links, mit Tor nach rechts. Sie
variiert in Groesse und Torhoehe, aber nicht in der Lage: der Spieler muss
wissen, wo er hin muss, wenn die Welle kippt.
"""
import json
import math
import random

from .settings import (
    TILE, MAP_W, MAP_H, VOID, WALL, FLOOR, GATE,
    ARENA_X0, ARENA_Y0, ARENA_X1, ARENA_Y1,
)

# Freie Tiles zwischen zwei Hindernissen - nur die Arena-Arten halten sich
# daran. Dort ist es die Regel, die alles begehbar haelt; die Dungeon- und
# Hoehlenarten erreichen dasselbe ueber die Reparatur.
MIN_GAP = 3

# Bezugsgroesse fuer die Skalierung: die Arena der Vollkarte, 62 x 40.
REF_W = ARENA_X1 - ARENA_X0 + 1
REF_H = ARENA_Y1 - ARENA_Y0 + 1

# Vor dem Tor bleibt frei. Dort steht der Spieler, wenn die Welle startet -
# eine Wand an dieser Stelle waere kein Detail, sondern ein Bug.
GATE_CLEAR_X = 7
GATE_CLEAR_Y = 5

# Gegner erscheinen weit weg vom Tor, moeglichst am Rand.
SPAWN_BORDER = 2
SPAWN_MIN_GATE = 20
SPAWN_SPREAD = 5
SPAWN_MAX = 24

# Vollflaechiges Mauerstueck fuer eingeschlossene Zellen. Im Original-
# Tileset gibt es das nicht - der Viewer erzeugt es zur Laufzeit aus dem
# oberen Randtile. Beim Export wird es an den Atlas angehaengt, damit es
# eine echte Koordinate hat.
FILL_TILE = (0, 11)
FILL_SOURCE = (3, 1)
FILL_ROW = 3


class Blueprint:
    """Fertige Karte plus alles, was das Spiel darueber wissen will."""

    def __init__(self, w=MAP_W, h=MAP_H, arena=None, has_safe=True,
                 safe_size=None, safe_pos="oben links"):
        # Masse gehoeren auf die Karte, nicht in Modulkonstanten: derselbe
        # Generator baut die grosse Arena und einen kleinen Abschnitt fuer
        # Tiled. Die Konstanten bleiben die Vorgabe.
        self.w = w
        self.h = h
        self.x0, self.y0, self.x1, self.y1 = arena or (
            ARENA_X0, ARENA_Y0, ARENA_X1, ARENA_Y1)
        self.has_safe = has_safe
        self.safe_size = safe_size
        self.safe_pos = safe_pos
        # Der Klotz, den der Startraum samt seiner Waende belegt. Das Feld
        # ergibt sich daraus - frueher stand die Ecke fest und liess sich
        # hinschreiben, jetzt muss sie gemerkt werden.
        self.safe_block = (0, 0, -1, -1)
        # Punkt, an dem wachsende Arten ansetzen: bei der Arena das
        # Torvorfeld, beim Abschnitt die Mitte.
        self.origin = (0, 0)
        # Wie sich diese Flaeche zur vollen Arena verhaelt. Bei der
        # Vollkarte ist das exakt 1,0 - Laengen und Anzahlen, die damit
        # skaliert werden, bleiben dort also unveraendert.
        self.fx = (self.x1 - self.x0 + 1) / float(REF_W)
        self.fy = (self.y1 - self.y0 + 1) / float(REF_H)
        self.flin = min(self.fx, self.fy)
        self.farea = self.fx * self.fy
        self.grid = [[VOID] * w for _ in range(h)]
        self.blocks = []           # die echten Zellen je Mauerteil im Feld
        self.pillars = []          # deren Bounding-Boxen - die Deko haengt daran
        self.spawns = []           # (tx, ty) Wellen-Spawnpunkte
        self.safe = (0, 0, 0, 0)   # x0, y0, x1, y1 (Innenraum, inklusive)
        self.gate = (0, 0, 0)      # x, y0, y1
        self.seed = 0
        self.mode = ""
        self.attempts = 1
        self.open_ratio = 0.0

    # -- Abfragen ---------------------------------------------------------
    def walkable(self, x, y):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return False
        return self.grid[y][x] in (FLOOR, GATE)

    @property
    def group(self):
        return MODES[self.mode]["gruppe"] if self.mode in MODES else "?"

    def to_dict(self):
        """Serialisierbare Fassung - so wandert die Karte in die Engine."""
        sym = {VOID: " ", WALL: "#", FLOOR: ".", GATE: "+"}
        sx0, sy0, sx1, sy1 = self.safe
        gx, gy0, gy1 = self.gate
        return {
            "seed": self.seed,
            "mode": self.mode,
            "group": self.group,
            "tile": TILE,
            "width": self.w,
            "height": self.h,
            "legend": {"void": " ", "wall": "#", "floor": ".", "gate": "+"},
            "safezone": {"x0": sx0, "y0": sy0, "x1": sx1, "y1": sy1,
                         "w": sx1 - sx0 + 1, "h": sy1 - sy0 + 1,
                         "pos": self.safe_pos},
            "gate": {"x": gx, "y0": gy0, "y1": gy1},
            "open_ratio": round(self.open_ratio, 4),
            "blocks": [{"box": {"x": x, "y": y, "w": w, "h": h},
                        "rects": [{"x": rx, "y": ry, "w": rw, "h": rh}
                                  for (rx, ry, rw, rh) in rects_from_cells(cells)]}
                       for (x, y, w, h), cells in zip(self.pillars, self.blocks)],
            "spawns": [{"x": x, "y": y} for (x, y) in self.spawns],
            "grid": ["".join(sym[c] for c in row) for row in self.grid],
        }

    def dump_json(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=1)
        return path


# ============================================================== Kacheln
def _walk(grid, x, y):
    if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
        return False
    return grid[y][x] in (FLOOR, GATE)


def wall_tile_coords(grid, x, y):
    """Atlas-Koordinate der Mauerkante an dieser Zelle.

    Der Tileset-Block bei Spalte 1..5 / Zeile 1..5 ist ein 3x3-Autotile:
    der Ring liefert die Kanten, der Kern den Boden. Welche Kante es ist,
    sagen die vier Nachbarn; bleibt keine uebrig, kommt die Innenecke ueber
    die Diagonale, und erst dann das Fuellstueck.
    """
    right = _walk(grid, x + 1, y)
    left = _walk(grid, x - 1, y)
    down = _walk(grid, x, y + 1)
    up = _walk(grid, x, y - 1)
    col = 1 if right else (5 if left else 3)
    row = 1 if down else (5 if up else 3)
    if col == 3 and row == 3:
        for (dx, dy, c, r) in ((-1, -1, 5, 5), (1, -1, 1, 5),
                               (-1, 1, 5, 1), (1, 1, 1, 1)):
            if _walk(grid, x + dx, y + dy):
                return (c, r)
        return FILL_TILE
    return (col, row)


def atlas_map(grid, seed=99):
    """(x, y) -> (Atlas-Spalte, Atlas-Zeile) fuer die ganze Karte.

    Einzige Quelle fuer die Tile-Auswahl: der Viewer zeichnet daraus, der
    Godot-Export baut daraus sein TileMapLayer. Zwei Implementierungen
    wuerden frueher oder spaeter auseinanderlaufen, und der Unterschied
    faellt erst in der Engine auf.
    """
    rng = random.Random(seed)
    out = {}
    for y in range(len(grid)):
        for x in range(len(grid[0])):
            cell = grid[y][x]
            if cell in (FLOOR, GATE):
                # Zwei Ziehungen pro Bodenzelle, Mauern ziehen nicht -
                # diese Reihenfolge ist Teil des Ergebnisses.
                c = 2 + rng.choice((0, 0, 0, 1, 2))
                r = 2 + rng.choice((0, 0, 0, 1, 2))
                out[(x, y)] = (c, r)
            elif cell == WALL:
                out[(x, y)] = wall_tile_coords(grid, x, y)
    return out


# ============================================================ Geometrie
def rects_from_cells(cells):
    """Zerlegt eine Zellmenge in moeglichst wenige Rechtecke.

    Ein L-Hindernis ist *nicht* seine Bounding-Box - die waere ein Viertel
    zu gross und die Hitbox wuerde nicht zur Grafik passen. Gierig von
    oben links: erst so weit nach rechts wie es geht, dann so weit nach
    unten, wie die volle Breite noch traegt.
    """
    remaining = set(cells)
    out = []
    while remaining:
        x0, y0 = min(remaining, key=lambda p: (p[1], p[0]))
        w = 1
        while (x0 + w, y0) in remaining:
            w += 1
        h = 1
        while all((x0 + i, y0 + h) in remaining for i in range(w)):
            h += 1
        for yy in range(y0, y0 + h):
            for xx in range(x0, x0 + w):
                remaining.discard((xx, yy))
        out.append((x0, y0, w, h))
    return out


def components(cells):
    """Zusammenhaengende Gruppen (4er-Nachbarschaft) einer Zellmenge."""
    todo = set(cells)
    out = []
    while todo:
        start = todo.pop()
        group = [start]
        stack = [start]
        while stack:
            x, y = stack.pop()
            for n in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if n in todo:
                    todo.discard(n)
                    group.append(n)
                    stack.append(n)
        out.append(group)
    return out


def _box(cells):
    xs = [x for x, _ in cells]
    ys = [y for _, y in cells]
    return (min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)


# ============================================================ Grundriss
def _base(bp, rng):
    """Boden, Aussenmauer, Safezone und Tor - der feste Teil jeder Art."""
    if not bp.has_safe:
        _base_abschnitt(bp)
        return
    g = bp.grid
    for y in range(bp.y0, bp.y1 + 1):
        for x in range(bp.x0, bp.x1 + 1):
            g[y][x] = FLOOR
    for x in range(bp.x0 - 1, bp.x1 + 2):
        g[bp.y0 - 1][x] = WALL
        g[bp.y1 + 1][x] = WALL
    for y in range(bp.y0 - 1, bp.y1 + 2):
        g[y][bp.x0 - 1] = WALL
        g[y][bp.x1 + 1] = WALL

    if bp.safe_size is None:
        breit = rng.randint(13, 17)
        hoch = rng.randint(11, 15)
        # Auch der Wurf muss in die Arena passen. Auf einer kleinen Karte
        # deckte der Startraum sonst das ganze Feld ab, und der Generator
        # rechnete anschliessend durch null.
        breit, hoch = clamp_startraum(breit, hoch,
                                      (bp.x1 - bp.x0 + 7,
                                       bp.y1 - bp.y0 + 7))
    else:
        # Feste Groesse: die beiden Wuerfe entfallen, damit verschiebt sich
        # der ganze Zufallsstrom. Derselbe Seed ergibt bei anderer
        # Startraumgroesse also eine andere Karte - das ist richtig so,
        # es ist eine andere Vorgabe.
        #
        # Gegen die Arena begrenzt, nicht bloss uebernommen: bei frei
        # eingegebenen Massen kann der Raum sonst groesser sein als die
        # Karte, und der Grundriss kippt.
        breit, hoch = clamp_startraum(bp.safe_size[0], bp.safe_size[1],
                                      (bp.x1 - bp.x0 + 1 + 6,
                                       bp.y1 - bp.y0 + 1 + 6))

    links = "links" in bp.safe_pos
    oben = bp.safe_pos.startswith("oben")

    if links:
        sx0 = bp.x0
        sx1 = sx0 + breit - 1
        gx = sx1 + 1                      # Tor an der rechten Wand
    else:
        sx1 = bp.x1
        sx0 = sx1 - breit + 1
        gx = sx0 - 1                      # Tor an der linken Wand
    if oben:
        sy0 = bp.y0
        sy1 = sy0 + hoch - 1
        trenn_y = sy1 + 1                 # Querwand unterhalb
        wand_von, wand_bis = bp.y0 - 1, sy1 + 1
    else:
        sy1 = bp.y1
        sy0 = sy1 - hoch + 1
        trenn_y = sy0 - 1                 # Querwand oberhalb
        wand_von, wand_bis = sy0 - 1, bp.y1 + 1

    # Der Rand haelt das Tor von den Ecken fern. Fest auf 3/4 gesetzt
    # verlangte er einen mindestens acht Zeilen hohen Raum - bei einem
    # kleinen Startraum ist dieser Abstand aber weder moeglich noch
    # noetig. Deshalb waechst er mit: hoechstens 3, mindestens 1, und
    # nie mehr als der Raum hergibt. Ab acht Zeilen ist er wieder 3,
    # dort aendert sich also nichts.
    rand = min(3, max(1, (hoch - 2) // 2))
    gy0 = rng.randint(sy0 + rand, max(sy0 + rand, sy1 - rand - 1))
    gy1 = gy0 + 1

    quer = range(bp.x0 - 1, gx + 1) if links else range(gx, bp.x1 + 2)
    for x in quer:
        g[trenn_y][x] = WALL
    for y in range(wand_von, wand_bis + 1):
        g[y][gx] = WALL
    for y in range(sy0, sy1 + 1):
        for x in range(sx0, sx1 + 1):
            g[y][x] = FLOOR
    for y in range(gy0, gy1 + 1):
        g[y][gx] = GATE

    bp.safe = (sx0, sy0, sx1, sy1)
    bp.gate = (gx, gy0, gy1)
    bp.safe_block = ((bp.x0 if links else gx), (bp.y0 if oben else trenn_y),
                     (gx if links else bp.x1), (trenn_y if oben else bp.y1))
    bp.origin = (gx + 2 if links else gx - 2, (gy0 + gy1) // 2)


def _base_abschnitt(bp):
    """Ein Abschnitt: nur Flaeche.

    Keine Aussenmauer, keine Safezone, kein Tor. Ohne Rand lassen sich
    zwei Abschnitte in Tiled aneinanderlegen - eine umlaufende Mauer waere
    genau die Naht, die dabei stoert.
    """
    for y in range(bp.y0, bp.y1 + 1):
        for x in range(bp.x0, bp.x1 + 1):
            bp.grid[y][x] = FLOOR
    bp.safe = (0, 0, -1, -1)
    bp.gate = (-1, -1, -1)
    bp.origin = ((bp.x0 + bp.x1) // 2, (bp.y0 + bp.y1) // 2)


def _field(bp):
    """Die Zellen, die eine Art gestalten darf: Arena ohne Safezone-Block."""
    if not bp.has_safe:
        return {(x, y) for y in range(bp.y0, bp.y1 + 1)
                for x in range(bp.x0, bp.x1 + 1)}
    bx0, by0, bx1, by1 = bp.safe_block
    out = set()
    for y in range(bp.y0, bp.y1 + 1):
        for x in range(bp.x0, bp.x1 + 1):
            if bx0 <= x <= bx1 and by0 <= y <= by1:
                continue
            out.add((x, y))
    return out


def _mark(near, x, y):
    h, w = len(near), len(near[0])
    for yy in range(max(0, y - MIN_GAP), min(h, y + MIN_GAP + 1)):
        row = near[yy]
        for xx in range(max(0, x - MIN_GAP), min(w, x + MIN_GAP + 1)):
            row[xx] = True


def _fields(bp, field):
    """`near` = zu dicht an einer Mauer, `keep` = darf nie zugebaut werden."""
    near = [[False] * bp.w for _ in range(bp.h)]
    keep = [[False] * bp.w for _ in range(bp.h)]
    keep_cells = []

    for y in range(bp.h):
        for x in range(bp.w):
            if bp.grid[y][x] == WALL:
                _mark(near, x, y)

    if not bp.has_safe:
        return near, keep, keep_cells
    gx, gy0, gy1 = bp.gate
    # Das Vorfeld liegt vor dem Tor, und das zeigt je nach Ecke nach
    # rechts oder nach links.
    if "links" in bp.safe_pos:
        spalten = range(gx, min(bp.x1, gx + GATE_CLEAR_X) + 1)
    else:
        spalten = range(max(bp.x0, gx - GATE_CLEAR_X), gx + 1)
    for y in range(max(bp.y0, gy0 - GATE_CLEAR_Y),
                   min(bp.y1, gy1 + GATE_CLEAR_Y) + 1):
        for x in spalten:
            if (x, y) in field:
                keep[y][x] = True
                keep_cells.append((x, y))
    return near, keep, keep_cells


# ======================================================== Arena-Arten
# Offene Flaeche, Hindernisse hinein. Eine Regel haelt alles begehbar:
# jedes Hindernis laesst MIN_GAP Tiles Luft zu jedem anderen und zur
# Aussenmauer - dann laeuft rundherum immer ein Weg.

def _normalise(cells):
    mx = min(x for x, _ in cells)
    my = min(y for _, y in cells)
    return sorted({(x - mx, y - my) for x, y in cells})


def _rotate(cells, times):
    for _ in range(times % 4):
        cells = [(-y, x) for (x, y) in cells]
    return _normalise(cells)


def _shape(rng):
    """Ein Hindernis als Liste von Tile-Offsets."""
    kind = rng.choices(("block", "balken", "ecke", "kreuz", "doppel"),
                       weights=(32, 22, 20, 12, 14))[0]

    if kind == "block":
        w, h = rng.randint(2, 4), rng.randint(2, 4)
        return [(x, y) for y in range(h) for x in range(w)]

    if kind == "balken":
        n, t = rng.randint(4, 7), rng.choice((1, 2))
        if rng.random() < 0.5:
            return [(x, y) for y in range(t) for x in range(n)]
        return [(x, y) for y in range(n) for x in range(t)]

    if kind == "ecke":
        a, b = rng.randint(3, 5), rng.randint(3, 5)
        cells = [(x, 0) for x in range(a)] + [(0, y) for y in range(1, b)]
        return _rotate(cells, rng.randint(0, 3))

    if kind == "kreuz":
        r = rng.randint(1, 2)
        cells = [(r, y) for y in range(2 * r + 1)]
        cells += [(x, r) for x in range(2 * r + 1)]
        return _normalise(cells)

    # doppel: zwei Bloecke mit zwei Tiles Schlitz. Der Schlitz unterschreitet
    # MIN_GAP absichtlich - das ist die Stelle, durch die man sich quetscht.
    # Zulaessig, weil er innerhalb *einer* Form entsteht und damit gewollt ist.
    w, h = rng.randint(2, 3), rng.randint(2, 3)
    cells = [(x, y) for y in range(h) for x in range(w)]
    if rng.random() < 0.5:
        cells += [(x + w + 2, y) for y in range(h) for x in range(w)]
    else:
        cells += [(x, y + h + 2) for y in range(h) for x in range(w)]
    return _normalise(cells)


def _stamp(bp, field, near, keep, cells, ox, oy):
    """Setzt eine Form, wenn sie passt."""
    put = []
    for (dx, dy) in cells:
        x, y = ox + dx, oy + dy
        if (x, y) not in field or keep[y][x] or near[y][x]:
            return False
        if bp.grid[y][x] != FLOOR:
            return False
        put.append((x, y))
    for (x, y) in put:
        bp.grid[y][x] = WALL
        _mark(near, x, y)
    return True


def _scatter(bp, rng, field, keep, near, arrangement):
    # Anzahl mit der Flaeche. Feste 16..26 Hindernisse sind auf der
    # Vorgabekarte richtig und auf einer 100x80 ein paar Kruemel - dort
    # kam 99 Prozent offen heraus und jede Karte fiel durch die Pruefung.
    target = _skal(rng.randint(16, 26), bp.farea, 6)
    placed = 0
    tries = 0
    while placed < target and tries < 1200:
        tries += 1
        cells = _shape(rng)
        w = max(x for x, _ in cells) + 1
        h = max(y for _, y in cells) + 1

        if arrangement == "ringe":
            cx = (bp.x0 + bp.x1) / 2.0
            cy = (bp.y0 + bp.y1) / 2.0
            ring = rng.choice((0.32, 0.55, 0.80))
            ang = rng.uniform(0.0, 2.0 * math.pi)
            ox = int(round(cx + math.cos(ang) * ring
                           * (bp.x1 - bp.x0) / 2.0 - w / 2.0))
            oy = int(round(cy + math.sin(ang) * ring
                           * (bp.y1 - bp.y0) / 2.0 - h / 2.0))
        else:
            ox = rng.randint(bp.x0, bp.x1 - w + 1)
            oy = rng.randint(bp.y0, bp.y1 - h + 1)

        if not _stamp(bp, field, near, keep, cells, ox, oy):
            continue
        placed += 1

        if arrangement == "gespiegelt":
            # Punktspiegelung an der Arenamitte. Die Bounding-Box bleibt
            # gleich gross, also verschiebt sich nur der Ursprung.
            mirror = _normalise([(w - 1 - x, h - 1 - y) for x, y in cells])
            mox = bp.x0 + bp.x1 - (ox + w - 1)
            moy = bp.y0 + bp.y1 - (oy + h - 1)
            if _stamp(bp, field, near, keep, mirror, mox, moy):
                placed += 1


def _carve_streu(bp, rng, field, keep, near):
    _scatter(bp, rng, field, keep, near, "streu")


def _carve_gespiegelt(bp, rng, field, keep, near):
    _scatter(bp, rng, field, keep, near, "gespiegelt")


def _carve_ringe(bp, rng, field, keep, near):
    _scatter(bp, rng, field, keep, near, "ringe")


def _carve_saeulen(bp, rng, field, keep, near):
    """Regelmaessiges Saeulenraster - die klassische Arena.

    Kein Zufall in der Anordnung, nur in den Massen: gleichmaessige
    Deckung liest sich als gebaut und nicht als hingewuerfelt, und man
    lernt sie im Lauf einer Runde.
    """
    pw, ph = rng.choice((2, 3)), rng.choice((2, 3))
    gap_x = rng.randint(4, 6)
    gap_y = rng.randint(4, 6)
    ox = bp.x0 + rng.randint(0, gap_x)
    oy = bp.y0 + rng.randint(0, gap_y)
    cells = [(x, y) for y in range(ph) for x in range(pw)]
    y = oy
    while y <= bp.y1 - ph + 1:
        x = ox
        while x <= bp.x1 - pw + 1:
            _stamp(bp, field, near, keep, cells, x, y)
            x += pw + gap_x
        y += ph + gap_y


def _carve_sektoren(bp, rng, field, keep, near):
    """Lange Trennwaende mit Durchgaengen - offene Flaeche, klare Linien."""
    # Die Waende reichen nie ganz bis an die Aussenmauer: an beiden Enden
    # bleiben ein paar Tiles frei. Sonst teilt eine einzige Wand die Arena
    # wirklich in zwei Haelften, und wenn die Durchgaenge ungluecklich
    # fallen, mauert die Reparatur eine davon komplett zu - aus einem
    # Drittel der Karte wird Fels.
    # Mit der Kantenlaenge, nicht mit der Flaeche: jede Trennwand ist so
    # lang wie die Karte. Ueber die Flaeche skaliert wuchs die Wandflaeche
    # mit Flaeche hoch 1,5 - bei 250x200 blieben 17 Prozent offen.
    for _ in range(_skal(rng.randint(3, 5), bp.flin, 2)):
        margin = rng.randint(2, 4)
        if rng.random() < 0.5:
            y = rng.randint(bp.y0 + 5, bp.y1 - 5)
            run = [(x, y) for x in range(bp.x0 + margin,
                                         bp.x1 - margin + 1)]
        else:
            x = rng.randint(bp.x0 + 5, bp.x1 - 5)
            run = [(x, y) for y in range(bp.y0 + margin,
                                         bp.y1 - margin + 1)]
        run = [p for p in run if p in field and not keep[p[1]][p[0]]]
        if len(run) < 12:
            continue
        # Zwei bis drei Durchgaenge, nie am aeussersten Ende: eine Wand,
        # die genau am Rand endet, ist keine Wand, sondern ein Umweg.
        gaps = set()
        for _ in range(rng.randint(2, 3)):
            centre = rng.randint(3, len(run) - 4)
            for d in range(-1, rng.randint(1, 2) + 1):
                gaps.add(centre + d)
        for i, (x, y) in enumerate(run):
            if i not in gaps and bp.grid[y][x] == FLOOR:
                bp.grid[y][x] = WALL


# ======================================================= Dungeon-Arten
# Alles Mauer, dann Raeume und Gaenge hinein.

def _fill(bp, field, value):
    for (x, y) in field:
        bp.grid[y][x] = value


def _carve_rect(bp, field, keep, x0, y0, w, h):
    out = 0
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            if (x, y) in field:
                bp.grid[y][x] = FLOOR
                out += 1
    return out


def _carve_line(bp, field, x0, y0, x1, y1, width=1):
    """Waagerechtes oder senkrechtes Stueck Gang, `width` Tiles breit."""
    half = (width - 1) // 2
    if y0 == y1:
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for d in range(-half, width - half):
                if (x, y0 + d) in field:
                    bp.grid[y0 + d][x] = FLOOR
    else:
        for y in range(min(y0, y1), max(y0, y1) + 1):
            for d in range(-half, width - half):
                if (x0 + d, y) in field:
                    bp.grid[y][x0 + d] = FLOOR


def _outside(field, cells):
    return sum(1 for p in cells if p not in field)


def _corridor(bp, field, rng, a, b, width=1):
    """L-foermiger Gang zwischen zwei Punkten.

    Der Knick geht nicht blind in eine Richtung: die Safezone ist ein
    Block mitten im Feld, und ein Gang, der durch sie hindurch soll, wird
    dort nicht gegraben - die Verbindung reisst, und die Reparatur macht
    aus dem abgehaengten Raum Fels. Also beide Varianten durchzaehlen und
    die nehmen, die weniger im Nichts liegt; bei Gleichstand entscheidet
    der Zufall wie vorher.
    """
    (ax, ay), (bx, by) = a, b
    weg1 = ([(x, ay) for x in range(min(ax, bx), max(ax, bx) + 1)]
            + [(bx, y) for y in range(min(ay, by), max(ay, by) + 1)])
    weg2 = ([(ax, y) for y in range(min(ay, by), max(ay, by) + 1)]
            + [(x, by) for x in range(min(ax, bx), max(ax, bx) + 1)])
    n1, n2 = _outside(field, weg1), _outside(field, weg2)
    erst_waagerecht = n1 < n2 if n1 != n2 else rng.random() < 0.5

    if erst_waagerecht:
        _carve_line(bp, field, ax, ay, bx, ay, width)
        _carve_line(bp, field, bx, ay, bx, by, width)
    else:
        _carve_line(bp, field, ax, ay, ax, by, width)
        _carve_line(bp, field, ax, by, bx, by, width)


def _grid_edges(rng, cols, rows, extra=0.0, allowed=None):
    """Spannbaum ueber ein cols x rows Raster, plus `extra` Anteil Zusatzkanten.

    Der Baum garantiert, dass jede Zelle erreichbar ist; die Zusatzkanten
    nehmen dem Ergebnis den Baumcharakter. Ohne sie gaebe es zwischen zwei
    Zimmern genau einen Weg, und jede Begegnung waere eine Sackgasse.

    `allowed` schraenkt auf tatsaechlich vorhandene Zellen ein. Das ist
    kein Feinschliff: die Safezone belegt eine Ecke des Rasters, dort
    entsteht gar kein Zimmer, und ein Baum ueber das volle Raster haengt
    echte Zimmer an solche Phantome. Die Tuer dorthin wird nie gegraben,
    und das Zimmer ist ab.
    """
    cells = [(c, r) for r in range(rows) for c in range(cols)
             if allowed is None or (c, r) in allowed]
    if not cells:
        return []
    pool = set(cells)
    start = rng.choice(cells)
    seen = {start}
    stack = [start]
    edges = []
    while stack:
        c, r = stack[-1]
        nbrs = [(c + dc, r + dr) for (dc, dr) in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if (c + dc, r + dr) in pool and (c + dc, r + dr) not in seen]
        if not nbrs:
            stack.pop()
            continue
        n = rng.choice(nbrs)
        edges.append(((c, r), n))
        seen.add(n)
        stack.append(n)

    if extra > 0:
        allpairs = []
        for (c, r) in cells:
            for (dc, dr) in ((1, 0), (0, 1)):
                n = (c + dc, r + dr)
                if n in pool:
                    allpairs.append(((c, r), n))
        have = {frozenset(e) for e in edges}
        rest = [e for e in allpairs if frozenset(e) not in have]
        rng.shuffle(rest)
        edges += rest[:int(len(rest) * extra)]
    return edges


def _skal(wert, faktor, minimum=1):
    """Eine Anzahl oder Laenge auf die Flaeche umrechnen.

    Bei voller Arena ist der Faktor 1,0 und der Wert kommt unveraendert
    zurueck - deshalb aendert die Skalierung an den grossen Karten nichts.
    """
    return max(minimum, int(round(wert * faktor)))


def _fit(lo, hi, span):
    """Groessenbereich auf das begrenzen, was tatsaechlich Platz hat.

    Begrenzen, nicht umrechnen: fuer die grosse Arena sind alle Bereiche
    ohnehin kleiner als die Flaeche, dort aendert das nichts. Nur im
    kleinen Abschnitt greift die Grenze - vorher stand dort ein leerer
    randrange und der Aufruf brach ab.
    """
    hi = min(hi, span)
    lo = min(lo, hi)
    return max(1, lo), max(1, hi)


def _bsp_tiefe(bp):
    """Wie oft geteilt wird. Mehr Flaeche, mehr Raeume - sonst werden die
    Raeume auf einer grossen Karte riesig statt zahlreich."""
    tiefe = 5
    while tiefe < 9 and bp.farea >= 2 ** (tiefe - 4):
        tiefe += 1
    return tiefe


def _bsp(rng, rect, min_w, min_h, depth):
    x, y, w, h = rect
    can_v = w >= min_w * 2 + 1
    can_h = h >= min_h * 2 + 1
    if depth <= 0 or not (can_v or can_h):
        return [rect]
    horizontal = rng.random() < 0.5 if (can_v and can_h) else can_h
    if horizontal:
        cut = rng.randint(min_h, h - min_h)
        parts = ((x, y, w, cut), (x, y + cut, w, h - cut))
    else:
        cut = rng.randint(min_w, w - min_w)
        parts = ((x, y, cut, h), (x + cut, y, w - cut, h))
    out = []
    for p in parts:
        out += _bsp(rng, p, min_w, min_h, depth - 1)
    return out


def _anchor(field, room):
    """Ein Punkt des Raums, der wirklich im Feld liegt.

    Der geometrische Mittelpunkt taugt dafuer nicht. Die Safezone ist ein
    Block mitten im Grundriss; faellt der Mittelpunkt hinein, beginnt
    jeder Gang von dort im Nichts, der Raum haengt ab und wird von der
    Reparatur zu Fels. Deshalb der naechstgelegene Punkt, den es gibt.
    """
    x, y, w, h = room
    cx, cy = x + w // 2, y + h // 2
    if (cx, cy) in field:
        return (cx, cy)
    best, best_d = None, None
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            if (xx, yy) in field:
                d = (xx - cx) ** 2 + (yy - cy) ** 2
                if best_d is None or d < best_d:
                    best, best_d = (xx, yy), d
    return best


def _rooms_connect(bp, field, rng, rooms, width):
    """Nachbarn verbinden, plus ein paar Querverbindungen.

    Nur die Kette zu verbinden gaebe einen Baum: genau ein Weg zwischen
    zwei Raeumen, und jede Begegnung wird zur Sackgasse. Ein paar Kanten
    mehr, und man kann um den Gegner herum statt nur vor ihm weg.
    """
    centres = [a for a in (_anchor(field, r) for r in rooms) if a is not None]
    if len(centres) < 2:
        return
    for i in range(1, len(centres)):
        _corridor(bp, field, rng, centres[i - 1], centres[i], width)
    for _ in range(max(1, len(centres) // 4)):
        a, b = rng.sample(range(len(centres)), 2)
        _corridor(bp, field, rng, centres[a], centres[b], width)


def _carve_raeume(bp, rng, field, keep, near):
    """Klassischer Dungeon: BSP-Raeume, mit Gaengen verbunden."""
    _fill(bp, field, WALL)
    leaves = _bsp(rng, (bp.x0, bp.y0,
                        bp.x1 - bp.x0 + 1, bp.y1 - bp.y0 + 1),
                  rng.randint(8, 11), rng.randint(7, 9), _bsp_tiefe(bp))
    rooms = []
    for (x, y, w, h) in leaves:
        rw = rng.randint(max(3, w - 6), max(4, w - 2))
        rh = rng.randint(max(3, h - 5), max(4, h - 2))
        rx = x + rng.randint(1, max(1, w - rw - 1))
        ry = y + rng.randint(1, max(1, h - rh - 1))
        if _carve_rect(bp, field, keep, rx, ry, rw, rh) > 0:
            rooms.append((rx, ry, rw, rh))
    if rooms:
        rng.shuffle(rooms)
        _rooms_connect(bp, field, rng, rooms, rng.choice((1, 2)))


def _carve_zellen(bp, rng, field, keep, near):
    """Raster aus Zimmern mit Tueren - gebaut, nicht gewachsen."""
    _fill(bp, field, WALL)
    # Erst die Anzahl waehlen, dann die Grenzen daraus rechnen. Andersherum
    # - feste Zimmergroesse, Spaltenzahl per Ganzzahldivision - bleibt
    # rechts und unten ein Rest stehen, den nie jemand betritt.
    cols = _skal(rng.randint(4, 6), bp.fx, 2)
    rows = _skal(rng.randint(3, 5), bp.fy, 2)
    span_x = bp.x1 - bp.x0 + 1
    span_y = bp.y1 - bp.y0 + 1
    xs = [bp.x0 + span_x * i // cols for i in range(cols + 1)]
    ys = [bp.y0 + span_y * i // rows for i in range(rows + 1)]

    real = set()
    for r in range(rows):
        for c in range(cols):
            x0, x1 = xs[c], xs[c + 1] - 1
            y0, y1 = ys[r], ys[r + 1] - 1
            if _carve_rect(bp, field, keep, x0 + 1, y0 + 1,
                           x1 - x0 - 1, y1 - y0 - 1) > 0:
                real.add((c, r))

    # Tueren entlang eines Spannbaums ueber das Zimmerraster, plus ein
    # paar zusaetzliche. Jede Tuer einzeln auszuwuerfeln waere einfacher,
    # aber dann bleibt irgendwann ein Eckzimmer ohne Tuer - und ein
    # unerreichbares Zimmer ist nach der Reparatur ein Klotz Fels.
    for (a, b) in _grid_edges(rng, cols, rows, extra=0.25, allowed=real):
        (ca, ra), (cb, rb) = a, b
        if ca == cb:                       # Tuer nach unten
            y = ys[max(ra, rb)]
            x0, x1 = xs[ca], xs[ca + 1] - 1
            lo, hi = min(x0 + 2, x1 - 1), max(x0 + 2, x1 - 2)
            dx = rng.randint(min(lo, hi), max(lo, hi))
            _carve_line(bp, field, dx, y - 1, dx, y + 1, rng.choice((1, 2)))
        else:                              # Tuer nach rechts
            x = xs[max(ca, cb)]
            y0, y1 = ys[ra], ys[ra + 1] - 1
            lo, hi = min(y0 + 2, y1 - 1), max(y0 + 2, y1 - 2)
            dy = rng.randint(min(lo, hi), max(lo, hi))
            _carve_line(bp, field, x - 1, dy, x + 1, dy, rng.choice((1, 2)))


def _carve_kammern(bp, rng, field, keep, near):
    """Wenige grosse Hallen, breit verbunden - Platz zum Ausweichen."""
    _fill(bp, field, WALL)
    w_lo, w_hi = _fit(9, 16, bp.x1 - bp.x0 + 1)
    h_lo, h_hi = _fit(7, 13, bp.y1 - bp.y0 + 1)
    rooms = []
    for _ in range(_skal(rng.randint(5, 8), bp.farea, 3)):
        for _try in range(40):
            w = rng.randint(w_lo, w_hi)
            h = rng.randint(h_lo, h_hi)
            x = rng.randint(bp.x0, bp.x1 - w + 1)
            y = rng.randint(bp.y0, bp.y1 - h + 1)
            if any(x < rx + rw + 2 and rx < x + w + 2
                   and y < ry + rh + 2 and ry < y + h + 2
                   for (rx, ry, rw, rh) in rooms):
                continue
            if _carve_rect(bp, field, keep, x, y, w, h) > 0:
                rooms.append((x, y, w, h))
            break
    if rooms:
        _rooms_connect(bp, field, rng, rooms, rng.choice((3, 4)))


# ===================================================== Organische Arten

def _neighbour_walls(bp, field, x, y):
    """Mauern im 3x3 herum. Was ausserhalb des Feldes liegt, zaehlt als Mauer -
    sonst frisst sich die Hoehle in die Aussenmauer und in die Safezone."""
    n = 0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            p = (x + dx, y + dy)
            if p not in field or bp.grid[p[1]][p[0]] == WALL:
                n += 1
    return n


def _smooth(bp, field, rounds):
    """Die 4-5-Regel.

    Eine einzige Schwelle fuer alle Zellen waere falsch: bei 45 Prozent
    Startdichte hat eine Zelle im Schnitt 3,7 Mauernachbarn, also faellt
    sie unter jede Schwelle von 5 - und die Hoehle waere nach zwei Runden
    ein leerer Saal. Bestehende Mauer haelt sich schon bei 4 Nachbarn,
    neue entsteht erst bei 5. Damit bleibt die Dichte ungefaehr, wo sie
    angefangen hat, und geglaettet wird trotzdem.
    """
    for _ in range(rounds):
        nxt = {}
        for (x, y) in field:
            n = _neighbour_walls(bp, field, x, y)
            if bp.grid[y][x] == WALL:
                nxt[(x, y)] = WALL if n >= 4 else FLOOR
            else:
                nxt[(x, y)] = WALL if n >= 5 else FLOOR
        for (x, y), v in nxt.items():
            bp.grid[y][x] = v


def _carve_hoehle(bp, rng, field, keep, near):
    """Zellulaerer Automat - unregelmaessige Kammern und Engstellen."""
    density = rng.uniform(0.44, 0.49)
    for (x, y) in field:
        bp.grid[y][x] = WALL if rng.random() < density else FLOOR
    _smooth(bp, field, rng.randint(4, 5))


def _carve_see(bp, rng, field, keep, near):
    """Dieselbe Mechanik, duenner gesaet - eine grosse offene Hoehle."""
    density = rng.uniform(0.36, 0.41)
    for (x, y) in field:
        bp.grid[y][x] = WALL if rng.random() < density else FLOOR
    _smooth(bp, field, rng.randint(5, 6))


def _carve_adern(bp, rng, field, keep, near):
    """Betrunkener Wanderer - gewundene Gaenge, die sich kreuzen.

    Zwei Dinge machen den Unterschied. Erstens genug Schritte: ein
    Zufallsweg laeuft staendig ueber sich selbst, ein Schritt pro Zelle
    graebt darum nur ein Fuenftel frei. Zweitens starten alle weiteren
    Wanderer auf schon Gegrabenem - sonst legt jeder sein eigenes,
    unerreichbares Gangnetz an, und die Reparatur mauert es wieder zu.
    """
    _fill(bp, field, WALL)
    carved = []
    walkers = rng.randint(3, 6)
    steps = int(len(field) * rng.uniform(1.6, 2.6)) // walkers
    for w in range(walkers):
        if w == 0 or not carved:
            x, y = bp.origin
        else:
            x, y = rng.choice(carved)
        brush = rng.choice((1, 1, 2))
        for _ in range(steps):
            for dy in range(brush):
                for dx in range(brush):
                    p = (x + dx, y + dy)
                    if p in field and bp.grid[p[1]][p[0]] != FLOOR:
                        bp.grid[p[1]][p[0]] = FLOOR
                        carved.append(p)
            dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
            x = max(bp.x0, min(bp.x1, x + dx))
            y = max(bp.y0, min(bp.y1, y + dy))


def _carve_inseln(bp, rng, field, keep, near):
    """Offene Flaeche mit gewachsenen Bloecken statt gesetzter Formen."""
    for _ in range(_skal(rng.randint(16, 24), bp.farea, 2)):
        cx, cy = rng.choice(sorted(field))
        size = _skal(rng.randint(14, 45), bp.flin, 4)
        x, y = cx, cy
        for _ in range(size):
            if (x, y) in field and not keep[y][x]:
                bp.grid[y][x] = WALL
            dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
            x = max(bp.x0, min(bp.x1, x + dx))
            y = max(bp.y0, min(bp.y1, y + dy))


# ==================================================== Labyrinth-Arten

def _maze(bp, rng, field, keep):
    """Rekursiver Backtracker auf dem ungeraden Gitter."""
    _fill(bp, field, WALL)
    # Startzellen auf ungeraden Koordinaten relativ zur Arenaecke, damit
    # zwischen zwei Gangzellen immer genau eine Mauer Platz hat.
    def ok(x, y):
        return (x, y) in field
    starts = [(x, y)
              for y in range(bp.y0, bp.y1 + 1, 2)
              for x in range(bp.x0, bp.x1 + 1, 2) if ok(x, y)]
    if not starts:
        return
    start = rng.choice(starts)
    bp.grid[start[1]][start[0]] = FLOOR
    stack = [start]
    seen = {start}
    while stack:
        x, y = stack[-1]
        nbrs = []
        for (dx, dy) in ((2, 0), (-2, 0), (0, 2), (0, -2)):
            n = (x + dx, y + dy)
            if n in seen or not ok(*n):
                continue
            nbrs.append((n, (x + dx // 2, y + dy // 2)))
        if not nbrs:
            stack.pop()
            continue
        n, between = rng.choice(nbrs)
        bp.grid[between[1]][between[0]] = FLOOR
        bp.grid[n[1]][n[0]] = FLOOR
        seen.add(n)
        stack.append(n)


def _ring_corridor(bp, field):
    """Ein Gang rundum innen an der Aussenmauer.

    Ohne ihn ist ein Labyrinth in diesem Grundriss haesslich: die Safezone
    sitzt in einer Ecke und schneidet Aeste ab, die dann zugemauert werden.
    Mit ihm haengt alles zusammen, und man kann aussen herumlaufen statt
    nur hinein.
    """
    for x in range(bp.x0, bp.x1 + 1):
        for y in (bp.y0, bp.y1):
            if (x, y) in field:
                bp.grid[y][x] = FLOOR
    for y in range(bp.y0, bp.y1 + 1):
        for x in (bp.x0, bp.x1):
            if (x, y) in field:
                bp.grid[y][x] = FLOOR


def _carve_labyrinth(bp, rng, field, keep, near):
    _maze(bp, rng, field, keep)
    _ring_corridor(bp, field)


def _carve_schleifen(bp, rng, field, keep, near):
    """Labyrinth, dann Sackgassen aufbrechen - Wege statt Fallen."""
    _maze(bp, rng, field, keep)
    _ring_corridor(bp, field)
    for _ in range(2):
        dead = []
        for (x, y) in field:
            if bp.grid[y][x] != FLOOR:
                continue
            open_n = sum(1 for n in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
                         if bp.walkable(*n))
            if open_n == 1:
                dead.append((x, y))
        for (x, y) in dead:
            walls = [n for n in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
                     if n in field and bp.grid[n[1]][n[0]] == WALL]
            if walls and rng.random() < 0.75:
                wx, wy = rng.choice(walls)
                bp.grid[wy][wx] = FLOOR


def _carve_hallen(bp, rng, field, keep, near):
    """Labyrinth mit weiten Gaengen - Dungeon-Optik, Arena-Bewegung."""
    _fill(bp, field, WALL)
    step = 4
    cells = [(x, y)
             for y in range(bp.y0, bp.y1 - 1, step)
             for x in range(bp.x0, bp.x1 - 1, step) if (x, y) in field]
    if not cells:
        return
    seen = {cells[0]}
    stack = [cells[0]]
    pool = set(cells)
    _carve_rect(bp, field, keep, cells[0][0], cells[0][1], 3, 3)
    while stack:
        x, y = stack[-1]
        nbrs = [(x + dx, y + dy) for (dx, dy)
                in ((step, 0), (-step, 0), (0, step), (0, -step))
                if (x + dx, y + dy) in pool and (x + dx, y + dy) not in seen]
        if not nbrs:
            stack.pop()
            continue
        n = rng.choice(nbrs)
        _carve_rect(bp, field, keep, n[0], n[1], 3, 3)
        _carve_line(bp, field, x + 1, y + 1, n[0] + 1, n[1] + 1, 3)
        seen.add(n)
        stack.append(n)


# ==================================================== Weitere Bauformen

def _set_wall(bp, field, keep, x, y):
    if (x, y) in field and not keep[y][x]:
        bp.grid[y][x] = WALL


def _carve_rotunde(bp, rng, field, keep, near):
    """Konzentrische Ringmauern mit versetzten Durchgaengen."""
    cx = (bp.x0 + bp.x1) / 2.0
    cy = (bp.y0 + bp.y1) / 2.0
    # Mehr Ringe auf groesserer Flaeche - sonst liegen sie immer weiter
    # auseinander und die Karte wird nach aussen hin leer.
    rings = _skal(rng.randint(3, 4), bp.flin, 2)
    for k in range(1, rings + 1):
        f = k / float(rings)
        rx = f * (bp.x1 - bp.x0) / 2.0 * 0.92
        ry = f * (bp.y1 - bp.y0) / 2.0 * 0.92
        if rx < 3 or ry < 3:
            continue
        gaps = [rng.uniform(0.0, 2.0 * math.pi) for _ in range(rng.randint(2, 3))]
        scale = min(rx, ry)
        for (x, y) in field:
            d = math.hypot((x - cx) / rx, (y - cy) / ry)
            if abs(d - 1.0) * scale > 0.7:
                continue
            ang = math.atan2(y - cy, x - cx) % (2.0 * math.pi)
            # Luecken als Winkelfenster - am aeusseren Ring deckt derselbe
            # Winkel mehr Tiles ab als am inneren, also waechst das Tor
            # nach aussen mit. Genau so soll es aussehen.
            if any(abs(((ang - g + math.pi) % (2.0 * math.pi)) - math.pi) < 0.28
                   for g in gaps):
                continue
            _set_wall(bp, field, keep, x, y)


def _carve_diagonal(bp, rng, field, keep, near):
    """Schraege Balken - die einzige Art, die nicht am Raster klebt."""
    for _ in range(_skal(rng.randint(8, 13), bp.farea, 3)):
        x = rng.randint(bp.x0, bp.x1)
        y = rng.randint(bp.y0, bp.y1)
        sx, sy = rng.choice((1, -1)), rng.choice((1, -1))
        length = _skal(rng.randint(6, 15), bp.flin, 3)
        thick = rng.choice((1, 1, 2))
        for i in range(length):
            for t in range(thick):
                _set_wall(bp, field, keep, x + i * sx, y + i * sy + t)


def _carve_stadt(bp, rng, field, keep, near):
    """Haeuserblocks mit Strassen dazwischen.

    Die Blocks sind massiv - man geht nicht hinein, man geht darum herum.
    Die Strassen sind per Konstruktion durchgehend, also kann hier nichts
    abgeschnitten werden.
    """
    street = rng.randint(3, 4)
    bw, bh = rng.randint(6, 10), rng.randint(5, 8)
    y = bp.y0 + rng.randint(0, street)
    while y <= bp.y1:
        x = bp.x0 + rng.randint(0, street)
        while x <= bp.x1:
            w = min(bw, bp.x1 - x + 1)
            h = min(bh, bp.y1 - y + 1)
            if w >= 3 and h >= 3:
                for yy in range(y, y + h):
                    for xx in range(x, x + w):
                        _set_wall(bp, field, keep, xx, yy)
            x += bw + street
        y += bh + street


def _carve_festung(bp, rng, field, keep, near):
    """Verschachtelte Ringmauern mit Toren auf wechselnden Seiten."""
    rings = rng.randint(2, 3)
    step_x = max(3, (bp.x1 - bp.x0) // (2 * (rings + 1)))
    step_y = max(3, (bp.y1 - bp.y0) // (2 * (rings + 1)))
    for k in range(1, rings + 1):
        x0, x1 = bp.x0 + k * step_x, bp.x1 - k * step_x
        y0, y1 = bp.y0 + k * step_y, bp.y1 - k * step_y
        if x1 - x0 < 7 or y1 - y0 < 7:
            break
        sides = {
            "n": [(x, y0) for x in range(x0, x1 + 1)],
            "s": [(x, y1) for x in range(x0, x1 + 1)],
            "w": [(x0, y) for y in range(y0, y1 + 1)],
            "o": [(x1, y) for y in range(y0, y1 + 1)],
        }
        offen = rng.sample(sorted(sides), 2)
        for name, run in sides.items():
            gap = set()
            if name in offen and len(run) > 9:
                c = rng.randint(3, len(run) - 4)
                gap = {c - 1, c, c + 1}
            for i, (x, y) in enumerate(run):
                if i not in gap:
                    _set_wall(bp, field, keep, x, y)


def _carve_katakomben(bp, rng, field, keep, near):
    """Viele kleine Kammern, enge Gaenge - dicht und unuebersichtlich."""
    _fill(bp, field, WALL)
    w_lo, w_hi = _fit(3, 6, bp.x1 - bp.x0 + 1)
    h_lo, h_hi = _fit(3, 5, bp.y1 - bp.y0 + 1)
    rooms = []
    for _ in range(_skal(rng.randint(20, 30), bp.farea, 8)):
        for _try in range(30):
            w, h = rng.randint(w_lo, w_hi), rng.randint(h_lo, h_hi)
            x = rng.randint(bp.x0, bp.x1 - w + 1)
            y = rng.randint(bp.y0, bp.y1 - h + 1)
            if any(x < rx + rw + 2 and rx < x + w + 2
                   and y < ry + rh + 2 and ry < y + h + 2
                   for (rx, ry, rw, rh) in rooms):
                continue
            if _carve_rect(bp, field, keep, x, y, w, h) > 0:
                rooms.append((x, y, w, h))
            break
    if rooms:
        rng.shuffle(rooms)
        _rooms_connect(bp, field, rng, rooms, 1)


def _carve_tempel(bp, rng, field, keep, near):
    """Achsensymmetrischer Grundriss um eine Mittelhalle.

    Symmetrie an der Senkrechten, nicht am Punkt: das liest sich als
    gebaut. Die Safezone bricht sie oben links - was dort haette
    entstehen sollen, faellt weg, der Spiegel rechts bleibt.
    """
    _fill(bp, field, WALL)
    mid = (bp.x0 + bp.x1) // 2
    hall_lo, hall_hi = _fit(4, 7, bp.x1 - bp.x0 + 1)
    hall = rng.randint(hall_lo, hall_hi)
    _carve_rect(bp, field, keep, mid - hall // 2, bp.y0 + 1,
                hall, bp.y1 - bp.y0 - 1)
    tw_lo, tw_hi = _fit(6, 11, bp.x1 - bp.x0 + 1)
    th_lo, th_hi = _fit(5, 9, bp.y1 - bp.y0 + 1)
    for _ in range(_skal(rng.randint(4, 6), bp.farea, 3)):
        w, h = rng.randint(tw_lo, tw_hi), rng.randint(th_lo, th_hi)
        hi = mid - hall // 2 - w - 1
        if hi <= bp.x0:
            continue
        x = rng.randint(bp.x0, hi)
        y = rng.randint(bp.y0, bp.y1 - h + 1)
        mx = bp.x0 + bp.x1 - (x + w - 1)
        for rx in (x, mx):
            _carve_rect(bp, field, keep, rx, y, w, h)
            _carve_line(bp, field, rx + w // 2, y + h // 2, mid, y + h // 2, 1)


def _carve_risse(bp, rng, field, keep, near):
    """Bruchlinien: Mauer dort, wo zwei Bereiche gleich weit weg sind."""
    cells = sorted(field)
    seeds = [rng.choice(cells)
             for _ in range(_skal(rng.randint(10, 16), bp.farea, 5))]

    region = {}
    riss = []
    for (x, y) in cells:
        d1 = d2 = 10 ** 9
        best = 0
        for i, (sx, sy) in enumerate(seeds):
            d = (x - sx) ** 2 + (y - sy) ** 2
            if d < d1:
                d1, d2, best = d, d1, i
            elif d < d2:
                d2 = d
        region[(x, y)] = best
        if math.sqrt(d2) - math.sqrt(d1) < 1.1:
            riss.append((x, y))

    for (x, y) in riss:
        _set_wall(bp, field, keep, x, y)

    # Ein Durchbruch je Nachbarschaft, nicht ein paar zufaellige.
    # Zufaellige Loecher trafen meist dieselbe Linie doppelt und andere
    # gar nicht - im Schnitt blieb die halbe Karte abgehaengt und wurde
    # zu Fels. Ueber die Nachbarschaften ist jede Scholle erreichbar,
    # weil ein Voronoi-Nachbarschaftsgraph zusammenhaengend ist.
    paare = {}
    for (x, y) in riss:
        ids = {region[n] for n in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
               if n in region}
        if len(ids) >= 2:
            paare.setdefault(tuple(sorted(ids)[:2]), []).append((x, y))
    for stellen in paare.values():
        cx, cy = rng.choice(stellen)
        for yy in range(cy - 1, cy + 2):
            for xx in range(cx - 1, cx + 2):
                if (xx, yy) in field:
                    bp.grid[yy][xx] = FLOOR


def _carve_krater(bp, rng, field, keep, near):
    """Runde Lichtungen im Fels, breit verbunden."""
    _fill(bp, field, WALL)
    kurz = min(bp.x1 - bp.x0 + 1, bp.y1 - bp.y0 + 1)
    r_lo, r_hi = _fit(4, 8, max(1, (kurz - 1) // 2))
    centres = []
    for _ in range(_skal(rng.randint(5, 8), bp.farea, 3)):
        r = rng.randint(r_lo, r_hi)
        for _try in range(30):
            cx = rng.randint(bp.x0 + r, bp.x1 - r)
            cy = rng.randint(bp.y0 + r, bp.y1 - r)
            # Ein Mittelpunkt im Safezone-Block ergaebe eine Lichtung, die
            # kaum gegraben wird und an der jeder Gang vorbeilaeuft.
            if (cx, cy) in field:
                break
        else:
            continue
        for y in range(cy - r, cy + r + 1):
            for x in range(cx - r, cx + r + 1):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r and (x, y) in field:
                    bp.grid[y][x] = FLOOR
        centres.append((cx, cy))
    for i in range(1, len(centres)):
        _corridor(bp, field, rng, centres[i - 1], centres[i], rng.choice((2, 3)))


def _carve_wurzeln(bp, rng, field, keep, near):
    """Verzweigte Gaenge, die vom Tor aus auswachsen."""
    _fill(bp, field, WALL)
    def branch(x, y, ang, length, width, depth):
        if depth <= 0 or length < 3:
            return
        for i in range(length + 1):
            nx = int(round(x + math.cos(ang) * i))
            ny = int(round(y + math.sin(ang) * i))
            for dy in range(width):
                for dx in range(width):
                    if (nx + dx, ny + dy) in field:
                        bp.grid[ny + dy][nx + dx] = FLOOR
        ex = int(round(x + math.cos(ang) * length))
        ey = int(round(y + math.sin(ang) * length))
        for _ in range(rng.randint(2, 4)):
            branch(ex, ey, ang + rng.uniform(-1.0, 1.0),
                   int(length * rng.uniform(0.65, 0.9)),
                   max(2, width - (1 if rng.random() < 0.35 else 0)),
                   depth - 1)

    # Zwei Staemme statt einem, und breiter: mit einem einzigen duennen
    # Ast blieben knapp ueber zehn Prozent der Karte begehbar, der Rest
    # war Fels, durch den man nur zusieht.
    ox, oy = bp.origin
    # Wuchsrichtung ins Feld hinein. Sitzt der Startraum rechts, zeigt
    # das Tor nach links - ein Stamm mit Winkel 0 stuende dort sofort vor
    # der Aussenmauer und die ganze Karte bliebe Fels.
    hinein = 0.0 if "links" in bp.safe_pos else math.pi
    branch(ox, oy, hinein, _skal(rng.randint(14, 20), bp.flin, 4), 4, 5)
    branch(ox, oy, hinein + rng.uniform(0.6, 1.2),
           _skal(rng.randint(12, 18), bp.flin, 4), 4, 5)


def _carve_spirale(bp, rng, field, keep, near):
    """Ein einziger Gang von aussen nach innen."""
    _fill(bp, field, WALL)
    width = rng.choice((2, 3))
    step = width + rng.choice((2, 3))
    x0, y0, x1, y1 = bp.x0, bp.y0, bp.x1, bp.y1
    while x1 - x0 > step + width and y1 - y0 > step + width:
        _carve_line(bp, field, x0, y0, x1, y0, width)
        _carve_line(bp, field, x1, y0, x1, y1, width)
        _carve_line(bp, field, x0, y1, x1, y1, width)
        # Die linke Seite bleibt oben offen - dort geht der Gang eine
        # Windung tiefer. Genau diese Luecke macht aus Ringen eine Spirale.
        _carve_line(bp, field, x0, y0 + step, x0, y1, width)
        x0 += step
        y0 += step
        x1 -= step
        y1 -= step


def _carve_kaefig(bp, rng, field, keep, near):
    """Gitter aus Mauern, jede Masche mit versetzten Luecken."""
    step = rng.randint(5, 8)
    for x in range(bp.x0 + step, bp.x1, step):
        for y in range(bp.y0, bp.y1 + 1):
            _set_wall(bp, field, keep, x, y)
    for y in range(bp.y0 + step, bp.y1, step):
        for x in range(bp.x0, bp.x1 + 1):
            _set_wall(bp, field, keep, x, y)
    # Je Masche und Seite eine Luecke: damit ist jedes Feld erreichbar,
    # ohne dass das Gitter seine Form verliert.
    for x in range(bp.x0 + step, bp.x1, step):
        for base in range(bp.y0, bp.y1, step):
            cy = base + rng.randint(1, max(1, step - 1))
            for d in range(2):
                if (x, cy + d) in field:
                    bp.grid[cy + d][x] = FLOOR
    for y in range(bp.y0 + step, bp.y1, step):
        for base in range(bp.x0, bp.x1, step):
            cx = base + rng.randint(1, max(1, step - 1))
            for d in range(2):
                if (cx + d, y) in field:
                    bp.grid[y][cx + d] = FLOOR


# ========================================================== Nachbereitung
def _reachable(bp):
    """Flutfuellung vom Tor aus. Zaehlt, was der Spieler wirklich erreicht."""
    gx, gy0, _ = bp.gate
    start = (gx, gy0)
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for (nx, ny) in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if (nx, ny) in seen or not bp.walkable(nx, ny):
                continue
            seen.add((nx, ny))
            stack.append((nx, ny))
    return seen


def _gate_link(bp, field, rng, max_links=6):
    """Verbindet das Tor mit dem, was die Art tatsaechlich gegraben hat.

    Vorher lief hier eine feste Linie vom Tor nach Osten. Die war blind:
    liegen alle Raeume weiter unten, trifft sie keinen einzigen, das Tor
    haengt an einem Stichgang - und die Reparatur macht aus dem ganzen
    Dungeon Fels. Gemessen waren das im schlimmsten Fall 770 von 920
    Bodenzellen.

    Also andersherum: nachsehen, was vom Tor aus *nicht* erreichbar ist,
    und zur groessten dieser Inseln einen Gang graben. Bis zu `max_links`
    mal, denn eine Hoehle zerfaellt gern in mehrere Teile. Krumen unter
    zwoelf Zellen bleiben liegen; die darf die Reparatur zumauern, dafuer
    ist sie da.
    """
    gx, gy0, gy1 = bp.gate
    start = (gx + 1, (gy0 + gy1) // 2)
    for _ in range(max_links):
        reach = _reachable(bp)
        lose = [(x, y) for (x, y) in field
                if bp.grid[y][x] == FLOOR and (x, y) not in reach]
        if not lose:
            return
        inseln = components(lose)
        groesste = max(inseln, key=len)
        if len(groesste) < 12:
            return
        ziel = min(groesste,
                   key=lambda p: (p[0] - start[0]) ** 2 + (p[1] - start[1]) ** 2)
        _corridor(bp, field, rng, start, ziel, 2)


def _link_abschnitt(bp, field, rng, max_links=6):
    """Inseln im Abschnitt zusammenhaengen.

    Beim Abschnitt gibt es kein Tor, von dem aus gemessen werden koennte.
    Also wird der groesste Bereich zum Bezug und alles Groessere daran
    angebunden - sonst faellt die halbe Flaeche der Reparatur zum Opfer.
    """
    for _ in range(max_links):
        floors = [p for p in field if bp.grid[p[1]][p[0]] == FLOOR]
        if not floors:
            return
        gruppen = components(floors)
        if len(gruppen) < 2:
            return
        gruppen.sort(key=len, reverse=True)
        haupt, zweit = gruppen[0], gruppen[1]
        if len(zweit) < 12:
            return
        mx = sum(p[0] for p in haupt) / float(len(haupt))
        my = sum(p[1] for p in haupt) / float(len(haupt))
        b = min(zweit, key=lambda p: (p[0] - mx) ** 2 + (p[1] - my) ** 2)
        a = min(haupt, key=lambda p: (p[0] - b[0]) ** 2 + (p[1] - b[1]) ** 2)
        _corridor(bp, field, rng, a, b, 2)


def _repair(bp):
    """Was vom Tor aus nicht erreichbar ist, wird zugemauert.

    Billiger und verlaesslicher, als jede Art einzeln beweisen zu lassen,
    dass sie keine abgeschlossene Blase erzeugt. Rueckgabe: wie viele
    Zellen dabei verloren gingen - zu viele heisst, der Wurf war schlecht.
    """
    if bp.has_safe:
        reach = _reachable(bp)
    else:
        # Ohne Tor gilt der groesste zusammenhaengende Bereich.
        floors = [(x, y) for y in range(bp.h) for x in range(bp.w)
                  if bp.grid[y][x] == FLOOR]
        gruppen = components(floors)
        reach = set(max(gruppen, key=len)) if gruppen else set()
    lost = 0
    for y in range(bp.h):
        for x in range(bp.w):
            if bp.grid[y][x] == FLOOR and (x, y) not in reach:
                bp.grid[y][x] = WALL
                lost += 1
    return lost


def _spawns(bp, rng):
    """Punkte weit weg vom Tor, moeglichst am Rand.

    Bei den offenen Arten liegt der Rand frei und die Bevorzugung greift.
    In einem Dungeon ist der Rand oft Mauer - dann zaehlt nur noch der
    Abstand zum Tor, sonst gaebe es gar keine Spawnpunkte.
    """
    gx, gy0, gy1 = bp.gate
    gcy = (gy0 + gy1) // 2
    far, border = [], []
    for y in range(bp.y0, bp.y1 + 1):
        for x in range(bp.x0, bp.x1 + 1):
            if bp.grid[y][x] != FLOOR:
                continue
            if max(abs(x - gx), abs(y - gcy)) < SPAWN_MIN_GATE:
                continue
            far.append((x, y))
            if min(x - bp.x0, bp.x1 - x,
                   y - bp.y0, bp.y1 - y) <= SPAWN_BORDER:
                border.append((x, y))

    pool = border if len(border) >= 12 else far
    rng.shuffle(pool)
    out = []
    for (x, y) in pool:
        if len(out) >= SPAWN_MAX:
            break
        if all(max(abs(x - ox), abs(y - oy)) >= SPAWN_SPREAD for ox, oy in out):
            out.append((x, y))
    out.sort(key=lambda p: (p[1], p[0]))
    return out


def spawns_for(source, seed=0):
    """Spawnpunkte fuer eine beliebige Karte.

    Braucht nur `.grid` und `.gate` - passt also auch auf das handgesetzte
    Layout, nicht nur auf einen Blueprint.
    """
    return _spawns(source, random.Random(seed))


def _blocks(bp, field):
    """Mauerteile im Feld als zusammenhaengende Gruppen."""
    cells = [(x, y) for (x, y) in field if bp.grid[y][x] == WALL]
    groups = components(cells)
    groups.sort(key=lambda g: (min(y for _, y in g), min(x for x, _ in g)))
    return groups


# ================================================================== Arten
MODES = {
    # --- offene Arena: passt zum Wellen-Survival ---------------------
    "streu":      {"gruppe": "Arena", "carve": _carve_streu,
                   "offen": (0.85, 0.96),
                   "text": "frei verteilte Deckung"},
    "gespiegelt": {"gruppe": "Arena", "carve": _carve_gespiegelt,
                   "offen": (0.85, 0.96),
                   "text": "punktsymmetrische Deckung"},
    "ringe":      {"gruppe": "Arena", "carve": _carve_ringe,
                   "offen": (0.85, 0.96),
                   "text": "Deckung auf drei Ringen"},
    "saeulen":    {"gruppe": "Arena", "carve": _carve_saeulen,
                   "offen": (0.82, 0.96),
                   "text": "regelmaessiges Saeulenraster"},
    "sektoren":   {"gruppe": "Arena", "carve": _carve_sektoren,
                   "offen": (0.86, 0.98),
                   "text": "Trennwaende mit Durchgaengen"},
    # --- Dungeon: Raeume und Gaenge ----------------------------------
    "raeume":     {"gruppe": "Dungeon", "carve": _carve_raeume,
                   "offen": (0.44, 0.74),
                   "text": "BSP-Raeume mit Gaengen"},
    "zellen":     {"gruppe": "Dungeon", "carve": _carve_zellen,
                   "offen": (0.60, 0.82),
                   "text": "Rasterzimmer mit Tueren"},
    "kammern":    {"gruppe": "Dungeon", "carve": _carve_kammern,
                   "offen": (0.32, 0.60),
                   "text": "wenige grosse Hallen"},
    # --- organisch ---------------------------------------------------
    "hoehle":     {"gruppe": "Organisch", "carve": _carve_hoehle,
                   "offen": (0.44, 0.74),
                   "text": "zellulaerer Automat"},
    "see":        {"gruppe": "Organisch", "carve": _carve_see,
                   "offen": (0.68, 0.92),
                   "text": "eine grosse offene Hoehle"},
    "adern":      {"gruppe": "Organisch", "carve": _carve_adern,
                   "offen": (0.25, 0.74),
                   "text": "gewundene Gaenge"},
    "inseln":     {"gruppe": "Organisch", "carve": _carve_inseln,
                   "offen": (0.76, 0.92),
                   "text": "gewachsene Bloecke"},
    # --- Labyrinth ---------------------------------------------------
    "labyrinth":  {"gruppe": "Labyrinth", "carve": _carve_labyrinth,
                   "offen": (0.50, 0.68),
                   "text": "echtes Labyrinth, enge Gaenge"},
    "schleifen":  {"gruppe": "Labyrinth", "carve": _carve_schleifen,
                   "offen": (0.52, 0.66),
                   "text": "Labyrinth ohne Sackgassen"},
    "hallen":     {"gruppe": "Labyrinth", "carve": _carve_hallen,
                   "offen": (0.66, 0.80),
                   "text": "Labyrinth mit weiten Gaengen"},
    # --- gebaute Formen ----------------------------------------------
    "rotunde":    {"gruppe": "Arena", "carve": _carve_rotunde,
                   "offen": (0.74, 0.90),
                   "text": "konzentrische Ringmauern"},
    "diagonal":   {"gruppe": "Arena", "carve": _carve_diagonal,
                   "offen": (0.86, 0.99),
                   "text": "schraege Balken"},
    "stadt":      {"gruppe": "Dungeon", "carve": _carve_stadt,
                   "offen": (0.44, 0.74),
                   "text": "Haeuserblocks mit Strassen"},
    "festung":    {"gruppe": "Dungeon", "carve": _carve_festung,
                   "offen": (0.82, 0.96),
                   "text": "verschachtelte Ringmauern mit Toren"},
    "katakomben": {"gruppe": "Dungeon", "carve": _carve_katakomben,
                   "offen": (0.28, 0.52),
                   "text": "viele kleine Kammern"},
    "tempel":     {"gruppe": "Dungeon", "carve": _carve_tempel,
                   "offen": (0.22, 0.54),
                   "text": "achsensymmetrisch um eine Mittelhalle"},
    "risse":      {"gruppe": "Organisch", "carve": _carve_risse,
                   "offen": (0.62, 0.95),
                   "text": "Bruchlinien wie gesprungenes Glas"},
    "krater":     {"gruppe": "Organisch", "carve": _carve_krater,
                   "offen": (0.20, 0.56),
                   "text": "runde Lichtungen im Fels"},
    "wurzeln":    {"gruppe": "Organisch", "carve": _carve_wurzeln,
                   "offen": (0.28, 0.64),
                   "text": "verzweigte Gaenge vom Tor aus"},
    "spirale":    {"gruppe": "Labyrinth", "carve": _carve_spirale,
                   "offen": (0.38, 0.66),
                   "text": "ein Gang von aussen nach innen"},
    "kaefig":     {"gruppe": "Labyrinth", "carve": _carve_kaefig,
                   "offen": (0.76, 0.90),
                   "text": "Gitter mit versetzten Luecken"},
}

GROUPS = ("Arena", "Dungeon", "Organisch", "Labyrinth")
# Nach Gruppen sortiert, nicht nach Einfuegereihenfolge: die elf spaeter
# hinzugekommenen Arten stehen im Wortverzeichnis hinten, und `TAB` waere
# dadurch zwischen den Gruppen hin und her gesprungen.
MODE_NAMES = tuple(name for g in GROUPS for name in MODES
                   if MODES[name]["gruppe"] == g)

# Arten, die alles zumauern und danach erst freischneiden. Sie brauchen
# die garantierte Anbindung ans Tor; die offenen Arten nicht.
WALL_FIRST = {"raeume", "zellen", "kammern", "hoehle", "see",
              "adern", "labyrinth", "schleifen", "hallen",
              "katakomben", "tempel", "krater", "wurzeln", "spirale"}


def modes_by_group():
    out = {}
    for name, spec in MODES.items():
        out.setdefault(spec["gruppe"], []).append(name)
    return out


# ================================================================= Bauen
def _grenzen(spanne, farea):
    """Erlaubter offener Anteil, auf die Kartengroesse bezogen.

    Die Werte sind an der Vorgabekarte gemessen. Auf einer viermal so
    grossen Karte verschiebt sich der Anteil systematisch - Gaenge werden
    laenger, Ringe duenner -, ohne dass die Karte schlechter waere. Statt
    die Grenzen pauschal aufzuweiten und damit die Vorgabekarte zu
    veraendern, waechst die Toleranz mit dem Groessenunterschied.

    Bei farea == 1.0 ist sie null: dieselben Karten wie bisher.
    """
    lo, hi = spanne
    if farea == 1.0:
        return lo, hi
    luft = min(0.35, 0.25 * abs(math.log(farea, 2)))
    return max(0.02, lo - luft), min(0.995, hi + luft)


def _try_build(rng, mode, w=MAP_W, h=MAP_H, arena=None, has_safe=True,
               safe_size=None, safe_pos="oben links"):
    spec = MODES[mode]
    bp = Blueprint(w, h, arena, has_safe, safe_size, safe_pos)
    bp.mode = mode
    _base(bp, rng)

    field = _field(bp)
    near, keep, keep_cells = _fields(bp, field)

    spec["carve"](bp, rng, field, keep, near)

    # Der Bereich vor dem Tor gehoert keiner Art.
    for (x, y) in keep_cells:
        bp.grid[y][x] = FLOOR
    if mode in WALL_FIRST:
        if bp.has_safe:
            _gate_link(bp, field, rng)
        else:
            _link_abschnitt(bp, field, rng)

    _repair(bp)

    if not field:
        # Kein Feld heisst: der Startraum fuellt die Karte. Das ist keine
        # Karte, sondern eine Fehleingabe - lieber verwerfen als teilen.
        return None
    open_cells = sum(1 for (x, y) in field if bp.grid[y][x] == FLOOR)
    ratio = open_cells / float(len(field))
    bp.open_ratio = ratio
    lo, hi = _grenzen(spec["offen"], bp.farea)
    if not (lo <= ratio <= hi):
        return None

    bp.blocks = _blocks(bp, field)
    bp.pillars = [_box(g) for g in bp.blocks]
    if not bp.blocks:
        return None

    if bp.has_safe:
        bp.spawns = _spawns(bp, rng)
        if len(bp.spawns) < 6:
            return None
    else:
        # Ein Abschnitt hat kein Tor - Spawnpunkte waeren ohne Bezug.
        bp.spawns = []
    return bp


# Abschnittsgroessen in Tiles. Bewusst ineinander aufgehend: ein grosser
# Abschnitt ist genau neun kleine, ein mittlerer vier. So passen sie in
# Tiled ohne Rechnerei aneinander.
# Welche Atlas-Kacheln Mauer sind - alles, was wall_tile_coords() liefern
# kann. Der Godot- und der Tiled-Export haengen beide daran: dort bekommt
# genau diese Auswahl eine Kollisionsflaeche.
WALL_TILES = ((1, 1), (3, 1), (5, 1), (1, 3), (5, 3),
              (1, 5), (3, 5), (5, 5), FILL_TILE)

# Arten, die in einen kleinen Abschnitt nicht passen: konzentrische Ringe,
# ein Zimmerraster und verschachtelte Ringmauern brauchen schlicht Flaeche.
# Gemessen, nicht geschaetzt - siehe README.
SECTION_UNFIT = {"klein": ("rotunde", "zellen", "festung")}

# Startraumgroessen in Tiles (Breite x Hoehe). `None` heisst wie bisher
# gewuerfelt - 13..17 breit, 11..15 hoch.
#
# Die Hoehe hat eine harte Untergrenze: das Tor sitzt bei sy0+3 bis
# sy1-4, darunter bliebe kein Platz dafuer. Neun ist das Kleinste, das
# noch aufgeht.
# In welcher Ecke der Startraum sitzt. Das Tor zeigt immer nach innen:
# bei den linken Ecken nach rechts, bei den rechten nach links.
SAFE_POSITIONS = ("oben links", "oben rechts", "unten links", "unten rechts")

# Grenzen fuer frei eingegebene Masse. Unten muss ein Startraum plus etwas
# Feld hineinpassen, oben ist es reine Vernunft: die Rechenzeit waechst
# mit der Flaeche, und eine 400x300-Karte ist keine Arena mehr.
# Gemessen, nicht geschaetzt: unter 48x36 fallen einzelne Arten durch,
# weil nach dem Startraum zu wenig Feld bleibt. Bei 48x36 kommen alle 26
# heraus.
MIN_W, MIN_H = 48, 36
MAX_W, MAX_H = 250, 200

# Startraum. Gemessen, nachdem der Torrand mitwaechst: ab 2 x 4 sitzt das
# Tor sauber zwischen zwei Wandstuecken. Bei Hoehe 3 stiesse es an den
# Rand des Raums, bei 2 raegte es heraus - das waere kein Raum mit Tuer
# mehr, sondern eine Luecke. Vorher stand hier 7 x 9, weil der Torrand
# fest war; das war eine Folge der Umsetzung, keine Notwendigkeit.
MIN_SAFE_W, MIN_SAFE_H = 2, 4


def clamp_masse(w, h):
    """Kartenmasse auf das Machbare begrenzen."""
    return (max(MIN_W, min(MAX_W, int(w))),
            max(MIN_H, min(MAX_H, int(h))))


def clamp_startraum(w, h, karte=None):
    """Startraum begrenzen - auch gegen die Karte, in die er soll.

    Ein Startraum, der breiter ist als die Arena, waere kein Startraum
    mehr, sondern die Karte. Deshalb hoechstens die halbe Flaeche.
    """
    w = max(MIN_SAFE_W, int(w))
    h = max(MIN_SAFE_H, int(h))
    if karte is not None:
        kw, kh = karte
        w = min(w, max(MIN_SAFE_W, (kw - 6) // 2))
        h = min(h, max(MIN_SAFE_H, (kh - 6) // 2))
    return w, h


SAFE_SIZES = {
    "klein":  (11, 9),
    "mittel": (15, 12),
    "gross":  (20, 16),
}


SECTIONS = {
    "klein":  (16, 12),
    "mittel": (32, 24),
    "gross":  (48, 36),
}


def modes_for_section(size):
    """Arten, die in dieser Abschnittsgroesse taugen."""
    unfit = SECTION_UNFIT.get(size, ())
    return [n for n in MODE_NAMES if n not in unfit]


def generate_section(seed=None, mode=None, size="mittel"):
    """Ein Kartenabschnitt ohne Safezone, Tor und Aussenmauer.

    Gedacht zum Zusammensetzen in Tiled: die Flaeche reicht bis an den
    Rand, damit zwei Abschnitte nahtlos aneinanderstossen.
    """
    if isinstance(size, (tuple, list)):
        # Eigene Masse. Ein Abschnitt darf kleiner sein als eine Vollkarte -
        # er braucht keinen Startraum -, deshalb eine eigene Untergrenze.
        w = max(8, min(MAX_W, int(size[0])))
        h = max(8, min(MAX_H, int(size[1])))
        size = "eigene"
    elif size in SECTIONS:
        w, h = SECTIONS[size]
    else:
        raise ValueError("unbekannte Groesse: %s" % size)
    if mode is None:
        # Nur aus dem waehlen, was in dieser Groesse auch herauskommt.
        moeglich = modes_for_section(size if size in SECTION_UNFIT else "gross")
        mode = random.Random(seed if seed is not None
                             else random.randrange(1, 10 ** 9)).choice(moeglich)
    return generate(seed, mode, w=w, h=h,
                    arena=(0, 0, w - 1, h - 1), has_safe=False)


def arena_fuer(w, h):
    """Arenagrenzen fuer eine Karte dieser Groesse.

    Der Rand bleibt wie bei der Vorgabekarte: eine Mauer, davor zwei
    Zellen Nichts. So sieht eine 100x80-Karte am Rand aus wie die 68x46.
    """
    return (3, 3, w - 4, h - 4)


def generate(seed=None, mode=None, w=MAP_W, h=MAP_H, arena=None,
             has_safe=True, safe_size=None, safe_pos="oben links"):
    """Baut eine Karte. Gleicher Seed, gleiche Karte - immer.

    Verworfene Anlaeufe ziehen weiter aus demselben Zufallsstrom, statt
    den Seed zu veraendern: der Seed bleibt die Identitaet der Karte,
    auch wenn dahinter zwoelf Versuche stecken.
    """
    if seed is None:
        seed = random.randrange(1, 10 ** 9)
    if arena is None and (w, h) != (MAP_W, MAP_H):
        w, h = clamp_masse(w, h)
        arena = arena_fuer(w, h)
    rng = random.Random(seed)
    if mode is None:
        mode = rng.choice(MODE_NAMES)
    if mode not in MODES:
        raise ValueError("unbekannte Art: %s" % mode)

    for attempt in range(1, 121):
        bp = _try_build(rng, mode, w, h, arena, has_safe, safe_size,
                        safe_pos)
        if bp is not None:
            bp.seed = seed
            bp.attempts = attempt
            return bp

    # Notnagel: leere Arena. Haesslich, aber spielbar - besser als ein
    # Absturz, falls irgendwann jemand an den Konstanten dreht.
    bp = Blueprint(w, h, arena, has_safe, safe_size, safe_pos)
    bp.mode = mode
    fallback = random.Random(seed)
    _base(bp, fallback)
    bp.seed = seed
    bp.attempts = 120
    bp.open_ratio = 1.0
    bp.spawns = _spawns(bp, fallback)
    return bp
