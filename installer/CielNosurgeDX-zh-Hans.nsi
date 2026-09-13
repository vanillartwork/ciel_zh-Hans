; Ciel nosurge DX -- Simplified Chinese patch installer
;
; The installer carries no game data. It ships this project's translations
; and tooling; the patched files are produced on the player's machine from
; the copy of the game they already own.
;
; Build it with installer/build-installer.ps1. See installer/README.md.

Unicode true
ManifestDPIAware true

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!include "WordFunc.nsh"
!include "WinMessages.nsh"
!include "x64.nsh"

!ifndef PATCH_VERSION
  !define PATCH_VERSION "0.0.0-dev"
!endif
!ifndef GAME_BUILD
  !define GAME_BUILD "6298523"
!endif

!define PRODUCT     "Ciel nosurge DX 简体中文补丁"
!define PRODUCT_EN  "CielNosurgeDX-zh-Hans"
!define PUBLISHER   "Ciel nosurge DX 简体中文计划"
!define REGKEY      "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_EN}"
; Steam writes one of these for every installed game, and its
; InstallLocation is the game folder itself -- no guessing at library paths.
!define GAMEKEY     "Software\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 1477480"
!define GAMEKEY32   "Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 1477480"
; staging is ~160 MB and the backups ~70 MB; the rest is headroom
!define NEEDED_MB   1200

Name "${PRODUCT} ${PATCH_VERSION}"
OutFile "..\..\dist\${PRODUCT_EN}-${PATCH_VERSION}-setup.exe"
InstallDir "$LOCALAPPDATA\${PRODUCT_EN}"
RequestExecutionLevel admin
ShowInstDetails show
ShowUninstDetails show
SetCompressor /SOLID lzma

Var GameDir
Var PyExe
Var LogFile
Var ProgFile
Var DoneFile
Var Bar          ; our progress bar, the one that shows real progress
Var Pct
Var Phase

!define MUI_ABORTWARNING
!define MUI_ICON "assets\patch.ico"
!define MUI_UNICON "assets\patch.ico"

; Simplified Chinese only: every string here is written in it, so a language
; choice would change a handful of built-in captions and nothing else.

!define MUI_WELCOMEPAGE_TITLE "安装 ${PRODUCT}"
!define MUI_WELCOMEPAGE_TEXT \
"适用的游戏版本：Steam build ${GAME_BUILD}$\r$\n\
补丁版本：${PATCH_VERSION}$\r$\n$\r$\n\
安装前会自动把被替换的原始文件备份到游戏目录下的 Backup 文件夹，随时可以通过卸载程序还原。$\r$\n$\r$\n\
本补丁为非官方爱好者作品，与 GUST／光荣特库摩没有任何隶属关系。本汉化补丁完全免费，仅供个人学习与交流使用。任何收费行为与本项目作者无关，请勿付款。如发现有人冒用本项目名义收费，欢迎向项目作者反馈。"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\NOTICE-INSTALLER.txt"

!define MUI_PAGE_HEADER_TEXT "选择游戏位置"
!define MUI_PAGE_HEADER_SUBTEXT "请指向 Ciel nosurge DX 的安装文件夹"
!define MUI_DIRECTORYPAGE_TEXT_TOP \
"下面的位置是自动检测到的，通常直接点“下一步”即可。$\r$\n\
如果不对，请选到包含 CielnosurgeDX.exe 和 Res_x64 的那个文件夹。"
!define MUI_DIRECTORYPAGE_TEXT_DESTINATION "游戏文件夹"
!define MUI_DIRECTORYPAGE_VARIABLE $GameDir
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE CheckGameDir
!insertmacro MUI_PAGE_DIRECTORY

!define MUI_PAGE_CUSTOMFUNCTION_SHOW InstFilesShow
!insertmacro MUI_PAGE_INSTFILES

