<#
.SYNOPSIS
    Plays one small real job through the job API of a locally running platform (M4-08b).

.DESCRIPTION
    Windows PowerShell 5.1, no extra modules (Invoke-WebRequest only). Run it from the repository
    root while `docker compose up` is running:

        powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\try-job.ps1

    Steps, each printed as OK or FEHLER:
      1. find one item for the area, send an order (reproject of one asset), expect 201 and a Location
      2. poll the status until successful or failed
      3. fetch the results, follow the 303, save result.tif, mask.tif and recipe.json
      4. send the same order again: expect a cache hit (successful at once, no new run)
      5. DELETE both jobs, expect "dismissed"
      6. search `docker compose logs api` for the job IDs: any hit is a FEHLER

    The search is the one the viewer makes: POST /stac/search with {"collections": [id], "bbox":
    [west, south, east, north], "datetime": "start/end", "limit": 1}. The order names exactly ONE
    item: the newest one the catalog finds for the area and period.

    The default area is a synthetic square on open farmland inland, not anybody's site; it goes to
    the platform in the search and in the order only. The script prints only its size - except with
    -Verbose, which prints every request the script sends (method, address, body, so the area too)
    and the size and type of every answer; use it to see what a search asked and what came back.

    Defaults need no setup: sentinel-2-c1-l2a is searched live at its source, and in July 2025 the
    default area has 18 scenes (checked against the source on 07.10.2026).

    cop-dem-glo-30 has no live search: its items exist only after
    `docker compose run --rm materialize cop-dem-glo-30`, which loads the WHOLE dataset (it cannot be
    limited to an area). If the area has no item, the script says which tile it needs and what the
    command would load: 26 450 items, about 30 requests to the source bucket (no image data), about
    5 minutes (about 45 s of listing at the source, measured on 26.09.2026, and about 4 minutes to
    write the items, measured here on 07.10.2026 in a session Postgres; yours will differ).

.PARAMETER Dataset
    Registry id of the dataset. Default sentinel-2-c1-l2a. Known: sentinel-2-c1-l2a (asset red, 20 m)
    and cop-dem-glo-30 (asset data, 90 m). Any other id needs -Asset and -Resolution.

.PARAMETER Bbox
    West, south, east, north in decimal degrees with a decimal point, separated by commas, e.g.
    -Bbox "10.50,49.50,10.51,49.51" (the default). In quotes when the script is started with -File.
    At most 2 x 2 km: a larger area is refused before anything is sent.

.PARAMETER Datetime
    Period to search, as a date or a date interval: 2025-07-01/2025-07-31 (the default for
    sentinel-2-c1-l2a), or RFC 3339 instants. Ignored for cop-dem-glo-30, whose items have no instant.

.PARAMETER Asset
    Asset key to reproject. Default: red for sentinel-2-c1-l2a, data for cop-dem-glo-30.

.PARAMETER Resolution
    Pixel size in the units of -TargetCrs. Default: 20 for sentinel-2-c1-l2a, 90 for cop-dem-glo-30.

.PARAMETER BaseUrl
    Where the platform's api runs. Default http://localhost:8000.

.PARAMETER SearchOnly
    Only the search of step 1: finds the item and stops (exit code 0 or 1). To check an area and a
    period before a job is sent.

.PARAMETER TargetCrs
    Target CRS of the reproject step. Default EPSG:3035 (metres, for Europe); choose another for
    other parts of the world.

.EXAMPLE
    .\scripts\try-job.ps1
    Sentinel-2 over the default area, July 2025.

.EXAMPLE
    .\scripts\try-job.ps1 -Bbox "10.50,49.50,10.51,49.51" -Datetime 2025-06-01/2025-06-30

.EXAMPLE
    .\scripts\try-job.ps1 -SearchOnly -Verbose -Bbox "8.535,47.365,8.545,47.372" -Datetime 2025-06-01/2025-08-31
    Only look for a scene, and print the search that was sent and the size of the answer.

.EXAMPLE
    .\scripts\try-job.ps1 -Dataset cop-dem-glo-30
    Copernicus DEM over the default area (needs the materialized catalog, see above).
#>
[CmdletBinding()]
param(
    [string]$Dataset = 'sentinel-2-c1-l2a',
    [string]$Bbox = '10.50,49.50,10.51,49.51',
    [string]$Datetime,
    [string]$Asset,
    [double]$Resolution,
    [string]$TargetCrs = 'EPSG:3035',
    [string]$BaseUrl = 'http://localhost:8000',
    [switch]$SearchOnly
)

