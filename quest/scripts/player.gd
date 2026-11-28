class_name VRPlayer
extends Node3D
## Arm-powered locomotion (port of the web build's player.js): hands are
## solid spheres; pushing on the world moves the body, letting go keeps the
## momentum of the last ~85 ms.

const G := 9.8
const HEAD_R := 0.2
const HAND_R := 0.05
const MAX_ARM := 1.3
const UNSTICK := 0.9
const RELEASE := 0.012
const VEL_WINDOW := 0.085
const VEL_LIMIT := 0.45
const JUMP_MULT := 1.15
const MAX_JUMP := 7.2
const MAX_SPEED := 18.0
const HAND_OFFSET := Vector3(0, -0.01, -0.03)
const COLORS := [Color("#5ec8ff"), Color("#ff9f43"), Color("#7bed9f"), Color("#ff6b9a"),
	Color("#c59bff"), Color("#fff176"), Color("#f4f1ea"), Color("#3d4f73")]
const HIST := 24


class Hand:
	var side := 0
	var tracked := false
	var local := Vector3.ZERO
	var basis_local := Basis.IDENTITY
	var world_basis := Basis.IDENTITY
	var pos := Vector3.ZERO
	var prev := Vector3.ZERO
	var target := Vector3.ZERO
	var contact := false
	var anchor := Vector3.ZERO
	var normal := Vector3.UP
	var col := -1
	var corr := Vector3.ZERO
	var lift := 0.0
	var bounce_cool := 0.0
	var last_tap := 0.0
	var vel := Vector3.ZERO
	var pose_name := &""
	var node: Node3D
	var arm: MeshInstance3D
	var controller: XRController3D


var phys: Phys
var sfx: Sfx
var fx: FX
var origin: XROrigin3D
var camera: XRCamera3D

var is_bot := false
var pname := "YOU"
var color_idx := 0
var color: Color = COLORS[0]
var rig_pos := Vector3.ZERO
var yaw := 0.0
var rig_basis := Basis.IDENTITY
var vel := Vector3.ZERO
var head := Vector3(0, 1, 0)
var head_local := Vector3(0, 1.3, 0)
var head_basis_local := Basis.IDENTITY
var head_basis := Basis.IDENTITY
var body_pos := Vector3.ZERO
var hands: Array[Hand] = []
var near := PackedInt32Array()
var hist_t := PackedFloat64Array()
var hist_p := PackedVector3Array()
var hist_n := 0
var hist_i := 0
var bounce_lock := 0.0
var last_land := 0.0
var snap_turn := true
var stick_ready := true
var needs_spawn := true
var spawn_point := Vector3(0, 1.5, 17.5)
var spawn_wait := 0.0
var on_respawn: Callable

# game state (same shape as bots)
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
var speed_mult := 1.0
var sph_pos := PackedVector3Array([Vector3.ZERO, Vector3.ZERO, Vector3.ZERO, Vector3.ZERO])
var sph_r := PackedFloat32Array([0.24, 0.26, 0.075, 0.075])

var hand_mat: StandardMaterial3D
var arm_mat: StandardMaterial3D


func setup(p_phys: Phys, p_sfx: Sfx, p_fx: FX, p_origin: XROrigin3D, p_camera: XRCamera3D, ctrl: Array, meshes: Dictionary) -> void:
	phys = p_phys
	sfx = p_sfx
	fx = p_fx
	origin = p_origin
	camera = p_camera
	hist_t.resize(HIST)
	hist_p.resize(HIST)
	hand_mat = Level.lambert(color)
	arm_mat = Level.lambert(color * 0.8)
	for side in range(2):
		var h := Hand.new()
		h.side = side
		h.local = Vector3(0.22 if side == 1 else -0.22, 0.75, -0.25)
		h.controller = ctrl[side]
		h.node = Node3D.new()
		var mitt := MeshInstance3D.new()
		mitt.mesh = meshes["player_mitt"]
		mitt.material_override = hand_mat
		h.node.add_child(mitt)
		var thumb := MeshInstance3D.new()
		thumb.mesh = meshes["player_thumb"]
		thumb.material_override = hand_mat
		thumb.position = Vector3(-0.035 if side == 1 else 0.035, 0.0, -0.04)
		h.node.add_child(thumb)
		h.arm = MeshInstance3D.new()
		h.arm.mesh = meshes["player_arm"]
		h.arm.material_override = arm_mat
		add_child(h.node)
		add_child(h.arm)
		hands.append(h)


