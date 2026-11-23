# IObit / iTop feature map for Driver Finder

Decision document. What in the IObit + iTop lineup is worth taking into Driver Finder,
what is marketing, and in what order to build it.

Surveyed: Driver Booster 13, Advanced SystemCare 18/19, IObit Uninstaller 16,
Smart Defrag 12, Software Updater 9, iTop Easy Desktop 4, iTop Screen Recorder,
iTop Data Recovery, iTop VPN, DualSafe, iTop PDF, Smart Game Booster.

---

## 1. The governing rule

**Take mechanisms, not categories.**

Driver Finder works today because it does one thing and does not lie about it: it
enumerates real devices, asks the Microsoft Update Catalog for real packages, filters
by architecture, and refuses to touch storage controllers without consent. Every
feature below is judged on whether it extends that trust, not on whether a competitor
ships it.

The IObit suite is a *bundle of 12 products* with a shared marketing voice. Copying
its scope would turn a credible driver tool into the thing SmartScreen warns about.
What is worth taking is a specific, short list of engineering mechanisms that
Driver Booster actually charges money for, plus three adjacent utilities that can be
built honestly on data Driver Finder already has.

---

## 2. What is worth building

### Tier 1 — build first (trust / reversibility)

| # | Feature | Source | Mechanism | Effort | Risk |
|---|---------|--------|-----------|--------|------|
| 1 | **Driver backup + rollback** | Driver Booster PRO ("auto backup multiple versions of drivers for safer restore") | `pnputil /export-driver <oemNN.inf> <dir>` before install; keep versions; roll back with `pnputil /delete-driver ... /uninstall /force` then re-add the exported INF | M | Low |
| 2 | **Restore point before a batch install** | Software Updater ("auto restore point before updates") | Elevated worker creates a checkpoint before the first package; skip + report if System Protection is off | S | Low |
| 3 | **Device Health panel** | Driver Booster ("fix 35+ device errors") | `Get-PnpDevice` problem codes, explained per code, with the fix that applies (reinstall, roll back, enable, remove node) | M | Low |
| 4 | **Offline driver pack export** | Driver Booster ("update and install network drivers offline") | `pnputil /export-driver * <dir>` → ZIP of all third-party INFs + this app's installer, so a fresh Windows install has its NIC/Wi-Fi drivers without a network | S | Low |

These four convert the app's current promise ("installs at your own risk") into
("installs, and can undo it"). That is the single biggest differentiator against
Driver Booster, and it is cheap: `pnputil` already exposes `/export-driver`,
`/delete-driver`, `/enable-device`, `/disable-device` on this machine (verified).

### Tier 1.5 — build second (breadth, near-zero maintenance)

| # | Feature | Source | Mechanism | Effort | Risk |
|---|---------|--------|-----------|--------|------|
| 5 | **App updates** | Software Updater ("1,100+ apps, one click, official sources") | `winget upgrade` for the catalog + `winget upgrade --id <id>` per app. No catalog to maintain, official vendor sources, already present on Windows 11 | M | Low-Med |

This is the highest-value item in the whole map and the cheapest per unit of user
benefit: **28 upgrades were pending on this machine** at time of survey. It reaches
Software Updater's outcome without owning a catalog of 1,100 download URLs — the part
of that product that rots fastest. Per-app opt-in only; never a silent "update
everything" (winget silent installers break apps that need a UI).

### Tier 2 — build if the app grows into "system health"

| # | Feature | Source | Mechanism | Effort | Risk |
|---|---------|--------|-----------|--------|------|
| 6 | **Startup impact (measured)** | ASC Startup Optimizer, Smart Defrag "clean startup" | Read `Microsoft-Windows-Diagnostics-Performance/Operational` events 101-110: Windows itself reports per-app boot/login time cost. Show measured milliseconds, not an invented score | M | Low |
| 7 | **Scheduled scans** | Driver Booster + Software Updater | Task Scheduler entry running a headless scan, writing results the GUI reads on next launch | S | Low |
| 8 | **Space audit** | ASC "Disk Space Issues" | Real folder sizes (WinSxS, hiberfil, pagefile, `Windows.old`, per-app caches) + safe cleanup: temp, Delivery Optimization cache, `Dism /StartComponentCleanup` | M | Low |
| 9 | **One "System Health" tab** | ASC "AI mode / one-click daily plan" | The honest version: drivers, device health, app updates, startup cost, space — five real checks, no "1,247 problems found!" counter | M | Low |

