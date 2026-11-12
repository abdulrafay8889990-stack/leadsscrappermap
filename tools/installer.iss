; Inno Setup script: turns the portable app folder into one "Lead Scraper Setup.exe".
; Built by tools\build.ps1 (needs Inno Setup 6: winget install JRSoftware.InnoSetup).
; Installs per user (no admin rights): %LOCALAPPDATA%\Programs\Lead Scraper, with Start Menu
; + Desktop shortcuts and an entry in Settings > Apps. User data (lead history, exports) lives
; elsewhere and is kept on uninstall.
;
; Uninstall uses uninstall.ps1 (run by Windows' signed PowerShell) instead of Inno's unins000.exe:
; Windows Smart App Control blocks unsigned executables, which would make "Uninstall" do nothing.

#define AppName "Lead Scraper"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\build\Lead Scraper"
#endif

[Setup]
AppId={{8C4F5D7A-2B1E-4F6A-9C3D-5E7B1A2C4D6F}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
DefaultDirName={localappdata}\Programs\{#AppName}
DisableDirPage=auto
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename={#AppName} Setup
SetupIconFile=..\assets\app.ico
Uninstallable=no
Compression=lzma2/ultra64
SolidCompression=yes
LZMANumBlockThreads=4
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; leftovers of an earlier setup version that used Inno's own uninstaller
Type: files; Name: "{app}\unins000.*"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{8C4F5D7A-2B1E-4F6A-9C3D-5E7B1A2C4D6F}_is1"; Flags: deletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\LeadScraper"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\LeadScraper"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#AppName}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\LeadScraper"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#AppVersion}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\LeadScraper"; ValueType: string; ValueName: "Publisher"; ValueData: "{#AppName}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\LeadScraper"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\app\assets\app.ico"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\LeadScraper"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\LeadScraper"; ValueType: string; ValueName: "UninstallString"; ValueData: "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\uninstall.ps1"""
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\LeadScraper"; ValueType: string; ValueName: "QuietUninstallString"; ValueData: "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{app}\uninstall.ps1"" -Silent"
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\LeadScraper"; ValueType: dword; ValueName: "NoModify"; ValueData: 1
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\LeadScraper"; ValueType: dword; ValueName: "NoRepair"; ValueData: 1
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\LeadScraper"; ValueType: dword; ValueName: "EstimatedSize"; ValueData: 236000

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; WorkingDir: "{app}"; IconFilename: "{app}\app\assets\app.ico"; Comment: "Collect business leads from Google Maps"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; WorkingDir: "{app}"; IconFilename: "{app}\app\assets\app.ico"; Comment: "Collect business leads from Google Maps"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
