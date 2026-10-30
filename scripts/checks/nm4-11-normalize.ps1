<#
.SYNOPSIS
    NM4-11: checks the methods of normalize (version 3) against the area statistics and a real job.

.DESCRIPTION
    Voraussetzung: der Stack laeuft (docker compose up -d --build) und das Netz erreicht die Quelle
    (Earth Search, ohne VPN). Aus dem Wurzelverzeichnis des Repos starten:

        .\scripts\checks\nm4-11-normalize.ps1

    Sperrt die Ausfuehrungsrichtlinie das Skript, einmal so:
        powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\checks\nm4-11-normalize.ps1

    Windows PowerShell 5.1, keine Module. Each step is printed as PASS or FAIL:
      1. find a Sentinel-2 scene (summer 2025, few clouds) around 7 E / 46 N, build a square in it
      2. POST the order to the tiler (band red, float64): the answer carries percentile_1 ... percentile_99
      3. per method (percentile, zscore, robust): the numbers of the answer go into a step of normalize
         version 3, the order runs as a job, and its result does what the method says over the same area
      4. refusals: a step without its numbers is refused, a step with the numbers of another method too
      5. docker compose logs tiler: no coordinate of the square

    The script prints no item id, no coordinate, no job id and no hash. Exit code 0 when all pass.
    It has not been run in the session that wrote it (no PowerShell there): the helpers are those of
    nm4-19-statistics.ps1; if a step fails because of the script, say so, do not read it as a fault of the platform.
#>
[CmdletBinding()]
param(
    [string]$ApiUrl = 'http://localhost:8000',
    [string]$TilerUrl = 'http://localhost:8001',
    [int]$JobTimeoutSeconds = 600
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'      # the progress bar makes Invoke-WebRequest slow in 5.1
$Invariant             = [System.Globalization.CultureInfo]::InvariantCulture
$Dataset               = 'sentinel-2-c1-l2a'
$SearchBox             = @(6.9, 45.9, 7.1, 46.1)
$SearchPeriod          = '2025-06-15T00:00:00Z/2025-08-31T23:59:59Z'
$MaxCloudPercent       = 10.0
$CentreLon             = 7.0137913
$CentreLat             = 46.0246802
$Half                  = 0.04
$script:Failed         = 0
$script:Passed         = 0
$script:ItemId         = $null

$ApiUrl   = $ApiUrl.TrimEnd('/')
$TilerUrl = $TilerUrl.TrimEnd('/')
$Root     = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Compose  = Join-Path $Root 'docker-compose.yml'
$Route    = "$TilerUrl/collections/$Dataset/statistics"

# ---- output -----------------------------------------------------------------------------------------

function Write-Pass {
    param([string]$Text)
    $script:Passed++
    Write-Host "PASS $Text" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Text, [string]$Expected, [string]$Got)
    $script:Failed++
    Write-Host "FAIL $Text (erwartet $Expected, bekommen $Got)" -ForegroundColor Red
}

function Test-Step {
    param([bool]$Good, [string]$Text, [string]$Expected, [string]$Got)
    if ($Good) { Write-Pass $Text } else { Write-Fail $Text $Expected $Got }
}

function Write-Info {
    param([string]$Text)
    Write-Host "     $Text" -ForegroundColor DarkGray
}

function Stop-Run {
    param([string]$Text, [string]$Expected, [string]$Got)
    Write-Fail $Text $Expected $Got
    Show-End
}

function Show-End {
    Write-Host ''
    if ($script:Failed -eq 0) {
        Write-Host "ALL PASS ($script:Passed)" -ForegroundColor Green
        exit 0
    }
    Write-Host "$script:Failed FAIL, $script:Passed PASS" -ForegroundColor Red
    exit 1
}

# ---- HTTP -------------------------------------------------------------------------------------------

