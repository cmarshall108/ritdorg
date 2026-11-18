"""Threaded ASGI adapter for the Flask application."""

from a2wsgi import WSGIMiddleware

from .app import app

asgi_app = WSGIMiddleware(app, workers=8)
