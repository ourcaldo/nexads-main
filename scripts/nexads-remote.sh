#!/bin/bash
# nexads-remote.sh — Remote nexAds fleet management
# Uses existing scripts/setup_ubuntu.sh and scripts/stop_nexads.sh on each server.
#
# Usage:
#   ./scripts/nexads-remote.sh <host|all> <action>
#
# Actions: start, stop, status, deploy, logs
#
# Examples:
#   ./scripts/nexads-remote.sh nexdev status
#   ./scripts/nexads-remote.sh nexdev-austria deploy
#   ./scripts/nexads-remote.sh all stop
#   ./scripts/nexads-remote.sh all status

set -e

REPO_URL="https://github.com/ourcaldo/nexads-main.git"
REMOTE_DIR="/home/nexdev/nexads"

ALL_HOSTS=(
    nexdev
    nexdev-auseast
    nexdev-auscen
    nexdev-nz
    nexdev-my
    nexdev-ausso
    nexdev-austria
    nexdev-bc
    nexdev-bs
    nexdev-swec
    nexdev-cacen
    nexdev-caes
    nexdev-inso
    nexdev-usea
    nexdev-uswe2
    nexdev-uscen
    nexdev-usea2
    nexdev-usso
    nexdev-uswe3
    nexdev-usno
)

ssh_cmd() {
    local host="$1"
    shift
    ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes "$host" "$@"
}

do_status() {
    local host="$1"
    echo "=== $host ==="
    ssh_cmd "$host" bash -s <<'REMOTE'
        cd ~/nexads 2>/dev/null || { echo "  NOT INSTALLED"; exit 0; }
        if [ -f nexads.pid ]; then
            PID=$(tr -d '[:space:]' < nexads.pid)
            if kill -0 "$PID" 2>/dev/null; then
                WORKERS=$(pgrep -cf 'multiprocessing.spawn' 2>/dev/null || echo 0)
                echo "  RUNNING (pid=$PID, workers=$WORKERS)"
            else
                echo "  STOPPED (stale pid file)"
            fi
        else
            if pgrep -f 'python3.*main.py' > /dev/null 2>&1; then
                echo "  RUNNING (no pid file)"
            else
                echo "  STOPPED"
            fi
        fi
        GIT=$(git log --oneline -1 2>/dev/null || echo "no git")
        echo "  Version: $GIT"
REMOTE
}

do_stop() {
    local host="$1"
    echo "=== Stopping $host ==="
    ssh_cmd "$host" bash -s <<'REMOTE'
        cd ~/nexads 2>/dev/null || { echo "  Not installed, nothing to stop"; exit 0; }
        bash scripts/stop_nexads.sh
        pkill -f 'Xvfb' 2>/dev/null || true
        echo "  Stopped"
REMOTE
}

do_start() {
    local host="$1"
    echo "=== Starting $host ==="
    ssh_cmd "$host" bash -s <<'REMOTE'
        cd ~/nexads || { echo "  ERROR: ~/nexads not found. Run deploy first."; exit 1; }

        # Check if already running
        if [ -f nexads.pid ]; then
            PID=$(tr -d '[:space:]' < nexads.pid)
            if kill -0 "$PID" 2>/dev/null; then
                echo "  Already running (pid=$PID). Stop first."
                exit 1
            fi
        fi

        # Start xvfb for headful mode on headless server
        if ! pgrep -f 'Xvfb :99' > /dev/null 2>&1; then
            Xvfb :99 -screen 0 1920x1080x24 &>/dev/null &
            sleep 1
        fi
        export DISPLAY=:99

        # Launch using setsid for proper process group tracking
        nohup setsid python3 main.py > nexads.log 2>&1 < /dev/null &
        MAIN_PID=$!
        MAIN_PGID="$(ps -o pgid= -p "$MAIN_PID" 2>/dev/null | tr -d '[:space:]')"
        echo "$MAIN_PID" > nexads.pid
        [ -n "$MAIN_PGID" ] && echo "$MAIN_PGID" > nexads.pgid

        sleep 3
        if kill -0 "$MAIN_PID" 2>/dev/null; then
            echo "  Started (pid=$MAIN_PID, pgid=$MAIN_PGID)"
        else
            echo "  WARNING: Process died. Last log lines:"
            tail -5 nexads.log 2>/dev/null
        fi
REMOTE
}

do_deploy() {
    local host="$1"
    echo "=== Deploying to $host ==="
    ssh_cmd "$host" bash -s -- "$REPO_URL" "$REMOTE_DIR" <<'REMOTE'
        REPO_URL="$1"
        REMOTE_DIR="$2"

        # Handle old nexads-main directory name
        if [ -d ~/nexads-main ] && [ ! -d "$REMOTE_DIR" ]; then
            echo "  Renaming ~/nexads-main -> ~/nexads..."
            mv ~/nexads-main "$REMOTE_DIR"
        fi

        # Clone or update repo (follows README approach)
        if [ -d "$REMOTE_DIR/.git" ]; then
            echo "  Updating existing repo..."
            cd "$REMOTE_DIR"
            git fetch origin
            git reset --hard origin/main
            git clean -fd
        else
            echo "  Cloning fresh repo..."
            git clone "$REPO_URL" "$REMOTE_DIR"
            cd "$REMOTE_DIR"
        fi

        # Stop if running, then setup + start (README workflow)
        bash scripts/stop_nexads.sh 2>/dev/null || true
        pkill -f 'Xvfb' 2>/dev/null || true
        chmod +x scripts/setup_ubuntu.sh
        ./scripts/setup_ubuntu.sh

        echo "  Deploy complete. Version: $(git log --oneline -1)"
REMOTE
}

do_logs() {
    local host="$1"
    echo "=== Logs from $host (last 30 lines) ==="
    ssh_cmd "$host" "tail -30 ~/nexads/nexads.log 2>/dev/null || echo 'No log file found'"
}

# --- Main ---

HOST="${1:-}"
ACTION="${2:-status}"

if [ -z "$HOST" ]; then
    echo "Usage: $0 <host|all> <start|stop|status|deploy|logs>"
    echo ""
    echo "Hosts: ${ALL_HOSTS[*]}"
    exit 1
fi

if [ "$HOST" = "all" ]; then
    for h in "${ALL_HOSTS[@]}"; do
        "do_${ACTION}" "$h" || echo "  FAILED on $h"
        echo ""
    done
else
    "do_${ACTION}" "$HOST"
fi
