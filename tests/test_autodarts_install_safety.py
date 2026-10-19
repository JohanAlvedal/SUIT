"""Non-destructive tests: Autodarts installation must never silently replace a working install."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import autodarts_service as ads


def _done(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


class DetectExistingInstallationTests(unittest.TestCase):
    def test_reports_legacy_system_units(self):
        with tempfile.TemporaryDirectory() as td:
            unit_dir = Path(td)
            (unit_dir / "autodarts.service").write_text("[Unit]\n")
            with patch.object(ads.subprocess, "run", return_value=_done(out="active\n")), \
                 patch.object(ads, "get_autodarts_cli_binary", return_value=None):
                info = ads.detect_existing_installation(system_unit_dir=unit_dir)
        self.assertEqual(info["system_units"], [str(unit_dir / "autodarts.service")])
        self.assertTrue(info["system_active"])

    def test_no_system_units_skips_systemctl(self):
        with tempfile.TemporaryDirectory() as td, \
             patch.object(ads.subprocess, "run") as run, \
             patch.object(ads, "get_autodarts_cli_binary", return_value=None):
            info = ads.detect_existing_installation(system_unit_dir=Path(td))
        self.assertEqual(info["system_units"], [])
        self.assertFalse(info["system_active"])
        run.assert_not_called()


class InstallRefusesImplicitReplacementTests(unittest.TestCase):
    @patch.object(ads, "_run_official_installer")
    @patch.object(ads, "_remove_legacy_system_service")
    @patch.object(ads, "detect_existing_installation")
    def test_refuses_without_confirmation(self, detect, remove, installer):
        detect.return_value = {"system_units": ["/etc/systemd/system/autodarts.service"],
                               "system_active": True, "user_unit": False, "binary": ""}
        ok, msg = ads.install_autodarts()
        self.assertFalse(ok)
        self.assertIn("Confirm replacement", msg)
        remove.assert_not_called()
        installer.assert_not_called()

    @patch.object(ads, "_run_official_installer")
    @patch.object(ads, "_remove_legacy_system_service", return_value=(False, "refused"))
    @patch.object(ads, "backup_unit_files", return_value=Path("/tmp/bak"))
    @patch.object(ads, "read_cam_config", return_value={"cams": []})
    @patch.object(ads, "read_stored_auth", return_value=("", ""))
    @patch.object(ads, "detect_existing_installation")
    def test_aborts_when_authorization_refused(self, detect, *_mocks):
        installer = _mocks[-1]
        detect.return_value = {"system_units": ["/etc/systemd/system/autodarts.service"],
                               "system_active": True, "user_unit": False, "binary": ""}
        ok, msg = ads.install_autodarts(replace_system_service=True)
        self.assertFalse(ok)
        self.assertIn("Nothing else was changed", msg)
        installer.assert_not_called()

    @patch.object(ads, "_run_official_installer")
    @patch.object(ads, "_remove_legacy_system_service")
    @patch.object(ads, "backup_unit_files", side_effect=OSError("disk full"))
    @patch.object(ads, "read_cam_config", return_value={"cams": []})
    @patch.object(ads, "read_stored_auth", return_value=("", ""))
    @patch.object(ads, "detect_existing_installation")
    def test_aborts_when_backup_fails(self, detect, _auth, _cam, _backup, remove, installer):
        detect.return_value = {"system_units": ["/etc/systemd/system/autodarts.service"],
                               "system_active": False, "user_unit": False, "binary": ""}
        ok, msg = ads.install_autodarts(replace_system_service=True)
        self.assertFalse(ok)
        self.assertIn("nothing changed", msg)
        remove.assert_not_called()
        installer.assert_not_called()


class BackupTests(unittest.TestCase):
    def test_copies_unit_files(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            unit = Path(src) / "autodarts.service"
            unit.write_text("ExecStart=/opt/autodarts\n")
            target = ads.backup_unit_files([str(unit)], backup_root=Path(dst))
            self.assertEqual((target / "autodarts.service").read_text(), "ExecStart=/opt/autodarts\n")


class LegacyRemovalTests(unittest.TestCase):
    @patch("core.admin.admin_prefix", return_value=["pkexec"])
    def test_ignores_paths_outside_allowlist(self, _prefix):
        with patch.object(ads.subprocess, "run") as run:
            ok, _ = ads._remove_legacy_system_service(["/etc/passwd"])
        self.assertTrue(ok)
        run.assert_not_called()

    @patch("core.admin.admin_prefix", return_value=["pkexec"])
    def test_single_authorized_call_with_quoted_paths(self, _prefix):
        path = str(ads.SYSTEM_UNIT_DIR / "autodarts.service")
        with patch.object(ads.subprocess, "run", return_value=_done()) as run, \
             patch.object(ads.Path, "exists", return_value=False):
            ok, _ = ads._remove_legacy_system_service([path])
        self.assertTrue(ok)
        self.assertEqual(run.call_count, 1)
        argv = run.call_args.args[0]
        self.assertEqual(argv[:3], ["pkexec", "/bin/bash", "-c"])
        self.assertIn("systemctl disable --now autodarts.service", argv[3])
        self.assertIn(f"rm -f {path}", argv[3])

    @patch("core.admin.admin_prefix", return_value=["pkexec"])
    def test_reports_refused_authorization(self, _prefix):
        path = str(ads.SYSTEM_UNIT_DIR / "autodarts.service")
        with patch.object(ads.subprocess, "run", return_value=_done(rc=126, err="Not authorized")):
            ok, msg = ads._remove_legacy_system_service([path])
        self.assertFalse(ok)
        self.assertIn("Not authorized", msg)


class InstallerDownloadTests(unittest.TestCase):
    def test_rejects_plain_http(self):
        with patch.object(ads.subprocess, "run") as run:
            ok, msg = ads._run_official_installer("http://autodarts.sh")
        self.assertFalse(ok)
        self.assertIn("non-HTTPS", msg)
        run.assert_not_called()

    def test_failed_download_never_executes_bash(self):
        with patch.object(ads.subprocess, "run", return_value=_done(rc=22, err="404")) as run:
            ok, _ = ads._run_official_installer("https://autodarts.sh")
        self.assertFalse(ok)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][0], "curl")
        self.assertIn("=https", run.call_args.args[0])


class GracefulStopTests(unittest.TestCase):
    def test_sigterm_before_sigkill_and_no_kill_if_exited(self):
        calls = []

        def fake_run(argv, **_kw):
            calls.append(argv)
            if argv[0] == "pgrep":
                return _done(rc=1)  # process already gone
            return _done()

        with patch.object(ads.subprocess, "run", side_effect=fake_run):
            ads._stop_running_autodarts(grace_seconds=1)
        self.assertIn(["pkill", "-TERM", "-x", "autodarts"], calls)
        self.assertNotIn(["pkill", "-KILL", "-x", "autodarts"], calls)


if __name__ == "__main__":
    unittest.main()
