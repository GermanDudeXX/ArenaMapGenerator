"""Karten und Abschnitte fuer Tiled schreiben - mit Hitboxen.

Erzeugt `.tmx` (Karte) und `.tsx` (Tileset). Die Kollision steht doppelt
drin, und das mit Absicht:

* **Im Tileset**, als Kollisionsflaeche je Mauerkachel. Die traegt jede
  Kachel mit sich - auch die, die spaeter von Hand in Tiled gesetzt wird.
  Wer Abschnitte zusammensetzt und nachbessert, braucht genau das.
* **Als Objektebene** in der Karte, ein Rechteck je zusammenhaengendem
  Mauerteil. Das ist die grobe, billige Fassung fuer Engines, die eine
  Objektebene lesen, aber keine Kachelkollision.

Beides liest Godot ueber die gaengigen Tiled-Importer, und Tiled selbst
zeigt beides an.

Aufruf:
    python tools/export_tiled.py --seed 4242
    python tools/export_tiled.py --abschnitt mittel --anzahl 6
    python tools/export_tiled.py --abschnitt klein --mode hoehle --seed 7
"""
import argparse
import os
import shutil
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from za import mapgen
from za.settings import TILE, WALL, FLOOR, GATE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tiled_export")

TSX_NAME = "ArenaTileset.tsx"
PNG_NAME = "ArenaTileset.png"

# Das uebrige CraftPix-Paket, als eigene Tilesets. Jede exportierte Karte
# bringt alles mit - so kann man in Tiled dekorieren, ohne sich die
# Grafiken zusammenzusuchen.
#
# Bewusst mehrere Tilesets statt eines Riesenatlas: erstens bleiben die
# Koordinaten des Gelaende-Atlas dadurch unangetastet und die Kartendaten
# gueltig, zweitens bekommt man in Tiled je Bereich einen eigenen Reiter
# statt einer Bildlaufleiste ueber tausend Kacheln.
ZUSATZ = [
    ("Objekte",           "Objekte.png"),
    ("ObjekteGross",      "ObjekteGross.png"),
    ("ObjekteDetails",    "ObjekteDetails.png"),
    ("AnimierteObjekte",  "AnimierteObjekte.png"),
    ("Charakter1",        "Charakter1.png"),
    ("Charakter2",        "Charakter2.png"),
    ("Charakter3",        "Charakter3.png"),
    ("CharakterDetails",  "CharakterDetails.png"),
    ("Gegner1",           "Gegner1.png"),
    ("Gegner2",           "Gegner2.png"),
    ("Gegner3",           "Gegner3.png"),
    ("Gegner4",           "Gegner4.png"),
]

TILED_VERSION = "1.11.0"
MAP_VERSION = "1.10"


# --------------------------------------------------------------- Tileset
def _pygame_bereit():
    """pygame nur hochfahren, wenn es nicht schon laeuft.

    Diese Funktionen werden auch aus dem laufenden Viewer heraus
    aufgerufen. Ein `pygame.quit()` am Ende raeumte dort das Fenster ab -
    ein Werkzeug darf die Anzeige nicht abschalten, die es benutzt.
    """
    import pygame
    if pygame.get_init() and pygame.display.get_surface() is not None:
        return False
    pygame.init()
    pygame.display.set_mode((64, 64))
    return True


def atlas_png(dest):
    """Den erweiterten Atlas schreiben und seine Masse liefern."""
    from tools.export_godot import build_atlas
    import pygame
    selbst = _pygame_bereit()
    cols, rows = build_atlas(dest)
    if selbst:
        pygame.quit()
    return cols, rows


def png_masse(pfad):
    """Breite und Hoehe eines PNG aus dem Kopf lesen - ohne pygame."""
    import struct
    with open(pfad, "rb") as fh:
        kopf = fh.read(33)
    w, h = struct.unpack(">II", kopf[16:24])
    return w, h


def schreibe_tilesets(out_dir, cols, rows):
    """Alle Tilesets schreiben: Gelaende zuerst, dann das ganze Paket.

    Rueckgabe: Liste aus (Dateiname der .tsx, Kachelzahl) in genau der
    Reihenfolge, in der die firstgid vergeben werden. Wer die Liste
    weiterreicht, kann die Nummern nicht mehr durcheinanderbringen.
    """
    raus = [(TSX_NAME, cols * rows)]
    write_tsx(os.path.join(out_dir, TSX_NAME), cols, rows)
    raus += _write_zusatz(out_dir)
    return raus


