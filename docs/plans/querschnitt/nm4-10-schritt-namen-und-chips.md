# NM4-10 — Laufnummer, eigene Namen und Band-Chips für Ergebnisse von Schritten

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 10 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach NM4-08; nicht gleichzeitig mit NM4-07, NM4-14 oder NM4-20 (Panel). Höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-10 aus `docs/plans/querschnitt/nm4-10-schritt-namen-und-chips.md` aus.“

## 1. Anlass

In einer Kette sieht ein Schritt nur das Ergebnis des vorigen; das Ergebnisband heißt heute immer `band_math`. Otto will die Schritte nummeriert, ihre Ergebnisse als Chips wie die Bänder und eigene Namen.

## 2. Soll

- **Format:** Schritt-Titel „1. Band_Math_1“, „2. Normalize_2“ usw. Die Nummer steckt im Namen des Ergebnisbands: Schritt 1 gibt `Band_Math_1` aus.
- **Eigener Name:** Der Name des Ergebnisbands lässt sich je Schritt umbenennen (etwa `ndvi`); `Band_Math_1` ist nur die Vorgabe. Der Name steht im Rezept, im Titel und auf dem Chip und gilt in den folgenden Schritten.
- **Chips:** Das Ergebnisband erscheint in den folgenden Schritten als Chip im selben runden Format wie die Bänder (M4-13c); ein Klick fügt es in den Ausdruck ein.
- **Nur verfügbare Bänder:** Ein späterer Schritt zeigt nur die Chips, die nach den vorigen Schritten noch da sind (nach Band math nur dessen Ergebnis, nach `mask` die Bänder ohne die Schicht). Die Regel kommt aus dem Backend; das Frontend baut sie nicht nach (wie M4-18b).

## 3. Im Plan klären (mit Optionen und Empfehlung)

- Versionierung: Der Bandname ändert Rezept, Hash und Bytes (`result.tif`); `op_version` bzw. `earthx.__version__`, Nachtrag in `adr/0014`. Werden alte Rezepte mit `band_math` weiter angenommen?
- Erlaubte Zeichen, Länge, Groß/Klein gegen die Regeln für Bandnamen im Ausdruck (R5); keine Doppel in der Kette; keine Kollision mit Bandnamen des Datensatzes.
- Umbenennen, wenn spätere Schritte den alten Namen nutzen: automatisch mitziehen oder Hinweis.
- Woher das Panel die verfügbaren Bänder je Schritt bekommt (Annahme-Antwort, eigene Route, TileJSON).
- Kachel-Pfad (M4-18b), Runner, Methodentext ziehen mit.

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Namen im Rezept, Hash ändert sich wie geplant, Kette mit eigenem Namen, Umbenennen, Kollisionen abgewiesen, Kachel gleich Job.
- Gegenprobe: Mit dem alten Code scheitern die neuen Tests.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
