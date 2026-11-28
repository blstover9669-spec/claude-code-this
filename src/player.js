// The player: arm-powered locomotion in VR (hands are solid; pushing on the
// world moves your body, letting go keeps your momentum) plus a simple
// keyboard/mouse fallback for desktop.
import * as THREE from 'three';
import { G, sdfOne } from './physics.js';

export const HEAD_R = 0.2;
export const HAND_R = 0.05;
const MAX_ARM = 1.3;       // hands can't be further than this from the head
const UNSTICK = 0.9;       // a stuck hand lets go if pulled this far
const RELEASE = 0.012;     // lifting a hand this far off a surface releases it
const VEL_WINDOW = 0.085;  // seconds of body motion averaged for a throw
const VEL_LIMIT = 0.45;    // slower than this on release = just drop
const JUMP_MULT = 1.15;
const MAX_JUMP = 7.2;
const MAX_SPEED = 18;
export const HAND_OFFSET = new THREE.Vector3(0, -0.01, -0.03); // grip origin -> knuckles

export const PLAYER_COLORS = [0x5ec8ff, 0xff9f43, 0x7bed9f, 0xff6b9a, 0xc59bff, 0xfff176, 0xf4f1ea, 0x3d4f73];
const UP = new THREE.Vector3(0, 1, 0);

function makeRes() { return { x: 0, y: 0, z: 0, nx: 0, ny: 1, nz: 0, col: null, t: 0, hit: false, ground: false, impact: 0, groundCol: null }; }

export class Player {
  constructor({ scene, rig, camera, phys, sfx, fx }) {
    this.scene = scene; this.rig = rig; this.camera = camera; this.phys = phys; this.sfx = sfx; this.fx = fx;
    this.isBot = false;
    this.name = 'YOU';
    this.colorIdx = 0;
    this.color = new THREE.Color(PLAYER_COLORS[0]);

    this.rigPos = new THREE.Vector3();
    this.yaw = 0;
    this.rigQuat = new THREE.Quaternion();
    this.vel = new THREE.Vector3();
    this.head = new THREE.Vector3(0, 1, 0);
    this.headLocal = new THREE.Vector3(0, 1.3, 0);
    this.headQuatLocal = new THREE.Quaternion();
    this.headQuat = new THREE.Quaternion();
    this.bodyPos = new THREE.Vector3();
    this.hands = [this._makeHand(0), this._makeHand(1)];
    this.near = [];
    this.res = makeRes(); this.res2 = makeRes();
    this.corr = new THREE.Vector3();
    this.tmpV = new THREE.Vector3(); this.tmpN = { x: 0, y: 1, z: 0 }; this.tmpHead = new THREE.Vector3();
    this.histT = new Float64Array(24); this.histX = new Float64Array(24); this.histY = new Float64Array(24); this.histZ = new Float64Array(24);
    this.histN = 0; this.histI = 0;
    this.bounceLock = 0;
    this.lastLand = 0;
    this.snapTurn = true;
    this.stickReady = true;
    this.speedMult = 1;
    this.needsSpawn = true;
    this.spawnPoint = new THREE.Vector3(0, 1.5, 17.5);
    this.mode = 'none';
    this.airTime = 0;

    // game state (shared shape with bots)
    this.it = false; this.infected = false; this.alive = true; this.ghost = false;
    this.score = 0; this.itTime = 0; this.tags = 0; this.stunUntil = 0; this.immuneUntil = 0; this.outTime = 0; this.infectedAt = 0;
    this.spheres = [{ x: 0, y: 0, z: 0, r: 0.24 }, { x: 0, y: 0, z: 0, r: 0.26 }, { x: 0, y: 0, z: 0, r: 0.075 }, { x: 0, y: 0, z: 0, r: 0.075 }];

    // desktop state
    this.dBody = new THREE.Vector3();
    this.dYaw = 0; this.dPitch = 0;
    this.dGroundTime = -1; this.dJumpTime = -1; this.dWall = false; this.dWallN = new THREE.Vector3();
    this.dPhase = 0; this.dSlap = 0; this.dClimbSfx = 0;
    this.camEuler = new THREE.Euler(0, 0, 0, 'YXZ');

    this._buildVisuals();
  }

