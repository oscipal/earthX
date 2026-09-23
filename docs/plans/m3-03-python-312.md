# M3-03 — Wechsel auf Python 3.12: Umsetzungsplan

**Aufgabe:** M3-03 aus `docs/plans/m3-dritte-quelle-und-interface.md` §4.
**Stufe B.** Plan-Schritt, **wartet auf Ottos Freigabe** (Fragen in §8).
**Ort im Repo:** `docs/plans/m3-03-python-312.md`
**Grundlagen:** `plans/m3-dritte-quelle-und-interface.md` (P16, §4 M3-03,
Abnahme §5 Punkt 7); `plans/m2-format-und-viewer.md` D17; `adr/0007` §3.8 und
F5; `adr/0002` §6; `cloud-umgebung.md` §2, §7; `ENTSCHEIDUNGSLOG.md`, Zeile
„Wechsel von Python 3.11 auf 3.12 als eigene Aufgabe“.
**Ausdrücklich erlaubt:** Änderungen an `.github/workflows/ci.yml`,
`.github/workflows/live-smoke.yml` und am SessionStart-Hook unter `.claude/`
samt `scripts/setup-cloud-session.sh` (M3-03 „Umfang“).

---

## 1. Ziel in einem Satz

Backend, CI, Image und Cloud-Sitzung laufen auf Python 3.12, bevor in M3 neue
Abhängigkeiten dazukommen; `zarr` bleibt dabei auf 3.1.x.

---

## 2. Messungen dieser Sitzung (23.09.2026)

Alles unten wurde in dieser Cloud-Sitzung ausgeführt, nicht aus Dokumentation
abgeleitet. Das Test-venv lag im Scratchpad, nicht im Repo.

### 2.1 Wie 3.12 in die Sitzung kommt

| Befund | Beleg |
|---|---|
| `/usr/bin/python3.12` ist im Image **schon installiert**: 3.12.3, Ubuntu-Paket `python3.12` 3.12.3-1ubuntu0.12, dazu `python3.12-venv` und `python3.12-dev` | `dpkg -l`, `python3.12 --version` |
| `python3` zeigt trotzdem auf 3.11: `/usr/local/bin/python3 → /usr/bin/python3.11`, angelegt beim Start der Sitzung; `/etc/alternatives/python3 → /usr/bin/python3.11` | `ls -la`, `update-alternatives --display python3` |
| Im Image liegen außerdem 3.10, 3.11 und 3.13 sowie Hilfsskripte `use-python <v>` (stellt `update-alternatives` um) und `create-venv-py3.12` | `/usr/local/bin/` |
| `apt` wird dafür **nicht** gebraucht; `deadsnakes` bleibt gesperrt und ist auch nicht nötig | — |
| Zweiter Weg: `uv` (im Image vorhanden) lädt `cpython-3.12.11` von GitHub in 1,5 s | `uv python install 3.12` in den Scratchpad |
| Das bestehende `.venv` verweist über `.venv/bin/python3 → /usr/local/bin/python3` auf 3.11. Stellte man nur den Symlink um, zeigte das venv auf 3.12, seine Pakete lägen aber unter `lib/python3.11` — ein kaputtes venv ohne Fehlermeldung | `ls -la .venv/bin/` |
| **Nebenbefund:** Ein nacktes `pytest` in der Sitzung ist heute **nicht** das des venv, sondern `/root/.local/bin/pytest`, ein `uv tool` des Images ohne die Backend-Pakete. Es bricht beim Sammeln ab (`1 error`). Nur `.venv/bin/pytest` läuft | `which -a pytest`, Probelauf |

### 2.2 Backend auf 3.12

Frisches venv mit `/usr/bin/python3.12 -m venv`, dann
`pip install -r backend/requirements-dev.txt` wie im Hook:

| Prüfung | 3.11 (heutiges `.venv`) | 3.12 (Test-venv) |
|---|---|---|
| Installation | — | fehlerfrei, 35 s |
| `ruff check backend` | grün | grün, auch mit `--target-version py312` |
| `lint-imports --config .importlinter` | grün | grün, 12 Verträge gehalten |
| `pytest` (aus der Repo-Wurzel, mit Postgres/pgstac) | 1067 passed | **1067 passed**, gleich viele Warnungen (728) |
| `zarr` | 3.1.6 | 3.1.6 (der Deckel `<3.2` greift weiter) |

### 2.3 Was sich unter 3.12 von selbst mitbewegt

Die offenen Bereiche in `backend/requirements.txt` lösen unter 3.12 anders auf,
weil mehrere Pakete neue Reihen nur noch für `>=3.12` bauen (PyPI:
`rasterio` 1.5.1 und `numpy` 2.5.3 verlangen `>=3.12`):

