# Arena Map Viewer + Generator

Baut Top-Down-Arenen aus dem *CraftPix Free Top Down Roguelike Game Kit* —
entweder das handgesetzte Layout oder eine aus einem Seed generierte Karte.
Reiner Betrachter: die Karte wird gezeichnet, die Kamera laesst sich frei
bewegen. Keine Spielfigur, keine Kollision, keine Spiellogik.

## Update

Bezugsquelle: **github.com/GermanDudeXX/ArenaMapGenerator** (oeffentlich).
Im Programm `F1` -> Zeile *Update* -> `ENTER` prueft, ein zweites `ENTER`
installiert. Auf der Kommandozeile `--update` bzw. `--update-jetzt`.

Neue Fassung veroeffentlichen:

```
1. za/version.py hochzaehlen
2. BAUEN.bat
3. gh release create v1.2.3 dist/ArenaMapTool.exe dist/LIESMICH.txt ^
     --repo GermanDudeXX/ArenaMapGenerator --title "ArenaMapTool 1.2.3"
```

Geprueft: `tools/pruefe_update.py` (acht Faelle gegen einen eigenen
Server) und `tools/pruefe_selbstersatz.py` (echte .exe ersetzt sich
wirklich). Zusaetzlich einmal vollstaendig gegen das echte GitHub: eine
0.9.0-Fassung hat sich selbstaendig auf 1.0.0 aktualisiert.

## Als .exe

`BAUEN.bat` erzeugt **eine einzelne Datei**: `dist\ArenaMapTool.exe`.
Kein Python noetig, keine Ordner daneben - die Grafiken stecken drin.
Bedienung und Tastenliste in `dist\LIESMICH.txt`.

Die .exe kann sich selbst pruefen:

```
ArenaMapTool.exe --selbsttest C:\Pfad\zum\Pruefordner
```

Das rechnet alle Groessen durch, zeichnet, exportiert nach Tiled und
schreibt einen Bericht. Beim Bauen laeuft das automatisch mit.

**Zielordner:** voreingestellt `ArenaExport` neben der .exe, aenderbar
ueber `F1` -> Zeile *Export-Ordner* -> `ENTER` (Windows-Ordnerdialog).
Die Wahl wird in `%APPDATA%\ArenaMapGen` gemerkt.

## Starten

```
python main.py                    handgesetztes Layout
python main.py --liste            alle Kartenarten auflisten
python main.py --random           gewuerfelte Karte, gewuerfelte Art
python main.py --seed 4242        genau diese Karte
python main.py --seed 7 --mode labyrinth
python main.py --seed 7 --startraum gross --startecke "unten rechts"
python main.py --seed 7 --breite 120 --hoehe 90
python main.py --seed 7 --breite 40 --hoehe 30 --abschnitt
python main.py --seed 7 --export  nur JSON schreiben, kein Fenster
```

Doppelklick auf **`START.bat`** startet das handgesetzte Layout. Einzige
Abhaengigkeit ist `pygame` — ausser bei `--export`, das laeuft ohne.

## Steuerung

| Taste | Aktion |
|---|---|
| `W A S D` / Pfeiltasten | Karte bewegen |
| `Shift` | schneller bewegen |
| `R` | neue Karte wuerfeln |
| `N` / `P` | Seed vor / zurueck |
| `F1` | **Auswahlmenue**: Groesse, Gruppe, Art - ENTER wuerfelt neu |
| `1` `2` `3` `4` | Gruppe waehlen: Arena / Dungeon / Organisch / Labyrinth |
| `TAB` / `Shift+TAB` | naechste / vorige Kartenart (gleicher Seed) |
| `C` | Art wieder je Seed wuerfeln |
| `L` | handgesetzt <-> generiert |
| `K` | Spawnpunkte an/aus |
| `E` | Karte schreiben: PNG + JSON nach `export/`, `.tmx` nach `tiled_export/` |
| `M` | Gesamtansicht der kompletten Karte an/aus |
| `G` | Tileraster an/aus (jede 8. Linie hervorgehoben) |
| `T` | Tor oeffnen/schliessen |
| `F11` | Vollbild |
| `H` | Hilfe ein-/ausblenden |
| `ESC` | Beenden |