  _makeHand(side) {
    return {
      side, tracked: false,
      local: new THREE.Vector3(side ? 0.22 : -0.22, 0.75, -0.25),
      quatLocal: new THREE.Quaternion(),
      worldQuat: new THREE.Quaternion(),
      pos: new THREE.Vector3(), prev: new THREE.Vector3(), target: new THREE.Vector3(),
      contact: false, anchor: new THREE.Vector3(), normal: new THREE.Vector3(0, 1, 0), col: null,
      corr: new THREE.Vector3(), lift: 0,
      bounceCool: 0, lastTap: 0,
      vel: new THREE.Vector3(),
      gamepad: null,
      mesh: null, arm: null,
    };
  }

  _buildVisuals() {
    this.handMat = new THREE.MeshLambertMaterial({ color: this.color, flatShading: true });
    this.armMat = new THREE.MeshLambertMaterial({ color: this.color.clone().multiplyScalar(0.8), flatShading: true });
    const mitt = new THREE.IcosahedronGeometry(HAND_R * 1.06, 1);
    mitt.scale(1, 0.86, 1.12);
    const armGeo = new THREE.CylinderGeometry(0.032, 0.05, 1, 7, 1);
    armGeo.translate(0, 0.5, 0);
    for (const h of this.hands) {
      h.mesh = new THREE.Group();
      const m = new THREE.Mesh(mitt, this.handMat);
      h.mesh.add(m);
      const thumb = new THREE.Mesh(new THREE.IcosahedronGeometry(0.02, 0), this.handMat);
      thumb.position.set(h.side ? -0.035 : 0.035, 0.0, -0.04);
      h.mesh.add(thumb);
      h.arm = new THREE.Mesh(armGeo, this.armMat);
      h.mesh.visible = false; h.arm.visible = false;
      this.scene.add(h.mesh, h.arm);
    }
  }

  setColor(idx) {
    this.colorIdx = (idx + PLAYER_COLORS.length) % PLAYER_COLORS.length;
    this.color.set(PLAYER_COLORS[this.colorIdx]);
    this.handMat.color.copy(this.color);
    this.armMat.color.copy(this.color).multiplyScalar(0.8);
  }

  setVisible(v) { for (const h of this.hands) { h.mesh.visible = v; h.arm.visible = v; } }

  // ----------------------------------------------------------- helpers
  _updateHead() {
    this.head.copy(this.headLocal).applyQuaternion(this.rigQuat).add(this.rigPos);
  }

  _target(h, out) {
    out.copy(h.local).applyQuaternion(this.rigQuat).add(this.rigPos);
    const dx = out.x - this.head.x, dy = out.y - this.head.y, dz = out.z - this.head.z;
    const d = Math.sqrt(dx * dx + dy * dy + dz * dz);
    if (d > MAX_ARM) {
      const k = MAX_ARM / d;
      out.set(this.head.x + dx * k, this.head.y + dy * k, this.head.z + dz * k);
    }
    return out;
  }

  _pushHist(now) {
    const i = (this.histI = (this.histI + 1) % 24);
    this.histT[i] = now; this.histX[i] = this.rigPos.x; this.histY[i] = this.rigPos.y; this.histZ[i] = this.rigPos.z;
    if (this.histN < 24) this.histN++;
  }