!define MUI_FINISHPAGE_TITLE "安装完成"
!define MUI_FINISHPAGE_TEXT \
"补丁已安装，照常从启动器启动游戏即可。$\r$\n$\r$\n\
要还原成日文原版，可以在“应用和功能”里卸载本补丁，或运行游戏目录下 Backup 文件夹里的卸载程序。$\r$\n$\r$\n\
安装日志：$LogFile"
!define MUI_FINISHPAGE_LINK "项目主页与问题反馈"
!define MUI_FINISHPAGE_LINK_LOCATION "https://github.com/vanillartwork/ciel_zh-Hans"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"


; ===========================================================================
; Progress
;
; NSIS owns the progress bar on the InstFiles page and rewrites its position
; after every instruction it executes, so setting that control by hand does
; not stick. Instead its bar is hidden and a second one is created in the
; same place; NSIS goes on updating the hidden one, and this one shows the
; percentage the tools report.
;
; The tools cannot report anything while NSIS blocks on them, so the long
; steps are started detached and their progress is read from a file they
; rewrite as they go. `--done` is how they hand back an exit status, since a
; detached process does not give us one.

Function InstFilesShow
  FindWindow $0 "#32770" "" $HWNDPARENT     ; the inner dialog of the page
  GetDlgItem $1 $0 1004                     ; the bar NSIS keeps rewriting
  ; put ours exactly where that one is, in dialog coordinates
  System::Call "*(i,i,i,i) i .r2"
  System::Call "user32::GetWindowRect(i r1, i r2)"
  System::Call "user32::MapWindowPoints(i 0, i r0, i r2, i 2)"
  System::Call "*$2(i .r3, i .r4, i .r5, i .r6)"
  System::Free $2
  IntOp $5 $5 - $3                          ; width
  IntOp $6 $6 - $4                          ; height
  ShowWindow $1 0                           ; SW_HIDE
  System::Call "user32::CreateWindowEx(i 0, t 'msctls_progress32', t '', i 0x50000001, i r3, i r4, i r5, i r6, i r0, i 0, i 0, i 0) i .s"
  Pop $Bar
  SendMessage $Bar ${PBM_SETRANGE32} 0 100
  SendMessage $Bar ${PBM_SETPOS} 0 0
FunctionEnd


!macro SetPct v
  SendMessage $Bar ${PBM_SETPOS} ${v} 0
!macroend


; Run one tool detached and watch its progress file until it writes --done.
!macro RunWatched tag lo_guard cmdline fallback_label
  Delete "$DoneFile"
  Delete "$ProgFile"
  Exec '${cmdline}'
  StrCpy $Phase "${fallback_label}"
  StrCpy $R7 0                              ; watchdog ticks of 200 ms
  StrCpy $R6 ${lo_guard}                    ; highest percent shown so far
  watch_${tag}:
    Sleep 200
    IntOp $R7 $R7 + 1
    ${If} $R7 > 18000                        ; give up after an hour
      StrCpy $0 "timeout"
      Goto watched_done_${tag}
    ${EndIf}
    ${If} ${FileExists} "$DoneFile"
      Goto watched_done_${tag}
    ${EndIf}
    ${IfNot} ${FileExists} "$ProgFile"
      Goto watch_${tag}
    ${EndIf}
    ClearErrors
    FileOpen $9 "$ProgFile" r
    ${If} ${Errors}
      Goto watch_${tag}
    ${EndIf}
    FileReadUTF16LE $9 $Pct
    FileReadUTF16LE $9 $R8
    FileClose $9
    ${WordReplace} "$Pct" "$\r" "" "+" $Pct
    ${WordReplace} "$Pct" "$\n" "" "+" $Pct
    ${WordReplace} "$R8" "$\r" "" "+" $R8
    ${WordReplace} "$R8" "$\n" "" "+" $R8
    ${If} $R8 != ""
    ${AndIf} $R8 != $Phase
      StrCpy $Phase $R8
      DetailPrint "$R8…"
    ${EndIf}
    ${If} $Pct > $R6                         ; ignore a torn or stale read
      StrCpy $R6 $Pct
      !insertmacro SetPct $Pct
    ${EndIf}
    Goto watch_${tag}
  watched_done_${tag}:
  FileOpen $9 "$DoneFile" r
  FileReadUTF16LE $9 $0
  FileClose $9
  ${WordReplace} "$0" "$\r" "" "+" $0
  ${WordReplace} "$0" "$\n" "" "+" $0
