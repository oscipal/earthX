<#
.SYNOPSIS
    Reports one harvested source and commits its approval file on a branch of its own (M5-20).

.DESCRIPTION
    Windows PowerShell 5.1, no extra modules. Run it from the repository root while `docker compose up -d` is running
    and after `docker compose run --rm harvest <source>`:

        powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\harvest-report.ps1 -Source govdata
        powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\harvest-report.ps1 -Source govdata -Classify

    With -Classify it only shows what the rule on geodata, the directory of places and the licence rules make of the
    source, with the samples for the release of the rule; nothing is written, no branch is made.

    Without it:
      1. checks that the checkout is clean and on main;
      2. makes the branch harvest/<day>-<source>;
      3. runs the report (`docker compose run --rm harvest-report <source>`), which writes the approval file and its
         report into backend/catalog/approvals/;
      4. commits both; where the report formed no new stack, it goes back to main and deletes the branch.

    It never pushes. Push the branch and open the draft PR with your own access (adr/0025 section 6.5, P1).

.PARAMETER Source
    The id of a source under backend/catalog/sources/.

.PARAMETER Classify
    Show the classification only (`--classify`); write nothing.
#>
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-z][a-z0-9-]{1,62}$')][string]$Source,
    [switch]$Classify
)

$ErrorActionPreference = 'Stop'

# On Linux (PowerShell 7) the report writes as the user who owns the checkout, never as root, so the approval file
# stays editable; Docker Desktop on Windows maps the files to the user anyway ($IsLinux is unset in PowerShell 5.1).
$asOwner = @()
if ($IsLinux) { $asOwner = @('--user', "$(id -u):$(id -g)") }

function Fail([string]$Message) {
    Write-Host "FEHLER: $Message"
    exit 1
}

if ($Classify) {
    docker compose run --build --rm @asOwner harvest-report $Source --classify
    exit $LASTEXITCODE
}

if (git status --porcelain) { Fail 'Der Checkout ist nicht sauber; erst committen oder aufraeumen.' }
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'main') { Fail "Der Checkout steht auf '$branch', nicht auf main." }

$day = Get-Date -Format 'yyyy-MM-dd'
$target = "harvest/$day-$Source"
git switch -c $target
if ($LASTEXITCODE -ne 0) { Fail "Der Branch $target laesst sich nicht anlegen." }

docker compose run --build --rm @asOwner harvest-report $Source
if ($LASTEXITCODE -ne 0) {
    git switch main
    git branch -D $target
    Fail 'Der Bericht ist gescheitert; der Branch ist geloescht.'
}

if (-not (git status --porcelain -- backend/catalog/approvals)) {
    git switch main
    git branch -D $target
    Write-Host 'OK: kein neuer Stapel, keine Freigabedatei; nichts zu committen.'
    exit 0
}

git add -- backend/catalog/approvals
git commit -m "Add the approval file of the harvest of $Source, $day"
if ($LASTEXITCODE -ne 0) { Fail 'Der Commit ist gescheitert.' }

Write-Host "OK: Branch $target mit Bericht und Freigabedatei."
Write-Host "Weiter mit deinem Zugang: git push -u origin $target"
Write-Host 'Dann den Draft-PR oeffnen, die Stichprobe in der .yaml abhaken, decision und decided_on setzen, mergen.'
