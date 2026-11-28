// Fuzzlings: AI players that gallop on their hands, hop, pounce and leap
// along the nav graph. The game sets an intent (chase / flee / goto / wander)
// and the bot works out how to get there.
import * as THREE from 'three';
import { G } from './physics.js';
import { BOT_R } from './nav.js';

export const BOT_PROFILES = [
  { name: 'Pip', color: 0xff6b6b, hat: 'cap' },
  { name: 'Moss', color: 0x6fcf7f, hat: 'leaf' },
  { name: 'Biscuit', color: 0xf4a259, hat: 'tuft' },
  { name: 'Zuzu', color: 0xa78bfa, hat: 'antenna' },
  { name: 'Nib', color: 0x4cc9f0, hat: 'horns' },
  { name: 'Tumble', color: 0xffd166, hat: 'bow' },
  { name: 'Fizz', color: 0x2ec4b6, hat: 'antenna' },
  { name: 'Pebble', color: 0xb9b3d6, hat: 'cap' },
  { name: 'Waffle', color: 0xc88a5a, hat: 'leaf' },
];

const UP = new THREE.Vector3(0, 1, 0);
const WHITE = new THREE.Color(0xffffff), BLACK = new THREE.Color(0x1d1530), MOUTH = new THREE.Color(0x5a1f2e);

function colored(geo, color, x = 0, y = 0, z = 0, sx = 1, sy = 1, sz = 1, rx = 0, ry = 0, rz = 0) {
  const g = geo.index ? geo.toNonIndexed() : geo;
  for (const k of Object.keys(g.attributes)) if (k !== 'position') g.deleteAttribute(k);
  g.scale(sx, sy, sz);
  if (rx || ry || rz) g.applyQuaternion(new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, ry, rz)));
  g.translate(x, y, z);
  const n = g.attributes.position.count, c = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) { c[i * 3] = color.r; c[i * 3 + 1] = color.g; c[i * 3 + 2] = color.b; }
  g.setAttribute('color', new THREE.BufferAttribute(c, 3));
  return g;
}

function merge(parts) {
  // tiny local merge to avoid importing utils here
  let total = 0;
  for (const p of parts) total += p.attributes.position.count;
  const pos = new Float32Array(total * 3), colr = new Float32Array(total * 3);
  let o = 0;
  for (const p of parts) {
    pos.set(p.attributes.position.array, o * 3);
    colr.set(p.attributes.color.array, o * 3);
    o += p.attributes.position.count;
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('color', new THREE.BufferAttribute(colr, 3));
  g.computeVertexNormals();
  return g;
}

let shared = null;
function getShared() {
  if (shared) return shared;
  const eyes = [];
  for (const s of [-1, 1]) {
    eyes.push(colored(new THREE.IcosahedronGeometry(0.095, 1), WHITE, s * 0.13, 0, 0.27));
    eyes.push(colored(new THREE.IcosahedronGeometry(0.05, 1), BLACK, s * 0.13, 0.005, 0.355));
    eyes.push(colored(new THREE.IcosahedronGeometry(0.017, 0), WHITE, s * 0.13 + 0.017, 0.025, 0.4));
  }
  const body = new THREE.IcosahedronGeometry(BOT_R, 2);
  {
    const p = body.attributes.position.array;
    for (let i = 0; i < p.length; i += 3) {
      const h = Math.sin(p[i] * 91.3 + p[i + 1] * 47.1 + p[i + 2] * 13.7) * 43758.5;
      const k = 1 + (h - Math.floor(h) - 0.5) * 0.09;
      p[i] *= k; p[i + 1] *= k; p[i + 2] *= k;
    }
    body.computeVertexNormals();
  }
  const hand = new THREE.IcosahedronGeometry(0.095, 1);
  hand.scale(1, 0.85, 1.1);
  const arm = new THREE.CylinderGeometry(0.038, 0.055, 1, 6, 1);
  arm.translate(0, 0.5, 0);
  const shadowTex = (() => {
    const c = document.createElement('canvas'); c.width = c.height = 64;
    const g = c.getContext('2d');
    const gr = g.createRadialGradient(32, 32, 2, 32, 32, 31);
    gr.addColorStop(0, 'rgba(0,0,0,0.55)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
    return new THREE.CanvasTexture(c);
  })();
  const star = new THREE.OctahedronGeometry(0.06, 0);
  shared = {
    eyes: merge(eyes),
    body,
    hand, arm, star,
    ring: new THREE.TorusGeometry(0.27, 0.035, 6, 24).rotateX(Math.PI / 2),
    vcMat: new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true }),
    starMat: new THREE.MeshBasicMaterial({ color: 0xffe066 }),
    shadowGeo: new THREE.CircleGeometry(0.42, 16).rotateX(-Math.PI / 2),
    shadowMat: new THREE.MeshBasicMaterial({ map: shadowTex, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 }),
  };
  return shared;
}

