class_name Game
extends Node3D
## Round flow, the four game modes and the bots' decision making
## (port of the web build's game.js).

const MODES := [
	{"id": "tag", "name": "TAG", "time": 120.0, "desc": "One fuzzling is IT. Touch someone to pass it on. Least time as IT wins!"},
	{"id": "infection", "name": "SPORE TAG", "time": 150.0, "desc": "Spores spread on touch. Stay clean until the timer runs out!"},
	{"id": "orbs", "name": "ORB RUSH", "time": 90.0, "desc": "Grab the glowing orbs scattered over the islands. Most orbs wins!"},
	{"id": "lava", "name": "LAVA RISE", "time": 150.0, "desc": "The lava is rising! Climb high and be the last one standing."},
]
const DIFFICULTY := [{"name": "EASY", "skill": 0.78}, {"name": "NORMAL", "skill": 1.0}, {"name": "HARD", "skill": 1.22}]
const BOT_COUNTS := [3, 5, 7, 9]
const ORB_COUNT := 16

var player: VRPlayer
var bots: Array = []
var nav: Nav
var level: Level
var sfx: Sfx
var fx: FX

var mode_idx := 0
var state := "free"
var timer := 0.0
var elapsed := 0.0
var result_timer := 0.0
var free_timer := 0.0
var human_active := false
var bot_count_idx := 2
var difficulty := 1
var ents: Array = []
var results: Array = []
var feed: Array[String] = []
var lava_y := -40.0
var lava_start := -3.5
var last_beep := 4
var version := 0
var now := 0.0
var on_toast: Callable
var on_change: Callable

var orb_pos: Array[Vector3] = []
var orb_node := PackedInt32Array()
var orb_active := PackedByteArray()
var orb_respawn := PackedFloat32Array()
var orb_phase := PackedFloat32Array()
var orb_core: MultiMeshInstance3D
var orb_halo: MultiMeshInstance3D


func setup(p_player: VRPlayer, p_bots: Array, p_nav: Nav, p_level: Level, p_sfx: Sfx, p_fx: FX) -> void:
	player = p_player
	bots = p_bots
	nav = p_nav
	level = p_level
	sfx = p_sfx
	fx = p_fx
	_build_orbs()
	apply_bot_count()


func mode() -> Dictionary:
	return MODES[mode_idx]


func bot_count() -> int:
	return BOT_COUNTS[bot_count_idx]


func _changed() -> void:
	version += 1
	if on_change.is_valid():
		on_change.call()


func toast(text: String, color := Color("#fff7ec"), big := false) -> void:
	if on_toast.is_valid():
		on_toast.call(text, color, big)


func log_event(text: String) -> void:
	feed.push_front(text)
	if feed.size() > 4:
		feed.resize(4)
	_changed()


# ------------------------------------------------------------ setup
func apply_bot_count() -> void:
	for i in range(bots.size()):
		var b: Bot = bots[i]
		var on := i < bot_count()
		if on and not b.active:
			b.place_at(nav.random_good())
		b.set_active(on)
	_rebuild_ents()


func _rebuild_ents() -> void:
	ents = []
	if human_active:
		ents.append(player)
	for b in bots:
		if b.active:
			ents.append(b)


func set_human(on: bool) -> void:
	human_active = on
	_rebuild_ents()
	stop_round(true)


func next_mode(dir := 1) -> void:
	mode_idx = posmod(mode_idx + dir, MODES.size())
	stop_round(true)
	toast(mode()["name"], Color("#ffd166"))


func cycle_bots() -> void:
	bot_count_idx = (bot_count_idx + 1) % BOT_COUNTS.size()
	apply_bot_count()
	stop_round(true)


func cycle_difficulty() -> void:
	difficulty = (difficulty + 1) % DIFFICULTY.size()
	_changed()


func toggle_round() -> void:
	if state == "free":
		start_countdown()
	else:
		stop_round(false)


func _reset_roles() -> void:
	for e in ents:
		e.it = false
		e.infected = false
		e.alive = true
		e.ghost = false
		e.score = 0
		e.it_time = 0.0
		e.tags = 0
		e.stun_until = 0.0
		e.immune_until = 0.0
		e.out_time = 0.0
		e.infected_at = 0.0
		e.speed_mult = 1.0
		e.set_status_look("")
	for b in bots:
		if not b.alive:
			b.set_alive(true)
	for i in range(ORB_COUNT):
		orb_active[i] = 0


