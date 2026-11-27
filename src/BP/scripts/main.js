// LAST NIGHT
//
// Everything you do after dark is written down: every step, every glance,
// every block you break. The next night it happens again. A faded copy of you
// walks your old path at the exact time you walked it. It does not see you,
// and it does not chase you. It is just remembering.
//
// But you keep going back to the same places. And if you are standing where
// you stood last night when it gets there, you trade places with your past.

import { world, system } from "@minecraft/server";

const ECHO = "lastnight:echo";
const NIGHT_START = 13000;
const NIGHT_END = 23000;
const SAMPLE = 10;                                   // ticks per recorded sample
const SLOTS = (NIGHT_END - NIGHT_START) / SAMPLE;    // 1000 samples per night
const CHUNK = 30000;                                 // dynamic property string limit is 32767
const TOUCH_DIST = 1.3;
const TOUCH_TICKS = 8;                               // x2 ticks (~0.8 s overlap to desync)
const RING_SIZE = 240;                               // last 2 minutes, for /scriptevent test

/** playerId -> { rec, past, replay, ring, warned } */
const states = new Map();

// ---------------------------------------------------------------- helpers

const valid = (e) => {
  try { return !!e && (typeof e.isValid === "function" ? e.isValid() : e.isValid); } catch { return false; }
};
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
const r1 = (n) => Math.round(n * 10);
const tod = () => world.getTimeOfDay();
const isNight = () => { const t = tod(); return t >= NIGHT_START && t < NIGHT_END; };
const nightSlot = () => (tod() - NIGHT_START) / SAMPLE;
const overworld = () => world.getDimension("overworld");

function lerpAngle(a, b, t) {
  let d = ((b - a + 540) % 360) - 180;
  return a + d * t;
}

function soundNear(dim, loc, id, opts = {}, radius = 48) {
  for (const p of world.getAllPlayers()) {
    try {
      if (p.dimension.id !== dim.id || dist(p.location, loc) > radius) continue;
      p.playSound(id, { ...opts, location: loc });
    } catch { }
  }
}

function setProp(e, key, value) {
  try { e.setProperty(key, value); } catch { }
}

function place(e, pos, facing) {
  try {
    if (facing) e.teleport(pos, { facingLocation: facing });
    else e.teleport(pos, { rotation: { x: pos.p ?? 0, y: pos.w ?? 0 } });
  } catch {
    try { e.teleport(pos); e.setRotation?.({ x: pos.p ?? 0, y: pos.w ?? 0 }); } catch { }
  }
}

function digSound(kind) {
  if (/log|plank|wood|fence|door|chest|table|bookshelf|stem|hyphae/.test(kind)) return "dig.wood";
  if (/dirt|grass|farmland|mycelium|podzol|moss|leaves|clay/.test(kind)) return "dig.grass";
  if (/sand|gravel|concrete_powder/.test(kind)) return "dig.gravel";
  if (/glass|ice/.test(kind)) return "random.glass";
  return "dig.stone";
}

function isAir(b) { return !!b && (b.isAir ?? b.typeId === "minecraft:air"); }

function findGround(dim, x, z, yHint) {
  const bx = Math.floor(x), bz = Math.floor(z), y0 = Math.floor(yHint);
  for (let dy = 0; dy <= 12; dy++) {
    for (const y of dy === 0 ? [y0] : [y0 + dy, y0 - dy]) {
      try {
        const below = dim.getBlock({ x: bx, y: y - 1, z: bz });
        if (isAir(dim.getBlock({ x: bx, y, z: bz })) && isAir(dim.getBlock({ x: bx, y: y + 1, z: bz }))
          && below && !isAir(below) && !below.typeId.includes("lava") && !below.typeId.includes("water")) {
          return { x: bx + 0.5, y, z: bz + 0.5 };
        }
      } catch { return undefined; }
    }
  }
  return undefined;
}

// ------------------------------------------------- night counter (persisted)

function getNights() { return Number(world.getDynamicProperty("ln:nights") ?? 0); }

// --------------------------------------------- recordings & persistence

const newRec = (night) => ({ night, samples: new Array(SLOTS), breaks: [] });
const sampleCount = (rec) => rec ? rec.samples.reduce((n, s) => n + (s ? 1 : 0), 0) : 0;

function encode(rec) {
  const parts = [];
  rec.samples.forEach((s, i) => { if (s) parts.push(`${i},${s.join(",")}`); });
  return parts.join("|");
}
function decode(night, str, breaksStr, len = SLOTS) {
  const rec = { night, samples: new Array(len), breaks: [] };
  if (str) for (const part of str.split("|")) {
    const [i, x, y, z, p, w] = part.split(",").map(Number);
    if (i >= 0 && i < len) rec.samples[i] = [x, y, z, p, w];
  }
  if (breaksStr) for (const part of breaksStr.split("|")) {
    const [s, x, y, z, k] = part.split(",");
    rec.breaks.push([Number(s), Number(x), Number(y), Number(z), k]);
  }
  return rec;
}