# ---- what else to try (change here) -------------------------------------------------------------
$Resampling     = 'bilinear'          # nearest | bilinear | cubic
$TimeoutSeconds = 300                 # how long to wait for the job
$PollSeconds    = 3
$OutputDir      = '.\try-job-output'
$ComposeFile    = $null              # default: docker-compose.yml next to the scripts folder
$MaxSideKm      = 2.0                # the largest area the script sends
# What each known dataset needs besides its id.
$Presets = @{
    'sentinel-2-c1-l2a' = @{ Asset = 'red';  Resolution = 20.0; Datetime = '2025-07-01/2025-07-31' }
    'cop-dem-glo-30'    = @{ Asset = 'data'; Resolution = 90.0; Datetime = '' }
}
# -------------------------------------------------------------------------------------------------

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'      # the progress bar makes Invoke-WebRequest slow in 5.1
$Invariant             = [System.Globalization.CultureInfo]::InvariantCulture
$script:Ok             = 0
$script:Failed         = 0
$script:Lines          = New-Object System.Collections.ArrayList
$JobsToDismiss         = New-Object System.Collections.ArrayList

function Write-Result {
    param([bool]$Good, [string]$Text)
    if ($Good) {
        $script:Ok++
        $label = 'OK    '
        $color = 'Green'
    } else {
        $script:Failed++
        $label = 'FEHLER'
        $color = 'Red'
    }
    [void]$script:Lines.Add("[$label] $Text")
    Write-Host "[$label] $Text" -ForegroundColor $color
}

function Write-Info {
    param([string]$Text)
    Write-Host "         $Text" -ForegroundColor DarkGray
}

function Write-Step {
    param([string]$Text)
    Write-Host ''
    Write-Host $Text -ForegroundColor Cyan
}

function Stop-Here {
    param([string]$Reason)
    Write-Result $false $Reason
    Show-Summary
    exit 1
}

function Show-Summary {
    Write-Host ''
    Write-Host '---- Zusammenfassung ----' -ForegroundColor Cyan
    foreach ($line in $script:Lines) {
        if ($line.StartsWith('[OK')) { Write-Host $line -ForegroundColor Green } else { Write-Host $line -ForegroundColor Red }
    }
    $color = 'Green'
    if ($script:Failed -gt 0) { $color = 'Red' }
    Write-Host ("{0} OK, {1} FEHLER" -f $script:Ok, $script:Failed) -ForegroundColor $color
}

function Get-HeaderValue {
    # Works for the header collections of 5.1 (WebHeaderCollection, Dictionary) and of 7 (HttpResponseHeaders).
    param($Headers, [string]$Name)
    if ($null -eq $Headers) { return $null }
    try {
        $value = $Headers[$Name]
        if ($null -ne $value) { return (@($value) -join ',') }
    } catch { }
    try {
        return (@($Headers.GetValues($Name)) -join ',')
    } catch { }
    return $null
}

function ConvertFrom-Bytes {
    param([byte[]]$Bytes)
    if ($null -eq $Bytes -or $Bytes.Length -eq 0) { return '' }
    $text = [System.Text.Encoding]::UTF8.GetString($Bytes)
    return $text.TrimStart([char]0xFEFF)
}

function Get-ResponseBytes {
    # The bytes of an Invoke-WebRequest answer. Not `.Content`: Windows PowerShell 5.1 hands that back as
    # bytes for a type it does not know as text (the platform's search answers application/geo+json),
    # and as text, decoded by a guessed charset, for others. Reading the bytes ourselves is the same everywhere.
    param($Response)
    try {
        $stream = $Response.RawContentStream
        if ($null -ne $stream) { return ,$stream.ToArray() }
    } catch { }
    $content = $Response.Content
    if ($content -is [byte[]]) { return ,$content }
    if ($null -eq $content) { return ,([byte[]]@()) }
    return ,[System.Text.Encoding]::UTF8.GetBytes([string]$content)
}

function Limit-Text {
    param([string]$Text, [int]$Max = 1500)
    if ($Text.Length -le $Max) { return $Text }
    return $Text.Substring(0, $Max) + " ... ($($Text.Length) Zeichen)"
}

