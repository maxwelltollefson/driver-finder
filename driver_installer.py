"""
Driver Installer Engine
Handles downloading, expanding, and elevated installation of Windows driver packages
with zero visible command prompt or powershell windows.
"""

import os
import sys
import json
import time
import subprocess
import urllib.request
import winreg

import paths

CREATE_NO_WINDOW = 0x08000000

def get_silent_startupinfo():
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0 # SW_HIDE
    return si


def check_system_reboot_pending():
    """Checks Windows Registry for system-wide reboot pending indicators."""
    reasons = []

    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending")
        winreg.CloseKey(key)
        reasons.append("Component Servicing pending reboot")
    except Exception:
        pass

    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired")
        winreg.CloseKey(key)
        reasons.append("Windows Update pending reboot")
    except Exception:
        pass

    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager")
        val, _ = winreg.QueryValueEx(key, "PendingFileRenameOperations")
        winreg.CloseKey(key)
        if val:
            reasons.append("Pending file replacements on reboot")
    except Exception:
        pass

    return len(reasons) > 0, reasons


def download_driver_file(url, dest_path, progress_callback=None):
    """
    Downloads file from url to dest_path with progress reporting.
    progress_callback(downloaded_bytes, total_bytes, percent)
    """
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    with urllib.request.urlopen(req, timeout=30) as resp:
        total_size = int(resp.headers.get('Content-Length', 0))
        downloaded = 0
        chunk_size = 128 * 1024 # 128 KB chunks

        with open(dest_path, 'wb') as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    pct = int(downloaded * 100 / total_size) if total_size > 0 else 0
                    progress_callback(downloaded, total_size, pct)

    return os.path.exists(dest_path) and os.path.getsize(dest_path) > 0


def extract_cab(cab_path, extract_dir):
    """
    Expands a Microsoft Cabinet (.cab) file silently into extract_dir with zero window popups.
    Returns list of discovered .inf files.
    """
    os.makedirs(extract_dir, exist_ok=True)
    cmd = f'expand -F:* "{cab_path}" "{extract_dir}"'
    proc = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
        startupinfo=get_silent_startupinfo()
    )
    
    inf_files = []
    for root, _, files in os.walk(extract_dir):
        for f in files:
            if f.lower().endswith('.inf'):
                inf_files.append(os.path.join(root, f))

    return inf_files


def _ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def launch_elevated_worker(download_dir):
    """
    Launches the installer elevated via UAC with no console window.
    A source run starts install_worker.py under pythonw. A frozen exe
    relaunches itself with --install-worker.
    Returns True if launch initiated successfully.
    """
    # Clean existing status file before starting
    status_file = os.path.join(download_dir, "install_status.json")
    if os.path.exists(status_file):
        try:
            os.remove(status_file)
        except Exception:
            pass

    if paths.is_frozen():
        file_path = sys.executable
        arg_list = ["--install-worker", download_dir]
    else:
        worker_script = os.path.join(paths.resource_dir(), "install_worker.py")
        python_exe = sys.executable
        pythonw_exe = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
        if not os.path.exists(pythonw_exe):
            pythonw_exe = python_exe
        file_path = pythonw_exe
        arg_list = [worker_script, download_dir]

    args_ps = ",".join(_ps_quote(arg) for arg in arg_list)
    ps_cmd = (
        f"Start-Process -FilePath {_ps_quote(file_path)} "
        f"-ArgumentList {args_ps} -Verb RunAs -WindowStyle Hidden"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=get_silent_startupinfo()
        )
        return proc.returncode == 0
    except Exception as e:
        print(f"Error launching elevated worker: {e}")
        return False


def restart_computer(delay_seconds=10):
    """Initiates a graceful Windows restart silently in the background."""
    cmd = f'shutdown /r /t {delay_seconds} /c "Restarting to finish installing updated drivers."'
    subprocess.Popen(
        cmd,
        shell=True,
        creationflags=CREATE_NO_WINDOW,
        startupinfo=get_silent_startupinfo()
    )


def cancel_restart():
    """Aborts a pending Windows restart silently."""
    subprocess.Popen(
        "shutdown /a",
        shell=True,
        creationflags=CREATE_NO_WINDOW,
        startupinfo=get_silent_startupinfo()
    )
