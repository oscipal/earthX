# NM4-50 — DEM: Layer-Manager und Ergebnisse wie bei Sentinel-2; Augen-Symbol für Sichtbarkeit

**Stand:** 28.10.2026, Fehlerbericht von Otto (Backlog-Punkt 50 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR. Zuerst nachstellen und die Ursache im PR nennen; bleibt der Klickweg unklar, Frage an Otto, bevor Code geändert wird.
**Modell:** Sonnet, Effort hoch (Zustandslogik von Karte und Layer-Manager).
**Start:** Frontend-Aufgabe, höchstens zwei Frontend-Sessions gleichzeitig. Vorrang vor neuen Funktionen.
**Startsatz:** „Führe Aufgabe NM4-50 aus `docs/plans/querschnitt/nm4-50-dem-layer-und-ergebnisse.md` aus.“

## 1. Befund (Otto, 28.10.2026, wörtlich)

> Was mir beim DEM aufgefallen ist: Da funktioniert der Layer manager nicht wirklich gut. Wenn ich einen layer hide dann wird er nicht immer hidden, außerdem speichert es einstellungen zur colormap und scale nicht. Show and hide results funktioniert auch nicht wirklich wie bei S2.
>
> Außerdem: der show and hide toggle bei den layern soll ein auge sein.
>
> und: bei DEM soll nicht in der vorschau schon das crop angezeigt werden sondern auch die full scene.

Hintergrund: Das Copernicus DEM (`cop-dem-glo-30`) hat keine Quicklooks; statt der Quicklook-Stufe erscheint direkt die Vollauflösung, zugeschnitten auf die AOI (Log 26.09.2026, M3-12), und es hat keine Zeitachse (`time_range=False`). Vermutlich laufen DEM-Ergebnisse und -Layer deshalb auf einem eigenen Weg, an dem die Regeln für Sentinel-2 nicht greifen.

## 2. Soll

1. **Ein Weg für alle Datensätze:** Layer-Manager, „Show/Hide results“, Auswahl, Ansicht und Anheften verhalten sich beim DEM genau wie bei Sentinel-2. Datensatzabhängig ist nur, was aus der Registry kommt (Quicklooks ja/nein, Zeitachse, Bänder), nie eigene Zweige im Code je Datensatz.
2. **Ausblenden wirkt immer:** Ein ausgeblendeter Layer ist nicht auf der Karte, auch nach `style.load`, Basemap- oder Projektionswechsel, Zoom unter/über Grenzen, Neuzeichnen der Ergebnisse.
3. **Darstellung bleibt:** Colormap, vmin/vmax bzw. Skala eines Layers bleiben gespeichert wie bei Sentinel-2 (Layer-Manager, UI-01), auch nach Aus- und Einblenden, Reihenfolge ändern und Neuladen, soweit das bei Sentinel-2 gilt.
4. **Show/Hide results** beim DEM nach denselben Regeln wie bei Sentinel-2 (Stand nach #221: „Hide“ blendet alles aus, Haken bleiben; Anhaken bei „Hide“ schaltet auf „Show“; zuletzt angehakt oben; Ausnahmen „Search“ → Show, „Crop“ → Hide).
6. **Vorschau zeigt die ganze Szene** (Otto, 28.10.2026: „bei DEM soll nicht in der vorschau schon das crop angezeigt werden sondern auch die full scene“): Ein angehaktes DEM-Ergebnis zeigt beim Stöbern die ganze Kachel in Vollauflösung, nicht den Zuschnitt auf die AOI, also wie der Quicklook bei Sentinel-2. Zuschneiden geschieht erst mit „Crop to AOI“. Das ersetzt den Teil „zugeschnitten auf die AOI“ der Entscheidung vom 26.09.2026 (Log, M3-12; Nachtrag dort, Originaltext stehen lassen). Unter der kleinsten freigegebenen Zoomstufe bleibt „Zoom in to see this dataset“. Ob ohne AOI weiter „Draw an AOI to view this dataset“ gilt oder die ganze Kachel erscheint: im PR klären, Vorschlag: ganze Kachel, weil sie keine AOI mehr braucht.
5. **Augen-Symbol:** Der Schalter für Sichtbarkeit im Layer-Manager ist ein Auge (offen = sichtbar, durchgestrichen = ausgeblendet), Tooltip „Hide layer“ / „Show layer“, gleiche Größe und Position wie heute.

## 3. Vorgehen

- Zuerst im echten Browser nachstellen (DEM suchen, Ergebnis ansehen, anheften, Colormap/Skala ändern, aus-/einblenden, Show/Hide results), jeden Fehler mit Klickweg und Ursache (Datei, Funktion) im PR.
- Prüfen, ob es datensatzspezifische Zweige gibt (etwa für „ohne Quicklooks“ oder `time_range=False`), die die gemeinsame Funktion `resultsOnMapOf` bzw. die Layer-Logik umgehen; zusammenführen.
- Dieselben Klickwege mit Sentinel-2 als Gegenprobe.

## 4. Grenzen

- Oberflächentexte nur Englisch; wenig Text, Erklärungen im Tooltip.
- Keine neue Abhängigkeit ohne Frage an Otto; Symbol aus dem vorhandenen Satz oder als kleines Inline-SVG.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests für jeden gefundenen Fehler (DEM und Sentinel-2 im selben Test, parametrisiert nach Datensatz), Gegenprobe mit dem alten Code.
- Test Augen-Symbol: Zustand und Tooltip.
- Prüfung im echten Browser (Playwright), Hell/Dunkel, schmales Fenster; Prüfanleitung für Otto mit dem DEM-Klickweg.
- Alle vier Pflicht-Checks grün.
- Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.
