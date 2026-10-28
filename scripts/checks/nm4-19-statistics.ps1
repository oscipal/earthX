<#
.SYNOPSIS
    NM4-19: checks the statistics of an AOI on the tiler against a real job (plan section 17.1).

.DESCRIPTION
    Voraussetzung: der Stack laeuft (docker compose up -d --build) und das Netz erreicht die Quelle
    (Earth Search, ohne VPN). Aus dem Wurzelverzeichnis des Repos starten:

        .\scripts\checks\nm4-19-statistics.ps1

    Sperrt die Ausfuehrungsrichtlinie das Skript, einmal so:
        powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\checks\nm4-19-statistics.ps1

    Windows PowerShell 5.1, keine Module. Six steps, each printed as PASS or FAIL:
      1. find a Sentinel-2 scene (summer 2025, few clouds) around 7 E / 46 N, build two squares in it
      2. POST the small square (0.08 deg) to the tiler: exact, factor 1, the same answer twice
      3. the same order as a job: wait for "successful", its statistics equal the tiler's field for field
      4. POST the large square (0.3 deg): read coarser, exact false, factor >= 2
      5. refusals: an order without an AOI is 422, a GET is 405
      6. docker compose logs tiler: no coordinate of either square, and the route's own line is there

    The script prints no item id, no coordinate, no job id and no hash. Exit code 0 when all pass.
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
# The centre of the squares: near 7 E / 46 N, with digits of its own, so that step 6 can look for them.
$CentreLon             = 7.0137913
$CentreLat             = 46.0246802
$SmallHalf             = 0.04
$LargeHalf             = 0.15
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

# ---- geometry and the order -------------------------------------------------------------------------

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

