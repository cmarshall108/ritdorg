#!/bin/sh
set -eu

cd "$(dirname "$0")"

CHECK_INTERVAL_SECONDS="${CHECK_INTERVAL_SECONDS:-10800}" # 3 hours
APP_PORT="${APP_PORT:-80}"
APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PID=""

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
    "$PYTHON_BIN" -m pip install uvicorn asgiref --break-system-packages
  else
    "$PYTHON_BIN" -m pip install -r requirements.txt
    "$PYTHON_BIN" -m pip install uvicorn asgiref
  fi
}

start_app() {
  echo "Starting app from app.py on $APP_HOST:$APP_PORT"
  "$PYTHON_BIN" -c "from asgiref.wsgi import WsgiToAsgi; from app import app; import uvicorn; uvicorn.run(WsgiToAsgi(app), host='$APP_HOST', port=$APP_PORT)" &
  APP_PID=$!
  echo "App PID: $APP_PID"
}

stop_app() {
  if [ -n "$APP_PID" ] && kill -0 "$APP_PID" 2>/dev/null; then
    echo "Stopping app PID $APP_PID"
    kill "$APP_PID"
    wait "$APP_PID" 2>/dev/null || true
    APP_PID=""
  fi
}

cleanup() {
  stop_app
}

trap cleanup INT TERM EXIT

ensure_https_origin

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "Tracking branch: $BRANCH"

install_dependencies
start_app

while true; do
  echo "Checking for updates..."
  git fetch origin "$BRANCH"

  LOCAL_HEAD="$(git rev-parse HEAD)"
  REMOTE_HEAD="$(git rev-parse "origin/$BRANCH")"

  if [ "$LOCAL_HEAD" != "$REMOTE_HEAD" ]; then
    echo "New commit detected on origin/$BRANCH. Pulling and redeploying..."
    stop_app
    git pull --ff-only origin "$BRANCH"
    install_dependencies
    start_app
  elif [ -n "$APP_PID" ] && ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "App process is not running. Restarting..."
    start_app
  else
    echo "No updates found. Next check in $CHECK_INTERVAL_SECONDS seconds."
  fi

  sleep "$CHECK_INTERVAL_SECONDS"
done
