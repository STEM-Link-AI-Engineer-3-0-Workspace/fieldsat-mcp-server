"""Root ASGI entry point for hosts that look for app.py (for example Vercel)."""

from fieldsat.asgi import app

__all__ = ["app"]
