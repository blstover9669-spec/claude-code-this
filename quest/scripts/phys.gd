class_name Phys
extends RefCounted
## Signed-distance collision world (port of the web build's physics.js).
## Colliders are spheres, oriented boxes, capsules, rounded vertical
## cylinders and (half) ellipsoids, stored in flat packed arrays.

const SPHERE := 0
const BOX := 1
const CAPSULE := 2
const CYL := 3
const ELLIPSOID := 4
const EPS := 0.0015
const MIN_STEP := 0.003
## material -> [slip, bounce]
const MATS := {
	"grass": [0.0, 0.0], "wood": [0.0, 0.0], "stone": [0.0, 0.0], "cap": [0.0, 0.0],
	"shroom": [0.0, 1.0], "crystal": [0.8, 0.0], "leaf": [0.0, 0.0], "cloud": [0.0, 0.0],
}

var count := 0
var ctype := PackedInt32Array()
var cmat := PackedStringArray()
var cslip := PackedFloat32Array()
var cbounce := PackedFloat32Array()
var cx := PackedFloat64Array()
var cy := PackedFloat64Array()
var cz := PackedFloat64Array()
var cbr := PackedFloat64Array()
var cp := PackedFloat64Array()

var hit_col := -1
# sphere_cast results
var res_pos := Vector3.ZERO
var res_n := Vector3.UP
var res_col := -1
# resolve_sphere results
var rs_pos := Vector3.ZERO
var rs_vel := Vector3.ZERO
var rs_n := Vector3.UP
var rs_col := -1
var rs_ground := false
var rs_ground_col := -1
var rs_impact := 0.0


func load_level(level: Dictionary) -> void:
	var cols: Array = level["colliders"]
	count = cols.size()
	ctype.resize(count)
	cmat.resize(count)
	cslip.resize(count)
	cbounce.resize(count)
	cx.resize(count)
	cy.resize(count)
	cz.resize(count)
	cbr.resize(count)
	cp.resize(count * 13)
	for i in range(count):
		var c: Dictionary = cols[i]
		ctype[i] = int(c["t"])
		var m: String = c["m"]
		cmat[i] = m
		var props: Array = MATS.get(m, [0.0, 0.0])
		cslip[i] = props[0]
		cbounce[i] = props[1]
		var cc: Array = c["c"]
		cx[i] = cc[0]
		cy[i] = cc[1]
		cz[i] = cc[2]
		cbr[i] = c["br"]
		var p: Array = c["p"]
		for k in range(13):
			cp[i * 13 + k] = float(p[k]) if k < p.size() else 0.0


func sdf_one(i: int, x: float, y: float, z: float) -> float:
	var o := i * 13
	var t := ctype[i]
	if t == SPHERE:
		var dx := x - cx[i]
		var dy := y - cy[i]
		var dz := z - cz[i]
		return sqrt(dx * dx + dy * dy + dz * dz) - cp[o]
	elif t == BOX:
		var dx := x - cx[i]
		var dy := y - cy[i]
		var dz := z - cz[i]
		var lx := absf(dx * cp[o + 4] + dy * cp[o + 5] + dz * cp[o + 6]) - cp[o]
		var ly := absf(dx * cp[o + 7] + dy * cp[o + 8] + dz * cp[o + 9]) - cp[o + 1]
		var lz := absf(dx * cp[o + 10] + dy * cp[o + 11] + dz * cp[o + 12]) - cp[o + 2]
		var mx := maxf(lx, 0.0)
		var my := maxf(ly, 0.0)
		var mz := maxf(lz, 0.0)
		var m := maxf(lx, maxf(ly, lz))
		return sqrt(mx * mx + my * my + mz * mz) + minf(m, 0.0) - cp[o + 3]
	elif t == CAPSULE:
		var pax := x - cp[o]
		var pay := y - cp[o + 1]
		var paz := z - cp[o + 2]
		var h := clampf((pax * cp[o + 3] + pay * cp[o + 4] + paz * cp[o + 5]) * cp[o + 6], 0.0, 1.0)
		var qx := pax - cp[o + 3] * h
		var qy := pay - cp[o + 4] * h
		var qz := paz - cp[o + 5] * h
		return sqrt(qx * qx + qy * qy + qz * qz) - cp[o + 7]
	elif t == CYL:
		var dx := x - cx[i]
		var dz := z - cz[i]
		var a := sqrt(dx * dx + dz * dz) - cp[o]
		var b := absf(y - cy[i]) - cp[o + 1]
		var ma := maxf(a, 0.0)
		var mb := maxf(b, 0.0)
		return minf(maxf(a, b), 0.0) + sqrt(ma * ma + mb * mb) - cp[o + 2]
	var ex := x - cx[i]
	var ey := y - cy[i]
	var ez := z - cz[i]
	var px := ex / cp[o]
	var py := ey / cp[o + 1]
	var pz := ez / cp[o + 2]
	var k0 := sqrt(px * px + py * py + pz * pz)
	var sx := px / cp[o]
	var sy := py / cp[o + 1]
	var sz := pz / cp[o + 2]
	var k1 := sqrt(sx * sx + sy * sy + sz * sz)
	var d := -minf(cp[o], minf(cp[o + 1], cp[o + 2]))
	if k1 > 1e-9:
		d = k0 * (k0 - 1.0) / k1
	var cut := cp[o + 3]
	if cut > 0.0:
		d = maxf(d, -ey)
	elif cut < 0.0:
		d = maxf(d, ey)
	return d


