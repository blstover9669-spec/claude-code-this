class_name Bot
extends Node3D
## A fuzzling: an AI player that gallops on its hands, hops, pounces and
## leaps along the nav graph (port of the web build's bots.js).

const G := 9.8
const BOT_R := 0.36
## path replans allowed this frame (reset by the frame loop)
static var replans_left := 2
const PROFILES := [
	{"name": "Pip", "color": Color("#ff6b6b"), "hat": "cap"},
	{"name": "Moss", "color": Color("#6fcf7f"), "hat": "leaf"},
	{"name": "Biscuit", "color": Color("#f4a259"), "hat": "tuft"},
	{"name": "Zuzu", "color": Color("#a78bfa"), "hat": "antenna"},
	{"name": "Nib", "color": Color("#4cc9f0"), "hat": "horns"},
	{"name": "Tumble", "color": Color("#ffd166"), "hat": "bow"},
	{"name": "Fizz", "color": Color("#2ec4b6"), "hat": "antenna"},
	{"name": "Pebble", "color": Color("#b9b3d6"), "hat": "cap"},
	{"name": "Waffle", "color": Color("#c88a5a"), "hat": "leaf"},
]

var phys: Phys
var nav: Nav
var sfx: Sfx
var fx: FX

var is_bot := true
var pname := ""
var color := Color.WHITE
var hat := ""
var pos := Vector3.ZERO
var body_pos := Vector3.ZERO
var vel := Vector3.ZERO
var desired := Vector3.ZERO
var facing := 0.0
var ground_time := -10.0
var jumping := false
var jump_start := 0.0
var jump_to := -1
var path := PackedInt32Array()
var has_path := false
var path_idx := 0
var goal := -1
var replan_at := 0.0
var flee_node := -1
var flee_at := 0.0
var wander_node := -1
var wander_at := 0.0
var lunge_at := 0.0
var stuck_at := 0.0
var stuck_ref := Vector3.ZERO
var los_at := 0.0
var los_ok := false
var think_at := 0.0
var lava_node := -1
var lava_pick_at := 0.0
# intent from the game: "wander" | "chase" | "flee" | "goto" | "idle"
var intent := "wander"
var target = null
var intent_node := -1
var skill := 1.0
var speed_mult := 1.0
var personal := 1.0
var active := true

var it := false
var infected := false
var alive := true
var ghost := false
var score := 0
var it_time := 0.0
var tags := 0
var stun_until := 0.0
var immune_until := 0.0
var out_time := 0.0
var infected_at := 0.0
var sph_pos := PackedVector3Array([Vector3.ZERO, Vector3.ZERO, Vector3.ZERO])
var sph_r := PackedFloat32Array([BOT_R + 0.03, 0.1, 0.1])

var near := PackedInt32Array()
var anim_phase := 0.0
var blink_at := 2.0
var blink_end := 0.0
var hand_pos := [Vector3.ZERO, Vector3.ZERO]
var shadow_at := 0.0
var shadow_y := -100.0
var last_chirp := 0.0

var body: MeshInstance3D
var eyes: MeshInstance3D
var ring: MeshInstance3D
var stars: Node3D
var tag_label: Label3D
var body_mat: StandardMaterial3D
var ring_mat: StandardMaterial3D
var hand_nodes: Array[MeshInstance3D] = []
var arm_nodes: Array[MeshInstance3D] = []
var shadow: MeshInstance3D


