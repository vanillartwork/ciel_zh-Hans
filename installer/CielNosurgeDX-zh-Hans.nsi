; Ciel nosurge DX -- Simplified Chinese patch installer
;
; The installer carries no game data.  What it ships is this project's own
; translations plus the tooling, and the patched archives are produced on the
; player's machine from the copy of the game they already own.  That keeps the
; download small and keeps game files out of the distribution entirely.
;
; What it does, in order:
;   1. find the game, or ask
;   2. check the files it is about to replace against the versions this patch
;      was built for, and stop if they are not recognised
;   3. check there is room for the work
;   4. unpack the toolchain into a working folder outside the game
;   5. build the patch there, from the player's own game files
;   6. install it, keeping the originals in the game's Backup folder
;   7. write an uninstaller that puts the originals back
;
; Build it with installer/build-installer.ps1, which assembles the payload
; first.  See installer/README.md.

Unicode true
ManifestDPIAware true

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "x64.nsh"

!ifndef PATCH_VERSION
  !define PATCH_VERSION "0.0.0-dev"
!endif
!ifndef GAME_VERSION
  !define GAME_VERSION "Steam 2025-07"
!endif

!define PRODUCT       "Ciel nosurge DX 简体中文补丁"
!define PRODUCT_EN    "CielNosurgeDX-zh-Hans"
!define PUBLISHER     "Ciel nosurge DX 简体中文计划"
!define REGKEY        "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_EN}"
!define WORKDIR       "$LOCALAPPDATA\${PRODUCT_EN}"
; the build unpacks and repacks a 1.7 GB archive
!define NEEDED_MB     6000

Name "${PRODUCT} ${PATCH_VERSION}"
OutFile "..\..\dist\${PRODUCT_EN}-${PATCH_VERSION}-setup.exe"
InstallDir "$LOCALAPPDATA\${PRODUCT_EN}"
RequestExecutionLevel admin
ShowInstDetails show
ShowUninstDetails show
SetCompressor /SOLID lzma

Var GameDir
Var PyExe

!define MUI_ABORTWARNING
!define MUI_ICON "assets\patch.ico"
!define MUI_UNICON "assets\patch.ico"
!define MUI_WELCOMEPAGE_TITLE "安装 ${PRODUCT}"
!define MUI_WELCOMEPAGE_TEXT \
"本补丁会把《シェルノサージュ DX》的界面与剧情文本替换为简体中文。$\r$\n$\r$\n\
适用的游戏版本：${GAME_VERSION}$\r$\n\
补丁版本：${PATCH_VERSION}$\r$\n$\r$\n\
安装程序不包含任何游戏文件。它会读取你自己已购买、已安装的游戏，$\r$\n\
在你的电脑上重新打包，因此需要约 6 GB 可用磁盘空间和几分钟时间。$\r$\n$\r$\n\
安装前会自动把被替换的原始文件备份到游戏目录下的 Backup 文件夹，$\r$\n\
随时可以通过卸载程序还原。$\r$\n$\r$\n\
本补丁为非官方爱好者作品，与 GUST／光荣特库摩没有任何隶属关系。"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\NOTICE-INSTALLER.txt"

; --- the game folder ---------------------------------------------------------
!define MUI_PAGE_HEADER_TEXT "选择游戏位置"
!define MUI_PAGE_HEADER_SUBTEXT "请指向 Ciel nosurge DX 的安装文件夹"
!define MUI_DIRECTORYPAGE_TEXT_TOP \
"请选择游戏的安装文件夹，也就是包含 CielnosurgeDX.exe 和 Res_x64 的那个文件夹。$\r$\n\
如果下面已经自动填好，通常直接点“下一步”即可。"
!define MUI_DIRECTORYPAGE_TEXT_DESTINATION "游戏文件夹"
!define MUI_DIRECTORYPAGE_VARIABLE $GameDir
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE CheckGameDir
!insertmacro MUI_PAGE_DIRECTORY

!insertmacro MUI_PAGE_INSTFILES

