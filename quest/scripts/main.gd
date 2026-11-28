extends Node3D
## Shroom Scramble for Meta Quest: boots OpenXR, builds the level, player,
## bots, game and UI, and runs the frame loop.
## Test hooks (desktop, XR off): -- --selftest | -- --shot=out.png --view=NAME

var level: Level
var player: VRPlayer
var bots: Array = []
var game: Game
var ui: GameUI
var sfx: Sfx
var fx: FX
var origin: XROrigin3D
var camera: XRCamera3D
var controllers: Array = []
var xr_interface: XRInterface
var xr_on := false
var mode := "attract"
var clock := 0.0
var args := PackedStringArray()
var shot_path := ""
var shot_view := ""
var shot_frames := 0
var sim_step: Callable
var fonts := {}
var keep_head := false
var last_head := Vector3.ZERO


func _ready() -> void:
	args = OS.get_cmdline_user_args()
	xr_interface = XRServer.find_interface("OpenXR")
	if xr_interface and xr_interface.is_initialized():
		get_viewport().use_xr = true
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
		xr_on = true
		xr_interface.connect("pose_recentered", _on_recentered)
	_build()
	if "--selftest" in args:
		var st = load("res://scripts/selftest.gd").new()
		await st.run(self)
		get_tree().quit()
		return
	for a in args:
		if a.begins_with("--shot="):
			shot_path = a.substr(7)
		elif a.begins_with("--view="):
			shot_view = a.substr(7)
	if xr_on:
		mode = "vr"
		player.visible = true
		game.set_human(true)
		get_tree().create_timer(2.5).timeout.connect(_hello)
	else:
		mode = "attract"
		player.visible = false
	if shot_path != "":
		_setup_shot()


func _hello() -> void:
	ui.toast("Punch START to play!", Color("#ffd166"), true)


func _build() -> void:
	level = Level.new()
	add_child(level)
	level.build()
	sfx = Sfx.new()
	add_child(sfx)
	sfx.setup()
	fx = FX.new()
	add_child(fx)
	fx.setup()
	var base: FontFile = load("res://data/fonts/Fredoka.ttf")
	# the variable font defaults to Light; the weight axis only takes its numeric OpenType tag
	var wght := TextServerManager.get_primary_interface().name_to_tag("wght")
	for pair in [["regular", 400], ["semibold", 600], ["bold", 700]]:
		var fv := FontVariation.new()
		fv.base_font = base
		fv.variation_opentype = {wght: pair[1]}
		fonts[pair[0]] = fv

	origin = XROrigin3D.new()
	add_child(origin)
	camera = XRCamera3D.new()
	camera.near = 0.04
	camera.far = 900.0
	camera.fov = 70.0
	origin.add_child(camera)
	camera.current = true
	for side in range(2):
		var c := XRController3D.new()
		c.tracker = &"left_hand" if side == 0 else &"right_hand"
		c.pose = &"grip" # Godot renames the grip_pose action to "grip" on the tracker
		origin.add_child(c)
		controllers.append(c)

	player = VRPlayer.new()
	add_child(player)
	player.setup(level.phys, sfx, fx, origin, camera, controllers, level.meshes)
	player.spawn_point = level.spawn
	player.on_respawn = _on_player_respawn

	var shared := level.meshes.duplicate()
	shared["vc_mat"] = Level.lambert(Color.WHITE, true)
	shared["star_mat"] = Level.unshaded(Color("#ffe066"))
	shared["font_semibold"] = fonts["semibold"]
	var pm := PlaneMesh.new()
	pm.size = Vector2(0.84, 0.84)
	shared["shadow_mesh"] = pm
	var g := Gradient.new()
	g.set_color(0, Color(0, 0, 0, 0.55))
	g.set_color(1, Color(0, 0, 0, 0))
	var gt := GradientTexture2D.new()
	gt.gradient = g
	gt.fill = GradientTexture2D.FILL_RADIAL
	gt.fill_from = Vector2(0.5, 0.5)
	gt.fill_to = Vector2(1.0, 0.5)
	gt.width = 64
	gt.height = 64
	var sm := StandardMaterial3D.new()
	sm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	sm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	sm.albedo_texture = gt
	sm.render_priority = 1
	shared["shadow_mat"] = sm
	for i in range(Bot.PROFILES.size()):
		var b := Bot.new()
		level.add_child(b)
		b.setup(Bot.PROFILES[i], level.phys, level.nav, sfx, fx, shared, level)
		b.place_at(level.nav.random_good())
		bots.append(b)

	game = Game.new()
	add_child(game)
	game.setup(player, bots, level.nav, level, sfx, fx)
	ui = GameUI.new()
	add_child(ui)
	ui.setup(level.data, game, player, sfx, fonts)


