"""Restore paths on Ubuntu: helper, touch calibration, defaults, keyring, uninstall."""
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent


def _stub_gi():
    """display_service/systemd_service import gi; CI may not have PyGObject."""
    try:
        import gi  # noqa: F401
        from gi.repository import Gio  # noqa: F401
    except Exception:
        gi = types.ModuleType("gi")
        gi.require_version = lambda *a, **k: None
        repo = types.ModuleType("gi.repository")
        repo.Gio = MagicMock()
        repo.GLib = MagicMock()
        gi.repository = repo
        sys.modules["gi"] = gi
        sys.modules["gi.repository"] = repo


_stub_gi()

from core import suit_helper  # noqa: E402
from core import admin  # noqa: E402
from core.display_service import DisplayService  # noqa: E402
from core.desktop_service import DesktopService, TOUCH_KEYS  # noqa: E402
from core.keyring_service import KeyringService  # noqa: E402
from core.power_service import PowerService, POWER_KEYS  # noqa: E402


class HelperValidationTests(unittest.TestCase):
    def test_rule_text_normalizes_matrix(self):
        rule = suit_helper.udev_rule_text("ILITEK Touch", "0 1 0 -1 0 1 0 0 1")
        self.assertIn('ATTRS{name}=="ILITEK Touch"', rule)
        self.assertIn('LIBINPUT_CALIBRATION_MATRIX}="0 1 0 -1 0 1 0 0 1"', rule)

    def test_rejects_injection_in_name_and_matrix(self):
        with self.assertRaises(suit_helper.HelperError):
            suit_helper.udev_rule_text('x", RUN+="/bin/sh', "1 0 0 0 1 0 0 0 1")
        with self.assertRaises(suit_helper.HelperError):
            suit_helper.validate_matrix("1 0 0 0 1 0 0 0")
        with self.assertRaises(suit_helper.HelperError):
            suit_helper.validate_matrix("1 0 0 0 1 0 0 0 $(id)")

    def test_rejects_bad_busid(self):
        with self.assertRaises(suit_helper.HelperError):
            suit_helper.validate_busid("../../power")

    def test_unit_verb_only_autodarts(self):
        args = suit_helper.build_parser().parse_args(["unit", "stop", "ssh.service"])
        with self.assertRaises(suit_helper.HelperError):
            suit_helper.cmd_unit(args)
        args = suit_helper.build_parser().parse_args(["unit", "poweroff", "autodarts.service"])
        with self.assertRaises(suit_helper.HelperError):
            suit_helper.cmd_unit(args)

    def test_gdm_config_generation(self):
        out = suit_helper.generate_gdm_config("[daemon]\nWaylandEnable=false\n", True, "darts")
        self.assertIn("[daemon]\nAutomaticLoginEnable=True\nAutomaticLogin=darts\n", out)
        self.assertIn("WaylandEnable=false", out)
        off = suit_helper.generate_gdm_config(out, False, "")
        self.assertIn("AutomaticLoginEnable=False", off)
        self.assertNotIn("AutomaticLogin=darts", off)

    def test_version_runs_without_root(self):
        res = subprocess.run([sys.executable, str(ROOT / "core" / "suit_helper.py"), "version"],
                             capture_output=True, text=True)
        self.assertEqual(res.stdout.strip(), suit_helper.HELPER_VERSION)

    def test_policy_points_at_installed_helper(self):
        policy = (ROOT / "assets" / "polkit" / "se.alvedal.suit.helper.policy").read_text()
        self.assertIn("/usr/libexec/suit/suit-helper", policy)
        self.assertIn("<allow_active>auth_admin_keep</allow_active>", policy)
        self.assertIn("<allow_any>no</allow_any>", policy)


class RunHelperTests(unittest.TestCase):
    @patch("core.admin._passwordless_sudo", return_value=False)
    @patch("core.admin.subprocess.run")
    def test_non_interactive_never_prompts(self, run, sudo):
        ok, msg = admin.run_helper(["touch-clear"], interactive=False)
        self.assertFalse(ok)
        run.assert_not_called()

    @patch("core.admin.installed_helper_current", return_value=False)
    @patch("core.admin._passwordless_sudo", return_value=False)
    @patch("core.admin.shutil.which", return_value="/usr/bin/pkexec")
    def test_fallback_runs_repo_helper_in_one_pkexec(self, which, sudo, current):
        cmd = admin.helper_command(["touch-clear"])
        self.assertEqual(cmd[0], "pkexec")
        self.assertEqual(cmd[2:4], ["-I", str(ROOT / "core" / "suit_helper.py")])
        self.assertEqual(cmd[-1], "touch-clear")

    @patch("core.admin.installed_helper_current", return_value=True)
    @patch("core.admin._passwordless_sudo", return_value=False)
    @patch("core.admin.shutil.which", return_value="/usr/bin/pkexec")
    def test_prefers_installed_helper(self, which, sudo, current):
        self.assertEqual(admin.helper_command(["logind-clear"]),
                         ["pkexec", "/usr/libexec/suit/suit-helper", "logind-clear"])