func stop_round(silent: bool) -> void:
	state = "free"
	free_timer = 0.0
	_reset_roles()
	results = []
	if not silent:
		toast("FREE PLAY", Color("#7bdff2"))
	_changed()


func start_countdown() -> void:
	_rebuild_ents()
	_reset_roles()
	results = []
	state = "countdown"
	timer = 3.5
	last_beep = 4
	if mode()["id"] == "lava":
		var ground := []
		for i in range(nav.n):
			if nav.ngood[i] == 1 and nav.nkind[i] == 0 and nav.nregion[i] == 0:
				ground.append(i)
		for b in bots:
			if b.active and ground.size() > 0:
				b.place_at(ground[randi() % ground.size()])
	toast(mode()["name"], Color("#ffd166"), true)
	_changed()


func _begin_play(t: float) -> void:
	state = "play"
	timer = mode()["time"]
	elapsed = 0.0
	var m: String = mode()["id"]
	if m == "tag" or m == "infection":
		var pool := []
		if ents.size() > 1 and randf() < 0.75:
			for e in ents:
				if e.is_bot:
					pool.append(e)
		if pool.is_empty():
			pool = ents.duplicate()
		var first = pool[randi() % pool.size()]
		if m == "tag":
			first.it = true
			first.set_status_look("it")
		else:
			first.infected = true
			first.set_status_look("infected")
		first.stun_until = t + 2.0
		if first == player:
			toast("YOU'RE IT!" if m == "tag" else "YOU HAVE SPORES!", Color("#ff7a45") if m == "tag" else Color("#6dff7a"), true)
		else:
			toast(("%s is IT — RUN!" if m == "tag" else "%s has spores — RUN!") % first.pname, Color("#ffd166"), true)
		log_event(("%s starts as IT" if m == "tag" else "%s starts spored") % first.pname)
	elif m == "orbs":
		for i in range(ORB_COUNT):
			_place_orb(i)
		toast("GRAB THE ORBS!", Color("#ffd166"), true)
	elif m == "lava":
		lava_y = lava_start
		toast("THE LAVA IS RISING!", Color("#ff7a45"), true)
	_apply_speed()
	sfx.horn()
	_changed()


func _end_round(reason: String) -> void:
	state = "results"
	result_timer = 9.0
	results = _compute_results()
	var me_won: bool = results.size() > 0 and results[0]["me"]
	if reason != "":
		log_event(reason)
	if me_won:
		toast("YOU WIN!", Color("#ffd166"), true)
	elif results.size() > 0:
		toast("%s WINS!" % results[0]["name"], Color("#fff7ec"), true)
	sfx.fanfare(me_won)
	for e in ents:
		e.it = false
		e.infected = false
		e.set_status_look("")
		e.speed_mult = 1.0
	_changed()


func _compute_results() -> Array:
	var m: String = mode()["id"]
	var rows := ents.duplicate()
	if m == "tag":
		rows.sort_custom(func(a, b): return a.it_time < b.it_time)
	elif m == "infection":
		rows.sort_custom(func(a, b): return (b.infected_at < a.infected_at) if a.infected == b.infected else (not a.infected))
	elif m == "orbs":
		rows.sort_custom(func(a, b): return a.score > b.score)
	else:
		rows.sort_custom(func(a, b): return (b.out_time < a.out_time) if a.alive == b.alive else a.alive)
	var out := []
	for e in rows:
		var stat := ""
		if m == "tag":
			stat = "%.1fs IT" % e.it_time
		elif m == "infection":
			stat = ("spored " + fmt_time(e.infected_at)) if e.infected else "CLEAN!"
		elif m == "orbs":
			stat = "%d orbs" % e.score
		else:
			stat = "SURVIVED" if e.alive else "melted " + fmt_time(e.out_time)
		out.append({"name": e.pname, "color": e.color, "stat": stat, "me": not e.is_bot})
	return out


static func fmt_time(t: float) -> String:
	var s := maxi(0, ceili(t))
	return "%d:%02d" % [s / 60, s % 60]


func _apply_speed() -> void:
	for e in ents:
		e.speed_mult = 1.12 if (e.it or e.infected) else 1.0