  _estimateVel(now, out) {
    out.set(0, 0, 0);
    if (this.histN < 2) return out;
    const i0 = this.histI;
    let oldest = i0;
    for (let k = 1; k < this.histN; k++) {
      const idx = (i0 - k + 24) % 24;
      oldest = idx;
      if (now - this.histT[idx] > VEL_WINDOW) break;
    }
    const dt = this.histT[i0] - this.histT[oldest];
    if (dt < 1e-3) return out;
    return out.set(this.histX[i0] - this.histX[oldest], this.histY[i0] - this.histY[oldest], this.histZ[i0] - this.histZ[oldest]).divideScalar(dt);
  }

  _haptic(h, intensity, ms) {
    const gp = h.gamepad;
    if (!gp || !gp.hapticActuators || !gp.hapticActuators[0]) return;
    try { gp.hapticActuators[0].pulse(Math.min(1, intensity), ms); } catch (e) { /* ignore */ }
  }

  _beginContact(h, res, impact, now) {
    h.contact = true;
    h.anchor.set(res.x, res.y, res.z);
    h.normal.set(res.nx, res.ny, res.nz);
    h.col = res.col;
    h.lift = 0;
    if (now - h.lastTap > 0.09 && impact > 0.2) {
      h.lastTap = now;
      const s = THREE.MathUtils.clamp(impact / 4, 0.12, 1);
      this.sfx.tap(res.col.mat.name, s, h.anchor);
      this._haptic(h, 0.12 + s * 0.6, 18 + s * 30);
      if (impact > 2.2) this.fx.dust(res.x, res.y, res.z, res.col.mat.name, s);
    }
  }

  _bounce(nx, ny, nz, impact, now, at) {
    const strength = THREE.MathUtils.clamp(2.5 + impact * 0.92, 6.5, 11.5);
    const vn = this.vel.x * nx + this.vel.y * ny + this.vel.z * nz;
    this.vel.x -= nx * vn; this.vel.y -= ny * vn; this.vel.z -= nz * vn;
    this.vel.multiplyScalar(0.85);
    this.vel.x += nx * strength; this.vel.y += ny * strength; this.vel.z += nz * strength;
    this.bounceLock = now + 0.15;
    this.hands[0].contact = this.hands[1].contact = false;
    this.histN = 0;
    this.sfx.boing(at, strength / 11.5);
    for (const h of this.hands) this._haptic(h, 0.9, 60);
    this.fx.burst(at.x, at.y, at.z, 0xff7ab8, 14, 3.5, 0.6);
  }

  _reproject(h) {
    const d = sdfOne(h.col, h.anchor.x, h.anchor.y, h.anchor.z) - HAND_R;
    const n = this.phys.normal(h.col, h.anchor.x, h.anchor.y, h.anchor.z, this.tmpN);
    h.anchor.x -= n.x * d; h.anchor.y -= n.y * d; h.anchor.z -= n.z * d;
    h.normal.set(n.x, n.y, n.z);
  }

  // ---------------------------------------------------------------- VR
  spawnVR() {
    // face the island: cancel the headset's yaw so the player looks down -Z
    const f = this.tmpV.set(0, 0, -1).applyQuaternion(this.headQuatLocal);
    const localYaw = Math.atan2(-f.x, -f.z);
    this.yaw = -localYaw;
    this.rigQuat.setFromAxisAngle(UP, this.yaw);
    const hl = this.tmpV.copy(this.headLocal).applyQuaternion(this.rigQuat);
    this.rigPos.copy(this.spawnPoint).sub(hl);
    this.vel.set(0, 0, 0);
    this._updateHead();
    for (const h of this.hands) { h.contact = false; this._target(h, h.pos); h.prev.copy(h.pos); }
    this.histN = 0;
    this.needsSpawn = false;
  }

  respawn() {
    if (this.mode === 'vr') { this.needsSpawn = true; }
    else if (this.mode === 'desktop') { this.dBody.copy(this.spawnPoint); this.vel.set(0, 0, 0); }
    this.sfx.whooshUp();
    if (this.onRespawn) this.onRespawn();
  }

