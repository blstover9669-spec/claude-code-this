# Shroom Scramble

Arm-powered tag on floating mushroom islands — a WebXR game for Meta Quest (with a desktop fallback).

You have no legs, only hands. Your hands are solid: push against the ground, trunks, rocks or mushrooms and your body moves the other way. Let go mid-swing and you keep your momentum, so you can run, leap and climb using nothing but your arms.

## Play it

### Native Quest app (APK)

[Download ShroomScramble-quest.apk](https://github.com/blstover9669-spec/claude-code-this/raw/claude/wonderful-brahmagupta-z9wixs/releases/ShroomScramble-quest.apk) (31 MB). It's a standalone native build: Godot 4.4 with OpenXR. It launches straight into VR, needs no browser and works offline. Your hands follow the Touch controllers' grip pose.

To sideload it:

1. Turn on **developer mode** for your headset in the Meta Horizon phone app (Menu → Devices → your headset → Headset settings → Developer mode). This requires a free Meta developer account.
2. Plug the Quest into a computer and accept the "Allow USB debugging" prompt inside the headset.
3. Install the APK, either by dragging it onto [SideQuest](https://sidequestvr.com/) or with `adb install -r ShroomScramble-quest.apk`.
4. In the headset, open your app library, switch the filter to **Unknown Sources**, and launch **Shroom Scramble**.

The Godot project lives in `quest/`. It's a port of the web version: the same level, colliders, bot nav graph and sounds are exported from the web build with `tools/export_godot_data.js`, and the same physics tests pass with identical numbers. To rebuild, run `tools/build_apk.sh` (it needs Godot 4.4.1, its export templates, JDK 17 and the Android SDK).

### Web version (no install)

**On a Quest:** open this link in the Meta Quest Browser and press **ENTER VR**:

https://raw.githack.com/blstover9669-spec/claude-code-this/claude/wonderful-brahmagupta-z9wixs/index.html

The first time, githack shows a one-off "External Content Notice". Tap **Open the page** to continue.

This runs on the headset itself, with no PC involved. Both arms are tracked by your two Touch controllers, just like any other Quest game.

**On a computer:** open the same link and press **Desktop preview**. It's a keyboard-and-mouse preview for people without a headset, not the real thing.

**Shorter link (optional):** in the repo, go to *Settings → Pages*, choose *Deploy from a branch*, select this branch and `/ (root)`, then save. The game will then be at `https://blstover9669-spec.github.io/claude-code-this/`.

## How to move (VR)

- **Run:** put your hands on the ground and swing them backwards, one after the other.
- **Jump:** push down hard with both hands, then lift them.
- **Climb:** reach up a trunk, stem or wall and pull down; repeat hand over hand.
- **Fling:** let go mid-push. Your speed carries you through the air.
- **Pink spotted caps are bouncy** — slap one (or land on it) to launch. **Crystals are slippery.** **Clouds** are soft and climbable.
- **Right thumbstick:** snap turn (you can switch it off on the console).

Punch the buttons on the wooden console next to the spawn point to start a round, change the mode, set the number of bots (3/5/7/9), pick a difficulty, change your colour, or toggle snap turn. Your left wrist shows the timer and your status.

## Modes

| Mode | Goal |
| --- | --- |
| **Tag** | One player is IT. Touch someone to pass it on. Least total time as IT wins. |
| **Spore Tag** | Touching spreads spores. Stay clean until the timer runs out. |
| **Orb Rush** | Grab the glowing orbs hidden around the islands, many of them up high. Most orbs wins. |
| **Lava Rise** | Lava rises from below. Climb high and be the last one standing. |

The bots ("fuzzlings") gallop on their hands, pounce on you when they're IT, dodge and flee when they're not, and plan routes across the islands, including jumps between mushroom caps, decks, rocks and clouds.

## Desktop controls

`WASD` move · mouse look · `Space` jump · `Shift` sprint · hold `W` against a wall to climb · click to slap (or press console buttons) · `Enter` start/stop round · `Q`/`E` change mode · `M` back to the menu.

## How it works

- **Arm locomotion** (`src/player.js`): each hand is a small sphere swept from where it was to where your controller is. When it hits something, the hand sticks to that spot and your body is moved so that the hand stays put. Lifting a hand off a surface releases it, and when your last hand lets go you get the average velocity of the last ~85 ms of body motion (with a small boost and a cap).
- **Collision** (`src/physics.js`): the whole level is built from signed-distance primitives (spheres, boxes, capsules, cylinders, half-ellipsoids). Every visible solid has a matching collider, so your hands hit exactly what you see.
- **Bots** (`src/nav.js`, `src/bots.js`): a navigation graph of ground and perch nodes. Every jump edge is a ballistic arc that has been checked against the world before use, and the bots path with A*.
- **Everything else**: the sound is synthesised with WebAudio (each surface has its own hand-tap sound, plus spatial bot chirps), and the level is built from merged, vertex-coloured low-poly meshes so it runs comfortably on a Quest.

No build step: it's plain ES modules plus three.js from a CDN. To run it locally, serve the folder (`python3 -m http.server`) and open `http://localhost:8000`. WebXR needs `https://` or `localhost`.
