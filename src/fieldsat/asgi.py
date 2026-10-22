"""ASGI app for hosting the live server behind uvicorn or a platform such as Vercel.

uv run uvicorn fieldsat.asgi:app --port 8000
"""

from .runtime import create_live_server

app = create_live_server().http_app(stateless_http=True, json_response=True)