def _write_zusatz(out_dir):
    from za.settings import ASSETS
    quelle = os.path.join(ASSETS, "craftpix")
    raus = []
    for name, png in ZUSATZ:
        von = os.path.join(quelle, png)
        if not os.path.exists(von):
            continue
        nach = os.path.join(out_dir, png)
        if os.path.abspath(von) != os.path.abspath(nach):
            shutil.copyfile(von, nach)
        w, h = png_masse(nach)
        cols, rows = w // TILE, h // TILE
        ts = ET.Element("tileset", {
            "version": MAP_VERSION, "tiledversion": TILED_VERSION,
            "name": name, "tilewidth": str(TILE), "tileheight": str(TILE),
            "tilecount": str(cols * rows), "columns": str(cols),
        })
        ET.SubElement(ts, "image", {"source": png,
                                    "width": str(w), "height": str(h)})
        tsx = name + ".tsx"
        _write(ET.ElementTree(ts), os.path.join(out_dir, tsx))
        raus.append((tsx, cols * rows))
    return raus


def write_tsx(path, cols, rows):
    """Tileset mit Kollisionsflaeche je Mauerkachel.

    Die Flaeche ist das ganze Tile. Das entspricht dem Modell des
    Generators - eine Mauerzelle ist ganz blockiert - und deckt sich mit
    dem, was der Godot-Export erzeugt.
    """
    ts = ET.Element("tileset", {
        "version": MAP_VERSION, "tiledversion": TILED_VERSION,
        "name": "ArenaTileset",
        "tilewidth": str(TILE), "tileheight": str(TILE),
        "tilecount": str(cols * rows), "columns": str(cols),
    })
    ET.SubElement(ts, "image", {
        "source": PNG_NAME,
        "width": str(cols * TILE), "height": str(rows * TILE),
    })
    for n, (c, r) in enumerate(mapgen.WALL_TILES, 1):
        tile = ET.SubElement(ts, "tile", {"id": str(r * cols + c)})
        og = ET.SubElement(tile, "objectgroup",
                           {"draworder": "index", "id": "1"})
        ET.SubElement(og, "object", {
            "id": "1", "x": "0", "y": "0",
            "width": str(TILE), "height": str(TILE),
        })
    _write(ET.ElementTree(ts), path)
    return len(mapgen.WALL_TILES)


# ------------------------------------------------------------------ Karte
def _gid(coord, cols):
    """Tiled zaehlt Kacheln ab 1, zeilenweise durch den Atlas."""
    c, r = coord
    return r * cols + c + 1


def hitbox_rects(bp):
    """Ein Rechteck je Mauerteil, plus die Aussenmauer der Vollkarte."""
    out = []
    for i, cells in enumerate(bp.blocks, 1):
        for j, r in enumerate(mapgen.rects_from_cells(cells), 1):
            out.append(("Block_%02d_%d" % (i, j), r))
    if bp.has_safe:
        from tools.export_godot import structure_hitboxes
        for (name, x, y, w, h) in structure_hitboxes(bp):
            out.append((name, (x, y, w, h)))
    return out


