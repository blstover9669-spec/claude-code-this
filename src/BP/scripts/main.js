// The Hollow — a stalker that only moves when you are not looking.
//
//  * At night it appears far behind you, at the edge of your vision.
//  * While it is on your screen it stays frozen.
//  * Look away and it creeps closer.
//  * Stare straight at it for a few seconds and it fades away... for now.
//  * Let it reach you and it will be in your face when you turn around.

import { world, system } from "@minecraft/server";

const ID = "hollow:watcher";
const TICK_RATE = 10; // logic runs every 10 game ticks (0.5s)

const CFG = {
  spawnCheckEvery: 200,      // ticks between spawn rolls per player
  spawnChance: 0.25,
  cooldownAfterEncounter: 1800,
  spawnDistMin: 26,
  spawnDistMax: 38,
  creepEvery: 3,             // unseen intervals between creeps (x0.5s)
  creepStep: 5,
  attackRange: 4.5,
  stareToBanish: 8,          // intervals (x0.5s) of direct stare
  onScreenDot: 0.80,         // ~37 deg: counts as "in view"
  stareDot: 0.975,           // ~13 deg: counts as "staring"
  jumpscareDamage: 6,
  ambientMin: 900,
  ambientMax: 2400,
};

/** watcherId -> state */
const stalkers = new Map();
/** playerId -> { nextSpawnRoll, cooldownUntil, nextAmbient } */
const players = new Map();

const WHISPERS = [
  "§7§o...it's behind you...",
  "§7§odon't turn around",
  "§7§oyou left the door open",
  "§7§owe see you",
  "§7§owhy are you still awake?",
  "§7§okeep looking. keep looking.",
  "§8§o...h e l l o...",
];

// ---------- helpers ----------

const valid = (e) => {
  try {
    if (!e) return false;
    return typeof e.isValid === "function" ? e.isValid() : e.isValid;
  } catch { return false; }
};
const sub = (a, b) => ({ x: a.x - b.x, y: a.y - b.y, z: a.z - b.z });
const len = (v) => Math.hypot(v.x, v.y, v.z);
const norm = (v) => { const l = len(v) || 1; return { x: v.x / l, y: v.y / l, z: v.z / l }; };
const dot = (a, b) => a.x * b.x + a.y * b.y + a.z * b.z;
const rand = (a, b) => a + Math.random() * (b - a);
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

const isNight = () => {
  const t = world.getTimeOfDay();
  return t >= 13000 && t <= 23000;
};

function run(entity, cmd) {
  try {
    if (typeof entity.runCommand === "function") entity.runCommand(cmd);
    else entity.runCommandAsync(cmd);
  } catch { /* command not available on this version */ }
}

function sound(player, id, opts = {}) {
  try { player.playSound(id, opts); } catch { }
}

function particles(dim, loc, id = "minecraft:soul_particle", n = 8) {
  for (let i = 0; i < n; i++) {
    try {
      dim.spawnParticle(id, { x: loc.x + rand(-0.4, 0.4), y: loc.y + rand(0, 2.8), z: loc.z + rand(-0.4, 0.4) });
    } catch { return; }
  }
}

function isAir(b) {
  if (!b) return false;
  return b.isAir ?? b.typeId === "minecraft:air";
}
function isStandable(b) {
  if (!b || isAir(b)) return false;
  if (b.isLiquid) return false;
  const t = b.typeId;
  return !(t.includes("water") || t.includes("lava"));
}

/** Finds a spot where the Hollow can stand near (x, z), scanning around yHint. */
function findGround(dim, x, z, yHint, range = 14) {
  const bx = Math.floor(x), bz = Math.floor(z), y0 = Math.floor(yHint);
  for (let dy = 0; dy <= range; dy++) {
    for (const y of dy === 0 ? [y0] : [y0 + dy, y0 - dy]) {
      try {
        const feet = dim.getBlock({ x: bx, y, z: bz });
        const head = dim.getBlock({ x: bx, y: y + 1, z: bz });
        const below = dim.getBlock({ x: bx, y: y - 1, z: bz });
        if (isAir(feet) && isAir(head) && isStandable(below)) {
          return { x: bx + 0.5, y, z: bz + 0.5 };
        }
      } catch { return undefined; } // unloaded chunk / out of bounds
    }
  }
  return undefined;
}

/** Returns { onScreen, staring, dist } for player -> hollow. */
function viewState(player, hollow) {
  const eye = player.getHeadLocation();
  const target = { x: hollow.location.x, y: hollow.location.y + 2.4, z: hollow.location.z };
  const to = sub(target, eye);
  const dist = len(to);
  const dir = norm(to);
  const d = dot(dir, player.getViewDirection());
  let visible = d >= CFG.onScreenDot;
  if (visible) {
    // blocked by terrain? then you can't actually see it
    try {
      const hit = player.dimension.getBlockFromRay(eye, dir, {
        maxDistance: dist, includeLiquidBlocks: false, includePassableBlocks: false,
      });
      if (hit && hit.block && len(sub(hit.block.location, eye)) < dist - 1.5) visible = false;
    } catch { }
  }
  return { onScreen: visible, staring: visible && d >= CFG.stareDot, dist };
}

