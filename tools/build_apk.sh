#!/bin/bash
# Builds the Meta Quest APK from quest/ with Godot 4.4.1 + the OpenXR vendors plugin.
# Expects: Godot at $GODOT, Android SDK at $ANDROID_HOME (build-tools 34, platform 34, NDK r23c),
# JDK 17 at $JAVA_HOME, and Godot 4.4.1 export templates installed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GODOT="${GODOT:-/opt/qtools/godot}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/qtools/android-sdk}"
# Godot's Gradle build needs exactly JDK 17 (a preset JAVA_HOME may point at a newer JDK)
export JAVA_HOME="${JDK17_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
export PATH="$JAVA_HOME/bin:$PATH"
KEYDIR="${KEYDIR:-$HOME/.shroom-keys}"
OUT="${1:-$ROOT/quest/build/ShroomScramble.apk}"

# Godot OpenXR vendors plugin (Meta loader + manifest entries), not stored in git
if [ ! -f "$ROOT/quest/addons/godotopenxrvendors/plugin.gdextension" ]; then
  TMP="$(mktemp -d)"
  curl -sSL -o "$TMP/vendors.zip" https://github.com/GodotVR/godot_openxr_vendors/releases/download/4.0.0-stable/godotopenxrvendorsaddon.zip
  mkdir -p "$ROOT/quest/addons" && unzip -q -o "$TMP/vendors.zip" -d "$TMP/x"
  cp -r "$TMP/x/asset/addons/godotopenxrvendors" "$ROOT/quest/addons/"
  rm -rf "$TMP"
fi

# point the Godot editor at the SDK/JDK
CFG="$HOME/.config/godot"
mkdir -p "$CFG"
for f in editor_settings-4.4.tres; do
  if [ ! -f "$CFG/$f" ]; then printf '[gd_resource type="EditorSettings" format=3]\n\n[resource]\n' > "$CFG/$f"; fi
  sed -i '/^export\/android\/android_sdk_path/d; /^export\/android\/java_sdk_path/d; /^export\/android\/debug_keystore/d; /^export\/android\/debug_keystore_user/d; /^export\/android\/debug_keystore_pass/d' "$CFG/$f"
  sed -i "/^\[resource\]/a export/android/android_sdk_path = \"$ANDROID_HOME\"\nexport/android/java_sdk_path = \"$JAVA_HOME\"\nexport/android/debug_keystore = \"$KEYDIR/debug.keystore\"\nexport/android/debug_keystore_user = \"androiddebugkey\"\nexport/android/debug_keystore_pass = \"android\"" "$CFG/$f"
done

# signing keys live outside the repo
mkdir -p "$KEYDIR"
if [ ! -f "$KEYDIR/debug.keystore" ]; then
  "$JAVA_HOME/bin/keytool" -genkeypair -keystore "$KEYDIR/debug.keystore" -alias androiddebugkey -storepass android -keypass android \
    -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Android Debug,O=Android,C=US" >/dev/null 2>&1
fi
if [ ! -f "$KEYDIR/release.keystore" ]; then
  PASS="$(head -c 18 /dev/urandom | base64 | tr -d '/+=')"
  echo "$PASS" > "$KEYDIR/release.pass"; chmod 600 "$KEYDIR/release.pass"
  "$JAVA_HOME/bin/keytool" -genkeypair -keystore "$KEYDIR/release.keystore" -alias shroom -storepass "$PASS" -keypass "$PASS" \
    -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Shroom Scramble" >/dev/null 2>&1
fi
export GODOT_ANDROID_KEYSTORE_RELEASE_PATH="$KEYDIR/release.keystore"
export GODOT_ANDROID_KEYSTORE_RELEASE_USER="shroom"
export GODOT_ANDROID_KEYSTORE_RELEASE_PASSWORD="$(cat "$KEYDIR/release.pass")"

mkdir -p "$(dirname "$OUT")"
cd "$ROOT/quest"
"$GODOT" --headless --path . --import >/dev/null 2>&1 || true
"$GODOT" --headless --path . --install-android-build-template --export-release "Quest" "$OUT"
ls -la "$OUT"
