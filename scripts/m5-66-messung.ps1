<#
.SYNOPSIS
    Measures broad search words and catalog-load without changes on the local platform (M5-66).

.DESCRIPTION
    Windows PowerShell 5.1, no extra modules. Run it from the repository root (wherever the file lies) while
    `docker compose up -d api` is running on the state to measure (docs/plans/m5/m5-66-breite-suche.md section 8):

        powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\m5-66-messung.ps1 -Label vorher

    Steps:
      1. catalog-load: one run first that brings the database in line (not timed), then -LoadRuns timed runs of
         `docker compose run --rm catalog-load` (with the start of pgstac-migrate) and as many with `--no-deps`.
         Kept of its output: the lines `time ...` (from M5-66 on) and the counts of written rows.
      2. search: POST /stac/collections with the words data, map and water, each without a filter, with a category,
         with a region and with both; data also from place 200. One run to warm up, then -Runs timed runs.

    Written to ..\earthx-ausgaben\m5-66\ next to the repository, never into it:
      <Label>-suche.csv   per query: best and median in ms, numberReturned, numberMatched, whether there is a next
                          page, and a hash of the ids of the page in their order (equal hash = same order)
      <Label>-laden.txt   the times of catalog-load and its kept lines
    No ids, titles or areas are written; the only texts are the three words of the queries.

.PARAMETER Label
    Name of the measurement, e.g. vorher or nachher.

.PARAMETER Runs
    Timed runs per query. Default 5.

.PARAMETER LoadRuns
    Timed runs of catalog-load, each with and without pgstac-migrate. Default 3.

.PARAMETER BaseUrl
    Where the api runs. Default http://localhost:8000.

.PARAMETER NoLoad
    Skip catalog-load.

.PARAMETER NoSearch
    Skip the search.
#>
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9_-]{1,40}$')][string]$Label,
    [ValidateRange(1, 50)][int]$Runs = 5,
    [ValidateRange(1, 20)][int]$LoadRuns = 3,
    [string]$BaseUrl = 'http://localhost:8000',
    [switch]$NoLoad,
    [switch]$NoSearch
)

$ErrorActionPreference = 'Stop'
$repo = (Get-Location).Path
if (-not (Test-Path (Join-Path $repo 'docker-compose.yml'))) { throw 'Bitte aus dem Wurzelverzeichnis des Repos starten' }
$out = Join-Path (Split-Path -Parent $repo) 'earthx-ausgaben\m5-66'
New-Item -ItemType Directory -Force -Path $out | Out-Null
Write-Host "Ausgaben nach $out"

function Get-Median([double[]]$values) {
    $sorted = $values | Sort-Object
    $n = $sorted.Count
    if ($n % 2 -eq 1) { return $sorted[($n - 1) / 2] }
    return ($sorted[$n / 2 - 1] + $sorted[$n / 2]) / 2
}

function Invoke-Compose([string]$arguments) {
    # cmd keeps the progress docker compose writes to stderr out of PowerShell's error records.
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $lines = cmd /c "docker compose $arguments 2>&1"
    $watch.Stop()
    return @{ Seconds = $watch.Elapsed.TotalSeconds; Lines = $lines; ExitCode = $LASTEXITCODE }
}

if (-not $NoLoad) {
    $report = New-Object System.Collections.Generic.List[string]
    $report.Add("M5-66 catalog-load ohne Aenderung, Messung $Label, $(Get-Date -Format s)")
    Write-Host 'catalog-load: ein Lauf vorab (nicht gemessen) ...'
    $first = Invoke-Compose 'run --rm catalog-load'
    if ($first.ExitCode -ne 0) { throw "catalog-load scheiterte (Exit $($first.ExitCode)); nichts gemessen" }
    foreach ($variant in @(@{ Name = 'mit pgstac-migrate'; Args = 'run --rm catalog-load' },
                           @{ Name = 'ohne pgstac-migrate (--no-deps)'; Args = 'run --rm --no-deps catalog-load' })) {
        $seconds = @()
        for ($i = 1; $i -le $LoadRuns; $i++) {
            $run = Invoke-Compose $variant.Args
            if ($run.ExitCode -ne 0) { throw "catalog-load scheiterte (Exit $($run.ExitCode))" }
            $seconds += $run.Seconds
            $report.Add(('{0}, Lauf {1}: {2:N1} s' -f $variant.Name, $i, $run.Seconds))
            foreach ($line in $run.Lines) {
                if ("$line" -match '^(time |search index rows of listed entries written|region rows changed|municipality rows changed|listed hand entries written|migrations applied)') {
                    $report.Add("    $line")
                }
            }
            Write-Host ('catalog-load {0}, Lauf {1}: {2:N1} s' -f $variant.Name, $i, $run.Seconds)
        }
        $report.Add(('{0}: bester {1:N1} s, Median {2:N1} s' -f $variant.Name, ($seconds | Measure-Object -Minimum).Minimum, (Get-Median $seconds)))
    }
    $report | Set-Content -Encoding UTF8 (Join-Path $out "$Label-laden.txt")
}

if (-not $NoSearch) {
    $sha = [Security.Cryptography.SHA256]::Create()
    $queries = [ordered]@{}
    foreach ($word in @('data', 'map', 'water')) {
        $queries["$word"] = @{ q = $word }
        $queries["$word + Kategorie water"] = @{ q = $word; category = 'water' }
        $queries["$word + Region DE"] = @{ q = $word; region = @('DE') }
        $queries["$word + Kategorie boundaries + Region DE"] = @{ q = $word; category = 'boundaries'; region = @('DE') }
        $queries["$word + Region CH"] = @{ q = $word; region = @('CH') }
    }
    $queries['data ab Platz 200'] = @{ q = 'data'; offset = 200 }
    $rows = New-Object System.Collections.Generic.List[object]
    foreach ($name in $queries.Keys) {
        $bytes = [Text.Encoding]::UTF8.GetBytes(($queries[$name] | ConvertTo-Json -Compress))
        $times = @()
        $answer = $null
        for ($i = 0; $i -le $Runs; $i++) {
            $watch = [Diagnostics.Stopwatch]::StartNew()
            $response = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$BaseUrl/stac/collections" `
                -ContentType 'application/json' -Body $bytes
            $watch.Stop()
            if ($i -gt 0) { $times += $watch.Elapsed.TotalMilliseconds }
            $answer = [Text.Encoding]::UTF8.GetString($response.RawContentStream.ToArray()) | ConvertFrom-Json
        }
        $ids = ($answer.collections | ForEach-Object { $_.id }) -join "`n"
        $hash = -join ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($ids)) | Select-Object -First 8 | ForEach-Object { $_.ToString('x2') })
        $matched = if ($null -ne $answer.numberMatched) { $answer.numberMatched } else { '-' }
        $next = [bool]($answer.links | Where-Object { $_.rel -eq 'next' })
        $row = [pscustomobject]@{
            Anfrage = $name
            BesterMs = [math]::Round(($times | Measure-Object -Minimum).Minimum)
            MedianMs = [math]::Round((Get-Median $times))
            Zurueck = $answer.numberReturned
            Treffer = $matched
            Weiter = $next
            Reihenfolge = $hash
        }
        $rows.Add($row)
        Write-Host ('{0,-45} bester {1,6} ms  Median {2,6} ms  Treffer {3}' -f $name, $row.BesterMs, $row.MedianMs, $matched)
    }
    $rows | Export-Csv -NoTypeInformation -Encoding UTF8 -Delimiter ';' (Join-Path $out "$Label-suche.csv")
}
Write-Host "Fertig: $out"