func setup(profile: Dictionary, p_phys: Phys, p_nav: Nav, p_sfx: Sfx, p_fx: FX, shared: Dictionary, world: Node3D) -> void:
	phys = p_phys
	nav = p_nav
	sfx = p_sfx
	fx = p_fx
	pname = profile["name"]
	color = profile["color"]
	hat = profile["hat"]
	personal = randf_range(0.92, 1.08)
	facing = randf() * TAU
	shadow_at = randf() * 0.08
	anim_phase = randf() * 6.0
	blink_at = randf_range(1.0, 4.0)
	body_mat = Level.lambert(color)
	body = MeshInstance3D.new()
	body.mesh = shared["bot_body"]
	body.material_override = body_mat
	add_child(body)
	eyes = MeshInstance3D.new()
	eyes.mesh = shared["bot_eyes"]
	eyes.material_override = shared["vc_mat"]
	eyes.position = Vector3(0, 0.08, 0)
	body.add_child(eyes)
	var hat_mesh := MeshInstance3D.new()
	hat_mesh.mesh = shared["hat_" + hat]
	hat_mesh.material_override = shared["vc_mat"]
	body.add_child(hat_mesh)
	ring_mat = Level.unshaded(Color8(0xff, 0x8a, 0x2a))
	ring = MeshInstance3D.new()
	ring.mesh = shared["bot_ring"]
	ring.material_override = ring_mat
	ring.position.y = 0.62
	ring.visible = false
	add_child(ring)
	stars = Node3D.new()
	for i in range(3):
		var s := MeshInstance3D.new()
		s.mesh = shared["bot_star"]
		s.material_override = shared["star_mat"]
		var a := float(i) / 3.0 * TAU
		s.position = Vector3(cos(a) * 0.26, 0, sin(a) * 0.26)
		stars.add_child(s)
	stars.position.y = 0.5
	stars.visible = false
	add_child(stars)
	tag_label = Label3D.new()
	tag_label.text = pname
	tag_label.font = shared["font_semibold"]
	tag_label.font_size = 48
	tag_label.pixel_size = 0.0036
	tag_label.outline_size = 14
	tag_label.outline_modulate = Color(0.1, 0.06, 0.18, 0.85)
	tag_label.modulate = Color(1, 0.97, 0.93)
	tag_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	tag_label.position.y = 0.82
	add_child(tag_label)
	var hm := Level.lambert(color * 0.72)
	for i in range(2):
		var h := MeshInstance3D.new()
		h.mesh = shared["bot_hand"]
		h.material_override = hm
		world.add_child(h)
		hand_nodes.append(h)
		var a := MeshInstance3D.new()
		a.mesh = shared["bot_arm"]
		a.material_override = hm
		world.add_child(a)
		arm_nodes.append(a)
	shadow = MeshInstance3D.new()
	shadow.mesh = shared["shadow_mesh"]
	shadow.material_override = shared["shadow_mat"]
	world.add_child(shadow)


func set_active(on: bool) -> void:
	active = on
	_set_visible(on and alive)


func _set_visible(v: bool) -> void:
	visible = v
	shadow.visible = v
	for n in hand_nodes:
		n.visible = v
	for n in arm_nodes:
		n.visible = v


func set_alive(a: bool) -> void:
	alive = a
	_set_visible(a and active)


func set_status_look(kind: String) -> void:
	body_mat.emission_enabled = kind == "it" or kind == "infected"
	body_mat.emission = Color8(0xff, 0x4a, 0x10) if kind == "it" else Color8(0x2f, 0xd6, 0x5a)
	body_mat.emission_energy_multiplier = 0.42 if kind == "it" else 0.38
	body_mat.albedo_color = color.lerp(Color8(0x7d, 0xff, 0x8a), 0.45) if kind == "infected" else color
	ring.visible = kind == "it" or kind == "infected"
	ring_mat.albedo_color = Color8(0x6d, 0xff, 0x7a) if kind == "infected" else Color8(0xff, 0x8a, 0x2a)


func place_at(node: int) -> void:
	var p := nav.pos(node)
	pos = Vector3(p.x + randf_range(-0.25, 0.25), p.y + 0.2, p.z + randf_range(-0.25, 0.25))
	body_pos = pos
	vel = Vector3.ZERO
	jumping = false
	has_path = false
	goal = -1
	hand_pos = [pos, pos]


func is_grounded(now: float) -> bool:
	return now - ground_time < 0.1


func _start_jump(now: float, to: int) -> void:
	jumping = true
	jump_start = now
	jump_to = to
	ground_time = -10.0


