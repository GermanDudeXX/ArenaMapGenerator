# Zufallskarten für Godot — Einbau

Erzeugt die Arena **zur Laufzeit**: Kacheln und Hitboxen entstehen beim
Start aus einem Seed. Jeder Durchlauf eine andere Karte, 26 Kartenarten.

Godot 4.4+, reines GDScript — läuft in einem C#/Mono-Projekt genauso.

Der Ordner **`arena/`** ist das ganze Paket.

## Einbauen

1. Ordner `arena/` in das Projekt kopieren, sodass er als **`res://arena/`**
   liegt.
2. `arena/ArenaMap.tscn` in die Level-Szene ziehen.

Fertig. Beim Start baut sich eine Zufallskarte auf.

> Der Pfad `res://arena/` ist nicht beliebig: die Szene verweist darauf.
> Soll der Ordner woanders hin, ihn **im Godot-Editor** verschieben — dann
> schreibt Godot die Verweise mit. Ein Verschieben im Explorer tut das nicht.

## Steuern

Im Inspector am Knoten `ArenaMap`:

| Feld | Bedeutung |
|---|---|
| `map_seed` | `0` = bei jedem Start neu würfeln. Sonst ergibt dieselbe Zahl immer dieselbe Karte. |
| `map_mode` | leer = Art würfeln. Sonst ein Artname (siehe unten). |
| `only_group` | leer = alle Gruppen. Sonst `Arena`, `Dungeon`, `Organisch` oder `Labyrinth` — dann wird nur daraus gewürfelt. |
| `tile_set_resource` | ist gesetzt, nicht anfassen. |
| `collision_layer` | Kollisionsebene der Hitboxen, Standard 1. |
| `regenerate_now` | Haken im Editor = sofort neu bauen (springt zurück). |

Aus dem Code:

```gdscript
$ArenaMap.regenerate()                    # neue Zufallskarte
$ArenaMap.regenerate(4242)                # genau diese Karte
$ArenaMap.regenerate(0, "labyrinth")      # Art erzwingen, Seed würfeln
```

Aus C# genauso:

```csharp
var map = GetNode<Node2D>("ArenaMap");
map.Call("regenerate", 0, "raeume");
var spawns = (Godot.Collections.Array)map.Get("spawn_points");
```

## Was das Spiel danach bekommt

Nach jedem Aufbau stehen am Knoten bereit, in **Weltkoordinaten**:

| Feld | Inhalt |
|---|---|
| `spawn_points` | `Array[Vector2]` — Wellen-Spawnpunkte, mindestens 20 Kacheln vom Tor entfernt und 5 auseinander |
| `safezone_rect` | `Rect2` der Safezone |
| `gate_rect` | `Rect2` des Tors (dort ist **keine** Kollision, das Tor ist offen) |
| `last_info` | `Dictionary`: seed, mode, group, open_ratio, blocks, spawns … |

Dazu das Signal `map_generated(info: Dictionary)` — feuert nach jedem
Aufbau, auch beim ersten.

Der Knotenbaum darunter:

```
ArenaMap
├── Ground            TileMapLayer, 2688 Kacheln
└── Hitboxes
    ├── Mauer_Nord / Sued / West / Ost
    ├── Safezone_Wand_Sued / Ost_Oben / Ost_Unten
    └── Block_01 …    ein StaticBody2D je Mauerteil
```

## Die 26 Kartenarten

| Gruppe | Arten |
|---|---|
| **Arena** (offen, für Wellen-Survival) | `streu` `gespiegelt` `ringe` `saeulen` `sektoren` `rotunde` `diagonal` |
| **Dungeon** (Räume und Gänge) | `raeume` `zellen` `kammern` `stadt` `festung` `katakomben` `tempel` |
| **Organisch** | `hoehle` `see` `adern` `inseln` `risse` `krater` `wurzeln` |
| **Labyrinth** | `labyrinth` `schleifen` `hallen` `spirale` `kaefig` |

