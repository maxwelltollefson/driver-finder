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


def _version_key(text):
    """Comparable form of a driver version: 24.70.0.3 -> (24, 70, 0, 3)."""
    parts = re.findall(r"\d+", str(text or ""))
    return tuple(int(part) for part in parts[:4])


def verify_devices(entries):
    """Read back what Windows actually bound after the install.

    pnputil's exit code says the package was added; it does not say the device
    works. Two sources, because neither alone is enough: pnputil XML carries the
    bound version and status (Get-PnpDevice returns DriverVersion = null on real
    hardware), and Get-PnpDevice carries the problem code.
    """
    import driver_backup

    ids = [entry.get("instance_id") for entry in entries if entry.get("instance_id")]
    if not ids:
        return []

    # Instance IDs come back with different hex casing from WMI than from pnputil,
    # so every comparison here is case-insensitive.
    quoted = ",".join("'" + str(i).replace("'", "''") + "'" for i in ids)
    script = (
        "$ids = @(" + quoted + "); "
        "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
        "Where-Object { $ids -contains $_.InstanceId } | "
        "Select-Object InstanceId, Status, @{n='Problem';e={[int]$_.Problem}} | "
        "ConvertTo-Json -Compress"
    )
    problems = {}
    present = set()
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", script],
            capture_output=True, text=True, timeout=180,
            creationflags=CREATE_NO_WINDOW, startupinfo=get_silent_startupinfo()
        )
        raw = (proc.stdout or "").strip()
        data = json.loads(raw) if raw else []
        if isinstance(data, dict):
            data = [data]
        for item in data:
            key = str(item.get("InstanceId") or "").upper()
            present.add(key)
            problems[key] = int(item.get("Problem") or 0)
    except Exception:
        pass

    results = []
    for entry in entries:
        instance_id = entry.get("instance_id") or ""
        key = instance_id.upper()
        expected = entry.get("expected_version") or ""
        state = driver_backup.device_state(instance_id)
        bound = state.get("version") or ""
        status = state.get("status") or ""
        problem = problems.get(key, 0)

        if ids and key not in present:
            verdict, detail = "failed", "The device is no longer present after the update."
        elif problem and problem not in (24, 45):
            verdict, detail = "failed", "Windows reports problem code %d after the update." % problem
        elif expected and bound and _version_key(bound)[:3] != _version_key(expected)[:3]:
            verdict = "mismatch"
            detail = "Windows still reports %s, not the %s that was installed." % (bound, expected)
        elif status and status.lower() not in ("started", "ok"):
            verdict, detail = "needs_reboot", "Device state is '%s', which usually clears on restart." % status
        else:
            verdict, detail = "ok", "Running %s, device reports %s." % (bound or expected or "?", status or "OK")

        results.append({
            "name": entry.get("name", ""),
            "instance_id": instance_id,
            "expected_version": expected,
            "actual_version": bound,
            "status": status,
            "problem": problem,
            "verdict": verdict,
            "detail": detail,
        })
    return results


def rollback_driver(plan, status_file, log_file):
    """Restore backed-up packages: remove what is bound now, re-add the backup.

    Accepts either one device (inf/backup_inf_path/device) or a list under
    "devices", so reverting a whole batch costs a single UAC approval.
    """
    jobs = plan.get("devices") or []
    if not jobs and (plan.get("inf") or plan.get("backup_inf_path")):
        jobs = [{"inf": plan.get("inf", ""), "backup_inf_path": plan.get("backup_inf_path", ""),
                 "device": plan.get("device", "device")}]
    if not jobs:
        update_status(status_file, {"state": "error", "percent": 0,
                                    "log_line": "Nothing to roll back."})
        return

    import driver_backup

    total = len(jobs)
    done = 0
    failures = []
    with open(log_file, "a", encoding="utf-8") as log_f:
        log_f.write("\n=======================================================\n")
        log_f.write("Rollback of %d device(s)\n" % total)
        log_f.write("=======================================================\n")
        log_f.flush()

        for index, job in enumerate(jobs, start=1):
            inf = job.get("inf", "")
            backup_inf = job.get("backup_inf_path", "")
            device = job.get("device", "device")
            percent = int((index - 1) * 100 / max(1, total))
            update_status(status_file, {
                "state": "installing", "job": "rollback_driver", "total": total,
                "current_index": index, "current_device": device, "percent": percent,
                "log_line": "Rolling back (%d/%d): %s" % (index, total, device),
                "reboot_required": False,
            })

            if not backup_inf or not os.path.isfile(backup_inf):
                failures.append("%s: backup package is missing" % device)
                log_f.write("SKIP %s: backup INF not found at %r\n" % (device, backup_inf))
                continue
            valid, why = driver_backup.validate_inf(backup_inf)
            if not valid:
                failures.append("%s: backup unreadable (%s)" % (device, why))
                log_f.write("SKIP %s: INF failed validation (%s)\n" % (device, why))
                continue

            if inf:
                rc, out = run_pnputil(["/delete-driver", inf, "/uninstall", "/force"])
                log_f.write("delete-driver %s -> %s\n%s\n" % (inf, rc, out))
                if rc not in (0, 3010):
                    failures.append("%s: could not remove %s" % (device, inf))
                    continue
            rc, out = run_pnputil(["/add-driver", backup_inf, "/install"])
            log_f.write("add-driver %s -> %s\n%s\n" % (backup_inf, rc, out))
            if rc not in (0, 259, 3010):
                failures.append("%s: backup did not install" % device)
                continue
            done += 1

        run_pnputil(["/scan-devices"])
        log_f.flush()

    verification = verify_devices([{"name": job.get("device", ""),
                                    "instance_id": job.get("instance_id", "")} for job in jobs])
    failed_verify = [item for item in verification if item["verdict"] == "failed"]

    if failures or failed_verify:
        summary = "Rolled back %d of %d. %d still need attention." % (
            done, total, len(failures) + len(failed_verify))
        state = "error"
    else:
        summary = "Rolled back %d device(s). Reboot to finish." % done
        state = "finished"

    update_status(status_file, {
        "state": state, "job": "rollback_driver", "total": total,
        "current_index": total, "current_device": "Complete", "percent": 100,
        "rolled_back": done, "failures": failures, "verification": verification,
        "log_line": summary, "reboot_required": False,
    })


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

    verification = verify_devices(devices) if total else []
    failed_verify = [item for item in verification if item["verdict"] == "failed"]

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
        "verification": verification,
        "verification_failures": len(failed_verify),
        "log_line": final_line + (
            " %d device(s) did not come back healthy." % len(failed_verify)
            if failed_verify else " Every device verified."),
        "reboot_required": reboot_required
    })

if __name__ == "__main__":
    main()