function Invoke-Http {
    # One request that never throws. Status 0: no answer at all. A body goes as UTF-8 bytes without a BOM.
    param([string]$Method = 'GET', [string]$Uri, [string]$Body, [int]$TimeoutSec = 300)
    $request = @{ Uri = $Uri; Method = $Method; UseBasicParsing = $true; TimeoutSec = $TimeoutSec }
    if ($Body) {
        $request.Body        = [System.Text.Encoding]::UTF8.GetBytes($Body)
        $request.ContentType = 'application/json'
    }
    $started = Get-Date
    try {
        $response = Invoke-WebRequest @request
        $text = Read-Content $response
        return [pscustomobject]@{ Status = [int]$response.StatusCode; Content = $text; Seconds = ((Get-Date) - $started).TotalSeconds }
    } catch {
        $failure = $_.Exception.Response
        if ($null -eq $failure) {
            return [pscustomobject]@{ Status = 0; Content = $_.Exception.Message; Seconds = 0 }
        }
        $text = ''
        try {
            $reader = New-Object System.IO.StreamReader($failure.GetResponseStream(), [System.Text.Encoding]::UTF8)
            $text = $reader.ReadToEnd()
            $reader.Close()
        } catch { }
        return [pscustomobject]@{ Status = [int]$failure.StatusCode; Content = $text; Seconds = 0 }
    }
}

function Read-Content {
    # The answer as UTF-8 text. 5.1 hands back bytes for a type it does not know as text (application/geo+json).
    param($Response)
    $bytes = $null
    try { $bytes = $Response.RawContentStream.ToArray() } catch { }
    if ($null -eq $bytes) {
        if ($Response.Content -is [byte[]]) { $bytes = $Response.Content } else { return [string]$Response.Content }
    }
    return [System.Text.Encoding]::UTF8.GetString($bytes).TrimStart([char]0xFEFF)
}

function ConvertFrom-JsonSafe {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
    try { return ($Text | ConvertFrom-Json) } catch { return $null }
}

function Get-Detail {
    # What a refusal says, without the body it may have been about and without the item it may name.
    param($Answer)
    $problem = ConvertFrom-JsonSafe $Answer.Content
    $text = "HTTP $($Answer.Status)"
    if ($null -ne $problem -and $problem.detail -is [string]) { $text = "HTTP $($Answer.Status): $($problem.detail)" }
    elseif ($null -ne $problem -and $problem.title) { $text = "HTTP $($Answer.Status): $($problem.title)" }
    elseif ($Answer.Status -eq 0) { $text = 'keine Antwort' }
    if ($script:ItemId) { $text = $text.Replace($script:ItemId, '<item>') }
    return $text
}

# ---- geometry ---------------------------------------------------------------------------------------

function Format-Number {
    param([double]$Value)
    return $Value.ToString('R', $Invariant)          # a decimal point, never a decimal comma
}

function New-Square {
    # A GeoJSON polygon as text: the square of half side $Half degrees around the centre.
    param([double]$Half)
    $w = Format-Number ($CentreLon - $Half); $e = Format-Number ($CentreLon + $Half)
    $s = Format-Number ($CentreLat - $Half); $n = Format-Number ($CentreLat + $Half)
    return '{"type": "Polygon", "coordinates": [[[' + "$w, $s], [$e, $s], [$e, $n], [$w, $n], [$w, $s" + ']]]}'
}

function Get-Rings {
    # The outer rings of a Polygon or MultiPolygon, each as a list of [lon, lat].
    param($Geometry)
    if ($null -eq $Geometry) { return @() }
    if ($Geometry.type -eq 'Polygon') { return ,@(,$Geometry.coordinates[0]) }
    if ($Geometry.type -eq 'MultiPolygon') { return ,@($Geometry.coordinates | ForEach-Object { ,$_[0] }) }
    return @()
}

function Test-Inside {
    # Whether the point lies in one of the rings (even-odd rule).
    param($Rings, [double]$Lon, [double]$Lat)
    foreach ($ring in $Rings) {
        $inside = $false
        $count = @($ring).Count
        for ($i = 0; $i -lt $count; $i++) {
            $a = $ring[$i]; $b = $ring[($i + 1) % $count]
            $ax = [double]$a[0]; $ay = [double]$a[1]; $bx = [double]$b[0]; $by = [double]$b[1]
            if ((($ay -gt $Lat) -ne ($by -gt $Lat)) -and ($Lon -lt ($bx - $ax) * ($Lat - $ay) / ($by - $ay) + $ax)) {
                $inside = -not $inside
            }
        }
        if ($inside) { return $true }
    }
    return $false
}

# ---- the orders -------------------------------------------------------------------------------------

function New-Order {
    # An order of recipe version 2: the bands of the output, no assets. $Steps is the text of the steps array.
    param([string]$ItemId, [string]$Aoi, [string]$Steps, [string]$Dtype)
    return '{"recipe_version": 2, "inputs": [{"name": "input", "dataset": "' + $Dataset + '", "groups": [["' + $ItemId +
        '"]]}], "aoi": ' + $Aoi + ', "steps": [' + $Steps + ']' +
        ', "output": {"kind": "raster", "format": "cog", "dtype": "' + $Dtype + '", "bands": ["red"]}}'
}

