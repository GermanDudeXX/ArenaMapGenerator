# Baut die Karte zur Laufzeit: Kacheln und Hitboxen aus einem Seed.
#
# Einbau: diesen Knoten ins Level haengen, fertig. `_ready()` erzeugt eine
# Karte; `regenerate()` macht eine neue, ohne die Szene zu tauschen.
#
#     $ArenaMap.regenerate()                      # neuer Zufallsseed
#     $ArenaMap.regenerate(4242)                  # genau diese Karte
#     $ArenaMap.regenerate(0, "labyrinth")        # Art erzwingen
#
# Danach stehen `spawn_points`, `safezone_rect` und `gate_rect` in
# Weltkoordinaten bereit - das, was ein Wellensystem braucht.
@tool
class_name ArenaMap
extends Node2D

signal map_generated(info: Dictionary)

## 0 = bei jedem Start neu wuerfeln. Sonst ergibt dieselbe Zahl immer
## dieselbe Karte (innerhalb von Godot - siehe Hinweis in ArenaGenerator).
@export var map_seed: int = 0

## Leer = Art je Seed wuerfeln. Sonst einer der Namen aus
## ArenaGenerator.MODES:
##   Arena     streu gespiegelt ringe saeulen sektoren rotunde diagonal
##   Dungeon   raeume zellen kammern stadt festung katakomben tempel
##   Organisch hoehle see adern inseln risse krater wurzeln
##   Labyrinth labyrinth schleifen hallen spirale kaefig
@export var map_mode: String = ""

## Nur eine Art aus dieser Gruppe waehlen, wenn `map_mode` leer ist.
## Leer = alle Gruppen. "Arena", "Dungeon", "Organisch" oder "Labyrinth".
## Fuer ein Wellen-Survival ist "Arena" die naheliegende Wahl - dort ist
## die Karte offen genug zum Ausweichen.
@export var only_group: String = ""

@export var tile_set_resource: TileSet

## Kollisionsebene der erzeugten Hitboxen.
@export_flags_2d_physics var collision_layer: int = 1

## Im Editor sofort neu bauen (Haken setzen, er springt zurueck).
@export var regenerate_now: bool = false:
	set(value):
		if value:
			regenerate()

var spawn_points: Array[Vector2] = []
var safezone_rect := Rect2()
var gate_rect := Rect2()
var last_info: Dictionary = {}

var _ground: TileMapLayer
var _hitboxes: Node2D


func _ready() -> void:
	if _ground == null:
		regenerate()


func regenerate(new_seed: int = -1, new_mode: String = "@") -> Dictionary:
	if new_seed >= 0:
		map_seed = new_seed
	if new_mode != "@":
		map_mode = new_mode

	var mode := map_mode
	if mode == "" and only_group != "":
		# Gruppe vorgeben, Art daraus wuerfeln - deterministisch am Seed,
		# damit derselbe Seed auch dieselbe Art trifft.
		var kandidaten := ArenaGenerator.modes_in_group(only_group)
		if not kandidaten.is_empty():
			var r := RandomNumberGenerator.new()
			if map_seed == 0:
				r.randomize()
			else:
				r.seed = map_seed
			mode = kandidaten[r.randi_range(0, kandidaten.size() - 1)]

	var gen := ArenaGenerator.generate(map_seed, mode)
	_build(gen)
	last_info = gen.info()
	map_generated.emit(last_info)
	return last_info


# ---------------------------------------------------------------- Aufbau
func _build(gen: ArenaGenerator) -> void:
	_reset()

	var tile: int = ArenaGenerator.TILE

	_ground = TileMapLayer.new()
	_ground.name = "Ground"
	_ground.tile_set = tile_set_resource
	# Pixel Art: nicht filtern, egal was im Zielprojekt eingestellt ist.
	_ground.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	add_child(_ground)
	if Engine.is_editor_hint() and owner != null:
		_ground.owner = owner

	if tile_set_resource != null and tile_set_resource.get_source_count() > 0:
		var source_id := tile_set_resource.get_source_id(0)
		var atlas := gen.atlas_map()
		for pos in atlas:
			_ground.set_cell(pos, source_id, atlas[pos], 0)
	else:
		push_warning("ArenaMap: kein TileSet gesetzt - es entstehen nur Hitboxen.")

	_hitboxes = Node2D.new()
	_hitboxes.name = "Hitboxes"
	add_child(_hitboxes)
	if Engine.is_editor_hint() and owner != null:
		_hitboxes.owner = owner

	_add_walls(gen, tile)
	for i in gen.blocks.size():
		_add_body("Block_%02d" % (i + 1),
				ArenaGenerator.rects_from_cells(gen.blocks[i]), tile)

	# Was das Spiel braucht, in Weltkoordinaten.
	spawn_points.clear()
	for p in gen.spawns:
		spawn_points.append(Vector2((p.x + 0.5) * tile, (p.y + 0.5) * tile))
	var s := gen.safe
	safezone_rect = Rect2(s.x * tile, s.y * tile,
			(s.z - s.x + 1) * tile, (s.w - s.y + 1) * tile)
	var g := gen.gate
	gate_rect = Rect2(g.x * tile, g.y * tile, tile, (g.z - g.y + 1) * tile)


