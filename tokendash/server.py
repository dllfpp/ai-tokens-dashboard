"""HTTP server: renders the dashboard server-side, no JavaScript.

Routes
  /?g=&at=&p=&sort=      the dashboard
  /s/<session>           one conversation
  /style.css             the stylesheet (versioned by content hash, cached forever)
  /api/overview?g=&at=&p=, /api/session/<id>   JSON
"""
import hashlib
import json
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from . import caveman, fmt, query, store
from .ui import view

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("TOKENDASH_DB", os.path.join(ROOT, "data", "usage.db"))
PORT = int(os.environ.get("TOKENDASH_PORT", "3020"))
INTERVAL = int(os.environ.get("TOKENDASH_INTERVAL", "30"))
CSS = open(os.path.join(os.path.dirname(view.__file__), "style.css"), "rb").read()
CSS_VERSION = hashlib.sha1(CSS).hexdigest()[:10]
# absolute address used by the social preview tags (og:image must be a full URL)
PUBLIC_URL = os.environ.get("TOKENDASH_PUBLIC_URL", "").rstrip("/")

# logo, favicons, app icons, social image, manifest: name -> (bytes, content type, version)
STATIC_DIR = os.path.join(os.path.dirname(view.__file__), "static")
TYPES = {".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon",
         ".webmanifest": "application/manifest+json"}
ASSETS = {}
for _name in sorted(os.listdir(STATIC_DIR)):
    _data = open(os.path.join(STATIC_DIR, _name), "rb").read()
    ASSETS[_name] = (_data, TYPES.get(os.path.splitext(_name)[1], "application/octet-stream"),
                     hashlib.sha1(_data).hexdigest()[:10])
# where browsers and crawlers look without being told
ALIASES = {"/favicon.ico": "favicon.ico", "/apple-touch-icon.png": "apple-touch-icon.png",
           "/site.webmanifest": "site.webmanifest"}

db = store.connect(DB_PATH)
lock = threading.Lock()


def collector():
    while True:
        try:
            with lock:
                store.ingest(db)
        except Exception as e:  # keep serving even if one transcript is odd
            print("ingest failed:", e, file=sys.stderr)
        time.sleep(INTERVAL)


def caveman_summary():
    """Caveman proxy data lives in another program's database: if it is locked or changes shape,
    the dashboard keeps working without the caveman part."""
    try:
        return caveman.summary(db)
    except sqlite3.Error as e:
        print("caveman data unavailable:", e, file=sys.stderr)
        return None


def json_default(o):
    return o.isoformat() if isinstance(o, datetime) else str(o)


class Handler(BaseHTTPRequestHandler):
    server_version = "tokendash"

    def log_message(self, *a):
        pass

    head_only = False

    def send(self, code, body, ctype="text/html; charset=utf-8", cache="no-store"):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if not self.head_only:
            self.wfile.write(data)

    def public_url(self):
        """Absolute base for the social preview tags: TOKENDASH_PUBLIC_URL, else the address
        the browser used (scheme from the reverse proxy's X-Forwarded-Proto)."""
        if PUBLIC_URL:
            return PUBLIC_URL
        proto = self.headers.get("X-Forwarded-Proto", "http").split(",")[0].strip()
        host = self.headers.get("Host", f"127.0.0.1:{PORT}")
        return f"{proto}://{host}"

    def do_HEAD(self):
        # link-preview fetchers often ask with HEAD before GET
        self.head_only = True
        self.do_GET()

    def do_GET(self):
        url = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(url.query).items()}
        params = {k: qs.get(k) for k in ("g", "at", "p", "sort", "pw")}
        path = url.path
        try:
            if path.startswith("/api/"):
                return self.api(path, params)
            if path == "/style.css":
                return self.send(200, CSS, "text/css; charset=utf-8", "public, max-age=31536000, immutable")
            name = ALIASES.get(path) or (path[len("/static/"):] if path.startswith("/static/") else None)
            if name is not None:
                if name not in ASSETS:
                    return self.send(404, "Not found", "text/plain; charset=utf-8")
                data, ctype, ver = ASSETS[name]
                cache = "public, max-age=31536000, immutable" if qs.get("v") == ver else "public, max-age=86400"
                return self.send(200, data, ctype, cache)
            u = fmt.Links("/", params, CSS_VERSION, {n: a[2] for n, a in ASSETS.items()}, self.public_url(), url.path)
            if path == "/":
                with lock:
                    ctx = query.overview(db, params["g"] or "day", params["at"], params["p"], params["sort"] or "new", params["pw"])
                    cav = caveman_summary()
                return self.send(200, view.overview(ctx, u, cav))
            if path == "/caveman":
                with lock:
                    cav = caveman_summary()
                return self.send(200, view.caveman_page(cav, u))
            if path.startswith("/s/"):
                with lock:
                    ctx = query.session(db, unquote(path[3:]))
                if not ctx:
                    return self.send(404, "No such conversation", "text/plain; charset=utf-8")
                return self.send(200, view.session(ctx, u))
            return self.send(404, "Not found", "text/plain; charset=utf-8")
        except BrokenPipeError:
            pass

    def api(self, path, params):
        with lock:
            if path == "/api/overview":
                data = query.overview(db, params["g"] or "day", params["at"], params["p"], params["sort"] or "new", params["pw"])
            elif path == "/api/caveman":
                data = caveman_summary()
            elif path.startswith("/api/session/"):
                data = query.session(db, unquote(path[len("/api/session/"):]))
            else:
                data = None
        if data is None:
            return self.send(404, '{"error":"not found"}', "application/json")
        return self.send(200, json.dumps(data, default=json_default), "application/json")


def main():
    with lock:
        n = store.ingest(db)
    print(f"imported {n} calls, serving on :{PORT}", flush=True)
    threading.Thread(target=collector, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