  snapTurnBy(angle) {
    this._updateHead();
    const hx = this.head.x, hy = this.head.y, hz = this.head.z;
    this.yaw += angle;
    this.rigQuat.setFromAxisAngle(UP, this.yaw);
    const hl = this.tmpV.copy(this.headLocal).applyQuaternion(this.rigQuat);
    this.rigPos.set(hx - hl.x, hy - hl.y, hz - hl.z);
    this._updateHead();
    for (const h of this.hands) { h.contact = false; this._target(h, h.pos); }
    this.histN = 0;
  }

  handleVRInput() {
    const right = this.hands[1];
    const gp = right.gamepad;
    if (!gp || !this.snapTurn) return;
    const x = gp.axes.length >= 4 ? gp.axes[2] : gp.axes[0] || 0;
    if (Math.abs(x) < 0.35) this.stickReady = true;
    else if (this.stickReady && Math.abs(x) > 0.75) {
      this.stickReady = false;
      this.snapTurnBy(x > 0 ? -Math.PI / 4 : Math.PI / 4);
      this.sfx.click(this.head);
    }
  }

  updateVR(dt, now) {
    const H = this.hands, res = this.res, res2 = this.res2, phys = this.phys;
    if (this.needsSpawn) this.spawnVR();
    for (const h of H) { h.bounceCool -= dt; h.prev.copy(h.pos); }
    this._updateHead();
    const anyPrev = H[0].contact || H[1].contact;
    const locked = now < this.bounceLock;

    // 1. free flight
    if (!anyPrev) {
      this.vel.y -= G * dt;
      this.rigPos.addScaledVector(this.vel, dt);
      this._updateHead();
      this.airTime += dt;
    } else this.airTime = 0;

    phys.gather(this.head.x, this.head.y - 0.3, this.head.z, MAX_ARM + 0.9 + this.vel.length() * dt, this.near);

    // 2. hands: keep anchored hands stuck, detect new touches
    let bounced = false;
    for (const h of H) {
      const T = this._target(h, h.target);
      h.corr.set(0, 0, 0);
      if (h.contact) {
        const vx = T.x - h.anchor.x, vy = T.y - h.anchor.y, vz = T.z - h.anchor.z;
        const n = h.normal;
        const vn = vx * n.x + vy * n.y + vz * n.z;
        if (vn > RELEASE || vx * vx + vy * vy + vz * vz > UNSTICK * UNSTICK) { h.contact = false; continue; }
        let tx = vx - vn * n.x, ty = vy - vn * n.y, tz = vz - vn * n.z;
        const slip = h.col.mat.slip;
        if (slip > 0) {
          h.anchor.x += tx * slip; h.anchor.y += ty * slip; h.anchor.z += tz * slip;
          this._reproject(h);
          tx *= 1 - slip; ty *= 1 - slip; tz *= 1 - slip;
        }
        const pen = vn < 0 ? vn : 0;
        h.corr.set(-tx - pen * n.x, -ty - pen * n.y, -tz - pen * n.z);
        h.lift = vn > 0 ? vn : 0;
      } else if (phys.sphereCast(this.near, h.pos.x, h.pos.y, h.pos.z, T.x, T.y, T.z, HAND_R, res)) {
        const impact = -((T.x - h.pos.x) * res.nx + (T.y - h.pos.y) * res.ny + (T.z - h.pos.z) * res.nz) / Math.max(dt, 1e-4);
        if (res.col.mat.bounce && impact > 1.0 && h.bounceCool <= 0 && !locked) {
          h.pos.set(res.x, res.y, res.z);
          this._bounce(res.nx, res.ny, res.nz, impact, now, h.pos);
          h.bounceCool = 0.35;
          bounced = true;
          break;
        }
        if (locked) continue;
        this._beginContact(h, res, impact, now);
        h.corr.set(res.x - T.x, res.y - T.y, res.z - T.z);
      }
    }

    // 3. move the body by what the hands demand
    if (!bounced) {
      const c0 = H[0].contact, c1 = H[1].contact;
      if (c0 && c1) this.corr.addVectors(H[0].corr, H[1].corr).multiplyScalar(0.5);
      else if (c0) this.corr.copy(H[0].corr);
      else if (c1) this.corr.copy(H[1].corr);
      else this.corr.set(0, 0, 0);
      if (c0 || c1) { this.rigPos.add(this.corr); this._updateHead(); }
    }

    // 4. head / body collision
    const anyNow = H[0].contact || H[1].contact;
    this.tmpHead.copy(this.head);
    if (phys.resolveSphere(this.near, this.tmpHead, HEAD_R, anyNow ? null : this.vel, res2)) {
      this.rigPos.x += this.tmpHead.x - this.head.x;
      this.rigPos.y += this.tmpHead.y - this.head.y;
      this.rigPos.z += this.tmpHead.z - this.head.z;
      this._updateHead();
      if (!anyNow) {
        if (res2.col.mat.bounce && res2.impact > 2.0 && !locked) {
          this._bounce(res2.nx, res2.ny, res2.nz, res2.impact * 0.8, now, this.head);
          bounced = true;
        } else if (res2.ground) {
          const f = Math.max(0, 1 - 9 * dt);
          this.vel.x *= f; this.vel.z *= f;
          if (res2.impact > 2.5 && now - this.lastLand > 0.3) {
            this.lastLand = now;
            this.sfx.tap(res2.col.mat.name, Math.min(1, res2.impact / 7), this.head);
          }
        }
      }
    }

    // 5. free hands follow the controllers, unless something is in the way
    const lockedNow = now < this.bounceLock;
    for (const h of H) {
      if (h.contact) { h.pos.copy(h.anchor).addScaledVector(h.normal, h.lift); continue; }
      const T = this._target(h, h.target);
      if (phys.sphereCast(this.near, h.pos.x, h.pos.y, h.pos.z, T.x, T.y, T.z, HAND_R, res)) {
        const impact = -((T.x - h.pos.x) * res.nx + (T.y - h.pos.y) * res.ny + (T.z - h.pos.z) * res.nz) / Math.max(dt, 1e-4);
        h.pos.set(res.x, res.y, res.z);
        if (lockedNow) continue;
        if (res.col.mat.bounce && impact > 1.0 && h.bounceCool <= 0) {
          this._bounce(res.nx, res.ny, res.nz, impact, now, h.pos);
          h.bounceCool = 0.35;
          bounced = true;
          continue;
        }
        this._beginContact(h, res, impact, now);
      } else h.pos.copy(T);
    }

    // 6. momentum: remember how the body moved while touching; throw on release
    const anyAfter = H[0].contact || H[1].contact;
    if (anyAfter) {
      if (!anyPrev) this.histN = 0;
      this._pushHist(now);
      this._estimateVel(now, this.vel);
    } else if (anyPrev && !bounced) {
      const v = this._estimateVel(now, this.tmpV);
      const s = v.length();
      if (s > VEL_LIMIT) {
        this.vel.copy(v).multiplyScalar(JUMP_MULT * this.speedMult);
        const max = MAX_JUMP * this.speedMult;
        if (this.vel.length() > max) this.vel.setLength(max);
      } else this.vel.set(0, 0, 0);
      this.histN = 0;
    }
    if (this.vel.lengthSq() > MAX_SPEED * MAX_SPEED) this.vel.setLength(MAX_SPEED);

    for (const h of H) {
      h.vel.subVectors(h.pos, h.prev).divideScalar(Math.max(dt, 1e-4));
      h.worldQuat.multiplyQuaternions(this.rigQuat, h.quatLocal);
    }
    this.headQuat.multiplyQuaternions(this.rigQuat, this.headQuatLocal);
    if (this.head.y < -28) this.respawn();
    this.rig.position.copy(this.rigPos);
    this.rig.quaternion.copy(this.rigQuat);
    this._updateBody();
    this._updateArms();
  }

