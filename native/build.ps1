<#
.SYNOPSIS
  Build cielzh.dll, the native display layer.

.DESCRIPTION
  /MT on purpose: the result imports KERNEL32 and nothing else, so the player
  needs no Visual C++ redistributable and the loader has no other DLL to find.

  The toolchain is located with vswhere rather than a fixed path, so a Visual
  Studio update does not silently stop building.
#>
[CmdletBinding()]
param(
    [ValidateSet("Debug", "Release")]
    [string]$Config = "Release",
    [string]$Out = ""
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Out) { $Out = Join-Path $here "build" }

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) { throw "vswhere.exe is not there; is Visual Studio installed?" }
$vsroot = & $vswhere -latest -products * `
    -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
    -property installationPath
if (-not $vsroot) { throw "no Visual Studio with the C++ x64 tools" }
$vcvars = Join-Path $vsroot "VC\Auxiliary\Build\vcvars64.bat"
if (-not (Test-Path $vcvars)) { throw "vcvars64.bat is not at $vcvars" }

New-Item -ItemType Directory -Force -Path $Out | Out-Null
$src = (Get-ChildItem (Join-Path $here "cielzh") -Filter *.cpp | ForEach-Object { $_.FullName })

$flags = if ($Config -eq "Release") { "/O2 /DNDEBUG" } else { "/Od /Zi /DDEBUG" }
$common = "/nologo /LD /MT /W4 /WX /EHsc /GS /guard:cf /std:c++17 /utf-8 $flags"
$common2 = "/nologo /MT /W4 /WX /EHsc /GS /guard:cf /std:c++17 /utf-8 $flags"
$link = "/DYNAMICBASE /NXCOMPAT /INCREMENTAL:NO"

$quoted = ($src | ForEach-Object { '"' + $_ + '"' }) -join " "
$dll = Join-Path $Out "cielzh.dll"
$cmd = "call `"$vcvars`" >nul 2>&1 && cd /d `"$Out`" && cl $common $quoted /link $link /OUT:`"$dll`""

Write-Host "config   $Config"
Write-Host "toolchain $vsroot"
& cmd /c $cmd
if ($LASTEXITCODE -ne 0) { throw "cl failed" }

# --- self-test ---------------------------------------------------------------
# Built from the same sources, not against the DLL: the recorder and the
# verifier are what these check, and linking them in directly keeps the test
# honest about which code it ran.
$test = Join-Path $Out "selftest.exe"
$testsrc = (Join-Path $here "test\selftest.cpp")
$libsrc = ($src | Where-Object { $_ -notmatch "dllmain\.cpp$" } |
           ForEach-Object { '"' + $_ + '"' }) -join " "
$tcmd = "call `"$vcvars`" >nul 2>&1 && cd /d `"$Out`" && cl $common2 `"$testsrc`" $libsrc /link $link /OUT:`"$test`""
& cmd /c $tcmd
if ($LASTEXITCODE -ne 0) { throw "self-test build failed" }
& $test
if ($LASTEXITCODE -ne 0) { throw "self-test failed" }

# --- entry chain test --------------------------------------------------------
# The emitted stub is exercised end to end: a stand-in call site, the real
# bytes, a fake IAT, and a probe for the original target.  Calling the DLL
# export directly cannot see whether the intercepted call's arguments survive.
$etest = Join-Path $Out "test_entry.exe"
$esrc = @(
    (Join-Path $here (Join-Path "test" "test_entry.cpp")),
    (Join-Path $here (Join-Path "loader" "entrycode.cpp"))
) | ForEach-Object { '"' + $_ + '"' }
$ecmd = "call `"$vcvars`" >nul 2>&1 && cd /d `"$Out`" && cl $common2 " +
        ($esrc -join " ") + " /link $link /OUT:`"$etest`""
& cmd /c $ecmd
if ($LASTEXITCODE -ne 0) { throw "entry test build failed" }
& $etest
if ($LASTEXITCODE -ne 0) { throw "entry test failed" }

# --- emit tool ---------------------------------------------------------------
# Produces the entry block for a layout the PE tool computes.  Built here so the
# bytes written into the executable come from the same source the tests run.
$emit = Join-Path $Out "emit_entry.exe"
$msrc = @(
    (Join-Path $here (Join-Path "loader" "emit_tool.cpp")),
    (Join-Path $here (Join-Path "loader" "entrycode.cpp"))
) | ForEach-Object { '"' + $_ + '"' }
$mcmd = "call `"$vcvars`" >nul 2>&1 && cd /d `"$Out`" && cl $common2 " +
        ($msrc -join " ") + " /link $link /OUT:`"$emit`""
& cmd /c $mcmd
if ($LASTEXITCODE -ne 0) { throw "emit tool build failed" }

$h = (Get-FileHash $dll -Algorithm SHA256).Hash.ToLower()
Write-Host ""
Write-Host "dll      $dll"
Write-Host "size     $([math]::Round((Get-Item $dll).Length / 1kb, 1)) KB"
Write-Host "sha256   $h"
