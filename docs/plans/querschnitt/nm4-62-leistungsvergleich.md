# NM4-62 — Leistungsvergleich alter Stand gegen main (Job, Zuschnitt, Kachel)

**Stand:** 30.10.2026, beauftragt von Otto (Backlog-Punkt 62 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** messen, Ursache suchen, beheben, wenn klein; sonst Bericht mit Vorschlag an Otto vor dem Code.
**Modell:** Opus, Effort hoch (Messung und Ursachensuche).
**Start:** sofort möglich, reines Backend (kein Frontend-Platz).
**Startsatz:** „Führe Aufgabe NM4-62 aus `docs/plans/querschnitt/nm4-62-leistungsvergleich.md` aus.“

## 1. Anlass (Ottos Messung, 30.10.2026, abends, schlechtes Netz)

Messung nach `adr/0022` §8.2 (Block B, Suche ohne `query`) auf Ottos Rechner, direkt nacheinander:

| | Stand von #215 (28.10.) | main (30.10.) |
|---|---|---|
| P1 kalte Mosaik-Kachel (4 Szenen, NDVI, z10, 512 px) | 8,2 / 21,3 / 27,5 s | 21,1 / 27,6 / 23,6 s |
| P2 warme Kachel | 0,52 s | 0,44 s |
| P3 Zuschnitt `red`+`nir`, 0,05° | 10,5 s | 15,6 s |
| P4 `scripts/try-job.ps1` (ganzes Skript) | 2,8 s | 12,7 s (weitere Läufe main: 12,5 und 15,5 s) |

Die Kachel ist bei beiden gleich langsam – das Netz war schlecht (Oregon 0,6–1 MB/s). Auffällig sind P4 und evtl. P3. P4 misst aber das ganze Skript aus dem jeweiligen Stand (Abfrageintervall, zusätzliche Schritte), ist also kein sauberer Vergleich.

## 2. Vorgehen

1. **Netz ausschalten:** Messung gegen die nachgebaute Quelle mit fester Verzögerung (`scripts/tile-bench/`, wie NM4-26/NM4-29), gleiche Szenen, gleiche Verzögerung, beide Stände (Merge-Commit von #215 und aktueller main) im selben Lauf, je mehrfach (Median).
2. **Gemessen wird serverseitig:**
   - Job: reine Laufzeit aus den Zeitstempeln des Jobs (angenommen → läuft → fertig), getrennt Wartezeit in der Queue, Lesen, Rechnen, Schreiben; derselbe Auftrag wie `try-job.ps1` (ein Asset, `reproject` nach EPSG:3035, 20 m, kleine Fläche) und ein NDVI mit `mask`.
   - Zuschnitt (`POST …/download`) und Mosaik-Kachel kalt/warm.
3. **`try-job.ps1` vergleichen:** Abfrageintervall und Schritte beider Fassungen; nennen, wie viel von P4 allein am Skript liegt.
4. **Ursache:** Ist main bei Job, Zuschnitt oder Kachel um mehr als 20 % langsamer, die Ursache per Bisektion über die Merges seit #215 suchen (Kandidaten u. a. NM4-43b band-Interleave/`reproject` v4, NM4-43c Speicher-/Zeitschätzung, NM4-57 Log-Filter, NM4-27 Aufräumer, Abfrage-Intervalle im Worker) und mit Zahlen belegen.
5. **Beheben**, wenn die Ursache klein und eindeutig ist (eigener Commit, Test, gleiche Messung danach); sonst Vorschlag mit Optionen an Otto.
6. **Wiederholbar machen:** ein Skript unter `scripts/` (z. B. `scripts/bench/compare.sh` oder PowerShell für Otto), das zwei Stände gegen die nachgebaute Quelle vergleicht, mit Aufruf im PR.

## 3. Grenzen

- Ausgehende Anfragen nur über `gateway`; die nachgebaute Quelle läuft lokal.
- Keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder Ausgaben.
- Nachträge heißen nach der Aufgabe („Nachtrag NM4-62“).
- Bilder nicht ins Repo.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 4. Abnahme

- Tabelle im PR: alter Stand gegen main, je Messgröße Median und Streuung, gegen die nachgebaute Quelle.
- Ursache benannt (oder belegt, dass es keine Regression gibt und P4 am Skript liegt).
- Falls behoben: Test und Messung danach.
- Alle vier Pflicht-Checks grün.
- Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.

## 5. Ergebnis (Nachtrag NM4-62, 30.10.2026)

**Kurz:** Keine Regression. Job, Zuschnitt und Kachel sind auf main gegen die nachgebaute Quelle im Median gleich schnell wie am Stand von #215 (alle Abweichungen ≤ 3 %). Beide Stände stellen dieselben Anfragen an die Quelle, Byte für Byte. P4 liegt an der Cache-Regel aus NM4-27 zusammen mit dem Abfrageintervall von `try-job.ps1`, nicht an einer langsameren Rechnung. Der einzige messbare Unterschied: Die Annahme eines `reproject`-Auftrags dauert länger (0,19 → 0,39 s). Belegstufen wie in `adr/0009`: [M] gemessen, [P] im Code gelesen, [A] eigene Ableitung.

### 5.1 Aufbau

- **Stände:** `ff22a59` (Merge von #215, 28.10.) und `38580e6` (main, 30.10.). Je ein Worktree und eine eigene Datenbank mit pgstac und den Migrationen des Stands. Die Messskripte sind für beide dieselben (dieser Branch).
- **Quelle:** `scripts/tile-bench/slow_source.py` mit 170 ms je Anfrage und 350 ms je Verbindung, Leitung unbegrenzt, Item nach 300 ms (wie NM4-26 und NM4-29). Synthetische COGs aus `make_cogs.py`, neu mit `SCL.tif` (20 m) für `mask`.
- **Kachel (P1, P2):** `cold_warm.py`: eine Mosaik-Kachel aus 4 Szenen, NDVI, z10, 512 px. Erst kalt aus frisch gestartetem `tiler` mit leerem Item-Cache, dann dieselbe Kachel warm.
- **Zuschnitt (P3):** `crop.py --size 0.05`: `red` und `nir`, 0,05°, frisch gestarteter `tiler`.
- **Jobs:** `job_bench.py`. Der Auftrag geht durch `accept_order`, `check_recipe_hosts` und `submit`, wie `POST …/execution` ihn behandelt. Ein `Supervisor` mit der Standardkonfiguration (wie in `docker-compose.yml`) startet den echten Kindprozess und lädt das Ergebnis hoch. Ersetzt sind nur die Nähte der Tests: Item aus `synthetic_item.py` (mit `file:checksum`, deshalb kein `HEAD`), GDAL liest von der nachgebauten Quelle, Objektspeicher ist `moto` im Prozess. Zeiten aus den Zeitstempeln des Jobs: Warten = angenommen → läuft, Laufzeit = läuft → fertig. Darin aus Hüllen um dieselben Funktionen: Start (Kindprozess bis zum Lauf, Importe), Lesen (COGs öffnen, Blöcke lesen), Rechnen (Pixelschritte, `reproject`-Pass), Schreiben (Arbeitsdateien, Maske, COG des Ergebnisses, Upload). Zwei Aufträge, beide in Rezeptversion 1 wie `try-job.ps1`: der Auftrag des Skripts (`red`, `reproject` nach EPSG:3035, 20 m, bilinear, 0,01°) und NDVI mit `mask` (Klassen 8, 9, 10; 0,05°). Jede Wiederholung hat eine neue Item-Fassung, also einen neuen Cache-Schlüssel und einen echten Lauf.
- **Ablauf:** 7 Wiederholungen. Die Stände wechseln sich ab, und welcher zuerst misst, wechselt je Wiederholung. Rechner der Sitzung: 4 Kerne, 16 GB.

### 5.2 Messung [M]

| Messgröße (s, Median und Spanne, n = 7) | `ff22a59` (#215) | `38580e6` (main) | main/#215 |
|---|---|---|---|
| P1 Mosaik-Kachel kalt (4 Szenen, NDVI, z10, 512 px) | 3,60 (3,58–3,66) | 3,65 (3,61–3,83) | 1,01 |
| P2 Mosaik-Kachel warm | 0,37 (0,36–0,40) | 0,36 (0,32–0,46) | 0,98 |
| P3 Zuschnitt `red`+`nir`, 0,05° | 2,42 (2,39–2,49) | 2,43 (2,40–2,45) | 1,00 |
| Job `reproject`: Warten | 0,01 (0,01–0,01) | 0,01 (0,01–0,01) | – |
| Job `reproject`: Laufzeit | 2,65 (2,56–2,75) | 2,74 (2,61–2,83) | 1,03 |
| – davon Start | 1,17 (1,08–1,27) | 1,19 (1,12–1,26) | 1,02 |
| – davon Lesen | 0,89 (0,89–0,91) | 0,90 (0,89–0,94) | 1,01 |
| – davon Rechnen | 0,05 (0,05–0,09) | 0,05 (0,05–0,12) | 0,95 |
| – davon Schreiben | 0,13 (0,11–0,15) | 0,12 (0,12–0,21) | 0,91 |
| Job NDVI mit `mask`: Warten | 0,01 (0,01–0,01) | 0,01 (0,01–0,01) | – |
| Job NDVI mit `mask`: Laufzeit | 4,13 (3,97–4,26) | 4,16 (4,09–4,27) | 1,01 |
| – davon Start | 1,19 (1,07–1,33) | 1,21 (1,16–1,38) | 1,02 |
| – davon Lesen | 2,41 (2,40–2,46) | 2,40 (2,40–2,44) | 1,00 |
| – davon Rechnen | 0,01 (0,01–0,05) | 0,01 (0,01–0,04) | – |
| – davon Schreiben | 0,14 (0,13–0,17) | 0,14 (0,14–0,20) | 1,03 |
| Annahme `reproject` (`accept_order` + `submit`) | 0,19 (0,17–0,21) | 0,39 (0,37–0,42) | 2,05 |
| Annahme NDVI mit `mask` | 0,08 (0,07–0,10) | 0,10 (0,09–0,12) | 1,25 |
| Ablauf von `try-job.ps1`, Runde 1 (Abfrage alle 3 s) | 3,33 | 3,88 | – |
| Ablauf von `try-job.ps1`, Runde 2, derselbe Auftrag | 0,27 (Cache-Treffer) | 3,66 (kein Treffer) | 13,6 |

„–“ beim Verhältnis: Werte unter 0,05 s, das Verhältnis sagt dort nichts. Die Teile der Laufzeit ergeben zusammen nicht genau die Laufzeit, weil Pipe, Abschluss und Zeilen in die Datenbank fehlen.

- **Quelle [M]:** Beide Stände holen für die kalte Kachel 32 Anfragen und 24,7 MB, für den Zuschnitt 8 Anfragen und 6,6 MB und für die 14 Jobs 98 Anfragen und 61,0 MB. Ein langsames Netz trifft sie also gleich.
- **Raster [M]:** Die Raster im ZIP des Zuschnitts sind in beiden Ständen bitgleich (SHA-256 aus `crop.py`).
- **Bisektion:** Kein Messwert von Job, Zuschnitt oder Kachel liegt mehr als 20 % über dem alten Stand, also entfällt sie (§2 Punkt 4). Auch die Kandidaten aus §2 zeigen keine Wirkung: Das Warten in der Queue liegt in beiden Ständen bei rund 10 ms (Weckruf über `NOTIFY`, `jobs/config.py` unverändert). Der Log-Filter aus NM4-57 und die längeren Importe von main ändern den Start um 0,02 s.

### 5.3 P4: Cache-Regel aus NM4-27, nicht die Rechnung

- **Skript [P]:** `scripts/try-job.ps1` ist zwischen beiden Ständen unverändert (`git diff ff22a59 38580e6 -- scripts/try-job.ps1` ist leer). Es wartet nach dem Senden 3 s, bevor es den Status das erste Mal abfragt (`$PollSeconds = 3`), und löscht am Ende beide Jobs (Schritt 5).
- **Regel [P]:** Seit NM4-27 (#214, gemergt nach #215; Frage 4, Otto: „sofort“) ist ein Lauf, an dem nur gelöschte Jobs hängen, ab dem Löschen kein Cache-Treffer mehr (`jobs/submit.py`, `_run_for`). Vorher setzte `DELETE` bei einem fertigen Job nur `dismissed`, und der Lauf blieb ein Treffer.
- **Folge [M]:** Am Stand von #215 bekommt jeder Lauf des Skripts nach dem ersten einen Treffer: Der Job ist sofort `successful`, und das Skript wartet nie. Auf main rechnet jeder Lauf den Job neu und wartet mindestens einmal 3 s. Im Modell sind das 0,27 s gegen 3,66 s (Tabelle, Runde 2).
- **Ottos Zahlen [A]:** 2,8 s für das ganze Skript am Stand von #215 sind mit einem echten Lauf nicht möglich, weil die erste Statusabfrage erst nach 3 s kommt. Der erste Auftrag war also ein Treffer aus einem früheren Lauf. Das Skript meldet das mit „Der Auftrag war schon fertig: ein Treffer aus einem früheren Lauf“. Auf main kommen die Laufzeit des Jobs gegen Oregon bei schlechtem Netz und deren Aufrundung auf ein Vielfaches von 3 s hinzu. Das erklärt die rund 10 s Unterschied (12,5–15,5 s gegen 2,8 s). Am Skript selbst liegt davon nur die Aufrundung, höchstens 3 s je Lauf; der Rest ist die beabsichtigte Cache-Regel. P4 misst deshalb zwischen den beiden Ständen nicht dasselbe.
- **P1 und P3 [A]:** Gegen die nachgebaute Quelle sind Kachel und Zuschnitt in beiden Ständen gleich, mit denselben Anfragen. Ottos Unterschiede (P1 8,2 / 21,3 / 27,5 s gegen 21,1 / 27,6 / 23,6 s; P3 10,5 gegen 15,6 s) liegen im Rahmen der Schwankung einer Leitung mit 0,6–1 MB/s.

### 5.4 Nebenbefund: Annahme eines `reproject`-Auftrags

- **Gemessen [M]:** Allein `accept_order` für den Auftrag von `try-job.ps1` braucht im laufenden Prozess 60 ms am Stand von #215 und 105 ms auf main (je 6 Aufrufe, ohne `submit`). NDVI mit `mask` bleibt bei 22–24 ms.
- **Ursache [M][P]:** Das Zielraster von `reproject` (`operators/reproject.py`, `_target_grid`: `transform_bounds` mit einem neuen PROJ-Transformer, rund 16 ms) wird je Auftrag fünfmal statt zweimal berechnet. Hinzugekommen sind die Aufrufe aus `plan.stock_steps` und `plan._planned_stock` (NM4-43, Ausgabebänder) in `estimate`. `submit` schätzt den Lauf noch einmal für sein Zeitlimit. Mit `submit` kommen so 0,2 s je Auftrag dazu.
- **Wirkung [A]:** Das verlängert nur die Antwort auf `POST …/execution` und die Schätzung, nicht den Job. Bei P4 macht es unter 0,2 von rund 10 s aus.
- **Nicht behoben:** Ein Cache in `processing` wäre Zustand zwischen Aufrufen im Worker-Kern (KLAERUNGEN B9). Das Raster einmal zu berechnen und durchzureichen, baut `plan.py` an mehreren Stellen um, und das ist nicht mehr klein. Vorschlag an Otto im PR.

### 5.5 Wiederholen

```bash
python -I scripts/tile-bench/make_cogs.py /tmp/tb/cogs                          # einmal, 1–2 min, ~860 MB
set -a; . ./.env.test; set +a                                                   # PG*-Variablen der Sitzung
REPS=7 COGS=/tmp/tb/cogs OUT=/tmp/tb/cmp scripts/tile-bench/compare.sh ff22a59 main
```

`compare.sh` legt je Stand einen Worktree unter `$OUT/trees` und eine Datenbank `earthx_bench_<sha>` an. Die Rolle braucht dafür das Recht, Datenbanken anzulegen. Am Ende druckt es die Tabelle aus §5.2 (`compare_summary.py`). Alle Ergebnisse stehen in `$OUT/results.jsonl`. Ein Lauf mit `REPS=7` dauert in der Sitzung rund 7 min. `RTT_MS`, `CONNECT_MS`, `MBIT` und `ITEM_MS` wirken wie in `bench.sh`. Einzelne Jobs: `PYTHONPATH=backend python scripts/tile-bench/job_bench.py --case reproject --reps 5`, dazu die Quelle wie in `bench.sh`. Es braucht Bash, Postgres und Python aus dem venv, also die Cloud-Sitzung oder WSL. Eine PowerShell-Fassung gibt es nicht.

### 5.6 Grenzen der Messung

- Der Job-Teil ruft `accept_order` und `submit` direkt auf, nicht über HTTP. Die Zeiten von FastAPI und `Invoke-WebRequest` fehlen in beiden Ständen gleich.
- `moto` statt Garage: Der Upload kostet hier 10–15 ms. Gegen Garage im Stack ist er länger, aber in beiden Ständen derselbe Code (`objectstore` unverändert).
- Die Quelle ist ein lokales Modell ohne Leitungsgrenze. Ottos Netz am 30.10. (0,6–1 MB/s) ist nicht nachgestellt. Weil beide Stände dieselben Bytes holen, ändert eine Grenze das Verhältnis nicht [A].

### 5.7 Antworten Otto (30.10.2026, zu #253)

1. **Annahme von `reproject`:** bleibt so. Als Backlog-Punkt für später: das Zielraster einmal berechnen und als Argument durchreichen, ohne Zustand im Worker-Kern. Den Punkt trägt der Planungs-Chat in `docs/plans/nach-m4-backlog.md` ein; dieser Branch ändert die Datei nicht (§4).
2. **`try-job.ps1`:** Option 2. Schritt 2 nennt jetzt die Laufzeit des Jobs aus seinem Status (`started` bis `finished`) in der OK-Zeile, damit sie auch in der Zusammenfassung steht. Ein Cache-Treffer ist dort ausdrücklich so benannt, mit dem Hinweis, dass die Laufzeit die des früheren Laufs ist. Fehlt eine der beiden Zeiten oder ist sie nicht lesbar, sagt die Zeile, dass die Laufzeit unbekannt ist. Getestet in `tests/integration/test_try_job_search.py` (`TestTheJobRuntimeTheScriptPrints`, gegen eine kleine nachgebaute Plattform). Der Test läuft nur mit PowerShell, also in der CI; in der Sitzung gibt es kein `pwsh`, er war hier nicht ausführbar.