# -------------------------------------------------------------- loop
func update(dt: float, t: float) -> void:
	now = t
	var skill: float = DIFFICULTY[difficulty]["skill"]
	for b in bots:
		if not b.active:
			continue
		b.skill = skill * (1.0 if state == "play" else 0.85)
		if t >= b.think_at:
			b.think_at = t + 0.22 + randf() * 0.1
			_brain(b, t)
	match state:
		"free":
			if not human_active:
				free_timer += dt
				if free_timer > 3.0:
					start_countdown()
		"countdown":
			timer -= dt
			var sec := ceili(timer)
			if sec < last_beep and sec >= 1 and sec <= 3:
				last_beep = sec
				sfx.beep(false)
				toast(str(sec), Color("#fff7ec"), true)
			if timer <= 0.0:
				sfx.beep(true)
				_begin_play(t)
		"play":
			timer -= dt
			elapsed += dt
			_mode_update(dt, t)
			if state == "play" and timer <= 0.0:
				var m: String = mode()["id"]
				_end_round("Time! The clean ones win." if m == "infection" else ("Time! Survivors win." if m == "lava" else "Time!"))
		"results":
			result_timer -= dt
			if result_timer <= 0.0:
				start_countdown()
	if not (state == "play" and mode()["id"] == "lava") and lava_y > -40.0:
		lava_y = maxf(-40.0, lava_y - dt * 3.0)
	level.set_lava(lava_y, lava_y > -39.5)
	_animate_orbs(t)


func _mode_update(dt: float, t: float) -> void:
	var m: String = mode()["id"]
	if m == "tag":
		for a in ents:
			if not a.it:
				continue
			a.it_time += dt
			if t < a.stun_until:
				continue
			for b in ents:
				if b == a or b.it or t < b.immune_until:
					continue
				if _touching(a, b):
					_pass_tag(a, b, t)
					break
	elif m == "infection":
		for a in ents:
			if not a.infected or t < a.stun_until:
				continue
			for b in ents:
				if b != a and not b.infected and _touching(a, b):
					_infect(a, b, t)
		var all_in := ents.size() > 1
		for e in ents:
			if not e.infected:
				all_in = false
				break
		if all_in:
			_end_round("Everyone got spored!")
	elif m == "orbs":
		for i in range(ORB_COUNT):
			if orb_active[i] == 0:
				if orb_respawn[i] > 0.0 and t > orb_respawn[i]:
					_place_orb(i)
				continue
			for e in ents:
				if _near_point(e, orb_pos[i], 0.3):
					_collect(i, e, t)
					break
	elif m == "lava":
		lava_y = lava_start + elapsed * 0.055 + elapsed * elapsed * 0.00045
		var alive_n := 0
		for e in ents:
			if not e.alive:
				continue
			var y: float = e.pos.y - 0.12 if e.is_bot else e.body_pos.y - 0.05
			if y < lava_y:
				_melt(e)
			else:
				alive_n += 1
		if (ents.size() > 1 and alive_n <= 1) or alive_n == 0:
			var last = null
			for e in ents:
				if e.alive:
					last = e
					break
			_end_round(("%s is the last one standing!" % last.pname) if last != null else "Everyone melted!")


func _touching(a, b) -> bool:
	var pa: PackedVector3Array = a.sph_pos
	var ra: PackedFloat32Array = a.sph_r
	var pb: PackedVector3Array = b.sph_pos
	var rb: PackedFloat32Array = b.sph_r
	for i in range(pa.size()):
		if ra[i] <= 0.0:
			continue
		for j in range(pb.size()):
			if rb[j] <= 0.0:
				continue
			var rr := ra[i] + rb[j]
			if pa[i].distance_squared_to(pb[j]) < rr * rr:
				return true
	return false


func _near_point(e, p: Vector3, r: float) -> bool:
	var pa: PackedVector3Array = e.sph_pos
	var ra: PackedFloat32Array = e.sph_r
	for i in range(pa.size()):
		if ra[i] <= 0.0:
			continue
		var rr := ra[i] + r
		if pa[i].distance_squared_to(p) < rr * rr:
			return true
	return false


func _haptic_player(amp: float, seconds: float) -> void:
	for h in player.hands:
		player.haptic(h, amp, seconds)


func _pass_tag(a, b, t: float) -> void:
	a.it = false
	a.set_status_look("")
	a.immune_until = t + 2.5
	a.tags += 1
	b.it = true
	b.set_status_look("it")
	b.stun_until = t + (1.6 if b.is_bot else 0.6)
	_apply_speed()
	fx.burst(b.body_pos, Color("#ff7a2f"), 22, 4.0, 0.7)
	if b == player:
		sfx.tag("got")
		toast("YOU'RE IT!", Color("#ff7a45"), true)
		_haptic_player(1.0, 0.12)
	elif a == player:
		sfx.tag("made")
		toast("Tagged %s!" % b.pname, Color("#7bed9f"))
		_haptic_player(0.7, 0.06)
	else:
		sfx.tag("other", b.body_pos)
	log_event("%s tagged %s" % [a.pname, b.pname])


