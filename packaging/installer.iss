; Inno Setup script for the Shorts app (Windows installer).
; Built by the GitHub Actions workflow (.github/workflows/
; build-windows.yml) — it runs: iscc packaging\installer.iss
; from the repo root, after PyInstaller has produced
; dist\shorts-app.exe. FFmpeg is already bundled inside that
; exe by shorts-app.spec, so the installer only copies files.
; Per-user install: no admin rights needed.

#define AppVersion "1.0.2"

[Setup]
AppName=Shorts App
AppVersion={#AppVersion}
AppPublisher=Rayhan
DefaultDirName={autopf}\ShortsApp
DefaultGroupName=Shorts App
OutputDir=..\installer
OutputBaseFilename=ShortsApp-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\shorts-app.exe

[Files]
Source: "..\dist\shorts-app.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Shorts App"; Filename: "{app}\shorts-app.exe"
Name: "{autodesktop}\Shorts App"; Filename: "{app}\shorts-app.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "ডেস্কটপে শর্টকাট বানাও"; GroupDescription: "অতিরিক্ত:"

[Run]
Filename: "{app}\shorts-app.exe"; Description: "Shorts App চালাও"; Flags: nowait postinstall skipifsilent