## Indices of colliders whose bounds come within `radius` of a point.
func gather(x: float, y: float, z: float, radius: float) -> PackedInt32Array:
	var out := PackedInt32Array()
	for i in range(count):
		var dx := x - cx[i]
		var dy := y - cy[i]
		var dz := z - cz[i]
		var rr := radius + cbr[i]
		if dx * dx + dy * dy + dz * dz < rr * rr:
			out.append(i)
	return out


func sdf(x: float, y: float, z: float, lst: PackedInt32Array) -> float:
	var best := 1e9
	var bc := -1
	for i in lst:
		var d := sdf_one(i, x, y, z)
		if d < best:
			best = d
			bc = i
	hit_col = bc
	return best


func normal_at(i: int, x: float, y: float, z: float) -> Vector3:
	var e := 0.001
	var nx := sdf_one(i, x + e, y, z) - sdf_one(i, x - e, y, z)
	var ny := sdf_one(i, x, y + e, z) - sdf_one(i, x, y - e, z)
	var nz := sdf_one(i, x, y, z + e) - sdf_one(i, x, y, z - e)
	var l := sqrt(nx * nx + ny * ny + nz * nz)
	if l < 1e-9:
		return Vector3.UP
	return Vector3(nx / l, ny / l, nz / l)


## Sweep a sphere from o to t. Touching only counts when moving into a
## surface, so a resting sphere can lift off. On hit: res_pos/res_n/res_col.
func sphere_cast(lst: PackedInt32Array, o: Vector3, t: Vector3, r: float) -> bool:
	var dx := t.x - o.x
	var dy := t.y - o.y
	var dz := t.z - o.z
	var length := sqrt(dx * dx + dy * dy + dz * dz)
	if length < 1e-6:
		return _contact_at(lst, t.x, t.y, t.z, r, 0.0, 0.0, 0.0)
	var ix := dx / length
	var iy := dy / length
	var iz := dz / length
	var s := 0.0
	for _it in range(96):
		var px := o.x + ix * s
		var py := o.y + iy * s
		var pz := o.z + iz * s
		var d := sdf(px, py, pz, lst) - r
		if d < EPS:
			var n := normal_at(hit_col, px, py, pz)
			if d < -0.01 or ix * n.x + iy * n.y + iz * n.z < -0.02:
				return _finish(px, py, pz, d, n)
			if s >= length:
				return false
			s = minf(length, s + MIN_STEP)
			continue
		if s >= length:
			return false
		s += maxf(d, MIN_STEP)
		if s > length:
			s = length
	return _contact_at(lst, t.x, t.y, t.z, r, ix, iy, iz)


func _contact_at(lst: PackedInt32Array, x: float, y: float, z: float, r: float, ix: float, iy: float, iz: float) -> bool:
	var d := sdf(x, y, z, lst) - r
	if d >= EPS:
		return false
	var n := normal_at(hit_col, x, y, z)
	if d < -0.01 or ix * n.x + iy * n.y + iz * n.z < -0.02:
		return _finish(x, y, z, d, n)
	return false


func _finish(px: float, py: float, pz: float, d: float, n: Vector3) -> bool:
	if d < 0.0:
		px -= n.x * d
		py -= n.y * d
		pz -= n.z * d
	res_pos = Vector3(px, py, pz)
	res_n = n
	res_col = hit_col
	return true


## Push a sphere out of the world. With use_vel, removes the velocity going
## into surfaces and records the biggest impact. Results in rs_*.
func resolve_sphere(lst: PackedInt32Array, p: Vector3, r: float, vel: Vector3, use_vel: bool) -> bool:
	var hit := false
	rs_ground = false
	rs_impact = 0.0
	rs_col = -1
	rs_ground_col = -1
	rs_n = Vector3.UP
	var px := p.x
	var py := p.y
	var pz := p.z
	var v := vel
	for _it in range(4):
		var d := sdf(px, py, pz, lst) - r
		if d >= 0.0:
			break
		var c := hit_col
		var n := normal_at(c, px, py, pz)
		px -= n.x * d
		py -= n.y * d
		pz -= n.z * d
		hit = true
		rs_col = c
		rs_n = n
		if n.y > 0.55:
			rs_ground = true
			rs_ground_col = c
		if use_vel:
			var vn := v.dot(n)
			if vn < 0.0:
				rs_impact = maxf(rs_impact, -vn)
				v -= n * vn
	rs_pos = Vector3(px, py, pz)
	rs_vel = v
	return hit


func segment_clear(lst: PackedInt32Array, a: Vector3, b: Vector3, r: float, step := 0.35) -> bool:
	var length := a.distance_to(b)
	var n := maxi(1, ceili(length / step))
	for i in range(n + 1):
		var p := a.lerp(b, float(i) / n)
		if sdf(p.x, p.y, p.z, lst) < r:
			return false
	return true