function hatGeometry(kind, color) {
  const dark = color.clone().multiplyScalar(0.65);
  const parts = [colored(new THREE.IcosahedronGeometry(0.06, 1), MOUTH, 0, -0.085, 0.335, 1, 0.42, 0.5)];
  const top = BOT_R * 0.93;
  if (kind === 'cap') {
    parts.push(colored(new THREE.SphereGeometry(0.2, 12, 4, 0, Math.PI * 2, 0, Math.PI / 2), new THREE.Color(0xea5a43), 0, top - 0.02, -0.02, 1, 0.65, 1));
    for (const [x, z] of [[0.08, 0.05], [-0.07, -0.08], [0, 0.12], [-0.1, 0.07]]) parts.push(colored(new THREE.IcosahedronGeometry(0.03, 0), WHITE, x, top + 0.085, z - 0.02, 1, 0.5, 1));
  } else if (kind === 'leaf') {
    parts.push(colored(new THREE.CylinderGeometry(0.012, 0.016, 0.12, 4), new THREE.Color(0x4a7a2a), 0, top + 0.05, 0));
    parts.push(colored(new THREE.IcosahedronGeometry(0.1, 1), new THREE.Color(0x5cc06b), 0.07, top + 0.13, 0, 1.1, 0.25, 0.55, 0, 0, -0.5));
  } else if (kind === 'antenna') {
    parts.push(colored(new THREE.CylinderGeometry(0.012, 0.014, 0.24, 4), dark, 0, top + 0.11, 0));
    parts.push(colored(new THREE.IcosahedronGeometry(0.045, 1), new THREE.Color(0xfff2a8), 0, top + 0.25, 0));
  } else if (kind === 'horns') {
    for (const s of [-1, 1]) parts.push(colored(new THREE.ConeGeometry(0.05, 0.16, 6), new THREE.Color(0xfff1dc), s * 0.15, top + 0.02, 0, 1, 1, 1, 0, 0, -s * 0.5));
  } else if (kind === 'tuft') {
    for (let i = 0; i < 3; i++) parts.push(colored(new THREE.ConeGeometry(0.045, 0.16, 4), dark, (i - 1) * 0.06, top + 0.05, 0.02 - Math.abs(i - 1) * 0.03, 1, 1, 1, 0.2, 0, (i - 1) * -0.5));
  } else if (kind === 'bow') {
    for (const s of [-1, 1]) parts.push(colored(new THREE.ConeGeometry(0.06, 0.13, 5), new THREE.Color(0xff6fb1), s * 0.07, top + 0.05, 0, 1, 1, 0.6, 0, 0, s * Math.PI / 2));
    parts.push(colored(new THREE.IcosahedronGeometry(0.035, 0), new THREE.Color(0xff9acb), 0, top + 0.05, 0));
  }
  return merge(parts);
}

