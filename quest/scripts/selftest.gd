extends RefCounted
## Headless self-test: replays the scripted locomotion checks and bot
## simulations used to validate the web build, and times GDScript costs.

const DT := 1.0 / 90.0

var m
var P: VRPlayer
var now := 1000.0


func _reset(spawn: Vector3) -> void:
	P.spawn_point = spawn
	P.head_local = Vector3(0, 1.6, 0)
	P.head_basis_local = Basis.IDENTITY
	P.hands[0].local = Vector3(-0.2, 0.9, -0.2)
	P.hands[1].local = Vector3(0.2, 0.9, -0.2)
	for h in P.hands:
		h.basis_local = Basis.IDENTITY
		h.contact = false
	P.needs_spawn = true
	P.vel = Vector3.ZERO
	P.update_vr(DT, now)
	now += DT


func _steps(seconds: float, fn: Callable) -> void:
	var n := int(round(seconds / DT))
	for i in range(n):
		fn.call(i * DT)
		P.update_vr(DT, now)
		now += DT


func _run_path(t: float, phase: float) -> Vector2:
	var period := 0.5
	var u := fposmod(t / period + phase, 1.0)
	if u < 0.5:
		var k := u / 0.5
		return Vector2(-0.55 + 0.75 * k, 0.6)
	var k2 := (u - 0.5) / 0.5
	return Vector2(0.2 - 0.75 * k2, 0.6 + sin(k2 * PI) * 0.3)


func _climb_hand(t: float, phase: float) -> Vector2:
	var u := fposmod(t / 0.9 + phase, 1.0)
	if u < 0.5:
		var k := u / 0.5
		return Vector2(-1.05, 1.9 - 0.85 * k)
	var k2 := (u - 0.5) / 0.5
	if k2 < 0.2:
		return Vector2(-1.05 + (k2 / 0.2) * 0.35, 1.05)
	if k2 < 0.8:
		return Vector2(-0.7, 1.05 + ((k2 - 0.2) / 0.6) * 0.85)
	return Vector2(-0.7 - ((k2 - 0.8) / 0.2) * 0.35, 1.9)