!define MUI_FINISHPAGE_TITLE "安装完成"
!define MUI_FINISHPAGE_TEXT \
"补丁已安装。照常从启动器启动游戏即可。$\r$\n$\r$\n\
如果想还原成日文原版，可以在“应用和功能”里卸载本补丁，$\r$\n\
或者运行游戏目录下 Backup 文件夹旁的卸载程序。$\r$\n$\r$\n\
翻译问题与错误反馈，欢迎到项目页面提交。"
!define MUI_FINISHPAGE_LINK "项目主页与问题反馈"
!define MUI_FINISHPAGE_LINK_LOCATION "https://github.com/vanillartwork/ciel_zh-Hans"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"


; =============================================================================
Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "本游戏与本补丁都只支持 64 位 Windows。"
    Abort
  ${EndIf}
  !insertmacro MUI_LANGDLL_DISPLAY
  Call DetectGameDir
FunctionEnd


; Fill in the game folder from Steam if we can, so most people never have to
; go looking for it.
Function DetectGameDir
  StrCpy $GameDir ""
  ReadRegStr $0 HKCU "Software\Valve\Steam" "SteamPath"
  ${If} $0 != ""
    StrCpy $1 "$0\steamapps\common\CielnosurgeDX"
    ${If} ${FileExists} "$1\CielnosurgeDX.exe"
      StrCpy $GameDir $1
      Return
    ${EndIf}
  ${EndIf}
  ReadRegStr $0 HKLM "SOFTWARE\WOW6432Node\Valve\Steam" "InstallPath"
  ${If} $0 != ""
    StrCpy $1 "$0\steamapps\common\CielnosurgeDX"
    ${If} ${FileExists} "$1\CielnosurgeDX.exe"
      StrCpy $GameDir $1
      Return
    ${EndIf}
  ${EndIf}
  ; Steam libraries on other drives are listed in libraryfolders.vdf, which
  ; NSIS cannot parse comfortably.  The Python side handles that case; here we
  ; just offer a likely default and let the player correct it.
  StrCpy $GameDir "$PROGRAMFILES32\Steam\steamapps\common\CielnosurgeDX"
FunctionEnd


Function CheckGameDir
  ${IfNot} ${FileExists} "$GameDir\CielnosurgeDX.exe"
    MessageBox MB_ICONEXCLAMATION \
      "在这个文件夹里找不到 CielnosurgeDX.exe。$\r$\n$\r$\n\
请选择游戏的安装文件夹，它通常长这样：$\r$\n\
...\steamapps\common\CielnosurgeDX"
    Abort
  ${EndIf}
  ${IfNot} ${FileExists} "$GameDir\Res_x64\PACK01.PAK"
    MessageBox MB_ICONEXCLAMATION \
      "这个文件夹里没有 Res_x64\PACK01.PAK，游戏安装似乎不完整。$\r$\n$\r$\n\
请先在 Steam 里对游戏执行“验证游戏文件完整性”，然后重新运行本安装程序。"
    Abort
  ${EndIf}

  ; The build needs room to unpack and rewrite a 1.7 GB archive.
  ${GetRoot} "$GameDir" $0
  ${DriveSpace} "$0" "/D=F /S=M" $1
  ${If} $1 < ${NEEDED_MB}
    MessageBox MB_ICONEXCLAMATION|MB_OKCANCEL \
      "$0 上只剩 $1 MB 可用空间，重新打包大约需要 ${NEEDED_MB} MB。$\r$\n$\r$\n\
空间不足时安装会失败。仍要继续吗？" IDOK +2
    Abort
  ${EndIf}
FunctionEnd


