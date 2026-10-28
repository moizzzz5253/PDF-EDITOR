# PDF//SCOPE first-run setup.
#
# Run by 'Start PDF Scope.vbs' when venv\ is missing or requirements.txt changed.
#   1. Reuse venv\ if it works. Otherwise find Python 3.10+, offering to install it with
#      winget (per-user, no admin) or to open python.org if that is not possible.
#   2. Create venv\ and install requirements.txt into it.
#   3. Once per venv, offer LibreOffice (only needed for Word to PDF).
# Writes logs\setup.log. Exit code 0 = ready, 1 = not ready (the user has been told why).
#
# By hand:  powershell -NoProfile -ExecutionPolicy Bypass -File launcher\setup.ps1 [-NoPrompt]
# -NoPrompt skips the optional LibreOffice question.
param([switch]$NoPrompt)

$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root 'venv'
$VenvPy = Join-Path $Venv 'Scripts\python.exe'
$Req = Join-Path $Root 'requirements.txt'
$Marker = Join-Path $Venv '.requirements.installed'
$AskedLO = Join-Path $Venv '.libreoffice-asked'
$LogDir = Join-Path $Root 'logs'
$Log = Join-Path $LogDir 'setup.log'
$Title = 'PDF//SCOPE setup'
$PythonPage = 'https://www.python.org/downloads/windows/'

New-Item -ItemType Directory -Force $LogDir | Out-Null
$Host.UI.RawUI.WindowTitle = $Title
$Shell = New-Object -ComObject WScript.Shell

function Say($text) {
    Write-Host $text
    Add-Content -Path $Log -Value ("{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $text)
}

# Yes/No dialog. Returns $true for Yes.
function Ask($text) { return $Shell.Popup($text, 0, $Title, 4 + 32) -eq 6 }

function Fail($text) {
    Say "FAILED: $text"
    [void]$Shell.Popup("$text`n`nDetails: $Log", 0, $Title, 16)
    exit 1
}

# Runs a program and copies its output to the console and the log. Returns the exit code.
function Run($exe, [string[]]$arguments) {
    Say "> $exe $($arguments -join ' ')"
    & $exe @arguments 2>&1 | ForEach-Object { Say "  $_" }
    return $LASTEXITCODE
}

# Full path of a Python 3.10+ interpreter, or $null. The Microsoft Store 'python.exe'
# placeholder fails this check (it exits with 9009 when given arguments).
function Test-Python($exe, [string[]]$pre) {
    try {
        $out = & $exe @pre -c "import sys; print(sys.version_info >= (3, 10)); print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out.Count -ge 2 -and $out[0] -eq 'True') { return $out[1] }
    } catch {}
    return $null
}

# Prefers a regular install over a Microsoft Store Python: the Store one lives in a versioned
# WindowsApps folder that changes on every Store update, which breaks venvs built from it.
function Find-Python {
    $found = @()
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) { $found += Test-Python $py.Source @('-3') }
    foreach ($c in @(Get-Command python.exe -All -ErrorAction SilentlyContinue)) {
        $found += Test-Python $c.Source @()
    }
    # Freshly installed Pythons are not on this window's PATH yet, so look in the usual folders.
    $dirs = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*", "$env:ProgramFiles\Python3*" -Directory -ErrorAction SilentlyContinue
    foreach ($d in $dirs) {
        $exe = Join-Path $d.FullName 'python.exe'
        if (Test-Path $exe) { $found += Test-Python $exe @() }
    }
    $found = @($found | Where-Object { $_ })
    $regular = @($found | Where-Object { $_ -notlike '*\WindowsApps\*' })
    if ($regular.Count) { return $regular[0] }
    if ($found.Count) { return $found[0] }
    return $null
}

function Update-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}

