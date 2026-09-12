"""Loopback-only HTTP surface for the Helix Engine."""

import json
import hmac
import os
import signal
import socket
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

from .runtime import Runtime


MAX_SETTINGS_BODY = 8192
WEB_ROOT = Path(__file__).resolve().parent / "web"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/release.js": ("app.js", "application/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/release.css": ("style.css", "text/css; charset=utf-8"),
}


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


class HelixHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = os.name != 'nt'
    daemon_threads = True

    def __init__(self, address, handler, runtime):
        self.runtime = runtime
        super().__init__(address, handler)

    def server_bind(self):
        # HTTPServer resolves its hostname synchronously. This server only
        # binds a literal loopback address; startup must not depend on DNS.
        # Windows SO_REUSEADDR permits a second active listener, unlike
        # POSIX. Claim the port exclusively so repeat launch opens the HUD.
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    def server_close(self):
        try:
            super().server_close()
        finally:
            self.runtime.close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        super().setup()
        # A declared body length must not leave a worker blocked forever when
        # a hostile client disconnects or sends fewer bytes than promised.
        self.connection.settimeout(2.0)

    def log_message(self, format, *args):
        # The command surface is intentionally quiet; telemetry is in SQLite.
        return

    @property
    def runtime(self):
        return self.server.runtime

    def _send_bytes(self, status, body, content_type="application/json; charset=utf-8", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        if extra:
            for key, value in extra.items():
                self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(body)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _send_json(self, status, value):
        self._send_bytes(status, _json(value))

    def _host(self):
        header = self.headers.get("Host")
        if not header or "\x00" in header:
            return None
        if header.startswith("["):
            closing = header.find("]")
            if closing < 0:
                return None
            host = header[1:closing].lower()
            port = header[closing + 2 :] if header[closing + 1 : closing + 2] == ":" else ""
        else:
            parts = header.rsplit(":", 1)
            host = parts[0].lower()
            port = parts[1] if len(parts) == 2 else ""
        if host not in {"127.0.0.1", "localhost"}:
            return None
        expected_port = str(self.server.server_port)
        if port != expected_port:
            return None
        return host

    def _same_origin(self):
        host = self._host()
        origin = self.headers.get("Origin")
        if host is None or not origin:
            return False
        try:
            parsed = urlsplit(origin)
            origin_port = parsed.port
        except ValueError:
            return False
        return (
            parsed.scheme == "http"
            and parsed.hostname == host
            and origin_port == self.server.server_port
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
            and parsed.username is None
            and parsed.password is None
        )

    def _settings_request_valid(self):
        if not self._same_origin():
            return False
        token = self.headers.get("X-Helix-CSRF")
        return isinstance(token, str) and hmac.compare_digest(token, self.runtime.csrf_token)

    def _body(self):
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length) if raw_length is not None else -1
        except (TypeError, ValueError):
            length = -1
        if length < 0:
            raise ValueError("Content-Length required")
        if length > MAX_SETTINGS_BODY:
            raise OverflowError("Request body exceeds limit")
        try:
            raw = self.rfile.read(length)
        except OSError as exc:
            raise ValueError("Incomplete request body") from exc
        if len(raw) != length:
            raise ValueError("Incomplete request body")
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            raise ValueError("Content-Type application/json required")
        try:
            return json.loads(
                raw,
                object_pairs_hook=self._unique_object,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Malformed JSON") from exc

    @staticmethod
    def _unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def do_GET(self):
        if self._host() is None:
            self._send_json(403, {"error": "invalid host"})
            return
        path = urlsplit(self.path).path
        if path == "/api/release-state":
            try:
                self._send_json(200, self.runtime.release_state())
            except Exception:
                self._send_json(500, {"error": "release state unavailable"})
            return
        if path == "/api/release-events":
            self._events()
            return
        static = STATIC_FILES.get(path)
        if static is not None:
            filename, content_type = static
            try:
                body = (WEB_ROOT / filename).read_bytes()
            except OSError:
                self._send_json(404, {"error": "not found"})
                return
            self._send_bytes(200, body, content_type)
            return
        self._send_json(404, {"error": "not found"})

    def _events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            while True:
                body = _json(self.runtime.release_state()).decode("utf-8")
                self.wfile.write(("data: " + body + "\n\n").encode("utf-8"))
                self.wfile.flush()
                for _ in range(10):
                    time.sleep(0.1)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            self.close_connection = True

    def do_POST(self):
        path = urlsplit(self.path).path
        if path != "/api/settings":
            self._send_json(404, {"error": "not found"})
            return
        if not self._settings_request_valid():
            self._send_json(403, {"error": "origin, host, or CSRF check failed"})
            return
        try:
            body = self._body()
        except OverflowError as exc:
            self._send_json(413, {"error": str(exc)})
            return
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        if not isinstance(body, dict) or set(body) != {"enabled", "revision"}:
            self._send_json(400, {"error": "enabled and revision are required"})
            return
        if type(body.get("enabled")) is not bool or type(body.get("revision")) is not int or body["revision"] < 0:
            self._send_json(400, {"error": "invalid settings"})
            return
        try:
            result = self.runtime.switch(body["enabled"], body["revision"])
        except ValueError as exc:
            if str(exc).startswith("Settings changed"):
                self._send_json(409, {"error": str(exc), "settings": self.runtime.settings()})
            else:
                self._send_json(400, {"error": str(exc)})
            return
        self._send_json(200, result)


def make_server(runtime, port=8769):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("Port must be an integer from 0 through 65535")
    runtime.enable_pricing()
    try:
        return HelixHTTPServer(("127.0.0.1", port), Handler, runtime)
    except BaseException:
        runtime.close()
        raise


def serve(runtime, port=8769, open_browser=False):
    """Serve until SIGTERM/SIGINT; always close the listening socket."""
    try:
        server = make_server(runtime, port)
    except OSError:
        # A second desktop launch can reopen a recognized local HUD. Never
        # terminate or replace a process occupying the requested port.
        if open_browser and port:
            try:
                with urlopen(f"http://127.0.0.1:{port}/api/release-state", timeout=2) as response:
                    payload = response.read(2_000_001)
                if len(payload) <= 2_000_000 and json.loads(payload).get('schema') == 'helix.app.v1':
                    webbrowser.open(f"http://127.0.0.1:{port}/")
                    return
            except (OSError, ValueError, AttributeError):
                pass
        raise
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{server.server_port}/")
    previous = {}

    def stop(signum, frame):
        # shutdown must run outside serve_forever's thread.
        threading.Thread(target=server.shutdown, name="helix-server-shutdown", daemon=True).start()

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, stop)
        except (ValueError, OSError):
            pass
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        for signum, handler in previous.items():
            try:
                signal.signal(signum, handler)
            except (ValueError, OSError):
                pass


__all__ = ["Handler", "HelixHTTPServer", "make_server", "serve"]
