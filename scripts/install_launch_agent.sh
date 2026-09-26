#!/bin/zsh
# Install the login LaunchAgent with this user's $HOME substituted in.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
src="$root/scripts/com.laya.opener.plist"
dst="$HOME/Library/LaunchAgents/com.laya.opener.plist"
bin="$HOME/Applications/Sayso.app/Contents/MacOS/Sayso"

if [[ ! -x "$bin" ]]; then
  echo "Sayso is not installed at $HOME/Applications/Sayso.app"
  echo "Run ./scripts/build_app.sh first."
  exit 2
fi

mkdir -p "$(dirname "$dst")"
sed "s|__HOME__|$HOME|g" "$src" > "$dst"
launchctl bootout "gui/$UID/com.laya.opener" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID" "$dst"
echo "installed $dst"
launchctl print "gui/$UID/com.laya.opener" | awk '/state =/{print; exit}'