func set_color(i: int) -> void:
	color_idx = posmod(i, COLORS.size())
	color = COLORS[color_idx]
	hand_mat.albedo_color = color
	arm_mat.albedo_color = color * 0.8
	arm_mat.albedo_color.a = hand_mat.albedo_color.a


func set_status_look(kind: String) -> void:
	hand_mat.emission_enabled = kind == "it" or kind == "infected"
	if kind == "it":
		hand_mat.emission = Color8(0xff, 0x5a, 0x1f)
	elif kind == "infected":
		hand_mat.emission = Color8(0x3c, 0xff, 0x6a)
	hand_mat.emission_energy_multiplier = 0.55
	var ghosty := kind == "ghost"
	for m in [hand_mat, arm_mat]:
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA if ghosty else BaseMaterial3D.TRANSPARENCY_DISABLED
		m.albedo_color.a = 0.35 if ghosty else 1.0


func setup_hidden(v: bool) -> void:
	visible = v


# ------------------------------------------------------------- helpers
func _update_head() -> void:
	head = rig_pos + rig_basis * head_local


func _target(h: Hand) -> Vector3:
	var out := rig_pos + rig_basis * h.local
	var d := out - head
	var l := d.length()
	if l > MAX_ARM:
		out = head + d * (MAX_ARM / l)
	return out


func _push_hist(now: float) -> void:
	hist_i = (hist_i + 1) % HIST
	hist_t[hist_i] = now
	hist_p[hist_i] = rig_pos
	if hist_n < HIST:
		hist_n += 1


func _estimate_vel(now: float) -> Vector3:
	if hist_n < 2:
		return Vector3.ZERO
	var oldest := hist_i
	for k in range(1, hist_n):
		var j := (hist_i - k + HIST) % HIST
		oldest = j
		if now - hist_t[j] > VEL_WINDOW:
			break
	var dt := hist_t[hist_i] - hist_t[oldest]
	if dt < 1e-3:
		return Vector3.ZERO
	return (hist_p[hist_i] - hist_p[oldest]) / dt


func haptic(h: Hand, amplitude: float, seconds: float) -> void:
	# haptics go through the tracker/action, independent of pose tracking
	if h.controller and h.controller.is_inside_tree():
		h.controller.trigger_haptic_pulse("haptic", 0.0, minf(1.0, amplitude), seconds, 0.0)


func _begin_contact(h: Hand, p: Vector3, n: Vector3, c: int, impact: float, now: float) -> void:
	h.contact = true
	h.anchor = p
	h.normal = n
	h.col = c
	h.lift = 0.0
	if now - h.last_tap > 0.09 and impact > 0.2:
		h.last_tap = now
		var s := clampf(impact / 4.0, 0.12, 1.0)
		sfx.tap(phys.cmat[c], s, p)
		haptic(h, 0.12 + s * 0.6, 0.018 + s * 0.03)
		if impact > 2.2:
			fx.dust(p, phys.cmat[c], s)


func _bounce(n: Vector3, impact: float, now: float, at: Vector3) -> void:
	var strength := clampf(2.5 + impact * 0.92, 6.5, 11.5)
	vel -= n * vel.dot(n)
	vel *= 0.85
	vel += n * strength
	bounce_lock = now + 0.15
	hands[0].contact = false
	hands[1].contact = false
	hist_n = 0
	sfx.boing(at, strength / 11.5)
	for h in hands:
		haptic(h, 0.9, 0.06)
	fx.burst(at, Color8(0xff, 0x7a, 0xb8), 14, 3.5, 0.6)


func _reproject(h: Hand) -> void:
	var d := phys.sdf_one(h.col, h.anchor.x, h.anchor.y, h.anchor.z) - HAND_R
	var n := phys.normal_at(h.col, h.anchor.x, h.anchor.y, h.anchor.z)
	h.anchor -= n * d
	h.normal = n


# ------------------------------------------------------------------ VR
## Godot's OpenXR module exposes the action map's pose actions on the hand
## trackers under shortened names: grip_pose -> "grip", default_pose ->
## "default" (which is the aim pose), aim_pose -> "aim". Read the grip pose
## straight from the tracker, falling back to the others if a runtime lacks it.
const POSE_NAMES := [&"grip", &"default", &"aim"]
const TRACKERS := [&"left_hand", &"right_hand"]


