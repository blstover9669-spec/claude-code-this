// In-world UI: a scoreboard sign with a console of punchable buttons, a wrist
// display in VR and floating "toast" messages that follow your view.
import * as THREE from 'three';
import { MAT } from './physics.js';
import { MODES, DIFFICULTY, fmtTime } from './game.js';
import { HAND_R } from './player.js';

export const FONT = 'Fredoka, "Trebuchet MS", system-ui, sans-serif';

export function rr(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}

function tri(g, cx, cy, s, dir) {
  g.beginPath();
  g.moveTo(cx + dir * s, cy);
  g.lineTo(cx - dir * s * 0.7, cy - s);
  g.lineTo(cx - dir * s * 0.7, cy + s);
  g.closePath();
  g.fill();
}

const BUTTONS = [
  { id: 'prev', x: -0.74, y: 0.16, w: 0.5, h: 0.25, color: '#ffa94d' },
  { id: 'start', x: 0, y: 0.16, w: 0.7, h: 0.25, color: '#51cf66' },
  { id: 'next', x: 0.74, y: 0.16, w: 0.5, h: 0.25, color: '#ffa94d' },
  { id: 'bots', x: -0.85, y: -0.15, w: 0.5, h: 0.22, color: '#74c0fc' },
  { id: 'level', x: -0.285, y: -0.15, w: 0.5, h: 0.22, color: '#b197fc' },
  { id: 'color', x: 0.285, y: -0.15, w: 0.5, h: 0.22, color: '#ff8cc6' },
  { id: 'turn', x: 0.85, y: -0.15, w: 0.5, h: 0.22, color: '#ffd43b' },
];
const FACE_Z = 0.07, BTN_D = 0.07;

// Builds the sign + console and registers their colliders. Must run before
// the nav graph is built so bots know to walk around it.
export function buildKiosk(scene, phys, pose) {
  const group = new THREE.Group();
  group.position.set(pose.x, 0, pose.z);
  group.rotation.y = pose.rotY;
  scene.add(group);
  const wood = new THREE.MeshLambertMaterial({ color: 0xa06a3c, flatShading: true });
  const dark = new THREE.MeshLambertMaterial({ color: 0x5e3a22, flatShading: true });
  const wp = new THREE.Vector3(), wq = new THREE.Quaternion();
  const box = (parent, w, h, d, x, y, z, mat, collide = true) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
    m.position.set(x, y, z);
    parent.add(m);
    if (collide) {
      m.updateWorldMatrix(true, false);
      m.getWorldPosition(wp); m.getWorldQuaternion(wq);
      phys.addBox(wp.x, wp.y, wp.z, w / 2, h / 2, d / 2, wq, MAT.wood, 0.02);
    }
    return m;
  };
  box(group, 0.14, 2.45, 0.14, -1.43, 1.225, 0, dark);
  box(group, 0.14, 2.45, 0.14, 1.43, 1.225, 0, dark);
  box(group, 2.74, 1.52, 0.08, 0, 1.6, 0, wood);
  box(group, 3.05, 0.1, 0.4, 0, 2.43, 0.02, dark);
  const canvas = document.createElement('canvas');
  canvas.width = 1024; canvas.height = 560;
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4;
  const board = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 1.42), new THREE.MeshBasicMaterial({ map: tex }));
  board.position.set(0, 1.6, 0.043);
  group.add(board);

  const panel = new THREE.Group();
  panel.position.set(0, 0.47, 0.52);
  panel.rotation.x = -0.55;
  group.add(panel);
  box(panel, 2.44, 0.7, 0.14, 0, 0, 0, wood);
  box(group, 0.14, 0.44, 0.14, -1.0, 0.22, 0.47, dark);
  box(group, 0.14, 0.44, 0.14, 1.0, 0.22, 0.47, dark);

  const buttons = BUTTONS.map((d) => {
    const c = document.createElement('canvas');
    c.width = 256; c.height = Math.round((256 * d.h) / d.w);
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    const side = new THREE.MeshLambertMaterial({ color: new THREE.Color(d.color).multiplyScalar(0.6) });
    const front = new THREE.MeshBasicMaterial({ map: t });
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(d.w, d.h, BTN_D), [side, side, side, side, front, side]);
    const z = FACE_Z + BTN_D / 2 - 0.005;
    mesh.position.set(d.x, d.y, z);
    panel.add(mesh);
    mesh.updateWorldMatrix(true, false);
    return { ...d, z, mesh, canvas: c, ctx: c.getContext('2d'), tex: t, cool: 0, downUntil: 0, worldPos: mesh.getWorldPosition(new THREE.Vector3()) };
  });
  return { group, panel, buttons, canvas, ctx: canvas.getContext('2d'), tex };
}

