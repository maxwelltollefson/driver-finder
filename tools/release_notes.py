"""Write release notes for a version from CHANGELOG.md.

Usage:
    python tools/release_notes.py            # notes for the version in version.py
    python tools/release_notes.py 2.8.0      # notes for a specific version
    python tools/release_notes.py > notes.md

Exits non-zero when the version has no changelog section, so CI fails rather
than publishing an empty release.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"

INSTALL_HINT = (
    "### Install\n\n"
    "Download `DriverFinder-Setup.exe` below and run it. No Python required and "
    "no administrator rights needed to install. Driver updates themselves ask for "
    "elevation once."
)

REVISION_MARKER = re.compile(r"\s*_\(revision \+?\d+, [a-z]+\)_")


def current_version():
    sys.path.insert(0, str(ROOT))
    import version  # noqa: E402

    return version.APP_VERSION


def section_for(version):
    text = CHANGELOG.read_text(encoding="utf-8")
    header = re.compile(rf"^## v{re.escape(version)}\b.*$", re.MULTILINE)
    match = header.search(text)
    if not match:
        return None

    body_start = match.end()
    next_header = re.compile(r"^## ", re.MULTILINE).search(text, body_start)
    body = text[body_start: next_header.start() if next_header else len(text)]
    return match.group(0).lstrip("# ").strip(), body.strip("\n")


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else current_version()
    section = section_for(version)

    if not section:
        print(f"error: CHANGELOG.md has no '## v{version}' section", file=sys.stderr)
        return 1

    heading, body = section
    body = REVISION_MARKER.sub("", body)
    print(f"**{heading}**")
    print()
    print(body)
    print()
    print(INSTALL_HINT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
