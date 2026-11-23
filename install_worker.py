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

def create_restore_point(description="Driver Finder driver update"):
    """Ask Windows for a checkpoint. Failure must never block the install."""
    script = (
        "try { Checkpoint-Computer -Description '" + description +
        "' -RestorePointType MODIFY_SETTINGS -ErrorAction Stop; 'RESTORE_POINT_OK' } "
        "catch { 'RESTORE_POINT_FAILED: ' + $_.Exception.Message }"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", script],
            capture_output=True, text=True, timeout=180,
            creationflags=CREATE_NO_WINDOW, startupinfo=get_silent_startupinfo()
        )
        output = ((proc.stdout or "") + (proc.stderr or "")).strip()
        if "RESTORE_POINT_OK" in output:
            # Windows silently skips checkpoints within 24h of the last one.
            return True, "Restore point requested (Windows may reuse one from the last 24 hours)."
        return False, output.splitlines()[-1] if output else "restore point request failed"
    except Exception as exc:
        return False, str(exc)


def run_pnputil(args, timeout=300):
    try:
        proc = subprocess.run(
            ["pnputil"] + args, capture_output=True, text=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW, startupinfo=get_silent_startupinfo()
        )
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()
    except Exception as exc:
        return 1, str(exc)


def rollback_driver(plan, status_file, log_file):
    """Restore a backed-up package: remove what is bound now, re-add the backup."""
    inf = plan.get("inf", "")
    backup_inf = plan.get("backup_inf_path", "")
    device = plan.get("device", "device")

    def report(state, percent, line):
        update_status(status_file, {
            "state": state, "job": "rollback_driver", "total": 3,
            "current_device": device, "percent": percent,
            "log_line": line, "reboot_required": False,
        })

    with open(log_file, "a", encoding="utf-8") as log_f:
        log_f.write("\n=======================================================\n")
        log_f.write("Rollback: %s -> %s\n" % (device, os.path.basename(backup_inf)))
        log_f.write("=======================================================\n")

        if not backup_inf or not os.path.isfile(backup_inf):
            report("error", 0, "Backup package is missing - nothing was changed.")
            log_f.write("Aborted: backup INF not found at %r\n" % backup_inf)
            return

        import driver_backup
        valid, why = driver_backup.validate_inf(backup_inf)
        if not valid:
            report("error", 0, "The backup package is unreadable (%s) - nothing was changed." % why)
            log_f.write("Aborted: backup INF failed validation: %s\n" % why)
            log_f.flush()
            return

        report("installing", 10, "Removing the current driver package...")
        if inf:
            rc, out = run_pnputil(["/delete-driver", inf, "/uninstall", "/force"])
            log_f.write("delete-driver %s -> %s\n%s\n" % (inf, rc, out))
            if rc not in (0, 3010):
                report("error", 10, "Could not remove the current package; nothing was changed.")
                log_f.flush()
                return

        report("installing", 55, "Reinstalling the backed-up driver...")
        rc, out = run_pnputil(["/add-driver", backup_inf, "/install"])
        log_f.write("add-driver %s -> %s\n%s\n" % (backup_inf, rc, out))
        ok_add = rc in (0, 259, 3010)

        report("installing", 85, "Rescanning hardware...")
        rc_scan, out_scan = run_pnputil(["/scan-devices"])
        log_f.write("scan-devices -> %s\n%s\n" % (rc_scan, out_scan))
        log_f.flush()

        if ok_add:
            report("finished", 100,
                   "Rolled back %s. Reboot to finish." % device)
        else:
            report("error", 100,
                   "The old package was removed but the backup did not install. "
                   "Use Device Manager to reinstall a driver for this device.")


def update_status(status_file, data):
    try:
        tmp_file = status_file + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        # os.replace is atomic: the GUI never sees the file half-written or missing.
        os.replace(tmp_file, status_file)
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

    job = plan.get("job", "install_drivers")
    if job == "rollback_driver":
        rollback_driver(plan, status_file, log_file)
        return

    devices = plan.get("devices", [])
    total = len(devices)
    reboot_required = False
    installed_ok = 0
    already_current = 0

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

    if plan.get("restore_point") and total:
        update_status(status_file, {
            "state": "starting", "total": total, "current_index": 0,
            "completed_count": 0, "current_device": "Creating restore point...",
            "percent": 0, "log_line": "Creating a System Restore point...",
            "reboot_required": False,
        })
        point_ok, point_msg = create_restore_point()
        plan["_restore_point"] = {"ok": point_ok, "message": point_msg}

    with open(log_file, "a", encoding="utf-8") as log_f:
        log_f.write(f"\n=======================================================\n")
        if plan.get("_restore_point"):
            log_f.write("Restore point: %s (%s)\n" % (
                "ok" if plan["_restore_point"]["ok"] else "failed",
                plan["_restore_point"]["message"]))
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

                if proc.returncode in (0, 3010):
                    installed_ok += 1
                elif proc.returncode == 259:
                    # ERROR_NO_MORE_ITEMS: "already exists / up-to-date on device"
                    # — pnputil did its job, there was just nothing to change.
                    already_current += 1

                if proc.returncode == 3010 or "reboot required" in output.lower():
                    reboot_required = True

            except Exception as e:
                log_f.write(f"    Exception during pnputil: {e}\n")
                log_f.flush()

            # Small pause to allow file writes
            time.sleep(0.3)

    # Only claim a reboot when we actually installed something: machines often
    # carry an unrelated pending reboot (pending file renames from Edge or
    # Windows Update) that has nothing to do with these drivers.
    if not reboot_required and installed_ok and check_system_reboot_pending():
        reboot_required = True

    if total == 0:
        final_line = "No driver packages were queued."
    elif installed_ok == 0:
        final_line = "No driver packages could be installed. See install_log.txt."
    else:
        final_line = f"Installed {installed_ok} of {total} driver package(s)."
        if already_current:
            final_line += f" {already_current} were already current."

    # Mark as completed
    update_status(status_file, {
        "state": "finished",
        "total": total,
        "current_index": total,
        "completed_count": total,
        "current_device": "Complete",
        "percent": 100,
        "installed_count": installed_ok,
        "already_current_count": already_current,
        "log_line": final_line,
        "reboot_required": reboot_required
    })

if __name__ == "__main__":
    main()
