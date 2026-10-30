# NM4-59 — Suchergebnisse als Eintrag „Results“ im Layer-Manager

**Stand:** 30.10.2026, Wunsch und Fehlerbericht von Otto (Backlog-Punkt 59 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** Planphase sofort möglich (nur Doku). Code: Frontend-Aufgabe (höchstens zwei Frontend-Sessions gleichzeitig), nach dem Merge von NM4-55 (#242), vor NM4-53 und NM4-54 (alle ändern die Ebenenfolge bzw. die Ansicht).
**Startsatz:** „Führe Aufgabe NM4-59 aus `docs/plans/querschnitt/nm4-59-results-als-layer.md` aus.“

## 1. Befund und Wunsch (Otto, 30.10.2026, wörtlich)

> was generell manchmal hängt: Wenn ich einen results eine gruppe offen habe (nix angeclickt) und einen layer hinzufüge (von einem fertigen job) ist der ja unter den results. Wenn ich dann hide results mache dann sehe ich den resulting layer von den jobs und wenn ich dann wieder show results mache dann sehe ich die results nicht immer obwohl sie angecklickt sind. Vielleicht würde es sinn machen einen Layer im layer manager zu haben "Results" wo ich auch die reihenfolge ändern kann, damit würde alles ein bisschen klarer werden und statt Hide und show results hätte ich dann auch gerne einfach ein Augensymbol. Dann müsste die ganze layer logik von den search results nicht mehr so kompliziert implementiert sein sondern könnte sich auf den layer manager stützen.

## 2. Soll (Otto)

1. **Fehler:** Nach „Hide results“ und wieder „Show results“ erscheinen die Suchergebnisse zuverlässig wieder, auch mit einem angehefteten Job-Ergebnis darunter. Zuerst nachstellen, Ursache nennen.
2. **Eintrag „Results“ im Layer-Manager:** Die Suchergebnisse (Quicklooks, Umrisse, angehakte Szenen) sind ein Eintrag „Results“ im Layer-Manager, dessen Lage gegenüber den anderen Layern Otto per Reihenfolge ändern kann wie bei jedem Layer.
3. **Auge statt „Show/Hide results“:** Sichtbarkeit über das Auge dieses Eintrags (wie bei allen Layern, NM4-50). Der bisherige Umschalter entfällt bzw. ist dasselbe Auge.
5. **Fest (Otto, 30.10.2026): „Bei den clicks gilt dann noch immer der letzte click ist oben.“** Innerhalb von „Results“ liegt unter den angehakten Szenen immer die zuletzt angehakte oben (#221). Die offene Gruppe bzw. der aktuelle Zeitschritt beim Abspielen liegt über angehakten Szenen anderer Gruppen (NM4-55, #242); eine frisch angehakte Szene gehört zur offenen Gruppe und liegt damit ganz oben. Der Layer-Manager ordnet nur „Results“ als Ganzes gegenüber den anderen Layern.
6. **Fest (Otto, 30.10.2026):** Live-Vorschau des Processing-Panels und Ansicht (Zuschnitt/ganze Szene, später mit Zeitschritten aus NM4-53) gehören zum Eintrag „Results“, keine eigenen Einträge. AOI und Zeichnung bleiben immer oben.
7. **Fest (Otto, 30.10.2026):** Die Ausnahmen bleiben und wirken auf das Auge von „Results“: „Search“ schaltet ein, „Crop to AOI“/„Crop & merge to AOI“ schaltet aus, Anhaken einer Szene bei ausgeschaltetem Auge schaltet ein. Sonst ändert nur das Auge die Sichtbarkeit.
4. **Einfacher:** Die Ebenenfolge der Suchergebnisse stützt sich auf den Layer-Manager statt auf eigene Marker und Sonderregeln.

## 3. Im Plan klären (Optionen, Empfehlung)

1. **Overlays** aus UI-02b/NM4-35 (Labels, Graticule, Relief): eigene Einträge oder fest wie heute? (Vorschau, Ansicht, Umrisse gehören laut §2 Punkt 6 zu „Results“.)
2. **Reihenfolge innerhalb von „Results“:** fest nach §2 Punkt 5 (Live-Vorschau ganz oben, dann offene Gruppe/aktueller Zeitschritt, angehakte Szenen anderer Gruppen in Anhak-Reihenfolge, dann Ansicht); der Plan zeigt nur die Umsetzung.
3. **Vorgabe-Lage** von „Results“ beim ersten Erscheinen (oben wie heute, Vorschlag) und was eine neue Suche damit macht.
4. **Ausnahmen:** fest nach §2 Punkt 7; der Plan zeigt nur die Umsetzung.
5. **Gibt es „Results“ ohne Suchergebnisse?** (Vorschlag: Eintrag erscheint mit der ersten Suche, verschwindet mit „Clear search results“.)
6. **Darstellung** im Layer-Manager: kein Colormap-/Skala-Menü für „Results“ (Quicklooks sind fertige Bilder); was zeigt die Zeile (z. B. Anzahl)?
7. **Was aus den bisherigen Markern** (`results-top`, `ticked-top`, `overlays-base` usw.) wird; Weg zu einer einzigen Ebenenfolge aus dem Zustand des Layer-Managers, auch nach `style.load`.
8. **Folgen für laufende und geplante Aufgaben:** NM4-53, NM4-54, NM4-43e, DS-03b; was sie nach NM4-59 anders machen.

## 4. Grenzen

- Nur Frontend.
- Oberflächentexte nur Englisch; wenig Text, Erklärungen im Tooltip.
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Nachträge heißen nach der Aufgabe („Nachtrag NM4-59“); frühere Regeln im Log per Nachtrag ersetzen, Originaltexte stehen lassen.
- Bilder der Browserprüfung nicht ins Repo, nur im PR beschreiben.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Test für Ottos Klickweg aus §1 (Gruppe offen, Job-Layer anheften, aus/an) mit Gegenprobe.
- Tests: Lage von „Results“ per Reihenfolge änderbar, Auge, Ausnahmen aus §3.4, Regeln innerhalb von „Results“, nach `style.load` und Basemap-Wechsel.
- Prüfung im echten Browser (Playwright), Hell/Dunkel, schmales Fenster; Prüfanleitung für Otto mit seinem Klickweg.
- Alle vier Pflicht-Checks grün.
- Log-Zeilen mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.
