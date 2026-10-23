#!/usr/bin/python3 -I
"""SUIT privileged helper.

Runs as root through pkexec (polkit action se.alvedal.suit.helper, installed
by install.sh as /usr/libexec/suit/suit-helper). It replaces the passwordless
sudo rule that upstream SUIT used to create: instead of root for everything,
only the fixed verbs below are possible and every argument is validated.

Doing a whole multi-step operation in ONE root process matters on a touch
kiosk: unbinding a USB touchscreen and then asking for a second password to
bind it again leaves the screen without touch input, so the second dialog
could never be answered.

This file must stay standalone (no imports from the SUIT checkout): the
installed copy is root-owned and must not load user-writable code.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HELPER_VERSION = "1"

UDEV_RULE_PATH = Path("/etc/udev/rules.d/99-suit-touch.rules")
LOGIND_DROPIN = Path("/etc/systemd/logind.conf.d/99-suit-power.conf")
GDM_CONFIGS = (Path("/etc/gdm3/custom.conf"), Path("/etc/gdm/custom.conf"))
USB_DRIVER = Path("/sys/bus/usb/drivers/usb")
USB_DEVICES = Path("/sys/bus/usb/devices")

TOUCH_NAME_RE = re.compile(r"^[A-Za-z0-9 _.,:()+/\-]{1,128}$")
BUSID_RE = re.compile(r"^\d+-\d+(\.\d+)*$")
USER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
UNIT_RE = re.compile(r"^autodarts[A-Za-z0-9_@.\-]{0,64}\.service$")
UNIT_ACTIONS = ("start", "stop", "restart", "reset-failed")
SYSTEMCTL = "/usr/bin/systemctl" if Path("/usr/bin/systemctl").exists() else "/bin/systemctl"
UDEVADM = "/usr/bin/udevadm" if Path("/usr/bin/udevadm").exists() else "/bin/udevadm"


class HelperError(Exception):
    pass


def _run(cmd: list[str]) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        raise HelperError(f"{' '.join(cmd)} failed: {res.stderr.strip() or res.returncode}")


def _write_root_file(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.suit-tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def validate_matrix(text: str) -> str:
    parts = text.split()
    if len(parts) != 9:
        raise HelperError("matrix must have 9 numbers")
    try:
        values = [float(p) for p in parts]
    except ValueError as exc:
        raise HelperError("matrix must be numeric") from exc
    return " ".join(f"{v:g}" for v in values)


def validate_busid(busid: str | None) -> str | None:
    if not busid:
        return None
    if not BUSID_RE.match(busid) or not (USB_DEVICES / busid).exists():
        raise HelperError(f"invalid USB bus id: {busid}")
    return busid


def udev_rule_text(name: str, matrix: str) -> str:
    if not TOUCH_NAME_RE.match(name):
        raise HelperError("invalid touch device name")
    return (
        f'ACTION=="add|change", KERNEL=="event*", ATTRS{{name}}=="{name}", '
        f'ENV{{LIBINPUT_CALIBRATION_MATRIX}}="{validate_matrix(matrix)}"\n'
    )


def _reload_udev() -> None:
    _run([UDEVADM, "control", "--reload-rules"])
    _run([UDEVADM, "trigger", "--subsystem-match=input"])


def _rebind(busid: str | None) -> None:
    if not busid:
        return
    time.sleep(0.6)  # let Mutter finish the rotation before the device drops
    (USB_DRIVER / "unbind").write_text(busid + "\n")
    time.sleep(1.0)
    try:
        (USB_DRIVER / "bind").write_text(busid + "\n")
    except OSError:
        time.sleep(1.0)  # one retry: never leave the touchscreen unbound
        (USB_DRIVER / "bind").write_text(busid + "\n")


def cmd_touch_apply(args) -> str:
    busid = validate_busid(args.rebind)
    rule = udev_rule_text(args.name, args.matrix)
    _write_root_file(UDEV_RULE_PATH, rule)
    _reload_udev()
    _rebind(busid)
    return "touch calibration applied"


def cmd_touch_clear(args) -> str:
    busid = validate_busid(args.rebind)
    if UDEV_RULE_PATH.exists():
        UDEV_RULE_PATH.unlink()
        _reload_udev()
        _rebind(busid)
        return "touch calibration cleared"
    return "no touch calibration to clear"


def generate_gdm_config(content: str, enabled: bool, user: str) -> str:
    lines = [
        line for line in content.splitlines()
        if not line.strip().startswith(("AutomaticLoginEnable=", "AutomaticLogin="))
    ]
    insert = ["AutomaticLoginEnable=True", f"AutomaticLogin={user}"] if enabled else ["AutomaticLoginEnable=False"]
    for i, line in enumerate(lines):
        if line.strip() == "[daemon]":
            return "\n".join(lines[:i + 1] + insert + lines[i + 1:]) + "\n"
    return "\n".join(["[daemon]", *insert, "", *lines]) + "\n"


def cmd_gdm_autologin(args) -> str:
    target = Path(args.config)
    if target not in GDM_CONFIGS:
        raise HelperError("unsupported GDM config path")
    if args.enable and not USER_RE.match(args.user or ""):
        raise HelperError("invalid user name")
    current = target.read_text(encoding="utf-8") if target.exists() else "[daemon]\n"
    backup = target.with_name(target.name + ".suit-orig")
    if target.exists() and not backup.exists():
        shutil.copy2(target, backup)  # first change only: the distro original
    _write_root_file(target, generate_gdm_config(current, args.enable, args.user or ""))
    return f"automatic login {'enabled' if args.enable else 'disabled'}"


def cmd_logind_clear(args) -> str:
    if LOGIND_DROPIN.exists():
        LOGIND_DROPIN.unlink()
        return "removed legacy logind drop-in"
    return "nothing to remove"


def cmd_unit(args) -> str:
    if args.action not in UNIT_ACTIONS or not UNIT_RE.match(args.name):
        raise HelperError("unit not allowed")
    _run([SYSTEMCTL, args.action, args.name])
    return f"{args.action} {args.name}"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="suit-helper")
    sub = p.add_subparsers(dest="verb", required=True)
    sub.add_parser("version")
    ta = sub.add_parser("touch-apply")
    ta.add_argument("--name", required=True)
    ta.add_argument("--matrix", required=True)
    ta.add_argument("--rebind")
    tc = sub.add_parser("touch-clear")
    tc.add_argument("--rebind")
    ga = sub.add_parser("gdm-autologin")
    ga.add_argument("--config", required=True)
    grp = ga.add_mutually_exclusive_group(required=True)
    grp.add_argument("--enable", action="store_true")
    grp.add_argument("--disable", action="store_true")
    ga.add_argument("--user", default="")
    sub.add_parser("logind-clear")
    un = sub.add_parser("unit")
    un.add_argument("action")
    un.add_argument("name")
    return p


HANDLERS = {
    "touch-apply": cmd_touch_apply,
    "touch-clear": cmd_touch_clear,
    "gdm-autologin": cmd_gdm_autologin,
    "logind-clear": cmd_logind_clear,
    "unit": cmd_unit,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.verb == "version":
        print(HELPER_VERSION)
        return 0
    if os.geteuid() != 0:
        print("suit-helper must run as root (via pkexec)", file=sys.stderr)
        return 2
    try:
        print(HANDLERS[args.verb](args))
        return 0
    except (HelperError, OSError, subprocess.SubprocessError) as exc:
        print(f"suit-helper: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