Für ein Wellen-Survival ist **`only_group = "Arena"`** die naheliegende
Einstellung: 88–97 % der Fläche begehbar, genug Platz zum Ausweichen.
`labyrinth` mit seinen ein Kachel breiten Gängen ist als Karte korrekt und
als Spielfeld vermutlich eine Zumutung. `hallen`, `stadt` und `festung`
sind die Kompromisse — Dungeon-Optik, Arena-Bewegung.

## Fest in jeder Art

Safezone oben links, Tor nach rechts, davor ein garantiert freier Bereich.
Größe und Torhöhe schwanken, die **Lage nicht** — der Spieler muss wissen,
wo er hin muss, wenn die Welle kippt.

Und: **jede Bodenkachel ist vom Tor aus erreichbar.** Das ist keine
Hoffnung, sondern geprüft (siehe unten).

## Rechenzeit

13–82 ms pro Karte, je nach Art (gemessen auf diesem Rechner, Godot 4.7.1
headless). Das gehört an einen Ladepunkt, nicht in `_process`. Am
langsamsten sind `hoehle` und `see` (zellulärer Automat), am schnellsten
die Arena-Arten.

## Seeds

Gleicher Seed und gleiche Art heißt **innerhalb von Godot** immer dieselbe
Karte. Aber: dieselbe Zahl ergibt **nicht** dieselbe Karte wie im
Python-Autorenwerkzeug. Godot würfelt mit PCG32, Python mit
Mersenne-Twister — gleiche Logik, andere Zahlenfolge. Wer eine bestimmte
Karte aus dem Werkzeug haben will, nimmt das gebackene Paket
(`godot_export/`) statt dieses hier.

## Geprüft

Alles mit Godot 4.7.1 headless gegen den echten Code, nicht auf dem Papier:

- **520 Karten** (26 Arten × 20 Seeds), kein Notnagel. Je Karte geprüft:
  jede Bodenkachel vom Tor erreichbar, Safezone unverbaut, Tor offen,
  Blöcke decken genau die Mauern, Rechteckzerlegung ohne Überlappung,
  genug Spawnpunkte. **Kein Fehler.**
- **Determinismus**: gleicher Seed → identisches Gitter, alle 26 Arten.
- **Zufall**: 20 von 20 Ziehungen mit `map_seed = 0` verschieden.
- **Knotenaufbau**: die Kollisionsflächen auf Kacheln zurückgerechnet und
  mit dem Gitter verglichen — kein Loch, keine Überlappung, alles auf dem
  16er-Raster. Spawnpunkte liegen auf Boden.
- **Szenenbetrieb**: `_ready()` baut die Karte, `regenerate()` tauscht sie
  im laufenden Spiel aus.

Die Prüfskripte liegen bei (`test_generator.gd`, `test_map_node.gd`,
`scene_main.gd`) — sie gehören nicht ins Spiel, aber wer den Generator
anfasst, kann sie erneut laufen lassen:

```
Godot --headless --path <projekt> --script res://test_generator.gd
Godot --headless --path <projekt> --script res://test_map_node.gd
```

## Kontrolle nach dem Einbau

Szene starten, **Debug → Kollisionsformen sichtbar** einschalten. Die roten
Umrisse müssen deckungsgleich auf den hellen Mauern liegen. Sieht die Karte
matschig aus, ist der Texturfilter an — dann ist `ArenaTileset.png.import`
nicht mitgekommen.

## Atlas

Das CraftPix-Tileset (19 × 11 Kacheln à 16 px) plus **eine angehängte
Zeile**. Die Kachel bei `0,11` ist ein vollflächiges Mauerstück für
komplett eingeschlossene Zellen — das gibt es im Original nicht, dort
blieben sonst Löcher in den Mauern. Zeilen 0–10 sind unverändert.

## Lizenz

Grafik: **CraftPix — Free Top Down Roguelike Game Kit (Pixel Art)**.
Es gelten die Lizenzbedingungen von CraftPix.
