"""
Driver Finder - Main Entry Point
Launches the GUI. Shortcuts are created by the installer or the in-app button,
never automatically on launch.
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

    # Ensure custom app icon exists
    icon_path = os.path.join(base_dir, "app_icon.ico")
    if not os.path.exists(icon_path):
        try:
            import generate_icon
            generate_icon.generate_icon(icon_path)
        except Exception as e:
            print(f"Warning: could not generate icon: {e}")

    # Launch GUI
    import gui
    gui.main()

if __name__ == "__main__":
    main()
