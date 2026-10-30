<#
.SYNOPSIS
    DS-03a2: checks the filter "Within AOI" of the search (earthx:aoi_cloud_cover) against the real source (plan section 6.18).

.DESCRIPTION
    Voraussetzung: der Stack laeuft (docker compose up -d --build) und das Netz erreicht die Quelle
    (Earth Search und den Bucket mit den Rastern, ohne VPN). Aus dem Wurzelverzeichnis des Repos starten:

        .\scripts\checks\ds-03a2-aoi-clouds.ps1

    Sperrt die Ausfuehrungsrichtlinie das Skript, einmal so:
        powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\checks\ds-03a2-aoi-clouds.ps1

    Windows PowerShell 5.1, keine Module. Six steps, each printed as PASS or FAIL:
      1. search Sentinel-2 over a square of 0.08 deg near 7 E / 46 N (summer 2025) with the range 0..100 % on the
         cloud share in the AOI: every scene carries its share (0..100) and its earthx:aoi_measure
      2. the range 0..10 %: exactly the scenes of step 1 whose share is at most 10; the same search again
         gives the same answer
      3. the page marker: with limit 3 the responses together give the scenes of step 1, none twice, none missing
      4. refusals, each a 400: no date range, a date range with an open end, a point as the area, a GET
         with query, earthx:aoi without the filter, the filter on the elevation model
      5. the coverage map refuses the filter (400)
      6. docker compose logs api: no coordinate of the square, and the line "aoi cloud filter" is there

    The script prints no item id, no coordinate, no marker and no hash. Exit code 0 when all pass.
