#define MyVer "2.0"
[Setup]
AppName=mestre-clipador
AppVersion={#MyVer}
AppPublisher=mestre-clipador
DefaultDirName={localappdata}\Programs\mestre-clipador
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=mestre-clipador-setup-{#MyVer}
SetupIconFile=icone.ico
UninstallDisplayIcon={app}\mestre-clipador.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"

[Files]
Source: "..\dist\mestre-clipador\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\mestre-clipador"; Filename: "{app}\mestre-clipador.exe"
Name: "{autodesktop}\mestre-clipador"; Filename: "{app}\mestre-clipador.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\mestre-clipador.exe"; Description: "Abrir o mestre-clipador"; Flags: nowait postinstall skipifsilent