function Invoke-Http {
    # One request; never throws. Status 0 means the platform could not be reached at all.
    # With -Verbose: the request as sent (method, address, body) and the size and type of the answer.
    param(
        [string]$Method = 'GET',
        [string]$Uri,
        [string]$Body,
        [string]$OutFile,
        [switch]$NoRedirect
    )
    $request = @{ Uri = $Uri; Method = $Method; UseBasicParsing = $true; TimeoutSec = 120 }
    Write-Verbose "-> $Method $Uri"
    if ($Body) {
        $request.Body        = $Body
        $request.ContentType = 'application/json; charset=utf-8'
        Write-Verbose "   Rumpf ($($Body.Length) Zeichen): $(Limit-Text $Body)"
    }
    if ($NoRedirect) { $request.MaximumRedirection = 0 }
    if ($OutFile)    { $request.OutFile = $OutFile; $request.PassThru = $true }    # without it nothing is returned
    try {
        $response = Invoke-WebRequest @request
        $type = Get-HeaderValue $response.Headers 'Content-Type'
        if ($OutFile) {
            $text  = ''
            $bytes = (Get-Item -LiteralPath $OutFile).Length
        } else {
            $raw   = Get-ResponseBytes $response
            $text  = ConvertFrom-Bytes $raw
            $bytes = $raw.Length
        }
        Write-Verbose "<- HTTP $([int]$response.StatusCode), $bytes Bytes, Content-Type: $type"
        return [pscustomobject]@{ Status = [int]$response.StatusCode; Headers = $response.Headers; Content = $text; Bytes = $bytes; Type = $type; Error = $null }
    } catch {
        $caught  = $_
        $failure = $caught.Exception.Response
        if ($null -eq $failure) {
            Write-Verbose "<- keine Antwort: $($caught.Exception.Message)"
            return [pscustomobject]@{ Status = 0; Headers = $null; Content = ''; Bytes = 0; Type = $null; Error = $caught.Exception.Message }
        }
        $text = ''
        try {
            $reader = New-Object System.IO.StreamReader($failure.GetResponseStream(), [System.Text.Encoding]::UTF8)
            $text = $reader.ReadToEnd()
            $reader.Close()
        } catch { }
        if (-not $text -and $null -ne $caught.ErrorDetails) { $text = [string]$caught.ErrorDetails.Message }
        $type = Get-HeaderValue $failure.Headers 'Content-Type'
        Write-Verbose "<- HTTP $([int]$failure.StatusCode), $($text.Length) Zeichen, Content-Type: $type"
        return [pscustomobject]@{ Status = [int]$failure.StatusCode; Headers = $failure.Headers; Content = $text; Bytes = $text.Length; Type = $type; Error = $null }
    }
}

function ConvertFrom-JsonSafe {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
    try { return ($Text | ConvertFrom-Json) } catch { return $null }
}

function Format-Number {
    param([double]$Value)
    return $Value.ToString('0.0###############', $Invariant)    # always a decimal point, never a decimal comma
}

function Get-ProblemText {
    param($Response)
    $problem = ConvertFrom-JsonSafe $Response.Content
    if ($null -ne $problem -and $null -ne $problem.title) { return "$($problem.title): $($problem.detail) [$($problem.type)]" }
    if ($null -ne $problem -and $null -ne $problem.description) { return "$($problem.code): $($problem.description)" }
    if ($null -ne $problem -and $problem.detail -is [string]) { return [string]$problem.detail }
    if ($Response.Error) { return $Response.Error }
    return "HTTP $($Response.Status)"
}

function Test-TiffFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 8) { return $false }
    $little = ($bytes[0] -eq 0x49 -and $bytes[1] -eq 0x49 -and ($bytes[2] -eq 0x2A -or $bytes[2] -eq 0x2B) -and $bytes[3] -eq 0)
    $big    = ($bytes[0] -eq 0x4D -and $bytes[1] -eq 0x4D -and $bytes[2] -eq 0 -and ($bytes[3] -eq 0x2A -or $bytes[3] -eq 0x2B))
    return ($little -or $big)
}

function ConvertTo-Box {
    # "w,s,e,n" (commas, semicolons or blanks) -> four numbers read with a decimal point; $null if not four numbers.
    param([string]$Text)
    $tokens = @($Text -split '[,;\s]+' | Where-Object { $_ })
    if ($tokens.Count -ne 4) { return $null }
    $numbers = @()
    foreach ($token in $tokens) {
        $value = 0.0
        if (-not [double]::TryParse($token, [System.Globalization.NumberStyles]::Float, $Invariant, [ref]$value)) { return $null }
        $numbers += $value
    }
    return $numbers
}

function Get-AreaSizeKm {
    # Width and height of the box in km (a spherical approximation; plenty for a size limit).
    param([double[]]$Box)
    $kmPerDegree = 111.32
    $height = ($Box[3] - $Box[1]) * $kmPerDegree
    $width  = ($Box[2] - $Box[0]) * $kmPerDegree * [math]::Cos((($Box[1] + $Box[3]) / 2) * [math]::PI / 180)
    return @($width, $height)
}

