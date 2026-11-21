"""
Driver Finder - Main Entry Point
Checks prerequisites, ensures desktop shortcut exists, and launches the GUI.
"""

import os
import sys

import paths

def main():
    # Frozen Setup.exe relaunches itself elevated to run pnputil.
    if len(sys.argv) >= 3 and sys.argv[1] == "--install-worker":
        import install_worker
        sys.argv = [sys.argv[0], sys.argv[2]]
        install_worker.main()
        return

    base_dir = paths.resource_dir()

    # 1. Ensure custom app icon exists
    icon_path = os.path.join(base_dir, "app_icon.ico")
    if not os.path.exists(icon_path):
        try:
            import generate_icon
            generate_icon.generate_icon(icon_path)
        except Exception as e:
            print(f"Warning: could not generate icon: {e}")

    # 2. Ensure Desktop shortcut exists
    try:
        import create_shortcut
        desktop = create_shortcut.get_desktop_path()
        lnk = os.path.join(desktop, "Driver Finder.lnk")
        bat = os.path.join(desktop, "Launch Driver Finder.bat")
        if not os.path.exists(lnk) and not os.path.exists(bat):
            create_shortcut.create_desktop_shortcuts(base_dir)
    except Exception as e:
        print(f"Shortcut setup note: {e}")

    # 3. Launch GUI
    import gui
    gui.main()

if __name__ == "__main__":
    main()
