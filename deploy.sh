#!/bin/sh
set -e

cd "$(dirname "$0")"

echo "Installing dependencies..."
pip install -r requirements.txt
pip install uvicorn asgiref

echo "Starting server on 0.0.0.0:80 with uvicorn..."
sudo $(which python) -c "
from asgiref.wsgi import WsgiToAsgi
from app import app
import uvicorn
uvicorn.run(WsgiToAsgi(app), host='0.0.0.0', port=80)
"
