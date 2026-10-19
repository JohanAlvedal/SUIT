# Ubuntu support (work in progress)

This branch adapts IteraThor's **SUIT for Fedora** to **Ubuntu Desktop** while
retaining the original Fedora installation path and the MIT license. Fedora
feature parity is not yet regression-tested after the safety changes.

## Safe installation on Ubuntu

For Ubuntu Desktop **24.04 LTS or newer**, running GNOME, use:
SUIT uses `Adw.NavigationView` (libadwaita >= 1.4); Ubuntu 22.04 ships
libadwaita 1.1 and cannot run this GTK4 UI without an unsupported upgrade.


```bash
git clone --branch feature/ubuntu-support https://github.com/JohanAlvedal/SUIT.git
cd SUIT
./install.sh --check    # read-only, reports OS and packages
./install.sh            # installs GTK4 / libadwaita and Python dependencies
```

Launch **SUIT** from Applications. The installer only installs distribution
packages and creates a user-level application launcher. It deliberately does
**not** remove old services, enable autologin, erase keyrings or configure
passwordless sudo. No root account or global Python pip installation is needed.

### Known limitations and safe-first policy

- Development is tested statically; **not yet verified on a physical Ubuntu NUC**.
- Autodarts must be installed and configured separately. Do not reinstall or
  remove a working Autodarts service just to test this GUI.
- SUIT's **Install Autodarts** never removes an existing system-wide
  `autodarts.service` silently. It asks first, backs up the unit files to
  `~/.local/share/suit/backup/autodarts-<timestamp>/`, requests one Polkit
  authorization and aborts without further changes if that is refused. The
  installer is downloaded over HTTPS to a temporary file before it runs
  (override with `SUIT_AUTODARTS_INSTALLER_URL`).
- Chromium on Ubuntu is usually packaged as a **Snap**. Kiosk fullscreen
  launch remains available, but SUIT's in-page session/power shortcuts are
  currently disabled on Ubuntu: the extension's Native Messaging host is not
  reliably accessible through the Snap sandbox. Do not claim these shortcuts
  work until a browser-specific integration has been tested.
- Ubuntu skips background camera-page prewarming at startup to reduce the risk
  of freezing the GTK interface. Camera pages still need physical testing.
- Fedora-specific GNOME RDP controls are hidden on Ubuntu. Use a separately
  configured remote-control solution rather than re-enabling GNOME RDP through SUIT.
- The original one-click **Apply All** workflow is disabled on Ubuntu. It
  silently changes login and keyring security, removes default applications and
  adjusts performance settings. Configure these deliberately and separately.
- Ubuntu package-removal/"debloat" and automatic Waydroid setup are disabled
  pending a package and platform review.
- Passwordless sudo is never automatically provisioned in this fork.
- Explicit administrator changes request Polkit authorization; touch calibration still needs hardware validation.
- Permanent Chromium Snap in-page controls installation is disabled pending testing.
- An app update uses a fast-forward only on the **current checked-out branch**;
  it must never hard-reset local changes or swap branches.
- Fedora-specific system settings may remain unavailable on Ubuntu.

### Initial validation checklist

1. Run `./install.sh --check`, then `bash -n install.sh`.
2. Install from a logged-in GNOME desktop session; start the app.
3. Confirm touchscreen, camera detection and the current Autodarts service
   without pressing destructive actions.
4. Check manual package installation authorizations and browser kiosk behavior.
5. Verify no unexpected sudoers rules, old service removals or keyring resets.
6. Only then test optional startup or login settings, with a backup available.

## Fedora installation

The same development branch supports Fedora using `dnf`:

```bash
git clone --branch feature/ubuntu-support https://github.com/JohanAlvedal/SUIT.git
cd SUIT
./install.sh --check
./install.sh
```

The original Fedora application features are retained as a goal, but the new
per-action authorization model and installer require real Fedora regression
testing before a production release or upstream merge.

## Contributing upstream

After hardware verification, open a PR from
`JohanAlvedal:feature/ubuntu-support` to `IteraThor/SUIT:main`.
Update repository URLs in the installation examples once merged.

Original project: https://github.com/IteraThor/SUIT.
