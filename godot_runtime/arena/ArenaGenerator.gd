# Kartengenerator zur Laufzeit - sechsundzwanzig Arten, ein Geruest.
#
# Portierung des Python-Generators aus dem Autorenwerkzeug. Der Ablauf ist
# derselbe und in derselben Reihenfolge:
#
#   1. Grundriss   Aussenmauer, Safezone oben links, Tor nach rechts
#   2. Schnitt     die Art fuellt das Feld - nur das unterscheidet sich
#   3. Anbindung   Gaenge vom Tor zu dem, was die Art gegraben hat
#   4. Reparatur   Flutfuellung vom Tor; Unerreichbares wird Mauer
#   5. Pruefung    offener Anteil, Bloecke, Spawnpunkte - sonst neuer Anlauf
#
# Schritt 4 ist der Grund, warum die Arten so kurz sein duerfen: eine Art
# muss nicht beweisen, dass sie keine abgeschlossene Blase erzeugt. Sie darf
# welche erzeugen, und sie werden zugemauert.
#
# ACHTUNG zu Seeds: dieselbe Zahl ergibt hier *nicht* dieselbe Karte wie im
# Python-Werkzeug. Godot wuerfelt mit PCG32, Python mit Mersenne-Twister -
# gleiche Logik, andere Zahlenfolge. Innerhalb von Godot ist ein Seed aber
# verlaesslich: gleicher Seed und gleiche Art heisst immer dieselbe Karte.
class_name ArenaGenerator
extends RefCounted

const MAP_W := 68
const MAP_H := 46
const TILE := 16

const ARENA_X0 := 3
const ARENA_Y0 := 3
const ARENA_X1 := 64
const ARENA_Y1 := 42

const VOID := 0
const WALL := 1
const FLOOR := 2
const GATE := 3

# Freie Tiles zwischen zwei Hindernissen - nur die Arena-Arten halten sich
# daran. Die uebrigen erreichen dasselbe ueber die Reparatur.
const MIN_GAP := 3

# Vor dem Tor bleibt frei. Dort steht der Spieler, wenn die Welle startet.
const GATE_CLEAR_X := 7
const GATE_CLEAR_Y := 5

const SPAWN_BORDER := 2
const SPAWN_MIN_GATE := 20
const SPAWN_SPREAD := 5
const SPAWN_MAX := 24

# Vollflaechiges Mauerstueck fuer eingeschlossene Zellen. Im Original-
# Tileset gibt es das nicht; im mitgelieferten Atlas ist es angehaengt.
const FILL_TILE := Vector2i(0, 11)

const GROUPS := ["Arena", "Dungeon", "Organisch", "Labyrinth"]

# gruppe, text, offen_min, offen_max, alles_mauer_zuerst
const MODES := {
	"streu":      ["Arena", "frei verteilte Deckung", 0.85, 0.96, false],
	"gespiegelt": ["Arena", "punktsymmetrische Deckung", 0.85, 0.96, false],
	"ringe":      ["Arena", "Deckung auf drei Ringen", 0.85, 0.96, false],
	"saeulen":    ["Arena", "regelmaessiges Saeulenraster", 0.82, 0.96, false],
	"sektoren":   ["Arena", "Trennwaende mit Durchgaengen", 0.86, 0.98, false],
	"rotunde":    ["Arena", "konzentrische Ringmauern", 0.74, 0.90, false],
	"diagonal":   ["Arena", "schraege Balken", 0.86, 0.99, false],
	"raeume":     ["Dungeon", "BSP-Raeume mit Gaengen", 0.44, 0.74, true],
	"zellen":     ["Dungeon", "Rasterzimmer mit Tueren", 0.60, 0.82, true],
	"kammern":    ["Dungeon", "wenige grosse Hallen", 0.32, 0.60, true],
	"stadt":      ["Dungeon", "Haeuserblocks mit Strassen", 0.44, 0.74, false],
	"festung":    ["Dungeon", "verschachtelte Ringmauern mit Toren", 0.82, 0.96, false],
	"katakomben": ["Dungeon", "viele kleine Kammern", 0.28, 0.52, true],
	"tempel":     ["Dungeon", "achsensymmetrisch um eine Mittelhalle", 0.22, 0.54, true],
	"hoehle":     ["Organisch", "zellulaerer Automat", 0.44, 0.74, true],
	"see":        ["Organisch", "eine grosse offene Hoehle", 0.68, 0.92, true],
	"adern":      ["Organisch", "gewundene Gaenge", 0.25, 0.74, true],
	"inseln":     ["Organisch", "gewachsene Bloecke", 0.76, 0.92, false],
	"risse":      ["Organisch", "Bruchlinien wie gesprungenes Glas", 0.62, 0.95, false],
	"krater":     ["Organisch", "runde Lichtungen im Fels", 0.20, 0.56, true],
	"wurzeln":    ["Organisch", "verzweigte Gaenge vom Tor aus", 0.28, 0.64, true],
	"labyrinth":  ["Labyrinth", "echtes Labyrinth, enge Gaenge", 0.50, 0.64, true],
	"schleifen":  ["Labyrinth", "Labyrinth ohne Sackgassen", 0.52, 0.66, true],
	"hallen":     ["Labyrinth", "Labyrinth mit weiten Gaengen", 0.66, 0.80, true],
	"spirale":    ["Labyrinth", "ein Gang von aussen nach innen", 0.38, 0.66, true],
	"kaefig":     ["Labyrinth", "Gitter mit versetzten Luecken", 0.76, 0.90, false],
}

# --- Zustand eines Bauversuchs ---------------------------------------------
var grid: PackedByteArray
var rng: RandomNumberGenerator

var safe := Vector4i.ZERO          # x0, y0, x1, y1 (Innenraum, inklusive)
var gate := Vector3i.ZERO          # x, y0, y1
var mode := ""
var seed_used := 0
var attempts := 1
var open_ratio := 0.0
var spawns: Array[Vector2i] = []
var blocks: Array = []             # je Mauerteil ein Array[Vector2i]

# Feld, Sperrzone und Mindestabstand als Bitmasken ueber dem Gitter, nicht
# als Dictionary mit Vector2i-Schluesseln. Der Generator fragt millionenfach
# "liegt das im Feld" - als Hash-Zugriff auf einen Vektor kostet das ein
# Vielfaches eines Array-Zugriffs, und die Karte braucht dann Sekunden
# statt Millisekunden.
var _field_mask: PackedByteArray
var _keep_mask: PackedByteArray
var _near_mask: PackedByteArray
var _field_list: Array[Vector2i] = []


static func mode_names() -> Array:
	return MODES.keys()


static func modes_in_group(gruppe: String) -> Array:
	var out := []
	for name in MODES:
		if MODES[name][0] == gruppe:
			out.append(name)
	return out


# ===========================================================================
# Einstieg
# ===========================================================================
static func generate(map_seed: int = 0, want_mode: String = "") -> ArenaGenerator:
	var pick_rng := RandomNumberGenerator.new()
	if map_seed == 0:
		pick_rng.randomize()
		map_seed = pick_rng.randi_range(1, 1000000000)

	var names: Array = MODES.keys()
	var chosen := want_mode
	if chosen == "" or not MODES.has(chosen):
		var r := RandomNumberGenerator.new()
		r.seed = map_seed
		chosen = names[r.randi_range(0, names.size() - 1)]

	# Verworfene Anlaeufe ziehen weiter aus demselben Strom, statt den Seed
	# zu veraendern: der Seed bleibt die Identitaet der Karte.
	var shared := RandomNumberGenerator.new()
	shared.seed = map_seed

	for attempt in range(1, 121):
		var g := ArenaGenerator.new()
		g.rng = shared
		if g._try_build(chosen):
			g.seed_used = map_seed
			g.mode = chosen
			g.attempts = attempt
			return g

	# Notnagel: leere Arena. Haesslich, aber spielbar - besser als nichts.
	var fallback := ArenaGenerator.new()
	fallback.rng = RandomNumberGenerator.new()
	fallback.rng.seed = map_seed
	fallback._new_grid()
	fallback._base()
	fallback.mode = chosen
	fallback.seed_used = map_seed
	fallback.attempts = 120
	fallback.open_ratio = 1.0
	fallback.spawns = fallback._make_spawns()
	fallback.blocks = []
	return fallback


