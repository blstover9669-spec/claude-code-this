// Entry point: renderer, WebXR session, desktop controls and the main loop.
import * as THREE from 'three';
import { buildWorld } from './world.js';
import { Nav } from './nav.js';
import { Player, HAND_OFFSET } from './player.js';
import { Bot, BOT_PROFILES, separateBots } from './bots.js';
import { Game } from './game.js';
import { Sfx } from './audio.js';
import { FX } from './fx.js';
import { UI, buildKiosk } from './ui.js';

const $ = (id) => document.getElementById(id);

async function boot() {
  try {
    await Promise.race([
      Promise.all([document.fonts.load('600 32px Fredoka'), document.fonts.load('700 50px Fredoka')]),
      new Promise((r) => setTimeout(r, 2500)),
    ]);
  } catch (e) { /* fall back to system fonts */ }

  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.xr.enabled = true;
  renderer.xr.setReferenceSpaceType('local-floor');
  $('app').appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(70, window.innerWidth / window.innerHeight, 0.04, 900);
  const rig = new THREE.Group();
  rig.add(camera);
  scene.add(rig);

  const sfx = new Sfx();
  const fx = new FX(scene);
  const world = buildWorld(scene);
  const kiosk = buildKiosk(scene, world.phys, world.kiosk);
  const nav = new Nav(world.phys);
  nav.build(world.regions, world.perches);
  const player = new Player({ scene, rig, camera, phys: world.phys, sfx, fx });
  player.spawnPoint.copy(world.spawn);
  const bots = BOT_PROFILES.map((p, i) => new Bot(i, p, { scene, phys: world.phys, nav, sfx, fx }));
  for (const b of bots) b.placeAt(nav.randomGood());
  const game = new Game({ scene, player, bots, nav, world, sfx, fx });
  const ui = new UI({ scene, camera, kiosk, game, player, sfx });
  player.onRespawn = () => ui.toast('Whoops! Back to the meadow', '#7bdff2');

  let mode = 'attract';
  const view = { pos: new THREE.Vector3(), quat: new THREE.Quaternion() };
  const keys = new Set();
  const desk = { yaw: 0, pitch: -0.08, fwd: 0, strafe: 0, jump: false, sprint: false };
  const tmpV = new THREE.Vector3();
  const nowSec = () => performance.now() / 1000;

  const showOverlay = (v) => $('overlay').classList.toggle('hidden', !v);
  const setDeskHud = (v) => {
    $('desk-hud').classList.toggle('hidden', !v);
    $('lock-hint').classList.toggle('hidden', !v || document.pointerLockElement === renderer.domElement);
  };

  // ---------------------------------------------------------------- VR
  function readXR(frame) {
    const ref = renderer.xr.getReferenceSpace();
    if (!ref) return;
    const pose = frame.getViewerPose(ref);
    if (pose) {
      const p = pose.transform.position, o = pose.transform.orientation;
      player.headLocal.set(p.x, p.y, p.z);
      player.headQuatLocal.set(o.x, o.y, o.z, o.w);
    }
    for (const src of frame.session.inputSources) {
      const side = src.handedness === 'left' ? 0 : src.handedness === 'right' ? 1 : -1;
      if (side < 0) continue;
      const h = player.hands[side];
      h.gamepad = src.gamepad || null;
      const space = src.gripSpace || src.targetRaySpace;
      const gp = space ? frame.getPose(space, ref) : null;
      if (gp) {
        const p = gp.transform.position, o = gp.transform.orientation;
        h.quatLocal.set(o.x, o.y, o.z, o.w);
        h.local.copy(HAND_OFFSET).applyQuaternion(h.quatLocal).add(tmpV.set(p.x, p.y, p.z));
        h.tracked = true;
      } else h.tracked = false;
    }
  }

  async function enterVR() {
    try {
      sfx.init();
      const session = await navigator.xr.requestSession('immersive-vr', { optionalFeatures: ['local-floor', 'bounded-floor', 'hand-tracking'] });
      session.addEventListener('end', onSessionEnd);
      await renderer.xr.setSession(session);
      if (renderer.xr.setFoveation) renderer.xr.setFoveation(0.5);
      if (document.pointerLockElement) document.exitPointerLock();
      mode = 'vr';
      player.startVR();
      player.setVisible(true);
      game.setHuman(true);
      showOverlay(false);
      setDeskHud(false);
      setTimeout(() => ui.toast('Punch START to play!', '#ffd166', true), 1200);
    } catch (err) {
      $('vr-note').textContent = 'Could not start VR: ' + (err && err.message ? err.message : err);
    }
  }

  function onSessionEnd() {
    mode = 'attract';
    player.mode = 'none';
    player.setVisible(false);
    game.setHuman(false);
    showOverlay(true);
  }

  // ----------------------------------------------------------- desktop
  function startDesktop() {
    sfx.init();
    mode = 'desktop';
    player.startDesktop();
    desk.yaw = 0; desk.pitch = -0.08;
    player.setVisible(true);
    game.setHuman(true);
    showOverlay(false);
    setDeskHud(true);
    try { renderer.domElement.requestPointerLock(); } catch (e) { /* ignore */ }
    ui.toast('Click START on the console!', '#ffd166', true);
  }

  function exitDesktop() {
    if (document.pointerLockElement) document.exitPointerLock();
    mode = 'attract';
    player.mode = 'none';
    player.setVisible(false);
    game.setHuman(false);
    setDeskHud(false);
    showOverlay(true);
  }

  function deskInput() {
    desk.fwd = (keys.has('KeyW') || keys.has('ArrowUp') ? 1 : 0) - (keys.has('KeyS') || keys.has('ArrowDown') ? 1 : 0);
    desk.strafe = (keys.has('KeyD') || keys.has('ArrowRight') ? 1 : 0) - (keys.has('KeyA') || keys.has('ArrowLeft') ? 1 : 0);
    desk.jump = keys.has('Space');
    desk.sprint = keys.has('ShiftLeft') || keys.has('ShiftRight');
    return desk;
  }

  window.addEventListener('keydown', (e) => {
    keys.add(e.code);
    if (mode !== 'desktop') return;
    if (e.code === 'Space' || e.code.startsWith('Arrow')) e.preventDefault();
    if (e.repeat) return;
    if (e.code === 'Enter') game.toggleRound();
    if (e.code === 'KeyE' || e.code === 'BracketRight') game.nextMode(1);
    if (e.code === 'KeyQ' || e.code === 'BracketLeft') game.nextMode(-1);
    if (e.code === 'KeyM') exitDesktop();
  });
  window.addEventListener('keyup', (e) => keys.delete(e.code));
  window.addEventListener('blur', () => keys.clear());
  renderer.domElement.addEventListener('mousedown', () => {
    if (mode !== 'desktop') return;
    if (document.pointerLockElement !== renderer.domElement) { try { renderer.domElement.requestPointerLock(); } catch (e) { /* ignore */ } return; }
    if (!ui.desktopClick(nowSec())) player.slap();
  });
  document.addEventListener('mousemove', (e) => {
    if (mode !== 'desktop' || document.pointerLockElement !== renderer.domElement) return;
    desk.yaw -= e.movementX * 0.0022;
    desk.pitch = THREE.MathUtils.clamp(desk.pitch - e.movementY * 0.0022, -1.45, 1.45);
  });
  document.addEventListener('pointerlockchange', () => {
    $('lock-hint').classList.toggle('hidden', mode !== 'desktop' || document.pointerLockElement === renderer.domElement);
  });
  $('lock-hint').addEventListener('click', () => { try { renderer.domElement.requestPointerLock(); } catch (e) { /* ignore */ } });
  $('exit-desktop').addEventListener('click', (e) => { e.stopPropagation(); exitDesktop(); });

  window.addEventListener('resize', () => {
    if (renderer.xr.isPresenting) return;
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  // ------------------------------------------------------- start screen
  const vrBtn = $('enter-vr'), note = $('vr-note');
  vrBtn.addEventListener('click', enterVR);
  $('play-desktop').addEventListener('click', startDesktop);
  if (!window.isSecureContext) {
    vrBtn.textContent = 'VR needs HTTPS';
    note.textContent = 'WebXR only works on https:// pages. Open the hosted link in your Quest browser.';
  } else if (!navigator.xr) {
    vrBtn.textContent = 'VR not available here';
    note.textContent = 'Open this page in the Meta Quest Browser to play in VR — or try it on desktop.';
  } else {
    navigator.xr.isSessionSupported('immersive-vr').then((ok) => {
      if (ok) { vrBtn.disabled = false; vrBtn.textContent = 'ENTER VR'; note.textContent = ''; }
      else { vrBtn.textContent = 'No headset found'; note.textContent = 'Open this page in the Meta Quest Browser to play in VR — or try it on desktop.'; }
    }).catch(() => { vrBtn.textContent = 'VR not available here'; });
  }

  // ---------------------------------------------------------- main loop
  function attract(now) {
    rig.position.set(0, 0, 0);
    rig.quaternion.identity();
    const a = now * 0.045 + 0.6;
    camera.position.set(Math.sin(a) * 31, 10.5 + Math.sin(now * 0.13) * 2.5, Math.cos(a) * 31);
    camera.lookAt(0, 3.5, -1);
  }

  const api = {
    THREE, renderer, scene, camera, rig, world, nav, player, bots, game, ui, sfx, fx,
    get mode() { return mode; },
    setMode(m) {
      mode = m;
      if (m === 'vrsim') { player.mode = 'vr'; player.needsSpawn = true; player.setVisible(true); game.setHuman(true); showOverlay(false); }
    },
    simStep: null,
    startDesktop, exitDesktop, separateBots,
    frames: 0,
  };
  window.__game = api;

  let last = nowSec();
  renderer.setAnimationLoop((tms, frame) => {
    const now = tms / 1000;
    let dt = now - last;
    last = now;
    if (!(dt > 0)) dt = 1 / 72;
    if (dt > 1 / 20) dt = 1 / 20;
    if (mode === 'vr' && frame) {
      readXR(frame);
      player.handleVRInput();
      player.updateVR(dt, now);
      view.pos.copy(player.head); view.quat.copy(player.headQuat);
    } else if (mode === 'vrsim') {
      if (api.simStep) api.simStep(now, dt);
      player.updateVR(dt, now);
      camera.position.copy(player.headLocal);
      camera.quaternion.copy(player.headQuatLocal);
      view.pos.copy(player.head); view.quat.copy(player.headQuat);
    } else if (mode === 'desktop') {
      player.updateDesktop(dt, now, deskInput());
      view.pos.copy(player.head); view.quat.copy(camera.quaternion);
    } else if (mode === 'freecam') {
      camera.updateMatrixWorld();
      camera.getWorldPosition(view.pos);
      camera.getWorldQuaternion(view.quat);
    } else {
      attract(now);
      camera.updateMatrixWorld();
      camera.getWorldPosition(view.pos);
      camera.getWorldQuaternion(view.quat);
    }
    for (const b of bots) b.update(dt, now);
    separateBots(bots);
    game.update(dt, now);
    ui.update(dt, now, mode, view);
    fx.update(dt, now);
    world.update(dt, now, view.pos);
    sfx.update(camera, mode === 'attract' ? 0 : player.speed());
    renderer.render(scene, camera);
    api.frames++;
  });

  $('loading').classList.add('hidden');
  showOverlay(true);
}

boot().catch((err) => {
  console.error(err);
  const el = $('loading');
  el.classList.remove('hidden');
  el.textContent = 'Something went wrong while loading: ' + (err && err.message ? err.message : err);
});
