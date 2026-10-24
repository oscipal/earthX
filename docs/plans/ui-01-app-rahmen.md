# UI-01 — App-Rahmen mit linker Leiste und Processing-Manager
 
**Stand:** 12.10.2026, ergänzt am 20.10.2026 (§1 Punkte 6–7, §3 Punkt 7, §4), 22.10.2026 (§1 Punkte 10 und 12) und 24.10.2026 (§1 Punkte 6 und 11), beauftragt von Otto.
**Meilenstein:** UI, direkt nach M4 (nach M4-20). Nummer und Name des Meilensteins stehen in `projektplan.md` noch aus.
**Stufe B:** Erst kommt der Plan im Draft-PR, Otto gibt ihn frei, dann folgt der Code.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** Nach M4-20. Die Aufgabe läuft nicht gleichzeitig mit einer anderen Aufgabe, die das Frontend-Layout ändert.
**Startsatz:** „Führe Aufgabe UI-01 aus `docs/plans/ui-01-app-rahmen.md` aus.“
 
## 1. Wünsche von Otto (12.10. und 20.10.2026)
 
1. **Linke Leiste.** Am linken Rand gibt es eine schmale, immer sichtbare Leiste mit je einem Symbol für:
   - das Control-Menü,
   - den Layer-Manager,
   - den Processing-Manager.
2. **Layer-Manager.** Er hängt fest am linken Rand neben der Leiste und ist nicht mehr frei schwebend wie heute.
3. **Processing-Manager.** Er zeigt nur laufende und fertige Jobs, je Job genau:
   - den Titel, vom Nutzer umbenennbar,
   - den Fortschritt,
   - das Ablaufdatum.
4. **Nicht löschbar.** Jobs lassen sich nicht löschen, nur archivieren und in eigene Gruppen einordnen (anlegen, umbenennen, zuordnen).
5. **Filter.** Man wählt zwischen „Active“ und „All“ (aktive und archivierte Jobs).
6. **Batch als ein Eintrag (20.10.2026).** Die Jobs eines Batches aus M4-13c-4 („One job per pass/scene“) erscheinen als **ein** Eintrag:
   - mit gemeinsamem Titel, Gesamtfortschritt (fertig, laufend, abgewiesen, gescheitert) und dem frühesten Ablaufdatum,
   - aufklappbar zu den einzelnen Teilen.
   Im Backend bleiben es einzelne Jobs: ein Raster je Job, Cache je Teil, Fehler je Teil getrennt, parallel in der Queue (M4-12 §5).
   **Share bei einem Batch (24.10.2026):** In M4-19e ist „Share“ für Stapel gesperrt. Der Plan schlägt vor, ob UI-01 einen Permalink für den ganzen Batch anbietet (ein Link, mehrere Aufträge) oder es bei der Sperre mit Grund bleibt.
7. **„Download all (ZIP)“ (20.10.2026).** Je Batch gibt es ein ZIP mit allen fertigen Teilergebnissen, je Teil ein Ordner mit dem Inhalt des Job-ZIP (Sollliste aus M4-30). Teile, die abgelaufen oder gescheitert sind, fehlen; welche das sind, steht in einer kurzen Liste im ZIP.
8. **Gleiche Breite der Layer-Zeilen (20.10.2026).** Alle Einträge im Layer-Manager sind gleich breit. Die Knöpfe stehen immer an derselben Stelle, auch wenn bei einem Layer ein Knopf fehlt, etwa „Download“. Ein fehlender Knopf lässt einen leeren Platz, statt die anderen zu verschieben.
9. **Ergebnisse aus dem Layer-Manager laden (20.10.2026).** Ein Ergebnis-Layer (Job-Ergebnis, M4-13c-5) hat einen Download-Knopf. Er lädt dasselbe Job-ZIP wie das Panel (Sollliste aus M4-30), ohne zweiten Weg. Ist das Ergebnis abgelaufen, ist der Knopf gesperrt und nennt den Grund.
10. **Reihenfolge greift immer (20.10.2026).**
    - **Befund:** Auch nach M4-28 ändert sich auf der Karte manchmal nichts, wenn man die Reihenfolge der Layer ändert.
    - **Vorgehen:** Zuerst die Ursache finden, mit einem Test, der am Code vor UI-01 scheitert. Otto liefert beim Start die Schritte, mit denen es auftritt.
    - **Ort der Behebung:** in der gemeinsamen Layer-Logik (`mapLayers`, Store), nicht nur in der neuen Optik.
    - **Prüfung:** nach jedem Umsortieren mit allen Layer-Arten (Quicklook, Vollauflösung, Vorschau, Ergebnis, Mosaik aus M4-17).
    - **Stapelung zwischen Überflügen (22.10.2026):** Die offene Ansicht und die angehefteten Layer stapeln mehrere Überflüge heute verschieden (bekannte Grenze aus M4-17c, Plan §15). Soll: gleiche Auswahl, gleiche Reihenfolge, gleiches Bild; dazu ein Test, der am Code vor UI-01 scheitert.
