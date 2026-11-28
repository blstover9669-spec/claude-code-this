// Collision world built from signed-distance primitives.
// Every solid thing in the level is a sphere, oriented box, capsule, rounded
// vertical cylinder or (half) ellipsoid. Distance queries are exact (or a safe
// lower bound), which makes sphere casts for hands and bodies cheap and robust.

export const G = 9.8;

// slip: 0 = full grip, 1 = frictionless. bounce: launches whoever hits it.
export const MAT = {
  grass:   { name: 'grass',   slip: 0,    bounce: 0 },
  wood:    { name: 'wood',    slip: 0,    bounce: 0 },
  stone:   { name: 'stone',   slip: 0,    bounce: 0 },
  cap:     { name: 'cap',     slip: 0,    bounce: 0 },
  shroom:  { name: 'shroom',  slip: 0,    bounce: 1 },
  crystal: { name: 'crystal', slip: 0.8,  bounce: 0 },
  leaf:    { name: 'leaf',    slip: 0,    bounce: 0 },
  cloud:   { name: 'cloud',   slip: 0,    bounce: 0 },
};

const SPHERE = 0, BOX = 1, CAPSULE = 2, CYL = 3, ELLIPSOID = 4;
const EPS = 0.0015;
const MIN_STEP = 0.003;

class Collider {
  constructor(type, mat) {
    this.type = type;
    this.mat = mat;
    this.id = -1;
    this.cx = 0; this.cy = 0; this.cz = 0; // centre
    this.br = 0;                            // bounding radius
    this.p = new Float64Array(13);
    this.tag = '';
  }
}

export function sdfOne(c, x, y, z) {
  const p = c.p;
  switch (c.type) {
    case SPHERE: {
      const dx = x - c.cx, dy = y - c.cy, dz = z - c.cz;
      return Math.sqrt(dx * dx + dy * dy + dz * dz) - p[0];
    }
    case BOX: {
      const dx = x - c.cx, dy = y - c.cy, dz = z - c.cz;
      const lx = Math.abs(dx * p[4] + dy * p[5] + dz * p[6]) - p[0];
      const ly = Math.abs(dx * p[7] + dy * p[8] + dz * p[9]) - p[1];
      const lz = Math.abs(dx * p[10] + dy * p[11] + dz * p[12]) - p[2];
      const mx = lx > 0 ? lx : 0, my = ly > 0 ? ly : 0, mz = lz > 0 ? lz : 0;
      const m = lx > ly ? (lx > lz ? lx : lz) : (ly > lz ? ly : lz);
      return Math.sqrt(mx * mx + my * my + mz * mz) + (m < 0 ? m : 0) - p[3];
    }
    case CAPSULE: {
      const pax = x - p[0], pay = y - p[1], paz = z - p[2];
      let h = (pax * p[3] + pay * p[4] + paz * p[5]) * p[6];
      h = h < 0 ? 0 : h > 1 ? 1 : h;
      const qx = pax - p[3] * h, qy = pay - p[4] * h, qz = paz - p[5] * h;
      return Math.sqrt(qx * qx + qy * qy + qz * qz) - p[7];
    }
    case CYL: {
      const dx = x - c.cx, dz = z - c.cz;
      const a = Math.sqrt(dx * dx + dz * dz) - p[0];
      const b = Math.abs(y - c.cy) - p[1];
      const ma = a > 0 ? a : 0, mb = b > 0 ? b : 0;
      const m = a > b ? a : b;
      return (m < 0 ? m : 0) + Math.sqrt(ma * ma + mb * mb) - p[2];
    }
    case ELLIPSOID: {
      const dx = x - c.cx, dy = y - c.cy, dz = z - c.cz;
      const px = dx / p[0], py = dy / p[1], pz = dz / p[2];
      const k0 = Math.sqrt(px * px + py * py + pz * pz);
      const qx = px / p[0], qy = py / p[1], qz = pz / p[2];
      const k1 = Math.sqrt(qx * qx + qy * qy + qz * qz);
      let d = k1 > 1e-9 ? (k0 * (k0 - 1)) / k1 : -Math.min(p[0], p[1], p[2]);
      if (p[3] > 0) { if (-dy > d) d = -dy; }       // keep the upper half (dome)
      else if (p[3] < 0) { if (dy > d) d = dy; }    // keep the lower half (bowl)
      return d;
    }
  }
  return 1e9;
}

export class PhysWorld {
  constructor() {
    this.colliders = [];
    this.hitCol = null;
    this.n = { x: 0, y: 1, z: 0 };
  }

