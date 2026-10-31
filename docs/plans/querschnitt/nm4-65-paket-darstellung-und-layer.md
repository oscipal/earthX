# NM4-65 — Paket Darstellung und Layer-Manager

**Stand:** 31.10.2026, Wünsche und ein Fehler von Otto (Backlog-Punkt 65 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR, je Teil ein eigener Commit. Braucht ein Teil das Backend (z. B. Perzentile, falls die Statistik sie nicht liefert): im PR begründen, vor dem Code kurz an Otto.
**Modell:** Sonnet, Effort hoch.
**Start:** Frontend-Aufgabe (höchstens zwei Frontend-Sessions gleichzeitig), nach dem Merge von NM4-43e PR 2 (#255); nicht gleichzeitig mit NM4-64 (beide ändern `BandSelect.tsx` und die Darstellungsfelder).
**Startsatz:** „Führe Aufgabe NM4-65 aus `docs/plans/querschnitt/nm4-65-paket-darstellung-und-layer.md` aus.“

## 1. Wünsche (Otto, 31.10.2026, wörtlich)

> im layer manager will ich an der ganz linken seite eines layer ein 2x3 feld von kleinen punkten mit denen ich die layer mit der maus verschieben kann. das mit den layern auswahl im layer manager gefällt mir, aber ich hätte gerne die möglichkeit, dass ich ein band als eigenen layer speichere. Der layer name ist dann einfach der name des bandes. Generell will ich bei den layern immer das datum der aufnahme dabei stehen haben. und ganz generell will ich bei min max bzw vmin vmax auch die möglichkeit haben das zu switchen das ich perzentile eingeben kann. Opacity bei der box im geclickten layer lässt sich ausserdem nicht ganz nach rechts schieben (opacity ist aber 1, nur erscheint es im menü nicht so, im layermanager schon). Die reihenfolge Band vmin vmax colormap (und die bezeichnung (im processing manager heisst es min max)) soll immer die gleiche sein.

> Und dieses rufzeichen (resampled to a common grid) will ich nicht haben, stattdessen eine kurze warnung die zu bestätigen ist, mit genauer beschreibung was das bedeutet.

## 2. Teile

1. **Ziehen zum Ordnen:** Ganz links in jeder Zeile des Layer-Managers (auch „Results“) ein Griff aus 2 × 3 kleinen Punkten; damit lässt sich die Zeile mit der Maus verschieben. ▲/▼ bleiben für Tastatur und Screenreader. Die Ebenenfolge (NM4-59) folgt der Liste.
2. **Band als eigener Layer:** Bei einem Ergebnis-Layer mit mehreren Bändern lässt sich das gerade gewählte Band als eigener Layer anheften (z. B. Menü der Zeile „Add band as layer“). Name des neuen Layers = Bandname. Er übernimmt die Darstellung des Bandes; Darstellung und „Save“ sind danach unabhängig vom Ursprungs-Layer.
3. **Datum der Aufnahme bei jedem Layer:** Jede Zeile im Layer-Manager zeigt das Aufnahmedatum (UTC, YYYY-MM-DD; Spanne bei mehreren Szenen; bei Daten ohne Zeitachse wie dem DEM keins). Gilt für Szenen-, Ergebnis- und Band-Layer.
4. **Perzentile statt Werte:** Bei vmin/vmax ein kleiner Umschalter „value / %“. Bei „%“ gibt Otto Perzentile ein (z. B. 2 und 98); die Werte ergeben sich aus der Statistik des Bandes (Vorschau: Messung aus NM4-19; Layer: `properties.bands[].statistics`). Gilt überall, wo vmin/vmax vorkommen (Ansicht, Processing-Vorschau, Layer-Manager). „Save“ speichert, welche Art eingegeben wurde.
5. **Fehler Opacity:** Im Einstellungsfeld eines angeklickten Layers lässt sich der Regler nicht ganz nach rechts schieben bzw. zeigt bei Opacity 1 nicht ganz rechts an (im Layer-Manager selbst richtig). Nachstellen, Ursache nennen, beheben; Test.
6. **Gleiche Reihenfolge und Namen:** Überall dieselbe Reihenfolge **Band · vmin · vmax · colormap** und dieselben Bezeichnungen („vmin“/„vmax“, nicht „min“/„max“ im Processing-Panel). Gemeinsame Komponente, keine zweite Variante. Bei „RGB“ (NM4-64) entfällt colormap.
7. **Warnung statt Rufzeichen „Resampled to a common grid“** (ersetzt Backlog-Punkt 51): kein Rufzeichen mehr. Werden Wertebänder auf ein gemeinsames Raster umgerechnet (verschiedene Auflösungen oder CRS/UTM-Zonen; nicht bei bloßer Maskenschicht), erscheint beim Start des Jobs (bzw. bei „Review“) eine kurze Warnung zum Bestätigen („Continue“ / „Cancel“) mit genauer Beschreibung: welche Bänder auf welches Raster (Auflösung, CRS) gebracht werden, mit welcher Methode (z. B. nearest/bilinear) und was das für die Werte bedeutet (Werte an Pixelgrenzen ändern sich, keine neuen Werte bei nearest). Text kurz, Englisch. Ob die Warnung je Auftrag nur einmal kommt: im PR vorschlagen.

8. **Schließen überall gleich** (Otto, 31.10.2026: „das < close button beim layer soll auch ein kleines rotes "x" werden (consistency!!)“): Der Knopf „‹ Close“ in den Einstellungen eines Layers wird ein kleines rotes „x“ (Tooltip „Close“). Die Session sucht alle Stellen, an denen etwas geschlossen wird (Panels, Popups wie „Advanced search“, Fenster wie Download, Einstellungen), und stellt sie auf dieselbe Komponente um; Liste im PR. „Clear search results“ (rotes ✕ mit Text) bleibt, wie es ist.

9. **Durchblättern der Layer (Otto, 31.10.2026):** „im layer manager hätt ich im Kopf gerne einen button der das scrollen durch die layer leicht erlaubt. Also es wird dann immer der angeclickte layer ganz oben angezeigt (ohne tatsächlich nach oben zu wandern sondern nur gehighlited, dann kann ich entweder mit den pfeiltasten durchgehen oder mit dem mausrad)“.
   - Ein Umschalter im Kopf des Layer-Managers (Symbol, Tooltip z. B. „Flip through layers“).
   - Ist er an, wird der angeklickte bzw. gewählte Layer **auf der Karte** über allen anderen Layern gezeichnet (unter AOI, Zeichnung und Umrissen), ohne dass sich die Reihenfolge in der Liste ändert; seine Zeile ist hervorgehoben.
   - Mit ↑/↓ oder dem Mausrad **über der Liste** wechselt die Wahl zum nächsten Layer (das Mausrad über der Karte zoomt weiter).
   - Aus (Umschalter oder Esc): die Karte zeigt wieder die echte Reihenfolge. Sichtbarkeit (Auge) wird respektiert; ausgeblendete Layer werden übersprungen oder kurz gezeigt – im PR vorschlagen.

## 3. Grenzen

- Oberflächentexte nur Englisch; wenig Text, Erklärungen im Tooltip; nicht Mögliches ausblenden statt ausgrauen.
- Keine neue Abhängigkeit ohne Frage an Otto (Ziehen mit eigener Logik oder HTML-Drag-and-Drop).
- Keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Nachträge heißen nach der Aufgabe („Nachtrag NM4-65“).
- Bilder nicht ins Repo.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 4. Abnahme

- Tests je Teil mit Gegenprobe (Opacity-Fehler mit Test für Ottos Weg).
- Prüfung im echten Browser (Playwright), Hell/Dunkel, schmales Fenster; Ziehen auch mit Tastatur-Ersatz (▲/▼).
- Prüfanleitung für Otto im PR, gegliedert nach Teil.
- Alle vier Pflicht-Checks grün.
- Log-Zeilen mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern.
- Vor „fertig“ ist main geholt.

## 5. Nachtrag NM4-65 (1.11.2026, Draft-PR [#266](https://github.com/oscipal/earthX/pull/266))

**Umgesetzt:** Teile 1, 2, 3, 5, 6, 8, 9, je ein Commit; Einzelheiten und Auslegungen im Log (Zeile „NM4-65 umgesetzt“) und in der PR-Beschreibung, dort auch die Prüfanleitung.

- **Teil 5, Ursache:** `.vc-field input` traf auch `input[type=range]`; Padding und Rahmen eines Textfelds verkleinerten die Spur im eigenen Kasten, der Wert war immer 1.
- **Teil 6:** Die Ansicht hat noch kein Band-Feld (NM4-45); `RenderFields` lässt es weg, die Reihenfolge bleibt Band · Index · vmin · vmax · Colormap. NM4-54 setzt das Band-Feld dort ein.
- **Teil 8, Liste der geschlossenen Stellen:** Layer-Einstellungen, Processing-Panel, Job-Details, Download-Fenster (drei Fassungen), „Advanced search“. Nicht umgestellt, weil sie nichts schließen: „Clear search results“, „✕ Clear“ der Ansicht, Entfernen von Layern, Schritten, Gruppen und Links, Toasts, das ✕ im Eingabefeld.
- **Aufräumen älterer Browser-Skripte:** `layer-settings`, `view-index`, `band-dropdowns`, `layer-rows` an die neuen Knöpfe und die Reihenfolge angepasst; `layer-settings` hat zwei Fälle, die schon an „Apply to all“ (#257) scheitern.

**Teile 4 und 7 (Antwort Otto, 1.11.2026: Backend erweitern, jeweils Option 1):** umgesetzt, im selben PR.

- **Teil 4:** Backend `percentile_1`…`percentile_99` in der AOI-Messung und neue Route `GET /results/{id}/statistics` (adr/0006 Nachtrag NM4-65); Frontend: Umschalter „value / %“ am Feld vmin in `RenderFields`, die Werte kommen in der Ansicht aus der Item-Statistik (`p=`), in der Vorschau aus der Messung (sonst `p=` auf der ersten Szene), im Ergebnis-Layer aus der neuen Route; der Look behält die Eingabe als `percent`.
- **Teil 7:** Backend `resampling` in der Kostenschätzung (adr/0014 Nachtrag NM4-65); Frontend: Warnung zum Bestätigen vor „Start job“, einmal je Auftrag; das Rufzeichen ist entfernt.
- **Offen:** Eine Szene im selben CRS mit anderer Pixelgröße oder anderem Ursprung warpt der Job; die Schätzung erkennt das aus den Item-Metadaten nicht sicher und meldet es nicht. Soll `scenes` das später über `proj:transform`/`proj:bbox` mit nennen?
