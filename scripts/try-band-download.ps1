<#
.SYNOPSIS
    Plays one small band download (crop) through a locally running platform and checks the ZIP (NM4-75).

.DESCRIPTION
    Windows PowerShell 5.1, no extra modules. Run it from the repository root while `docker compose up`
    is running:

        powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\try-band-download.ps1 -Form multi_band -CommonResolution 20

    Steps, each printed as OK or FEHLER:
      1. find one item for the area (the search of the viewer: POST /stac/search)
      2. POST /collections/{dataset}/download with the bands, the form and the area; save the ZIP
      3. read the ZIP: the files lie in exports/, exports/BANDS.txt is there, and every raster file named in
         BANDS.txt is in the ZIP (and the other way round); every raster starts like a TIFF
      4. print exports/BANDS.txt

    The area is a synthetic square on open farmland inland, not anybody's site. It goes to the platform in the
    search and in the request body only; the script prints only its size.

.PARAMETER Form
    per_band (default), per_resolution or multi_band.

.PARAMETER CommonResolution
    Metres, only with -Form multi_band (for example 20).

.PARAMETER Assets
    Asset keys to download. Default: red, nir, rededge1, scl (10 m, 10 m, 20 m and a 20 m classification layer).

.PARAMETER Bbox
    West, south, east, north with a decimal point, in quotes. At most 2 x 2 km.

.PARAMETER Datetime
    Period to search, 2025-07-01/2025-07-31 by default.

.PARAMETER BaseUrl
    Where the platform's api runs. Default http://localhost:8000.

.EXAMPLE
    .\scripts\try-band-download.ps1
    One file per band.

.EXAMPLE
    .\scripts\try-band-download.ps1 -Form per_resolution
    One multi-band file per resolution (bands_10m.tif and bands_20m.tif).