function save(player, key, rec) {
  try {
    const str = rec ? encode(rec) : "";
    const n = Math.ceil(str.length / CHUNK);
    const old = Number(player.getDynamicProperty(`ln:${key}:n`) ?? 0);
    for (let i = 0; i < Math.max(n, old); i++) {
      player.setDynamicProperty(`ln:${key}:${i}`, i < n ? str.slice(i * CHUNK, (i + 1) * CHUNK) : undefined);
    }
    player.setDynamicProperty(`ln:${key}:n`, n);
    player.setDynamicProperty(`ln:${key}:night`, rec ? rec.night : undefined);
    player.setDynamicProperty(`ln:${key}:b`, rec ? rec.breaks.slice(-300).map((b) => b.join(",")).join("|") : undefined);
  } catch { }
}

function load(player, key) {
  try {
    const night = player.getDynamicProperty(`ln:${key}:night`);
    if (night === undefined) return null;
    const n = Number(player.getDynamicProperty(`ln:${key}:n`) ?? 0);
    let str = "";
    for (let i = 0; i < n; i++) str += player.getDynamicProperty(`ln:${key}:${i}`) ?? "";
    return decode(Number(night), str, player.getDynamicProperty(`ln:${key}:b`));
  } catch { return null; }
}

// --------------------------------------------------------------- replay

function startReplay(player, st, rec, clock, isTest = false) {
  endReplay(st, false);
  if (!rec || sampleCount(rec) < 12) return;
  const now = clock();
  const idx = rec.samples.map((s, i) => (s ? i : -1)).filter((i) => i >= 0);
  const dusk = rec.samples[idx[0]];
  st.replay = {
    rec, clock, isTest,
    entity: undefined,
    lastKnown: undefined,
    prev: undefined,
    walk: 0,
    swingUntil: 0,
    touch: 0,
    frozen: false,
    lastSlot: idx[idx.length - 1],
    dusk: { x: dusk[0] / 10, y: dusk[1] / 10, z: dusk[2] / 10 },
    nextBreak: rec.breaks.findIndex((b) => b[0] >= now),
    glitchAt: !isTest && getNights() >= 3 && Math.random() < 0.5
      ? idx[Math.floor(Math.random() * idx.length)] : -1,
    glitched: false,
  };
  if (st.replay.nextBreak < 0) st.replay.nextBreak = rec.breaks.length;
}

function endReplay(st, fade = true) {
  const r = st.replay;
  st.replay = undefined;
  if (!r || !valid(r.entity)) return;
  if (fade) {
    for (let i = 0; i < 6; i++) {
      try {
        r.entity.dimension.spawnParticle("minecraft:basic_smoke_particle",
          { x: r.entity.location.x + Math.random() - 0.5, y: r.entity.location.y + Math.random() * 1.8, z: r.entity.location.z + Math.random() - 0.5 });
      } catch { }
    }
  }
  try { r.entity.remove(); } catch { }
}

function positionAt(r, slot) {
  const i = Math.floor(slot);
  const a = r.rec.samples[i];
  if (!a) return r.lastKnown; // gap (logged off, other dimension): it waits where you left
  const b = r.rec.samples[i + 1];
  const t = b ? slot - i : 0;
  const B = b ?? a;
  const pos = {
    x: (a[0] + (B[0] - a[0]) * t) / 10,
    y: (a[1] + (B[1] - a[1]) * t) / 10,
    z: (a[2] + (B[2] - a[2]) * t) / 10,
    p: a[3] + (B[3] - a[3]) * t,
    w: lerpAngle(a[4], B[4], t),
  };
  r.lastKnown = pos;
  return pos;
}

