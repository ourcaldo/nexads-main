#!/usr/bin/env bash
set -euo pipefail

# Stop nexAds background run including worker and camoufox child processes.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

if [ -f "nexads.pgid" ]; then
  pgid="$(tr -d '[:space:]' < nexads.pgid)"
  if [ -n "$pgid" ] && ps -o pgid= -p "$pgid" >/dev/null 2>&1; then
    echo "Stopping nexAds process group -$pgid ..."
    kill -TERM -- "-$pgid" || true
    sleep 2
    if ps -o pgid= -p "$pgid" >/dev/null 2>&1; then
      echo "Process group still running, forcing kill -$pgid ..."
      kill -KILL -- "-$pgid" || true
    fi
  fi
fi

if [ -f "nexads.pid" ]; then
  pid="$(tr -d '[:space:]' < nexads.pid)"
  if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
    echo "Stopping nexAds parent PID $pid ..."
    kill -TERM "$pid" || true
    sleep 1
    kill -KILL "$pid" >/dev/null 2>&1 || true
  fi
fi

# Final safety cleanup in case orphaned browser children remain.
pkill -f "camoufox-bin" >/dev/null 2>&1 || true
pkill -f "python3 main.py" >/dev/null 2>&1 || true

rm -f nexads.pid nexads.pgid

echo "nexAds stop routine finished."
