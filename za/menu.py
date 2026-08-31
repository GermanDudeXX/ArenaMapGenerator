"""Auswahlmenue im Viewer.

Die Zeilen stehen nicht fest: waehlt man "eigene" Masse, kommen zwei
Textfelder dazu, und beim Abschnitt faellt der Startraum weg. Deshalb hat
jede Zeile einen Namen statt einer Nummer - eine feste Reihenfolge mit
Indizes waere bei wechselnder Zeilenzahl genau die Sorte Fehler, die man
erst bemerkt, wenn die falsche Zeile reagiert.

Alles, was hier einstellbar ist, gibt es auch als Taste oder als Schalter
auf der Kommandozeile. Das Menue ist die Fassung fuer alle, die sich das
nicht merken wollen, kein zweiter Bedienweg mit eigenen Faehigkeiten.
"""
from . import mapgen
from .paths import kuerzen
from .textfield import TextField
from . import theme

# "Groesse" umfasst auch die Vollkarte - aus Sicht des Bedieners ist das
# dieselbe Frage: wie gross soll das Stueck sein, das ich bekomme.
SIZES = [
    (None, "Vollkarte %d x %d" % (mapgen.MAP_W, mapgen.MAP_H)),
    ("klein", "Abschnitt klein %d x %d" % mapgen.SECTIONS["klein"]),
    ("mittel", "Abschnitt mittel %d x %d" % mapgen.SECTIONS["mittel"]),
    ("gross", "Abschnitt gross %d x %d" % mapgen.SECTIONS["gross"]),
    ("eigene", "eigene Masse"),
]

GROUPS = ["alle"] + list(mapgen.GROUPS)

# Startraum: der abgesperrte Bereich, in dem der Spieler anfaengt. Nur bei
# der Vollkarte - ein Abschnitt hat keinen.
SAFES = [(None, "zufaellig 13-17 x 11-15")] + [
    (n, "%s  %d x %d" % (n, *mapgen.SAFE_SIZES[n]))
    for n in ("klein", "mittel", "gross")] + [("eigene", "eigene Masse")]

ECKEN = list(mapgen.SAFE_POSITIONS)