  _add(c) {
    c.id = this.colliders.length;
    this.colliders.push(c);
    return c;
  }

  addSphere(x, y, z, r, mat) {
    const c = new Collider(SPHERE, mat);
    c.cx = x; c.cy = y; c.cz = z; c.br = r; c.p[0] = r;
    return this._add(c);
  }

  // q: optional {x,y,z,w} quaternion
  addBox(x, y, z, hx, hy, hz, q, mat, round = 0.03) {
    const c = new Collider(BOX, mat);
    c.cx = x; c.cy = y; c.cz = z;
    const rr = Math.min(round, hx * 0.9, hy * 0.9, hz * 0.9);
    c.p[0] = hx - rr; c.p[1] = hy - rr; c.p[2] = hz - rr; c.p[3] = rr;
    let m00 = 1, m01 = 0, m02 = 0, m10 = 0, m11 = 1, m12 = 0, m20 = 0, m21 = 0, m22 = 1;
    if (q) {
      const { x: qx, y: qy, z: qz, w: qw } = q;
      m00 = 1 - 2 * (qy * qy + qz * qz); m01 = 2 * (qx * qy - qz * qw); m02 = 2 * (qx * qz + qy * qw);
      m10 = 2 * (qx * qy + qz * qw); m11 = 1 - 2 * (qx * qx + qz * qz); m12 = 2 * (qy * qz - qx * qw);
      m20 = 2 * (qx * qz - qy * qw); m21 = 2 * (qy * qz + qx * qw); m22 = 1 - 2 * (qx * qx + qy * qy);
    }
    // local axes (columns of the rotation matrix)
    c.p[4] = m00; c.p[5] = m10; c.p[6] = m20;
    c.p[7] = m01; c.p[8] = m11; c.p[9] = m21;
    c.p[10] = m02; c.p[11] = m12; c.p[12] = m22;
    c.br = Math.sqrt(hx * hx + hy * hy + hz * hz);
    return this._add(c);
  }

  addCapsule(ax, ay, az, bx, by, bz, r, mat) {
    const c = new Collider(CAPSULE, mat);
    const dx = bx - ax, dy = by - ay, dz = bz - az;
    c.p[0] = ax; c.p[1] = ay; c.p[2] = az;
    c.p[3] = dx; c.p[4] = dy; c.p[5] = dz;
    c.p[6] = 1 / Math.max(1e-9, dx * dx + dy * dy + dz * dz);
    c.p[7] = r;
    c.cx = (ax + bx) / 2; c.cy = (ay + by) / 2; c.cz = (az + bz) / 2;
    c.br = Math.sqrt(dx * dx + dy * dy + dz * dz) / 2 + r;
    return this._add(c);
  }

  // vertical cylinder centred at (x,y,z), radius r, half height hh, rounded edges
  addCylinder(x, y, z, r, hh, mat, round = 0.08) {
    const c = new Collider(CYL, mat);
    const rr = Math.min(round, r * 0.9, hh * 0.9);
    c.cx = x; c.cy = y; c.cz = z;
    c.p[0] = r - rr; c.p[1] = hh - rr; c.p[2] = rr;
    c.br = Math.sqrt(r * r + hh * hh);
    return this._add(c);
  }

  // cut: 0 full ellipsoid, 1 upper half only (dome), -1 lower half only (bowl)
  addEllipsoid(x, y, z, rx, ry, rz, mat, cut = 0) {
    const c = new Collider(ELLIPSOID, mat);
    c.cx = x; c.cy = y; c.cz = z;
    c.p[0] = rx; c.p[1] = ry; c.p[2] = rz; c.p[3] = cut;
    c.br = Math.max(rx, ry, rz);
    return this._add(c);
  }

  // Collect colliders whose bounds come within `radius` of a point.
  gather(x, y, z, radius, out) {
    out.length = 0;
    const cs = this.colliders;
    for (let i = 0; i < cs.length; i++) {
      const c = cs[i];
      const dx = x - c.cx, dy = y - c.cy, dz = z - c.cz, rr = radius + c.br;
      if (dx * dx + dy * dy + dz * dz < rr * rr) out.push(c);
    }
    return out;
  }

  sdf(x, y, z, list) {
    let best = 1e9, bc = null;
    for (let i = 0; i < list.length; i++) {
      const d = sdfOne(list[i], x, y, z);
      if (d < best) { best = d; bc = list[i]; }
    }
    this.hitCol = bc;
    return best;
  }

