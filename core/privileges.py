"""Administrator authorization checks.

SUIT must never grant unrestricted passwordless sudo or a global Polkit
exemption automatically. Per-operation authorization is handled separately.
"""
import subprocess
from core.logger import get_logger

logger = get_logger("privileges")


def check_sudo_privileges() -> bool:
    try:
        return subprocess.run(
            ["sudo", "-n", "true"], capture_output=True, timeout=5
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def setup_sudoers_pkexec(user: str | None = None) -> tuple[bool, str]:
    return (False,
            "Unrestricted passwordless sudo setup has been removed for security. "
            "Authorize individual system actions as needed.")
