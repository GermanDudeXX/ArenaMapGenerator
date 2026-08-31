"""Die .exe ausliefern, ohne eine laufende Fassung zu zerreissen.

`shutil.copyfile` kuerzt das Ziel sofort auf null und schreibt dann neu.
Eine PyInstaller-Datei liest ihr Archiv aber aus sich selbst, waehrend
sie laeuft - wer sie in genau diesem Moment startet, bekommt eine halb
geschriebene Datei und die Meldung "Failed to load Python DLL".

Deshalb: daneben schreiben, dann umbenennen. `os.replace` ist auf NTFS
atomar; eine laufende Instanz behaelt ihre alte Datei, jeder neue Start
bekommt die neue.
"""
import hashlib
import os
import shutil
import sys

QUELLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "dist", "ArenaMapTool.exe")


def liefere(quelle, ziel):
    ordner = os.path.dirname(ziel)
    os.makedirs(ordner, exist_ok=True)
    zwischen = os.path.join(ordner, ".ArenaMapTool.neu")
    shutil.copyfile(quelle, zwischen)
    os.replace(zwischen, ziel)          # atomar auf demselben Laufwerk
    return hashlib.md5(open(ziel, "rb").read()).hexdigest()


def main():
    ziele = sys.argv[1:] or [r"C:\Users\budzm\Downloads\ArenaMapTool.exe"]
    soll = hashlib.md5(open(QUELLE, "rb").read()).hexdigest()
    print("Quelle: %s  %s" % (QUELLE, soll[:12]))
    schlecht = 0
    for z in ziele:
        ist = liefere(QUELLE, z)
        print("  %-52s %s %s" % (z, ist[:12], "OK" if ist == soll else "ABWEICHUNG"))
        schlecht += ist != soll
    return 1 if schlecht else 0


if __name__ == "__main__":
    sys.exit(main())
