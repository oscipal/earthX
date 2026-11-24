<#
.SYNOPSIS
    One harvest run without a terminal: harvest, report, link check, approval by rules, one pull request, merge (M5-67).

.DESCRIPTION
    Windows PowerShell 5.1, no extra modules, no local Python: every step runs in `docker compose`. Started by a double
    click on the desktop shortcut "EarthX Harvest" (made once with -Install). Plan: docs/plans/m5/m5-67-harvest-automatisch.md;
    rules: docs/adr/0033-freigabe-gelisteter-eintraege.md section 8.5 (Otto, 2026-11-24).

    A run: checks git, gh, a clean checkout and Docker (starts Docker Desktop if needed); `docker compose up -d --build`;
    a branch harvest/<day>; per enabled source a harvest, then licence spellings and grants, the report with its
    classify excerpt, the link check, the approval by rules and the files of the run in docs/harvest/; commits, push,
    one pull request with gh; waits for the four required checks, merges with a merge commit, pulls and starts the
    platform again. The first run is a trial: it hides nothing and approves nothing.

    On an error nothing is merged, the branch stays, and the window says what happened in one line, with the line of the
    failing step that says why. Only exit codes decide what counts as an error: a harvest that paused on purpose (exit
    code 75, a budget of pages reached) is a success with a note in the report. Everything the run prints goes to
    ..\earthx-ausgaben\<day>_<time>\ next to the checkout, never into the repository; the repository gets only the
    cleaned files of the run.

    A second run on the same day takes a branch of its own (harvest/<day>-<time>). Draft pull requests of earlier failed
    runs (title "Harvest run ... (failed)", branch harvest/<day>...) are closed by the next run with a short comment, and
    their branches are deleted.

.PARAMETER Install
    Check git, gh (logged in), docker and .env, make ..\earthx-ausgaben\ and the desktop shortcut "EarthX Harvest".

.PARAMETER NoPause
    Do not wait for Enter at the end (for a run from a terminal).
#>
param(
    [switch]$Install,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$Repo = Split-Path -Parent $PSScriptRoot
$OutRoot = Join-Path (Split-Path -Parent $Repo) 'earthx-ausgaben'
$Dash = [char]0x2014
# The required checks of .github/workflows/ci.yml, by name (Otto, 24.11.2026: Backend, Frontend, Modulgrenzen,
# compose-topology).
$RequiredChecks = @(
    "Backend $Dash lint and tests",
    "Frontend $Dash lint, types and tests",
    'Module boundaries (import-linter)',
    'Compose topology'
)
$CheckMinutes = 90
$DockerMinutes = 5
# The exit code of `harvest` for a pause on purpose (EXIT_PAUSED in backend/earthx/discovery/harvest.py): a success.
$PauseCode = 75
$HarvestServices = @('harvest', 'harvest-report', 'harvest-grants', 'harvest-linkcheck', 'harvest-spellings', 'harvest-cycle')
$Utf8 = New-Object System.Text.UTF8Encoding $false

# On Linux (PowerShell 7) the containers write as the owner of the checkout; $IsLinux is unset in PowerShell 5.1.
$AsOwner = @()
if ($IsLinux) { $AsOwner = @('--user', "$(id -u):$(id -g)") }

$script:Log = $null
$script:LastOutput = @()

function Say([string]$Text) {
    Write-Host $Text
    if ($script:Log) { [System.IO.File]::AppendAllText($script:Log, $Text + "`n", $Utf8) }
}

# One item of the output of a native command as text. Windows PowerShell 5.1 hands a line of standard error over as an
# ErrorRecord, and an empty one prints as its type name: that is text for the log, never an error. Only exit codes
# decide whether a command failed.
function Text-Of($Item) {
    if ($Item -is [System.Management.Automation.ErrorRecord]) { $text = "$($Item.Exception.Message)" } else { $text = "$Item" }
    if ($text -eq 'System.Management.Automation.RemoteException') { return '' }
    return $text
}

# Run a native command with its output into the log of the run (or into $Capture), never into the repository.
# Returns the exit code; Windows PowerShell 5.1 turns stderr into errors under 'Stop', hence 'Continue' around it.
# Its output stays in $script:LastOutput, so that an error can name the line that says why (Reason).
function Native([string]$Label, [string[]]$Command, [string]$Capture = '') {
    $exe = $Command[0]
    $rest = @()
    if ($Command.Count -gt 1) { $rest = $Command[1..($Command.Count - 1)] }
    if ($script:Log) { [System.IO.File]::AppendAllText($script:Log, "== $Label`n", $Utf8) }
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = @(& $exe @rest 2>&1 | ForEach-Object { Text-Of $_ })
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    $script:LastOutput = $out
    if ($Capture) { [System.IO.File]::WriteAllLines($Capture, [string[]]$out, $Utf8) }
    if ($script:Log -and $out.Count) { [System.IO.File]::AppendAllText($script:Log, ($out -join "`n") + "`n", $Utf8) }
    return $code
}

# The standard output of a native command (gh, git, compose) as an array of its non-empty lines, $null on an error.
# Never unrolled: PowerShell turns a returned empty array into $null and a one-element array into its element, so the
# array goes back wrapped (return ,$out). Standard error stays out of the data and goes nowhere (2>$null).
function Lines([string[]]$Command) {
    $exe = $Command[0]
    $rest = @()
    if ($Command.Count -gt 1) { $rest = $Command[1..($Command.Count - 1)] }
    if ($script:Log) { [System.IO.File]::AppendAllText($script:Log, "== $($Command -join ' ')`n", $Utf8) }
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = @(& $exe @rest 2>$null | ForEach-Object { Text-Of $_ } | Where-Object { $_ -ne '' })
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) { return $null }
    return ,$out
}