func _infect(a, b, t: float) -> void:
	b.infected = true
	b.infected_at = elapsed
	b.set_status_look("infected")
	b.stun_until = t + (1.2 if b.is_bot else 0.5)
	a.tags += 1
	_apply_speed()
	fx.burst(b.body_pos, Color("#6dff7a"), 22, 3.5, 0.8)
	if b == player:
		sfx.tag("got")
		toast("SPORED! Go get them!", Color("#6dff7a"), true)
		_haptic_player(1.0, 0.12)
	elif a == player:
		sfx.tag("made")
		toast("Spored %s!" % b.pname, Color("#6dff7a"))
		_haptic_player(0.7, 0.06)
	else:
		sfx.tag("other", b.body_pos)
	var left := 0
	for e in ents:
		if not e.infected:
			left += 1
	log_event("%s spored %s (%d left)" % [a.pname, b.pname, left])


func _melt(e) -> void:
	e.alive = false
	e.out_time = elapsed
	fx.burst(Vector3(e.body_pos.x, lava_y + 0.2, e.body_pos.z), Color("#ff5a1f"), 26, 4.0, 0.9)
	sfx.sizzle(e.body_pos)
	if e.is_bot:
		e.set_alive(false)
	else:
		e.ghost = true
		e.set_status_look("ghost")
		toast("YOU MELTED! Spectating…", Color("#ff7a45"), true)
		_haptic_player(1.0, 0.2)
	log_event("%s melted!" % e.pname)


# -------------------------------------------------------------- orbs
func _build_orbs() -> void:
	orb_pos.resize(ORB_COUNT)
	orb_node.resize(ORB_COUNT)
	orb_active.resize(ORB_COUNT)
	orb_respawn.resize(ORB_COUNT)
	orb_phase.resize(ORB_COUNT)
	for i in range(ORB_COUNT):
		orb_pos[i] = Vector3.ZERO
		orb_phase[i] = randf() * 6.0
	var core_mesh := SphereMesh.new()
	core_mesh.radius = 0.15
	core_mesh.height = 0.3
	core_mesh.radial_segments = 10
	core_mesh.rings = 5
	core_mesh.material = Level.unshaded(Color("#ffe27a"))
	var halo_mesh := SphereMesh.new()
	halo_mesh.radius = 0.3
	halo_mesh.height = 0.6
	halo_mesh.radial_segments = 12
	halo_mesh.rings = 6
	var hm := Level.unshaded(Color(1.0, 0.7, 0.28, 0.28))
	hm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	hm.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	hm.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	halo_mesh.material = hm
	orb_core = MultiMeshInstance3D.new()
	orb_halo = MultiMeshInstance3D.new()
	for pair in [[orb_core, core_mesh], [orb_halo, halo_mesh]]:
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.instance_count = ORB_COUNT
		mm.mesh = pair[1]
		pair[0].multimesh = mm
		pair[0].extra_cull_margin = 16384.0
		add_child(pair[0])


func _place_orb(i: int) -> void:
	var best := -1
	for tries in range(40):
		var c := randi() % nav.n
		if nav.nkind[c] == 0 and randf() < 0.55:
			continue
		var p := nav.pos(c)
		var ok := true
		for j in range(ORB_COUNT):
			if j != i and orb_active[j] == 1 and orb_pos[j].distance_squared_to(p) < 16.0:
				ok = false
				break
		if ok:
			best = c
			break
	if best < 0:
		best = randi() % nav.n
	orb_node[i] = best
	orb_pos[i] = nav.pos(best) + Vector3(0, 0.15, 0)
	orb_active[i] = 1
	orb_respawn[i] = 0.0


func _collect(i: int, e, t: float) -> void:
	orb_active[i] = 0
	orb_respawn[i] = t + 4.0
	e.score += 1
	fx.burst(orb_pos[i], Color("#ffd34d"), 18, 3.0, 0.6)
	sfx.orb(orb_pos[i], e == player)
	if e == player:
		toast("+1 ORB  (%d)" % e.score, Color("#ffd166"))
		_haptic_player(0.6, 0.05)
	_changed()