func _los(now: float, tp: Vector3) -> bool:
	if now < los_at:
		return los_ok
	los_at = now + 0.2
	var mid := (pos + tp) * 0.5
	var lst := phys.gather(mid.x, mid.y, mid.z, pos.distance_to(tp) * 0.5 + 1.0)
	los_ok = phys.segment_clear(lst, pos + Vector3(0, 0.1, 0), tp, 0.16, 0.4)
	return los_ok


func _steer_to(x: float, z: float, spd: float, arrive: bool) -> float:
	var dx := x - pos.x
	var dz := z - pos.z
	var dist := sqrt(dx * dx + dz * dz)
	if dist > 0.05:
		var s := spd * minf(1.0, 0.25 + dist * 0.5) if arrive else spd
		if not (arrive and dist < 0.35):
			desired = Vector3(dx / dist * s, 0, dz / dist * s)
	return dist


func _pick_flee(tp: Vector3) -> int:
	var best := -1
	var bs := -1e9
	var tx := tp.x - pos.x
	var tz := tp.z - pos.z
	var tl := maxf(sqrt(tx * tx + tz * tz), 0.001)
	for k in range(22):
		var i := nav.random_good()
		var np := nav.pos(i)
		var d_me := sqrt((np.x - pos.x) ** 2 + (np.z - pos.z) ** 2)
		if d_me > 20.0:
			continue
		var d_t := sqrt((np.x - tp.x) ** 2 + (np.z - tp.z) ** 2) + maxf(0.0, np.y - tp.y) * 0.8
		var s := d_t - d_me * 0.3 + (1.2 if nav.nkind[i] == 1 else 0.0) + randf() * 2.5
		var dot := ((np.x - pos.x) * tx + (np.z - pos.z) * tz) / (maxf(d_me, 0.001) * tl)
		if dot > 0.4:
			s -= 8.0
		if s > bs:
			bs = s
			best = i
	return best


func _pick_wander() -> int:
	for k in range(12):
		var i := nav.random_good()
		var np := nav.pos(i)
		if sqrt((np.x - pos.x) ** 2 + (np.z - pos.z) ** 2) < 16.0:
			return i
	return nav.random_good()


func _follow(now: float, g: int, spd: float) -> void:
	if g < 0 or jumping:
		return
	var need := g != goal or not has_path or now > replan_at
	if need and replans_left > 0:
		# path finding is the expensive bit: only a couple of bots replan per frame
		replans_left -= 1
		goal = g
		replan_at = now + 0.8 + randf() * 0.5
		var start := nav.nearest(pos.x, pos.y, pos.z, false)
		path = nav.find_path(start, g)
		has_path = true
		path_idx = 0
	elif need and (g != goal or not has_path):
		var gp0 := nav.pos(g)
		_steer_to(gp0.x, gp0.z, spd, true)
		return
	if path_idx >= path.size():
		var gp := nav.pos(g)
		_steer_to(gp.x, gp.z, spd, true)
		return
	var ei := path[path_idx]
	var a := nav.pos(nav.e_from[ei])
	var b := nav.pos(nav.e_to[ei])
	if nav.e_jump[ei] == 0:
		if _steer_to(b.x, b.z, spd, false) < 0.9:
			path_idx += 1
		return
	var d_a := sqrt((a.x - pos.x) ** 2 + (a.z - pos.z) ** 2)
	if d_a > 0.9 or absf(a.y - pos.y) > 0.9:
		_steer_to(a.x, a.z, spd, d_a < 2.0)
		if d_a > 6.0 or absf(a.y - pos.y) > 2.0:
			replan_at = minf(replan_at, now + 0.25)
		return
	if is_grounded(now):
		var v := nav.launch(pos, b, 10.0, 12.5)
		if nav.launch_t > 0.0:
			vel = v
			_start_jump(now, nav.e_to[ei])
			path_idx += 1
			if randf() < 0.25:
				_chirp(now, 1.0)
		else:
			replan_at = now
	else:
		_steer_to(a.x, a.z, spd * 0.5, true)


