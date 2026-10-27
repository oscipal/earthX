# NM4-29 — 512er-Kacheln prüfen

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 29 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Messung und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach dem Merge von NM4-26; nicht gleichzeitig mit NM4-04 oder NM4-19 (`tiler`).
**Startsatz:** „Führe Aufgabe NM4-29 aus `docs/plans/querschnitt/nm4-29-kacheln-512.md` aus.“

## 1. Anlass

NM4-26 (26.10.2026) hat gezeigt: Der Browser öffnet über HTTP/1.1 nur 6 Verbindungen, die Kacheln warten dort in einer Schlange. Größere Kacheln (512 statt 256 px) hießen ein Viertel der Anfragen für dieselbe Fläche. Otto hat das als eigene Aufgabe vorgesehen.

## 2. Soll

- Entscheiden mit Messung, ob Kacheln mit 512 px eine Ansicht spürbar schneller machen, und wenn ja, umstellen.

## 3. Im Plan klären (mit Optionen und Empfehlung)

- **Messung** mit `scripts/tile-bench` (aus NM4-26): Gesamtzeit einer Ansicht und gelesene Bytes je Kachelgröße, bei unbegrenzter Leitung und 100 Mbit/s.
- **Folgen:** Zoomlogik der Karte, freigegebene Zoomstufen (Mosaik ab Zoom 8, Grenzen der Item-Kachel), Grenzen der Mosaik-Kachel (Items je Kachel), Statistik-Routen, TileJSON (`tileSize`), Bitgleichheit Kachel ↔ Job (`adr/0014` §6.3) auf der nativen Ebene.
- Gilt die Umstellung für alle Kachel-Arten (Szene, Mosaik, Vorschau, Ergebnis) oder nur einige?

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Messung vorher/nachher im PR; Bitgleich-Tests grün; Prüfung im echten Browser.
- Nachtrag in `adr/0006` bzw. `adr/0014`, falls `tileSize` oder Zoomgrenzen sich ändern.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n) mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat, siehe Kopf des Backlogs).
- Vor „fertig“ ist main geholt.
