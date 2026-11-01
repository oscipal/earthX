# NM4-71 — Normalize: Vorschau ohne AOI geschätzt, Job immer mit exakten Werten

**Stand:** 01.11.2026, beauftragt von Otto (Backlog-Punkt 71 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, Quellen, Messung), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Recherche, Messung und Plan; Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach dem Merge von NM4-11b (#269). Backend und Frontend in einer Session. Höchstens zwei Stufe-B-Sessions und zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-71 aus `docs/plans/querschnitt/nm4-71-normalize-exakt-im-job.md` aus.“

## 1. Wunsch (Otto, 01.11.2026, wörtlich)

> von mir aus kann das in der vorschau so sein aber bei einem gestarteten job sollen dann schon die echten werte hergenommen werden. (Auch wenn die AOI grösser als 2048px ist)

„Das“ meint: Die messenden Methoden von `normalize` (Percentile, Z-score, Robust) messen für die Vorschau ohne AOI bzw. bei großer Fläche über eine verkleinerte Fassung (Overview).

## 2. Heute (NM4-11, #244; NM4-11b, #269)

- `normalize` Version 3 mit `method`; die gemessenen Werte stehen vor dem Start im Rezept (`measured`), gemessen über die Statistik-Route aus NM4-19 (exakt bis 2048², darüber nicht exakt).
- Die messenden Methoden sind ohne AOI gesperrt; „Fixed range“ geht immer.
- Normalize wirkt im Bandvorrat an Ort und Stelle (Otto, 01.11.2026: danach ist z. B. „red“ das normalisierte Band).
- ⚙ am Ergebnis: gesperrte Schritte behalten ihre gespeicherten `measured`-Werte (Antwort Otto zu #269).

## 3. Soll (Otto)

1. **Vorschau:** Die messenden Methoden gehen auch ohne AOI (ganze Szene) und bei Flächen über 2048²; gemessen wird für die Vorschau auf einer Overview. Hinweis hinter (i): Vorschau geschätzt, der Job misst exakt.
2. **Job:** Ein gestarteter Job nimmt immer die **exakten** Werte über die ganze Fläche des Auftrags, unabhängig von ihrer Größe.

## 4. Im Plan klären (je Optionen, Empfehlung, bei Rechenrelevanz Quellen und Messung)

1. **Wo exakt gemessen wird:**
   - (a) im Job: erster Durchgang misst über die Fläche, zweiter normalisiert (Worker-Kern bleibt zustandslos: beide Durchgänge im selben Job, nichts zwischen Jobs gemerkt);
   - (b) vor dem Start in `api` über eine erweiterte Statistik-Route ohne Größengrenze (Start wartet);
   - (c) andere.
   Speicher, Laufzeit und gelesene Bytes für Sentinel-2 (eine Szene, ganze Szene und große AOI, ein und mehrere Bänder) messen.
2. **Rezept und Hash:** Bei (a) stehen im Rezept Methode und Parameter, nicht die Zahlen; die exakten Zahlen gehören in Herkunft und Metadaten des Ergebnisses. Folgen für `normalize`-Version, `resolved`, Hash, Cache, Runner (Runner rechnet gleich), alte Rezepte mit `measured` (weiter angenommen?), Permalink und Ablage. Bezug `adr/0014`, `adr/0016`, `adr/0020`.
3. **⚙ am Ergebnis (NM4-05b):** Die gesperrten Schritte behalten die Werte des Ergebnisses (Antwort Otto zu #269). Wie das mit (a) zusammengeht (z. B. die exakten Zahlen aus den Metadaten des Ergebnisses als feste Werte übernehmen).
4. **Stapel:** Jeder Auftrag misst für sich (wie heute); gleiche Werte für alle Aufträge bleibt Backlog-Punkt 60.
5. **Exaktheit:** Perzentile exakt (vollständige Sortierung bzw. Histogramm mit ausreichender Auflösung?) gegen Kosten; Recherche, wie andere es machen (etwa Google Earth Engine `reduceRegion` mit `scale`/`bestEffort`, openEO `quantiles`, rasterio/GDAL-Statistik), mit Quellen.
6. **Vorschau-Schätzung:** Overview-Stufe, Abweichung zur exakten Messung belegen (Tabelle für typische Bänder und Indizes).

## 5. Grenzen

- Modulgrenzen laut `architekturplan.md` 3.1; ausgehend nur über `gateway`; Worker-Kern zustandslos; `decomp.py` nicht anfassen.
- Oberflächentexte nur Englisch; wenig Text, Erklärungen hinter (i) bzw. im Tooltip.
- Keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Nachträge in ADRs heißen nach der Aufgabe („Nachtrag NM4-71“).
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 6. Abnahme

- Plan im Draft-PR mit Optionen, Empfehlung, Quellen und Messung; Otto gibt frei.
- Danach: Tests mit Gegenprobe (Job exakt auch über 2048², Vorschau ohne AOI, alte Rezepte, ⚙), bitgleich Job/Runner; Browserprüfung in Hell/Dunkel und schmalem Fenster; Prüfanleitung für Otto (Browser und PowerShell 5.1).
- Alle vier Pflicht-Checks grün; Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.