def write_tmx(path, bp, cols, tilesets=None):
    atlas = mapgen.atlas_map(bp.grid)
    leer = 0

    m = ET.Element("map", {
        "version": MAP_VERSION, "tiledversion": TILED_VERSION,
        "orientation": "orthogonal", "renderorder": "right-down",
        "width": str(bp.w), "height": str(bp.h),
        "tilewidth": str(TILE), "tileheight": str(TILE),
        "infinite": "0", "nextlayerid": "4", "nextobjectid": "1",
    })
    # Der Gelaende-Atlas steht immer zuerst und behaelt firstgid 1 -
    # dadurch bleiben die Kacheldaten unten unveraendert gueltig, egal
    # wie viele Tilesets noch dazukommen.
    gid = 1
    for tsx, anzahl in (tilesets or [(TSX_NAME, 0)]):
        ET.SubElement(m, "tileset", {"firstgid": str(gid), "source": tsx})
        gid += anzahl

    layer = ET.SubElement(m, "layer", {
        "id": "1", "name": "Boden",
        "width": str(bp.w), "height": str(bp.h),
    })
    zeilen = []
    for y in range(bp.h):
        zeile = []
        for x in range(bp.w):
            coord = atlas.get((x, y))
            zeile.append(str(_gid(coord, cols)) if coord else str(leer))
        zeilen.append(",".join(zeile))
    data = ET.SubElement(layer, "data", {"encoding": "csv"})
    data.text = "\n" + ",\n".join(zeilen) + "\n"

    og = ET.SubElement(m, "objectgroup", {"id": "2", "name": "Kollision"})
    oid = 1
    for name, (x, y, w, h) in hitbox_rects(bp):
        ET.SubElement(og, "object", {
            "id": str(oid), "name": name,
            "x": str(x * TILE), "y": str(y * TILE),
            "width": str(w * TILE), "height": str(h * TILE),
        })
        oid += 1

    if bp.spawns:
        sg = ET.SubElement(m, "objectgroup", {"id": "3", "name": "Spawns"})
        for (sx, sy) in bp.spawns:
            o = ET.SubElement(sg, "object", {
                "id": str(oid), "name": "Spawn",
                "x": str(sx * TILE + TILE // 2),
                "y": str(sy * TILE + TILE // 2),
            })
            ET.SubElement(o, "point")
            oid += 1
    m.set("nextobjectid", str(oid))

    _write(ET.ElementTree(m), path)
    return oid - 1


def _write(tree, path):
    ET.indent(tree, space=" ")
    tree.write(path, encoding="UTF-8", xml_declaration=True)


def vorschau_png(bp, dest):
    """Die Karte als Bild - ohne World, das haengt an der Vollkarte.

    Gezeichnet wird direkt aus atlas_map(); damit sieht die Vorschau
    genauso aus wie das, was in der .tmx steht.
    """
    import pygame
    from za.settings import ASSETS, C_BG
    from za.world import build_fill_tile

    selbst = _pygame_bereit()
    sheet = pygame.image.load(
        os.path.join(ASSETS, "tiles", "Tileset.png")).convert_alpha()
    kacheln = {}
    for r in range(sheet.get_height() // TILE):
        for c in range(sheet.get_width() // TILE):
            kacheln[(c, r)] = sheet.subsurface((c * TILE, r * TILE, TILE, TILE))
    kacheln[mapgen.FILL_TILE] = build_fill_tile(kacheln[mapgen.FILL_SOURCE])

    surf = pygame.Surface((bp.w * TILE, bp.h * TILE))
    surf.fill(C_BG)
    for (x, y), coord in mapgen.atlas_map(bp.grid).items():
        surf.blit(kacheln[coord], (x * TILE, y * TILE))
    pygame.image.save(surf, dest)
    if selbst:
        pygame.quit()


# ------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description="Tiled-Export")
    ap.add_argument("--abschnitt", choices=sorted(mapgen.SECTIONS),
                    default=None,
                    help="Abschnitt dieser Groesse statt der Vollkarte")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--mode", default=None)
    ap.add_argument("--anzahl", type=int, default=1,
                    help="mehrere Abschnitte auf einmal")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--vorschau", action="store_true",
                    help="zu jeder .tmx ein PNG zum Ansehen")
    a = ap.parse_args(argv)

    os.makedirs(a.out, exist_ok=True)
    cols, rows = atlas_png(os.path.join(a.out, PNG_NAME))
    tilesets = schreibe_tilesets(a.out, cols, rows)
    print("Tilesets %d, zusammen %d Kacheln  (Gelaende %dx%d, %d mit Kollision)"
          % (len(tilesets), sum(n for _, n in tilesets), cols, rows,
             len(mapgen.WALL_TILES)))
    for tsx, n in tilesets[1:]:
        print("   + %-24s %4d Kacheln" % (tsx, n))

    import random
    dateien = []
    for i in range(a.anzahl):
        seed = a.seed if a.seed is not None else random.randrange(1, 10 ** 9)
        if a.anzahl > 1 and a.seed is not None:
            seed = a.seed + i
        if a.abschnitt:
            bp = mapgen.generate_section(seed, a.mode, a.abschnitt)
            name = "abschnitt_%s_%s_%d.tmx" % (a.abschnitt, bp.mode, bp.seed)
        else:
            bp = mapgen.generate(seed, a.mode)
            name = "karte_%s_%d.tmx" % (bp.mode, bp.seed)
        pfad = os.path.join(a.out, name)
        n_obj = write_tmx(pfad, bp, cols, tilesets)
        dateien.append(pfad)
        if a.vorschau:
            vorschau_png(bp, pfad[:-4] + ".png")
        print("  %-44s %2dx%-2d  %-11s %3d%% offen  %3d Objekte"
              % (name, bp.w, bp.h, bp.mode,
                 round(bp.open_ratio * 100), n_obj))
    print()
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