func _animate_orbs(t: float) -> void:
	var show: bool = state == "play" and mode()["id"] == "orbs"
	for i in range(ORB_COUNT):
		var s := 0.0
		if show and orb_active[i] == 1:
			s = 1.0 + sin(t * 5.0 + orb_phase[i]) * 0.12
		var b := Basis.from_euler(Vector3(t * 1.3 + orb_phase[i], t * 1.7, 0)).scaled(Vector3(s, s, s)) if s > 0.0 else Basis.from_scale(Vector3(0.0001, 0.0001, 0.0001))
		var xf := Transform3D(b, orb_pos[i] + Vector3(0, sin(t * 2.0 + orb_phase[i]) * 0.08, 0))
		orb_core.multimesh.set_instance_transform(i, xf)
		orb_halo.multimesh.set_instance_transform(i, xf)


# ------------------------------------------------------------ brains
func _brain(bot: Bot, t: float) -> void:
	if not bot.alive:
		bot.intent = "idle"
		bot.target = null
		return
	var m: String = mode()["id"] if state == "play" else "free"
	if m == "tag" or m == "infection":
		var hunter: bool = bot.it if m == "tag" else bot.infected
		if hunter:
			var cur = bot.target if bot.intent == "chase" else null
			var tgt = _pick_target(bot, m, t, cur)
			bot.intent = "chase" if tgt != null else "wander"
			bot.target = tgt
		else:
			var threat = null
			var td := 1e9
			for e in ents:
				if e == bot:
					continue
				var hunting: bool = e.it if m == "tag" else e.infected
				if not hunting:
					continue
				var d: float = e.body_pos.distance_to(bot.pos)
				if d < td:
					td = d
					threat = e
			if threat != null and td < 11.0 * (0.75 + 0.25 * bot.skill):
				bot.intent = "flee"
				bot.target = threat
			else:
				bot.intent = "wander"
				bot.target = null
	elif m == "orbs":
		var best := -1
		var bs := 1e9
		for i in range(ORB_COUNT):
			if orb_active[i] == 0 or nav.ngood[orb_node[i]] == 0:
				continue
			var s := orb_pos[i].distance_to(bot.pos) + maxf(0.0, orb_pos[i].y - bot.pos.y) * 0.8
			for b in bots:
				if b != bot and b.active and b.intent == "goto" and b.intent_node == orb_node[i] and b.pos.distance_to(orb_pos[i]) < orb_pos[i].distance_to(bot.pos):
					s += 8.0
			if s < bs:
				bs = s
				best = i
		if best >= 0:
			bot.intent = "goto"
			bot.intent_node = orb_node[best]
		else:
			bot.intent = "wander"
		bot.target = null
	elif m == "lava":
		var need := bot.lava_node < 0 or t > bot.lava_pick_at
		if not need and nav.ny[bot.lava_node] < lava_y + 1.8:
			need = true
		if need:
			bot.lava_node = _pick_safe(bot)
			bot.lava_pick_at = t + 3.0 + randf() * 3.0
		bot.intent = "goto"
		bot.intent_node = bot.lava_node
		bot.target = null
	else:
		bot.intent = "wander"
		bot.target = null


func _pick_target(bot: Bot, m: String, t: float, current):
	var best = null
	var bd := 1e9
	for e in ents:
		if e == bot or not e.alive:
			continue
		if m == "tag":
			if e.it or t < e.immune_until:
				continue
		elif e.infected:
			continue
		var d: float = e.body_pos.distance_to(bot.pos)
		if not e.is_bot:
			d *= 0.75
		d += maxf(0.0, e.body_pos.y - bot.pos.y - 1.5) * 1.5
		if e == current:
			d *= 0.8
		if d < bd:
			bd = d
			best = e
	return best


func _pick_safe(bot: Bot) -> int:
	var best := -1
	var bs := -1e9
	for k in range(36):
		var i := nav.random_good()
		if nav.ny[i] < lava_y + 2.2:
			continue
		var s := nav.ny[i] * 1.2 - sqrt((nav.nx[i] - bot.pos.x) ** 2 + (nav.nz[i] - bot.pos.z) ** 2) * 0.45 + randf() * 3.0
		if s > bs:
			bs = s
			best = i
	if best < 0:
		for i in nav.good_list:
			if best < 0 or nav.ny[i] > nav.ny[best]:
				best = i
	return best
