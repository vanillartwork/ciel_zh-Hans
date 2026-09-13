<#
.SYNOPSIS
  Assemble the payload and compile the Windows installer.

.DESCRIPTION
  The installer ships no game data.  What goes into it is:

    python\   an embeddable CPython plus numpy and Pillow, so the patch can
              be built on a machine with no Python installed
    tools\    this project's pipeline
    data\     this project's translations and glossary

  The patched archives themselves are produced on the player's machine from
  the copy of the game they own, which is why none of them appear here.

  Run this on a machine with NSIS installed (makensis on PATH, or pass -Nsis).

.EXAMPLE
  .\build-installer.ps1 -Version 0.9.0
#>
[CmdletBinding()]
param(
    [string]$Version = "0.0.0-dev",
    [string]$GameVersion = "Steam 2025-07",
    [string]$PythonVersion = "3.12.7",
    [string]$Nsis = "makensis",
    [switch]$SkipPython
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
$payload = Join-Path $here "payload"

Write-Host "repo     $repo"
Write-Host "version  $Version"

# --- 1. clean payload --------------------------------------------------------
# -SkipPython means "reuse the runtime already staged", so that one directory
# has to survive the clean or the flag defeats itself.
if (Test-Path $payload) {
    Get-ChildItem $payload -Force | Where-Object {
        -not ($SkipPython -and $_.Name -eq "python")
    } | Remove-Item -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $payload | Out-Null
if ($SkipPython -and -not (Test-Path (Join-Path $payload "python"))) {
    throw "-SkipPython was given but installer/payload/python is not there; run once without it"
}

# --- 2. embeddable Python + the two wheels the font build needs --------------
if (-not $SkipPython) {
    $pyDir = Join-Path $payload "python"
    New-Item -ItemType Directory -Force -Path $pyDir | Out-Null
    $zip = Join-Path $env:TEMP "python-$PythonVersion-embed-amd64.zip"
    if (-not (Test-Path $zip)) {
        $url = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
        Write-Host "downloading $url"
        Invoke-WebRequest -Uri $url -OutFile $zip
    }
    Expand-Archive -Path $zip -DestinationPath $pyDir -Force

    # the embeddable build ships with site-packages switched off
    Get-ChildItem $pyDir -Filter "python*._pth" | ForEach-Object {
        $t = Get-Content $_.FullName
        $t = $t -replace "^#\s*import site", "import site"
        if ($t -notcontains "Lib\site-packages") { $t += "Lib\site-packages" }
        Set-Content -Path $_.FullName -Value $t -Encoding ASCII
    }

    $site = Join-Path $pyDir "Lib\site-packages"
    New-Item -ItemType Directory -Force -Path $site | Out-Null

    # pip runs from whatever Python is on this machine; the wheels it fetches
    # are for the embedded runtime, not this one, hence --platform/--abi.
    # Do not trust Get-Command here: on Windows `python` is often the Microsoft
    # Store stub, which resolves fine and then exits without doing anything.
    # Try each candidate for real and keep the first that answers.
    $pyCmd = $null
    foreach ($c in @(@("py", "-3"), @("python3"), @("python"))) {
        try {
            $v = & $c[0] @($c[1..($c.Length - 1)]) "--version" 2>$null
            if ($LASTEXITCODE -eq 0 -and $v -match "Python 3") { $pyCmd = $c; break }
        } catch { }
    }
    if (-not $pyCmd) { throw "no working Python 3 on PATH to run pip with" }
    $pipArgs = @($pyCmd[1..($pyCmd.Length - 1)])
    $parts = $PythonVersion -split "\."
    $abi = "cp" + $parts[0] + $parts[1]

    Write-Host "installing numpy and Pillow into the embedded runtime (via $($pyCmd -join ' '))"
    & $pyCmd[0] @pipArgs -m pip install --target $site --only-binary=:all: `
        --platform win_amd64 --implementation cp --abi $abi `
        --python-version $PythonVersion numpy pillow
    if ($LASTEXITCODE -ne 0) { throw "pip could not fetch numpy/Pillow" }
}

# --- 3. the pipeline and the translation data --------------------------------
Write-Host "copying tools and data"
Copy-Item -Recurse (Join-Path $repo "tools") (Join-Path $payload "tools")
Copy-Item -Recurse (Join-Path $repo "data")  (Join-Path $payload "data")
Get-ChildItem -Recurse -Force -Path $payload -Include "__pycache__" -Directory |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# Guard rail: the payload must never contain game data.  If one of these shows
# up, something has gone wrong upstream and the installer must not be shipped.
$forbidden = Get-ChildItem -Recurse -File -Path $payload |
    Where-Object { $_.Extension -in ".pak", ".g1t", ".psarc", ".gtx" -or $_.Name -like "Cielnosurge*.exe" }
if ($forbidden) {
    $forbidden | ForEach-Object { Write-Host "  $($_.FullName)" }
    throw "game data found in the installer payload; refusing to build"
}

Set-Content -Path (Join-Path $payload "VERSION") -Value $Version -Encoding UTF8

$bytes = (Get-ChildItem -Recurse -File $payload | Measure-Object Length -Sum).Sum
Write-Host ("payload  {0:N1} MB" -f ($bytes / 1MB))

# --- 4. compile --------------------------------------------------------------
New-Item -ItemType Directory -Force -Path (Join-Path $repo "..\dist") | Out-Null
$nsi = Join-Path $here "CielNosurgeDX-zh-Hans.nsi"
Write-Host "compiling with NSIS"
& $Nsis "/DPATCH_VERSION=$Version" "/DGAME_VERSION=$GameVersion" $nsi
if ($LASTEXITCODE -ne 0) { throw "makensis failed" }

$out = Join-Path $repo "..\dist\CielNosurgeDX-zh-Hans-$Version-setup.exe"
if (Test-Path $out) {
    $h = (Get-FileHash $out -Algorithm SHA256).Hash.ToLower()
    Write-Host ""
    Write-Host "installer  $out"
    Write-Host ("size       {0:N1} MB" -f ((Get-Item $out).Length / 1MB))
    Write-Host "sha256     $h"
    Set-Content -Path "$out.sha256" -Value "$h  $(Split-Path -Leaf $out)" -Encoding ASCII
}
