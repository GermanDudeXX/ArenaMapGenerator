"""Baut das fertige Godot-Paket - eine Karte, ihre Hitboxen, sonst nichts.

Die ganze Kette in einem Aufruf:

  1. Generator laeuft, Atlas und Kartendaten entstehen
  2. Godot baut daraus ArenaMap.tscn und ArenaTileset.tres
  3. Godot prueft die gebaute Szene gegen die Daten
  4. Ergebnis landet in godot_export/arena/

Godot schreibt die Szene selbst, weil `tile_map_data` in einer .tscn ein
Binaerblob ist. Von Hand getippt waere er geraten, und ein Fehler darin
faellt erst dem auf, der die Datei oeffnet.

Aufruf:  python tools/make_godot_package.py --seed 4242
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "godot_export")
BUILD = os.path.join(OUT, "_build")

PROJECT_CFG = """config_version=5

[application]
config/name="ArenaBuild"
config/features=PackedStringArray("4.4", "GL Compatibility")

[rendering]
renderer/rendering_method="mobile"
textures/canvas_textures/default_texture_filter=0
"""


def find_godot(explicit=None):
    if explicit:
        return explicit
    candidates = [
        os.path.join(os.path.expanduser("~"), "tools", "godot",
                     "Godot_v4.7.1-stable_win64_console.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    found = shutil.which("godot")
    if found:
        return found
    raise SystemExit(
        "Godot nicht gefunden. Pfad mit --godot angeben.")


def _preview(seed, mode, dest):
    """Dieselbe Karte durch den pygame-Renderer - das Soll-Bild."""
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    from za.world import World
    from za.settings import MAP_W, MAP_H, TILE, C_BG

    pygame.init()
    pygame.display.set_mode((64, 64))
    world = World(seed, mode)
    surf = pygame.Surface((MAP_W * TILE, MAP_H * TILE))
    surf.fill(C_BG)
    world.draw(surf, (0, 0))
    pygame.image.save(surf, dest)
    pygame.quit()


def run(godot, project, *args):
    cmd = [godot, "--headless", "--path", project] + list(args)
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(description="Godot-Paket bauen")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--mode", default=None)
    ap.add_argument("--godot", default=None)
    a = ap.parse_args(argv)

    godot = find_godot(a.godot)

    # --- 1. Generator ----------------------------------------------------
    from tools.export_godot import export
    data, json_path, missing, extra, doubled = export(a.seed, a.mode)
    if missing or extra or doubled:
        raise SystemExit("Hitboxen decken die Mauern nicht sauber ab - "
                         "Abbruch (%d fehlen, %d ueber Boden, %d doppelt)"
                         % (len(missing), len(extra), len(doubled)))
    print("1/4  Generator: Seed %d, Art %s, %d Kacheln, %d Bodies"
          % (data["seed"], data["mode"], len(data["cells"]),
             len(data["walls"]) + len(data["obstacles"])))

    # --- 2. Staging-Projekt ---------------------------------------------
    stage = tempfile.mkdtemp(prefix="arena_godot_")
    arena = os.path.join(stage, "arena")
    os.makedirs(arena)
    with open(os.path.join(stage, "project.godot"), "w", encoding="utf-8") as fh:
        fh.write(PROJECT_CFG)
    shutil.copy(os.path.join(BUILD, "ArenaTileset.png"), arena)
    shutil.copy(json_path, arena)
    for gd in ("build_scene.gd", "verify_scene.gd"):
        shutil.copy(os.path.join(HERE, gd), stage)

    p = run(godot, stage, "--import")
    if p.returncode != 0:
        print(p.stdout, p.stderr)
        raise SystemExit("Godot-Import fehlgeschlagen")
    print("2/4  Godot: Atlas importiert")

    # --- 3. Szene bauen --------------------------------------------------
    p = run(godot, stage, "--script", "res://build_scene.gd")
    line = [l for l in p.stdout.splitlines() if l.startswith("OK")]
    if p.returncode != 0 or not line:
        print(p.stdout, p.stderr)
        raise SystemExit("Szene bauen fehlgeschlagen")
    print("3/4  Godot baut Szene: %s" % line[0][3:].strip())

    # --- 4. Szene pruefen ------------------------------------------------
    p = run(godot, stage, "--script", "res://verify_scene.gd")
    if p.returncode != 0 or "PRUEFUNG OK" not in p.stdout:
        print(p.stdout, p.stderr)
        raise SystemExit("Pruefung fehlgeschlagen")
    detail = [l for l in p.stdout.splitlines() if l.startswith("Bodies")]
    print("4/4  Godot prueft Szene: OK  (%s)"
          % (detail[0] if detail else ""))

    # --- Ergebnis einsammeln --------------------------------------------
    dest = os.path.join(OUT, "arena")
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    for name in ("ArenaMap.tscn", "ArenaTileset.tres",
                 "ArenaTileset.png", "ArenaTileset.png.import"):
        src = os.path.join(arena, name)
        if os.path.exists(src):
            shutil.copy(src, dest)
    shutil.rmtree(stage, ignore_errors=True)

    # --- Vorschau --------------------------------------------------------
    # Liegt neben dem Paket, nicht darin: in res://arena/ wuerde Godot sie
    # als Textur importieren, und sie gehoert nicht zur Karte.
    _preview(data["seed"], data.get("mode"),
             os.path.join(OUT, "VORSCHAU.png"))

    print()
    print("Fertig:", dest)
    for name in sorted(os.listdir(dest)):
        print("   %-28s %7d Bytes"
              % (name, os.path.getsize(os.path.join(dest, name))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
