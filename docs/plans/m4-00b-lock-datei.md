# M4-00b — Lock-Datei für die Backend-Pakete: Umsetzungsplan

**Aufgabe:** M4-00b aus `docs/plans/m4-processing-kern.md` §4.
**Stufe B** — **von Otto am 02.10.2026 freigegeben** mit F1 (1), F2 (1),
F3 (1), F4 (1) (§9). Dazu: Das Backend läuft bei Otto nur in Docker (Docker
Desktop unter Windows, x86_64), nie nativ; Linux x86_64 ist Pflicht, aarch64
darf mitlaufen, native Plattformen außerhalb von Docker müssen nicht abgedeckt
sein. Die Reihenfolge der pip-Optionen prüft ein Test; der Grund für die
Ausnahme `version-parser` steht im Erzeugungsskript. Der Plan-Schritt ist damit
abgeschlossen, die Umsetzung läuft.
**Ort im Repo:** `docs/plans/m4-00b-lock-datei.md`
**Grundlagen:** `plans/m4-processing-kern.md` (Q16, §1.2, §4 M4-00b, §5 Punkt 9,
§6); `plans/m3-15-abnahme.md` §12 („Lock-Datei“); `plans/m3-03-python-312.md`
(Muster für Hook-Nachweis, F4); `cloud-umgebung.md` §3, §7; `adr/0002` §6;
`ENTSCHEIDUNGSLOG.md`, Zeilen vom 30.09.2026 („Vorschlag: Lock-Datei“) und vom
02.10.2026 („M4 Q16“).
**Ausdrücklich erlaubt:** Änderungen an `.github/workflows/ci.yml` und
`.github/workflows/live-smoke.yml` (M4-00b „Umfang“). `.claude/settings.json`
bleibt unverändert (§5.4).

**Belegstufen** wie in `adr/0009`: [M] in dieser Session gemessen,
[P] am Primärdokument gelesen, [S] Zusammenfassung, [A] eigene Ableitung.

---

## 1. Ziel in einem Satz

CI, Image und Cloud-Session installieren dieselben Backend-Pakete in denselben
Versionen, jede Datei gegen einen eingecheckten Hash geprüft; eine neue
Veröffentlichung irgendwo im Abhängigkeitsbaum ändert nichts mehr, bis jemand
die Lock-Datei bewusst erneuert.

---

## 2. Messungen dieser Session (02.10.2026)

Alles in einem Wegwerf-venv im Scratchpad, mit `/usr/bin/python3.12`; das
Projekt-venv und die Anforderungsdateien blieben unberührt. Netz nur zu
`pypi.org` und `files.pythonhosted.org` (frei in der Session). Die
Dokumentations-Hosts `docs.astral.sh`, `pip.pypa.io` und
`pip-tools.readthedocs.io` sind aus der Session gesperrt [M]; die pip-Doku ist
deshalb aus dem Quellpaket `pip-26.2.1` (PyPI) gelesen, die uv-Optionen aus
`uv pip compile --help`.

### 2.1 Werkzeuge

| Werkzeug | Stand | Befund |
|---|---|---|
| `uv` | 0.8.17 im Image (`/root/.local/bin/uv`), neueste Version auf PyPI 0.12.22 | `uv pip compile` vorhanden; löst `backend/requirements.txt` in unter 4 s auf [M] |
| `pip-tools` | 7.6.1 auf PyPI | per `pip install pip-tools` in der Session installierbar; Laufzeit und Ergebnis in §2.5 [M] |
| `pip lock` | in pip 26.2.1 vorhanden | schreibt `pylock.toml`; `pip install` liest das Format in 26.2.1 nicht (kein Treffer für `pylock` im Installationsbefehl des Quellpakets) [P] — fällt damit aus, CI und Image bräuchten ein zweites Werkzeug |

Wichtig für alle Varianten: **Installiert wird mit `pip` allein.** Das
Werkzeug zum Erzeugen braucht nur, wer die Lock-Datei erneuert. CI, Image und
Hook bekommen kein neues Werkzeug [A].

### 2.2 Auflösung und Plattformen

`uv pip compile --generate-hashes --python-version 3.12`, einmal je Zielplattform
und einmal `--universal` [M]:

