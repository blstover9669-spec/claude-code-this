// Round flow, the four game modes, and the bots' decision making.
import * as THREE from 'three';

export const MODES = [
  { id: 'tag', name: 'TAG', time: 120, desc: 'One fuzzling is IT. Touch someone to pass it on. Least time as IT wins!' },
  { id: 'infection', name: 'SPORE TAG', time: 150, desc: 'Spores spread on touch. Stay clean until the timer runs out!' },
  { id: 'orbs', name: 'ORB RUSH', time: 90, desc: 'Grab the glowing orbs scattered over the islands. Most orbs wins!' },
  { id: 'lava', name: 'LAVA RISE', time: 150, desc: 'The lava is rising! Climb high and be the last one standing.' },
];
export const DIFFICULTY = [{ name: 'EASY', skill: 0.78 }, { name: 'NORMAL', skill: 1.0 }, { name: 'HARD', skill: 1.22 }];
const BOT_COUNTS = [3, 5, 7, 9];
const ORB_COUNT = 16;

export function fmtTime(t) {
  t = Math.max(0, Math.ceil(t));
  return Math.floor(t / 60) + ':' + String(t % 60).padStart(2, '0');
}

export class Game {
  constructor({ scene, player, bots, nav, world, sfx, fx }) {
    this.scene = scene; this.player = player; this.bots = bots; this.nav = nav; this.world = world; this.sfx = sfx; this.fx = fx;
    this.modeIdx = 0;
    this.state = 'free';
    this.timer = 0; this.elapsed = 0; this.resultTimer = 0; this.freeTimer = 0;
    this.humanActive = false;
    this.botCountIdx = 2;
    this.difficulty = 1;
    this.ents = [];
    this.results = null;
    this.feed = [];
    this.onToast = () => {};
    this.onChange = () => {};
    this.lavaY = -40;
    this.lavaStart = -3.5;
    this.lastBeep = 0;
    this.version = 0;
    this._buildOrbs();
    this.applyBotCount();
  }

  get mode() { return MODES[this.modeIdx]; }
  get botCount() { return BOT_COUNTS[this.botCountIdx]; }

  _changed() { this.version++; this.onChange(); }

  toast(text, color = '#fff7ec', big = false) { this.onToast(text, color, big); }

  log(text) {
    this.feed.unshift(text);
    if (this.feed.length > 4) this.feed.length = 4;
    this._changed();
  }

  // ------------------------------------------------------------ setup
  applyBotCount() {
    this.bots.forEach((b, i) => {
      const on = i < this.botCount;
      if (on && !b.active) b.placeAt(this.nav.randomGood());
      b.setActive(on);
    });
    this._rebuildEnts();
  }

  _rebuildEnts() {
    this.ents = (this.humanActive ? [this.player] : []).concat(this.bots.filter((b) => b.active));
  }

  setHuman(active) {
    this.humanActive = active;
    this._rebuildEnts();
    this.stopRound(true);
  }

  nextMode(dir = 1) {
    this.modeIdx = (this.modeIdx + dir + MODES.length) % MODES.length;
    this.stopRound(true);
    this.toast(this.mode.name, '#ffd166');
  }

  cycleBots() {
    this.botCountIdx = (this.botCountIdx + 1) % BOT_COUNTS.length;
    this.applyBotCount();
    this.stopRound(true);
  }

  cycleDifficulty() {
    this.difficulty = (this.difficulty + 1) % DIFFICULTY.length;
    this._changed();
  }

  toggleRound() {
    if (this.state === 'free') this.startCountdown();
    else this.stopRound(false);
  }

  _resetRoles() {
    for (const e of this.ents) {
      e.it = false; e.infected = false; e.alive = true; e.ghost = false;
      e.score = 0; e.itTime = 0; e.tags = 0; e.stunUntil = 0; e.immuneUntil = 0; e.outTime = 0; e.infectedAt = 0;
      e.speedMult = 1;
      e.setStatusLook('');
      if (e.isBot) e.setAlive(true);
    }
    for (const b of this.bots) if (!b.alive) b.setAlive(true);
    this.orbs.forEach((o) => { o.active = false; });
  }

  stopRound(silent) {
    this.state = 'free';
    this.freeTimer = 0;
    this._resetRoles();
    this.results = null;
    if (!silent) this.toast('FREE PLAY', '#7bdff2');
    this._changed();
  }

