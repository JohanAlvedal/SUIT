import json
import os
import shutil
import subprocess
from pathlib import Path
from core.logger import get_logger
from core.package_manager import distribution_id

logger = get_logger("kiosk")

AUTOSTART_DIR = Path.home() / ".config" / "autostart"
DEFAULT_DESKTOP_FILE = AUTOSTART_DIR / "suit-kiosk.desktop"

EXTENSION_ID = "ifmcoidaalmjijjhnpafmjngeceapboj"
NATIVE_HOST_NAME = "com.suit.kiosk"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTENSION_DIR = PROJECT_ROOT / "kiosk_extension"
HOST_SCRIPT = EXTENSION_DIR / "host" / "suit_kiosk_host.py"

# Browser profile roots. Ubuntu's Chromium is a Snap whose profile lives under
# ~/snap/chromium/common/chromium instead of ~/.config/chromium.
SNAP_CHROMIUM_COMMON = Path.home() / "snap" / "chromium" / "common"
BROWSER_PROFILE_DIRS = [
    Path.home() / ".config" / "chromium",
    SNAP_CHROMIUM_COMMON / "chromium",
    Path.home() / ".config" / "google-chrome",
    Path.home() / ".config" / "BraveSoftware" / "Brave-Browser",
]

NATIVE_MESSAGING_DIRS = [
    Path.home() / ".config" / "chromium" / "NativeMessagingHosts",
    Path.home() / ".config" / "google-chrome" / "NativeMessagingHosts",
    Path.home() / ".config" / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts",
]

