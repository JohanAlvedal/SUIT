<div align="center">
  <img src="assets/icons/suit-icon.png" alt="SUIT icon" width="120">
  <h1>SUIT for Autodarts</h1>
  <p><strong>Setup Utilities by IteraThor — Fedora and Ubuntu Desktop</strong></p>
</div>

> **Community development branch:** This is JohanAlvedal's Ubuntu support proposal
> based on [IteraThor/SUIT](https://github.com/IteraThor/SUIT). The Ubuntu port is
> under development and has **not yet been validated on physical hardware**.
> Features described below are inherited from upstream and may not work on both
> distributions yet.

## Platform status

| Platform | Status | Notes |
| --- | --- | --- |
| Fedora Workstation | Original upstream target | The installer retains `dnf`; Fedora regression testing is still needed for this fork. |
| Ubuntu Desktop 24.04 LTS or newer (GNOME) | Experimental | Installer uses `apt`; graphical and camera tests still needed on a real machine. |
| Ubuntu 22.04 and older | Not supported | SUIT uses `Adw.NavigationView`, which requires libadwaita 1.4 or newer. |

## Installation

Install from a **logged-in graphical desktop session**. Use the steps for your
distribution below. SUIT is a management GUI; install/configure Autodarts itself
separately.

### Ubuntu Desktop (24.04 LTS or newer)

```bash
git clone --branch feature/ubuntu-support https://github.com/JohanAlvedal/SUIT.git
cd SUIT
./install.sh --check     # Safe preview: does not change the computer
./install.sh             # Uses apt and creates a SUIT application launcher
```

### Fedora Workstation

```bash
git clone --branch feature/ubuntu-support https://github.com/JohanAlvedal/SUIT.git
cd SUIT
./install.sh --check     # Safe preview: does not change the computer
./install.sh             # Uses dnf and creates a SUIT application launcher
```

After installation, launch **SUIT (Autodarts)** from the application menu.

**Important:** The installer does not uninstall the previous SUIT version,
change sudoers/Polkit policy, disable screen locking, reset keyrings, or change
Autodarts services. Do not run the optional legacy cleanup script without
reviewing its consequences.

### What currently differs between platforms?

| Function | Fedora | Ubuntu |
| --- | --- | --- |
| GTK4/libadwaita dashboard | Upstream implementation | Ported; hardware testing pending |
| Camera focus and board utilities | Upstream implementation | Hardware testing pending |
| Screen orientation and touch | Upstream implementation | Hardware testing pending |
| Browser kiosk | Upstream implementation | Chromium Snap behavior requires testing |
| Permanent Chromium in-page controls | Upstream implementation | Disabled pending Snap compatibility work |
| System-wide **Apply All** | Upstream workflow | Disabled to prevent unsafe bulk changes |
| Automatic application removal (debloat) | Upstream workflow | Disabled pending package review |
| Automatic Waydroid install | Upstream workflow | Disabled pending platform review |

The fork also removes the original broad **passwordless sudo** setup on both
platforms. Privileged operations may ask for authentication, and some older
system utilities still need follow-up changes and testing.

See [Ubuntu setup, caveats and validation](docs/ubuntu.md) for details.

## Keeping your installation updated

SUIT's built-in updater in this branch attempts a fast-forward on the **current
checked-out branch only**. It refuses to discard local changes. Until Ubuntu
support is merged upstream, continue using this fork's development branch.

## Legacy SUIT installations

The upstream project includes `uninstall_legacy.sh` for removing older
background services, touch rules and autostart entries. **It is not executed
automatically by this installer.** Review the script and back up your
configuration before choosing to run it.

---

## Features & Modes

### 1. Main Dashboard
Modern Libadwaita touch menu providing rapid access to all system tools and live status.

<div align="center">
  <img src="docs/assets/screenshots/01-main-dashboard.png" alt="SUIT Main Dashboard" width="700">
</div>

* Large 48px+ touch targets optimized for touchscreens.
* Quick access to community resources, Discord, and 3D print models.
* Integrated one-click update checker.

---

### 2. System Utilities & Touchscreen Tweaks
One-click performance, display, and desktop optimizations for dartboard machines.

<div align="center">
  <img src="docs/assets/screenshots/02-system-tweaks.png" alt="System Utilities and Touchscreen Tweaks" width="700">
</div>

* **Touchscreen Tweaks**: Enlarges GNOME top bar to 54px, expands button touch padding, enables On-Screen Keyboard (OSK), and restores window Minimize/Maximize buttons across Chromium and desktop apps.
* **Performance Profile**: Locks CPU governors to high-performance mode to minimize dart detection latency.
* **Display Keepalive & Auto-Login**: Bypasses screen blanking, sleep timeouts, and login password prompts.

---

### 3. Autodarts Setup
Manage the Autodarts core service daemon, camera configurations, and board pairing.

<div align="center">
  <img src="docs/assets/screenshots/03-autodarts-setup.png" alt="Autodarts Setup" width="700">
</div>

* One-tap service controls to start, stop, or restart `autodarts.service`.
* Live camera selection with resolution and frame rate adjustments (up to 1080p, 30 FPS).
* Direct board pairing wizard and local web UI launcher.

---

### 4. Camera Focus Tool
Optical calibration wizard to achieve razor-sharp focus across all 3 Autodarts cameras.

* **Sweet-Spot HUD**: Projects a green target reticle directly onto the furthest double ring wire.
* **2.5x Magnifier Lens**: Live zoomed view centered on the sweet spot for fine optical lens adjustments.
* **Sharpness Score Meter**: Normalized 0–100 score gauge with real-time peak tracking and focus trend indicators.
* **Audio Tone Guidance**: Modulates pitch dynamically as focus improves, allowing you to focus lenses while standing at the board without looking at the screen.

---

### 5. Screen & Touch Manager
Wayland display orientation and touch coordinate matrix calibration.

<div align="center">
  <img src="docs/assets/screenshots/05-screen-touch.png" alt="Screen and Touch Manager" width="700">
</div>

* Rotate displays seamlessly between 0° Normal, 90° Right, 180° Inverted, and 270° Left.
* Automatic touch matrix calibration (`LIBINPUT_CALIBRATION_MATRIX`) via udev rules to align touch input with rotated screens.
* Discovers connected displays and touchscreen controllers automatically.

---

### 6. Fullscreen Kiosk Mode
Run Autodarts as a dedicated full-screen appliance with customized browser controls.

<div align="center">
  <img src="docs/assets/screenshots/06-kiosk-controls.png" alt="Fullscreen Kiosk Mode with In-Page Controls" width="420">
</div>

* Boots Chromium directly into fullscreen mode without desktop distractions.
* Toggle automatic autostart on boot.
* Built-in Chromium extension adding Power, Reboot, and Exit buttons directly into the Autodarts web scoreboard.
