#!/bin/sh
set -e

cd "$(dirname "$0")"

echo "Installing dependencies..."
sudo python3 -m pip install -r requirements.txt --break-system-packages
sudo python3 -m pip install uvicorn asgiref --break-system-packages

mkdir -p data
echo "Starting server on 0.0.0.0:80 with uvicorn..."
echo "   (All stdout/stderr is automatically captured to data/server.log for diagnostics.)"
echo "   For automatic crash recovery + git redeploys, prefer:  sudo ./auto_redeploy.sh"
PYTHON_BIN=$(which python3 || which python)
# Capture *everything* (uvicorn logs, Python exceptions, etc.) into the
# rotating server log so nothing is lost when the process is daemonized.
sudo "$PYTHON_BIN" -c "
from asgiref.wsgi import WsgiToAsgi
from app import app
import uvicorn
uvicorn.run(WsgiToAsgi(app), host='0.0.0.0', port=80)
" 2>&1 | tee -a data/server.log
