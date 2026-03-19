#!/bin/bash
# nexads-remote.sh — Remote nexAds server management
# Usage:
#   ./scripts/nexads-remote.sh <host> <action>
#   ./scripts/nexads-remote.sh all <action>
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
    nexdev-austria
    nexdev-bc
    nexdev-bs
    nexdev-swec
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
        if pgrep -f 'python3.*main.py' > /dev/null 2>&1; then
            WORKERS=$(pgrep -cf 'multiprocessing.spawn' 2>/dev/null || echo 0)
            PID=$(cat nexads.pid 2>/dev/null || pgrep -f 'python3.*main.py' -o)
            echo "  RUNNING (pid=$PID, workers=$WORKERS)"
        else
            echo "  STOPPED"
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

        # Kill main process
        if [ -f nexads.pid ]; then
            PID=$(cat nexads.pid)
            kill "$PID" 2>/dev/null && echo "  Sent SIGTERM to main process $PID"
            sleep 2
        fi

        # Kill any remaining nexads processes
        pkill -f 'python3.*main.py' 2>/dev/null || true
        sleep 1

        # Kill orphaned browser processes
        pkill -f 'chromium|chrome|camoufox|firefox' 2>/dev/null || true
        pkill -f 'Xvfb' 2>/dev/null || true

        # Clean up pid file
        rm -f nexads.pid nexads.pgid

        # Verify
        if pgrep -f 'python3.*main.py' > /dev/null 2>&1; then
            echo "  WARNING: Still running, force killing..."
            pkill -9 -f 'python3.*main.py' 2>/dev/null || true
            sleep 1
        fi
        echo "  Stopped"
REMOTE
}

do_start() {
    local host="$1"
    echo "=== Starting $host ==="
    ssh_cmd "$host" bash -s <<'REMOTE'
        cd ~/nexads || { echo "  ERROR: ~/nexads not found. Run deploy first."; exit 1; }

        # Check if already running
        if pgrep -f 'python3.*main.py' > /dev/null 2>&1; then
            echo "  Already running. Stop first."
            exit 1
        fi

        # Start with virtual display (xvfb) for headful mode on headless server
        export DISPLAY=:99
        Xvfb :99 -screen 0 1920x1080x24 &>/dev/null &
        sleep 1

        # Launch nexAds in background
        nohup python3 main.py > nexads.log 2>&1 &
        MAIN_PID=$!
        echo "$MAIN_PID" > nexads.pid
        echo "  Started (pid=$MAIN_PID, log=nexads.log)"

        # Wait briefly and verify it's still running
        sleep 3
        if kill -0 "$MAIN_PID" 2>/dev/null; then
            echo "  Verified running"
        else
            echo "  WARNING: Process died. Check nexads.log"
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

        echo "  Installing system dependencies..."
        sudo apt-get update -qq > /dev/null 2>&1
        sudo apt-get install -y -qq xvfb git python3-pip > /dev/null 2>&1

        # Install Chrome for patchright
        if ! command -v google-chrome &> /dev/null; then
            echo "  Installing Google Chrome..."
            wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
            sudo apt-get install -y -qq /tmp/chrome.deb > /dev/null 2>&1 || sudo apt-get -f install -y -qq > /dev/null 2>&1
            rm -f /tmp/chrome.deb
        fi

        # Stop existing nexads if running
        if pgrep -f 'python3.*main.py' > /dev/null 2>&1; then
            echo "  Stopping existing nexads..."
            pkill -f 'python3.*main.py' 2>/dev/null || true
            pkill -f 'chromium|chrome|camoufox|firefox' 2>/dev/null || true
            pkill -f 'Xvfb' 2>/dev/null || true
            sleep 2
        fi

        # Clone or update repo
        if [ -d "$REMOTE_DIR/.git" ]; then
            echo "  Updating existing repo..."
            cd "$REMOTE_DIR"
            git fetch origin
            git reset --hard origin/main
        else
            # Handle case where nexads files are in ~/ directly (old layout)
            if [ -f ~/main.py ] && [ -f ~/config.json ] && [ ! -d "$REMOTE_DIR" ]; then
                echo "  Backing up old layout from ~/..."
                mkdir -p ~/nexads-old-backup
                cp ~/config.json ~/nexads-old-backup/ 2>/dev/null || true
                cp ~/proxy.txt ~/nexads-old-backup/ 2>/dev/null || true
            fi

            echo "  Cloning fresh repo..."
            rm -rf "$REMOTE_DIR"
            git clone "$REPO_URL" "$REMOTE_DIR"
            cd "$REMOTE_DIR"

            # Restore config if backed up
            if [ -f ~/nexads-old-backup/config.json ]; then
                cp ~/nexads-old-backup/config.json "$REMOTE_DIR/config.json"
                echo "  Restored config.json from backup"
            fi
            if [ -f ~/nexads-old-backup/proxy.txt ]; then
                cp ~/nexads-old-backup/proxy.txt "$REMOTE_DIR/proxy.txt"
                echo "  Restored proxy.txt from backup"
            fi
        fi

        cd "$REMOTE_DIR"

        # Install Python dependencies
        echo "  Installing Python dependencies..."
        pip3 install --user -q -r requirements.txt 2>&1 | tail -3

        # Install patchright Chrome
        echo "  Installing patchright Chrome..."
        python3 -m patchright install chrome 2>&1 | tail -3

        # Fetch camoufox browser
        echo "  Fetching camoufox..."
        python3 -m camoufox fetch 2>&1 | tail -3

        # Install playwright browsers (needed by camoufox)
        echo "  Installing playwright browsers..."
        python3 -m playwright install firefox 2>&1 | tail -3

        echo "  Deploy complete. Git: $(git log --oneline -1)"
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
