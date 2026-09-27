#!/bin/zsh
# Build Sayso, then a zip + a drag-to-Applications DMG for GitHub Releases.
# Usage: ./scripts/package_release.sh [version]
# Default version is CFBundleShortVersionString from Info.plist.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

plist="$root/native/notch/Info.plist"
version="${1:-$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$plist")}"
if [[ -z "$version" ]]; then
  echo "no version" >&2
  exit 2
fi

"$root/scripts/build_app.sh"

app="$root/dist/Sayso.app"
if [[ ! -x "$app/Contents/MacOS/Sayso" ]]; then
  echo "missing $app" >&2
  exit 2
fi

stage="$root/dist/release"
rm -rf "$stage"
mkdir -p "$stage"

zip_name="Sayso-${version}-macos-arm64.zip"
dmg_name="Sayso-${version}-macos-arm64.dmg"
zip_path="$stage/$zip_name"
dmg_path="$stage/$dmg_name"

# Zip of the signed .app — unzip anywhere, then drag into /Applications.
(
  cd "$root/dist"
  ditto -c -k --keepParent "Sayso.app" "$zip_path"
)

# DMG with the app + an Applications shortcut so Finder is a one-drag install.
vol="Sayso ${version}"
work="$(mktemp -d "${TMPDIR:-/tmp}/sayso-dmg.XXXXXX")"
trap 'rm -rf "$work"' EXIT
ditto "$app" "$work/Sayso.app"
ln -s /Applications "$work/Applications"

# Hide the Applications symlink's name clutter is fine; users know the folder.
hdiutil create \
  -volname "$vol" \
  -srcfolder "$work" \
  -ov \
  -format UDZO \
  -imagekey zlib-level=9 \
  "$dmg_path" >/dev/null

# README for the release folder / anyone who unzips the repo artifact.
cat > "$stage/INSTALL.txt" <<EOF
Sayso ${version} — macOS 14+ Apple Silicon

Install
  1. Open Sayso-${version}-macos-arm64.dmg
  2. Drag Sayso into Applications
  3. Open Applications → Sayso (right-click → Open the first time if Gatekeeper asks)
  4. Grant Microphone and Speech Recognition
  5. Hover the purple notch dot, press Control-Option-Space, or say Hey Mac

Or unzip Sayso-${version}-macos-arm64.zip and drag Sayso.app into Applications.

Default engine is Off. Named apps, system settings, and URLs work with no Docker
and no API key. Turn on Laya or Jev in Settings only for paraphrases.

Uninstall
  Quit Sayso from the menu-bar waveform, then move Sayso.app to the Trash.
EOF

echo "zip $zip_path"
echo "dmg $dmg_path"
ls -lh "$zip_path" "$dmg_path"
