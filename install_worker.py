"""
Silent Elevated Installation Worker
Runs elevated via UAC and silently installs each driver package using pnputil.
Writes live progress and log updates to JSON/text files for the GUI to display in real-time.
Zero visible console or powershell windows.
"""

import os
import sys
import json
import time
import re
import subprocess
import winreg

CREATE_NO_WINDOW = 0x08000000

def get_silent_startupinfo():
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return si

def check_system_reboot_pending():
    reasons = []
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending")
        winreg.CloseKey(key)
        reasons.append("Component Servicing")
    except Exception:
        pass

    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired")
        winreg.CloseKey(key)
        reasons.append("Windows Update")
    except Exception:
        pass

    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager")
        val, _ = winreg.QueryValueEx(key, "PendingFileRenameOperations")
        winreg.CloseKey(key)
        if val:
            reasons.append("Pending File Operations")
    except Exception:
        pass

    return len(reasons) > 0

def update_status(status_file, data):
    try:
        tmp_file = status_file + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        if os.path.exists(status_file):
            os.remove(status_file)
        os.rename(tmp_file, status_file)
    except Exception:
        pass

def main():
    if len(sys.argv) < 2:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    else:
        base_dir = sys.argv[1]

    plan_file = os.path.join(base_dir, "install_plan.json")
    status_file = os.path.join(base_dir, "install_status.json")
    log_file = os.path.join(base_dir, "install_log.txt")

    if not os.path.exists(plan_file):
        update_status(status_file, {
            "state": "error",
            "error": "Plan file not found",
            "percent": 0
        })
        return

    with open(plan_file, "r", encoding="utf-8") as f:
        plan = json.load(f)

    devices = plan.get("devices", [])
    total = len(devices)
    reboot_required = False

    update_status(status_file, {
        "state": "starting",
        "total": total,
        "current_index": 0,
        "completed_count": 0,
        "current_device": "Initializing...",
        "percent": 0,
        "log_line": f"Starting silent installation of {total} driver package(s)...",
        "reboot_required": False
    })

    with open(log_file, "a", encoding="utf-8") as log_f:
        log_f.write(f"\n=======================================================\n")
        log_f.write(f"Driver Installation Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_f.write(f"Packages to install: {total}\n")
        log_f.write(f"=======================================================\n")

        for idx, dev in enumerate(devices):
            dev_name = dev.get("name", f"Device #{idx+1}")
            extract_dir = dev.get("extract_dir", "")

            # Update progress before installing this driver
            pct = int((idx) * 100 / total) if total > 0 else 0
            update_status(status_file, {
                "state": "installing",
                "total": total,
                "current_index": idx + 1,
                "completed_count": idx,
                "current_device": dev_name,
                "percent": pct,
                "log_line": f"Installing driver ({idx+1}/{total}): {dev_name}...",
                "reboot_required": reboot_required
            })

            log_f.write(f"\n>>> [{idx+1}/{total}] Installing: {dev_name}\n")
            log_f.write(f"    Source: {extract_dir}\n")
            log_f.flush()

            if not os.path.isdir(extract_dir):
                log_f.write("    Error: Directory does not exist.\n")
                continue

            # Run pnputil silently
            # Format: pnputil /add-driver "<extract_dir>\*.inf" /subdirs /install
            inf_target = os.path.join(extract_dir, "*.inf")
            cmd = ["pnputil", "/add-driver", inf_target, "/subdirs", "/install"]

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    creationflags=CREATE_NO_WINDOW,
                    startupinfo=get_silent_startupinfo()
                )
                output = proc.stdout + "\n" + proc.stderr
                log_f.write(output + "\n")
                log_f.write(f"    Exit code: {proc.returncode}\n")
                log_f.flush()

                if proc.returncode == 3010 or "reboot required" in output.lower():
                    reboot_required = True

            except Exception as e:
                log_f.write(f"    Exception during pnputil: {e}\n")
                log_f.flush()

            # Small pause to allow file writes
            time.sleep(0.3)

    # Check system registry for pending reboot
    if not reboot_required and check_system_reboot_pending():
        reboot_required = True

    # Mark as completed
    update_status(status_file, {
        "state": "finished",
        "total": total,
        "current_index": total,
        "completed_count": total,
        "current_device": "Complete",
        "percent": 100,
        "log_line": "All driver packages have been installed into the system.",
        "reboot_required": reboot_required
    })

if __name__ == "__main__":
    main()
