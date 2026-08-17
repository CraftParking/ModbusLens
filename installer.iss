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
; Same AppId across versions is what makes a newer Setup.exe recognized as an update to
; an existing install (same install path, one Apps & Features entry, not a duplicate) --
; never regenerate this GUID for ModbusLens.
;
; Update-safety: if ModbusLens.exe is running when the user installs an update, Windows
; would otherwise lock the file and the install would fail outright. CloseApplications
; detects that (via Windows' Restart Manager) and prompts to close it first;
; RestartApplications reopens it afterward.
CloseApplications=yes
RestartApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[InstallDelete]
; PyInstaller onedir's _internal folder's exact file set can change between versions
; (a dependency added or dropped) -- [Files] below only overwrites/adds what THIS
; version lists, it never removes files an older version left behind. Wipe it clean
; before every install/update so nothing orphaned survives across versions.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\ModbusLens\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