  startCountdown() {
    this._rebuildEnts();
    this._resetRoles();
    this.results = null;
    this.state = 'countdown';
    this.timer = 3.5;
    this.lastBeep = 4;
    if (this.mode.id === 'lava') {
      const ground = this.nav.nodes.filter((n) => n.good && n.kind === 0 && n.region === 0);
      for (const b of this.bots) if (b.active && ground.length) b.placeAt(ground[Math.floor(Math.random() * ground.length)].i);
    }
    this.toast(this.mode.name, '#ffd166', true);
    this._changed();
  }

  _beginPlay(now) {
    this.state = 'play';
    this.timer = this.mode.time;
    this.elapsed = 0;
    const ents = this.ents;
    const m = this.mode.id;
    if (m === 'tag' || m === 'infection') {
      const pool = ents.length > 1 && Math.random() < 0.75 ? ents.filter((e) => e.isBot) : ents;
      const first = pool[Math.floor(Math.random() * pool.length)];
      if (m === 'tag') { first.it = true; first.setStatusLook('it'); }
      else { first.infected = true; first.setStatusLook('infected'); }
      first.stunUntil = now + 2.0;
      if (first === this.player) this.toast(m === 'tag' ? "YOU'RE IT!" : 'YOU HAVE SPORES!', m === 'tag' ? '#ff7a45' : '#6dff7a', true);
      else this.toast(m === 'tag' ? `${first.name} is IT — RUN!` : `${first.name} has spores — RUN!`, '#ffd166', true);
      this.log(m === 'tag' ? `${first.name} starts as IT` : `${first.name} starts spored`);
    } else if (m === 'orbs') {
      this.orbs.forEach((o, i) => this._placeOrb(o, i * 0.0));
      this.toast('GRAB THE ORBS!', '#ffd166', true);
    } else if (m === 'lava') {
      this.lavaY = this.lavaStart;
      this.toast('THE LAVA IS RISING!', '#ff7a45', true);
    }
    this._applySpeed();
    this.sfx.horn();
    this._changed();
  }

  _endRound(reason) {
    this.state = 'results';
    this.resultTimer = 9;
    this.results = this._computeResults();
    const w = this.results[0];
    const meWon = w && w.me;
    if (reason) this.log(reason);
    this.toast(meWon ? 'YOU WIN!' : w ? `${w.name} WINS!` : 'ROUND OVER', meWon ? '#ffd166' : '#fff7ec', true);
    this.sfx.fanfare(meWon);
    for (const e of this.ents) { e.it = false; e.infected = false; e.setStatusLook(''); e.speedMult = 1; }
    this._changed();
  }

  _computeResults() {
    const m = this.mode.id;
    const rows = this.ents.slice();
    let stat;
    if (m === 'tag') { rows.sort((a, b) => a.itTime - b.itTime); stat = (e) => `${e.itTime.toFixed(1)}s IT`; }
    else if (m === 'infection') {
      rows.sort((a, b) => (a.infected === b.infected ? b.infectedAt - a.infectedAt : a.infected ? 1 : -1));
      stat = (e) => (e.infected ? `spored ${fmtTime(e.infectedAt)}` : 'CLEAN!');
    } else if (m === 'orbs') { rows.sort((a, b) => b.score - a.score); stat = (e) => `${e.score} orbs`; }
    else {
      rows.sort((a, b) => (a.alive === b.alive ? b.outTime - a.outTime : a.alive ? -1 : 1));
      stat = (e) => (e.alive ? 'SURVIVED' : `melted ${fmtTime(e.outTime)}`);
    }
    return rows.map((e) => ({ name: e.name, color: '#' + e.color.getHexString(), stat: stat(e), me: !e.isBot }));
  }

  _applySpeed() {
    for (const e of this.ents) e.speedMult = e.it || e.infected ? 1.12 : 1;
  }

