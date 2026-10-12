"""Non-destructive Ubuntu compatibility and update-safety checks."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import package_manager
from core.debloat_service import DebloatService
from core.privileges import setup_sudoers_pkexec
from core.update_service import UpdateService


class UbuntuSupportTests(unittest.TestCase):
    def test_detect_ubuntu(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "os-release"
            path.write_text('NAME="Ubuntu"\nID=ubuntu\nVERSION_ID="24.04"\n')
            self.assertEqual(package_manager.distribution_id(path), "ubuntu")

    @patch("core.package_manager.distribution_id", return_value="ubuntu")
    @patch("core.package_manager.shutil.which", return_value="/usr/bin/pkexec")
    @patch("core.package_manager.subprocess.run")
    def test_install_uses_apt_and_per_action_authorization(self, run, which, distro):
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        ok, _ = package_manager.install_packages(["seahorse"])
        self.assertTrue(ok)
        args = run.call_args.args[0]
        self.assertEqual(args[:4], ["pkexec", "apt-get", "install", "-y"])
        self.assertIn("seahorse", args)
        self.assertNotIn("dnf", args)

    @patch("core.package_manager.distribution_id", return_value="ubuntu")
    @patch("core.package_manager.shutil.which", return_value=None)
    def test_no_silent_root_grant_when_auth_unavailable(self, which, distro):
        ok, detail = package_manager.install_packages(["seahorse"])
        self.assertFalse(ok)
        self.assertIn("authorization", detail.lower())

    @patch("core.debloat_service.distribution_id", return_value="ubuntu")
    def test_ubuntu_debloat_refuses_package_removal(self, distro):
        ok, detail = DebloatService.debloat_packages(["firefox"])
        self.assertFalse(ok)
        self.assertIn("disabled", detail)

    def test_unrestricted_sudo_not_granted(self):
        ok, msg = setup_sudoers_pkexec("testuser")
        self.assertFalse(ok)
        self.assertIn("removed", msg)

    @patch.object(UpdateService, "ensure_dependencies")
    @patch.object(UpdateService, "_current_branch", return_value="feature/ubuntu-support")
    @patch("core.update_service.subprocess.run")
    def test_update_is_fast_forward_only_on_current_branch(self, run, current, dependencies):
        run.return_value = subprocess.CompletedProcess([], 0, "", "")
        with tempfile.TemporaryDirectory() as td:
            ok, _ = UpdateService.apply_update(Path(td))
        self.assertTrue(ok)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands, [
            ["git", "fetch", "origin", "feature/ubuntu-support"],
            ["git", "pull", "--ff-only", "origin", "feature/ubuntu-support"],
        ])
        self.assertNotIn("reset", str(commands))

    @patch.object(UpdateService, "_current_branch", return_value="feature/ubuntu-support")
    @patch("core.update_service.subprocess.run")
    def test_failed_pull_never_hard_resets(self, run, current):
        run.side_effect = [
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 1, "", "Diverged"),
        ]
        with tempfile.TemporaryDirectory() as td:
            ok, msg = UpdateService.apply_update(Path(td))
        self.assertFalse(ok)
        self.assertIn("without changing local files", msg)
        self.assertEqual(run.call_count, 2)

    @patch.object(UpdateService, "_current_branch", return_value="feature/ubuntu-support")
    @patch("core.update_service.subprocess.run")
    def test_check_update_counts_correct_branch(self, run, current):
        run.side_effect = [
            subprocess.CompletedProcess([], 0, "", ""),      # fetch
            subprocess.CompletedProcess([], 0, "abc123", ""),  # local sha
            subprocess.CompletedProcess([], 0, "def456", ""),  # remote sha
            subprocess.CompletedProcess([], 0, "2", ""),       # rev-list
            subprocess.CompletedProcess([], 0, "New update", ""),  # log
        ]
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".git").mkdir()
            status = UpdateService.check_update(Path(td))
        self.assertTrue(status["has_update"])
        self.assertEqual(status["commits_behind"], 2)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn("HEAD..origin/feature/ubuntu-support", commands[3])


if __name__ == "__main__":
    unittest.main()
