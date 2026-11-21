"""
Utility to create Windows Desktop Shortcuts for Driver Finder.
Creates both a .lnk shortcut (with custom icon) and a .bat launcher on the user's Desktop.
Executes 100% silently without command windows.
"""

import os
import sys
import subprocess

import paths

CREATE_NO_WINDOW = 0x08000000

def get_silent_startupinfo():
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return si

def get_desktop_path():
    user_profile = os.environ.get('USERPROFILE', '')
    if user_profile:
        d = os.path.join(user_profile, 'Desktop')
        if os.path.isdir(d):
            return d

    try:
        cmd = '[Environment]::GetFolderPath(\'Desktop\')'
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=get_silent_startupinfo()
        )
        path = res.stdout.strip()
        if path and os.path.isdir(path):
            return path
    except Exception:
        pass
            
    return os.path.expanduser('~/Desktop')

def create_desktop_shortcuts(project_dir=None):
    if not project_dir:
        project_dir = paths.resource_dir()

    desktop = get_desktop_path()
    if not os.path.isdir(desktop):
        return False

    if paths.is_frozen():
        pythonw_exe = sys.executable
        main_py = ""
        project_dir = os.path.dirname(sys.executable)
        icon_ico = sys.executable
    else:
        main_py = os.path.join(project_dir, "main.py")
        icon_ico = os.path.join(project_dir, "app_icon.ico")
        python_exe = sys.executable
        pythonw_exe = os.path.join(os.path.dirname(python_exe), "pythonw.exe")
        if not os.path.exists(pythonw_exe):
            pythonw_exe = python_exe

    # A frozen exe takes no arguments; a source run needs the quoted .py path.
    shortcut_args = '"' + main_py + '"' if main_py else ""
    shortcut_args = shortcut_args.replace("'", "''")

    # 1. Create .lnk Shortcut via PowerShell / WScript.Shell silently
    lnk_path = os.path.join(desktop, "Driver Finder.lnk")
    ps_script = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut("{lnk_path}")
    $Shortcut.TargetPath = "{pythonw_exe}"
    $Shortcut.Arguments = '{shortcut_args}'
    $Shortcut.WorkingDirectory = "{project_dir}"
    $Shortcut.Description = "Scan PC hardware and check for manufacturer driver updates"
    if (Test-Path "{icon_ico}") {{
        $Shortcut.IconLocation = "{icon_ico},0"
    }}
    $Shortcut.Save()
    """
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=get_silent_startupinfo()
        )
    except Exception:
        pass

    # 2. Source runs also get a batch launcher. An installed exe does not need one.
    if paths.is_frozen():
        return True

    bat_path = os.path.join(desktop, "Launch Driver Finder.bat")
    try:
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write("@echo off\r\n")
            f.write(f'start "" "{pythonw_exe}" "{main_py}"\r\n')
            f.write("exit\r\n")
    except Exception:
        pass

    return True

if __name__ == "__main__":
    create_desktop_shortcuts()
