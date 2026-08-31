# Prueft die gebaute Szene gegen die Daten, aus denen sie entstanden ist.
#
# Der Sinn: die Kette pygame-Bild -> atlas_map -> arena_data.json ist in
# Python schon geprueft. Hier wird das letzte Glied geschlossen - dass in
# der .tscn wirklich dieselben Kacheln und dieselben Kollisionsflaechen
# stehen. Erst dann ist "sieht aus wie die Vorschau" eine Aussage und
# keine Hoffnung.
extends SceneTree

const DATA := "res://arena/arena_data.json"
const SCENE := "res://arena/ArenaMap.tscn"


func _init() -> void:
	var file := FileAccess.open(DATA, FileAccess.READ)
	var data: Dictionary = JSON.parse_string(file.get_as_text())
	file.close()

	var packed: PackedScene = load(SCENE)
	if packed == null:
		push_error("ArenaMap.tscn nicht ladbar")
		quit(1)
		return
	var root: Node = packed.instantiate()
	var problems: Array[String] = []

	var tile: int = int(data["tile"])

	# ------------------------------------------------------- Kacheln
	var ground: TileMapLayer = root.get_node_or_null("Ground")
	if ground == null:
		problems.append("Knoten Ground fehlt")
	else:
		var want := {}
		for cell in data["cells"]:
			want[Vector2i(int(cell["x"]), int(cell["y"]))] = \
				Vector2i(int(cell["ax"]), int(cell["ay"]))
		var used := ground.get_used_cells()
		if used.size() != want.size():
			problems.append("Kachelzahl: %d in der Szene, %d erwartet"
				% [used.size(), want.size()])
		var wrong := 0
		for pos in used:
			if not want.has(pos):
				wrong += 1
			elif ground.get_cell_atlas_coords(pos) != want[pos]:
				wrong += 1
		if wrong > 0:
			problems.append("%d Kacheln stimmen nicht" % wrong)
		if ground.tile_set == null:
			problems.append("Ground hat kein TileSet")

	# ------------------------------------------------------ Hitboxen
	var hitboxes: Node = root.get_node_or_null("Hitboxes")
	if hitboxes == null:
		problems.append("Knoten Hitboxes fehlt")
	else:
		var groups: Array = data["walls"] + data["obstacles"]
		if hitboxes.get_child_count() != groups.size():
			problems.append("Bodies: %d in der Szene, %d erwartet"
				% [hitboxes.get_child_count(), groups.size()])

		# Jede Kollisionsflaeche auf Tilezellen zurueckrechnen und mit den
		# Mauerzellen der Karte vergleichen. Das faengt einen falschen
		# Mittelpunkt oder eine halbe Kachel Versatz, was im Bild noch
		# unsichtbar waere, im Spiel aber eine unsichtbare Wand ergibt.
		var covered := {}
		var shapes := 0
		for body in hitboxes.get_children():
			if not (body is StaticBody2D):
				problems.append("%s ist kein StaticBody2D" % body.name)
				continue
			for child in body.get_children():
				if not (child is CollisionShape2D):
					continue
				shapes += 1
				var rect: RectangleShape2D = child.shape
				if rect == null:
					problems.append("%s/%s ohne Shape" % [body.name, child.name])
					continue
				var centre: Vector2 = body.position + child.position
				var top_left: Vector2 = centre - rect.size * 0.5
				var cw := int(round(rect.size.x / tile))
				var ch := int(round(rect.size.y / tile))
				var cx := int(round(top_left.x / tile))
				var cy := int(round(top_left.y / tile))
				if absf(top_left.x - cx * tile) > 0.01 \
						or absf(top_left.y - cy * tile) > 0.01:
					problems.append("%s liegt nicht auf dem Raster" % body.name)
				for yy in range(cy, cy + ch):
					for xx in range(cx, cx + cw):
						var key := Vector2i(xx, yy)
						covered[key] = int(covered.get(key, 0)) + 1

		# Mauerzellen aus den Hitbox-Daten selbst ableiten waere zirkulaer;
		# stattdessen aus dem Kachelbild: alles, was keine Bodenkachel ist.
		var want_walls := {}
		var floor_coords := {}
		for c in range(2, 5):
			for r in range(2, 5):
				floor_coords[Vector2i(c, r)] = true
		for cell in data["cells"]:
			var coord := Vector2i(int(cell["ax"]), int(cell["ay"]))
			if not floor_coords.has(coord):
				want_walls[Vector2i(int(cell["x"]), int(cell["y"]))] = true

		var missing := 0
		for key in want_walls:
			if not covered.has(key):
				missing += 1
		var extra := 0
		var doubled := 0
		for key in covered:
			if not want_walls.has(key):
				extra += 1
			if int(covered[key]) > 1:
				doubled += 1
		if missing > 0:
			problems.append("%d Mauerzellen ohne Hitbox" % missing)
		if extra > 0:
			problems.append("%d Hitbox-Zellen ueber Boden" % extra)
		if doubled > 0:
			problems.append("%d Zellen doppelt belegt" % doubled)

		print("Bodies %d, Shapes %d, gedeckte Zellen %d"
			% [hitboxes.get_child_count(), shapes, covered.size()])

	root.free()

	if problems.is_empty():
		print("PRUEFUNG OK")
		quit(0)
	else:
		for p in problems:
			printerr("FEHLER: %s" % p)
		quit(1)