| Variante | Pakete in `requirements.lock` | Unterschied zu Linux x86_64 |
|---|---|---|
| `--python-platform x86_64-manylinux_2_28` | 108 | — |
| `--python-platform aarch64-manylinux_2_28` | 108 | keiner, gleiche Versionen |
| `--universal` | 110 | gleiche Versionen; zusätzlich `httpx2-jsfetch` (nur `emscripten`) und `tzdata` (nur `win32`/`emscripten`), beide über Marker auf Linux nicht installiert; Marker an `httpcore2`, `psycopg-binary`, `truststore`, `uvloop` |

Die Hashes umfassen in jeder Variante **alle** Dateien der gewählten Version auf
PyPI (Wheels aller Plattformen und das sdist) [M], nicht nur die der
Zielplattform. Der Unterschied liegt nur in der Auswahl der Pakete über Marker.

Ob die gewählten Versionen auf der jeweiligen Plattform als Wheel vorliegen,
geprüft mit der universellen Dev-Lock-Datei als Eingabe und
`--only-binary :all: --no-binary version-parser` [M]:

| Plattform | Ergebnis |
|---|---|
| Linux x86_64 (CI, Image, Session) | alle als Wheel |
| Linux aarch64 (Docker auf Apple Silicon) | alle als Wheel |
| macOS arm64 nativ, Ziel 14.0 | `rasterio==1.5.2` ohne passendes Wheel |
| macOS arm64 nativ, Ziel 15.0 | alle als Wheel |
| macOS x86_64 nativ, Standardziel | `pyproj==3.8.0` ohne passendes Wheel (`macosx_15_0_x86_64`) |

Das ist kein Effekt der Lock-Datei: Ohne sie wählt `pip` heute dieselben
Versionen [A]. Nach `README.md` §2 braucht der lokale Start nur Docker.

### 2.3 Dev-Lock-Datei passt zur Laufzeit-Lock-Datei

`requirements-dev.txt` bindet `requirements.txt` per `-r` ein. Erzeugt man die
Dev-Lock-Datei mit `-c requirements.lock` als Constraint, stehen alle 110
Einträge der Laufzeit-Lock-Datei unverändert in der Dev-Lock-Datei; dazu kommen
11 reine Dev-Pakete (`pytest`, `ruff`, `import-linter` mit ihren
Abhängigkeiten, `colorama` nur `win32`), zusammen 121 [M].

### 2.4 Installation mit `--require-hashes`

| Lauf | Ergebnis |
|---|---|
| frisches venv, `pip install --require-hashes -r <dev-lock>` | grün; `pip check` ohne Befund; `pip freeze` **identisch** mit dem Projekt-venv, das der Hook heute ohne Lock-Datei installiert hat (118 Pakete) [M] |
| dasselbe mit `--only-binary :all:` | **scheitert**: `version-parser==1.0.1` (Abhängigkeit von `pypgstac`) gibt es nur als sdist [M] |
| dasselbe mit `--only-binary :all: --no-binary version-parser`, ohne Cache | grün in 41 s, `version-parser` wird aus dem sdist gebaut [M] |
| Optionen in der Lock-Datei selbst (`uv … --emit-build-options`) | **scheitert**: uv schreibt `--no-binary version-parser` vor `--only-binary :all:`, und pip lässt die spätere Zeile `:all:` die frühere Ausnahme aufheben [M] |

Laut pip-Doku (`docs/html/topics/secure-installs.md` in 26.2.1) gehören zu
einer sicheren Installation zwei Dinge: `--require-hashes` und
`--only-binary :all:` [P]. Hash-Prüfung ist „all-or-nothing“; fehlt einer
Abhängigkeit der Eintrag mit Hash, bricht pip ab („Hashes are required for
_all_ dependencies“) [P]. Ein sdist wird gegen seinen Hash geprüft; was der
Build in seiner isolierten Umgebung nachlädt (bei `version-parser`: `setuptools`,
nur `setup.py`, kein `pyproject.toml` [M]), steht nicht in der Lock-Datei und
wird nicht gegen einen eingecheckten Hash geprüft [A].

### 2.5 pip-tools zum Vergleich

`pip-compile --generate-hashes --allow-unsafe` (pip-tools 7.6.1) auf
`backend/requirements.txt` [M]:

- Laufzeit 4 min 53 s gegen unter 4 s mit uv (pip-tools lädt die Dateien für
  die Hashes selbst herunter).
- 108 Pakete, **dieselben Versionen** wie `uv` für Linux x86_64; die Dateien
  unterscheiden sich nur in der Schreibweise der Extras
  (`psycopg[binary,pool]` statt `psycopg`).
