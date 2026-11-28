class_name Nav
extends RefCounted
## Bot navigation graph (exported from the web build): ground + perch nodes,
## walk and ballistic-jump edges stored CSR-style, A* path finding.

const G := 9.8
const BOT_R := 0.36

var n := 0
var nx := PackedFloat32Array()
var ny := PackedFloat32Array()
var nz := PackedFloat32Array()
var nr := PackedFloat32Array()
var nkind := PackedInt32Array()
var nregion := PackedInt32Array()
var ngood := PackedByteArray()
var e_start := PackedInt32Array()
var e_from := PackedInt32Array()
var e_to := PackedInt32Array()
var e_jump := PackedByteArray()
var e_cost := PackedFloat32Array()
var good_list := PackedInt32Array()
var launch_t := -1.0
var path_ok := false

var _g := PackedFloat32Array()
var _came := PackedInt32Array()
var _closed := PackedByteArray()
var _hk := PackedFloat32Array()
var _hv := PackedInt32Array()


func load_level(level: Dictionary) -> void:
	var nodes: Array = level["nodes"]
	var edges: Array = level["edges"]
	n = nodes.size()
	nx.resize(n)
	ny.resize(n)
	nz.resize(n)
	nr.resize(n)
	nkind.resize(n)
	nregion.resize(n)
	ngood.resize(n)
	e_start.resize(n + 1)
	var ei := 0
	for i in range(n):
		var nd: Array = nodes[i]
		nx[i] = nd[0]
		ny[i] = nd[1]
		nz[i] = nd[2]
		nr[i] = nd[3]
		nkind[i] = int(nd[4])
		nregion[i] = int(nd[5])
		ngood[i] = int(nd[6])
		if ngood[i] == 1:
			good_list.append(i)
		e_start[i] = ei
		for e in edges[i]:
			e_from.append(i)
			e_to.append(int(e[0]))
			e_jump.append(int(e[1]))
			e_cost.append(float(e[2]))
			ei += 1
	e_start[n] = ei


func pos(i: int) -> Vector3:
	return Vector3(nx[i], ny[i], nz[i])


## Ballistic launch from s to e peaking a little above the higher point.
## Sets launch_t (flight time, -1 if too demanding) and returns velocity.
func launch(s: Vector3, e: Vector3, max_h := 9.5, max_v := 11.8) -> Vector3:
	var dx := e.x - s.x
	var dz := e.z - s.z
	var dxz := sqrt(dx * dx + dz * dz)
	var apex := maxf(s.y, e.y) + 0.6 + dxz * 0.09
	var vy := sqrt(2.0 * G * (apex - s.y))
	var t := vy / G + sqrt(2.0 * (apex - e.y) / G)
	var vh := dxz / t
	if vh > max_h or vy > max_v:
		launch_t = -1.0
		return Vector3.ZERO
	launch_t = t
	if dxz > 1e-6:
		return Vector3(dx / dxz * vh, vy, dz / dxz * vh)
	return Vector3(0.0, vy, 0.0)


func nearest(x: float, y: float, z: float, good_only := true) -> int:
	var best := -1
	var bs := 1e18
	for i in range(n):
		if good_only and ngood[i] == 0:
			continue
		var dx := nx[i] - x
		var dz := nz[i] - z
		var dy := ny[i] - y
		if dy > 0.0:
			dy *= 2.2
		else:
			dy *= 1.2
		var s := dx * dx + dz * dz + dy * dy
		if s < bs:
			bs = s
			best = i
	return best


func random_good() -> int:
	return good_list[randi() % good_list.size()]


func _heur(i: int, gx: float, gy: float, gz: float) -> float:
	var dx := nx[i] - gx
	var dy := ny[i] - gy
	var dz := nz[i] - gz
	return sqrt(dx * dx + dy * dy + dz * dz) / 9.0


func _hpush(k: float, v: int) -> void:
	_hk.append(k)
	_hv.append(v)
	var i := _hk.size() - 1
	while i > 0:
		var p := (i - 1) >> 1
		if _hk[p] <= k:
			break
		_hk[i] = _hk[p]
		_hv[i] = _hv[p]
		i = p
	_hk[i] = k
	_hv[i] = v


func _hpop() -> int:
	var top := _hv[0]
	var last := _hk.size() - 1
	var lk := _hk[last]
	var lv := _hv[last]
	_hk.resize(last)
	_hv.resize(last)
	var size := last
	if size > 0:
		var i := 0
		while true:
			var l := 2 * i + 1
			var r := l + 1
			var m := i
			var mk := lk
			if l < size and _hk[l] < mk:
				m = l
				mk = _hk[l]
			if r < size and _hk[r] < mk:
				m = r
			if m == i:
				break
			_hk[i] = _hk[m]
			_hv[i] = _hv[m]
			i = m
		_hk[i] = lk
		_hv[i] = lv
	return top


## A*: returns the edge indices from start to goal (path_ok tells success).
func find_path(start: int, goal: int) -> PackedInt32Array:
	path_ok = false
	var out := PackedInt32Array()
	if start < 0 or goal < 0:
		return out
	if start == goal:
		path_ok = true
		return out
	if _g.size() != n:
		_g.resize(n)
		_came.resize(n)
		_closed.resize(n)
	_g.fill(INF)
	_came.fill(-1)
	_closed.fill(0)
	_hk.clear()
	_hv.clear()
	var gx := nx[goal]
	var gy := ny[goal]
	var gz := nz[goal]
	_g[start] = 0.0
	_hpush(_heur(start, gx, gy, gz), start)
	while _hk.size() > 0:
		var c := _hpop()
		if _closed[c] == 1:
			continue
		if c == goal:
			break
		_closed[c] = 1
		var gc := _g[c]
		for ei in range(e_start[c], e_start[c + 1]):
			var to := e_to[ei]
			var ng := gc + e_cost[ei]
			if ng < _g[to]:
				_g[to] = ng
				_came[to] = ei
				_hpush(ng + _heur(to, gx, gy, gz), to)
	if _g[goal] == INF:
		return out
	var cur := goal
	while cur != start:
		var ei := _came[cur]
		if ei < 0:
			return PackedInt32Array()
		out.append(ei)
		cur = e_from[ei]
	out.reverse()
	path_ok = true
	return out
