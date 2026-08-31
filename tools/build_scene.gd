# Laesst Godot die Szene schreiben, statt sie von Hand zu tippen.
#
# `tile_map_data` in einem .tscn ist ein Binaerblob; von Hand geschrieben
# waere er geraten, und ein Fehler darin faellt erst dem Entwickler auf.
# Also baut dieses Skript die Knoten mit der normalen API und laesst
# PackedScene + ResourceSaver das Dateiformat machen.
#
# Aufruf:
#   Godot_v4.7.1-stable_win64_console.exe --headless --path <projekt> \
#       --script res://build_scene.gd
extends SceneTree

const DATA := "res://arena/arena_data.json"
const TEX := "res://arena/ArenaTileset.png"
const TILESET_OUT := "res://arena/ArenaTileset.tres"
const SCENE_OUT := "res://arena/ArenaMap.tscn"


func _init() -> void:
	var file := FileAccess.open(DATA, FileAccess.READ)
	if file == null:
		push_error("arena_data.json nicht lesbar")
		quit(1)
		return
	var data: Dictionary = JSON.parse_string(file.get_as_text())
	file.close()

	var tile: int = int(data["tile"])
	var tile_v := Vector2i(tile, tile)

	# ---------------------------------------------------------- TileSet
	var texture: Texture2D = load(TEX)
	if texture == null:
		push_error("ArenaTileset.png nicht ladbar")
		quit(1)
		return

	var atlas := TileSetAtlasSource.new()
	atlas.texture = texture
	atlas.texture_region_size = tile_v

	# Nur die Kacheln anlegen, die die Karte wirklich benutzt. Ein Atlas
	# voller leerer Slots waere im Editor nur Rauschen.
	var seen := {}
	for cell in data["cells"]:
		var coord := Vector2i(int(cell["ax"]), int(cell["ay"]))
		if not seen.has(coord):
			seen[coord] = true
			atlas.create_tile(coord)

	var tileset := TileSet.new()
	tileset.tile_size = tile_v
	var source_id: int = tileset.add_source(atlas, 0)
	var err := ResourceSaver.save(tileset, TILESET_OUT)
	if err != OK:
		push_error("TileSet nicht speicherbar: %d" % err)
		quit(1)
		return

	# ------------------------------------------------------------ Szene
	var root := Node2D.new()
	root.name = "ArenaMap"

	var ground := TileMapLayer.new()
	ground.name = "Ground"
	ground.tile_set = load(TILESET_OUT)
	# Pixel Art: nicht filtern, egal was im Zielprojekt eingestellt ist.
	ground.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	for cell in data["cells"]:
		ground.set_cell(
			Vector2i(int(cell["x"]), int(cell["y"])),
			source_id,
			Vector2i(int(cell["ax"]), int(cell["ay"])),
			0)
	root.add_child(ground)
	ground.owner = root

	var hitboxes := Node2D.new()
	hitboxes.name = "Hitboxes"
	root.add_child(hitboxes)
	hitboxes.owner = root

	var groups: Array = data["walls"] + data["obstacles"]
	for group in groups:
		_add_body(root, hitboxes, group, tile)

	var packed := PackedScene.new()
	if packed.pack(root) != OK:
		push_error("Szene nicht packbar")
		quit(1)
		return
	err = ResourceSaver.save(packed, SCENE_OUT)
	if err != OK:
		push_error("Szene nicht speicherbar: %d" % err)
		quit(1)
		return

	print("OK  %d Kacheln  %d Atlas-Slots  %d Bodies"
		% [data["cells"].size(), seen.size(), groups.size()])
	root.free()
	quit(0)


func _add_body(root: Node, parent: Node, group: Dictionary, tile: int) -> void:
	# Ein Body je Hindernis. Der Body sitzt in der Mitte seiner
	# Bounding-Box, die Shapes liegen relativ dazu: dann verschiebt ein
	# Zug am Body im Editor das ganze Hindernis und nicht nur ein Stueck.
	var rects: Array = group["rects"]
	var min_x := INF
	var min_y := INF
	var max_x := -INF
	var max_y := -INF
	for r in rects:
		min_x = min(min_x, float(r["x"]))
		min_y = min(min_y, float(r["y"]))
		max_x = max(max_x, float(r["x"]) + float(r["w"]))
		max_y = max(max_y, float(r["y"]) + float(r["h"]))

	var body := StaticBody2D.new()
	body.name = String(group["name"])
	body.position = Vector2((min_x + max_x) * 0.5 * tile,
							(min_y + max_y) * 0.5 * tile)
	parent.add_child(body)
	body.owner = root

	var i := 1
	for r in rects:
		var shape := RectangleShape2D.new()
		shape.size = Vector2(float(r["w"]) * tile, float(r["h"]) * tile)
		var node := CollisionShape2D.new()
		node.name = "Shape" if rects.size() == 1 else "Shape%d" % i
		node.shape = shape
		node.position = Vector2(
			(float(r["x"]) + float(r["w"]) * 0.5) * tile,
			(float(r["y"]) + float(r["h"]) * 0.5) * tile) - body.position
		body.add_child(node)
		node.owner = root
		i += 1
