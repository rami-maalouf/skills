#!/bin/zsh
# install.sh - install the always-on OpenOats call-debrief watcher.
#
# IMPORTANT (macOS TCC): a background launchd agent CANNOT read file contents under
# ~/Documents or touch the iCloud vault unless granted Full Disk Access. And it cannot
# even open its own script if that script lives under ~/Documents. So we COPY the runtime
# scripts out to ~/.mac-automations (a non-protected location, matching the existing
# com.rami.* agents) and you grant Full Disk Access to /bin/zsh once (see the end of this
# script). Source of truth stays in the repo; re-run this script after editing the scripts.
set -euo pipefail

REPO_DIR="${0:A:h}"
LABEL="com.rami.openoats-debrief.watch"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
RUNTIME="$HOME/.mac-automations/openoats-debrief"
WATCH_DIR="/Users/rami/Documents/transcriptions/OpenOats"
STATE_DIR="$HOME/Library/Application Support/openoats-debrief"
LOG_DIR="$HOME/Library/Logs/OpenOatsDebrief"
STATE="$STATE_DIR/.processed"

mkdir -p "$HOME/.mac-automations" "$STATE_DIR" "$LOG_DIR" "$HOME/Library/LaunchAgents"

# never reinstall under a live debrief: zsh reads a running script lazily, so copying over it
# corrupts the run, and bootout kills it before its lock is released.
while launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | grep -q "state = running"; do
  echo "a debrief is running - waiting for it to finish before reinstalling (ctrl-c to abort)..."
  sleep 15
done

# replace any old symlink-into-Documents with a REAL directory of copies
[[ -L "$RUNTIME" ]] && rm -f "$RUNTIME"
mkdir -p "$RUNTIME"
cp "$REPO_DIR"/{watch-openoats.sh,run-debrief.sh,retry-debrief.sh,apply-proposals.sh,presenting-check.sh,debrief-prompt.md,apply-proposals-prompt.md} "$RUNTIME"/
chmod +x "$RUNTIME"/*.sh

# seed state with the existing backlog so first load does NOT debrief old calls
if [[ ! -f "$STATE" ]]; then
  setopt null_glob
  for f in "$WATCH_DIR"/*.md; do print -r -- "${f:t}"; done > "$STATE"
  echo "seeded $(wc -l < "$STATE" | tr -d ' ') existing files as already-processed (backlog skipped)"
fi

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$RUNTIME/watch-openoats.sh</string>
  </array>
  <key>WatchPaths</key>
  <array>
    <string>$WATCH_DIR</string>
  </array>
  <key>StartInterval</key>
  <integer>120</integer>
  <key>AbandonProcessGroup</key>
  <true/>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/watch.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/watch.err.log</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"

echo "installed and loaded: $LABEL"
echo "runtime scripts: $RUNTIME (copied out of ~/Documents)"
echo "watching:        $WATCH_DIR"
echo ""
echo "ONE-TIME MANUAL STEP - grant Full Disk Access to /bin/zsh:"
echo "  System Settings > Privacy & Security > Full Disk Access > + >"
echo "  press Cmd+Shift+G, enter /bin/zsh, Open, ensure the toggle is ON."
echo "  (without this, the agent can see filenames but cannot read transcripts or write the vault.)"
echo ""
echo "stop it:    launchctl bootout gui/$(id -u)/$LABEL"
echo "retry a gave-up debrief: $RUNTIME/retry-debrief.sh [name]   (no args = all quarantined)"
