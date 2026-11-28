// Navigation graph for bots: ground nodes on every island plus "perch" nodes
// on caps, decks, rocks and clouds. Edges are either short walks or ballistic
// jumps whose arcs were checked against the collision world.
import { G } from './physics.js';

export const BOT_R = 0.36;

class Heap {
  constructor() { this.k = []; this.v = []; }
  get size() { return this.k.length; }
  push(key, val) {
    const k = this.k, v = this.v;
    let i = k.length; k.push(key); v.push(val);
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (k[p] <= key) break;
      k[i] = k[p]; v[i] = v[p]; i = p;
    }
    k[i] = key; v[i] = val;
  }
  pop() {
    const k = this.k, v = this.v;
    const top = v[0];
    const lk = k.pop(), lv = v.pop();
    if (k.length) {
      let i = 0;
      const n = k.length;
      for (;;) {
        const l = 2 * i + 1, r = l + 1;
        let m = i, mk = lk;
        if (l < n && k[l] < mk) { m = l; mk = k[l]; }
        if (r < n && k[r] < mk) { m = r; mk = k[r]; }
        if (m === i) break;
        k[i] = k[m]; v[i] = v[m]; i = m;
      }
      k[i] = lk; v[i] = lv;
    }
    return top;
  }
}

export class Nav {
  constructor(phys) {
    this.phys = phys;
    this.nodes = [];
    this.goodList = [];
    this._near = [];
    this._v = { x: 0, y: 0, z: 0 };
  }

  addNode(x, y, z, r, kind, region) {
    const n = { i: this.nodes.length, x, y, z, r, kind, region, edges: [], good: false };
    this.nodes.push(n);
    return n;
  }

  // Ballistic launch from s to e that peaks a little above the higher point.
  // Returns flight time (or -1 if too demanding) and writes velocity to out.
  launch(sx, sy, sz, ex, ey, ez, out, maxH = 9.5, maxV = 11.8) {
    const dx = ex - sx, dz = ez - sz;
    const dxz = Math.sqrt(dx * dx + dz * dz);
    const apex = Math.max(sy, ey) + 0.6 + dxz * 0.09;
    const vy = Math.sqrt(2 * G * (apex - sy));
    const T = vy / G + Math.sqrt((2 * (apex - ey)) / G);
    const vh = dxz / T;
    if (vh > maxH || vy > maxV) return -1;
    out.x = dxz > 1e-6 ? (dx / dxz) * vh : 0;
    out.y = vy;
    out.z = dxz > 1e-6 ? (dz / dxz) * vh : 0;
    return T;
  }

  arcClear(a, v, T) {
    const phys = this.phys, near = this._near;
    const mt = T / 2;
    const mx = a.x + v.x * mt, my = a.y + v.y * mt - 0.5 * G * mt * mt, mz = a.z + v.z * mt;
    const reach = (Math.sqrt(v.x * v.x + v.z * v.z) * T) / 2 + v.y * v.y / (2 * G) + 2;
    phys.gather(mx, my, mz, reach, near);
    const steps = 16;
    for (let k = 1; k < steps; k++) {
      const t = (T * k) / steps;
      const px = a.x + v.x * t, py = a.y + v.y * t - 0.5 * G * t * t, pz = a.z + v.z * t;
      if (phys.sdf(px, py, pz, near) < BOT_R * 0.82) return false;
    }
    return true;
  }