  // ----------------------------------------------------------- desktop
  startDesktop() {
    this.mode = 'desktop';
    this.dBody.copy(this.spawnPoint);
    this.vel.set(0, 0, 0);
    this.dYaw = 0; this.dPitch = -0.08;
    this.camera.position.set(0, 0, 0);
    this.rig.quaternion.identity();
  }

  startVR() {
    this.mode = 'vr';
    this.needsSpawn = true;
    this.camera.position.set(0, 0, 0);
    this.camera.quaternion.identity();
  }

  updateDesktop(dt, now, inp) {
    const phys = this.phys, res = this.res;
    this.dYaw = inp.yaw; this.dPitch = inp.pitch;
    const sin = Math.sin(this.dYaw), cos = Math.cos(this.dYaw);
    let wx = -sin * inp.fwd + cos * inp.strafe, wz = -cos * inp.fwd - sin * inp.strafe;
    const wl = Math.hypot(wx, wz);
    if (wl > 1) { wx /= wl; wz /= wl; }
    const top = (inp.sprint ? 7.0 : 4.8) * this.speedMult;
    const grounded = now - this.dGroundTime < 0.12;
    const accel = (grounded ? 38 : 9) * dt;
    let ax = wx * top - this.vel.x, az = wz * top - this.vel.z;
    const al = Math.hypot(ax, az);
    if (al > accel) { ax *= accel / al; az *= accel / al; }
    this.vel.x += ax; this.vel.z += az;
    if (grounded && inp.jump && now - this.dJumpTime > 0.3) {
      this.vel.y = 5.6; this.dJumpTime = now;
      this.sfx.tap('grass', 0.3, this.dBody);
    }
    // climbing: push into a steep wall to scramble up it
    if (this.dWall && inp.fwd > 0 && wx * -this.dWallN.x + wz * -this.dWallN.z > 0.35) {
      if (this.vel.y < 3.4) this.vel.y = 3.4;
      if (now - this.dClimbSfx > 0.22) { this.dClimbSfx = now; this.sfx.tap(this.dWallMat || 'wood', 0.25, this.dBody); }
    }
    this.vel.y -= G * dt;
    this.dBody.addScaledVector(this.vel, dt);
    phys.gather(this.dBody.x, this.dBody.y, this.dBody.z, 1.2 + this.vel.length() * dt, this.near);
    this.dWall = false;
    if (phys.resolveSphere(this.near, this.dBody, 0.3, this.vel, res)) {
      if (res.ground) this.dGroundTime = now;
      if (Math.abs(res.ny) < 0.5) { this.dWall = true; this.dWallN.set(res.nx, res.ny, res.nz); this.dWallMat = res.col.mat.name; }
      if (res.col.mat.bounce && res.impact > 2) {
        this.vel.y = THREE.MathUtils.clamp(res.impact * 1.1 + 4.5, 8.5, 13);
        this.sfx.boing(this.dBody, 0.8);
        this.fx.burst(this.dBody.x, this.dBody.y - 0.3, this.dBody.z, 0xff7ab8, 12, 3, 0.6);
      } else if (res.impact > 3 && now - this.lastLand > 0.25) {
        this.lastLand = now;
        this.sfx.tap(res.col.mat.name, Math.min(1, res.impact / 8), this.dBody);
      }
    }
    if (this.dBody.y < -28) this.respawn();

    this.head.copy(this.dBody); this.head.y += 0.36;
    this.rig.position.copy(this.head);
    this.camEuler.set(this.dPitch, this.dYaw, 0, 'YXZ');
    this.camera.quaternion.setFromEuler(this.camEuler);
    this.headQuat.copy(this.camera.quaternion);

    // cosmetic hands that bob while running; click to slap
    const speed = Math.hypot(this.vel.x, this.vel.z);
    if (grounded) this.dPhase += dt * (speed * 2.2 + 0.5);
    this.dSlap = Math.max(0, this.dSlap - dt);
    for (const h of this.hands) {
      const s = h.side ? 1 : -1;
      const bob = Math.sin(this.dPhase * 2 + h.side * Math.PI) * Math.min(1, speed / 5);
      let lx = 0.23 * s, ly = -0.27 + bob * 0.06, lz = -0.42 + bob * 0.08;
      if (h.side === 1 && this.dSlap > 0) {
        const k = Math.sin((this.dSlap / 0.25) * Math.PI);
        lx = THREE.MathUtils.lerp(lx, 0.04, k); ly = THREE.MathUtils.lerp(ly, -0.08, k); lz = THREE.MathUtils.lerp(lz, -0.85, k);
      }
      h.prev.copy(h.pos);
      h.pos.set(lx, ly, lz).applyQuaternion(this.camera.quaternion).add(this.head);
      h.worldQuat.copy(this.camera.quaternion);
      h.vel.subVectors(h.pos, h.prev).divideScalar(Math.max(dt, 1e-4));
      h.contact = false;
    }
    this._updateBody();
    this._updateArms();
  }