!macroend


!macro Phase name label lo hi
  DetailPrint "${label}"
  !insertmacro RunWatched ${name} ${lo} '"$PyExe" "$INSTDIR\tools\build.py" --game "$GameDir" --out "$INSTDIR\build" --version "${PATCH_VERSION}" --log "$LogFile" --progress "$ProgFile" --progress-range ${lo} ${hi} --done "$DoneFile" --phase ${name}' "${label}"
  ${If} $0 != 0
    !insertmacro Failed
  ${EndIf}
  !insertmacro SetPct ${hi}
!macroend

!macro Failed
  MessageBox MB_ICONSTOP \
    "生成补丁失败。$\r$\n$\r$\n\
游戏文件没有被改动，可以正常游玩。$\r$\n$\r$\n\
详细原因见日志：$\r$\n$LogFile"
  Abort
!macroend


Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "本游戏与本补丁都只支持 64 位 Windows。"
    Abort
  ${EndIf}
  Call DetectGameDir
FunctionEnd


; Steam's own uninstall entry gives the folder outright. The Steam client's
; own registry value is the fallback, and it stores the path with forward
; slashes, which have to be turned round before Windows will take them.
Function DetectGameDir
  StrCpy $GameDir ""
  ReadRegStr $0 HKLM "${GAMEKEY}" "InstallLocation"
  ${If} $0 == ""
    ReadRegStr $0 HKLM "${GAMEKEY32}" "InstallLocation"
  ${EndIf}
  ${If} $0 == ""
    ReadRegStr $0 HKCU "${GAMEKEY}" "InstallLocation"
  ${EndIf}
  ${If} $0 != ""
    ${WordReplace} "$0" "/" "\" "+" $0
    ${If} ${FileExists} "$0\CielnosurgeDX.exe"
      StrCpy $GameDir $0
      Return
    ${EndIf}
  ${EndIf}

  ReadRegStr $1 HKCU "Software\Valve\Steam" "SteamPath"
  ${If} $1 == ""
    ReadRegStr $1 HKLM "Software\WOW6432Node\Valve\Steam" "InstallPath"
  ${EndIf}
  ${If} $1 != ""
    ${WordReplace} "$1" "/" "\" "+" $1
    StrCpy $2 "$1\steamapps\common\CielnosurgeDX"
    ${If} ${FileExists} "$2\CielnosurgeDX.exe"
      StrCpy $GameDir $2
      Return
    ${EndIf}
  ${EndIf}

  StrCpy $GameDir "$PROGRAMFILES32\Steam\steamapps\common\CielnosurgeDX"
FunctionEnd


Function CheckGameDir
  ${WordReplace} "$GameDir" "/" "\" "+" $GameDir
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
  ${GetRoot} "$GameDir" $0
  ${DriveSpace} "$0" "/D=F /S=M" $1
  ${If} $1 < ${NEEDED_MB}
    MessageBox MB_ICONEXCLAMATION|MB_OKCANCEL \
      "$0 上只剩 $1 MB 可用空间，生成补丁大约需要 ${NEEDED_MB} MB。$\r$\n$\r$\n\
空间不足时安装会失败。仍要继续吗？" IDOK +2
    Abort
  ${EndIf}
FunctionEnd


