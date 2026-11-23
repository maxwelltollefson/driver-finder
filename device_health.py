"""Explain devices that are not working, without inventing problems.

`pnputil /enum-devices` has no /problems filter, so exact problem codes come from
`Get-PnpDevice`. Crucially, a healthy machine reports dozens of problem codes that
are all phantom (CM_PROB_PHANTOM / CM_PROB_DEVICE_NOT_THERE) — hardware that was
once attached. Reporting those would be the scare-counter pattern this app avoids,
so they are filtered out and counted separately.
"""

import json
import subprocess

CREATE_NO_WINDOW = 0x08000000

# CM_PROB code -> (title, what it means, what actually fixes it)
PROBLEM_CODES = {
    1: ("Device not configured",
        "Windows has no configuration for this device yet.",
        "Reinstall the manufacturer driver, or run Scan for hardware changes."),
    3: ("Out of memory",
        "Windows could not allocate the resources this device needs.",
        "Close other programs and reboot; if it returns, disable other devices in the same slot."),
    10: ("Device cannot start",
        "The driver loaded but the hardware did not respond.",
        "Reinstall the manufacturer driver, then reboot. If a newer driver was just installed, roll it back."),
    12: ("Not enough free resources",
        "Two devices are asking for the same resources.",
        "Reboot; if it persists, move the card to another slot or disable the conflicting device."),
    14: ("Device cannot work properly",
        "The device needs a resource it cannot get.",
        "Reboot, then try a different slot or port."),
    18: ("Reinstall the drivers",
        "Windows flagged the driver for a clean reinstall.",
        "Reinstall the manufacturer driver."),
    19: ("Registry problem",
        "The driver's registry entry is damaged.",
        "Reinstall the manufacturer driver."),
    22: ("Disabled",
        "The device was deliberately turned off.",
        "Enable it again if you want it to work."),
    28: ("No driver installed",
        "Windows has no driver for this device at all.",
        "Install the manufacturer driver — this is what the Check Updates button is for."),
    31: ("Device not working properly",
        "Windows could not load a driver for this device.",
        "Install the correct driver; if one is installed, reinstall it."),
    32: ("Driver service failed to start",
        "The driver's service could not be started.",
        "Reinstall the driver, or roll back to the previous version."),
    37: ("Driver failed to load",
        "A previous driver for this device could not unload.",
        "Reboot. If it persists, reinstall the driver."),
    39: ("Driver is corrupt or missing",
        "The driver file is damaged or absent.",
        "Reinstall the manufacturer driver."),
    43: ("Driver reported a failure",
        "The driver itself told Windows it stopped working — commonly a crashed GPU driver.",
        "Reinstall or update the driver. For a GPU, a clean install of the manufacturer package is the usual fix."),
    44: ("Removal was blocked",
        "A driver refused to let the device be removed.",
        "Reboot, then retry the removal."),
    48: ("Driver blocked by policy",
        "Windows blocked this driver as incompatible.",
        "Install a driver the catalog lists for this Windows version."),
    52: ("No signature on driver",
        "The driver is unsigned, so Windows will not load it.",
        "Use a signed package from the manufacturer."),
}

# Not real problems: the hardware is not attached right now.
IGNORED_CODES = {24, 45}


def _powershell_json(script, timeout=120):
    command = [
        "powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-Command", script,
    ]
    proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                          creationflags=CREATE_NO_WINDOW)
    text = (proc.stdout or "").strip()
    if not text:
        return None, ((proc.stderr or "").strip() or f"PowerShell exited {proc.returncode}")
    try:
        return json.loads(text), ""
    except Exception as exc:
        return None, f"could not parse PowerShell output: {exc}"


def scan_problems():
    """Present devices with a real problem, plus how many phantom nodes were skipped."""
    script = (
        "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
        # CM_PROB_NONE is 0, not null: filtering on null reports every healthy
        # device as broken (153 devices on the dev machine).
        "Where-Object { [int]$_.Problem -ne 0 } | "
        "Select-Object InstanceId, FriendlyName, Class, Status, "
        "@{n='Problem';e={[int]$_.Problem}}, "
        "@{n='ErrorCode';e={[int]$_.ConfigManagerErrorCode}} | "
        "ConvertTo-Json -Compress"
    )
    data, error = _powershell_json(script)
    if data is None:
        return {"devices": [], "ignored": 0, "error": error}
    if isinstance(data, dict):
        data = [data]

    devices, ignored = [], 0
    for item in data:
        code = item.get("Problem")
        try:
            code = int(code)
        except (TypeError, ValueError):
            continue
        if code == 0:
            continue
        if code in IGNORED_CODES:
            ignored += 1
            continue
        title, meaning, fix = PROBLEM_CODES.get(
            code,
            (f"Device problem {code}",
             "Windows reported a problem with this device.",
             "Reinstall the manufacturer driver, then reboot."),
        )
        devices.append({
            "instance_id": item.get("InstanceId") or "",
            "description": item.get("FriendlyName") or "(unnamed device)",
            "device_class": item.get("Class") or "",
            "status": item.get("Status") or "",
            "code": code,
            "error_code": item.get("ErrorCode", 0),
            "title": title,
            "meaning": meaning,
            "fix": fix,
            "critical": code in (10, 28, 31, 39, 43),
        })

    devices.sort(key=lambda entry: (not entry["critical"], entry["device_class"], entry["description"]))
    return {"devices": devices, "ignored": ignored, "error": ""}


def explain(device):
    """(title, meaning, fix) for one entry produced by scan_problems."""
    return device.get("title", ""), device.get("meaning", ""), device.get("fix", "")