In der Gesamtansicht markiert der goldene Rahmen den Ausschnitt, den die
Nahansicht gerade zeigt. Rote Ringe sind Wellen-Spawnpunkte.

## Die Karte

68 × 46 Tiles à 16 px (1088 × 736 px insgesamt):

- **Arena** — begehbarer Bereich von Tile (3,3) bis (64,42), umlaufende
  Aussenmauer, Hindernisbloecke als Deckung.
- **Abgesperrter Bereich** — eigener Raum in der oberen linken Ecke, durch
  eine eigene Mauer abgetrennt, blau eingefaerbt und umrandet. Einziger
  Zugang ist das zwei Tiles hohe Tor.
- **Deko** — Kisten, Faesser, Truhe und Hebel; 26 animierte Wandfackeln.

Das handgesetzte Layout steht in `World._build_grid()`, alle Masse in
`za/settings.py`.

## Generator

`za/mapgen.py` erzeugt aus einem Seed dasselbe Zellengitter, das
`_build_grid()` sonst von Hand hinschreibt. Alles danach - Autotiling,
Deko, Fackeln, Zeichnen, Godot-Export - haengt nur am Gitter und weiss
nicht, woher es kommt. Deshalb kostet eine neue Kartenart keine Zeile
ausserhalb von `mapgen.py`.

### Sechsundzwanzig Arten

`python main.py --liste` zeigt sie; `--mode NAME` erzwingt eine.

| Gruppe | Art | Anordnung | offen |
|---|---|---|---|
| Arena | `streu` | frei verteilte Deckung | 89-94 % |
| Arena | `gespiegelt` | punktsymmetrische Deckung | 90-94 % |
| Arena | `ringe` | Deckung auf drei Ringen | 91-95 % |
| Arena | `saeulen` | regelmaessiges Saeulenraster | 88-95 % |
| Arena | `sektoren` | Trennwaende mit Durchgaengen | 91-97 % |
| Arena | `rotunde` | konzentrische Ringmauern | 79-85 % |
| Arena | `diagonal` | schraege Balken | 90-98 % |
| Dungeon | `raeume` | BSP-Raeume mit Gaengen | 50-68 % |
| Dungeon | `zellen` | Rasterzimmer mit Tueren | 65-77 % |
| Dungeon | `kammern` | wenige grosse Hallen | 37-55 % |
| Dungeon | `stadt` | Haeuserblocks mit Strassen | 49-68 % |
| Dungeon | `festung` | verschachtelte Ringmauern mit Toren | 87-92 % |
| Dungeon | `katakomben` | viele kleine Kammern | 32-46 % |
| Dungeon | `tempel` | achsensymmetrisch um eine Mittelhalle | 25-47 % |
| Organisch | `hoehle` | zellulaerer Automat | 49-68 % |
| Organisch | `see` | eine grosse offene Hoehle | 72-89 % |
| Organisch | `adern` | gewundene Gaenge | 28-69 % |
| Organisch | `inseln` | gewachsene Bloecke | 81-89 % |
| Organisch | `risse` | Bruchlinien wie gesprungenes Glas | 67-92 % |
| Organisch | `krater` | runde Lichtungen im Fels | 23-50 % |
| Organisch | `wurzeln` | verzweigte Gaenge vom Tor aus | 31-58 % |
| Labyrinth | `labyrinth` | echtes Labyrinth, enge Gaenge | 56-57 % |
| Labyrinth | `schleifen` | Labyrinth ohne Sackgassen | 58-59 % |
| Labyrinth | `hallen` | Labyrinth mit weiten Gaengen | 71-73 % |
| Labyrinth | `spirale` | ein Gang von aussen nach innen | 42-60 % |
| Labyrinth | `kaefig` | Gitter mit versetzten Luecken | 81-85 % |

Fuer ein Wellen-Survival taugen die Arena-Arten am besten. `labyrinth`
mit seinen ein Tile breiten Gaengen ist als Karte korrekt und als
Spielfeld vermutlich eine Zumutung; `krater` und `tempel` sind zu grossen
Teilen Fels, in dem man nichts zu suchen hat. Die Kompromisse mit
Dungeon-Optik und Arena-Bewegung sind `hallen`, `stadt` und `festung`.

