"""Baut das Godot-Paket: Atlas-PNG + Kartendaten.

Zwei Schritte, und der zweite passiert nicht hier:

1. Dieses Skript schreibt `ArenaTileset.png` und `arena_data.json`.
2. `tools/build_scene.gd` laesst *Godot selbst* daraus `ArenaMap.tscn`
   und `ArenaTileset.tres` schreiben.

Der zweite Schritt geht bewusst durch Godot. Ein .tscn von Hand zu
tippen hiesse, das Binaerformat von `tile_map_data` zu raten - und ein
Fehler darin faellt erst dem Entwickler auf, nicht mir. Godot kennt sein
eigenes Format.

Aufruf:  python tools/export_godot.py --seed 4242
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from za import mapgen
from za.settings import (
    ASSETS, TILE, MAP_W, MAP_H, WALL,
    ARENA_X0, ARENA_Y0, ARENA_X1, ARENA_Y1,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Zwischenstaende - das ausgelieferte Paket liegt eine Ebene hoeher.
OUT = os.path.join(ROOT, "godot_export", "_build")


def build_atlas(dest):
    """Original-Tileset plus eine Zeile fuer das Fuellstueck.

    Das Fuellstueck erzeugt der Viewer sonst zur Laufzeit und es hat
    darum keine Atlas-Koordinate. Angehaengt statt in einen freien Slot
    geschrieben: so bleibt das Original Zeile fuer Zeile an seinem Platz,
    und wer das Tileset kennt, findet sich weiter zurecht.
    """
    from za.world import build_fill_tile

    sheet = pygame.image.load(os.path.join(ASSETS, "tiles", "Tileset.png"))
    sheet = sheet.convert_alpha()
    cols = sheet.get_width() // TILE
    rows = sheet.get_height() // TILE

    fx, fy = mapgen.FILL_TILE
    need_rows = max(rows, fy + 1)
    out = pygame.Surface((max(cols, fx + 1) * TILE, need_rows * TILE),
                         pygame.SRCALPHA)
    out.blit(sheet, (0, 0))

    src = sheet.subsurface((mapgen.FILL_SOURCE[0] * TILE,
                            mapgen.FILL_SOURCE[1] * TILE, TILE, TILE))
    out.blit(build_fill_tile(src), (fx * TILE, fy * TILE))
    pygame.image.save(out, dest)
    return out.get_width() // TILE, out.get_height() // TILE


def structure_hitboxes(bp):
    """Aussenmauer und Safezone-Waende als benannte Rechtecke.

    Nicht generisch aus dem Gitter gelesen, sondern aus den Massen
    gerechnet: so bekommt der Entwickler acht sinnvoll benannte Bodies
    statt vierzig namenlose Bruchstuecke.
    """
    sx0, sy0, sx1, sy1 = bp.safe
    gx, gy0, gy1 = bp.gate
    x0, y0, x1, y1 = bp.x0, bp.y0, bp.x1, bp.y1
    aw = x1 - x0 + 3                    # Aussenmauer inkl. Ecken
    ah = y1 - y0 + 3
    out = [
        ("Mauer_Nord", x0 - 1, y0 - 1, aw, 1),
        ("Mauer_Sued", x0 - 1, y1 + 1, aw, 1),
        ("Mauer_West", x0 - 1, y0, 1, ah - 2),
        ("Mauer_Ost", x1 + 1, y0, 1, ah - 2),
    ]

    # Startraum: eine Querwand und die Torwand in zwei Stuecken, weil das
    # Tor dazwischen liegt. Wo die liegen, haengt an der Ecke - deshalb
    # aus dem gemerkten Klotz gerechnet und nicht hingeschrieben. Die
    # Ecken gehoeren jeweils genau einer Wand: zwei Bodies uebereinander
    # waeren nicht falsch, aber wer einen wegschiebt, uebersieht den
    # anderen.
    links = "links" in bp.safe_pos
    oben = bp.safe_pos.startswith("oben")
    trenn_y = sy1 + 1 if oben else sy0 - 1
    quer_x0 = x0 if links else gx
    quer_br = (gx - x0 + 1) if links else (x1 - gx + 1)
    out.append(("Safezone_Querwand", quer_x0, trenn_y, quer_br, 1))

    if oben:
        out.append(("Safezone_Torwand_Oben", gx, y0, 1, gy0 - y0))
        out.append(("Safezone_Torwand_Unten", gx, gy1 + 1, 1, sy1 - gy1))
    else:
        out.append(("Safezone_Torwand_Oben", gx, sy0, 1, gy0 - sy0))
        out.append(("Safezone_Torwand_Unten", gx, gy1 + 1, 1, y1 - gy1))

    return [(n, x, y, w, h) for (n, x, y, w, h) in out if w > 0 and h > 0]


def export(seed, mode=None):
    os.makedirs(OUT, exist_ok=True)
    pygame.init()
    pygame.display.set_mode((64, 64))

    bp = mapgen.generate(seed, mode)
    acols, arows = build_atlas(os.path.join(OUT, "ArenaTileset.png"))

    atlas = mapgen.atlas_map(bp.grid)
    cells = [{"x": x, "y": y, "ax": c, "ay": r}
             for (x, y), (c, r) in sorted(atlas.items(), key=lambda kv: (kv[0][1], kv[0][0]))]

    obstacles = []
    for i, shape in enumerate(bp.blocks, 1):
        obstacles.append({
            "name": "Block_%02d" % i,
            "rects": [{"x": x, "y": y, "w": w, "h": h}
                      for (x, y, w, h) in mapgen.rects_from_cells(shape)],
        })

    walls = [{"name": n, "rects": [{"x": x, "y": y, "w": w, "h": h}]}
             for (n, x, y, w, h) in structure_hitboxes(bp)]

    data = {
        "seed": bp.seed,
        "mode": bp.mode,
        "group": bp.group,
        "tile": TILE,
        "width": MAP_W,
        "height": MAP_H,
        "atlas_columns": acols,
        "atlas_rows": arows,
        "cells": cells,
        "walls": walls,
        "obstacles": obstacles,
    }
    path = os.path.join(OUT, "arena_data.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)

    # Gegenprobe: jede Mauerzelle im Gitter muss von genau einer Hitbox
    # gedeckt sein, und keine Hitbox darf ueber Boden liegen. Ohne das
    # kann die Grafik stimmen und die Kollision trotzdem falsch sein.
    covered = {}
    for group in (walls + obstacles):
        for r in group["rects"]:
            for yy in range(r["y"], r["y"] + r["h"]):
                for xx in range(r["x"], r["x"] + r["w"]):
                    covered[(xx, yy)] = covered.get((xx, yy), 0) + 1
    wall_cells = {(x, y) for y in range(MAP_H) for x in range(MAP_W)
                  if bp.grid[y][x] == WALL}
    missing = wall_cells - set(covered)
    extra = set(covered) - wall_cells
    doubled = {p for p, n in covered.items() if n > 1}

    pygame.quit()
    return data, path, missing, extra, doubled


def main(argv=None):
    ap = argparse.ArgumentParser(description="Godot-Export vorbereiten")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--mode", default=None)
    a = ap.parse_args(argv)

    data, path, missing, extra, doubled = export(a.seed, a.mode)
    print("Seed %d  Art %s (%s)" % (data["seed"], data["mode"], data["group"]))
    print("  Atlas    %d x %d Tiles" % (data["atlas_columns"], data["atlas_rows"]))
    print("  Tiles    %d" % len(data["cells"]))
    print("  Hitboxen %d Waende + %d Deckungen = %d Bodies, %d Rechtecke"
          % (len(data["walls"]), len(data["obstacles"]),
             len(data["walls"]) + len(data["obstacles"]),
             sum(len(g["rects"]) for g in data["walls"] + data["obstacles"])))
    print("  Deckung nicht abgedeckt: %d, ueber Boden: %d, doppelt: %d"
          % (len(missing), len(extra), len(doubled)))
    print(path)
    return 0 if not (missing or extra or doubled) else 1


if __name__ == "__main__":
    sys.exit(main())
