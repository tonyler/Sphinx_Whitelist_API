#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/api.pid"

# Kill by PID file
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill -TERM "$PID" 2>/dev/null
        sleep 2
        kill -KILL "$PID" 2>/dev/null
    fi
    rm -f "$PID_FILE"
fi

# Kill any remaining processes on port 8002
fuser -k 8002/tcp 2>/dev/null

# Kill any stray python processes running main.py from this dir
pkill -f "$SCRIPT_DIR/main.py" 2>/dev/null
pkill -f "venv/bin/python main.py" 2>/dev/null

sleep 1

# Verify
if fuser 8002/tcp 2>/dev/null | grep -q .; then
    echo "WARNING: port 8002 still in use"
else
    echo "API stopped"
fi