func info() -> Dictionary:
	return {
		"seed": seed_used,
		"mode": mode,
		"group": MODES[mode][0] if MODES.has(mode) else "?",
		"text": MODES[mode][1] if MODES.has(mode) else "",
		"attempts": attempts,
		"open_ratio": open_ratio,
		"blocks": blocks.size(),
		"spawns": spawns.size(),
		"safezone": safe,
		"gate": gate,
	}


# ===========================================================================
# Gitterzugriff
# ===========================================================================
func _new_grid() -> void:
	grid = PackedByteArray()
	grid.resize(MAP_W * MAP_H)
	grid.fill(VOID)


func at(x: int, y: int) -> int:
	if x < 0 or y < 0 or x >= MAP_W or y >= MAP_H:
		return VOID
	return grid[y * MAP_W + x]


func _put(x: int, y: int, value: int) -> void:
	grid[y * MAP_W + x] = value


func walkable(x: int, y: int) -> bool:
	var c := at(x, y)
	return c == FLOOR or c == GATE


func in_field(p: Vector2i) -> bool:
	return _fld(p.x, p.y)


func _fld(x: int, y: int) -> bool:
	if x < 0 or y < 0 or x >= MAP_W or y >= MAP_H:
		return false
	return _field_mask[y * MAP_W + x] == 1


func _kept(x: int, y: int) -> bool:
	return _keep_mask[y * MAP_W + x] == 1


func _is_near(x: int, y: int) -> bool:
	return _near_mask[y * MAP_W + x] == 1


# --- Zufallshelfer ---------------------------------------------------------
func _pick(list: Array):
	return list[rng.randi_range(0, list.size() - 1)]


func _shuffled(list: Array) -> Array:
	# Array.shuffle() zieht aus dem globalen Zufall und wuerde den Seed
	# umgehen - also Fisher-Yates von Hand, mit unserem rng.
	var out := list.duplicate()
	for i in range(out.size() - 1, 0, -1):
		var j := rng.randi_range(0, i)
		var tmp = out[i]
		out[i] = out[j]
		out[j] = tmp
	return out


func _weighted(names: Array, weights: Array) -> String:
	var total := 0
	for w in weights:
		total += w
	var r := rng.randi_range(1, total)
	for i in names.size():
		r -= weights[i]
		if r <= 0:
			return names[i]
	return names[names.size() - 1]


# ===========================================================================
# 1. Grundriss
# ===========================================================================
func _base() -> void:
	for y in range(ARENA_Y0, ARENA_Y1 + 1):
		for x in range(ARENA_X0, ARENA_X1 + 1):
			_put(x, y, FLOOR)
	for x in range(ARENA_X0 - 1, ARENA_X1 + 2):
		_put(x, ARENA_Y0 - 1, WALL)
		_put(x, ARENA_Y1 + 1, WALL)
	for y in range(ARENA_Y0 - 1, ARENA_Y1 + 2):
		_put(ARENA_X0 - 1, y, WALL)
		_put(ARENA_X1 + 1, y, WALL)

	var sx0 := ARENA_X0
	var sy0 := ARENA_Y0
	var sx1 := sx0 + rng.randi_range(13, 17) - 1
	var sy1 := sy0 + rng.randi_range(11, 15) - 1
	var gx := sx1 + 1
	var gy0 := rng.randi_range(sy0 + 3, sy1 - 4)
	var gy1 := gy0 + 1

	for x in range(ARENA_X0 - 1, gx + 1):
		_put(x, sy1 + 1, WALL)
	for y in range(ARENA_Y0 - 1, sy1 + 2):
		_put(gx, y, WALL)
	for y in range(sy0, sy1 + 1):
		for x in range(sx0, sx1 + 1):
			_put(x, y, FLOOR)
	for y in range(gy0, gy1 + 1):
		_put(gx, y, GATE)

	safe = Vector4i(sx0, sy0, sx1, sy1)
	gate = Vector3i(gx, gy0, gy1)


func _build_field() -> void:
	_field_mask = PackedByteArray()
	_field_mask.resize(MAP_W * MAP_H)
	_field_mask.fill(0)
	_field_list.clear()
	var sy1 := safe.w
	var gx := gate.x
	for y in range(ARENA_Y0, ARENA_Y1 + 1):
		for x in range(ARENA_X0, ARENA_X1 + 1):
			if x <= gx and y <= sy1 + 1:
				continue        # Safezone-Block samt ihrer Waende
			_field_mask[y * MAP_W + x] = 1
			_field_list.append(Vector2i(x, y))


func _mark_near(x: int, y: int) -> void:
	for yy in range(maxi(0, y - MIN_GAP), mini(MAP_H, y + MIN_GAP + 1)):
		for xx in range(maxi(0, x - MIN_GAP), mini(MAP_W, x + MIN_GAP + 1)):
			_near_mask[yy * MAP_W + xx] = 1


func _build_masks() -> Array[Vector2i]:
	_near_mask = PackedByteArray()
	_near_mask.resize(MAP_W * MAP_H)
	_near_mask.fill(0)
	_keep_mask = PackedByteArray()
	_keep_mask.resize(MAP_W * MAP_H)
	_keep_mask.fill(0)
	for y in MAP_H:
		for x in MAP_W:
			if at(x, y) == WALL:
				_mark_near(x, y)

	var keep_cells: Array[Vector2i] = []
	var gx := gate.x
	var gy0 := gate.y
	var gy1 := gate.z
	for y in range(maxi(ARENA_Y0, gy0 - GATE_CLEAR_Y),
			mini(ARENA_Y1, gy1 + GATE_CLEAR_Y) + 1):
		for x in range(gx, mini(ARENA_X1, gx + GATE_CLEAR_X) + 1):
			if _fld(x, y):
				_keep_mask[y * MAP_W + x] = 1
				keep_cells.append(Vector2i(x, y))
	return keep_cells


# ===========================================================================
# Werkzeuge fuers Schnittmuster
# ===========================================================================
func _fill_field(value: int) -> void:
	for p in _field_list:
		_put(p.x, p.y, value)


func _carve_rect(x0: int, y0: int, w: int, h: int) -> int:
	var n := 0
	for y in range(y0, y0 + h):
		for x in range(x0, x0 + w):
			if _fld(x, y):
				_put(x, y, FLOOR)
				n += 1
	return n


func _carve_line(x0: int, y0: int, x1: int, y1: int, width: int = 1) -> void:
	var half := int((width - 1) / 2.0)
	if y0 == y1:
		for x in range(mini(x0, x1), maxi(x0, x1) + 1):
			for d in range(-half, width - half):
				if _fld(x, y0 + d):
					_put(x, y0 + d, FLOOR)
	else:
		for y in range(mini(y0, y1), maxi(y0, y1) + 1):
			for d in range(-half, width - half):
				if _fld(x0 + d, y):
					_put(x0 + d, y, FLOOR)


func _outside(cells: Array) -> int:
	var n := 0
	for p in cells:
		if not _fld(p.x, p.y):
			n += 1
	return n


func _corridor(a: Vector2i, b: Vector2i, width: int = 1) -> void:
	# Der Knick geht nicht blind in eine Richtung: die Safezone ist ein Block
	# mitten im Feld, und ein Gang durch sie hindurch wird nicht gegraben -
	# die Verbindung reisst und der Raum haengt ab. Also beide Varianten
	# durchzaehlen und die nehmen, die weniger im Nichts liegt.
	var weg1: Array[Vector2i] = []
	for x in range(mini(a.x, b.x), maxi(a.x, b.x) + 1):
		weg1.append(Vector2i(x, a.y))
	for y in range(mini(a.y, b.y), maxi(a.y, b.y) + 1):
		weg1.append(Vector2i(b.x, y))
	var weg2: Array[Vector2i] = []
	for y in range(mini(a.y, b.y), maxi(a.y, b.y) + 1):
		weg2.append(Vector2i(a.x, y))
	for x in range(mini(a.x, b.x), maxi(a.x, b.x) + 1):
		weg2.append(Vector2i(x, b.y))

	var n1 := _outside(weg1)
	var n2 := _outside(weg2)
	var erst_waagerecht := (n1 < n2) if n1 != n2 else (rng.randf() < 0.5)

	if erst_waagerecht:
		_carve_line(a.x, a.y, b.x, a.y, width)
		_carve_line(b.x, a.y, b.x, b.y, width)
	else:
		_carve_line(a.x, a.y, a.x, b.y, width)
		_carve_line(a.x, b.y, b.x, b.y, width)