  // -------------------------------------------------------------- loop
  update(dt, now) {
    this.now = now;
    const skill = DIFFICULTY[this.difficulty].skill;
    for (const b of this.bots) {
      if (!b.active) continue;
      b.skill = skill * (this.state === 'play' ? 1 : 0.85);
      if (!(now < b.thinkAt)) { b.thinkAt = now + 0.22 + Math.random() * 0.1; this._brain(b, now); }
    }
    switch (this.state) {
      case 'free':
        if (!this.humanActive) { this.freeTimer += dt; if (this.freeTimer > 3) this.startCountdown(); }
        break;
      case 'countdown': {
        this.timer -= dt;
        const sec = Math.ceil(this.timer);
        if (sec < this.lastBeep && sec >= 1 && sec <= 3) { this.lastBeep = sec; this.sfx.beep(false); this.toast(String(sec), '#fff7ec', true); }
        if (this.timer <= 0) { this.sfx.beep(true); this._beginPlay(now); }
        break;
      }
      case 'play':
        this.timer -= dt;
        this.elapsed += dt;
        this._modeUpdate(dt, now);
        if (this.state === 'play' && this.timer <= 0) {
          const m = this.mode.id;
          this._endRound(m === 'infection' ? 'Time! The clean ones win.' : m === 'lava' ? 'Time! Survivors win.' : 'Time!');
        }
        break;
      case 'results':
        this.resultTimer -= dt;
        if (this.resultTimer <= 0) this.startCountdown();
        break;
    }
    // lava visuals
    if (!(this.state === 'play' && this.mode.id === 'lava') && this.lavaY > -40) {
      this.lavaY = Math.max(-40, this.lavaY - dt * 3);
    }
    this.world.setLava(this.lavaY, this.lavaY > -39.5);
    this._animateOrbs(dt, now);
  }

  _modeUpdate(dt, now) {
    const ents = this.ents, m = this.mode.id;
    if (m === 'tag') {
      for (const a of ents) {
        if (!a.it) continue;
        a.itTime += dt;
        if (now < a.stunUntil) continue;
        for (const b of ents) {
          if (b === a || b.it || now < b.immuneUntil) continue;
          if (this._touching(a, b)) { this._passTag(a, b, now); break; }
        }
      }
    } else if (m === 'infection') {
      for (const a of ents) {
        if (!a.infected || now < a.stunUntil) continue;
        for (const b of ents) if (b !== a && !b.infected && this._touching(a, b)) this._infect(a, b, now);
      }
      if (ents.length > 1 && ents.every((e) => e.infected)) this._endRound('Everyone got spored!');
    } else if (m === 'orbs') {
      for (const o of this.orbs) {
        if (!o.active) { if (now > o.respawnAt && o.respawnAt > 0) this._placeOrb(o); continue; }
        for (const e of ents) {
          if (this._nearPoint(e, o.pos, 0.3)) { this._collect(o, e, now); break; }
        }
      }
    } else if (m === 'lava') {
      const t = this.elapsed;
      this.lavaY = this.lavaStart + t * 0.055 + t * t * 0.00045;
      let alive = 0;
      for (const e of ents) {
        if (!e.alive) continue;
        const y = e.isBot ? e.pos.y - 0.12 : e.bodyPos.y - 0.05;
        if (y < this.lavaY) this._melt(e);
        else alive++;
      }
      if ((ents.length > 1 && alive <= 1) || alive === 0) {
        const last = ents.find((e) => e.alive);
        this._endRound(last ? `${last.name} is the last one standing!` : 'Everyone melted!');
      }
    }
  }

  _touching(a, b) {
    const sa = a.spheres, sb = b.spheres;
    for (let i = 0; i < sa.length; i++) {
      const s = sa[i];
      if (s.r <= 0) continue;
      for (let j = 0; j < sb.length; j++) {
        const t = sb[j];
        if (t.r <= 0) continue;
        const dx = s.x - t.x, dy = s.y - t.y, dz = s.z - t.z, rr = s.r + t.r;
        if (dx * dx + dy * dy + dz * dz < rr * rr) return true;
      }
    }
    return false;
  }

  _nearPoint(e, p, r) {
    for (const s of e.spheres) {
      if (s.r <= 0) continue;
      const dx = s.x - p.x, dy = s.y - p.y, dz = s.z - p.z, rr = s.r + r;
      if (dx * dx + dy * dy + dz * dz < rr * rr) return true;
    }
    return false;
  }

  _hapticPlayer(i, ms) { for (const h of this.player.hands) this.player._haptic(h, i, ms); }