function pstate(player) {
  let s = players.get(player.id);
  if (!s) {
    const now = system.currentTick;
    s = { nextSpawnRoll: now + CFG.spawnCheckEvery, cooldownUntil: 0, nextAmbient: now + rand(CFG.ambientMin, CFG.ambientMax) };
    players.set(player.id, s);
  }
  return s;
}

function hasStalker(player) {
  for (const s of stalkers.values()) if (s.targetId === player.id) return true;
  return false;
}

// ---------- spawning / removal ----------

function spawnFor(player, forced = false) {
  if (player.dimension.id !== "minecraft:overworld" && !forced) return false;
  const view = player.getViewDirection();
  const back = Math.atan2(-view.z, -view.x);
  for (let attempt = 0; attempt < 8; attempt++) {
    const ang = back + rand(-1.0, 1.0);
    const r = rand(CFG.spawnDistMin, CFG.spawnDistMax);
    const x = player.location.x + Math.cos(ang) * r;
    const z = player.location.z + Math.sin(ang) * r;
    const spot = findGround(player.dimension, x, z, player.location.y + 4, 20);
    if (!spot) continue;
    try {
      const h = player.dimension.spawnEntity(ID, spot);
      h.teleport(spot, { facingLocation: player.location });
      stalkers.set(h.id, { targetId: player.id, seen: 0, unseen: 0, spotted: false, attacking: false, manual: forced });
      return true;
    } catch { return false; }
  }
  return false;
}

function vanish(hollow, player, loud = false) {
  const s = stalkers.get(hollow.id);
  stalkers.delete(hollow.id);
  if (player) {
    pstate(player).cooldownUntil = system.currentTick + CFG.cooldownAfterEncounter;
    sound(player, loud ? "mob.endermen.portal" : "ambient.cave", { location: hollow.location, volume: loud ? 1 : 0.6, pitch: 0.5 });
  }
  if (valid(hollow)) {
    particles(hollow.dimension, hollow.location);
    try { hollow.remove(); } catch { }
  }
  return s;
}

// ---------- the scare ----------

function jumpscare(hollow, player, state) {
  state.attacking = true;
  const eye = player.getHeadLocation();
  const v = player.getViewDirection();
  // put it right in front of the player's face
  const loc = { x: eye.x + v.x * 1.3, y: player.location.y - 0.4, z: eye.z + v.z * 1.3 };
  try { hollow.teleport(loc, { facingLocation: eye }); } catch { }
  sound(player, "mob.endermen.stare", { volume: 1.0, pitch: 0.6 });
  sound(player, "mob.warden.roar", { volume: 0.8, pitch: 1.6 });
  try { player.addEffect("darkness", 120, { amplifier: 0, showParticles: false }); } catch { }
  try { player.addEffect("nausea", 160, { amplifier: 0, showParticles: false }); } catch { }
  try { player.addEffect("slowness", 40, { amplifier: 3, showParticles: false }); } catch { }
  run(player, "camerashake add @s 0.6 1.2 positional");
  try { player.onScreenDisplay.setTitle("§4§l ", { subtitle: "§8found you", fadeInDuration: 0, stayDuration: 20, fadeOutDuration: 10 }); } catch { }
  system.runTimeout(() => {
    try { player.applyDamage(CFG.jumpscareDamage); } catch { }
  }, 6);
  system.runTimeout(() => { if (valid(hollow)) vanish(hollow, player, true); }, 18);
}

// ---------- per-tick logic ----------

function creepCloser(hollow, player) {
  const to = sub(player.location, hollow.location);
  const flat = norm({ x: to.x, y: 0, z: to.z });
  const step = Math.min(CFG.creepStep, len(to) - 2);
  const nx = hollow.location.x + flat.x * step + rand(-1.5, 1.5);
  const nz = hollow.location.z + flat.z * step + rand(-1.5, 1.5);
  const spot = findGround(hollow.dimension, nx, nz, hollow.location.y + 1, 8);
  if (!spot) return;
  try { hollow.teleport(spot, { facingLocation: player.getHeadLocation() }); } catch { }
  // a single quiet footstep behind you
  if (Math.random() < 0.6) sound(player, "step.gravel", { location: spot, volume: 0.5, pitch: 0.6 });
}

