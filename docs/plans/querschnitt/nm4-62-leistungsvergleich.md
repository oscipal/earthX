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
