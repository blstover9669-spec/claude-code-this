// All sound is synthesised on the fly with WebAudio: hand taps that depend on
// the surface, boings, chirps, tag stingers and a soft windy ambience.
export class Sfx {
  constructor() {
    this.ctx = null;
    this.master = null;
    this.nextBird = 0;
    this.windLevel = 0;
    this._f = { x: 0, y: 0, z: -1 };
  }

  init() {
    if (this.ctx) { if (this.ctx.state === 'suspended') this.ctx.resume(); return; }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ctx = (this.ctx = new AC());
    this.master = ctx.createGain();
    this.master.gain.value = 0.85;
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -14; comp.knee.value = 10; comp.ratio.value = 4;
    comp.attack.value = 0.003; comp.release.value = 0.2;
    this.master.connect(comp);
    comp.connect(ctx.destination);
    const len = Math.floor(ctx.sampleRate * 1.5);
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    this.noise = buf;
    this._ambience();
  }

  get t() { return this.ctx.currentTime; }

  _out(pos, gain = 1) {
    const ctx = this.ctx;
    const g = ctx.createGain();
    g.gain.value = gain;
    if (pos) {
      const p = ctx.createPanner();
      p.panningModel = 'HRTF';
      p.distanceModel = 'inverse';
      p.refDistance = 1.2; p.maxDistance = 80; p.rolloffFactor = 1.15;
      if (p.positionX) { p.positionX.value = pos.x; p.positionY.value = pos.y; p.positionZ.value = pos.z; }
      else p.setPosition(pos.x, pos.y, pos.z);
      g.connect(p); p.connect(this.master);
    } else g.connect(this.master);
    return g;
  }

