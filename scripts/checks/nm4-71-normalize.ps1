<#
.SYNOPSIS
    NM4-71: normalize version 4 measures exactly in the job; the preview estimates, also without an AOI.

.DESCRIPTION
    Voraussetzung: der Stack laeuft (docker compose up -d --build) und das Netz erreicht die Quelle
    (Earth Search, ohne VPN). Aus dem Wurzelverzeichnis des Repos starten:

        .\scripts\checks\nm4-71-normalize.ps1

    Mit der ganzen Szene als Job (dauert je nach Leitung mehrere Minuten):

        .\scripts\checks\nm4-71-normalize.ps1 -WholeScene

    Sperrt die Ausfuehrungsrichtlinie das Skript, einmal so:
        powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\checks\nm4-71-normalize.ps1

    Windows PowerShell 5.1, keine Module. Each step is printed as PASS or FAIL:
      1. find a Sentinel-2 scene (summer 2025, else April to October; at most 10 % clouds) around 7 E / 46 N whose
         outline holds a square of 0.3 degrees (larger than 2048 x 2048 pixels at 10 m), the square laid into that
         outline as near to 7 E / 46 N as it fits; when none fits, the reasons are counted (no id, no coordinate)
      2. preview: POST the order to the tiler without an AOI (whole scene) and with the square: both answer,
         coarser than the result (exact false, factor above 1)
      3. job: normalize version 4 (percentile 2-98, z-score) over the square, without numbers in the recipe; the
         result carries the exact numbers (earthx:normalize, exact true) and does what the method says
      4. the gear: version 3 with the numbers of the result gives the same statistics as the job
      5. refusals: version 4 with numbers, and a step of version 4 in the start of a measure
      6. optional (-WholeScene): the same job without an AOI over the whole scene
      7. docker compose logs tiler: no coordinate of the square

    The script prints no item id, no coordinate, no job id and no hash. Exit code 0 when all pass.
    It has not been run in the session that wrote it (no PowerShell there): the helpers are those of
    nm4-11-normalize.ps1; if a step fails because of the script, say so, do not read it as a fault of the platform.
