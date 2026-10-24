# UI-02 — Basemap-Auswahl und Projektion
 
**Stand:** 12.10.2026, beauftragt von Otto; ergänzt am 24.10.2026 (§3 Permalink).
**Meilenstein:** UI, direkt nach M4 (nach M4-20).
**Stufe B mit Recherche:** Plan mit Quellen im Draft-PR, Otto gibt frei, dann Code.
**Modell:** Opus (Effort hoch) für Plan und Recherche, Sonnet (Effort hoch) für die Umsetzung.
**Start:** Nach M4-20. Läuft nicht gleichzeitig mit UI-01, weil beide die Kartenschalter berühren.
**Startsatz:** „Führe Aufgabe UI-02 aus `docs/plans/vp3/ui-02-basemap-projektion.md` aus.“
 
## 1. Wünsche von Otto (12.10.2026)
 
1. Der Button „Mercator“ oben rechts entfällt. Ein Basemap-Menü ersetzt ihn.
2. **Basemaps:**
   - Satellitenbild
   - Straßenkarte
   - nur Umrisse (Küsten, Grenzen)
   - weitere Vorschläge willkommen
3. **Projektionen** im selben Menü:
   - Mercator
   - Globus
   - Equal Earth, falls möglich
Vorschläge für weitere Ebenen, im Plan zu bewerten:
- Schummerung aus dem eigenen Copernicus DEM
- Beschriftungen ein- und ausblendbar
- Gradnetz
- Sentinel-2-Kachelraster (MGRS) als Overlay
- der heutige Schalter „Light“ und gegebenenfalls „Dark“, eingegliedert ins Menü
## 2. Recherche mit Quellen (Pflicht vor jeder Empfehlung)
 
1. **Anbieter je Basemap.** Für jeden Anbieter:
   - **Lizenz:** Ist kommerzielle Nutzung erlaubt? Das Repo ist AGPL, die Plattform kann später kommerziell betrieben werden. Viele Satelliten-Basemaps sind nur nichtkommerziell nutzbar.
   - **Nutzungsregeln:** zum Beispiel die Tile Usage Policy von OSM, die keine starke Nutzung erlaubt.
   - **Attribution**
   - **API-Schlüssel:** Keine Secrets im Repo. Anbieter ohne Schlüssel bevorzugen. Braucht ein Anbieter einen Schlüssel, ist das eine Frage an Otto.
   - **Selbst hosten:** etwa PMTiles oder Protomaps, mit Aufwand und Speicherbedarf.
2. **Datenschutz.** Basemap-Kacheln lädt der Browser direkt bei Dritten. Die Regel „ausgehende Requests nur über `gateway`“ gilt für das Backend. Klären:
   - ob ein Hinweis für die Nutzer nötig ist,
   - ob ein Weg über die eigene Plattform sinnvoll wäre.
3. **Projektionen.**
   - Welche Projektionen kann die Kartenbibliothek des Frontends (Version im Lockfile)? Globus und Mercator wahrscheinlich ja.
   - Equal Earth: Geht das mit Kachelkarten überhaupt? Mit welchem Aufwand, etwa Wechsel der Bibliothek oder Reprojektion im Browser?
   - Was passiert mit den eigenen Ebenen (Kacheln aus dem Tiler, AOI-Zeichnung, Footprints, Coverage-Map) in jeder Projektion?
   - Am Code prüfen, nicht annehmen.
4. **Schummerung aus dem DEM.**
   - Geht das über den vorhandenen Tiler?
   - Wie steht es um die Regeln für `expression` und Algorithmen (`DefaultRender`, R5 aus M4-09)?
   - Was kostet es?
## 3. Im Plan mit Optionen und Empfehlung
 
- Auswahl der Basemaps und Anbieter, mit einer Tabelle zu Lizenz, Nutzungsregeln, Schlüssel und Attribution.
- Welche Projektionen jetzt kommen, welche später und welche nicht.
- Aufbau des Menüs (Englisch) und die Vorgabe beim ersten Start.
- Wird die Wahl des Nutzers im Browser gemerkt?
- **Permalink (aus M4-19e, 24.10.2026):** Der Permalink speichert heute keine Basemap, weil es nur eine gibt. Mit der Auswahl kommen Basemap und Projektion in den gespeicherten Zustand des Permalinks; ältere Permalinks ohne diese Felder öffnen mit der Vorgabe.
## 4. Grenzen
 
- Keine Secrets im Repo. Keine neue Abhängigkeit ohne Frage an Otto.
- Oberflächentexte nur auf Englisch.
- Attribution immer sichtbar, wie es die Lizenz verlangt.
- Backend nur, falls die Schummerung es braucht, und dann im Plan begründet.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.
## 5. Abnahme
 
- Für jede Basemap und Projektion gibt es einen Test, dass die Auswahl greift und die Attribution stimmt.
- Die eigenen Ebenen bleiben in jeder angebotenen Projektion lagerichtig, belegt mit einem Test oder einer Prüfanleitung.
- Alle vier Pflicht-Checks der CI sind grün.
- Prüfanleitung für Otto (Browser).
- Log-Zeilen.
- Vor „fertig“ ist main geholt.