function nameTag(text, color) {
  const c = document.createElement('canvas'); c.width = 256; c.height = 64;
  const g = c.getContext('2d');
  g.fillStyle = 'rgba(25,15,45,0.6)';
  g.beginPath();
  g.moveTo(42, 8); g.arcTo(238, 8, 238, 56, 24); g.arcTo(238, 56, 18, 56, 24); g.arcTo(18, 56, 18, 8, 24); g.arcTo(18, 8, 238, 8, 24);
  g.closePath(); g.fill();
  g.fillStyle = '#' + color.getHexString();
  g.beginPath(); g.arc(44, 32, 10, 0, Math.PI * 2); g.fill();
  g.font = '600 32px Fredoka, "Trebuchet MS", sans-serif';
  g.fillStyle = '#fff7ec'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(text, 138, 34);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
  s.scale.set(0.64, 0.16, 1);
  return s;
}

function lerpAngle(a, b, t) {
  let d = b - a;
  while (d > Math.PI) d -= Math.PI * 2;
  while (d < -Math.PI) d += Math.PI * 2;
  return a + d * t;
}

export class Bot {
  constructor(index, profile, ctx) {
    this.scene = ctx.scene; this.phys = ctx.phys; this.nav = ctx.nav; this.sfx = ctx.sfx; this.fx = ctx.fx;
    this.isBot = true;
    this.index = index;
    this.name = profile.name;
    this.color = new THREE.Color(profile.color);
    this.hat = profile.hat;
    this.pos = new THREE.Vector3();
    this.bodyPos = this.pos;
    this.vel = new THREE.Vector3();
    this.desired = new THREE.Vector3();
    this.facing = Math.random() * Math.PI * 2;
    this.groundTime = -10; this.jumping = false; this.jumpStart = 0; this.jumpTo = -1; this.hopTimer = 0;
    this.path = null; this.pathIdx = 0; this.goal = -1; this.replanAt = 0;
    this.fleeNode = -1; this.fleeAt = 0; this.wanderNode = -1; this.wanderAt = 0;
    this.lungeAt = 0; this.stuckAt = 0; this.stuckRef = new THREE.Vector3();
    this.losAt = 0; this.losOk = false;
    this.intent = { type: 'wander', target: null, node: -1 };
    this.skill = 1; this.speedMult = 1;
    this.personal = 0.92 + Math.random() * 0.16;
    this.it = false; this.infected = false; this.alive = true; this.ghost = false;
    this.score = 0; this.itTime = 0; this.tags = 0; this.stunUntil = 0; this.immuneUntil = 0; this.outTime = 0; this.infectedAt = 0;
    this.active = true;
    this.spheres = [{ x: 0, y: 0, z: 0, r: BOT_R + 0.03 }, { x: 0, y: 0, z: 0, r: 0.1 }, { x: 0, y: 0, z: 0, r: 0.1 }];
    this.near = [];
    this.res = { hit: false, ground: false, impact: 0, col: null, groundCol: null, nx: 0, ny: 1, nz: 0, x: 0, y: 0, z: 0, t: 0 };
    this.launchV = { x: 0, y: 0, z: 0 };
    this.animPhase = Math.random() * 6; this.blinkAt = 1 + Math.random() * 3; this.blinkEnd = 0;
    this.hands = [{ pos: new THREE.Vector3(), t: new THREE.Vector3() }, { pos: new THREE.Vector3(), t: new THREE.Vector3() }];
    this.shadowAt = 0; this.shadowY = 0;
    this.lastChirp = 0;
    this._buildVisual();
  }

