# Prueft den Knoten, nicht nur die Rechnung dahinter.
#
# Der Generator kann stimmen und der Aufbau trotzdem falsch sein: eine
# Kollisionsflaeche um eine halbe Kachel versetzt sieht im Bild richtig aus
# und ergibt im Spiel eine unsichtbare Wand. Also die gebauten Knoten
# zurueckrechnen und mit dem Gitter vergleichen, aus dem sie entstanden sind.
extends SceneTree

var f: FileAccess


func say(t: String) -> void:
	f.store_line(t)
	f.flush()


func _init() -> void:
	f = FileAccess.open("res://node_out.txt", FileAccess.WRITE)
	var tileset: TileSet = load("res://arena/ArenaTileset.tres")
	var fehler: Array[String] = []

	for probe in [[4242, "streu"], [7, "raeume"], [11, "labyrinth"],
			[3, "hoehle"], [99, "stadt"]]:
		_pruefe(int(probe[0]), String(probe[1]), tileset, fehler)

	# Gleicher Seed, gleiche Karte - auch ueber den Knoten.
	var a := _baue(555, "raeume", tileset)
	var b := _baue(555, "raeume", tileset)
	var ground_a: TileMapLayer = a.get_node("Ground")
	var ground_b: TileMapLayer = b.get_node("Ground")
	if ground_a.get_used_cells() != ground_b.get_used_cells():
		fehler.append("gleicher Seed ergibt verschiedene Karten")
	say("Determinismus ueber den Knoten: %d Kacheln beide Male"
		% ground_a.get_used_cells().size())
	a.free()
	b.free()

	# Seed 0 heisst: jedes Mal eine andere.
	var gesehen := {}
	for i in 8:
		var m := _baue(0, "", tileset)
		gesehen[str(m.last_info["seed"]) + "/" + str(m.last_info["mode"])] = true
		m.free()
	say("Zufall: %d verschiedene aus 8 Ziehungen" % gesehen.size())
	if gesehen.size() < 7:
		fehler.append("Seed 0 wiederholt sich zu oft")

	say("")
	if fehler.is_empty():
		say("KNOTENPRUEFUNG OK")
		f.close()
		quit(0)
	else:
		for m in fehler:
			say("FEHLER: " + m)
		f.close()
		quit(1)


func _baue(map_seed: int, mode: String, tileset: TileSet) -> ArenaMap:
	var node := ArenaMap.new()
	node.tile_set_resource = tileset
	node.map_seed = map_seed
	node.map_mode = mode
	root.add_child(node)
	# Waehrend SceneTree._init() ist der Baum noch nicht so weit, dass
	# _ready() feuert - im Spiel tut es das. Fuer den Test also direkt
	# aufrufen; dass _ready() den Aufbau ausloest, prueft scene_main.gd.
	node.regenerate()
	root.remove_child(node)
	return node


func _pruefe(map_seed: int, mode: String, tileset: TileSet,
		fehler: Array[String]) -> void:
	var tag := "%s/%d" % [mode, map_seed]
	var node := _baue(map_seed, mode, tileset)
	var tile: int = ArenaGenerator.TILE

	# Dieselbe Karte noch einmal rechnen und die Knoten dagegen halten.
	var gen := ArenaGenerator.generate(map_seed, mode)
	var soll := gen.atlas_map()

	var ground: TileMapLayer = node.get_node_or_null("Ground")
	if ground == null:
		fehler.append(tag + ": kein Ground")
		node.free()
		return
	var used := ground.get_used_cells()
	if used.size() != soll.size():
		fehler.append("%s: %d Kacheln statt %d" % [tag, used.size(), soll.size()])
	var falsch := 0
	for pos in used:
		if not soll.has(pos) or ground.get_cell_atlas_coords(pos) != soll[pos]:
			falsch += 1
	if falsch > 0:
		fehler.append("%s: %d Kacheln stimmen nicht" % [tag, falsch])
	if ground.texture_filter != CanvasItem.TEXTURE_FILTER_NEAREST:
		fehler.append(tag + ": Texturfilter nicht NEAREST")

	# Hitboxen auf Kacheln zurueckrechnen.
	var hitboxes: Node = node.get_node_or_null("Hitboxes")
	if hitboxes == null:
		fehler.append(tag + ": keine Hitboxes")
		node.free()
		return
	var gedeckt := {}
	var shapes := 0
	var doppelt := 0
	for body in hitboxes.get_children():
		for child in body.get_children():
			if not (child is CollisionShape2D):
				continue
			shapes += 1
			var rect: RectangleShape2D = child.shape
			var centre: Vector2 = body.position + child.position
			var top_left: Vector2 = centre - rect.size * 0.5
			var cx := int(round(top_left.x / tile))
			var cy := int(round(top_left.y / tile))
			if absf(top_left.x - cx * tile) > 0.01 \
					or absf(top_left.y - cy * tile) > 0.01:
				fehler.append("%s: %s nicht auf dem Raster" % [tag, body.name])
			for yy in range(cy, cy + int(round(rect.size.y / tile))):
				for xx in range(cx, cx + int(round(rect.size.x / tile))):
					var p := Vector2i(xx, yy)
					if gedeckt.has(p):
						doppelt += 1
					gedeckt[p] = true

	# Soll: alle Mauerzellen der Karte.
	var mauern := {}
	for y in ArenaGenerator.MAP_H:
		for x in ArenaGenerator.MAP_W:
			if gen.at(x, y) == ArenaGenerator.WALL:
				mauern[Vector2i(x, y)] = true
	var fehlend := 0
	for p in mauern:
		if not gedeckt.has(p):
			fehlend += 1
	var ueber := 0
	for p in gedeckt:
		if not mauern.has(p):
			ueber += 1
	if fehlend > 0:
		fehler.append("%s: %d Mauerzellen ohne Hitbox" % [tag, fehlend])
	if ueber > 0:
		fehler.append("%s: %d Hitbox-Zellen ueber Boden" % [tag, ueber])
	if doppelt > 0:
		fehler.append("%s: %d Zellen doppelt belegt" % [tag, doppelt])

	# Spawnpunkte muessen auf Boden liegen.
	var schlecht := 0
	for w in node.spawn_points:
		var tx := int(w.x / tile)
		var ty := int(w.y / tile)
		if gen.at(tx, ty) != ArenaGenerator.FLOOR:
			schlecht += 1
	if schlecht > 0:
		fehler.append("%s: %d Spawnpunkte nicht auf Boden" % [tag, schlecht])

	say("%-16s %4d Kacheln  %2d Bodies  %3d Shapes  %4d Mauerzellen  %2d Spawns"
		% [tag, used.size(), hitboxes.get_child_count(), shapes,
			mauern.size(), node.spawn_points.size()])
	node.free()
