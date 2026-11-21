# Builds a windowed app folder, then an Inno Setup installer.
# Run from the repo root on Windows.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python -m pip install --upgrade pip
python -m pip install "pyinstaller>=6.0"

if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }

# Stamp the exe with the version and revision from version.py
python tools\make_version_file.py build\version_info.txt

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "Driver Finder" `
    --icon "app_icon.ico" `
    --add-data "app_icon.ico;." `
    --version-file "build\version_info.txt" `
    --hidden-import install_worker `
    --hidden-import paths `
    main.py

$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Error "Inno Setup 6 (ISCC.exe) was not found. Install it, or let GitHub Actions build the installer."
}

& $iscc "installer\DriverFinder.iss"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Output "Installer: dist\installer\DriverFinder-Setup.exe"