  _buildVisual() {
    const S = getShared();
    this.root = new THREE.Group();
    this.bodyMat = new THREE.MeshLambertMaterial({ color: this.color, flatShading: true });
    this.body = new THREE.Mesh(S.body, this.bodyMat);
    this.root.add(this.body);
    this.eyes = new THREE.Mesh(S.eyes, S.vcMat);
    this.eyes.position.set(0, 0.08, 0);
    this.body.add(this.eyes);
    this.hatMesh = new THREE.Mesh(hatGeometry(this.hat, this.color), S.vcMat);
    this.body.add(this.hatMesh);
    this.ringMat = new THREE.MeshBasicMaterial({ color: 0xff7a2f });
    this.ring = new THREE.Mesh(S.ring, this.ringMat);
    this.ring.position.y = 0.62;
    this.ring.visible = false;
    this.root.add(this.ring);
    this.stars = new THREE.Group();
    for (let i = 0; i < 3; i++) {
      const s = new THREE.Mesh(S.star, S.starMat);
      const a = (i / 3) * Math.PI * 2;
      s.position.set(Math.cos(a) * 0.26, 0, Math.sin(a) * 0.26);
      this.stars.add(s);
    }
    this.stars.position.y = 0.5;
    this.stars.visible = false;
    this.root.add(this.stars);
    this.tag = nameTag(this.name, this.color);
    this.tag.position.y = 0.82;
    this.root.add(this.tag);
    this.handMat = new THREE.MeshLambertMaterial({ color: this.color.clone().multiplyScalar(0.72), flatShading: true });
    this.handMeshes = this.hands.map(() => new THREE.Mesh(S.hand, this.handMat));
    this.armMeshes = this.hands.map(() => new THREE.Mesh(S.arm, this.handMat));
    this.shadow = new THREE.Mesh(S.shadowGeo, S.shadowMat);
    this.scene.add(this.root, ...this.handMeshes, ...this.armMeshes, this.shadow);
  }

  setActive(on) {
    this.active = on;
    this._setVisible(on && this.alive);
  }

  _setVisible(v) {
    this.root.visible = v;
    this.shadow.visible = v;
    for (const m of this.handMeshes) m.visible = v;
    for (const m of this.armMeshes) m.visible = v;
  }

  setAlive(a) { this.alive = a; this._setVisible(a && this.active); }

  setStatusLook(kind) {
    this.bodyMat.emissive.setHex(kind === 'it' ? 0xff4a10 : kind === 'infected' ? 0x2fd65a : 0x000000);
    this.bodyMat.emissiveIntensity = kind === 'it' ? 0.42 : kind === 'infected' ? 0.38 : 0;
    this.bodyMat.color.copy(this.color);
    if (kind === 'infected') this.bodyMat.color.lerp(new THREE.Color(0x7dff8a), 0.45);
    this.ring.visible = kind === 'it' || kind === 'infected';
    this.ringMat.color.setHex(kind === 'infected' ? 0x6dff7a : 0xff8a2a);
  }

  placeAt(node) {
    const n = this.nav.nodes[node];
    this.pos.set(n.x + (Math.random() - 0.5) * 0.5, n.y + 0.2, n.z + (Math.random() - 0.5) * 0.5);
    this.vel.set(0, 0, 0);
    this.jumping = false; this.path = null; this.goal = -1;
    for (const h of this.hands) h.pos.copy(this.pos);
  }

  isGrounded(now) { return now - this.groundTime < 0.1; }

  _startJump(now, to) {
    this.jumping = true; this.jumpStart = now; this.jumpTo = to; this.groundTime = -10;
  }

  _los(now, tp) {
    if (now < this.losAt) return this.losOk;
    this.losAt = now + 0.2;
    const p = this.pos;
    this.phys.gather((p.x + tp.x) / 2, (p.y + tp.y) / 2, (p.z + tp.z) / 2, p.distanceTo(tp) / 2 + 1, this.near);
    this.losOk = this.phys.segmentClear(this.near, p.x, p.y + 0.1, p.z, tp.x, tp.y, tp.z, 0.16, 0.4);
    return this.losOk;
  }

  _steerTo(x, z, spd, arrive) {
    const dx = x - this.pos.x, dz = z - this.pos.z;
    const dist = Math.hypot(dx, dz);
    if (dist > 0.05) {
      const s = arrive ? spd * Math.min(1, 0.25 + dist * 0.5) : spd;
      if (!(arrive && dist < 0.35)) this.desired.set((dx / dist) * s, 0, (dz / dist) * s);
    }
    return dist;
  }

