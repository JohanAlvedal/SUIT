"""Minimal, distribution-aware system package operations.

Installing GUI applications must not silently grant passwordless administrator
access. A Polkit authentication dialog is used when possible; otherwise the
operation fails with an explanatory message.
"""

import os
import shutil
import subprocess
from pathlib import Path

from core.logger import get_logger

logger = get_logger("packages")


def distribution_id(os_release: Path = Path("/etc/os-release")) -> str:
    try:
        for line in os_release.read_text(encoding="utf-8").splitlines():
            if line.startswith("ID="):
                return line.partition("=")[2].strip().strip('"').strip("'").lower()
    except OSError:
        pass
    return "unknown"


def package_tool() -> str | None:
    distro = distribution_id()
    if distro == "ubuntu":
        return "apt-get"
    if distro == "fedora":
        return "dnf"
    return None


def install_packages(packages: list[str]) -> tuple[bool, str]:
    """Install named system packages after authorization; never via shell."""
    if not packages:
        return True, "No packages requested."
    tool = package_tool()
    if not tool:
        return False, "Unsupported Linux distribution (expected Ubuntu or Fedora)."

    command = [tool, "install", "-y"]
    if tool == "dnf":
        command += ["--setopt=install_weak_deps=False"]
    else:
        command += ["--no-install-recommends"]
    command += packages

    # sudo -n never prompts for a password from a headless GUI callback. Try
    # the desktop authentication agent instead of modifying sudoers.
    if shutil.which("pkexec"):
        command = ["pkexec", *command]
    elif shutil.which("sudo"):
        command = ["sudo", "-n", *command]
    else:
        return False, "No administrator authorization tool (pkexec/sudo) found."

    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=300)
        if proc.returncode == 0:
            return True, f"Installed: {', '.join(packages)}"
        detail = (proc.stderr or proc.stdout).strip()
        return False, f"Package installation failed: {detail or proc.returncode}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("Package installation failed: %s", exc)
        return False, f"Package installation failed: {exc}"
