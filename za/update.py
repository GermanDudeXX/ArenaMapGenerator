"""Selbstaktualisierung: nachsehen, ob es eine neuere .exe gibt.

Drei Quellen, weil die Wahl nicht technisch ist, sondern eine Frage
davon, wer aktualisieren koennen soll:

* **oeffentliches GitHub-Repo** - jeder, der die .exe hat, bekommt
  Updates. Kein Schluessel noetig.
* **privates GitHub-Repo** - nur wer einen Zugangsschluessel hinterlegt
  hat. Das ist normalerweise nur der Entwickler selbst.
* **beliebige URL** - eine `version.json` irgendwo abgelegt. Wie die
  oeffentliche Variante, ohne GitHub.

Zum Schluessel, ausdruecklich: er wird **nicht** mitgepackt, sondern zur
Laufzeit aus `%APPDATA%\\ArenaMapGen\\token.txt` gelesen. Ein Schluessel
in der .exe waere fuer jeden lesbar, der sie bekommt - eine .exe von
PyInstaller ist ein Archiv, kein Tresor. Wer die Datei weitergibt, gaebe
seinen GitHub-Zugang mit weiter.

Deshalb gilt: bei einem privaten Repo koennen **Empfaenger der .exe nicht
aktualisieren**. Das ist keine Einschraenkung dieses Moduls, das ist die
Bedeutung von "privat".
"""
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

from . import paths
from .version import VERSION

REPO = "GermanDudeXX/ArenaMapGenerator"
API = "https://api.github.com/repos/%s/releases/latest" % REPO

# Kurz, damit ein hakendes Netz den Viewer nicht einfriert.
TIMEOUT = 12


# ------------------------------------------------------------- Versionen
def zerlege(text):
    """"v1.2.3" oder "1.2" zu (1, 2, 3). Unlesbares wird (0,)."""
    zahlen = re.findall(r"\d+", str(text or ""))
    return tuple(int(z) for z in zahlen[:4]) or (0,)


def neuer_als(dort, hier):
    a, b = zerlege(dort), zerlege(hier)
    laenge = max(len(a), len(b))
    a += (0,) * (laenge - len(a))
    b += (0,) * (laenge - len(b))
    return a > b


# --------------------------------------------------------------- Schluessel
def token_datei():
    return os.path.join(os.path.dirname(paths.config_file()), "token.txt")


def token():
    """Zugangsschluessel, falls hinterlegt. Sonst None."""
    try:
        with open(token_datei(), encoding="utf-8") as fh:
            t = fh.read().strip()
        return t or None
    except Exception:
        return None


# ------------------------------------------------------------------ Abruf
def _hole_json(url, mit_token=True):
    kopf = {"User-Agent": "ArenaMapTool/%s" % VERSION,
            "Accept": "application/vnd.github+json"}
    t = token() if mit_token else None
    if t:
        kopf["Authorization"] = "Bearer " + t
    req = urllib.request.Request(url, headers=kopf)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


def _warum_404(ziel):
    """Unterscheiden: Repo unerreichbar oder nur noch kein Release."""
    if "api.github.com" not in ziel:
        return "Nichts gefunden unter %s" % ziel
    try:
        _hole_json("https://api.github.com/repos/%s" % REPO)
    except Exception:
        return ("Repo nicht erreichbar. Privat? Dann muss ein Schluessel in "
                "%s liegen." % token_datei())
    return ("Repo erreichbar, aber noch kein Release veroeffentlicht. "
            "Sobald eines mit angehaengter .exe da ist, meldet sich das hier.")