`export/kontaktbogen.png` zeigt alle sechsundzwanzig am selben Seed
(`python tools/kontaktbogen.py --seed 4242`).

### Wie es funktioniert

Fuer jede Art derselbe Ablauf, und nur Schritt 2 unterscheidet sich:

1. **Grundriss** - Aussenmauer, Safezone oben links, Tor nach rechts
2. **Schnitt** - die Art fuellt das Feld
3. **Anbindung** - garantierter Weg vom Tor ins Feld
4. **Reparatur** - Flutfuellung vom Tor; was nicht erreichbar ist, wird Mauer
5. **Pruefung** - offener Anteil, Bloecke, Spawnpunkte, sonst neuer Anlauf

Schritt 4 ist der Grund, warum die Arten so kurz sein duerfen. Ein
Hoehlengenerator muss nicht beweisen, dass er keine abgeschlossene Blase
erzeugt; er darf welche erzeugen, und sie werden zugemauert. Was ein
Generator nicht garantieren muss, muss er auch nicht koennen.

Die **Arena-Arten** brauchen Schritt 4 gar nicht: dort haelt eine einzige
Regel alles begehbar - jedes Hindernis laesst `MIN_GAP` (3) Tiles Luft zu
jedem anderen und zur Aussenmauer, dann laeuft rundherum immer ein Weg.

**Fest bleibt in jeder Art:** Safezone oben links, Tor nach rechts, davor
ein garantiert freier Bereich. Groesse und Torhoehe variieren, die Lage
nicht - der Spieler muss wissen, wo er hin muss, wenn die Welle kippt.

Verworfene Anlaeufe ziehen weiter aus demselben Zufallsstrom, statt den
Seed zu veraendern: **gleicher Seed und gleiche Art heisst immer dieselbe
Karte.** Gemessen ueber 780 Karten (26 Arten x 30 Seeds): kein Notnagel,
im Schnitt 1,2 Anlaeufe, 2-18 ms pro Karte.

Spawnpunkte liegen mindestens 20 Tiles vom Tor entfernt und 5 Tiles
auseinander, bevorzugt am Rand. In einem Dungeon ist der Rand oft Mauer -
dann zaehlt nur noch der Abstand zum Tor, sonst gaebe es keine.

## Export

`E` im Viewer oder `--export` auf der Kommandozeile schreibt nach `export/`:

- `map_<seed>.png` — die fertig gezeichnete Karte
- `map_<seed>.json` — Gitter, Safezone, Tor, Hindernisse und Spawnpunkte

Das JSON ist das, was in eine Engine wandert. Gitter als Zeichenzeilen
(`#` Mauer, `.` Boden, `+` Tor, Leerzeichen ausserhalb), dazu die
Bounding-Boxen der Hindernisse und die Spawnpunkte als Tile-Koordinaten.

## Eigene Masse

Die Zeile *Groesse* kennt neben Vollkarte und den drei Abschnittsgroessen
auch **eigene Masse**: dann erscheinen zwei Textfelder fuer Breite und
Hoehe, und eine Zeile, ob ein Startraum dazugehoert oder nicht.

Grenzen, gemessen und nicht geraten:

| | von | bis |
|---|---|---|
| Vollkarte | 48 x 36 | 250 x 200 |
| Abschnitt | 8 x 8 | 250 x 200 |
| Startraum | 7 x 9 | halbe Arena |

Unter 48 x 36 bleibt nach dem Startraum zu wenig Feld, dort fallen
einzelne Arten durch. Ab etwa 200 x 150 dauert eine Karte spuerbar
laenger - die Rechenzeit waechst mit der Flaeche.

Anzahlen und Laengen im Generator sind flaechenrelativ: bei 100 x 80
setzt `streu` rund achtzig Hindernisse statt zwanzig, `raeume` teilt
tiefer. Bei der Vorgabekarte ist der Faktor exakt 1,0 - dort aendert sich
dadurch nichts.

## Auswahlmenue

`F1` oeffnet im Viewer ein Menue mit drei Zeilen:

