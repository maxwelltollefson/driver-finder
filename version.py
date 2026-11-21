"""Single source of truth for the app version and revision.

Every change gets a new revision number, and the size of the jump shows the
scale of the change:

    small    +1    wording, typo, one-line fix
    notable  +3    user-visible fix, behaviour change, new feature
    major   +10    overhaul

Bump with:
    python bump_version.py --kind small --note "what changed"

That updates this file, installer/DriverFinder.iss, and CHANGELOG.md.
`tools/check_revision.py` fails the build if app code changes without a bump.
"""

APP_VERSION = "2.5.0"

APP_REVISION_NUMBER = 17
APP_REVISION_DATE = "2026.11.21"

APP_REVISION = f"{APP_REVISION_DATE}-R{APP_REVISION_NUMBER}"
APP_BUILD_INFO = f"v{APP_VERSION} [Rev {APP_REVISION}]"
