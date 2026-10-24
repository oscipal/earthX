# NM4-06 — Gemergter Zuschnitt als ein Objekt im Panel

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 6 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-06 aus `docs/plans/querschnitt/nm4-06-zuschnitt-als-ein-objekt.md` aus.“

## 1. Anlass

Wird Processing aus einem Layer gestartet, der schon gemergt und auf die AOI zugeschnitten ist („Crop & merge to AOI“ bzw. die angeheftete Zuschnitt-Ansicht), bietet das Panel trotzdem „Run as: One job / One job per pass / One job per scene“ an (M4-13c-4).

## 2. Soll

- So ein Layer gilt als **ein Objekt**: „Run as“ ist ausgeblendet (nicht nur gesperrt), „Area“ steht fest auf „AOI only“ und folgt der AOI des Zuschnitts, das Panel schickt genau einen Auftrag (Mosaik des Überflugs mit AOI, M4-12a).
- Umfasst der Layer Szenen mehrerer Überflüge, geht ein einzelner Auftrag nicht (ein Mosaik-Job umfasst genau einen Überflug, M4-12a F6). Das Panel sagt das mit Grund (Tooltip/Fehlermeldung).
- Einstieg aus der Auswahl und aus anderen Layern bleibt unverändert, mit „Run as“.

## 3. Umfang

- Erkennen am Einstieg (M4-13c-2), etwa an der Art des Layers; keine zweite Regel neben der bestehenden Einstiegslogik. Die Session nennt die Stelle im PR.

## 4. Offene Punkte (bei Unklarheit Frage an Otto)

- Mehrere Überflüge: abweisen oder doch die Wahl je Überflug anbieten? Vorschlag im PR; bei Unklarheit Frage an Otto.

## 5. Grenzen

- Nur Frontend.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 6. Abnahme

- Tests: Einstieg aus gemergtem Zuschnitt (kein „Run as“, ein Auftrag, „AOI only“); Einstieg aus der Auswahl (wie bisher); Zuschnitt über mehrere Überflüge.
- Gegenprobe: Mit dem alten Code scheitern die neuen Tests.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
