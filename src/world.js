// Builds the level: floating mushroom islands, trees, crystals and clouds.
// Every solid visual has a matching collider in the physics world, and spots
// where bots can stand are registered as nav "perches".
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { PhysWorld, MAT } from './physics.js';

// ---------------------------------------------------------------- helpers
function ihash(ix, iy, iz) {
  let h = (Math.imul(ix, 374761393) + Math.imul(iy, 668265263) + Math.imul(iz, 1440662683)) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}
export function phash(x, y, z) {
  return ihash(Math.round(x * 97), Math.round(y * 97), Math.round(z * 97));
}
export function vnoise(x, y, z) {
  const ix = Math.floor(x), iy = Math.floor(y), iz = Math.floor(z);
  const fx = x - ix, fy = y - iy, fz = z - iz;
  const ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy), uz = fz * fz * (3 - 2 * fz);
  const a = ihash(ix, iy, iz), b = ihash(ix + 1, iy, iz), c = ihash(ix, iy + 1, iz), d = ihash(ix + 1, iy + 1, iz);
  const e = ihash(ix, iy, iz + 1), f = ihash(ix + 1, iy, iz + 1), g = ihash(ix, iy + 1, iz + 1), h = ihash(ix + 1, iy + 1, iz + 1);
  const x1 = a + (b - a) * ux, x2 = c + (d - c) * ux, x3 = e + (f - e) * ux, x4 = g + (h - g) * ux;
  const y1 = x1 + (x2 - x1) * uy, y2 = x3 + (x4 - x3) * uy;
  return y1 + (y2 - y1) * uz;
}
export function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const UP = new THREE.Vector3(0, 1, 0);
const col = (h) => new THREE.Color(h);
export const PAL = {
  grass1: col(0x8fd35f), grass2: col(0x5fb24c), grass3: col(0xc4e57a),
  dirt: col(0x9a6440), dirt2: col(0x6b4329),
  rock1: col(0xa59fc2), rock2: col(0x7a73a0), rock3: col(0x4f4575),
  bark: col(0x8f5c39), bark2: col(0x5c3a24),
  leaf1: col(0x5cc06b), leaf2: col(0x3a9656), leaf3: col(0xa8e070),
  stem: col(0xf6e9d3), stem2: col(0xd9c3a3), gill: col(0xf3d6ba),
  capTan: col(0xdb9158), capRed: col(0xea5a43), capViolet: col(0xa47ce4), capPink: col(0xff5fa8), spot: col(0xfff7f0),
  plank: col(0xcc9560), plank2: col(0x9a6638),
  crystal1: col(0x7fe9ff), crystal2: col(0xc29cff),
  lantern1: col(0xffd36e), lantern2: col(0x7ff0ff),
};
const tc = new THREE.Color();

function vary(out, x, y, z, amt) {
  const k = 1 + (phash(x * 1.7 + 3, y * 1.3, z * 1.9) - 0.5) * 2 * amt;
  out.r *= k; out.g *= k; out.b *= k;
}

function MQ(x, y, z, q, sx = 1, sy = 1, sz = 1) {
  return new THREE.Matrix4().compose(new THREE.Vector3(x, y, z), q || new THREE.Quaternion(), new THREE.Vector3(sx, sy, sz));
}
function quatY(a) { return new THREE.Quaternion().setFromAxisAngle(UP, a); }
function quatEuler(x, y, z) { return new THREE.Quaternion().setFromEuler(new THREE.Euler(x, y, z)); }
function quatAlong(dx, dy, dz) { return new THREE.Quaternion().setFromUnitVectors(UP, new THREE.Vector3(dx, dy, dz).normalize()); }

function paintFaces(g, paint) {
  const pos = g.attributes.position.array;
  const n = pos.length / 3;
  const colors = new Float32Array(n * 3);
  for (let i = 0; i < n; i += 3) {
    const o = i * 3;
    const ax = pos[o], ay = pos[o + 1], az = pos[o + 2];
    const bx = pos[o + 3], by = pos[o + 4], bz = pos[o + 5];
    const cx = pos[o + 6], cy = pos[o + 7], cz = pos[o + 8];
    const ux = bx - ax, uy = by - ay, uz = bz - az, vx = cx - ax, vy = cy - ay, vz = cz - az;
    let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    const l = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;
    nx /= l; ny /= l; nz /= l;
    if (typeof paint === 'function') paint((ax + bx + cx) / 3, (ay + by + cy) / 3, (az + bz + cz) / 3, nx, ny, nz, tc);
    else tc.copy(paint);
    for (let k = 0; k < 3; k++) {
      colors[o + k * 3] = tc.r; colors[o + k * 3 + 1] = tc.g; colors[o + k * 3 + 2] = tc.b;
    }
  }
  g.setAttribute('color', new THREE.BufferAttribute(colors, 3));
}

function jitterRadial(g, cx, cy, cz, amp) {
  const pos = g.attributes.position.array;
  for (let i = 0; i < pos.length; i += 3) {
    const x = pos[i], y = pos[i + 1], z = pos[i + 2];
    const dx = x - cx, dy = y - cy, dz = z - cz;
    const l = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;
    const k = (phash(x, y, z) - 0.5) * 2 * amp;
    pos[i] += (dx / l) * k; pos[i + 1] += (dy / l) * k; pos[i + 2] += (dz / l) * k;
  }
}

// Make a flat-shaded, vertex-coloured, world-space geometry ready for merging.
function prep(geo, matrix, paint, jitter = 0, jc = null) {
  const g = geo.index ? geo.toNonIndexed() : geo;
  for (const k of Object.keys(g.attributes)) if (k !== 'position') g.deleteAttribute(k);
  g.applyMatrix4(matrix);
  if (jitter > 0 && jc) jitterRadial(g, jc[0], jc[1], jc[2], jitter);
  g.computeVertexNormals();
  paintFaces(g, paint);
  return g;
}

