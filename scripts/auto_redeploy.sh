#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

CHECK_INTERVAL_SECONDS="${CHECK_INTERVAL_SECONDS:-10800}" # 3 hours
APP_PORT="${APP_PORT:-80}"
APP_HOST="${APP_HOST:-0.0.0.0}"
FORCE_KILL_PORT_PROCESS="${FORCE_KILL_PORT_PROCESS:-0}"

# Where we automatically capture *all* stdout/stderr (uvicorn access logs,
# Python tracebacks, print()s, module loggers, etc.). Rotated inside the keeper.
LOG_FILE="data/server.log"
KEEPER_PID=""

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "Python is required but was not found in PATH."
  exit 1
fi

if [ "$APP_PORT" -lt 1024 ] && [ "$(id -u)" -ne 0 ]; then
  echo "Port $APP_PORT usually requires root. Run with sudo or set APP_PORT to a non-privileged port."
  exit 1
fi

ensure_https_origin() {
  ORIGIN_URL="$(git remote get-url origin)"

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
  if "$PYTHON_BIN" -m pip help install | grep -q -- "--break-system-packages"; then
    "$PYTHON_BIN" -m pip install -r requirements.txt --break-system-packages
  else
    "$PYTHON_BIN" -m pip install -r requirements.txt
  fi
  # (uvicorn + asgiref + python-dotenv are declared in requirements.txt)
}

check_port_available() {
  if ! command -v lsof >/dev/null 2>&1; then
    return 0
  fi

  LISTEN_PIDS="$(lsof -t -iTCP:"$APP_PORT" -sTCP:LISTEN 2>/dev/null | tr '\n' ' ')"
  if [ -z "$LISTEN_PIDS" ]; then
    return 0
  fi

  echo "Port $APP_PORT is already in use by PID(s): $LISTEN_PIDS"
  lsof -nP -iTCP:"$APP_PORT" -sTCP:LISTEN || true

  if [ "$FORCE_KILL_PORT_PROCESS" = "1" ]; then
    echo "FORCE_KILL_PORT_PROCESS=1 set; stopping PID(s) on port $APP_PORT"
    for pid in $LISTEN_PIDS; do
      kill "$pid" 2>/dev/null || true
    done
    return 0
  fi

  echo "Set FORCE_KILL_PORT_PROCESS=1 to stop current listener(s), or use a different APP_PORT."
  exit 1
}

# Build the exact one-liner we exec so we can reliably pkill / pgrep it.
SERVER_CMD="from asgiref.wsgi import WsgiToAsgi; from ritdorg.app import app; import uvicorn; uvicorn.run(WsgiToAsgi(app), host='$APP_HOST', port=$APP_PORT)"

start_keeper() {
  # Ensure log directory exists (data/ is already used for DB + caches).
  mkdir -p "$(dirname "$LOG_FILE")"

  # Simple size-based rotation (keeps .1 ... .5) so the log never grows unbounded.
  if [ -f "$LOG_FILE" ]; then
    sz=$(wc -c <"$LOG_FILE" 2>/dev/null || echo 0)
    if [ "$sz" -gt 10485760 ]; then  # 10 MiB
      for i in 4 3 2 1; do
        if [ -f "$LOG_FILE.$i" ]; then
          mv "$LOG_FILE.$i" "$LOG_FILE.$((i + 1))" 2>/dev/null || true
        fi
      done
      mv "$LOG_FILE" "$LOG_FILE.1" 2>/dev/null || true
    fi
  fi

  check_port_available
  echo "Starting auto-restarting server keeper (logs -> $LOG_FILE) on $APP_HOST:$APP_PORT"

  # The keeper subshell lives "forever". Inside it we loop the actual server
  # process so that *any* crash, OOM, uncaught exception, or uvicorn exit
  # causes an immediate restart (with 5s backoff). All output is tee'd to the
  # log file. This is what keeps the web server online at all times.
  (
    while true; do
      echo "=== $(date '+%Y-%m-%d %H:%M:%S') Starting RITDorg (auto-restart keeper) ===" >> "$LOG_FILE"
      # The python -c is the real server; it blocks until it dies.
      # RITD_NO_CONSOLE_LOG suppresses the StreamHandler so RotatingFileHandler
      # lines are not duplicated by the outer tee/redirect into server.log.
      RITD_NO_CONSOLE_LOG=1 "$PYTHON_BIN" -c "$SERVER_CMD" >> "$LOG_FILE" 2>&1
      code=$?
      echo "=== $(date '+%Y-%m-%d %H:%M:%S') Server process exited (code=$code). Restarting in 5s... ===" >> "$LOG_FILE"
      sleep 5
    done
  ) &
  KEEPER_PID=$!
  echo "$KEEPER_PID" > .keeper.pid
  echo "Keeper PID: $KEEPER_PID"
}

stop_keeper() {
  # Stop the keeper subshell (and therefore the inner server loop).
  if [ -f .keeper.pid ]; then
    kp=$(cat .keeper.pid 2>/dev/null || echo "")
    if [ -n "$kp" ] && kill -0 "$kp" 2>/dev/null; then
      echo "Stopping keeper PID $kp"
      kill "$kp" 2>/dev/null || true
      # Also reap direct children (the python -c instances).
      pkill -P "$kp" 2>/dev/null || true
      wait "$kp" 2>/dev/null || true
    fi
    rm -f .keeper.pid
  fi
  KEEPER_PID=""

  # Belt-and-suspenders: kill any stray server processes that match our
  # distinctive python -c invocation (in case of manual starts, old keepers, etc).
  pkill -f "from asgiref.wsgi import WsgiToAsgi; from ritdorg.app import app" 2>/dev/null || true
}

cleanup() {
  stop_keeper
}

trap cleanup INT TERM EXIT

ensure_https_origin

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "Tracking branch: $BRANCH"

install_dependencies
start_keeper

while true; do
  echo "Checking for updates..."
  git fetch origin "$BRANCH"

  LOCAL_HEAD="$(git rev-parse HEAD)"
  REMOTE_HEAD="$(git rev-parse "origin/$BRANCH")"

  if [ "$LOCAL_HEAD" != "$REMOTE_HEAD" ]; then
    echo "New commit detected on origin/$BRANCH. Pulling and redeploying..."
    stop_keeper
    git pull --ff-only origin "$BRANCH"
    install_dependencies
    start_keeper
  else
    # The keeper subshell (and its inner restart loop) keeps the server
    # process alive at all times. We only need to make sure the *keeper*
    # itself is still running (it can only die on external kill or OOM of
    # the whole script).
    if [ -f .keeper.pid ]; then
      kp=$(cat .keeper.pid 2>/dev/null || echo 0)
      if ! kill -0 "$kp" 2>/dev/null; then
        echo "Keeper process disappeared. Restarting keeper (and therefore the web server)..."
        start_keeper
      fi
    else
      echo "No keeper PID file. Starting keeper..."
      start_keeper
    fi
    echo "No updates found. Next check in $CHECK_INTERVAL_SECONDS seconds. (Server keeper keeps it online; logs in $LOG_FILE)"
  fi

  sleep "$CHECK_INTERVAL_SECONDS"
done