func _chirp(now: float, pitch: float) -> void:
	if now - last_chirp < 0.8:
		return
	last_chirp = now
	sfx.chirp(pos, pitch * personal)


func think(now: float) -> void:
	desired = Vector3.ZERO
	if now < stun_until:
		return
	var spd := 4.5 * skill * speed_mult * personal
	var grounded := is_grounded(now)
	if intent == "chase" and target != null:
		var tp: Vector3 = target.body_pos
		var tv: Vector3 = target.vel
		var lead := 0.3 * skill
		var px := tp.x + tv.x * lead
		var pz := tp.z + tv.z * lead
		var py := tp.y
		var dx := px - pos.x
		var dz := pz - pos.z
		var dy := py - pos.y
		var dxz := maxf(sqrt(dx * dx + dz * dz), 0.001)
		if dxz < 7.5 and dy < 1.4 and dy > -2.5 and _los(now, tp):
			has_path = false
			goal = -1
			desired = Vector3(dx / dxz * spd, 0, dz / dxz * spd)
			if grounded and not jumping and now > lunge_at and dxz < 2.9 * skill:
				var s := 5.2 + 1.6 * skill
				vel = Vector3(dx / dxz * s, 3.3 + maxf(0.0, dy) * 1.6, dz / dxz * s)
				_start_jump(now, -1)
				lunge_at = now + 1.0 + randf() * 0.6 / skill
				_chirp(now, 1.35)
			return
		if dy >= 1.4 and dy < 5.0 and dxz < 6.5 and grounded and not jumping and now > lunge_at:
			var v := nav.launch(pos, Vector3(px, py + 0.15, pz), 9.5, 12.5)
			if nav.launch_t > 0.0:
				vel = v
				_start_jump(now, -1)
				lunge_at = now + 1.4 + randf() * 0.7
				_chirp(now, 1.15)
				return
		_follow(now, nav.nearest(px, py, pz), spd)
	elif intent == "flee" and target != null:
		var tp: Vector3 = target.body_pos
		var dist := pos.distance_to(tp)
		if flee_node < 0 or now > flee_at or (dist < 4.0 and now > flee_at - 1.2):
			flee_node = _pick_flee(tp)
			flee_at = now + 1.8 + randf()
		if dist < 2.3 and grounded and not jumping and now > lunge_at and randf() < 0.6 * skill:
			var ax := pos.x - tp.x
			var az := pos.z - tp.z
			var al := maxf(sqrt(ax * ax + az * az), 0.001)
			var side := 1.0 if randf() < 0.5 else -1.0
			var ux := ax / al
			var uz := az / al
			var ex := ux * 0.8 - uz * side * 0.6
			var ez := uz * 0.8 + ux * side * 0.6
			vel = Vector3(ex * 6.0 * skill, 4.3, ez * 6.0 * skill)
			_start_jump(now, -1)
			lunge_at = now + 1.4
			_chirp(now, 1.7)
			return
		_follow(now, flee_node, spd)
	elif intent == "goto" and intent_node >= 0:
		_follow(now, intent_node, spd)
	elif intent == "idle":
		pass
	else:
		var need := wander_node < 0 or now > wander_at
		if not need:
			var wp := nav.pos(wander_node)
			need = sqrt((wp.x - pos.x) ** 2 + (wp.z - pos.z) ** 2) < 1.2
		if need:
			wander_node = _pick_wander()
			wander_at = now + 6.0 + randf() * 7.0
		_follow(now, wander_node, spd * 0.72)
	# stuck? hop and replan
	if now > stuck_at:
		if desired.length_squared() > 1.0 and pos.distance_to(stuck_ref) < 0.6 and not jumping:
			vel.y = 5.2
			vel.x += randf_range(-2.0, 2.0)
			vel.z += randf_range(-2.0, 2.0)
			_start_jump(now, -1)
			replan_at = now
			wander_node = -1
			flee_node = -1
		stuck_ref = pos
		stuck_at = now + 2.0


