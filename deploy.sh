#!/bin/sh
set -e

cd "$(dirname "$0")"

echo "Installing dependencies..."
pip install -r requirements.txt --break-system-packages
pip install uvicorn asgiref --break-system-packages

echo "Starting server on 0.0.0.0:80 with uvicorn..."
PYTHON_BIN=$(which python3 || which python)
sudo "$PYTHON_BIN" -c "
from asgiref.wsgi import WsgiToAsgi
from app import app
import uvicorn
uvicorn.run(WsgiToAsgi(app), host='0.0.0.0', port=80)
"