func _anchor(room: Rect2i) -> Vector2i:
	# Der geometrische Mittelpunkt taugt nicht: faellt er in den Safezone-
	# Block, beginnt jeder Gang von dort im Nichts und der Raum haengt ab.
	var c := Vector2i(room.position.x + int(room.size.x / 2.0),
			room.position.y + int(room.size.y / 2.0))
	if _fld(c.x, c.y):
		return c
	var best := Vector2i(-1, -1)
	var best_d := -1
	for y in range(room.position.y, room.position.y + room.size.y):
		for x in range(room.position.x, room.position.x + room.size.x):
			var p := Vector2i(x, y)
			if not _fld(p.x, p.y):
				continue
			var d: int = (x - c.x) * (x - c.x) + (y - c.y) * (y - c.y)
			if best_d < 0 or d < best_d:
				best_d = d
				best = p
	return best


func _rooms_connect(rooms: Array, width: int) -> void:
	var centres: Array[Vector2i] = []
	for r in rooms:
		var a := _anchor(r)
		if a.x >= 0:
			centres.append(a)
	if centres.size() < 2:
		return
	for i in range(1, centres.size()):
		_corridor(centres[i - 1], centres[i], width)
	# Nur die Kette gaebe einen Baum: genau ein Weg zwischen zwei Raeumen,
	# und jede Begegnung wird zur Sackgasse.
	for _i in range(maxi(1, int(centres.size() / 4.0))):
		var a := rng.randi_range(0, centres.size() - 1)
		var b := rng.randi_range(0, centres.size() - 1)
		if a != b:
			_corridor(centres[a], centres[b], width)


func _set_wall(x: int, y: int) -> void:
	var p := Vector2i(x, y)
	if _fld(p.x, p.y) and not _kept(p.x, p.y):
		_put(x, y, WALL)


# ===========================================================================
# Arena-Arten: offene Flaeche, Hindernisse hinein
# ===========================================================================
func _normalise(cells: Array) -> Array:
	var mx := 1 << 30
	var my := 1 << 30
	for c in cells:
		mx = mini(mx, c.x)
		my = mini(my, c.y)
	var seen := {}
	var out := []
	for c in cells:
		var p := Vector2i(c.x - mx, c.y - my)
		if not seen.has(p):
			seen[p] = true
			out.append(p)
	return out


func _rotate(cells: Array, times: int) -> Array:
	var out := cells.duplicate()
	for _i in range(times % 4):
		var next := []
		for c in out:
			next.append(Vector2i(-c.y, c.x))
		out = next
	return _normalise(out)


func _shape() -> Array:
	var kind := _weighted(["block", "balken", "ecke", "kreuz", "doppel"],
			[32, 22, 20, 12, 14])
	var cells := []

	if kind == "block":
		var w := rng.randi_range(2, 4)
		var h := rng.randi_range(2, 4)
		for y in h:
			for x in w:
				cells.append(Vector2i(x, y))
		return cells

	if kind == "balken":
		var n := rng.randi_range(4, 7)
		var t: int = _pick([1, 2])
		if rng.randf() < 0.5:
			for y in t:
				for x in n:
					cells.append(Vector2i(x, y))
		else:
			for y in n:
				for x in t:
					cells.append(Vector2i(x, y))
		return cells

	if kind == "ecke":
		var a := rng.randi_range(3, 5)
		var b := rng.randi_range(3, 5)
		for x in a:
			cells.append(Vector2i(x, 0))
		for y in range(1, b):
			cells.append(Vector2i(0, y))
		return _rotate(cells, rng.randi_range(0, 3))

	if kind == "kreuz":
		var r := rng.randi_range(1, 2)
		for y in (2 * r + 1):
			cells.append(Vector2i(r, y))
		for x in (2 * r + 1):
			cells.append(Vector2i(x, r))
		return _normalise(cells)

	# doppel: zwei Bloecke mit zwei Tiles Schlitz. Der Schlitz unterschreitet
	# MIN_GAP absichtlich - das ist die Stelle, durch die man sich quetscht.
	var bw := rng.randi_range(2, 3)
	var bh := rng.randi_range(2, 3)
	for y in bh:
		for x in bw:
			cells.append(Vector2i(x, y))
	if rng.randf() < 0.5:
		for y in bh:
			for x in bw:
				cells.append(Vector2i(x + bw + 2, y))
	else:
		for y in bh:
			for x in bw:
				cells.append(Vector2i(x, y + bh + 2))
	return _normalise(cells)


func _stamp(cells: Array, ox: int, oy: int) -> bool:
	var put: Array[Vector2i] = []
	for c in cells:
		var p := Vector2i(ox + c.x, oy + c.y)
		if not _fld(p.x, p.y) or _kept(p.x, p.y) or _is_near(p.x, p.y):
			return false
		if at(p.x, p.y) != FLOOR:
			return false
		put.append(p)
	for p in put:
		_put(p.x, p.y, WALL)
		_mark_near(p.x, p.y)
	return true


func _scatter(arrangement: String) -> void:
	var target := rng.randi_range(16, 26)
	var placed := 0
	var tries := 0
	while placed < target and tries < 1200:
		tries += 1
		var cells := _shape()
		var w := 0
		var h := 0
		for c in cells:
			w = maxi(w, c.x + 1)
			h = maxi(h, c.y + 1)

		var ox := 0
		var oy := 0
		if arrangement == "ringe":
			var cx := (ARENA_X0 + ARENA_X1) / 2.0
			var cy := (ARENA_Y0 + ARENA_Y1) / 2.0
			var ring: float = _pick([0.32, 0.55, 0.80])
			var ang := rng.randf_range(0.0, TAU)
			ox = int(round(cx + cos(ang) * ring * (ARENA_X1 - ARENA_X0) / 2.0 - w / 2.0))
			oy = int(round(cy + sin(ang) * ring * (ARENA_Y1 - ARENA_Y0) / 2.0 - h / 2.0))
		else:
			ox = rng.randi_range(ARENA_X0, ARENA_X1 - w + 1)
			oy = rng.randi_range(ARENA_Y0, ARENA_Y1 - h + 1)

		if not _stamp(cells, ox, oy):
			continue
		placed += 1

		if arrangement == "gespiegelt":
			var mirror := []
			for c in cells:
				mirror.append(Vector2i(w - 1 - c.x, h - 1 - c.y))
			mirror = _normalise(mirror)
			var mox := ARENA_X0 + ARENA_X1 - (ox + w - 1)
			var moy := ARENA_Y0 + ARENA_Y1 - (oy + h - 1)
			if _stamp(mirror, mox, moy):
				placed += 1


func _carve_saeulen() -> void:
	# Kein Zufall in der Anordnung, nur in den Massen: gleichmaessige
	# Deckung liest sich als gebaut und nicht als hingewuerfelt.
	var pw: int = _pick([2, 3])
	var ph: int = _pick([2, 3])
	var gap_x := rng.randi_range(4, 6)
	var gap_y := rng.randi_range(4, 6)
	var cells := []
	for y in ph:
		for x in pw:
			cells.append(Vector2i(x, y))
	var y0 := ARENA_Y0 + rng.randi_range(0, gap_y)
	while y0 <= ARENA_Y1 - ph + 1:
		var x0 := ARENA_X0 + rng.randi_range(0, gap_x)
		while x0 <= ARENA_X1 - pw + 1:
			_stamp(cells, x0, y0)
			x0 += pw + gap_x
		y0 += ph + gap_y


