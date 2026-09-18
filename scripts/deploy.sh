#!/bin/sh
set -e

cd "$(dirname "$0")/.."

APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8080}"
PYTHON_BIN="$(command -v python3 || command -v python || true)"

if [ "$(id -u)" -eq 0 ]; then
	echo "Refusing to run the web application as root." >&2
	echo "Run as an unprivileged service account behind a reverse proxy." >&2
	exit 1
fi

if [ -z "$PYTHON_BIN" ]; then
	echo "Python is required but was not found in PATH." >&2
	exit 1
fi

if [ "$APP_PORT" -lt 1024 ]; then
	echo "Use an unprivileged port such as APP_PORT=8080 behind a reverse proxy." >&2
	exit 1
fi

echo "Installing dependencies..."
"$PYTHON_BIN" -m pip install -r requirements.txt
# (uvicorn + asgiref + python-dotenv are declared in requirements.txt)

mkdir -p data
echo "Starting server on $APP_HOST:$APP_PORT with uvicorn..."
echo "   (All stdout/stderr is automatically captured to data/server.log for diagnostics.)"
echo "   For automatic crash recovery + git redeploys, prefer: ./scripts/auto_redeploy.sh"
# Capture *everything* (uvicorn logs, Python exceptions, etc.) into the
# rotating server log so nothing is lost when the process is daemonized.
# RITD_NO_CONSOLE_LOG tells app.py to skip adding a StreamHandler so that
# our RotatingFileHandler output is not duplicated by the tee into server.log.
RITD_NO_CONSOLE_LOG=1 "$PYTHON_BIN" -c "
from asgiref.wsgi import WsgiToAsgi
from ritdorg.app import app
import uvicorn
uvicorn.run(WsgiToAsgi(app), host='$APP_HOST', port=$APP_PORT)
" 2>&1 | tee -a data/server.log