11. **Klick auf einen Ergebnis-Layer (20.10.2026).**
    - **Heute:** Es erscheinen die Suchergebnisse.
    - **Soll:** Es erscheint dieselbe Ansicht wie bei anderen Layern, bezogen auf das Ergebnis: Wertebereich (vmin, vmax), Colormap und Deckkraft, mit der Vorgabe aus der Statistik (M4-32).
    - **Keine Einheiten im Layer-Manager (Otto, 24.10.2026):** Weder Zeilen noch Darstellung im Layer-Manager zeigen eine Einheit, bei keiner Layer-Art. Einheiten stehen im Processing-Panel (Band-Chips, M4-19b) und in den Daten (`bands[].unit`).
    - **Nicht in UI-01:** Processing auf einem Ergebnis, also ein Ergebnis als Eingabe eines neuen Rezepts. Das braucht vorher eine Entscheidungsvorlage (Stufe C, siehe `claude/nach-m4-backlog.md`). Bis dahin ist der Processing-Knopf bei Ergebnis-Layern gesperrt und nennt den Grund.
12. **Nur „Download (ZIP)“ je fertigem Job (22.10.2026).**
    - Ein fertiger Job zeigt in Liste und Details nur noch „Download (ZIP)“.
    - Die Einträge „Methods“ und „Copy“ aus M4-19a entfallen. Es gibt **nirgends** einen Knopf, der den Methodentext kopiert.
    - Der Methodentext bleibt im ZIP. Er wandert nach M4 als Feld in `recipe.json` (`claude/nach-m4-backlog.md`).
    - Der Link `methods` im Ergebnisdokument der API bleibt bestehen.
## 2. Stand vor der Aufgabe
 
- **Vorher lesen:** den Stand des Frontends nach M4-13c lesen (Panel, Jobliste „⚙ Jobs (n)“, Batch aus c-4, Layer-Manager nach M4-28, Control-Menü, Kartenschalter).
- **Pläne:** `plans/m4-13-processing-panel.md`, `plans/m4-13c-vorschau-und-viewer.md` und `plans/m4-zusaetze-2026-10-12.md` §2.
- **Keine Konten bis M6.** Ein Job ist nur über seine zufällige `jobID` erreichbar. Eine Liste aller Jobs gibt es absichtlich nicht (`adr/0013`).
- **Ablauf.** Ergebnisse laufen nach 7 Tagen ab (`410`).
- **Wieder starten.** Ein Job lässt sich erst mit M4-19 (Permalinks, „Parameter übernehmen“) wieder starten.
- **Speicher im Browser.** Die Titel der Jobs liegen seit M4-13c-4 im `sessionStorage` und gehen beim Schließen des Tabs verloren.
- **Job-ZIP.** Seit M4-11b-1 streamt `api` das ZIP eines Jobs, mit Fortsetzen über ETag und ZIP64; den Inhalt legt M4-30 an einer Stelle fest.
## 3. Im Plan mit Optionen und Empfehlung klären
 
1. **Ablage.** Titel, Gruppen, Batch-Zugehörigkeit, der Status „archiviert“ und ein von Hand gesetzter Farbbereich je Job (M4-32b) liegen bis M6 nur im Browser, dauerhaft und nicht mehr im `sessionStorage`. An der API für einzelne Jobs ändert sich nichts.
   - Wie wird gespeichert (Schlüssel, Version des Formats, Übernahme der Titel aus dem `sessionStorage`)?
   - Was passiert in einem privaten Fenster oder bei gelöschten Browserdaten?
   - Der Nutzer erfährt das in einem Satz (Englisch).
