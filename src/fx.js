// Pooled particle bursts (tags, bounces, dust) and drifting ambient spores.
import * as THREE from 'three';

function dotTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d');
  const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  gr.addColorStop(0, 'rgba(255,255,255,1)');
  gr.addColorStop(0.35, 'rgba(255,255,255,0.7)');
  gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}

const DUST = { grass: 0x9fe07a, wood: 0xd9a56a, stone: 0xc9c3e0, cap: 0xf3d6b0, leaf: 0x7fdc7a, crystal: 0x9ff4ff, cloud: 0xffffff, shroom: 0xff8cc6 };

export class FX {
  constructor(scene) {
    const N = (this.N = 600);
    this.pos = new Float32Array(N * 3);
    this.col = new Float32Array(N * 3);
    this.base = new Float32Array(N * 3);
    this.vel = new Float32Array(N * 3);
    this.life = new Float32Array(N);
    this.max = new Float32Array(N);
    for (let i = 0; i < N; i++) this.pos[i * 3 + 1] = -1000;
    this.next = 0;
    const tex = dotTexture();
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('color', new THREE.BufferAttribute(this.col, 3).setUsage(THREE.DynamicDrawUsage));
    this.points = new THREE.Points(g, new THREE.PointsMaterial({ size: 0.11, map: tex, vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    this.points.frustumCulled = false;
    scene.add(this.points);

    // ambient spores floating over the Meadow
    const M = (this.M = 280);
    this.sp = new Float32Array(M * 3);
    this.spBase = new Float32Array(M * 3);
    this.spPh = new Float32Array(M);
    const sc = new Float32Array(M * 3);
    const tints = [[1, 0.95, 0.7], [0.75, 1, 0.85], [1, 0.8, 0.95]];
    for (let i = 0; i < M; i++) {
      const a = Math.random() * Math.PI * 2, d = Math.sqrt(Math.random()) * 30;
      this.spBase[i * 3] = Math.cos(a) * d;
      this.spBase[i * 3 + 1] = 0.6 + Math.random() * 16;
      this.spBase[i * 3 + 2] = Math.sin(a) * d;
      this.spPh[i] = Math.random() * 100;
      const t = tints[i % 3], k = 0.35 + Math.random() * 0.35;
      sc[i * 3] = t[0] * k; sc[i * 3 + 1] = t[1] * k; sc[i * 3 + 2] = t[2] * k;
    }
    const g2 = new THREE.BufferGeometry();
    g2.setAttribute('position', new THREE.BufferAttribute(this.sp, 3).setUsage(THREE.DynamicDrawUsage));
    g2.setAttribute('color', new THREE.BufferAttribute(sc, 3));
    this.spores = new THREE.Points(g2, new THREE.PointsMaterial({ size: 0.07, map: tex, vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    this.spores.frustumCulled = false;
    scene.add(this.spores);
    this._c = new THREE.Color();
  }

  burst(x, y, z, color, count = 12, speed = 3, life = 0.6) {
    const c = this._c.set(color);
    for (let k = 0; k < count; k++) {
      const i = this.next;
      this.next = (this.next + 1) % this.N;
      const u = Math.random() * 2 - 1, a = Math.random() * Math.PI * 2, r = Math.sqrt(1 - u * u);
      const s = speed * (0.4 + Math.random() * 0.6);
      this.pos[i * 3] = x; this.pos[i * 3 + 1] = y; this.pos[i * 3 + 2] = z;
      this.vel[i * 3] = r * Math.cos(a) * s; this.vel[i * 3 + 1] = Math.abs(u) * s * 0.8 + s * 0.3; this.vel[i * 3 + 2] = r * Math.sin(a) * s;
      const j = 0.8 + Math.random() * 0.4;
      this.base[i * 3] = c.r * j; this.base[i * 3 + 1] = c.g * j; this.base[i * 3 + 2] = c.b * j;
      this.life[i] = this.max[i] = life * (0.6 + Math.random() * 0.6);
    }
  }

  dust(x, y, z, mat, s) {
    this.burst(x, y, z, DUST[mat] || 0xffffff, Math.round(3 + s * 6), 1.2 + s * 1.5, 0.45);
  }

  update(dt, time) {
    const N = this.N, p = this.pos, v = this.vel, c = this.col, b = this.base;
    for (let i = 0; i < N; i++) {
      if (this.life[i] <= 0) continue;
      this.life[i] -= dt;
      if (this.life[i] <= 0) { p[i * 3 + 1] = -1000; c[i * 3] = c[i * 3 + 1] = c[i * 3 + 2] = 0; continue; }
      v[i * 3 + 1] -= 4 * dt;
      const drag = 1 - 1.5 * dt;
      v[i * 3] *= drag; v[i * 3 + 1] *= drag; v[i * 3 + 2] *= drag;
      p[i * 3] += v[i * 3] * dt; p[i * 3 + 1] += v[i * 3 + 1] * dt; p[i * 3 + 2] += v[i * 3 + 2] * dt;
      const k = this.life[i] / this.max[i];
      c[i * 3] = b[i * 3] * k; c[i * 3 + 1] = b[i * 3 + 1] * k; c[i * 3 + 2] = b[i * 3 + 2] * k;
    }
    this.points.geometry.attributes.position.needsUpdate = true;
    this.points.geometry.attributes.color.needsUpdate = true;
    const sp = this.sp, sb = this.spBase;
    for (let i = 0; i < this.M; i++) {
      const ph = this.spPh[i] + time * 0.25;
      sp[i * 3] = sb[i * 3] + Math.sin(ph) * 1.2;
      sp[i * 3 + 1] = sb[i * 3 + 1] + Math.sin(ph * 0.7 + 1) * 0.8;
      sp[i * 3 + 2] = sb[i * 3 + 2] + Math.cos(ph * 0.9) * 1.2;
    }
    this.spores.geometry.attributes.position.needsUpdate = true;
  }
}
