<#
.SYNOPSIS
  Attach cdb to CielnosurgeDX.exe the moment Steam starts it, and detach again.

.DESCRIPTION
  The executable calls SteamAPI_RestartAppIfNecessary, so starting it straight
  from a debugger usually just hands it back to Steam and exits.  Instead this
  sets the Image File Execution Options "Debugger" value for CielnosurgeDX.exe:
  Steam launches the game exactly as it normally does, and Windows starts it
  under cdb.  Nothing about Steam or the game is bypassed.

  That value is a system-wide registry setting under HKLM.  While it is set,
  EVERY start of CielnosurgeDX.exe goes through cdb.  Run -Disable when done.

  -Enable   needs an elevated 64-bit PowerShell; refuses unless the game folder
            currently holds the ORIGINAL executable (see swap_original.py).
  -Disable  removes only the value this script wrote, and the key only if this
            script created it.
  -Status   shows what is set.
  -Threads  use stage1_threads.cdb (logs other-thread SetText/GetText; slow).

.EXAMPLE
  .\debug.ps1 -Enable
  .\debug.ps1 -Disable
#>
[CmdletBinding()]
param(
    [switch]$Enable,
    [switch]$Disable,
    [switch]$Status,
    [switch]$Threads,
    [string]$Cdb = "",
    [string]$Game = "${env:ProgramFiles(x86)}\Steam\steamapps\common\CielnosurgeDX",
    [string]$Work = ""
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$exeName = "CielnosurgeDX.exe"
$key = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\$exeName"
$originalSha = "04b755ab2eb26f26f79df9d2a24d9dcc62f5adca43bdb4871a137866d5d60b90"
if (-not $Work) { $Work = Join-Path $env:LOCALAPPDATA "cielzh_stage1" }
$stateFile = Join-Path $Work "ifeo-state.json"

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Find-Cdb {
    if ($Cdb) {
        if (-not (Test-Path $Cdb)) { throw "cdb.exe is not at $Cdb" }
        return $Cdb
    }
    $candidates = @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\Debuggers\x64\cdb.exe",
        "$env:ProgramFiles\Windows Kits\10\Debuggers\x64\cdb.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    throw ("cdb.exe not found.  Install 'Debugging Tools for Windows' from the " +
           "Windows SDK installer (only that feature is needed), or pass -Cdb <path>.")
}

function Get-Debugger {
    if (-not (Test-Path $key)) { return $null }
    (Get-ItemProperty -Path $key -Name Debugger -ErrorAction SilentlyContinue).Debugger
}

function Copy-CdbScript {
    param([string]$Source, [string]$Destination)
    # CDB 10.0.28000's $$< reader can replay comment fragments from LF-only
    # files as commands. Normalize at deployment, regardless of Git/editor EOLs.
    $content = [IO.File]::ReadAllText($Source)
    $content = $content -replace "\r\n?|\n", "`r`n"
    [IO.File]::WriteAllText($Destination, $content, [Text.UTF8Encoding]::new($false))
}

if (-not [Environment]::Is64BitProcess) {
    throw "Run this from 64-bit PowerShell; a 32-bit one writes to WOW6432Node, which a 64-bit game ignores."
}

if ($Status -or -not ($Enable -or $Disable)) {
    $v = Get-Debugger
    if ($v) { Write-Host "IFEO Debugger is SET for $exeName`n  $v" }
    else    { Write-Host "IFEO Debugger is not set for $exeName" }
    if (Test-Path $stateFile) { Write-Host "state: $stateFile" }
    return
}

if (-not (Test-Admin)) { throw "Run this from an elevated (Administrator) PowerShell." }

if ($Enable) {
    $existing = Get-Debugger
    if ($existing) {
        throw "A Debugger value is already set for $exeName; not overwriting it:`n  $existing"
    }
    $gameExe = Join-Path $Game $exeName
    if (-not (Test-Path $gameExe)) { throw "No $exeName under $Game; pass -Game <folder>." }
    $h = (Get-FileHash $gameExe -Algorithm SHA256).Hash.ToLower()
    if ($h -ne $originalSha) {
        throw ("$exeName in the game folder is not the original (sha256 $h).  " +
               "The breakpoints are addresses in the original; run " +
               "'py -3 swap_original.py in' first.")
    }
    if ($Work -match '\s') {
        throw "The work folder '$Work' contains a space, which cdb's script path cannot take here; pass -Work <folder without spaces>."
    }
    $cdbExe = Find-Cdb
    New-Item -ItemType Directory -Force -Path $Work | Out-Null

    $scriptName = if ($Threads) { "stage1_threads.cdb" } else { "stage1.cdb" }
    $script = Join-Path $Work $scriptName
    Copy-CdbScript -Source (Join-Path $here $scriptName) -Destination $script
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $log = Join-Path $Work "stage1-$stamp.log"

    # Single quotes: '$$<' is cdb syntax, not a PowerShell variable.
    $value = '"' + $cdbExe + '" -G -logo "' + $log + '" -c "$$<' + $script + '"'

    $createdKey = $false
    if (-not (Test-Path $key)) {
        New-Item -Path $key -Force | Out-Null
        $createdKey = $true
    }
    New-ItemProperty -Path $key -Name Debugger -Value $value -PropertyType String -Force | Out-Null

    @{ value = $value; created_key = $createdKey; log = $log; script = $scriptName;
       enabled = (Get-Date -Format "yyyy-MM-dd HH:mm:ss") } |
        ConvertTo-Json | Set-Content -Path $stateFile -Encoding UTF8

    Write-Host "Enabled.  Start the game from Steam as usual; a cdb console window will open."
    Write-Host "  script  $scriptName"
    Write-Host "  log     $log"
    Write-Host "When done: quit the game, then run  .\debug.ps1 -Disable"
    return
}

if ($Disable) {
    if (-not (Test-Path $stateFile)) {
        $v = Get-Debugger
        if ($v) { throw "A Debugger value is set but this script has no record of writing it; leaving it alone:`n  $v" }
        Write-Host "Nothing to disable."
        return
    }
    $state = Get-Content $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $v = Get-Debugger
    if ($v -and $v -ne $state.value) {
        throw "The Debugger value changed since -Enable; leaving it alone:`n  $v"
    }
    if ($v) { Remove-ItemProperty -Path $key -Name Debugger }
    if ($state.created_key -and (Test-Path $key)) {
        $item = Get-Item $key
        if ($item.ValueCount -eq 0 -and $item.SubKeyCount -eq 0) { Remove-Item $key }
    }
    Remove-Item $stateFile
    Write-Host "Disabled.  $exeName starts normally again."
    Write-Host "Log(s) are in $Work"
}
