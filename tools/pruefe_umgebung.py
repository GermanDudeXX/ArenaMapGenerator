"""Prueft, dass die neu gestartete .exe keine Wegweiser auf den alten
Entpackordner erbt.

Das ist der Test, der beim letzten Mal gefehlt hat. `pruefe_selbstersatz.py`
prueft, *dass* getauscht wird - und es wurde getauscht, die Datei stimmte
hinterher. Trotzdem meldete die neu gestartete Fassung beim Benutzer
"Failed to load Python DLL python313.dll".

Der Grund: PyInstaller sagt seinem Kindprozess ueber Umgebungsvariablen
(`_PYI_ARCHIVE_FILE`, `_PYI_APPLICATION_HOME_DIR`, ...), wo die entpackte
Laufzeit liegt. Die erbt jeder weitere Prozess - die cmd.exe des Updates
und ueber deren `start` auch die neue .exe. Die sucht ihre Laufzeit dann
im Ordner der *alten* Fassung, den die alte Fassung beim Beenden loescht.

Damit ist es ein Wettlauf: mal ist der Ordner noch da und alles geht gut,
mal nicht. Ein Test, der nur das Ergebnis des Tauschs anschaut, sieht das
nie. Dieser hier schaut auf die Ursache und ist deshalb eindeutig.

Geprueft wird die echte Kette: .exe -> cmd.exe -> .exe, ueber dieselbe
Funktion, die auch das Update benutzt.

Aufruf:  python tools/pruefe_umgebung.py [pfad/zur/ArenaMapTool.exe]
"""
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VORGABE = os.path.join(ROOT, "dist", "ArenaMapTool.exe")


def main():
    exe = sys.argv[1] if len(sys.argv) > 1 else VORGABE
    if not os.path.exists(exe):
        print("Keine .exe:", exe)
        return 2

    fehler = []
    tmp = tempfile.mkdtemp(prefix="arena_umgebung_")

    # 1. Was sieht die .exe selbst? Hier *muessen* Variablen stehen -
    #    sonst prueft der zweite Teil gegen nichts und waere wertlos.
    p = subprocess.run([exe, "--umgebung"], capture_output=True, text=True,
                       timeout=120)
    try:
        eigen = json.loads(p.stdout.strip() or "{}")
    except ValueError:
        print("Unlesbare Ausgabe:", p.stdout[:200], p.stderr[:200])
        return 1
    print("Die .exe selbst erbt %d Variablen:" % len(eigen))
    for k in sorted(eigen):
        print("   %-28s %s" % (k, eigen[k][:70]))
    if not eigen:
        fehler.append("Die .exe erbt gar nichts - der Test prueft ins Leere. "
                      "Entweder ist die .exe nicht gepackt, oder PyInstaller "
                      "hat die Variablennamen geaendert.")

    def kette(nummer, roh_weg):
        """Einmal .exe -> cmd.exe -> .exe laufen lassen und mitlesen."""
        ziel = os.path.join(tmp, "kind%d.json" % nummer)
        befehl = [exe, "--umgebung-kette", ziel]
        if roh_weg:
            befehl.append("--umgebung-roh")
        subprocess.run(befehl, capture_output=True, text=True, timeout=120)
        for _ in range(40):
            time.sleep(0.5)
            if os.path.exists(ziel) and os.path.getsize(ziel) > 0:
                break
        if not os.path.exists(ziel):
            return None
        text = open(ziel, encoding="utf-8", errors="replace").read().strip()
        try:
            return json.loads(text or "{}")
        except ValueError:
            return None

    # Worauf es ankommt, ist nicht, *ob* die Variablen im neuen Prozess
    # stehen - der Bootloader setzt sie fuer sein eigenes Kind selbst und
    # muss das auch. Es kommt darauf an, *worauf sie zeigen*: auf einen
    # frisch entpackten eigenen Ordner, nicht auf den der alten Fassung.
    heim = eigen.get("_PYI_APPLICATION_HOME_DIR", "")

    # 2. Der alte Weg als Vergleich. Ohne ihn wuesste niemand, ob dieser
    #    Test ueberhaupt etwas faengt - genau daran ist die letzte
    #    Pruefung gescheitert.
    print()
    alt = kette(1, True)
    if alt:
        print("alter Weg  (Popen ohne eigene Umgebung): startete, Heimat %s"
              % alt.get("_PYI_APPLICATION_HOME_DIR", "?"))
        if alt.get("_PYI_APPLICATION_HOME_DIR") == heim:
            print("           -> uebernimmt den Ordner der alten Fassung, "
                  "das kracht sobald die alte ihn aufraeumt")
        else:
            # Kein Fehler, sondern der Grund, warum dieser Fehler so
            # schwer zu fassen ist: der Starter entscheidet nicht immer
            # gleich. Der Vergleichsfall ist deshalb eine Beobachtung,
            # keine Bedingung - sonst schlaege die Pruefung mal so und
            # mal so aus, und das waere schlimmer als kein Test.
            print("           -> kam diesmal mit eigenem Ordner hoch "
                  "(der Fehler ist ein Wettlauf, nicht immer sichtbar)")
    else:
        # Genau das ist der Fehlerfall des Benutzers: die .exe kommt gar
        # nicht hoch. Sie sucht ihre Laufzeit im geerbten Ordner, der zu
        # dem Zeitpunkt meist schon geloescht ist - "Failed to load Python
        # DLL python313.dll". Sie schreibt deshalb nichts.
        print("alter Weg  (Popen ohne eigene Umgebung): kam nicht hoch "
              "(genau der Fehler des Benutzers)")

    # 3. Und der Weg, den das Update wirklich geht.
    kind = kette(2, False)
    if not kind:
        fehler.append("Die neu gestartete .exe kam nicht hoch")
    else:
        eigenes = kind.get("_PYI_APPLICATION_HOME_DIR", "")
        print("neuer Weg  (starte_losgeloest)         : startete, Heimat %s"
              % (eigenes or "?"))
        if eigenes == heim:
            fehler.append("Die neu gestartete .exe benutzt den Entpackordner "
                          "der alten Fassung (%s) - genau das kracht, sobald "
                          "die alte ihn aufraeumt" % heim)
        elif not eigenes:
            fehler.append("Die neu gestartete .exe hat keinen eigenen "
                          "Entpackordner gemeldet")
        else:
            print("           -> eigener Ordner, unabhaengig von der alten "
                  "Fassung")

    for name in os.listdir(tmp):
        try:
            os.remove(os.path.join(tmp, name))
        except OSError:
            pass
    try:
        os.rmdir(tmp)
    except OSError:
        pass

    print()
    if fehler:
        for f in fehler:
            print("FEHLER:", f)
        return 1
    print("UMGEBUNG OK - die neu gestartete .exe startet mit sauberer "
          "Umgebung und findet ihre eigene Laufzeit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