```
Groesse         Vollkarte 68x46 | Abschnitt klein / mittel / gross
Gruppe          alle | Arena | Dungeon | Organisch | Labyrinth
Art             (zufaellig) oder eine feste
Startraum       zufaellig | klein 11x9 | mittel 15x12 | gross 20x16
Startraum-Ecke  oben links | oben rechts | unten links | unten rechts
Schriftgroesse  winzig ... riesig   (wirkt sofort, wird gemerkt)
Farbschema      dunkel | hell | kontrast | gruen | bernstein
Seed            leer = wuerfeln, oder eine Zahl eintippen
Export-Ordner   wohin die Dateien gehen
```

Hoch/Runter waehlt die Zeile, Links/Rechts aendert den Wert, ENTER
wuerfelt eine neue Karte mit diesen Einstellungen. In der Seed-Zeile
tippt man Ziffern (Entf loescht, Links/Rechts blaettert +/- 1); in der
Ordner-Zeile oeffnet ENTER den Ordnerdialog. Die Artenliste ist
gefiltert: in `klein` stehen nur die 23 Arten, die dort auch etwas
ergeben, und eine gewaehlte Art faellt weg, sobald sie nicht mehr passt.

Mit `E` landet das Gezeigte als PNG, JSON *und* `.tmx` auf der Platte -
ein Abschnitt, der einem gefaellt, ist damit einen Tastendruck von Tiled
entfernt.

## Abschnitte fuer Tiled

Neben der Vollkarte erzeugt derselbe Generator **Abschnitte** - Stuecke
ohne Safezone, Tor und Aussenmauer, zum Zusammensetzen in Tiled:

| Groesse | Kacheln | passt |
|---|---|---|
| `klein` | 16 x 12 | 23 der 26 Arten |
| `mittel` | 32 x 24 | alle 26 |
| `gross` | 48 x 36 | alle 26 |

Die Groessen gehen ineinander auf: ein grosser Abschnitt ist genau neun
kleine. Abschnitte haben keinen Rand, damit zwei Teile nahtlos
aneinanderstossen.

```
python tools/export_tiled.py --seed 4242                  Vollkarte
python tools/export_tiled.py --abschnitt mittel --anzahl 8 --vorschau
python tools/export_tiled.py --abschnitt klein --mode hoehle --seed 7
python tools/pruefe_tiled.py                              Gegenprobe
```

Jeder Export bringt das **komplette CraftPix-Paket** mit - 13 Tilesets
mit ueber 5000 Kacheln (Gelaende, Objekte, Details, animierte Objekte,
Charaktere, Gegner), je rund 100 KB. In Tiled bekommt jedes einen
eigenen Reiter. Der Gelaende-Atlas behaelt dabei `firstgid` 1, damit
die Kacheldaten der Karte unveraendert gueltig bleiben.

Die Kollision steht in der `.tmx` doppelt: **im Tileset je Mauerkachel**
(geht beim Zusammensetzen und Nachmalen mit) und als **Objektebene**
(Momentaufnahme, fuer Engines ohne Kachelkollision). Details in
`tiled_export/README.md`.

In `klein` fehlen `rotunde`, `zellen` und `festung` - konzentrische Ringe,
ein Zimmerraster und verschachtelte Ringmauern brauchen mehr Flaeche als
16 x 12. Gemessen ueber 12 Seeds je Art und Groesse.

## Zwei Wege in die Engine

Es gibt das Godot-Paket in zwei Fassungen - je nachdem, ob die Karte
feststehen oder jedes Mal neu entstehen soll:

| Ordner | Was der Entwickler bekommt |
|---|---|
| `godot_export/` | **eine gebackene Karte.** Fertige `ArenaMap.tscn` mit Kacheln und Hitboxen, Seed und Art gewaehlt. Aendert sich nie, im Editor Kachel fuer Kachel bearbeitbar. |
| `godot_runtime/` | **Zufallskarten zur Laufzeit.** Der Generator selbst, in GDScript. Jeder Start eine andere Karte, 26 Arten, `regenerate()` im laufenden Spiel. |

Beide liegen als ZIP daneben (`ArenaMap_Godot.zip` bzw.
`ArenaRandom_Godot.zip`) und haben eine eigene Einbauanleitung.

Ein Hinweis zu Seeds: der Laufzeitgenerator liefert bei gleicher Zahl
*nicht* dieselbe Karte wie dieses Werkzeug. Godot wuerfelt mit PCG32,
Python mit Mersenne-Twister - gleiche Logik, andere Zahlenfolge. Wer eine
bestimmte Karte aus dem Viewer will, nimmt die gebackene Fassung.

