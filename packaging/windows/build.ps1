# Build the Windows installer for Voiceprint Studio (声纹工坊).
#
# Requirements:
#   - Python 3.10+ with requirements-dev.txt installed
#   - Inno Setup 6 (https://jrsoftware.org/isdl.php) - iscc.exe on PATH or in
#     "C:\Program Files (x86)\Inno Setup 6\"
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
#   powershell ... -File packaging\windows\build.ps1 -SkipBuild

param(
    [switch]$SkipBuild,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

if (-not $Python) {
    $venvPython = Join-Path $Root ".venv\Scripts\python.exe"
    $Python = if (Test-Path $venvPython) { $venvPython } else { "python" }
}

$Exe = Join-Path $Root "dist\VoiceprintStudio\VoiceprintStudio.exe"

if (-not (Test-Path "src\voiceprint_studio\resources\icon.ico")) {
    Write-Host "==> generating icons"
    & $Python "scripts\make_icons.py"
    if ($LASTEXITCODE -ne 0) { throw "icon generation failed" }
}

if (-not (Test-Path "src\voiceprint_studio\resources\pretrained_eres2netv2.ckpt")) {
    Write-Host "==> downloading model checkpoint"
    & $Python "scripts\download_model.py"
    if ($LASTEXITCODE -ne 0) { throw "model download failed" }
}

if (-not $SkipBuild) {
    Write-Host "==> building VoiceprintStudio.exe"
    & $Python -m PyInstaller --noconfirm --clean "packaging\voiceprint_studio.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
}

if (-not (Test-Path $Exe)) {
    throw "$Exe not found; run without -SkipBuild"
}

Write-Host "==> verifying frozen self-test"
& $Exe --self-test
if ($LASTEXITCODE -ne 0) { throw "self-test failed" }

$Iscc = $env:ISCC
if (-not $Iscc) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { $Iscc = $candidate; break }
    }
}
if (-not $Iscc) {
    $Iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
}
if (-not $Iscc) {
    throw "ISCC.exe (Inno Setup 6) not found. Install it or set `$env:ISCC."
}

Write-Host "==> compiling installer with $Iscc"
& $Iscc "packaging\windows\voiceprint_studio.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed" }

$Setup = Join-Path $Root "dist\VoiceprintStudio-1.0.0-Setup.exe"
Write-Host ""
Write-Host "Done: $Setup"