#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/api.pid"

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "API already running (PID $(cat "$PID_FILE"))"
    exit 1
fi

cd "$SCRIPT_DIR"
nohup venv/bin/python main.py > /tmp/whitelist-api.log 2>&1 &
echo $! > "$PID_FILE"
echo "API started (PID $!)"