function New-Order {
    # The order as the panel builds it: NDVI over red and nir, float32. Without $Aoi it has no area.
    param([string]$ItemId, [string]$Aoi)
    $area = ''
    if ($Aoi) { $area = ', "aoi": ' + $Aoi }
    return '{"recipe_version": 1, "inputs": [{"name": "input", "dataset": "' + $Dataset + '", "groups": [["' + $ItemId +
        '"]], "assets": ["red", "nir"]}]' + $area +
        ', "steps": [{"op": "band_math", "op_version": 1, "params": {"expression": "(nir - red) / (nir + red)"}}]' +
        ', "output": {"kind": "raster", "format": "cog", "dtype": "float32"}}'
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

function Compare-Statistics {
    # The names of the fields in which two statistics objects differ (empty: the same, field for field).
    param($Left, $Right)
    $names = @()
    foreach ($object in @($Left, $Right)) {
        foreach ($property in $object.PSObject.Properties) {
            if ($names -notcontains $property.Name) { $names += $property.Name }
        }
    }
    $differ = @()
    foreach ($name in $names) {
        $a = $Left.$name; $b = $Right.$name
        if ($null -eq $a -or $null -eq $b) {
            if (-not ($null -eq $a -and $null -eq $b)) { $differ += $name }
            continue
        }
        if (([double]$a).ToString('R', $Invariant) -ne ([double]$b).ToString('R', $Invariant)) { $differ += $name }
    }
    return ,$differ
}

# ---- 1. scene and squares ---------------------------------------------------------------------------
Write-Host "NM4-19: Statistik ueber die AOI, $Dataset" -ForegroundColor Cyan
Write-Host ''
Write-Host '1. Szene suchen, Quadrate bilden' -ForegroundColor Cyan

$box = ($SearchBox | ForEach-Object { Format-Number $_ }) -join ', '
$search = '{"collections": ["' + $Dataset + '"], "bbox": [' + $box + '], "datetime": "' + $SearchPeriod + '", "limit": 30}'
$found = Invoke-Http -Method Post -Uri "$ApiUrl/stac/search" -Body $search -TimeoutSec 120
if ($found.Status -ne 200) {
    Stop-Run 'Szene suchen' 'HTTP 200 (laeuft docker compose up -d --build?)' (Get-Detail $found)
}
$features = @((ConvertFrom-JsonSafe $found.Content).features)
$small = $SmallHalf; $large = $LargeHalf
$corners = @(
    @(($CentreLon - $small), ($CentreLat - $small)), @(($CentreLon + $small), ($CentreLat - $small)),
    @(($CentreLon + $small), ($CentreLat + $small)), @(($CentreLon - $small), ($CentreLat + $small))
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
    Stop-Run 'Szene suchen' "eine Szene mit hoechstens $MaxCloudPercent % Wolken, die das kleine Quadrat ganz enthaelt" "$($features.Count) Szenen, keine passt"
}
$scene = $candidates | Sort-Object Cloud | Select-Object -First 1
$script:ItemId = $scene.Id
Write-Pass ("Szene gefunden ({0} Kandidaten, Wolken {1} %), Quadrate von {2} und {3} Grad gebildet" -f `
    $candidates.Count, $scene.Cloud.ToString('0.#', $Invariant), (2 * $SmallHalf).ToString('0.##', $Invariant), (2 * $LargeHalf).ToString('0.##', $Invariant))
$smallAoi = New-Square $SmallHalf
$largeAoi = New-Square $LargeHalf
$order = New-Order $script:ItemId $smallAoi

# ---- 2. the measure over the small square -------------------------------------------------------------
Write-Host ''
Write-Host '2. Messung ueber das kleine Quadrat' -ForegroundColor Cyan

$first = Invoke-Http -Method Post -Uri $Route -Body $order
$area = $null
if ($first.Status -ne 200) {
    Write-Fail 'Messung' 'HTTP 200' (Get-Detail $first)
} else {
    $area = ConvertFrom-JsonSafe $first.Content
    Write-Info ("Dauer {0} s" -f $first.Seconds.ToString('0.0', $Invariant))
    Test-Step ($area.exact -eq $true) 'Messung exakt' 'exact = True' "exact = $($area.exact)"
    Test-Step ([int]$area.factor -eq 1) 'Messung auf dem Raster des Jobs' 'factor = 1' "factor = $($area.factor)"
    $count = 0
    if ($area.bands -and $area.bands[0].statistics.count) { $count = [int64]$area.bands[0].statistics.count }
    Test-Step ($count -gt 0) 'Messung zaehlt gueltige Pixel' 'count > 0' "count = $count"
    # The second may come from the cache, whose jsonb orders the keys its own way: compared field for field.
    $second = Invoke-Http -Method Post -Uri $Route -Body $order
    Write-Info ("zweite Messung {0} s" -f $second.Seconds.ToString('0.0', $Invariant))
    $again = ConvertFrom-JsonSafe $second.Content
    if ($second.Status -ne 200 -or $null -eq $again -or -not $again.bands) {
        Write-Fail 'Zweite Messung' 'HTTP 200' (Get-Detail $second)
    } else {
        $differ = Compare-Statistics $area.bands[0].statistics $again.bands[0].statistics
        if ($again.exact -ne $area.exact -or [int]$again.factor -ne [int]$area.factor) { $differ += 'exact/factor' }
        Test-Step ($differ.Count -eq 0) 'Zweite Messung gibt dieselbe Antwort' 'dieselbe Antwort' ("Abweichung in: " + ($differ -join ', '))
    }
}

# ---- 3. the same order as a job ---------------------------------------------------------------------
Write-Host ''
Write-Host '3. Derselbe Auftrag als Job' -ForegroundColor Cyan

$placed = Invoke-Http -Method Post -Uri "$ApiUrl/processing/processes/recipe/execution" -Body ('{"inputs": {"recipe": ' + $order + '}}')
$job = ConvertFrom-JsonSafe $placed.Content
if (($placed.Status -ne 201 -and $placed.Status -ne 200) -or $null -eq $job -or -not $job.jobID) {
    Write-Fail 'Job starten' 'HTTP 201 mit jobID' (Get-Detail $placed)
} else {
    $statusUrl = "$ApiUrl/processing/jobs/$([string]$job.jobID)"
    $deadline = (Get-Date).AddSeconds($JobTimeoutSeconds)
    $state = [string]$job.status
    while ($state -ne 'successful' -and $state -ne 'failed' -and $state -ne 'dismissed' -and (Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        $poll = Invoke-Http -Uri $statusUrl -TimeoutSec 60
        if ($poll.Status -eq 200) { $state = [string](ConvertFrom-JsonSafe $poll.Content).status }
    }
    if ($state -ne 'successful') {
        Write-Fail 'Job fertig' "successful in $JobTimeoutSeconds s (laeuft der Dienst worker?)" $state
    } else {
        Write-Pass 'Job ist successful'
        $results = Invoke-Http -Uri "$statusUrl/results" -TimeoutSec 60
        $document = ConvertFrom-JsonSafe $results.Content
        $jobStatistics = $null
        if ($null -ne $document -and $null -ne $document.result.properties) { $jobStatistics = $document.result.properties.bands[0].statistics }
        if ($null -eq $jobStatistics) {
            Write-Fail 'Statistik des Jobs lesen' 'result.properties.bands[0].statistics' (Get-Detail $results)
        } elseif ($null -eq $area) {
            Write-Fail 'Vergleich mit dem Job' 'eine Messung aus Schritt 2' 'keine'
        } else {
            $differ = Compare-Statistics $jobStatistics $area.bands[0].statistics
            Test-Step ($differ.Count -eq 0) 'Statistik des Jobs gleich der Messung, Feld fuer Feld' 'keine Abweichung' ("Abweichung in: " + ($differ -join ', '))
        }
    }
}

# ---- 4. the large square ----------------------------------------------------------------------------
Write-Host ''
Write-Host '4. Messung ueber das grosse Quadrat' -ForegroundColor Cyan

$coarse = Invoke-Http -Method Post -Uri $Route -Body (New-Order $script:ItemId $largeAoi)
if ($coarse.Status -ne 200) {
    Write-Fail 'Grobe Messung' 'HTTP 200' (Get-Detail $coarse)
} else {
    $answer = ConvertFrom-JsonSafe $coarse.Content
    Write-Info ("Dauer {0} s" -f $coarse.Seconds.ToString('0.0', $Invariant))
    Test-Step ($answer.exact -eq $false) 'Grosses Quadrat groeber gelesen' 'exact = False' "exact = $($answer.exact)"
    Test-Step ([int]$answer.factor -ge 2) 'Faktor des groeberen Rasters' 'factor >= 2' "factor = $($answer.factor)"
}

# ---- 5. refusals ------------------------------------------------------------------------------------
Write-Host ''
Write-Host '5. Ablehnungen' -ForegroundColor Cyan

$without = Invoke-Http -Method Post -Uri $Route -Body (New-Order $script:ItemId '')
Test-Step ($without.Status -eq 422) 'Auftrag ohne AOI abgelehnt' 'HTTP 422' "HTTP $($without.Status)"
$get = Invoke-Http -Uri $Route -TimeoutSec 60
Test-Step ($get.Status -eq 405) 'GET auf die Route abgelehnt' 'HTTP 405' "HTTP $($get.Status)"

# ---- 6. the log of the tiler ------------------------------------------------------------------------
Write-Host ''
Write-Host '6. docker compose logs tiler' -ForegroundColor Cyan

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
        # Every number of both squares, cut to four decimals (a log might round them), as a number of its own:
        # no digit just before it, so that the seconds of a timestamp ("...:06.9737...") are no hit.
        $hits = 0
        foreach ($half in @($SmallHalf, $LargeHalf)) {
            foreach ($value in @(($CentreLon - $half), ($CentreLon + $half), ($CentreLat - $half), ($CentreLat + $half))) {
                $cut = ([math]::Truncate($value * 10000) / 10000).ToString('0.0000', $Invariant)
                if ([regex]::IsMatch($log, '(?<![0-9])' + [regex]::Escape($cut))) { $hits++ }
            }
        }
        Test-Step ($hits -eq 0) 'Keine Koordinate der Quadrate im Log des tiler' '0 Treffer' "$hits Treffer"
        Test-Step ($log.Contains('area statistics measured')) 'Die Zeile der Route steht im Log (die Suche war nicht leer)' 'eine Zeile "area statistics measured"' 'keine'
        Test-Step ($log.Contains("/collections/$Dataset/statistics")) 'Das Zugriffslog nennt den Pfad der Route' "Pfad /collections/$Dataset/statistics" 'keinen'
    }
}

Show-End
