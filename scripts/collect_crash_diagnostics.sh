#!/usr/bin/env bash
# Collect diagnostics after main process crash (OOM, segfault, etc.).
# Author: Vasiliy Zdanovskiy
# email: vasilyvz@gmail.com
#
# Usage: run after the server has crashed (stale pidfile or port 15000 not listening).
#   ./scripts/collect_crash_diagnostics.sh [path_to_log_dir]
# Default log dir: ./logs (relative to project root).

set -e
LOG_DIR="${1:-./logs}"
LOG_FILE="${LOG_DIR}/mcp_server.log"
OUT_FILE="crash_diagnostics_$(date +%Y%m%d_%H%M%S).txt"

echo "=== Crash diagnostics ===" | tee "$OUT_FILE"
echo "Date: $(date -Iseconds)" | tee -a "$OUT_FILE"
echo "Log file: $LOG_FILE" | tee -a "$OUT_FILE"
echo "" | tee -a "$OUT_FILE"

echo "--- Last 80 lines of log (main process heartbeat / faulthandler / shutdown) ---" | tee -a "$OUT_FILE"
if [[ -f "$LOG_FILE" ]]; then
  tail -80 "$LOG_FILE" | tee -a "$OUT_FILE"
else
  echo "(log file not found)" | tee -a "$OUT_FILE"
fi
echo "" | tee -a "$OUT_FILE"

echo "--- Kernel messages (OOM, kill) - may require sudo ---" | tee -a "$OUT_FILE"
if dmesg 2>/dev/null | tail -60 >> "$OUT_FILE"; then
  :
else
  echo "dmesg not available (run: sudo dmesg | tail -100)" | tee -a "$OUT_FILE"
fi

echo "" | tee -a "$OUT_FILE"
echo "Diagnostics written to $OUT_FILE"