#>
[CmdletBinding()]
param(
    [string]$ApiUrl = 'http://localhost:8000',
    [string]$TilerUrl = 'http://localhost:8001',
    [int]$JobTimeoutSeconds = 1200,
    [switch]$WholeScene
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'      # the progress bar makes Invoke-WebRequest slow in 5.1
$Invariant             = [System.Globalization.CultureInfo]::InvariantCulture
$Dataset               = 'sentinel-2-c1-l2a'
$SearchBox             = @(6.9, 45.9, 7.1, 46.1)
#: Tried one after the other until a scene fits: the summer first, then a wider season.
$SearchPeriods         = @('2025-06-15T00:00:00Z/2025-08-31T23:59:59Z', '2025-04-01T00:00:00Z/2025-10-31T23:59:59Z')
$MaxCloudPercent       = 10.0
#: The point the square should lie near; the square itself is laid into the outline of the chosen scene (step 1).
$PreferLon             = 7.0137913
$PreferLat             = 46.0246802
$CentreLon             = $PreferLon
$CentreLat             = $PreferLat
#: Half the side of the square: 0.3 degrees are about 23 x 33 km here, above 2048 x 2048 pixels at 10 m.
$Half                  = 0.15
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

function Test-InRing {
    # Whether the point [lon, lat] lies in the ring (even-odd rule).
    param($Ring, [double]$Lon, [double]$Lat)
    $inside = $false
    $count = @($Ring).Count
    for ($i = 0; $i -lt $count; $i++) {
        $a = $Ring[$i]; $b = $Ring[($i + 1) % $count]
        $ax = [double]$a[0]; $ay = [double]$a[1]; $bx = [double]$b[0]; $by = [double]$b[1]
        if ((($ay -gt $Lat) -ne ($by -gt $Lat)) -and ($Lon -lt ($bx - $ax) * ($Lat - $ay) / ($by - $ay) + $ax)) {
            $inside = -not $inside
        }
    }
    return $inside
}

function Test-SquareInRing {
    # Whether the square of half side $Half around the point lies in the ring: corners, middles of the sides, centre.
    param($Ring, [double]$Lon, [double]$Lat, [double]$Half)
    foreach ($dx in @(-1, 0, 1)) {
        foreach ($dy in @(-1, 0, 1)) {
            if (-not (Test-InRing $Ring ($Lon + $dx * $Half) ($Lat + $dy * $Half))) { return $false }
        }
    }
    return $true
}

function Find-Square {
    # The centre of a square of half side $Half that lies wholly in one ring of the outline, nearest to the preferred
    # point: that point itself if the square fits there, else the nearest of a 9 x 9 grid over the ring; $null if none.
    param($Rings, [double]$Half, [double]$PreferLon, [double]$PreferLat)
    $best = $null
    $bestDistance = [double]::MaxValue
    foreach ($ring in $Rings) {
        $points = @($ring)
        if ($points.Count -lt 4) { continue }
        if (Test-SquareInRing $ring $PreferLon $PreferLat $Half) {
            return [pscustomobject]@{ Lon = $PreferLon; Lat = $PreferLat }
        }
        $lons = @($points | ForEach-Object { [double]$_[0] })
        $lats = @($points | ForEach-Object { [double]$_[1] })
        $west = ($lons | Measure-Object -Minimum).Minimum + $Half
        $east = ($lons | Measure-Object -Maximum).Maximum - $Half
        $south = ($lats | Measure-Object -Minimum).Minimum + $Half
        $north = ($lats | Measure-Object -Maximum).Maximum - $Half
        if ($east -lt $west -or $north -lt $south) { continue }
        for ($i = 0; $i -le 8; $i++) {
            for ($j = 0; $j -le 8; $j++) {
                $lon = $west + ($east - $west) * $i / 8
                $lat = $south + ($north - $south) * $j / 8
                $distance = ($lon - $PreferLon) * ($lon - $PreferLon) + ($lat - $PreferLat) * ($lat - $PreferLat)
                if ($distance -lt $bestDistance -and (Test-SquareInRing $ring $lon $lat $Half)) {
                    $best = [pscustomobject]@{ Lon = $lon; Lat = $lat }
                    $bestDistance = $distance
                }
            }
        }
    }
    return $best
}

function Select-Scene {
    # The clearest scene with at most $MaxCloud % clouds whose outline holds the square, with the centre of the square;
    # and, counted, why the others did not fit. Names no scene and no coordinate.
    param($Features, [double]$MaxCloud, [double]$Half, [double]$PreferLon, [double]$PreferLat)
    $reasons = [ordered]@{ 'ohne Wolkenangabe' = 0; 'wolkig' = 0; 'ohne Umriss' = 0; 'Quadrat nicht enthalten' = 0 }
    $candidates = @()
    foreach ($feature in @($Features)) {
        if ($null -eq $feature) { continue }
        $cloud = $null
        if ($null -ne $feature.properties) { $cloud = $feature.properties.'eo:cloud_cover' }
        if ($null -eq $cloud) { $reasons['ohne Wolkenangabe']++; continue }
        if ([double]$cloud -gt $MaxCloud) { $reasons['wolkig']++; continue }
        $rings = Get-Rings $feature.geometry
        if ($null -eq $rings -or @($rings).Count -eq 0) { $reasons['ohne Umriss']++; continue }
        $centre = Find-Square $rings $Half $PreferLon $PreferLat
        if ($null -eq $centre) { $reasons['Quadrat nicht enthalten']++; continue }
        $candidates += [pscustomobject]@{ Id = [string]$feature.id; Cloud = [double]$cloud; Lon = $centre.Lon; Lat = $centre.Lat }
    }
    $chosen = $candidates | Sort-Object Cloud | Select-Object -First 1
    return [pscustomobject]@{ Scene = $chosen; Count = $candidates.Count; Reasons = $reasons }
}

function Format-Reasons {
    param($Reasons)
    return (@($Reasons.Keys | ForEach-Object { "{0}: {1}" -f $_, $Reasons[$_] }) -join ', ')
}

# ---- the orders -------------------------------------------------------------------------------------

function New-Order {
    # An order of recipe version 2: the bands of the output, no assets. $Steps is the text of the steps array.
    # Without $Aoi the order names the whole scene (the platform takes the footprint as its area).
    param([string]$ItemId, [string]$Aoi, [string]$Steps, [string]$Dtype)
    $area = ''
    if ($Aoi) { $area = ', "aoi": ' + $Aoi }
    return '{"recipe_version": 2, "inputs": [{"name": "input", "dataset": "' + $Dataset + '", "groups": [["' + $ItemId +
        '"]]}]' + $area + ', "steps": [' + $Steps + ']' +
        ', "output": {"kind": "raster", "format": "cog", "dtype": "' + $Dtype + '", "bands": ["red"]}}'
}

function New-Step {
    param([int]$Version, [string]$Params)
    return '{"op": "normalize", "op_version": ' + $Version + ', "params": ' + $Params + '}'
}

function Get-JobResult {
    # The statistics of the first band of the job's result, or $null (a FAIL is printed).
    param([string]$Order, [string]$Text)
    $placed = Invoke-Http -Method Post -Uri "$ApiUrl/processing/processes/recipe/execution" -Body ('{"inputs": {"recipe": ' + $Order + '}}')
    $job = ConvertFrom-JsonSafe $placed.Content
    if (($placed.Status -ne 201 -and $placed.Status -ne 200) -or $null -eq $job -or -not $job.jobID) {
        Write-Fail "${Text}: Job starten" 'HTTP 201 mit jobID' (Get-Detail $placed)
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
        Write-Fail "${Text}: Job fertig" "successful in $JobTimeoutSeconds s (laeuft der Dienst worker?)" $state
        return $null
    }
    $results = Invoke-Http -Uri "$statusUrl/results" -TimeoutSec 60
    $document = ConvertFrom-JsonSafe $results.Content
    if ($null -eq $document -or $null -eq $document.result.properties) {
        Write-Fail "${Text}: Statistik des Jobs lesen" 'result.properties.bands[0].statistics' (Get-Detail $results)
        return $null
    }
    $properties = $document.result.properties
    return [pscustomobject]@{
        Statistics = $properties.bands[0].statistics
        Lineage    = [string]$properties.'processing:lineage'
        Normalize  = $properties.'earthx:normalize'
    }
}

function Format-Value {
    param($Value)
    return ([double]$Value).ToString('R', $Invariant)
}

# ---- 1. scene and square ----------------------------------------------------------------------------
Write-Host "NM4-71: normalize exakt im Job, $Dataset" -ForegroundColor Cyan
Write-Host ''
Write-Host '1. Szene suchen, Quadrat bilden' -ForegroundColor Cyan

$box = ($SearchBox | ForEach-Object { Format-Number $_ }) -join ', '
$selected = $null
$tried = @()
foreach ($period in $SearchPeriods) {
    # No cloud filter at the source: the reasons below count every scene of the area.
    $search = '{"collections": ["' + $Dataset + '"], "bbox": [' + $box + '], "datetime": "' + $period + '", "limit": 100}'
    $found = Invoke-Http -Method Post -Uri "$ApiUrl/stac/search" -Body $search -TimeoutSec 120
    if ($found.Status -ne 200) {
        Stop-Run 'Szene suchen' 'HTTP 200 (laeuft docker compose up -d --build?)' (Get-Detail $found)
    }
    $features = @((ConvertFrom-JsonSafe $found.Content).features)
    $selected = Select-Scene $features $MaxCloudPercent $Half $PreferLon $PreferLat
    $tried += ("{0} Szenen ({1})" -f $features.Count, (Format-Reasons $selected.Reasons))
    if ($null -ne $selected.Scene) { break }
}
if ($null -eq $selected -or $null -eq $selected.Scene) {
    Stop-Run 'Szene suchen' "eine Szene mit hoechstens $MaxCloudPercent % Wolken, deren Umriss ein Quadrat von $(2 * $Half) Grad enthaelt" ($tried -join '; ')
}
$scene = $selected.Scene
$script:ItemId = $scene.Id
$CentreLon = [double]$scene.Lon
$CentreLat = [double]$scene.Lat
Write-Pass ("Szene gefunden ({0} Kandidaten, Wolken {1} %), Quadrat von {2} Grad im Umriss gebildet" -f `
    $selected.Count, $scene.Cloud.ToString('0.#', $Invariant), (2 * $Half).ToString('0.##', $Invariant))
Write-Info ('Suche: ' + ($tried -join '; '))
$aoi = New-Square $Half

# ---- 2. the preview's measure --------------------------------------------------------------------
Write-Host ''
Write-Host '2. Vorschau: Messung ohne AOI und ueber das Quadrat (Band red, float64)' -ForegroundColor Cyan

$whole = Invoke-Http -Method Post -Uri $Route -Body (New-Order $script:ItemId '' '' 'float64')
$wholeAnswer = ConvertFrom-JsonSafe $whole.Content
Test-Step ($whole.Status -eq 200) 'Messung ohne AOI angenommen (ganze Szene)' 'HTTP 200' (Get-Detail $whole)
if ($whole.Status -eq 200) {
    Test-Step ((-not $wholeAnswer.exact) -and [int]$wholeAnswer.factor -gt 1) 'Ganze Szene: geschaetzt auf einem groeberen Raster' 'exact false, factor > 1' "exact $($wholeAnswer.exact), factor $($wholeAnswer.factor)"
    Write-Info ("Dauer {0} s, factor {1}" -f $whole.Seconds.ToString('0.0', $Invariant), $wholeAnswer.factor)
}

$measure = Invoke-Http -Method Post -Uri $Route -Body (New-Order $script:ItemId $aoi '' 'float64')
if ($measure.Status -ne 200) {
    Stop-Run 'Messung ueber das Quadrat' 'HTTP 200' (Get-Detail $measure)
}
$answer = ConvertFrom-JsonSafe $measure.Content
$m = $answer.bands[0].statistics
Test-Step ((-not $answer.exact) -and [int]$answer.factor -gt 1) 'Quadrat ueber 2048 x 2048: Vorschau geschaetzt' 'exact false, factor > 1' "exact $($answer.exact), factor $($answer.factor)"
Write-Info ("Dauer {0} s, factor {1}" -f $measure.Seconds.ToString('0.0', $Invariant), $answer.factor)

# ---- 3. jobs of version 4 ---------------------------------------------------------------------------
Write-Host ''
Write-Host '3. Jobs mit normalize Version 4 (keine Zahlen im Rezept)' -ForegroundColor Cyan

$percentileV4 = '{"method": "percentile", "bands": ["red"], "low": 2, "high": 98, "out_min": 0, "out_max": 1, "clip": true}'
$zscoreV4 = '{"method": "zscore", "bands": ["red"]}'

$exactNumbers = $null
$percentileStatistics = $null
$job = Get-JobResult (New-Order $script:ItemId $aoi (New-Step 4 $percentileV4) 'float32') 'Perzentile'
if ($null -ne $job) {
    Write-Pass 'Perzentile: Job ist successful'
    $entry = @($job.Normalize) | Select-Object -First 1
    $numbers = $null
    if ($null -ne $entry -and $null -ne $entry.bands) { $numbers = $entry.bands.red }
    Test-Step ($null -ne $numbers -and $entry.exact -eq $true -and $null -ne $numbers.p_low -and $null -ne $numbers.p_high) 'Perzentile: das Ergebnis nennt die exakten Zahlen (earthx:normalize)' 'exact true, p_low, p_high' 'fehlt'
    if ($null -ne $numbers -and $null -ne $numbers.p_low) {
        $exactNumbers = $numbers
        $percentileStatistics = $job.Statistics
        Write-Info ("exakt p2 {0}, p98 {1}; Vorschau p2 {2}, p98 {3}" -f (Format-Value $numbers.p_low), (Format-Value $numbers.p_high), (Format-Value $m.percentile_2), (Format-Value $m.percentile_98))
        $span = [double]$numbers.p_high - [double]$numbers.p_low
        $off = [math]::Max([math]::Abs([double]$m.percentile_2 - [double]$numbers.p_low), [math]::Abs([double]$m.percentile_98 - [double]$numbers.p_high))
        Test-Step ($span -gt 0 -and $off -le 0.1 * $span) 'Perzentile: Vorschau und Job liegen nah beieinander' 'Abweichung <= 10 % der Spanne' (Format-Value $off)
    }
    Test-Step ([double]$job.Statistics.minimum -eq 0 -and [double]$job.Statistics.maximum -eq 1) 'Perzentile: die Enden des Ergebnisses sind 0 und 1' 'minimum 0, maximum 1' "minimum $($job.Statistics.minimum), maximum $($job.Statistics.maximum)"
}

$job = Get-JobResult (New-Order $script:ItemId $aoi (New-Step 4 $zscoreV4) 'float32') 'Z-Score'
if ($null -ne $job) {
    Write-Pass 'Z-Score: Job ist successful'
    Test-Step ([math]::Abs([double]$job.Statistics.mean) -lt 0.0001) 'Z-Score: Mittelwert des Ergebnisses ist 0' '|mittel| < 0.0001' (Format-Value $job.Statistics.mean)
    Test-Step ([math]::Abs([double]$job.Statistics.stddev - 1) -lt 0.0001) 'Z-Score: Streuung des Ergebnisses ist 1' '|streuung - 1| < 0.0001' (Format-Value $job.Statistics.stddev)
}

# ---- 4. the gear: version 3 with the numbers of the result ------------------------------------------
Write-Host ''
Write-Host '4. Zahnrad: Version 3 mit den Zahlen des Ergebnisses rechnet wie der Job' -ForegroundColor Cyan

if ($null -eq $exactNumbers) {
    Write-Fail 'Zahnrad' 'die Zahlen aus Schritt 3' 'keine'
} else {
    $fixed = '{"method": "percentile", "bands": ["red"], "low": 2, "high": 98, "out_min": 0, "out_max": 1, "clip": true, ' +
        '"measured": {"factor": 1, "bands": {"red": {"p_low": ' + (Format-Value $exactNumbers.p_low) + ', "p_high": ' + (Format-Value $exactNumbers.p_high) + '}}}}'
    $job = Get-JobResult (New-Order $script:ItemId $aoi (New-Step 3 $fixed) 'float32') 'Zahnrad'
    if ($null -ne $job) {
        $same = $true
        foreach ($name in @('minimum', 'maximum', 'mean', 'stddev', 'count', 'percentile_2', 'percentile_98')) {
            if ((Format-Value $job.Statistics.$name) -ne (Format-Value $percentileStatistics.$name)) { $same = $false }
        }
        Test-Step $same 'Zahnrad: dieselbe Statistik wie der Job mit Version 4' 'alle Felder gleich' 'verschieden'
    }
}

# ---- 5. refusals ------------------------------------------------------------------------------------
Write-Host ''
Write-Host '5. Ablehnungen' -ForegroundColor Cyan

$withNumbers = '{"method": "zscore", "bands": ["red"], "measured": {"factor": 1, "bands": {"red": {"mean": 0.1, "stddev": 0.1}}}}'
$placed = Invoke-Http -Method Post -Uri "$ApiUrl/processing/processes/recipe/execution" -Body ('{"inputs": {"recipe": ' + (New-Order $script:ItemId $aoi (New-Step 4 $withNumbers) 'float32') + '}}')
Test-Step ($placed.Status -eq 422 -or $placed.Status -eq 400) 'Version 4 mit Zahlen abgelehnt' 'HTTP 422 oder 400' "HTTP $($placed.Status)"
$inMeasure = Invoke-Http -Method Post -Uri $Route -Body (New-Order $script:ItemId $aoi (New-Step 4 $zscoreV4) 'float64')
Test-Step ($inMeasure.Status -eq 422 -or $inMeasure.Status -eq 400) 'Messung mit einem Schritt Version 4 im Anfang abgelehnt' 'HTTP 422 oder 400' "HTTP $($inMeasure.Status)"
Write-Info ("Grund: " + (Get-Detail $inMeasure))

# ---- 6. the whole scene -----------------------------------------------------------------------------
Write-Host ''
Write-Host '6. Ganze Szene als Job' -ForegroundColor Cyan

if (-not $WholeScene) {
    Write-Info 'uebersprungen (mit -WholeScene starten)'
} else {
    $job = Get-JobResult (New-Order $script:ItemId '' (New-Step 4 $percentileV4) 'float32') 'Ganze Szene'
    if ($null -ne $job) {
        Write-Pass 'Ganze Szene: Job ist successful'
        $entry = @($job.Normalize) | Select-Object -First 1
        Test-Step ($null -ne $entry -and $entry.exact -eq $true) 'Ganze Szene: exakt gemessen' 'earthx:normalize mit exact true' 'fehlt'
        if ($null -ne $entry -and $null -ne $wholeAnswer) {
            Write-Info ("exakt p2 {0}, p98 {1}; Vorschau p2 {2}, p98 {3}" -f (Format-Value $entry.bands.red.p_low), (Format-Value $entry.bands.red.p_high), `
                (Format-Value $wholeAnswer.bands[0].statistics.percentile_2), (Format-Value $wholeAnswer.bands[0].statistics.percentile_98))
        }
    }
}

# ---- 7. the log of the tiler ------------------------------------------------------------------------
Write-Host ''
Write-Host '7. docker compose logs tiler' -ForegroundColor Cyan

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