  build(regions, perches) {
    const phys = this.phys, near = this._near;
    const t0 = performance.now();
    // ground nodes
    regions.forEach((reg, ri) => {
      const step = 3.1;
      for (let gx = reg.cx - reg.r; gx <= reg.cx + reg.r; gx += step) {
        for (let gz = reg.cz - reg.r; gz <= reg.cz + reg.r; gz += step) {
          const dx = gx - reg.cx, dz = gz - reg.cz;
          if (dx * dx + dz * dz > (reg.r - 1.2) * (reg.r - 1.2)) continue;
          const y = reg.y + BOT_R + 0.03;
          phys.gather(gx, y, gz, 2, near);
          if (phys.sdf(gx, y, gz, near) < BOT_R * 0.95) continue;
          this.addNode(gx, y, gz, 1.3, 0, ri);
        }
      }
    });
    // perch nodes
    for (const p of perches) {
      const y = p.y + BOT_R + 0.03;
      phys.gather(p.x, y, p.z, 2, near);
      if (phys.sdf(p.x, y, p.z, near) < BOT_R * 0.8) continue;
      if (phys.sdf(p.x, y - BOT_R - 0.3, p.z, near) > 0.15) continue; // nothing underneath
      this.addNode(p.x, y, p.z, Math.max(0.3, p.r), 1, -1);
    }
    // edges
    const N = this.nodes.length, v = this._v;
    for (let i = 0; i < N; i++) {
      const a = this.nodes[i];
      for (let j = 0; j < N; j++) {
        if (i === j) continue;
        const b = this.nodes[j];
        const dx = b.x - a.x, dz = b.z - a.z, dy = b.y - a.y;
        const dxz = Math.sqrt(dx * dx + dz * dz);
        if (a.kind === 0 && b.kind === 0 && a.region === b.region) {
          if (dxz < 4.6 && Math.abs(dy) < 0.5) {
            phys.gather((a.x + b.x) / 2, a.y, (a.z + b.z) / 2, dxz / 2 + 1, near);
            if (phys.segmentClear(near, a.x, a.y + 0.05, a.z, b.x, b.y + 0.05, b.z, BOT_R * 0.85)) {
              a.edges.push({ from: i, to: j, jump: false, cost: dxz / 4.5 });
            }
          }
          continue;
        }
        if (dxz > 10.5 || dy > 5.4 || dy < -15) continue;
        if (dxz < 0.7 && Math.abs(dy) < 0.5) continue;
        const T = this.launch(a.x, a.y, a.z, b.x, b.y, b.z, v);
        if (T < 0) continue;
        if (!this.arcClear(a, v, T)) continue;
        a.edges.push({ from: i, to: j, jump: true, cost: T + 0.5 });
      }
    }
    // keep nodes that are reachable from (and can return to) the main island
    const fwd = new Uint8Array(N), bwd = new Uint8Array(N);
    const rev = Array.from({ length: N }, () => []);
    for (const n of this.nodes) for (const e of n.edges) rev[e.to].push(e.from);
    const seeds = this.nodes.filter((n) => n.kind === 0 && n.region === 0).map((n) => n.i);
    const bfs = (mark, next) => {
      const q = seeds.slice();
      for (const s of q) mark[s] = 1;
      while (q.length) {
        const c = q.pop();
        for (const t of next(c)) if (!mark[t]) { mark[t] = 1; q.push(t); }
      }
    };
    bfs(fwd, (c) => this.nodes[c].edges.map((e) => e.to));
    bfs(bwd, (c) => rev[c]);
    this.goodList = [];
    for (let i = 0; i < N; i++) {
      this.nodes[i].good = !!(fwd[i] && bwd[i]);
      if (this.nodes[i].good) this.goodList.push(i);
    }
    this.buildMs = performance.now() - t0;
    this.edgeCount = this.nodes.reduce((s, n) => s + n.edges.length, 0);
  }

  nearest(x, y, z, goodOnly = true) {
    let best = -1, bs = 1e18;
    const nodes = this.nodes;
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      if (goodOnly && !n.good) continue;
      const dx = n.x - x, dz = n.z - z;
      let dy = n.y - y;
      dy = dy > 0 ? dy * 2.2 : dy * 1.2; // prefer nodes at or below the point
      const s = dx * dx + dz * dz + dy * dy;
      if (s < bs) { bs = s; best = i; }
    }
    return best;
  }

  randomGood(rng = Math.random) {
    return this.goodList[Math.floor(rng() * this.goodList.length)];
  }

  // A* over the graph. Returns an array of edges or null.
  findPath(start, goal) {
    if (start < 0 || goal < 0) return null;
    if (start === goal) return [];
    const nodes = this.nodes, N = nodes.length;
    if (!this._g || this._g.length !== N) {
      this._g = new Float64Array(N);
      this._came = new Array(N);
      this._closed = new Uint8Array(N);
    }
    const g = this._g, came = this._came, closed = this._closed;
    g.fill(Infinity); closed.fill(0);
    const gn = nodes[goal];
    const h = (n) => Math.sqrt((n.x - gn.x) ** 2 + (n.y - gn.y) ** 2 + (n.z - gn.z) ** 2) / 9;
    const open = new Heap();
    g[start] = 0; came[start] = null;
    open.push(h(nodes[start]), start);
    while (open.size) {
      const c = open.pop();
      if (closed[c]) continue;
      if (c === goal) break;
      closed[c] = 1;
      const gc = g[c];
      for (const e of nodes[c].edges) {
        const ng = gc + e.cost;
        if (ng < g[e.to]) {
          g[e.to] = ng; came[e.to] = e;
          open.push(ng + h(nodes[e.to]), e.to);
        }
      }
    }
    if (g[goal] === Infinity) return null;
    const path = [];
    let e = came[goal];
    while (e) { path.push(e); e = came[e.from]; }
    path.reverse();
    return path;
  }
}
