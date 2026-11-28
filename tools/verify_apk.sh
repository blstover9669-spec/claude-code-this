#!/bin/bash
# Sanity-checks a Quest APK: package info, VR manifest entries, native libs, signature.
set -uo pipefail
APK="${1:?usage: verify_apk.sh app.apk}"
BT="${ANDROID_HOME:-/opt/qtools/android-sdk}/build-tools/34.0.0"
export JAVA_HOME="${JDK17_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
echo "== size: $(du -h "$APK" | cut -f1)"
echo "== badging"
"$BT/aapt2" dump badging "$APK" | grep -E "^package:|sdkVersion|targetSdkVersion|native-code|application-label:|launchable-activity|uses-feature" | sed 's/^/  /'
echo "== manifest: VR / OpenXR entries"
"$BT/aapt2" dump xmltree --file AndroidManifest.xml "$APK" | grep -E "category|headtracking|com.oculus|khronos|openxr|xr_mode|supportedDevices|vr" | sed 's/^ */  /' | sort -u
echo "== native libraries"
unzip -l "$APK" | grep -E "lib/.*\.so" | awk '{print "  " $1 "  " $4}'
echo "== game data"
unzip -l "$APK" | grep -E "assets/.*(\.pck|project\.binary|meshes|level)" | awk '{print "  " $1 "  " $4}' | head
echo "== signature"
"$BT/apksigner" verify --verbose --print-certs "$APK" 2>&1 | grep -E "Verifies|Verified using|Signer #1 certificate DN|WARNING" | sed 's/^/  /'
