param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "LapSim's .venv is missing. Run setup_lapsim.cmd first."
}

# Keep each test process small on machines with a tight Windows commit limit.
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"

$tkInfo = @(& $venvPython -c 'import _tkinter, sys; print(sys.base_prefix); print(_tkinter.TCL_VERSION); print(_tkinter.TK_VERSION)')
if ($LASTEXITCODE -ne 0 -or $tkInfo.Count -ne 3) {
    throw "Could not inspect this Python installation's Tk libraries."
}
$baseTcl = Join-Path $tkInfo[0] "tcl"
$tclLibrary = Join-Path $baseTcl ("tcl" + $tkInfo[1])
$tkLibrary = Join-Path $baseTcl ("tk" + $tkInfo[2])
if (Test-Path -LiteralPath (Join-Path $tclLibrary "init.tcl")) {
    $env:TCL_LIBRARY = $tclLibrary
}
if (Test-Path -LiteralPath (Join-Path $tkLibrary "tk.tcl")) {
    $env:TK_LIBRARY = $tkLibrary
}

$testFiles = @(Get-ChildItem -LiteralPath (Join-Path $projectRoot "tests") -File -Filter "test_*.py" | Sort-Object Name)
if ($testFiles.Count -eq 0) {
    throw "No repository test files were found."
}
$chunkSize = 15

Push-Location $projectRoot
try {
    for ($start = 0; $start -lt $testFiles.Count; $start += $chunkSize) {
        $length = [Math]::Min($chunkSize, $testFiles.Count - $start)
        $targets = @($testFiles | Select-Object -Skip $start -First $length -ExpandProperty FullName)
        $groupNumber = [int][Math]::Floor($start / $chunkSize) + 1
        Write-Host "LapSim test group $groupNumber ($length files)..."
        & $venvPython -m pytest -q -rs @targets
        if ($LASTEXITCODE -ne 0) {
            throw "Test group $groupNumber failed. Fix it before presenting results."
        }
    }
    Write-Host "All $($testFiles.Count) LapSim test files passed."
}
finally {
    Pop-Location
}
