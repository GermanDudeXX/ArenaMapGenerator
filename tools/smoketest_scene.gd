# Simuliert den Entwickler: Szene instanzieren wie in einem Level und
# nachsehen, ob wirklich alles da ist. Laeuft in einem *frischen* Projekt,
# in das nur der Ordner arena/ kopiert wurde - damit auch die Pfade und
# der Atlas-Import mitgeprueft sind und nicht nur die Datei.
extends SceneTree


func _init() -> void:
	var packed: PackedScene = load("res://arena/ArenaMap.tscn")
	if packed == null:
		printerr("FEHLER: ArenaMap.tscn laedt nicht")
		quit(1)
		return

	var map: Node = packed.instantiate()
	var level := Node2D.new()
	level.name = "Level"
	level.add_child(map)

	var ground: TileMapLayer = map.get_node("Ground")
	var hitboxes: Node = map.get_node("Hitboxes")

	var problems: Array[String] = []
	if ground.tile_set == null:
		problems.append("TileSet fehlt")
	elif ground.tile_set.get_source_count() == 0:
		problems.append("TileSet hat keine Quelle")
	else:
		var src := ground.tile_set.get_source(ground.tile_set.get_source_id(0))
		if src is TileSetAtlasSource and src.texture == null:
			problems.append("Atlas-Textur fehlt - PNG nicht importiert?")

	if ground.get_used_cells().is_empty():
		problems.append("keine Kacheln")
	if ground.texture_filter != CanvasItem.TEXTURE_FILTER_NEAREST:
		problems.append("Texturfilter nicht auf NEAREST")

	var bodies := 0
	var shapes := 0
	for child in hitboxes.get_children():
		if child is StaticBody2D:
			bodies += 1
			for sub in child.get_children():
				if sub is CollisionShape2D and sub.shape != null:
					shapes += 1
	if bodies == 0:
		problems.append("keine Hitboxen")

	var rect := ground.get_used_rect()
	print("Szene geladen: %d Kacheln, Bereich %s, %d Bodies, %d Shapes"
		% [ground.get_used_cells().size(), rect, bodies, shapes])
	print("Erster Body: %s bei %s"
		% [hitboxes.get_child(0).name, hitboxes.get_child(0).position])

	level.free()

	if problems.is_empty():
		print("SMOKETEST OK")
		quit(0)
	else:
		for p in problems:
			printerr("FEHLER: %s" % p)
		quit(1)