class KioskService:
    EXTENSION_ID = EXTENSION_ID
    NATIVE_HOST_NAME = NATIVE_HOST_NAME
    EXTENSION_DIR = EXTENSION_DIR
    HOST_SCRIPT = HOST_SCRIPT

    INSTALLED_EXTENSION_DIR = Path.home() / ".local" / "share" / "suit" / "kiosk_extension"
    # Copies used with the localhost bridge (Ubuntu). The Snap's `home`
    # interface cannot read hidden folders such as ~/.local, so for Chromium
    # Snap the extension must live in the Snap's own user-common directory.
    SNAP_BRIDGE_EXTENSION_DIR = SNAP_CHROMIUM_COMMON / "suit-kiosk-extension"
    BRIDGE_EXTENSION_DIR = Path.home() / ".local" / "share" / "suit" / "kiosk_extension_bridge"
    CHROMIUM_CONF_PATH = Path("/etc/chromium/chromium.conf")
    SYSTEM_NATIVE_MESSAGING_DIR = Path("/etc/chromium/native-messaging-hosts")
    USER_DESKTOP_DIR = Path.home() / ".local" / "share" / "applications"
    USER_DESKTOP_PATH = USER_DESKTOP_DIR / "chromium-browser.desktop"

    SUIT_MARKER_START = "# >>> SUIT Autodarts In-Page Controls >>>"
    SUIT_MARKER_END = "# <<< SUIT Autodarts In-Page Controls <<<"

    @classmethod
    def get_extension_path(cls) -> Path:
        if cls.INSTALLED_EXTENSION_DIR.exists():
            return cls.INSTALLED_EXTENSION_DIR
        return cls.EXTENSION_DIR

    @classmethod
    def sync_extension_files(cls) -> None:
        """Syncs the latest extension files to user data directory if already installed."""
        try:
            if cls.INSTALLED_EXTENSION_DIR.exists() and cls.EXTENSION_DIR.exists():
                shutil.copytree(cls.EXTENSION_DIR, cls.INSTALLED_EXTENSION_DIR, dirs_exist_ok=True)
                host_script = cls.INSTALLED_EXTENSION_DIR / "host" / "suit_kiosk_host.py"
                if host_script.exists():
                    host_script.chmod(0o755)
        except Exception:
            pass

    @classmethod
    def is_permanent_extension_installed(cls, chromium_conf: Path | None = None, desktop_path: Path | None = None) -> bool:
        """Check if the SUIT In-Page Controls extension is permanently configured in Chromium."""
        conf_file = chromium_conf or cls.CHROMIUM_CONF_PATH
        desk_file = desktop_path or cls.USER_DESKTOP_PATH

        if conf_file.exists():
            try:
                content = conf_file.read_text(encoding="utf-8")
                if cls.SUIT_MARKER_START in content:
                    return True
            except Exception:
                pass

        if desk_file.exists():
            try:
                content = desk_file.read_text(encoding="utf-8")
                if "--load-extension" in content:
                    return True
            except Exception:
                pass

        return False

    @classmethod
    def install_permanent_extension(cls, chromium_conf: Path | None = None, desktop_path: Path | None = None) -> tuple[bool, str]:
        """
        Permanently installs the SUIT In-Page Controls extension into Chromium:
        1. Copies extension files to ~/.local/share/suit/kiosk_extension/
        2. Installs Native Messaging Host manifest for user and system
        3. Configures /etc/chromium/chromium.conf with --load-extension
        4. Configures ~/.local/share/applications/chromium-browser.desktop
        """
        conf_file = chromium_conf or cls.CHROMIUM_CONF_PATH
        desk_file = desktop_path or cls.USER_DESKTOP_PATH
        if not cls.supports_permanent_extension():
            return (False, "Permanent Chromium extension installation is not validated "
                           "with Ubuntu's sandboxed Chromium Snap. Use kiosk without "
                           "permanent controls or a separate browser extension.")

        try:
            # 1. Sync extension files to persistent user data directory
            cls.INSTALLED_EXTENSION_DIR.mkdir(parents=True, exist_ok=True)
            if cls.EXTENSION_DIR.exists():
                shutil.copytree(cls.EXTENSION_DIR, cls.INSTALLED_EXTENSION_DIR, dirs_exist_ok=True)
            host_script = cls.INSTALLED_EXTENSION_DIR / "host" / "suit_kiosk_host.py"
            if host_script.exists():
                host_script.chmod(0o755)

            # 2. Install user native messaging host manifests
            cls.ensure_native_messaging_host(host_script_path=host_script)

            # Install system native messaging host manifest if directory exists
            manifest_content = {
                "name": cls.NATIVE_HOST_NAME,
                "description": "SUIT Kiosk System Control Bridge",
                "path": str(host_script.resolve()),
                "type": "stdio",
                "allowed_origins": [
                    f"chrome-extension://{cls.EXTENSION_ID}/"
                ]
            }
            manifest_json = json.dumps(manifest_content, indent=2)
            system_manifest = cls.SYSTEM_NATIVE_MESSAGING_DIR / f"{cls.NATIVE_HOST_NAME}.json"
            try:
                subprocess.run(
                    ["sudo", "-n", "mkdir", "-p", str(cls.SYSTEM_NATIVE_MESSAGING_DIR)],
                    check=False,
                    capture_output=True
                )
                subprocess.run(
                    ["sudo", "-n", "tee", str(system_manifest)],
                    input=manifest_json,
                    text=True,
                    check=False,
                    capture_output=True
                )
            except Exception as e:
                logger.debug("System native messaging manifest write skipped: %s", e)

            # 3. Configure /etc/chromium/chromium.conf
            ext_dir_path = str(cls.INSTALLED_EXTENSION_DIR.resolve())
            if conf_file.exists():
                content = conf_file.read_text(encoding="utf-8")
                if cls.SUIT_MARKER_START not in content:
                    snippet = f"\n{cls.SUIT_MARKER_START}\nCHROMIUM_FLAGS+=\" --load-extension={ext_dir_path}\"\n{cls.SUIT_MARKER_END}\n"
                    # If this is the real system file, write with sudo; if a test file, write directly
                    if conf_file == cls.CHROMIUM_CONF_PATH:
                        subprocess.run(
                            ["sudo", "-n", "tee", "-a", str(conf_file)],
                            input=snippet,
                            text=True,
                            check=True,
                            capture_output=True
                        )
                    else:
                        with conf_file.open("a", encoding="utf-8") as f:
                            f.write(snippet)
                    logger.info("Configured %s with permanent extension", conf_file)

            # 4. User desktop launcher override for GNOME Dash
            desk_file.parent.mkdir(parents=True, exist_ok=True)
            src_desktop = Path("/usr/share/applications/chromium-browser.desktop")
            src_content = ""
            if src_desktop.exists():
                src_content = src_desktop.read_text(encoding="utf-8")
            elif desk_file.exists():
                src_content = desk_file.read_text(encoding="utf-8")

            if src_content:
                lines = src_content.splitlines()
                new_lines = []
                ext_flag = f"--load-extension={ext_dir_path}"
                for line in lines:
                    if line.startswith("Exec=") and ext_flag not in line:
                        if "%U" in line:
                            line = line.replace("%U", f"{ext_flag} %U")
                        else:
                            line = f"{line} {ext_flag}"
                    new_lines.append(line)
                desk_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                logger.info("Created desktop launcher override at %s", desk_file)

            return True, "In-Page Controls extension installed into Chromium."
        except Exception as e:
            logger.exception("Failed installing permanent extension into Chromium")
            return False, f"Installation failed: {e}"

    @classmethod
    def uninstall_permanent_extension(cls, chromium_conf: Path | None = None, desktop_path: Path | None = None) -> tuple[bool, str]:
        """
        Removes permanent SUIT In-Page Controls extension from Chromium:
        1. Strips load-extension snippet from /etc/chromium/chromium.conf
        2. Removes user desktop launcher override
        3. Cleans system native messaging manifest
        """
        conf_file = chromium_conf or cls.CHROMIUM_CONF_PATH
        desk_file = desktop_path or cls.USER_DESKTOP_PATH

        try:
            # 1. Clean /etc/chromium/chromium.conf
            if conf_file.exists():
                content = conf_file.read_text(encoding="utf-8")
                if cls.SUIT_MARKER_START in content:
                    lines = content.splitlines()
                    cleaned_lines = []
                    skipping = False
                    for line in lines:
                        if cls.SUIT_MARKER_START in line:
                            skipping = True
                            continue
                        if cls.SUIT_MARKER_END in line:
                            skipping = False
                            continue
                        if not skipping:
                            cleaned_lines.append(line)
                    new_content = "\n".join(cleaned_lines).strip() + "\n"
                    if conf_file == cls.CHROMIUM_CONF_PATH:
                        subprocess.run(
                            ["sudo", "-n", "tee", str(conf_file)],
                            input=new_content,
                            text=True,
                            check=True,
                            capture_output=True
                        )
                    else:
                        conf_file.write_text(new_content, encoding="utf-8")
                    logger.info("Cleaned %s", conf_file)

            # 2. Remove user desktop launcher override
            if desk_file.exists():
                desk_file.unlink()
                logger.info("Removed %s", desk_file)

            # 3. Remove system native messaging manifest
            system_manifest = cls.SYSTEM_NATIVE_MESSAGING_DIR / f"{cls.NATIVE_HOST_NAME}.json"
            try:
                subprocess.run(["sudo", "-n", "rm", "-f", str(system_manifest)], check=False, capture_output=True)
            except Exception:
                pass

            return True, "In-Page Controls extension removed from Chromium."
        except Exception as e:
            logger.exception("Failed uninstalling permanent extension from Chromium")
            return False, f"Removal failed: {e}"

    @classmethod
    def ensure_native_messaging_host(cls, host_script_path: Path | None = None) -> bool:
        """
        Installs the Native Messaging Host JSON manifest for Chromium, Google Chrome, and Brave.
        """
        script_path = host_script_path or cls.HOST_SCRIPT
        try:
            if script_path.exists():
                script_path.chmod(0o755)

            manifest_content = {
                "name": cls.NATIVE_HOST_NAME,
                "description": "SUIT Kiosk System Control Bridge",
                "path": str(script_path.resolve()),
                "type": "stdio",
                "allowed_origins": [
                    f"chrome-extension://{cls.EXTENSION_ID}/"
                ]
            }

            for host_dir in NATIVE_MESSAGING_DIRS:
                host_dir.mkdir(parents=True, exist_ok=True)
                manifest_file = host_dir / f"{cls.NATIVE_HOST_NAME}.json"
                manifest_file.write_text(json.dumps(manifest_content, indent=2), encoding="utf-8")
                logger.debug(f"Installed native messaging manifest: {manifest_file}")

            logger.info("Ensured SUIT Kiosk native messaging host manifests across browsers")
            return True
        except Exception:
            logger.exception("Failed installing native messaging host manifest")
            return False

    @classmethod
    def supports_inpage_controls(cls) -> bool:
        """In-page controls work on Fedora (native messaging) and Ubuntu (localhost bridge)."""
        return True

    @classmethod
    def supports_permanent_extension(cls) -> bool:
        """Installing the extension into every Chromium launch (/etc/chromium) is Fedora-only."""
        return distribution_id() != "ubuntu"

    @staticmethod
    def is_snap_browser(browser: str | None) -> bool:
        resolved = shutil.which(browser or "") or ""
        if resolved.startswith("/snap/"):
            return True
        # Ubuntu's chromium-browser .deb is only a wrapper that launches the Snap.
        return Path(resolved).name in ("chromium-browser", "chromium") and Path("/snap/bin/chromium").exists()

    @classmethod
    def uses_bridge(cls, browser: str | None = None) -> bool:
        """Ubuntu (and any Snap browser) cannot use native messaging -> localhost bridge."""
        return distribution_id() == "ubuntu" or cls.is_snap_browser(browser)

    @classmethod
    def prepare_bridge_extension(cls, browser: str | None = None, target: Path | None = None) -> Path:
        """Copy the extension (without the native host) to a browser-readable folder
        and write the bridge port/token next to it, readable only by the extension."""
        from core.kiosk_bridge import load_or_create_config

        dest = target or (cls.SNAP_BRIDGE_EXTENSION_DIR if cls.is_snap_browser(browser) else cls.BRIDGE_EXTENSION_DIR)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copytree(cls.EXTENSION_DIR, dest, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("host", "__pycache__"))
        os.chmod(dest, 0o700)
        cfg = load_or_create_config()
        cfg_file = dest / "bridge_config.json"
        fd = os.open(cfg_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"url": f"http://127.0.0.1:{cfg['port']}/action", "token": cfg["token"]}, fh)
        return dest

    @classmethod
    def get_kiosk_flags(cls, enable_controls: bool = True, browser: str | None = None) -> list[str]:
        flags = [
            # Wayland on a Wayland session, X11 otherwise (forcing wayland
            # breaks Chromium on an Xorg login).
            "--ozone-platform-hint=auto",
            "--kiosk",
            "--noerrdialogs",
            "--no-first-run",
            # After a power cut: no "Restore pages?" bubble.
            "--hide-crash-restore-bubble",
            "--disable-session-crashed-bubble",
            "--disable-infobars",
            # With autologin GNOME Keyring is locked; without this Chromium
            # blocks on an unlock prompt behind the kiosk window.
            "--password-store=basic",
            "--check-for-update-interval=31536000"
        ]
        if enable_controls and cls.supports_inpage_controls():
            if cls.uses_bridge(browser):
                try:
                    ext_dir = cls.prepare_bridge_extension(browser)
                except OSError:
                    logger.exception("Could not prepare kiosk extension for bridge mode")
                    return flags
            else:
                ext_dir = cls.INSTALLED_EXTENSION_DIR if cls.INSTALLED_EXTENSION_DIR.exists() else cls.EXTENSION_DIR
            if ext_dir.exists():
                flags.append(f"--load-extension={ext_dir.resolve()}")
        return flags

    @classmethod
    def clean_stale_singleton_locks(cls) -> None:
        """Safely removes stale Singleton lock files from browser config directories."""
        for pdir in BROWSER_PROFILE_DIRS:
            if pdir.exists():
                for lock in pdir.glob("Singleton*"):
                    try:
                        lock.unlink(missing_ok=True)
                        logger.debug(f"Removed stale lock: {lock}")
                    except Exception as e:
                        logger.debug(f"Failed removing {lock}: {e}")

    @classmethod
    def ensure_launcher_script(cls) -> Path:
        bin_dir = Path.home() / ".local" / "share" / "suit" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        script_path = bin_dir / "launch-kiosk.sh"
        content = """#!/usr/bin/env bash
# SUIT Autodarts Kiosk Launcher
# After a power cut or hostname change Chromium refuses to start ("profile in
# use") or shows a restore bubble. Clean both for every known profile root,
# including Ubuntu's Chromium Snap under ~/snap/chromium/common/chromium.
for profile_root in "$HOME/.config/chromium" "$HOME/snap/chromium/common/chromium" \
                    "$HOME/.config/google-chrome" "$HOME/.config/BraveSoftware/Brave-Browser"; do
    [ -d "$profile_root" ] || continue
    rm -f "$profile_root"/Singleton* 2>/dev/null
    prefs="$profile_root/Default/Preferences"
    if [ -f "$prefs" ]; then
        sed -i -e 's/"exited_cleanly":false/"exited_cleanly":true/' \
               -e 's/"exit_type":"[A-Za-z]*"/"exit_type":"Normal"/' "$prefs" 2>/dev/null
    fi
done

# Automatically dismiss GNOME Shell Overview on startup so kiosk displays fullscreen seamlessly
(
    for i in $(seq 1 40); do
        if [ "$(busctl --user get-property org.gnome.Shell /org/gnome/Shell org.gnome.Shell OverviewActive 2>/dev/null)" = "b true" ]; then
            gdbus call --session --dest org.gnome.Shell --object-path /org/gnome/Shell --method org.freedesktop.DBus.Properties.Set org.gnome.Shell OverviewActive "<false>" >/dev/null 2>&1
        fi
        sleep 0.25
    done
) &

# Ubuntu / Chromium Snap: start the localhost bridge for the in-page controls
# inside this graphical session (logind then allows poweroff/reboot). It exits
# immediately if it is already running.
if [ -f "$HOME/.config/suit/kiosk_bridge.json" ] && [ -f "__SUIT_ROOT__/core/kiosk_bridge.py" ]; then
    python3 "__SUIT_ROOT__/core/kiosk_bridge.py" >/dev/null 2>&1 &
fi

exec "$@"
""".replace("__SUIT_ROOT__", str(PROJECT_ROOT))
        script_path.write_text(content, encoding="utf-8")
        script_path.chmod(0o755)
        return script_path

    @classmethod
    def find_browser_binary(cls) -> str:
        for candidate in ["chromium-browser", "chromium", "google-chrome", "brave-browser"]:
            if shutil.which(candidate):
                return candidate
        return "chromium"

    @classmethod
    def resolve_browser(cls, browser: str | None = None) -> str:
        if not browser:
            return cls.find_browser_binary()
        if not shutil.which(browser):
            detected = cls.find_browser_binary()
            if shutil.which(detected):
                return detected
        return browser

    @classmethod
    def generate_desktop_entry(cls, url: str, browser: str = "chromium", enable_controls: bool = True) -> str:
        launcher = cls.ensure_launcher_script()
        actual_browser = cls.resolve_browser(browser)
        flags = cls.get_kiosk_flags(enable_controls=enable_controls, browser=actual_browser)
        cmd = f'{launcher} {actual_browser} {" ".join(flags)} "{url}"'
        return f"""[Desktop Entry]
Type=Application
Name=Autodarts Kiosk
Exec={cmd}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
"""

    @classmethod
    def set_autostart(cls, enabled: bool, url: str = "https://play.autodarts.com/", browser: str = "chromium", enable_controls: bool = True, desktop_file: Path | None = None) -> bool:
        target_file = desktop_file or DEFAULT_DESKTOP_FILE
        try:
            if not enabled:
                if target_file.exists():
                    target_file.unlink()
                logger.info(f"Removed kiosk autostart file: {target_file}")
                return True

            if enable_controls and not cls.uses_bridge(cls.resolve_browser(browser)):
                cls.ensure_native_messaging_host()

            target_file.parent.mkdir(parents=True, exist_ok=True)
            entry = cls.generate_desktop_entry(url, browser, enable_controls=enable_controls)
            target_file.write_text(entry, encoding="utf-8")
            target_file.chmod(0o644)
            logger.info(f"Created kiosk autostart file: {target_file}")
            return True
        except Exception:
            logger.exception("Failed configuring kiosk autostart")
            return False

    @classmethod
    def is_autostart_enabled(cls, desktop_file: Path | None = None) -> bool:
        target_file = desktop_file or DEFAULT_DESKTOP_FILE
        return target_file.exists()

    @classmethod
    def is_power_controls_enabled(cls, desktop_file: Path | None = None) -> bool:
        target_file = desktop_file or DEFAULT_DESKTOP_FILE
        if not target_file.exists():
            return True
        try:
            content = target_file.read_text(encoding="utf-8")
            return "--load-extension" in content
        except Exception:
            return True

