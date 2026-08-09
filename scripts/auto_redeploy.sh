#!/bin/sh
# RITDorg production keeper
# - Forever-restarts the web server after any crash or exit
# - Polls GitHub and redeploys on new commits
# - Health-checks the live port and force-restarts wedged processes
# - Captures all logs to data/server.log
#
# Usage:
#   sudo nohup ./scripts/auto_redeploy.sh >> data/auto_redeploy.out 2>&1 &
set -eu

cd "$(dirname "$0")/.."

# ---------------------------------------------------------------------------
# Config (override via environment)
# ---------------------------------------------------------------------------
CHECK_INTERVAL_SECONDS="${CHECK_INTERVAL_SECONDS:-60}"
RESTART_DELAY_SECONDS="${RESTART_DELAY_SECONDS:-3}"
HEALTH_FAIL_THRESHOLD="${HEALTH_FAIL_THRESHOLD:-3}"
APP_PORT="${APP_PORT:-80}"
APP_HOST="${APP_HOST:-0.0.0.0}"
FORCE_KILL_PORT_PROCESS="${FORCE_KILL_PORT_PROCESS:-0}"
HEALTH_URL="${HEALTH_URL:-}"
LOG_FILE="${LOG_FILE:-data/server.log}"
KEEPER_PID_FILE="${KEEPER_PID_FILE:-.keeper.pid}"
MAX_LOG_BYTES="${MAX_LOG_BYTES:-10485760}"  # 10 MiB

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
KEEPER_PID=""
HEALTH_FAILS=0
LAST_DEPLOY_SHA=""
PYTHON_BIN="$(command -v python3 || command -v python || true)"

# Distinctive one-liner so pkill/pgrep can find our server process reliably.
SERVER_CMD="from asgiref.wsgi import WsgiToAsgi; from ritdorg.app import app; import uvicorn; uvicorn.run(WsgiToAsgi(app), host='$APP_HOST', port=$APP_PORT, log_level='info', timeout_keep_alive=30, limit_concurrency=100)"
SERVER_MATCH="from asgiref.wsgi import WsgiToAsgi; from ritdorg.app import app"

# ---------------------------------------------------------------------------
# Bootstrap checks
# ---------------------------------------------------------------------------
if [ -z "$PYTHON_BIN" ]; then
  echo "Python is required but was not found in PATH." >&2
  exit 1
fi

if [ "$APP_PORT" -lt 1024 ] && [ "$(id -u)" -ne 0 ]; then
  echo "Port $APP_PORT usually requires root. Run with sudo or set APP_PORT to a non-privileged port." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() {
  msg="=== $(date '+%Y-%m-%d %H:%M:%S') $* ==="
  echo "$msg"
  mkdir -p "$(dirname "$LOG_FILE")"
  echo "$msg" >> "$LOG_FILE"
}

trim() {
  echo "$1" | tr -d '[:space:]'
}

ensure_https_origin() {
  origin="$(git remote get-url origin 2>/dev/null || true)"
  [ -n "$origin" ] || {
    echo "No git origin configured; git auto-redeploy will be skipped."
    return 0
  }

  case "$origin" in
    https://*) ;;
    git@github.com:*)
      path="${origin#git@github.com:}"
      git remote set-url origin "https://github.com/$path"
      echo "Updated origin to HTTPS: https://github.com/$path"
      ;;
    ssh://git@github.com/*)
      path="${origin#ssh://git@github.com/}"
      git remote set-url origin "https://github.com/$path"
      echo "Updated origin to HTTPS: https://github.com/$path"
      ;;
    *)
      echo "Origin is not a standard GitHub SSH URL. Leaving as-is: $origin"
      ;;
  esac
}

install_dependencies() {
  echo "Installing/updating dependencies..."
  if "$PYTHON_BIN" -m pip help install 2>/dev/null | grep -q -- "--break-system-packages"; then
    "$PYTHON_BIN" -m pip install -r requirements.txt --break-system-packages
  else
    "$PYTHON_BIN" -m pip install -r requirements.txt
  fi
}

rotate_log_if_needed() {
  mkdir -p "$(dirname "$LOG_FILE")"
  [ -f "$LOG_FILE" ] || return 0

  sz=$(trim "$(wc -c <"$LOG_FILE" 2>/dev/null || echo 0)")
  [ "${sz:-0}" -gt "$MAX_LOG_BYTES" ] || return 0

  i=4
  while [ "$i" -ge 1 ]; do
    [ -f "$LOG_FILE.$i" ] && mv "$LOG_FILE.$i" "$LOG_FILE.$((i + 1))" 2>/dev/null || true
    i=$((i - 1))
  done
  mv "$LOG_FILE" "$LOG_FILE.1" 2>/dev/null || true
}