- `pip-compile --help` kennt keine Option für eine andere Zielplattform oder
  eine universelle Auflösung; es löst für die Umgebung auf, in der es läuft.
- Warnt, dass sich mit Version 8.0.0 der Standard für Extras ändert.

---

## 3. Umfang

| Datei | Änderung |
|---|---|
| `backend/requirements.lock` | neu, erzeugt; Laufzeitpakete für das Image |
| `backend/requirements-dev.lock` | neu, erzeugt; Laufzeit- plus Dev-Pakete für CI und Session |
| `scripts/lock-backend.sh` | neu; der eine Befehl, der beide Dateien erzeugt (§4) |
| `backend/requirements-dev.txt` | `packaging` als direkte Dev-Abhängigkeit mit Begründungskommentar (der Test in §6 importiert es; heute nur transitiv über `pytest`, Version bleibt 26.3) |
| `.github/workflows/ci.yml` | Jobs `backend` und `import-boundaries` installieren aus `requirements-dev.lock`; `cache-dependency-path` zeigt auf die Lock-Dateien |
| `.github/workflows/live-smoke.yml` | alle drei Jobs ebenso |
| `backend/Dockerfile` | `COPY requirements.lock` und Installation daraus |
| `scripts/setup-cloud-session.sh` | Installation aus `requirements-dev.lock`, Log-Zeile entsprechend |
| `backend/tests/test_backend_lock.py` | neu (§6) |
| `README.md` | kurzer Abschnitt „Backend-Abhängigkeiten erneuern“ (§7) |
| `docs/cloud-umgebung.md` | Nachtrag in §7 mit Datum; §3 bekommt einen Satz, dass pip seit M4-00b aus der Lock-Datei installiert |
| `docs/ENTSCHEIDUNGSLOG.md` | Zeilen nach §8, am Ende |

**Nicht angefasst:** die Versionen der exakt gepinnten Pakete (`rio-tiler`
9.4.6, `pypgstac` 0.9.12, `stac-fastapi.pgstac` 6.4.1, `titiler.core` 2.3.0,
Kappe `zarr<3.2`) und alle übrigen Zeilen der `.txt`-Dateien; Anwendungscode;
`.claude/settings.json`; `compose/objectstore/requirements-smoke.txt` (gehört
nicht zu den Backend-Paketen, siehe F4); `pip install --upgrade pip` in CI und
Hook (pip ist das Installationswerkzeug, nicht Teil des Baums; ein Pin dafür
wäre eine eigene Frage).

**Umfang in Zeilen:** ohne die zwei erzeugten Lock-Dateien (zusammen rund
4 400 Zeilen, fast alles Hashes) etwa 250–300 geänderte Zeilen, davon gut die
Hälfte Test.

---

## 4. Lock-Dateien erzeugen

`scripts/lock-backend.sh` (bash, `set -euo pipefail`, aus der Repo-Wurzel oder
von überall, Pfade über `BASH_SOURCE`) ruft nacheinander auf — hier mit den
Empfehlungen aus F1–F3:

```bash
uv pip compile backend/requirements.txt \
  --universal --python-version 3.12 --generate-hashes \
  --only-binary :all: --no-binary version-parser \
  --custom-compile-command scripts/lock-backend.sh \
  -o backend/requirements.lock

uv pip compile backend/requirements-dev.txt \
  -c backend/requirements.lock \
  --universal --python-version 3.12 --generate-hashes \
  --only-binary :all: --no-binary version-parser \
  --custom-compile-command scripts/lock-backend.sh \
  -o backend/requirements-dev.lock
```

- **`--custom-compile-command`** schreibt das Skript statt des langen Befehls in
  den Kopf beider Dateien [M]; wer die Datei öffnet, sieht, wie sie entsteht.
- **`--only-binary` beim Erzeugen** sorgt dafür, dass uv nur Versionen wählt, die
  als Wheel vorliegen; so fällt ein neues sdist-only-Paket beim Erneuern auf,
  nicht erst in der CI [A].
- **Ohne `--upgrade`** behält uv die Versionen einer bestehenden Ausgabedatei, so
  weit die Anforderungen es zulassen [P, uv-Hilfetext zu `--upgrade`]. Ein
  bewusstes Erneuern ist `scripts/lock-backend.sh --upgrade` (das Skript reicht
  Argumente an beide Aufrufe durch).
- Das Skript prüft, dass `uv` vorhanden ist, und bricht sonst mit einer klaren
  Meldung ab; es installiert nichts selbst.

