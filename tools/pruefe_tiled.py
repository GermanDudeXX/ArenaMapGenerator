"""Prueft den Tiled-Export, indem Tiled selbst ihn liest.

Tiled exportiert die .tmx nach JSON. Wenn das durchlaeuft, ist die Datei
gueltig - das ist die eine Haelfte. Die andere: das zurueckgelesene JSON
gegen das Gitter halten, aus dem es entstanden ist. Eine Datei kann
formal gueltig sein und trotzdem die falsche Karte enthalten.

Geprueft wird:
  * jede Kachel des Bodens stimmt mit atlas_map() ueberein
  * die Kollisionsobjekte decken genau die Mauerzellen, ohne Ueberlappung
  * jede Mauerkachel im Tileset traegt ihre eigene Kollisionsflaeche
  * Spawnpunkte liegen auf Boden

Aufruf:  python tools/pruefe_tiled.py
"""
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from za import mapgen
from za.settings import TILE, WALL, FLOOR
from tools import export_tiled

TILED = r"C:\Program Files\Tiled\tiled.exe"


def tiled_liest(tmx, ziel):
    """Tiled die Datei lesen und als JSON zurueckschreiben lassen."""
    p = subprocess.run([TILED, "--export-map", tmx, ziel],
                       capture_output=True, text=True)
    if p.returncode != 0 or not os.path.exists(ziel):
        return None, (p.stdout + p.stderr).strip()
    with open(ziel, encoding="utf-8") as fh:
        return json.load(fh), ""