function desync(player, st) {
  const r = st.replay;
  r.frozen = true;
  const echo = r.entity;
  setProp(echo, "lastnight:walk", 0);
  setProp(echo, "lastnight:swing", false);
  place(echo, echo.location, player.getHeadLocation());
  try { player.playSound("mob.endermen.portal", { volume: 1, pitch: 0.4 }); } catch { }
  try { player.playSound("random.orb", { volume: 0.6, pitch: 0.1 }); } catch { }
  try { player.addEffect("darkness", 100, { amplifier: 0, showParticles: false }); } catch { }
  try { player.addEffect("nausea", 140, { amplifier: 0, showParticles: false }); } catch { }
  try { player.onScreenDisplay.setTitle("§0.", { subtitle: "§8§oyou weren't supposed to be here yet", fadeInDuration: 0, stayDuration: 30, fadeOutDuration: 20 }); } catch { }

  system.runTimeout(() => {
    if (!valid(player)) return;
    const dest = findGround(overworld(), r.dusk.x, r.dusk.z, r.dusk.y);
    if (dest && player.dimension.id === "minecraft:overworld") {
      try { player.teleport(dest); } catch { }
      try { player.playSound("mob.endermen.portal", { volume: 1, pitch: 0.4 }); } catch { }
      try { player.onScreenDisplay.setActionBar("§8§othis is where you were when it got dark."); } catch { }
      // your past stays where you were, staring at where you went
      if (valid(echo)) place(echo, echo.location, dest);
    } else {
      try { player.onScreenDisplay.setActionBar("§8§o...almost."); } catch { }
    }
  }, 30);
}

function updateReplay(player, st, tick) {
  const r = st.replay;
  if (r.frozen) return;
  const slot = r.clock();
  if (r.isTest && slot > r.lastSlot + 10) return endReplay(st);

  // the glitch: once, for six seconds, it stops remembering and looks at you
  if (r.glitchAt >= 0 && slot >= r.glitchAt && slot < r.glitchAt + 12 && valid(r.entity)) {
    if (!r.glitched) {
      r.glitched = true;
      setProp(r.entity, "lastnight:walk", 0);
      soundNear(r.entity.dimension, r.entity.location, "ambient.cave", { volume: 0.7, pitch: 0.5 }, 64);
    }
    place(r.entity, r.entity.location, player.getHeadLocation());
    return;
  }

  const pos = positionAt(r, slot);
  if (!pos) return;
  const dim = overworld();
  if (!valid(r.entity)) {
    try {
      r.entity = dim.spawnEntity(ECHO, pos);
    } catch { return; } // chunk not loaded: it's out there somewhere anyway
  }
  const e = r.entity;
  place(e, pos);

  // walk animation from real displacement
  const moved = r.prev ? Math.hypot(pos.x - r.prev.x, pos.z - r.prev.z) : 0;
  r.prev = pos;
  const target = Math.min(1, moved / 0.17);
  const w = r.walk * 0.6 + target * 0.4;
  if (Math.abs(w - r.walk) > 0.04 || (w < 0.05 && r.walk !== 0)) {
    r.walk = w < 0.05 ? 0 : w;
    setProp(e, "lastnight:walk", r.walk);
  }
  if (r.walk > 0.5 && tick % 8 === 0) soundNear(dim, pos, "step.stone", { volume: 0.35, pitch: 0.8 }, 24);

  // the sounds of you, mining, last night
  while (r.nextBreak < r.rec.breaks.length && r.rec.breaks[r.nextBreak][0] <= slot) {
    const [, bx, by, bz, kind] = r.rec.breaks[r.nextBreak++];
    soundNear(dim, { x: bx + 0.5, y: by + 0.5, z: bz + 0.5 }, digSound(kind), { volume: 1, pitch: 0.75 }, 56);
    setProp(e, "lastnight:swing", true);
    r.swingUntil = tick + 10;
  }
  if (r.swingUntil && tick >= r.swingUntil) { r.swingUntil = 0; setProp(e, "lastnight:swing", false); }

  // crossing paths with yourself
  if (player.dimension.id !== dim.id) return;
  const d = dist(player.location, e.location);
  if (!st.warned && d < 8) {
    st.warned = true;
    try { player.setDynamicProperty("ln:warned", true); } catch { }
    try { player.onScreenDisplay.setActionBar("§7§odon't be where you were."); } catch { }
  }
  if (d < TOUCH_DIST) {
    if (++r.touch >= TOUCH_TICKS) desync(player, st);
  } else r.touch = 0;
}

// ---------------------------------------------------------- night cycle

function beginNight(player, st, announce) {
  const nights = getNights();
  const cur = st.rec ?? load(player, "cur");
  if (cur && cur.night !== nights && sampleCount(cur) >= 12) {
    st.past = cur;
    save(player, "past", cur);
  } else if (!st.past) {
    st.past = load(player, "past");
  }
  st.rec = cur && cur.night === nights ? cur : newRec(nights);
  if (st.past) startReplay(player, st, st.past, nightSlot);
  if (announce) {
    system.runTimeout(() => {
      try {
        player.onScreenDisplay.setActionBar(st.past ? "§8§olast night is happening again." : "§8§osomething is taking notes.");
      } catch { }
    }, 60);
  }
}

function endNight(player, st) {
  if (st.rec) save(player, "cur", st.rec);
  endReplay(st);
}

