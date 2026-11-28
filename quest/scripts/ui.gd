class_name GameUI
extends Node3D
## In-world UI: scoreboard sign + punchable console, wrist display and toasts.

const FACE_Z := 0.07
const BTN_D := 0.07
const INK := Color("#2a1640")


class Canvas extends Control:
	var painter: Callable

	func _draw() -> void:
		if painter.is_valid():
			painter.call(self)


var game: Game
var player: VRPlayer
var sfx: Sfx
var font_bold: FontVariation
var font_semi: FontVariation
var font_reg: FontVariation

var board_vp: SubViewport
var board_canvas: Canvas
var wrist_vp: SubViewport
var wrist_canvas: Canvas
var wrist_quad: MeshInstance3D
var toast_vp: SubViewport
var toast_canvas: Canvas
var toast_quad: MeshInstance3D
var toast_mat: StandardMaterial3D
var toast_text := ""
var toast_color := Color.WHITE
var toast_big := false
var toast_life := 0.0
var toast_dur := 1.0
var toast_init := false

var panel: Node3D
var buttons: Array = []
var dirty := true
var labels_dirty := true
var board_at := 0.0
var board_tick := 0.0
var wrist_at := 0.0
var clock := 0.0


static func m4(e: Array) -> Transform3D:
	# three.js column-major matrix elements -> Transform3D
	return Transform3D(Basis(Vector3(e[0], e[1], e[2]), Vector3(e[4], e[5], e[6]), Vector3(e[8], e[9], e[10])), Vector3(e[12], e[13], e[14]))


func setup(data: Dictionary, p_game: Game, p_player: VRPlayer, p_sfx: Sfx, fonts: Dictionary) -> void:
	game = p_game
	player = p_player
	sfx = p_sfx
	font_bold = fonts["bold"]
	font_semi = fonts["semibold"]
	font_reg = fonts["regular"]
	game.on_change = _on_game_change
	game.on_toast = toast

	# scoreboard
	board_vp = _viewport(Vector2i(1024, 560), false)
	board_canvas = _canvas(board_vp, _paint_board)
	var board := MeshInstance3D.new()
	var bq := QuadMesh.new()
	bq.size = Vector2(2.6, 1.42)
	board.mesh = bq
	var bm := Level.unshaded(Color.WHITE)
	bm.albedo_texture = board_vp.get_texture()
	board.material_override = bm
	add_child(board)
	board.transform = m4(data["boardMatrix"])

	# console buttons
	panel = Node3D.new()
	add_child(panel)
	panel.transform = m4(data["panelMatrix"])
	for d in data["buttons"]:
		var b := {"id": d["id"], "x": float(d["x"]), "y": float(d["y"]), "w": float(d["w"]), "h": float(d["h"]), "z": float(d["z"]),
			"color": Color(d["color"]), "cool": 0.0, "down_until": 0.0, "inside": [false, false]}
		var mesh := MeshInstance3D.new()
		var bx := BoxMesh.new()
		bx.size = Vector3(b["w"], b["h"], BTN_D)
		mesh.mesh = bx
		var mat := Level.lambert(b["color"])
		mat.emission_enabled = true
		mat.emission = b["color"] * 0.35
		mesh.material_override = mat
		mesh.position = Vector3(b["x"], b["y"], b["z"])
		panel.add_child(mesh)
		var label := Label3D.new()
		label.font = font_bold
		label.font_size = 64
		label.modulate = INK
		label.outline_size = 0
		label.position = Vector3(0, 0, BTN_D / 2.0 + 0.003)
		mesh.add_child(label)
		b["mesh"] = mesh
		b["mat"] = mat
		b["label"] = label
		if b["id"] == "prev" or b["id"] == "next":
			var arrow := MeshInstance3D.new()
			var pm := PrismMesh.new()
			pm.size = Vector3(0.07, 0.06, 0.012)
			arrow.mesh = pm
			arrow.material_override = Level.unshaded(INK)
			var dir := -1.0 if b["id"] == "prev" else 1.0
			arrow.rotation.z = -dir * PI / 2.0
			arrow.position = Vector3(dir * (b["w"] * 0.5 - 0.075), 0, BTN_D / 2.0 + 0.006)
			mesh.add_child(arrow)
			label.position.x = -dir * 0.035
		if b["id"] == "color":
			var sw := MeshInstance3D.new()
			var cm := CylinderMesh.new()
			cm.top_radius = 0.045
			cm.bottom_radius = 0.045
			cm.height = 0.012
			cm.radial_segments = 20
			sw.mesh = cm
			sw.rotation.x = PI / 2.0
			sw.position = Vector3(b["w"] * 0.5 - 0.08, 0, BTN_D / 2.0 + 0.006)
			b["swatch_mat"] = Level.unshaded(player.color)
			sw.material_override = b["swatch_mat"]
			mesh.add_child(sw)
			label.position.x = -0.04
		buttons.append(b)

	# wrist display (left hand). WebXR/OpenXR grip: the back of the left hand
	# faces -X and +Y runs up the arm, so the face sits on -X reading toward the fingers.
	wrist_vp = _viewport(Vector2i(256, 160), true)
	wrist_canvas = _canvas(wrist_vp, _paint_wrist)
	wrist_quad = MeshInstance3D.new()
	var wq := QuadMesh.new()
	wq.size = Vector2(0.11, 0.069)
	wrist_quad.mesh = wq
	var wm := Level.unshaded(Color.WHITE)
	wm.albedo_texture = wrist_vp.get_texture()
	wm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	wm.cull_mode = BaseMaterial3D.CULL_DISABLED
	wrist_quad.material_override = wm
	wrist_quad.transform = Transform3D(Basis(Vector3(0, -1, 0), Vector3(0, 0, 1), Vector3(-1, 0, 0)), Vector3(-0.062, 0.07, 0.0))
	player.hands[0].node.add_child(wrist_quad)

	# toast
	toast_vp = _viewport(Vector2i(1024, 256), true)
	toast_canvas = _canvas(toast_vp, _paint_toast)
	toast_quad = MeshInstance3D.new()
	var tq := QuadMesh.new()
	tq.size = Vector2(1.0, 0.25)
	toast_quad.mesh = tq
	toast_mat = Level.unshaded(Color(1, 1, 1, 0))
	toast_mat.albedo_texture = toast_vp.get_texture()
	toast_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	toast_mat.no_depth_test = true
	toast_mat.render_priority = 100
	toast_quad.material_override = toast_mat
	toast_quad.visible = false
	add_child(toast_quad)
	_draw_labels()