Section "安装" SecMain
  SetOutPath "$INSTDIR"
  DetailPrint "正在释放工具与翻译数据…"
  ; Payload assembled by build-installer.ps1: an embedded Python runtime, the
  ; pipeline, and this project's translation data.  No game files.
  File /r "payload\python\*.*"
  File /r "payload\tools"
  File /r "payload\data"
  File "payload\VERSION"

  StrCpy $PyExe "$INSTDIR\python.exe"
  ${IfNot} ${FileExists} "$PyExe"
    DetailPrint "未找到随附的 Python，改用系统 Python。"
    StrCpy $PyExe "py"
  ${EndIf}

  DetailPrint "正在核对游戏版本…"
  nsExec::ExecToLog '"$PyExe" "$INSTDIR\tools\preflight.py" --game "$GameDir" --data "$INSTDIR\data"'
  Pop $0
  ${If} $0 != 0
    DetailPrint "版本核对未通过。"
    MessageBox MB_ICONSTOP \
      "这个游戏版本不是本补丁所针对的版本，安装已中止，游戏文件没有被改动。$\r$\n$\r$\n\
上方日志里写明了具体原因。如果游戏刚更新过，请到项目页面反馈。"
    Abort
  ${EndIf}

  DetailPrint "正在从你的游戏文件生成补丁，这一步需要几分钟，请不要关闭窗口…"
  nsExec::ExecToLog '"$PyExe" "$INSTDIR\tools\build.py" --game "$GameDir" --out "$INSTDIR\build" --version "${PATCH_VERSION}"'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONSTOP \
      "生成补丁失败，安装已中止。$\r$\n$\r$\n\
游戏文件没有被改动，可以正常游玩。上方日志里写明了失败的原因，$\r$\n\
反馈问题时请把它一并附上。"
    Abort
  ${EndIf}

  DetailPrint "正在备份原始文件并安装…"
  nsExec::ExecToLog '"$PyExe" "$INSTDIR\tools\install.py" --game "$GameDir" --from "$INSTDIR\build" --data "$INSTDIR\data" --apply'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_ICONSTOP \
      "安装补丁文件时出错。$\r$\n$\r$\n\
安装程序已经把改动过的文件还原回去了。如果游戏仍然不正常，$\r$\n\
请在 Steam 里对游戏执行“验证游戏文件完整性”。"
    Abort
  ${EndIf}

  ; The build tree is several gigabytes and is of no further use.
  DetailPrint "正在清理临时文件…"
  RMDir /r "$INSTDIR\build"

  WriteUninstaller "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "${REGKEY}" "DisplayName"     "${PRODUCT}"
  WriteRegStr HKLM "${REGKEY}" "DisplayVersion"  "${PATCH_VERSION}"
  WriteRegStr HKLM "${REGKEY}" "Publisher"       "${PUBLISHER}"
  WriteRegStr HKLM "${REGKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${REGKEY}" "GameDir"         "$GameDir"
  WriteRegStr HKLM "${REGKEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKLM "${REGKEY}" "NoModify" 1
  WriteRegDWORD HKLM "${REGKEY}" "NoRepair" 1
SectionEnd


; =============================================================================
Section "Uninstall"
  ReadRegStr $GameDir HKLM "${REGKEY}" "GameDir"
  ${If} $GameDir == ""
    MessageBox MB_ICONEXCLAMATION \
      "找不到当初安装到的游戏文件夹。$\r$\n$\r$\n\
请在 Steam 里对游戏执行“验证游戏文件完整性”，即可还原为日文原版。"
  ${Else}
    DetailPrint "正在还原原始游戏文件…"
    StrCpy $PyExe "$INSTDIR\python.exe"
    ${IfNot} ${FileExists} "$PyExe"
      StrCpy $PyExe "py"
    ${EndIf}
    nsExec::ExecToLog '"$PyExe" "$INSTDIR\tools\install.py" --game "$GameDir" --restore'
    Pop $0
    ${If} $0 != 0
      MessageBox MB_ICONEXCLAMATION \
        "有文件没能自动还原。$\r$\n$\r$\n\
原始文件应该还在：$GameDir\Backup$\r$\n\
也可以在 Steam 里对游戏执行“验证游戏文件完整性”来取回干净的文件。"
    ${EndIf}
  ${EndIf}

  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "${REGKEY}"
SectionEnd
