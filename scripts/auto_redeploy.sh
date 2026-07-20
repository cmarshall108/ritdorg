#!/bin/sh
# RITDorg production keeper:
#   - Always restarts the web server after any crash/exit
#   - Polls GitHub frequently and redeploys on every new commit
#   - Health-checks the live port and force-restarts if the process is wedged
#   - Captures all logs to data/server.log
set -eu

cd "$(dirname "$0")/.."

# How often to poll git + health (default: 60s — was 3 hours).
CHECK_INTERVAL_SECONDS="${CHECK_INTERVAL_SECONDS:-60}"
# Backoff after a crash before relaunching the server process.
RESTART_DELAY_SECONDS="${RESTART_DELAY_SECONDS:-3}"
# Consecutive failed health checks before force-restarting a wedged process.
HEALTH_FAIL_THRESHOLD="${HEALTH_FAIL_THRESHOLD:-3}"
APP_PORT="${APP_PORT:-80}"
APP_HOST="${APP_HOST:-0.0.0.0}"
FORCE_KILL_PORT_PROCESS="${FORCE_KILL_PORT_PROCESS:-0}"
# Optional absolute health URL override (defaults to loopback on APP_PORT).
HEALTH_URL="${HEALTH_URL:-}"

LOG_FILE="data/server.log"
KEEPER_PID=""
HEALTH_FAILS=0
LAST_DEPLOY_SHA=""

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "Python is required but was not found in PATH."
  exit 1
fi

if [ "$APP_PORT" -lt 1024 ] && [ "$(id -u)" -ne 0 ]; then
  echo "Port $APP_PORT usually requires root. Run with sudo or set APP_PORT to a non-privileged port."
  exit 1
fi

log() {
  # Mirror keeper messages to both stdout (nohup capture) and server.log.
  msg="=== $(date '+%Y-%m-%d %H:%M:%S') $* ==="
  echo "$msg"
  mkdir -p "$(dirname "$LOG_FILE")"
  echo "$msg" >> "$LOG_FILE"
}

ensure_https_origin() {
  ORIGIN_URL="$(git remote get-url origin 2>/dev/null || true)"
  if [ -z "$ORIGIN_URL" ]; then
    echo "No git origin configured; git auto-redeploy will be skipped."
    return 0
  fi

  case "$ORIGIN_URL" in
    https://*)
      ;;
    git@github.com:*)
      REPO_PATH="${ORIGIN_URL#git@github.com:}"
      git remote set-url origin "https://github.com/$REPO_PATH"
      echo "Updated origin to HTTPS: https://github.com/$REPO_PATH"
      ;;
    ssh://git@github.com/*)
      REPO_PATH="${ORIGIN_URL#ssh://git@github.com/}"
      git remote set-url origin "https://github.com/$REPO_PATH"
      echo "Updated origin to HTTPS: https://github.com/$REPO_PATH"
      ;;
    *)
      echo "Origin is not a standard GitHub SSH URL. Leaving as-is: $ORIGIN_URL"
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
  if [ -f "$LOG_FILE" ]; then
    sz=$(wc -c <"$LOG_FILE" 2>/dev/null || echo 0)
    # Portable numeric compare (strip whitespace from wc).
    sz=$(echo "$sz" | tr -d '[:space:]')
    if [ "${sz:-0}" -gt 10485760 ]; then  # 10 MiB
      i=4
      while [ "$i" -ge 1 ]; do
        if [ -f "$LOG_FILE.$i" ]; then
          mv "$LOG_FILE.$i" "$LOG_FILE.$((i + 1))" 2>/dev/null || true
        fi
        i=$((i - 1))
      done
      mv "$LOG_FILE" "$LOG_FILE.1" 2>/dev/null || true
    fi
  fi
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
  LISTEN_PIDS="$(port_listener_pids)"
  if [ -z "$(echo "$LISTEN_PIDS" | tr -d '[:space:]')" ]; then
    return 0
  fi
  log "Freeing port $APP_PORT (PIDs: $LISTEN_PIDS)"
  for pid in $LISTEN_PIDS; do
    kill "$pid" 2>/dev/null || true
  done
  # Give listeners a moment, then SIGKILL stragglers.
  sleep 1
  LISTEN_PIDS="$(port_listener_pids)"
  for pid in $LISTEN_PIDS; do
    kill -9 "$pid" 2>/dev/null || true
  done
  sleep 1
}

check_port_available() {
  LISTEN_PIDS="$(port_listener_pids)"
  if [ -z "$(echo "$LISTEN_PIDS" | tr -d '[:space:]')" ]; then
    return 0
  fi

  echo "Port $APP_PORT is already in use by PID(s): $LISTEN_PIDS"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$APP_PORT" -sTCP:LISTEN || true
  fi

  if [ "$FORCE_KILL_PORT_PROCESS" = "1" ]; then
    free_port
    return 0
  fi

  echo "Set FORCE_KILL_PORT_PROCESS=1 to stop current listener(s), or use a different APP_PORT."
  exit 1
}

# Distinctive one-liner so pkill/pgrep can find our server process reliably.
SERVER_CMD="from asgiref.wsgi import WsgiToAsgi; from ritdorg.app import app; import uvicorn; uvicorn.run(WsgiToAsgi(app), host='$APP_HOST', port=$APP_PORT, log_level='info', timeout_keep_alive=30, limit_concurrency=100)"

server_match_pattern() {
  echo "from asgiref.wsgi import WsgiToAsgi; from ritdorg.app import app"
}

