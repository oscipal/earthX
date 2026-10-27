# NM4-35 — Relief (Schummerung) als Overlay und optional als Basemap

**Stand:** 27.10.2026, beauftragt von Otto (Backlog-Punkt 35; Vorschlag aus dem Plan von UI-02, §6).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Recherche und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach dem Merge von UI-02a (Basemap-Menü). Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-35 aus `docs/plans/querschnitt/nm4-35-relief.md` aus.“

## 1. Anlass

UI-02 hat eine Schummerung aus dem eigenen Copernicus DEM geprüft: Der `tiler` weist `algorithm` heute ab, und eine weltweite Grundkarte ginge nur mit einer vorab gerechneten Pyramide im eigenen Speicher. Otto möchte das Relief trotzdem (27.10.2026) – als Overlay über jeder Basemap und optional als eigene Basemap „Relief“.

## 2. Soll

- Schalter „Relief“ in der Gruppe „Overlays“ des Basemap-Menüs (UI-02): halbtransparente Schummerung über jeder Basemap, unter den eigenen Bildern und unter den Labels.
- Optional eine Basemap „Relief“ (graue Schummerung allein).
- Die Wahl wird im Browser gemerkt wie die übrigen Einstellungen des Menüs; Permalink wie Basemap und Projektion (gilt für die Ansicht, überschreibt die gespeicherte Vorgabe nicht, UI-02 Frage 8).

## 3. Im Plan klären (mit Optionen und Empfehlung)

- **Option A (Vorschlag):** MapLibre zeichnet die Schummerung selbst im Browser (Ebene `hillshade`, Quelle `raster-dem`) aus freien Höhenkacheln ohne Schlüssel, etwa AWS „Terrain Tiles“ (Terrarium) aus der Registry of Open Data. Kein Backend, keine Pyramide. Mit Quellen prüfen: Lizenz und Attribution der Höhendaten, Verfügbarkeit, Ratenlimits, CORS, Datenschutz (Kacheln lädt der Browser direkt, wie die Basemaps).
- **Option B:** Höhenkacheln aus dem eigenen Copernicus DEM über den `tiler` (Terrarium- oder Terrain-RGB-Kodierung) und Schummerung in MapLibre; dafür vorab gerechnete Pyramide für niedrige Zoomstufen im eigenen Speicher. Aufwand, Speicher, Kosten.
- **Option C:** Schummerung als fertiges Bild aus dem `tiler` (Algorithmus `hillshade`). Kosten je Kachel, Zoomgrenzen.
- Darstellung: Beleuchtungsrichtung, Überhöhung, Deckkraft (feste Vorgabe, keine Einstellmöglichkeit nötig); Verhalten im Globus.

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip.
- Keine neue Abhängigkeit ohne Frage an Otto; keine Schlüssel oder Secrets.
- Bei Option A gilt die Regel „ausgehende Requests nur über `gateway`“ nicht (Browser lädt direkt, wie Basemaps); im Plan ausdrücklich festhalten.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Schalter und Basemap aus dem Menü, Reihenfolge der Ebenen (Relief unter eigenen Bildern und Labels), Merken im Browser, Permalink.
- Prüfung im echten Browser (Playwright), Hell/Dunkel, Mercator und Globus; Prüfanleitung für Otto im PR.
- Attribution der Höhendaten sichtbar (UI-02 Frage 4).
- Alle vier Pflicht-Checks grün; Log-Zeile mit PR-Nummer (Backlog pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.