func _carve_sektoren() -> void:
	# Die Waende reichen nie ganz bis an die Aussenmauer. Sonst teilt eine
	# einzige Wand die Arena wirklich, und wenn die Durchgaenge ungluecklich
	# fallen, mauert die Reparatur eine Haelfte komplett zu.
	for _i in range(rng.randi_range(3, 5)):
		var margin := rng.randi_range(2, 4)
		var run: Array[Vector2i] = []
		if rng.randf() < 0.5:
			var y := rng.randi_range(ARENA_Y0 + 5, ARENA_Y1 - 5)
			for x in range(ARENA_X0 + margin, ARENA_X1 - margin + 1):
				run.append(Vector2i(x, y))
		else:
			var x := rng.randi_range(ARENA_X0 + 5, ARENA_X1 - 5)
			for y in range(ARENA_Y0 + margin, ARENA_Y1 - margin + 1):
				run.append(Vector2i(x, y))

		var frei: Array[Vector2i] = []
		for p in run:
			if _fld(p.x, p.y) and not _kept(p.x, p.y):
				frei.append(p)
		if frei.size() < 12:
			continue
		var gaps := {}
		for _g in range(rng.randi_range(2, 3)):
			var centre := rng.randi_range(3, frei.size() - 4)
			for d in range(-1, rng.randi_range(1, 2) + 1):
				gaps[centre + d] = true
		for i in frei.size():
			if not gaps.has(i) and at(frei[i].x, frei[i].y) == FLOOR:
				_put(frei[i].x, frei[i].y, WALL)


func _carve_rotunde() -> void:
	var cx := (ARENA_X0 + ARENA_X1) / 2.0
	var cy := (ARENA_Y0 + ARENA_Y1) / 2.0
	var rings := rng.randi_range(3, 4)
	for k in range(1, rings + 1):
		var f := float(k) / float(rings)
		var rx := f * (ARENA_X1 - ARENA_X0) / 2.0 * 0.92
		var ry := f * (ARENA_Y1 - ARENA_Y0) / 2.0 * 0.92
		if rx < 3.0 or ry < 3.0:
			continue
		var gaps := []
		for _g in range(rng.randi_range(2, 3)):
			gaps.append(rng.randf_range(0.0, TAU))
		var scale := minf(rx, ry)
		for p in _field_list:
			var d := sqrt(pow((p.x - cx) / rx, 2.0) + pow((p.y - cy) / ry, 2.0))
			if absf(d - 1.0) * scale > 0.7:
				continue
			var ang := fposmod(atan2(p.y - cy, p.x - cx), TAU)
			var im_tor := false
			for g in gaps:
				if absf(fposmod(ang - g + PI, TAU) - PI) < 0.28:
					im_tor = true
					break
			if not im_tor:
				_set_wall(p.x, p.y)


func _carve_diagonal() -> void:
	for _i in range(rng.randi_range(8, 13)):
		var x := rng.randi_range(ARENA_X0, ARENA_X1)
		var y := rng.randi_range(ARENA_Y0, ARENA_Y1)
		var sx: int = _pick([1, -1])
		var sy: int = _pick([1, -1])
		var length := rng.randi_range(6, 15)
		var thick: int = _pick([1, 1, 2])
		for i in length:
			for t in thick:
				_set_wall(x + i * sx, y + i * sy + t)


func _carve_stadt() -> void:
	# Die Blocks sind massiv - man geht nicht hinein, man geht darum herum.
	# Die Strassen sind per Konstruktion durchgehend.
	var street := rng.randi_range(3, 4)
	var bw := rng.randi_range(6, 10)
	var bh := rng.randi_range(5, 8)
	var y := ARENA_Y0 + rng.randi_range(0, street)
	while y <= ARENA_Y1:
		var x := ARENA_X0 + rng.randi_range(0, street)
		while x <= ARENA_X1:
			var w := mini(bw, ARENA_X1 - x + 1)
			var h := mini(bh, ARENA_Y1 - y + 1)
			if w >= 3 and h >= 3:
				for yy in range(y, y + h):
					for xx in range(x, x + w):
						_set_wall(xx, yy)
			x += bw + street
		y += bh + street


func _carve_festung() -> void:
	var rings := rng.randi_range(2, 3)
	var step_x := maxi(3, int((ARENA_X1 - ARENA_X0) / float(2 * (rings + 1))))
	var step_y := maxi(3, int((ARENA_Y1 - ARENA_Y0) / float(2 * (rings + 1))))
	for k in range(1, rings + 1):
		var x0 := ARENA_X0 + k * step_x
		var x1 := ARENA_X1 - k * step_x
		var y0 := ARENA_Y0 + k * step_y
		var y1 := ARENA_Y1 - k * step_y
		if x1 - x0 < 7 or y1 - y0 < 7:
			break
		var sides := {}
		var n_run: Array[Vector2i] = []
		var s_run: Array[Vector2i] = []
		for x in range(x0, x1 + 1):
			n_run.append(Vector2i(x, y0))
			s_run.append(Vector2i(x, y1))
		var w_run: Array[Vector2i] = []
		var o_run: Array[Vector2i] = []
		for y in range(y0, y1 + 1):
			w_run.append(Vector2i(x0, y))
			o_run.append(Vector2i(x1, y))
		sides["n"] = n_run
		sides["s"] = s_run
		sides["w"] = w_run
		sides["o"] = o_run

		var namen := _shuffled(["n", "o", "s", "w"])
		var offen := [namen[0], namen[1]]
		for name in sides:
			var run: Array = sides[name]
			var gap := {}
			if offen.has(name) and run.size() > 9:
				var c := rng.randi_range(3, run.size() - 4)
				gap[c - 1] = true
				gap[c] = true
				gap[c + 1] = true
			for i in run.size():
				if not gap.has(i):
					_set_wall(run[i].x, run[i].y)


func _carve_kaefig() -> void:
	var step := rng.randi_range(5, 8)
	for x in range(ARENA_X0 + step, ARENA_X1, step):
		for y in range(ARENA_Y0, ARENA_Y1 + 1):
			_set_wall(x, y)
	for y in range(ARENA_Y0 + step, ARENA_Y1, step):
		for x in range(ARENA_X0, ARENA_X1 + 1):
			_set_wall(x, y)
	# Je Masche und Seite eine Luecke: damit ist jedes Feld erreichbar,
	# ohne dass das Gitter seine Form verliert.
	for x in range(ARENA_X0 + step, ARENA_X1, step):
		for base in range(ARENA_Y0, ARENA_Y1, step):
			var cy := base + rng.randi_range(1, maxi(1, step - 1))
			for d in 2:
				if _fld(x, cy + d):
					_put(x, cy + d, FLOOR)
	for y in range(ARENA_Y0 + step, ARENA_Y1, step):
		for base in range(ARENA_X0, ARENA_X1, step):
			var cx := base + rng.randi_range(1, maxi(1, step - 1))
			for d in 2:
				if _fld(cx + d, y):
					_put(cx + d, y, FLOOR)


func _carve_inseln() -> void:
	for _i in range(rng.randi_range(16, 24)):
		var start: Vector2i = _pick(_field_list)
		var size := rng.randi_range(14, 45)
		var x := start.x
		var y := start.y
		for _s in range(size):
			_set_wall(x, y)
			var step: Vector2i = _pick([Vector2i(1, 0), Vector2i(-1, 0),
					Vector2i(0, 1), Vector2i(0, -1)])
			x = clampi(x + step.x, ARENA_X0, ARENA_X1)
			y = clampi(y + step.y, ARENA_Y0, ARENA_Y1)


