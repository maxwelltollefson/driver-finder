"""Self-update: check GitHub for a newer Driver Finder release and install it.

Flow: fetch the latest release -> compare versions -> hand the installer to
Windows after the user approves. The installer is per-user, so no UAC prompt.

Only a frozen (installed) build will install an update; a source run just opens
the release page.
"""

import json
import os
import re
import subprocess
import urllib.request

import paths

REPO = "maxwelltollefson/driver-finder"
LATEST_API = "https://api.github.com/repos/%s/releases/latest" % REPO
RELEASES_PAGE = "https://github.com/%s/releases/latest" % REPO
ASSET_NAME = "DriverFinder-Setup.exe"
USER_AGENT = "Driver-Finder-Updater"

CREATE_NO_WINDOW = 0x08000000


class UpdateError(Exception):
    """The release could not be checked or downloaded."""


def _silent_startupinfo():
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return startupinfo


def version_tuple(text):
    if not text:
        return ()
    return tuple(int(part) for part in re.findall(r"\d+", str(text)))


def is_newer(remote_version, current_version):
    """True when remote_version is a higher version than current_version."""
    remote = version_tuple(remote_version)
    current = version_tuple(current_version)
    if not remote:
        return False

    length = max(len(remote), len(current))
    remote = remote + (0,) * (length - len(remote))
    current = current + (0,) * (length - len(current))
    return remote > current


def fetch_latest_release(timeout=10):
    """Return the newest published release as a dict. Raises UpdateError."""
    request = urllib.request.Request(
        LATEST_API,
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", "ignore"))
    except Exception as exc:
        raise UpdateError(str(exc) or "could not reach GitHub")

    asset = None
    for item in data.get("assets", []):
        if item.get("name") == ASSET_NAME:
            asset = item
            break

    if not asset:
        raise UpdateError("release has no %s asset" % ASSET_NAME)

    tag = str(data.get("tag_name") or "")
    return {
        "version": tag.lstrip("vV"),
        "tag": tag,
        "name": data.get("name") or tag,
        "notes": data.get("body") or "",
        "url": asset.get("browser_download_url") or "",
        "size": asset.get("size") or 0,
        "page": data.get("html_url") or RELEASES_PAGE,
    }


def download_installer(release, progress_cb=None):
    """Download the release installer, checking size and that it is an exe."""
    if not release.get("url"):
        raise UpdateError("release has no download URL")

    target_dir = os.path.join(paths.cache_dir(), "updates")
    os.makedirs(target_dir, exist_ok=True)
    destination = os.path.join(target_dir, ASSET_NAME)

    request = urllib.request.Request(release["url"], headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or release.get("size") or 0)
            downloaded = 0
            with open(destination, "wb") as handle:
                while True:
                    chunk = response.read(128 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        percent = int(downloaded * 100 / total) if total else 0
                        progress_cb(downloaded, total, percent)
    except Exception as exc:
        raise UpdateError(str(exc))

    expected = release.get("size") or 0
    actual = os.path.getsize(destination)
    if expected and actual != expected:
        raise UpdateError("size mismatch: expected %d bytes, got %d" % (expected, actual))

    with open(destination, "rb") as handle:
        if handle.read(2) != b"MZ":
            raise UpdateError("downloaded file is not a Windows executable")

    return destination


def launch_installer_and_relaunch(installer_path, app_exe, delay_seconds=2):
    """Run the installer, then reopen the app once it finishes.

    A helper process does the waiting so this app can exit first and let the
    installer replace its files.
    """
    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    script = (
        "Start-Sleep -Seconds %d; "
        "$p = Start-Process -FilePath %s -ArgumentList '/SILENT','/NORESTART' -Wait -PassThru; "
        "if ($p.ExitCode -eq 0) { Start-Process -FilePath %s }"
    ) % (delay_seconds, quote(installer_path), quote(app_exe))

    subprocess.Popen(
        ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-NonInteractive", "-Command", script],
        creationflags=CREATE_NO_WINDOW,
        startupinfo=_silent_startupinfo(),
    )
