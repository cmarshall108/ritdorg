#!/bin/sh
set -e

cd "$(dirname "$0")"

echo "Installing dependencies..."
sudo python3 -m pip install -r requirements.txt --break-system-packages
# (uvicorn + asgiref + python-dotenv are declared in requirements.txt)

mkdir -p data
echo "Starting server on 0.0.0.0:80 with uvicorn..."
echo "   (All stdout/stderr is automatically captured to data/server.log for diagnostics.)"
echo "   For automatic crash recovery + git redeploys, prefer:  sudo ./auto_redeploy.sh"
PYTHON_BIN=$(which python3 || which python)
# Capture *everything* (uvicorn logs, Python exceptions, etc.) into the
# rotating server log so nothing is lost when the process is daemonized.
# RITD_NO_CONSOLE_LOG tells app.py to skip adding a StreamHandler so that
# our RotatingFileHandler output is not duplicated by the tee into server.log.
sudo env RITD_NO_CONSOLE_LOG=1 "$PYTHON_BIN" -c "
from asgiref.wsgi import WsgiToAsgi
from app import app
import uvicorn
uvicorn.run(WsgiToAsgi(app), host='0.0.0.0', port=80)
" 2>&1 | tee -a data/server.log
