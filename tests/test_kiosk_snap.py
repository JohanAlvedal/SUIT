"""Kiosk launch robustness on Ubuntu (Chromium Snap) — non-destructive."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.kiosk_service import KioskService


class KioskFlagTests(unittest.TestCase):
    def test_flags_are_session_type_neutral_and_keyring_free(self):
        flags = KioskService.get_kiosk_flags(enable_controls=False)
        self.assertIn("--ozone-platform-hint=auto", flags)
        self.assertNotIn("--ozone-platform=wayland", flags)
        self.assertIn("--password-store=basic", flags)
        self.assertIn("--hide-crash-restore-bubble", flags)
        self.assertIn("--kiosk", flags)


class LauncherScriptTests(unittest.TestCase):
    def _run_launcher(self, home: Path) -> Path:
        with patch.object(Path, "home", return_value=home):
            script = KioskService.ensure_launcher_script()
        self.assertEqual(subprocess.run(["bash", "-n", str(script)]).returncode, 0)
        env = dict(os.environ, HOME=str(home))
        # `true` stands in for the browser; busctl/gdbus are absent or fail harmlessly.
        subprocess.run([str(script), "true"], env=env, timeout=30, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return script

    def test_cleans_snap_profile_after_power_cut(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            snap = home / "snap" / "chromium" / "common" / "chromium"
            (snap / "Default").mkdir(parents=True)
            (snap / "SingletonLock").symlink_to("otherhost-1234")
            (snap / "SingletonSocket").write_text("")
            prefs = snap / "Default" / "Preferences"
            prefs.write_text(json.dumps({"profile": {"exit_type": "Crashed", "exited_cleanly": False}},
                                        separators=(",", ":")))
            self._run_launcher(home)
            self.assertFalse((snap / "SingletonLock").is_symlink())
            self.assertFalse((snap / "SingletonSocket").exists())
            data = json.loads(prefs.read_text())
            self.assertEqual(data["profile"]["exit_type"], "Normal")
            self.assertTrue(data["profile"]["exited_cleanly"])

    def test_missing_profiles_are_fine(self):
        with tempfile.TemporaryDirectory() as td:
            self._run_launcher(Path(td))

    def test_stale_lock_cleanup_includes_snap_profile(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            snap = home / "snap" / "chromium" / "common" / "chromium"
            snap.mkdir(parents=True)
            (snap / "SingletonCookie").write_text("")
            with patch("core.kiosk_service.BROWSER_PROFILE_DIRS", [snap]):
                KioskService.clean_stale_singleton_locks()
            self.assertFalse((snap / "SingletonCookie").exists())


if __name__ == "__main__":
    unittest.main()


import http.client
import threading
from http.server import ThreadingHTTPServer

from core import kiosk_bridge


class BridgeServerTests(unittest.TestCase):
    TOKEN = "t" * 43

    def setUp(self):
        self.calls = []

        def handle_action(action):
            self.calls.append(action)
            return {"status": "ok", "action": action}

        handler = kiosk_bridge.make_handler(self.TOKEN, handle_action)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _post(self, body, headers=None, method="POST", path="/action"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        base = {"Content-Type": "application/json", "X-SUIT-Token": self.TOKEN,
                "Origin": kiosk_bridge.ALLOWED_ORIGIN}
        base.update(headers or {})
        base = {k: v for k, v in base.items() if v is not None}
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=base)
        resp = conn.getresponse()
        data = json.loads(resp.read() or b"{}")
        conn.close()
        return resp.status, data

    def test_valid_request_runs_action(self):
        status, data = self._post({"action": "ping"})
        self.assertEqual(status, 200)
        self.assertEqual(self.calls, ["ping"])

    def test_missing_or_wrong_token_is_rejected(self):
        self.assertEqual(self._post({"action": "poweroff"}, {"X-SUIT-Token": None})[0], 401)
        self.assertEqual(self._post({"action": "poweroff"}, {"X-SUIT-Token": "x" * 43})[0], 401)
        self.assertEqual(self.calls, [])

    def test_web_page_origin_is_rejected_even_with_token(self):
        status, _ = self._post({"action": "poweroff"}, {"Origin": "https://evil.example"})
        self.assertEqual(status, 403)
        self.assertEqual(self.calls, [])

    def test_cors_preflight_is_never_approved(self):
        status, _ = self._post(None, method="OPTIONS")
        self.assertEqual(status, 405)

    def test_simple_cross_site_form_post_is_rejected(self):
        status, _ = self._post({"action": "reboot"}, {"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        self.assertEqual(self.calls, [])

    def test_unknown_action_is_rejected(self):
        status, _ = self._post({"action": "rm -rf /"})
        self.assertEqual(status, 400)
        self.assertEqual(self.calls, [])

    def test_binds_loopback_only(self):
        self.assertEqual(kiosk_bridge.BRIDGE_HOST, "127.0.0.1")


class BridgeConfigTests(unittest.TestCase):
    def test_config_is_private_and_stable(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "suit" / "kiosk_bridge.json"
            first = kiosk_bridge.load_or_create_config(path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertGreaterEqual(len(first["token"]), 32)
            self.assertEqual(kiosk_bridge.load_or_create_config(path), first)

    def test_bridge_extension_has_token_but_no_native_host(self):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "ext"
            cfg_path = Path(td) / "kiosk_bridge.json"
            with patch.object(kiosk_bridge, "CONFIG_PATH", cfg_path):
                KioskService.prepare_bridge_extension(target=dest)
            self.assertTrue((dest / "manifest.json").is_file())
            self.assertFalse((dest / "host").exists())
            cfg = json.loads((dest / "bridge_config.json").read_text())
            self.assertEqual(cfg["url"], f"http://127.0.0.1:{kiosk_bridge.BRIDGE_PORT}/action")
            self.assertEqual((dest / "bridge_config.json").stat().st_mode & 0o777, 0o600)
            manifest = json.loads((dest / "manifest.json").read_text())
            self.assertIn("http://127.0.0.1/*", manifest["host_permissions"])

    def test_bridge_config_is_not_web_accessible(self):
        manifest = json.loads((KioskService.EXTENSION_DIR / "manifest.json").read_text())
        exposed = [r for entry in manifest.get("web_accessible_resources", []) for r in entry.get("resources", [])]
        self.assertFalse(any("bridge_config" in r or r == "*" for r in exposed))


class BridgeModeSelectionTests(unittest.TestCase):
    @patch("core.kiosk_service.distribution_id", return_value="ubuntu")
    def test_ubuntu_loads_bridge_extension(self, _d):
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td)
            with patch.object(KioskService, "prepare_bridge_extension", return_value=dest):
                flags = KioskService.get_kiosk_flags(enable_controls=True, browser="chromium")
        self.assertIn(f"--load-extension={dest.resolve()}", flags)

    @patch("core.kiosk_service.distribution_id", return_value="fedora")
    @patch.object(KioskService, "is_snap_browser", return_value=False)
    def test_fedora_keeps_native_messaging(self, _s, _d):
        self.assertFalse(KioskService.uses_bridge("chromium"))
        self.assertTrue(KioskService.supports_permanent_extension())

    def test_launcher_starts_bridge_only_when_configured(self):
        with tempfile.TemporaryDirectory() as td, patch.object(Path, "home", return_value=Path(td)):
            script = KioskService.ensure_launcher_script().read_text()
        self.assertIn('[ -f "$HOME/.config/suit/kiosk_bridge.json" ]', script)
        self.assertIn(str(Path(kiosk_bridge.__file__).resolve()), script)
