#!/bin/zsh
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

python3 - << 'PY'
import json, sys
sys.path.insert(0, ".")
from opener.catalog import APPS, LAYA_URL
from opener.policy import DEFAULT_THRESHOLDS
payload = {
    "laya_url": LAYA_URL,
    "laya_container": "laya-upstream",
    "container": "laya-upstream",
    "thresholds": DEFAULT_THRESHOLDS,
    "intent": {
        "launch": "user wants a macOS application launched or brought to the front right now",
        "chat": "greeting, thanks, small talk, weather, or a question that does not launch software",
        "refuse": "user does not want any app opened: don't, never, hate",
    },
    "unspecified": "no named app matches; a generic request; or the target is not in this list.",
    "apps": APPS,
}
with open("catalog.json", "w") as f:
    json.dump(payload, f, indent=2)
    f.write("\n")
PY

app="$root/dist/Sayso.app"
rm -rf "$app"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
cp "$root/native/notch/Info.plist" "$app/Contents/Info.plist"
cp "$root/catalog.json" "$app/Contents/Resources/catalog.json"
# Decide loop ships inside the app. One implementation — the Python package.
rsync -a --delete --exclude='__pycache__' --exclude='*.pyc' "$root/opener/" "$app/Contents/Resources/opener/"
if [[ -f "$root/native/notch/AppIcon.icns" ]]; then
  cp "$root/native/notch/AppIcon.icns" "$app/Contents/Resources/AppIcon.icns"
fi

sdk="$(xcrun --show-sdk-path)"
objc="$root/dist/ExceptionCatch.o"
clang -c -fobjc-arc -isysroot "$sdk" -target arm64-apple-macos14.0 \
  -o "$objc" "$root/native/notch/ExceptionCatch.m"
swiftc -O -parse-as-library \
  -target arm64-apple-macos14.0 \
  -sdk "$sdk" \
  -import-objc-header "$root/native/notch/ExceptionCatch.h" \
  -framework AppKit -framework SwiftUI -framework Speech \
  -framework AVFoundation -framework Carbon -framework Foundation \
  -framework ApplicationServices -framework IOKit -framework CoreAudio \
  "$root/native/notch/Engine.swift" \
  "$root/native/notch/Settings.swift" \
  "$root/native/notch/SpeechListen.swift" \
  "$root/native/notch/NotchApp.swift" \
  "$objc" \
  -o "$app/Contents/MacOS/Sayso"

# Stable identity so TCC (mic/speech) survives rebuilds and restarts.
identity="-"
keychain=""
if security find-identity -v -p codesigning 2>/dev/null | grep -q "Apple Development"; then
  identity="$(security find-identity -v -p codesigning | awk -F'\"' '/Apple Development/{print $2; exit}')"
else
  pair="$("$root/scripts/ensure_codesign.sh")"
  keychain="${pair%%|*}"
  identity="${pair##*|}"
  security unlock-keychain -p "laya-opener-codesign" "$keychain" >/dev/null
  security list-keychains -d user | grep -q "$keychain" || security list-keychains -d user -s "$keychain" $(security list-keychains -d user | tr -d '"')
fi
sign=(codesign --force --deep --sign "$identity")
if [[ -n "$keychain" ]]; then
  sign+=(--keychain "$keychain")
fi
"${sign[@]}" "$app"

# Same path every time so macOS can keep mic/speech grants.
# Bundle ID + codesign identity stay com.laya.opener / "Laya Opener".
stable="$HOME/Applications/Sayso.app"
mkdir -p "$HOME/Applications"
rm -rf "$HOME/Applications/LayaOpener.app" "$stable"
ditto "$app" "$stable"
"${sign[@]}" "$stable"
echo "built $app"
echo "installed $stable"
echo "signed $identity"
