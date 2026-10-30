<#
.SYNOPSIS
    DS-02c: checks the search filters of Sentinel-2 on the running platform, against the real source.

.DESCRIPTION
    Voraussetzung: der Stack laeuft (docker compose up -d --build) und das Netz erreicht die Quelle
    (Earth Search, ohne VPN). Aus dem Wurzelverzeichnis des Repos starten:

        .\scripts\checks\ds-02-filters.ps1

    Sperrt die Ausfuehrungsrichtlinie das Skript, einmal so:
        powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\checks\ds-02-filters.ps1

    Windows PowerShell 5.1, keine Module. Five steps, each printed as PASS or FAIL:
      1. GET /stac/collections: Sentinel-2 publishes its filters in groups, the clouds first; the DEM publishes none
      2. a search with a cloud limit keeps fewer scenes than the same search without, and every scene it returns is
         inside the limit (box of one degree in the Alps, June 2024: no one's AOI)
      3. a choice: the satellite and the processing baseline keep exactly the scenes that carry the value
      4. refusals: a bound outside the range, a property nobody offers, a filter for a dataset that is not searched,
         and both spellings in one request are 400 and the text names no value; GET with query is 400
      5. the coverage counts as many scenes as the search finds, with the same filter

    The script prints no item id and no coordinate (it compares counts and values of fields). Exit code 0 when all pass.
#>
[CmdletBinding()]
param(
    [string]$ApiUrl = 'http://localhost:8000'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'      # the progress bar makes Invoke-WebRequest slow in 5.1
$Dataset               = 'sentinel-2-c1-l2a'
$Dem                   = 'cop-dem-glo-30'
$Box                   = '[10, 47, 11, 48]'
$BoxText               = '10,47,11,48'
$Period                = '2024-06-01T00:00:00Z/2024-06-30T23:59:59Z'
$script:Failed         = 0
$script:Passed         = 0

$ApiUrl = $ApiUrl.TrimEnd('/')

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
    param([string]$Method = 'GET', [string]$Uri, [string]$Body, [int]$TimeoutSec = 120)
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
    param($Answer)
    $problem = ConvertFrom-JsonSafe $Answer.Content
    if ($null -ne $problem -and $problem.detail -is [string]) { return "HTTP $($Answer.Status): $($problem.detail)" }
    if ($Answer.Status -eq 0) { return 'keine Antwort' }
    return "HTTP $($Answer.Status)"
}

function Invoke-Search {
    # A search of the box and month; $Query is the text of `query_by_collection` or empty.
    param([string]$Query, [string]$Collections = ('"' + $Dataset + '"'))
    $extra = ''
    if ($Query) { $extra = ', "query_by_collection": ' + $Query }
    $body = '{"collections": [' + $Collections + '], "bbox": ' + $Box + ', "datetime": "' + $Period + '", "limit": 100' + $extra + '}'
    return Invoke-Http -Method 'POST' -Uri "$ApiUrl/stac/search" -Body $body
}

function Get-Features {
    param($Answer)
    $parsed = ConvertFrom-JsonSafe $Answer.Content
    if ($null -eq $parsed -or $null -eq $parsed.features) { return @() }
    return @($parsed.features)
}

function Get-Coverage {
    # `total_count` of the coverage of the box and month, with the filter as the text of `query` or without.
    param([string]$Query)
    $uri = "$ApiUrl/coverage/$Dataset" + "?zoom=4&bbox=$BoxText&datetime=" + [uri]::EscapeDataString($Period)
    if ($Query) { $uri = $uri + '&query=' + [uri]::EscapeDataString($Query) }
    $answer = Invoke-Http -Uri $uri
    $parsed = ConvertFrom-JsonSafe $answer.Content
    if ($null -eq $parsed -or $null -eq $parsed.total_count) { return -1 }
    return [int]$parsed.total_count
}

# ---- 1. what the collections publish ------------------------------------------------------------------

$collections = ConvertFrom-JsonSafe (Invoke-Http -Uri "$ApiUrl/stac/collections").Content
if ($null -eq $collections) {
    Write-Fail 'GET /stac/collections' 'a list of collections' 'no answer'
    Show-End
}
$sentinel = @($collections.collections | Where-Object { $_.id -eq $Dataset })[0]
$dem      = @($collections.collections | Where-Object { $_.id -eq $Dem })[0]
$filters  = @()
if ($null -ne $sentinel) { $filters = @($sentinel.'earthx:search_filters') }
$groups = @()
foreach ($filter in $filters) { if ($groups -notcontains $filter.group) { $groups += $filter.group } }
Test-Step ($filters.Count -ge 13) 'Sentinel-2 publishes at least the 13 filters of 30.10.2026' '13 or more' "$($filters.Count)"
Test-Step ($groups.Count -ge 2 -and $groups[0] -eq 'Clouds') 'in groups, the group Clouds first' 'Clouds first' ($groups -join ',')
Test-Step (@($filters | Where-Object { -not $_.title -or -not $_.group -or -not $_.description }).Count -eq 0) 'each with title, group and tooltip' 'none missing' 'one missing'
$first = ''
if ($filters.Count -gt 0) { $first = $filters[0].property }
Test-Step ($first -eq 'eo:cloud_cover') 'the cloud cover comes first' 'eo:cloud_cover' $first
$demFilters = @()
if ($null -ne $dem) { $demFilters = @($dem.'earthx:search_filters' | Where-Object { $null -ne $_ }) }
Test-Step ($null -ne $dem -and $demFilters.Count -eq 0) 'the DEM publishes none' '0' "$($demFilters.Count)"

# ---- 2. a range ---------------------------------------------------------------------------------------

$all      = @(Get-Features (Invoke-Search ''))
$cloudy   = '{"' + $Dataset + '": {"eo:cloud_cover": {"lte": 20}}}'
$kept     = @(Get-Features (Invoke-Search $cloudy))
$outside  = @($kept | Where-Object { [double]$_.properties.'eo:cloud_cover' -gt 20 })
Test-Step ($all.Count -gt 0 -and $all.Count -lt 100) 'the search of the box finds scenes' 'between 1 and 99' "$($all.Count)"
Test-Step ($kept.Count -gt 0 -and $kept.Count -lt $all.Count) 'a cloud limit keeps fewer scenes' "fewer than $($all.Count)" "$($kept.Count)"
Test-Step ($outside.Count -eq 0) 'every scene it keeps is inside the limit' '0 outside' "$($outside.Count) outside"

# ---- 3. a choice ---------------------------------------------------------------------------------------

$satellite = @(Get-Features (Invoke-Search ('{"' + $Dataset + '": {"platform": {"in": ["sentinel-2a"]}}}')))
$notA      = @($satellite | Where-Object { $_.properties.platform -ne 'sentinel-2a' })
$expectedA = @($all | Where-Object { $_.properties.platform -eq 'sentinel-2a' }).Count
Test-Step ($satellite.Count -eq $expectedA -and $notA.Count -eq 0) 'the satellite keeps exactly the scenes of Sentinel-2A' "$expectedA" "$($satellite.Count)"
$held    = $all[0].properties.'s2:processing_baseline'
$expectedBaseline = @($all | Where-Object { $_.properties.'s2:processing_baseline' -eq $held }).Count
$baseline = @(Get-Features (Invoke-Search ('{"' + $Dataset + '": {"s2:processing_baseline": {"in": ["' + $held + '"]}}}')))
Test-Step ($baseline.Count -eq $expectedBaseline) 'the processing baseline keeps exactly the scenes that carry it' "$expectedBaseline" "$($baseline.Count)"
$noBaseline = @(Get-Features (Invoke-Search ('{"' + $Dataset + '": {"s2:processing_baseline": {"in": ["05.00"]}}}')))
Test-Step ($noBaseline.Count -eq 0 -or $held -eq '05.00') 'a baseline no scene of June 2024 carries keeps none' '0' "$($noBaseline.Count)"

# ---- 4. refusals ---------------------------------------------------------------------------------------

$tooHigh = Invoke-Search ('{"' + $Dataset + '": {"eo:cloud_cover": {"gte": 123.456}}}')
Test-Step ($tooHigh.Status -eq 400) 'a bound outside the range is 400' '400' (Get-Detail $tooHigh)
Test-Step (-not $tooHigh.Content.Contains('123.456')) 'and the text does not name the value' 'no value' (Get-Detail $tooHigh)
$unknown = Invoke-Search ('{"' + $Dataset + '": {"foo:bar": {"gte": 1}}}')
Test-Step ($unknown.Status -eq 400) 'a property nobody offers is 400' '400' (Get-Detail $unknown)
$other = Invoke-Search ('{"' + $Dem + '": {"eo:cloud_cover": {"lte": 20}}}')
Test-Step ($other.Status -eq 400) 'a filter for a dataset that is not searched is 400' '400' (Get-Detail $other)
$both = Invoke-Http -Method 'POST' -Uri "$ApiUrl/stac/search" -Body ('{"collections": ["' + $Dataset + '"], "bbox": ' + $Box + ', "query": {"eo:cloud_cover": {"lte": 20}}, "query_by_collection": ' + $cloudy + '}')
Test-Step ($both.Status -eq 400) 'query and query_by_collection together are 400' '400' (Get-Detail $both)
$get = Invoke-Http -Uri ("$ApiUrl/stac/search?collections=$Dataset&bbox=$BoxText&query=" + [uri]::EscapeDataString('{"eo:cloud_cover": {"lte": 20}}'))
Test-Step ($get.Status -eq 400) 'GET with query is 400' '400' (Get-Detail $get)

# ---- 5. the coverage -----------------------------------------------------------------------------------

$counted = Get-Coverage '{"eo:cloud_cover": {"lte": 20}}'
$total   = Get-Coverage ''
Test-Step ($counted -eq $kept.Count) 'the coverage counts as many scenes as the search keeps' "$($kept.Count)" "$counted"
Test-Step ($total -eq $all.Count) 'and without the filter as many as the search finds' "$($all.Count)" "$total"

Show-End