func _on_game_change() -> void:
	dirty = true
	labels_dirty = true


func _viewport(size: Vector2i, transparent: bool) -> SubViewport:
	var vp := SubViewport.new()
	vp.size = size
	vp.transparent_bg = transparent
	vp.disable_3d = true
	vp.render_target_update_mode = SubViewport.UPDATE_ONCE
	add_child(vp)
	return vp


func _canvas(vp: SubViewport, painter: Callable) -> Canvas:
	var c := Canvas.new()
	c.painter = painter
	c.size = Vector2(vp.size)
	vp.add_child(c)
	return c


func _redraw(vp: SubViewport, c: Canvas) -> void:
	c.queue_redraw()
	vp.render_target_update_mode = SubViewport.UPDATE_ONCE


static func rr(c: Control, rect: Rect2, radius: float, color: Color, border := 0.0, border_color := Color.TRANSPARENT) -> void:
	var sb := StyleBoxFlat.new()
	sb.bg_color = color
	sb.set_corner_radius_all(int(radius))
	sb.anti_aliasing = true
	if border > 0.0:
		sb.set_border_width_all(int(border))
		sb.border_color = border_color
	c.draw_style_box(sb, rect)


static func tri(c: Control, center: Vector2, s: float, dir: float, color: Color) -> void:
	c.draw_colored_polygon(PackedVector2Array([center + Vector2(dir * s, 0), center + Vector2(-dir * s * 0.7, -s), center + Vector2(-dir * s * 0.7, s)]), color)


# --------------------------------------------------------------- toast
func toast(text: String, color := Color("#fff7ec"), big := false) -> void:
	toast_text = text
	toast_color = color
	toast_big = big
	toast_life = 2.2 if big else 1.5
	toast_dur = toast_life
	toast_quad.visible = true
	_redraw(toast_vp, toast_canvas)


