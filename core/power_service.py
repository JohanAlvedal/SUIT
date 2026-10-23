import subprocess
import shutil
import re
from core.package_manager import distribution_id
from core.admin import run_helper
from pathlib import Path
from core.logger import get_logger

logger = get_logger("power")

DEFAULT_GDM_CONFIG = Path("/etc/gdm3/custom.conf") if distribution_id() == "ubuntu" else Path("/etc/gdm/custom.conf")
LEGACY_LOGIND_DROPIN = Path("/etc/systemd/logind.conf.d/99-suit-power.conf")

# GNOME keys SUIT changes for "Display Always On". Restoring uses
# `gsettings reset` so each distro gets its own default back (Ubuntu and
# Fedora differ, e.g. Ubuntu's idle-delay is 300, not 900).
POWER_KEYS = [
    ("org.gnome.desktop.session", "idle-delay"),
    ("org.gnome.settings-daemon.plugins.power", "idle-dim"),
    ("org.gnome.settings-daemon.plugins.power", "sleep-inactive-ac-type"),
    ("org.gnome.settings-daemon.plugins.power", "sleep-inactive-battery-type"),
    ("org.gnome.settings-daemon.plugins.power", "power-button-action"),
    ("org.gnome.desktop.screensaver", "lock-enabled"),
]