## Feeds controller poses through XR trackers exactly the way Godot's OpenXR
## module publishes them (grip_pose action -> "grip" pose on "left_hand" /
## "right_hand", head on "head"/"default") and checks the in-game hands follow.
func _xr_check() -> Dictionary:
	var conf := XRPose.XR_TRACKING_CONFIDENCE_HIGH
	var head := XRPositionalTracker.new()
	head.name = &"head"
	head.type = XRServer.TRACKER_HEAD
	var trk: Array[XRControllerTracker] = []
	for side in range(2):
		var t := XRControllerTracker.new()
		t.name = &"left_hand" if side == 0 else &"right_hand"
		t.type = XRServer.TRACKER_CONTROLLER
		t.hand = XRPositionalTracker.TRACKER_HAND_LEFT if side == 0 else XRPositionalTracker.TRACKER_HAND_RIGHT
		trk.append(t)
	XRServer.add_tracker(head)
	for t in trk:
		XRServer.add_tracker(t)
	var res := {}
	# phase 1: hands waving above the head (never touching anything)
	P.spawn_point = Vector3(2, 1.5, 9)
	P.needs_spawn = true
	P.vel = Vector3.ZERO
	var max_err := 0.0
	var max_ctrl_err := 0.0
	var tracked_frames := 0
	var moved := 0.0
	var first := Vector3.ZERO
	for i in range(240):
		var t := i * DT
		head.set_pose(&"default", Transform3D(Basis.IDENTITY, Vector3(0, 1.6, 0)), Vector3.ZERO, Vector3.ZERO, conf)
		var lp := Vector3(-0.3 + 0.12 * sin(t * 6.0), 1.85 + 0.1 * cos(t * 6.0), -0.3)
		var rp := Vector3(0.3 + 0.12 * cos(t * 5.0), 1.9 + 0.08 * sin(t * 5.0), -0.35)
		var lb := Basis.from_euler(Vector3(0.4 * sin(t * 2.0), 0.3, 0.2))
		var rb := Basis.from_euler(Vector3(-0.3, -0.25 * cos(t * 2.0), -0.1))
		trk[0].set_pose(&"grip", Transform3D(lb, lp), Vector3.ZERO, Vector3.ZERO, conf)
		trk[1].set_pose(&"grip", Transform3D(rb, rp), Vector3.ZERO, Vector3.ZERO, conf)
		P.read_xr()
		P.update_vr(DT, now)
		now += DT
		if i == 60:
			first = P.hands[1].pos
		if i > 60:
			moved = maxf(moved, P.hands[1].pos.distance_to(first))
			var poses := [Transform3D(lb, lp), Transform3D(rb, rp)]
			for s in range(2):
				var h: VRPlayer.Hand = P.hands[s]
				var pose: Transform3D = poses[s]
				if h.tracked:
					tracked_frames += 1
				if not h.contact:
					var expect := P.rig_pos + P.rig_basis * (pose.origin + pose.basis * VRPlayer.HAND_OFFSET)
					max_err = maxf(max_err, h.pos.distance_to(expect))
				var c: XRController3D = m.controllers[s]
				max_ctrl_err = maxf(max_ctrl_err, c.transform.origin.distance_to(pose.origin))
	res["hands_tracked_frames"] = tracked_frames
	res["pose_used"] = [String(P.hands[0].pose_name), String(P.hands[1].pose_name)]
	res["max_hand_error_m"] = snappedf(max_err, 0.0001)
	res["right_hand_travel_m"] = snappedf(moved, 0.01)
	res["controller_nodes_tracking"] = [m.controllers[0].get_has_tracking_data(), m.controllers[1].get_has_tracking_data()]
	res["max_controller_node_error_m"] = snappedf(max_ctrl_err, 0.0001)
	res["camera_follows_head"] = m.camera.transform.origin.distance_to(Vector3(0, 1.6, 0)) < 0.001
	# phase 2: run using nothing but controller poses
	P.spawn_point = Vector3(2, 1.5, 9)
	P.needs_spawn = true
	P.vel = Vector3.ZERO
	for i in range(90):
		head.set_pose(&"default", Transform3D(Basis.IDENTITY, Vector3(0, 1.6, 0)), Vector3.ZERO, Vector3.ZERO, conf)
		trk[0].set_pose(&"grip", Transform3D(Basis.IDENTITY, Vector3(-0.22, 0.6, -0.2)), Vector3.ZERO, Vector3.ZERO, conf)
		trk[1].set_pose(&"grip", Transform3D(Basis.IDENTITY, Vector3(0.22, 0.6, -0.2)), Vector3.ZERO, Vector3.ZERO, conf)
		P.read_xr()
		P.update_vr(DT, now)
		now += DT
	var start := P.head
	for i in range(270):
		var t := i * DT
		var a := _run_path(t, 0.0)
		var b := _run_path(t, 0.5)
		head.set_pose(&"default", Transform3D(Basis.IDENTITY, Vector3(0, 1.6, 0)), Vector3.ZERO, Vector3.ZERO, conf)
		trk[0].set_pose(&"grip", Transform3D(Basis.IDENTITY, Vector3(-0.22, a.y, a.x)), Vector3.ZERO, Vector3.ZERO, conf)
		trk[1].set_pose(&"grip", Transform3D(Basis.IDENTITY, Vector3(0.22, b.y, b.x)), Vector3.ZERO, Vector3.ZERO, conf)
		P.read_xr()
		P.update_vr(DT, now)
		now += DT
	res["run_via_controllers_dz"] = snappedf(P.head.z - start.z, 0.01)
	# phase 3: a tracker that only reports the aim/default pose still drives the hand
	trk[0].invalidate_pose(&"grip")
	trk[0].set_pose(&"default", Transform3D(Basis.IDENTITY, Vector3(-0.3, 1.9, -0.3)), Vector3.ZERO, Vector3.ZERO, conf)
	P.read_xr()
	res["fallback_pose"] = String(P.hands[0].pose_name)
	res["fallback_tracked"] = P.hands[0].tracked
	XRServer.remove_tracker(head)
	for t in trk:
		XRServer.remove_tracker(t)
	return res