# The line of the last native command that says why it failed, for the window, fehler.log and the pull request: the last
# line that names a failure, else the last line. Empty where the command printed nothing.
function Reason {
    $lines = @($script:LastOutput | ForEach-Object { "$_".Trim() } | Where-Object { $_ -ne '' })
    # The containers print their log as JSON lines; the line that says why is a plain one, if there is any.
    $plain = @($lines | Where-Object { -not $_.StartsWith('{') })
    if ($plain.Count) { $lines = $plain }
    if (-not $lines.Count) { return '' }
    $pick = $null
    foreach ($pattern in @('(?i)\bfailed\b|traceback|exception', '(?i)\b(error|fehler|denied|refused|fatal|invalid|cannot|unable)\b')) {
        $hit = @($lines | Where-Object { $_ -match $pattern })
        if ($hit.Count) { $pick = $hit[$hit.Count - 1]; break }
    }
    if ($null -eq $pick) { $pick = $lines[$lines.Count - 1] }
    if ($pick.Length -gt 240) { $pick = $pick.Substring(0, 240) }
    return " Grund: $pick"
}

function Compose([string]$Label, [string[]]$Arguments, [string]$Capture = '') {
    return Native $Label (@('docker', 'compose', '--progress', 'quiet') + $Arguments) $Capture
}

function Install {
    # Here a message for Otto, not a red NativeCommandError (Windows PowerShell 5.1 under 'Stop').
    $ErrorActionPreference = 'Continue'
    $missing = @()
    foreach ($tool in 'git', 'gh', 'docker') {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { $missing += $tool }
    }
    if ($missing.Count) {
        Write-Host "FEHLT: $($missing -join ', '). Einrichtung: docs/plans/m5/m5-67-harvest-automatisch.md, Abschnitt 11."
        return 1
    }
    & gh auth status *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'FEHLT: gh ist nicht angemeldet. Erst: gh auth login, dann gh auth setup-git.'
        return 1
    }
    if (-not (Test-Path (Join-Path $Repo '.env'))) {
        Write-Host 'FEHLT: .env im Checkout.'
        return 1
    }
    New-Item -ItemType Directory -Force -Path $OutRoot | Out-Null
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut((Join-Path $desktop 'EarthX Harvest.lnk'))
    $link.TargetPath = Join-Path $PSHOME 'powershell.exe'
    $link.Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '"'
    $link.WorkingDirectory = $Repo
    $link.Description = 'EarthX: ein Harvest-Lauf (M5-67)'
    $link.Save()
    Write-Host "OK: Verknuepfung 'EarthX Harvest' auf dem Desktop, Ausgaben in $OutRoot."
    return 0
}

