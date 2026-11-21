"""Fail when app code changes without a revision bump.

Compares HEAD against the previous commit. Documentation and workflow files do
not require a bump; anything that ships in the app does.
"""

import subprocess
import sys

CODE_SUFFIXES = (".py", ".iss", ".spec")
EXEMPT_PATHS = (
    "version.py",
    "bump_version.py",
    "tools/",
)


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()


def show(ref, path):
    result = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""


def main():
    changed = [f for f in git("diff", "--name-only", "HEAD~1", "HEAD").splitlines() if f.strip()]
    if not changed:
        print("No changed files in this commit.")
        return 0

    code_changed = [
        f for f in changed
        if f.endswith(CODE_SUFFIXES) and not any(f.startswith(p) or f == p for p in EXEMPT_PATHS)
    ]

    if not code_changed:
        print("Only docs/config changed - no revision bump required.")
        return 0

    if show("HEAD~1", "version.py") != show("HEAD", "version.py"):
        print("App code changed and version.py was updated.")
        return 0

    print("::error::App code changed without a revision bump:")
    for filename in code_changed:
        print(f"  - {filename}")
    print("")
    print("Run one of:")
    print('  python bump_version.py --kind small   --note "..."   # +1 wording/typo/one-liner')
    print('  python bump_version.py --kind notable --note "..."   # +3 user-visible fix or feature')
    print('  python bump_version.py --kind major   --note "..."   # +10 overhaul')
    return 1


if __name__ == "__main__":
    sys.exit(main())