| Paket | unter 3.11 | unter 3.12 | Bemerkung |
|---|---|---|---|
| `rasterio` | 1.4.4 (GDAL 3.10.3) | 1.5.1 (**GDAL 3.12.4**) | Kachel- und Zuschnitt-Pfad für COGs |
| `numpy` | 2.4.6 | 2.5.3 | |
| `rioxarray` | 0.19.0 | 0.23.0 | `.rio`-Accessor im Zarr-Pfad (`adr/0007` §3.4) |
| `numcodecs` | 0.16.5 | 0.17.0 | Codecs des Zarr-Pfads, kommt über `zarr` |
| `pyproj` | 3.7.2 | 3.8.0 | |
| `click-plugins`, `cligj` | vorhanden | entfallen | Abhängigkeiten von `rasterio` 1.4 |

Alle exakt gepinnten Pakete (`rio-tiler`, `titiler.core`, `pypgstac`,
`stac-fastapi.pgstac`) bleiben gleich. Die Offline-Tests sind mit dem neuen
Stand grün, darunter der Zarr-Leser gegen das synthetische Mini-Zarr und
`test_image_carries_what_the_wheels_need.py` gegen das `rasterio`-1.5.1-Wheel.
**Nicht** geprüft ist der Lesepfad gegen die echten Quellen: `gateway` erreicht
sie aus einer Sitzung nicht (M2-13), und der Live-Smoke liest nur Metadaten.
`rasterio` 1.4.4 gibt es auch als `cp312`-Wheel; der alte Stand ließe sich also
festhalten (Frage F3).

---

## 3. Umfang

Alle Stellen, an denen die Python-Version heute steht (`git grep` außerhalb von
`docs/`), und was sich an ihnen ändert:

| Datei | heute | geplant |
|---|---|---|
| `.github/workflows/ci.yml` | `PYTHON_VERSION: "3.11"` (gilt für `backend` und `import-boundaries`) | `"3.12"`; keine Matrix (F2) |
| `.github/workflows/live-smoke.yml` | zweimal `python-version: "3.11"` | `env: PYTHON_VERSION: "3.12"` auf Workflow-Ebene wie in `ci.yml`, beide Jobs lesen es |
| `backend/Dockerfile` | `FROM python:3.11-slim`, Kommentar nennt `environment.yml` (seit `adr/0008` gelöscht) | `FROM python:3.12-slim`; Kommentar ohne `environment.yml`, begründet mit CI und Sitzung |
| `pyproject.toml` | `target-version = "py311"` | `"py312"` (gemessen: keine neuen Funde) |
| `backend/requirements.txt` | Kommentar zu `zarr`: „3.1.6 is the last release that runs on Python 3.11 … moving to 3.12 is its own task (D17)“ | Deckel `zarr>=3.1,<3.2` bleibt; Kommentar sagt, dass er seit M3-03 nicht mehr von Python erzwungen ist und die Anhebung eine eigene Entscheidung ist. Je nach F3 zusätzliche Deckel |
| `scripts/setup-cloud-session.sh` | `python3 -m venv` (→ 3.11); ein vorhandenes venv wird nie geprüft | siehe §4 |
| `.claude/settings.json` | Hook-Eintrag | **unverändert**; das Skript trägt die Änderung |
| `backend/tests/test_image_carries_what_the_wheels_need.py` | Docstring nennt `python:3.11-slim` | `python:3.12-slim` |
| neu: `backend/tests/test_python_version.py` | — | siehe §5 |
| `docs/cloud-umgebung.md` §1, §2, §7 | „Python 3.11.15, systemweit“ | 3.12 im Image, `python3` zeigt auf 3.11, der Hook legt das venv ausdrücklich mit 3.12 an; `pytest` im Pfad (§4) |
| `docs/ENTSCHEIDUNGSLOG.md` | — | neue Zeilen am Ende (§7); keine bestehende Zeile geändert |

**Nicht anfassen:** `zarr`-Deckel, exakt gepinnte Pakete, `docker-compose.yml`
(nennt keine Python-Version), `.importlinter`, Frontend und Node-Version,
historische Pläne und ADRs (`m1-08`, `adr/0007` §3.8 bleiben als Stand ihrer
Zeit stehen). Die Log-Zeile „Wechsel von Python 3.11 auf 3.12 als eigene
Aufgabe“ bleibt unverändert; ihr Status wird über eine neue Zeile am Ende
geschlossen, damit M3-00, das parallel dieselbe Datei ändert, keinen Konflikt
bekommt.

---

## 4. Der SessionStart-Hook