function Start-Docker {
    if ((Native 'docker info' @('docker', 'info')) -eq 0) { return }
    $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path $desktop)) { throw 'Docker: Docker antwortet nicht, und Docker Desktop ist nicht installiert.' }
    Say 'Docker Desktop wird gestartet ...'
    Start-Process $desktop | Out-Null
    $until = (Get-Date).AddMinutes($DockerMinutes)
    while ((Get-Date) -lt $until) {
        Start-Sleep -Seconds 10
        if ((Native 'docker info' @('docker', 'info')) -eq 0) { return }
    }
    throw 'Docker: Docker antwortet nicht. Docker Desktop oeffnen und neu starten.'
}

# pass, fail or pending for the required checks of a pull request.
function Get-CheckState([string]$Number) {
    $json = Lines @('gh', 'pr', 'checks', $Number, '--json', 'name,bucket')
    if ($null -eq $json) { return 'pending' }
    $checks = ($json -join "`n") | ConvertFrom-Json
    $state = 'pass'
    foreach ($name in $RequiredChecks) {
        $found = @($checks | Where-Object { $_.name -eq $name })
        if (-not $found.Count) { $state = 'pending'; continue }
        foreach ($check in $found) {
            # Only a pass counts: a skipped required check has not shown anything (fail, cancel, skipping).
            if ($check.bucket -eq 'pending') { $state = 'pending' }
            elseif ($check.bucket -ne 'pass') { return 'fail' }
        }
    }
    return $state
}

function Commit([string]$Message, [string[]]$Paths) {
    Native "git add" (@('git', 'add', '--') + $Paths) | Out-Null
    $staged = Lines @('git', 'diff', '--cached', '--name-only')
    if ($staged -and $staged.Count) {
        if ((Native "git commit" @('git', 'commit', '-q', '-m', $Message)) -ne 0) { throw "Git: Commit gescheitert ($Message).$(Reason)" }
    }
}

# Draft pull requests of earlier failed runs (title "Harvest run ... (failed)", branch harvest/<day>[-...]) are closed with
# a short comment and their branches deleted: the next run replaces them (Otto, 24.11.2026). Nothing else is touched, and
# nothing here stops the run. Returns the numbers closed.
function Close-FailedRuns {
    $json = Lines @('gh', 'pr', 'list', '--state', 'open', '--draft', '--limit', '200', '--json', 'number,headRefName,title')
    if ($null -eq $json -or -not $json.Count) { return ,@() }
    $closed = @()
    # Assigned before it is looped over: Windows PowerShell 5.1 hands an array out of ConvertFrom-Json as one object.
    $parsed = ($json -join "`n") | ConvertFrom-Json
    foreach ($pr in $parsed) {
        if ($pr.headRefName -notmatch '^harvest/[0-9]{4}-[0-9]{2}-[0-9]{2}(-[0-9]+)*$') { continue }
        if ($pr.title -notmatch '^Harvest run .+ \(failed\)$') { continue }
        $comment = 'Geschlossen vom naechsten Harvest-Lauf: Dieser Lauf ist gescheitert, ein neuer ersetzt ihn. Der Branch wird geloescht.'
        if ((Native "close PR $($pr.number)" @('gh', 'pr', 'close', "$($pr.number)", '--comment', $comment, '--delete-branch')) -eq 0) {
            $closed += "$($pr.number)"
            if ((Native 'local branch?' @('git', 'rev-parse', '--verify', '--quiet', $pr.headRefName)) -eq 0) {
                Native 'delete local branch' @('git', 'branch', '-D', $pr.headRefName) | Out-Null
            }
        }
    }
    return ,$closed
}

