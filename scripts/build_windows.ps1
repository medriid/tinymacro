$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

function Say($message) {
    Write-Host ""
    Write-Host "==> $message"
}

function Need-Command($name, $message) {
    $command = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Missing command '$name'. $message"
    }
}

function Invoke-Native {
    & $args[0] @($args | Select-Object -Skip 1)
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $($args -join ' ')"
    }
}

function Remove-WithRetry($path, [switch]$Recurse) {
    if (-not (Test-Path -LiteralPath $path)) {
        return
    }
    for ($attempt = 1; $attempt -le 10; $attempt++) {
        try {
            if ($Recurse) {
                Remove-Item -LiteralPath $path -Recurse -Force
            } else {
                Remove-Item -LiteralPath $path -Force
            }
            return
        } catch {
            if ($attempt -eq 10) {
                throw
            }
            Start-Sleep -Milliseconds (250 * $attempt)
        }
    }
}

Say "Tiny Macro Windows build preflight"
Write-Host "Project: $root"

Need-Command "py" "Install Python 3.12 or newer for Windows."

$pythonVersion = py -3.14 -c "import sys; print(sys.version.split()[0])"
Write-Host "Python: $pythonVersion"

Say "Recreating build virtualenv"
if (Test-Path -LiteralPath ".venv-windows-build") {
    Remove-WithRetry ".venv-windows-build" -Recurse
}
py -3.14 -m venv .venv-windows-build

$python = Join-Path $root ".venv-windows-build\Scripts\python.exe"
$pyinstaller = Join-Path $root ".venv-windows-build\Scripts\pyinstaller.exe"

Say "Installing Tiny Macro and PyInstaller"
Invoke-Native $python -m pip install --upgrade pip wheel setuptools
Invoke-Native $python -m pip install --timeout 120 --retries 20 -e ".[build,vision]"

Say "Regenerating multi-resolution app icon"
$env:QT_QPA_PLATFORM = "offscreen"
Invoke-Native $python -c "from tinymacro.gui.icons import render_app_ico, ICON_DIR; render_app_ico(ICON_DIR / 'app' / 'app.ico')"
Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue

Say "Cleaning old Windows build output"
if (Test-Path -LiteralPath "build") {
    Remove-WithRetry "build" -Recurse
}
if (Test-Path -LiteralPath "dist\tiny-macro-windows") {
    Remove-WithRetry "dist\tiny-macro-windows" -Recurse
}
New-Item -ItemType Directory -Force -Path "dist" | Out-Null

Say "Building onedir Windows app"
Invoke-Native $pyinstaller --clean --noconfirm "packaging\tiny-macro-windows.spec"

$exe = Join-Path $root "dist\tiny-macro-windows\tiny-macro-windows.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "PyInstaller finished but $exe was not created."
}

@"
Tiny Macro Windows build

Run:
  tiny-macro-windows.exe

The Windows build uses native low-level keyboard/mouse hooks for global capture
and hotkeys, and SendInput for playback.

Notes:
  - Normal desktop apps should work.
  - To control elevated/admin apps, run Tiny Macro as administrator too.
  - Some games, anti-cheat software, raw-input apps, or protected windows may
    block synthetic input.
  - Antivirus tools may flag macro recorders because they globally capture and
    replay keyboard and mouse input.
"@ | Set-Content -LiteralPath (Join-Path $root "dist\README-WINDOWS.txt") -Encoding UTF8

Say "Build complete"
Write-Host "Executable: $exe"
Write-Host "Notes:      $(Join-Path $root "dist\README-WINDOWS.txt")"