#>
[CmdletBinding()]
param(
    [string]$ApiUrl = 'http://localhost:8000'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'      # the progress bar makes Invoke-WebRequest slow in 5.1
$Invariant             = [System.Globalization.CultureInfo]::InvariantCulture
$Dataset               = 'sentinel-2-c1-l2a'
$Elevation             = 'cop-dem-glo-30'
$Period                = '2025-06-15T00:00:00Z/2025-08-31T23:59:59Z'
# The centre of the square: near 7 E / 46 N, with digits of its own, so that step 6 can look for them.
$CentreLon             = 7.0137913
$CentreLat             = 46.0246802
$Half                  = 0.04
$MaxResponses          = 40
$script:Failed         = 0
$script:Passed         = 0

$ApiUrl  = $ApiUrl.TrimEnd('/')
$Root    = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Compose = Join-Path $Root 'docker-compose.yml'
$Search  = "$ApiUrl/stac/search"

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
    try {
        $response = Invoke-WebRequest @request
        return [pscustomobject]@{ Status = [int]$response.StatusCode; Content = (Read-Content $response) }
    } catch {
        $failure = $_.Exception.Response
        if ($null -eq $failure) {
            return [pscustomobject]@{ Status = 0; Content = $_.Exception.Message }
        }
        $text = ''
        try {
            $reader = New-Object System.IO.StreamReader($failure.GetResponseStream(), [System.Text.Encoding]::UTF8)
            $text = $reader.ReadToEnd()
            $reader.Close()
        } catch { }
        return [pscustomobject]@{ Status = [int]$failure.StatusCode; Content = $text }
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
    # What a refusal says: the status and the text of the platform, which names no value of the request.
    param($Answer)
    $problem = ConvertFrom-JsonSafe $Answer.Content
    if ($null -ne $problem -and $problem.detail -is [string]) { return "HTTP $($Answer.Status): $($problem.detail)" }
    if ($Answer.Status -eq 0) { return 'keine Antwort' }
    return "HTTP $($Answer.Status)"
}

# ---- the search -------------------------------------------------------------------------------------

function Format-Number {
    param([double]$Value)
    return $Value.ToString('R', $Invariant)          # a decimal point, never a decimal comma
}

function New-Square {
    # A GeoJSON polygon as text: the square of half side $Half degrees around the centre.
    $w = Format-Number ($CentreLon - $Half); $e = Format-Number ($CentreLon + $Half)
    $s = Format-Number ($CentreLat - $Half); $n = Format-Number ($CentreLat + $Half)
    return '{"type": "Polygon", "coordinates": [[[' + "$w, $s], [$e, $s], [$e, $n], [$w, $n], [$w, $s" + ']]]}'
}

function New-Body {
    # The search as the panel will send it. $Upper: the upper bound of the share in the AOI, $null for no filter.
    param([string]$Collection = $Dataset, [string]$Datetime = $Period, [string]$Area = (New-Square), $Upper = 100,
          [int]$Limit = 100, [string]$Token, [string]$Extra)
    $text = '{"collections": ["' + $Collection + '"]'
    if ($Datetime) { $text += ', "datetime": "' + $Datetime + '"' }
    if ($Area) { $text += ', "intersects": ' + $Area }
    $text += ', "limit": ' + $Limit
    if ($null -ne $Upper) {
        $text += ', "query_by_collection": {"' + $Collection + '": {"earthx:aoi_cloud_cover": {"lte": ' + (Format-Number $Upper) + '}}}'
    }
    if ($Token) { $text += ', "token": "' + $Token + '"' }
    if ($Extra) { $text += ', ' + $Extra }
    return $text + '}'
}

function Get-Scenes {
    # The scenes of an answer as [pscustomobject]@{ Id; Share }, in the order of the answer.
    param($Answer)
    $scenes = @()
    foreach ($feature in @($Answer.features)) {
        if ($null -eq $feature) { continue }
        $scenes += [pscustomobject]@{ Id = [string]$feature.id; Share = $feature.properties.'earthx:aoi_cloud_cover'; Measure = $feature.properties.'earthx:aoi_measure' }
    }
    return ,$scenes
}

function Get-NextToken {
    param($Answer)
    foreach ($link in @($Answer.links)) {
        if ($null -ne $link -and $link.rel -eq 'next' -and $null -ne $link.body -and $link.body.token) {
            return ([string]$link.body.token)
        }
    }
    return $null
}

function Read-All {
    # Every response of one search, followed by its marker; $null when one fails. Scenes in the order given.
    param([int]$Limit, $Upper)
    $scenes = @()
    $token = $null
    for ($i = 0; $i -lt $MaxResponses; $i++) {
        $answer = Invoke-Http -Method Post -Uri $Search -Body (New-Body -Limit $Limit -Upper $Upper -Token $token) -TimeoutSec 120
        $document = ConvertFrom-JsonSafe $answer.Content
        if ($answer.Status -ne 200 -or $null -eq $document) { return $null }
        $scenes += Get-Scenes $document
        $token = Get-NextToken $document
        if (-not $token) { return ,$scenes }
    }
    return $null
}

# ---- 1. the range 0..100 ----------------------------------------------------------------------------
Write-Host "DS-03a2: Wolkenanteil in der AOI, $Dataset" -ForegroundColor Cyan
Write-Host ''
Write-Host '1. Bereich 0..100 %: jede Szene traegt ihren Anteil' -ForegroundColor Cyan

$first = Invoke-Http -Method Post -Uri $Search -Body (New-Body) -TimeoutSec 180
$document = ConvertFrom-JsonSafe $first.Content
if ($first.Status -ne 200 -or $null -eq $document) {
    Stop-Run 'Suche mit dem Filter' 'HTTP 200 (laeuft docker compose up -d --build, erreicht das Netz die Quelle?)' (Get-Detail $first)
}
$counts = $document.'earthx:aoi_filter'
# Every scene of the search, over as many responses as it takes (one response checks at most 100 scenes or 8 s).
$all = Read-All -Limit 100 -Upper 100
if ($null -eq $all) { Stop-Run 'Alle Antworten der Suche lesen' 'HTTP 200 in hoechstens 40 Antworten' 'Fehler' }
$firstScenes = Get-Scenes $document
Test-Step ($all.Count -gt 0) 'Die Suche liefert Szenen' 'mindestens eine Szene im Sommer 2025' "$($all.Count) Szenen"
Test-Step ($null -ne $counts -and $counts.checked -ge $firstScenes.Count -and $counts.found -eq $firstScenes.Count) 'Die Antwort zaehlt: geprueft >= gefunden = zurueckgegeben' 'earthx:aoi_filter mit checked und found' 'fehlt oder passt nicht'
$badShare = @($all | Where-Object { $null -eq $_.Share -or [double]$_.Share -lt 0 -or [double]$_.Share -gt 100 })
$badMeasure = @($all | Where-Object { $null -eq $_.Measure -or $null -eq $_.Measure.cloud_pixels -or $null -eq $_.Measure.data_pixels -or $null -eq $_.Measure.data_percent -or $null -eq $_.Measure.resolution })
Test-Step (($badShare.Count + $badMeasure.Count) -eq 0) 'Jede Szene hat ihren Anteil (0..100) und earthx:aoi_measure' 'alle vollstaendig' "$($badShare.Count) ohne Anteil, $($badMeasure.Count) ohne Zaehlung"
if ($all.Count -eq 0) { Stop-Run 'Weiter ohne Szenen' 'Szenen aus Schritt 1' 'keine' }

# ---- 2. the range 0..10 -----------------------------------------------------------------------------
Write-Host ''
Write-Host '2. Bereich 0..10 %: genau die Szenen aus Schritt 1 mit hoechstens 10 %' -ForegroundColor Cyan

$narrow = Read-All -Limit 100 -Upper 10
if ($null -eq $narrow) {
    Write-Fail 'Suche mit dem engeren Bereich' 'HTTP 200 in hoechstens 40 Antworten' 'Fehler'
} else {
    $expected = @($all | Where-Object { [double]$_.Share -le 10 } | ForEach-Object { $_.Id } | Sort-Object)
    $got = @($narrow | ForEach-Object { $_.Id } | Sort-Object)
    Test-Step (($expected -join '|') -eq ($got -join '|')) 'Die Szenen sind die mit hoechstens 10 % aus Schritt 1' "$($expected.Count) Szenen" "$($got.Count) Szenen"
    $again = Read-All -Limit 100 -Upper 10
    $same = $null -ne $again -and (($again | ForEach-Object { $_.Id + ':' + (Format-Number ([double]$_.Share)) }) -join '|') -eq (($narrow | ForEach-Object { $_.Id + ':' + (Format-Number ([double]$_.Share)) }) -join '|')
    Test-Step $same 'Dieselbe Suche noch einmal gibt dieselbe Antwort (aus dem Cache)' 'gleiche Szenen, gleiche Anteile' 'Abweichung'
}

# ---- 3. the marker ----------------------------------------------------------------------------------
Write-Host ''
Write-Host '3. Seitenmarke: mit limit 3 keine Luecke und kein Doppel' -ForegroundColor Cyan

$paged = Read-All -Limit 3 -Upper 100
if ($null -eq $paged) {
    Write-Fail 'Seiten mit limit 3' 'HTTP 200 in hoechstens 40 Antworten' 'Fehler oder zu viele Antworten'
} else {
    $ids = @($paged | ForEach-Object { $_.Id })
    $unique = @($ids | Sort-Object -Unique)
    $expected = @($all | ForEach-Object { $_.Id } | Sort-Object)
    Test-Step ($ids.Count -eq $unique.Count) 'Keine Szene kommt zweimal' 'keine Doppel' "$($ids.Count - $unique.Count) Doppel"
    Test-Step (($expected -join '|') -eq ($unique -join '|')) 'Alle Szenen aus Schritt 1 sind dabei' "$($expected.Count) Szenen" "$($unique.Count) Szenen"
}

# ---- 4. refusals ------------------------------------------------------------------------------------
Write-Host ''
Write-Host '4. Ablehnungen' -ForegroundColor Cyan

function Test-Refusal {
    param([string]$Text, $Answer, [string]$Contains)
    $detail = Get-Detail $Answer
    Test-Step ($Answer.Status -eq 400 -and $detail.Contains($Contains)) $Text "HTTP 400 mit '$Contains'" $detail
}

$point = '{"type": "Point", "coordinates": [' + (Format-Number $CentreLon) + ', ' + (Format-Number $CentreLat) + ']}'
Test-Refusal 'Ohne Zeitraum' (Invoke-Http -Method Post -Uri $Search -Body (New-Body -Datetime '')) 'date range'
Test-Refusal 'Zeitraum mit offenem Ende' (Invoke-Http -Method Post -Uri $Search -Body (New-Body -Datetime '2025-06-15T00:00:00Z/..')) 'date range'
Test-Refusal 'Punkt als Flaeche' (Invoke-Http -Method Post -Uri $Search -Body (New-Body -Area $point)) 'needs an area'
Test-Refusal 'earthx:aoi ohne den Filter' (Invoke-Http -Method Post -Uri $Search -Body (New-Body -Upper $null -Extra ('"earthx:aoi": ' + (New-Square)))) 'cloud share'
$elevation = Invoke-Http -Method Post -Uri $Search -Body (New-Body -Collection $Elevation)
Test-Step ($elevation.Status -eq 400) 'Der Filter beim Hoehenmodell' 'HTTP 400' (Get-Detail $elevation)
$get = Invoke-Http -Uri ("$Search" + '?collections=' + $Dataset + '&query=%7B%7D')
Test-Step ($get.Status -eq 400 -and (Get-Detail $get).Contains('POST')) 'GET mit query' "HTTP 400 mit 'POST'" (Get-Detail $get)

# ---- 5. the coverage map ----------------------------------------------------------------------------
Write-Host ''
Write-Host '5. Die Coverage-Karte nimmt den Filter nicht' -ForegroundColor Cyan

$query = [uri]::EscapeDataString('{"earthx:aoi_cloud_cover": {"lte": 20}}')
$coverage = Invoke-Http -Uri "$ApiUrl/coverage/${Dataset}?zoom=4&query=$query"
Test-Refusal 'Coverage mit dem Filter' $coverage 'coverage map'

# ---- 6. the log of the api --------------------------------------------------------------------------
Write-Host ''
Write-Host '6. docker compose logs api' -ForegroundColor Cyan

if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Fail 'Log lesen' 'docker im PATH' 'nicht gefunden'
} else {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'      # docker writes progress to stderr; 5.1 would turn that into an error
    $log = (& docker compose -f $Compose logs --no-color api 2>&1 | Out-String)
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previous
    if ($code -ne 0 -or [string]::IsNullOrWhiteSpace($log)) {
        Write-Fail 'Log lesen' 'Zeilen von docker compose logs api' "Exit-Code $code, leer"
    } else {
        # Every number of the square, cut to four decimals (a log might round them), as a number of its own:
        # no digit just before it, so that the seconds of a timestamp ("...:06.9737...") are no hit.
        $hits = 0
        foreach ($value in @(($CentreLon - $Half), ($CentreLon + $Half), ($CentreLat - $Half), ($CentreLat + $Half))) {
            $cut = ([math]::Truncate($value * 10000) / 10000).ToString('0.0000', $Invariant)
            if ([regex]::IsMatch($log, '(?<![0-9])' + [regex]::Escape($cut))) { $hits++ }
        }
        Test-Step ($hits -eq 0) 'Keine Koordinate des Quadrats im Log der api' '0 Treffer' "$hits Treffer"
        Test-Step ($log.Contains('aoi cloud filter')) 'Die Zeile "aoi cloud filter" steht im Log' 'eine Zeile je Antwort' 'keine'
        Test-Step ($log.Contains('/stac/search')) 'Das Zugriffslog nennt den Pfad der Suche' 'Pfad /stac/search' 'keinen'
    }
}

Show-End
