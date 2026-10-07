<#
.SYNOPSIS
    Plays one small real job through the job API of a locally running platform (M4-08b).

.DESCRIPTION
    Windows PowerShell 5.1, no extra modules (Invoke-WebRequest only). Run it from the repository
    root while `docker compose up` is running:

        powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\try-job.ps1

    Needs the Copernicus DEM in the local catalog (README: "Den dritten Datensatz laden"):

        docker compose run --rm materialize cop-dem-glo-30

    Steps, each printed as OK or FEHLER:
      1. send an order (reproject on cop-dem-glo-30), expect 201 and a Location
      2. poll the status until successful or failed
      3. fetch the results, follow the 303, save result.tif, mask.tif and recipe.json
      4. send the same order again: expect a cache hit (successful at once, no new run)
      5. DELETE both jobs, expect "dismissed"
      6. search `docker compose logs api` for the job IDs: any hit is a FEHLER

    The area below is a synthetic square, not anybody's site. It goes to the platform in the order
    only; the script never prints it.
#>

# ---- what to try (change here) ------------------------------------------------------------------
$BaseUrl        = 'http://localhost:8000'
$Dataset        = 'cop-dem-glo-30'
$Asset          = 'data'
# A small square in decimal degrees (synthetic): about 1 km on a side, inside one 1x1 degree tile.
$AoiWest        = 9.50
$AoiSouth       = 47.50
$AoiEast        = 9.51
$AoiNorth       = 47.51
# The reproject step: target CRS, pixel size in the units of that CRS (metres for EPSG:3035).
$TargetCrs      = 'EPSG:3035'
$Resolution     = 90.0
$Resampling     = 'bilinear'          # nearest | bilinear | cubic
$TimeoutSeconds = 300                 # how long to wait for the job
$PollSeconds    = 3
$OutputDir      = '.\try-job-output'
$ComposeFile    = $null              # default: docker-compose.yml next to the scripts folder
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

function Invoke-Http {
    # One request; never throws. Status 0 means the platform could not be reached at all.
    param(
        [string]$Method = 'GET',
        [string]$Uri,
        [string]$Body,
        [string]$OutFile,
        [switch]$NoRedirect
    )
    $request = @{ Uri = $Uri; Method = $Method; UseBasicParsing = $true; TimeoutSec = 120 }
    if ($Body) {
        $request.Body        = $Body
        $request.ContentType = 'application/json; charset=utf-8'
    }
    if ($NoRedirect) { $request.MaximumRedirection = 0 }
    if ($OutFile)    { $request.OutFile = $OutFile; $request.PassThru = $true }    # without it nothing is returned
    try {
        $response = Invoke-WebRequest @request
        return [pscustomobject]@{ Status = [int]$response.StatusCode; Headers = $response.Headers; Content = $response.Content; Error = $null }
    } catch {
        $caught  = $_
        $failure = $caught.Exception.Response
        if ($null -eq $failure) {
            return [pscustomobject]@{ Status = 0; Headers = $null; Content = ''; Error = $caught.Exception.Message }
        }
        $text = ''
        try {
            $reader = New-Object System.IO.StreamReader($failure.GetResponseStream())
            $text = $reader.ReadToEnd()
            $reader.Close()
        } catch { }
        if (-not $text -and $null -ne $caught.ErrorDetails) { $text = [string]$caught.ErrorDetails.Message }
        return [pscustomobject]@{ Status = [int]$failure.StatusCode; Headers = $failure.Headers; Content = $text; Error = $null }
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

$west  = Format-Number $AoiWest
$south = Format-Number $AoiSouth
$east  = Format-Number $AoiEast
$north = Format-Number $AoiNorth
$bbox  = "$west,$south,$east,$north"

$found = Invoke-Http -Uri "$BaseUrl/stac/collections/$Dataset/items?limit=1&bbox=$bbox"
if ($found.Status -ne 200) {
    Stop-Here "Item suchen: HTTP $($found.Status) $($found.Error) - läuft die Plattform (docker compose up)?"
}
$collection = ConvertFrom-JsonSafe $found.Content
if ($null -eq $collection -or @($collection.features).Count -lt 1) {
    Write-Info "Der Katalog kennt keine Items für $Dataset in diesem Bereich."
    Write-Info "Einmalig laden: docker compose run --rm materialize $Dataset"
    Stop-Here 'Item suchen: kein Item gefunden'
}
$itemId = [string]$collection.features[0].id
Write-Result $true "Item gefunden: $itemId"

$order = @"
{"inputs": {"recipe": {
  "recipe_version": 1,
  "inputs": [{"name": "dem", "dataset": "$Dataset", "groups": [["$itemId"]], "assets": ["$Asset"]}],
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
        Write-Info '- die Quelle gab keine Fassung der Eingabe (der DEM braucht einen ETag auf einen HEAD-Abruf): ohne Fassung kein Treffer'
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
