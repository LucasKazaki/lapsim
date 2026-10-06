param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Bound native numerical-library workers in pip's build helpers and the
# preflight process, including machines with broad inherited BLAS defaults.
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"

$projectRoot = $PSScriptRoot
$venvDirectory = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvDirectory "Scripts\python.exe"
$checkScript = Join-Path $projectRoot "scripts\check_desktop.py"
$versionCheck = "import sys; sys.exit(0 if sys.version_info >= (3, 11) and sys.maxsize > 2**32 else 1)"

function Test-SupportedPython {
    param([string]$Executable, [string[]]$LauncherArguments)
    try {
        & $Executable @LauncherArguments -c $versionCheck 2>$null
        return $LASTEXITCODE -eq 0
    }
    catch {
        # Windows PowerShell can promote a missing `py -3.x` runtime's stderr
        # to a terminating error even though this is only a candidate probe.
        return $false
    }
}

function Find-SupportedPython {
    # Prefer the version used for this checkout's desktop verification when
    # available, while accepting any installed 64-bit Python 3.11 or newer.
    $candidates = @(
        @{ Executable = "py"; Arguments = @("-3.12") },
        @{ Executable = "py"; Arguments = @("-3.13") },
        @{ Executable = "py"; Arguments = @("-3.11") },
        @{ Executable = "py"; Arguments = @("-3") },
        @{ Executable = "python"; Arguments = @() },
        @{ Executable = "python3"; Arguments = @() }
    )
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Executable -ErrorAction SilentlyContinue
        if ($null -eq $command) { continue }
        $arguments = [string[]] $candidate.Arguments
        if (Test-SupportedPython -Executable $command.Source -LauncherArguments $arguments) {
            return @{ Executable = $command.Source; Arguments = $arguments }
        }
    }
    throw "Install 64-bit Python 3.11 or newer with Tk support, then rerun setup_lapsim.cmd."
}

Push-Location $projectRoot
try {
    if (Test-Path $venvPython) {
        if (-not (Test-SupportedPython -Executable $venvPython -LauncherArguments @())) {
            throw "Existing .venv uses an unsupported Python. Rename that folder and rerun setup."
        }
        Write-Host "Using the existing .venv."
    }
    else {
        if (Test-Path $venvDirectory) {
            throw "Existing .venv is incomplete. Rename that folder and rerun setup."
        }
        $basePython = Find-SupportedPython
        Write-Host "Creating .venv with $($basePython.Executable) $($basePython.Arguments -join ' ') ..."
        & $basePython.Executable @($basePython.Arguments) -m venv $venvDirectory
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
            throw "Python could not create .venv. Check the Python installation and free disk space."
        }
    }

    Write-Host "Installing LapSim and its required packages and test tool..."
    & $venvPython -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) {
        throw "Package installation failed. Check the pip error above and internet access."
    }

    Write-Host "Checking the desktop environment and bundled course..."
    & $venvPython $checkScript
    if ($LASTEXITCODE -ne 0) {
        throw "The desktop check failed. Read the error above; then rerun setup."
    }

    Write-Host "Setup complete. Double-click launch_lapsim.cmd to open LapSim."
}
catch {
    Write-Host "LapSim setup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    Pop-Location
}