func _carve_risse() -> void:
	var seeds: Array[Vector2i] = []
	for _i in range(rng.randi_range(10, 16)):
		seeds.append(_pick(_field_list))

	var region := {}
	var riss: Array[Vector2i] = []
	for p in _field_list:
		var d1 := 1 << 30
		var d2 := 1 << 30
		var best := 0
		for i in seeds.size():
			var s := seeds[i]
			var d: int = (p.x - s.x) * (p.x - s.x) + (p.y - s.y) * (p.y - s.y)
			if d < d1:
				d2 = d1
				d1 = d
				best = i
			elif d < d2:
				d2 = d
		region[p] = best
		if sqrt(float(d2)) - sqrt(float(d1)) < 1.1:
			riss.append(p)

	for p in riss:
		_set_wall(p.x, p.y)

	# Ein Durchbruch je Nachbarschaft, nicht ein paar zufaellige. Zufaellige
	# Loecher trafen meist dieselbe Linie doppelt und andere gar nicht - im
	# Schnitt blieb die halbe Karte abgehaengt und wurde zu Fels.
	var paare := {}
	for p in riss:
		var ids := {}
		for n in [Vector2i(p.x - 1, p.y), Vector2i(p.x + 1, p.y),
				Vector2i(p.x, p.y - 1), Vector2i(p.x, p.y + 1)]:
			if region.has(n):
				ids[region[n]] = true
		if ids.size() >= 2:
			var keys := ids.keys()
			keys.sort()
			var key := Vector2i(keys[0], keys[1])
			if not paare.has(key):
				paare[key] = []
			paare[key].append(p)
	for key in paare:
		var stellen: Array = paare[key]
		var c: Vector2i = _pick(stellen)
		for yy in range(c.y - 1, c.y + 2):
			for xx in range(c.x - 1, c.x + 2):
				if _fld(xx, yy):
					_put(xx, yy, FLOOR)


# ===========================================================================
# Dungeon-Arten: alles Mauer, dann Raeume und Gaenge hinein
# ===========================================================================
func _bsp(rect: Rect2i, min_w: int, min_h: int, depth: int) -> Array:
	var can_v := rect.size.x >= min_w * 2 + 1
	var can_h := rect.size.y >= min_h * 2 + 1
	if depth <= 0 or not (can_v or can_h):
		return [rect]
	var horizontal := (rng.randf() < 0.5) if (can_v and can_h) else can_h
	var parts := []
	if horizontal:
		var cut := rng.randi_range(min_h, rect.size.y - min_h)
		parts = [
			Rect2i(rect.position, Vector2i(rect.size.x, cut)),
			Rect2i(Vector2i(rect.position.x, rect.position.y + cut),
					Vector2i(rect.size.x, rect.size.y - cut)),
		]
	else:
		var cut := rng.randi_range(min_w, rect.size.x - min_w)
		parts = [
			Rect2i(rect.position, Vector2i(cut, rect.size.y)),
			Rect2i(Vector2i(rect.position.x + cut, rect.position.y),
					Vector2i(rect.size.x - cut, rect.size.y)),
		]
	var out := []
	for p in parts:
		out += _bsp(p, min_w, min_h, depth - 1)
	return out


func _carve_raeume() -> void:
	_fill_field(WALL)
	var leaves := _bsp(Rect2i(ARENA_X0, ARENA_Y0,
			ARENA_X1 - ARENA_X0 + 1, ARENA_Y1 - ARENA_Y0 + 1),
			rng.randi_range(8, 11), rng.randi_range(7, 9), 5)
	var rooms := []
	for leaf in leaves:
		var w: int = leaf.size.x
		var h: int = leaf.size.y
		var rw := rng.randi_range(maxi(3, w - 6), maxi(4, w - 2))
		var rh := rng.randi_range(maxi(3, h - 5), maxi(4, h - 2))
		var rx: int = leaf.position.x + rng.randi_range(1, maxi(1, w - rw - 1))
		var ry: int = leaf.position.y + rng.randi_range(1, maxi(1, h - rh - 1))
		if _carve_rect(rx, ry, rw, rh) > 0:
			rooms.append(Rect2i(rx, ry, rw, rh))
	if not rooms.is_empty():
		_rooms_connect(_shuffled(rooms), _pick([1, 2]))


static func _edge_key(a: Vector2i, b: Vector2i) -> Vector4i:
	# Kante ohne Richtung: die kleinere Zelle zuerst, damit (a,b) und (b,a)
	# denselben Schluessel ergeben.
	if b.y < a.y or (b.y == a.y and b.x < a.x):
		return Vector4i(b.x, b.y, a.x, a.y)
	return Vector4i(a.x, a.y, b.x, b.y)


func _grid_edges(cols: int, rows: int, extra: float, allowed: Dictionary) -> Array:
	# `allowed` schraenkt auf tatsaechlich vorhandene Zimmer ein. Die
	# Safezone belegt eine Ecke des Rasters, dort entsteht gar kein Zimmer,
	# und ein Baum ueber das volle Raster haengt echte Zimmer an solche
	# Phantome. Die Tuer dorthin wird nie gegraben, das Zimmer ist ab.
	var cells := []
	for r in rows:
		for c in cols:
			var p := Vector2i(c, r)
			if allowed.is_empty() or allowed.has(p):
				cells.append(p)
	if cells.is_empty():
		return []
	var pool := {}
	for c in cells:
		pool[c] = true

	var start: Vector2i = _pick(cells)
	var seen := {start: true}
	var stack: Array[Vector2i] = [start]
	var edges := []
	while not stack.is_empty():
		var cur: Vector2i = stack[stack.size() - 1]
		var nbrs := []
		for d: Vector2i in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
			var n := cur + d
			if pool.has(n) and not seen.has(n):
				nbrs.append(n)
		if nbrs.is_empty():
			stack.pop_back()
			continue
		var n2: Vector2i = _pick(nbrs)
		edges.append([cur, n2])
		seen[n2] = true
		stack.append(n2)

	if extra > 0.0:
		var have := {}
		for e in edges:
			have[_edge_key(e[0], e[1])] = true
		var rest := []
		for c: Vector2i in cells:
			for d: Vector2i in [Vector2i(1, 0), Vector2i(0, 1)]:
				var n: Vector2i = c + d
				if not pool.has(n):
					continue
				if not have.has(_edge_key(c, n)):
					rest.append([c, n])
		rest = _shuffled(rest)
		var take := int(rest.size() * extra)
		for i in mini(take, rest.size()):
			edges.append(rest[i])
	return edges


func _carve_zellen() -> void:
	_fill_field(WALL)
	# Erst die Anzahl waehlen, dann die Grenzen daraus rechnen. Andersherum -
	# feste Zimmergroesse, Spaltenzahl per Ganzzahldivision - bleibt rechts
	# und unten ein Rest stehen, den nie jemand betritt.
	var cols := rng.randi_range(4, 6)
	var rows := rng.randi_range(3, 5)
	var span_x := ARENA_X1 - ARENA_X0 + 1
	var span_y := ARENA_Y1 - ARENA_Y0 + 1
	var xs := []
	var ys := []
	for i in range(cols + 1):
		xs.append(ARENA_X0 + int(span_x * i / float(cols)))
	for i in range(rows + 1):
		ys.append(ARENA_Y0 + int(span_y * i / float(rows)))

	var real := {}
	for r in rows:
		for c in cols:
			var x0: int = xs[c]
			var x1: int = xs[c + 1] - 1
			var y0: int = ys[r]
			var y1: int = ys[r + 1] - 1
			if _carve_rect(x0 + 1, y0 + 1, x1 - x0 - 1, y1 - y0 - 1) > 0:
				real[Vector2i(c, r)] = true

	for e in _grid_edges(cols, rows, 0.25, real):
		var a: Vector2i = e[0]
		var b: Vector2i = e[1]
		if a.x == b.x:                       # Tuer nach unten
			var y: int = ys[maxi(a.y, b.y)]
			var x0: int = xs[a.x]
			var x1: int = xs[a.x + 1] - 1
			var lo := mini(x0 + 2, x1 - 1)
			var hi := maxi(x0 + 2, x1 - 2)
			var dx := rng.randi_range(mini(lo, hi), maxi(lo, hi))
			_carve_line(dx, y - 1, dx, y + 1, _pick([1, 2]))
		else:                                # Tuer nach rechts
			var x: int = xs[maxi(a.x, b.x)]
			var y0: int = ys[a.y]
			var y1: int = ys[a.y + 1] - 1
			var lo := mini(y0 + 2, y1 - 1)
			var hi := maxi(y0 + 2, y1 - 2)
			var dy := rng.randi_range(mini(lo, hi), maxi(lo, hi))
			_carve_line(x - 1, dy, x + 1, dy, _pick([1, 2]))