class Menu:
    """Zustand des Auswahlmenues. Zeichnen macht der Viewer."""

    def __init__(self, size=None, gruppe="alle", mode=None, seed=None,
                 export_dir="", safe=None, ecke="oben links",
                 masse=None, safe_masse=None,
                 hud="normal", schema="dunkel"):
        self.row = 0
        self.size_i = next((i for i, (s, _) in enumerate(SIZES) if s == size), 0)
        self.group_i = GROUPS.index(gruppe) if gruppe in GROUPS else 0
        self.mode = mode          # None = zufaellig
        self.export_dir = export_dir
        self.safe_i = next((i for i, (n, _) in enumerate(SAFES) if n == safe), 0)
        self.ecke_i = ECKEN.index(ecke) if ecke in ECKEN else 0

        vor = masse or (mapgen.MAP_W, mapgen.MAP_H)
        self.breite = TextField(str(vor[0]), max_len=3)
        self.hoehe = TextField(str(vor[1]), max_len=3)
        sv = safe_masse or mapgen.SAFE_SIZES["mittel"]
        self.sr_breite = TextField(str(sv[0]), max_len=3)
        self.sr_hoehe = TextField(str(sv[1]), max_len=3)

        # Der Seed steht als Text da, nicht als Zahl: waehrend des Tippens
        # ist "" ein gueltiger Zwischenstand, 0 aber ein gueltiger Seed.
        self.seed_field = TextField("" if seed is None else str(seed))
        self.update_text = "ENTER prueft"
        self.hud_i = (theme.GROESSEN_NAMEN.index(hud)
                      if hud in theme.GROESSEN_NAMEN else 2)
        self.schema_i = theme.NAMEN.index(schema) if schema in theme.NAMEN else 0

    # ------------------------------------------------------------- Werte
    @property
    def size(self):
        """Abschnittsgroesse: Name, (b, h) bei eigenen Massen, sonst None."""
        n = SIZES[self.size_i][0]
        if n == "eigene":
            return self.eigene_masse() if not self.voll_gemeint() else None
        return n

    def voll_gemeint(self):
        """Bei eigenen Massen: ist die Vollkarte gemeint?

        Eine frei eingegebene Groesse kann beides sein. Entschieden wird
        es am Startraum: wer einen will, meint eine Vollkarte.
        """
        return SIZES[self.size_i][0] == "eigene" and self.mit_startraum

    @property
    def mit_startraum(self):
        return getattr(self, "_mit_sr", True)

    @mit_startraum.setter
    def mit_startraum(self, wert):
        self._mit_sr = bool(wert)

    def eigene_masse(self):
        b = self.breite.as_int() or mapgen.MAP_W
        h = self.hoehe.as_int() or mapgen.MAP_H
        if self.ist_abschnitt():
            return (max(8, min(mapgen.MAX_W, b)),
                    max(8, min(mapgen.MAX_H, h)))
        return mapgen.clamp_masse(b, h)

    @staticmethod
    def _hinweis(eingabe, ergebnis):
        """Sagen, wenn die Eingabe zurechtgebogen wurde.

        Vorher stand in der Zeile nur das Ergebnis. Wer 2 x 2 eintippt und
        7 x 9 lesen muss, haelt das fuer einen Fehler - und hat recht,
        solange niemand dazuschreibt, dass es eine Untergrenze gibt.
        """
        if eingabe == ergebnis:
            return ""
        return "  (Eingabe %d x %d angepasst)" % eingabe

    @property
    def gruppe(self):
        return GROUPS[self.group_i]

    @property
    def ecke(self):
        return ECKEN[self.ecke_i]

    @property
    def safe_name(self):
        return SAFES[self.safe_i][0]

    @property
    def safe_size(self):
        """Masse des Startraums, oder None fuer gewuerfelt."""
        n = self.safe_name
        if n == "eigene":
            return mapgen.clamp_startraum(self.sr_breite.as_int() or 15,
                                          self.sr_hoehe.as_int() or 12)
        return mapgen.SAFE_SIZES[n] if n else None

    @property
    def hud(self):
        return theme.GROESSEN_NAMEN[self.hud_i]

    @property
    def schema(self):
        return theme.NAMEN[self.schema_i]

    @property
    def seed(self):
        """Eingegebener Seed, oder None fuer wuerfeln."""
        return self.seed_field.as_int()

    @property
    def seed_text(self):
        return self.seed_field.text

    def kartenart(self):
        """"voll" oder "abschnitt" - was gebaut werden soll."""
        return "abschnitt" if self.ist_abschnitt() else "voll"

    def groesse(self):
        """None fuer die Vorgabemasse, ein Name, oder (Breite, Hoehe)."""
        n = SIZES[self.size_i][0]
        if n == "eigene":
            return self.eigene_masse()
        return n

    def ist_abschnitt(self):
        """Wird ein Abschnitt gebaut - also einer ohne Startraum?"""
        n = SIZES[self.size_i][0]
        if n == "eigene":
            return not self.mit_startraum
        return n is not None

    def arten(self):
        """Arten, die zur aktuellen Groesse und Gruppe passen.

        Beides zusammen: eine kleine Karte kann nicht jede Art, und die
        Gruppe schraenkt weiter ein. Waere das nicht gefiltert, stuende
        im Menue eine Auswahl, die beim Wuerfeln nichts ergibt.
        """
        n = SIZES[self.size_i][0]
        if n in (None, "eigene"):
            namen = list(mapgen.MODE_NAMES)
        else:
            namen = mapgen.modes_for_section(n)
        if self.gruppe != "alle":
            namen = [m for m in namen
                     if mapgen.MODES[m]["gruppe"] == self.gruppe]
        return namen

    # ------------------------------------------------------------ Zeilen
    def zeilen(self):
        """(schluessel, Beschriftung, Wert) je sichtbarer Zeile."""
        eigen = SIZES[self.size_i][0] == "eigene"
        abschnitt = self.ist_abschnitt()
        art = self.mode or "(zufaellig)"

        z = [("groesse", "Groesse", SIZES[self.size_i][1])]
        if eigen:
            b, h = self.eigene_masse()
            z.append(("art_karte", "  davon",
                      "Abschnitt (ohne Startraum)" if abschnitt
                      else "Vollkarte (mit Startraum)"))
            z.append(("breite", "  Breite", self.breite.text))
            roh = (self.breite.as_int() or b, self.hoehe.as_int() or h)
            z.append(("hoehe", "  Hoehe", "%s      -> %d x %d Kacheln%s"
                      % (self.hoehe.text, b, h,
                         self._hinweis(roh, (b, h)))))
        z.append(("gruppe", "Gruppe", self.gruppe))
        z.append(("art", "Art", "%s   [%d moeglich]" % (art, len(self.arten()))))

        if abschnitt:
            z.append(("startraum", "Startraum", "- (nur Vollkarte)"))
        else:
            z.append(("startraum", "Startraum", SAFES[self.safe_i][1]))
            if self.safe_name == "eigene":
                sb, sh = self.safe_size
                z.append(("sr_breite", "  Breite", self.sr_breite.text))
                roh = (self.sr_breite.as_int() or sb,
                       self.sr_hoehe.as_int() or sh)
                z.append(("sr_hoehe", "  Hoehe", "%s      -> %d x %d Kacheln%s"
                          % (self.sr_hoehe.text, sb, sh,
                             self._hinweis(roh, (sb, sh)))))
            z.append(("ecke", "Startraum-Ecke", self.ecke))

        z.append(("seed", "Seed", self.seed_text or "(zufaellig)"))
        z.append(("hud", "Schriftgroesse", self.hud))
        z.append(("schema", "Farbschema", self.schema))
        z.append(("ordner", "Export-Ordner", kuerzen(self.export_dir, 38)))
        z.append(("update", "Update", self.update_text))
        return z

    def schluessel(self):
        return [k for k, _, _ in self.zeilen()]

    def aktiv(self):
        """Schluessel der gewaehlten Zeile."""
        s = self.schluessel()
        self.row = max(0, min(self.row, len(s) - 1))
        return s[self.row]

    def feld(self, key=None):
        """Textfeld der Zeile, oder None wenn es keins ist."""
        key = key or self.aktiv()
        return {"breite": self.breite, "hoehe": self.hoehe,
                "sr_breite": self.sr_breite, "sr_hoehe": self.sr_hoehe,
                "seed": self.seed_field}.get(key)

    def hinweise(self):
        """Tastenhilfe, passend zur gewaehlten Zeile."""
        key = self.aktiv()
        if key == "ordner":
            return [("ENTER", "Ordner waehlen"), ("Hoch/Runter", "Zeile"),
                    ("F1", "schliessen")]
        if key == "update":
            return [("ENTER", "pruefen bzw. installieren"),
                    ("Hoch/Runter", "Zeile"), ("F1", "schliessen")]
        if key in ("hud", "schema"):
            return [("Links/Rechts", "aendern - wirkt sofort"),
                    ("Hoch/Runter", "Zeile"), ("F1", "schliessen")]
        if self.feld(key) is not None:
            zusatz = ("Seed eins hoch/runter" if key == "seed"
                      else "Wert eins hoch/runter")
            return [("Ziffern", "tippen"), ("Links/Rechts", "Schreibmarke"),
                    ("+ / -", zusatz), ("Strg+V", "einfuegen"),
                    ("ENTER", "Karte bauen")]
        return [("Hoch/Runter", "Zeile"), ("Links/Rechts", "aendern"),
                ("ENTER", "neu wuerfeln"), ("F1", "schliessen")]

    # ----------------------------------------------------------- Bedienen
    def move(self, delta):
        n = len(self.schluessel())
        self.row = (self.row + delta) % n

    def step(self, delta):
        """+/- auf der gewaehlten Zeile: Zahl im Feld verstellen."""
        key = self.aktiv()
        f = self.feld(key)
        if f is None:
            return
        if key == "seed":
            f.set_text(str(max(1, (f.as_int() or 1) + delta)))
        else:
            f.set_text(str(max(1, (f.as_int() or 1) + delta)))

    def change(self, delta):
        """Wert der gewaehlten Zeile aendern (Links/Rechts)."""
        key = self.aktiv()
        if key == "groesse":
            self.size_i = (self.size_i + delta) % len(SIZES)
            self._repair_mode()
        elif key == "art_karte":
            self.mit_startraum = not self.mit_startraum
            self._repair_mode()
        elif key == "gruppe":
            self.group_i = (self.group_i + delta) % len(GROUPS)
            self._repair_mode()
        elif key == "art":
            namen = [None] + self.arten()
            try:
                i = namen.index(self.mode)
            except ValueError:
                i = 0
            self.mode = namen[(i + delta) % len(namen)]
        elif key == "startraum":
            self.safe_i = (self.safe_i + delta) % len(SAFES)
        elif key == "ecke":
            self.ecke_i = (self.ecke_i + delta) % len(ECKEN)
        elif key == "hud":
            self.hud_i = (self.hud_i + delta) % len(theme.GROESSEN_NAMEN)
        elif key == "schema":
            self.schema_i = (self.schema_i + delta) % len(theme.NAMEN)
        else:
            # In einem Textfeld bewegen Links/Rechts die Schreibmarke -
            # wie in jedem Textfeld. Fuer +/-1 gibt es Plus und Minus.
            f = self.feld(key)
            if f is not None:
                (f.left if delta < 0 else f.right)()

    def _repair_mode(self):
        """Eine gewaehlte Art fallen lassen, wenn sie nicht mehr passt.

        Sonst bleibt zum Beispiel `festung` stehen, nachdem auf `klein`
        umgestellt wurde - und der Generator liefert dort nichts.
        """
        if self.mode is not None and self.mode not in self.arten():
            self.mode = None
