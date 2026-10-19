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