  slap() { if (this.dSlap <= 0) { this.dSlap = 0.25; this.sfx.whoosh && this.sfx.whoosh(); } }

  // ------------------------------------------------------------ shared
  _updateBody() {
    this.bodyPos.copy(this.head); this.bodyPos.y -= 0.3;
    const s = this.spheres;
    s[0].x = this.head.x; s[0].y = this.head.y; s[0].z = this.head.z;
    s[1].x = this.bodyPos.x; s[1].y = this.bodyPos.y; s[1].z = this.bodyPos.z;
    for (let i = 0; i < 2; i++) {
      const p = this.hands[i].pos;
      s[2 + i].x = p.x; s[2 + i].y = p.y; s[2 + i].z = p.z;
      s[2 + i].r = this.mode === 'desktop' ? (i === 1 && this.dSlap > 0 ? 0.16 : 0.0) : 0.075;
    }
  }

  _updateArms() {
    const f = this.tmpV.set(0, 0, -1).applyQuaternion(this.headQuat);
    const yaw = Math.atan2(-f.x, -f.z);
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    for (const h of this.hands) {
      h.mesh.position.copy(h.pos);
      h.mesh.quaternion.copy(h.worldQuat);
      const s = h.side ? 1 : -1;
      // shoulder: a bit below and beside the head, following head yaw
      const lx = 0.17 * s, lz = 0.07;
      const sx = this.head.x + lx * cy + lz * sy, sz = this.head.z - lx * sy + lz * cy, syy = this.head.y - 0.26;
      const dx = h.pos.x - sx, dy = h.pos.y - syy, dz = h.pos.z - sz;
      const len = Math.sqrt(dx * dx + dy * dy + dz * dz);
      h.arm.position.set(sx, syy, sz);
      if (len > 1e-4) {
        this.tmpHead.set(dx / len, dy / len, dz / len);
        h.arm.quaternion.setFromUnitVectors(UP, this.tmpHead);
      }
      h.arm.scale.set(1, Math.max(0.01, len - 0.04), 1);
      h.arm.visible = h.mesh.visible && this.mode === 'vr';
    }
  }

  setStatusLook(kind) {
    const e = kind === 'it' ? 0xff5a1f : kind === 'infected' ? 0x3cff6a : 0x000000;
    this.handMat.emissive.setHex(e);
    this.handMat.emissiveIntensity = kind ? 0.55 : 0;
    this.handMat.transparent = kind === 'ghost';
    this.handMat.opacity = kind === 'ghost' ? 0.35 : 1;
    this.armMat.transparent = kind === 'ghost';
    this.armMat.opacity = kind === 'ghost' ? 0.35 : 1;
  }

  speed() { return this.vel.length(); }
}