def pruefe(url=None):
    """Nachsehen, ob es etwas Neueres gibt.

    Rueckgabe: (zustand, text, version, download_url). `zustand` ist
    "neu", "aktuell", "keins" oder "fehler" - der Aufrufer soll nicht
    Texte auswerten muessen.
    """
    ziel = url or API
    try:
        daten = _hole_json(ziel)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # 404 heisst bei GitHub zweierlei: es gibt nichts, oder man
            # darf es nicht sehen. Welches von beidem, verraet die Frage
            # nach dem Repo selbst - sonst raet die Meldung, und geraten
            # hat sie bei einem oeffentlichen Repo ohne Release falsch.
            return ("keins", _warum_404(ziel), None, None)
        if e.code in (401, 403):
            return ("fehler", "Zugang verweigert (HTTP %d). Schluessel "
                              "falsch oder abgelaufen." % e.code, None, None)
        return ("fehler", "HTTP %d" % e.code, None, None)
    except Exception as e:
        return ("fehler", "Kein Netz: %s" % type(e).__name__, None, None)

    # Eine version.json darf dieselben Felder benutzen wie GitHub - dann
    # braucht der Rest hier keine Fallunterscheidung.
    version = daten.get("tag_name") or daten.get("version")
    laden = None
    for a in daten.get("assets", []) or []:
        if str(a.get("name", "")).lower().endswith(".exe"):
            laden = a.get("browser_download_url") or a.get("url")
            break
    if not laden:
        laden = daten.get("url_exe") or daten.get("download_url")

    if not version:
        return ("keins", "Kein Release veroeffentlicht", None, None)
    if not neuer_als(version, VERSION):
        return ("aktuell", "Bereits aktuell (%s)" % VERSION, version, laden)
    if not laden:
        return ("fehler", "Release %s hat keine .exe angehaengt" % version,
                version, None)
    return ("neu", "Version %s verfuegbar (installiert: %s)"
            % (version, VERSION), version, laden)


def lade(url, ziel, melde=None):
    """Datei laden und pruefen, dass es ueberhaupt ein Programm ist.

    Der Groessen- und Kopfbytentest ist kein Sicherheitsmerkmal, sondern
    ein Schutz gegen das Naheliegende: eine Fehlerseite oder ein
    abgebrochener Download, der sonst als .exe an die Stelle der alten
    truete.
    """
    kopf = {"User-Agent": "ArenaMapTool/%s" % VERSION,
            "Accept": "application/octet-stream"}
    t = token()
    if t:
        kopf["Authorization"] = "Bearer " + t
    req = urllib.request.Request(url, headers=kopf)
    with urllib.request.urlopen(req, timeout=TIMEOUT * 5) as r:
        gesamt = int(r.headers.get("Content-Length") or 0)
        geladen = 0
        with open(ziel, "wb") as fh:
            while True:
                brocken = r.read(65536)
                if not brocken:
                    break
                fh.write(brocken)
                geladen += len(brocken)
                if melde and gesamt:
                    melde(geladen / float(gesamt))

    with open(ziel, "rb") as fh:
        magie = fh.read(2)
    if magie != b"MZ" or os.path.getsize(ziel) < 1_000_000:
        os.remove(ziel)
        raise ValueError("Das Geladene ist kein Windows-Programm")
    return ziel


# PyInstaller sagt seinem eigenen Kindprozess ueber Umgebungsvariablen,
# wo die entpackte Laufzeit liegt. Diese Variablen erbt *jeder* Prozess,
# den wir starten - also auch die cmd.exe des Updates und ueber sie die
# neu gestartete .exe. Die sucht ihre Laufzeit dann in dem Entpackordner
# der *alten* Fassung, den die alte Fassung beim Beenden loescht.
#
# Ergebnis: "Failed to load Python DLL python313.dll" - und zwar als
# Wettlauf. Kommt der Neustart, bevor der Ordner geloescht ist, geht es
# gut; sonst nicht. Genau deshalb lief die Pruefung hier durch und beim
# Benutzer krachte es trotzdem.
PYI_VARS = ("_PYI_ARCHIVE_FILE", "_PYI_APPLICATION_HOME_DIR",
            "_PYI_PARENT_PROCESS_LEVEL", "_PYI_SPLASH_IPC",
            "_MEIPASS", "_MEIPASS2")


