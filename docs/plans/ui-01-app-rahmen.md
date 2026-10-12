# UI-01 — App-Rahmen mit linker Leiste und Processing-Manager

**Stand:** 12.10.2026, beauftragt von Otto.
**Meilenstein:** UI, direkt nach M4 (nach M4-20). Nummer und Name des Meilensteins stehen in `projektplan.md` noch aus.
**Stufe B:** Erst kommt der Plan im Draft-PR, Otto gibt ihn frei, dann folgt der Code.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** Nach M4-20. Die Aufgabe läuft nicht gleichzeitig mit einer anderen Aufgabe, die das Frontend-Layout ändert.
**Startsatz:** „Führe Aufgabe UI-01 aus `docs/plans/ui-01-app-rahmen.md` aus.“

## 1. Wünsche von Otto (12.10.2026)

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

## 2. Stand vor der Aufgabe

- **Vorher lesen:** Den Stand des Frontends nach M4-13c lesen: Panel, Jobliste „⚙ Jobs (n)“, Layer-Manager, Control-Menü, Kartenschalter.
- **Pläne:** `plans/m4-13-processing-panel.md` und `plans/m4-zusaetze-2026-10-12.md` §2.
- **Keine Konten bis M6.** Ein Job ist nur über seine zufällige `jobID` erreichbar. Eine Liste aller Jobs gibt es absichtlich nicht (`adr/0013`).
- **Ablauf.** Ergebnisse laufen nach 7 Tagen ab (`410`).
- **Wieder starten.** Ein Job lässt sich erst mit M4-19 (Permalinks, „Parameter übernehmen“) wieder starten.

## 3. Im Plan mit Optionen und Empfehlung klären

1. **Ablage.** Titel, Gruppen und der Status „archiviert“ liegen bis M6 nur im Browser. Für die API ändert sich nichts.
   - Wie wird gespeichert (Schlüssel, Version des Formats)?
   - Was passiert in einem privaten Fenster oder bei gelöschten Browserdaten?
   - Der Nutzer erfährt das in einem Satz (Englisch).
2. **Vorgabetitel.** Der Titel wird aus Operator, Datensatz und Datum gebildet, zum Beispiel „NDVI · sentinel-2-c1-l2a · 12 Oct“.
3. **Abgelaufene Jobs.** Sie bleiben mit dem Status „Expired“ sichtbar. Bleibt eine Kopie von `recipe.json` im Browser, damit M4-19 den Job später wieder starten kann? Die AOI bleibt dabei nur im Browser.
4. **„Nicht löschbar“ und laufende Jobs.**
   - Bleibt „Cancel“ für laufende Jobs (OGC `dismiss`)?
   - Ruft das Panel `DELETE` für fertige Jobs gar nicht mehr auf?
5. **Details eines Jobs.** Die Liste zeigt nur Titel, Fortschritt und Ablaufdatum. Wo erscheinen Schritte, Download und Fehlermeldung? Vorschlag: Ein Klick auf den Job öffnet das Processing-Fenster mit diesem Job.
6. **Leiste und Panels.**
   - Breite, Symbole, Tooltips (Englisch), Tastatur und Screenreader.
   - Was passiert auf schmalen Bildschirmen?
   - Darf mehr als ein Panel gleichzeitig offen sein?
   - Wohin wandert das heutige „⚙ Jobs (n)“?

## 4. Grenzen

- Nur Frontend. Keine Änderung an API oder Backend.
- Oberflächentexte ausschließlich auf Englisch.
- Bestehende Funktionen bleiben erreichbar. Der Plan listet jede verschobene Funktion mit ihrem neuen Ort auf.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Die Tests für Leiste, Manager, Archiv, Gruppen, Filter, Umbenennen und Neuladen mit gespeicherten Jobs sind grün.
- Alle vier Pflicht-Checks der CI sind grün.
- Im PR liegt eine Prüfanleitung für Otto (Browser).
- Log-Zeilen für Ottos Antworten.
- Vor „fertig“ ist main geholt.
