; Inno Setup script for Voiceprint Studio (声纹工坊).
; Build with:  iscc packaging\windows\voiceprint_studio.iss
; Expects the PyInstaller onedir output in dist\VoiceprintStudio\.

#define MyAppName "声纹工坊"
#define MyAppNameEn "Voiceprint Studio"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Voiceprint Studio"
#define MyAppExeName "VoiceprintStudio.exe"

[Setup]
AppId={{8C1A4D8E-5B7E-4A72-9F23-6E0B2C91A5D4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#MyAppNameEn} Installer
DefaultDirName={autopf}\Voiceprint Studio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=VoiceprintStudio-{#MyAppVersion}-Setup
SetupIconFile=..\..\src\voiceprint_studio\resources\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} ({#MyAppNameEn})
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0
DisableWelcomePage=no
LicenseFile=..\..\LICENSE.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\VoiceprintStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} 使用说明"; Filename: "{app}\README.md"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"