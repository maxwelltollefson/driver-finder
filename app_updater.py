"""Application updates through winget.

winget has no JSON output (`--output` is rejected in 1.29), so the table is parsed
by slicing at the header row's word offsets — that survives localization, since the
column count and the id shape do not change. Ids look like `Publisher.App.EXE`:
one token, no spaces, at least one dot.

Nothing is ever installed silently in bulk: one package per explicit call.
"""

import re
import subprocess

CREATE_NO_WINDOW = 0x08000000
ID_PATTERN = re.compile(r"^[\w+.-]+\.[\w+.-]+$")
VERSIONISH = re.compile(r"^v?\d")


def _run(args, timeout=900):
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                              creationflags=CREATE_NO_WINDOW)
        return proc.returncode, (proc.stdout or ""), (proc.stderr or "")
    except FileNotFoundError:
        return 127, "", "winget is not installed on this system"
    except subprocess.TimeoutExpired:
        return 1, "", "winget timed out"
    except Exception as exc:
        return 1, "", str(exc)


def winget_version():
    rc, out, err = _run(["winget", "--version"], timeout=60)
    if rc != 0:
        return ""
    match = re.search(r"v?\d+\.\d+\.\d+", out + err)
    return match.group(0) if match else "installed"


def _column_offsets(header):
    return [match.start() for match in re.finditer(r"\S+", header)]


def parse_upgrade_table(text):
    """Rows of {name, id, version, available, source} from `winget upgrade` output."""
    lines = text.replace("\r\n", "\n").split("\n")
    rows = []

    separator = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped and set(stripped) <= {"-"} and len(stripped) > 20:
            separator = index
            break
    if separator is None or separator == 0:
        return rows

    header = lines[separator - 1]
    offsets = _column_offsets(header)
    if len(offsets) < 4:
        offsets = None

    for line in lines[separator + 1:]:
        if not line.strip():
            continue
        fields = None
        if offsets:
            bounds = offsets + [len(line)]
            fields = [line[bounds[i]:bounds[i + 1]].strip() for i in range(len(offsets))]
        if not fields or len(fields) < 4 or not ID_PATTERN.match(fields[1] or ""):
            fields = [part.strip() for part in re.split(r"\s{2,}", line.strip())]
        if len(fields) < 4 or not ID_PATTERN.match(fields[1] or ""):
            continue
        rows.append({
            "name": fields[0],
            "id": fields[1],
            "version": fields[2],
            "available": fields[3],
            "source": fields[4] if len(fields) > 4 else "",
        })
    return rows


def list_upgrades(include_unknown=True):
    if not winget_version():
        return {"updates": [], "error": "winget is not available on this Windows build", "raw": ""}
    args = ["winget", "upgrade", "--include-unknown", "--disable-interactivity"]
    if not include_unknown:
        args = ["winget", "upgrade", "--disable-interactivity"]
    rc, out, err = _run(args, timeout=300)
    combined = out + err
    rows = parse_upgrade_table(combined)
    error = ""
    if rc != 0 and not rows:
        error = (err.strip() or out.strip() or f"winget exited {rc}").splitlines()[-1][:200]
    return {"updates": rows, "error": error, "raw": combined}


def upgrade(package_id, silent=True):
    """Upgrade exactly one package. Returns (ok, output)."""
    if not package_id:
        return False, "no package id"
    args = ["winget", "upgrade", "--id", package_id, "--exact",
            "--accept-package-agreements", "--accept-source-agreements",
            "--disable-interactivity"]
    if silent:
        args.append("--silent")
    rc, out, err = _run(args, timeout=1800)
    combined = (out + err).strip()
    lowered = combined.lower()
    if rc == 0:
        return True, combined
    if "no applicable upgrade" in lowered or "no available upgrade" in lowered:
        return True, "Already current."
    return False, combined or f"winget exited {rc}"