func read_xr() -> void:
	head_local = camera.transform.origin
	head_basis_local = camera.transform.basis
	for h in hands:
		h.tracked = false
		var tracker := XRServer.get_tracker(TRACKERS[h.side]) as XRPositionalTracker
		if tracker == null:
			continue
		for pn in POSE_NAMES:
			var pose := tracker.get_pose(pn)
			if pose != null and pose.has_tracking_data:
				var t := pose.get_adjusted_transform()
				h.basis_local = t.basis
				# the aim pose sits ~6 cm ahead of the grip along the pointing ray
				var off := HAND_OFFSET if pn == &"grip" else HAND_OFFSET + Vector3(0, 0, 0.06)
				h.local = t.origin + t.basis * off
				h.tracked = true
				h.pose_name = pn
				break


func spawn_vr() -> void:
	var f := head_basis_local * Vector3(0, 0, -1)
	yaw = -atan2(-f.x, -f.z)
	rig_basis = Basis(Vector3.UP, yaw)
	rig_pos = spawn_point - rig_basis * head_local
	vel = Vector3.ZERO
	_update_head()
	for h in hands:
		h.contact = false
		h.pos = _target(h)
		h.prev = h.pos
	hist_n = 0
	needs_spawn = false


func respawn() -> void:
	needs_spawn = true
	sfx.whoosh_up()
	if on_respawn.is_valid():
		on_respawn.call()


func snap_turn_by(angle: float) -> void:
	_update_head()
	var keep := head
	yaw += angle
	rig_basis = Basis(Vector3.UP, yaw)
	rig_pos = keep - rig_basis * head_local
	_update_head()
	for h in hands:
		h.contact = false
		h.pos = _target(h)
	hist_n = 0


func handle_input() -> void:
	if not snap_turn:
		return
	var c := hands[1].controller
	if c == null:
		return
	var x := c.get_vector2("primary").x
	if absf(x) < 0.35:
		stick_ready = true
	elif stick_ready and absf(x) > 0.75:
		stick_ready = false
		snap_turn_by(-PI / 4.0 if x > 0.0 else PI / 4.0)
		sfx.click(head)