function Find-LibreOffice {
    if ($env:PDFSCOPE_SOFFICE) { return $env:PDFSCOPE_SOFFICE }
    $cmd = Get-Command soffice -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if ($base) {
            $exe = Join-Path $base 'LibreOffice\program\soffice.exe'
            if (Test-Path $exe) { return $exe }
        }
    }
    return $null
}

$HasWinget = [bool](Get-Command winget.exe -ErrorAction SilentlyContinue)
Say "=== PDF//SCOPE setup in $Root"

# ---------------------------------------------------------------- 1. Python + venv
if ((Test-Path $VenvPy) -and (Test-Python $VenvPy @())) {
    Say "Using the existing environment in venv\"
} else {
    if (Test-Path $Venv) {
        Say "venv\ is incomplete or broken (for example, its Python was uninstalled). Rebuilding it."
        Remove-Item -Recurse -Force $Venv
    }

    Say "Looking for Python 3.10 or newer..."
    $Python = Find-Python
    if (-not $Python) {
        Say "Python 3.10+ was not found."
        if ($HasWinget -and (Ask "PDF//SCOPE needs Python, and it is not installed on this computer.`n`nInstall Python 3.12 now? It installs for your user only and takes a minute or two.")) {
            Say "Installing Python 3.12 with winget. Windows may ask you to confirm."
            $rc = Run 'winget.exe' @('install', '--id', 'Python.Python.3.12', '--exact', '--scope', 'user', '--silent',
                                    '--accept-package-agreements', '--accept-source-agreements')
            Update-Path
            $Python = Find-Python
            if (-not $Python) { Fail "Python could not be installed automatically (winget exit code $rc).`n`nInstall it from $PythonPage, then double-click Start PDF Scope again." }
        } else {
            Start-Process $PythonPage
            [void]$Shell.Popup("Install Python from the page that just opened (the big 'Download Python' button).`n`nIn the installer, tick 'Add python.exe to PATH' at the bottom of the first screen, then click Install Now.`n`nWhen it finishes, double-click Start PDF Scope again.", 0, $Title, 64)
            Say "Sent the user to $PythonPage"
            exit 1
        }
    }
    Say "Found Python: $Python"

    Say "Creating venv\ ..."
    if ((Run $Python @('-m', 'venv', $Venv)) -ne 0 -or -not (Test-Path $VenvPy)) { Fail "Could not create the Python environment in $Venv." }
}

# ---------------------------------------------------------------- 2. Packages
Say "Installing packages (the first time downloads about 100 MB)..."
[void](Run $VenvPy @('-m', 'pip', 'install', '--upgrade', '--disable-pip-version-check', 'pip'))
if ((Run $VenvPy @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', $Req)) -ne 0) {
    Fail "Installing the packages failed. Check your internet connection, then double-click Start PDF Scope again."
}
Copy-Item -Force $Req $Marker
Say "Packages installed."

# ---------------------------------------------------------------- 3. LibreOffice (optional)
$lo = Find-LibreOffice
if ($lo) {
    Say "LibreOffice found: $lo"
} elseif ($NoPrompt -or (Test-Path $AskedLO)) {
    Say "LibreOffice not installed. Word to PDF is unavailable; everything else works."
} else {
    New-Item -ItemType File -Force $AskedLO | Out-Null
    if ($HasWinget -and (Ask "Optional: Word to PDF needs LibreOffice (free, about 350 MB). Everything else works without it.`n`nInstall LibreOffice now?")) {
        Say "Installing LibreOffice with winget. Windows may ask you to confirm."
        $rc = Run 'winget.exe' @('install', '--id', 'TheDocumentFoundation.LibreOffice', '--exact', '--silent',
                                '--accept-package-agreements', '--accept-source-agreements')
        if (Find-LibreOffice) { Say "LibreOffice installed." }
        else { Say "LibreOffice was not installed (winget exit code $rc). Word to PDF stays unavailable." }
    } else {
        Say "Skipped LibreOffice. Install it later from https://www.libreoffice.org to enable Word to PDF."
    }
}

Say "=== Setup complete."
exit 0
