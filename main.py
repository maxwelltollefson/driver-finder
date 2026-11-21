"""
Driver Finder - Main Entry Point
Launches the GUI. Shortcuts are created by the installer or the in-app button,
never automatically on launch.
"""

import os
import sys

import paths

def _check_updates_cli():
    """Headless update check, for diagnosing the packaged build."""
    import json
    import updater
    from version import APP_VERSION

    try:
        release = updater.fetch_latest_release()
        result = {
            "ok": True,
            "current": APP_VERSION,
            "latest": release["version"],
            "newer": updater.is_newer(release["version"], APP_VERSION),
            "asset_url": release["url"],
            "asset_size": release["size"],
        }
    except Exception as exc:
        result = {"ok": False, "current": APP_VERSION, "error": f"{type(exc).__name__}: {exc}"}

    target = os.path.join(paths.cache_dir(), "update-check.json")
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    return result


def main():
    # Frozen Setup.exe relaunches itself elevated to run pnputil.
    if len(sys.argv) >= 3 and sys.argv[1] == "--install-worker":
        import install_worker
        sys.argv = [sys.argv[0], sys.argv[2]]
        install_worker.main()
        return

    if len(sys.argv) >= 2 and sys.argv[1] == "--check-updates":
        _check_updates_cli()
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
