#!/bin/zsh
# presenting-check.sh
# exit 0 => Rami is presenting: one of his meeting/share apps is ACTIVELY using the mic right now.
# exit 1 => not presenting.
# run-debrief uses this to choose the alert: presenting => quiet banner only; otherwise => sticky critical alert.
#
# design rationale (learned the hard way):
# - macOS does NOT expose "is my screen being captured" to a normal shell tool.
# - plain "mic in use" is noisy: system brokers (replayd) and streaming apps (Meld Studio) hold the mic
#   even when Rami is not on a call.
# - "app is open" is too loose: Zen is his everyday browser and Slack/OpenOats are usually running.
# so the reliable proxy for "on a call / presenting" is: one of Rami's named apps is ACTIVELY doing mic
# input. that only happens when the app is really in a call (Zen just being open does not do mic input).
# conservative by design: any uncertainty resolves to NOT presenting, so the sticky alert still fires.
#
# apps counted: Zoom, Zen (e.g. Google Meet), Slack (huddle), Screen Studio, OpenOats.
# manual override for anything not covered: `touch ~/.openoats-presenting` (delete when done).

[[ -f "$HOME/.openoats-presenting" ]] && exit 0

# PIDs of processes currently doing microphone INPUT (CoreAudio per-process API, macOS 14+)
pids=$(/usr/bin/swift - <<'SWIFT' 2>/dev/null
import CoreAudio
import Foundation
var addr = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyProcessObjectList,
                                      mScope: kAudioObjectPropertyScopeGlobal,
                                      mElement: kAudioObjectPropertyElementMain)
var size = UInt32(0)
guard AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size) == noErr else { exit(0) }
let n = Int(size) / MemoryLayout<AudioObjectID>.size
if n == 0 { exit(0) }
var procs = [AudioObjectID](repeating: 0, count: n)
guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil, &size, &procs) == noErr else { exit(0) }
for p in procs {
  var running = UInt32(0); var s = UInt32(MemoryLayout<UInt32>.size)
  var a = AudioObjectPropertyAddress(mSelector: kAudioProcessPropertyIsRunningInput,
                                     mScope: kAudioObjectPropertyScopeGlobal,
                                     mElement: kAudioObjectPropertyElementMain)
  if AudioObjectGetPropertyData(p, &a, 0, nil, &s, &running) == noErr, running != 0 {
    var pid = pid_t(0); var ps = UInt32(MemoryLayout<pid_t>.size)
    var pa = AudioObjectPropertyAddress(mSelector: kAudioProcessPropertyPID,
                                        mScope: kAudioObjectPropertyScopeGlobal,
                                        mElement: kAudioObjectPropertyElementMain)
    if AudioObjectGetPropertyData(p, &pa, 0, nil, &ps, &pid) == noErr { print(pid) }
  }
}
SWIFT
)

[[ -z "$pids" ]] && exit 1   # nothing using the mic -> not on a call -> not presenting

# is any actively-micing process one of Rami's meeting/share apps?
for pid in ${(f)pids}; do
  args=$(ps -p "$pid" -o args= 2>/dev/null) || continue
  case "$args" in
    (*zoom.us*)                   exit 0 ;;  # Zoom
    (*/Zen.app/*)                 exit 0 ;;  # Zen browser (e.g. Google Meet)
    (*/Slack.app/*)               exit 0 ;;  # Slack huddle
    (*"/Screen Studio.app/"*)     exit 0 ;;  # Screen Studio
    (*/OpenOats.app/*)            exit 0 ;;  # OpenOats
  esac
done
exit 1
