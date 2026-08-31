"""Prueft, dass die gepackte .exe sich wirklich selbst ersetzen kann.

Das ist der Test, der gefehlt hat. `pruefe_update.py` deckt alles ab, was
sich ohne Bundle pruefen laesst - und genau deshalb lief es dort durch:
ausserhalb der .exe lehnt `tausche_und_starte()` ab, der eigentliche Pfad
wurde also nie ausgefuehrt. Ein Formatierungsfehler darin ist erst beim
Benutzer aufgeschlagen.

Hier laeuft die echte .exe, gegen einen eigenen Server, in einem eigenen
Ordner - mit einer *Kopie*, damit ein Fehlschlag nichts kaputtmacht.

Aufruf:  python tools/pruefe_selbstersatz.py [pfad/zur/ArenaMapTool.exe]
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


def _beende_aus(ordner):
    """Nur Prozesse beenden, deren .exe in diesem Ordner liegt.

    Ueber PowerShell, nicht ueber wmic - das gibt es auf Windows 11
    nicht mehr. Und ausdruecklich nicht ueber den Programmnamen: das
    erwischt auch die Fassung, die jemand anderes gerade offen hat.
    """
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter "
         "\"Name='ArenaMapTool.exe'\" | "
         "ForEach-Object { $_.ProcessId.ToString() + '|' + $_.ExecutablePath }"],
        capture_output=True, text=True)
    for zeile in r.stdout.splitlines():
        if "|" not in zeile:
            continue
        pid, pfad = zeile.split("|", 1)
        if ordner.lower() in pfad.strip().lower():
            subprocess.run(["taskkill", "/PID", pid.strip(), "/F"],
                           capture_output=True)


def main():
    quelle = sys.argv[1] if len(sys.argv) > 1 else VORGABE
    if not os.path.exists(quelle):
        print("Keine .exe:", quelle)
        return 2

    tmp = tempfile.mkdtemp(prefix="arena_update_")
    exe = os.path.join(tmp, "ArenaMapTool.exe")
    shutil.copyfile(quelle, exe)

    original = open(exe, "rb").read()
    # Die "neue Fassung" ist dasselbe Programm mit einem Kennzeichen am
    # Ende. Muss ein echtes Programm sein - eine Attrappe wuerde nur die
    # Pruefung im Updater testen, nicht den Tausch.
    neu = original + b"\n; NEUE FASSUNG 9.9.9\n"
    soll = hashlib.md5(neu).hexdigest()
    print("Kopie in %s" % tmp)
    print("vorher : %s  %d Bytes" % (hashlib.md5(original).hexdigest()[:12],
                                     len(original)))
    print("soll   : %s  %d Bytes" % (soll[:12], len(neu)))

    srv = server(neu)
    api = "http://127.0.0.1:%d/api" % srv.server_port
    log = os.path.join(tmp, "ausgabe.txt")
    fehler = []
    try:
        with open(log, "w") as fh:
            p = subprocess.Popen([exe, "--update-jetzt", "--update-quelle", api],
                                 stdout=fh, stderr=subprocess.STDOUT, cwd=tmp)
            try:
                p.wait(timeout=90)
            except subprocess.TimeoutExpired:
                p.kill()
                fehler.append("Aufruf kehrte nicht zurueck")
        print("Ausgabe:", " | ".join(
            l.strip() for l in open(log, encoding="utf-8", errors="replace")
            if l.strip())[:150])

        # Das Stapelskript wartet auf das Ende des Prozesses und tauscht dann.
        for _ in range(40):
            time.sleep(1)
            if os.path.exists(exe) and \
                    hashlib.md5(open(exe, "rb").read()).hexdigest() == soll:
                break
    finally:
        srv.shutdown()
        # Nur was aus diesem Ordner laeuft. Frueher stand hier ein
        # taskkill nach Programmnamen - das erwischt auch die Fassung,
        # die der Benutzer gerade offen hat, und reisst sie mitten im
        # Entpacken ab ("Failed to load Python DLL").
        _beende_aus(tmp)
        time.sleep(1)

    ist = hashlib.md5(open(exe, "rb").read()).hexdigest()
    print("nachher: %s  %d Bytes" % (ist[:12], os.path.getsize(exe)))
    if ist != soll:
        fehler.append("Datei wurde nicht ersetzt")

    reste = [f for f in os.listdir(tmp)
             if f.endswith((".bat", ".neu.exe"))]
    if reste:
        fehler.append("Reste geblieben: %s" % reste)
    print("Ordner :", sorted(os.listdir(tmp)))

    try:
        shutil.rmtree(tmp)
    except Exception:
        pass

    print()
    if fehler:
        for f in fehler:
            print("FEHLER:", f)
        return 1
    print("SELBSTERSATZ OK - die .exe hat sich ersetzt und neu gestartet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