func _place_rooms(count: int, w_lo: int, w_hi: int, h_lo: int, h_hi: int) -> Array:
	var rooms := []
	for _i in range(count):
		for _try in range(40):
			var w := rng.randi_range(w_lo, w_hi)
			var h := rng.randi_range(h_lo, h_hi)
			var x := rng.randi_range(ARENA_X0, ARENA_X1 - w + 1)
			var y := rng.randi_range(ARENA_Y0, ARENA_Y1 - h + 1)
			var kollision := false
			for r in rooms:
				if x < r.position.x + r.size.x + 2 and r.position.x < x + w + 2 \
						and y < r.position.y + r.size.y + 2 and r.position.y < y + h + 2:
					kollision = true
					break
			if kollision:
				continue
			if _carve_rect(x, y, w, h) > 0:
				rooms.append(Rect2i(x, y, w, h))
			break
	return rooms


func _carve_kammern() -> void:
	_fill_field(WALL)
	var rooms := _place_rooms(rng.randi_range(5, 8), 9, 16, 7, 13)
	if not rooms.is_empty():
		_rooms_connect(rooms, _pick([3, 4]))


func _carve_katakomben() -> void:
	_fill_field(WALL)
	var rooms := _place_rooms(rng.randi_range(20, 30), 3, 6, 3, 5)
	if not rooms.is_empty():
		_rooms_connect(_shuffled(rooms), 1)


func _carve_tempel() -> void:
	# Symmetrie an der Senkrechten, nicht am Punkt: das liest sich als
	# gebaut. Die Safezone bricht sie oben links - was dort haette entstehen
	# sollen, faellt weg, der Spiegel rechts bleibt.
	_fill_field(WALL)
	var mid := int((ARENA_X0 + ARENA_X1) / 2.0)
	var hall := rng.randi_range(4, 7)
	_carve_rect(mid - int(hall / 2.0), ARENA_Y0 + 1, hall, ARENA_Y1 - ARENA_Y0 - 1)
	for _i in range(rng.randi_range(4, 6)):
		var w := rng.randi_range(6, 11)
		var h := rng.randi_range(5, 9)
		var hi := mid - int(hall / 2.0) - w - 1
		if hi <= ARENA_X0:
			continue
		var x := rng.randi_range(ARENA_X0, hi)
		var y := rng.randi_range(ARENA_Y0, ARENA_Y1 - h + 1)
		var mx := ARENA_X0 + ARENA_X1 - (x + w - 1)
		for rx in [x, mx]:
			_carve_rect(rx, y, w, h)
			_carve_line(rx + int(w / 2.0), y + int(h / 2.0), mid, y + int(h / 2.0), 1)


func _carve_krater() -> void:
	_fill_field(WALL)
	var centres: Array[Vector2i] = []
	for _i in range(rng.randi_range(5, 8)):
		var r := rng.randi_range(4, 8)
		var c := Vector2i(-1, -1)
		for _try in range(30):
			var cand := Vector2i(rng.randi_range(ARENA_X0 + r, ARENA_X1 - r),
					rng.randi_range(ARENA_Y0 + r, ARENA_Y1 - r))
			# Ein Mittelpunkt im Safezone-Block ergaebe eine Lichtung, die
			# kaum gegraben wird und an der jeder Gang vorbeilaeuft.
			if _fld(cand.x, cand.y):
				c = cand
				break
		if c.x < 0:
			continue
		for y in range(c.y - r, c.y + r + 1):
			for x in range(c.x - r, c.x + r + 1):
				if (x - c.x) * (x - c.x) + (y - c.y) * (y - c.y) <= r * r \
						and _fld(x, y):
					_put(x, y, FLOOR)
		centres.append(c)
	for i in range(1, centres.size()):
		_corridor(centres[i - 1], centres[i], _pick([2, 3]))


# ===========================================================================
# Organische Arten
# ===========================================================================
func _neighbour_walls(snapshot: PackedByteArray, x: int, y: int) -> int:
	# Was ausserhalb des Feldes liegt, zaehlt als Mauer - sonst frisst sich
	# die Hoehle in die Aussenmauer und in die Safezone.
	var n := 0
	for dy: int in [-1, 0, 1]:
		for dx: int in [-1, 0, 1]:
			if dx == 0 and dy == 0:
				continue
			var nx := x + dx
			var ny := y + dy
			if not _fld(nx, ny) or snapshot[ny * MAP_W + nx] == WALL:
				n += 1
	return n


func _smooth(rounds: int) -> void:
	# Die 4-5-Regel. Eine einzige Schwelle fuer alle Zellen waere falsch:
	# bei 45 Prozent Startdichte hat eine Zelle im Schnitt 3,7 Mauernachbarn,
	# faellt also unter jede Schwelle von 5 - und die Hoehle waere nach zwei
	# Runden ein leerer Saal. Bestehende Mauer haelt sich schon bei 4.
	for _r in range(rounds):
		# Schnappschuss des Gitters statt eines Dictionarys mit Vector2i-
		# Schluesseln: gelesen wird ohnehin der Stand von vor der Runde,
		# und ein kopiertes PackedByteArray ist um ein Vielfaches billiger
		# als zweitausend Hash-Eintraege pro Durchgang.
		var snapshot := grid.duplicate()
		for p in _field_list:
			var n := _neighbour_walls(snapshot, p.x, p.y)
			var war_mauer := snapshot[p.y * MAP_W + p.x] == WALL
			var schwelle := 4 if war_mauer else 5
			_put(p.x, p.y, WALL if n >= schwelle else FLOOR)


func _carve_cave(density: float, rounds: int) -> void:
	for p in _field_list:
		_put(p.x, p.y, WALL if rng.randf() < density else FLOOR)
	_smooth(rounds)


func _carve_adern() -> void:
	# Zwei Dinge machen den Unterschied. Genug Schritte: ein Zufallsweg
	# laeuft staendig ueber sich selbst, ein Schritt pro Zelle graebt darum
	# nur ein Fuenftel frei. Und alle weiteren Wanderer starten auf schon
	# Gegrabenem - sonst legt jeder sein eigenes, unerreichbares Gangnetz an.
	_fill_field(WALL)
	var carved: Array[Vector2i] = []
	var walkers := rng.randi_range(3, 6)
	var steps := int(_field_list.size() * rng.randf_range(1.6, 2.6) / walkers)
	var gx := gate.x
	var mitte := int((gate.y + gate.z) / 2.0)
	for w in walkers:
		var x := gx + 2
		var y := mitte
		if w > 0 and not carved.is_empty():
			var s: Vector2i = _pick(carved)
			x = s.x
			y = s.y
		var brush: int = _pick([1, 1, 2])
		for _s in range(steps):
			for dy in brush:
				for dx in brush:
					var p := Vector2i(x + dx, y + dy)
					if _fld(p.x, p.y) and at(p.x, p.y) != FLOOR:
						_put(p.x, p.y, FLOOR)
						carved.append(p)
			var step: Vector2i = _pick([Vector2i(1, 0), Vector2i(-1, 0),
					Vector2i(0, 1), Vector2i(0, -1)])
			x = clampi(x + step.x, ARENA_X0, ARENA_X1)
			y = clampi(y + step.y, ARENA_Y0, ARENA_Y1)


func _carve_wurzeln() -> void:
	_fill_field(WALL)
	var mitte := int((gate.y + gate.z) / 2.0)
	# Zwei Staemme statt einem, und breiter: mit einem einzigen duennen Ast
	# blieben knapp ueber zehn Prozent der Karte begehbar.
	_branch(gate.x + 2, mitte, 0.0, rng.randi_range(14, 20), 4, 5)
	_branch(gate.x + 2, mitte, rng.randf_range(0.6, 1.2), rng.randi_range(12, 18), 4, 5)


func _branch(x: int, y: int, ang: float, length: int, width: int, depth: int) -> void:
	if depth <= 0 or length < 3:
		return
	for i in range(length + 1):
		var nx := int(round(x + cos(ang) * i))
		var ny := int(round(y + sin(ang) * i))
		for dy in width:
			for dx in width:
				if _fld(nx + dx, ny + dy):
					_put(nx + dx, ny + dy, FLOOR)
	var ex := int(round(x + cos(ang) * length))
	var ey := int(round(y + sin(ang) * length))
	for _i in range(rng.randi_range(2, 4)):
		_branch(ex, ey, ang + rng.randf_range(-1.0, 1.0),
				int(length * rng.randf_range(0.65, 0.9)),
				maxi(2, width - (1 if rng.randf() < 0.35 else 0)),
				depth - 1)


