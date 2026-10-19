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
