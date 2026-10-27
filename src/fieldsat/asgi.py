"""ASGI app for hosting the live server behind uvicorn or a platform such as Vercel.

uv run uvicorn fieldsat.asgi:app --port 8000
"""

from dotenv import find_dotenv, load_dotenv

from fieldsat.runtime import create_live_server

# Read .env from the working directory when there is one. Platform variables win.
load_dotenv(find_dotenv(usecwd=True))

app = create_live_server().http_app(stateless_http=True, json_response=True)