2. **Vorgabetitel.** Der Titel wird aus Operator, Datensatz und Datum gebildet, zum Beispiel „NDVI · sentinel-2-c1-l2a · 12 Oct“.
3. **Abgelaufene Jobs.** Sie bleiben mit dem Status „Expired“ sichtbar. Bleibt eine Kopie von `recipe.json` im Browser, damit M4-19 den Job später wieder starten kann? Die AOI bleibt dabei nur im Browser.
4. **„Nicht löschbar“ und laufende Jobs.**
   - Bleibt „Cancel“ für laufende Jobs (OGC `dismiss`), auch für einen ganzen Batch?
   - Ruft das Panel `DELETE` für fertige Jobs gar nicht mehr auf?
5. **Details eines Jobs.** Die Liste zeigt nur Titel, Fortschritt und Ablaufdatum. Wo erscheinen Schritte, Download und Fehlermeldung? Vorschlag: Ein Klick auf den Job öffnet das Processing-Fenster mit diesem Job. Als Aktion gibt es dort nur „Download (ZIP)“, keine Anzeige und kein Kopieren des Methodentexts (§1 Punkt 12).
6. **Leiste und Panels.**
   - Breite, Symbole, Tooltips (Englisch), Tastatur und Screenreader.
   - Was passiert auf schmalen Bildschirmen?
   - Darf mehr als ein Panel gleichzeitig offen sein?
   - Wohin wandert das heutige „⚙ Jobs (n)“?
7. **„Download all (ZIP)“.**
   - **Neue Route:** Nötig ist eine Route in `api`, etwa `POST /processing/bundles`, mit der Liste der `jobID`s im Body (nie in der URL). Sie setzt das ZIP aus den einzelnen Job-ZIPs zusammen und nutzt dabei denselben Code wie M4-11b-1 (Streaming, ZIP64, Inhalt aus der Definition von M4-30). Keine neue Ablage im Objektspeicher.
   - **Grenzen:** höchstens 25 Teile wie beim Batch, Größe und Deckel. Klären, ob 5 GB je Bündel gelten oder eine eigene Grenze.
   - **Fortsetzen:** Ist das fortsetzbar wie das Job-ZIP? Wie entsteht der ETag aus den Teilen?
   - **Datenschutz:** keine `jobID`s und keine AOI in Logs oder URLs.
## 4. Grenzen
 
- Schwerpunkt Frontend.
- Backend nur für die Bündel-Route aus §3 Punkt 7, mit Wiederverwendung des Codes aus M4-11b-1 und M4-30 und ohne neue Abhängigkeit. Für einzelne Jobs ändert sich an der API nichts.
- Oberflächentexte ausschließlich auf Englisch.
- Bestehende Funktionen bleiben erreichbar. Der Plan listet jede verschobene Funktion mit ihrem neuen Ort auf.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.
## 5. Abnahme
 
- Tests sind grün für:
  - Leiste, Manager, Archiv, Gruppen, Filter, Umbenennen und Neuladen mit gespeicherten Jobs,
  - Batch als ein Eintrag mit Aufklappen und Gesamtfortschritt,
  - „Download all (ZIP)“ mit allen Teilen, mit abgelaufenen bzw. gescheiterten Teilen und über der Grenze,
  - gleiche Breite und feste Knopfpositionen der Layer-Zeilen, auch ohne Download-Knopf,
  - Download eines Ergebnis-Layers, auch im abgelaufenen Zustand,
  - Reihenfolge nach jedem Umsortieren mit allen Layer-Arten; der Test zum Befund aus Punkt 10 scheitert am alten Code,
  - Ansicht und angeheftete Layer stapeln mehrere Überflüge gleich (Punkt 10),
  - Klick auf einen Ergebnis-Layer öffnet die Ansicht für Darstellung (vmin, vmax, Colormap), nicht die Suchergebnisse,
  - ein fertiger Job zeigt nur „Download (ZIP)“; kein „Methods“ und kein „Copy“ irgendwo im Frontend (Gegenprobe gegen den Stand nach M4-19a).
- Alle vier Pflicht-Checks der CI sind grün.
- Im PR liegt eine Prüfanleitung für Otto (Browser und PowerShell).
- Log-Zeilen für Ottos Antworten.
- Vor „fertig“ ist main geholt.
