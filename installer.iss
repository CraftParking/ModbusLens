; Inno Setup script for ModbusLens.
; Packages the --onedir PyInstaller build (dist\ModbusLens\) into a normal Windows
; installer -- no runtime self-extraction, so it avoids the whole class of onefile
; bootloader bugs (non-ASCII usernames, AV races) documented in notes.md, and reads as
; a normal app install to AV heuristics instead of a suspicious single self-extracting
; exe.
;
; Build first: python build_exe.py onedir
; Then compile: "C:\Users\PlayGround\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss

#define MyAppName "ModbusLens"
#define MyAppVersion "2.2.0"
#define MyAppPublisher "CraftParking"
#define MyAppURL "https://github.com/CraftParking/ModbusLens"
#define MyAppExeName "ModbusLens.exe"

[Setup]
AppId={{63F509AF-5533-4DF6-92AB-30304F77F485}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=installer_output
OutputBaseFilename=ModbusLens-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
SetupIconFile=assets\icon.ico
WizardStyle=modern
DisableProgramGroupPage=yes
; Program Files needs admin rights to write to -- expected/normal for a per-machine
; desktop app install, triggers one UAC prompt during setup.
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\ModbusLens\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
