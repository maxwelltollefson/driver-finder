"""Driver backup, offline export and rollback bookkeeping.

`pnputil /export-driver` runs WITHOUT elevation (verified on Windows 26H2), so
backing up before an install costs no UAC prompt. Only removing a package during
a rollback needs the elevated worker.

An exported package keeps its own oemNN.inf name, so a rollback is:
    pnputil /delete-driver <inf bound now> /uninstall /force
    pnputil /add-driver "<backup>\\<inf>" /install
"""

import json
import os
import re
import subprocess
import time

import paths

CREATE_NO_WINDOW = 0x08000000
THIRD_PARTY_INF = re.compile(r"^oem\d+\.inf$", re.IGNORECASE)
MANIFEST = "manifest.json"


def _run(args, timeout=180):
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()
    except FileNotFoundError:
        return 127, "pnputil was not found on this system"
    except Exception as exc:
        return 1, str(exc)


def is_third_party_inf(name):
    """Inbox (Windows-owned) drivers cannot be exported or rolled back."""
    return bool(THIRD_PARTY_INF.match((name or "").strip()))


def slug(text, limit=38):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (text or "").strip())
    return (cleaned or "driver")[:limit].strip("_") or "driver"


def current_inf(instance_id):
    """The INF bound to a device right now, read fresh from Windows."""
    if not instance_id:
        return ""
    temp = os.path.join(paths.cache_dir(), "one_device.xml")
    try:
        if os.path.exists(temp):
            os.remove(temp)
        rc, _ = _run(["pnputil", "/enum-devices", "/instanceid", instance_id,
                      "/drivers", "/format", "xml", "/output-file", temp], timeout=60)
        if rc != 0 or not os.path.exists(temp):
            return ""
        with open(temp, "r", encoding="utf-8", errors="replace") as handle:
            text = handle.read()
        match = re.search(r"<DriverName>([^<]+)</DriverName>", text)
        return match.group(1).strip() if match else ""
    except Exception:
        return ""
    finally:
        try:
            if os.path.exists(temp):
                os.remove(temp)
        except Exception:
            pass


def export_driver(inf_name, dest_dir):
    """Export one package. Returns (ok, message)."""
    if not is_third_party_inf(inf_name):
        return False, f"{inf_name or 'unknown INF'} is managed by Windows, so there is nothing to back up"
    os.makedirs(dest_dir, exist_ok=True)
    rc, output = _run(["pnputil", "/export-driver", inf_name, dest_dir])
    if rc != 0:
        return False, output.splitlines()[-1] if output else f"pnputil exited {rc}"
    has_inf = any(name.lower().endswith(".inf") for name in os.listdir(dest_dir))
    if not has_inf:
        return False, "pnputil reported success but no .inf was written"
    return True, output.splitlines()[-1] if output else "exported"


def export_all_drivers(dest_dir):
    """Every third-party package on the machine — the offline pack primitive."""
    os.makedirs(dest_dir, exist_ok=True)
    rc, output = _run(["pnputil", "/export-driver", "*", dest_dir], timeout=900)
    if rc != 0:
        return False, output.splitlines()[-1] if output else f"pnputil exited {rc}"
    infs = sum(1 for root, _dirs, files in os.walk(dest_dir)
               for name in files if name.lower().endswith(".inf"))
    return infs > 0, f"{infs} package(s) exported"