kill_server_processes() {
  # Kill any python -c server matching our distinctive import string.
  pkill -f "$(server_match_pattern)" 2>/dev/null || true
  sleep 1
  # Force-kill leftovers.
  pkill -9 -f "$(server_match_pattern)" 2>/dev/null || true
  free_port
}

start_keeper() {
  rotate_log_if_needed
  check_port_available
  log "Starting auto-restarting server keeper (logs -> $LOG_FILE) on $APP_HOST:$APP_PORT"

  # The keeper subshell lives forever. Inside it we loop the actual server
  # process so that *any* crash, OOM, uncaught exception, or uvicorn exit
  # causes an automatic restart. All output is appended to the log file.
  (
    # Don't inherit the outer EXIT trap into the subshell.
    trap - INT TERM EXIT
    fails=0
    while true; do
      echo "=== $(date '+%Y-%m-%d %H:%M:%S') Starting RITDorg (auto-restart keeper) ===" >> "$LOG_FILE"
      # RITD_NO_CONSOLE_LOG suppresses StreamHandler so RotatingFileHandler
      # lines are not duplicated by this redirect into server.log.
      set +e
      RITD_NO_CONSOLE_LOG=1 "$PYTHON_BIN" -c "$SERVER_CMD" >> "$LOG_FILE" 2>&1
      code=$?
      set -e
      fails=$((fails + 1))
      # Exponential-ish backoff capped at 60s so a boot-loop doesn't thrash.
      delay="$RESTART_DELAY_SECONDS"
      if [ "$fails" -gt 5 ]; then
        delay=15
      fi
      if [ "$fails" -gt 15 ]; then
        delay=60
      fi
      echo "=== $(date '+%Y-%m-%d %H:%M:%S') Server process exited (code=$code). Restarting in ${delay}s (fail #$fails)... ===" >> "$LOG_FILE"
      # Clear anything still bound to the port before relaunch.
      pkill -f "$(server_match_pattern)" 2>/dev/null || true
      sleep "$delay"
      # Decay fail counter slowly so a recovered process doesn't stay in
      # long-backoff mode forever.
      if [ "$fails" -gt 0 ]; then
        fails=$((fails - 1))
      fi
    done
  ) &
  KEEPER_PID=$!
  echo "$KEEPER_PID" > .keeper.pid
  log "Keeper PID: $KEEPER_PID"
  HEALTH_FAILS=0
}

stop_keeper() {
  if [ -f .keeper.pid ]; then
    kp=$(cat .keeper.pid 2>/dev/null || echo "")
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
    rm -f .keeper.pid
  fi
  KEEPER_PID=""
  kill_server_processes
}

keeper_alive() {
  if [ -f .keeper.pid ]; then
    kp=$(cat .keeper.pid 2>/dev/null || echo "")
    if [ -n "$kp" ] && kill -0 "$kp" 2>/dev/null; then
      KEEPER_PID="$kp"
      return 0
    fi
  fi
  return 1
}

ensure_keeper() {
  if keeper_alive; then
    return 0
  fi
  log "Keeper process missing — restarting keeper (and therefore the web server)"
  start_keeper
}

health_url() {
  if [ -n "$HEALTH_URL" ]; then
    echo "$HEALTH_URL"
    return
  fi
  # Prefer loopback; APP_HOST may be 0.0.0.0 which is not a connect target.
  echo "http://127.0.0.1:${APP_PORT}/healthz"
}

probe_health() {
  url="$(health_url)"
  # Prefer curl; fall back to python urllib.
  if command -v curl >/dev/null 2>&1; then
    code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")
    [ "$code" = "200" ]
    return $?
  fi
  "$PYTHON_BIN" - "$url" <<'PY' 2>/dev/null
import sys, urllib.request
url = sys.argv[1]
try:
    with urllib.request.urlopen(url, timeout=5) as r:
        sys.exit(0 if getattr(r, "status", 200) == 200 else 1)
except Exception:
    sys.exit(1)
PY
}

check_health_or_restart() {
  # Only probe once the keeper is up; give a brand-new process a few seconds.
  if ! keeper_alive; then
    ensure_keeper
    return 0
  fi
  # If nothing is listening yet (boot), don't count as a hard fail immediately.
  LISTEN_PIDS="$(port_listener_pids)"
  if [ -z "$(echo "$LISTEN_PIDS" | tr -d '[:space:]')" ]; then
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
    # Kill only the server children; keeper loop will relaunch automatically.
    kill_server_processes
    HEALTH_FAILS=0
    # If the keeper itself died during the kill, bring it back.
    ensure_keeper
  fi
}

redeploy_from_git() {
  branch="$1"
  log "New commit on origin/$branch — pulling and redeploying"
  stop_keeper
  # Prefer a clean fast-forward; if that fails (local drift), reset hard to
  # origin so production always tracks GitHub. Local uncommitted work on a
  # production host is not expected.
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
  # 1) Always keep the crash-restart keeper alive.
  ensure_keeper

  # 2) GitHub change detection — redeploy on every new commit.
  if git remote get-url origin >/dev/null 2>&1; then
    if git fetch origin "$BRANCH" >/dev/null 2>&1; then
      LOCAL_HEAD="$(git rev-parse HEAD 2>/dev/null || echo "")"
      REMOTE_HEAD="$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo "")"
      if [ -n "$REMOTE_HEAD" ] && [ "$LOCAL_HEAD" != "$REMOTE_HEAD" ]; then
        redeploy_from_git "$BRANCH"
      fi
    else
      log "git fetch failed (network?); will retry next cycle"
    fi
  fi

  # 3) Liveness probe — restart wedged (non-crashed but hung) servers.
  check_health_or_restart

  sleep "$CHECK_INTERVAL_SECONDS"
done
