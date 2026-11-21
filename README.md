# Driver Finder 🔍🚀 (Version 2.3.0 - Revision 2026.11.21-R4)

**Driver Finder** is a Windows application that scans your computer's hardware devices, identifies installed driver versions and release dates, and checks for the latest official manufacturer drivers using the Microsoft Update Catalog and OEM support portals (Dell, Intel, NVIDIA, AMD, Realtek, etc.).

It features a **1-Click "Update All Drivers"** engine that downloads, extracts, and installs all updated drivers automatically using Windows PnP utilities, with built-in restart detection, an instant reboot button, 100% silent execution (no flashing console windows), dual-phase progress bars, and prominent in-app revision badges.

## Install

Download [DriverFinder-Setup.exe](https://github.com/maxwelltollefson/driver-finder/releases/latest) and run it. No Python install is required and no administrator rights are needed to install — it installs for the current user. The setup adds a desktop shortcut. Administrator approval is only requested later, when you actually install a driver update.

Driver packages are downloaded at runtime from Microsoft Update Catalog. They are not stored in this repository.

### Updates

The app checks GitHub for a newer release at startup and offers it in a banner with the release notes. Installing an update is one click: it downloads `DriverFinder-Setup.exe`, verifies the size and that it is a real executable, then installs and reopens itself. No admin prompt, since the installer is per-user. **Update App** in the header checks on demand.

To run from source: `python main.py` (Windows, Python 3 with tkinter).

## Compatibility

- **Any display language.** Device enumeration uses `pnputil /format xml`, whose element names are fixed schema names. The old text output is translated on non-English Windows and parsed as zero devices.
- **Any architecture.** The app reports the OS architecture and refuses catalog packages built for a different one, instead of offering an ARM64 laptop an x64 driver.
- **Storage controllers are opt-in.** NVMe/SATA/RAID drivers are excluded from Update All and need an explicit confirmation, because a wrong or interrupted storage driver can leave Windows unable to boot.
- **Clear failure instead of a blank list.** If the Windows build predates 10 1903 (no `pnputil /enum-devices`) or enumeration is blocked, the app says so.
- **High-DPI and small screens.** The app declares DPI awareness and sizes itself to the screen instead of a fixed 1116x779.

## Versioning

Every change gets a new revision number, and the jump size shows the scale:

- **small +1** — wording, typo, one-line fix
- **notable +3** — user-visible fix, behaviour change, new feature
- **major +10** — overhaul (add `--breaking` when it breaks compatibility)

```bash
python bump_version.py --kind notable --note "What changed"
```

That updates `version.py` (single source of truth), the installer version in
`installer/DriverFinder.iss`, and `CHANGELOG.md`. CI runs
`tools/check_revision.py` and fails the build if app code changes without a
revision bump.

---

## What's New in Rev 2026.11.21-R4 (v2.3.0)

- **🏷️ Prominent In-App Revision Badges**: The program displays its active build version (`v2.3.0`) and revision code (`Rev 2026.11.21-R4`) in the window title bar, top header banner, and bottom status bar.
- **🎧 Subsystem-Aware Audio Matching (Realtek ALC3234 on Dell Inspiron 15-3567)**:
  - Eliminated stale folder caching in the installer that was reusing previously failed cross-OEM files.
  - Linked directly to the verified Dell-certified package (`6.0.9960.1` with `HDXDELLCSMB2018.inf`) matching Subsystem ID `1028078B`.
- **🖥️ Dell OEM Graphics Protection (Intel HD Graphics 620)**:
  - Clarified that `v27.20.100.9664` is Dell's official certified driver for this model.
  - Windows PnP Driver Ranking rules protect Dell-calibrated display profiles against generic/foreign INF packages. The app now accurately identifies this driver as **Up to Date (Dell Official)**.
- **🛡️ Windows Inbox System Drivers**: Filtered out Windows internal kernel and inbox system devices (`usbvideo.inf`, `machine.inf`) from false update prompts.

---

## Key Features

- **🚀 1-Click "Update All Drivers"**:
  - Automatically downloads each pending official driver package (`.cab`) directly from Microsoft's signed update servers.
  - Automatically extracts all `.inf`, `.cat`, `.sys`, and `.dll` driver files.
  - Automatically adds and installs all driver packages into your Windows DriverStore using native `pnputil`.
  - A single Windows Administrator (UAC) authorization handles the entire batch.
- **🔄 Smart Restart Detection & Quick Reboot Button**:
  - Automatically detects if newly installed drivers require a system restart (via Windows DriverStore exit code `3010`, installation logs, and Windows Component-Based Servicing registry).
  - Displays a high-visibility alert banner and a dedicated **"🔄 Restart Computer Now"** button.
  - Includes a safe 10-second confirmation countdown with an **"Abort Restart"** button in case you need to save open work.
- **⚡ Individual Driver Installation**:
  - Click any individual device and select **"⬇️ Install This Driver"** to update only that specific component.
- **🔍 Fast Hardware Scan**:
  - Scans all 180+ connected devices in ~2 seconds.
  - Automatically detects the computer model and service tag.
  - Highlights primary hardware: *Display & Graphics, Network & Wi-Fi, Audio & Sound, Bluetooth, and Storage*.
- **🌐 Manufacturer Portals**:
  - Direct 1-click link to the exact Dell support page tailored to your laptop's Service Tag.
  - Direct links to Intel Driver & Support Assistant, Realtek, NVIDIA, and AMD support.
- **📌 Desktop Shortcut**:
  - The installer places **"Driver Finder"** on your Desktop and in the Start Menu. The app can also create it on demand from the Tools menu; nothing is created behind your back on launch.

---

## How to Use Driver Finder

1. **Launch the Program**: Double-click **Driver Finder** on your Desktop.
2. **Scan & Check**: The app automatically scans your hardware on startup and checks for updates. You can also click **"Scan Computer"** or **"Check Updates"** at any time.
3. **Update All Drivers**:
   - Click the green **"🚀 Update All Drivers"** button.
   - The Installation Manager will download each driver package, extract it, and install it.
   - Click **"Yes"** on the Windows Administrator prompt when prompted.
4. **Restart If Needed**:
   - If any driver requires a system reboot, click the red **"🔄 Restart Computer Now"** button to restart your computer and finalize the installation.

---

## Project Structure

- `main.py`: Application launcher and desktop shortcut verifier.
- `gui.py`: Modern graphical user interface with live progress bars and restart management.
- `driver_installer.py`: Driver downloader, CAB extractor, elevated PnP installer, and Windows shutdown/restart controller.
- `driver_scanner.py`: Native hardware scanner and Microsoft Update Catalog search engine.
- `catalog.py`: Microsoft Update Catalog client — keep-alive HTTP plus a 24-hour on-disk query cache.
- `updater.py`: Self-update — checks GitHub releases, verifies and installs the new build.
- `paths.py`: Source/frozen path helpers (an installed copy writes to `%LOCALAPPDATA%`).
- `create_shortcut.py`: Windows desktop shortcut generator.
- `generate_icon.py`: Custom icon generator (`app_icon.ico`).
- `Run_Driver_Finder.bat`: Local launcher inside the folder.
