# Last Night: a Minecraft Bedrock horror add-on

Everything you do after dark gets recorded.
**The next night, it happens again.**

A faded, glitching copy of you walks the exact path you walked last night, at the exact time you walked it. It looks where you looked, and it mines what you mined, so you'll hear your own pickaxe out in the dark. It doesn't see you and it doesn't chase you. It's just remembering.

The catch is that you keep going back to the same places: your base, your mine, the path home. **If you're standing where you stood last night when it gets there, you trade places with your past.** The screen goes black and you wake up wherever you were at sunset the night before. Your past self stays behind, staring at the spot you vanished to.

## Rules it follows
- It replays **only your most recent night**. Each night overwrites the one before.
- If you logged off or went to the Nether last night, it stops where you left and waits there.
- If you slept last night, it stands beside your bed.
- Hitting it hurts **you**.
- After a few nights, sometimes it stops remembering for a moment and turns to look at you.
- It fades at dawn.

Every player in multiplayer has their own copy.

## Setup
1. Open `dist/LastNight.mcaddon` to import it.
2. In world settings, enable both **Last Night** packs. Minecraft 1.21+ is required, with no experimental toggles (it uses the stable `@minecraft/server` 1.11.0 API).
3. The first night is quiet, because that's when it starts recording.

**Quick test:** walk around for a minute, then run `/scriptevent lastnight:test` (cheats on). This replays your last 2 minutes starting now. Walk back over your own path and see what happens.

## Building
```
python3 tools/gen_textures.py   # textures + icons (Pillow)
python3 tools/build.py          # -> dist/LastNight.mcaddon
```
