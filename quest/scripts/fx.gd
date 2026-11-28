class_name FX
extends Node3D
## Pooled one-shot particle bursts (tags, bounces, dust) and drifting spores.

const DUST := {"grass": Color("#9fe07a"), "wood": Color("#d9a56a"), "stone": Color("#c9c3e0"),
	"cap": Color("#f3d6b0"), "leaf": Color("#7fdc7a"), "crystal": Color("#9ff4ff"),
	"cloud": Color("#ffffff"), "shroom": Color("#ff8cc6")}

var pool: Array[CPUParticles3D] = []
var idx := 0
var dot_mat: StandardMaterial3D


func setup() -> void:
	var grad := Gradient.new()
	grad.set_color(0, Color(1, 1, 1, 1))
	grad.set_color(1, Color(1, 1, 1, 0))
	grad.add_point(0.35, Color(1, 1, 1, 0.7))
	var tex := GradientTexture2D.new()
	tex.gradient = grad
	tex.fill = GradientTexture2D.FILL_RADIAL
	tex.fill_from = Vector2(0.5, 0.5)
	tex.fill_to = Vector2(1.0, 0.5)
	tex.width = 64
	tex.height = 64
	dot_mat = StandardMaterial3D.new()
	dot_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	dot_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	dot_mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	dot_mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	dot_mat.vertex_color_use_as_albedo = true
	dot_mat.albedo_texture = tex
	dot_mat.disable_receive_shadows = true
	var quad := QuadMesh.new()
	quad.size = Vector2(0.11, 0.11)
	quad.material = dot_mat
	var fade := Gradient.new()
	fade.set_color(0, Color(1, 1, 1, 1))
	fade.set_color(1, Color(0, 0, 0, 1))
	for i in range(14):
		var p := CPUParticles3D.new()
		p.emitting = false
		p.one_shot = true
		p.explosiveness = 1.0
		p.local_coords = false
		p.mesh = quad
		p.direction = Vector3.UP
		p.spread = 180.0
		p.gravity = Vector3(0, -4, 0)
		p.damping_min = 1.0
		p.damping_max = 2.0
		p.color_ramp = fade
		p.scale_amount_min = 0.7
		p.scale_amount_max = 1.3
		add_child(p)
		pool.append(p)
	# ambient spores floating over the meadow
	var spores := CPUParticles3D.new()
	spores.amount = 220
	spores.lifetime = 14.0
	spores.preprocess = 14.0
	spores.local_coords = false
	spores.mesh = quad
	spores.emission_shape = CPUParticles3D.EMISSION_SHAPE_BOX
	spores.emission_box_extents = Vector3(30, 8, 30)
	spores.position = Vector3(0, 8.6, 0)
	spores.direction = Vector3.UP
	spores.spread = 180.0
	spores.gravity = Vector3.ZERO
	spores.initial_velocity_min = 0.05
	spores.initial_velocity_max = 0.3
	spores.scale_amount_min = 0.4
	spores.scale_amount_max = 0.8
	var sg := Gradient.new()
	sg.set_color(0, Color(0, 0, 0, 1))
	sg.set_color(1, Color(0, 0, 0, 1))
	sg.add_point(0.2, Color(0.6, 0.58, 0.42, 1))
	sg.add_point(0.8, Color(0.55, 0.6, 0.5, 1))
	spores.color_ramp = sg
	add_child(spores)


func burst(at: Vector3, color: Color, count := 12, speed := 3.0, life := 0.6) -> void:
	var p := pool[idx]
	idx = (idx + 1) % pool.size()
	p.global_position = at
	p.amount = maxi(1, count)
	p.lifetime = maxf(0.1, life)
	p.initial_velocity_min = speed * 0.4
	p.initial_velocity_max = speed
	p.color = color
	p.restart()
	p.emitting = true


func dust(at: Vector3, mat: String, s: float) -> void:
	burst(at, DUST.get(mat, Color.WHITE), int(round(3 + s * 6)), 1.2 + s * 1.5, 0.45)