def pruefe(bp, tmx, cols, fehler, tag):
    with tempfile.TemporaryDirectory() as tmp:
        ziel = os.path.join(tmp, "out.json")
        daten, meldung = tiled_liest(tmx, ziel)
    if daten is None:
        fehler.append("%s: Tiled kann die Datei nicht lesen (%s)"
                      % (tag, meldung[:120]))
        return 0, 0

    if daten["width"] != bp.w or daten["height"] != bp.h:
        fehler.append("%s: Masse %dx%d statt %dx%d"
                      % (tag, daten["width"], daten["height"], bp.w, bp.h))

    ts = daten.get("tilesets", [])
    if len(ts) < 13:
        fehler.append("%s: nur %d Tilesets in der Karte" % (tag, len(ts)))
    if ts and ts[0]["firstgid"] != 1:
        fehler.append("%s: Gelaende-Tileset hat firstgid %d" % (tag, ts[0]["firstgid"]))

    boden = next((l for l in daten["layers"] if l.get("name") == "Boden"), None)
    if boden is None:
        fehler.append(tag + ": Ebene Boden fehlt")
        return 0, 0

    soll = mapgen.atlas_map(bp.grid)
    falsch = 0
    for y in range(bp.h):
        for x in range(bp.w):
            gid = boden["data"][y * bp.w + x]
            coord = soll.get((x, y))
            if coord is None:
                if gid != 0:
                    falsch += 1
                continue
            if gid != coord[1] * cols + coord[0] + 1:
                falsch += 1
    if falsch:
        fehler.append("%s: %d Kacheln stimmen nicht" % (tag, falsch))

    # Kollisionsobjekte auf Zellen zurueckrechnen
    koll = next((l for l in daten["layers"] if l.get("name") == "Kollision"), None)
    gedeckt = {}
    doppelt = 0
    if koll is None:
        fehler.append(tag + ": Ebene Kollision fehlt")
    else:
        for o in koll["objects"]:
            if o["x"] % TILE or o["y"] % TILE \
                    or o["width"] % TILE or o["height"] % TILE:
                fehler.append("%s: Objekt %s nicht auf dem Raster"
                              % (tag, o.get("name")))
                continue
            for yy in range(int(o["y"] // TILE),
                            int((o["y"] + o["height"]) // TILE)):
                for xx in range(int(o["x"] // TILE),
                                int((o["x"] + o["width"]) // TILE)):
                    if (xx, yy) in gedeckt:
                        doppelt += 1
                    gedeckt[(xx, yy)] = True

    mauern = {(x, y) for y in range(bp.h) for x in range(bp.w)
              if bp.grid[y][x] == WALL}
    fehlend = len(mauern - set(gedeckt))
    ueber = len(set(gedeckt) - mauern)
    if fehlend:
        fehler.append("%s: %d Mauerzellen ohne Objekt" % (tag, fehlend))
    if ueber:
        fehler.append("%s: %d Objektzellen ueber Boden" % (tag, ueber))
    if doppelt:
        fehler.append("%s: %d Zellen doppelt belegt" % (tag, doppelt))

    spawns = next((l for l in daten["layers"] if l.get("name") == "Spawns"), None)
    if spawns:
        for o in spawns["objects"]:
            tx, ty = int(o["x"] // TILE), int(o["y"] // TILE)
            if bp.grid[ty][tx] != FLOOR:
                fehler.append(tag + ": Spawnpunkt nicht auf Boden")
                break
    return len(mauern), len(koll["objects"]) if koll else 0


def pruefe_tsx(pfad, cols, fehler):
    """Traegt jede Mauerkachel im Tileset ihre Kollisionsflaeche?"""
    wurzel = ET.parse(pfad).getroot()
    haben = set()
    for tile in wurzel.findall("tile"):
        if tile.find("objectgroup/object") is not None:
            haben.add(int(tile.get("id")))
    soll = {r * cols + c for (c, r) in mapgen.WALL_TILES}
    if haben != soll:
        fehler.append("Tileset: Kollisionskacheln %s statt %s"
                      % (sorted(haben), sorted(soll)))
    return len(haben)


def main():
    if not os.path.exists(TILED):
        print("Tiled nicht gefunden:", TILED)
        return 2

    out = os.path.join(export_tiled.ROOT, "tiled_export")
    os.makedirs(out, exist_ok=True)
    cols, rows = export_tiled.atlas_png(os.path.join(out, export_tiled.PNG_NAME))
    tilesets = export_tiled.schreibe_tilesets(out, cols, rows)
    tsx = os.path.join(out, export_tiled.TSX_NAME)

    fehler = []
    n = pruefe_tsx(tsx, cols, fehler)
    print("Gelaende-Tileset: %d Mauerkacheln mit Kollisionsflaeche" % n)
    print("Mitgeliefert    : %d Tilesets, %d Kacheln"
          % (len(tilesets), sum(k for _, k in tilesets)))
    # Jedes zusaetzliche Tileset muss existieren und sein Bild finden.
    for tsx_name, _k in tilesets:
        pfad = os.path.join(out, tsx_name)
        if not os.path.exists(pfad):
            fehler.append("Tileset fehlt: " + tsx_name); continue
        bild = ET.parse(pfad).getroot().find("image").get("source")
        if not os.path.exists(os.path.join(out, bild)):
            fehler.append("Bild fehlt: %s (aus %s)" % (bild, tsx_name))
    print()
    print("%-34s %6s %8s %8s" % ("DATEI", "GROESSE", "MAUERN", "OBJEKTE"))

    proben = [("voll", None, 4242, "gespiegelt"),
              ("voll", None, 77, "raeume"),
              ("voll", None, 11, "labyrinth"),
              ("abs", "klein", 7, "hoehle"),
              ("abs", "klein", 3, "streu"),
              ("abs", "mittel", 100, None),
              ("abs", "mittel", 5, "katakomben"),
              ("abs", "gross", 42, None),
              ("abs", "gross", 8, "spirale")]

    for art, groesse, seed, mode in proben:
        if art == "voll":
            bp = mapgen.generate(seed, mode)
            name = "pruef_karte_%s_%d.tmx" % (bp.mode, seed)
        else:
            bp = mapgen.generate_section(seed, mode, groesse)
            name = "pruef_abschnitt_%s_%s_%d.tmx" % (groesse, bp.mode, seed)
        pfad = os.path.join(out, name)
        export_tiled.write_tmx(pfad, bp, cols, tilesets)
        mauern, objekte = pruefe(bp, pfad, cols, fehler, name)
        print("%-34s %3dx%-3d %6d %8d" % (name, bp.w, bp.h, mauern, objekte))
        os.remove(pfad)

    print()
    if fehler:
        for f in fehler:
            print("FEHLER:", f)
        return 1
    print("TILED-PRUEFUNG OK - Tiled liest alle Dateien, und der Inhalt")
    print("stimmt mit dem Gitter ueberein, aus dem er entstanden ist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