// Disc with roughly even triangles (nicer per-face colouring than a fan).
function discGeometry(R, rings, segs, rng) {
  const verts = [0, 0, 0];
  const starts = [0], counts = [1];
  for (let r = 1; r <= rings; r++) {
    const rad = (R * r) / rings;
    const n = Math.max(6, Math.round((segs * r) / rings));
    starts.push(verts.length / 3); counts.push(n);
    for (let s = 0; s < n; s++) {
      const edge = r === rings;
      const ja = edge ? 0 : (rng() - 0.5) * ((Math.PI * 2) / n) * 0.45;
      const jr = edge ? 0 : (rng() - 0.5) * (R / rings) * 0.45;
      const a = (s / n) * Math.PI * 2 + ja;
      verts.push(Math.cos(a) * (rad + jr), 0, Math.sin(a) * (rad + jr));
    }
  }
  const idx = [];
  const tri = (a, b, c) => {
    // keep the face pointing up
    const ax = verts[a * 3], az = verts[a * 3 + 2], bx = verts[b * 3], bz = verts[b * 3 + 2], cx = verts[c * 3], cz = verts[c * 3 + 2];
    const y = (bz - az) * (cx - ax) - (bx - ax) * (cz - az);
    if (y >= 0) idx.push(a, b, c); else idx.push(a, c, b);
  };
  for (let r = 1; r <= rings; r++) {
    const is = starts[r - 1], ni = counts[r - 1], os = starts[r], no = counts[r];
    if (r === 1) { for (let s = 0; s < no; s++) tri(0, os + ((s + 1) % no), os + s); continue; }
    let a = 0, b = 0;
    while (a < ni || b < no) {
      const ta = (a + 1) / ni, tb = (b + 1) / no;
      if (b >= no || (a < ni && ta < tb)) { tri(is + (a % ni), os + (b % no), is + ((a + 1) % ni)); a++; }
      else { tri(is + (a % ni), os + (b % no), os + ((b + 1) % no)); b++; }
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
  g.setIndex(idx);
  return g;
}

class Builder {
  constructor() { this.parts = { solid: [], glow: [], cloud: [] }; }
  add(kind, geo) { this.parts[kind].push(geo); }
  finish(scene, mats) {
    for (const kind of Object.keys(this.parts)) {
      const list = this.parts[kind];
      if (!list.length) continue;
      const mesh = new THREE.Mesh(mergeGeometries(list, false), mats[kind]);
      mesh.matrixAutoUpdate = false;
      mesh.updateMatrix();
      mesh.name = 'world-' + kind;
      scene.add(mesh);
      for (const g of list) g.dispose();
    }
  }
}

// ------------------------------------------------------------- features
function perch(ctx, x, y, z, r) { if (ctx.solid) ctx.perches.push({ x, y, z, r }); }

function island(ctx, cx, topY, cz, R, depth) {
  const { B, W } = ctx;
  const slabH = 2.4;
  if (ctx.solid) {
    W.addCylinder(cx, topY - slabH / 2, cz, R, slabH / 2, MAT.grass, 0.18).tag = 'island';
    W.addEllipsoid(cx, topY - slabH + 0.5, cz, R * 0.96, depth, R * 0.96, MAT.stone, -1).tag = 'island';
    ctx.regions.push({ cx, cz, r: R, y: topY });
  }
  const segs = Math.max(20, Math.round(R * 3));
  const grass = (x, y, z, nx, ny, nz, out) => {
    const n = vnoise(x * 0.16, 3.1, z * 0.16), n2 = vnoise(x * 0.7 + 9, 1.7, z * 0.7);
    out.copy(PAL.grass2).lerp(PAL.grass1, n);
    if (n2 > 0.62) out.lerp(PAL.grass3, (n2 - 0.62) * 2.2);
    vary(out, x, y, z, 0.05);
  };
  B.add('solid', prep(discGeometry(R, Math.max(4, Math.round(R / 1.6)), segs, ctx.rng), MQ(cx, topY, cz), grass));
  B.add('solid', prep(new THREE.CylinderGeometry(R, R, slabH, segs, 3, true), MQ(cx, topY - slabH / 2, cz), (x, y, z, nx, ny, nz, out) => {
    if (y > topY - 0.45) { out.copy(PAL.grass2).multiplyScalar(0.78); vary(out, x, y, z, 0.05); return; }
    const band = 0.5 + 0.5 * Math.sin(y * 4.0 + vnoise(x * 0.4, y * 0.4, z * 0.4) * 4.0);
    out.copy(PAL.dirt).lerp(PAL.dirt2, band * 0.6);
    vary(out, x, y, z, 0.07);
  }));
  const ucy = topY - slabH + 0.5;
  const under = new THREE.SphereGeometry(1, segs, Math.max(6, Math.round(depth / 1.4)), 0, Math.PI * 2, Math.PI / 2, Math.PI / 2);
  B.add('solid', prep(under, MQ(cx, ucy, cz, null, R * 0.96, depth, R * 0.96), (x, y, z, nx, ny, nz, out) => {
    const t = THREE.MathUtils.clamp((topY - y) / (depth + 2.5), 0, 1);
    const band = 0.5 + 0.5 * Math.sin(y * 1.3 + vnoise(x * 0.2, y * 0.3, z * 0.2) * 5.0);
    out.copy(PAL.dirt2).lerp(PAL.rock2, Math.min(1, t * 1.7)).lerp(PAL.rock3, t * t);
    out.lerp(PAL.rock1, band * 0.25 * (1 - t));
    vary(out, x, y, z, 0.08);
  }, Math.min(0.6, R * 0.03), [cx, ucy, cz]));
}

function barkPaint(cx, cz, gy) {
  return (x, y, z, nx, ny, nz, out) => {
    const a = Math.atan2(z - cz, x - cx);
    const s = vnoise(a * 2.5 + 7, y * 0.35, 0.5);
    out.copy(PAL.bark).lerp(PAL.bark2, s * 0.75);
    out.multiplyScalar(0.72 + 0.28 * THREE.MathUtils.clamp((y - gy) / 2.2, 0, 1));
    vary(out, x, y, z, 0.06);
  };
}
function leafPaint(x, y, z, nx, ny, nz, out) {
  const n = vnoise(x * 0.9, y * 0.9, z * 0.9);
  out.copy(PAL.leaf2).lerp(PAL.leaf1, n);
  if (ny > 0.4) out.lerp(PAL.leaf3, (ny - 0.4) * 0.7 * n);
  vary(out, x, y, z, 0.08);
}

function capsuleVisual(ctx, ax, ay, az, bx, by, bz, r, paint, radial = 9) {
  const dx = bx - ax, dy = by - ay, dz = bz - az;
  const len = Math.sqrt(dx * dx + dy * dy + dz * dz);
  const g = new THREE.CapsuleGeometry(r * 1.035, len, 3, radial);
  ctx.B.add('solid', prep(g, MQ((ax + bx) / 2, (ay + by) / 2, (az + bz) / 2, quatAlong(dx, dy, dz)), paint));
}

function branch(ctx, ax, ay, az, bx, by, bz, r, gy) {
  if (ctx.solid) ctx.W.addCapsule(ax, ay, az, bx, by, bz, r, MAT.wood);
  capsuleVisual(ctx, ax, ay, az, bx, by, bz, r, barkPaint(ax, az, gy), 7);
}

function leafBlob(ctx, x, y, z, rx, ry, rz) {
  if (ctx.solid) ctx.W.addEllipsoid(x, y, z, rx, ry, rz, MAT.leaf, 0);
  const g = new THREE.IcosahedronGeometry(1, 2);
  ctx.B.add('solid', prep(g, MQ(x, y, z, null, rx * 1.015, ry * 1.015, rz * 1.015), leafPaint, Math.min(rx, ry) * 0.05, [x, y, z]));
}

function tree(ctx, x, z, gy, h, trunkR, canopyR, opts = {}) {
  const { W, rng } = ctx;
  if (ctx.solid) W.addCapsule(x, gy - 0.4, z, x, gy + h, z, trunkR, MAT.wood);
  const trunk = new THREE.CylinderGeometry(trunkR * 1.03, trunkR * 1.03, h + 0.4, 10, Math.max(2, Math.round(h / 1.5)));
  ctx.B.add('solid', prep(trunk, MQ(x, gy - 0.4 + (h + 0.4) / 2, z), barkPaint(x, z, gy), trunkR * 0.03, [x, gy + h / 2, z]));
  // roots
  const roots = 4;
  for (let i = 0; i < roots; i++) {
    const a = (i / roots) * Math.PI * 2 + rng() * 0.8;
    const ca = Math.cos(a), sa = Math.sin(a);
    branch(ctx, x + ca * trunkR * 0.5, gy + 0.75, z + sa * trunkR * 0.5, x + ca * (trunkR + 1.1), gy - 0.12, z + sa * (trunkR + 1.1), trunkR * 0.32, gy);
  }
  // canopy
  const cy = gy + h + canopyR * 0.22;
  leafBlob(ctx, x, cy, z, canopyR, canopyR * 0.62, canopyR);
  const blobs = 3;
  for (let i = 0; i < blobs; i++) {
    const a = (i / blobs) * Math.PI * 2 + rng() * 1.5;
    const rr = canopyR * (0.5 + rng() * 0.12);
    leafBlob(ctx, x + Math.cos(a) * canopyR * 0.72, cy - canopyR * 0.18 + rng() * 0.5, z + Math.sin(a) * canopyR * 0.72, rr, rr * 0.75, rr);
  }
  perch(ctx, x, cy + canopyR * 0.62, z, canopyR * 0.35);
  // branches
  for (const br of opts.branches || []) {
    const [a, y0, len, rise] = br;
    const ex = x + Math.cos(a) * (trunkR + len), ez = z + Math.sin(a) * (trunkR + len);
    branch(ctx, x, gy + y0, z, ex, gy + y0 + rise, ez, 0.28, gy);
    perch(ctx, ex - Math.cos(a) * 0.3, gy + y0 + rise + 0.28, ez - Math.sin(a) * 0.3, 0.25);
  }
  if (opts.platform) deck(ctx, x, gy + opts.platform, z, opts.platformSize || 2.1, opts.platformSize || 2.1, opts.rot || 0, false);
}

// Wooden deck. y = top surface height.
function deck(ctx, x, y, z, hx, hz, rot, posts = true, postFloor = 0) {
  const q = quatY(rot);
  const th = 0.13;
  if (ctx.solid) ctx.W.addBox(x, y - th, z, hx, th, hz, q, MAT.wood, 0.03);
  const planks = Math.max(3, Math.round(hz / 0.25));
  const pw = (2 * hz) / planks;
  const ax = new THREE.Vector3(1, 0, 0).applyQuaternion(q), az = new THREE.Vector3(0, 0, 1).applyQuaternion(q);
  for (let i = 0; i < planks; i++) {
    const o = -hz + pw * (i + 0.5);
    const shadeK = 0.85 + ctx.rng() * 0.3;
    const g = new THREE.BoxGeometry(hx * 2, th * 2, pw * 0.94);
    ctx.B.add('solid', prep(g, MQ(x + az.x * o, y - th, z + az.z * o, q), (px, py, pz, nx, ny, nz, out) => {
      out.copy(PAL.plank).lerp(PAL.plank2, ny > 0.5 ? 0.0 : 0.5).multiplyScalar(shadeK);
      vary(out, px, py, pz, 0.04);
    }));
  }
  // under-beams
  for (const s of [-1, 1]) {
    const o = s * (hx - 0.18);
    const g = new THREE.BoxGeometry(0.22, 0.2, hz * 2);
    ctx.B.add('solid', prep(g, MQ(x + ax.x * o, y - th * 2 - 0.1, z + ax.z * o, q), PAL.plank2));
  }
  if (posts) {
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
      const px = x + ax.x * sx * (hx - 0.2) + az.x * sz * (hz - 0.2);
      const pz = z + ax.z * sx * (hx - 0.2) + az.z * sz * (hz - 0.2);
      const ph = y - th * 2 - postFloor;
      if (ctx.solid) ctx.W.addBox(px, postFloor + ph / 2, pz, 0.12, ph / 2, 0.12, q, MAT.wood, 0.02);
      ctx.B.add('solid', prep(new THREE.BoxGeometry(0.24, ph, 0.24), MQ(px, postFloor + ph / 2, pz, q), PAL.plank2));
    }
  }
  // perches on the deck
  const cxs = hx > 1.4 ? [-0.55, 0.55] : [0];
  const czs = hz > 1.4 ? [-0.55, 0.55] : [0];
  for (const sx of cxs) for (const sz of czs) {
    perch(ctx, x + ax.x * sx * hx + az.x * sz * hz, y, z + ax.z * sx * hx + az.z * sz * hz, Math.min(hx, hz) * 0.4);
  }
}

function mushroom(ctx, x, z, gy, stemH, capR, capH, kind, opts = {}) {
  const { W } = ctx;
  const stemR = opts.stemR || Math.max(0.2, capR * 0.19);
  const lx = opts.lean ? opts.lean[0] : 0, lz = opts.lean ? opts.lean[1] : 0;
  const tx = x + lx, tz = z + lz;
  const capY = gy + stemH;
  const bouncy = kind === 'bouncy';
  if (ctx.solid) {
    W.addCapsule(x, gy - 0.3, z, tx, capY - 0.05, tz, stemR, MAT.cap);
    W.addEllipsoid(tx, capY, tz, capR, capH, capR, bouncy ? MAT.shroom : MAT.cap, 1);
  }
  // stem
  const dx = tx - x, dy = capY + 0.3 - gy, dz = tz - z;
  const len = Math.sqrt(dx * dx + dy * dy + dz * dz);
  const stem = new THREE.CylinderGeometry(stemR * 1.03, stemR * 1.14, len, 10, Math.max(1, Math.round(len / 1.5)));
  ctx.B.add('solid', prep(stem, MQ((x + tx) / 2, (gy - 0.3 + capY) / 2, (z + tz) / 2, quatAlong(dx, dy, dz)), (px, py, pz, nx, ny, nz, out) => {
    out.copy(PAL.stem).lerp(PAL.stem2, vnoise(px * 3, py * 1.2, pz * 3) * 0.6);
    out.multiplyScalar(0.75 + 0.25 * THREE.MathUtils.clamp((py - gy) / Math.max(1, stemH), 0, 1));
    vary(out, px, py, pz, 0.04);
  }));
  // cap
  const base = { bouncy: PAL.capPink, tan: PAL.capTan, red: PAL.capRed, violet: PAL.capViolet }[kind] || PAL.capTan;
  const spots = bouncy || kind === 'red';
  const segs = capR > 3 ? 30 : 20;
  const dome = new THREE.SphereGeometry(1, segs, Math.round(segs / 3), 0, Math.PI * 2, 0, Math.PI / 2);
  ctx.B.add('solid', prep(dome, MQ(tx, capY, tz, null, capR * 1.012, capH * 1.012, capR * 1.012), (px, py, pz, nx, ny, nz, out) => {
    out.copy(base).multiplyScalar(0.8 + 0.2 * THREE.MathUtils.clamp(ny, 0, 1));
    if (spots) {
      const s = vnoise(px * (2.2 / Math.max(1, capR * 0.6)) + 5, py * 2.2, pz * (2.2 / Math.max(1, capR * 0.6)));
      if (s > 0.68) out.copy(PAL.spot);
    }
    vary(out, px, py, pz, 0.05);
  }));
  const under = new THREE.CircleGeometry(capR * 1.01, segs);
  ctx.B.add('solid', prep(under, MQ(tx, capY - 0.002, tz, quatEuler(Math.PI / 2, 0, 0)), (px, py, pz, nx, ny, nz, out) => {
    const a = Math.atan2(pz - tz, px - tx);
    out.copy(PAL.gill).multiplyScalar(0.72 + 0.12 * Math.sin(a * segs));
  }));
  perch(ctx, tx, capY + capH, tz, capR * 0.45);
  return { x: tx, y: capY, z: tz };
}

function boulder(ctx, x, y, z, rx, ry, rz, opts = {}) {
  if (ctx.solid) ctx.W.addEllipsoid(x, y, z, rx, ry, rz, MAT.stone, 0);
  const g = new THREE.IcosahedronGeometry(1, Math.max(rx, ry, rz) > 1.4 ? 2 : 1);
  const moss = opts.moss !== false;
  ctx.B.add('solid', prep(g, MQ(x, y, z, null, rx * 1.04, ry * 1.04, rz * 1.04), (px, py, pz, nx, ny, nz, out) => {
    out.copy(PAL.rock1).lerp(PAL.rock2, vnoise(px * 1.3, py * 1.3, pz * 1.3));
    if (moss && ny > 0.72) out.lerp(PAL.grass2, 0.75);
    vary(out, px, py, pz, 0.07);
  }, Math.min(rx, ry, rz) * 0.05, [x, y, z]));
  if (Math.min(rx, rz) > 0.8 && opts.perch !== false) perch(ctx, x, y + ry, z, Math.min(rx, rz) * 0.4);
}

function crystal(ctx, x, y, z, h, w, rx, ry, rz, tint) {
  const q = quatEuler(rx, ry, rz);
  const axis = new THREE.Vector3(0, 1, 0).applyQuaternion(q);
  const cx = x + axis.x * h / 2, cy = y + axis.y * h / 2, cz = z + axis.z * h / 2;
  if (ctx.solid) ctx.W.addBox(cx, cy, cz, w, h / 2, w, q, MAT.crystal, 0.02);
  const base = tint === 1 ? PAL.crystal2 : PAL.crystal1;
  const paint = (px, py, pz, nx, ny, nz, out) => {
    out.copy(base).multiplyScalar(0.75 + 0.35 * Math.abs(nx * 0.6 + nz * 0.8));
  };
  ctx.B.add('glow', prep(new THREE.BoxGeometry(w * 2, h, w * 2), MQ(cx, cy, cz, q), paint));
  const tip = new THREE.ConeGeometry(w * Math.SQRT2, w * 2.4, 4);
  tip.rotateY(Math.PI / 4);
  tip.translate(0, h / 2 + w * 1.2, 0);
  ctx.B.add('glow', prep(tip, MQ(cx, cy, cz, q), paint));
}

function log(ctx, ax, ay, az, bx, by, bz, r, perches = 0) {
  if (ctx.solid) ctx.W.addCapsule(ax, ay, az, bx, by, bz, r, MAT.wood);
  capsuleVisual(ctx, ax, ay, az, bx, by, bz, r, barkPaint(ax, az, Math.min(ay, by) - 3), 10);
  for (let i = 0; i < perches; i++) {
    const t = (i + 1) / (perches + 1);
    perch(ctx, ax + (bx - ax) * t, ay + (by - ay) * t + r, az + (bz - az) * t, 0.3);
  }
}

function cloudPlatform(ctx, x, y, z, r, ry) {
  if (ctx.solid) ctx.W.addEllipsoid(x, y, z, r, ry, r, MAT.cloud, 0);
  const add = (px, py, pz, sx, sy, sz) => {
    ctx.B.add('cloud', prep(new THREE.IcosahedronGeometry(1, 2), MQ(px, py, pz, null, sx, sy, sz), (a, b, c, nx, ny, nz, out) => {
      out.setRGB(1, 1, 1).multiplyScalar(0.9 + 0.1 * ny);
    }, Math.min(sx, sy) * 0.04, [px, py, pz]));
  };
  add(x, y, z, r * 1.015, ry * 1.015, r * 1.015);
  for (let i = 0; i < 5; i++) {
    const a = (i / 5) * Math.PI * 2 + ctx.rng();
    const s = r * (0.38 + ctx.rng() * 0.12);
    add(x + Math.cos(a) * r * 0.72, y - ry * 0.35, z + Math.sin(a) * r * 0.72, s, s * 0.7, s);
  }
  perch(ctx, x, y + ry, z, r * 0.45);
}

function cloudDecor(ctx, x, y, z, s) {
  const n = 4 + Math.floor(ctx.rng() * 3);
  for (let i = 0; i < n; i++) {
    const a = ctx.rng() * Math.PI * 2, d = ctx.rng() * s * 1.1;
    const r = s * (0.45 + ctx.rng() * 0.5);
    ctx.B.add('cloud', prep(new THREE.IcosahedronGeometry(1, 1), MQ(x + Math.cos(a) * d, y + ctx.rng() * s * 0.3, z + Math.sin(a) * d, null, r * 1.3, r * 0.75, r),
      (a1, b1, c1, nx, ny, nz, out) => out.setRGB(1, 1, 1).multiplyScalar(0.86 + 0.14 * ny)));
  }
}

function lantern(ctx, x, z, gy, s, tint) {
  const stemH = 0.35 * s;
  ctx.B.add('solid', prep(new THREE.CylinderGeometry(0.035 * s, 0.05 * s, stemH, 5), MQ(x, gy + stemH / 2, z), PAL.stem));
  const cap = new THREE.SphereGeometry(0.16 * s, 8, 3, 0, Math.PI * 2, 0, Math.PI / 2);
  ctx.B.add('glow', prep(cap, MQ(x, gy + stemH, z, null, 1, 0.8, 1), tint ? PAL.lantern2 : PAL.lantern1));
}

function stump(ctx, x, z, gy, r, h) {
  if (ctx.solid) ctx.W.addCylinder(x, gy + h / 2 - 0.2, z, r, h / 2 + 0.2, MAT.wood, 0.12);
  ctx.B.add('solid', prep(new THREE.CylinderGeometry(r * 1.01, r * 1.01, h + 0.4, 16, 3, true), MQ(x, gy + h / 2 - 0.2, z), barkPaint(x, z, gy)));
  const top = discGeometry(r, 4, 16, ctx.rng);
  ctx.B.add('solid', prep(top, MQ(x, gy + h, z), (px, py, pz, nx, ny, nz, out) => {
    const d = Math.sqrt((px - x) ** 2 + (pz - z) ** 2);
    out.copy(PAL.plank).multiplyScalar(0.8 + 0.2 * Math.sin(d * 7));
    if (d > r - 0.25) out.copy(PAL.bark2);
  }));
  perch(ctx, x, gy + h, z, r * 0.5);
}

// --------------------------------------------------------------- the map
export function buildWorld(scene) {
  const W = new PhysWorld();
  const B = new Builder();
  const ctx = { W, B, rng: mulberry32(20261128), perches: [], regions: [], solid: true };

  // islands -------------------------------------------------------------
  island(ctx, 0, 0, 0, 24, 15);        // Meadow (main)
  island(ctx, 40, 1.5, -6, 8.5, 8);    // Crystal Isle
  island(ctx, -31, 5, -25, 7.5, 7);    // Stump Isle

  // the Great Shroom in the middle, with a spiral of shelf fungi on its stem
  mushroom(ctx, 0, -3, 0, 7.0, 5.2, 2.3, 'tan', { stemR: 1.1 });
  const shelves = [[1.5, 0.5], [2.9, 2.3], [4.3, 4.1], [5.7, 5.9]];
  for (const [h, a] of shelves) {
    const sx = Math.cos(a) * 1.75, sz = -3 + Math.sin(a) * 1.75;
    W.addCylinder(sx, h, sz, 0.78, 0.09, MAT.cap, 0.06);
    B.add('solid', prep(new THREE.CylinderGeometry(0.78, 0.7, 0.18, 14), MQ(sx, h, sz), (px, py, pz, nx, ny, nz, out) => {
      out.copy(PAL.capTan).multiplyScalar(ny > 0.5 ? 1.0 : 0.75); vary(out, px, py, pz, 0.05);
    }));
    perch(ctx, sx + Math.cos(a) * 0.15, h + 0.09, sz + Math.sin(a) * 0.15, 0.3);
  }
  // stepping shrooms spiralling up to the big cap
  mushroom(ctx, 6.6, 1.6, 0, 2.2, 1.6, 0.75, 'red');
  mushroom(ctx, 7.6, -4.0, 0, 4.2, 1.5, 0.7, 'violet');
  mushroom(ctx, 4.8, -8.6, 0, 6.0, 1.5, 0.7, 'red');

  // bouncy shrooms
  mushroom(ctx, -5.8, 5.2, 0, 0.8, 1.5, 0.65, 'bouncy');
  mushroom(ctx, -10.5, -2.5, 0, 1.3, 1.6, 0.7, 'bouncy');
  mushroom(ctx, 10.8, 5.8, 0, 1.0, 1.4, 0.6, 'bouncy');
  mushroom(ctx, 3.5, -16.5, 0, 1.1, 1.5, 0.65, 'bouncy');
  mushroom(ctx, 37.5, -1.5, 1.5, 0.9, 1.3, 0.6, 'bouncy');

  // trees with treehouse decks
  tree(ctx, -12.5, -11, 0, 11, 0.95, 4.2, { platform: 4.8, rot: 0.4, branches: [[0.6, 7.2, 3.2, 1.0], [3.6, 8.4, 2.6, 0.6]] });
  tree(ctx, 14, -11.5, 0, 10, 0.85, 3.8, { platform: 4.0, rot: -0.3, branches: [[2.4, 6.6, 3.0, 0.9]] });
  tree(ctx, -15.5, 8.5, 0, 9, 0.8, 3.6, { platform: 3.6, rot: 0.2, branches: [[-0.7, 6.0, 2.8, 0.7]] });
  tree(ctx, 16, 9.5, 0, 9.5, 0.85, 3.7, { platform: 4.2, rot: 0.9, branches: [[3.9, 6.4, 2.9, 0.8]] });
  // step boulders next to the trees
  boulder(ctx, -9.4, 0.55, -8.3, 1.3, 1.3, 1.2);
  boulder(ctx, 11.0, 0.5, -9.0, 1.2, 1.2, 1.1);
  boulder(ctx, -12.6, 0.5, 6.0, 1.2, 1.1, 1.2);
  boulder(ctx, 13.3, 0.6, 7.0, 1.2, 1.3, 1.2);

  // practice tower near spawn: a wooden block with hand holds
  const towerQ = quatY(0.35);
  W.addBox(6.2, 1.2, 12.2, 1.05, 1.2, 1.05, towerQ, MAT.wood, 0.04);
  B.add('solid', prep(new THREE.BoxGeometry(2.1, 2.4, 2.1, 3, 4, 3), MQ(6.2, 1.2, 12.2, towerQ), (px, py, pz, nx, ny, nz, out) => {
    out.copy(PAL.plank).lerp(PAL.plank2, ny > 0.5 ? 0 : 0.35 + 0.3 * Math.sin(py * 9));
    vary(out, px, py, pz, 0.05);
  }));
  perch(ctx, 6.2, 2.4, 12.2, 0.6);
  {
    const ax = new THREE.Vector3(1, 0, 0).applyQuaternion(towerQ), az = new THREE.Vector3(0, 0, 1).applyQuaternion(towerQ);
    const holds = [[-0.5, 0.5], [0.4, 0.9], [-0.2, 1.4], [0.5, 1.8], [-0.45, 2.1]];
    for (const face of [1, -1]) for (const [u, hy] of holds) {
      const hx = 6.2 + az.x * 1.05 * face + ax.x * u * face, hz = 12.2 + az.z * 1.05 * face + ax.z * u * face;
      boulder(ctx, hx, hy, hz, 0.14, 0.11, 0.14, { moss: false, perch: false });
    }
  }

  // stepping rocks to Crystal Isle
  boulder(ctx, 26.6, 0.2, -4.6, 1.3, 0.6, 1.3);
  boulder(ctx, 30.3, 0.75, -5.4, 1.1, 0.55, 1.1);
  // Crystal Isle
  crystal(ctx, 41, 1.3, -6.5, 6.5, 0.55, 0.05, 0.3, -0.04, 0);
  crystal(ctx, 42.4, 1.3, -4.8, 4.2, 0.42, 0.3, 0.8, 0.25, 1);
  crystal(ctx, 39.4, 1.3, -8.3, 3.6, 0.4, -0.35, 0.2, 0.2, 0);
  crystal(ctx, 43.2, 1.3, -8.4, 3.0, 0.36, -0.3, 1.2, -0.35, 1);
  crystal(ctx, 38.6, 1.3, -4.4, 2.4, 0.3, 0.35, 0.5, 0.1, 1);
  boulder(ctx, 44.5, 1.8, -2.5, 1.2, 1.0, 1.1);
  deck(ctx, 36.4, 2.9, -9.6, 1.3, 1.3, 0.5, true, 1.5);
  // crystal outcrop on the Meadow
  crystal(ctx, -19.5, -0.2, -1.5, 4.0, 0.45, 0.15, 0.4, 0.1, 1);
  crystal(ctx, -18.4, -0.2, 0.2, 2.6, 0.34, -0.2, 1.1, -0.3, 0);
  crystal(ctx, -20.4, -0.2, -3.2, 2.2, 0.3, 0.3, 0.2, 0.3, 0);

  // log ramp up to Stump Isle
  log(ctx, -16.0, 0.35, -15.4, -26.6, 5.35, -21.0, 0.6, 4);
  stump(ctx, -32.0, -26.2, 5, 2.8, 3.6);
  boulder(ctx, -28.4, 5.6, -28.8, 1.1, 1.1, 1.0);
  tree(ctx, -35.2, -22.4, 5, 7.5, 0.6, 2.8, {});
  deck(ctx, -28.6, 6.9, -21.6, 1.0, 1.0, 0.2, true, 5);

  // floating cloud platforms over the Meadow
  cloudPlatform(ctx, -3.5, 12.4, 3.2, 2.3, 0.75);
  cloudPlatform(ctx, 5.6, 13.6, 0.9, 2.0, 0.7);
  cloudPlatform(ctx, -7.2, 14.8, -5.6, 2.1, 0.7);
  cloudPlatform(ctx, 2.2, 16.4, -9.6, 1.8, 0.6);

  // scattered rocks and logs
  boulder(ctx, -6.8, 0.2, 13.6, 0.95, 0.75, 0.85);
  boulder(ctx, 9.6, 0.2, 15.4, 0.85, 0.65, 0.95);
  boulder(ctx, -18.2, 0.3, -9.4, 1.05, 0.95, 1.1);
  boulder(ctx, 19.2, 0.3, -2.2, 1.15, 1.0, 1.05);
  boulder(ctx, -2.2, 0.1, -19.2, 0.9, 0.6, 1.0);
  log(ctx, -4.2, 0.42, 21.0, 2.2, 0.42, 21.6, 0.42);
  log(ctx, 17.5, 0.38, -6.5, 20.5, 0.38, 1.0, 0.38);
  stump(ctx, -8.6, -15.8, 0, 1.0, 1.0);
  stump(ctx, 8.4, 19.5, 0, 0.9, 0.7);

  // lantern shrooms (decor)
  const lanterns = [[-1, 11], [2.5, 10.5], [-4.5, 9.5], [-10, 1.5], [9.5, 2], [-3, -12], [12, -4], [-14, -4], [3, -20], [-21, 5],
    [20, 6], [-7, 18], [7, 17], [15, -16], [-16, -16], [-27, -24], [-33, -29], [-29, -20], [42, -1], [36, -7], [45, -7], [39, -11]];
  for (const [lx, lz] of lanterns) {
    const gy = lx < -24 ? 5 : lx > 30 ? 1.5 : 0;
    for (let i = 0; i < 3; i++) {
      lantern(ctx, lx + (ctx.rng() - 0.5) * 0.9, lz + (ctx.rng() - 0.5) * 0.9, gy, 0.7 + ctx.rng() * 0.8, ctx.rng() < 0.35);
    }
  }

  // far-away scenery (visual only) -------------------------------------
  ctx.solid = false;
  const far = [[95, 6, -40, 12], [-90, 18, -70, 10], [-120, -6, 30, 14], [70, 24, 80, 8], [-40, 30, -120, 9], [130, -12, 30, 13], [10, -8, -130, 11], [-75, 2, 95, 9]];
  for (const [fx, fy, fz, fr] of far) {
    island(ctx, fx, fy, fz, fr, fr * 0.8);
    const n = Math.round(fr / 4);
    for (let i = 0; i < n; i++) {
      const a = ctx.rng() * Math.PI * 2, d = ctx.rng() * fr * 0.6;
      const tx = fx + Math.cos(a) * d, tz = fz + Math.sin(a) * d;
      if (ctx.rng() < 0.5) tree(ctx, tx, tz, fy, 6 + ctx.rng() * 5, 0.6, 2.6 + ctx.rng() * 1.5, {});
      else mushroom(ctx, tx, tz, fy, 2 + ctx.rng() * 5, 1.5 + ctx.rng() * 2.5, 0.8 + ctx.rng(), ['tan', 'red', 'violet', 'bouncy'][Math.floor(ctx.rng() * 4)]);
    }
  }
  for (let i = 0; i < 26; i++) {
    const a = ctx.rng() * Math.PI * 2, d = 35 + ctx.rng() * 120;
    cloudDecor(ctx, Math.cos(a) * d, -22 + ctx.rng() * 50 - (d < 60 ? 14 : 0), Math.sin(a) * d, 4 + ctx.rng() * 7);
  }
  ctx.solid = true;

  // materials & merged meshes ------------------------------------------
  const mats = {
    solid: new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true }),
    glow: new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true, emissive: 0x4a4a70 }),
    cloud: new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true, emissive: 0x6a5a78 }),
  };
  B.finish(scene, mats);

  // grass tufts and flowers (instanced, no collision)
  const solidNear = [];
  const clearOfProps = (x, y, z, r) => {
    W.gather(x, y, z, r + 0.5, solidNear);
    for (const c of solidNear) {
      if (c.tag === 'island') continue;
      if (W.sdf(x, y, z, [c]) < r) return false;
    }
    return true;
  };
  const spots = [];
  for (const reg of ctx.regions) {
    const count = Math.round(reg.r * reg.r * 1.6);
    for (let i = 0; i < count; i++) {
      const a = ctx.rng() * Math.PI * 2, d = Math.sqrt(ctx.rng()) * (reg.r - 0.6);
      const x = reg.cx + Math.cos(a) * d, z = reg.cz + Math.sin(a) * d;
      if (clearOfProps(x, reg.y + 0.1, z, 0.12)) spots.push([x, reg.y, z]);
    }
  }
  const tuftGeo = new THREE.ConeGeometry(0.06, 0.26, 3, 1);
  tuftGeo.translate(0, 0.12, 0);
  const tufts = new THREE.InstancedMesh(tuftGeo, new THREE.MeshLambertMaterial({ flatShading: true }), spots.length);
  const flowerGeo = new THREE.IcosahedronGeometry(0.055, 0);
  const flowerCount = Math.floor(spots.length / 5);
  const flowers = new THREE.InstancedMesh(flowerGeo, new THREE.MeshLambertMaterial({ flatShading: true, emissive: 0x332233 }), flowerCount);
  const m4 = new THREE.Matrix4(), q4 = new THREE.Quaternion(), s4 = new THREE.Vector3(), p4 = new THREE.Vector3(), e4 = new THREE.Euler();
  const flowerCols = [0xff7aa8, 0xffe066, 0xffffff, 0x9fd8ff, 0xffa36c, 0xd59bff].map((h) => new THREE.Color(h));
  let fi = 0;
  spots.forEach(([x, y, z], i) => {
    e4.set((ctx.rng() - 0.5) * 0.5, ctx.rng() * 6, (ctx.rng() - 0.5) * 0.5);
    q4.setFromEuler(e4);
    const s = 0.7 + ctx.rng() * 0.9;
    m4.compose(p4.set(x, y, z), q4, s4.set(s, s * (0.8 + ctx.rng() * 0.6), s));
    tufts.setMatrixAt(i, m4);
    tc.copy(PAL.grass2).lerp(PAL.grass3, ctx.rng() * 0.8).multiplyScalar(0.85 + ctx.rng() * 0.25);
    tufts.setColorAt(i, tc);
    if (i % 5 === 0 && fi < flowerCount) {
      m4.compose(p4.set(x + 0.05, y + 0.14 + ctx.rng() * 0.08, z), q4, s4.set(1, 0.7, 1));
      flowers.setMatrixAt(fi, m4);
      flowers.setColorAt(fi, flowerCols[Math.floor(ctx.rng() * flowerCols.length)]);
      fi++;
    }
  });
  scene.add(tufts, flowers);

  // sky ----------------------------------------------------------------
  const sunDir = new THREE.Vector3(-0.62, 0.42, 0.66).normalize();
  const sky = new THREE.Mesh(
    new THREE.SphereGeometry(420, 32, 16),
    new THREE.ShaderMaterial({
      side: THREE.BackSide, depthWrite: false, fog: false,
      uniforms: {
        top: { value: new THREE.Color(0x4f86e8) },
        horizon: { value: new THREE.Color(0xffc8a2) },
        bottom: { value: new THREE.Color(0xd99bc6) },
        sunDir: { value: sunDir },
        sunColor: { value: new THREE.Color(0xfff0c8) },
      },
      vertexShader: 'varying vec3 vDir; void main(){ vDir = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: `uniform vec3 top; uniform vec3 horizon; uniform vec3 bottom; uniform vec3 sunDir; uniform vec3 sunColor; varying vec3 vDir;
        void main(){ vec3 d = normalize(vDir); float h = d.y;
          vec3 c = h > 0.0 ? mix(horizon, top, pow(min(h * 1.4, 1.0), 0.55)) : mix(horizon, bottom, pow(min(-h * 2.0, 1.0), 0.6));
          float s = max(dot(d, sunDir), 0.0);
          c += sunColor * (pow(s, 900.0) * 4.0 + pow(s, 24.0) * 0.45 + pow(s, 4.0) * 0.12);
          gl_FragColor = vec4(c, 1.0);
          #include <colorspace_fragment>
        }`,
    })
  );
  sky.renderOrder = -10;
  sky.frustumCulled = false;
  scene.add(sky);
  scene.fog = new THREE.Fog(0xf7c9ad, 55, 240);
  scene.background = new THREE.Color(0xf7c9ad);

  const hemi = new THREE.HemisphereLight(0xd6ecff, 0x9a7055, 1.9);
  const sun = new THREE.DirectionalLight(0xffe2bf, 2.5);
  sun.position.copy(sunDir).multiplyScalar(50);
  scene.add(hemi, sun);

  // cloud sea far below
  const sea = new THREE.Mesh(new THREE.CircleGeometry(400, 48), new THREE.MeshBasicMaterial({ color: 0xf6dbe8 }));
  sea.rotation.x = -Math.PI / 2;
  sea.position.y = -38;
  scene.add(sea);

  // lava (only shown in Lava Rise)
  const lavaMat = new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uA: { value: new THREE.Color(0xff4a12) }, uB: { value: new THREE.Color(0xffd34d) }, uC: { value: new THREE.Color(0x861400) } },
    vertexShader: 'varying vec2 vW; void main(){ vec4 w = modelMatrix * vec4(position,1.0); vW = w.xz; gl_Position = projectionMatrix * viewMatrix * w; }',
    fragmentShader: `uniform float uTime; uniform vec3 uA; uniform vec3 uB; uniform vec3 uC; varying vec2 vW;
      float h(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
      float n(vec2 p){ vec2 i = floor(p), f = fract(p); vec2 u = f*f*(3.0-2.0*f);
        return mix(mix(h(i), h(i+vec2(1.0,0.0)), u.x), mix(h(i+vec2(0.0,1.0)), h(i+vec2(1.0,1.0)), u.x), u.y); }
      void main(){ vec2 p = vW * 0.22; float t = uTime * 0.3;
        float a = n(p + vec2(t, -t * 0.7)) * 0.6 + n(p * 2.3 - vec2(t * 1.3, t)) * 0.4;
        float crack = 1.0 - smoothstep(0.0, 0.06, abs(a - 0.5));
        vec3 c = mix(uC, uA, smoothstep(0.2, 0.75, a));
        c = mix(c, uB, clamp(crack * 0.9 + pow(a, 5.0), 0.0, 1.0));
        gl_FragColor = vec4(c, 1.0);
        #include <colorspace_fragment>
      }`,
  });
  const lava = new THREE.Mesh(new THREE.CircleGeometry(300, 64), lavaMat);
  lava.rotation.x = -Math.PI / 2;
  lava.position.y = -40;
  lava.visible = false;
  scene.add(lava);

  const groundTint = new THREE.Color(0x9a7055), lavaTint = new THREE.Color(0xff6a2a);

  return {
    phys: W,
    perches: ctx.perches,
    regions: ctx.regions,
    spawn: new THREE.Vector3(0, 1.5, 17.5),
    kiosk: { x: -1.9, z: 14.1, rotY: 0.5 },
    sunDir,
    lavaY: -40,
    setLava(y, visible) {
      this.lavaY = y;
      lava.position.y = y;
      lava.visible = visible;
      hemi.groundColor.copy(groundTint).lerp(lavaTint, visible ? THREE.MathUtils.clamp((y + 4) / 8, 0, 0.8) : 0);
    },
    update(dt, time, camPos) {
      sky.position.copy(camPos);
      lavaMat.uniforms.uTime.value = time;
    },
  };
}