# ===========================================================================
# Labyrinth-Arten
# ===========================================================================
func _maze() -> void:
	_fill_field(WALL)
	# Startzellen im Zweierschritt, damit zwischen zwei Gangzellen immer
	# genau eine Mauer Platz hat.
	var starts: Array[Vector2i] = []
	for y in range(ARENA_Y0, ARENA_Y1 + 1, 2):
		for x in range(ARENA_X0, ARENA_X1 + 1, 2):
			var p := Vector2i(x, y)
			if _fld(p.x, p.y):
				starts.append(p)
	if starts.is_empty():
		return
	var start: Vector2i = _pick(starts)
	_put(start.x, start.y, FLOOR)
	var stack: Array[Vector2i] = [start]
	var seen := {start: true}
	while not stack.is_empty():
		var cur: Vector2i = stack[stack.size() - 1]
		var nbrs := []
		for d: Vector2i in [Vector2i(2, 0), Vector2i(-2, 0), Vector2i(0, 2), Vector2i(0, -2)]:
			var n := cur + d
			if seen.has(n) or not _fld(n.x, n.y):
				continue
			nbrs.append([n, cur + d / 2])
		if nbrs.is_empty():
			stack.pop_back()
			continue
		var pick: Array = _pick(nbrs)
		var n2: Vector2i = pick[0]
		var between: Vector2i = pick[1]
		_put(between.x, between.y, FLOOR)
		_put(n2.x, n2.y, FLOOR)
		seen[n2] = true
		stack.append(n2)


func _ring_corridor() -> void:
	# Ohne ihn ist ein Labyrinth in diesem Grundriss haesslich: die Safezone
	# sitzt in einer Ecke und schneidet Aeste ab, die dann zugemauert werden.
	for x in range(ARENA_X0, ARENA_X1 + 1):
		for y in [ARENA_Y0, ARENA_Y1]:
			if _fld(x, y):
				_put(x, y, FLOOR)
	for y in range(ARENA_Y0, ARENA_Y1 + 1):
		for x in [ARENA_X0, ARENA_X1]:
			if _fld(x, y):
				_put(x, y, FLOOR)


func _carve_schleifen() -> void:
	_maze()
	_ring_corridor()
	for _r in 2:
		var dead: Array[Vector2i] = []
		for p in _field_list:
			if at(p.x, p.y) != FLOOR:
				continue
			var open_n := 0
			for n in [Vector2i(p.x - 1, p.y), Vector2i(p.x + 1, p.y),
					Vector2i(p.x, p.y - 1), Vector2i(p.x, p.y + 1)]:
				if walkable(n.x, n.y):
					open_n += 1
			if open_n == 1:
				dead.append(p)
		for p in dead:
			var walls := []
			for n in [Vector2i(p.x - 1, p.y), Vector2i(p.x + 1, p.y),
					Vector2i(p.x, p.y - 1), Vector2i(p.x, p.y + 1)]:
				if _fld(n.x, n.y) and at(n.x, n.y) == WALL:
					walls.append(n)
			if not walls.is_empty() and rng.randf() < 0.75:
				var w: Vector2i = _pick(walls)
				_put(w.x, w.y, FLOOR)


func _carve_hallen() -> void:
	_fill_field(WALL)
	var step := 4
	var cells: Array[Vector2i] = []
	for y in range(ARENA_Y0, ARENA_Y1 - 1, step):
		for x in range(ARENA_X0, ARENA_X1 - 1, step):
			var p := Vector2i(x, y)
			if _fld(p.x, p.y):
				cells.append(p)
	if cells.is_empty():
		return
	var pool := {}
	for c in cells:
		pool[c] = true
	var start := cells[0]
	var seen := {start: true}
	var stack: Array[Vector2i] = [start]
	_carve_rect(start.x, start.y, 3, 3)
	while not stack.is_empty():
		var cur: Vector2i = stack[stack.size() - 1]
		var nbrs := []
		for d: Vector2i in [Vector2i(step, 0), Vector2i(-step, 0),
				Vector2i(0, step), Vector2i(0, -step)]:
			var n := cur + d
			if pool.has(n) and not seen.has(n):
				nbrs.append(n)
		if nbrs.is_empty():
			stack.pop_back()
			continue
		var n2: Vector2i = _pick(nbrs)
		_carve_rect(n2.x, n2.y, 3, 3)
		_carve_line(cur.x + 1, cur.y + 1, n2.x + 1, n2.y + 1, 3)
		seen[n2] = true
		stack.append(n2)


func _carve_spirale() -> void:
	_fill_field(WALL)
	var width: int = _pick([2, 3])
	var step: int = width + _pick([2, 3])
	var x0 := ARENA_X0
	var y0 := ARENA_Y0
	var x1 := ARENA_X1
	var y1 := ARENA_Y1
	while x1 - x0 > step + width and y1 - y0 > step + width:
		_carve_line(x0, y0, x1, y0, width)
		_carve_line(x1, y0, x1, y1, width)
		_carve_line(x0, y1, x1, y1, width)
		# Die linke Seite bleibt oben offen - dort geht der Gang eine Windung
		# tiefer. Genau diese Luecke macht aus Ringen eine Spirale.
		_carve_line(x0, y0 + step, x0, y1, width)
		x0 += step
		y0 += step
		x1 -= step
		y1 -= step


# ===========================================================================
# 3.-5. Anbindung, Reparatur, Pruefung
# ===========================================================================
func _reachable() -> Dictionary:
	var start := Vector2i(gate.x, gate.y)
	var seen := {start: true}
	var stack: Array[Vector2i] = [start]
	while not stack.is_empty():
		var p: Vector2i = stack.pop_back()
		for n in [Vector2i(p.x - 1, p.y), Vector2i(p.x + 1, p.y),
				Vector2i(p.x, p.y - 1), Vector2i(p.x, p.y + 1)]:
			if seen.has(n) or not walkable(n.x, n.y):
				continue
			seen[n] = true
			stack.append(n)
	return seen


func _gate_link(max_links: int = 6) -> void:
	# Frueher lief hier eine feste Linie vom Tor nach Osten. Die war blind:
	# liegen alle Raeume weiter unten, trifft sie keinen einzigen, das Tor
	# haengt an einem Stichgang - und die Reparatur macht aus dem ganzen
	# Dungeon Fels. Gemessen waren das bis zu 770 von 920 Bodenzellen.
	#
	# Also andersherum: nachsehen, was vom Tor aus *nicht* erreichbar ist,
	# und zur groessten dieser Inseln einen Gang graben.
	var start := Vector2i(gate.x + 1, int((gate.y + gate.z) / 2.0))
	for _i in range(max_links):
		var reach := _reachable()
		var lose: Array[Vector2i] = []
		for p in _field_list:
			if at(p.x, p.y) == FLOOR and not reach.has(p):
				lose.append(p)
		if lose.is_empty():
			return
		var inseln := components(lose)
		var groesste: Array = inseln[0]
		for g in inseln:
			if g.size() > groesste.size():
				groesste = g
		# Krumen darf die Reparatur zumauern, dafuer ist sie da.
		if groesste.size() < 12:
			return
		var ziel: Vector2i = groesste[0]
		var best := 1 << 30
		for p in groesste:
			var d: int = (p.x - start.x) * (p.x - start.x) + (p.y - start.y) * (p.y - start.y)
			if d < best:
				best = d
				ziel = p
		_corridor(start, ziel, 2)


func _repair() -> int:
	var reach := _reachable()
	var lost := 0
	for y in MAP_H:
		for x in MAP_W:
			if at(x, y) == FLOOR and not reach.has(Vector2i(x, y)):
				_put(x, y, WALL)
				lost += 1
	return lost


