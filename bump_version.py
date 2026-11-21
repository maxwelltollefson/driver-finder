"""Bump the app revision (and version) and record it in the changelog.

Every change needs a new revision. Pick the kind by scale:

    small    +1    wording, typo, one-line fix
    notable  +3    user-visible fix, behaviour change, new feature
    major   +10    overhaul

Version numbers follow the same kind: small bumps the patch, notable bumps the
minor, and major also bumps the minor unless --breaking is passed.

Usage:
    python bump_version.py --kind small --note "Fix crash on empty device list"
    python bump_version.py --kind major --note "Overhaul scan engine"
"""

import argparse
import datetime
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
VERSION_FILE = ROOT / "version.py"
ISS_FILE = ROOT / "installer" / "DriverFinder.iss"
CHANGELOG = ROOT / "CHANGELOG.md"

REVISION_STEP = {"small": 1, "notable": 3, "major": 10}


def read_value(text, name):
    match = re.search(rf'^{name} = "([^"]+)"', text, re.MULTILINE)
    if not match:
        sys.exit(f"version.py: could not find {name}")
    return match.group(1)


def write_value(text, name, value):
    new_text, count = re.subn(rf'^{name} = "[^"]+"', f'{name} = "{value}"', text, count=1, flags=re.MULTILINE)
    if count != 1:
        sys.exit(f"version.py: could not update {name}")
    return new_text


def read_int(text, name):
    match = re.search(rf"^{name} = (\d+)", text, re.MULTILINE)
    if not match:
        sys.exit(f"version.py: could not find {name}")
    return int(match.group(1))


def bump_semver(version, kind, breaking):
    major, minor, patch = (int(part) for part in version.split("."))
    if breaking:
        return f"{major + 1}.0.0"
    if kind == "small":
        return f"{major}.{minor}.{patch + 1}"
    return f"{major}.{minor + 1}.0"


def main():
    parser = argparse.ArgumentParser(description="Bump the Driver Finder revision.")
    parser.add_argument("--kind", choices=sorted(REVISION_STEP), required=True)
    parser.add_argument("--note", required=True, help="one line describing the change")
    parser.add_argument("--breaking", action="store_true", help="also bump the semver major")
    parser.add_argument("--date", help="YYYY.MM.DD override (defaults to today)")
    args = parser.parse_args()

    text = VERSION_FILE.read_text(encoding="utf-8")
    old_version = read_value(text, "APP_VERSION")
    old_revision_number = read_int(text, "APP_REVISION_NUMBER")

    new_revision_number = old_revision_number + REVISION_STEP[args.kind]
    new_version = bump_semver(old_version, args.kind, args.breaking)
    new_date = args.date or datetime.date.today().strftime("%Y.%m.%d")

    text = write_value(text, "APP_VERSION", new_version)
    text = write_value(text, "APP_REVISION_DATE", new_date)
    text = re.sub(r"^APP_REVISION_NUMBER = \d+", f"APP_REVISION_NUMBER = {new_revision_number}", text, count=1, flags=re.MULTILINE)
    VERSION_FILE.write_text(text, encoding="utf-8", newline="\n")

    if ISS_FILE.exists():
        iss = ISS_FILE.read_text(encoding="utf-8")
        iss = re.sub(r'^#define AppVersion "[^"]+"', f'#define AppVersion "{new_version}"', iss, count=1, flags=re.MULTILINE)
        iss = re.sub(r"^VersionInfoVersion=.*$", f"VersionInfoVersion={new_version}.0", iss, count=1, flags=re.MULTILINE)
        ISS_FILE.write_text(iss, encoding="utf-8", newline="\n")

    entry = (
        f"## v{new_version} · Rev {new_date}-R{new_revision_number}\n"
        f"- {args.note}  _(revision +{REVISION_STEP[args.kind]}, {args.kind})_\n\n"
    )
    if CHANGELOG.exists():
        existing = CHANGELOG.read_text(encoding="utf-8")
        marker = "## "
        index = existing.find(marker)
        if index >= 0:
            existing = existing[:index] + entry + existing[index:]
        else:
            existing = existing.rstrip() + "\n\n" + entry
    else:
        existing = "# Changelog\n\n" + entry
    CHANGELOG.write_text(existing, encoding="utf-8", newline="\n")

    print(f"v{old_version} R{old_revision_number}  ->  v{new_version} R{new_revision_number} ({new_date}-R{new_revision_number})")


if __name__ == "__main__":
    main()
