#define Surum GetEnv("CEVIRIX_SURUM")
[Setup]
AppId={{6B2E4C1A-9F3D-4E7A-B0C2-CE51A1F0C001}
AppName=Çevirix PC
AppVersion={#Surum}
AppPublisher=Yasin Öztürk
DefaultDirName={localappdata}\Programs\Cevirix
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=cikti
OutputBaseFilename=CevirixPC-Kurulum
SetupIconFile=veri\cevirix.ico
UninstallDisplayIcon={app}\Cevirix.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "masaustu"; Description: "Masaüstüne kısayol koy"; Flags: checkedonce

[Files]
Source: "dist\Cevirix\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Çevirix PC"; Filename: "{app}\Cevirix.exe"
Name: "{autodesktop}\Çevirix PC"; Filename: "{app}\Cevirix.exe"; Tasks: masaustu

[Run]
Filename: "{app}\Cevirix.exe"; Description: "Çevirix PC'yi şimdi aç"; Flags: nowait postinstall skipifsilent
