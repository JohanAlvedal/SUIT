"""Per-operation administrator authorization without passwordless sudo setup."""

import shutil
import subprocess


def admin_prefix() -> list[str]:
    """Use existing passwordless sudo, otherwise request desktop Polkit auth.

    Running in a GNOME session provides the pkexec authentication dialog.
    This does not create a sudoers rule or a permanent Polkit exception.
    """
    try:
        status = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=4)
        if status.returncode == 0:
            return ["sudo", "-n"]
    except (OSError, subprocess.TimeoutExpired):
        pass
    if shutil.which("pkexec"):
        return ["pkexec"]
    return ["sudo", "-n"]  # Fail closed when no graphical agent is available.
