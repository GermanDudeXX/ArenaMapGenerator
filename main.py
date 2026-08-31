"""Arena Map Viewer + Generator - Einstiegspunkt.

    python main.py                 handgesetztes Layout (wie bisher)
    python main.py --seed 1234     genau diese generierte Karte
    python main.py --random        eine gewuerfelte Karte
    python main.py --seed 7 --export   nur exportieren, kein Fenster
"""
import argparse
import os
import sys

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")


def selbsttest(ziel):
    """Prueft eine gepackte .exe: Grafiken, Generator, Export.

    Ohne das koennte ich das Bundle nur ansehen, nicht pruefen - und ein
    fehlendes Asset faellt sonst erst dem Benutzer beim Doppelklick auf.
    Schreibt einen Bericht in den Zielordner und liefert 0 oder 1.
    """
    import traceback
    os.makedirs(ziel, exist_ok=True)
    bericht = os.path.join(ziel, "selbsttest.txt")
    zeilen = []
    fehler = []

    def sag(t):
        zeilen.append(t)

    try:
        from za import paths, mapgen
        sag("gefroren   : %s" % paths.frozen())
        sag("assets     : %s" % paths.assets_dir())
        sag("exe_dir    : %s" % paths.exe_dir())

        for datei in ("tiles/Tileset.png", "anim/Fire1.png",
                      "anim/BigDoor_S.png", "objects/misc/torch.png",
                      "objects/boxes/1.png"):
            pfad = os.path.join(paths.assets_dir(), *datei.split("/"))
            if not os.path.exists(pfad):
                fehler.append("Grafik fehlt: " + datei)
        sag("Grafiken   : %d geprueft" % 5)

        sag("Arten      : %d" % len(mapgen.MODE_NAMES))
        for size in (None, "klein", "mittel", "gross"):
            bp = (mapgen.generate(1234) if size is None
                  else mapgen.generate_section(1234, None, size))
            sag("  %-7s %2dx%-2d %-11s %3d%% offen, %d Bloecke"
                % (size or "voll", bp.w, bp.h, bp.mode,
                   round(bp.open_ratio * 100), len(bp.blocks)))

        # Zeichnen und Exportieren - das braucht die Grafiken wirklich.
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        pygame.init()
        pygame.display.set_mode((64, 64))
        from za.world import World
        from za.settings import TILE, C_BG
        from tools import export_tiled as T

        w = World(1234, None, "mittel")
        surf = pygame.Surface((w.w * TILE, w.h * TILE))
        surf.fill(C_BG)
        w.draw(surf, (0, 0))
        pygame.image.save(surf, os.path.join(ziel, "selbsttest.png"))
        sag("Zeichnen   : ok (%d Deko, %d Fackeln)"
            % (len(w.props), len(w.torches)))

        # Menue und Textfeld wirklich benutzen, nicht nur importieren.
        # Ein blosser Import beweist nicht, dass die Eingabe funktioniert.
        from za.menu import Menu
        menu = Menu(size="mittel", gruppe="Dungeon", seed=4242,
                    export_dir=ziel, safe="gross")
        feld = menu.seed_field
        feld.left(); feld.left(); feld.insert("9")
        if feld.text != "42942":
            fehler.append("Textfeld: %r statt '42942'" % feld.text)
        feld.backspace(); feld.home(); feld.delete()
        if feld.text != "242" or menu.seed != 242:
            fehler.append("Textfeld: %r / %r" % (feld.text, menu.seed))
        menu.row = menu.schluessel().index("seed")
        menu.step(1)
        namen = [n for _k, n, _w in menu.zeilen()]
        # Beim Abschnitt faellt die Ecke weg - eine feste Erwartung fuer
        # beide Faelle waere immer fuer einen davon falsch.
        if namen != ["Groesse", "Gruppe", "Art", "Startraum", "Seed",
                     "Schriftgroesse", "Farbschema", "Export-Ordner",
                     "Update"]:
            fehler.append("Menuezeilen Abschnitt: %s" % namen)
        voll = Menu(export_dir=ziel)
        vnamen = [n for _k, n, _w in voll.zeilen()]
        if vnamen != ["Groesse", "Gruppe", "Art", "Startraum",
                      "Startraum-Ecke", "Seed", "Schriftgroesse",
                      "Farbschema", "Export-Ordner", "Update"]:
            fehler.append("Menuezeilen Vollkarte: %s" % vnamen)
        # Eigene Masse blendet zwei Felder ein.
        voll.size_i = [i for i, (n, _) in
                       enumerate(__import__("za.menu", fromlist=["SIZES"]).SIZES)
                       if n == "eigene"][0]
        if "breite" not in voll.schluessel():
            fehler.append("eigene Masse blendet keine Felder ein")
        sag("Menue      : %d Zeilen, Seed-Feld ok (%s), %d Arten waehlbar"
            % (len(namen), menu.seed_text, len(menu.arten())))

        # Startraumgroessen einmal durchrechnen - die aendern den
        # Grundriss und damit alles, was danach kommt.
        for sr in (None, "klein", "mittel", "gross"):
            b2 = mapgen.generate(99, "streu",
                                 safe_size=mapgen.SAFE_SIZES.get(sr))
            sx0, sy0, sx1, sy1 = b2.safe
            soll = mapgen.SAFE_SIZES.get(sr)
            ist = (sx1 - sx0 + 1, sy1 - sy0 + 1)
            if soll and ist != soll:
                fehler.append("Startraum %s: %s statt %s" % (sr, ist, soll))
        sag("Startraum  : 4 Groessen geprueft")

        # Eigene Kartenmasse - die Skalierung der Anzahlen haengt daran,
        # und eine zu kleine Karte hat frueher durch null geteilt.
        for (bw, bh) in ((48, 36), (68, 46), (120, 90), (10, 8)):
            b4 = mapgen.generate(5, "streu", w=bw, h=bh)
            if not b4.blocks:
                fehler.append("eigene Masse %dx%d: keine Karte" % (bw, bh))
        for (bw, bh) in ((8, 8), (24, 18), (80, 60)):
            b5 = mapgen.generate_section(5, "hoehle", (bw, bh))
            if not b5.blocks:
                fehler.append("Abschnitt %dx%d: keine Karte" % (bw, bh))
        sag("Eigene Masse: 7 Groessen geprueft")

        # Anzeige: Schemata und Schriftgroessen muessen alle Farben kennen.
        from za import theme
        for name in theme.NAMEN:
            f = theme.farben(name)
            fehlt = {"text", "dim", "akzent", "aktiv", "kasten", "rand",
                     "balken", "spawn"} - set(f)
            if fehlt:
                fehler.append("Schema %s fehlt %s" % (name, sorted(fehlt)))
        sag("Anzeige    : %d Schemata, %d Schriftgroessen"
            % (len(theme.NAMEN), len(theme.GROESSEN_NAMEN)))

        # Alle vier Ecken: Lage des Raums und Richtung des Tors haengen
        # daran, und daran haengen wiederum die Hitboxen.
        from tools.export_tiled import hitbox_rects
        from za.settings import WALL
        for pos in mapgen.SAFE_POSITIONS:
            b3 = mapgen.generate(99, "streu", safe_pos=pos)
            gedeckt = set()
            for _n, (x, y, bw, bh) in hitbox_rects(b3):
                for yy in range(y, y + bh):
                    for xx in range(x, x + bw):
                        gedeckt.add((xx, yy))
            mauern = {(x, y) for y in range(b3.h) for x in range(b3.w)
                      if b3.grid[y][x] == WALL}
            if gedeckt != mauern:
                fehler.append("Ecke %s: Hitboxen decken nicht (%d/%d)"
                              % (pos, len(gedeckt), len(mauern)))
        sag("Ecken      : 4 geprueft, Hitboxen decken exakt")

        # tkinter wird nur fuer Ordnerdialog und Einfuegen gebraucht -
        # beides Pfade, die der Selbsttest sonst nie beruehrt. Ein
        # zurechtgestutztes Bundle koennte es verlieren, ohne dass es
        # auffaellt, bis jemand F1 drueckt.
        try:
            import tkinter
            wurzel = tkinter.Tk()
            wurzel.withdraw()
            wurzel.destroy()
            from tkinter import filedialog          # noqa: F401
            sag("tkinter    : Fenster und Dateidialog vorhanden")
        except Exception as err:
            fehler.append("tkinter fehlt: %s" % err)

        tiled = os.path.join(ziel, "tiled")
        os.makedirs(tiled, exist_ok=True)
        cols, rows = T.atlas_png(os.path.join(tiled, T.PNG_NAME))
        tilesets = T.schreibe_tilesets(tiled, cols, rows)
        n = T.write_tmx(os.path.join(tiled, "selbsttest.tmx"),
                        w.blueprint, cols, tilesets)
        # Jede .tsx muss ihr Bild danebenliegen haben - im Bundle fehlt
        # sonst genau das, was der Export verspricht.
        import xml.etree.ElementTree as ET
        for tsx, _k in tilesets:
            baum = ET.parse(os.path.join(tiled, tsx))
            bild = baum.getroot().find("image").get("source")
            if not os.path.exists(os.path.join(tiled, bild)):
                fehler.append("Tileset-Bild fehlt: %s" % bild)
        sag("Tiled      : %d Tilesets, %d Kacheln, %d Objekte"
            % (len(tilesets), sum(k for _, k in tilesets), n))
        pygame.quit()
    except Exception:
        fehler.append(traceback.format_exc())

    zeilen.append("")
    zeilen.append("ERGEBNIS: " + ("OK" if not fehler else "FEHLER"))
    zeilen += fehler
    text = os.linesep.join(zeilen)
    with open(bericht, "w", encoding="utf-8") as fh:
        fh.write(text + os.linesep)
    print(text)
    return 0 if not fehler else 1