  _pickFlee(tp) {
    const nav = this.nav, p = this.pos;
    let best = -1, bs = -1e9;
    const tx = tp.x - p.x, tz = tp.z - p.z, tl = Math.hypot(tx, tz) || 1;
    for (let k = 0; k < 22; k++) {
      const i = nav.randomGood();
      const n = nav.nodes[i];
      const dMe = Math.hypot(n.x - p.x, n.z - p.z);
      if (dMe > 20) continue;
      const dT = Math.hypot(n.x - tp.x, n.z - tp.z) + Math.max(0, n.y - tp.y) * 0.8;
      let s = dT - dMe * 0.3 + (n.kind ? 1.2 : 0) + Math.random() * 2.5;
      const dot = ((n.x - p.x) * tx + (n.z - p.z) * tz) / ((dMe || 1) * tl);
      if (dot > 0.4) s -= 8;
      if (s > bs) { bs = s; best = i; }
    }
    return best;
  }

  _pickWander() {
    const nav = this.nav, p = this.pos;
    for (let k = 0; k < 12; k++) {
      const i = nav.randomGood();
      const n = nav.nodes[i];
      if (Math.hypot(n.x - p.x, n.z - p.z) < 16) return i;
    }
    return nav.randomGood();
  }

  _follow(now, goal, spd) {
    const nav = this.nav;
    if (goal < 0 || this.jumping) return;
    if (goal !== this.goal || !this.path || now > this.replanAt) {
      this.goal = goal;
      this.replanAt = now + 0.8 + Math.random() * 0.5;
      const start = nav.nearest(this.pos.x, this.pos.y, this.pos.z, false);
      this.path = nav.findPath(start, goal) || [];
      this.pathIdx = 0;
    }
    const p = this.pos;
    if (this.pathIdx >= this.path.length) {
      const g = nav.nodes[goal];
      this._steerTo(g.x, g.z, spd, true);
      return;
    }
    const e = this.path[this.pathIdx];
    const a = nav.nodes[e.from], b = nav.nodes[e.to];
    if (!e.jump) {
      if (this._steerTo(b.x, b.z, spd, false) < 0.9) this.pathIdx++;
      return;
    }
    const dA = Math.hypot(a.x - p.x, a.z - p.z);
    if (dA > 0.9 || Math.abs(a.y - p.y) > 0.9) {
      this._steerTo(a.x, a.z, spd, dA < 2);
      if (dA > 6 || Math.abs(a.y - p.y) > 2) this.replanAt = Math.min(this.replanAt, now + 0.25);
      return;
    }
    if (this.isGrounded(now)) {
      const T = nav.launch(p.x, p.y, p.z, b.x, b.y, b.z, this.launchV, 10, 12.5);
      if (T > 0) {
        this.vel.set(this.launchV.x, this.launchV.y, this.launchV.z);
        this._startJump(now, e.to);
        this.pathIdx++;
        if (Math.random() < 0.25) this._chirp(now, 1.0);
      } else this.replanAt = now;
    } else this._steerTo(a.x, a.z, spd * 0.5, true);
  }

  _chirp(now, pitch) {
    if (now - this.lastChirp < 0.8) return;
    this.lastChirp = now;
    this.sfx.chirp(this.pos, pitch * this.personal);
  }