  _passTag(a, b, now) {
    a.it = false; a.setStatusLook(''); a.immuneUntil = now + 2.5; a.tags++;
    b.it = true; b.setStatusLook('it'); b.stunUntil = now + (b.isBot ? 1.6 : 0.6);
    this._applySpeed();
    this.fx.burst(b.bodyPos.x, b.bodyPos.y, b.bodyPos.z, 0xff7a2f, 22, 4, 0.7);
    if (b === this.player) { this.sfx.tag('got'); this.toast("YOU'RE IT!", '#ff7a45', true); this._hapticPlayer(1, 120); }
    else if (a === this.player) { this.sfx.tag('made'); this.toast(`Tagged ${b.name}!`, '#7bed9f'); this._hapticPlayer(0.7, 60); }
    else this.sfx.tag('other', b.bodyPos);
    this.log(`${a.name} tagged ${b.name}`);
  }

  _infect(a, b, now) {
    b.infected = true; b.infectedAt = this.elapsed; b.setStatusLook('infected');
    b.stunUntil = now + (b.isBot ? 1.2 : 0.5);
    a.tags++;
    this._applySpeed();
    this.fx.burst(b.bodyPos.x, b.bodyPos.y, b.bodyPos.z, 0x6dff7a, 22, 3.5, 0.8);
    if (b === this.player) { this.sfx.tag('got'); this.toast('SPORED! Go get them!', '#6dff7a', true); this._hapticPlayer(1, 120); }
    else if (a === this.player) { this.sfx.tag('made'); this.toast(`Spored ${b.name}!`, '#6dff7a'); this._hapticPlayer(0.7, 60); }
    else this.sfx.tag('other', b.bodyPos);
    const left = this.ents.filter((e) => !e.infected).length;
    this.log(`${a.name} spored ${b.name} (${left} left)`);
  }

  _melt(e) {
    e.alive = false; e.outTime = this.elapsed;
    this.fx.burst(e.bodyPos.x, this.lavaY + 0.2, e.bodyPos.z, 0xff5a1f, 26, 4, 0.9);
    this.sfx.sizzle(e.bodyPos);
    if (e.isBot) e.setAlive(false);
    else { e.ghost = true; e.setStatusLook('ghost'); this.toast('YOU MELTED! Spectating…', '#ff7a45', true); this._hapticPlayer(1, 200); }
    this.log(`${e.name} melted!`);
  }

