"""Print version fields as KEY=VALUE lines for GitHub Actions step outputs."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import version  # noqa: E402

print(f"tag=v{version.APP_VERSION}")
print(f"label=Driver Finder {version.APP_VERSION}")
print(f"revision={version.APP_REVISION}")
print(f"build_info={version.APP_BUILD_INFO}")
