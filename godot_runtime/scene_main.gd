# Prueft, dass _ready() den Aufbau ausloest - im echten Szenenbetrieb,
# nicht aus einem SceneTree-Skript heraus.
extends Node2D


func _ready() -> void:
	var f := FileAccess.open("res://ready_out.txt", FileAccess.WRITE)
	var map: ArenaMap = $ArenaMap
	f.store_line("nach _ready: Kinder=%d" % map.get_child_count())
	var ground: TileMapLayer = map.get_node_or_null("Ground")
	f.store_line("Ground: %s Kacheln" % [
		ground.get_used_cells().size() if ground else "fehlt"])
	f.store_line("Hitboxes: %d Bodies" % [
		map.get_node("Hitboxes").get_child_count() if map.has_node("Hitboxes") else -1])
	f.store_line("Info: %s" % [map.last_info])
	f.store_line("Spawns: %d" % map.spawn_points.size())

	# Und noch einmal neu - ohne die Szene zu tauschen.
	var vorher: int = map.last_info["seed"]
	map.regenerate()
	f.store_line("nach regenerate(): Seed %d -> %d, Art %s, Kacheln %d" % [
		vorher, map.last_info["seed"], map.last_info["mode"],
		map.get_node("Ground").get_used_cells().size()])
	f.close()
	get_tree().quit(0)