class TouchRestoreTests(unittest.TestCase):
    def test_clear_without_rule_needs_no_privileges(self):
        with tempfile.TemporaryDirectory() as td, patch("core.display_service.run_helper") as helper:
            ok = DisplayService.write_udev_rule(None, None, rule_path=Path(td) / "99-suit-touch.rules")
        self.assertTrue(ok)
        helper.assert_not_called()

    def test_same_rule_is_not_rewritten(self):
        with tempfile.TemporaryDirectory() as td, patch("core.display_service.run_helper") as helper, \
                patch.object(DisplayService, "_resolve_touch_device_name", side_effect=lambda n: n):
            rule = Path(td) / "99-suit-touch.rules"
            rule.write_text(suit_helper.udev_rule_text("Touch", "0 1 0 -1 0 1 0 0 1"))
            ok = DisplayService.write_udev_rule("Touch", "0 1 0 -1 0 1 0 0 1", rule_path=rule)
        self.assertTrue(ok)
        helper.assert_not_called()

    def test_clear_and_rebind_is_one_privileged_call(self):
        with tempfile.TemporaryDirectory() as td, \
                patch("core.display_service.run_helper", return_value=(True, "ok")) as helper, \
                patch.object(DisplayService, "find_usb_busid", return_value="1-4"):
            rule = Path(td) / "99-suit-touch.rules"
            rule.write_text("old")
            DisplayService.write_udev_rule(None, None, rebind_device="Touch", rule_path=rule)
        helper.assert_called_once()
        self.assertEqual(helper.call_args.args[0], ["touch-clear", "--rebind", "1-4"])

    def test_no_privileged_step_runs_shell_tee(self):
        source = (ROOT / "core" / "display_service.py").read_text()
        self.assertNotIn("admin_prefix", source)
        self.assertNotIn("/sys/bus/usb/drivers/usb/unbind", source)


class DefaultsRestoreTests(unittest.TestCase):
    @patch("core.desktop_service.subprocess.run")
    def test_touch_off_resets_to_distro_defaults(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "@as []", "")
        with tempfile.TemporaryDirectory() as td:
            DesktopService.set_touch_scaling(False, target_dir=Path(td) / "touch-scaling@suit",
                                             gtk4_path=Path(td) / "g4.css", gtk3_path=Path(td) / "g3.css")
        calls = [c.args[0] for c in run.call_args_list]
        for schema, key in TOUCH_KEYS:
            self.assertIn(["gsettings", "reset", schema, key], calls)
        self.assertNotIn(["gsettings", "set", "org.gnome.desktop.wm.preferences", "button-layout", "'appmenu:close'"], calls)

    @patch("core.power_service.subprocess.run")
    def test_display_sleep_restore_uses_reset(self, run):
        PowerService.set_power_and_sleep(disable_sleep=False)
        calls = [c.args[0] for c in run.call_args_list]
        self.assertEqual(calls, [["gsettings", "reset", s, k] for s, k in POWER_KEYS])

    @patch("core.power_service.shutil.which", return_value="/usr/bin/powerprofilesctl")
    @patch("core.power_service.subprocess.run")
    def test_profile_restore_is_balanced(self, run, which):
        ok, _ = PowerService.restore_default_profile()
        self.assertTrue(ok)
        self.assertEqual(run.call_args.args[0], ["powerprofilesctl", "set", "balanced"])

    @patch("core.power_service.shutil.which", return_value="/usr/bin/powerprofilesctl")
    @patch("core.power_service.subprocess.run")
    def test_available_profiles_parsed(self, run, which):
        run.return_value = subprocess.CompletedProcess([], 0,
            "  balanced:\n    CpuDriver:\tamd_pstate\n    PlatformDriver:\tplatform_profile\n\n* power-saver:\n    CpuDriver:\tamd_pstate\n", "")
        self.assertEqual(PowerService.available_power_profiles(), ["balanced", "power-saver"])

    @patch("core.desktop_service.subprocess.run")
    def test_visuals_restore_without_backup_resets(self, run):
        with tempfile.TemporaryDirectory() as td, \
                patch("core.desktop_service.VISUALS_BACKUP_PATH", Path(td) / "none.json"), \
                patch("core.desktop_service.SUIT_WALLPAPER_INSTALLED", Path(td) / "wp.png"):
            ok, _ = DesktopService.restore_desktop_visuals()
        self.assertTrue(ok)
        calls = [c.args[0] for c in run.call_args_list]
        self.assertIn(["gsettings", "reset", "org.gnome.desktop.interface", "color-scheme"], calls)


class KeyringBackupTests(unittest.TestCase):
    def test_second_reset_keeps_original_backup_and_restore_works(self):
        with tempfile.TemporaryDirectory() as td, patch("core.keyring_service.subprocess.run"):
            kdir = Path(td)
            ring = kdir / "login.keyring"
            ring.write_text("[keyring]\nsalt=abc\nORIGINAL\n")
            KeyringService.reset_keyring_to_blank(ring)
            KeyringService.reset_keyring_to_blank(ring)
            backups = KeyringService.list_keyring_backups(kdir)
            self.assertEqual(len(backups), 2)
            self.assertTrue(any("ORIGINAL" in b.read_text() for b in backups))
            original = next(b for b in backups if "ORIGINAL" in b.read_text())
            ok, _ = KeyringService.restore_keyring_backup(original, keyring_dir=kdir)
            self.assertTrue(ok)
            self.assertIn("ORIGINAL", ring.read_text())


class UninstallTests(unittest.TestCase):
    def test_scripts_parse(self):
        for script in ("uninstall.sh", "install.sh"):
            subprocess.run(["bash", "-n", str(ROOT / script)], check=True)

    def test_uninstall_restores_and_asks(self):
        text = (ROOT / "uninstall.sh").read_text()
        self.assertNotIn("SUIT for Fedora", text)
        self.assertIn("restore_desktop_visuals", text)
        self.assertIn("set_touch_scaling(False)", text)
        self.assertIn("/etc/gdm3/custom.conf", text)
        self.assertIn("se.alvedal.suit.helper.policy", text)

    def test_install_ships_helper(self):
        text = (ROOT / "install.sh").read_text()
        self.assertIn("/usr/libexec/suit/suit-helper", text)


if __name__ == "__main__":
    unittest.main()
