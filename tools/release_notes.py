"""Write release notes for a version from CHANGELOG.md.

Usage:
    python tools/release_notes.py                      # notes for the version in version.py
    python tools/release_notes.py 2.8.0                # notes for a specific version
    python tools/release_notes.py -o notes.md          # write UTF-8 file (preferred)
    python tools/release_notes.py > notes.md           # stdout, forced UTF-8

Encoding matters: a shell redirect on Windows can emit cp1252, turning "·" into a
lone 0xB7 byte that GitHub renders as a replacement character.

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
    argv = sys.argv[1:]
    output_path = None
    if "-o" in argv:
        index = argv.index("-o")
        output_path = argv[index + 1]
        del argv[index:index + 2]

    version = argv[0] if argv else current_version()
    section = section_for(version)

    if not section:
        print(f"error: CHANGELOG.md has no '## v{version}' section", file=sys.stderr)
        return 1

    heading, body = section
    body = REVISION_MARKER.sub("", body)
    notes = f"**{heading}**\n\n{body}\n\n{INSTALL_HINT}\n"

    if output_path:
        pathlib.Path(output_path).write_text(notes, encoding="utf-8", newline="\n")
        print(f"wrote {output_path}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
