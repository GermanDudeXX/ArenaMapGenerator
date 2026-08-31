"""Alle Kartenarten nebeneinander auf ein Blatt.

Dieselbe Zahl als Seed fuer jede Art: dann liegt der Unterschied
zwischen zwei Bildern wirklich an der Art und nicht daran, dass zwei
verschiedene Karten verglichen werden.

Aufruf:  python tools/kontaktbogen.py --seed 4242
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from za import mapgen
from za.settings import MAP_W, MAP_H, TILE, C_BG, C_TEXT, C_GOLD, C_DIM

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COLS = 4
SHRINK = 3          # Karte wird auf 1/SHRINK verkleinert
PAD = 10
HEAD = 22


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kontaktbogen aller Kartenarten")
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--out", default=os.path.join(ROOT, "export",
                                                  "kontaktbogen.png"))
    a = ap.parse_args(argv)

    pygame.init()
    pygame.display.set_mode((64, 64))
    from za.world import World

    tw, th = MAP_W * TILE // SHRINK, MAP_H * TILE // SHRINK
    names = mapgen.MODE_NAMES
    rows = (len(names) + COLS - 1) // COLS
    sheet = pygame.Surface((PAD + COLS * (tw + PAD),
                            PAD + rows * (th + HEAD + PAD)))
    sheet.fill((16, 17, 24))
    font = pygame.font.SysFont("consolas,couriernew,monospace", 14, bold=True)
    small = pygame.font.SysFont("consolas,couriernew,monospace", 11)

    for i, name in enumerate(names):
        world = World(a.seed, name)
        bp = world.blueprint
        full = pygame.Surface((MAP_W * TILE, MAP_H * TILE))
        full.fill(C_BG)
        world.draw(full, (0, 0))

        col, row = i % COLS, i // COLS
        x = PAD + col * (tw + PAD)
        y = PAD + row * (th + HEAD + PAD)

        sheet.blit(font.render(name, True, C_GOLD), (x, y))
        spec = mapgen.MODES[name]
        info = "%s - %s - %d%% offen" % (spec["gruppe"], spec["text"],
                                         round(bp.open_ratio * 100))
        sheet.blit(small.render(info, True, C_DIM), (x, y + 13))
        sheet.blit(pygame.transform.smoothscale(full, (tw, th)),
                   (x, y + HEAD))
        pygame.draw.rect(sheet, (60, 66, 86), (x, y + HEAD, tw, th), 1)
        print("  %-11s %-10s %2d Bloecke  %2d Spawns  %d%% offen"
              % (name, spec["gruppe"], len(bp.blocks), len(bp.spawns),
                 round(bp.open_ratio * 100)))

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    pygame.image.save(sheet, a.out)
    pygame.quit()
    print("\n%s  (%d x %d)" % (a.out, sheet.get_width(), sheet.get_height()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