func update_vr(dt: float, now: float) -> void:
	if needs_spawn:
		# wait for real head tracking before placing the player
		spawn_wait += dt
		if head_local.y < 0.3 and spawn_wait < 1.5:
			origin.transform = Transform3D(rig_basis, rig_pos)
			return
		spawn_vr()
		spawn_wait = 0.0
	for h in hands:
		h.bounce_cool -= dt
		h.prev = h.pos
	_update_head()
	var any_prev := hands[0].contact or hands[1].contact

	# 1. free flight
	if not any_prev:
		vel.y -= G * dt
		rig_pos += vel * dt
		_update_head()

	near = phys.gather(head.x, head.y - 0.3, head.z, MAX_ARM + 0.9 + vel.length() * dt)

	# 2. hands: keep anchored hands stuck, detect new touches
	var bounced := false
	for h in hands:
		var t := _target(h)
		h.target = t
		h.corr = Vector3.ZERO
		if h.contact:
			var v := t - h.anchor
			var n := h.normal
			var vn := v.dot(n)
			if vn > RELEASE or v.length_squared() > UNSTICK * UNSTICK:
				h.contact = false
				continue
			var tv := v - n * vn
			var slip := phys.cslip[h.col]
			if slip > 0.0:
				h.anchor += tv * slip
				_reproject(h)
				tv *= 1.0 - slip
			h.corr = -tv - n * minf(vn, 0.0)
			h.lift = maxf(vn, 0.0)
		elif phys.sphere_cast(near, h.pos, t, HAND_R):
			var impact := -(t - h.pos).dot(phys.res_n) / maxf(dt, 1e-4)
			if phys.cbounce[phys.res_col] > 0.0 and impact > 1.0 and h.bounce_cool <= 0.0 and now >= bounce_lock:
				h.pos = phys.res_pos
				_bounce(phys.res_n, impact, now, h.pos)
				h.bounce_cool = 0.35
				bounced = true
				break
			if now < bounce_lock:
				continue
			var hp := phys.res_pos
			_begin_contact(h, hp, phys.res_n, phys.res_col, impact, now)
			h.corr = hp - t

	# 3. move the body by what the hands demand
	if not bounced:
		var c0 := hands[0].contact
		var c1 := hands[1].contact
		if c0 or c1:
			var corr := hands[0].corr if c0 else hands[1].corr
			if c0 and c1:
				corr = (hands[0].corr + hands[1].corr) * 0.5
			rig_pos += corr
			_update_head()

	# 4. head / body collision
	var any_now := hands[0].contact or hands[1].contact
	if phys.resolve_sphere(near, head, HEAD_R, vel, not any_now):
		rig_pos += phys.rs_pos - head
		_update_head()
		if not any_now:
			vel = phys.rs_vel
			if phys.cbounce[phys.rs_col] > 0.0 and phys.rs_impact > 2.0 and now >= bounce_lock:
				_bounce(phys.rs_n, phys.rs_impact * 0.8, now, head)
				bounced = true
			elif phys.rs_ground:
				var f := maxf(0.0, 1.0 - 9.0 * dt)
				vel.x *= f
				vel.z *= f
				if phys.rs_impact > 2.5 and now - last_land > 0.3:
					last_land = now
					sfx.tap(phys.cmat[phys.rs_col], minf(1.0, phys.rs_impact / 7.0), head)

	# 5. free hands follow the controllers unless something is in the way
	for h in hands:
		if h.contact:
			h.pos = h.anchor + h.normal * h.lift
			continue
		var t := _target(h)
		h.target = t
		if phys.sphere_cast(near, h.pos, t, HAND_R):
			var impact := -(t - h.pos).dot(phys.res_n) / maxf(dt, 1e-4)
			h.pos = phys.res_pos
			if now < bounce_lock:
				continue
			if phys.cbounce[phys.res_col] > 0.0 and impact > 1.0 and h.bounce_cool <= 0.0:
				_bounce(phys.res_n, impact, now, h.pos)
				h.bounce_cool = 0.35
				bounced = true
				continue
			_begin_contact(h, h.pos, phys.res_n, phys.res_col, impact, now)
		else:
			h.pos = t

	# 6. momentum: remember how the body moved while touching; throw on release
	var any_after := hands[0].contact or hands[1].contact
	if any_after:
		if not any_prev:
			hist_n = 0
		_push_hist(now)
		vel = _estimate_vel(now)
	elif any_prev and not bounced:
		var v := _estimate_vel(now)
		if v.length() > VEL_LIMIT:
			vel = v * JUMP_MULT * speed_mult
			var mx := MAX_JUMP * speed_mult
			if vel.length() > mx:
				vel = vel.normalized() * mx
		else:
			vel = Vector3.ZERO
		hist_n = 0
	if vel.length_squared() > MAX_SPEED * MAX_SPEED:
		vel = vel.normalized() * MAX_SPEED

	for h in hands:
		h.vel = (h.pos - h.prev) / maxf(dt, 1e-4)
		h.world_basis = rig_basis * h.basis_local
	head_basis = rig_basis * head_basis_local
	if head.y < -28.0:
		respawn()
	origin.transform = Transform3D(rig_basis, rig_pos)
	update_body()
	update_visuals()


func update_body() -> void:
	body_pos = head - Vector3(0, 0.3, 0)
	sph_pos[0] = head
	sph_pos[1] = body_pos
	sph_pos[2] = hands[0].pos
	sph_pos[3] = hands[1].pos


func update_visuals() -> void:
	var f := head_basis * Vector3(0, 0, -1)
	var hy := atan2(-f.x, -f.z)
	var cyw := cos(hy)
	var syw := sin(hy)
	for h in hands:
		h.node.global_transform = Transform3D(h.world_basis.orthonormalized(), h.pos)
		var s := 1.0 if h.side == 1 else -1.0
		var lx := 0.17 * s
		var lz := 0.07
		var sh := Vector3(head.x + lx * cyw + lz * syw, head.y - 0.26, head.z - lx * syw + lz * cyw)
		var d := h.pos - sh
		var l := d.length()
		if l > 1e-4:
			var q := Quaternion(Vector3.UP, d / l)
			h.arm.global_transform = Transform3D(Basis(q) * Basis.from_scale(Vector3(1, maxf(0.01, l - 0.04), 1)), sh)


func speed() -> float:
	return vel.length()
