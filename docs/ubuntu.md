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
- Chromium on Ubuntu is usually packaged as a **Snap**. A native messaging
  host started by the Snap runs inside its sandbox and cannot shut down or
  restart the PC, so on Ubuntu the kiosk's in-page controls (power off,
  restart, exit kiosk, board light) go through a small **localhost bridge**
  instead (`core/kiosk_bridge.py`, 127.0.0.1:47231):
  - started by the kiosk launcher inside the graphical session, so logind
    allows power actions exactly as from the GNOME menu;
  - every call needs a random per-install token, stored in
    `~/.config/suit/kiosk_bridge.json` (0600) and in the extension copy;
  - web pages cannot trigger it: CORS preflights are never approved, a
    non-extension `Origin` is refused, and only six fixed actions exist.
  The extension is copied to `~/snap/chromium/common/suit-kiosk-extension`
  because the Snap cannot read hidden folders such as `~/.local`.
  Needs hardware verification before calling it production-ready.
- Kiosk launch cleans stale `Singleton*` locks and marks the profile as
  cleanly exited in both `~/.config/chromium` and the Snap profile
  (`~/snap/chromium/common/chromium`), so a power cut does not leave the kiosk
  stuck on "profile in use" or a restore bubble. `--password-store=basic`
  avoids a hidden GNOME Keyring prompt after autologin.
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
- Adding the controls to *every* Chromium window (`/etc/chromium`) stays Fedora-only;
  on Ubuntu they are loaded by the kiosk launch only.
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
