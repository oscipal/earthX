# M4-28 — Layer-Manager reparieren: Tempo, Reihenfolge, falsche Layer

**Stand:** 19.10.2026, beauftragt von Otto.
**Stufe A, mit Diagnose zuerst:** Ursachen im PR belegen, dann beheben. Ändert die Behebung die Bedienung, ist das eine Frage an Otto.
**Modell:** Sonnet, Effort hoch.
**Start:** Nach dem Merge von M4-13c-2 (#153), weil c-2 Vorschau-Layer und „Replace source layer“ einführt. Vor M4-13c-5, das Job-Ergebnisse als Layer bringt. Läuft nicht gleichzeitig mit einer anderen Aufgabe, die Layer oder Kartenquellen ändert.
**Startsatz:** „Führe Aufgabe M4-28 aus `docs/plans/m4-28-layer-manager-reparieren.md` aus.“

## 1. Befund (Otto, lokal im Browser, 19.10.2026)

1. **Langsam:** Schaltet man einen Layer ein oder aus, dauert es sehr lange, bis er wieder erscheint.
2. **Reihenfolge:** Oben in der Liste ist nicht immer oben auf der Karte.
3. **Falscher Layer:** Beim Ein- oder Ausschalten werden manchmal andere Layer geschaltet als der angeklickte.

## 2. Vorgehen

1. **Diagnose am Code, mit Beleg im PR.** Je Befund die Ursache benennen, mit Datei und Funktion. Typische Kandidaten, am Code zu prüfen und nicht anzunehmen:
   - Der Schalter entfernt Quelle und Layer und legt sie neu an, statt nur die Sichtbarkeit zu ändern. Dann werden alle Kacheln neu geladen.
   - Die Reihenfolge auf der Karte wird nicht bei jeder Änderung aus der Liste abgeleitet, also kein festes `beforeId` bzw. kein Neuordnen nach dem Hinzufügen.
   - Die IDs der Layer sind nicht stabil, etwa ein Index als Schlüssel, eine doppelte ID, oder ein Zustand, der veraltet ist, wenn das Klicken ihn ausliest. Dadurch trifft ein Klick den falschen Eintrag.
2. **Beheben:**
   - Sichtbarkeit nur über die Eigenschaft des Layers schalten, ohne Quelle und Kacheln neu anzulegen. Eine Ausnahme ist im PR begründet.
   - Die Reihenfolge auf der Karte folgt immer der Liste, auch nach Hinzufügen, Entfernen, Ersetzen und Neuladen.
   - Jeder Layer hat eine stabile, eindeutige ID, und die Klicks arbeiten mit dieser ID.
3. **Mitprüfen:** die Layer aus M4-13c-2. Dazu gehören angeheftete Vorschau, „Replace source layer“, das Auge zum Wiederherstellen und die Fokusansicht.

## 3. Tests und Messung

- Tests je Befund, die mit dem alten Code scheitern (Gegenprobe):
  - Schalten legt keine Quelle neu an.
  - Die Reihenfolge stimmt nach jeder Operation.
  - Ein Klick schaltet genau den gewählten Layer, auch bei gleichen Namen und nach Umsortieren.
- **Messung im PR:** Zeit vom Klick bis zum sichtbaren Layer, vorher und nachher, soweit sie in der Sitzung messbar ist. Sonst die Zahl der Kachelanfragen je Schalten, vorher und nachher.
- **Prüfanleitung für Otto (Browser):**
  - fünf Layer anlegen,
  - umsortieren,
  - mehrfach schnell ein- und ausschalten,
  - eine Vorschau anheften und „Replace“ ausprobieren.

  Erwartet: sofortiges Umschalten, oben in der Liste ist oben auf der Karte, und es reagiert immer der angeklickte Layer.

## 4. Grenzen

- Nur Frontend. Kein Umbau von Aussehen oder Ort des Layer-Managers; das macht UI-01.
- Oberflächentexte nur auf Englisch.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Doku und Abnahme

- Log-Zeile mit Ursachen und Behebung.
- Zeile M4-28 in `docs/plans/m4-processing-kern.md` §3.
- Abnahme:
  - Die Tests aus §3 sind grün.
  - Alle vier Pflicht-Checks der CI sind grün.
  - Die Prüfanleitung ist im PR.
  - Vor „fertig“ ist main geholt.

## 6. Umsetzung (19.10.2026)

**Hinweis zum Plan:** „Replace source layer“ und das Auge zum Wiederherstellen gibt es seit M4-13c-2 nicht mehr (Otto, 19.10.2026, Log). Mitgeprüft sind die angeheftete Vorschau (`derived: 'preview'`, Overlays mit `preview: true`; sie läuft über denselben Abgleich wie jeder Layer, Test „orders a layer with several overlays as one block“ und die Tests zum Schalten) und die Fokusansicht (liegt über den Layern, siehe Befund 2).

### 6.1 Diagnose (Beleg am Code und im Browser)

Geprüft mit echtem MapLibre in Chromium (Prüfstand außerhalb des Repos: lokaler Kachelserver mit 120 ms Verzögerung, der Anfragen je Layer zählt; `syncLayers` und der Store unverändert eingebunden; zusätzlich die echte App mit eingesetzten Layern).

1. **Langsam — `mapLayers.ts::syncLayers`.** Jeder Aufruf rief `clearLayerOverlays` und legte danach alle Quellen neu an. `MapView` ruft `syncLayers` bei jeder Änderung an `layers` auf, also auch bei Deckkraft und Verschieben. Gemessen (5 Layer, je 9 Kacheln): Ausschalten 36, Einschalten 45, Verschieben 45, sechsmal schnell schalten 45, Deckkraft-Regler 45 Kachelanfragen, bis zum ruhigen Bild 1,1–1,4 s.
2. **Reihenfolge — `mapLayers.ts::placeImage/placeRaster` mit `beforeAoi`.** Jeder neue Layer kam an die Spitze, ohne Bezug zur Liste. Das stimmt nur, solange alle Overlays gleichzeitig ankommen: Ein Quicklook wird erst nach dem Laden des Bildes gesetzt und lag dann über allen Kacheln, auch über Layern weiter oben in der Liste (Browser: Liste `A` (Kacheln) über `B` (Quicklook, 600 ms) zeigte beim Anlegen `B`, nach Aus- und Einschalten von `A` dann `A`). Dazu kam die Ansicht (`syncFocusRaster`, `syncBrowseMosaic`): Sie wird ebenfalls „unter die AOI“ gesetzt, lag also je nach letzter Aktion über oder unter den Layern.
3. **Falscher Layer.** Der Klickweg ist in Ordnung: `LayerManager` schlüsselt und handelt nach `layer.id`, `toggleLayerVisible`/`moveLayer` suchen nach der ID, die IDs sind eindeutig (`nextBatchId` mit Zähler). Tests dazu bestehen auch mit dem alten Code und bleiben als Schutz. Was den Eindruck macht: (a) die Karten-IDs hießen `layer-lyr-<laufende Nummer der sichtbaren Overlays>` und gehörten nach jedem Schalten zu einem anderen Layer; (b) durch Befund 1 verschwanden und erschienen beim Schalten alle Layer, nicht nur der angeklickte; (c) Bilder, die der Layer-Manager nicht schaltet (siehe die Fragen unten). Einen Rennfall zwischen zwei Aufrufen von `syncLayers` (Quicklook kommt nach dem nächsten Aufruf) gab es nicht: der alte Code verwarf ihn über einen Zähler; im neuen Code prüft der Rückruf, ob der Layer noch in der Liste steht.

### 6.2 Behebung

- `syncLayers` gleicht ab: Quelle und Layer werden einmal angelegt und danach nur geändert — Sichtbarkeit (`visibility`), Deckkraft (`raster-opacity`), Reihenfolge (`moveLayer`, nur wenn sich die Reihenfolge der Liste geändert hat). Neu angelegt wird nur, was neu ist oder woraus es gebaut ist (Signatur aus URL, Grenzen, Stufen) sich ändert. Ein ausgeblendeter Quicklook wird nicht geladen; er wird beim Einblenden geholt. Die Ausnahme „Quelle neu anlegen“ gilt nur bei geänderter Signatur.
- IDs der Karte: `layer-src-<Layer-ID>-<n>` und `layer-lyr-<Layer-ID>-<n>`.
- Reihenfolge: ein unsichtbarer Marker `layers-top` (Hintergrundebene, `visibility: none`) direkt unter der AOI; jeder Layer wird unter den nächsten sichtbar gesetzten Nachbarn darüber gelegt, ein spät eintreffender Quicklook ebenso. Die Ansicht (Vorschau-Mosaik, Vollauflösung) liegt damit immer über den angehefteten Layern, wie beim Laden der Seite; die Live-Vorschau des Panels bleibt ganz oben.

### 6.3 Tests

`mapLayers.test.ts` (neu gefasst, Karte mit Reihenfolge, Quellenprotokoll und gesetzten Eigenschaften): Schalten ohne neue oder entfernte Quelle, Deckkraft an Ort und Stelle, ein ausgeschalteter Layer startet erst beim Einschalten, IDs hängen am Layer, Zwillinge mit gleichem Namen und Bild, neuer oder entfernter Layer, Reihenfolge nach Hinzufügen oben/mittig/unten, Entfernen, Ersetzen, Ausschalten, Verschieben, Layer mit mehreren Overlays, Neuladen des Stils, Ansicht über den Layern, `ensureBaseLayers`; späte Quicklooks (Reihenfolge, entfernter Layer, in der Zwischenzeit ausgeblendet, nur einmal gesetzt). `LayerManager.test.tsx`: Klick auf Auge, Verschieben, Entfernen und Deckkraft treffen die Zeile, auch bei fünf gleichnamigen Layern. Gegenprobe: 22 der neuen Fälle in `mapLayers.test.ts` scheitern am alten `mapLayers.ts` (zusätzlich scheiterte „keeps the active view above …“ allein an der Reihenfolge); die Klick-Tests laufen mit beiden Ständen, sie sind der Schutz für Befund 3.

### 6.4 Messung

Wie in 6.1, vorher → nachher, fünf Layer, 120 ms je Kachel: Ausschalten 36 → 0 Kachelanfragen, 1,08 s → 0,33 s; Einschalten 45 → 0, 1,32 s → 0,39 s; Verschieben 45 → 0, 1,36 s → 0,31 s; sechsmal schnell schalten 45 → 0, 1,35 s → 0,47 s; Deckkraft-Regler 45 → 0, 1,35 s → 0,62 s. Die Zeiten sind „Klick bis die Karte ruhig ist“ in einem Chromium ohne GPU (Software-GL) und nur untereinander vergleichbar. Das Anlegen der Layer lädt unverändert alle Kacheln einmal.

### 6.5 Antworten von Otto (20.10.2026) und ihre Umsetzung

1. **Angeheftete Zuschnitte nicht zusätzlich zeichnen** (Option 1). `searchLayers.ts::layersOnMap` lässt einen Such-Zuschnitt weg, dessen Bild (Kachel-URLs und Grenzen) schon als angeheftete Ebene in der Liste steht, auch wenn deren Auge aus ist. Entfernt man die Kopie, erscheint der Zuschnitt wieder. Der Test in `store.sections.test.ts` ist angepasst (eine Zeichnung statt zwei, ausgeblendet keine, ohne Kopie wieder der Zuschnitt). Ebenen ohne Overlays gelten nie als gleich.
2. **Ansicht eines angehefteten Layers liegt an dessen Platz und folgt seinem Auge; der Klick auf den Namen ändert die Reihenfolge nicht.** `store.ts::selectLayer` merkt sich den Layer (`viewLayerId`; `exitFocus` und `LEAVE_FOCUS` setzen ihn zurück). `viewLayer.ts::viewLayerOf` gilt, solange die Ansicht genau zeigt, was der Layer angeheftet hat: gleiche Szenen, gleiche Darstellung (Streckung, Colormap), gleiches „Crop to AOI“ und bei Zuschnitt dieselbe AOI. Dann zeichnet der Layer das Bild — an seinem Platz in der Liste, mit seinem Auge und seiner Deckkraft; `syncFocusRaster` legt die Kacheln der Ansicht nicht noch einmal darüber (`tilesInLayer`). „Hide image“ der Ansicht blendet den Layer mit aus. Ändert man die Ansicht (andere Szenen, „Apply“ mit neuen Werten, neue AOI beim Zuschnitt), ist sie wieder ihr eigenes Bild über den Layern; die angeheftete Kopie bleibt, wie sie war. Die Vorschau-Kachel unterhalb der freigegebenen Stufe (Quicklook-Unterlage) zeichnet weiter die Ansicht, folgt aber demselben Auge.

**Nicht umgesetzt, weil nicht gefragt:** Legt man die Vollauflösungs-Ansicht mit „Add to layers“ selbst als Layer an, ist `viewLayerId` nicht gesetzt; die Ansicht liegt dann weiter über allen Layern, und das Auge der neuen Kopie schaltet nur die Kopie. Soll das auch an den Platz der Kopie, ist das ein Satz in `store.ts::addCurrentToLayers`.

### 6.6 Tests zu 6.5

`viewLayer.test.ts` (neu): `viewLayerOf` für gleiche, andere, mehr und weniger Szenen, andere Streckung, Colormap, Zuschnitt und AOI, Quicklook-Layer; `layersForMap`, `viewShown`; auf einer Karte mit Reihenfolge: Namensklick ändert Liste und Reihenfolge nicht, keine Kacheln der Ansicht obenauf, Auge, „Hide image“, Verschieben, geänderte Ansicht liegt obenauf, Verlassen setzt zurück. `searchLayers.test.ts` und `store.sections.test.ts`: Zuschnitt nicht doppelt. `LayerManager.test.tsx`: Klick auf den Namen. Gegenprobe in der Sitzung: `viewLayerOf` immer leer (7 Fälle scheitern), „Hide image“ ohne Wirkung auf den Layer (2), `selectLayer` ohne Merken (4), Zuschnitte nicht entdoppelt (3).
