#!/usr/bin/env bash
# SUIT uninstall: removes SUIT and puts back what it changed.
# Works on Ubuntu and Fedora. Run it from a terminal in the desktop session
# (gsettings needs the session). Asks before touching automatic login and
# screen rotation. Never removes Autodarts itself or its configuration.
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PURGE=0
if [ "${1:-}" == "--purge" ] || [ "${1:-}" == "--all" ]; then
    PURGE=1
fi

ask() {
    # Default "no"; without a terminal (non-interactive) always "no".
    [ -t 0 ] || return 1
    local answer
    read -r -p "$1 [y/N] " answer
    [[ "$answer" =~ ^[YyJj] ]]
}

echo "========================================="
echo "        SUIT - Uninstall & Restore       "
echo "========================================="

echo "[1/7] Stopping and removing SUIT services..."
if systemctl --user is-active --quiet suit-camera-settings.service 2>/dev/null; then
    echo "  - Stopping suit-camera-settings.service"
    systemctl --user stop suit-camera-settings.service || true
fi
if systemctl --user is-enabled --quiet suit-camera-settings.service 2>/dev/null; then
    echo "  - Disabling suit-camera-settings.service"
    systemctl --user disable suit-camera-settings.service || true
fi
rm -f "$HOME/.config/systemd/user/suit-camera-settings.service"
rm -f "$HOME/.config/systemd/user/default.target.wants/suit-camera-settings.service"
systemctl --user daemon-reload || true

echo "  - Stopping kiosk bridge and removing its token and extension copies"
pkill -f "core/kiosk_bridge.py" 2>/dev/null || true
rm -f "$HOME/.config/suit/kiosk_bridge.json"
rm -rf "$HOME/snap/chromium/common/suit-kiosk-extension" \
       "$HOME/.local/share/suit/kiosk_extension_bridge" \
       "$HOME/.local/share/suit/kiosk_extension" \
       "$HOME/.local/share/suit/bin"

echo "[2/7] Removing SUIT autostart entries..."
for auto in suit-rotation.desktop suit-kiosk.desktop suit-chromium.desktop; do
    if [ -f "$HOME/.config/autostart/$auto" ]; then
        echo "  - Removing ~/.config/autostart/$auto"
        rm -f "$HOME/.config/autostart/$auto"
    fi
done

echo "[3/7] Restoring desktop settings (theme, touch tweaks, display sleep)..."
if command -v gsettings >/dev/null 2>&1 && [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    (cd "$ROOT" && python3 - <<'PY') || echo "  ! Could not restore some desktop settings."
from core.desktop_service import DesktopService
from core.power_service import PowerService

if DesktopService.has_visuals_backup() or DesktopService.get_visuals_status().get("wallpaper"):
    ok, msg = DesktopService.restore_desktop_visuals()
    print("  -", msg)
if DesktopService.USER_EXTENSION_DIR.exists() or DesktopService.is_touch_scaling_enabled(DesktopService):
    ok, msg = DesktopService.set_touch_scaling(False)
    print("  -", msg)
if PowerService.is_power_and_sleep_optimized():
    PowerService.set_power_and_sleep(disable_sleep=False)
    print("  - Display sleep and lock screen restored to system defaults.")
PY
else
    echo "  ! Not in a desktop session: run this again from a terminal on the dartboard PC"
    echo "    to restore theme, touch tweaks and display sleep."
fi

if command -v powerprofilesctl >/dev/null 2>&1 && [ "$(powerprofilesctl get 2>/dev/null)" == "performance" ]; then
    echo "  - Power profile back to Balanced"
    powerprofilesctl set balanced || true
fi

echo "[4/7] Touchscreen calibration and screen rotation..."
if [ -f "/etc/udev/rules.d/99-suit-touch.rules" ]; then
    echo "  - Removing /etc/udev/rules.d/99-suit-touch.rules"
    sudo rm -f "/etc/udev/rules.d/99-suit-touch.rules" || true
    sudo udevadm control --reload-rules || true
    sudo udevadm trigger --subsystem-match=input || true
fi
if [ -f "$HOME/.suit_rotation_config.json" ] && [ -f "$HOME/.config/monitors.xml" ]; then
    if ask "  Reset screen rotation to normal (removes ~/.config/monitors.xml)?"; then
        mv "$HOME/.config/monitors.xml" "$HOME/.config/monitors.xml.suit-removed"
        echo "  - Moved to ~/.config/monitors.xml.suit-removed (takes effect at next login)"
    else
        echo "  - Keeping current screen rotation."
    fi
fi

echo "[5/7] Automatic login..."
GDM_CONF=""
for conf in /etc/gdm3/custom.conf /etc/gdm/custom.conf; do
    [ -f "$conf" ] && GDM_CONF="$conf" && break
done
if [ -n "$GDM_CONF" ] && grep -Eq '^AutomaticLoginEnable *= *(True|true|1)' "$GDM_CONF"; then
    if ask "  Turn off automatic login (password at startup again)?"; then
        sudo sed -i -E 's/^AutomaticLoginEnable *=.*/AutomaticLoginEnable=False/' "$GDM_CONF"
        echo "  - Automatic login disabled in $GDM_CONF"
    else
        echo "  - Keeping automatic login."
    fi
else
    echo "  - Automatic login not enabled; nothing to do."
fi

echo "[6/7] Removing SUIT helper, polkit action and launchers..."
if [ -e /usr/libexec/suit/suit-helper ] || [ -e /usr/share/polkit-1/actions/se.alvedal.suit.helper.policy ]; then
    sudo rm -f /usr/libexec/suit/suit-helper /usr/share/polkit-1/actions/se.alvedal.suit.helper.policy || true
    sudo rmdir /usr/libexec/suit 2>/dev/null || true
fi
for desktop_dir in "$HOME/Desktop" "$HOME/Schreibtisch" "$(xdg-user-dir DESKTOP 2>/dev/null || true)"; do
    [ -n "$desktop_dir" ] || continue
    for f in "de.iterathor.suit.gtk.desktop" "SUIT.desktop"; do
        if [ -f "$desktop_dir/$f" ]; then
            echo "  - Removing $desktop_dir/$f"
            rm -f "$desktop_dir/$f"
        fi
    done
done
for f in "de.iterathor.suit.gtk.desktop" "SUIT.desktop"; do
    if [ -f "$HOME/.local/share/applications/$f" ]; then
        echo "  - Removing ~/.local/share/applications/$f"
        rm -f "$HOME/.local/share/applications/$f"
    fi
done

echo "[7/7] Configuration files..."
if [ "$PURGE" == "1" ]; then
    echo "  - Purging SUIT configurations..."
    rm -f "$HOME/.suit_rotation_config.json"
    rm -f "$HOME/.suit_camera_profiles.json"
    rm -f "$HOME/suit.log"
    rm -f "$ROOT/suit.log"
    rm -rf "$HOME/.local/share/suit" "$HOME/.config/suit"
else
    echo "  - Preserving camera and touch configurations (~/.suit_*.json)"
    echo "    and Autodarts config backups (~/.local/share/suit/backup)."
    echo "    (Run with --purge to remove them as well.)"
fi
if ls "$HOME/.local/share/keyrings/"*.suit-*.bak >/dev/null 2>&1 || [ -f "$HOME/.local/share/keyrings/login.keyring.bak" ]; then
    echo "  - Keyring backups made by SUIT are kept in ~/.local/share/keyrings/ (*.bak)."
fi

echo "========================================="
echo "SUIT uninstalled. Autodarts itself was not touched."
echo "You can now delete the SUIT folder if desired."
echo "========================================="
