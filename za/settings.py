"""Konstanten fuer den Arena-Map-Viewer."""
import os

from .paths import assets_dir, exe_dir

# Als Skript sind das dieselben Ordner; in der gepackten .exe kommen die
# Grafiken aus dem Temp-Verzeichnis des Bundles und die Ausgabe daneben.
ROOT = exe_dir()
ASSETS = assets_dir()

# --- Aufloesung -------------------------------------------------------------
TILE = 16
VIEW_W, VIEW_H = 480, 270          # interne Render-Aufloesung (wird hochskaliert)
FPS = 60

# --- Karte ------------------------------------------------------------------
MAP_W, MAP_H = 68, 46              # in Tiles

ARENA_X0, ARENA_Y0 = 3, 3          # begehbarer Arena-Bereich (inklusive)
ARENA_X1, ARENA_Y1 = 64, 42

SAFE_X0, SAFE_Y0 = 3, 3            # Innenraum des abgesperrten Bereichs
SAFE_X1, SAFE_Y1 = 18, 16
GATE_X = 19                        # Torspalte
GATE_Y0, GATE_Y1 = 9, 10           # Tor ist zwei Tiles hoch

# --- Zellentypen ------------------------------------------------------------
VOID, WALL, FLOOR, GATE = 0, 1, 2, 3

# --- Farben -----------------------------------------------------------------
C_BG = (13, 13, 20)
C_TEXT = (233, 237, 245)
C_DIM = (139, 147, 168)
C_GOLD = (247, 178, 62)
C_SAFE = (96, 202, 164)