func _make_spawns() -> Array[Vector2i]:
	# Bei den offenen Arten liegt der Rand frei und die Bevorzugung greift.
	# In einem Dungeon ist der Rand oft Mauer - dann zaehlt nur noch der
	# Abstand zum Tor, sonst gaebe es gar keine Spawnpunkte.
	var gx := gate.x
	var gcy := int((gate.y + gate.z) / 2.0)
	var far: Array[Vector2i] = []
	var border: Array[Vector2i] = []
	for y in range(ARENA_Y0, ARENA_Y1 + 1):
		for x in range(ARENA_X0, ARENA_X1 + 1):
			if at(x, y) != FLOOR:
				continue
			if maxi(absi(x - gx), absi(y - gcy)) < SPAWN_MIN_GATE:
				continue
			var p := Vector2i(x, y)
			far.append(p)
			if mini(mini(x - ARENA_X0, ARENA_X1 - x),
					mini(y - ARENA_Y0, ARENA_Y1 - y)) <= SPAWN_BORDER:
				border.append(p)

	var pool: Array = border if border.size() >= 12 else far
	pool = _shuffled(pool)
	var out: Array[Vector2i] = []
	for p in pool:
		if out.size() >= SPAWN_MAX:
			break
		var weit_genug := true
		for o in out:
			if maxi(absi(p.x - o.x), absi(p.y - o.y)) < SPAWN_SPREAD:
				weit_genug = false
				break
		if weit_genug:
			out.append(p)
	out.sort_custom(func(a, b): return a.y < b.y if a.y != b.y else a.x < b.x)
	return out


static func components(cells: Array) -> Array:
	# Einmal ueber die Eingabe laufen und Besuchtes ueberspringen. Frueher
	# stand hier `todo.keys()[0]`, was bei jedem Startpunkt das komplette
	# Schluesselarray kopiert - quadratisch, und bei ein paar hundert
	# Mauerzellen der Grund, warum eine Karte Sekunden brauchte.
	var todo := {}
	for c in cells:
		todo[c] = true
	var out := []
	for start in cells:
		if not todo.has(start):
			continue
		todo.erase(start)
		var group: Array[Vector2i] = [start]
		var stack: Array[Vector2i] = [start]
		while not stack.is_empty():
			var p: Vector2i = stack.pop_back()
			for n in [Vector2i(p.x - 1, p.y), Vector2i(p.x + 1, p.y),
					Vector2i(p.x, p.y - 1), Vector2i(p.x, p.y + 1)]:
				if todo.has(n):
					todo.erase(n)
					group.append(n)
					stack.append(n)
		out.append(group)
	return out


static func rects_from_cells(cells: Array) -> Array:
	# Ein L-Hindernis ist nicht seine Bounding-Box - die waere ein Viertel zu
	# gross und die Hitbox wuerde nicht zur Grafik passen. Gierig von oben
	# links: erst nach rechts, dann so weit nach unten, wie die volle Breite
	# noch traegt.
	# Einmal nach Zeile/Spalte sortieren und der Reihe nach abarbeiten.
	# Vorher wurde je Rechteck das Minimum linear gesucht - bei grossen
	# Mauerteilen (ein Labyrinth hat welche mit hunderten Zellen) war das
	# der zweite quadratische Posten.
	var remaining := {}
	for c in cells:
		remaining[c] = true
	var sorted_cells := cells.duplicate()
	sorted_cells.sort_custom(func(a, b):
		return a.y < b.y if a.y != b.y else a.x < b.x)
	var out: Array[Rect2i] = []
	for best in sorted_cells:
		if not remaining.has(best):
			continue
		var w := 1
		while remaining.has(Vector2i(best.x + w, best.y)):
			w += 1
		var h := 1
		while true:
			var voll := true
			for i in w:
				if not remaining.has(Vector2i(best.x + i, best.y + h)):
					voll = false
					break
			if not voll:
				break
			h += 1
		for yy in range(best.y, best.y + h):
			for xx in range(best.x, best.x + w):
				remaining.erase(Vector2i(xx, yy))
		out.append(Rect2i(best.x, best.y, w, h))
	return out


func _collect_blocks() -> Array:
	var cells: Array[Vector2i] = []
	for p in _field_list:
		if at(p.x, p.y) == WALL:
			cells.append(p)
	var groups := components(cells)
	groups.sort_custom(func(a, b):
		var ay := 1 << 30
		var by := 1 << 30
		for p in a:
			ay = mini(ay, p.y)
		for p in b:
			by = mini(by, p.y)
		return ay < by)
	return groups


func _dispatch(name: String) -> void:
	match name:
		"streu": _scatter("streu")
		"gespiegelt": _scatter("gespiegelt")
		"ringe": _scatter("ringe")
		"saeulen": _carve_saeulen()
		"sektoren": _carve_sektoren()
		"rotunde": _carve_rotunde()
		"diagonal": _carve_diagonal()
		"raeume": _carve_raeume()
		"zellen": _carve_zellen()
		"kammern": _carve_kammern()
		"stadt": _carve_stadt()
		"festung": _carve_festung()
		"katakomben": _carve_katakomben()
		"tempel": _carve_tempel()
		"hoehle": _carve_cave(rng.randf_range(0.44, 0.49), rng.randi_range(4, 5))
		"see": _carve_cave(rng.randf_range(0.36, 0.41), rng.randi_range(5, 6))
		"adern": _carve_adern()
		"inseln": _carve_inseln()
		"risse": _carve_risse()
		"krater": _carve_krater()
		"wurzeln": _carve_wurzeln()
		"labyrinth":
			_maze()
			_ring_corridor()
		"schleifen": _carve_schleifen()
		"hallen": _carve_hallen()
		"spirale": _carve_spirale()
		"kaefig": _carve_kaefig()


func _try_build(name: String) -> bool:
	_new_grid()
	_base()
	_build_field()
	var keep_cells := _build_masks()

	_dispatch(name)

	# Der Bereich vor dem Tor gehoert keiner Art.
	for p in keep_cells:
		_put(p.x, p.y, FLOOR)
	if MODES[name][4]:
		_gate_link()

	_repair()

	var open_cells := 0
	for p in _field_list:
		if at(p.x, p.y) == FLOOR:
			open_cells += 1
	open_ratio = float(open_cells) / float(_field_list.size())
	if open_ratio < MODES[name][2] or open_ratio > MODES[name][3]:
		return false

	blocks = _collect_blocks()
	if blocks.is_empty():
		return false

	spawns = _make_spawns()
	if spawns.size() < 6:
		return false
	return true


# ===========================================================================
# Kacheln - dieselbe Auswahl wie im Werkzeug
# ===========================================================================
func wall_tile_coords(x: int, y: int) -> Vector2i:
	# Der Tileset-Block bei Spalte 1..5 / Zeile 1..5 ist ein 3x3-Autotile:
	# der Ring liefert die Kanten, der Kern den Boden. Welche Kante es ist,
	# sagen die vier Nachbarn; bleibt keine uebrig, kommt die Innenecke ueber
	# die Diagonale, und erst dann das Fuellstueck.
	var col := 1 if walkable(x + 1, y) else (5 if walkable(x - 1, y) else 3)
	var row := 1 if walkable(x, y + 1) else (5 if walkable(x, y - 1) else 3)
	if col == 3 and row == 3:
		for e in [[-1, -1, 5, 5], [1, -1, 1, 5], [-1, 1, 5, 1], [1, 1, 1, 1]]:
			if walkable(x + e[0], y + e[1]):
				return Vector2i(e[2], e[3])
		return FILL_TILE
	return Vector2i(col, row)


func atlas_map(tile_seed: int = 99) -> Dictionary:
	var r := RandomNumberGenerator.new()
	r.seed = tile_seed
	var out := {}
	var varianten := [0, 0, 0, 1, 2]
	for y in MAP_H:
		for x in MAP_W:
			var cell := at(x, y)
			if cell == FLOOR or cell == GATE:
				# Zwei Ziehungen pro Bodenzelle, Mauern ziehen nicht.
				var c: int = 2 + varianten[r.randi_range(0, 4)]
				var rr: int = 2 + varianten[r.randi_range(0, 4)]
				out[Vector2i(x, y)] = Vector2i(c, rr)
			elif cell == WALL:
				out[Vector2i(x, y)] = wall_tile_coords(x, y)
	return out
