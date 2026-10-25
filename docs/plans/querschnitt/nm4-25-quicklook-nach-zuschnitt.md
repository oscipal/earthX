# NM4-25 — Quicklook nach „Crop & merge to AOI“ sofort zuschneiden

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 25 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** nach dem Merge von UI-01 (ordnet Leisten und Panels neu). Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-25 aus `docs/plans/querschnitt/nm4-25-quicklook-nach-zuschnitt.md` aus.“

## 1. Anlass

Nach „Crop & merge to AOI“ bleibt der Quicklook der ganzen Szene noch eine Weile sichtbar, auch außerhalb der AOI (Otto, 25.10.2026).

## 2. Soll

- Außerhalb der AOI verschwindet der Quicklook sofort.
- Innerhalb der AOI bleibt er stehen, bis die Kacheln des Zuschnitts für den sichtbaren Ausschnitt geladen sind; dann wird er ersetzt, ohne Aufblitzen der Basemap (Vorgabe „Bild verschwindet nie“, UI-01a).

## 3. Umfang

- Ursache am Code finden und im PR nennen (Unterlage, alte Ansicht, fehlende Maske).
- Behebung in der gemeinsamen Layer-Logik (`mapLayers.ts`, `viewLayer.ts`, Store), nicht nur für diesen Knopf.

## 4. Offene Punkte (bei Unklarheit Frage an Otto)

- Gilt dasselbe für andere Wechsel (Ansicht → angehefteter Zuschnitt, Mosaik → Zuschnitt)? Liste im PR.

## 5. Grenzen

- Nur Frontend.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 6. Abnahme

- Test mit verzögerten Kacheln: außerhalb der AOI sofort leer, innerhalb kein leerer Moment.
- Gegenprobe: Mit dem alten Code scheitert der Test.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