Section "安装" SecMain
  SetOutPath "$INSTDIR"
  StrCpy $LogFile "$INSTDIR\install.log"
  StrCpy $ProgFile "$INSTDIR\progress.txt"
  StrCpy $DoneFile "$INSTDIR\done.txt"
  Delete "$LogFile"

  DetailPrint "正在释放工具与翻译数据…"
  ; Payload from build-installer.ps1: an embedded Python runtime, the
  ; pipeline, and this project's translation data. No game files.
  File /r "payload\python\*.*"
  File /r "payload\tools"
  File /r "payload\data"
  File "payload\VERSION"
  !insertmacro SetPct 10

  ; pythonw, not python: Exec runs the child in its own window, and the
  ; console one would flash up once for every phase.
  StrCpy $PyExe "$INSTDIR\pythonw.exe"
  ${IfNot} ${FileExists} "$PyExe"
    StrCpy $PyExe "$INSTDIR\python.exe"
  ${EndIf}
  ${IfNot} ${FileExists} "$PyExe"
    DetailPrint "未找到随附的 Python，改用系统 Python。"
    StrCpy $PyExe "pyw"
  ${EndIf}

  DetailPrint "正在核对游戏版本…"
  !insertmacro RunWatched pre 10 '"$PyExe" "$INSTDIR\tools\preflight.py" --game "$GameDir" --data "$INSTDIR\data" --log "$LogFile" --progress "$ProgFile" --progress-range 10 14 --done "$DoneFile"' "正在核对游戏版本"
  ${If} $0 != 0
    MessageBox MB_ICONSTOP \
      "这个游戏版本不是本补丁所针对的版本，安装已中止，游戏文件没有被改动。$\r$\n$\r$\n\
详细原因见日志：$\r$\n$LogFile$\r$\n$\r$\n\
如果游戏刚更新过，请到项目页面反馈。"
    Abort
  ${EndIf}
  !insertmacro SetPct 14

  DetailPrint "接下来会用你自己的游戏文件生成补丁，大约需要 2~3 分钟。"
  !insertmacro Phase check   "[1/5] 检查翻译数据"       14 18
  !insertmacro Phase extract "[2/5] 提取原文并合并译文"   18 46
  !insertmacro Phase font    "[3/5] 重建字库"           46 60
  !insertmacro Phase inject  "[4/5] 写回译文并修改程序"   60 80
  !insertmacro Phase repack  "[5/5] 重新打包"           80 92

  DetailPrint "正在备份原始文件并安装…"
  !insertmacro RunWatched inst 92 '"$PyExe" "$INSTDIR\tools\install.py" --game "$GameDir" --from "$INSTDIR\build" --data "$INSTDIR\data" --log "$LogFile" --progress "$ProgFile" --progress-range 92 99 --done "$DoneFile" --apply' "正在备份原始文件并安装"
  ${If} $0 != 0
    MessageBox MB_ICONSTOP \
      "安装补丁文件时出错。$\r$\n$\r$\n\
安装程序已经把改动过的文件还原回去了。如果游戏仍然不正常，$\r$\n\
请在 Steam 里对游戏执行“验证游戏文件完整性”。$\r$\n$\r$\n\
详细原因见日志：$\r$\n$LogFile"
    Abort
  ${EndIf}

  DetailPrint "正在清理临时文件…"
  RMDir /r "$INSTDIR\build"
  Delete "$ProgFile"
  Delete "$DoneFile"

  WriteUninstaller "$INSTDIR\uninstall.exe"
  ; a second copy beside the backups, because that is where someone looking
  ; to undo this will look first
  CreateDirectory "$GameDir\Backup"
  CopyFiles /SILENT "$INSTDIR\uninstall.exe" "$GameDir\Backup\卸载简体中文补丁.exe"

  WriteRegStr HKLM "${REGKEY}" "DisplayName"     "${PRODUCT}"
  WriteRegStr HKLM "${REGKEY}" "DisplayVersion"  "${PATCH_VERSION}"
  WriteRegStr HKLM "${REGKEY}" "Publisher"       "${PUBLISHER}"
  WriteRegStr HKLM "${REGKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${REGKEY}" "GameDir"         "$GameDir"
  WriteRegStr HKLM "${REGKEY}" "DisplayIcon"     "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "${REGKEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegDWORD HKLM "${REGKEY}" "NoModify" 1
  WriteRegDWORD HKLM "${REGKEY}" "NoRepair" 1
  !insertmacro SetPct 100
SectionEnd


; ===========================================================================
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
    Delete "$GameDir\Backup\卸载简体中文补丁.exe"
  ${EndIf}
  RMDir /r "$INSTDIR"
  DeleteRegKey HKLM "${REGKEY}"
SectionEnd