Item 6 is the only one that answers the question the user actually asks ("why is my
boot slow") with numbers, because Windows already records them.

### Tier 3 — optional, only on explicit request

| # | Feature | Source | Why it is lower | Effort | Risk |
|---|---------|--------|-----------------|--------|------|
| 10 | Uninstall with leftover scan | IObit Uninstaller | Real value, but wrong-deletion risk means review-before-delete UI, per-item checkbox, full undo list | L | Med |
| 11 | Bloatware / Appx removal | Uninstaller 16 "Bloatware Remover" | Can break Store/Start/search if a dependency is removed; needs a curated allow-list | M | Med-High |
| 12 | TRIM + HDD defrag | Smart Defrag | Correct on NVMe (`Optimize-Volume -ReTrim`), pointless-to-harmful as marketed. Only worth a "last optimized" readout | S | Low |
| 13 | Silent auto-install during idle | Driver Booster PRO | Unattended driver installs are exactly how machines break. Opt-in, default off, and never for storage | M | High |

---

## 3. What to leave alone, and why

| Feature | Source | Verdict | Reason |
|---|---|---|---|
| Registry cleaning | ASC | **No** | No measured effect on boot or app launch; every "fix" is an irreversible edit to a machine whose registry is already self-consistent. The classic source of "optimizer broke my PC". |
| Turbo Boost / RAM release | ASC, iTop | **No** | Windows memory management is already correct. Forcing free RAM causes paging; the "before/after" numbers are cosmetic. |
| Game Boost | Driver Booster, Smart Game Booster | **No** | Temporary priority tweaks with no reproducible frame-time gain. |
| Missing game DLL fixer ("680+ DLLs") | Driver Booster | **No** | Redistributing game DLLs is a licensing problem and a malware vector. |
| Boot-time / registry defrag | Smart Defrag | **No** | Boot-time defrag predates SSD boot; registry defrag has no measured benefit and risks a corrupt hive. |
| Free-space defrag, game defrag | Smart Defrag | **No** | No measurable benefit on NTFS with modern prefetch/SuperFetch behaviour. |
| Privacy sweep (browser traces, "digital fingerprint") | ASC | **No** | Destructive to sessions, out of scope, and the fingerprint claim is not verifiable. |
| Antivirus / anti-spyware | ASC Ultimate, Malware Fighter | **No** | A real engine needs signatures, a cloud backend and 24/7 response; shipping a weak one would fight Defender and give false assurance. Irresponsible at this scale. |
| Secure file shredder | Uninstaller | **No** | On NVMe with wear levelling and TRIM, there is no overwrite guarantee. Promising "beyond recovery" would be false. |
| Software relocation | Uninstaller 16 | **No** | Moving installed programs across volumes breaks paths, services and COM registrations. |
| iTop Easy Desktop, Screen Recorder, Data Recovery, VPN, PDF, DualSafe | iTop | **No** | Different products, not features. Merging them is how bundles are born. |
| "23,000,000 driver database" | Driver Booster | **Not applicable** | Driver Finder's advantage is sourcing from the Microsoft Update Catalog and OEM sites — auditable provenance instead of a private database. Keep that and say so. |

---

> **Status:** Tier 1 and item 5 shipped in **v3.0.0**.

## 4. Recommended sequence

**v3.0 — "it can undo itself"** (Tier 1: items 1-4)
Backup, rollback, restore point, offline pack, device health. This is the release that
makes installing from this app defensible on someone else's machine.

**v3.1 — "everything is out of date"** (item 5)
App updates through winget, per-app selection. Biggest visible win per line of code.

**v3.2 — "why is it slow"** (items 6-8, 9 if wanted)
Measured startup cost, scheduled scans, honest space audit.

**Stop there unless asked.** Items 10-13 each carry a maintenance and support cost that
a one-person project cannot absorb indefinitely, and they are the ones that generate
"this tool deleted my…" reports.

---

## 5. Feasibility evidence (measured on this machine, 2026-11-21)

- `winget` v1.29.380 present; **28 upgrades available** → item 5 has immediate real output.
- `pnputil` supports `/export-driver`, `/delete-driver`, `/enable-device`, `/disable-device` → items 1-3 need no new mechanism.
- **250 third-party driver packages** installed → a full driver backup is a real artifact (hundreds of MB), and worth zipping.
- `Get-PnpDevice` reports **61 problem codes, all phantom/non-present** (59 × `CM_PROB_PHANTOM`, 2 × `CM_PROB_DEVICE_NOT_THERE`) → the device-health view must filter to *present* devices, or it invents 61 problems on a healthy machine. This is precisely the scare-counter pattern to avoid.
- `Get-ComputerRestorePoint` → **Access denied unelevated**; `DisableSR` unset, `RPSessionInterval=1` → restore points are possible but creation must happen inside the existing elevated worker, and the UI must handle "System Protection off".

---

## 6. Open questions

1. Does Driver Finder stay a driver tool (Tiers 1 + 1.5 only) or become a system-health
   tool (through Tier 2)? Everything above is a defensible stopping point.
2. Is winget acceptable as the app-update source, or does that need a catalog of our own?
3. For rollback, keep driver backups forever, or keep the last 2 versions per device and
   prune automatically?
