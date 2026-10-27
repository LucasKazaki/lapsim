# Bounded serial campaign. Each job rechecks admission; any guard failure stops.
param([Parameter(Mandatory=$true)][string]$PythonExe,[string]$Directory='work/gpu-search-20261026')
$ErrorActionPreference='Stop'
$searchRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $searchRoot
$searchPython=(Resolve-Path -LiteralPath $PythonExe).Path
$searchPlan=Get-Content -LiteralPath (Join-Path $Directory 'plan.json') -Raw | ConvertFrom-Json
function Invoke-SearchCandidate([object]$Entry,[string]$Scenario){
    if(Test-Path -LiteralPath (Join-Path $Directory 'pause.requested')){throw 'Coordinated search pause requested; no next job launched'}
    $searchComplete=$true
    foreach($searchCourse in $searchPlan.courses.PSObject.Properties.Name){
        $searchSummary=Join-Path $Directory "records/$Scenario/$($Entry.id)/$searchCourse.summary.json"
        if(-not(Test-Path -LiteralPath $searchSummary)){$searchComplete=$false}
    }
    if($searchComplete){Write-Output "Preserved complete coverage: $Scenario / $($Entry.id)";return}
    $searchAbbreviation=switch($Scenario){'train'{'t'}'heldout-a'{'ha'}'heldout-b'{'hb'}}
    $searchShort=if($Entry.anchor){'base'}else{$Entry.id.Substring(0,5)}
    $searchAttempt="ga-$searchAbbreviation-$searchShort"
    if(Test-Path -LiteralPath "work/gpu-readiness-20261026/search-evaluate-$searchAttempt.guard.json"){
        throw 'Existing incomplete attempt requires inspection; no blind retry'
    }
    Write-Output "Launching $Scenario / $($Entry.id) at $((Get-Date).ToUniversalTime().ToString('o'))"
    & "$searchRoot/scripts/run_gpu_validation_guarded.ps1" -Phase search-evaluate -Attempt $searchAttempt -Candidate $Entry.id -Scenario $Scenario -SearchDirectory $Directory -PythonExe $searchPython
    if($LASTEXITCODE -ne 0){throw "Search job stopped: $Scenario / $($Entry.id); inspect saved guard and partial records"}
    $searchCoverage=Get-Content -LiteralPath (Join-Path $Directory 'coverage.json') -Raw | ConvertFrom-Json
    Write-Output ($searchCoverage.counts | ConvertTo-Json -Compress)
}
foreach($searchEntry in $searchPlan.initial_population){Invoke-SearchCandidate $searchEntry 'train'}
$searchGenerationPath=Join-Path $Directory 'generation-1.json'
if(-not(Test-Path -LiteralPath $searchGenerationPath)){
    & $searchPython -u scripts/run_gpu_search.py --directory $Directory --breed
    if($LASTEXITCODE -ne 0){throw 'Genetic selection failed; no held-out data used'}
}
$searchGeneration=Get-Content -LiteralPath $searchGenerationPath -Raw | ConvertFrom-Json
foreach($searchEntry in $searchGeneration.offspring){Invoke-SearchCandidate $searchEntry 'train'}
$searchHeldPath=Join-Path $Directory 'heldout-pool.json'
if(-not(Test-Path -LiteralPath $searchHeldPath)){
    & $searchPython -u scripts/run_gpu_search.py --directory $Directory --freeze
    if($LASTEXITCODE -ne 0){throw 'Finalist freeze failed; no held-out execution'}
}
$searchHeld=Get-Content -LiteralPath $searchHeldPath -Raw | ConvertFrom-Json
foreach($searchScenario in @('heldout-a','heldout-b')){
    foreach($searchEntry in $searchHeld.candidates){Invoke-SearchCandidate $searchEntry $searchScenario}
}
& $searchPython -u scripts/run_gpu_search.py --directory $Directory --summary
if($LASTEXITCODE -ne 0){throw 'Final common-field scoring failed'}
Write-Output 'Bounded GPU search and frozen held-out evaluation completed; inspect coverage and exclusions before claiming winners.'