func _on_player_respawn() -> void:
	ui.toast("Whoops! Back to the meadow", Color("#7bdff2"))


func _on_recentered() -> void:
	# keep the player's head where it was in the world after a recenter
	last_head = player.head
	keep_head = true
	XRServer.center_on_hmd(XRServer.RESET_BUT_KEEP_TILT, true)


func _attract(now: float) -> void:
	origin.transform = Transform3D.IDENTITY
	var a := now * 0.045 + 0.6
	var p := Vector3(sin(a) * 31.0, 10.5 + sin(now * 0.13) * 2.5, cos(a) * 31.0)
	camera.transform = Transform3D(Basis.looking_at(Vector3(0, 3.5, -1) - p, Vector3.UP), p)


func step(dt: float, now: float) -> void:
	var view_pos: Vector3
	var view_basis: Basis
	if mode == "vr":
		player.read_xr()
		if keep_head and not player.needs_spawn:
			keep_head = false
			player.rig_pos = last_head - player.rig_basis * player.head_local
			for h in player.hands:
				h.contact = false
		player.handle_input()
		player.update_vr(dt, now)
		view_pos = player.head
		view_basis = player.head_basis
	elif mode == "vrsim":
		if sim_step.is_valid():
			sim_step.call(now, dt)
		player.update_vr(dt, now)
		camera.transform = Transform3D(player.head_basis_local, player.head_local)
		view_pos = player.head
		view_basis = player.head_basis
	elif mode == "freecam":
		view_pos = camera.global_position
		view_basis = camera.global_transform.basis
	else:
		_attract(now)
		view_pos = camera.global_position
		view_basis = camera.global_transform.basis
	Bot.replans_left = 2
	for b in bots:
		b.update(dt, now)
	Bot.separate(bots)
	game.update(dt, now)
	ui.update(dt, now, mode == "vr" or mode == "vrsim", view_pos, view_basis)
	level.follow_camera(view_pos)
	sfx.update(dt, player.speed() if mode == "vr" else 0.0, view_pos)


func _process(delta: float) -> void:
	if "--selftest" in args:
		return
	var dt := clampf(delta, 1.0 / 240.0, 1.0 / 20.0)
	clock += dt
	step(dt, clock)
	if shot_path != "":
		_shot_tick()


# ------------------------------------------------------- screenshot hooks
func _fast_forward(seconds: float) -> void:
	var dt := 1.0 / 60.0
	for i in range(int(seconds * 60.0)):
		clock += dt
		Bot.replans_left = 2
		for b in bots:
			b.update(dt, clock)
		Bot.separate(bots)
		game.update(dt, clock)


func _look(from: Vector3, at: Vector3) -> void:
	origin.transform = Transform3D.IDENTITY
	camera.transform = Transform3D(Basis.looking_at(at - from, Vector3.UP), from)


func _setup_shot() -> void:
	sfx.enabled = false
	match shot_view:
		"spawn":
			mode = "freecam"
			_look(Vector3(1.5, 2.2, 19.0), Vector3(-1.0, 3.0, 4.0))
		"bots":
			mode = "freecam"
			game.mode_idx = 0
			game.start_countdown()
			_fast_forward(8.0)
			var it_bot = bots[0]
			for b in bots:
				if b.it:
					it_bot = b
			_look(it_bot.pos + Vector3(3.2, 1.1, 3.2), it_bot.pos + Vector3(0, 0.2, 0))
		"lava":
			mode = "freecam"
			game.mode_idx = 3
			game.start_countdown()
			_fast_forward(50.0)
			_look(Vector3(18.0, 9.0, 22.0), Vector3(0.0, 2.0, -2.0))
		"vr":
			mode = "vrsim"
			player.visible = true
			game.set_human(true)
			player.spawn_point = Vector3(-1.0, 1.5, 15.6)
			player.head_local = Vector3(0, 1.6, 0)
			player.head_basis_local = Basis.IDENTITY
			player.needs_spawn = true
			var look := Basis.from_euler(Vector3(-0.32, 0.38, 0))
			sim_step = func(t: float, _dt: float) -> void:
				if t > 0.6:
					player.head_basis_local = look
				player.hands[0].local = Vector3(-0.25, 0.85, -0.3)
				player.hands[1].local = Vector3(0.12, 1.15, -0.55)
				player.hands[0].basis_local = look
				player.hands[1].basis_local = look
		_:
			mode = "attract"


func _shot_tick() -> void:
	shot_frames += 1
	if shot_frames == 45:
		await RenderingServer.frame_post_draw
		var img := get_viewport().get_texture().get_image()
		img.save_png(shot_path)
		print("saved ", shot_path)
		get_tree().quit()