## Projektstruktur

```
ZombieArena/
  main.py            Einstiegspunkt, CLI
  START.bat          Starter fuer Windows
  assets/            benoetigte Grafiken aus dem CraftPix-Pack
  export/            erzeugte Karten (PNG + JSON), Kontaktbogen
  godot_export/      Godot-Paket mit einer gebackenen Karte
  godot_runtime/     Godot-Paket mit dem Generator (Zufallskarten)
  tiled_export/      .tmx-Karten und -Abschnitte fuer Tiled
  ArenaTool.spec   Bauplan fuer die .exe
  BAUEN.bat        baut und prueft sie
  dist/            die fertige ArenaMapTool.exe
  za/
    settings.py      Konstanten, Kartenmasse
    paths.py         Pfade im Projekt und in der .exe
    assetlib.py      Laden/Zerschneiden der Spritesheets
    mapgen.py        prozeduraler Generator, alle Kartenarten
    menu.py          Auswahlmenue (Groesse, Gruppe, Art)
    world.py         Kartenaufbau, Autotiling, Deko, Zeichnen
    viewer.py        Fenster, Kamera, Overlays
  tools/
    kontaktbogen.py       alle Arten auf ein Blatt
    export_tiled.py       .tmx + .tsx fuer Tiled
    pruefe_tiled.py       laesst Tiled den Export gegenlesen
    export_godot.py       Atlas + Kartendaten
    build_scene.gd        Godot baut die .tscn
    verify_scene.gd       Godot prueft sie
    make_godot_package.py die ganze Kette
```

Die Welt wird intern in 480 × 270 gerendert und ganzzahlig hochskaliert; die
Overlays zeichnen in Fensteraufloesung, damit die Schrift scharf bleibt.

## Autotiling

Der Tileset-Block bei Spalte 1–5 / Zeile 1–5 ist ein 3×3-Autotile: der Ring
liefert die Mauerkanten, der 3×3-Kern (Spalte 2–4, Zeile 2–4) den Boden.
`mapgen.wall_tile_coords()` waehlt pro Mauerzelle die Kante anhand der
Nachbarn und faellt bei Innenecken auf die Diagonale zurueck. Voellig
eingeschlossene Zellen (Hinderniskerne) bekommen ein aus dem Randtile
erzeugtes Fuellstueck — sonst blieben dort Loecher.

Die Auswahl steht bewusst in `mapgen` und nicht im Viewer: der
Godot-Export braucht dieselbe Entscheidung, und zwei Implementierungen
wuerden irgendwann auseinanderlaufen — auffallen wuerde es erst in der
Engine. `World._render_ground()` blittet nur noch, was `atlas_map()` sagt.

Das ist der eigentliche Trick: **das Tileset liefert die Kanten, der Code
liefert die Form.** Deshalb kostet eine neue Karte nichts ausser einem Seed.

## Herkunft und Lizenz der Grafiken

Alle Pixel-Art stammt aus dem **CraftPix Free Top Down Roguelike Game Kit**
und liegt in `assets/`. Es gelten die Lizenzbedingungen von CraftPix -
wer dieses Repo benutzt, sollte sie dort nachlesen, bevor er die Grafiken
weitergibt oder in ein eigenes Produkt uebernimmt.

Der Programmcode in `za/`, `tools/`, `main.py` und den Godot-Skripten
haengt nicht daran: er kennt nur ein Zellengitter und Atlas-Koordinaten
und laesst sich mit jedem anderen 16x16-Tileset betreiben.

## Assets

Grafiken: **CraftPix — Free Top Down Roguelike Game Kit (Pixel Art)**.
Unter `assets/` liegen nur noch die von der Karte benutzten Dateien (Tileset,
Kisten, Fackel, Feuer-, Truhen-, Hebel- und Toranimation). Das vollstaendige
Pack liegt weiterhin unter
`C:\Users\budzm\Downloads\craftpix-net-436971-free-top-down-roguelike-game-kit-pixel-art.zip`.
Es gelten die Lizenzbedingungen von CraftPix.
