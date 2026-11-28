class_name Level
extends Node3D
## Loads the exported level (geometry, colliders, nav graph) and builds the
## sky, lights, fog, cloud sea and lava.

const SKY_SHADER := """
shader_type spatial;
render_mode unshaded, cull_front, depth_draw_never, fog_disabled, shadows_disabled;
uniform vec3 top_col : source_color = vec3(0.31, 0.525, 0.91);
uniform vec3 horizon_col : source_color = vec3(1.0, 0.784, 0.635);
uniform vec3 bottom_col : source_color = vec3(0.851, 0.608, 0.776);
uniform vec3 sun_col : source_color = vec3(1.0, 0.941, 0.784);
uniform vec3 sun_dir = vec3(-0.62, 0.42, 0.66);
varying vec3 dir;
void vertex() { dir = VERTEX; }
void fragment() {
	vec3 d = normalize(dir);
	float h = d.y;
	vec3 c = h > 0.0 ? mix(horizon_col, top_col, pow(min(h * 1.4, 1.0), 0.55)) : mix(horizon_col, bottom_col, pow(min(-h * 2.0, 1.0), 0.6));
	float s = max(dot(d, normalize(sun_dir)), 0.0);
	c += sun_col * (pow(s, 900.0) * 4.0 + pow(s, 24.0) * 0.45 + pow(s, 4.0) * 0.12);
	ALBEDO = c;
}
"""

const LAVA_SHADER := """
shader_type spatial;
render_mode unshaded, fog_disabled, shadows_disabled;
uniform vec3 col_a : source_color = vec3(1.0, 0.29, 0.07);
uniform vec3 col_b : source_color = vec3(1.0, 0.827, 0.302);
uniform vec3 col_c : source_color = vec3(0.525, 0.078, 0.0);
varying vec2 w;
float h(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float n(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(h(i), h(i + vec2(1.0, 0.0)), u.x), mix(h(i + vec2(0.0, 1.0)), h(i + vec2(1.0, 1.0)), u.x), u.y);
}
void vertex() { w = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xz; }
void fragment() {
	vec2 p = w * 0.22;
	float t = TIME * 0.3;
	float a = n(p + vec2(t, -t * 0.7)) * 0.6 + n(p * 2.3 - vec2(t * 1.3, t)) * 0.4;
	float crack = 1.0 - smoothstep(0.0, 0.06, abs(a - 0.5));
	vec3 c = mix(col_c, col_a, smoothstep(0.2, 0.75, a));
	c = mix(c, col_b, clamp(crack * 0.9 + pow(a, 5.0), 0.0, 1.0));
	ALBEDO = c;
}
"""

var data: Dictionary
var meshes := {}
var phys := Phys.new()
var nav := Nav.new()
var spawn := Vector3(0, 1.5, 17.5)
var sun_dir := Vector3(-0.62, 0.42, 0.66).normalized()
var env: Environment
var sky: MeshInstance3D
var lava: MeshInstance3D
var lava_y := -40.0
var ground_fill: DirectionalLight3D
var load_ms := 0


func build() -> void:
	var t0 := Time.get_ticks_msec()
	data = JSON.parse_string(FileAccess.get_file_as_string("res://data/level.json"))
	phys.load_level(data)
	nav.load_level(data)
	var sp: Array = data["spawn"]
	spawn = Vector3(sp[0], sp[1], sp[2])
	var sd: Array = data["sunDir"]
	sun_dir = Vector3(sd[0], sd[1], sd[2]).normalized()
	_load_meshes()
	_build_static()
	_build_environment()
	load_ms = Time.get_ticks_msec() - t0


func _load_meshes() -> void:
	var header: Array = JSON.parse_string(FileAccess.get_file_as_string("res://data/meshes.json"))
	var bytes := FileAccess.get_file_as_bytes("res://data/meshes.bin")
	for h in header:
		var cnt := int(h["n"])
		var off := int(h["off"])
		var pa := bytes.slice(off, off + cnt * 12).to_float32_array()
		var na := bytes.slice(off + cnt * 12, off + cnt * 24).to_float32_array()
		var ca := bytes.slice(off + cnt * 24, off + cnt * 36).to_float32_array()
		var verts := PackedVector3Array()
		var norms := PackedVector3Array()
		var cols := PackedColorArray()
		verts.resize(cnt)
		norms.resize(cnt)
		cols.resize(cnt)
		for i in range(cnt):
			var j := i * 3
			verts[i] = Vector3(pa[j], pa[j + 1], pa[j + 2])
			norms[i] = Vector3(na[j], na[j + 1], na[j + 2])
			cols[i] = Color(ca[j], ca[j + 1], ca[j + 2])
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = verts
		arrays[Mesh.ARRAY_NORMAL] = norms
		arrays[Mesh.ARRAY_COLOR] = cols
		var am := ArrayMesh.new()
		am.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		meshes[String(h["name"])] = am