function stateFor(player) {
  let st = states.get(player.id);
  if (!st) {
    st = { rec: undefined, past: undefined, replay: undefined, ring: [], warned: !!player.getDynamicProperty("ln:warned") };
    states.set(player.id, st);
    if (isNight() && world.getDynamicProperty("ln:inNight")) beginNight(player, st, false);
  }
  return st;
}

// ------------------------------------------------------------ main loop

system.runInterval(() => {
  const tick = system.currentTick;
  const night = isNight();
  const wasNight = !!world.getDynamicProperty("ln:inNight");

  if (night && !wasNight) {
    world.setDynamicProperty("ln:nights", getNights() + 1);
    world.setDynamicProperty("ln:inNight", true);
    for (const p of world.getAllPlayers()) beginNight(p, stateFor(p), true);
  } else if (!night && wasNight) {
    world.setDynamicProperty("ln:inNight", false);
    for (const p of world.getAllPlayers()) endNight(p, stateFor(p));
  }

  for (const player of world.getAllPlayers()) {
    const st = stateFor(player);
    const inOverworld = player.dimension.id === "minecraft:overworld";

    if (tick % SAMPLE === 0 && inOverworld) {
      const l = player.location, rot = player.getRotation();
      const s = [r1(l.x), r1(l.y), r1(l.z), Math.round(rot.x), Math.round(rot.y)];
      st.ring.push({ s, breaks: [] });
      if (st.ring.length > RING_SIZE) st.ring.shift();
      if (night && st.rec) {
        const slot = Math.floor(nightSlot());
        if (slot >= 0 && slot < SLOTS) st.rec.samples[slot] = s;
      }
    }
    if (night && st.rec && tick % 600 === 0) save(player, "cur", st.rec);

    if (st.replay) {
      try { updateReplay(player, st, tick); } catch { }
    }
  }

  // clean up any echo nobody is remembering anymore
  if (tick % 100 === 0) {
    const live = new Set();
    for (const st of states.values()) if (st.replay && valid(st.replay.entity)) live.add(st.replay.entity.id);
    try {
      for (const e of overworld().getEntities({ type: ECHO })) if (!live.has(e.id)) e.remove();
    } catch { }
  }
}, 2);

// ---------------------------------------------------------------- events

world.afterEvents.playerBreakBlock.subscribe(({ player, block, brokenBlockPermutation }) => {
  const st = states.get(player.id);
  if (!st || player.dimension.id !== "minecraft:overworld") return;
  const kind = (brokenBlockPermutation?.type?.id ?? "stone").replace("minecraft:", "");
  const { x, y, z } = block.location;
  if (isNight() && st.rec) st.rec.breaks.push([Math.floor(nightSlot()), x, y, z, kind]);
  const last = st.ring[st.ring.length - 1];
  if (last) last.breaks.push([x, y, z, kind]);
});

// It's you. Of course it hurts.
world.afterEvents.entityHitEntity.subscribe(({ damagingEntity, hitEntity }) => {
  if (hitEntity?.typeId !== ECHO || damagingEntity?.typeId !== "minecraft:player") return;
  try { damagingEntity.applyDamage(3); } catch { }
  try { damagingEntity.playSound("game.player.hurt", { volume: 1, pitch: 0.7 }); } catch { }
  try { damagingEntity.onScreenDisplay.setActionBar("§8§oit hurt. why did it hurt?"); } catch { }
});

world.afterEvents.playerLeave.subscribe(({ playerId }) => {
  const st = states.get(playerId);
  if (st) endReplay(st, false);
  states.delete(playerId);
});

world.afterEvents.playerSpawn.subscribe(({ player, initialSpawn }) => {
  if (!initialSpawn || player.getDynamicProperty("ln:greeted")) return;
  system.runTimeout(() => {
    try {
      player.setDynamicProperty("ln:greeted", true);
      player.sendMessage("§8§oRemember what you do tonight. Something else will.");
    } catch { }
  }, 120);
});

// Testing: /scriptevent lastnight:test  -> replays your last 2 minutes, starting now
system.afterEvents?.scriptEventReceive?.subscribe(({ id, sourceEntity: player }) => {
  if (id !== "lastnight:test" || player?.typeId !== "minecraft:player") return;
  const st = stateFor(player);
  if (st.ring.length < 12) {
    player.sendMessage("§7Walk around for a bit first, then try again.");
    return;
  }
  const rec = { night: -1, samples: st.ring.map((e) => e.s), breaks: [] };
  st.ring.forEach((e, i) => e.breaks.forEach((b) => rec.breaks.push([i, ...b])));
  const start = system.currentTick;
  startReplay(player, st, rec, () => (system.currentTick - start) / SAMPLE, true);
  player.sendMessage("§7Replaying your last two minutes. Go stand somewhere you stood.");
});
