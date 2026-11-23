# Changelog

Driver Finder. Every change bumps the revision number; the size of the jump
shows the scale: **small +1**, **notable +3**, **major +10**. Bump with
`python bump_version.py --kind small|notable|major --note "..."`.

## v3.0.0 · Rev 2026.11.23-R64
Driver Finder can now undo what it does, explain why a device is broken, and update
your applications as well as your drivers.

### Driver backups and rollback
- Every install backs up the driver package it is about to replace, first. The export
  uses `pnputil /export-driver`, which needs no administrator approval, so the safety net
  costs no extra UAC prompt.
- New **Backups** window lists every backup with device, package, version and size on
  disk, and reinstalls one: the package bound now is removed and the backed-up package
  re-added, elevated, with live progress.
- **Back Up All Drivers** exports every third-party package on the PC - the thing worth
  doing before reinstalling Windows and losing Wi-Fi.
- **Export Offline Pack (ZIP)** bundles those packages with a README so a fresh install
  can get a network adapter working with no internet.

### System Restore point before a batch install
- The elevated worker asks Windows for a checkpoint before the first package. If System
  Protection is off it says so and the install continues: a restore point is a bonus,
  never a precondition.

### Device Health
- New **Device Health** window lists devices Windows reports as broken, with the meaning
  of each problem code and the fix that applies, in plain English.
- Disconnected hardware is excluded and counted separately. A healthy machine reports
  dozens of phantom problem codes; listing those would invent problems that do not exist.

### Application updates (winget)
- New **App Updates** window lists installed programs with a newer version in the winget
  repository, showing installed and available versions.
- You choose which ones update; each runs one at a time with its output shown. Nothing
  updates in the background and no package is chosen for you.

### Also
- Healthy devices are no longer reported as problems (`CM_PROB_NONE` is 0, not null).
- Three new header buttons; the header still reflows and wraps when the window narrows.

## v2.14.0 · Rev 2026.11.21-R54
- Top bars reflow instead of clipping; app opens maximized  _(revision +3, notable)_

## v2.13.0 · Rev 2026.11.21-R51
- Fix Device Manager button: launch via shell/mmc instead of CreateProcess on a .msc  _(revision +3, notable)_

## v2.12.0 · Rev 2026.11.21-R48
- Compatibility overhaul: locale-proof XML scanning, architecture-aware packages, storage-driver guard, DPI and small-screen support, clear scan failures  _(revision +10, major)_

## v2.11.2 · Rev 2026.11.21-R38
- Count pnputil 259 (already current) as success instead of a miss  _(revision +1, small)_

## v2.11.1 · Rev 2026.11.21-R37
- Add a headless --check-updates diagnostic and log update-check failures  _(revision +1, small)_

## v2.11.0 · Rev 2026.11.21-R36
- Self-update: checks GitHub releases, shows notes, installs and reopens on approval  _(revision +3, notable)_

## v2.10.0 · Rev 2026.11.21-R33
- Check Updates now covers every device in the current tab, not only primary ones  _(revision +3, notable)_

## v2.9.1 · Rev 2026.11.21-R30
- Status column fits Windows-Managed; versions no longer render as vN/A  _(revision +1, small)_

## v2.9.0 · Rev 2026.11.21-R29
- Windows-managed drivers are labelled and explained instead of looking checkable  _(revision +3, notable)_

## v2.8.0 · Rev 2026.11.21-R26
- Only report a restart when this run actually installed a driver; report installed count  _(revision +3, notable)_

## v2.7.0 · Rev 2026.11.21-R23
- Fix driver install hanging at UAC: worker path with spaces was split into two arguments  _(revision +3, notable)_

## v2.6.0 · Rev 2026.11.21-R20
- Exe now carries its own version and revision in file properties  _(revision +3, notable)_

## v2.5.0 · Rev 2026.11.21-R17
- Versioning: every change bumps the revision, enforced in CI  _(revision +3, notable)_

## v2.4.0 · Rev 2026.11.21-R14
- Performance overhaul: parallel update checks (14.9 s -> 2.8 s), parallel driver downloads, SMBIOS serial read instead of PowerShell (320 ms -> 0.16 ms), 24-hour on-disk catalog cache.  _(revision +10, major)_
- A device whose catalog check fails is now reported as "Check Failed" instead of "Up to Date".
- Driver packages are named by job index, so two devices with similar names can no longer overwrite each other's package.
- Installer: per-user install with no admin prompt at setup, explicit shortcut icon, closes a running app so in-place updates succeed.

## v2.3.0 · Rev 2026.11.21-R4
- Baseline revision: hardware scan, Microsoft Update Catalog checks, one-click driver installation, silent elevated installer.
