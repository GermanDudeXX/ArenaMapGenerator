"""Prueft den Updater gegen einen eigenen kleinen Server.

Gegen GitHub selbst laesst sich das nicht pruefen, solange dort kein
Release liegt - und ein Test, der von einem fremden Dienst abhaengt, ist
ohnehin keiner. Also ein Server im eigenen Haus, der GitHub-Antworten
nachbildet: eine mit Release, eine ohne, eine die einen Schluessel
verlangt, und eine, die Unsinn liefert.

Geprueft wird, was schiefgehen kann:
  * neuere Version erkannt, gleiche Version nicht faelschlich angeboten
  * privates Repo ohne Schluessel -> verstaendliche Meldung, kein Absturz
  * mit Schluessel -> geht durch, und der Schluessel steht im Kopf
  * Download landet vollstaendig und wird als Programm erkannt
  * eine Fehlerseite statt einer .exe wird abgelehnt, nicht gespeichert

Aufruf:  python tools/pruefe_update.py
"""
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from za import update as U
from za.version import VERSION

EXE = b"MZ" + b"\0" * 1_200_000          # sieht aus wie ein Programm
GESEHEN = {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, daten):
        roh = json.dumps(daten).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(roh)))
        self.end_headers()
        self.wfile.write(roh)

    def do_GET(self):
        GESEHEN[self.path] = dict(self.headers)
        basis = "http://127.0.0.1:%d" % self.server.server_port

        if self.path == "/neu":
            return self._json(200, {
                "tag_name": "v9.9.9",
                "assets": [{"name": "ArenaMapTool.exe",
                            "browser_download_url": basis + "/exe"}]})
        if self.path == "/gleich":
            return self._json(200, {
                "tag_name": VERSION,
                "assets": [{"name": "ArenaMapTool.exe",
                            "browser_download_url": basis + "/exe"}]})
        if self.path == "/ohne_release":
            return self._json(404, {"message": "Not Found"})
        if self.path == "/ohne_exe":
            return self._json(200, {"tag_name": "v9.9.9", "assets": [
                {"name": "quelltext.zip",
                 "browser_download_url": basis + "/exe"}]})
        if self.path == "/privat":
            # Wie GitHub bei einem privaten Repo: ohne Schluessel 404.
            if self.headers.get("Authorization") != "Bearer GEHEIM":
                return self._json(404, {"message": "Not Found"})
            return self._json(200, {
                "tag_name": "v2.0.0",
                "assets": [{"name": "ArenaMapTool.exe",
                            "browser_download_url": basis + "/exe"}]})
        if self.path == "/verboten":
            return self._json(403, {"message": "Bad credentials"})
        if self.path == "/versionjson":
            # Eigener Webspace statt GitHub - dieselben Felder.
            return self._json(200, {"version": "3.1.0",
                                    "url_exe": basis + "/exe"})
        if self.path == "/exe":
            self.send_response(200)
            self.send_header("Content-Length", str(len(EXE)))
            self.end_headers()
            self.wfile.write(EXE)
            return
        if self.path == "/fehlerseite":
            roh = b"<html>Nicht gefunden</html>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(roh)))
            self.end_headers()
            self.wfile.write(roh)
            return
        self._json(404, {"message": "Not Found"})


def main():
    fehler = []
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    basis = "http://127.0.0.1:%d" % srv.server_port
    print("Testserver auf", basis)
    print()

    # Schluesseldatei wegnehmen und spaeter zurueckgeben - der Test darf
    # den echten Schluessel des Benutzers weder lesen noch verlieren.
    tf = U.token_datei()
    gesichert = None
    if os.path.exists(tf):
        with open(tf, encoding="utf-8") as fh:
            gesichert = fh.read()
        os.remove(tf)

    try:
        print("%-22s %-9s %s" % ("FALL", "ZUSTAND", "MELDUNG"))
        faelle = [
            ("neue Version", "/neu", "neu"),
            ("gleiche Version", "/gleich", "aktuell"),
            ("kein Release", "/ohne_release", "keins"),
            ("Release ohne .exe", "/ohne_exe", "fehler"),
            ("privat, kein Schluessel", "/privat", "keins"),
            ("Zugang verweigert", "/verboten", "fehler"),
            ("eigene version.json", "/versionjson", "neu"),
        ]
        for name, pfad, soll in faelle:
            zustand, text, ver, url = U.pruefe(basis + pfad)
            print("%-22s %-9s %s" % (name, zustand, text[:52]))
            if zustand != soll:
                fehler.append("%s: %s statt %s" % (name, zustand, soll))

        # Ein 404 darf nicht raten. Gegen die echte GitHub-Schnittstelle
        # muss die Meldung unterscheiden, ob das Repo unerreichbar ist
        # oder nur noch kein Release hat - vorher stand dort pauschal
        # "vermutlich privat", was bei einem oeffentlichen Repo ohne
        # Release schlicht falsch war.
        zustand, text, _v, _u = U.pruefe()
        print()
        print("gegen das echte Repo:", zustand, "-", text[:70])
        unklar = ("kein Release" not in text
                  and "nicht erreichbar" not in text)
        if zustand == "keins" and unklar:
            fehler.append("404-Meldung sagt nicht, woran es liegt: %s" % text)

        print()
        # Mit Schluessel muss das private Repo durchgehen.
        os.makedirs(os.path.dirname(tf), exist_ok=True)
        with open(tf, "w", encoding="utf-8") as fh:
            fh.write("GEHEIM\n")
        zustand, text, ver, url = U.pruefe(basis + "/privat")
        print("%-22s %-9s %s" % ("privat mit Schluessel", zustand, text[:52]))
        if zustand != "neu" or ver != "v2.0.0":
            fehler.append("privat mit Schluessel: %s / %s" % (zustand, ver))
        if GESEHEN.get("/privat", {}).get("Authorization") != "Bearer GEHEIM":
            fehler.append("Schluessel wurde nicht mitgeschickt")

        print()
        with tempfile.TemporaryDirectory() as tmp:
            ziel = os.path.join(tmp, "neu.exe")
            U.lade(basis + "/exe", ziel)
            groesse = os.path.getsize(ziel)
            print("Download: %d Bytes, beginnt mit %r"
                  % (groesse, open(ziel, "rb").read(2)))
            if groesse != len(EXE):
                fehler.append("Download unvollstaendig: %d" % groesse)

            # Eine Fehlerseite darf nicht als .exe liegenbleiben.
            schrott = os.path.join(tmp, "schrott.exe")
            try:
                U.lade(basis + "/fehlerseite", schrott)
                fehler.append("Fehlerseite wurde als Programm angenommen")
            except ValueError as e:
                print("Fehlerseite abgelehnt:", e)
            if os.path.exists(schrott):
                fehler.append("abgelehnte Datei blieb liegen")

        # Ausserhalb der .exe darf sich nichts selbst ersetzen.
        try:
            U.tausche_und_starte("egal.exe")
            fehler.append("Selbstersetzung ausserhalb der .exe erlaubt")
        except RuntimeError:
            print("Selbstersetzung als Skript: abgelehnt (richtig)")
    finally:
        srv.shutdown()
        if os.path.exists(tf):
            os.remove(tf)
        if gesichert is not None:
            with open(tf, "w", encoding="utf-8") as fh:
                fh.write(gesichert)

    print()
    if fehler:
        for f in fehler:
            print("FEHLER:", f)
        return 1
    print("UPDATE-PRUEFUNG OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