function ConvertTo-StacDatetime {
    # '2025-07-01/2025-07-31' -> '2025-07-01T00:00:00Z/2025-07-31T23:59:59Z'; one date -> that whole day.
    param([string]$Text)
    $parts = $Text.Trim().Split('/')
    if ($parts.Count -eq 1 -and $parts[0] -ne '..') { $parts = @($parts[0], $parts[0]) }
    if ($parts.Count -ne 2) { return $null }
    $out = @()
    for ($n = 0; $n -lt 2; $n++) {
        $part = $parts[$n].Trim()
        if ($part -eq '..') {
            $out += $part
        } elseif ($part -match '^\d{4}-\d{2}-\d{2}$') {
            if ($n -eq 0) { $out += "${part}T00:00:00Z" } else { $out += "${part}T23:59:59Z" }
        } elseif ($part -match '^\d{4}-\d{2}-\d{2}T[0-9:.]+(Z|[+-]\d{2}:\d{2})$') {
            $out += $part
        } else {
            return $null
        }
    }
    return ($out -join '/')
}

function Get-FeatureCount {
    param($Collection)
    if ($null -eq $Collection -or $null -eq $Collection.features) { return 0 }
    return @($Collection.features).Count
}

function Get-DemTileNames {
    # The 1 x 1 degree tiles a box touches, named as the source names them (the south-west corner).
    param([double[]]$Box)
    $names = @()
    $lat0 = [int][math]::Floor($Box[1]); $lat1 = [int][math]::Floor($Box[3] - 1e-9)
    $lon0 = [int][math]::Floor($Box[0]); $lon1 = [int][math]::Floor($Box[2] - 1e-9)
    for ($lat = $lat0; $lat -le $lat1; $lat++) {
        for ($lon = $lon0; $lon -le $lon1; $lon++) {
            if ($lat -ge 0) { $ns = 'N{0:00}' -f $lat } else { $ns = 'S{0:00}' -f (-$lat) }
            if ($lon -ge 0) { $ew = 'E{0:000}' -f $lon } else { $ew = 'W{0:000}' -f (-$lon) }
            $names += [pscustomobject]@{ Name = "Copernicus_DSM_COG_10_${ns}_00_${ew}_00_DEM"; Lat = $lat; Lon = $lon }
        }
    }
    return $names
}

function Write-MaterializeFacts {
    Write-Info '  Umfang:   26 450 Items (eine je Kachel der Quelle), keine Bilddaten'
    Write-Info '  Anfragen: rund 30 an copernicus-dem-30m.s3.amazonaws.com (Kachelliste 1,1 MB, Sperrliste, Bucket-Listing in 27 Seiten)'
    Write-Info '  Dauer:    rund 5 Minuten: das Listing etwa 45 s (gemessen am 26.09.2026, 1 Anfrage/s), das Schreiben der Items'
    Write-Info '            in den Katalog etwa 4 Minuten (235 s für 26 450 Items, gemessen am 07.10.2026 in der Postgres einer'
    Write-Info '            Sitzung; auf diesem Rechner kann es anders sein)'
    Write-Info '  Danach:   ein zweiter Lauf ohne Änderung an der Quelle endet nach einer Anfrage mit "unchanged".'
}

function Write-DemHint {
    param([double[]]$Box)
    $tiles = @(Get-DemTileNames $Box)
    $names = ($tiles | ForEach-Object { $_.Name }) -join ', '
    $any = Invoke-Http -Method Post -Uri "$BaseUrl/stac/search" -Body ('{"collections": ["' + $Dataset + '"], "limit": 1}')
    $anything = ($any.Status -eq 200 -and (Get-FeatureCount (ConvertFrom-JsonSafe $any.Content)) -gt 0)
    Write-Info "Das Gebiet liegt in $($tiles.Count) Kachel(n) des $Dataset (je 1 x 1 Grad): $names"
    if ($anything) {
        Write-Info 'Der Katalog hat Items für diesen Datensatz, aber keins für diese Kachel.'
        $gap = @($tiles | Where-Object { $_.Lat -ge 38 -and $_.Lat -le 41 -and $_.Lon -ge 43 -and $_.Lon -le 50 })
        if ($gap.Count -gt 0) {
            Write-Info 'Die Kachel liegt in der Lücke der 25 zurückgezogenen Kacheln (N38-N41, E043-E050, adr/0009 §10.3): die Quelle selbst hat dort nichts.'
        } else {
            Write-Info 'Mögliche Gründe: offenes Meer (dort gibt es keine DEM-Kacheln), oder der Katalog ist unvollständig.'
            Write-Info '  Unvollständig? Ein neuer Lauf mit --force lädt die ganze Kachelliste neu (Umfang und Dauer unten):'
            Write-Info "    docker compose run --rm materialize $Dataset --force"
            Write-MaterializeFacts
        }
        Write-Info 'Oder ein Gebiet an Land wählen (-Bbox) bzw. -Dataset sentinel-2-c1-l2a (Standard), das nichts davon braucht.'
        return
    }
    Write-Info "Der Katalog hat für $Dataset noch gar kein Item: der Datensatz wurde nicht materialisiert."
    Write-Info 'Der Befehl lässt sich nicht auf ein Gebiet beschränken; er lädt den ganzen Datensatz, also auch die Kachel(n) oben:'
    Write-Info "    docker compose run --rm materialize $Dataset"
    Write-MaterializeFacts
    Write-Info 'Wer nicht warten will: -Dataset sentinel-2-c1-l2a (Standard) braucht nichts davon.'
}