Der erste Lauf in der Umsetzung wählt keine neuen Versionen gegenüber dem
heutigen Projekt-venv (§2.4, `pip freeze` identisch); der PR belegt das mit
demselben Vergleich.

---

## 5. Installation an vier Stellen

Gleicher Befehl überall (mit den Empfehlungen aus F3):

```bash
pip install --require-hashes --only-binary :all: --no-binary version-parser \
  -r backend/requirements-dev.lock        # Image: requirements.lock
```

Die Reihenfolge `--only-binary :all:` vor `--no-binary version-parser` ist
nötig (§2.4); der Test in §6 prüft die vier Stellen auf genau diese Optionen.

### 5.1 `ci.yml`

- `backend`: Schritt „Install dependencies“ wie oben;
  `cache-dependency-path: backend/requirements-dev.lock`.
- `import-boundaries`: wie oben. Bekommt dabei kein `cache: pip`, wie heute.
- `frontend`, `compose-topology`: unverändert (`compose-topology` baut das Image
  und prüft so den Dockerfile-Weg mit).
- Job-Namen bleiben gleich; der Branch-Schutz (Pflicht-Checks) ist nicht
  berührt.

### 5.2 `live-smoke.yml`

Die drei Jobs wie `backend`. Der Live-Smoke läuft nicht im PR; die erste
Ausführung nach dem Merge ist der planmäßige Lauf um 05:17 UTC. Optional stößt
Otto ihn nach dem Merge per `workflow_dispatch` an.

### 5.3 `backend/Dockerfile`

```dockerfile
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes \
      --only-binary :all: --no-binary version-parser -r requirements.lock
```

Kommentar darüber: woher die Datei kommt, warum die Optionen. Der Rest des
Dockerfile bleibt. Nach dem Merge baut Otto einmal mit `--no-cache` neu
(Plan §1.3).

### 5.4 SessionStart-Hook

`scripts/setup-cloud-session.sh` installiert aus `requirements-dev.lock`; der
Kommentarblock über dem Schritt bekommt einen Satz zur Lock-Datei. Der
Eintrag in `.claude/settings.json` ruft dasselbe Skript wie bisher auf und
bleibt deshalb unverändert.

Ein bestehendes venv mit neueren Versionen (aus der Zeit vor der Lock-Datei)
wird dabei auf die Versionen der Lock-Datei gebracht; Pakete, die nicht mehr in
der Lock-Datei stehen, bleiben liegen, wie heute auch [A]. Ein `pip-sync` oder
`uv pip sync` würde sie entfernen, bringt aber ein Werkzeug in den Hook; nicht
vorgesehen.

---

## 6. Test: `backend/tests/test_backend_lock.py`

Ohne Netz, ohne uv, nur Dateien lesen; Muster `test_frontend_deps_hook.py`
(kleine Hilfsfunktionen, synthetische Dateien in `tmp_path` für die Fehlerfälle)
und `test_python_version.py` (ein Muster findet nichts → Test fällt, statt die
Stelle still aus dem Vergleich zu nehmen).

**Am echten Repo:**

1. Jede Anforderung aus `requirements.txt` steht in `requirements.lock`, mit
   einer Version, die den Specifier erfüllt (`packaging.requirements`,
   `packaging.specifiers`); dasselbe für `requirements-dev.txt` (samt `-r`)
   gegen `requirements-dev.lock`.
2. Jeder Eintrag beider Lock-Dateien ist `name==version`, hat mindestens einen
   `--hash=sha256:`, und kein Name kommt doppelt vor.
3. Jeder Eintrag von `requirements.lock` steht mit gleicher Version, gleichem
   Marker und gleichen Hashes in `requirements-dev.lock` (CI prüft, was das Image
   installiert).
4. Beide Köpfe nennen `scripts/lock-backend.sh`.
5. Jede Installationsstelle — beide Workflows (jede `pip install`-Zeile, die
   `backend/requirements` nennt), `backend/Dockerfile`, Hook — installiert aus
   einer `.lock`-Datei mit `--require-hashes` und den Optionen aus §5; keine
   Stelle installiert mehr aus einer `.txt`-Datei des Backends.

**Fehlerfälle und zweckfremde Nutzung (synthetisch):**

- Anforderung fehlt in der Lock-Datei → erkannt (die geforderte Gegenprobe;
  zusätzlich im PR einmal am echten Repo: eine Zeile aus `requirements.lock`
  entfernt, Test rot, Ausgabe im PR).