port_listener_pids() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -iTCP:"$APP_PORT" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ' || true
    return 0
  fi
  if command -v fuser >/dev/null 2>&1; then
    fuser "${APP_PORT}/tcp" 2>/dev/null | tr -s ' ' || true
    return 0
  fi
  echo ""
}

free_port() {
  pids="$(port_listener_pids)"
  [ -n "$(trim "$pids")" ] || return 0

  log "Freeing port $APP_PORT (PIDs: $pids)"
  for pid in $pids; do
    kill "$pid" 2>/dev/null || true
  done
  sleep 1

  pids="$(port_listener_pids)"
  for pid in $pids; do
    kill -9 "$pid" 2>/dev/null || true
  done
  sleep 1
}

check_port_available() {
  pids="$(port_listener_pids)"
  [ -n "$(trim "$pids")" ] || return 0

  echo "Port $APP_PORT is already in use by PID(s): $pids"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$APP_PORT" -sTCP:LISTEN || true
  fi

  if [ "$FORCE_KILL_PORT_PROCESS" = "1" ]; then
    free_port
    return 0
  fi

  echo "Set FORCE_KILL_PORT_PROCESS=1 to stop current listener(s), or use a different APP_PORT." >&2
  exit 1
}

kill_server_processes() {
  pkill -f "$SERVER_MATCH" 2>/dev/null || true
  sleep 1
  pkill -9 -f "$SERVER_MATCH" 2>/dev/null || true
  free_port
}

restart_backoff_seconds() {
  fails="$1"
  if [ "$fails" -gt 15 ]; then
    echo 60
  elif [ "$fails" -gt 5 ]; then
    echo 15
  else
    echo "$RESTART_DELAY_SECONDS"
  fi
}

# ---------------------------------------------------------------------------
# Keeper: forever-restarts the Python/uvicorn process
# ---------------------------------------------------------------------------
start_keeper() {
  rotate_log_if_needed
  check_port_available
  log "Starting auto-restarting server keeper (logs -> $LOG_FILE) on $APP_HOST:$APP_PORT"

  (
    # Do not inherit outer EXIT trap; keeper manages its own lifecycle.
    trap - INT TERM EXIT
    fails=0
    started_at=0

    while true; do
      echo "=== $(date '+%Y-%m-%d %H:%M:%S') Starting RITDorg (auto-restart keeper) ===" >> "$LOG_FILE"
      started_at=$(date +%s 2>/dev/null || echo 0)

      # RITD_NO_CONSOLE_LOG avoids duplicate StreamHandler lines in server.log.
      set +e
      RITD_NO_CONSOLE_LOG=1 "$PYTHON_BIN" -c "$SERVER_CMD" >> "$LOG_FILE" 2>&1
      code=$?
      set -e

      now=$(date +%s 2>/dev/null || echo 0)
      runtime=0
      if [ "$started_at" -gt 0 ] && [ "$now" -ge "$started_at" ]; then
        runtime=$((now - started_at))
      fi

      # A process that stayed up a while is considered healthy; reset backoff.
      if [ "$runtime" -ge 120 ]; then
        fails=0
      else
        fails=$((fails + 1))
      fi

      delay="$(restart_backoff_seconds "$fails")"
      echo "=== $(date '+%Y-%m-%d %H:%M:%S') Server exited (code=$code, up ${runtime}s). Restarting in ${delay}s (fail #$fails)... ===" >> "$LOG_FILE"

      # Clear anything still bound to the port before relaunch.
      pkill -f "$SERVER_MATCH" 2>/dev/null || true
      free_port
      sleep "$delay"
    done
  ) &

  KEEPER_PID=$!
  echo "$KEEPER_PID" > "$KEEPER_PID_FILE"
  log "Keeper PID: $KEEPER_PID"
  HEALTH_FAILS=0
}

stop_keeper() {
  kp=""
  if [ -f "$KEEPER_PID_FILE" ]; then
    kp=$(cat "$KEEPER_PID_FILE" 2>/dev/null || echo "")
  fi
  if [ -z "$kp" ] && [ -n "$KEEPER_PID" ]; then
    kp="$KEEPER_PID"
  fi

  if [ -n "$kp" ] && kill -0 "$kp" 2>/dev/null; then
    log "Stopping keeper PID $kp"
    kill "$kp" 2>/dev/null || true
    pkill -P "$kp" 2>/dev/null || true

    waited=0
    while [ "$waited" -lt 10 ] && kill -0 "$kp" 2>/dev/null; do
      sleep 1
      waited=$((waited + 1))
    done

    if kill -0 "$kp" 2>/dev/null; then
      kill -9 "$kp" 2>/dev/null || true
      pkill -9 -P "$kp" 2>/dev/null || true
    fi
    wait "$kp" 2>/dev/null || true
  fi

  rm -f "$KEEPER_PID_FILE"
  KEEPER_PID=""
  kill_server_processes
}