# Whether a branch of this name exists here or on origin.
function Branch-Taken([string]$Name) {
    return ((Native 'branch?' @('git', 'rev-parse', '--verify', '--quiet', $Name)) -eq 0) -or
           ((Native 'remote branch?' @('git', 'ls-remote', '--exit-code', '--heads', 'origin', $Name)) -eq 0)
}

if ($Install) { exit (Install) }

$day = Get-Date -Format 'yyyy-MM-dd'
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
New-Item -ItemType Directory -Force -Path $OutRoot | Out-Null
$RunDir = Join-Path $OutRoot $stamp
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
$script:Log = Join-Path $RunDir 'protokoll.txt'
$Lock = Join-Path $OutRoot 'lauf.lock'
$Run = "${RunDir}:/run"

# The lock holds the process id of the run; made atomically (CreateNew), so two double clicks cannot both start. A
# lock whose process is gone (a window closed mid-run) is taken over.
function Take-Lock {
    try {
        $stream = [System.IO.File]::Open($Lock, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
        $bytes = $Utf8.GetBytes("$PID")
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Close()
        return $true
    } catch {
        return $false
    }
}
if (-not (Take-Lock)) {
    $other = "$(Get-Content -Path $Lock -ErrorAction SilentlyContinue)".Trim()
    $alive = ($other -match '^[0-9]+$') -and [bool](Get-Process -Id ([int]$other) -ErrorAction SilentlyContinue)
    if (-not $alive) {
        Remove-Item $Lock -ErrorAction SilentlyContinue
        $alive = -not (Take-Lock)
    }
    if ($alive) {
        Say 'Ein Lauf laeuft schon. Erst wenn sein Fenster zu ist, startet ein neuer.'
        if (-not $NoPause) { Read-Host 'Enter zum Schliessen' | Out-Null }
        exit 1
    }
}

# Keep the computer awake while the run lasts; the screen may go off.
$Power = $null
if ($env:OS -eq 'Windows_NT') {
    $Power = Add-Type -Name 'Power' -Namespace 'EarthX' -PassThru -MemberDefinition `
        '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
    [void]$Power::SetThreadExecutionState([uint32]2147483649)
}

$Branch = $null
$Label = $day
$Closed = @()
$Summary = $null
$SummaryDone = $false
$Message = ''
$ExitCode = 0
$Step = 'Start'
try {
    Set-Location $Repo

    $Step = 'Pruefen'
    foreach ($tool in 'git', 'gh', 'docker') {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Pruefen: $tool fehlt. Einrichtung im Plan M5-67, Abschnitt 11." }
    }
    if ((Native 'gh auth status' @('gh', 'auth', 'status')) -ne 0) { throw "Pruefen: gh ist nicht angemeldet (gh auth login).$(Reason)" }
    $dirty = Lines @('git', 'status', '--porcelain')
    if ($null -eq $dirty -or $dirty.Count) { throw 'Pruefen: Im Checkout sind ungesicherte Aenderungen. Erst committen oder verwerfen.' }
    if ((Native 'git switch main' @('git', 'switch', 'main')) -ne 0) { throw "Pruefen: main laesst sich nicht auschecken.$(Reason)" }
    if ((Native 'git pull' @('git', 'pull', '--ff-only')) -ne 0) { throw "Pruefen: main laesst sich nicht aktualisieren.$(Reason)" }

    $Step = 'Docker'
    Start-Docker
    if ((Compose 'compose up' @('up', '-d', '--build')) -ne 0) { throw "Docker: Die Plattform startet nicht (docker compose up).$(Reason)" }

    $Step = 'Aufraeumen'
    $Closed = Close-FailedRuns
    if ($Closed.Count) { Say "Gescheiterte Draft-PRs frueherer Laeufe geschlossen: $($Closed -join ', ')." }

    $Step = 'Branch'
    # The first run of a day is harvest/<day>; a second one (its branch may still stand, with a draft PR) takes the time.
    $Branch = "harvest/$day"
    if (Branch-Taken $Branch) {
        $Label = "$day " + (Get-Date -Format 'HH:mm')
        $Branch = "harvest/$day-" + (Get-Date -Format 'HHmm')
        $number = 2
        $base = $Branch
        while (Branch-Taken $Branch) {
            $Branch = "$base-$number"
            $number += 1
        }
    }
    if ((Native 'git switch -c' @('git', 'switch', '-c', $Branch)) -ne 0) { $Branch = $null; throw "Branch: laesst sich nicht anlegen.$(Reason)" }
    $Trial = -not (Get-ChildItem (Join-Path $Repo 'docs\harvest\laeufe') -Directory -ErrorAction SilentlyContinue)
    if ($Trial) { Say 'Probelauf (erster Lauf): nichts wird verborgen, nichts freigegeben.' }
    $Summary = @('run', '--rm') + $AsOwner + @('-v', $Run, 'harvest-cycle', 'summary', '--run', '/run', '--harvest', '/harvest', '--approvals', '/approvals', '--day', $day)
    if ($Trial) { $Summary += '--trial' }

    $Step = 'Ernten'
    if ((Compose 'build' (@('--profile', 'harvest', 'build') + $HarvestServices)) -ne 0) { throw "Ernten: Die Images lassen sich nicht bauen.$(Reason)" }
    $Sources = Lines @('docker', 'compose', '--progress', 'quiet', 'run', '--rm', 'harvest-cycle', 'sources')
    if ($null -eq $Sources -or -not $Sources.Count) { throw 'Ernten: keine freigegebene Quelle gefunden.' }
    $Harvested = @()
    foreach ($source in $Sources) {
        Say "Ernte $source ..."
        $code = Compose "harvest $source" @('run', '--rm', 'harvest', $source) (Join-Path $RunDir "harvest-$source.txt")
        if ($code -eq 0) {
            $Harvested += $source
        } elseif ($code -eq $PauseCode) {
            # A pause on purpose (a budget reached, the source asked for a rest) keeps its place: a success with a note in
            # the report, never a failure. The report goes on with what the source delivered so far.
            $Harvested += $source
            [System.IO.File]::AppendAllText((Join-Path $RunDir 'quellen-pause.txt'), "$source`n", $Utf8)
            Say "Hinweis: $source hat planmaessig pausiert, der naechste Lauf setzt fort."
        } else {
            [System.IO.File]::AppendAllText((Join-Path $RunDir 'quellen-fehler.txt'), "${source}: Der Harvest endete mit Fehler (Exit-Code $code).$(Reason)`n", $Utf8)
        }
    }

    $Step = 'Lizenzen'
    if ((Compose 'spellings' (@('run', '--rm') + $AsOwner + @('-v', $Run, 'harvest-spellings', '--json', '/run/spellings.json'))) -ne 0) { throw "Lizenzen: Schreibweisen gescheitert.$(Reason)" }
    if ((Compose 'grants' (@('run', '--rm') + $AsOwner + @('harvest-grants') + $Sources)) -ne 0) { throw "Lizenzen: Freigaben je Herausgeber gescheitert.$(Reason)" }
    if ((Compose 'rebuild' (@('--profile', 'harvest', 'build') + $HarvestServices)) -ne 0) { throw "Lizenzen: Die Images lassen sich nicht neu bauen.$(Reason)" }

    $Step = 'Bericht'
    foreach ($source in $Harvested) {
        Say "Bericht $source ..."
        $code = Compose "report $source" (@('run', '--rm') + $AsOwner + @('-v', $Run, 'harvest-report', $source, '--json', "/run/report-$source.json"))
        if ($code -ne 0) { throw "Bericht: Der Bericht von $source ist gescheitert.$(Reason)" }
        Compose "classify $source" (@('run', '--rm') + $AsOwner + @('harvest-report', $source, '--classify')) (Join-Path $RunDir "classify-$source.txt") | Out-Null
    }

    $Step = 'Linkpruefung'
    Say 'Linkpruefung ...'
    $check = @('run', '--rm') + $AsOwner + @('-v', $Run, 'harvest-linkcheck', '--json', '/run/linkcheck.json')
    if ($Trial) { $check += '--dry-run' }
    if ((Compose 'linkcheck' $check) -ne 0) {
        # Plan section 10: the run goes on; nothing is hidden and nothing new passes, the finding says why.
        [System.IO.File]::WriteAllText((Join-Path $RunDir 'linkpruefung-fehler.txt'), 'Die Linkpruefung ist gescheitert (protokoll.txt).', $Utf8)
    }

    $Step = 'Freigabe'
    $new = Lines @('git', 'status', '--porcelain', '--', 'backend/catalog/approvals')
    if ($null -eq $new) { throw 'Freigabe: git status gescheitert.' }
    $files = @($new | ForEach-Object { $_.Substring(3) } | Where-Object { $_ -like '*.yaml' } | ForEach-Object { Split-Path -Leaf $_ })
    $decide = @('run', '--rm') + $AsOwner + @('-v', $Run, 'harvest-cycle', 'decide', '--run', '/run', '--approvals', '/approvals', '--day', $day)
    if ($Trial) { $decide += '--trial' }
    if ((Compose 'decide' ($decide + $files)) -ne 0) { throw "Freigabe: Die Freigabe nach Regeln ist gescheitert.$(Reason)" }

    $Step = 'Laufdateien'
    $prs = Lines @('gh', 'pr', 'list', '--state', 'open', '--search', 'head:harvest/', '--json', 'number', '--jq', '.[].number')
    if ($prs) { [System.IO.File]::WriteAllLines((Join-Path $RunDir 'offene-prs.txt'), [string[]]$prs, $Utf8) }
    $SummaryDone = $true
    if ((Compose 'summary' $Summary) -ne 0) { throw "Laufdateien: Die Laufdateien lassen sich nicht schreiben.$(Reason)" }

    $Step = 'Git'
    Commit "Grant licences to new publishers and add licence spellings, harvest run $day" @('backend/catalog/licenses')
    Commit "Add the approval files of the harvest run $day" @('backend/catalog/approvals')
    Commit "Add the files of the harvest run $day and update the harvest findings" @('docs/harvest')
    $ahead = Lines @('git', 'rev-list', '--count', "main..$Branch")
    if ($null -eq $ahead -or $ahead.Count -ne 1) { throw 'Git: Zahl der Commits nicht lesbar.' }
    if ([int]$ahead[0] -eq 0) {
        Native 'back to main' @('git', 'switch', 'main') | Out-Null
        Native 'delete branch' @('git', 'branch', '-D', $Branch) | Out-Null
        $Branch = $null
        $Message = 'FERTIG: nichts Neues, kein PR.'
    } else {
        if ((Native 'push' @('git', 'push', '-u', 'origin', $Branch)) -ne 0) { throw "Git: Push gescheitert, Branch $Branch liegt lokal.$(Reason)" }
        $Step = 'PR'
        $title = "Harvest run $Label"
        if ($Trial) { $title = "Harvest run $Label (trial)" }
        if ((Native 'pr create' @('gh', 'pr', 'create', '--base', 'main', '--head', $Branch, '--title', $title, '--body-file', (Join-Path $RunDir 'pr-body.md'))) -ne 0) {
            throw "PR: gh pr create gescheitert. Branch $Branch ist gepusht.$(Reason)"
        }
        $view = Lines @('gh', 'pr', 'view', $Branch, '--json', 'number', '--jq', '.number')
        if ($null -eq $view -or $view.Count -ne 1 -or $view[0] -notmatch '^[0-9]+$') { throw "PR: Nummer des PR nicht lesbar. Branch $Branch ist gepusht." }
        $Pr = $view[0]

        $Step = 'Checks'
        Say "PR $Pr offen, warte auf die Pflicht-Checks (hoechstens $CheckMinutes min) ..."
        $until = (Get-Date).AddMinutes($CheckMinutes)
        $state = 'pending'
        while ($state -eq 'pending' -and (Get-Date) -lt $until) {
            Start-Sleep -Seconds 30
            $state = Get-CheckState $Pr
        }
        if ($state -ne 'pass') { throw "Checks: nicht gruen ($state). PR $Pr bleibt offen, nichts gemergt." }

        $Step = 'Merge'
        if ((Native 'merge' @('gh', 'pr', 'merge', $Pr, '--merge', '--delete-branch')) -ne 0) {
            throw "Merge: abgelehnt (Branch-Schutz?). PR $Pr bleibt offen.$(Reason)"
        }
        $Branch = $null
        Native 'switch main' @('git', 'switch', 'main') | Out-Null
        if ((Native 'pull' @('git', 'pull', '--ff-only')) -ne 0) { throw "Merge: gemergt, aber main laesst sich nicht aktualisieren.$(Reason)" }
        if ((Compose 'compose up' @('up', '-d', '--build')) -ne 0) { throw "Merge: gemergt, aber die Plattform startet nicht.$(Reason)" }
        $result = [System.IO.File]::ReadAllText((Join-Path $RunDir 'ergebnis.txt'), $Utf8).Trim()
        $Message = "FERTIG: PR $Pr gemergt. $result"
    }
} catch {
    $ExitCode = 1
    $text = "$($_.Exception.Message)".Trim()
    # An error that is no `throw` of this script (no message, or only the type name of standard error): say where.
    if (-not $text -or $text -eq 'System.Management.Automation.RemoteException') {
        $text = "unerwarteter Fehler in Zeile $($_.InvocationInfo.ScriptLineNumber)"
    }
    if ($text -notmatch '^[A-Za-z]+:') { $text = "${Step}: $text" }
    $Message = "FEHLER in $text Details: $RunDir"
    [System.IO.File]::WriteAllText((Join-Path $RunDir 'lauf-fehler.txt'), $text, $Utf8)
    # F10 = 1: on the branch, the files of the run with the error go into a draft PR; nothing is merged.
    if ($Branch -and $Step -notin @('Checks', 'Merge', 'PR')) {
        try {
            # The files of the run once: a second summary would write a second folder and the findings twice.
            if ($Summary -and -not $SummaryDone) { Compose 'summary after error' $Summary | Out-Null }
            Commit "Add the files of the failed harvest run $day" @('docs/harvest', 'backend/catalog/approvals', 'backend/catalog/licenses')
            $draft = 1
            if ((Native 'push' @('git', 'push', '-u', 'origin', $Branch)) -eq 0) {
                $draft = Native 'draft pr' @('gh', 'pr', 'create', '--draft', '--base', 'main', '--head', $Branch, '--title', "Harvest run $Label (failed)", '--body-file', (Join-Path $RunDir 'pr-body.md'))
            }
            if ($draft -eq 0) { $Message += " Branch $Branch mit Draft-PR." } else { $Message += " Branch $Branch liegt ohne PR da." }
        } catch {
            $Message += " Branch $Branch liegt lokal."
        }
    }
} finally {
    Remove-Item $Lock -ErrorAction SilentlyContinue
    if ($Power) { [void]$Power::SetThreadExecutionState([uint32]2147483648) }
}

Say $Message
if (-not $NoPause) { Read-Host 'Enter zum Schliessen' | Out-Null }
exit $ExitCode