static func lambert(color := Color.WHITE, vertex_colors := false) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = color
	m.vertex_color_use_as_albedo = vertex_colors
	m.roughness = 1.0
	m.metallic_specular = 0.0
	m.specular_mode = BaseMaterial3D.SPECULAR_DISABLED
	m.diffuse_mode = BaseMaterial3D.DIFFUSE_LAMBERT
	return m


static func unshaded(color: Color) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = color
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	return m


func _build_static() -> void:
	var solid := lambert(Color.WHITE, true)
	var glow := lambert(Color.WHITE, true)
	glow.emission_enabled = true
	glow.emission = Color8(0x4a, 0x4a, 0x70)
	var cloud := lambert(Color.WHITE, true)
	cloud.emission_enabled = true
	cloud.emission = Color8(0x6a, 0x5a, 0x78)
	for pair in [["world_solid", solid], ["world_glow", glow], ["world_cloud", cloud]]:
		var mi := MeshInstance3D.new()
		mi.mesh = meshes[pair[0]]
		mi.material_override = pair[1]
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		mi.name = pair[0]
		add_child(mi)


func _build_environment() -> void:
	var we := WorldEnvironment.new()
	env = Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color8(0xf7, 0xc9, 0xad)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color8(0xd9, 0xd4, 0xe0)
	env.ambient_light_energy = 0.5
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_DEPTH
	env.fog_light_color = Color8(0xf7, 0xc9, 0xad)
	env.fog_light_energy = 1.0
	env.fog_density = 1.0
	env.fog_depth_begin = 55.0
	env.fog_depth_end = 240.0
	env.fog_depth_curve = 1.0
	env.fog_sky_affect = 0.0
	we.environment = env
	add_child(we)

	var sun := DirectionalLight3D.new()
	sun.light_color = Color8(0xff, 0xe2, 0xbf)
	sun.light_energy = 1.15
	sun.basis = Basis.looking_at(-sun_dir, Vector3.UP)
	add_child(sun)
	var sky_fill := DirectionalLight3D.new()
	sky_fill.light_color = Color8(0xd6, 0xec, 0xff)
	sky_fill.light_energy = 0.45
	sky_fill.basis = Basis.looking_at(Vector3(0.25, -1.0, 0.15).normalized(), Vector3.FORWARD)
	add_child(sky_fill)
	ground_fill = DirectionalLight3D.new()
	ground_fill.light_color = Color8(0x9a, 0x70, 0x55)
	ground_fill.light_energy = 0.3
	ground_fill.basis = Basis.looking_at(Vector3(-0.1, 1.0, 0.05).normalized(), Vector3.FORWARD)
	add_child(ground_fill)

	sky = MeshInstance3D.new()
	var sm := SphereMesh.new()
	sm.radius = 420.0
	sm.height = 840.0
	sm.radial_segments = 32
	sm.rings = 16
	sky.mesh = sm
	var skym := ShaderMaterial.new()
	var sh := Shader.new()
	sh.code = SKY_SHADER
	skym.shader = sh
	skym.set_shader_parameter("sun_dir", sun_dir)
	skym.render_priority = -100
	sky.material_override = skym
	sky.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	sky.extra_cull_margin = 16384.0
	add_child(sky)

	var sea := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(800, 800)
	sea.mesh = pm
	sea.material_override = unshaded(Color8(0xf6, 0xdb, 0xe8))
	sea.position.y = -38.0
	add_child(sea)

	lava = MeshInstance3D.new()
	var lm := PlaneMesh.new()
	lm.size = Vector2(600, 600)
	lm.subdivide_width = 8
	lm.subdivide_depth = 8
	lava.mesh = lm
	var lmat := ShaderMaterial.new()
	var lsh := Shader.new()
	lsh.code = LAVA_SHADER
	lmat.shader = lsh
	lava.material_override = lmat
	lava.position.y = -40.0
	lava.visible = false
	add_child(lava)


func set_lava(y: float, visible_now: bool) -> void:
	lava_y = y
	lava.position.y = y
	lava.visible = visible_now
	var k := clampf((y + 4.0) / 8.0, 0.0, 0.8) if visible_now else 0.0
	ground_fill.light_color = Color8(0x9a, 0x70, 0x55).lerp(Color8(0xff, 0x6a, 0x2a), k)
	ground_fill.light_energy = 0.3 + k * 0.6


func follow_camera(cam_pos: Vector3) -> void:
	sky.global_position = cam_pos
