"""Per-operation administrator authorization without passwordless sudo setup."""

import shutil
import subprocess
import sys
from pathlib import Path

INSTALLED_HELPER = Path("/usr/libexec/suit/suit-helper")
REPO_HELPER = Path(__file__).resolve().parent / "suit_helper.py"


def _passwordless_sudo() -> bool:
    try:
        return subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=4).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def admin_prefix() -> list[str]:
    """Use existing passwordless sudo, otherwise request desktop Polkit auth.

    Running in a GNOME session provides the pkexec authentication dialog.
    This does not create a sudoers rule or a permanent Polkit exception.
    """
    if _passwordless_sudo():
        return ["sudo", "-n"]
    if shutil.which("pkexec"):
        return ["pkexec"]
    return ["sudo", "-n"]  # Fail closed when no graphical agent is available.


def _repo_helper_version() -> str:
    for line in REPO_HELPER.read_text(encoding="utf-8").splitlines():
        if line.startswith("HELPER_VERSION"):
            return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def installed_helper_current() -> bool:
    """True if install.sh put a root-owned helper of the current version in place."""
    if not INSTALLED_HELPER.exists():
        return False
    try:
        res = subprocess.run([str(INSTALLED_HELPER), "version"], capture_output=True, text=True, timeout=5)
        return res.returncode == 0 and res.stdout.strip() == _repo_helper_version()
    except (OSError, subprocess.TimeoutExpired):
        return False


def helper_command(args: list[str]) -> list[str]:
    """Command line that runs one helper verb as root.

    Preferred: the installed helper via its own polkit action (one prompt,
    remembered for a few minutes). Fallback before install.sh has been rerun:
    the checkout's copy through generic pkexec - still one prompt per whole
    operation instead of one per step.
    """
    if installed_helper_current():
        target = [str(INSTALLED_HELPER)]
    else:
        target = [sys.executable, "-I", str(REPO_HELPER)]
    if _passwordless_sudo():
        return ["sudo", "-n", *target, *args]
    if shutil.which("pkexec"):
        return ["pkexec", *target, *args]
    return ["sudo", "-n", *target, *args]


def run_helper(args: list[str], interactive: bool = True, timeout: int = 120) -> tuple[bool, str]:
    """Run a privileged helper verb. interactive=False never shows a password
    dialog (used at login/boot, where a dialog would hide behind the kiosk)."""
    if not interactive and not _passwordless_sudo():
        return False, "administrator authorization needed (skipped without a dialog)"
    try:
        res = subprocess.run(helper_command(args), capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if res.returncode in (126, 127) and not res.stderr.strip().startswith("suit-helper"):
        return False, "Authorization was cancelled or denied."
    msg = (res.stdout.strip() or res.stderr.strip()).splitlines()
    return res.returncode == 0, (msg[-1] if msg else "")
