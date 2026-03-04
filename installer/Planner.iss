; Inno Setup script for Planner (Streamlit). Build after running build_dist.ps1 and download_python_embedded.ps1.

#define SourceDir "..\installer_sources"
; Version: bump when releasing a new installer (v2.1 = 2.1.0)
#define MyAppVersion "3.0.1"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}}
AppName=Planner
AppVerName=Planner {#MyAppVersion}
AppVersion={#MyAppVersion}
AppPublisher=Planner
AppPublisherURL=https://github.com
AppSupportURL=https://github.com
AppUpdatesURL=https://github.com
DefaultDirName={autopf}\Planner
DefaultGroupName=Planner
OutputDir=output
OutputBaseFilename=PlannerSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
; Version info embedded in PlannerSetup.exe
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName=Planner
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCompany=Planner
VersionInfoCopyright=Copyright (C) ArtemVashchenko
VersionInfoDescription=Planner Setup

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#SourceDir}\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
; config.toml: only if missing (preserve user config on update)
#ifexist "..\installer_sources\config_default\config.toml"
Source: "{#SourceDir}\config_default\config.toml"; DestDir: "{app}\app\.streamlit"; Flags: onlyifdoesntexist
#endif
Source: "{#SourceDir}\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\start_planner.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\setup_venv.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\scripts\*"; DestDir: "{app}\scripts"; Flags: ignoreversion recursesubdirs createallsubdirs
; Optional: include VC Redist to avoid 0xC00004BC on PCs without it (put vc_redist.x64.exe in installer_sources\redist\)
#ifexist "..\installer_sources\redist\vc_redist.x64.exe"
Source: "{#SourceDir}\redist\vc_redist.x64.exe"; DestDir: "{app}\redist"; Flags: ignoreversion
#endif
; Optional: include NSSM for "Install as Windows Service" (run installer\scripts\download_nssm.ps1)
#ifexist "..\installer_sources\nssm\nssm.exe"
Source: "{#SourceDir}\nssm\nssm.exe"; DestDir: "{app}\nssm"; Flags: ignoreversion
#endif

[Run]
; setup_venv.bat and create_desktop_url/register_task are run from [Code] for logging and -LogPath
; Install as Windows Service (prompts UAC; requires NSSM). Hidden on upgrade (service already configured).
Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -Command ""Start-Process -FilePath '{app}\scripts\install_service.bat' -ArgumentList '{app}' -Verb RunAs -Wait"""; Description: "Install as Windows Service (requires administrator)"; StatusMsg: "Installing service..."; Flags: postinstall; Check: not IsUpgrade
; Start Service Now: starts Windows service (no CMD window). Only shown when service exists and is stopped.
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Start-Process cmd -ArgumentList '/c sc start Planner' -Verb RunAs -Wait -WindowStyle Hidden"""; Description: "Start Planner service now"; StatusMsg: "Starting service..."; Flags: postinstall unchecked runhidden; Check: PlannerServiceExistsAndStopped

[UninstallDelete]
Type: files; Name: "{userdesktop}\Planner.url"

[Code]
var
  InstallLogPath: String;
  UninstallLogPath: String;

function IsUpgrade: Boolean;
var
  S: String;
begin
  Result := RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1', 'Inno Setup: App Path', S) or
            RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1', 'Inno Setup: App Path', S);
end;

procedure WriteInstallLog(const Msg: String);
var
  Line: String;
begin
  if InstallLogPath = '' then Exit;
  Line := '[' + GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':') + '] ' + Msg + #13#10;
  if not SaveStringToFile(InstallLogPath, Line, True) then
    Log('WriteInstallLog failed: ' + Msg);
end;

function IsPlannerServiceRunning: Boolean;
var
  ResultCode: Integer;
begin
  Result := False;
  if Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -Command "$s=Get-Service -Name Planner -EA 0; if($s -and $s.Status -eq ''Running''){exit 1}; exit 0"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := (ResultCode = 1);
end;

function StopPlannerService: Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd -ArgumentList ''/c sc stop Planner'' -Verb RunAs -Wait"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if Result then
    Sleep(1500);
end;

function PlannerServiceExistsAndStopped: Boolean;
var
  ResultCode: Integer;
begin
  Result := False;
  if Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -Command "$s=Get-Service -Name Planner -EA 0; if($s -and $s.Status -ne ''Running''){exit 1}; exit 0"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := (ResultCode = 1);
end;

function StartPlannerService: Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd -ArgumentList ''/c sc start Planner'' -Verb RunAs -Wait -WindowStyle Hidden"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if Result then
    Sleep(1000);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  VCRedistPath, AppDir, ScriptsDir, DesktopPath: String;
begin
  if CurStep = ssInstall then
    if IsUpgrade then
      WriteInstallLog('Upgrade: copying files to ' + ExpandConstant('{app}'))
    else
      WriteInstallLog('Fresh install: copying files to ' + ExpandConstant('{app}'));

  if CurStep = ssPostInstall then
  begin
    AppDir := ExpandConstant('{app}');
    ScriptsDir := AppDir + '\scripts';
    DesktopPath := ExpandConstant('{userdesktop}');

    { VC Redist: skip on upgrade (already installed) }
    VCRedistPath := AppDir + '\redist\vc_redist.x64.exe';
    if FileExists(VCRedistPath) and not IsUpgrade then
    begin
      WriteInstallLog('Installing Visual C++ Redistributable (with elevation): ' + VCRedistPath);
      if Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath ''' + VCRedistPath + ''' -ArgumentList ''/install'',''/quiet'',''/norestart'' -Verb RunAs -Wait"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
        WriteInstallLog('VC Redist finished with code: ' + IntToStr(ResultCode))
      else
        WriteInstallLog('VC Redist execution failed');
      Sleep(1500);
    end
    else if IsUpgrade then
      WriteInstallLog('Upgrade: skipping VC Redist (already installed)')
    else
      WriteInstallLog('VC Redist not present, skipping');

    { venv: full setup on fresh install, pip-only update on upgrade }
    if IsUpgrade and DirExists(AppDir + '\venv') then
    begin
      WriteInstallLog('Upgrade: updating pip packages (setup_venv.bat update)...');
      if not Exec(AppDir + '\setup_venv.bat', 'update', AppDir, SW_SHOW, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      begin
        WriteInstallLog('setup_venv.bat update failed with code: ' + IntToStr(ResultCode));
        MsgBox('Обновление зависимостей Python завершилось с ошибкой (код ' + IntToStr(ResultCode) + ').' + #13#10 + #13#10 +
          'Запустите вручную из папки установки: setup_venv.bat update', mbError, MB_OK);
        Abort;
      end;
      WriteInstallLog('setup_venv.bat update finished with code: ' + IntToStr(ResultCode));
    end
    else
    begin
      WriteInstallLog('Running setup_venv.bat to create virtual environment...');
      if not Exec(AppDir + '\setup_venv.bat', '', AppDir, SW_SHOW, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
      begin
        WriteInstallLog('setup_venv.bat failed with code: ' + IntToStr(ResultCode));
        MsgBox('Создание виртуального окружения Python завершилось с ошибкой (код ' + IntToStr(ResultCode) + ').' + #13#10 + #13#10 +
          'Проверьте интернет и запустите вручную из папки установки: setup_venv.bat' + #13#10 + #13#10 +
          'Если при запуске Python появляется ошибка 0xC00004BC, на целевом ПК нужно установить Microsoft Visual C++ 2015-2022 Redistributable (x64):' + #13#10 +
          'https://aka.ms/vs/17/release/vc_redist.x64.exe', mbError, MB_OK);
        Abort;
      end;
      WriteInstallLog('setup_venv.bat finished with code: ' + IntToStr(ResultCode));
    end;

    WriteInstallLog('Creating desktop shortcut...');
    if not Exec('powershell.exe', '-ExecutionPolicy Bypass -File "' + ScriptsDir + '\create_desktop_url.ps1" -DesktopPath "' + DesktopPath + '" -LogPath "' + InstallLogPath + '"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      WriteInstallLog('create_desktop_url.ps1 execution failed (PowerShell did not start)')
    else if ResultCode <> 0 then
    begin
      WriteInstallLog('create_desktop_url.ps1 failed with exit code: ' + IntToStr(ResultCode));
      MsgBox('Не удалось создать ярлык на рабочем столе (код ' + IntToStr(ResultCode) + ').' + #13#10 + 'Создайте ярлык вручную или запускайте Planner из папки установки.', mbError, MB_OK);
    end
    else
      WriteInstallLog('create_desktop_url.ps1 completed successfully');

    { On upgrade: auto-start service if it exists and was stopped (we stopped it before install) }
    if IsUpgrade and PlannerServiceExistsAndStopped then
    begin
      WriteInstallLog('Starting Planner service (was stopped for update)...');
      if StartPlannerService then
        WriteInstallLog('Planner service started successfully')
      else
        WriteInstallLog('Failed to start Planner service (user may need to start manually)');
    end;

    WriteInstallLog('Install completed successfully.');
  end;
end;

function InitializeSetup(): Boolean;
var
  LogsDir: String;
begin
  Result := True;

  { Check if Planner service is running; offer to stop or warn }
  if IsPlannerServiceRunning then
  begin
    case MsgBox('Служба Planner запущена.' + #13#10 + #13#10 +
      'Рекомендуется остановить её перед установкой или обновлением.' + #13#10 + #13#10 +
      'Остановить службу сейчас? (потребуются права администратора)' + #13#10 + #13#10 +
      '«Да» — остановить и продолжить' + #13#10 +
      '«Нет» — продолжить без остановки (возможны ошибки)' + #13#10 +
      '«Отмена» — прервать установку', mbConfirmation, MB_YESNOCANCEL) of
      IDYES:
        begin
          if not StopPlannerService then
          begin
            if MsgBox('Не удалось остановить службу (возможно, недостаточно прав).' + #13#10 + #13#10 +
              'Продолжить установку без остановки?', mbError, MB_YESNO) = IDNO then
              Result := False;
          end
          else if IsPlannerServiceRunning then
          begin
            if MsgBox('Служба всё ещё запущена. Продолжить установку?', mbError, MB_YESNO) = IDNO then
              Result := False;
          end;
        end;
      IDNO:;
      IDCANCEL: Result := False;
    end;
    if not Result then Exit;
  end;

  LogsDir := ExpandConstant('{userappdata}\Planner\Logs');
  if ForceDirectories(LogsDir) then
  begin
    { Filename: no colons (invalid on Windows); use date_time for standard pattern }
    InstallLogPath := LogsDir + '\install_' + GetDateTimeString('yyyy-mm-dd_hh-nn-ss', '-', '-') + '.log';
    WriteInstallLog('Planner Setup started, version {#MyAppVersion}');
    if IsUpgrade then
      WriteInstallLog('Mode: upgrade (existing installation detected)')
    else
      WriteInstallLog('Mode: fresh install');
  end
  else
    InstallLogPath := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  LogsDir, Line, AppDir, UninstallBat: String;
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    { Remove Windows Service with elevation if NSSM was bundled (files still present) }
    AppDir := ExpandConstant('{app}');
    if FileExists(AppDir + '\nssm\nssm.exe') then
    begin
      UninstallBat := AppDir + '\scripts\uninstall_service.bat';
      if FileExists(UninstallBat) then
        Exec('powershell.exe', '-ExecutionPolicy Bypass -Command "Start-Process -FilePath ''' + UninstallBat + ''' -ArgumentList ''' + AppDir + ''' -Verb RunAs -Wait"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;

    LogsDir := ExpandConstant('{userappdata}\Planner\Logs');
    if ForceDirectories(LogsDir) then
    begin
      { Filename: no colons (invalid on Windows); use date_time for standard pattern }
      UninstallLogPath := LogsDir + '\uninstall_' + GetDateTimeString('yyyy-mm-dd_hh-nn-ss', '-', '-') + '.log';
      Line := '[' + GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':') + '] Planner Uninstall started, version {#MyAppVersion}' + #13#10;
      SaveStringToFile(UninstallLogPath, Line, False);
    end
    else
      UninstallLogPath := '';
  end;
  if CurUninstallStep = usPostUninstall then
  begin
    if UninstallLogPath <> '' then
    begin
      Line := '[' + GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':') + '] Planner Uninstall completed.' + #13#10;
      SaveStringToFile(UninstallLogPath, Line, True);
    end;
  end;
end;
