# UI-01h — „Hide results“ gilt immer; Zuschnitt entfernbar

**Stand:** 27.10.2026, Fehlerbericht von Otto. Ergänzt UI-01g (`docs/plans/vp3/ui-01g-suchergebnisse-angedockt.md`, #209).
**Stufe A:** direkt umsetzen, ein Draft-PR, nur Frontend.
**Modell:** Sonnet, Effort hoch (Zustandslogik der Karte).
**Start:** nach dem Merge von UI-02a (#211), weil UI-02a die Ebenen nach einem Basemap-Wechsel neu aufbaut. Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe UI-01h aus `docs/plans/vp3/ui-01h-ergebnisse-ausblenden.md` aus.“

## 1. Befund (Otto, 27.10.2026, wörtlich)

> When I select a search result and crop to AOI in full resolution I dont have any way to clear it. When I press clear in the control panel suddenly the search result (the original quicklook from the crop) appears and doesn't toggle off even if I click hide results. If I click hide results they should ALWAYS be toggled off and not shown on the map the ONLY exception is when a scene is selected then it should also be shown even though hide results is set.

Zwei Fehler:
1. Der Zuschnitt („Crop to AOI“) lässt sich nicht von der Karte entfernen.
2. Nach einem „Clear“ erscheint der Quicklook des Suchergebnisses wieder und bleibt trotz „Hide results“ sichtbar.

**Zuerst nachstellen:** Die Session stellt beide Fehler im echten Browser nach und nennt im PR den genauen Klickweg, vor allem welcher Knopf mit „clear“ gemeint ist. Laut UI-01g hat die Steuerleiste kein „Clear“ mehr; in Frage kommen „Clear search results“ (rotes ✕), ein „Clear“ im Control-Menü oder ein Entfernen in der Steuerleiste. Gelingt das Nachstellen nicht eindeutig: Frage an Otto, bevor Code geändert wird.

## 2. Regeln (Otto, 27.10.2026)

1. **„Hide results“ gilt immer.** Solange „Hide results“ gesetzt ist, zeigt die Karte keine Suchergebnisse: keine Umrisse, keine Quicklooks, keine Hervorhebung. Kein anderer Vorgang hebt das auf: kein Clear (welcher auch immer), kein Zuschnitt, kein Entfernen eines Layers, kein Basemap- oder Projektionswechsel, kein Nachladen („Load more“), keine neue Suche, kein Neuladen der Seite.
2. **Einzige Ausnahme: ausgewählte Szenen.** Eine ausgewählte Szene bzw. Auswahl erscheint auch bei „Hide results“, mit ihren normalen Steuerelementen (so schon in UI-01g). Wird die Auswahl aufgehoben, verschwindet sie wieder, solange „Hide results“ gilt.
3. **Nur der Umschalter ändert den Zustand.** Kein anderer Knopf schaltet „Show/Hide results“ um.
4. **Zuschnitt ist ein Layer.** Das Ergebnis von „Crop to AOI“ bzw. „Crop & merge to AOI“ steht als Layer im Layer-Manager und lässt sich dort mit dem üblichen Entfernen-Knopf löschen (UI-01g: Layer und Suchergebnisse sind entkoppelt). Ist das heute nicht so, ist das der Fehler 1. Das Entfernen des Zuschnitts bringt keine verborgenen Ergebnisse zurück.

## 3. Umsetzung

- **Eine Stelle:** Was von den Suchergebnissen auf der Karte erscheint, ergibt sich aus einer einzigen Funktion des Zustands (Sichtbarkeit, Auswahl, Ergebnisliste). Keine verstreuten Flags, die einzelne Vorgänge setzen. Die Session nennt die Funktion im PR.
- Auch der Wiederaufbau der Ebenen nach `style.load` (UI-02a, Basemap-Wechsel) geht über diese Funktion.

## 4. Grenzen

- Nur Frontend. Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip.
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- **Tests als Matrix:** Zustand „Hide“ bzw. „Show“ × Auswahl ja/nein × Vorgang (jedes Clear, Crop, Layer entfernen, Basemap- und Projektionswechsel, Load more, neue Suche, Neuladen). Erwartet: bei „Hide“ ohne Auswahl nie ein Ergebnis auf der Karte; mit Auswahl nur die Auswahl.
- Test: Zuschnitt erscheint im Layer-Manager und lässt sich entfernen; danach keine Ergebnisse bei „Hide“.
- Gegenprobe: Mit dem alten Code scheitern die Tests zu Ottos Klickweg.
- Prüfung im echten Browser (Playwright), Hell/Dunkel, schmales Fenster; Prüfanleitung für Otto im PR (Ottos Klickweg aus §1 Schritt für Schritt).
- Alle vier Pflicht-Checks grün; Log-Zeile.
- Vor „fertig“ ist main geholt.