Heute legt `scripts/setup-cloud-session.sh` das venv mit `python3` an und prüft
ein vorhandenes venv nie. Nach dem Wechsel muss es drei Dinge können:

1. **Venv mit 3.12 anlegen, ausdrücklich:** `python3.12 -m venv`, nicht
   `python3`. Das Interpreter-Kommando steht einmal oben im Skript
   (`PYTHON=python3.12`).
2. **Ein venv mit falscher Version ersetzen:** Liefert
   `.venv/bin/python -c 'import sys; print(sys.version_info[:2])'` nicht
   `(3, 12)`, wird `.venv` gelöscht und neu angelegt. `.venv/` ist
   `.gitignore`d und enthält nur Installiertes; Löschen ist hier Wegwerfen
   eines Build-Ergebnisses, keine Daten.
3. **Fehlt `python3.12`, nicht auf 3.11 ausweichen:** Warnung mit genauer
   Angabe, was fehlt, kein venv, die Zusammenfassung meldet `venv FEHLT`.
   `have_venv` prüft zusätzlich die Version.

Der Hook stellt `python3` systemweit **nicht** um (`use-python 3.12` ginge,
fasst aber Dinge des Images an, die das Repo nichts angehen).

**`pytest` im Pfad (F4).** Die Abnahme verlangt, dass eine frische Sitzung
„`pytest` aus der Repo-Wurzel ohne Nachinstallation“ ausführt, und `CLAUDE.md`
nennt `pytest` als Befehl. Heute greift ein nacktes `pytest` das Werkzeug des
Images und bricht ab (§2.1). Vorschlag: Der Hook schreibt
`export VIRTUAL_ENV=…/.venv` und `export PATH=…/.venv/bin:$PATH` in die Datei,
die Claude Code einem SessionStart-Hook als `$CLAUDE_ENV_FILE` übergibt; die
Werte gelten dann für alle folgenden Bash-Befehle der Sitzung. Ist die Variable
nicht gesetzt, meldet der Hook das und macht weiter. Ob das in der
Cloud-Umgebung wirkt, lässt sich nur in einer **neu gestarteten** Sitzung
messen (§6); aus dieser Sitzung ist `CLAUDE_ENV_FILE` nicht sichtbar.

---

## 5. Tests

Neu `backend/tests/test_python_version.py`, zwei kleine Tests:

- **Der Interpreter ist 3.12.** `sys.version_info[:2] == (3, 12)`. Schlägt in
  CI fehl, wenn `setup-python` doch eine andere Version liefert, und in einer
  Sitzung, die versehentlich das alte venv benutzt. Bewusst `==`, nicht `>=`:
  ein späterer Wechsel auf 3.13 soll wieder eine bewusste Aufgabe sein.
- **Alle Stellen nennen dieselbe Version.** Der Test liest die Version aus
  `backend/Dockerfile` (`FROM python:X.Y-slim`), `ci.yml` und
  `live-smoke.yml` (`PYTHON_VERSION`), `pyproject.toml` (`target-version`) und
  dem Hook (`PYTHON=`) und vergleicht sie. Fehlerfälle: eine Datei ohne
  erkennbare Angabe gilt als Fehler, nicht als Treffer — sonst wäre der Test
  durch Umformulieren still zu umgehen. Die Ausleselogik bekommt eigene Fälle
  mit synthetischen Zeichenketten (Angabe fehlt, zwei verschiedene Angaben in
  einer Datei, Kommentarzeile mit alter Version wird nicht gewertet).

Der Rest ist durch die bestehende Suite abgedeckt: 1067 Tests, darunter der
Wheel-Abgleich für das Image, laufen auf 3.12 unverändert grün (§2.2).

---

## 6. Ablauf und Nachweise

Kleine, getrennte Commits:

1. Plan (dieser PR-Stand).
2. CI und Live-Smoke auf 3.12.
3. Dockerfile auf `python:3.12-slim`, Docstring des Wheel-Tests.
4. `pyproject.toml` `py312`, `requirements.txt`-Kommentar (und Deckel je F3).
5. Hook: venv mit 3.12, Versionsprüfung, `CLAUDE_ENV_FILE`.
6. `test_python_version.py`.
7. `cloud-umgebung.md`, Log-Zeilen.

Vor jedem Push in der Sitzung: `ruff check backend`, `lint-imports`,
`pytest` — alles im neu angelegten 3.12-venv. Der Hook wird in der Sitzung mit
gesetztem `CLAUDE_PROJECT_DIR` zweimal nacheinander ausgeführt (Anlegen,
dann Überspringen), einmal gegen das alte 3.11-venv (Ersetzen) und einmal mit
einer Scratchpad-Datei als `CLAUDE_ENV_FILE`.

