"""Wo liegt was - im Projekt und in der gepackten .exe.

Als Skript ist beides derselbe Ordner. In der .exe nicht: PyInstaller
packt die Grafiken beim Start in ein Temp-Verzeichnis aus, das nach dem
Beenden wieder verschwindet. Dorthin zu exportieren waere ein
Fehlschlag, den niemand bemerkt - die Datei ist geschrieben und nach dem
Schliessen weg.

Deshalb zwei getrennte Fragen:

* `assets_dir()` - woher die Grafiken kommen (im Bundle: das Temp-Verzeichnis)
* `output_dir()` - wohin Ergebnisse gehen (vom Benutzer gewaehlt, gemerkt)

Der gewaehlte Ordner landet in %APPDATA%, nicht neben der .exe: wer sie
nach Programme legt, hat dort keine Schreibrechte.
"""
import json
import os
import sys

APP = "ArenaMapGen"


def frozen():
    """Laeuft das hier aus einer gepackten .exe?"""
    return getattr(sys, "frozen", False)


def assets_dir():
    """Ordner mit den Grafiken."""
    if frozen():
        return os.path.join(sys._MEIPASS, "assets")
    return os.path.join(_project_root(), "assets")


def _project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def exe_dir():
    """Ordner, in dem die .exe liegt - bzw. das Projekt."""
    if frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return _project_root()


def config_file():
    basis = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(basis, APP, "einstellungen.json")


def default_output():
    return os.path.join(exe_dir(), "ArenaExport")


def load_settings():
    """Alle gemerkten Einstellungen. Fehlt die Datei, sind es die Vorgaben."""
    vorgabe = {"export": default_output(), "theme": "dunkel",
               "hud": "normal"}
    try:
        with open(config_file(), encoding="utf-8") as fh:
            gespeichert = json.load(fh)
        if isinstance(gespeichert, dict):
            vorgabe.update({k: v for k, v in gespeichert.items()
                            if k in vorgabe})
    except Exception:
        pass
    return vorgabe


def save_settings(**werte):
    """Einstellungen ergaenzen, nicht ersetzen.

    Wer nur die Farbe aendert, soll nicht den Ordner verlieren - deshalb
    erst lesen, dann zusammenfuehren.
    """
    daten = load_settings()
    daten.update(werte)
    try:
        ziel = config_file()
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with open(ziel, "w", encoding="utf-8") as fh:
            json.dump(daten, fh, indent=1)
        return True
    except Exception:
        return False


def load_output():
    """Gemerkter Zielordner, sonst der Vorgabeort."""
    try:
        with open(config_file(), encoding="utf-8") as fh:
            pfad = json.load(fh).get("export")
        if pfad and os.path.isdir(os.path.dirname(pfad) or "."):
            return pfad
    except Exception:
        # Eine kaputte oder fehlende Einstellungsdatei ist kein Fehler,
        # der jemanden interessiert - dann eben der Vorgabeort.
        pass
    return default_output()


def save_output(pfad):
    return save_settings(export=pfad)


def kuerzen(pfad, laenge=44):
    """Langen Pfad fuer die Anzeige eindampfen, Ende behalten."""
    if len(pfad) <= laenge:
        return pfad
    return "..." + pfad[-(laenge - 3):]


def waehle_ordner(start=None):
    """Ordnerauswahl. Gibt den Pfad zurueck oder None bei Abbruch.

    tkinter steckt in der Standardbibliothek und wird mitgepackt. Fehlt
    es doch, bleibt der bisherige Ordner - der Viewer darf daran nicht
    haengenbleiben.
    """
    try:
        import tkinter
        from tkinter import filedialog
    except Exception:
        return None
    wurzel = None
    try:
        wurzel = tkinter.Tk()
        wurzel.withdraw()
        wurzel.attributes("-topmost", True)
        pfad = filedialog.askdirectory(
            title="Ordner fuer die Exporte waehlen",
            initialdir=start or exe_dir(), mustexist=False)
        return pfad or None
    except Exception:
        return None
    finally:
        if wurzel is not None:
            try:
                wurzel.destroy()
            except Exception:
                pass
