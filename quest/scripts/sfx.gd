class_name Sfx
extends Node
## Plays the pre-rendered sound effects (exported from the web build's
## WebAudio synth) through pooled 3D/2D players, plus wind ambience.

const NAMES := ["tap_grass", "tap_wood", "tap_stone", "tap_cap", "tap_leaf", "tap_crystal", "tap_cloud",
	"boing", "chirp", "tag_made", "tag_got", "tag_other", "orb", "sizzle", "click", "beep", "beep_go",
	"horn", "fanfare_win", "fanfare_lose", "whoosh", "whoosh_up", "bird0", "bird1", "bird2", "loop_wind", "loop_rush"]

var streams := {}
var pool3d: Array[AudioStreamPlayer3D] = []
var pool2d: Array[AudioStreamPlayer] = []
var i3 := 0
var i2 := 0
var wind: AudioStreamPlayer
var rush: AudioStreamPlayer
var next_bird := 4.0
var clock := 0.0
var enabled := true


func setup() -> void:
	for n in NAMES:
		var s = load("res://data/sfx/%s.wav" % n)
		if s:
			streams[n] = s
	for i in range(28):
		var p := AudioStreamPlayer3D.new()
		p.unit_size = 2.5
		p.max_distance = 70.0
		p.attenuation_model = AudioStreamPlayer3D.ATTENUATION_INVERSE_DISTANCE
		p.panning_strength = 1.0
		add_child(p)
		pool3d.append(p)
	for i in range(8):
		var p := AudioStreamPlayer.new()
		add_child(p)
		pool2d.append(p)
	wind = _looper("loop_wind", -21.0)
	rush = _looper("loop_rush", -80.0)


func _looper(n: String, db: float) -> AudioStreamPlayer:
	var p := AudioStreamPlayer.new()
	add_child(p)
	if streams.has(n):
		var s: AudioStreamWAV = (streams[n] as AudioStreamWAV).duplicate()
		s.loop_mode = AudioStreamWAV.LOOP_FORWARD
		s.loop_begin = 0
		s.loop_end = int(s.get_length() * s.mix_rate)
		p.stream = s
		p.volume_db = db
		p.play()
	return p


func _play3d(n: String, at: Vector3, gain: float, pitch := 1.0) -> void:
	if not enabled or not streams.has(n) or gain <= 0.001:
		return
	var p := pool3d[i3]
	i3 = (i3 + 1) % pool3d.size()
	p.stream = streams[n]
	p.global_position = at
	p.volume_db = linear_to_db(gain)
	p.pitch_scale = pitch
	p.play()


func _play2d(n: String, gain: float, pitch := 1.0) -> void:
	if not enabled or not streams.has(n):
		return
	var p := pool2d[i2]
	i2 = (i2 + 1) % pool2d.size()
	p.stream = streams[n]
	p.volume_db = linear_to_db(gain)
	p.pitch_scale = pitch
	p.play()


func _r() -> float:
	return randf_range(0.9, 1.1)


func tap(mat: String, s: float, at: Vector3) -> void:
	var n := "tap_" + mat
	if mat == "shroom":
		boing(at, s)
		return
	if not streams.has(n):
		n = "tap_grass"
	_play3d(n, at, clampf(s, 0.08, 1.0) * 0.8, _r())


func boing(at: Vector3, s := 1.0) -> void:
	_play3d("boing", at, clampf(s, 0.2, 1.0) * 0.75, randf_range(0.92, 1.08))


func chirp(at: Vector3, pitch := 1.0) -> void:
	_play3d("chirp", at, 0.45, pitch)


func tag(kind: String, at := Vector3.ZERO) -> void:
	if kind == "made":
		_play2d("tag_made", 0.45)
	elif kind == "got":
		_play2d("tag_got", 0.55)
	else:
		_play3d("tag_other", at, 0.6)


func orb(at: Vector3, mine: bool) -> void:
	if mine:
		_play2d("orb", 0.5)
	else:
		_play3d("orb", at, 0.55)


func sizzle(at: Vector3) -> void:
	_play3d("sizzle", at, 0.8)


func click(at: Vector3) -> void:
	_play3d("click", at, 0.5)


func beep(go: bool) -> void:
	_play2d("beep_go" if go else "beep", 0.35)


func horn() -> void:
	_play2d("horn", 0.35)


func fanfare(win: bool) -> void:
	_play2d("fanfare_win" if win else "fanfare_lose", 0.45)


func whoosh_up() -> void:
	_play2d("whoosh_up", 0.4)


func update(dt: float, speed: float, listener: Vector3) -> void:
	clock += dt
	if rush and rush.stream:
		var k := clampf((speed - 2.5) / 9.0, 0.0, 1.0)
		var target := linear_to_db(maxf(k * 0.32, 0.0001))
		rush.volume_db = lerpf(rush.volume_db, target, 1.0 - exp(-dt / 0.08))
		rush.pitch_scale = 0.8 + k * 0.6
	if clock > next_bird:
		next_bird = clock + randf_range(3.0, 9.0)
		var a := randf() * TAU
		var d := randf_range(18.0, 43.0)
		_play3d("bird%d" % (randi() % 3), listener + Vector3(cos(a) * d, randf_range(6.0, 16.0), sin(a) * d), 0.5, randf_range(0.85, 1.2))
