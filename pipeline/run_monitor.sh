#!/bin/zsh
# Poll for the next Sentinel-1 pass over the barrier lake and measure it when it
# lands. Scheduled hourly by a LaunchAgent because the RTC product appears some
# hours after acquisition, not at the acquisition time.
#
# Acquisitions being waited on:
#   28 Aug 12:21Z  orbit 85  ascending
#   31 Aug 00:10Z  orbit 121 descending
#    5 Sep 00:18Z  orbit 19  descending
#
# Idempotent: re-measuring an already-cached scene is cheap, and later passes
# need measuring too, so this keeps running rather than disarming on first hit.

set -u
DIR="/Users/konsta/cat_projects/rheality/pipeline"
PY="$DIR/.venv/bin/python"
LOG="$DIR/data/barrier_monitor.log"
STOP="2026-09-10"

cd "$DIR" || exit 1
stamp() { date -u "+%Y-%m-%dT%H:%M:%SZ"; }

if [[ "$(date -u +%Y-%m-%d)" > "$STOP" ]]; then
  echo "$(stamp) past $STOP, nothing left to wait for. Unload with:" >> "$LOG"
  echo "  launchctl bootout gui/$(id -u)/space.rheality.barrier-monitor" >> "$LOG"
  exit 0
fi

if "$PY" -u nepal_barrier_monitor_2026.py check >> "$LOG" 2>&1; then
  echo "$(stamp) scene available, measuring" >> "$LOG"
  "$PY" -u nepal_barrier_monitor_2026.py measure >> "$LOG" 2>&1
  echo "$(stamp) measure exit $?" >> "$LOG"
else
  echo "$(stamp) no post-event scene yet" >> "$LOG"
fi