export class UI {
  constructor({ scene, camera, kiosk, game, player, sfx }) {
    this.scene = scene; this.camera = camera; this.k = kiosk; this.game = game; this.player = player; this.sfx = sfx;
    this.inv = new THREE.Matrix4();
    this.v = new THREE.Vector3(); this.v2 = new THREE.Vector3();
    this.ray = new THREE.Raycaster();
    this.boardAt = 0; this.boardTick = 0; this.wristAt = 0;
    this.dirty = true; this.labelsDirty = true;
    this.inside = kiosk.buttons.map(() => [false, false]);
    game.onChange = () => { this.dirty = true; this.labelsDirty = true; };
    game.onToast = (t, c, big) => this.toast(t, c, big);
    this._buildToast();
    this._buildWrist();
    this.drawLabels();
    this.drawBoard();
  }

  // ------------------------------------------------------------ toast
  _buildToast() {
    const c = document.createElement('canvas');
    c.width = 1024; c.height = 256;
    this.toastCtx = c.getContext('2d');
    this.toastTex = new THREE.CanvasTexture(c);
    this.toastTex.colorSpace = THREE.SRGBColorSpace;
    this.toastMesh = new THREE.Mesh(new THREE.PlaneGeometry(1.0, 0.25),
      new THREE.MeshBasicMaterial({ map: this.toastTex, transparent: true, depthTest: false, depthWrite: false, opacity: 0, fog: false }));
    this.toastMesh.renderOrder = 1000;
    this.toastMesh.frustumCulled = false;
    this.toastMesh.visible = false;
    this.scene.add(this.toastMesh);
    this.toastLife = 0; this.toastDur = 1; this.toastInit = false;
  }

  toast(text, color = '#fff7ec', big = false) {
    const g = this.toastCtx, W = 1024, H = 256;
    g.clearRect(0, 0, W, H);
    let size = big ? 118 : 80;
    g.font = `700 ${size}px ${FONT}`;
    let w = g.measureText(text).width;
    if (w > 900) { size = Math.floor((size * 900) / w); g.font = `700 ${size}px ${FONT}`; w = g.measureText(text).width; }
    const bw = w + 90, bh = size * 1.45;
    rr(g, (W - bw) / 2, (H - bh) / 2, bw, bh, bh / 2);
    g.fillStyle = 'rgba(28,16,52,0.78)';
    g.fill();
    g.lineWidth = 6; g.strokeStyle = color; g.globalAlpha = 0.6; g.stroke(); g.globalAlpha = 1;
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.lineWidth = 10; g.strokeStyle = 'rgba(20,10,40,0.9)'; g.strokeText(text, W / 2, H / 2 + size * 0.04);
    g.fillStyle = color; g.fillText(text, W / 2, H / 2 + size * 0.04);
    this.toastTex.needsUpdate = true;
    this.toastLife = this.toastDur = big ? 2.2 : 1.5;
    this.toastMesh.visible = true;
  }

