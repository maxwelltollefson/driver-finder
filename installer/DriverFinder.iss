; Driver Finder installer
; Built by build.ps1 / GitHub Actions. Users run DriverFinder-Setup.exe.

#define AppName "Driver Finder"
#define AppVersion "2.11.1"
#define AppPublisher "Maxwell Tollefson"
#define AppExe "Driver Finder.exe"

[Setup]
AppId={{7E4B1C2A-9F30-4D6E-A1B8-2C5D8E0F4A61}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppVerName={#AppName} {#AppVersion}
VersionInfoVersion=2.11.1.0
VersionInfoProductName={#AppName}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
DefaultDirName={localappdata}\Programs\Driver Finder
DefaultGroupName=Driver Finder
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=DriverFinder-Setup
SetupIconFile=..\app_icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\dist\Driver Finder\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Driver Finder"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\{#AppExe}"; IconIndex: 0
Name: "{autodesktop}\Driver Finder"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\{#AppExe}"; IconIndex: 0
Name: "{group}\Uninstall Driver Finder"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch Driver Finder"; Flags: nowait postinstall skipifsilent
