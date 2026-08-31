"""Prueft, ob die .exe nach dem Selbsttausch auch wirklich wieder hochkommt.

`pruefe_selbstersatz.py` prueft, *dass* getauscht wird - und das stimmte
auch: die Datei war hinterher richtig. Trotzdem meldete die neu gestartete
Fassung beim Benutzer "Failed to load Python DLL python313.dll". Ein Test,
der nur die Bytes der Datei anschaut, sieht das nie.

Hier laeuft deshalb der ganze Weg und am Ende die einzige Frage, auf die
es ankommt: laeuft danach ein Prozess aus diesem Ordner?

Und zwar mehrfach, denn der Verdacht ist ein Wettlauf - einmal Glueck
haben beweist nichts.

Aufruf:  python tools/pruefe_neustart.py [pfad/zur/exe] [anlaeufe]
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VORGABE = os.path.join(ROOT, "dist", "ArenaMapTool.exe")


def server(neue_bytes):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == "/api":
                basis = "http://127.0.0.1:%d" % self.server.server_port
                roh = json.dumps({
                    "tag_name": "v9.9.9",
                    "assets": [{"name": "ArenaMapTool.exe",
                                "browser_download_url": basis + "/exe"}],
                }).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(roh)))
                self.end_headers()
                self.wfile.write(roh)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(neue_bytes)))
            self.end_headers()
            self.wfile.write(neue_bytes)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def prozesse_aus(ordner):
    """PIDs, deren .exe in diesem Ordner liegt. Nie nach Namen allein -
    das erwischt auch die Fassung, die der Benutzer offen hat."""
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='ArenaMapTool.exe'\" | "
         "ForEach-Object { $_.ProcessId.ToString() + '|' + $_.ExecutablePath }"],
        capture_output=True, text=True)
    raus = []
    for zeile in r.stdout.splitlines():
        if "|" in zeile:
            pid, pfad = zeile.split("|", 1)
            if ordner.lower() in pfad.strip().lower():
                raus.append(int(pid.strip()))
    return raus


def beende(ordner):
    for pid in prozesse_aus(ordner):
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True)


def anlauf(quelle, nummer):
    """Einmal tauschen lassen und nachsehen, ob danach etwas laeuft."""
    tmp = tempfile.mkdtemp(prefix="arena_neustart_")
    exe = os.path.join(tmp, "ArenaMapTool.exe")
    shutil.copyfile(quelle, exe)
    neu = open(exe, "rb").read() + b"\n; NEUE FASSUNG 9.9.9\n"
    soll = hashlib.md5(neu).hexdigest()

    srv = server(neu)
    api = "http://127.0.0.1:%d/api" % srv.server_port
    getauscht = False
    laeuft = False
    try:
        subprocess.run([exe, "--update-jetzt", "--update-quelle", api],
                       capture_output=True, text=True, timeout=180, cwd=tmp)
        for _ in range(60):
            time.sleep(1)
            if os.path.exists(exe) and \
                    hashlib.md5(open(exe, "rb").read()).hexdigest() == soll:
                getauscht = True
                break
        # Die neu gestartete Fassung braucht einen Moment, bis sie ihr
        # Fenster hat. Kommt sie gar nicht hoch, steht hier nie etwas.
        for _ in range(30):
            time.sleep(1)
            if prozesse_aus(tmp):
                laeuft = True
                break
    except subprocess.TimeoutExpired:
        pass
    finally:
        srv.shutdown()
        beende(tmp)
        time.sleep(1)
        try:
            shutil.rmtree(tmp)
        except OSError:
            pass

    print("  Anlauf %d: getauscht %-5s  laeuft danach %-5s  %s"
          % (nummer, "ja" if getauscht else "NEIN",
             "ja" if laeuft else "NEIN",
             "" if (getauscht and laeuft) else "<-- so sieht der Fehler aus"))
    return getauscht, laeuft


def main():
    quelle = sys.argv[1] if len(sys.argv) > 1 else VORGABE
    anlaeufe = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    if not os.path.exists(quelle):
        print("Keine .exe:", quelle)
        return 2

    print("Pruefe %s" % quelle)
    print("%d Anlaeufe - ein einzelner Erfolg beweist bei einem Wettlauf "
          "nichts." % anlaeufe)
    print()
    ergebnisse = [anlauf(quelle, i + 1) for i in range(anlaeufe)]
    print()
    getauscht = sum(1 for g, _ in ergebnisse if g)
    lief = sum(1 for _, l in ergebnisse if l)
    print("getauscht: %d/%d    danach gelaufen: %d/%d"
          % (getauscht, anlaeufe, lief, anlaeufe))
    if getauscht < anlaeufe:
        print("FEHLER: der Tausch selbst schlug fehl")
        return 1
    if lief < anlaeufe:
        print("FEHLER: die neue Fassung kam nicht hoch - genau der Fehler, "
              "den der Benutzer sieht")
        return 1
    print("NEUSTART OK - nach jedem Tausch lief die neue Fassung")
    return 0


if __name__ == "__main__":
    sys.exit(main())
