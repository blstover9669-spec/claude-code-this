# The Hollow: a Minecraft Bedrock horror add-on

A tall, pale figure with hollow black eyes shows up at night, far behind you. It moves only when you aren't looking.

**Download:** [`dist/TheHollow.mcaddon`](dist/TheHollow.mcaddon). Open it on a device with Minecraft Bedrock and it imports both packs.

## How it behaves

| You... | It... |
|---|---|
| Turn your back at night | May appear 26–38 blocks away, at the edge of your vision |
| Have it anywhere on screen | Freezes. Your heartbeat picks up |
| Look away | Creeps 5 blocks closer every ~1.5 s, with a quiet footstep |
| Stare straight at it for ~4 s | It fades: *"...not yet."* |
| Punch it | It can't be hurt. It vanishes and leaves you blinded |
| Let it get within ~4 blocks | **Jumpscare.** It's in your face when you turn around: darkness, nausea, camera shake, 3 hearts of damage |

Walls block line of sight, so it can sneak up behind trees and hills.
It also leaves at sunrise.

At night you'll also get random **ambient scares**: footsteps following you, whispers on the action bar, cave sounds, and doors closing behind you.

## Setup
1. Import the `.mcaddon`.
2. In world settings, enable both **The Hollow** behavior pack and resource pack. Minecraft 1.21+ is required. No experimental toggles are needed (it uses the stable `@minecraft/server` 1.11.0 API).
3. Wait for night, or test it right away:
   - `/scriptevent hollow:summon` spawns one behind you (cheats on)
   - A **Spawn The Hollow** egg is in the creative inventory

## Tuning
Every timing and distance is in the `CFG` block at the top of `src/BP/scripts/main.js`.

## Building
```
python3 tools/gen_textures.py   # regenerate textures + pack icons (needs Pillow)
python3 tools/build.py          # -> dist/TheHollow.mcaddon
```
