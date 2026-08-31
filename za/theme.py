"""Farbschemata fuer die Anzeige.

Die Kartengrafik bleibt davon unberuehrt - das ist Pixel-Art aus dem
Tileset und hat mit der Bedienoberflaeche nichts zu tun. Eingefaerbt wird
nur, was darueber liegt: Kopfzeile, Menue, Hilfe, Marken.

Jedes Schema nennt dieselben sechs Rollen. Wer eins hinzufuegt, muss also
nichts weiter anfassen als dieses Wortverzeichnis.
"""

THEMES = {
    "dunkel": {
        "text":  (233, 237, 245),
        "dim":   (139, 147, 168),
        "akzent": (247, 178, 62),
        "aktiv": (96, 202, 164),
        "kasten": (10, 12, 20),
        "rand":  (64, 72, 96),
        "balken": (38, 46, 66),
        "spawn": (226, 86, 74),
    },
    "hell": {
        "text":  (24, 26, 34),
        "dim":   (86, 92, 108),
        "akzent": (176, 96, 8),
        "aktiv": (16, 122, 92),
        "kasten": (238, 240, 246),
        "rand":  (150, 158, 176),
        "balken": (206, 212, 226),
        "spawn": (188, 40, 32),
    },
    "kontrast": {
        "text":  (255, 255, 255),
        "dim":   (200, 200, 200),
        "akzent": (255, 214, 0),
        "aktiv": (0, 255, 170),
        "kasten": (0, 0, 0),
        "rand":  (255, 255, 255),
        "balken": (48, 48, 48),
        "spawn": (255, 64, 64),
    },
    "gruen": {
        "text":  (206, 244, 206),
        "dim":   (120, 168, 120),
        "akzent": (156, 240, 90),
        "aktiv": (72, 220, 140),
        "kasten": (8, 20, 10),
        "rand":  (48, 92, 56),
        "balken": (24, 56, 32),
        "spawn": (240, 120, 60),
    },
    "bernstein": {
        "text":  (250, 226, 178),
        "dim":   (176, 142, 96),
        "akzent": (255, 176, 32),
        "aktiv": (255, 214, 120),
        "kasten": (24, 14, 4),
        "rand":  (104, 72, 24),
        "balken": (56, 36, 12),
        "spawn": (220, 96, 72),
    },
}

NAMEN = list(THEMES)

# Wie gross die Schrift im Verhaeltnis zur Fensterskalierung ist.
GROESSEN = [("winzig", 0.7), ("klein", 0.85), ("normal", 1.0),
            ("gross", 1.25), ("riesig", 1.5)]

GROESSEN_NAMEN = [n for n, _ in GROESSEN]


def farben(name):
    return THEMES.get(name, THEMES["dunkel"])


def faktor(name):
    for n, f in GROESSEN:
        if n == name:
            return f
    return 1.0