  normal(c, x, y, z, out) {
    const e = 0.001;
    const nx = sdfOne(c, x + e, y, z) - sdfOne(c, x - e, y, z);
    const ny = sdfOne(c, x, y + e, z) - sdfOne(c, x, y - e, z);
    const nz = sdfOne(c, x, y, z + e) - sdfOne(c, x, y, z - e);
    const l = Math.sqrt(nx * nx + ny * ny + nz * nz);
    if (l < 1e-9) { out.x = 0; out.y = 1; out.z = 0; }
    else { out.x = nx / l; out.y = ny / l; out.z = nz / l; }
    return out;
  }

  // Sweep a sphere from o to t. On hit, res gets the (non-penetrating) centre
  // at first contact, the surface normal and the collider. Touching a surface
  // only counts when moving into it, so a resting sphere can lift off freely.
  sphereCast(list, ox, oy, oz, tx, ty, tz, r, res) {
    const dx = tx - ox, dy = ty - oy, dz = tz - oz;
    const len = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (len < 1e-6) return this._contactAt(list, tx, ty, tz, r, res, 0, 0, 0, 0);
    const ix = dx / len, iy = dy / len, iz = dz / len;
    let t = 0;
    for (let i = 0; i < 96; i++) {
      const px = ox + ix * t, py = oy + iy * t, pz = oz + iz * t;
      const d = this.sdf(px, py, pz, list) - r;
      if (d < EPS) {
        const n = this.normal(this.hitCol, px, py, pz, this.n);
        if (d < -0.01 || ix * n.x + iy * n.y + iz * n.z < -0.02) return this._finish(px, py, pz, d, res, t);
        if (t >= len) return false;
        t = Math.min(len, t + MIN_STEP); // grazing or leaving the surface: keep going
        continue;
      }
      if (t >= len) return false;
      t += d > MIN_STEP ? d : MIN_STEP;
      if (t > len) t = len;
    }
    return this._contactAt(list, tx, ty, tz, r, res, len, ix, iy, iz);
  }

  _contactAt(list, x, y, z, r, res, t, ix, iy, iz) {
    const d = this.sdf(x, y, z, list) - r;
    if (d >= EPS) return false;
    const n = this.normal(this.hitCol, x, y, z, this.n);
    if (d < -0.01 || ix * n.x + iy * n.y + iz * n.z < -0.02) return this._finish(x, y, z, d, res, t);
    return false;
  }

  _finish(px, py, pz, d, res, t) {
    const c = this.hitCol;
    const n = this.normal(c, px, py, pz, this.n);
    if (d < 0) { px -= n.x * d; py -= n.y * d; pz -= n.z * d; }
    res.x = px; res.y = py; res.z = pz;
    res.nx = n.x; res.ny = n.y; res.nz = n.z;
    res.col = c; res.t = t;
    return true;
  }

  // Push a sphere out of the world. Optionally removes the velocity component
  // going into surfaces and reports the biggest impact speed.
  resolveSphere(list, p, r, vel, res) {
    res.hit = false; res.ground = false; res.impact = 0; res.col = null; res.groundCol = null;
    res.nx = 0; res.ny = 1; res.nz = 0;
    for (let i = 0; i < 4; i++) {
      const d = this.sdf(p.x, p.y, p.z, list) - r;
      if (d >= 0) break;
      const c = this.hitCol;
      const n = this.normal(c, p.x, p.y, p.z, this.n);
      p.x -= n.x * d; p.y -= n.y * d; p.z -= n.z * d;
      res.hit = true; res.col = c; res.nx = n.x; res.ny = n.y; res.nz = n.z;
      if (n.y > 0.55) { res.ground = true; res.groundCol = c; }
      if (vel) {
        const vn = vel.x * n.x + vel.y * n.y + vel.z * n.z;
        if (vn < 0) {
          if (-vn > res.impact) res.impact = -vn;
          vel.x -= n.x * vn; vel.y -= n.y * vn; vel.z -= n.z * vn;
        }
      }
    }
    return res.hit;
  }

  // Is a sphere of radius r free to travel the straight segment a->b?
  segmentClear(list, ax, ay, az, bx, by, bz, r, step = 0.35) {
    const dx = bx - ax, dy = by - ay, dz = bz - az;
    const len = Math.sqrt(dx * dx + dy * dy + dz * dz);
    const n = Math.max(1, Math.ceil(len / step));
    for (let i = 0; i <= n; i++) {
      const t = i / n;
      if (this.sdf(ax + dx * t, ay + dy * t, az + dz * t, list) < r) return false;
    }
    return true;
  }
}
