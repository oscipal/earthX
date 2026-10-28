# NM4-53 — Ansicht nach „Crop & merge“ über mehrere Gruppen und Datensätze: Zeitschritte durchschalten

**Stand:** 28.10.2026, Wunsch von Otto (Backlog-Punkt 53 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach dem Merge von NM4-50 (gleicher Bereich: Auswahl über Gruppen und Datensätze). Nicht gleichzeitig mit NM4-45 (beide ändern die Leiste der Ansicht); NM4-45 folgt danach. Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig; höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-53 aus `docs/plans/querschnitt/nm4-53-ansicht-mehrere-zeitschritte.md` aus.“

## 1. Wunsch (Otto, 28.10.2026, wörtlich)

> wenn ich mehrere szenen von verschiedenen gruppen bzw datensätzen auswähle und crop and merge to AOI drücke, dann will ich erstens nicht das der click beim DEM zB verschwindet wenn ich zu S2 wechsle (in den search results) und zweitens dass eine bar unten im dem fenster wo ich colormap und scale undso einstellen kann erscheint wo ich die timesteps pro datensatz durchclicken kann (also nur klein, zwei pfeile links und rechts neben dem Datum und ob S2A oder S2B usw (zumindest bei S2)) und dann auch noch eine dropdown wo ich den datensatz auswählen kann und noch zusätzlich ein button "add all to layers", der andere add to layers button soll dann nur die szene die derzeit angezeigt wird zum layer manager hinzufügen.

Der erste Teil (Haken verschwinden beim Wechsel der Gruppe bzw. des Datensatzes) ist ein Fehler und geht an NM4-50. Diese Aufgabe baut den zweiten Teil.

## 2. Soll (Otto)

- **Zeitschritte:** Nach „Crop & merge to AOI“ mit Szenen aus mehreren Gruppen (Überflügen) bzw. Datensätzen zeigt die Ansicht einen Zeitschritt zur Zeit. In der Leiste der Ansicht (dort, wo Colormap, vmin/vmax und „auto-scale“ stehen) gibt es eine kleine Zeile: `‹  2025-07-29 · S2A  ›`. Die Pfeile schalten zum vorigen bzw. nächsten Zeitschritt des gewählten Datensatzes. Der Satellit steht dabei, wo der Datensatz ihn hat (Sentinel-2: S2A/S2B/S2C aus `platform`).
- **Datensatz:** Ein Dropdown wählt den Datensatz, dessen Zeitschritte die Pfeile durchschalten.
- **„Add to layers“** heftet nur den gerade angezeigten Zeitschritt an.
- **„Add all to layers“** (neu) heftet alle Zeitschritte aller Datensätze der Ansicht an.
- **Nicht Mögliches ausblenden:** Gibt es nur einen Zeitschritt, erscheinen keine Pfeile; nur ein Datensatz, kein Dropdown; „Add all to layers“ nur bei mehr als einem Zeitschritt insgesamt.

## 3. Im Plan klären (Optionen, Empfehlung)

1. **Was ein Zeitschritt ist:** je Datensatz eine Gruppe (Überflug) mit ihren angehakten Szenen, gemergt; Datensätze ohne Zeitachse (DEM) haben einen Zeitschritt. Reihenfolge nach Datum.
2. **Welcher Zeitschritt zuerst:** etwa der früheste oder der zuletzt angehakte.
3. **Darstellung je Zeitschritt oder je Datensatz:** gelten Colormap und vmin/vmax für alle Zeitschritte eines Datensatzes gemeinsam (Vorschlag, vergleichbar) oder je Zeitschritt?
4. **Die übrigen Knöpfe:** Was tun „Download merged crop“, „Process“, „Clear“, „Change image“ bei mehreren Zeitschritten (nur den angezeigten, alle, je Datensatz)? Zusammenhang mit NM4-06 (gemergter Zuschnitt als ein Objekt) und dem Batch (UI-01).
5. **Namen der angehefteten Layer** (Datensatz, Datum, Satellit) und ihre Reihenfolge im Layer-Manager.
6. **Tastatur:** Pfeiltasten bei Fokus in der Leiste; Verhältnis zur Zeitleiste der Suchergebnisse (NM4-18).
7. **Kopf der Ansicht** (aus #211: „Sentinel-2 L2A · 2025-07-29 · AOI crop“): zeigt den angezeigten Zeitschritt; die Regeln für Breite und „…“ gelten weiter.
8. **Regeln aus #211/#221** (Show/Hide, Anhak-Reihenfolge, feste Plätze der Leisten) bleiben; Durchschalten ändert Show/Hide nicht.

## 4. Grenzen

- Nur Frontend, außer der Plan begründet etwas anderes.
- Oberflächentexte nur Englisch; wenig Text, Erklärungen im Tooltip.
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Nachträge in ADRs heißen nach der Aufgabe („Nachtrag NM4-53“).
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Zeitschritte je Datensatz, Pfeile und Dropdown (inkl. Ausblenden bei einem Eintrag), „Add to layers“ nur der angezeigte, „Add all to layers“ alle, Darstellung nach Antwort 3, Regeln aus #211/#221 unverändert. Gegenprobe.
- Prüfung im echten Browser (Playwright), Hell/Dunkel, schmales Fenster; Prüfanleitung für Otto mit S2 aus zwei Überflügen und DEM.
- Alle vier Pflicht-Checks grün.
- Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.