func _paint_toast(c: Control) -> void:
	var size := 118 if toast_big else 80
	var w := font_bold.get_string_size(toast_text, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
	if w > 900.0:
		size = int(size * 900.0 / w)
		w = font_bold.get_string_size(toast_text, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
	var bw := w + 90.0
	var bh := size * 1.45
	var rect := Rect2((1024.0 - bw) / 2.0, (256.0 - bh) / 2.0, bw, bh)
	var edge := toast_color
	edge.a = 0.6
	rr(c, rect, bh / 2.0, Color(0.11, 0.063, 0.2, 0.8), 6, edge)
	var base := 128.0 + size * 0.36
	c.draw_string_outline(font_bold, Vector2(0, base), toast_text, HORIZONTAL_ALIGNMENT_CENTER, 1024, size, 10, Color(0.08, 0.04, 0.16, 0.9))
	c.draw_string(font_bold, Vector2(0, base), toast_text, HORIZONTAL_ALIGNMENT_CENTER, 1024, size, toast_color)


func _update_toast(dt: float, view_pos: Vector3, view_basis: Basis) -> void:
	if toast_life <= 0.0:
		toast_quad.visible = false
		return
	toast_life -= dt
	var t := toast_dur - toast_life
	toast_mat.albedo_color.a = minf(1.0, t / 0.12) * minf(1.0, toast_life / 0.3)
	var target := view_pos + view_basis * Vector3(0, -0.09, -1.45)
	if not toast_init:
		toast_quad.global_position = target
		toast_init = true
	else:
		toast_quad.global_position = toast_quad.global_position.lerp(target, 1.0 - exp(-7.0 * dt))
	var q := Quaternion(toast_quad.global_transform.basis.orthonormalized()).slerp(Quaternion(view_basis.orthonormalized()), 1.0 - exp(-10.0 * dt))
	var s := 1.0 + 0.18 * maxf(0.0, 1.0 - t / 0.16)
	toast_quad.global_transform = Transform3D(Basis(q).scaled(Vector3(s, s, s)), toast_quad.global_position)


# --------------------------------------------------------------- wrist
func _status() -> Array:
	var m: String = game.mode()["id"]
	if game.state != "play":
		var txt := "ROUND OVER" if game.state == "results" else ("GET READY" if game.state == "countdown" else "FREE PLAY")
		return [txt, Color("#7bdff2")]
	if m == "tag":
		return ["YOU'RE IT!", Color("#ff7a45")] if player.it else ["SAFE", Color("#7bed9f")]
	if m == "infection":
		return ["SPORED", Color("#6dff7a")] if player.infected else ["CLEAN", Color("#7bdff2")]
	if m == "orbs":
		return ["ORBS %d" % player.score, Color("#ffd166")]
	return ["ALIVE", Color("#ffd166")] if player.alive else ["MELTED", Color("#ff7a45")]


func _paint_wrist(c: Control) -> void:
	var st := _status()
	rr(c, Rect2(6, 6, 244, 148), 26, Color(0.11, 0.063, 0.2, 0.9), 6, st[1])
	c.draw_string(font_semi, Vector2(0, 40), game.mode()["name"], HORIZONTAL_ALIGNMENT_CENTER, 256, 24, Color("#e9d9ff"))
	var t := "--:--"
	if game.state == "play":
		t = Game.fmt_time(game.timer)
	elif game.state == "countdown":
		t = str(maxi(1, ceili(game.timer)))
	elif game.state == "results":
		t = Game.fmt_time(game.result_timer)
	c.draw_string(font_bold, Vector2(0, 98), t, HORIZONTAL_ALIGNMENT_CENTER, 256, 52, Color("#fff7ec"))
	c.draw_string(font_bold, Vector2(0, 138), st[0], HORIZONTAL_ALIGNMENT_CENTER, 256, 28, st[1])


# --------------------------------------------------------------- board
func _label(id: String) -> String:
	match id:
		"prev", "next":
			return "MODE"
		"start":
			return "START" if game.state == "free" else "STOP"
		"bots":
			return "BOTS %d" % game.bot_count()
		"level":
			return Game.DIFFICULTY[game.difficulty]["name"]
		"color":
			return "COLOR"
		"turn":
			return "SNAP TURN" if player.snap_turn else "NO TURN"
	return id


func _draw_labels() -> void:
	for b in buttons:
		var label: Label3D = b["label"]
		var text := _label(b["id"])
		label.text = text
		var room: float = b["w"] * (0.55 if b["id"] in ["prev", "next", "color"] else 0.84)
		var tw := font_bold.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 64).x
		label.pixel_size = minf(b["h"] * 0.42 / 64.0, room / maxf(tw, 1.0))
		if b["id"] == "start":
			var col := Color("#51cf66") if game.state == "free" else Color("#ff6b6b")
			b["mat"].albedo_color = col
			b["mat"].emission = col * 0.35
		if b.has("swatch_mat"):
			b["swatch_mat"].albedo_color = player.color


func _row_stat(e) -> String:
	if game.state != "play":
		return ""
	var m: String = game.mode()["id"]
	if m == "tag":
		return "%ds" % int(e.it_time)
	if m == "infection":
		return "spored" if e.infected else "clean"
	if m == "orbs":
		return str(e.score)
	return "alive" if e.alive else "melted"


func _paint_board(c: Control) -> void:
	var W := 1024.0
	var H := 560.0
	c.draw_rect(Rect2(0, 0, W, H), Color("#5e3a22"))
	rr(c, Rect2(12, 12, W - 24, H - 24), 26, Color("#22143d"))
	rr(c, Rect2(12, 12, W - 24, (H - 24) * 0.55), 26, Color(0.21, 0.13, 0.35, 0.55))
	c.draw_string(font_bold, Vector2(40, 80), "SHROOM", HORIZONTAL_ALIGNMENT_LEFT, -1, 50, Color("#ffb347"))
	var tw := font_bold.get_string_size("SHROOM ", HORIZONTAL_ALIGNMENT_LEFT, -1, 50).x
	c.draw_string(font_bold, Vector2(40 + tw, 80), "SCRAMBLE", HORIZONTAL_ALIGNMENT_LEFT, -1, 50, Color("#7bdff2"))
	var mt: String = game.mode()["name"]
	var mw := font_bold.get_string_size(mt, HORIZONTAL_ALIGNMENT_LEFT, -1, 34).x + 96.0
	rr(c, Rect2(W - 40 - mw, 34, mw, 58), 29, Color("#ffd166"))
	tri(c, Vector2(W - 40 - mw + 26, 63), 11, -1.0, INK)
	tri(c, Vector2(W - 66, 63), 11, 1.0, INK)
	c.draw_string(font_bold, Vector2(W - 40 - mw, 75), mt, HORIZONTAL_ALIGNMENT_CENTER, mw, 34, INK)

	var line := ""
	var sub := ""
	var col := Color("#7bdff2")
	var ents: Array = game.ents
	if game.state == "free":
		line = "FREE PLAY"
		sub = "Punch START on the console to begin a round"
	elif game.state == "countdown":
		line = "GET READY… %d" % maxi(1, ceili(game.timer))
		col = Color("#ffd166")
	elif game.state == "play":
		line = Game.fmt_time(game.timer)
		col = Color("#fff7ec")
		var m: String = game.mode()["id"]
		if m == "tag":
			for e in ents:
				if e.it:
					sub = ("%s is IT" % e.pname) if e.is_bot else "YOU are IT"
		elif m == "infection":
			var clean := 0
			for e in ents:
				if not e.infected:
					clean += 1
			sub = "%d of %d still clean" % [clean, ents.size()]
		elif m == "orbs":
			sub = ("You have %d orbs" % player.score) if game.human_active else "Grab the orbs!"
		else:
			var alive_n := 0
			for e in ents:
				if e.alive:
					alive_n += 1
			sub = "%d still standing · lava %.1fm" % [alive_n, maxf(0.0, game.lava_y)]
	else:
		line = "ROUND OVER"
		sub = "Next round in %d…" % maxi(0, ceili(game.result_timer))
		col = Color("#ffd166")
	c.draw_string(font_bold, Vector2(40, 160), line, HORIZONTAL_ALIGNMENT_LEFT, -1, 56, col)
	var lw := font_bold.get_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, -1, 56).x
	c.draw_string(font_semi, Vector2(40 + lw + 26, 156), sub, HORIZONTAL_ALIGNMENT_LEFT, W - 80 - lw - 26, 30, Color("#e9d9ff"))
	c.draw_string(font_reg, Vector2(40, 202), game.mode()["desc"], HORIZONTAL_ALIGNMENT_LEFT, W - 80, 25, Color("#cbb8f0"))

	var showing_results := game.state == "results" and game.results.size() > 0
	var rows := []
	if showing_results:
		rows = game.results
	else:
		for e in ents:
			var badge := ""
			if e.it:
				badge = "IT"
			elif e.infected:
				badge = "SPORED"
			elif not e.alive and game.state == "play":
				badge = "OUT"
			rows.append({"name": e.pname if e.is_bot else "YOU", "color": e.color, "stat": _row_stat(e), "me": not e.is_bot, "badge": badge})
	var col_w := (W - 100.0) / 2.0
	var row_h := 46.0
	for i in range(mini(rows.size(), 10)):
		var r: Dictionary = rows[i]
		var cx := 40.0 + floorf(i / 5.0) * (col_w + 20.0)
		var cy := 236.0 + (i % 5) * row_h
		if r["me"]:
			rr(c, Rect2(cx - 8, cy, col_w, row_h - 6), 12, Color(1.0, 0.82, 0.4, 0.14))
		var x := cx + 6.0
		if showing_results:
			c.draw_string(font_bold, Vector2(x, cy + 30), "%d." % (i + 1), HORIZONTAL_ALIGNMENT_LEFT, -1, 26, Color("#ffd166") if i == 0 else Color("#9f8cc9"))
			x += 38.0
		c.draw_circle(Vector2(x + 12, cy + 20), 12, r["color"])
		var name_col := Color("#ffd166") if r["me"] else Color("#fff7ec")
		c.draw_string(font_semi, Vector2(x + 34, cy + 30), r["name"], HORIZONTAL_ALIGNMENT_LEFT, -1, 28, name_col)
		var badge: String = r.get("badge", "")
		if badge != "":
			var nw := font_semi.get_string_size(r["name"], HORIZONTAL_ALIGNMENT_LEFT, -1, 28).x
			var bw := font_bold.get_string_size(badge, HORIZONTAL_ALIGNMENT_LEFT, -1, 18).x + 18.0
			var bcol := Color("#ff7a45") if badge == "IT" else (Color("#4cd964") if badge == "SPORED" else Color("#8a7aa8"))
			rr(c, Rect2(x + 44 + nw, cy + 8, bw, 26), 13, bcol)
			c.draw_string(font_bold, Vector2(x + 53 + nw, cy + 28), badge, HORIZONTAL_ALIGNMENT_LEFT, -1, 18, Color("#1d1233"))
		var stat: String = r["stat"]
		if stat != "":
			c.draw_string(font_semi, Vector2(cx, cy + 29), stat, HORIZONTAL_ALIGNMENT_RIGHT, col_w - 20.0, 24, Color("#cbb8f0"))
	for i in range(mini(game.feed.size(), 2)):
		c.draw_string(font_reg, Vector2(40, 498 + i * 28), "• " + game.feed[i], HORIZONTAL_ALIGNMENT_LEFT, -1, 22, Color("#9f8cc9") if i > 0 else Color("#cbb8f0"))
	if game.human_active:
		c.draw_string(font_reg, Vector2(0, 526), "Push off with your hands · let go to fling!", HORIZONTAL_ALIGNMENT_RIGHT, W - 40, 22, Color("#9f8cc9"))


