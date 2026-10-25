# NM4-26 — Kacheln schneller: Durchsatz von `tiler` und `gateway`

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 26 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Messung, Recherche und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** hohe Priorität; sofort möglich (Backend). Höchstens zwei Stufe-B-Sessions gleichzeitig; nicht gleichzeitig mit NM4-04 oder NM4-19 (`tiler`).
**Startsatz:** „Führe Aufgabe NM4-26 aus `docs/plans/querschnitt/nm4-26-kachel-leistung.md` aus.“

## 1. Anlass

Ottos Messung im Browser (25.10.2026, lokal mit `docker compose`): Eine NDVI-Vorschau braucht rund 40 s für 325 Anfragen. Einzelne Kacheln (rund 30–35 kB) brauchen 1,7 bis 6,5 s, mit gleichmäßig steigenden Zeiten – die Anfragen warten in einer Schlange. Auch reine `visual`-Kacheln ohne Rechnung brauchen 2,6 bis 4,2 s. Dasselbe Bild schon vor UI-01a (Stand `745ecb2`), es ist also keine Regression aus UI-01a. Daneben: Die Suche (`search`, je 1,9 MB) wird beim Öffnen dreimal geladen, und eine `statistics`-Anfrage mit `op` endete mit `400`.

## 2. Soll

- Kacheln einer Ansicht kommen deutlich schneller; das Ziel legt der Plan nach der Messung fest (Vorschlag: eine typische Ansicht in unter 10 s, einzelne Kachel ohne Warteschlange unter 1 s).
- Die Suche wird beim Öffnen genau einmal geladen.
- Die `statistics`-Anfrage der Vorschau scheitert nicht mehr mit `400` (Ursache finden; falls Frontend falsche Parameter schickt, dort beheben).

## 3. Umfang

- **Messung zuerst** (lokal in der Session, synthetische Quelle über die Testnähte und, wo möglich, Zeitanteile im Code): Zeit je Kachel aufgeteilt in Warten, Item holen, COG-Lesen über `gateway`, Rechnen, Kodieren. Tabelle im PR.
- **Recherche mit Quellen (Pflicht, rechenrelevant):** Gleichzeitigkeit im `tiler` (Prozesse/Threads von uvicorn, Threadpool von FastAPI/Starlette für synchrone Routen, rio-tiler-Empfehlungen), GDAL-Einstellungen für entfernte COGs (`GDAL_HTTP_MULTIPLEX`, `GDAL_HTTP_VERSION`, `VSI_CACHE`, `GDAL_CACHEMAX`, `GDAL_DISABLE_READDIR_ON_OPEN`, `CPL_VSIL_CURL_ALLOWED_EXTENSIONS`), Verbindungen offen halten über `gateway` (Keep-Alive, Pool), Item-Cache.
- Die doppelte bzw. dreifache Suche im Frontend: Ursache (Effekt mit wechselnden Abhängigkeiten, StrictMode, Neuaufbau) finden und beheben.

## 4. Im Plan klären (mit Optionen und Empfehlung)

- Welche Stellschrauben zuerst (Gleichzeitigkeit, GDAL, Verbindungen, Caches) – mit Zahlen und Kosten (Speicher je Prozess, Grenze 500 MB im Worker gilt nicht für den `tiler`, aber Speicher des Hosts nennen).
- Wirkung auf die Bitgleichheit Kachel ↔ Job (darf sich nicht ändern; Tests aus `adr/0014` §6.3 laufen weiter).
- Ob etwas davon `docker-compose.yml` braucht (Variablen, Prozesszahl) und wie es in Produktion aussieht.

## 5. Grenzen

- Ausgehende Requests bleiben ausschließlich über `gateway`; die Prüfungen in `gateway` (B8/B9) werden nicht gelockert.
- `.github/` bleibt unverändert.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 6. Abnahme

- Messung vorher/nachher mit derselben Methode im PR; Test für „Suche genau einmal“ und für die `statistics`-Ursache, die am alten Code scheitern; Bitgleich-Tests weiter grün.
- Nachtrag in `adr/0006` bzw. `architekturplan.md`, falls sich Gleichzeitigkeit oder Verbindungen grundlegend ändern.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