- Version außerhalb des Specifiers (z. B. `zarr==3.2.0` gegen `<3.2`) und
  abweichender exakter Pin (`rio-tiler==9.4.7`) → erkannt.
- Eintrag ohne Hash, Eintrag ohne `==` (Bereich in der Lock-Datei), doppelter
  Eintrag → erkannt.
- Editable- oder URL-Eintrag (`-e .`, `pkg @ https://…`) in der Lock-Datei →
  abgelehnt; die Lock-Datei kennt nur Index-Pakete.
- Namensschreibweisen (`stac-fastapi.pgstac` gegen `stac-fastapi-pgstac`,
  `titiler.core` gegen `titiler-core`) werden nach PEP 503 normalisiert und
  gelten als gleich.
- Extras (`uvicorn[standard]`, `pypgstac[psycopg]`, `psycopg[pool]`): geprüft
  wird das Paket selbst. Fehlt eine Abhängigkeit eines Extras, bricht
  `pip install --require-hashes` in der CI ab (§2.4, [P]); der Test
  wiederholt das nicht.
- Eine Workflow-Datei, in der das Muster keine Installationszeile findet →
  Test fällt.

**Was der Test nicht kann:** prüfen, ob die Lock-Datei die *neueste* mögliche
Auflösung ist. Das soll er auch nicht — Erneuern ist ein eigener PR.

---

## 7. Anleitung zum Erneuern

In `README.md` ein Abschnitt unter §2 („Backend-Abhängigkeiten ändern oder
erneuern“), in `cloud-umgebung.md` §7 ein Nachtrag mit Verweis darauf:

1. `.txt` ändern (neue Abhängigkeit, neuer Bereich) oder gar nichts für ein
   reines Erneuern.
2. `scripts/lock-backend.sh` (nur nötige Änderungen) bzw.
   `scripts/lock-backend.sh --upgrade` (alles auf neueste erlaubte Versionen).
3. `pytest backend/tests/test_backend_lock.py`, dann die ganze Suite.
4. Eigener PR mit dem Diff der Lock-Dateien; neue Pakete im Baum sind im
   PR-Text genannt (Plan §1.2: Bibliotheken, die selbst Verbindungen öffnen,
   gehören auf die Verbotsliste von `http-only-in-gateway`).
5. Nach dem Merge lokal `docker compose build --no-cache`.

`uv` ist in der Cloud-Session vorhanden (§2.1); lokal ist es per
`pip install uv` oder als Einzeldatei zu haben. Mit welcher uv-Version erzeugt
wurde, steht im PR-Text; die Ausgabe ist zwischen Versionen nicht garantiert
gleich formatiert [A], der Test hängt davon nicht ab.

---

## 8. Ablauf und Nachweise

1. Branch auf `main` (erledigt).
2. Skript und Lock-Dateien; Vergleich `pip freeze` frisches venv gegen
   Projekt-venv (Ergebnis im PR).
3. Installationsstellen umstellen; Test.
4. `ruff check backend`, `pytest`, `lint-imports --config .importlinter`
   (mit `PYTHONPATH=backend`) lokal; Ergebnisse im PR.
5. Gegenprobe: eine Anforderung aus der Lock-Datei entfernt → Test rot
   (Ausgabe im PR), danach zurück.
6. Push; Pflicht-CI grün, darin `compose-topology` mit dem neuen Dockerfile.
7. **Hook-Nachweis:** Otto startet eine neue Session auf dem Branch (wie
   M3-03 F4). Belegt ist es, wenn die Zusammenfassung des Hooks `venv ok`
   meldet und `pip freeze` im Projekt-venv der Dev-Lock-Datei entspricht (ein
   Einzeiler dafür steht im PR). Bis dahin steht der Punkt im PR als offen.
8. Doku, Log-Zeilen; `main` holen; PR-Text.

**Log-Zeilen** (am Ende von `ENTSCHEIDUNGSLOG.md`, nach Ottos Antworten):

- M4-00b Plan freigegeben mit F1–F4 (Antworten).
- M4-00b umgesetzt: Lock-Dateien, Werkzeug, Plattformabdeckung,
  `--only-binary` mit Ausnahme `version-parser`; Erneuern als eigener PR.

Kein ADR: Die Entscheidung „Lock-Datei“ ist schon gefallen (Q16); hier geht es
um Werkzeug und Form. Wenn Otto das anders sieht, ist ein ADR-Entwurf in
derselben Session möglich.

---