  think(dt, now) {
    this.desired.set(0, 0, 0);
    if (now < this.stunUntil) return;
    const it = this.intent;
    const spd = 4.5 * this.skill * this.speedMult * this.personal;
    const grounded = this.isGrounded(now);
    if (it.type === 'chase' && it.target) {
      const t = it.target, tp = t.bodyPos;
      const lead = 0.3 * this.skill;
      const px = tp.x + t.vel.x * lead, pz = tp.z + t.vel.z * lead, py = tp.y;
      const dx = px - this.pos.x, dz = pz - this.pos.z, dy = py - this.pos.y;
      const dxz = Math.hypot(dx, dz) || 0.001;
      if (dxz < 7.5 && dy < 1.4 && dy > -2.5 && this._los(now, tp)) {
        this.path = null; this.goal = -1;
        this.desired.set((dx / dxz) * spd, 0, (dz / dxz) * spd);
        if (grounded && !this.jumping && now > this.lungeAt && dxz < 2.9 * this.skill) {
          const s = 5.2 + 1.6 * this.skill;
          this.vel.set((dx / dxz) * s, 3.3 + Math.max(0, dy) * 1.6, (dz / dxz) * s);
          this._startJump(now, -1);
          this.lungeAt = now + 1.0 + Math.random() * 0.6 / this.skill;
          this._chirp(now, 1.35);
        }
        return;
      }
      if (dy >= 1.4 && dy < 5 && dxz < 6.5 && grounded && !this.jumping && now > this.lungeAt) {
        const T = this.nav.launch(this.pos.x, this.pos.y, this.pos.z, px, py + 0.15, pz, this.launchV, 9.5, 12.5);
        if (T > 0) {
          this.vel.set(this.launchV.x, this.launchV.y, this.launchV.z);
          this._startJump(now, -1);
          this.lungeAt = now + 1.4 + Math.random() * 0.7;
          this._chirp(now, 1.15);
          return;
        }
      }
      this._follow(now, this.nav.nearest(px, py, pz), spd);
    } else if (it.type === 'flee' && it.target) {
      const tp = it.target.bodyPos;
      const dist = this.pos.distanceTo(tp);
      if (this.fleeNode < 0 || now > this.fleeAt || (dist < 4 && now > this.fleeAt - 1.2)) {
        this.fleeNode = this._pickFlee(tp);
        this.fleeAt = now + 1.8 + Math.random();
      }
      if (dist < 2.3 && grounded && !this.jumping && now > this.lungeAt && Math.random() < 0.6 * this.skill) {
        const ax = this.pos.x - tp.x, az = this.pos.z - tp.z, al = Math.hypot(ax, az) || 1;
        const side = Math.random() < 0.5 ? 1 : -1;
        const ux = ax / al, uz = az / al;
        const ex = ux * 0.8 - uz * side * 0.6, ez = uz * 0.8 + ux * side * 0.6;
        this.vel.set(ex * 6 * this.skill, 4.3, ez * 6 * this.skill);
        this._startJump(now, -1);
        this.lungeAt = now + 1.4;
        this._chirp(now, 1.7);
        return;
      }
      this._follow(now, this.fleeNode, spd);
    } else if (it.type === 'goto' && it.node >= 0) {
      this._follow(now, it.node, spd);
    } else if (it.type === 'idle') {
      // stand still
    } else {
      const n = this.wanderNode >= 0 ? this.nav.nodes[this.wanderNode] : null;
      if (!n || now > this.wanderAt || Math.hypot(n.x - this.pos.x, n.z - this.pos.z) < 1.2) {
        this.wanderNode = this._pickWander();
        this.wanderAt = now + 6 + Math.random() * 7;
      }
      this._follow(now, this.wanderNode, spd * 0.72);
    }
    // stuck? give a hop and replan
    if (now > this.stuckAt) {
      if (this.desired.lengthSq() > 1 && this.pos.distanceTo(this.stuckRef) < 0.6 && !this.jumping) {
        this.vel.y = 5.2;
        this.vel.x += (Math.random() - 0.5) * 4; this.vel.z += (Math.random() - 0.5) * 4;
        this._startJump(now, -1);
        this.replanAt = now; this.wanderNode = -1; this.fleeNode = -1;
      }
      this.stuckRef.copy(this.pos);
      this.stuckAt = now + 2.0;
    }
  }

  update(dt, now) {
    if (!this.active || !this.alive) return;
    this.think(dt, now);
    this._integrate(dt, now);
    this._animate(dt, now);
  }