def saubere_umgebung():
    """Die Umgebung ohne die Wegweiser auf unseren Entpackordner."""
    return {k: v for k, v in os.environ.items()
            if k not in PYI_VARS and not k.startswith("_PYI_")}


def geerbte_pyi_vars():
    """Was dieser Prozess an solchen Variablen sieht. Fuer die Pruefung."""
    return {k: v for k, v in os.environ.items()
            if k in PYI_VARS or k.startswith("_PYI_")}


def starte_losgeloest(befehl):
    """Einen Prozess starten, der uns ueberlebt - mit sauberer Umgebung.

    Ausgabekanaele ausdruecklich abhaengen. Ohne das erbt der neue Prozess
    die Pipes dieses Prozesses, und wer die .exe von aussen aufruft und
    ihre Ausgabe mitliest, wartet ewig - die Pipe schliesst nie.
    """
    return subprocess.Popen(
        befehl, env=saubere_umgebung(),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, close_fds=True,
        creationflags=(getattr(subprocess, "DETACHED_PROCESS", 0)
                       | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)))


def tausche_und_starte(neu):
    """Die laufende .exe ersetzen.

    Windows laesst eine laufende Datei nicht ueberschreiben. Also
    uebernimmt ein kleines Stapelskript: es wartet, bis dieser Prozess
    weg ist, schiebt die neue Datei an die alte Stelle, startet sie und
    loescht sich selbst.
    """
    if not paths.frozen():
        raise RuntimeError("Nur die gepackte .exe kann sich ersetzen")
    alt = os.path.abspath(sys.executable)
    bat = os.path.join(os.path.dirname(alt), "_update.bat")

    # Zeilenweise zusammengesetzt, ohne %-Formatierung. Vorher stand hier
    # ein Block aneinandergrenzender Zeichenketten mit einem % am Ende -
    # Python klebt solche Literale aber *vor* der Formatierung zusammen,
    # und damit geriet das %PID% des Stapelskripts mit hinein. Ergebnis
    # war ein Absturz genau in dem Moment, in dem das Update laufen soll.
    # Nicht auf die eigene Prozessnummer warten, sondern den Tausch so
    # lange wiederholen, bis er gelingt. Grund: eine PyInstaller-Datei
    # laeuft als *zwei* Prozesse - der Starter haelt die .exe offen,
    # waehrend der eigentliche Code im Kindprozess laeuft. Auf die eigene
    # PID zu warten reichte nicht, die Datei blieb gesperrt und der Tausch
    # scheiterte lautlos.
    zeilen = [
        "@echo off",
        # Zweiter Riegel gegen dasselbe: selbst wenn diese cmd.exe die
        # Variablen doch geerbt haette, gibt sie sie nicht weiter.
    ] + ['set "' + v + '="' for v in PYI_VARS] + [
        "set N=0",
        ":versuch",
        'move /Y "' + neu + '" "' + alt + '" >nul 2>&1',
        "if not errorlevel 1 goto fertig",
        "set /a N+=1",
        "if %N% GEQ 60 goto aufgeben",
        "ping -n 2 127.0.0.1 >nul",
        "goto versuch",
        ":fertig",
        # Kurz Luft lassen, bevor die neue Fassung startet: der alte
        # Prozess raeumt beim Beenden noch seinen Entpackordner weg.
        "ping -n 3 127.0.0.1 >nul",
        'start "" "' + alt + '"',
        'del "%~f0"',
        "exit /b 0",
        ":aufgeben",
        # Bleibt die alte Fassung gesperrt, lieber nichts anfassen und
        # die geladene Datei liegenlassen, als halb zu tauschen.
        'del "%~f0"',
    ]
    with open(bat, "w", encoding="ascii", newline="") as fh:
        fh.write("\r\n".join(zeilen) + "\r\n")

    starte_losgeloest(["cmd", "/c", bat])
    return bat