if (-not $ComposeFile) {
    $here = $PSScriptRoot
    if (-not $here) { $here = Join-Path (Get-Location).Path 'scripts' }
    $ComposeFile = Join-Path (Split-Path -Parent $here) 'docker-compose.yml'
}
$BaseUrl   = $BaseUrl.TrimEnd('/')
$OutputDir = [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path $OutputDir))
Write-Host "Job-Schnittstelle unter $BaseUrl/processing, Datensatz $Dataset" -ForegroundColor Cyan

# ---- 1. place the order -------------------------------------------------------------------------
Write-Step '1. Auftrag senden'

# The inputs, checked before anything is sent.
$box = ConvertTo-Box $Bbox
if ($null -eq $box) { Stop-Here '-Bbox: genau vier Zahlen mit Dezimalpunkt erwartet: "West,Süd,Ost,Nord"' }
if ($box[0] -ge $box[2] -or $box[1] -ge $box[3] -or $box[0] -lt -180 -or $box[2] -gt 180 -or $box[1] -lt -90 -or $box[3] -gt 90) {
    Stop-Here '-Bbox: West < Ost und Süd < Nord, Längen -180..180, Breiten -90..90 erwartet'
}
$size = Get-AreaSizeKm $box
if ($size[0] -gt $MaxSideKm -or $size[1] -gt $MaxSideKm) {
    Stop-Here ("-Bbox: das Gebiet ist {0} x {1} km, erlaubt sind höchstens {2} x {2} km" -f `
        $size[0].ToString('0.0', $Invariant), $size[1].ToString('0.0', $Invariant), $MaxSideKm.ToString('0.#', $Invariant))
}
if ($Presets.ContainsKey($Dataset)) {
    if (-not $Asset)      { $Asset = $Presets[$Dataset].Asset }
    if (-not $Resolution) { $Resolution = $Presets[$Dataset].Resolution }
    if (-not $PSBoundParameters.ContainsKey('Datetime')) { $Datetime = $Presets[$Dataset].Datetime }
}
if (-not $Asset -or -not $Resolution) {
    Stop-Here "Datensatz ${Dataset}: unbekannt für dieses Skript, -Asset und -Resolution angeben"
}
if ($Resolution -le 0) { Stop-Here '-Resolution: eine Zahl größer als 0 erwartet' }
if ($Dataset -eq 'cop-dem-glo-30' -and $Datetime) {
    Write-Info 'Hinweis: cop-dem-glo-30 hat keinen Zeitpunkt je Item, -Datetime wird nicht verwendet.'
    $Datetime = ''
}
$stacDatetime = $null
if ($Datetime) {
    $stacDatetime = ConvertTo-StacDatetime $Datetime
    if (-not $stacDatetime) { Stop-Here "-Datetime: '$Datetime' nicht lesbar (z. B. 2025-07-01/2025-07-31)" }
}
$kmText = "{0} x {1} km" -f $size[0].ToString('0.0', $Invariant), $size[1].ToString('0.0', $Invariant)
Write-Info "Gebiet: $kmText, Asset $Asset, Ziel $TargetCrs mit $(Format-Number $Resolution)"
if ($stacDatetime) { Write-Info "Zeitraum: $stacDatetime" }

$west  = Format-Number $box[0]
$south = Format-Number $box[1]
$east  = Format-Number $box[2]
$north = Format-Number $box[3]
$bboxText = "$west,$south,$east,$north"

# The search the viewer makes (frontend api.ts searchItems): POST /stac/search with a JSON body, bbox as
# four numbers [west, south, east, north], datetime as "start/end" with times, limit.
$searchBody = '{"collections": ["' + $Dataset + '"], "bbox": [' + $bboxText + ']'
if ($stacDatetime) { $searchBody += ', "datetime": "' + $stacDatetime + '"' }
$searchBody += ', "limit": 1}'
$found = Invoke-Http -Method Post -Uri "$BaseUrl/stac/search" -Body $searchBody
if ($found.Status -eq 0) {
    Stop-Here "Item suchen: die Plattform antwortet nicht ($($found.Error)) - läuft sie (docker compose up)?"
}
if ($found.Status -ne 200) {
    Stop-Here "Item suchen: HTTP $($found.Status) - $(Get-ProblemText $found)"
}
$collection = ConvertFrom-JsonSafe $found.Content
if ($null -eq $collection) {
    Stop-Here "Item suchen: die Antwort ist kein lesbares JSON ($($found.Bytes) Bytes, Content-Type: $($found.Type)); mit -Verbose sieht man die Anfrage"
}
if ($null -eq $collection.features) {
    Stop-Here "Item suchen: die Antwort hat kein Feld features ($($found.Bytes) Bytes, Content-Type: $($found.Type))"
}
Write-Info "Antwort der Suche: $($found.Bytes) Bytes, $(Get-FeatureCount $collection) Item(s)"
if ((Get-FeatureCount $collection) -lt 1) {
    if ($Dataset -eq 'cop-dem-glo-30') {
        Write-DemHint $box
    } else {
        Write-Info "Der Katalog findet für $Dataset in diesem Gebiet und Zeitraum kein Item."
        Write-Info 'Zeitraum erweitern (-Datetime 2025-06-01/2025-08-31) oder ein anderes Gebiet wählen (-Bbox); -Verbose zeigt die gesendete Anfrage.'
    }
    Stop-Here 'Item suchen: kein Item gefunden'
}
$item   = $collection.features[0]
$itemId = [string]$item.id
$when   = ''
if ($item.properties -and $item.properties.datetime) {
    $raw = $item.properties.datetime
    if ($raw -is [datetime]) {      # PowerShell 6+ turns the text into a date; 5.1 leaves it as text
        $when = ' vom ' + $raw.ToUniversalTime().ToString('yyyy-MM-dd HH:mm', $Invariant) + ' UTC'
    } else {
        $when = " vom $raw"
    }
}
Write-Result $true "Item gefunden (genau eines wird verwendet): $itemId$when"
if ($SearchOnly) {
    Show-Summary
    exit 0
}

$order = @"
{"inputs": {"recipe": {
  "recipe_version": 1,
  "inputs": [{"name": "scene", "dataset": "$Dataset", "groups": [["$itemId"]], "assets": ["$Asset"]}],
  "aoi": {"type": "Polygon", "coordinates": [[[$west, $south], [$east, $south], [$east, $north], [$west, $north], [$west, $south]]]},
  "steps": [{"op": "reproject", "op_version": 2, "params": {"crs": "$TargetCrs", "resolution": $(Format-Number $Resolution), "resampling": "$Resampling"}}],
  "output": {"kind": "raster", "format": "cog", "dtype": "float32"}
}}}
"@

$placed = Invoke-Http -Method Post -Uri "$BaseUrl/processing/processes/recipe/execution" -Body $order
if ($placed.Status -ne 201) {
    Stop-Here "Auftrag senden: erwartet 201, bekommen $($placed.Status) - $(Get-ProblemText $placed)"
}
$job = ConvertFrom-JsonSafe $placed.Content
if ($null -eq $job -or -not $job.jobID) { Stop-Here 'Auftrag senden: 201, aber keine jobID im Rumpf' }
$jobId = [string]$job.jobID
[void]$JobsToDismiss.Add($jobId)
$location = Get-HeaderValue $placed.Headers 'Location'
if ($location -eq "/processing/jobs/$jobId") {
    Write-Result $true "Auftrag gesendet: 201, Location zeigt auf den Job ($($job.status))"
} else {
    Write-Result $false "Auftrag gesendet, aber Location ist '$location' statt '/processing/jobs/<jobID>'"
}
if ($job.status -eq 'successful') {
    Write-Info 'Der Auftrag war schon fertig: ein Treffer aus einem früheren Lauf (Cache, 7 Tage).'
}
if ($job.skippedItems -and @($job.skippedItems).Count -gt 0) {
    Write-Info "Ausgelassene Items (die Fläche berührt sie nicht): $(@($job.skippedItems) -join ', ')"
}

# ---- 2. wait for the end ------------------------------------------------------------------------
Write-Step '2. Status abfragen'

$statusUrl = "$BaseUrl/processing/jobs/$jobId"
$deadline  = (Get-Date).AddSeconds($TimeoutSeconds)
$state     = $job
$last      = ''
while ($true) {
    $now = "$($state.status) $($state.progress)%"
    if ($now -ne $last) {
        Write-Info "Stand: $now"
        $last = $now
    }
    if ($state.status -eq 'successful' -or $state.status -eq 'failed' -or $state.status -eq 'dismissed') { break }
    if ((Get-Date) -gt $deadline) { break }
    Start-Sleep -Seconds $PollSeconds
    $poll = Invoke-Http -Uri $statusUrl
    if ($poll.Status -ne 200) {
        Write-Result $false "Status abfragen: HTTP $($poll.Status) $(Get-ProblemText $poll)"
        break
    }
    $state = ConvertFrom-JsonSafe $poll.Content
}
$finished = $false
if ($state.status -eq 'successful') {
    Write-Result $true 'Job ist successful'
    $finished = $true
} elseif ($state.status -eq 'failed') {
    $why = Invoke-Http -Uri "$statusUrl/results"
    Write-Result $false "Job ist failed: $(Get-ProblemText $why)"
} else {
    Write-Result $false "Job nicht fertig nach $TimeoutSeconds s (Stand: $($state.status) $($state.progress)%). Läuft der Dienst worker (docker compose ps)?"
}

# ---- 3. results ---------------------------------------------------------------------------------
Write-Step '3. Ergebnisse holen'

if (-not $finished) {
    Write-Result $false 'Ergebnisse holen: übersprungen, der Job ist nicht successful'
} else {
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
    $results = Invoke-Http -Uri "$statusUrl/results"
    $document = ConvertFrom-JsonSafe $results.Content
    if ($results.Status -ne 200 -or $null -eq $document) {
        Write-Result $false "Ergebnisdokument: HTTP $($results.Status) $(Get-ProblemText $results)"
    } else {
        Write-Result $true 'Ergebnisdokument: 200 mit result, mask und recipe'
        foreach ($name in @('result', 'mask', 'recipe')) {
            $entry = $document.$name
            if ($null -eq $entry -or -not $entry.href) {
                Write-Result $false "Ergebnis '$name': kein Link im Dokument"
                continue
            }
            $file = Split-Path -Leaf ([string]$entry.href)
            $target = Join-Path $OutputDir $file
            if ($name -eq 'recipe') {
                $link = Invoke-Http -Uri "$BaseUrl$($entry.href)" -OutFile $target
                if ($link.Status -ne 200) {
                    Write-Result $false "recipe.json: erwartet 200, bekommen $($link.Status) $(Get-ProblemText $link)"
                    continue
                }
                $text = [System.IO.File]::ReadAllText($target, (New-Object System.Text.UTF8Encoding($false)))
                $recipe = ConvertFrom-JsonSafe $text
                if ($null -ne $recipe -and $recipe.recipe_id -eq $job.recipeID -and $text -notmatch 'c1:[0-9a-f]{16}') {
                    Write-Result $true "recipe.json gespeichert: $target (eigene recipe_id, kein Hash)"
                } else {
                    Write-Result $false 'recipe.json gespeichert, aber recipe_id passt nicht zum Job oder ein Hash steht darin'
                }
                continue
            }
            $link = Invoke-Http -Uri "$BaseUrl$($entry.href)" -NoRedirect
            if ($link.Status -ne 303) {
                Write-Result $false "${file}: erwartet 303, bekommen $($link.Status) $(Get-ProblemText $link)"
                continue
            }
            $signed  = Get-HeaderValue $link.Headers 'Location'
            $noStore = Get-HeaderValue $link.Headers 'Cache-Control'
            if (-not $signed -or $noStore -notmatch 'no-store') {
                Write-Result $false "${file}: 303 ohne Location oder ohne Cache-Control: no-store"
                continue
            }
            $download = Invoke-Http -Uri $signed -OutFile $target
            if ($download.Status -ne 200 -and $download.Status -ne 0) {
                Write-Result $false "${file}: Download von der signierten URL: HTTP $($download.Status)"
            } elseif ($download.Status -eq 0) {
                Write-Result $false "${file}: Download von der signierten URL nicht erreichbar: $($download.Error)"
            } elseif (Test-TiffFile $target) {
                $size = (Get-Item -LiteralPath $target).Length
                Write-Result $true "${file}: 303, no-store, $size Bytes gespeichert: $target"
            } else {
                Write-Result $false "${file}: heruntergeladen, aber keine TIFF-Datei: $target"
            }
        }
    }
}

# ---- 4. the same order again: a cache hit -------------------------------------------------------
Write-Step '4. Denselben Auftrag erneut senden (Cache-Treffer)'

$again = Invoke-Http -Method Post -Uri "$BaseUrl/processing/processes/recipe/execution" -Body $order
if ($again.Status -ne 201) {
    Write-Result $false "Zweiter Auftrag: erwartet 201, bekommen $($again.Status) - $(Get-ProblemText $again)"
} else {
    $second = ConvertFrom-JsonSafe $again.Content
    $secondId = [string]$second.jobID
    [void]$JobsToDismiss.Add($secondId)
    if ($secondId -eq $jobId) {
        Write-Result $false 'Zweiter Auftrag: dieselbe jobID wie der erste (jeder Auftrag bekommt eine eigene)'
    } elseif ($second.status -eq 'successful') {
        Write-Result $true 'Zweiter Auftrag: sofort successful, kein neuer Lauf (Cache-Treffer), eigene jobID'
    } else {
        Write-Result $false "Zweiter Auftrag: Stand '$($second.status)' statt successful - kein Cache-Treffer, ein neuer Lauf wurde angelegt"
        Write-Info 'Mögliche Gründe:'
        if (-not $finished) {
            Write-Info '- der erste Job ist nicht successful, es gibt nichts, was als Treffer dienen könnte'
        }
        if ($Dataset -eq 'cop-dem-glo-30') {
            Write-Info '- die Quelle gab keine Fassung der Eingabe (der DEM braucht einen ETag auf einen HEAD-Abruf): ohne Fassung kein Treffer'
        } else {
            Write-Info '- die Quelle gab keine Fassung der Eingabe (Prüfsumme file:checksum am Asset oder updated am Item): ohne Fassung kein Treffer'
        }
        Write-Info '- das Ergebnis hat weniger als 24 Stunden Restlaufzeit'
        Write-Info '- die Quelle hat sich zwischen den Aufträgen geändert (neue Fassung)'
        Write-Info '- Einzelheiten: docker compose logs api (Zeile "order accepted", Feld order_cacheable)'
    }
}

# ---- 5. dismiss ---------------------------------------------------------------------------------
Write-Step '5. DELETE und Status dismissed'

$number = 0
foreach ($id in $JobsToDismiss) {
    $number++
    $deleted = Invoke-Http -Method Delete -Uri "$BaseUrl/processing/jobs/$id"
    $body = ConvertFrom-JsonSafe $deleted.Content
    if ($deleted.Status -eq 200 -and $null -ne $body -and $body.status -eq 'dismissed') {
        Write-Result $true "Job $number : DELETE 200, Status dismissed"
    } else {
        Write-Result $false "Job $number : DELETE erwartet 200/dismissed, bekommen $($deleted.Status) $(Get-ProblemText $deleted)"
        continue
    }
    $after = Invoke-Http -Uri "$BaseUrl/processing/jobs/$id"
    if ($after.Status -eq 404) {
        Write-Result $true "Job $number : danach 404 (ein verworfener Job ist nicht mehr zu sehen)"
    } else {
        Write-Result $false "Job $number : nach DELETE erwartet 404, bekommen $($after.Status)"
    }
}

# ---- 6. the log must not name a job -------------------------------------------------------------
Write-Step '6. docker compose logs api nach der jobID durchsuchen'

if ($null -eq (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Result $false 'Log prüfen: docker nicht gefunden, die jobID konnte nicht gesucht werden'
} else {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'      # docker writes progress to stderr; 5.1 would turn that into an error
    $log = (& docker compose -f $ComposeFile logs --no-color api 2>&1 | Out-String)
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previous
    if ($code -ne 0 -or [string]::IsNullOrWhiteSpace($log)) {
        Write-Result $false "Log prüfen: docker compose logs api lieferte nichts (Exit-Code $code)"
    } else {
        $hits = 0
        foreach ($id in $JobsToDismiss) {
            if ($log.Contains($id)) { $hits++ }
        }
        $hash = [regex]::IsMatch($log, 'c1:[0-9a-f]{16}')
        if ($hits -gt 0) {
            Write-Result $false "Log: $hits der $($JobsToDismiss.Count) jobIDs stehen im Log von api"
        } else {
            Write-Result $true "Log: keine der $($JobsToDismiss.Count) jobIDs steht im Log von api"
        }
        if ($hash) {
            Write-Result $false 'Log: ein Rezept-Hash (c1:...) steht im Log von api'
        } else {
            Write-Result $true 'Log: kein Rezept-Hash im Log von api'
        }
        if ($log.Contains('/processing/jobs/{jobID}')) {
            Write-Result $true 'Log: die Zugriffszeilen tragen den Platzhalter {jobID} (die Suche war nicht leer)'
        } else {
            Write-Result $false 'Log: keine Zugriffszeile mit {jobID} gefunden - die Suche beweist nichts (läuft api mit dem Stand von M4-08b?)'
        }
    }
}

Show-Summary
if ($script:Failed -gt 0) { exit 1 }
exit 0
