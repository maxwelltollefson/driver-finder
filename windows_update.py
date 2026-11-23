"""Read-only view of driver packages Windows Update is offering.

Uses the Windows Update Agent COM API, which needs no elevation for a search.
Nothing here installs anything: Windows Update owns these packages, and the app's
job is to stop being blind to them.
"""

import json
import re
import subprocess
import time

CREATE_NO_WINDOW = 0x08000000
CACHE_TTL_SECONDS = 600
_CACHE = {"stamp": 0.0, "data": None}

SEARCH_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$session = New-Object -ComObject Microsoft.Update.Session
$searcher = $session.CreateUpdateSearcher()
$result = $searcher.Search("IsInstalled=0 and Type='Driver'")
$items = @()
foreach ($u in $result.Updates) {
    $items += [pscustomobject]@{
        Title       = $u.Title
        Version     = $(if ($u.DriverVerDate) { $u.DriverVerDate.ToString('yyyy-MM-dd') } else { '' })
        Manufacturer = $u.DriverManufacturer
        Model       = $u.DriverModel
        SizeMB      = [math]::Round(($u.MaxDownloadSize / 1MB), 1)
        HardwareIds = ($u.DriverHardwareID -join '|')
        Reboot      = [bool]$u.RebootRequired
    }
}
if ($items.Count -eq 0) { '[]' } else { $items | ConvertTo-Json -Compress }
"""


TITLE_VERSION = re.compile(r"\(([0-9][0-9.]{3,})\)\s*$")


def list_driver_offers(timeout=180, force=False):
    """Pending Windows Update driver packages, or an error message.

    The agent search takes ~24 s on a warm cache-free machine, so results are
    cached: re-opening the window must not re-run it.
    """
    if not force and _CACHE["data"] is not None \
            and (time.time() - _CACHE["stamp"]) < CACHE_TTL_SECONDS:
        return _CACHE["data"]
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", SEARCH_SCRIPT],
            capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
    except FileNotFoundError:
        return {"offers": [], "error": "PowerShell is not available"}
    except subprocess.TimeoutExpired:
        return {"offers": [], "error": "Windows Update did not answer in time"}
    except Exception as exc:
        return {"offers": [], "error": str(exc)}

    raw = (proc.stdout or "").strip()
    if not raw:
        detail = ((proc.stderr or "").strip() or "no output").splitlines()[-1]
        return {"offers": [], "error": detail[:200]}
    try:
        data = json.loads(raw)
    except Exception as exc:
        return {"offers": [], "error": "could not read the answer: %s" % exc}
    if isinstance(data, dict):
        data = [data]

    offers = []
    for item in data:
        hardware_ids = [part for part in str(item.get("HardwareIds") or "").split("|") if part]
        title = item.get("Title") or ""
        version_match = TITLE_VERSION.search(title)
        offers.append({
            "title": title,
            "version": (version_match.group(1) if version_match else ""),
            "date": item.get("Version") or "",
            "manufacturer": item.get("Manufacturer") or "",
            "model": item.get("Model") or "",
            "size_mb": item.get("SizeMB") or 0,
            "hardware_ids": hardware_ids,
            "reboot": bool(item.get("Reboot")),
        })
    result = {"offers": offers, "error": ""}
    _CACHE["stamp"] = time.time()
    _CACHE["data"] = result
    return result


def match_to_devices(offers, devices):
    """Attach the local device a Windows Update offer targets, when the hardware
    IDs line up. Matching is on hardware ID only — never on the title."""
    by_hwid = {}
    for device in devices or []:
        for hwid in device.get("hardware_ids") or []:
            by_hwid.setdefault(str(hwid).upper(), device)
        if device.get("primary_hwid"):
            by_hwid.setdefault(str(device["primary_hwid"]).upper(), device)

    for offer in offers:
        match = None
        for hwid in offer.get("hardware_ids", []):
            match = by_hwid.get(str(hwid).upper())
            if match:
                break
        offer["device"] = (match or {}).get("description", "")
        offer["instance_id"] = (match or {}).get("instance_id", "")
        offer["installed_version"] = (match or {}).get("driver_version", "")
    return offers
