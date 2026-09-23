; Mosaic ERP per-user installer (NSIS). No admin required.
!include "MUI2.nsh"

Name "Mosaic ERP"
OutFile "MosaicERP-windows-x64-setup.exe"
Unicode true
InstallDir "$LOCALAPPDATA\Programs\MosaicERP"
InstallDirRegKey HKCU "Software\MosaicERP" "InstallDir"
RequestExecutionLevel user

!define APPNAME "Mosaic ERP"
!define PUBLISHER "Hearthplug"
!define VERSION "1.3.3"
!define EXE "MosaicERP.exe"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install"
  SetOutPath "$INSTDIR"
  File "dist\MosaicERP.exe"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\Mosaic ERP"
  CreateShortcut "$SMPROGRAMS\Mosaic ERP\Mosaic ERP.lnk" "$INSTDIR\${EXE}"
  CreateShortcut "$SMPROGRAMS\Mosaic ERP\Uninstall Mosaic ERP.lnk" "$INSTDIR\Uninstall.exe"
  CreateShortcut "$DESKTOP\Mosaic ERP.lnk" "$INSTDIR\${EXE}"
  WriteRegStr HKCU "Software\MosaicERP" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MosaicERP" "DisplayName" "${APPNAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MosaicERP" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MosaicERP" "Publisher" "${PUBLISHER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MosaicERP" "DisplayIcon" "$INSTDIR\${EXE}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MosaicERP" "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MosaicERP" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MosaicERP" "NoRepair" 1
SectionEnd

Section "Uninstall"
  ; Stop the app and the local assistant model server if they are running.
  nsExec::Exec 'taskkill /F /IM MosaicERP.exe'
  nsExec::Exec 'taskkill /F /IM llama-server.exe'
  Sleep 1500
  MessageBox MB_YESNO|MB_ICONQUESTION "Keep your shop data?$\r$\n$\r$\nChoose Yes to keep your business data in $LOCALAPPDATA\MosaicERP (a future install can pick it up).$\r$\nChoose No to delete it permanently." IDYES keep_data
  RMDir /r "$LOCALAPPDATA\MosaicERP"
keep_data:
  RMDir /r "$INSTDIR"
  RMDir /r "$SMPROGRAMS\Mosaic ERP"
  Delete "$DESKTOP\Mosaic ERP.lnk"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\MosaicERP"
  DeleteRegKey HKCU "Software\MosaicERP"
SectionEnd
