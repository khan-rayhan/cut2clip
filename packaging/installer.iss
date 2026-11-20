; Inno Setup script for Cut2Clip (Windows installer).
; Built by the GitHub Actions workflow (.github/workflows/
; build-windows.yml) — it runs: iscc packaging\installer.iss
; from the repo root, after PyInstaller has produced
; dist\cut2clip.exe. FFmpeg is already bundled inside that
; exe by cut2clip.spec, so the installer only copies files.
; Per-user install: no admin rights needed.

#define AppVersion "1.0.3"

[Setup]
AppName=Cut2Clip
AppVersion={#AppVersion}
AppPublisher=Rayhan
DefaultDirName={autopf}\Cut2Clip
DefaultGroupName=Cut2Clip
OutputDir=..\installer
OutputBaseFilename=Cut2Clip-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\cut2clip.exe

[Files]
Source: "..\dist\cut2clip.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Cut2Clip"; Filename: "{app}\cut2clip.exe"
Name: "{autodesktop}\Cut2Clip"; Filename: "{app}\cut2clip.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "ডেস্কটপে শর্টকাট বানাও"; GroupDescription: "অতিরিক্ত:"

[Run]
Filename: "{app}\cut2clip.exe"; Description: "Cut2Clip চালাও"; Flags: nowait postinstall skipifsilent
