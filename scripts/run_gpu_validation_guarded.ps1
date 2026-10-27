# One bounded GPU validation process; unchanged 10 GiB admission / 8 GiB reserve.
param(
    [Parameter(Mandatory=$true)][ValidateSet('tests','powered-tests','resident-tests','resident-only','resident-count-tests','resident-benchmark','tournament-tests','integration-tests','search-tests','policy-probes','search-evaluate','representative-laps','courses-laps','benchmark','powered-benchmark')][string]$Phase,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-z0-9-]{1,32}$')][string]$Attempt,
    [string]$Device='NVIDIA GeForce RTX 5080',
    [string]$PythonExe='',
    [string]$BaselineRoot='',
    [string]$ReferenceRoot='',
    [ValidatePattern('^[a-z0-9_-]{1,80}$')][string]$Candidate='',
    [ValidateSet('train','heldout-a','heldout-b')][string]$Scenario='train',
    [string]$SearchDirectory='work/gpu-search-20261026'
)
$ErrorActionPreference='Stop'
$gpuTaskRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $gpuTaskRoot
$gpuEvidence="work/gpu-readiness-20261026/$Phase-$Attempt"
$gpuEvidenceDirectory=Split-Path -Parent $gpuEvidence
if(-not(Test-Path -LiteralPath $gpuEvidenceDirectory)){New-Item -ItemType Directory -Path $gpuEvidenceDirectory -Force | Out-Null}
foreach($gpuSuffix in @('.guard.json','.stdout.txt','.stderr.txt','.junit.xml','.benchmark.json')){
    if(Test-Path -LiteralPath ($gpuEvidence+$gpuSuffix)){throw 'Preserve prior evidence; choose a new attempt'}
}
$gpuMemory=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
$gpuHeadroom=($gpuMemory.CommitLimit-$gpuMemory.CommittedBytes)/1GB
if($gpuHeadroom -lt 10){
    [pscustomobject]@{utc=(Get-Date -AsUTC -Format o);outcome='admission_refused';headroomGiB=$gpuHeadroom;reserveGiB=8;jobAllowanceGiB=2;processLaunched=$false} | ConvertTo-Json | Set-Content "$gpuEvidence.guard.json" -Encoding utf8
    throw 'Reserve plus job allowance unavailable; no launch and no polling retry'
}
$env:PYTHONPATH=Join-Path $gpuTaskRoot 'src'
$env:OMP_NUM_THREADS='1';$env:OPENBLAS_NUM_THREADS='1';$env:MKL_NUM_THREADS='1'
$env:LAPSIM_TEST_GPU=$Device
$gpuPython=if($PythonExe){(Resolve-Path -LiteralPath $PythonExe).Path}else{Join-Path $gpuTaskRoot '.venv\Scripts\python.exe'}
$gpuArgs=if($Phase -eq 'tests'){
    @('-u','-m','pytest','tests/test_planar_opencl.py','tests/test_planar_dynamics.py','tests/test_powered_opencl.py','tests/test_powered_planar.py','-q','--maxfail=2',"--junitxml=$gpuEvidence.junit.xml")
}elseif($Phase -eq 'search-tests'){
    @('-u','-m','pytest','tests/test_gpu_search.py','tests/test_tournament_scoring.py','tests/test_gpu_tournament.py','-q','--maxfail=2',"--junitxml=$gpuEvidence.junit.xml")
}elseif($Phase -eq 'policy-probes'){
    @('-u','scripts/validate_gpu_rollouts.py','--phase','policies','--device',('"'+$Device+'"'),'--output',"$gpuEvidence.validation.json")
}elseif($Phase -eq 'search-evaluate'){
    if(-not $Candidate){throw 'Explicit search candidate required'}
    @('-u','scripts/run_gpu_search.py','--directory',('"'+$SearchDirectory+'"'),'--run',$Candidate,'--scenario',$Scenario)
}elseif($Phase -eq 'integration-tests'){
    @('-u','-m','pytest','tests/test_controller_tournament.py','tests/test_tournament_courses.py','tests/test_gpu_tournament.py','tests/test_resident_powered.py','-q','--maxfail=2',"--junitxml=$gpuEvidence.junit.xml")
}elseif($Phase -eq 'representative-laps'){
    $gpuLapArgs=@('-u','scripts/validate_gpu_rollouts.py','--phase','representative','--device',('"'+$Device+'"'),'--output',"$gpuEvidence.validation.json")
    if($ReferenceRoot){$gpuLapArgs+=@('--reuse-cpu',('"'+(Resolve-Path -LiteralPath $ReferenceRoot).Path+'"'))}
    $gpuLapArgs
}elseif($Phase -eq 'courses-laps'){
    if(-not $BaselineRoot){throw 'Explicit CPU baseline root required'}
    @('-u','scripts/validate_gpu_rollouts.py','--phase','courses','--baseline-root',('"'+(Resolve-Path -LiteralPath $BaselineRoot).Path+'"'),'--device',('"'+$Device+'"'),'--output',"$gpuEvidence.validation.json")
}elseif($Phase -eq 'tournament-tests'){
    @('-u','-m','pytest','tests/test_gpu_tournament.py','-q','--maxfail=2',"--junitxml=$gpuEvidence.junit.xml")
}elseif($Phase -eq 'resident-benchmark'){
    @('-u','scripts/benchmark_resident_gpu.py','--device',('"'+$Device+'"'),'--output',"$gpuEvidence.benchmark.json")
}elseif($Phase -eq 'resident-count-tests'){
    @('-u','-m','pytest','tests/test_resident_powered.py','-k','substep_count','-q','--maxfail=2',"--junitxml=$gpuEvidence.junit.xml")
}elseif($Phase -eq 'resident-only'){
    @('-u','-m','pytest','tests/test_resident_powered.py','-q','--maxfail=2',"--junitxml=$gpuEvidence.junit.xml")
}elseif($Phase -eq 'resident-tests'){
    @('-u','-m','pytest','tests/test_planar_opencl.py','tests/test_powered_opencl.py','tests/test_resident_powered.py','-q','--maxfail=2',"--junitxml=$gpuEvidence.junit.xml")
}elseif($Phase -eq 'powered-tests'){
    @('-u','-m','pytest','tests/test_powered_opencl.py','-q','--maxfail=2',"--junitxml=$gpuEvidence.junit.xml")
}elseif($Phase -eq 'powered-benchmark'){
    @('-u','scripts/benchmark_powered_gpu.py','--device',('"'+$Device+'"'),'--output',"$gpuEvidence.benchmark.json")
}else{
    @('-u','scripts/benchmark_planar_gpu.py','--device',('"'+$Device+'"'),'--saved-course-samples','--output',"$gpuEvidence.benchmark.json")
}
$gpuProcess=Start-Process -FilePath $gpuPython -ArgumentList $gpuArgs -WorkingDirectory $gpuTaskRoot -WindowStyle Hidden -RedirectStandardOutput "$gpuEvidence.stdout.txt" -RedirectStandardError "$gpuEvidence.stderr.txt" -PassThru
$gpuProcess.PriorityClass='BelowNormal'
$gpuStarted=$gpuProcess.StartTime.ToUniversalTime()
$gpuClock=[Diagnostics.Stopwatch]::StartNew();$gpuSamples=@();$gpuAbort=$null
Write-Output "Started owned GPU validation $($gpuProcess.Id); commit headroom $([math]::Round($gpuHeadroom,3)) GiB"
while(-not $gpuProcess.HasExited){
    $gpuMemory=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
    $gpuAvailable=($gpuMemory.CommitLimit-$gpuMemory.CommittedBytes)/1GB
    $gpuSamples+=[pscustomobject]@{utc=(Get-Date -AsUTC -Format o);headroomGiB=$gpuAvailable;elapsedWallS=$gpuClock.Elapsed.TotalSeconds}
    if($gpuAvailable -lt 8){$gpuAbort='commit_reserve_breached'}
    if($gpuClock.Elapsed.TotalSeconds -gt 180){$gpuAbort='wall_budget_exceeded'}
    if($gpuAbort){
        $gpuExact=Get-Process -Id $gpuProcess.Id -ErrorAction SilentlyContinue
        if($gpuExact -and $gpuExact.StartTime.ToUniversalTime() -eq $gpuStarted -and $gpuExact.Path -eq $gpuPython){
            & taskkill.exe /PID $gpuProcess.Id /T /F
            if($LASTEXITCODE -ne 0){throw 'Exact owned stop outcome uncertain'}
        }
        break
    }
    Start-Sleep -Seconds 2
    $gpuProcess.Refresh()
}
$gpuProcess.WaitForExit();$gpuProcess.Refresh()
$gpuRecord=[pscustomobject]@{utc=(Get-Date -AsUTC -Format o);outcome=$(if($gpuAbort){$gpuAbort}else{'process_completed'});processLaunched=$true;phase=$Phase;candidate=$Candidate;scenario=$Scenario;device=$Device;launcherPid=$gpuProcess.Id;launcherStartedUtc=$gpuStarted.ToString('o');exitCode=$gpuProcess.ExitCode;reserveGiB=8;jobAllowanceGiB=2;headroomBeforeGiB=$gpuHeadroom;wallSeconds=$gpuClock.Elapsed.TotalSeconds;samples=$gpuSamples;scope='One bounded optional OpenCL FP64 validation/search process; CPU screening preserved; 180 s outer cap; no installation, hardware actuation, browser or unrelated process changes'}
$gpuRecord | ConvertTo-Json -Depth 5 | Set-Content "$gpuEvidence.guard.json" -Encoding utf8
$gpuRecord | Select-Object utc,outcome,exitCode,headroomBeforeGiB,wallSeconds | ConvertTo-Json
if($gpuAbort){exit 1}
exit $gpuProcess.ExitCode