func update(dt: float, now: float) -> void:
	if not active or not alive:
		return
	think(now)
	_integrate(dt, now)
	_animate(dt, now)


func _integrate(dt: float, now: float) -> void:
	var grounded := is_grounded(now)
	if jumping:
		if jump_to >= 0:
			var b := nav.pos(jump_to)
			var disc := vel.y * vel.y + 2.0 * G * (pos.y - b.y)
			if disc > 0.0:
				var tl := maxf(0.12, (vel.y + sqrt(disc)) / G)
				var wx := (b.x - pos.x) / tl
				var wz := (b.z - pos.z) / tl
				var acc := 6.0 * dt
				var ax := wx - vel.x
				var az := wz - vel.z
				var al := sqrt(ax * ax + az * az)
				if al > acc:
					ax *= acc / al
					az *= acc / al
				vel.x += ax
				vel.z += az
		if now - jump_start > 3.0:
			jumping = false
	else:
		var hopping := now - ground_time < 0.75
		var acc := (26.0 if grounded or hopping else 4.0) * dt
		var ax := desired.x - vel.x
		var az := desired.z - vel.z
		var al := sqrt(ax * ax + az * az)
		if al > acc:
			ax *= acc / al
			az *= acc / al
		vel.x += ax
		vel.z += az
		if grounded and desired.x * desired.x + desired.z * desired.z > 1.0:
			vel.y = 2.2 + randf() * 0.5
	vel.y -= G * dt
	pos += vel * dt
	near = phys.gather(pos.x, pos.y, pos.z, BOT_R + 0.6 + vel.length() * dt)
	if phys.resolve_sphere(near, pos, BOT_R, vel, true):
		pos = phys.rs_pos
		vel = phys.rs_vel
		if phys.cbounce[phys.rs_col] > 0.0 and phys.rs_impact > 1.8 and phys.rs_n.y > 0.3:
			vel.y = maxf(vel.y, 8.2 + randf() * 2.5)
			_start_jump(now, -1)
			sfx.boing(pos, 0.55)
			fx.burst(pos - Vector3(0, BOT_R, 0), Color8(0xff, 0x7a, 0xb8), 8, 2.5, 0.5)
		elif phys.rs_ground:
			if jumping and now - jump_start > 0.12:
				jumping = false
				if jump_to >= 0:
					var b := nav.pos(jump_to)
					if sqrt((b.x - pos.x) ** 2 + (b.z - pos.z) ** 2) > 1.6 or absf(b.y - pos.y) > 1.0:
						replan_at = now
				if phys.rs_impact > 3.0:
					sfx.tap(phys.cmat[phys.rs_col], minf(0.7, phys.rs_impact / 10.0), pos)
			if not jumping:
				ground_time = now
	if grounded and not jumping and desired.x * desired.x + desired.z * desired.z < 0.01:
		var f := maxf(0.0, 1.0 - 10.0 * dt)
		vel.x *= f
		vel.z *= f
	body_pos = pos
	if pos.y < -24.0:
		place_at(nav.random_good())
		fx.burst(pos, Color.WHITE, 12, 2.0, 0.6)


