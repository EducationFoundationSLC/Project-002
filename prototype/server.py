"""Self-contained local server for the Project-002 website prototype.

Usage:
    python prototype/server.py

Serves prototype/index.html on http://localhost:8000.
If a built SQLite database exists at prototype/data/property.db (or website/data/property.db),
serves the /api/* endpoints locally. Otherwise the prototype automatically falls back to
live PASLC GIS data.
"""
import importlib.util
import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOCAL_DB = os.path.join(HERE, "data", "property.db")
WEBSITE_DB = os.path.join(ROOT, "website", "data", "property.db")
DB_PATH = LOCAL_DB if os.path.exists(LOCAL_DB) else (WEBSITE_DB if os.path.exists(WEBSITE_DB) else None)

backend = None
if DB_PATH:
    spec = importlib.util.spec_from_file_location("website_server", os.path.join(ROOT, "website", "server.py"))
    backend = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.join(ROOT, "website"))
    spec.loader.exec_module(backend)
    backend.DB_PATH = DB_PATH


class PrototypeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path.startswith("/api/"):
            if not backend:
                return self.send_error(503, "Local SQLite database not built yet")
            q = {k: v[-1] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/api/properties":
                    return self.send_json(backend.api_properties(q))
                if url.path == "/api/map":
                    return self.send_json(backend.api_map(q))
                if url.path == "/api/filters":
                    return self.send_json(backend.api_filters())
                if url.path.startswith("/api/property/"):
                    data = backend.api_property(int(url.path.rsplit("/", 1)[1]))
                    return self.send_json(data) if data else self.send_error(404)
            except (ValueError, KeyError):
                return self.send_error(400, "Bad parameter")
            return self.send_error(404)
        self.send_static(url.path)

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        full = os.path.realpath(os.path.join(HERE, rel))
        if not full.startswith(os.path.realpath(HERE) + os.sep) or not os.path.isfile(full):
            return self.send_error(404)
        with open(full, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(full)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def main():
    port = int(os.environ.get("PORT", 8000))
    mode = f"Local SQLite ({DB_PATH})" if DB_PATH else "Live PASLC GIS fallback (no property.db found)"
    print(f"Serving prototype on http://localhost:{port}  [{mode}]")
    ThreadingHTTPServer(("127.0.0.1", port), PrototypeHandler).serve_forever()


if __name__ == "__main__":
    main()