keeper_alive() {
  kp=""
  if [ -f "$KEEPER_PID_FILE" ]; then
    kp=$(cat "$KEEPER_PID_FILE" 2>/dev/null || echo "")
  fi
  if [ -n "$kp" ] && kill -0 "$kp" 2>/dev/null; then
    KEEPER_PID="$kp"
    return 0
  fi
  return 1
}

ensure_keeper() {
  keeper_alive && return 0
  log "Keeper process missing — restarting keeper (and therefore the web server)"
  start_keeper
}

# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------
health_url() {
  if [ -n "$HEALTH_URL" ]; then
    echo "$HEALTH_URL"
  else
    # Prefer loopback; APP_HOST may be 0.0.0.0 which is not a connect target.
    echo "http://127.0.0.1:${APP_PORT}/healthz"
  fi
}

probe_health() {
  url="$(health_url)"
  if command -v curl >/dev/null 2>&1; then
    code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")
    [ "$code" = "200" ]
    return $?
  fi

  "$PYTHON_BIN" - "$url" <<'PY' 2>/dev/null
import sys
import urllib.request

url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=5) as response:
        sys.exit(0 if getattr(response, "status", 200) == 200 else 1)
except Exception:
    sys.exit(1)
PY
}

check_health_or_restart() {
  if ! keeper_alive; then
    ensure_keeper
    return 0
  fi

  pids="$(port_listener_pids)"
  if [ -z "$(trim "$pids")" ]; then
    HEALTH_FAILS=$((HEALTH_FAILS + 1))
    log "Health: nothing listening on :$APP_PORT (fail #$HEALTH_FAILS)"
  elif probe_health; then
    if [ "$HEALTH_FAILS" -ne 0 ]; then
      log "Health: recovered after $HEALTH_FAILS failure(s)"
    fi
    HEALTH_FAILS=0
    return 0
  else
    HEALTH_FAILS=$((HEALTH_FAILS + 1))
    log "Health check failed for $(health_url) (fail #$HEALTH_FAILS)"
  fi

  if [ "$HEALTH_FAILS" -ge "$HEALTH_FAIL_THRESHOLD" ]; then
    log "Health failed ${HEALTH_FAILS}x — force-restarting server"
    # Kill only server children; keeper loop relaunches automatically.
    kill_server_processes
    HEALTH_FAILS=0
    ensure_keeper
  fi
}

# ---------------------------------------------------------------------------
# Git redeploy
# ---------------------------------------------------------------------------
redeploy_from_git() {
  branch="$1"
  log "New commit on origin/$branch — pulling and redeploying"
  stop_keeper

  # Prefer clean fast-forward; hard-reset if local drift blocks production.
  if ! git pull --ff-only origin "$branch"; then
    log "ff-only pull failed; resetting hard to origin/$branch"
    git fetch origin "$branch"
    git reset --hard "origin/$branch"
  fi

  install_dependencies
  LAST_DEPLOY_SHA="$(git rev-parse HEAD)"
  start_keeper
  log "Redeploy complete at $LAST_DEPLOY_SHA"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
cleanup() {
  log "auto_redeploy shutting down"
  stop_keeper
}

trap cleanup INT TERM EXIT

mkdir -p data
ensure_https_origin

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
log "Tracking branch: $BRANCH (check every ${CHECK_INTERVAL_SECONDS}s)"

install_dependencies
LAST_DEPLOY_SHA="$(git rev-parse HEAD 2>/dev/null || echo "")"
start_keeper

# Brief grace period so the first health probe isn't a false negative.
sleep 2

while true; do
  # 1) Keep the crash-restart keeper alive (restarts if the keeper itself dies).
  ensure_keeper

  # 2) Redeploy when GitHub has a new commit.
  if git remote get-url origin >/dev/null 2>&1; then
    if git fetch origin "$BRANCH" >/dev/null 2>&1; then
      local_head="$(git rev-parse HEAD 2>/dev/null || echo "")"
      remote_head="$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo "")"
      if [ -n "$remote_head" ] && [ "$local_head" != "$remote_head" ]; then
        redeploy_from_git "$BRANCH"
      fi
    else
      log "git fetch failed (network?); will retry next cycle"
    fi
  fi

  # 3) Restart wedged (non-crashed but hung) servers.
  check_health_or_restart

  sleep "$CHECK_INTERVAL_SECONDS"
done