func _reset() -> void:
	for child in get_children():
		remove_child(child)
		child.queue_free()
	_ground = null
	_hitboxes = null


func _add_walls(gen: ArenaGenerator, tile: int) -> void:
	# Aussenmauer und Safezone-Waende aus den Massen gerechnet, nicht aus
	# dem Gitter gelesen: so bekommt der Entwickler sinnvoll benannte
	# Bodies statt einem Dutzend namenloser Bruchstuecke. Die Ecken
	# gehoeren jeweils genau einer Wand - zwei Bodies uebereinander waeren
	# nicht falsch, aber wer einen wegschiebt, uebersieht den anderen.
	var x0: int = ArenaGenerator.ARENA_X0
	var y0: int = ArenaGenerator.ARENA_Y0
	var x1: int = ArenaGenerator.ARENA_X1
	var y1: int = ArenaGenerator.ARENA_Y1
	var aw := x1 - x0 + 3
	var ah := y1 - y0 + 3
	var sy1: int = gen.safe.w
	var gx: int = gen.gate.x
	var gy0: int = gen.gate.y
	var gy1: int = gen.gate.z

	var teile := [
		["Mauer_Nord", Rect2i(x0 - 1, y0 - 1, aw, 1)],
		["Mauer_Sued", Rect2i(x0 - 1, y1 + 1, aw, 1)],
		["Mauer_West", Rect2i(x0 - 1, y0, 1, ah - 2)],
		["Mauer_Ost", Rect2i(x1 + 1, y0, 1, ah - 2)],
		["Safezone_Wand_Sued", Rect2i(x0, sy1 + 1, gx - x0 + 1, 1)],
		["Safezone_Wand_Ost_Oben", Rect2i(gx, y0, 1, gy0 - y0)],
		["Safezone_Wand_Ost_Unten", Rect2i(gx, gy1 + 1, 1, sy1 - gy1)],
	]
	for teil in teile:
		var r: Rect2i = teil[1]
		if r.size.x > 0 and r.size.y > 0:
			_add_body(teil[0], [r], tile)


func _add_body(body_name: String, rects: Array, tile: int) -> void:
	if rects.is_empty():
		return
	# Der Body sitzt in der Mitte seiner Bounding-Box, die Shapes liegen
	# relativ dazu: dann verschiebt ein Zug am Body das ganze Hindernis
	# und nicht nur ein Stueck.
	var min_x := 1 << 30
	var min_y := 1 << 30
	var max_x := -(1 << 30)
	var max_y := -(1 << 30)
	for r in rects:
		min_x = mini(min_x, r.position.x)
		min_y = mini(min_y, r.position.y)
		max_x = maxi(max_x, r.position.x + r.size.x)
		max_y = maxi(max_y, r.position.y + r.size.y)

	var body := StaticBody2D.new()
	body.name = body_name
	body.collision_layer = collision_layer
	body.position = Vector2((min_x + max_x) * 0.5 * tile,
			(min_y + max_y) * 0.5 * tile)
	_hitboxes.add_child(body)
	if Engine.is_editor_hint() and owner != null:
		body.owner = owner

	var i := 1
	for r in rects:
		var shape := RectangleShape2D.new()
		shape.size = Vector2(r.size.x * tile, r.size.y * tile)
		var node := CollisionShape2D.new()
		node.name = "Shape" if rects.size() == 1 else "Shape%d" % i
		node.shape = shape
		node.position = Vector2((r.position.x + r.size.x * 0.5) * tile,
				(r.position.y + r.size.y * 0.5) * tile) - body.position
		body.add_child(node)
		if Engine.is_editor_hint() and owner != null:
			node.owner = owner
		i += 1