class PowerService:
    @staticmethod
    def set_screen_blanking(disable_blanking: bool) -> bool:
        return PowerService.set_power_and_sleep(disable_sleep=disable_blanking)

    @staticmethod
    def is_blanking_disabled() -> bool:
        return PowerService.is_power_and_sleep_optimized()

    @staticmethod
    def available_power_profiles() -> list[str]:
        """Profiles power-profiles-daemon offers on this CPU ("performance" is
        missing on many machines)."""
        if not shutil.which("powerprofilesctl"):
            return []
        try:
            res = subprocess.run(["powerprofilesctl", "list"], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return []
        return re.findall(r"^[ *]*([a-z-]+):\s*$", res.stdout, flags=re.MULTILINE)

    @staticmethod
    def is_performance_profile_active(profile: str = "throughput-performance") -> bool:
        try:
            if distribution_id() == "ubuntu" and shutil.which("powerprofilesctl"):
                res = subprocess.run(["powerprofilesctl", "get"], capture_output=True, text=True)
                return res.returncode == 0 and res.stdout.strip() == "performance"
            res = subprocess.run(["tuned-adm", "active"], capture_output=True, text=True)
            return profile in res.stdout
        except Exception:
            logger.debug("Failed checking tuned-adm active profile")
            return False

    @classmethod
    def set_performance_profile(cls, profile: str = "throughput-performance") -> bool:
        try:
            if distribution_id() == "ubuntu" and shutil.which("powerprofilesctl"):
                available = cls.available_power_profiles()
                if available and "performance" not in available:
                    logger.warning("CPU offers no 'performance' profile (available: %s)", ", ".join(available))
                    return False
                subprocess.run(["powerprofilesctl", "set", "performance"], check=True, capture_output=True)
            else:
                subprocess.run(["sudo", "-n", "tuned-adm", "profile", profile], check=True, capture_output=True)
            logger.info("Set system performance profile")
            return True
        except Exception:
            logger.exception(f"Failed setting performance profile to {profile}")
            return False

    @classmethod
    def restore_default_profile(cls) -> tuple[bool, str]:
        """Back to the distro default: 'balanced' (Ubuntu) / tuned's recommendation (Fedora)."""
        try:
            if shutil.which("powerprofilesctl"):
                subprocess.run(["powerprofilesctl", "set", "balanced"], check=True, capture_output=True)
                return True, "Power profile restored to Balanced."
            if shutil.which("tuned-adm"):
                res = subprocess.run(["tuned-adm", "recommend"], capture_output=True, text=True)
                rec = res.stdout.strip() or "balanced"
                subprocess.run(["sudo", "-n", "tuned-adm", "profile", rec], check=True, capture_output=True)
                return True, f"Power profile restored to {rec}."
        except Exception as exc:
            logger.exception("Failed restoring default power profile")
            return False, f"Could not restore power profile: {exc}"
        return False, "No power profile tool found."

    @staticmethod
    def is_power_and_sleep_optimized() -> bool:
        try:
            res1 = subprocess.run(["gsettings", "get", "org.gnome.desktop.session", "idle-delay"], capture_output=True, text=True)
            if not ("uint32 0" in res1.stdout or res1.stdout.strip() == "0"):
                return False
            res2 = subprocess.run(["gsettings", "get", "org.gnome.settings-daemon.plugins.power", "idle-dim"], capture_output=True, text=True)
            if "false" not in res2.stdout.lower():
                return False
            res3 = subprocess.run(["gsettings", "get", "org.gnome.settings-daemon.plugins.power", "sleep-inactive-ac-type"], capture_output=True, text=True)
            if "nothing" not in res3.stdout.lower():
                return False
            return True
        except Exception:
            logger.debug("Failed checking GNOME power and sleep settings")
            return False

    @staticmethod
    def set_power_and_sleep(disable_sleep: bool = True) -> bool:
        try:
            if disable_sleep:
                subprocess.run(["gsettings", "set", "org.gnome.desktop.session", "idle-delay", "0"], check=True)
                subprocess.run(["gsettings", "set", "org.gnome.settings-daemon.plugins.power", "idle-dim", "false"], check=True)
                subprocess.run(["gsettings", "set", "org.gnome.settings-daemon.plugins.power", "sleep-inactive-ac-type", "'nothing'"], check=True)
                subprocess.run(["gsettings", "set", "org.gnome.settings-daemon.plugins.power", "sleep-inactive-battery-type", "'nothing'"], check=True)
                subprocess.run(["gsettings", "set", "org.gnome.settings-daemon.plugins.power", "power-button-action", "'interactive'"], check=True)
                # No lock screen popping up over the kiosk after idle/resume.
                subprocess.run(["gsettings", "set", "org.gnome.desktop.screensaver", "lock-enabled", "false"], check=False)
                # Old SUIT versions wrote this drop-in; only ask for rights if it exists.
                if LEGACY_LOGIND_DROPIN.exists():
                    run_helper(["logind-clear"])
            else:
                for schema, key in POWER_KEYS:
                    subprocess.run(["gsettings", "reset", schema, key], check=True)
            logger.info(f"Configured power and sleep settings: disable_sleep={disable_sleep}")
            return True
        except Exception:
            logger.exception("Failed configuring power and sleep settings")
            return False

    @staticmethod
    def generate_gdm_config(config_path: Path, enabled: bool, user: str) -> str:
        content = config_path.read_text(encoding="utf-8") if config_path.exists() else "[daemon]\n"
        lines = [
            line for line in content.splitlines()
            if not line.strip().startswith("AutomaticLoginEnable=") and not line.strip().startswith("AutomaticLogin=")
        ]
        
        daemon_idx = -1
        for i, line in enumerate(lines):
            if line.strip() == "[daemon]":
                daemon_idx = i
                break
                
        if enabled:
            insert_lines = [
                "AutomaticLoginEnable=True",
                f"AutomaticLogin={user}"
            ]
        else:
            insert_lines = [
                "AutomaticLoginEnable=False"
            ]
            
        if daemon_idx != -1:
            lines = lines[:daemon_idx + 1] + insert_lines + lines[daemon_idx + 1:]
        else:
            lines = ["[daemon]"] + insert_lines + [""] + lines
            
        return "\n".join(lines) + "\n"

    @classmethod
    def get_step1_status(cls, user: str) -> dict:
        profile_ok = cls.is_performance_profile_active("throughput-performance")
        power_ok = cls.is_power_and_sleep_optimized()
        autologin_enabled, active_user = cls.is_auto_login_enabled()
        autologin_ok = autologin_enabled and (not user or active_user == user)
        return {
            "profile_ok": profile_ok,
            "power_ok": power_ok,
            "autologin_ok": autologin_ok,
            "all_ok": profile_ok and power_ok and autologin_ok,
            "user": active_user or user
        }

    @classmethod
    def apply_all_system_energy_and_login(cls, user: str) -> bool:
        ok1 = cls.set_performance_profile("throughput-performance")
        ok2 = cls.set_power_and_sleep(disable_sleep=True)
        ok3 = cls.set_auto_login(enabled=True, user=user)
        return ok1 and ok2 and ok3

    @classmethod
    def set_auto_login(cls, enabled: bool, user: str, config_path: Path | None = None) -> bool:
        target_path = config_path or DEFAULT_GDM_CONFIG
        try:
            if config_path is not None:
                # Tests / custom targets: plain write, no privileges involved.
                target_path.write_text(cls.generate_gdm_config(target_path, enabled, user), encoding="utf-8")
                return True
            current, current_user = cls.is_auto_login_enabled(target_path)
            if current == enabled and (not enabled or current_user == user):
                return True  # already as requested: no password prompt
            args = ["gdm-autologin", "--config", str(target_path),
                    "--enable" if enabled else "--disable", "--user", user or ""]
            ok, msg = run_helper(args)
            if not ok:
                logger.warning("GDM auto-login not changed: %s", msg)
                return False
            logger.info(f"Updated GDM auto-login to enabled={enabled} for user {user}")
            return True
        except Exception:
            logger.exception("Failed configuring GDM auto-login")
            return False

    @classmethod
    def is_auto_login_enabled(cls, config_path: Path | None = None) -> tuple[bool, str]:
        target_path = config_path or DEFAULT_GDM_CONFIG
        if not target_path.exists():
            return False, ""
        try:
            content = target_path.read_text(encoding="utf-8")
            enabled_match = re.search(r"AutomaticLoginEnable\s*=\s*(True|true|1)", content)
            user_match = re.search(r"AutomaticLogin\s*=\s*([^\s\n]+)", content)
            enabled = bool(enabled_match)
            user = user_match.group(1).strip() if user_match else ""
            return enabled, user
        except Exception:
            logger.exception("Error checking GDM auto-login")
            return False, ""
