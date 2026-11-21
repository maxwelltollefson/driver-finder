# Changelog

Driver Finder. Every change bumps the revision number; the size of the jump
shows the scale: **small +1**, **notable +3**, **major +10**. Bump with
`python bump_version.py --kind small|notable|major --note "..."`.

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
