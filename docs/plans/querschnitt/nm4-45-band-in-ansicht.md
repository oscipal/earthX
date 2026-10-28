# NM4-45 — Einzelne Bänder in der Vollauflösungs-Ansicht per Dropdown

**Stand:** 27.10.2026, beauftragt von Otto (Backlog-Punkt 45 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR. Braucht es mehr als Frontend (etwa eine neue `tiler`-Route oder ein Registry-Feld), legt die Session das Otto zuerst als Frage vor.
**Modell:** Sonnet, Effort mittel.
**Start:** nach dem Merge von NM4-53 (beide ändern die Leiste der Ansicht). Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-45 aus `docs/plans/querschnitt/nm4-45-band-in-ansicht.md` aus.“

## 1. Wunsch (Otto, 27.10.2026, wörtlich)

> bei der full resolution view will ich auch einzelne bänder mittels dropdown anzeigen lassen.

## 2. Soll

- In der Ansicht (Zuschnitt, ganze Szene, gemergte Szenen; aus #211) ein Dropdown „Band“. Vorgabe ist die heutige Darstellung (bei Sentinel-2 `visual`, Echtfarben). Daneben jedes einzelne Band des Datensatzes.
- Bei einem einzelnen Band greifen Colormap, vmin/vmax, „auto-scale“ und „Apply“ wie heute bei Einband-Datensätzen. Bei `visual` bleiben sie, wie sie sind.
- Welche Assets im Dropdown stehen, kommt aus der Registry (Bänder, nicht `auxiliary_assets` wie `preview`; `visual` nur als Vorgabe-Eintrag). Keine Namenslisten im Frontend.
- „Add to layers“ heftet das gewählte Band an; der Layer behält Band und Darstellung.
- Wechsel des Bandes ändert nichts an Show/Hide, Auswahl oder Position der Leisten (Regeln aus #211).
- Ein Dropdown mit nur einem Eintrag erscheint nicht (nicht Mögliches ausblenden).

## 3. Im PR klären

- Die Kachel-Route nimmt den Asset-Schlüssel schon als Parameter (`?asset=…`, M2-04). Reicht das für Zuschnitt und gemergte Szenen (Mosaik-Kachel), oder fehlt ein Weg? Falls Backend nötig: Frage an Otto vor dem Code.
- Vorgabe für vmin/vmax je Band (Statistik der Szene, F18; über die AOI kommt mit NM4-19).
- Einheiten: keine Anzeige der Einheit „1“; sonst wie im Panel.
- Nur Einzelbänder; Falschfarben aus drei Bändern sind nicht Teil dieser Aufgabe.

## 4. Grenzen

- Oberflächentexte nur Englisch; wenig Text, Erklärungen im Tooltip.
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Dropdown mit den Bändern aus der Registry, Vorgabe `visual`, Wechsel auf ein Band zeigt Colormap/vmin/vmax, Anheften behält das Band, kein Dropdown bei nur einem Eintrag, Show/Hide und Leistenpositionen unverändert. Gegenprobe mit dem alten Code.
- Prüfung im echten Browser (Playwright), Hell/Dunkel, schmales Fenster; Prüfanleitung für Otto im PR.
- Alle vier Pflicht-Checks grün.
- Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.
