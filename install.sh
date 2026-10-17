#!/usr/bin/env bash
# SUIT installer for Fedora and Ubuntu Desktop.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source /etc/os-release

case "${ID:-}" in
  ubuntu)
    # NavigationView requires libadwaita >= 1.4 (Ubuntu 24.04 ships 1.5).
    if ! dpkg --compare-versions "${VERSION_ID:-0}" ge "24.04"; then
      echo "Ubuntu 24.04 or newer is required (libadwaita >= 1.4)." >&2
      exit 1
    fi
    DISTRO="ubuntu"
    PACKAGES=(python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
              python3-evdev python3-qrcode python3-opencv python3-numpy
              v4l-utils git xdg-user-dirs)
    ;;
  fedora)
    DISTRO="fedora"
    PACKAGES=(python3 python3-gobject libadwaita python3-evdev
              python3-qrcode python3-opencv v4l-utils git)
    ;;
  *)
    echo "Unsupported distribution: ${PRETTY_NAME:-unknown}." >&2
    echo "Currently supported: Ubuntu Desktop and Fedora Workstation." >&2
    exit 1
    ;;
esac

echo "SUIT setup for ${PRETTY_NAME} (${DISTRO})"
if [[ "${1:-}" == "--check" ]]; then
  echo "Read-only check: planned packages: ${PACKAGES[*]}"
  echo "The legacy uninstaller is never run automatically."
  exit 0
fi
if [[ $# -ne 0 ]]; then
  echo "Usage: ./install.sh [--check]" >&2
  exit 2
fi

# Package installation is the only privileged action performed by this script.
# Do not run the legacy uninstaller or change sudoers, login or keyring settings.
if [[ "$DISTRO" == "ubuntu" ]]; then
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends "${PACKAGES[@]}"
else
  sudo dnf install -y --setopt=install_weak_deps=False "${PACKAGES[@]}"
fi

python3 "$ROOT/create_launcher.py"

# Keep Fedora's existing touchscreen/display boot configuration in sync after
# an explicit install; do not alter Ubuntu login/display autostarts automatically.
if [[ "$DISTRO" == "fedora" && -f "$HOME/.suit_rotation_config.json" ]]; then
  python3 -c "import sys; sys.path.insert(0, '$ROOT'); from core.display_service import DisplayService; DisplayService.ensure_autostart()" 2>/dev/null || true
fi
echo "SUIT installed. Start it from the Applications menu."
echo "Some advanced Fedora-specific controls remain unavailable on Ubuntu."