# --------------------------------------------------------------- input
func press(b: Dictionary, t: float, hand) -> void:
	if t < b["cool"]:
		return
	b["cool"] = t + 0.35
	b["down_until"] = t + 0.15
	sfx.click(b["mesh"].global_position)
	if hand != null:
		player.haptic(hand, 0.55, 0.035)
	match b["id"]:
		"prev":
			game.next_mode(-1)
		"next":
			game.next_mode(1)
		"start":
			game.toggle_round()
		"bots":
			game.cycle_bots()
			toast("%d BOTS" % game.bot_count(), Color("#74c0fc"))
		"level":
			game.cycle_difficulty()
			toast(Game.DIFFICULTY[game.difficulty]["name"], Color("#b197fc"))
		"color":
			player.set_color(player.color_idx + 1)
		"turn":
			player.snap_turn = not player.snap_turn
			toast("SNAP TURN ON" if player.snap_turn else "SNAP TURN OFF", Color("#ffd43b"))
	labels_dirty = true
	dirty = true


func update(dt: float, t: float, vr_active: bool, view_pos: Vector3, view_basis: Basis) -> void:
	clock = t
	var inv := panel.global_transform.affine_inverse()
	for hi in range(2):
		var h = player.hands[hi]
		var lp: Vector3 = inv * h.pos
		for b in buttons:
			var inside: bool = vr_active and absf(lp.x - b["x"]) < b["w"] / 2.0 + 0.02 and absf(lp.y - b["y"]) < b["h"] / 2.0 + 0.02 \
				and lp.z < FACE_Z + BTN_D + VRPlayer.HAND_R + 0.015 and lp.z > -0.1
			if inside and not b["inside"][hi]:
				press(b, t, h)
			b["inside"][hi] = inside
	for b in buttons:
		var mesh: MeshInstance3D = b["mesh"]
		var target: float = b["z"] - 0.03 if t < b["down_until"] else b["z"]
		mesh.position.z += (target - mesh.position.z) * (1.0 - exp(-30.0 * dt))
	if labels_dirty:
		labels_dirty = false
		_draw_labels()
	var live := game.state != "free"
	if t > board_at and (dirty or (live and t > board_tick)):
		dirty = false
		board_at = t + 0.3
		board_tick = t + 1.0
		_redraw(board_vp, board_canvas)
	wrist_quad.visible = vr_active
	if vr_active and t > wrist_at:
		wrist_at = t + 0.5
		_redraw(wrist_vp, wrist_canvas)
	_update_toast(dt, view_pos, view_basis)