## 9. Fragen an Otto

**F1 — Werkzeug zum Erzeugen?**
1. **`uv pip compile` (Empfehlung).** Schon in der Session, löst in Sekunden,
   kann universell für alle Plattformen auflösen (§2.2) und den Kopf der Datei
   auf das Skript setzen. Nur fürs Erneuern nötig; CI, Image und Hook
   installieren weiter mit pip.
2. `pip-compile` (pip-tools). Ebenfalls Ausgabe im `requirements`-Format mit
   Hashes; löst aber nur für die Plattform auf, auf der es läuft (§2.5).
3. `pip lock` (`pylock.toml`). Nicht empfohlen: `pip install` liest das Format
   in 26.2.1 noch nicht (§2.1).

**F2 — Welche Plattformen deckt die Lock-Datei ab? Und: Startest du das
Backend je außerhalb von Docker, und baust du das Image auf einem Mac mit
Apple Silicon (dann ist es Linux aarch64)?**
1. **Universell (`--universal`) (Empfehlung).** Eine Datei für Linux x86_64,
   Linux aarch64 und — sofern Wheels da sind — macOS; zwei zusätzliche Einträge,
   die auf Linux über Marker entfallen (§2.2). Kein Nachteil für CI, Image,
   Session.
2. Nur Linux x86_64 (CI, Image, Session). Kleiner Unterschied in der Datei;
   ein Image-Bau auf Apple Silicon funktioniert heute trotzdem (gleiche
   Auflösung, §2.2), wäre aber nicht zugesichert.

Nativ auf macOS gilt in beiden Fällen: arm64 ab macOS 15, x86_64 derzeit nicht
(fehlende Wheels von `rasterio`/`pyproj`, unabhängig von der Lock-Datei).

**F3 — Nur Wheels installieren?**
1. **`--only-binary :all:` mit der einen Ausnahme `--no-binary version-parser`
   (Empfehlung).** Entspricht der pip-Empfehlung (§2.4); ein neues
   sdist-only-Paket im Baum fällt beim Erneuern laut auf statt still gebaut zu
   werden. Kosten: die Ausnahme steht an vier Stellen (vom Test abgeglichen),
   und `setuptools` für den Bau von `version-parser` bleibt ungeprüft.
2. Nur `--require-hashes`. Einfacher, wörtlich wie im Aufgabentext; pip baut
   jedes sdist, für das kein passendes Wheel da ist, mit ungeprüften
   Build-Abhängigkeiten.

**F4 — `compose/objectstore/requirements-smoke.txt` (Paket für den
Objektspeicher-Smoke in `compose-topology`)?**
1. **Nicht in dieser Aufgabe (Empfehlung).** Gehört nicht zu den
   Backend-Paketen; eine eigene kleine Stufe-A-Aufgabe, falls gewünscht.
2. Mit in diese Aufgabe, gleiches Verfahren, dritte Lock-Datei.

**Von Otto auszuführen:**
- Nach der Umsetzung eine neue Session auf diesem Branch starten (§8 Punkt 7).
- Nach dem Merge lokal `docker compose build --no-cache` (Plan §1.3).

---

## 10. Stand der Umsetzung (02.10.2026)

Umgesetzt wie in §3–§7 mit den Antworten F1–F4 (je Option 1).

- `scripts/lock-backend.sh` erzeugt `requirements.lock` (110 Einträge) und
  `requirements-dev.lock` (121 Einträge, darin alle 110 unverändert) [M].
- Frisches venv, `pip install --require-hashes --only-binary :all:
  --no-binary version-parser -r backend/requirements-dev.lock` ohne Cache:
  `pip check` ohne Befund, `pip freeze` identisch mit dem Projekt-venv
  (118 Pakete). Aus `requirements.lock` allein: 108 Pakete, `pip check` ohne
  Befund [M].
- `backend/tests/test_backend_lock.py`: 37 Fälle grün. Gegenproben am echten
  Repo [M]: `shapely` aus `requirements.lock` entfernt → rot
  („shapely is not in the lock file“); im Dockerfile `--no-binary
  version-parser` vor `--only-binary :all:` gesetzt → rot. Beide danach
  zurückgesetzt.
- `packaging` steht als direkte Dev-Anforderung in `requirements-dev.txt`;
  die Version (26.3) blieb unverändert.
- **Offen:** Beleg des SessionStart-Hooks in einer neu gestarteten Session
  (§8 Punkt 7). Otto startet sie nach dem „fertig“.