def mapgen_masse(b, h, abschnitt):
    """Eingegebene Masse begrenzen - fehlende Angabe wird zur Vorgabe."""
    from za import mapgen
    b = b or (mapgen.SECTIONS["mittel"][0] if abschnitt else mapgen.MAP_W)
    h = h or (mapgen.SECTIONS["mittel"][1] if abschnitt else mapgen.MAP_H)
    if abschnitt:
        return (max(8, min(mapgen.MAX_W, b)), max(8, min(mapgen.MAX_H, h)))
    return mapgen.clamp_masse(b, h)


def updaten(quelle, einspielen):
    """Auf der Kommandozeile nach einer neuen Fassung sehen."""
    from za import update as U, paths
    zustand, text, ver, url = U.pruefe(quelle)
    print("Installiert: %s" % U.VERSION)
    print("Ergebnis   : %s - %s" % (zustand, text))
    if zustand != "neu" or not einspielen:
        # "keins" ist kein Fehler des Werkzeugs, sondern eine Auskunft:
        # es gibt noch nichts Neueres. Nur "fehler" ist ein Fehler.
        return 1 if zustand == "fehler" else 0
    if not paths.frozen():
        print("Nur die gepackte .exe kann sich selbst ersetzen.")
        return 1
    ziel = os.path.join(os.path.dirname(os.path.abspath(sys.executable)),
                        "ArenaMapTool.neu.exe")
    print("Lade %s ..." % url)
    U.lade(url, ziel)
    U.tausche_und_starte(ziel)
    print("Wird eingespielt, das Programm startet neu.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Arena Map Viewer + Generator")
    ap.add_argument("--seed", type=int, default=None,
                    help="Seed der generierten Karte")
    ap.add_argument("--random", action="store_true",
                    help="mit gewuerfeltem Seed starten")
    ap.add_argument("--mode", default=None,
                    help="Kartenart erzwingen (--liste zeigt alle)")
    ap.add_argument("--breite", type=int, default=None,
                    help="eigene Kartenbreite in Kacheln")
    ap.add_argument("--hoehe", type=int, default=None,
                    help="eigene Kartenhoehe in Kacheln")
    ap.add_argument("--abschnitt", action="store_true",
                    help="mit --breite/--hoehe: Abschnitt statt Vollkarte")
    ap.add_argument("--startraum", choices=("klein", "mittel", "gross"),
                    default=None,
                    help="Groesse des Startraums (Vorgabe: gewuerfelt)")
    ap.add_argument("--startecke", choices=("oben links", "oben rechts",
                                            "unten links", "unten rechts"),
                    default="oben links", help="Ecke des Startraums")
    ap.add_argument("--version", action="store_true",
                    help="Versionsnummer anzeigen und beenden")
    ap.add_argument("--update", action="store_true",
                    help="nachsehen, ob es eine neuere Fassung gibt")
    ap.add_argument("--update-jetzt", action="store_true",
                    help="pruefen und, wenn neuer, gleich einspielen")
    ap.add_argument("--update-quelle", default=None,
                    help="andere Adresse fuer die Pruefung (zum Testen)")
    ap.add_argument("--selbsttest", metavar="ORDNER", default=None,
                    help="Alles einmal durchrechnen und schreiben, dann "
                         "beenden - prueft die gepackte .exe")
    ap.add_argument("--liste", action="store_true",
                    help="alle Kartenarten auflisten und beenden")
    ap.add_argument("--export", action="store_true",
                    help="Karte als JSON schreiben und beenden (kein Fenster)")
    ap.add_argument("--out", default=None, help="Zielpfad fuer --export")
    args = ap.parse_args(argv)

    if args.version:
        from za.version import VERSION
        from za import paths
        print("ArenaMapTool %s" % VERSION)
        print("gefroren: %s" % paths.frozen())
        print("laeuft aus: %s" % (sys.executable if paths.frozen() else __file__))
        return 0

    if args.update or args.update_jetzt:
        return updaten(args.update_quelle, args.update_jetzt)

    if args.selbsttest:
        return selbsttest(args.selbsttest)

    if args.liste:
        from za import mapgen
        for gruppe in mapgen.GROUPS:
            print("\n%s" % gruppe.upper())
            for name in mapgen.MODE_NAMES:
                spec = mapgen.MODES[name]
                if spec["gruppe"] == gruppe:
                    print("  %-11s %s" % (name, spec["text"]))
        print()
        return 0

    seed = args.seed
    if seed is None and args.random:
        import random
        seed = random.randrange(1, 10 ** 9)

    if args.export:
        # Reiner Batch-Pfad: kein pygame, kein Display. So laesst sich der
        # Generator aus einem Buildskript oder der Engine heraus aufrufen.
        from za import mapgen
        if args.breite or args.hoehe:
            m = mapgen_masse(args.breite, args.hoehe, args.abschnitt)
            if args.abschnitt:
                bp = mapgen.generate_section(seed, args.mode, m)
            else:
                bp = mapgen.generate(
                    seed, args.mode, w=m[0], h=m[1],
                    safe_size=mapgen.SAFE_SIZES.get(args.startraum),
                    safe_pos=args.startecke)
        else:
            bp = mapgen.generate(
                seed, args.mode,
                safe_size=mapgen.SAFE_SIZES.get(args.startraum),
                safe_pos=args.startecke)
        out = args.out or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "export", "map_%d.json" % bp.seed)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        bp.dump_json(out)
        print("Seed %d  Art %s (%s)  %d Bloecke  %d%% offen  %d Spawns"
              % (bp.seed, bp.mode, bp.group, len(bp.blocks),
                 round(bp.open_ratio * 100), len(bp.spawns)))
        print(out)
        return 0

    if args.mode and seed is None:
        # Ein Stil ohne Seed waere sonst wirkungslos - das handgesetzte
        # Layout hat keinen.
        import random
        seed = random.randrange(1, 10 ** 9)

    from za.viewer import Viewer
    masse = None
    groesse = None
    if args.breite or args.hoehe:
        masse = mapgen_masse(args.breite, args.hoehe, args.abschnitt)
        if args.abschnitt:
            groesse, masse = masse, None
    Viewer(seed, args.mode, groesse, args.startraum, args.startecke,
           masse).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