  _updateToast(dt, view) {
    const m = this.toastMesh;
    if (this.toastLife <= 0) { m.visible = false; return; }
    this.toastLife -= dt;
    const t = this.toastDur - this.toastLife;
    m.material.opacity = Math.min(1, t / 0.12) * Math.min(1, this.toastLife / 0.3);
    const fwd = this.v.set(0, -0.09, -1.45).applyQuaternion(view.quat).add(view.pos);
    if (!this.toastInit) { m.position.copy(fwd); this.toastInit = true; }
    else m.position.lerp(fwd, 1 - Math.exp(-7 * dt));
    m.quaternion.slerp(view.quat, 1 - Math.exp(-10 * dt));
    const s = 1 + 0.18 * Math.max(0, 1 - t / 0.16);
    m.scale.set(s, s, s);
  }

  // ------------------------------------------------------------ wrist
  _buildWrist() {
    const c = document.createElement('canvas');
    c.width = 256; c.height = 160;
    this.wristCtx = c.getContext('2d');
    this.wristTex = new THREE.CanvasTexture(c);
    this.wristTex.colorSpace = THREE.SRGBColorSpace;
    this.wrist = new THREE.Mesh(new THREE.PlaneGeometry(0.11, 0.069),
      new THREE.MeshBasicMaterial({ map: this.wristTex, transparent: true, side: THREE.DoubleSide, fog: false }));
    // WebXR grip space: the back of the left hand faces -X and +Y runs up the
    // arm, so a watch face sits on the -X side, reading toward the fingers.
    this.wrist.position.set(-0.062, 0.07, 0.0);
    this.wrist.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(
      new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, 0, 1), new THREE.Vector3(-1, 0, 0)));
    this.wrist.visible = false;
    this.player.hands[0].mesh.add(this.wrist);
  }

  _status() {
    const p = this.player, game = this.game, m = game.mode.id;
    if (game.state !== 'play') return { text: game.state === 'results' ? 'ROUND OVER' : game.state === 'countdown' ? 'GET READY' : 'FREE PLAY', color: '#7bdff2' };
    if (m === 'tag') return p.it ? { text: "YOU'RE IT!", color: '#ff7a45' } : { text: 'SAFE', color: '#7bed9f' };
    if (m === 'infection') return p.infected ? { text: 'SPORED', color: '#6dff7a' } : { text: 'CLEAN', color: '#7bdff2' };
    if (m === 'orbs') return { text: `ORBS ${p.score}`, color: '#ffd166' };
    return p.alive ? { text: 'ALIVE', color: '#ffd166' } : { text: 'MELTED', color: '#ff7a45' };
  }

  drawWrist() {
    const g = this.wristCtx, game = this.game;
    g.clearRect(0, 0, 256, 160);
    const st = this._status();
    rr(g, 6, 6, 244, 148, 26);
    g.fillStyle = 'rgba(28,16,52,0.88)'; g.fill();
    g.lineWidth = 6; g.strokeStyle = st.color; g.stroke();
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillStyle = '#e9d9ff'; g.font = `600 24px ${FONT}`;
    g.fillText(game.mode.name, 128, 32);
    g.fillStyle = '#fff7ec'; g.font = `700 52px ${FONT}`;
    const t = game.state === 'play' ? fmtTime(game.timer) : game.state === 'countdown' ? String(Math.max(1, Math.ceil(game.timer))) : game.state === 'results' ? fmtTime(game.resultTimer) : '--:--';
    g.fillText(t, 128, 80);
    g.fillStyle = st.color; g.font = `700 28px ${FONT}`;
    g.fillText(st.text, 128, 128);
    this.wristTex.needsUpdate = true;
  }

  // ------------------------------------------------------------ board
  _label(id) {
    const game = this.game, p = this.player;
    switch (id) {
      case 'prev': case 'next': return 'MODE';
      case 'start': return game.state === 'free' ? 'START' : 'STOP';
      case 'bots': return `BOTS ${game.botCount}`;
      case 'level': return DIFFICULTY[game.difficulty].name;
      case 'color': return 'COLOR';
      case 'turn': return p.snapTurn ? 'SNAP TURN' : 'NO TURN';
    }
    return id;
  }

  drawLabels() {
    for (const b of this.k.buttons) {
      const g = b.ctx, W = b.canvas.width, H = b.canvas.height;
      let color = b.color;
      if (b.id === 'start') color = this.game.state === 'free' ? '#51cf66' : '#ff6b6b';
      g.fillStyle = color; g.fillRect(0, 0, W, H);
      const grd = g.createLinearGradient(0, 0, 0, H);
      grd.addColorStop(0, 'rgba(255,255,255,0.35)'); grd.addColorStop(0.5, 'rgba(255,255,255,0)'); grd.addColorStop(1, 'rgba(0,0,0,0.18)');
      g.fillStyle = grd; g.fillRect(0, 0, W, H);
      g.lineWidth = 8; g.strokeStyle = 'rgba(40,20,60,0.35)'; g.strokeRect(4, 4, W - 8, H - 8);
      const text = this._label(b.id);
      let size = Math.round(H * 0.46);
      g.font = `700 ${size}px ${FONT}`;
      let tw = g.measureText(text).width;
      const room = b.id === 'prev' || b.id === 'next' ? W * 0.62 : b.id === 'color' ? W * 0.6 : W * 0.86;
      if (tw > room) { size = Math.floor((size * room) / tw); g.font = `700 ${size}px ${FONT}`; tw = g.measureText(text).width; }
      g.fillStyle = '#2a1640'; g.textAlign = 'center'; g.textBaseline = 'middle';
      let cx = W / 2;
      if (b.id === 'prev') { tri(g, W * 0.14, H / 2, H * 0.2, -1); cx = W * 0.58; }
      if (b.id === 'next') { tri(g, W * 0.86, H / 2, H * 0.2, 1); cx = W * 0.42; }
      if (b.id === 'color') {
        cx = W * 0.4;
        g.fillStyle = '#' + this.player.color.getHexString();
        g.beginPath(); g.arc(W * 0.82, H / 2, H * 0.24, 0, Math.PI * 2); g.fill();
        g.lineWidth = 5; g.strokeStyle = '#2a1640'; g.stroke();
        g.fillStyle = '#2a1640';
      }
      g.fillText(text, cx, H / 2 + size * 0.05);
      b.tex.needsUpdate = true;
    }
  }

  _rowStat(e) {
    const game = this.game, m = game.mode.id;
    if (game.state !== 'play') return '';
    if (m === 'tag') return `${e.itTime.toFixed(0)}s`;
    if (m === 'infection') return e.infected ? 'spored' : 'clean';
    if (m === 'orbs') return `${e.score}`;
    return e.alive ? 'alive' : 'melted';
  }

  drawBoard() {
    const g = this.k.ctx, W = 1024, H = 560, game = this.game;
    g.clearRect(0, 0, W, H);
    g.fillStyle = '#5e3a22'; g.fillRect(0, 0, W, H);
    const bg = g.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, '#36215a'); bg.addColorStop(1, '#1c1132');
    rr(g, 12, 12, W - 24, H - 24, 26); g.fillStyle = bg; g.fill();
    g.textAlign = 'left'; g.textBaseline = 'alphabetic';
    g.font = `700 50px ${FONT}`;
    g.fillStyle = '#ffb347'; g.fillText('SHROOM', 40, 80);
    const tw = g.measureText('SHROOM ').width;
    g.fillStyle = '#7bdff2'; g.fillText('SCRAMBLE', 40 + tw, 80);
    // mode pill
    g.font = `700 34px ${FONT}`;
    const mt = game.mode.name, mw = g.measureText(mt).width + 96;
    rr(g, W - 40 - mw, 34, mw, 58, 29); g.fillStyle = '#ffd166'; g.fill();
    g.fillStyle = '#2a1640';
    tri(g, W - 40 - mw + 26, 63, 11, -1); tri(g, W - 66, 63, 11, 1);
    g.textAlign = 'center'; g.fillText(mt, W - 40 - mw / 2, 75);
    g.textAlign = 'left';
    // status
    let line = '', sub = '', col = '#7bdff2';
    if (game.state === 'free') { line = 'FREE PLAY'; sub = 'Punch START on the console to begin a round'; }
    else if (game.state === 'countdown') { line = `GET READY… ${Math.max(1, Math.ceil(game.timer))}`; col = '#ffd166'; }
    else if (game.state === 'play') {
      line = fmtTime(game.timer); col = '#fff7ec';
      const m = game.mode.id, ents = game.ents;
      if (m === 'tag') { const it = ents.find((e) => e.it); sub = it ? `${it.isBot ? it.name + ' is' : 'YOU are'} IT` : ''; }
      else if (m === 'infection') sub = `${ents.filter((e) => !e.infected).length} of ${ents.length} still clean`;
      else if (m === 'orbs') sub = this.game.humanActive ? `You have ${this.player.score} orbs` : 'Grab the orbs!';
      else sub = `${ents.filter((e) => e.alive).length} still standing · lava ${Math.max(0, game.lavaY).toFixed(1)}m`;
    } else { line = 'ROUND OVER'; sub = `Next round in ${Math.max(0, Math.ceil(game.resultTimer))}…`; col = '#ffd166'; }
    g.font = `700 56px ${FONT}`; g.fillStyle = col; g.fillText(line, 40, 160);
    const lw = g.measureText(line).width;
    g.font = `500 30px ${FONT}`; g.fillStyle = '#e9d9ff'; g.fillText(sub, 40 + lw + 26, 156);
    // description
    g.font = `400 25px ${FONT}`; g.fillStyle = '#cbb8f0';
    g.fillText(game.mode.desc, 40, 202, W - 80);
    // participants / results
    const results = game.state === 'results' && game.results;
    const rows = results ? game.results : game.ents.map((e) => ({
      name: e.isBot ? e.name : 'YOU', color: '#' + e.color.getHexString(), stat: this._rowStat(e), me: !e.isBot,
      badge: e.it ? 'IT' : e.infected ? 'SPORED' : !e.alive && game.state === 'play' ? 'OUT' : '',
    }));
    const colW = (W - 100) / 2, rowH = 46, top = 236, perCol = 5;
    rows.slice(0, 10).forEach((r, i) => {
      const cx = 40 + Math.floor(i / perCol) * (colW + 20), cy = top + (i % perCol) * rowH;
      if (r.me) { rr(g, cx - 8, cy, colW, rowH - 6, 12); g.fillStyle = 'rgba(255,209,102,0.14)'; g.fill(); }
      let x = cx + 6;
      if (results) {
        g.font = `700 26px ${FONT}`; g.fillStyle = i === 0 ? '#ffd166' : '#9f8cc9';
        g.fillText(`${i + 1}.`, x, cy + 30); x += 38;
      }
      g.fillStyle = r.color; g.beginPath(); g.arc(x + 12, cy + 20, 12, 0, Math.PI * 2); g.fill();
      g.font = `600 28px ${FONT}`; g.fillStyle = r.me ? '#ffd166' : '#fff7ec';
      g.fillText(r.name, x + 34, cy + 30);
      if (r.badge) {
        const nw = g.measureText(r.name).width;
        g.font = `700 18px ${FONT}`;
        const bw = g.measureText(r.badge).width + 18;
        rr(g, x + 44 + nw, cy + 8, bw, 26, 13);
        g.fillStyle = r.badge === 'IT' ? '#ff7a45' : r.badge === 'SPORED' ? '#4cd964' : '#8a7aa8'; g.fill();
        g.fillStyle = '#1d1233'; g.fillText(r.badge, x + 53 + nw, cy + 28);
      }
      if (r.stat) {
        g.font = `500 24px ${FONT}`; g.fillStyle = '#cbb8f0'; g.textAlign = 'right';
        g.fillText(r.stat, cx + colW - 20, cy + 29);
        g.textAlign = 'left';
      }
    });
    // feed + tip
    g.font = `400 22px ${FONT}`;
    game.feed.slice(0, 2).forEach((f, i) => { g.fillStyle = i ? '#9f8cc9' : '#cbb8f0'; g.fillText('• ' + f, 40, 498 + i * 28); });
    g.textAlign = 'right'; g.fillStyle = '#9f8cc9';
    g.fillText(this.game.humanActive ? 'Push off with your hands · let go to fling!' : '', W - 40, 526);
    g.textAlign = 'left';
    this.k.tex.needsUpdate = true;
  }

  // ------------------------------------------------------------ input
  press(b, now, hand) {
    if (now < b.cool) return;
    b.cool = now + 0.35;
    b.downUntil = now + 0.15;
    this.sfx.click(b.worldPos);
    if (hand) this.player._haptic(hand, 0.55, 35);
    const game = this.game;
    switch (b.id) {
      case 'prev': game.nextMode(-1); break;
      case 'next': game.nextMode(1); break;
      case 'start': game.toggleRound(); break;
      case 'bots': game.cycleBots(); this.toast(`${game.botCount} BOTS`, '#74c0fc'); break;
      case 'level': game.cycleDifficulty(); this.toast(DIFFICULTY[game.difficulty].name, '#b197fc'); break;
      case 'color': this.player.setColor(this.player.colorIdx + 1); break;
      case 'turn': this.player.snapTurn = !this.player.snapTurn; this.toast(this.player.snapTurn ? 'SNAP TURN ON' : 'SNAP TURN OFF', '#ffd43b'); break;
    }
    this.labelsDirty = true; this.dirty = true;
  }

  desktopClick(now) {
    this.ray.setFromCamera({ x: 0, y: 0 }, this.camera);
    const hits = this.ray.intersectObjects(this.k.buttons.map((b) => b.mesh), false);
    if (hits.length && hits[0].distance < 4.5) {
      const b = this.k.buttons.find((x) => x.mesh === hits[0].object);
      if (b) { this.press(b, now, null); return true; }
    }
    return false;
  }

  update(dt, now, mode, view) {
    const k = this.k;
    k.panel.updateWorldMatrix(true, false);
    this.inv.copy(k.panel.matrixWorld).invert();
    const hands = this.player.hands;
    for (let hi = 0; hi < 2; hi++) {
      const h = hands[hi];
      const active = mode === 'vr' || mode === 'vrsim' || (mode === 'desktop' && hi === 1 && this.player.dSlap > 0);
      this.v.copy(h.pos).applyMatrix4(this.inv);
      for (let bi = 0; bi < k.buttons.length; bi++) {
        const b = k.buttons[bi];
        const inside = active &&
          Math.abs(this.v.x - b.x) < b.w / 2 + 0.02 &&
          Math.abs(this.v.y - b.y) < b.h / 2 + 0.02 &&
          this.v.z < FACE_Z + BTN_D + HAND_R + 0.015 && this.v.z > -0.1;
        if (inside && !this.inside[bi][hi]) this.press(b, now, mode === 'desktop' ? null : h);
        this.inside[bi][hi] = inside;
      }
    }
    for (const b of k.buttons) {
      const target = now < b.downUntil ? b.z - 0.03 : b.z;
      b.mesh.position.z += (target - b.mesh.position.z) * (1 - Math.exp(-30 * dt));
    }
    if (this.labelsDirty) { this.labelsDirty = false; this.drawLabels(); }
    // big texture uploads are costly on a headset: redraw on change, else ~1 Hz
    const live = this.game.state !== 'free';
    if (now > this.boardAt && (this.dirty || (live && now > this.boardTick))) {
      this.dirty = false;
      this.boardAt = now + 0.3;
      this.boardTick = now + 1.0;
      this.drawBoard();
    }
    const vr = mode === 'vr' || mode === 'vrsim';
    this.wrist.visible = vr;
    if (vr && now > this.wristAt) { this.wristAt = now + 0.5; this.drawWrist(); }
    this._updateToast(dt, view);
  }
}