#>
[CmdletBinding()]
param(
    [string]$Dataset = 'sentinel-2-c1-l2a',
    [ValidateSet('per_band', 'per_resolution', 'multi_band')][string]$Form = 'per_band',
    [double]$CommonResolution,
    [string[]]$Assets = @('red', 'nir', 'rededge1', 'scl'),
    [string]$Bbox = '10.50,49.50,10.51,49.51',
    [string]$Datetime = '2025-07-01/2025-07-31',
    [string]$BaseUrl = 'http://localhost:8000',
    [string]$OutputDir = '.\try-band-download-output'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'
$Invariant             = [System.Globalization.CultureInfo]::InvariantCulture
$failed                = 0
$BaseUrl               = $BaseUrl.TrimEnd('/')

function Write-Result {
    param([bool]$Good, [string]$Text)
    if ($Good) { Write-Host "[OK    ] $Text" -ForegroundColor Green }
    else { $script:failed++; Write-Host "[FEHLER] $Text" -ForegroundColor Red }
}

function Read-Answer {
    # One request; never throws. Returns Status (0: no answer), Text, and the file when -OutFile is given.
    param([string]$Uri, [string]$Body, [string]$OutFile)
    $request = @{ Uri = $Uri; Method = 'Post'; UseBasicParsing = $true; TimeoutSec = 300; ContentType = 'application/json; charset=utf-8'; Body = $Body }
    if ($OutFile) { $request.OutFile = $OutFile; $request.PassThru = $true }
    try {
        $response = Invoke-WebRequest @request
        $text = ''
        if (-not $OutFile) {
            $stream = $response.RawContentStream
            $text = [System.Text.Encoding]::UTF8.GetString($stream.ToArray()).TrimStart([char]0xFEFF)
        }
        return [pscustomobject]@{ Status = [int]$response.StatusCode; Text = $text }
    } catch {
        $failure = $_.Exception.Response
        if ($null -eq $failure) { return [pscustomobject]@{ Status = 0; Text = $_.Exception.Message } }
        $text = ''
        try {
            $reader = New-Object System.IO.StreamReader($failure.GetResponseStream(), [System.Text.Encoding]::UTF8)
            $text = $reader.ReadToEnd()
            $reader.Close()
        } catch { }
        return [pscustomobject]@{ Status = [int]$failure.StatusCode; Text = $text }
    }
}

function ConvertTo-Number {
    param([string]$Text)
    return [double]::Parse($Text.Trim(), [System.Globalization.NumberStyles]::Float, $Invariant)
}

# ---- inputs, checked before anything is sent ------------------------------------------------------
if (($Form -eq 'multi_band') -and ($CommonResolution -le 0)) {
    Write-Result $false '-CommonResolution (Meter) wird bei -Form multi_band gebraucht'
    exit 1
}
if (($Form -ne 'multi_band') -and ($CommonResolution -gt 0)) {
    Write-Result $false '-CommonResolution gehört nur zu -Form multi_band'
    exit 1
}
$numbers = @($Bbox -split '[,;\s]+' | Where-Object { $_ } | ForEach-Object { ConvertTo-Number $_ })
if ($numbers.Count -ne 4) { Write-Result $false '-Bbox: genau vier Zahlen "West,Süd,Ost,Nord" erwartet'; exit 1 }
$widthKm  = ($numbers[2] - $numbers[0]) * 111.32 * [math]::Cos((($numbers[1] + $numbers[3]) / 2) * [math]::PI / 180)
$heightKm = ($numbers[3] - $numbers[1]) * 111.32
if ($widthKm -le 0 -or $heightKm -le 0 -or $widthKm -gt 2 -or $heightKm -gt 2) {
    Write-Result $false '-Bbox: West < Ost, Süd < Nord, höchstens 2 x 2 km'
    exit 1
}
$west = $numbers[0].ToString('0.0###############', $Invariant); $south = $numbers[1].ToString('0.0###############', $Invariant)
$east = $numbers[2].ToString('0.0###############', $Invariant); $north = $numbers[3].ToString('0.0###############', $Invariant)
Write-Host ("Gebiet: {0} x {1} km, Form {2}" -f $widthKm.ToString('0.0', $Invariant), $heightKm.ToString('0.0', $Invariant), $Form) -ForegroundColor Cyan

# ---- 1. find one item -----------------------------------------------------------------------------
$parts = $Datetime.Split('/')
if ($parts.Count -ne 2) { Write-Result $false '-Datetime: "Start/Ende" als Datum erwartet'; exit 1 }
$search = '{"collections": ["' + $Dataset + '"], "bbox": [' + "$west,$south,$east,$north" + '], "datetime": "' + $parts[0] + 'T00:00:00Z/' + $parts[1] + 'T23:59:59Z", "limit": 1}'
$found = Read-Answer -Uri "$BaseUrl/stac/search" -Body $search
if ($found.Status -ne 200) { Write-Result $false "Item suchen: HTTP $($found.Status) - läuft die Plattform (docker compose up)?"; exit 1 }
$items = @((ConvertFrom-Json $found.Text).features)
if ($items.Count -lt 1) { Write-Result $false 'Item suchen: für Gebiet und Zeitraum gibt es keine Szene'; exit 1 }
$itemId = [string]$items[0].id
Write-Result $true 'Item gefunden (die Kennung wird nicht ausgegeben)'

# ---- 2. download ----------------------------------------------------------------------------------
$assetList = ($Assets | ForEach-Object { '"' + $_ + '"' }) -join ', '
$aoi = '{"type": "Polygon", "coordinates": [[[' + "$west, $south], [$east, $south], [$east, $north], [$west, $north], [$west, $south" + ']]]}'
$body = '{"groups": [["' + $itemId + '"]], "assets": [' + $assetList + '], "aoi": ' + $aoi + ', "form": "' + $Form + '"'
if ($Form -eq 'multi_band') { $body += ', "common_resolution": ' + $CommonResolution.ToString($Invariant) }
$body += '}'
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$zipPath = Join-Path (Resolve-Path $OutputDir).Path "$Dataset-$Form.zip"
$answer = Read-Answer -Uri "$BaseUrl/collections/$Dataset/download" -Body $body -OutFile $zipPath
if ($answer.Status -ne 200) {
    $detail = ''
    if ($answer.Text) { $detail = " - $($answer.Text)" }
    Write-Result $false "Download: HTTP $($answer.Status)$detail"
    exit 1
}
Write-Result $true ("Download: {0} KB gespeichert unter {1}" -f [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1024), $zipPath)

# ---- 3. read the ZIP ------------------------------------------------------------------------------
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $names = @($zip.Entries | ForEach-Object { $_.FullName })
    $rasters = @($names | Where-Object { $_ -like 'exports/*.tif' -and $_ -notlike '*_mask.tif' })
    Write-Result ($rasters.Count -gt 0) "exports/ enthält $($rasters.Count) Datendatei(en): $($rasters -join ', ')"
    Write-Result ($names -contains 'exports/BANDS.txt') 'exports/BANDS.txt ist da'
    Write-Result (($names -contains 'ATTRIBUTION.txt') -and ($names -contains 'aoi.geojson')) 'ATTRIBUTION.txt und aoi.geojson sind da'
    $outside = @($names | Where-Object { $_ -like '*.tif' -and $_ -notlike 'exports/*' })
    Write-Result ($outside.Count -eq 0) 'keine Rasterdatei außerhalb von exports/'

    $bands = $zip.GetEntry('exports/BANDS.txt')
    $text = ''
    if ($null -ne $bands) {
        $reader = New-Object System.IO.StreamReader($bands.Open(), [System.Text.Encoding]::UTF8)
        $text = $reader.ReadToEnd()
        $reader.Close()
    }
    $listed = @($text -split "`n" | Where-Object { $_ -like 'File: *' } | ForEach-Object { $_.Substring(6).Trim() })
    $missing = @($listed | Where-Object { $names -notcontains $_ })
    $unlisted = @($rasters | Where-Object { $listed -notcontains $_ })
    Write-Result (($missing.Count -eq 0) -and ($unlisted.Count -eq 0)) "BANDS.txt nennt genau die Dateien des ZIP ($($listed.Count))"

    foreach ($name in $rasters) {
        $stream = $zip.GetEntry($name).Open()
        $head = New-Object byte[] 4
        [void]$stream.Read($head, 0, 4)
        $stream.Close()
        $tiff = (($head[0] -eq 0x49) -and ($head[1] -eq 0x49) -and ($head[2] -eq 0x2A) -and ($head[3] -eq 0)) -or (($head[0] -eq 0x4D) -and ($head[1] -eq 0x4D) -and ($head[2] -eq 0) -and ($head[3] -eq 0x2A))
        Write-Result $tiff "$name beginnt wie ein TIFF"
    }
} finally {
    $zip.Dispose()
}

# ---- 4. BANDS.txt ---------------------------------------------------------------------------------
Write-Host ''
Write-Host '---- exports/BANDS.txt ----' -ForegroundColor Cyan
Write-Host $text
if ($failed -gt 0) { Write-Host "$failed FEHLER" -ForegroundColor Red; exit 1 }
Write-Host 'Alles OK' -ForegroundColor Green
