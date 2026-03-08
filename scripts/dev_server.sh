#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE_DIR="$(cd "$ROOT_DIR/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$RUN_DIR/hei-agent.pid"
LOG_FILE="$LOG_DIR/hei-agent.log"

DEFAULT_PORT="${PORT:-8011}"
HOST="${HOST:-127.0.0.1}"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in \
    "$WORKSPACE_DIR/.venv/bin/python" \
    "$ROOT_DIR/.venv/bin/python" \
    "$(command -v python3)"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi

mkdir -p "$RUN_DIR" "$LOG_DIR"

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

start() {
  if is_running; then
    echo "HEI-agent already running (pid=$(cat "$PID_FILE"))."
    exit 0
  fi

  echo "Starting HEI-agent on http://$HOST:$DEFAULT_PORT ..."
  nohup "$PYTHON_BIN" -m uvicorn app.main:app \
    --app-dir "$ROOT_DIR" \
    --host "$HOST" \
    --port "$DEFAULT_PORT" \
    >"$LOG_FILE" 2>&1 &

  echo $! > "$PID_FILE"
  sleep 1

  if is_running; then
    echo "Started (pid=$(cat "$PID_FILE")). Logs: $LOG_FILE"
  else
    echo "Failed to start. Check logs: $LOG_FILE"
    exit 1
  fi
}

stop() {
  if ! is_running; then
    rm -f "$PID_FILE"
    echo "HEI-agent is not running."
    exit 0
  fi

  local pid
  pid="$(cat "$PID_FILE")"
  echo "Stopping HEI-agent (pid=$pid) ..."
  kill "$pid" 2>/dev/null || true

  for _ in {1..20}; do
    if kill -0 "$pid" 2>/dev/null; then
      sleep 0.2
    else
      break
    fi
  done

  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi

  rm -f "$PID_FILE"
  echo "Stopped."
}

status() {
  if is_running; then
    local pid
    pid="$(cat "$PID_FILE")"
    echo "HEI-agent is running (pid=$pid)."
    curl --noproxy '*' -sS "http://$HOST:$DEFAULT_PORT/health" --max-time 3 >/dev/null && \
      echo "Health check: OK" || echo "Health check: NOT READY"
  else
    echo "HEI-agent is not running."
  fi
}

logs() {
  if [[ -f "$LOG_FILE" ]]; then
    tail -n 80 "$LOG_FILE"
  else
    echo "No log file yet: $LOG_FILE"
  fi
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  logs) logs ;;
  *)
    cat <<'EOF'
Usage: scripts/dev_server.sh <start|stop|restart|status|logs>

Environment variables (optional):
  PORT=8011
  HOST=127.0.0.1
  PYTHON_BIN=/path/to/python
EOF
    exit 1
    ;;
esac
