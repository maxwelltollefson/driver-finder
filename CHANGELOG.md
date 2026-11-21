# Changelog

Driver Finder. Every change bumps the revision number; the size of the jump
shows the scale: **small +1**, **notable +3**, **major +10**. Bump with
`python bump_version.py --kind small|notable|major --note "..."`.

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