function updateStalker(hollow, state) {
  const player = world.getAllPlayers().find((p) => p.id === state.targetId);
  if (!player || !valid(player) || player.dimension.id !== hollow.dimension.id) return vanish(hollow);
  if (state.attacking) return;
  if (!isNight() && !state.manual) return vanish(hollow, player);

  const { onScreen, staring, dist } = viewState(player, hollow);
  if (dist > 90) return vanish(hollow, player);

  if (onScreen) {
    state.unseen = 0;
    if (!state.spotted) {
      state.spotted = true;
      sound(player, "mob.warden.heartbeat", { volume: 1.0, pitch: 0.7 });
    }
    if (staring) {
      state.seen++;
      if (state.seen === 3) sound(player, "mob.warden.heartbeat", { volume: 1.0, pitch: 0.9 });
      if (state.seen >= CFG.stareToBanish) {
        try { player.onScreenDisplay.setActionBar("§8§o...not yet."); } catch { }
        return vanish(hollow, player);
      }
    } else {
      state.seen = Math.max(0, state.seen - 1);
    }
    return;
  }

  // not on screen -> it moves
  state.seen = 0;
  state.unseen++;
  if (dist <= CFG.attackRange) return jumpscare(hollow, player, state);
  if (state.unseen % CFG.creepEvery === 0) creepCloser(hollow, player);
}

function ambientScare(player) {
  const roll = Math.random();
  const v = player.getViewDirection();
  const behind = { x: player.location.x - v.x * 3, y: player.location.y, z: player.location.z - v.z * 3 };
  if (roll < 0.35) {
    // footsteps that follow you
    for (let i = 0; i < 4; i++) {
      system.runTimeout(() => {
        if (!valid(player)) return;
        const vv = player.getViewDirection();
        const loc = { x: player.location.x - vv.x * (4 - i * 0.6), y: player.location.y, z: player.location.z - vv.z * (4 - i * 0.6) };
        sound(player, "step.grass", { location: loc, volume: 0.8, pitch: 0.8 });
      }, i * 9);
    }
  } else if (roll < 0.65) {
    try { player.onScreenDisplay.setActionBar(pick(WHISPERS)); } catch { }
    sound(player, "ambient.soulsand_valley.mood", { location: behind, volume: 0.8, pitch: 0.6 });
  } else if (roll < 0.85) {
    sound(player, "ambient.cave", { location: behind, volume: 1.0, pitch: 0.8 });
  } else {
    sound(player, "random.door_close", { location: behind, volume: 0.6, pitch: 0.7 });
  }
}

system.runInterval(() => {
  const now = system.currentTick;

  // clean up orphans (e.g. after a world reload) and update live stalkers
  const alive = new Set();
  for (const dimId of ["overworld", "nether", "the_end"]) {
    let list = [];
    try { list = world.getDimension(dimId).getEntities({ type: ID }); } catch { }
    for (const h of list) {
      const s = stalkers.get(h.id);
      if (!s) { try { h.remove(); } catch { } continue; }
      alive.add(h.id);
      try { updateStalker(h, s); } catch { }
    }
  }
  // forget stalkers whose entity is gone (unloaded chunk etc.)
  for (const [id, s] of stalkers) if (!alive.has(id) && !s.attacking) stalkers.delete(id);

  if (!isNight()) return;
  for (const player of world.getAllPlayers()) {
    const s = pstate(player);
    if (now >= s.nextAmbient) {
      s.nextAmbient = now + rand(CFG.ambientMin, CFG.ambientMax);
      ambientScare(player);
    }
    if (now >= s.nextSpawnRoll) {
      s.nextSpawnRoll = now + CFG.spawnCheckEvery;
      if (now >= s.cooldownUntil && !hasStalker(player) && Math.random() < CFG.spawnChance) spawnFor(player);
    }
  }
}, TICK_RATE);

// Hitting it doesn't hurt it. It just leaves, and it isn't happy about it.
world.afterEvents.entityHitEntity.subscribe(({ damagingEntity, hitEntity }) => {
  if (hitEntity?.typeId !== ID || damagingEntity?.typeId !== "minecraft:player") return;
  try { damagingEntity.addEffect("blindness", 50, { amplifier: 0, showParticles: false }); } catch { }
  vanish(hitEntity, damagingEntity, true);
});

// Spawn eggs / /summon: adopt the nearest player as the target.
world.afterEvents.entitySpawn.subscribe(({ entity }) => {
  if (entity?.typeId !== ID || stalkers.has(entity.id)) return;
  system.runTimeout(() => {
    if (!valid(entity) || stalkers.has(entity.id)) return;
    let best, bestD = Infinity;
    for (const p of entity.dimension.getPlayers()) {
      const d = len(sub(p.location, entity.location));
      if (d < bestD) { bestD = d; best = p; }
    }
    if (best) stalkers.set(entity.id, { targetId: best.id, seen: 0, unseen: 0, spotted: false, attacking: false, manual: true });
    else try { entity.remove(); } catch { }
  }, 1);
});

// First join greeting
world.afterEvents.playerSpawn.subscribe(({ player, initialSpawn }) => {
  if (!initialSpawn) return;
  system.runTimeout(() => {
    try { player.sendMessage("§8You feel like you're being watched."); } catch { }
  }, 100);
});

// Testing: /scriptevent hollow:summon
system.afterEvents?.scriptEventReceive?.subscribe(({ id, sourceEntity }) => {
  if (id !== "hollow:summon" || sourceEntity?.typeId !== "minecraft:player") return;
  if (!spawnFor(sourceEntity, true)) sourceEntity.sendMessage("§cNo place for it to stand. It will find one later.");
});
