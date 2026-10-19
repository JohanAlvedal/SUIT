"""Localhost bridge for the SUIT kiosk extension.

Why: Ubuntu ships Chromium as a Snap. A native messaging host started by the
Snap runs inside its AppArmor sandbox and cannot call systemctl/logind, so
the in-page power/session buttons never worked there. The extension instead
calls this small HTTP server on 127.0.0.1, which runs as the logged-in user
inside the graphical session (started by the kiosk launcher), so logind
allows poweroff/reboot without a password exactly as it does from the GNOME
menu.

Security model:
- binds 127.0.0.1 only
- every request needs the per-install random token (X-SUIT-Token header);
  the token is only readable by the extension (its own bridge_config.json)
  and the user (~/.config/suit/kiosk_bridge.json, 0600)
- the custom header and JSON content type force a CORS preflight, which this
  server never approves, so ordinary web pages cannot trigger actions
- an Origin header, if present, must be the SUIT extension
- only a fixed allowlist of actions; the action logic is the same code the
  native messaging host uses (kiosk_extension/host/suit_kiosk_host.py)
"""
from __future__ import annotations

import hmac
import importlib.util
import json
import os
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 47231
CONFIG_PATH = Path.home() / ".config" / "suit" / "kiosk_bridge.json"
EXTENSION_ID = "ifmcoidaalmjijjhnpafmjngeceapboj"
ALLOWED_ORIGIN = f"chrome-extension://{EXTENSION_ID}"
ALLOWED_ACTIONS = frozenset({
    "ping", "poweroff", "reboot", "exit_kiosk", "get_light_status", "toggle_light",
})
MAX_BODY = 1024

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HOST_SCRIPT = PROJECT_ROOT / "kiosk_extension" / "host" / "suit_kiosk_host.py"


def load_or_create_config(path: Path | None = None) -> dict:
    """Return {"port", "token"}; create a 0600 config with a fresh token if missing."""
    target = path or CONFIG_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(data.get("token"), str) and len(data["token"]) >= 32:
            return {"port": int(data.get("port", BRIDGE_PORT)), "token": data["token"]}
    except (OSError, ValueError):
        pass
    data = {"port": BRIDGE_PORT, "token": secrets.token_urlsafe(32)}
    target.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.chmod(target, 0o600)
    return data


def _load_action_handler():
    """Reuse the native host's handle_action so both paths behave identically."""
    spec = importlib.util.spec_from_file_location("suit_kiosk_host", HOST_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.handle_action


def make_handler(token: str, handle_action):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SUITKioskBridge/1"

        def log_message(self, fmt, *args):  # keep journal quiet
            pass

        def _reply(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):  # never approve a CORS preflight
            self._reply(405, {"status": "error", "error": "method not allowed"})

        def do_GET(self):
            self._reply(405, {"status": "error", "error": "method not allowed"})

        def do_POST(self):
            if self.path != "/action":
                return self._reply(404, {"status": "error", "error": "not found"})
            origin = self.headers.get("Origin")
            if origin is not None and origin != ALLOWED_ORIGIN:
                return self._reply(403, {"status": "error", "error": "forbidden origin"})
            supplied = self.headers.get("X-SUIT-Token", "")
            if not hmac.compare_digest(supplied.encode(), token.encode()):
                return self._reply(401, {"status": "error", "error": "unauthorized"})
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._reply(415, {"status": "error", "error": "json required"})
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY:
                return self._reply(413, {"status": "error", "error": "bad length"})
            try:
                request = json.loads(self.rfile.read(length) or b"{}")
                action = request.get("action", "")
            except (ValueError, AttributeError):
                return self._reply(400, {"status": "error", "error": "invalid json"})
            if action not in ALLOWED_ACTIONS:
                return self._reply(400, {"status": "error", "error": "unknown action"})
            try:
                return self._reply(200, handle_action(action))
            except Exception as exc:  # never crash the bridge on one bad action
                return self._reply(500, {"status": "error", "error": str(exc)})

    return Handler


def serve(config: dict | None = None, handle_action=None) -> int:
    cfg = config or load_or_create_config()
    handler = make_handler(cfg["token"], handle_action or _load_action_handler())
    try:
        server = ThreadingHTTPServer((BRIDGE_HOST, cfg["port"]), handler)
    except OSError:
        # Already running in this session (port taken): nothing to do.
        return 0
    server.daemon_threads = True
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(serve())