  _integrate(dt, now) {
    const p = this.pos, v = this.vel, d = this.desired;
    const grounded = this.isGrounded(now);
    if (this.jumping) {
      if (this.jumpTo >= 0) {
        // gentle air control so long jumps land on target
        const b = this.nav.nodes[this.jumpTo];
        const disc = v.y * v.y + 2 * G * (p.y - b.y);
        if (disc > 0) {
          const tl = Math.max(0.12, (v.y + Math.sqrt(disc)) / G);
          const wx = (b.x - p.x) / tl, wz = (b.z - p.z) / tl;
          const acc = 6 * dt;
          let ax = wx - v.x, az = wz - v.z;
          const al = Math.hypot(ax, az);
          if (al > acc) { ax *= acc / al; az *= acc / al; }
          v.x += ax; v.z += az;
        }
      }
      if (now - this.jumpStart > 3) this.jumping = false;
    } else {
      const hopping = now - this.groundTime < 0.75;
      const acc = (grounded || hopping ? 26 : 4) * dt;
      let ax = d.x - v.x, az = d.z - v.z;
      const al = Math.hypot(ax, az);
      if (al > acc) { ax *= acc / al; az *= acc / al; }
      v.x += ax; v.z += az;
      if (grounded && d.x * d.x + d.z * d.z > 1.0) v.y = 2.2 + Math.random() * 0.5; // gallop hop
    }
    v.y -= G * dt;
    p.addScaledVector(v, dt);
    this.phys.gather(p.x, p.y, p.z, BOT_R + 0.6 + v.length() * dt, this.near);
    const res = this.res;
    if (this.phys.resolveSphere(this.near, p, BOT_R, v, res)) {
      if (res.col.mat.bounce && res.impact > 1.8 && res.ny > 0.3) {
        v.y = Math.max(v.y, 8.2 + Math.random() * 2.5);
        this._startJump(now, -1);
        this.sfx.boing(p, 0.55);
        this.fx.burst(p.x, p.y - BOT_R, p.z, 0xff7ab8, 8, 2.5, 0.5);
      } else if (res.ground) {
        if (this.jumping && now - this.jumpStart > 0.12) {
          this.jumping = false;
          if (this.jumpTo >= 0) {
            const b = this.nav.nodes[this.jumpTo];
            if (Math.hypot(b.x - p.x, b.z - p.z) > 1.6 || Math.abs(b.y - p.y) > 1) this.replanAt = now;
          }
          if (res.impact > 3) this.sfx.tap(res.col.mat.name, Math.min(0.7, res.impact / 10), p);
        }
        if (!this.jumping) this.groundTime = now;
      }
    }
    if (grounded && !this.jumping && d.x * d.x + d.z * d.z < 0.01) {
      const f = Math.max(0, 1 - 10 * dt);
      v.x *= f; v.z *= f;
    }
    if (p.y < -24) {
      this.placeAt(this.nav.randomGood());
      this.fx.burst(this.pos.x, this.pos.y, this.pos.z, 0xffffff, 12, 2, 0.6);
    }
  }

