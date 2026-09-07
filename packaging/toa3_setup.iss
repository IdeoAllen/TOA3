; TOA3 Setup - Inno Setup 6
; 对齐 TOA2 toa_setup.iss；独立 AppId，可与 TOA2 并存。
#define MyAppName "Training Operations Assistant 3 (TOA3)"
#define MyAppNameCN "赋能培训运营助手 TOA3（运营宝）"
#define MyAppDirName "TOA3"
#ifndef MyAppVersion
#define MyAppVersion "3.0.0"
#endif
#define MyAppPublisher "YCZH"
#define MyAppExeName "TOA3.exe"
#define MyAppURL "mailto:chengchengzhao@eautosh.com"
#ifndef MyReleaseDir
  #define MyReleaseDir "TOA3-v" + MyAppVersion + "-win64"
#endif
#ifndef SetupIconFile
  #define SetupIconFile "..\avatars\logo.ico"
#endif

[Setup]
AppId={{B9D4F2E3-5C6A-7D8E-9F0A-1B2C3D4E5F6A}
AppName={#MyAppNameCN}
AppVersion={#MyAppVersion}
AppVerName={#MyAppNameCN} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppDirName}
DefaultGroupName={#MyAppDirName}
DisableProgramGroupPage=yes
DisableDirPage=auto
UsePreviousAppDir=no
UsePreviousGroup=yes
UsePreviousTasks=no
UsePreviousSetupType=no
OutputDir=dist
#ifndef SetupBaseName
  #define SetupBaseName "TOA3-Setup-v{#MyAppVersion}"
#endif
OutputBaseFilename={#SetupBaseName}
SetupIconFile={#SetupIconFile}
UninstallDisplayName={#MyAppNameCN}
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppNameCN}
VersionInfoProductVersion={#MyAppVersion}
CloseApplications=force
RestartApplications=yes
CloseApplicationsFilter=*.exe
AppMutex=YCZH_TOA3_RELEASE_MUTEX
SetupLogging=yes
AllowNoIcons=yes
Uninstallable=yes
CreateUninstallRegKey=yes
UpdateUninstallLogAppName=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
english.BeveledLabel=TOA3
english.SetupAppTitle=Install TOA3
english.SetupWindowTitle=Install TOA3 %1
english.UninstallAppTitle=Uninstall TOA3
english.UninstallAppFullTitle=Uninstall TOA3
english.WelcomeLabel1=Welcome to TOA3 Setup
english.WelcomeLabel2=This will install [name/ver] on your computer.%n%nClose other apps before continuing.%n%nNo license is required during setup. After install, ask your admin for a TOA2 license key and activate inside the app (online).
english.FinishedLabel=[name] has been installed. Launch it and activate with a license key from your admin when ready.
english.ConfirmUninstall=Remove %1 completely?
english.UninstalledAll=[name] was removed successfully.

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"

[Files]
Source: "dist\{#MyReleaseDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; 正式包必须带 _internal（onedir）。禁止 skipifsourcedoesntexist，缺目录应编译失败而非装成巨型 onefile。
Source: "dist\{#MyReleaseDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\{#MyReleaseDir}\avatars\*"; DestDir: "{app}\avatars"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\{#MyReleaseDir}\resources\*"; DestDir: "{app}\resources"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\{#MyReleaseDir}\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "dist\{#MyReleaseDir}\ui\*"; DestDir: "{app}\ui"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "dist\{#MyReleaseDir}\README.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "dist\{#MyReleaseDir}\config\*"; DestDir: "{app}\config"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs
Source: "dist\{#MyReleaseDir}\config\app.yml"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "dist\{#MyReleaseDir}\config\app.release.yml"; DestDir: "{app}\config"; Flags: ignoreversion skipifsourcedoesntexist
Source: "dist\{#MyReleaseDir}\config\license.json"; DestDir: "{app}\config"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\TOA3"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\avatars\logo.ico"; Comment: "{#MyAppNameCN}"
Name: "{group}\Uninstall TOA3"; Filename: "{uninstallexe}"; Comment: "Uninstall TOA3"
Name: "{userdesktop}\TOA3"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\avatars\logo.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "安装完成后启动 TOA3"; Flags: nowait postinstall skipifsilent

[InstallDelete]
Type: filesandordirs; Name: "{app}\output"
Type: filesandordirs; Name: "{app}\cache"
; 旧版误用 onefile 巨型 exe 无 _internal，升级时清掉残留避免仍点到坏入口
Type: filesandordirs; Name: "{app}\_MEI*"
Type: files; Name: "{app}\config\admin_bootstrap_code.txt"
Type: files; Name: "{app}\config\app.dev.yml"
Type: files; Name: "{app}\unins000.msg"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\output"
Type: filesandordirs; Name: "{app}\cache"

[Code]
var
  OptionalLicenseKey: String;

function GetPreviousInstallDir(): String;
var
  S: String;
  UninstallKey: String;
begin
  Result := '';
  UninstallKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1';
  if RegQueryStringValue(HKCU, UninstallKey, 'InstallLocation', S) or
     RegQueryStringValue(HKLM, UninstallKey, 'InstallLocation', S) then
    Result := RemoveBackslashUnlessRoot(S);
end;

function InitializeSetup(): Boolean;
var
  ParamLicense: String;
  PrevDir: String;
  LocalDir: String;
begin
  Result := True;
  OptionalLicenseKey := '';
  ParamLicense := ExpandConstant('{param:LICENSE}');
  if ParamLicense <> '' then
    OptionalLicenseKey := Trim(ParamLicense);

  if not IsAdminInstallMode then
  begin
    LocalDir := ExpandConstant('{localappdata}\Programs\{#MyAppDirName}');
    PrevDir := GetPreviousInstallDir();
    if (PrevDir <> '') and (Pos('Program Files', PrevDir) > 0) then
    begin
      WizardForm.DirEdit.Text := LocalDir;
      Log('Redirect install from Program Files to per-user: ' + LocalDir);
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  ExePath: String;
  Args: String;
  PyDll: String;
begin
  if CurStep = ssPostInstall then
  begin
    PyDll := ExpandConstant('{app}\_internal\python311.dll');
    if not FileExists(PyDll) then
      MsgBox('安装不完整：缺少 _internal\python311.dll。' + #13#10 +
        '请勿使用旧版单文件包；请重新下载正式 TOA3-Setup 安装。' + #13#10 +
        '否则启动会出现 Failed to load Python DLL / _MEI。', mbError, MB_OK);

    if OptionalLicenseKey <> '' then
    begin
      ExePath := ExpandConstant('{app}\{#MyAppExeName}');
      if FileExists(ExePath) then
      begin
        Args := '--activate-license "' + OptionalLicenseKey + '"';
        if Exec(ExePath, Args, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode) then
        begin
          if ResultCode <> 0 then
            Log('Optional post-install activate failed, exit=' + IntToStr(ResultCode) + ' (user can activate in app)');
        end;
      end;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{app}\data');
    if DirExists(DataDir) then
    begin
      if MsgBox('Also delete local user data under %LOCALAPPDATA%\YCZH-TOA3?' + #13#10 +
                'Choose No to keep data for reinstall.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(ExpandConstant('{localappdata}\YCZH-TOA3'), True, True, True);
      end;
    end;
  end;
end;
