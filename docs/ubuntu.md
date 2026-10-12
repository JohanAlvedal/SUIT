# Ubuntu support (work in progress)

This branch adapts IteraThor's **SUIT for Fedora** to **Ubuntu Desktop** while
preserving Fedora support and the original MIT license.

## Safe installation on Ubuntu

For Ubuntu Desktop with GNOME, run:

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
- Chromium on Ubuntu is packaged as a **Snap**. Kiosk mode and the SUIT
  native-messaging extension must be validated on the actual computer.
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

The parent project remains at https://github.com/IteraThor/SUIT.