func run(main) -> void:
	m = main
	P = m.player
	var out := {}
	out["load_ms"] = m.level.load_ms
	out["colliders"] = m.level.phys.count
	out["nav_nodes"] = m.level.nav.n
	out["nav_edges"] = m.level.nav.e_to.size()

	# 1. idle
	_reset(Vector3(2, 1.5, 9))
	_steps(2.0, func(_t): pass)
	out["idle"] = {"headY": snappedf(P.head.y, 0.001), "contacts": [P.hands[0].contact, P.hands[1].contact], "vel": snappedf(P.vel.length(), 0.001)}

	# 2. run toward -Z
	_reset(Vector3(2, 1.5, 9))
	_steps(1.0, func(_t): pass)
	var start := P.head
	var stats := {"max": 0.0}
	_steps(3.0, func(t):
		var a := _run_path(t, 0.0)
		var b := _run_path(t, 0.5)
		P.hands[0].local = Vector3(-0.22, a.y, a.x)
		P.hands[1].local = Vector3(0.22, b.y, b.x)
		stats["max"] = maxf(stats["max"], Vector2(P.vel.x, P.vel.z).length()))
	out["run"] = {"dz": snappedf(P.head.z - start.z, 0.01), "dx": snappedf(P.head.x - start.x, 0.01), "maxSpeed": snappedf(stats["max"], 0.01)}

	# 3. jump: shove down, then yank up
	_reset(Vector3(2, 1.5, 9))
	P.hands[0].local = Vector3(-0.22, 0.75, -0.25)
	P.hands[1].local = Vector3(0.22, 0.75, -0.25)
	_steps(1.0, func(_t): pass)
	var y0 := P.head.y
	_steps(0.12, func(t):
		var k := minf(1.0, t / 0.12)
		P.hands[0].local.y = 0.75 - 0.35 * k
		P.hands[1].local.y = 0.75 - 0.35 * k)
	_steps(0.05, func(t):
		var k := minf(1.0, t / 0.05)
		P.hands[0].local.y = 0.4 + 0.5 * k
		P.hands[1].local.y = 0.4 + 0.5 * k)
	var launch_vy := P.vel.y
	var jstats := {"peak": P.head.y}
	_steps(1.2, func(_t): jstats["peak"] = maxf(jstats["peak"], P.head.y))
	out["jump"] = {"launchVy": snappedf(launch_vy, 0.01), "rise": snappedf(jstats["peak"] - y0, 0.01)}

	# 4. climb the Great Shroom stem hand over hand
	_reset(Vector3(0, 1.2, -0.85))
	_steps(1.0, func(_t): pass)
	var cy0 := P.head.y
	var cstats := {"max": cy0}
	_steps(5.0, func(t):
		var a := _climb_hand(t, 0.0)
		var b := _climb_hand(t, 0.5)
		P.hands[0].local = Vector3(-0.25, a.y, a.x)
		P.hands[1].local = Vector3(0.25, b.y, b.x)
		cstats["max"] = maxf(cstats["max"], P.head.y))
	out["climb"] = {"startY": snappedf(cy0, 0.01), "maxY": snappedf(cstats["max"], 0.01)}

	# 5. bounce on the pink cap at (-5.8, 5.2)
	_reset(Vector3(-5.8, 3.6, 5.2))
	var bstats := {"up": 0.0, "max": -1e9}
	_steps(2.5, func(_t):
		bstats["up"] = maxf(bstats["up"], P.vel.y)
		bstats["max"] = maxf(bstats["max"], P.head.y))
	out["bounce"] = {"maxUpVel": snappedf(bstats["up"], 0.01), "maxY": snappedf(bstats["max"], 0.01)}

	# 6. head rest with hands raised
	_reset(Vector3(10, 3, 14))
	P.hands[0].local = Vector3(-0.3, 2.0, 0)
	P.hands[1].local = Vector3(0.3, 2.0, 0)
	_steps(2.5, func(_t): pass)
	out["headRest"] = {"headY": snappedf(P.head.y, 0.001)}

	# 7. timing: one player update while running
	_reset(Vector3(2, 1.5, 9))
	var t0 := Time.get_ticks_usec()
	_steps(3.0, func(t):
		var a := _run_path(t, 0.0)
		var b := _run_path(t, 0.5)
		P.hands[0].local = Vector3(-0.22, a.y, a.x)
		P.hands[1].local = Vector3(0.22, b.y, b.x))
	out["ms_per_player_update"] = snappedf((Time.get_ticks_usec() - t0) / 1000.0 / 270.0, 0.0001)
	print("SELFTEST_LOCO ", JSON.stringify(out))
	print("SELFTEST_XR ", JSON.stringify(_xr_check()))

	# 8. bot-only rounds of every mode
	var g: Game = m.game
	var sim := {}
	var dt := 1.0 / 60.0
	var frames := 0
	var tb := Time.get_ticks_usec()
	var worst := 0.0
	for mi in range(Game.MODES.size()):
		g.mode_idx = mi
		g.stop_round(true)
		g.start_countdown()
		var jumps := 0
		var max_y := 0.0
		var name: String = Game.MODES[mi]["id"]
		var steps := int((float(Game.MODES[mi]["time"]) + 4.0) / dt)
		var done := false
		for s in range(steps):
			var f0 := Time.get_ticks_usec()
			Bot.replans_left = 2
			for b in m.bots:
				var was: bool = b.jumping
				b.update(dt, now)
				if b.jumping and not was:
					jumps += 1
				if b.active and b.alive:
					max_y = maxf(max_y, b.pos.y)
			Bot.separate(m.bots)
			g.update(dt, now)
			worst = maxf(worst, (Time.get_ticks_usec() - f0) / 1000.0)
			now += dt
			frames += 1
			if g.state == "results" and not done:
				done = true
				var res := []
				for r in g.results:
					res.append("%s:%s" % [r["name"], r["stat"]])
				sim[name] = {"elapsed": snappedf(g.elapsed, 0.1), "results": res, "feed": g.feed.duplicate(), "jumps": jumps, "maxY": snappedf(max_y, 0.1)}
		if not done:
			sim[name] = {"notFinished": true, "state": g.state, "feed": g.feed.duplicate()}
	sim["ms_per_bot_frame"] = snappedf((Time.get_ticks_usec() - tb) / 1000.0 / frames, 0.001)
	sim["worst_frame_ms"] = snappedf(worst, 0.01)
	print("SELFTEST_SIM ", JSON.stringify(sim))
	g.stop_round(true)