function New-Step {
    param([string]$Params)
    return '{"op": "normalize", "op_version": 3, "params": ' + $Params + '}'
}

function Get-JobResult {
    # The statistics of the first band of the job's result, or $null (a FAIL is printed).
    param([string]$Order, [string]$Text)
    $placed = Invoke-Http -Method Post -Uri "$ApiUrl/processing/processes/recipe/execution" -Body ('{"inputs": {"recipe": ' + $Order + '}}')
    $job = ConvertFrom-JsonSafe $placed.Content
    if (($placed.Status -ne 201 -and $placed.Status -ne 200) -or $null -eq $job -or -not $job.jobID) {
        Write-Fail "$Text: Job starten" 'HTTP 201 mit jobID' (Get-Detail $placed)
        return $null
    }
    $statusUrl = "$ApiUrl/processing/jobs/$([string]$job.jobID)"
    $deadline = (Get-Date).AddSeconds($JobTimeoutSeconds)
    $state = [string]$job.status
    while ($state -ne 'successful' -and $state -ne 'failed' -and $state -ne 'dismissed' -and (Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        $poll = Invoke-Http -Uri $statusUrl -TimeoutSec 60
        if ($poll.Status -eq 200) { $state = [string](ConvertFrom-JsonSafe $poll.Content).status }
    }
    if ($state -ne 'successful') {
        Write-Fail "$Text: Job fertig" "successful in $JobTimeoutSeconds s (laeuft der Dienst worker?)" $state
        return $null
    }
    $results = Invoke-Http -Uri "$statusUrl/results" -TimeoutSec 60
    $document = ConvertFrom-JsonSafe $results.Content
    if ($null -eq $document -or $null -eq $document.result.properties) {
        Write-Fail "$Text: Statistik des Jobs lesen" 'result.properties.bands[0].statistics' (Get-Detail $results)
        return $null
    }
    return [pscustomobject]@{ Statistics = $document.result.properties.bands[0].statistics; Lineage = [string]$document.result.properties.'processing:lineage' }
}

function Format-Value {
    param($Value)
    return ([double]$Value).ToString('R', $Invariant)
}

# ---- 1. scene and square ----------------------------------------------------------------------------
Write-Host "NM4-11: Methoden von normalize, $Dataset" -ForegroundColor Cyan
Write-Host ''
Write-Host '1. Szene suchen, Quadrat bilden' -ForegroundColor Cyan

$box = ($SearchBox | ForEach-Object { Format-Number $_ }) -join ', '
$search = '{"collections": ["' + $Dataset + '"], "bbox": [' + $box + '], "datetime": "' + $SearchPeriod + '", "limit": 30' +
    ', "query": {"eo:cloud_cover": {"lte": ' + (Format-Number $MaxCloudPercent) + '}}}'
$found = Invoke-Http -Method Post -Uri "$ApiUrl/stac/search" -Body $search -TimeoutSec 120
if ($found.Status -ne 200) {
    Stop-Run 'Szene suchen' 'HTTP 200 (laeuft docker compose up -d --build?)' (Get-Detail $found)
}
$features = @((ConvertFrom-JsonSafe $found.Content).features)
$corners = @(
    @(($CentreLon - $Half), ($CentreLat - $Half)), @(($CentreLon + $Half), ($CentreLat - $Half)),
    @(($CentreLon + $Half), ($CentreLat + $Half)), @(($CentreLon - $Half), ($CentreLat + $Half))
)
$candidates = @()
foreach ($feature in $features) {
    if ($null -eq $feature -or $null -eq $feature.properties) { continue }
    $cloud = $feature.properties.'eo:cloud_cover'
    if ($null -eq $cloud -or [double]$cloud -gt $MaxCloudPercent) { continue }
    $rings = Get-Rings $feature.geometry
    $covered = $true
    foreach ($corner in $corners) {
        if (-not (Test-Inside $rings $corner[0] $corner[1])) { $covered = $false; break }
    }
    if ($covered) { $candidates += [pscustomobject]@{ Id = [string]$feature.id; Cloud = [double]$cloud } }
}
if ($candidates.Count -eq 0) {
    Stop-Run 'Szene suchen' "eine Szene mit hoechstens $MaxCloudPercent % Wolken, die das Quadrat ganz enthaelt" "$($features.Count) Szenen, keine passt"
}
$scene = $candidates | Sort-Object Cloud | Select-Object -First 1
$script:ItemId = $scene.Id
Write-Pass ("Szene gefunden ({0} Kandidaten, Wolken {1} %), Quadrat von {2} Grad gebildet" -f `
    $candidates.Count, $scene.Cloud.ToString('0.#', $Invariant), (2 * $Half).ToString('0.##', $Invariant))
$aoi = New-Square $Half

# ---- 2. the measure ---------------------------------------------------------------------------------
Write-Host ''
Write-Host '2. Messung ueber das Quadrat (Band red, float64)' -ForegroundColor Cyan

$measure = Invoke-Http -Method Post -Uri $Route -Body (New-Order $script:ItemId $aoi '' 'float64')
$m = $null
if ($measure.Status -ne 200) {
    Stop-Run 'Messung' 'HTTP 200' (Get-Detail $measure)
}
$answer = ConvertFrom-JsonSafe $measure.Content
$m = $answer.bands[0].statistics
Write-Info ("Dauer {0} s, factor {1}" -f $measure.Seconds.ToString('0.0', $Invariant), $answer.factor)
$names = @('minimum', 'percentile_1', 'percentile_2', 'percentile_5', 'percentile_25', 'percentile_50', 'percentile_75', 'percentile_95', 'percentile_98', 'percentile_99', 'maximum')
$missing = @($names | Where-Object { $null -eq $m.$_ })
Test-Step ($missing.Count -eq 0) 'Die Antwort traegt Minimum, alle Perzentile und Maximum' 'alle elf Zahlen' ("fehlt: " + ($missing -join ', '))
if ($missing.Count -gt 0) { Show-End }
$ordered = $true
for ($i = 1; $i -lt $names.Count; $i++) {
    if ([double]$m.($names[$i]) -lt [double]$m.($names[$i - 1])) { $ordered = $false }
}
Test-Step $ordered 'Die Zahlen steigen von Minimum bis Maximum' 'aufsteigend' 'nicht aufsteigend'
$iqr = [double]$m.percentile_75 - [double]$m.percentile_25
Test-Step ($iqr -gt 0 -and [double]$m.stddev -gt 0) 'Das Band ist ueber dem Quadrat nicht konstant' 'Quartilsabstand und Streuung > 0' "Quartilsabstand $iqr"
if ($iqr -le 0 -or [double]$m.stddev -le 0) { Show-End }

# ---- 3. one job per method --------------------------------------------------------------------------
Write-Host ''
Write-Host '3. Ein Job je Methode, mit den gemessenen Zahlen im Schritt' -ForegroundColor Cyan

$factor = [int]$answer.factor
$percentileParams = '{"method": "percentile", "bands": ["red"], "low": 2, "high": 98, "out_min": 0, "out_max": 1, "clip": true, ' +
    '"measured": {"factor": ' + $factor + ', "bands": {"red": {"p_low": ' + (Format-Value $m.percentile_2) + ', "p_high": ' + (Format-Value $m.percentile_98) + '}}}}'
$zscoreParams = '{"method": "zscore", "bands": ["red"], "measured": {"factor": ' + $factor + ', "bands": {"red": {"mean": ' +
    (Format-Value $m.mean) + ', "stddev": ' + (Format-Value $m.stddev) + '}}}}'
$robustParams = '{"method": "robust", "bands": ["red"], "measured": {"factor": ' + $factor + ', "bands": {"red": {"p25": ' +
    (Format-Value $m.percentile_25) + ', "median": ' + (Format-Value $m.percentile_50) + ', "p75": ' + (Format-Value $m.percentile_75) + '}}}}'

$job = Get-JobResult (New-Order $script:ItemId $aoi (New-Step $percentileParams) 'float32') 'Perzentile'
if ($null -ne $job) {
    Write-Pass 'Perzentile: Job ist successful'
    Test-Step ([double]$job.Statistics.minimum -eq 0 -and [double]$job.Statistics.maximum -eq 1) 'Perzentile: die Enden des Ergebnisses sind 0 und 1' 'minimum 0, maximum 1' "minimum $($job.Statistics.minimum), maximum $($job.Statistics.maximum)"
    Test-Step ($job.Lineage.Contains('percentiles 2 to 98')) 'Perzentile: die Herkunft nennt die Methode' 'percentiles 2 to 98' $job.Lineage
}

$job = Get-JobResult (New-Order $script:ItemId $aoi (New-Step $zscoreParams) 'float32') 'Z-Score'
if ($null -ne $job) {
    Write-Pass 'Z-Score: Job ist successful'
    Test-Step ([math]::Abs([double]$job.Statistics.mean) -lt 0.001) 'Z-Score: Mittelwert des Ergebnisses ist 0' '|mittel| < 0.001' (Format-Value $job.Statistics.mean)
    Test-Step ([math]::Abs([double]$job.Statistics.stddev - 1) -lt 0.001) 'Z-Score: Streuung des Ergebnisses ist 1' '|streuung - 1| < 0.001' (Format-Value $job.Statistics.stddev)
}

$job = Get-JobResult (New-Order $script:ItemId $aoi (New-Step $robustParams) 'float32') 'Robust'
if ($null -ne $job) {
    Write-Pass 'Robust: Job ist successful'
    # The result carries the 2nd and 98th percentile only: they must be those of the measure, scaled the same way.
    $expectedLow = ([double]$m.percentile_2 - [double]$m.percentile_50) / $iqr
    $expectedHigh = ([double]$m.percentile_98 - [double]$m.percentile_50) / $iqr
    $slack = 0.03 * ([math]::Abs($expectedHigh - $expectedLow))
    Test-Step ([math]::Abs([double]$job.Statistics.percentile_2 - $expectedLow) -le $slack) 'Robust: 2. Perzentil des Ergebnisses wie gerechnet' (Format-Value $expectedLow) (Format-Value $job.Statistics.percentile_2)
    Test-Step ([math]::Abs([double]$job.Statistics.percentile_98 - $expectedHigh) -le $slack) 'Robust: 98. Perzentil des Ergebnisses wie gerechnet' (Format-Value $expectedHigh) (Format-Value $job.Statistics.percentile_98)
}

# ---- 4. refusals ------------------------------------------------------------------------------------
Write-Host ''
Write-Host '4. Ablehnungen' -ForegroundColor Cyan

$noNumbers = Invoke-Http -Method Post -Uri $Route -Body (New-Order $script:ItemId $aoi (New-Step '{"method": "zscore", "bands": ["red"]}') 'float64')
Test-Step ($noNumbers.Status -eq 422 -or $noNumbers.Status -eq 400) 'Schritt ohne Zahlen abgelehnt' 'HTTP 422 oder 400' "HTTP $($noNumbers.Status)"
$wrong = '{"method": "zscore", "bands": ["red"], "clip": true, "measured": {"factor": 1, "bands": {"red": {"mean": 0.1, "stddev": 0.1}}}}'
$foreign = Invoke-Http -Method Post -Uri $Route -Body (New-Order $script:ItemId $aoi (New-Step $wrong) 'float64')
Test-Step ($foreign.Status -eq 422 -or $foreign.Status -eq 400) 'Schritt mit dem Feld einer anderen Methode abgelehnt' 'HTTP 422 oder 400' "HTTP $($foreign.Status)"
Write-Info ("Grund: " + (Get-Detail $foreign))

# ---- 5. the log of the tiler ------------------------------------------------------------------------
Write-Host ''
Write-Host '5. docker compose logs tiler' -ForegroundColor Cyan

if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Fail 'Log lesen' 'docker im PATH' 'nicht gefunden'
} else {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'      # docker writes progress to stderr; 5.1 would turn that into an error
    $log = (& docker compose -f $Compose logs --no-color tiler 2>&1 | Out-String)
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previous
    if ($code -ne 0 -or [string]::IsNullOrWhiteSpace($log)) {
        Write-Fail 'Log lesen' 'Zeilen von docker compose logs tiler' "Exit-Code $code, leer"
    } else {
        $hits = 0
        foreach ($value in @(($CentreLon - $Half), ($CentreLon + $Half), ($CentreLat - $Half), ($CentreLat + $Half))) {
            $cut = ([math]::Truncate($value * 10000) / 10000).ToString('0.0000', $Invariant)
            if ([regex]::IsMatch($log, '(?<![0-9])' + [regex]::Escape($cut))) { $hits++ }
        }
        Test-Step ($hits -eq 0) 'Keine Koordinate des Quadrats im Log des tiler' '0 Treffer' "$hits Treffer"
        Test-Step ($log.Contains('area statistics measured')) 'Die Zeile der Route steht im Log (die Suche war nicht leer)' 'eine Zeile "area statistics measured"' 'keine'
    }
}

Show-End