**Was nur außerhalb dieser Sitzung zu belegen ist:**

- **CI:** die vier Pflicht-Checks auf dem Draft-PR, `compose-topology` baut das
  Image auf `python:3.12-slim`. Die Job-Namen bleiben gleich, damit der
  Branch-Schutz sie weiter findet (deshalb keine Matrix, F2).
- **Frische Sitzung:** Otto startet eine neue Sitzung auf diesem Branch; darin
  laufen ohne weitere Schritte `pytest` aus der Repo-Wurzel und
  `.venv/bin/python --version` → 3.12. Das Ergebnis kommt in den PR.
- **Live-Smoke:** einmal per `workflow_dispatch` auf dem Branch, wenn Otto das
  will; sonst läuft er nach dem Merge planmäßig.

---

## 7. Log-Zeilen (am Ende von `ENTSCHEIDUNGSLOG.md`)

- Python 3.12 für Backend, CI, Image und Sitzung; in der Sitzung aus dem
  Ubuntu-Paket des Images (bzw. je nach F1); 3.11 läuft in CI nicht mit (F2);
  `zarr` bleibt auf 3.1.x. Schließt die Zeile „Wechsel von Python 3.11 auf 3.12
  als eigene Aufgabe“.
- Umgang mit den mitbewegten Paketen laut F3.
- Hook setzt das venv in den Pfad der Sitzung (F4).

---

## 8. Fragen an Otto

**F1 — Woher kommt 3.12 in der Sitzung?**
1. **Ubuntu-Paket `/usr/bin/python3.12` aus dem Image (Empfehlung).** Schon
   installiert, kein Netz, Sicherheitsupdates über Ubuntu; nur Patchstand
   3.12.3 statt des neuesten 3.12.x in CI und Image — für Tests ohne Belang.
2. `uv python install 3.12` im Hook. Neuester Patchstand wie CI, aber ein
   Download von GitHub bei jedem Sitzungsstart und `uv` als stille
   Voraussetzung aus dem Image.
3. `use-python 3.12` im Hook, stellt `python3` systemweit um. Nicht empfohlen:
   greift in das Image ein, das venv braucht es nicht.

**F2 — Läuft 3.11 in der CI übergangsweise mit?**
1. **Nein (Empfehlung).** Unter 3.11 lösen fünf Pakete anders auf (§2.3); ein
   3.11-Job prüfte einen Stand, den niemand mehr betreibt. Eine Matrix änderte
   außerdem die Job-Namen der Pflicht-Checks und damit den Branch-Schutz
   (braucht Otto). Zurück ginge es mit einem Revert dieses PR.
2. Ja, als zusätzlicher, nicht verpflichtender Job bis zum Ende von M3.

**F3 — Die mitbewegten Pakete (`rasterio` 1.5 mit GDAL 3.12, `numpy` 2.5,
`rioxarray` 0.23, `numcodecs` 0.17, `pyproj` 3.8)?**
1. **Mitgehen lassen (Empfehlung).** Die Bereiche sind bewusst offen, nur
   Pakete mit genanntem Grund sind exakt gepinnt; alle 1067 Tests sind grün.
   Das Risiko liegt im Lesepfad gegen echte Quellen, den keine Sitzung prüfen
   kann: dafür prüft Otto lokal je Datensatz eine Kachel und einen
   Zuschnitt-Download (Liste im PR).
2. Den Stand von 3.11 festhalten (`rasterio<1.5`, `numpy<2.5`,
   `rioxarray<0.20`, `numcodecs<0.17`, `pyproj<3.8`) und die Anhebung als
   eigene Aufgabe führen, wie bei `zarr`. Trennt Python- und
   Bibliothekswechsel sauber, kostet fünf Deckel, die später wieder fallen.
3. Nur GDAL festhalten (`rasterio<1.5`), den Rest mitgehen lassen.

**F4 — `pytest` im Pfad der Sitzung?**
1. **Ja, über `$CLAUDE_ENV_FILE` im Hook (Empfehlung),** wie in §4. Wirkt es
   in der frischen Sitzung nicht, meldet der PR das und Variante 2 gilt.
2. Nein; `CLAUDE.md` und `cloud-umgebung.md` nennen in der Sitzung
   `.venv/bin/pytest`. Änderung an `CLAUDE.md` bräuchte deine Freigabe.

**Von Otto auszuführen:**
- Eine neue Sitzung auf diesem Branch starten, sobald die Umsetzung gepusht
  ist (Nachweis §6).
- Lokal die eigene Umgebung auf 3.12 neu anlegen; bei F3 (1) je Datensatz eine
  Kachel und einen Zuschnitt-Download prüfen.
