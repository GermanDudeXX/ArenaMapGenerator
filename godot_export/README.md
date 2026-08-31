# Arena-Map für Godot — Einbau

Fertige Karte plus Hitboxen für Godot 4.7. Sonst nichts: keine Skripte,
keine Spiellogik, keine Gegner, keine Spawnpunkte.

Der Ordner **`arena/`** ist das ganze Paket.

## Einbauen

1. Ordner `arena/` in das Projekt kopieren, sodass er als **`res://arena/`**
   liegt. Godot importiert das PNG beim nächsten Start selbst.
2. `ArenaMap.tscn` aus dem FileSystem-Dock in die Level-Szene ziehen.

Das war's. Es erscheint **ein** Knoten `ArenaMap`.

> Der Pfad `res://arena/` ist nicht beliebig: die `.tscn` verweist darauf.
> Wenn der Ordner woanders hin soll, ihn **im Godot-Editor** verschieben
> (FileSystem-Dock, Drag & Drop) — dann schreibt Godot die Verweise mit.
> Ein Verschieben im Explorer tut das nicht.

## Einzeln bearbeiten

Instanzierte Szenen sind in Godot erst mal gesperrt. Ein Rechtsklick auf
`ArenaMap` → **„Bearbeitbare Kinder"** (Editable Children), und ab da ist
jeder einzelne Teil anklick- und verschiebbar:

```
ArenaMap
├── Ground                    TileMapLayer — jede Kachel einzeln malbar
└── Hitboxes
    ├── Mauer_Nord            StaticBody2D
    ├── Mauer_Sued
    ├── Mauer_West
    ├── Mauer_Ost
    ├── Safezone_Wand_Sued
    ├── Safezone_Wand_Ost_Oben
    ├── Safezone_Wand_Ost_Unten
    ├── Deckung_01            ein Body je Hindernis
    ├── Deckung_02
    └── …  (22 Stück)
```

Jedes Hindernis ist **ein** `StaticBody2D`. Ein Zug am Body verschiebt das
ganze Hindernis; die `CollisionShape2D` darunter sind relativ dazu gesetzt.
Wer die Grafik dazu mitnehmen will, muss die Kacheln in `Ground` von Hand
mitziehen — Grafik und Kollision sind bewusst getrennt.

Hindernisse aus L-, Kreuz- oder Doppelform haben mehrere `Shape1`,
`Shape2` … unter demselben Body, weil ein Rechteck sie nicht deckt. Die
Bounding-Box wäre zu groß gewesen und hätte unsichtbare Wände ergeben.

## Was drin ist

| Datei | Inhalt |
|---|---|
| `arena/ArenaMap.tscn` | die Szene: `Ground` + `Hitboxes` |
| `arena/ArenaTileset.tres` | TileSet, 16 px, 18 benutzte Kacheln |
| `arena/ArenaTileset.png` | Atlas (siehe unten) |
| `arena/ArenaTileset.png.import` | Importeinstellung — **Filter aus**, sonst matscht die Pixel-Art |
| `VORSCHAU.png` | wie die Karte aussehen muss — gehört **nicht** ins Projekt |

**Karte:** 68 × 46 Kacheln à 16 px = 1088 × 736 px. Arena von Kachel (3,3)
bis (64,42), umlaufende Außenmauer, Safezone oben links, Tor auf Kachel
(17, 9–10) — dort ist **keine** Kollision, das Tor ist absichtlich offen.

**Kollision:** 29 `StaticBody2D`, 38 Rechtecke, decken exakt die 417
Mauerkacheln ab. Kein Loch, keine Überlappung, alles auf dem 16er-Raster.
Alle Bodies liegen auf Kollisionsebene 1 — falls ihr eigene Layer nutzt,
in Godot umstellen.

**Atlas:** das CraftPix-Tileset (19 × 11) plus **eine angehängte Zeile**.
Die Kachel bei `0,11` ist ein vollflächiges Mauerstück für komplett
eingeschlossene Zellen — das gibt es im Original nicht, dort blieben sonst
Löcher in den Hindernissen. Zeilen 0–10 sind unverändert das Original.

## Kontrolle nach dem Einbau

Die Szene ist vor der Auslieferung von Godot selbst geprüft worden: alle
2688 Kacheln stimmen mit den Solldaten überein, und jede Kollisionsfläche
liegt auf genau den Kacheln, die Mauer sind.

Nach dem Einbau reicht ein Blick: Szene starten, **Debug → Kollisionsformen
sichtbar** einschalten. Die roten Umrisse müssen deckungsgleich auf den
hellen Mauern und Hindernissen liegen. Wenn die Karte matschig aussieht,
ist der Texturfilter an — dann ist die `.png.import` nicht mitgekommen.

## Lizenz

Grafik: **CraftPix — Free Top Down Roguelike Game Kit (Pixel Art)**.
Es gelten die Lizenzbedingungen von CraftPix.
