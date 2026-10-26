# E17-R10 one-candidate guard. Unchanged admission/reserve/180s wall policy.
# Invoke only in a newly coordinated slot; never loop after admission refusal.
param([Parameter(Mandatory=$true)][ValidateSet('tests','accept')][string]$Phase,[Parameter(Mandatory=$true)][ValidatePattern('^[a-z0-9-]{1,32}$')][string]$Attempt,[ValidatePattern('^[a-z0-9_-]{1,64}$')][string]$Candidate='awd')
$ErrorActionPreference='Stop'
$sensitivityRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $sensitivityRoot
$sensitivityPrefix="work/evidence/online-courses-$Phase-$Attempt"
if ((Test-Path "$sensitivityPrefix.guard.json") -or (Test-Path "$sensitivityPrefix.junit.xml") -or (Test-Path "$sensitivityPrefix.stdout.txt") -or (Test-Path "$sensitivityPrefix.stderr.txt") -or (Test-Path "$sensitivityPrefix.ga-admission.json")) {throw 'Preserve earlier evidence; choose a new coordinated attempt'}
$sensitivityMemory=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
$sensitivityBefore=($sensitivityMemory.CommitLimit-$sensitivityMemory.CommittedBytes)/1GB
if($sensitivityBefore -lt 10){
    [pscustomobject]@{utc=(Get-Date -AsUTC -Format o);outcome='admission_refused';headroomGiB=$sensitivityBefore;reserveGiB=8;jobAllowanceGiB=2;processLaunched=$false} | ConvertTo-Json | Set-Content "$sensitivityPrefix.guard.json" -Encoding utf8
    throw 'Reserve plus job allowance unavailable; no launch and no gate retry'
}
$env:PYTHONPATH=Join-Path $sensitivityRoot 'src'
$env:OMP_NUM_THREADS='1';$env:OPENBLAS_NUM_THREADS='1'
$sensitivityPython=Join-Path $sensitivityRoot '.venv\Scripts\python.exe'
$sensitivityGaBudget=$null
$sensitivityFrozen=$null
$sensitivityArgs=if($Phase -eq 'tests'){@('-u','-m','pytest','tests/test_online_courses.py','tests/test_course_library_web.py','-q','--maxfail=2',"--junitxml=$sensitivityPrefix.junit.xml")}else{@('-u','scripts/accept_online_course.py','--course',$Candidate,'--output',"$sensitivityPrefix.record.json")}
$sensitivityProcess=Start-Process -FilePath $sensitivityPython -ArgumentList $sensitivityArgs -WorkingDirectory $sensitivityRoot -WindowStyle Hidden -RedirectStandardOutput "$sensitivityPrefix.stdout.txt" -RedirectStandardError "$sensitivityPrefix.stderr.txt" -PassThru
$sensitivityProcess.PriorityClass='BelowNormal'
$sensitivityStarted=$sensitivityProcess.StartTime.ToUniversalTime()
$sensitivityClock=[Diagnostics.Stopwatch]::StartNew();$sensitivitySamples=@();$sensitivityAbort=$null
Write-Output "Started owned ten-lap launcher $($sensitivityProcess.Id); headroom $([math]::Round($sensitivityBefore,3)) GiB"
while(-not $sensitivityProcess.HasExited){
    $sensitivityMemory=Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory
    $sensitivityHeadroom=($sensitivityMemory.CommitLimit-$sensitivityMemory.CommittedBytes)/1GB
    $sensitivitySamples+=[pscustomobject]@{utc=(Get-Date -AsUTC -Format o);headroomGiB=$sensitivityHeadroom;elapsedWallS=$sensitivityClock.Elapsed.TotalSeconds}
    if($sensitivityHeadroom -lt 8){$sensitivityAbort='commit_reserve_breached'}
    if($sensitivityClock.Elapsed.TotalSeconds -gt 180){$sensitivityAbort='wall_budget_exceeded'}

    if($sensitivityAbort){
        $sensitivityExact=Get-Process -Id $sensitivityProcess.Id -ErrorAction SilentlyContinue
        if($sensitivityExact -and $sensitivityExact.StartTime.ToUniversalTime() -eq $sensitivityStarted -and $sensitivityExact.Path -eq $sensitivityPython){
            & taskkill.exe /PID $sensitivityProcess.Id /T /F
            if($LASTEXITCODE -ne 0){throw 'Exact owned stop outcome uncertain'}
        }
        break
    }
    Start-Sleep -Seconds 2
    $sensitivityProcess.Refresh()
}
$sensitivityProcess.WaitForExit();$sensitivityProcess.Refresh()
$sensitivityRecord=[pscustomobject]@{utc=(Get-Date -AsUTC -Format o);outcome=$(if($sensitivityAbort){$sensitivityAbort}else{'process_completed'});processLaunched=$true;campaignPhase=$Phase;candidateId=$Candidate;launcherPid=$sensitivityProcess.Id;launcherStartedUtc=$sensitivityStarted.ToString('o');exitCode=$sensitivityProcess.ExitCode;reserveGiB=8;jobAllowanceGiB=2;headroomBeforeGiB=$sensitivityBefore;wallSeconds=$sensitivityClock.Elapsed.TotalSeconds;initialGaBudgetBefore=$sensitivityGaBudget;samples=$sensitivitySamples;scope='One bounded R11 review job; 2 GiB admission allowance above unchanged 8 GiB reserve; below-normal priority; one native thread; 180 s wall cap; checkpoints each lap; no browser, hardware or unrelated process'}
$sensitivityRecord | ConvertTo-Json -Depth 5 | Set-Content "$sensitivityPrefix.guard.json" -Encoding utf8
$sensitivityRecord | Select-Object utc,outcome,processLaunched,exitCode,headroomBeforeGiB,wallSeconds | ConvertTo-Json
if($sensitivityAbort){exit 1}
exit $sensitivityProcess.ExitCode
