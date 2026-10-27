# Short CPU-only C/virtual-bench verification. Never a GPU/search launcher.
param(
    [Parameter(Mandatory=$true)][ValidateSet('tests','host-build','arm-build','virtual-check','package-check')][string]$Phase,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-z0-9-]{1,40}$')][string]$Attempt,
    [Parameter(Mandatory=$true)][string]$PythonExe,
    [string]$HostCompiler='', [string]$ArmToolchain='', [string]$Qemu='', [string]$Firmware='',
    [string]$EvidenceRoot='work/ev-readiness-20261027'
)
$ErrorActionPreference='Stop'
$evRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $evRoot
$evEvidence=[IO.Path]::GetFullPath((Join-Path $evRoot $EvidenceRoot))
if(-not $evEvidence.StartsWith($evRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){
    throw 'Evidence must stay inside the selected checkout'
}
New-Item -ItemType Directory -Path $evEvidence -Force | Out-Null
$evPrefix=Join-Path $evEvidence "$Phase-$Attempt"
foreach($evSuffix in @('.guard.json','.stdout.txt','.stderr.txt','.junit.xml','')){
    if(Test-Path -LiteralPath ($evPrefix+$evSuffix)){throw 'Preserve previous evidence; choose a new attempt'}
}
function Quote-Path([string]$Value){
    if($Value.Contains('"')){throw 'Unsupported quote in explicit path'}
    return '"'+$Value+'"'
}
$evPython=(Resolve-Path -LiteralPath $PythonExe).Path
$evMemory=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
$evHeadroom=($evMemory.CommitLimit-$evMemory.CommittedBytes)/1GB
# A measured short Python/compiler/QEMU fixture, not a full numerical batch.
# Heavy simulator/search admission remains 10 GiB in its original launcher.
$evAllowance=.75
if($evHeadroom -lt (8+$evAllowance)){
    [pscustomobject]@{utc=(Get-Date -AsUTC -Format o);outcome='admission_refused';phase=$Phase;processLaunched=$false;headroomGiB=$evHeadroom;reserveGiB=8;jobAllowanceGiB=$evAllowance} |
        ConvertTo-Json | Set-Content -LiteralPath ($evPrefix+'.guard.json') -Encoding utf8
    throw 'Short-bench admission refused; no launch and no polling retry'
}
$env:PYTHONPATH=Join-Path $evRoot 'src'
$env:OMP_NUM_THREADS='1';$env:OPENBLAS_NUM_THREADS='1';$env:MKL_NUM_THREADS='1'
if($Phase -eq 'package-check'){
    # Process-local trust for this already-selected checkout; no global Git edit.
    $env:GIT_CONFIG_COUNT='1';$env:GIT_CONFIG_KEY_0='safe.directory';$env:GIT_CONFIG_VALUE_0=$evRoot
}
if($HostCompiler){$env:CC=(Resolve-Path -LiteralPath $HostCompiler).Path}
$evArgs=switch($Phase){
    'tests' { @('-u','-m','pytest','tests/test_team_vehicle_spec.py','tests/test_team_spec_resources.py','tests/test_constrained_actuation.py',
        'tests/test_incremental_controller_backend.py','tests/test_native_closed_loop.py',
        'tests/test_stm32_bench_build.py','tests/test_stm32_bench_protocol.py','-q','--maxfail=2',
        ('--junitxml='+ (Quote-Path ($evPrefix+'.junit.xml')))) }
    'host-build' {
        if(-not $HostCompiler){throw 'Explicit installed host compiler required'}
        @('-u','-m','lapsim.experiments.native_controller','--cc',(Quote-Path $env:CC),'--output-dir',(Quote-Path $evPrefix))
    }
    'arm-build' {
        if(-not $ArmToolchain){throw 'Explicit installed Arm GNU 12.3 toolchain required'}
        @('-u','scripts/build_stm32_bench.py','--toolchain-dir',(Quote-Path $ArmToolchain),'--output-dir',(Quote-Path $evPrefix))
    }
    'virtual-check' {
        if(-not $Qemu -or -not $Firmware){throw 'Explicit QEMU executable and bench ELF required'}
        if([IO.Path]::GetFileName($Qemu) -ne 'qemu-system-arm.exe'){throw 'This Windows guard accepts the explicit ARM system emulator only'}
        @('-u','quality/run_stm32_bench.py','--qemu',(Quote-Path $Qemu),'--elf',(Quote-Path $Firmware),'--output-dir',(Quote-Path $evPrefix))
    }
    'package-check' { @('-u','setup.py','build_py','--build-lib',(Quote-Path $evPrefix)) }
}
$evProcess=Start-Process -FilePath $evPython -ArgumentList $evArgs -WorkingDirectory $evRoot -WindowStyle Hidden `
    -RedirectStandardOutput ($evPrefix+'.stdout.txt') -RedirectStandardError ($evPrefix+'.stderr.txt') -PassThru
$evProcess.PriorityClass='BelowNormal';$evStarted=$evProcess.StartTime.ToUniversalTime()
$evClock=[Diagnostics.Stopwatch]::StartNew();$evSamples=@();$evAbort=$null
Write-Output "Started owned short $Phase job $($evProcess.Id); headroom $([math]::Round($evHeadroom,3)) GiB"
while(-not $evProcess.HasExited){
    try {
        $evMemory=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
        $evAvailable=($evMemory.CommitLimit-$evMemory.CommittedBytes)/1GB
        $evSamples+=[pscustomobject]@{utc=(Get-Date -AsUTC -Format o);headroomGiB=$evAvailable;elapsedWallS=$evClock.Elapsed.TotalSeconds}
        if($evAvailable -lt 8){$evAbort='commit_reserve_breached'}
    } catch {
        # Loss of monitoring is an abort, never permission to run unguarded.
        $evAbort='memory_monitor_unavailable'
    }
    if($evClock.Elapsed.TotalSeconds -gt 180){$evAbort='wall_budget_exceeded'}
    if($evAbort){
        $evExact=Get-Process -Id $evProcess.Id -ErrorAction SilentlyContinue
        if($evExact -and $evExact.StartTime.ToUniversalTime() -eq $evStarted -and $evExact.Path -eq $evPython){
            & taskkill.exe /PID $evProcess.Id /T /F
            if($LASTEXITCODE -ne 0){throw 'Owned process stop outcome uncertain'}
        }
        break
    }
    Start-Sleep -Milliseconds 500
    $evProcess.Refresh()
}
if(-not $evProcess.WaitForExit(10000)){throw 'Owned process exit outcome uncertain'}
$evProcess.Refresh()
$evReceipt=[pscustomobject]@{utc=(Get-Date -AsUTC -Format o);phase=$Phase;outcome=$(if($evAbort){$evAbort}else{'process_completed'});processLaunched=$true;
    launcherPid=$evProcess.Id;launcherStartedUtc=$evStarted.ToString('o');exitCode=$evProcess.ExitCode;reserveGiB=8;jobAllowanceGiB=$evAllowance;
    headroomBeforeGiB=$evHeadroom;wallSeconds=$evClock.Elapsed.TotalSeconds;samples=$evSamples;
    scope='Short serial CPU host/ARM/virtual-bench acceptance only; no GPU, installation, physical device or settings changes'}
$evReceipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath ($evPrefix+'.guard.json') -Encoding utf8
$evReceipt | Select-Object utc,phase,outcome,exitCode,headroomBeforeGiB,wallSeconds | ConvertTo-Json
if($evAbort){exit 1}
exit $evProcess.ExitCode