  _env(g, t0, peak, dur, attack = 0.004) {
    g.gain.setValueAtTime(0.0001, t0);
    g.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak), t0 + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  }

  _noise(dest, t0, dur, type, freq, q, peak) {
    const ctx = this.ctx;
    const src = ctx.createBufferSource();
    src.buffer = this.noise;
    const f = ctx.createBiquadFilter();
    f.type = type; f.frequency.value = freq; f.Q.value = q;
    const g = ctx.createGain();
    this._env(g, t0, peak, dur);
    src.connect(f); f.connect(g); g.connect(dest);
    src.start(t0, Math.random());
    src.stop(t0 + dur + 0.03);
  }

  _tone(dest, t0, dur, type, f0, f1, peak, attack = 0.004) {
    const ctx = this.ctx;
    const o = ctx.createOscillator();
    o.type = type;
    o.frequency.setValueAtTime(f0, t0);
    if (f1 !== f0) o.frequency.exponentialRampToValueAtTime(f1, t0 + dur);
    const g = ctx.createGain();
    this._env(g, t0, peak, dur, attack);
    o.connect(g); g.connect(dest);
    o.start(t0);
    o.stop(t0 + dur + 0.03);
  }

  tap(mat, s, pos) {
    if (!this.ctx) return;
    const t = this.t, out = this._out(pos, 1), r = 0.9 + Math.random() * 0.2;
    s = Math.max(0.08, Math.min(1, s));
    switch (mat) {
      case 'wood':
        this._noise(out, t, 0.05, 'bandpass', 1500 * r, 3, 0.55 * s);
        this._tone(out, t, 0.09, 'triangle', 280 * r, 180 * r, 0.6 * s);
        break;
      case 'stone':
        this._noise(out, t, 0.04, 'highpass', 2300 * r, 0.8, 0.5 * s);
        this._tone(out, t, 0.06, 'sine', 170 * r, 95 * r, 0.5 * s);
        break;
      case 'cap':
        this._noise(out, t, 0.08, 'lowpass', 650 * r, 1, 0.45 * s);
        this._tone(out, t, 0.12, 'sine', 150 * r, 100 * r, 0.65 * s);
        break;
      case 'leaf':
        this._noise(out, t, 0.16, 'bandpass', 3000 * r, 0.6, 0.5 * s);
        this._tone(out, t, 0.05, 'sine', 130 * r, 90 * r, 0.25 * s);
        break;
      case 'crystal':
        this._tone(out, t, 0.6, 'sine', 1568 * r, 1568 * r, 0.16 * s, 0.002);
        this._tone(out, t, 0.4, 'sine', 2349 * r, 2349 * r, 0.09 * s, 0.002);
        this._noise(out, t, 0.03, 'highpass', 5000, 0.7, 0.2 * s);
        break;
      case 'cloud':
        this._noise(out, t, 0.18, 'lowpass', 420 * r, 0.5, 0.5 * s);
        this._tone(out, t, 0.15, 'sine', 220 * r, 320 * r, 0.22 * s);
        break;
      case 'shroom':
        this.boing(pos, s);
        break;
      default:
        this._noise(out, t, 0.09, 'lowpass', 900 * r, 0.7, 0.5 * s);
        this._tone(out, t, 0.08, 'sine', 125 * r, 70 * r, 0.55 * s);
    }
  }

  boing(pos, s = 1) {
    if (!this.ctx) return;
    const t = this.t, out = this._out(pos, 1), r = 0.92 + Math.random() * 0.16;
    this._tone(out, t, 0.32, 'sine', 160 * r, 560 * r, 0.55 * s, 0.006);
    this._tone(out, t + 0.01, 0.26, 'triangle', 320 * r, 1040 * r, 0.16 * s, 0.006);
    this._noise(out, t, 0.06, 'lowpass', 500, 1, 0.35 * s);
  }

  chirp(pos, pitch = 1) {
    if (!this.ctx) return;
    const t = this.t, out = this._out(pos, 0.9);
    this._tone(out, t, 0.06, 'sine', 1150 * pitch, 1900 * pitch, 0.2, 0.003);
    this._tone(out, t + 0.065, 0.08, 'sine', 1600 * pitch, 1050 * pitch, 0.16, 0.003);
  }

  tag(kind, pos) {
    if (!this.ctx) return;
    const t = this.t;
    if (kind === 'made') {
      const out = this._out(null, 0.5);
      [784, 988, 1319].forEach((f, i) => this._tone(out, t + i * 0.07, 0.16, 'square', f, f, 0.22));
    } else if (kind === 'got') {
      const out = this._out(null, 0.55);
      this._tone(out, t, 0.18, 'sawtooth', 660, 640, 0.25);
      this._tone(out, t + 0.16, 0.32, 'sawtooth', 440, 330, 0.25);
      this._noise(out, t, 0.25, 'bandpass', 1200, 1, 0.2);
    } else {
      const out = this._out(pos, 0.9);
      this._tone(out, t, 0.14, 'square', 900, 1400, 0.12);
      this._noise(out, t, 0.12, 'highpass', 3000, 0.8, 0.12);
    }
  }

  orb(pos, mine) {
    if (!this.ctx) return;
    const t = this.t, out = this._out(mine ? null : pos, mine ? 0.5 : 0.8);
    this._tone(out, t, 0.18, 'sine', 1319, 1319, 0.3);
    this._tone(out, t + 0.08, 0.35, 'sine', 1976, 1976, 0.26);
    this._noise(out, t, 0.2, 'highpass', 6000, 0.7, 0.08);
  }

  sizzle(pos) {
    if (!this.ctx) return;
    const t = this.t, out = this._out(pos, 1);
    this._noise(out, t, 0.7, 'highpass', 2500, 0.6, 0.5);
    this._tone(out, t, 0.5, 'sawtooth', 120, 50, 0.25);
  }

  click(pos) {
    if (!this.ctx) return;
    const t = this.t, out = this._out(pos, 0.8);
    this._tone(out, t, 0.05, 'square', 1200, 900, 0.15);
    this._noise(out, t, 0.02, 'highpass', 4000, 0.7, 0.2);
  }

  beep(go) {
    if (!this.ctx) return;
    const t = this.t, out = this._out(null, 0.4);
    this._tone(out, t, go ? 0.45 : 0.14, 'square', go ? 988 : 660, go ? 988 : 660, 0.3);
  }

  horn() {
    if (!this.ctx) return;
    const t = this.t, out = this._out(null, 0.35);
    for (const f of [262, 392, 523]) this._tone(out, t, 0.6, 'sawtooth', f, f * 1.01, 0.18, 0.02);
  }

  fanfare(win) {
    if (!this.ctx) return;
    const t = this.t, out = this._out(null, 0.4);
    const notes = win ? [523, 659, 784, 1047, 1319] : [523, 494, 440];
    notes.forEach((f, i) => this._tone(out, t + i * 0.11, 0.3, 'triangle', f, f, 0.32));
  }

  whoosh() {
    if (!this.ctx) return;
    const t = this.t, out = this._out(null, 0.4);
    this._noise(out, t, 0.18, 'bandpass', 900, 1.2, 0.35);
  }

  whooshUp() {
    if (!this.ctx) return;
    const t = this.t, out = this._out(null, 0.4);
    this._tone(out, t, 0.5, 'sine', 300, 1200, 0.2, 0.05);
  }

  _ambience() {
    const ctx = this.ctx;
    const wind = ctx.createBufferSource();
    wind.buffer = this.noise; wind.loop = true;
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass'; lp.frequency.value = 380;
    const g = ctx.createGain(); g.gain.value = 0.05;
    const lfo = ctx.createOscillator(); lfo.frequency.value = 0.07;
    const lfoG = ctx.createGain(); lfoG.gain.value = 0.025;
    lfo.connect(lfoG); lfoG.connect(g.gain);
    wind.connect(lp); lp.connect(g); g.connect(this.master);
    wind.start(); lfo.start();
    // speed whoosh, driven by player speed
    const rush = ctx.createBufferSource();
    rush.buffer = this.noise; rush.loop = true;
    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass'; bp.frequency.value = 700; bp.Q.value = 0.7;
    this.rushGain = ctx.createGain(); this.rushGain.gain.value = 0;
    this.rushFilter = bp;
    rush.connect(bp); bp.connect(this.rushGain); this.rushGain.connect(this.master);
    rush.start();
  }

  _bird(t) {
    const a = Math.random() * Math.PI * 2, d = 18 + Math.random() * 25;
    const pos = { x: Math.cos(a) * d, y: 6 + Math.random() * 10, z: Math.sin(a) * d };
    const out = this._out(pos, 0.5);
    const base = 2200 + Math.random() * 1600, n = 2 + Math.floor(Math.random() * 4);
    for (let i = 0; i < n; i++) this._tone(out, t + i * 0.11, 0.08, 'sine', base, base * (0.75 + Math.random() * 0.6), 0.09, 0.005);
  }

  update(camera, speed) {
    if (!this.ctx) return;
    const L = this.ctx.listener, e = camera.matrixWorld.elements;
    const px = e[12], py = e[13], pz = e[14];
    const fx = -e[8], fy = -e[9], fz = -e[10], ux = e[4], uy = e[5], uz = e[6];
    if (L.positionX) {
      L.positionX.value = px; L.positionY.value = py; L.positionZ.value = pz;
      L.forwardX.value = fx; L.forwardY.value = fy; L.forwardZ.value = fz;
      L.upX.value = ux; L.upY.value = uy; L.upZ.value = uz;
    } else {
      L.setPosition(px, py, pz);
      L.setOrientation(fx, fy, fz, ux, uy, uz);
    }
    const t = this.t;
    const target = Math.min(1, Math.max(0, (speed - 2.5) / 9));
    this.rushGain.gain.setTargetAtTime(target * 0.32, t, 0.08);
    this.rushFilter.frequency.setTargetAtTime(500 + target * 900, t, 0.1);
    if (t > this.nextBird) {
      if (this.nextBird > 0) this._bird(t);
      this.nextBird = t + 3 + Math.random() * 6;
    }
  }
}
