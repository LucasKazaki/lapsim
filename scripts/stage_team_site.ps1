param([Parameter(Mandatory = $true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$destination = [IO.Path]::GetFullPath($OutputDirectory)
if ($destination -eq $repository -or $destination.StartsWith((Join-Path $repository 'src') + [IO.Path]::DirectorySeparatorChar)) {
    throw 'Choose a separate static output directory.'
}
foreach ($protected in @('docs', 'tests', 'web')) {
    $protectedPath = Join-Path $repository $protected
    if ($destination -eq $protectedPath -or $destination.StartsWith($protectedPath + [IO.Path]::DirectorySeparatorChar)) {
        throw 'Choose a separate static output directory.'
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $destination 'assets/runtime-manifest.json'))) {
    throw 'Build the browser simulator with scripts/build_web.py first.'
}

# Preserve repository-relative source links in the complete expandable map.
$paths = @(git -C $repository ls-files) + @('docs/simulator_research.md', 'docs/web_simulator.md')
foreach ($relative in ($paths | Sort-Object -Unique)) {
    if ($relative -match '^(\.github/|output/|packaging/)' -or $relative -eq 'index.html' -or $relative -eq 'docs/simulator_flowchart/browser_check.cjs') { continue }
    $source = [IO.Path]::GetFullPath((Join-Path $repository $relative))
    if (-not $source.StartsWith($repository + [IO.Path]::DirectorySeparatorChar)) { throw 'Source escapes the checkout.' }
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { continue }
    $target = Join-Path $destination $relative
    New-Item -ItemType Directory -Path (Split-Path $target -Parent) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Force
}

# This tracked page is also linked as a source target; use the canonical app.
@'
<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LapSim browser simulator</title>
<p><a href="../index.html">Open the browser simulator</a></p>
<script>location.replace('../index.html'+location.search+location.hash);</script></html>
'@ | Set-Content -LiteralPath (Join-Path $destination 'web/index.html') -Encoding utf8NoBOM
$excludedHarness = Join-Path $destination 'docs/simulator_flowchart/browser_check.cjs'
if (Test-Path -LiteralPath $excludedHarness -PathType Leaf) { Remove-Item -LiteralPath $excludedHarness }

$mapPage = Join-Path $destination 'docs/simulator_flowchart/index.html'
$mapHtml = Get-Content -LiteralPath $mapPage -Raw
$readmeLink = '<a class="repo-link" href="../../README.md">Repository README</a>'
if (-not $mapHtml.Contains($readmeLink)) { throw 'Map navigation anchor changed; update the staging script.' }
$mapHtml.Replace($readmeLink, '<a class="repo-link" href="../../index.html">Simulator</a><a class="repo-link" href="../../research/index.html">Research</a>' + $readmeLink) |
    Set-Content -LiteralPath $mapPage -Encoding utf8NoBOM

$mapDirectory = Join-Path $destination 'map'
New-Item -ItemType Directory -Path $mapDirectory -Force | Out-Null
@'
<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LapSim physics map</title>
<p><a href="../docs/simulator_flowchart/index.html">Open the complete physics map</a></p>
<script>location.replace('../docs/simulator_flowchart/index.html'+location.search+location.hash);</script></html>
'@ | Set-Content -LiteralPath (Join-Path $mapDirectory 'index.html') -Encoding utf8NoBOM

$researchDirectory = Join-Path $destination 'research'
New-Item -ItemType Directory -Path $researchDirectory -Force | Out-Null
$markdown = Join-Path $repository 'docs/simulator_research.md'
$body = (ConvertFrom-Markdown -LiteralPath $markdown).Html
$template = @'
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Official-source simulator comparison, driving policies, brake controls, and LapSim implementation boundaries."><title>LapSim · Driving and simulator research</title>
<style>
:root{color-scheme:light dark;--bg:#f5f6f8;--fg:#172332;--muted:#526071;--line:#d8dfe5;--panel:#fff;--link:#075cab}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.65 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}nav{display:flex;gap:24px;align-items:center;flex-wrap:wrap;padding:24px max(24px,calc((100vw - 1120px)/2));border-bottom:1px solid var(--line);background:var(--panel)}nav strong{margin-right:auto;font-size:20px}a{color:var(--link);text-underline-offset:3px}a:focus-visible{outline:3px solid var(--link);outline-offset:5px;border-radius:3px}main{max-width:1120px;margin:40px auto;padding:0 24px 64px}h1{font-size:clamp(32px,4vw,46px);line-height:1.15;letter-spacing:-.035em;max-width:850px}h2{margin-top:56px;font-size:26px;letter-spacing:-.02em}p{max-width:900px}table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.55;background:var(--panel)}th,td{border:1px solid var(--line);padding:16px;text-align:left;vertical-align:top}th{font-weight:650}pre{padding:24px;border:1px solid var(--line);border-radius:16px;background:var(--panel);overflow:auto;font-size:14px}code{font-family:ui-monospace,Consolas,monospace;font-size:.9em}p code{overflow-wrap:anywhere}footer{color:var(--muted);border-top:1px solid var(--line);margin-top:48px;padding-top:24px}section.table-scroll{overflow:auto;border-radius:14px}section.table-scroll table{min-width:650px}button{font:inherit}@media(prefers-color-scheme:dark){:root{--bg:#11171e;--fg:#e7edf3;--muted:#a9b6c5;--line:#35414e;--panel:#19222c;--link:#8cc8ff}}@media(max-width:600px){nav{gap:16px}nav strong{width:100%}main{margin-top:28px;padding-left:18px;padding-right:18px}th,td{padding:12px}}
</style></head><body><nav><strong>LapSim Team Lab</strong><a href="../index.html">Simulator</a><a href="../map/index.html">Physics map</a><a href="https://github.com/LucasKazaki/lapsim">GitHub repository</a></nav><main>
%%BODY%%
<footer>Research source: <a href="../docs/simulator_research.md">download the report</a>. <a href="../docs/web_simulator.md">Browser guide</a>. Controls are described at their actual implementation maturity.</footer></main></body></html>
'@
$body = $body.Replace('<table>', '<section class="table-scroll" role="region" aria-label="Comparison table" tabindex="0"><table>').Replace('</table>', '</table></section>')
$template.Replace('%%BODY%%', $body) | Set-Content -LiteralPath (Join-Path $researchDirectory 'index.html') -Encoding utf8NoBOM
Write-Output "Staged complete map, repository source links, and research in $destination"

# Static hosts do not generate filesystem directory listings for branch links.
foreach ($relative in @('analysis/events', 'analysis/endurance', 'analysis/accel', 'tests')) {
    $directory = Join-Path $destination $relative
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) { continue }
    $items = foreach ($entry in (Get-ChildItem -LiteralPath $directory | Sort-Object Name)) {
        $name = [Net.WebUtility]::HtmlEncode($entry.Name)
        $href = [Uri]::EscapeDataString($entry.Name)
        "<li><a href='$href'>$name</a></li>"
    }
    $mapHref = ('../' * ($relative.Split('/').Count)) + 'docs/simulator_flowchart/index.html'
    "<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>LapSim source · $relative</title><main style='font:16px/1.6 system-ui;max-width:900px;margin:40px auto;padding:24px'><a href='$mapHref'>Return to physics map</a><h1>$relative</h1><ul>$($items -join '')</ul></main></html>" |
        Set-Content -LiteralPath (Join-Path $directory 'index.html') -Encoding utf8NoBOM
}