func _animate(dt: float, now: float) -> void:
	var hs := sqrt(vel.x * vel.x + vel.z * vel.z)
	var yaw_t := facing
	var stunned := now < stun_until
	var chasing_close := target != null and intent == "chase" and pos.distance_to(target.body_pos) < 6.0
	if chasing_close:
		var tp: Vector3 = target.body_pos
		yaw_t = atan2(tp.x - pos.x, tp.z - pos.z)
	elif hs > 0.6:
		yaw_t = atan2(vel.x, vel.z)
	if stunned:
		facing += dt * 9.0
	else:
		facing = lerp_angle(facing, yaw_t, 1.0 - exp(-10.0 * dt))
	position = pos
	rotation = Vector3(0, facing, 0)
	var sy := clampf(1.0 + vel.y * 0.035, 0.84, 1.2)
	var sxz := 1.0 / sqrt(sy)
	body.scale = Vector3(sxz, sy, sxz)
	body.rotation.x = minf(0.35, hs * 0.05)
	if now > blink_at:
		blink_end = now + 0.12
		blink_at = now + randf_range(2.0, 6.0)
	eyes.scale.y = 0.12 if now < blink_end else 1.0
	stars.visible = stunned
	if stunned:
		stars.rotation.y = now * 6.0
	if ring.visible:
		ring.rotation.y = now * 2.5
		ring.position.y = 0.62 + sin(now * 4.0) * 0.03

	var fx_ := sin(facing)
	var fz := cos(facing)
	var sx := cos(facing)
	var sz := -sin(facing)
	var grounded := now - ground_time < 0.3 and not jumping
	if grounded and hs > 0.5:
		anim_phase += dt * hs / 0.3
	var reach := target != null and intent == "chase" and pos.distance_to(target.body_pos) < 2.2
	var k := 1.0 - exp(-26.0 * dt)
	for i in range(2):
		var sg := 1.0 if i == 1 else -1.0
		var ph := anim_phase + i * PI
		var fo := 0.14
		var up := -BOT_R + 0.09
		var so := 0.3
		if stunned:
			fo = 0.05
			up = 0.32 + sin(now * 12.0 + i * 3.0) * 0.08
			so = 0.24
		elif reach:
			fo = 0.5
			up = 0.05 + sin(now * 20.0 + i * 2.0) * 0.05
			so = 0.2
		elif not grounded:
			fo = 0.12
			up = 0.32
			so = 0.42
		elif hs > 0.5:
			fo = 0.08 - cos(ph) * 0.32
			up = -BOT_R + 0.1 + maxf(0.0, sin(ph)) * 0.22
		var t := Vector3(pos.x + fx_ * fo + sx * sg * so, pos.y + up, pos.z + fz * fo + sz * sg * so)
		var hp: Vector3 = hand_pos[i]
		hp = hp.lerp(t, k)
		hand_pos[i] = hp
		hand_nodes[i].global_transform = Transform3D(Basis(Vector3.UP, facing), hp)
		var sh := Vector3(pos.x + sx * sg * 0.25, pos.y + 0.02, pos.z + sz * sg * 0.25)
		var d := hp - sh
		var l := maxf(d.length(), 1e-4)
		arm_nodes[i].global_transform = Transform3D(Basis(Quaternion(Vector3.UP, d / l)) * Basis.from_scale(Vector3(1, maxf(0.01, l - 0.05), 1)), sh)
	sph_pos[0] = pos
	sph_pos[1] = hand_pos[0]
	sph_pos[2] = hand_pos[1]

	# blob shadow on whatever is below
	if now > shadow_at:
		shadow_at = now + 0.08
		var lst := phys.gather(pos.x, pos.y - 3.0, pos.z, 3.5)
		if phys.sphere_cast(lst, pos, pos - Vector3(0, 7, 0), 0.05):
			shadow_y = phys.res_pos.y - 0.04
		else:
			shadow_y = -100.0
	shadow.global_position = Vector3(pos.x, shadow_y, pos.z)
	var sc := clampf(1.2 - (pos.y - shadow_y) * 0.12, 0.3, 1.0)
	shadow.scale = Vector3(sc, 1, sc)
	shadow.visible = visible and shadow_y > -50.0


## Keep bots from stacking on top of each other.
static func separate(bots: Array) -> void:
	var min_d := BOT_R * 2.0
	for i in range(bots.size()):
		var a: Bot = bots[i]
		if not a.active or not a.alive:
			continue
		for j in range(i + 1, bots.size()):
			var b: Bot = bots[j]
			if not b.active or not b.alive:
				continue
			var d := b.pos - a.pos
			var d2 := d.length_squared()
			if d2 < min_d * min_d and d2 > 1e-6:
				var dl := sqrt(d2)
				var push := (min_d - dl) * 0.5
				var nx := d.x / dl
				var nz := d.z / dl
				a.pos.x -= nx * push
				a.pos.z -= nz * push
				b.pos.x += nx * push
				b.pos.z += nz * push
