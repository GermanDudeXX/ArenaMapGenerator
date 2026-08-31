# Prueft den Laufzeitgenerator - dieselben Fragen wie auf der Python-Seite.
#
# Fuer jede Art ueber viele Seeds: kommt eine Karte heraus, ist jede
# Bodenzelle vom Tor erreichbar, bleibt die Safezone unverbaut, ist das Tor
# offen, decken die Bloecke genau die Feldmauern, gibt es Spawnpunkte -
# und wie lange dauert es.
#
#   Godot --headless --path <projekt> --script res://test_generator.gd
extends SceneTree

const SEEDS := 20

var f: FileAccess


func say(t: String) -> void:
	f.store_line(t)
	f.flush()


func _init() -> void:
	f = FileAccess.open("res://test_out.txt", FileAccess.WRITE)
	var namen: Array = ArenaGenerator.mode_names()
	var fehler: Array[String] = []
	var gesamt := 0
	var notnagel := 0
	var t_all := Time.get_ticks_msec()

	say("%-11s %-10s %5s %6s %-13s %6s %7s"
		% ["ART", "GRUPPE", "OK", "NOT", "OFFEN", "BLK", "ZEIT"])

	for name in namen:
		var t0 := Time.get_ticks_msec()
		var ok := 0
		var nots := 0
		var lo := 2.0
		var hi := -1.0
		var summe := 0.0
		var blk := 0
		for s in range(1, SEEDS + 1):
			gesamt += 1
			var g := ArenaGenerator.generate(s, name)
			if g.blocks.is_empty():
				nots += 1
				notnagel += 1
				continue
			ok += 1
			lo = minf(lo, g.open_ratio)
			hi = maxf(hi, g.open_ratio)
			summe += g.open_ratio
			blk += g.blocks.size()
			_check(g, name, s, fehler)
		var dt := Time.get_ticks_msec() - t0
		say("%-11s %-10s %5d %6d %.2f (%.2f-%.2f) %6.1f %5dms"
			% [name, ArenaGenerator.MODES[name][0], ok, nots,
				summe / maxf(1.0, float(ok)), lo, hi,
				float(blk) / maxf(1.0, float(ok)), dt / SEEDS])

	# Determinismus: derselbe Seed muss dasselbe Gitter ergeben.
	for name in namen:
		var a := ArenaGenerator.generate(777, name)
		var b := ArenaGenerator.generate(777, name)
		if a.grid != b.grid:
			fehler.append("%s: nicht deterministisch" % name)

	# Zufaellig heisst auch: nicht immer dasselbe.
	var gesehen := {}
	for i in 20:
		var g := ArenaGenerator.generate(0, "")
		gesehen[str(g.seed_used) + "/" + g.mode] = true
	if gesehen.size() < 15:
		fehler.append("Zufall wiederholt sich: nur %d verschiedene aus 20"
			% gesehen.size())

	say("")
	say("%d Karten in %.1fs, %d Notnagel, %d verschiedene aus 20 Zufallsziehungen"
		% [gesamt, (Time.get_ticks_msec() - t_all) / 1000.0, notnagel,
			gesehen.size()])
	if fehler.is_empty():
		say("PRUEFUNG OK")
		f.close()
		quit(0)
	else:
		for msg in fehler:
			say("FEHLER: " + msg)
		f.close()
		quit(1)


func _check(g: ArenaGenerator, name: String, s: int, fehler: Array[String]) -> void:
	var tag := "%s/%d" % [name, s]

	# Alles begehbare muss vom Tor aus erreichbar sein.
	var boden := 0
	for y in ArenaGenerator.MAP_H:
		for x in ArenaGenerator.MAP_W:
			var c := g.at(x, y)
			if c == ArenaGenerator.FLOOR or c == ArenaGenerator.GATE:
				boden += 1
	if g._reachable().size() != boden:
		fehler.append(tag + ": nicht alles vom Tor erreichbar")

	# Safezone unverbaut, Tor offen.
	for y in range(g.safe.y, g.safe.w + 1):
		for x in range(g.safe.x, g.safe.z + 1):
			if g.at(x, y) != ArenaGenerator.FLOOR:
				fehler.append(tag + ": Safezone verbaut")
				return
	for y in range(g.gate.y, g.gate.z + 1):
		if g.at(g.gate.x, y) != ArenaGenerator.GATE:
			fehler.append(tag + ": Tor verbaut")
			return

	# Bloecke muessen genau die Mauern im Feld sein.
	var aus_bloecken := {}
	for group in g.blocks:
		for p in group:
			aus_bloecken[p] = true
	var im_feld := {}
	for p in g._field_list:
		if g.at(p.x, p.y) == ArenaGenerator.WALL:
			im_feld[p] = true
	if aus_bloecken.size() != im_feld.size():
		fehler.append(tag + ": Bloecke decken die Mauern nicht")
		return
	for p in im_feld:
		if not aus_bloecken.has(p):
			fehler.append(tag + ": Bloecke decken die Mauern nicht")
			return

	# Rechteckzerlegung: Flaeche gleich, keine Ueberlappung.
	for group in g.blocks:
		var abgedeckt := {}
		for r in ArenaGenerator.rects_from_cells(group):
			for yy in range(r.position.y, r.position.y + r.size.y):
				for xx in range(r.position.x, r.position.x + r.size.x):
					var p := Vector2i(xx, yy)
					if abgedeckt.has(p):
						fehler.append(tag + ": Rechtecke ueberlappen")
						return
					abgedeckt[p] = true
		if abgedeckt.size() != group.size():
			fehler.append(tag + ": Rechtecke decken den Block nicht")
			return

	if g.spawns.size() < 6:
		fehler.append(tag + ": zu wenige Spawnpunkte (%d)" % g.spawns.size())