  _animate(dt, now) {
    const p = this.pos, v = this.vel;
    const hs = Math.hypot(v.x, v.z);
    let yawT = this.facing;
    const tgt = this.intent.target;
    const stunned = now < this.stunUntil;
    if (tgt && this.intent.type === 'chase' && p.distanceTo(tgt.bodyPos) < 6) {
      yawT = Math.atan2(tgt.bodyPos.x - p.x, tgt.bodyPos.z - p.z);
    } else if (hs > 0.6) yawT = Math.atan2(v.x, v.z);
    this.facing = stunned ? this.facing + dt * 9 : lerpAngle(this.facing, yawT, 1 - Math.exp(-10 * dt));
    this.root.position.copy(p);
    this.root.rotation.y = this.facing;
    const sy = THREE.MathUtils.clamp(1 + v.y * 0.035, 0.84, 1.2);
    const sxz = 1 / Math.sqrt(sy);
    this.body.scale.set(sxz, sy, sxz);
    this.body.rotation.x = Math.min(0.35, hs * 0.05);
    if (now > this.blinkAt) { this.blinkEnd = now + 0.12; this.blinkAt = now + 2 + Math.random() * 4; }
    this.eyes.scale.y = now < this.blinkEnd ? 0.12 : 1;
    this.stars.visible = stunned;
    if (stunned) this.stars.rotation.y = -this.facing + now * 6;
    if (this.ring.visible) { this.ring.rotation.y = now * 2.5; this.ring.position.y = 0.62 + Math.sin(now * 4) * 0.03; }

    // hands: gallop when running, reach up when airborne, rest when idle
    const fx = Math.sin(this.facing), fz = Math.cos(this.facing);
    const sx = Math.cos(this.facing), sz = -Math.sin(this.facing);
    const grounded = now - this.groundTime < 0.3 && !this.jumping;
    if (grounded && hs > 0.5) this.animPhase += (dt * hs) / 0.3;
    const reach = tgt && this.intent.type === 'chase' && p.distanceTo(tgt.bodyPos) < 2.2;
    const k = 1 - Math.exp(-26 * dt);
    for (let i = 0; i < 2; i++) {
      const sg = i ? 1 : -1;
      const ph = this.animPhase + i * Math.PI;
      let fo, up, so = 0.3;
      if (stunned) { fo = 0.05; up = 0.32 + Math.sin(now * 12 + i * 3) * 0.08; so = 0.24; }
      else if (reach) { fo = 0.5; up = 0.05 + Math.sin(now * 20 + i * 2) * 0.05; so = 0.2; }
      else if (!grounded) { fo = 0.12; up = 0.32; so = 0.42; }
      else if (hs > 0.5) { fo = 0.08 - Math.cos(ph) * 0.32; up = -BOT_R + 0.1 + Math.max(0, Math.sin(ph)) * 0.22; }
      else { fo = 0.14; up = -BOT_R + 0.09; so = 0.3; }
      const h = this.hands[i];
      h.t.set(p.x + fx * fo + sx * sg * so, p.y + up, p.z + fz * fo + sz * sg * so);
      h.pos.lerp(h.t, k);
      this.handMeshes[i].position.copy(h.pos);
      this.handMeshes[i].rotation.y = this.facing;
      const shx = p.x + sx * sg * 0.25, shy = p.y + 0.02, shz = p.z + sz * sg * 0.25;
      const dx = h.pos.x - shx, dy = h.pos.y - shy, dz = h.pos.z - shz;
      const len = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1e-4;
      const arm = this.armMeshes[i];
      arm.position.set(shx, shy, shz);
      arm.quaternion.setFromUnitVectors(UP, h.t.set(dx / len, dy / len, dz / len));
      arm.scale.set(1, Math.max(0.01, len - 0.05), 1);
    }
    const s = this.spheres;
    s[0].x = p.x; s[0].y = p.y; s[0].z = p.z;
    for (let i = 0; i < 2; i++) { const hp = this.hands[i].pos; s[1 + i].x = hp.x; s[1 + i].y = hp.y; s[1 + i].z = hp.z; }

    // blob shadow on whatever is below
    if (now > this.shadowAt) {
      this.shadowAt = now + 0.05;
      this.phys.gather(p.x, p.y - 3, p.z, 3.5, this.near);
      if (this.phys.sphereCast(this.near, p.x, p.y, p.z, p.x, p.y - 7, p.z, 0.05, this.res)) this.shadowY = this.res.y - 0.04;
      else this.shadowY = -100;
    }
    this.shadow.position.set(p.x, this.shadowY, p.z);
    const hgt = p.y - this.shadowY;
    const sc = THREE.MathUtils.clamp(1.2 - hgt * 0.12, 0.3, 1);
    this.shadow.scale.set(sc, 1, sc);
    this.shadow.visible = this.root.visible && this.shadowY > -50;
  }
}

// keep bots from stacking on top of each other
export function separateBots(bots) {
  for (let i = 0; i < bots.length; i++) {
    const a = bots[i];
    if (!a.active || !a.alive) continue;
    for (let j = i + 1; j < bots.length; j++) {
      const b = bots[j];
      if (!b.active || !b.alive) continue;
      const dx = b.pos.x - a.pos.x, dy = b.pos.y - a.pos.y, dz = b.pos.z - a.pos.z;
      const d2 = dx * dx + dy * dy + dz * dz;
      const min = BOT_R * 2;
      if (d2 < min * min && d2 > 1e-6) {
        const d = Math.sqrt(d2), push = (min - d) * 0.5;
        const nx = dx / d, nz = dz / d;
        a.pos.x -= nx * push; a.pos.z -= nz * push;
        b.pos.x += nx * push; b.pos.z += nz * push;
      }
    }
  }
}