  // -------------------------------------------------------------- orbs
  _buildOrbs() {
    this.orbs = [];
    const core = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(0.15, 1), new THREE.MeshBasicMaterial({ color: 0xffe27a }), ORB_COUNT);
    const halo = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(0.3, 1), new THREE.MeshBasicMaterial({ color: 0xffb347, transparent: true, opacity: 0.28, depthWrite: false, blending: THREE.AdditiveBlending }), ORB_COUNT);
    core.frustumCulled = halo.frustumCulled = false;
    this.orbCore = core; this.orbHalo = halo;
    this.scene.add(core, halo);
    for (let i = 0; i < ORB_COUNT; i++) this.orbs.push({ pos: new THREE.Vector3(), node: -1, active: false, respawnAt: 0, phase: Math.random() * 6 });
    this._m = new THREE.Matrix4(); this._q = new THREE.Quaternion(); this._s = new THREE.Vector3(); this._e = new THREE.Euler();
  }

  _placeOrb(o) {
    const nodes = this.nav.nodes;
    let best = -1;
    for (let tries = 0; tries < 40; tries++) {
      const i = Math.floor(Math.random() * nodes.length);
      const n = nodes[i];
      if (n.kind === 0 && Math.random() < 0.55) continue; // favour high, tricky spots
      let ok = true;
      for (const other of this.orbs) if (other !== o && other.active && other.pos.distanceToSquared(n) < 16) { ok = false; break; }
      if (ok) { best = i; break; }
    }
    if (best < 0) best = Math.floor(Math.random() * nodes.length);
    const n = nodes[best];
    o.node = best;
    o.pos.set(n.x, n.y + 0.15, n.z);
    o.active = true;
    o.respawnAt = 0;
  }

  _collect(o, e, now) {
    o.active = false;
    o.respawnAt = now + 4;
    e.score++;
    this.fx.burst(o.pos.x, o.pos.y, o.pos.z, 0xffd34d, 18, 3, 0.6);
    this.sfx.orb(o.pos, e === this.player);
    if (e === this.player) { this.toast(`+1 ORB  (${e.score})`, '#ffd166'); this._hapticPlayer(0.6, 50); }
    this._changed();
  }

  _animateOrbs(dt, now) {
    const show = this.state === 'play' && this.mode.id === 'orbs';
    this.orbs.forEach((o, i) => {
      const vis = show && o.active;
      const s = vis ? 1 + Math.sin(now * 5 + o.phase) * 0.12 : 0;
      this._e.set(now * 1.3 + o.phase, now * 1.7, 0);
      this._q.setFromEuler(this._e);
      this._m.compose(this._s.set(o.pos.x, o.pos.y + Math.sin(now * 2 + o.phase) * 0.08, o.pos.z), this._q, new THREE.Vector3(s, s, s));
      this.orbCore.setMatrixAt(i, this._m);
      this.orbHalo.setMatrixAt(i, this._m);
    });
    this.orbCore.instanceMatrix.needsUpdate = true;
    this.orbHalo.instanceMatrix.needsUpdate = true;
  }

  // ------------------------------------------------------------ brains
  _brain(bot, now) {
    const it = bot.intent;
    if (!bot.alive) { it.type = 'idle'; it.target = null; return; }
    const playing = this.state === 'play';
    const m = playing ? this.mode.id : 'free';
    if (m === 'tag' || m === 'infection') {
      const hunter = m === 'tag' ? bot.it : bot.infected;
      if (hunter) {
        const cur = it.type === 'chase' ? it.target : null;
        const t = this._pickTarget(bot, (e) => e.alive && (m === 'tag' ? !e.it && now >= e.immuneUntil : !e.infected), cur);
        it.type = t ? 'chase' : 'wander'; it.target = t;
      } else {
        let threat = null, td = 1e9;
        for (const e of this.ents) {
          if (e === bot || !(m === 'tag' ? e.it : e.infected)) continue;
          const d = e.bodyPos.distanceTo(bot.pos);
          if (d < td) { td = d; threat = e; }
        }
        if (threat && td < 11 * (0.75 + 0.25 * bot.skill)) { it.type = 'flee'; it.target = threat; }
        else { it.type = 'wander'; it.target = null; }
      }
    } else if (m === 'orbs') {
      let best = null, bs = 1e9;
      for (const o of this.orbs) {
        if (!o.active || !this.nav.nodes[o.node].good) continue;
        let s = o.pos.distanceTo(bot.pos) + Math.max(0, o.pos.y - bot.pos.y) * 0.8;
        for (const b of this.bots) {
          if (b !== bot && b.active && b.intent.type === 'goto' && b.intent.node === o.node && b.pos.distanceTo(o.pos) < o.pos.distanceTo(bot.pos)) s += 8;
        }
        if (s < bs) { bs = s; best = o; }
      }
      if (best) { it.type = 'goto'; it.node = best.node; it.target = null; }
      else { it.type = 'wander'; it.target = null; }
    } else if (m === 'lava') {
      const n = bot.lavaNode >= 0 ? this.nav.nodes[bot.lavaNode] : null;
      if (!n || now > bot.lavaPickAt || n.y < this.lavaY + 1.8) {
        bot.lavaNode = this._pickSafe(bot);
        bot.lavaPickAt = now + 3 + Math.random() * 3;
      }
      it.type = 'goto'; it.node = bot.lavaNode; it.target = null;
    } else {
      it.type = 'wander'; it.target = null;
    }
  }

  _pickTarget(bot, filter, current) {
    let best = null, bd = 1e9;
    for (const e of this.ents) {
      if (e === bot || !filter(e)) continue;
      let d = e.bodyPos.distanceTo(bot.pos);
      if (!e.isBot) d *= 0.75; // the human is the juiciest target
      d += Math.max(0, e.bodyPos.y - bot.pos.y - 1.5) * 1.5;
      if (e === current) d *= 0.8; // stick with a target unless someone is much closer
      if (d < bd) { bd = d; best = e; }
    }
    return best;
  }

  _pickSafe(bot) {
    const nav = this.nav;
    let best = -1, bs = -1e9;
    for (let k = 0; k < 36; k++) {
      const i = nav.randomGood();
      const n = nav.nodes[i];
      if (n.y < this.lavaY + 2.2) continue;
      const s = n.y * 1.2 - Math.hypot(n.x - bot.pos.x, n.z - bot.pos.z) * 0.45 + Math.random() * 3;
      if (s > bs) { bs = s; best = i; }
    }
    if (best < 0) {
      for (const i of nav.goodList) if (best < 0 || nav.nodes[i].y > nav.nodes[best].y) best = i;
    }
    return best;
  }
}
