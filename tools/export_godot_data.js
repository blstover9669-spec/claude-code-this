// Exports the tested web build's level data for the native Godot (Quest APK) port:
//   level.json  - colliders, nav graph, spawn, kiosk/button layout
//   meshes.json + meshes.bin - world/bot/player geometry (Godot winding, flat normals, linear vertex colours)
//   sfx/*.wav   - every synthesised sound effect, rendered offline
// Usage: node tools/export_godot_data.js http://127.0.0.1:8765/index.html quest/data
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const URL = process.argv[2] || 'http://127.0.0.1:8765/index.html';
const OUT = process.argv[3] || 'quest/data';

(async () => {
  fs.mkdirSync(path.join(OUT, 'sfx'), { recursive: true });
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--autoplay-policy=no-user-gesture-required'] });
  const page = await browser.newPage({ viewport: { width: 320, height: 200 } });
  page.on('pageerror', (e) => console.log('pageerror', e.message));
  await page.goto(URL);
  await page.waitForFunction(() => window.__game && window.__game.frames > 2, null, { timeout: 60000 });
  await page.evaluate(() => window.__game.renderer.setAnimationLoop(null));

  // ------------------------------------------------------------ level
  const level = await page.evaluate(() => {
    const g = window.__game;
    const r = (v) => Math.round(v * 1e5) / 1e5;
    const colliders = g.world.phys.colliders.map((c) => ({ t: c.type, m: c.mat.name, tag: c.tag, c: [c.cx, c.cy, c.cz].map(r), br: r(c.br), p: Array.from(c.p).map(r) }));
    const nodes = g.nav.nodes.map((n) => [r(n.x), r(n.y), r(n.z), r(n.r), n.kind, n.region, n.good ? 1 : 0]);
    const edges = g.nav.nodes.map((n) => n.edges.map((e) => [e.to, e.jump ? 1 : 0, r(e.cost)]));
    const k = g.ui.k;
    k.group.updateWorldMatrix(true, true);
    const board = k.group.children.find((o) => o.isMesh && o.material && o.material.map && !Array.isArray(o.material));
    return {
      colliders, nodes, edges,
      spawn: g.world.spawn.toArray(),
      kiosk: g.world.kiosk,
      panelMatrix: k.panel.matrixWorld.elements.map(r),
      boardMatrix: board.matrixWorld.elements.map(r),
      buttons: k.buttons.map((b) => ({ id: b.id, x: b.x, y: b.y, w: b.w, h: b.h, z: b.z, color: b.color })),
      sunDir: g.world.sunDir.toArray(),
    };
  });
  fs.writeFileSync(path.join(OUT, 'level.json'), JSON.stringify(level));
  console.log(`level: ${level.colliders.length} colliders, ${level.nodes.length} nav nodes, ${level.edges.reduce((s, e) => s + e.length, 0)} edges`);

  // ----------------------------------------------------------- meshes
  const meshes = await page.evaluate(() => {
    const g = window.__game, THREE = g.THREE;
    const b64 = (f32) => {
      const u8 = new Uint8Array(f32.buffer, f32.byteOffset, f32.byteLength);
      let s = '';
      for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
      return btoa(s);
    };
    // Bake a geometry into flat arrays: world (or local) space, flat normals,
    // per-vertex linear colour, triangles re-wound clockwise for Godot.
    const bake = (geo, matrix, colorFn) => {
      const g2 = geo.index ? geo.toNonIndexed() : geo.clone();
      if (matrix) g2.applyMatrix4(matrix);
      const pos = g2.attributes.position.array;
      const col = g2.attributes.color ? g2.attributes.color.array : null;
      const n = pos.length / 3;
      const P = new Float32Array(n * 3), N = new Float32Array(n * 3), C = new Float32Array(n * 3);
      const order = [0, 2, 1];
      const tmp = new THREE.Color();
      for (let t = 0; t < n; t += 3) {
        const a = t * 3, b = a + 3, c = a + 6;
        const ux = pos[b] - pos[a], uy = pos[b + 1] - pos[a + 1], uz = pos[b + 2] - pos[a + 2];
        const vx = pos[c] - pos[a], vy = pos[c + 1] - pos[a + 1], vz = pos[c + 2] - pos[a + 2];
        let nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
        const l = Math.hypot(nx, ny, nz) || 1; nx /= l; ny /= l; nz /= l;
        for (let k = 0; k < 3; k++) {
          const s = (t + order[k]) * 3, d = (t + k) * 3;
          P[d] = pos[s]; P[d + 1] = pos[s + 1]; P[d + 2] = pos[s + 2];
          N[d] = nx; N[d + 1] = ny; N[d + 2] = nz;
          if (col) { C[d] = col[s]; C[d + 1] = col[s + 1]; C[d + 2] = col[s + 2]; }
          else if (colorFn) { colorFn(tmp); C[d] = tmp.r; C[d + 1] = tmp.g; C[d + 2] = tmp.b; }
          else { C[d] = C[d + 1] = C[d + 2] = 1; }
        }
      }
      return { n, P, N, C };
    };
    const join = (parts) => {
      const n = parts.reduce((s, p) => s + p.n, 0);
      const P = new Float32Array(n * 3), N = new Float32Array(n * 3), C = new Float32Array(n * 3);
      let o = 0;
      for (const p of parts) { P.set(p.P, o * 3); N.set(p.N, o * 3); C.set(p.C, o * 3); o += p.n; }
      return { n, P, N, C };
    };
    const out = {};
    const add = (name, m) => { out[name] = { n: m.n, P: b64(m.P), N: b64(m.N), C: b64(m.C) }; };

    // static world: merged vertex-coloured meshes + baked grass/flowers + kiosk frame
    const solid = [bake(g.scene.getObjectByName('world-solid').geometry, null)];
    const m4 = new THREE.Matrix4(), c4 = new THREE.Color();
    for (const im of g.scene.children.filter((o) => o.isInstancedMesh)) {
      const p = im.geometry.parameters || {};
      const isTuft = im.geometry.type === 'ConeGeometry';
      const isFlower = im.geometry.type === 'IcosahedronGeometry' && Math.abs((p.radius || 0) - 0.055) < 1e-6;
      if (!isTuft && !isFlower) continue;
      for (let i = 0; i < im.count; i++) {
        im.getMatrixAt(i, m4);
        im.getColorAt(i, c4);
        const cc = c4.clone();
        if (isFlower) cc.multiplyScalar(1.25);
        solid.push(bake(im.geometry, m4, (t) => t.copy(cc)));
      }
    }
    const k = g.ui.k;
    const skip = new Set(k.buttons.map((b) => b.mesh));
    k.group.updateWorldMatrix(true, true);
    k.group.traverse((o) => {
      if (!o.isMesh || skip.has(o)) return;
      if (o.material && o.material.map) return; // the board canvas: rebuilt in Godot
      const cc = o.material.color.clone();
      solid.push(bake(o.geometry, o.matrixWorld, (t) => t.copy(cc)));
    });
    add('world_solid', join(solid));
    add('world_glow', bake(g.scene.getObjectByName('world-glow').geometry, null));
    add('world_cloud', bake(g.scene.getObjectByName('world-cloud').geometry, null));

    // bot parts (local space)
    const bot = g.bots[0];
    add('bot_body', bake(bot.body.geometry, null));
    add('bot_eyes', bake(bot.eyes.geometry, null));
    add('bot_hand', bake(bot.handMeshes[0].geometry, null));
    add('bot_arm', bake(bot.armMeshes[0].geometry, null));
    add('bot_ring', bake(bot.ring.geometry, null));
    add('bot_star', bake(bot.stars.children[0].geometry, null));
    const hats = {};
    for (const b of g.bots) if (!hats[b.hat]) { hats[b.hat] = 1; add('hat_' + b.hat, bake(b.hatMesh.geometry, null)); }
    // player parts
    const ph = g.player.hands[0];
    add('player_mitt', bake(ph.mesh.children[0].geometry, null));
    add('player_thumb', bake(ph.mesh.children[1].geometry, null));
    add('player_arm', bake(ph.arm.geometry, null));
    return out;
  });
  const header = [];
  const chunks = [];
  let off = 0;
  for (const [name, m] of Object.entries(meshes)) {
    const bufs = [Buffer.from(m.P, 'base64'), Buffer.from(m.N, 'base64'), Buffer.from(m.C, 'base64')];
    header.push({ name, n: m.n, off });
    for (const b of bufs) { chunks.push(b); off += b.length; }
  }
  fs.writeFileSync(path.join(OUT, 'meshes.bin'), Buffer.concat(chunks));
  fs.writeFileSync(path.join(OUT, 'meshes.json'), JSON.stringify(header));
  console.log('meshes:', header.map((h) => `${h.name}(${h.n})`).join(' '), `${(off / 1048576).toFixed(1)}MB`);

  // ------------------------------------------------------------ sounds
  const sounds = await page.evaluate(async () => {
    const { Sfx } = await import('/src/audio.js');
    const SR = 44100;
    const wav = (data) => {
      const n = data.length, buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
      const w = (o, s) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
      w(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); w(8, 'WAVE'); w(12, 'fmt ');
      v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
      v.setUint32(24, SR, true); v.setUint32(28, SR * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
      w(36, 'data'); v.setUint32(40, n * 2, true);
      for (let i = 0; i < n; i++) v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, data[i])) * 32767, true);
      const u8 = new Uint8Array(buf);
      let s = '';
      for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
      return btoa(s);
    };
    const render = async (dur, fn, peak = 0.9) => {
      const off = new OfflineAudioContext(1, Math.ceil(dur * SR), SR);
      const s = new Sfx();
      s.ctx = off;
      s.master = off.createGain();
      s.master.connect(off.destination);
      const nb = off.createBuffer(1, SR * 2, SR), d = nb.getChannelData(0);
      for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
      s.noise = nb;
      fn(s, off);
      const buf = await off.startRendering();
      const data = buf.getChannelData(0);
      let mx = 0;
      for (let i = 0; i < data.length; i++) mx = Math.max(mx, Math.abs(data[i]));
      // trim trailing silence
      let end = data.length;
      while (end > 1000 && Math.abs(data[end - 1]) < 0.0005 * Math.max(mx, 1e-6)) end--;
      const outd = data.slice(0, end);
      if (mx > 0 && peak) for (let i = 0; i < outd.length; i++) outd[i] *= peak / mx;
      return outd;
    };
    const loop = async (dur, type, freq, q) => {
      const data = await render(dur + 0.5, (s, off) => {
        const src = off.createBufferSource();
        src.buffer = s.noise; src.loop = true;
        const f = off.createBiquadFilter(); f.type = type; f.frequency.value = freq; f.Q.value = q;
        src.connect(f); f.connect(off.destination); src.start(0);
      }, 0.8);
      const F = Math.floor(0.5 * SR), n = data.length - F, out = new Float32Array(n);
      for (let i = 0; i < n; i++) out[i] = data[i];
      for (let i = 0; i < F; i++) { const k = i / F; out[i] = data[i] * k + data[n + i] * (1 - k); }
      return out;
    };
    const list = {};
    for (const m of ['grass', 'wood', 'stone', 'cap', 'leaf', 'crystal', 'cloud']) list['tap_' + m] = wav(await render(0.8, (s) => s.tap(m, 1, null)));
    list.boing = wav(await render(0.6, (s) => s.boing(null, 1)));
    list.chirp = wav(await render(0.3, (s) => s.chirp(null, 1)));
    list.tag_made = wav(await render(0.5, (s) => s.tag('made')));
    list.tag_got = wav(await render(0.7, (s) => s.tag('got')));
    list.tag_other = wav(await render(0.3, (s) => s.tag('other', null)));
    list.orb = wav(await render(0.6, (s) => s.orb(null, true)));
    list.sizzle = wav(await render(0.9, (s) => s.sizzle(null)));
    list.click = wav(await render(0.2, (s) => s.click(null)));
    list.beep = wav(await render(0.3, (s) => s.beep(false)));
    list.beep_go = wav(await render(0.6, (s) => s.beep(true)));
    list.horn = wav(await render(0.8, (s) => s.horn()));
    list.fanfare_win = wav(await render(1.0, (s) => s.fanfare(true)));
    list.fanfare_lose = wav(await render(0.7, (s) => s.fanfare(false)));
    list.whoosh = wav(await render(0.3, (s) => s.whoosh()));
    list.whoosh_up = wav(await render(0.7, (s) => s.whooshUp()));
    for (let b = 0; b < 3; b++) {
      list['bird' + b] = wav(await render(0.7, (s) => {
        const out = s._out(null, 0.5), base = 2200 + Math.random() * 1600, n = 2 + Math.floor(Math.random() * 4);
        for (let i = 0; i < n; i++) s._tone(out, i * 0.11, 0.08, 'sine', base, base * (0.75 + Math.random() * 0.6), 0.09, 0.005);
      }));
    }
    list.loop_wind = wav(await loop(6, 'lowpass', 380, 0.7));
    list.loop_rush = wav(await loop(4, 'bandpass', 700, 0.7));
    return list;
  });
  for (const [name, data] of Object.entries(sounds)) fs.writeFileSync(path.join(OUT, 'sfx', name + '.wav'), Buffer.from(data, 'base64'));
  console.log('sounds:', Object.keys(sounds).length);
  await browser.close();
})();
