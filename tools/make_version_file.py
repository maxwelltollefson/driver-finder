"""Generate a PyInstaller version resource so the exe reports its version.

Without this, the built exe has blank version properties in Explorer, Task
Manager and file dialogs, even though the app title and installer carry the
revision. ProductVersion includes the revision code.

Usage: python tools/make_version_file.py <output-path>
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from version import APP_VERSION, APP_REVISION, APP_BUILD_INFO  # noqa: E402

COMPANY = "Maxwell Tollefson"
PRODUCT = "Driver Finder"
EXE_NAME = "Driver Finder.exe"

TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', '{company}'),
        StringStruct('FileDescription', '{product}'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('InternalName', '{product}'),
        StringStruct('LegalCopyright', ''),
        StringStruct('OriginalFilename', '{exe}'),
        StringStruct('ProductName', '{product}'),
        StringStruct('ProductVersion', '{build_info}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python tools/make_version_file.py <output-path>")

    parts = [int(p) for p in APP_VERSION.split(".")]
    while len(parts) < 4:
        parts.append(0)

    content = TEMPLATE.format(
        version_tuple=tuple(parts),
        version=APP_VERSION,
        build_info=APP_BUILD_INFO,
        company=COMPANY,
        product=PRODUCT,
        exe=EXE_NAME,
    )

    out = pathlib.Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    print(f"version resource: {out} -> {APP_BUILD_INFO}")


if __name__ == "__main__":
    main()