def validate_inf(path):
    """Structural check on a backup INF before anything is uninstalled.

    The rollback deletes the bound package *before* re-adding the backup, so a
    backup we cannot read would leave the device driverless. INF files are
    UTF-16LE or ANSI, never guess the encoding from the first bytes alone.
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read(262144)
    except OSError as exc:
        return False, "cannot read the file: %s" % exc
    if not raw:
        return False, "the file is empty"

    text = None
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            text = raw.decode("utf-16")
        except Exception:
            text = None
    if text is None:
        for encoding in ("utf-8", "cp1252", "latin-1"):
            try:
                text = raw.decode(encoding)
                break
            except Exception:
                continue
    if text is None:
        return False, "the file is not readable text"

    lowered = text.lower()
    if "[version]" not in lowered:
        return False, "no [Version] section"
    if "signature=" not in lowered:
        return False, "no Signature entry"
    return True, "ok"


def backup_devices(devices, label="manual backup", app_version=""):
    """Export the current driver for each device that has a third-party package."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = os.path.join(paths.backups_dir(), stamp)
    os.makedirs(base, exist_ok=True)

    entries = []
    for index, device in enumerate(devices):
        inf = device.get("driver_name") or device.get("inf_name") or ""
        if not is_third_party_inf(inf):
            continue
        description = device.get("description") or device.get("name") or "Device"
        folder = f"{index:02d}_{slug(description)}"
        ok, message = export_driver(inf, os.path.join(base, folder))
        entries.append({
            "instance_id": device.get("instance_id", ""),
            "description": description,
            "device_class": device.get("class_name") or device.get("category", ""),
            "inf": inf,
            "version": device.get("driver_version", ""),
            "version_date": device.get("driver_date", ""),
            "provider": device.get("driver_provider", ""),
            "folder": folder,
            "ok": ok,
            "message": message,
        })

    manifest = {
        "schema": 1,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "created_local": time.time(),
        "label": label,
        "app_version": app_version,
        "machine": os.environ.get("COMPUTERNAME", ""),
        "entry_count": len([entry for entry in entries if entry["ok"]]),
        "entries": entries,
    }
    with open(os.path.join(base, MANIFEST), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    if not entries:
        try:
            os.rmdir(base)
        except OSError:
            pass
        manifest["base"] = ""
        return manifest

    manifest["base"] = base
    return manifest


def export_offline_pack(zip_path, progress=None):
    """Every third-party driver plus a README, zipped for a clean Windows install."""
    import shutil

    staging = os.path.join(paths.data_dir(), "offline-staging")
    if os.path.isdir(staging):
        shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)

    if progress:
        progress("Exporting driver packages...")
    ok, message = export_all_drivers(staging)
    if not ok:
        shutil.rmtree(staging, ignore_errors=True)
        return False, "", message

    readme = os.path.join(staging, "READ-ME-FIRST.txt")
    try:
        with open(readme, "w", encoding="utf-8") as handle:
            handle.write(
                "Driver Finder offline driver pack\n"
                "=================================\n\n"
                "Every third-party driver package that was installed on this PC.\n\n"
                "On a fresh Windows install, before you have network access:\n\n"
                "  1. Right-click the .inf for your network adapter and choose Install, or\n"
                "  2. Run this from an administrator prompt in this folder:\n"
                "       pnputil /add-driver *.inf /subdirs /install\n\n"
                "Then run the Driver Finder installer and let it check the catalog.\n"
            )
    except Exception:
        pass

    if progress:
        progress("Compressing (this is the slow part)...")
    base = zip_path[:-4] if zip_path.lower().endswith(".zip") else zip_path
    try:
        archive = shutil.make_archive(base, "zip", staging)
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        return False, "", "compression failed: %s" % exc
    shutil.rmtree(staging, ignore_errors=True)
    size_mb = os.path.getsize(archive) / 1048576.0 if os.path.exists(archive) else 0
    return True, archive, "%s, %.0f MB" % (message, size_mb)


def list_backups():
    """Newest first. Unreadable manifests are skipped, not fatal."""
    found = []
    root = paths.backups_dir()
    try:
        names = sorted(os.listdir(root), reverse=True)
    except OSError:
        return found
    for name in names:
        path = os.path.join(root, name, MANIFEST)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
            manifest["base"] = os.path.join(root, name)
            found.append(manifest)
        except Exception:
            continue
    found.sort(key=lambda item: item.get("created", ""), reverse=True)
    return found


def find_rollback(instance_id):
    """Newest successful backup entry for this device."""
    if not instance_id:
        return None, None
    for manifest in list_backups():
        for entry in manifest.get("entries", []):
            if entry.get("instance_id") == instance_id and entry.get("ok"):
                return manifest, entry
    return None, None


def backup_inf_path(manifest, entry):
    if not manifest or not entry:
        return ""
    folder = os.path.join(manifest.get("base", ""), entry.get("folder", ""))
    if not os.path.isdir(folder):
        return ""
    for name in os.listdir(folder):
        if name.lower() == (entry.get("inf") or "").lower():
            return os.path.join(folder, name)
    for name in os.listdir(folder):
        if name.lower().endswith(".inf"):
            return os.path.join(folder, name)
    return ""
