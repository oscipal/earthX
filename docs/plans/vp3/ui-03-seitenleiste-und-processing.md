# UI-03 — Seitenleiste rechts, aufgeräumtes Processing, einheitliches Erscheinungsbild

**Stand:** 01.11.2026, beauftragt von Otto (Backlog-Punkt 72 in `docs/plans/nach-m4-backlog.md`). Nimmt NM4-20 (Processing-Panel klarer gegliedert) in sich auf.
**Stufe B:** Erst kommt der Plan im Draft-PR (Konzept, Varianten, Empfehlung, Schnitt in Teile), Otto gibt ihn frei, dann setzt dieselbe Session **Teil 1** um. Die weiteren Teile bekommen je eine neue Session und einen eigenen PR.
**Modell:** Opus für Konzept und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach dem Merge von NM4-54 (#272). Vor NM4-56 (Paket Oberfläche). Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig, höchstens zwei Stufe-B-Sessions gleichzeitig. Teil 2 (Processing-Panel) nicht gleichzeitig mit dem Frontend-Teil von NM4-71.
**Startsatz:** „Führe Aufgabe UI-03 aus `docs/plans/vp3/ui-03-seitenleiste-und-processing.md` aus.“

## 1. Wunsch (Otto, 01.11.2026, wörtlich)

> ich hätte gerne diese layer und ansichts menüs nicht mehr als kleine box unten sondern als seitenleiste rechts. Und der processing manager gehört finde ich auch aufgeräumt.

Zum Processing-Manager: „Unübersichtliche Gruppen“, „eigentlich das Panel“, dazu wörtlich:

> generell finde ich ihn zu schmal und es ist nicht so clean, will eher apple mäßiges design dass alles einheitlich seinen platz hat und nicht quer durch ist.

## 2. Antworten Otto (01.11.2026)

1. **Seitenleiste rechts öffnet bei Klick:** Sie erscheint, wenn eine Ansicht („Crop to AOI“, „Crop & merge to AOI“, ganze Szene) oder ein Layer (Ergebnis, angeheftete Ansicht) geöffnet wird, und schließt mit dem kleinen roten „x“. Sonst bleibt die Karte frei.
2. **Inhalt der Seitenleiste:** nur die Einstellungen von Ansicht bzw. Layer (die heutige Box aus NM4-54 Teil 5: Band, vmin, vmax, Colormap, Opacity, Knopfzeile mit „Apply“/„Apply to all“, „Add to layers“, Downloads). Der Layer-Manager bleibt, wo er ist.
3. **Auswahl- und Zeitleiste** (NM4-66) bleibt unten.
4. **Processing:** Panel (Schritte, Bandvorrat, Ausgabe, Vorschau) und Processing-Manager (Jobs, Gruppen, Stapel) sind gemeint. Zu schmal; Gruppen unübersichtlich; ein ruhiges, einheitliches Erscheinungsbild „wie bei Apple“: jedes Element hat seinen festen Platz.

## 3. Soll

### Teil 1 – Seitenleiste rechts (Inspector)

- Die Einstellungsbox wird eine Seitenleiste am rechten Rand, volle Höhe unter der Kopfzeile, feste Breite (Vorschlag im Plan), über der Karte; die Karte darunter bleibt bedienbar.
- Ein gemeinsames Bauteil für Ansicht der Suche, angeheftete Ansicht und Ergebnis-Layer (Grundlage: NM4-54 Teil 5). Feste Reihenfolge der Abschnitte; Felder behalten ihren Platz und sind gesperrt mit Grund, wenn sie gerade nicht gelten.
- Wechsel der Ansicht bzw. des Layers tauscht den Inhalt, die Leiste bleibt stehen. Schließen mit rotem „x“, Esc schließt ebenfalls.
- Zeitschritte der Ansicht (NM4-53: Datensatz-Dropdown, `‹ Datum ›`) im Kopf der Seitenleiste.
- Schmale Fenster (unter etwa 900 px): Vorschlag im Plan (z. B. Leiste über die ganze Breite oder als Blatt von unten); Auswahl- und Zeitleiste unten bleiben erreichbar.

### Teil 2 – Processing-Panel (ersetzt NM4-20)

- Breiter (Vorschlag im Plan, abgestimmt mit linker Leiste und Seitenleiste rechts).
- Klare Abschnitte mit festem Platz: Herkunft/Eingabe, Bandvorrat, Schritte, Ausgabe, Vorschau, Start; gleiche Abstände, gleiche Feldbreiten, gleiche Knopfformen; Erklärungen hinter (i) bzw. im Tooltip.
- Schritte als einheitliche Karten (Kopf mit Name, Umbenennen, Entfernen; Inhalt je Operator in derselben Raster-Ordnung).

### Teil 3 – Processing-Manager

- Breiter, Gruppen und Stapel auf einen Blick: Gruppe als Kopfzeile mit Anzahl und Zustand, Jobs darunter in gleicher Zeilenform, feste Plätze für Status, Titel, Datum, Aktionen.
- Weniger Knöpfe je Zeile, seltene Aktionen in einem Menü (…).

### Für alle Teile – einheitliches Erscheinungsbild

- Gemeinsame Gestaltungsgrundlagen als Tokens (Abstände, Schriftgrößen, Radien, Linien, Farben für Hell/Dunkel), einmal definiert und überall benutzt; keine Einzelwerte in Komponenten.
- Ruhig: wenige Rahmen, klare Gruppierung über Abstand und Überschriften, eine Schriftfamilie (System-Schrift), einheitliche Bedienelemente (Segment-Umschalter, Schalter, Dropdowns, Zahlfelder).
- Bestehende Regeln gelten weiter: Oberflächentexte Englisch, wenig Text, Erklärungen hinter (i); alle Schließen-Knöpfe kleines rotes „x“ (`CloseButton.tsx`); bestehende gesperrte Elemente werden nicht entfernt (NM4-30 entfällt); Show/Hide-, Ebenen- und Ansichtsregeln aus #211, #221, #249, #257, #266, #267, #272 bleiben.

## 4. Im Plan klären (je Varianten, Empfehlung)

1. **Konzept:** Aufteilung des Bildschirms (linke Leiste, Karte, Seitenleiste rechts, Leiste unten) mit Maßen für 1280, 1920 und 360 px; Skizze als Text bzw. ASCII im PR (keine Bilder ins Repo). Recherche mit Quellen, wie Apple (Human Interface Guidelines: Sidebar, Inspector) und vergleichbare Kartenanwendungen (z. B. QGIS, ArcGIS Online, Google Earth Engine Code Editor, Sentinel Hub EO Browser) Einstellungen und Ergebnislisten ordnen.
2. **Tokens:** Vorschlag der Werte (Abstandsskala, Schriftgrade, Radien) und wo sie liegen.
3. **Schnitt:** Bestätigen oder ändern: Teil 1 Seitenleiste + Tokens, Teil 2 Processing-Panel, Teil 3 Processing-Manager; je Teil Umfang, Reihenfolge, Konflikte mit laufenden Aufgaben (NM4-71, NM4-56).
4. **Was mit NM4-56 (Zahlenformat, weniger Text, schmale Fenster) zusammenfällt**, damit es nicht doppelt gemacht wird.

## 5. Grenzen

- Nur Frontend. Keine neue Abhängigkeit ohne Frage an Otto (kein UI-Framework ohne Freigabe).
- Keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Bilder der Browserprüfung nicht ins Repo, nur im PR beschreiben. Nachträge heißen nach der Aufgabe („Nachtrag UI-03“).
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 6. Abnahme

- Plan im Draft-PR mit Konzept, Varianten, Empfehlung, Quellen und Schnitt; Otto gibt frei.
- Teil 1 danach in derselben Session: Tests mit Gegenprobe, Browserprüfung (Hell/Dunkel, 1280, 1920 und 360 px; Ansicht, angeheftete Ansicht, Ergebnis-Layer; Wechsel, Schließen, Esc), Prüfanleitung für Otto; die vorhandenen Browser-Skripte, die die Box betreffen, nachgezogen.
- Alle vier Pflicht-Checks grün; Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.

## 7. Plan (01.11.2026, zur Freigabe durch Otto)

Stufe B: Bis zur Freigabe ist kein Produktivcode geändert. Grundlage ist `main` nach #272 (NM4-54) und #274. Belegstufen wie in UI-02: [P] Code oder Primärquelle gelesen, [M] in der Sitzung gemessen, [S] nur Zusammenfassung einer Websuche (vor einer Entscheidung gegenzuprüfen), [A] eigene Ableitung.

**Abgrenzung zu UI-04 (Otto, 01.11.2026):** NM4-56 geht in UI-04 „Einheitlichkeit“ auf (`docs/plans/vp3/ui-04-einheitlichkeit.md`, kommt mit der nächsten Doku-Runde): Bestandsaufnahme über die ganze Oberfläche, Begriffsliste, Leitfaden `docs/ui/leitfaden.md`, Prüfungen gegen Rückfälle, Zahlenformat, weniger Text und schmale Fenster. **UI-03 legt die Tokens fest, UI-04 zieht sie überall durch.** Wo §3 und §4 oben NM4-56 nennen, gilt UI-04 (Originaltext bleibt stehen).

**Vorgabe Otto (01.11.2026, zum Plan):** Die Regeln aus #272 gelten auch in der Seitenleiste: am Layer ist ein Band erst mit „Apply“ zu sehen, „Save“ speichert; „Temporary“ steht neben dem Titel der Ansicht wie umgesetzt; die Colormap bei RGB heißt „— none —“.

### 7.0 Kurzfassung

- **Aufteilung:** links Leiste (48 px) und Panel (340 px) für Listen und Suche; Mitte Karte; rechts **eine** Seitenleiste von 320 px, bündig am rechten Rand, von unter der Knopfzeile oben (64 px) bis zum Fuß des Fensters. Unten in der Mitte der Karte Auswahl- und Zeitleiste wie heute (§7.2).
- **Die Seitenleiste** zeigt die Einstellungen der offenen Ansicht oder des offenen Layers in fester Reihenfolge: Kopf (Titel, „Temporary“, Auge, rotes x; darunter Datensatz und `‹ Datum ›`), „Display“ (Band, Min, Max, Colormap, Opacity, darunter Auto · Apply · Save/Apply to all), „Actions“ (§7.3). Ein Bauteil `Inspector` für alle drei Arten.
- **Processing und Seitenleiste** teilen sich den rechten Rand (Empfehlung V2, §7.2): das Processing-Panel liegt in derselben Spalte, breiter, und deckt die Einstellungen ab, solange es offen ist; beim Schließen sind sie wieder da. Frage 1.
- **Unter 900 px:** die Seitenleiste wird ein Blatt von unten (von der Leiste bis zum rechten Rand, höchstens 55 % der Höhe, Griff zum Einklappen auf den Kopf), wie heute das Processing-Panel; Auswahl- und Zeitleiste liegen darüber (§7.2).
- **Tokens** in einer neuen Datei `frontend/src/tokens.css`: Abstände 4/8/12/16/24/32, Schriftgrade 11/12/13/15/17, Radien 6/10/Pille, Linien, Steuerhöhe 28 px, Farben hell/dunkel (die heutigen Namen bleiben). Eine Schriftfamilie: System-Schrift, Ziffern gleich breit (Frage 4, ersetzt die Monospace-Regel des Prototyps).
- **Schnitt:** UI-03a Seitenleiste + Tokens (diese Session), UI-03b Processing-Panel (nach #273), UI-03c Processing-Manager (nach UI-03b). UI-04 zieht die Tokens durch die übrige Oberfläche und übernimmt Zahlenformat, weniger Text, Begriffsliste, Leitfaden und die drei Funde bei 320/360 px (§7.6).
- **Fragen an Otto:** sieben offen, am Ende (§7.8); Frage 7 hat Otto mit UI-04 beantwortet.

### 7.1 Stand im Code [P]

- **Box heute:** `ViewerControls.tsx` (Ansicht der Suche und angeheftete Ansicht, `compact`), `ResultControls.tsx` (Ergebnis-Layer), gemeinsam `RenderFields.tsx` (Band · vmin · vmax · Colormap), `OpacityRow.tsx`, `CloseButton.tsx`, `useEscClose.ts`. In `App.tsx` liegt sie in `.overlay.bottom` über `SelectionBlock`, als `Draggable` (verschiebbar), 672 px breit (`.scene-view`, 12er-Raster, `index.css`), unter 600 px vier Spalten.
- **Wechsel:** `focusMode` (Ansicht) bzw. `resultViewLayerId` (Ergebnis); `viewOfLayer` (angeheftete Ansicht). Schließen ohne „Save“ stellt den gespeicherten Stand her (`revertViewLayer`, `MapLayer.saved`, #272).
- **Processing-Panel:** `.processing-sheet` liegt schon heute rechts: `top: 64px; right: 16px; bottom: 16px; width: clamp(420px, 36vw, 600px)` (1280 px → 460, 1920 px → 600); unter 900 px ein Blatt von unten (`max-height: 60vh`, Griff). Es öffnet aus der Auswahlleiste, aus der Ansicht („⚙ Process“) und aus dem Processing-Manager (Details eines Jobs). Die Box der Ansicht weicht ihm heute nach links aus (`.bottom.beside-sheet`).
- **Links:** `.app-rail` 48 px, `.dock` 340 px (Suche, Layer-Manager, Ergebnisse, Processing-Manager), volle Höhe, bündig.
- **Oben rechts:** „⤢ Zoom to selection“, „Basemap“, „Light/Dark“ (`top: 16px`). **Unten rechts:** MapLibre-Zoomknöpfe (`NavigationControl`, `MapView.tsx`) und Attribution, beide lägen unter einer Seitenleiste.
- **Gestaltung:** zwei Themen über `.app[data-theme]` mit Farbtoken (`--panel-bg`, `--panel-border`, `--accent`, `--accent-2`, `--text`, `--muted`, `--input-bg`, `--glow`, `--row-hover`, `--map-bg`). Sonst keine Tokens: in `index.css` (rund 3400 Zeilen) stehen 599 Zeilen mit `px`, Schriftgrade 8 bis 16 px in neun Stufen (am häufigsten 11, 10, 12), Radien 1 bis 10 px in sechs Stufen. Schrift durchgehend `var(--mono)` (31 Stellen); die Schriften werden nicht geladen, es greift der System-Rückfall (Inventar).

### 7.2 Konzept: Aufteilung des Bildschirms

**Grundsatz [A]:** links das, womit man sucht und auswählt (Listen, Panels); rechts das, was zum gerade Gewählten gehört (Einstellungen, Processing eines Jobs). Das entspricht der Ordnung „Sidebar links, Inspector rechts“ (§7.5) und dem heutigen Platz des Processing-Panels.

**Skizze 1920 × 1080, Panel links offen, Ansicht offen:**

```
┌──┬──────────────┬───────────────────────────────────────────┬──────────────────┐
│  │              │                  [⤢ Zoom][Basemap][☾ Dark] │  (64 px frei)    │
│R │  Panel       │                                           ├──────────────────┤
│a │  (Search /   │                                           │ S2 · Crop  [Tmp] │
│i │  Layers /    │                                           │        👁   x    │
│l │  Results /   │               K A R T E                   │ [S2A ▾] ‹ 12 Jun›│
│  │  Jobs)       │                                           │ DISPLAY          │
│48│  340 px      │                                           │ Band     [RGB ▾] │
│  │              │                                           │ Min [  ] Max [  ]│
│  │              │                                           │ Colormap [none▾] │
│  │              │       ┌───────────────────────────┐       │ Opacity ━━━━○    │
│  │              │       │ Auswahl + Zeitleiste      │   [+] │ [Auto][Apply][⋯] │
│  │              │       └───────────────────────────┘   [-] │ ACTIONS          │
│  │              │                            © Attribution  │ …                │
└──┴──────────────┴───────────────────────────────────────────┴──────────────────┘
   48             388                                      1600              1920
```

Maße (Breite der freien Karte = Fenster − Leiste − Panel − Seitenleiste):

| Fenster | Leiste | Panel links | Karte frei | Seitenleiste | Processing (V2) |
|---|---|---|---|---|---|
| 1920 | 48 | 340 | 1212 (ohne Panel 1552) | 320 | 600 statt 320 → Karte 932 |
| 1280 | 48 | 340 | 572 (ohne Panel 912) | 320 | 520 statt 320 → Karte 372 |
| 360 | 48 | über die Karte (wie heute) | 312 | Blatt von unten, 312 × höchstens 55 % | Blatt wie heute |

- **Seitenleiste:** `top: 64px; right: 0; bottom: 0; width: 320px`, linke Kante als Linie, keine Ecken (wie das Panel links), Hintergrund `--panel-bg` mit Unschärfe. Kopf und Fuß stehen, die Mitte scrollt. Sie ist nicht mehr verschiebbar (heute `Draggable`): ein fester Platz ist der Kern des Wunsches. Die Karte bleibt links davon bedienbar; unter der Leiste selbst nicht (sie ist undurchsichtig genug, um zu lesen).
- **Breite 320 px [A]:** das Raster aus §7.3 braucht 288 px Inhalt (zwei Zahlfelder nebeneinander je 88 px mit Beschriftung, Dropdowns 184 px); 280 px wäre am Rand, 360 px kostet bei 1280 px 40 px Karte. Frage 2.
- **Unten:** Auswahl- und Zeitleiste bleiben, wo sie sind, und werden in der freien Karte zwischen Leiste links und Seitenleiste mittig gesetzt (wie heute `.beside-sheet`); die Regel aus NM4-66 (sie weichen dem Panel links nicht aus) bleibt.
- **Oben rechts:** die drei Knöpfe bleiben über der Seitenleiste am rechten Rand (`top: 16px`); die Seitenleiste beginnt darunter.
- **Unten rechts:** Zoomknöpfe, Attribution und das Zeichen „Preview“ rücken um die Breite der Seitenleiste nach links, solange sie offen ist (Klasse an `.app`, CSS-Variable `--inspector-width`; MapLibre bleibt unverändert).
- **Statusleiste oben:** mittig in der freien Karte wie die Leiste unten.

**Processing und Seitenleiste (Frage 1):**

- **V1** Processing-Panel nach links an den Platz des Panels (breit, 520–600 px), Seitenleiste rechts bleibt immer frei für Einstellungen. Nachteil: Layer-Manager und Suche sind verdeckt, solange Processing offen ist; die Details eines Jobs ersetzen die Liste der Jobs (Rückweg „‹ Jobs“ nötig); bei 1280 px mit Seitenleiste nur 352 px Karte.
- **V2 (Empfehlung)** eine Spalte rechts: das Processing-Panel öffnet an der Stelle der Seitenleiste, breiter (`clamp(520px, 34vw, 640px)`: 1280 → 520, 1920 → 640), und deckt die Einstellungen ab; schließt es (rotes x, Esc), sind die Einstellungen wieder da, mit dem, was darin stand. Wie ein Schritt tiefer auf demselben Platz („⚙ Process“ in der Ansicht führt nach rechts weiter, x führt zurück). Die Jobliste links und die Details rechts bleiben wie heute. Nachteil: Während Processing offen ist, sind die Einstellungen der Ansicht nicht zu sehen; das Panel hat seine eigene Vorschau mit Band · vmin · vmax · Colormap.
- **V3** beide nebeneinander rechts (Seitenleiste links neben Processing). Bei 1280 px bleiben mit Panel links 32 px Karte; nur ab etwa 1600 px brauchbar.

**Unter 900 px (Frage 5):** die Seitenleiste wird ein Blatt von unten, von der Leiste links bis zum rechten Rand, höchstens 55 % der Höhe, mit dem Griff des Processing-Panels (Klick klappt auf den Kopf ein, Titel und x bleiben sichtbar). Auswahl- und Zeitleiste stehen darüber (wie heute `.beside-sheet` unter 900 px); ist das Blatt eingeklappt, rücken sie nach unten. Zoomknöpfe und Attribution rücken über das Blatt. Alternative: Blatt über die ganze Höhe (dann ist die Karte nicht zu sehen, während man die Werte ändert).

### 7.3 Die Seitenleiste (Inspector), Teil 1

Ein Bauteil `Inspector.tsx` mit drei Inhalten (Ansicht der Suche, angeheftete Ansicht, Ergebnis-Layer); `ViewerControls` und `ResultControls` liefern nur noch ihre Felder und Aktionen, Rahmen und Reihenfolge kommen aus dem Bauteil. Feste Reihenfolge, gleiche Plätze für alle drei:

```
┌────────────────────────────────────┐
│ Sentinel-2 · Crop  [Temporary] 👁 x│  Kopf, Zeile 1 (Titel, Kasten, Auge, rotes x)
│ [Sentinel-2 L2A ▾]  ‹ 12 Jun 2026 ›│  Kopf, Zeile 2 (Datensatz, Zeitschritt, NM4-53)
├────────────────────────────────────┤
│ DISPLAY                            │  Abschnitt 1
│ Band      [ RGB                 ▾] │
│ Range     [ 100   ] – [ 2900  ]    │
│           [ Values | %  ]          │
│ Colormap  [ — none —            ▾] │  gesperrt bei RGB, Grund im Tooltip
│ Opacity   ━━━━━━━━━━━━━━○  80 %    │  gesperrt in der Ansicht der Suche (Frage 6)
│ [ Auto ]  [ Apply ]  [ Apply to all]│  bzw. „Save“ am Layer
├────────────────────────────────────┤
│ ACTIONS                            │  Abschnitt 2
│ [＋ Add to layers ] [＋ Add all   ] │
│ [⚙ Process       ] [⇩ Download    ]│
│ [‹ Change image  ] [✕ Clear       ]│
└────────────────────────────────────┘
```

- **Raster:** Beschriftung links in einer Spalte von 72 px (Apple-Formular, §7.5), Bedienelement rechts; jede Zeile 28 px hoch, 8 px Abstand, 24 px zwischen Abschnitten; Abschnittsüberschrift 11 px, halbfett, `--muted`. Keine Rahmen um Abschnitte, nur eine Linie unter dem Kopf.
- **Gesperrt statt weg:** was für die Wahl nicht gilt, bleibt an seinem Platz, gesperrt mit Grund im Tooltip (Colormap bei RGB, Pfeile bei einem Bild, Band bei einem Ergebnis mit einem Band). Regeln aus #272 unverändert (Vorgabe oben): Apply zeichnet, Save behält, Schließen ohne Save stellt den gespeicherten Stand her.
- **Kopf, Zeile 2 am Layer:** das Aufnahmedatum als Text an der Stelle von `‹ Datum ›` (NM4-65), Pfeile gesperrt („A layer holds one image“); ohne Datum bleibt die Zeile leer stehen, damit „Display“ immer an derselben Höhe beginnt [A].
- **Actions je Art (Frage 6):** Ansicht der Suche: „＋ Add to layers“, „＋ Add all to layers“ (gesperrt bei einem Bild), „⚙ Process“, „‹ Change image“, „✕ Clear“, wie heute. Angeheftete Ansicht und Ergebnis-Layer: Empfehlung, der Abschnitt bleibt mit den Knöpfen, die der Layer-Manager heute in der Zeile hat (⇩ Download), Entfernen bleibt im Layer-Manager.
- **Wechsel:** eine andere Ansicht bzw. ein anderer Layer tauscht den Inhalt, die Leiste bleibt stehen (kein Schließen und Öffnen, keine Animation); für den alten Layer gilt „Schließen ohne Save“ wie heute.
- **Schließen:** rotes x (`CloseButton`) und Esc (`useEscClose`, Ausnahmen wie heute: Feld, Menü, Panel am Rand). Fokus nach dem Schließen auf das Element, das sie geöffnet hat (Layer-Zeile bzw. Knopf der Auswahlleiste) [A].
- **Bedienelemente:** Segment-Umschalter (Values | %), Schieber (Opacity), Dropdowns und Zahlfelder einheitlich in Höhe 28 px, Radius 6 px, gleiche Fokuslinie; Knöpfe in zwei Formen (gefüllt für den Hauptknopf, Umriss für die übrigen).

### 7.4 Tokens

**Wo:** neue Datei `frontend/src/tokens.css`, in `main.tsx` vor `index.css` geladen. Darin `:root` (Abstände, Schrift, Radien, Höhen) und die beiden Themen (`.app[data-theme='normal']`, `.app[data-theme='tech']`) mit den Farben, die heute in `index.css` stehen (die Namen bleiben, neu kommen nur die fehlenden). Komponenten benutzen nur `var(--…)`; ein Test liest die CSS-Dateien und schlägt fehl, wenn in den von UI-03 umgestellten Bereichen ein harter Wert für Abstand, Schriftgrad oder Radius steht (Gegenprobe: ein eingefügter Wert macht ihn rot).

| Gruppe | Tokens | Werte |
|---|---|---|
| Abstand | `--space-1` … `--space-6` | 4, 8, 12, 16, 24, 32 px |
| Schriftgrad | `--text-xs`, `--text-sm`, `--text-md`, `--text-lg`, `--text-xl` | 11, 12, 13, 15, 17 px |
| Zeilenhöhe | `--leading-tight`, `--leading` | 1.2, 1.4 |
| Gewicht | `--weight-regular`, `--weight-semibold` | 400, 600 |
| Radius | `--radius-sm`, `--radius-md`, `--radius-full` | 6, 10, 999 px |
| Linie | `--line-width`, `--line` (= `--panel-border`), `--line-soft` | 1 px, Farbe je Thema |
| Höhe | `--control-height`, `--control-height-sm` | 28, 22 px |
| Breiten | `--rail-width`, `--dock-width`, `--inspector-width`, `--sheet-wide-width` | 48, 340, 320, `clamp(520px, 34vw, 640px)` |
| Farbe neu | `--surface-2` (Feldhintergrund), `--danger` (rotes x), `--focus` | je Thema |
| Schrift | `--font` (System), `--font-mono` (nur Code und Formeln) | `system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif` |

- **Schrift (Frage 4):** Empfehlung System-Schrift überall mit `font-variant-numeric: tabular-nums` (Ziffern gleich breit, Zahlen stehen untereinander); Großschreibung und Sperrung nur noch für Abschnittsüberschriften. Das ersetzt die Monospace-Regel des Prototyps (Inventar, „HUD-Oberflächendesign“); die dunklen Tafeln und Farbtoken bleiben.
- **Kleinster Grad 11 px** (heute 8–10 px an rund 34 Stellen): Lesbarkeit und Kontrast, im Inventar als Mangel vermerkt.
- **Umfang je Teil:** Teil 1 legt alle Tokens an, stellt Seitenleiste, die gemeinsamen Bedienelemente (`.ghost-btn`, `.primary-btn`, `select`, Zahlfelder, `.pp-seg`, `.close-x`) und die Schrift um. Teil 2 und 3 stellen ihre Bereiche um. Die übrigen Panels (Suche, Layer-Manager, Ergebnisse, Menüs, Dialoge) stellt UI-04 um; dort kommen auch der Leitfaden und die Prüfungen gegen Rückfälle über die ganze Oberfläche hin. Der Token-Test von UI-03 ist so gebaut, dass UI-04 nur die Liste der geprüften Bereiche erweitert.

### 7.5 Recherche mit Quellen

(folgt)

### 7.6 Schnitt und Konflikte

1. **UI-03a, diese Session nach Freigabe:** Tokens (`tokens.css`), Schrift, gemeinsame Bedienelemente, `Inspector.tsx` mit den drei Inhalten, Platz rechts und Blatt unter 900 px, Mitte der Leiste unten und der Statusleiste, Zoomknöpfe/Attribution, Processing auf dem Platz der Seitenleiste (V2) mit unveränderter Breite. Tests (vitest, jsdom) und Browser-Skripte `settings-box.cjs` (neu: Platz und Maße der Leiste bei 1280/1920/360, Wechsel, x, Esc), `view-index`, `view-steps`, `nm4-65`, `play-steps`, `results-layer`, `dem-layers`, `layer-settings` nachgezogen. Geschätzt 350–450 Zeilen ohne Tests; liegt es darüber, Schnitt in 3a1 (Tokens, Schrift, Bedienelemente) und 3a2 (Seitenleiste).
2. **UI-03b, neue Session:** Processing-Panel breiter (`--sheet-wide-width`), Abschnitte Herkunft/Eingabe · Bandvorrat · Schritte · Ausgabe · Vorschau · Start, Schritte als Karten (Kopf: Name, Umbenennen, ↑ ↓, Entfernen; Inhalt im selben Raster). Erst nach dem Merge von #273 (NM4-71 ändert `ProcessingPanel.tsx`, `StepForm.tsx`, `NormalizeFields.tsx`) und nicht gleichzeitig mit einem Frontend-Teil von NM4-71.
3. **UI-03c, neue Session nach UI-03b:** Processing-Manager: Gruppe als Kopfzeile mit Anzahl und Zustand, Jobs in gleicher Zeilenform mit festen Spalten (Status · Titel · Datum · Aktionen), je Zeile ein Hauptknopf (Download bzw. Retry/Restore) und „⋯“ für den Rest (heute schon `RowMenu`). Breite: das Panel links bleibt 340 px, außer Otto will den Manager breiter (Frage 8).

**Konflikte:** #270 (NM4-29b) und #273 (NM4-71) berühren `ViewerControls`, `ResultControls`, `index.css` und `App.tsx` nicht [P, `git diff --stat`]; Teil 1 kann neben ihnen laufen. Teil 2 kollidiert mit #273. UI-04 (mit NM4-56) kommt nach UI-03 und baut auf den Tokens auf; UI-03 ändert deshalb nach Teil 1 keine Werte der Tokens mehr ohne Frage an Otto.

**Grenze zu UI-04, nicht doppelt [A]:**

| Thema | UI-03 | UI-04 |
|---|---|---|
| Zahlenformat (NM4-21) | nicht berührt; Felder zeigen weiter, was der Store liefert | eine Formatierfunktion für alle Anzeigen, auch in der Seitenleiste (UI-04) |
| Weniger Text (NM4-22) | Seitenleiste, Processing-Panel und -Manager gleich nach der Regel (Erklärung hinter (i)/Tooltip) | übrige Panels; die Bestandsaufnahme markiert die UI-03-Bereiche als erledigt |
| Schmale Fenster | Seitenleiste als Blatt, Leiste unten über dem Blatt, Zoomknöpfe | die drei Funde aus Punkt 58 (320 px Control-Menü, Ebenenliste über Statusleiste, Statusmeldung) |
| Tokens | festlegen (`tokens.css`); Seitenleiste, gemeinsame Bedienelemente, Schrift, Processing-Panel und -Manager | überall durchziehen, Prüfung gegen Rückfälle über die ganze Oberfläche |
| Begriffe, Leitfaden | Wortlaut der Seitenleiste und des Processing wie heute (Englisch, kurz) | Begriffsliste, `docs/ui/leitfaden.md` (UI-03 liefert dafür §7.3 und §7.4 als Grundlage) |

### 7.7 Prüfung und Abnahme von Teil 1

- **vitest:** `Inspector` zeigt für alle drei Arten dieselbe Reihenfolge der Abschnitte; Wechsel tauscht den Inhalt ohne Schließen; x und Esc schließen und stellen ohne „Save“ den gespeicherten Stand her (Gegenprobe: mit „Save“ bleibt er); gesperrte Felder tragen ihren Grund; Processing öffnet an derselben Stelle und gibt die Einstellungen beim Schließen zurück; Token-Test aus §7.4. Fehlerfälle: Layer während offener Leiste entfernt (Leiste schließt), Ansicht ohne Bild, Esc in einem Feld.
- **Browser (Playwright, vorhandene Attrappe ohne Backend):** hell/dunkel × 1280/1920/360 × Ansicht/angeheftete Ansicht/Ergebnis; gemessen: Platz und Breite der Leiste, gleiche y-Lage der Abschnitte bei allen drei Arten, kein Überlauf, Leiste unten mittig in der freien Karte, Zoomknöpfe sichtbar. Bilder nur im PR beschrieben.
- **Prüfanleitung für Otto** im PR.

### 7.8 Fragen an Otto

1. **Processing und Seitenleiste:** (1) eine Spalte rechts, Processing deckt die Einstellungen ab und gibt sie beim Schließen zurück (**Empfehlung**, V2); (2) Processing nach links an den Platz des Panels (V1); (3) nebeneinander rechts (V3).
2. **Breite der Seitenleiste:** (1) 320 px (**Empfehlung**); (2) 360 px; (3) 280 px.
3. **Rand:** (1) bündig am rechten Rand, volle Höhe unter der Knopfzeile, wie das Panel links (**Empfehlung**); (2) schwebend mit 16 px Abstand und runden Ecken wie heute das Processing-Panel.
4. **Schrift:** (1) System-Schrift überall, Ziffern gleich breit (**Empfehlung**, ersetzt Monospace aus dem Prototyp); (2) System-Schrift, Monospace für Zahlen und Kennungen; (3) Monospace bleibt.
5. **Unter 900 px:** (1) Blatt von unten, höchstens 55 % Höhe, einklappbar (**Empfehlung**); (2) Blatt über die ganze Höhe.
6. **Gesperrt statt weg in der Seitenleiste:** (1) Opacity in der Ansicht der Suche gesperrt („Add to layers to set the opacity“), am Layer ein Abschnitt „Actions“ mit ⇩ Download (**Empfehlung**); (2) Opacity und „Actions“ nur, wo sie gelten.
7. **Tokens für die übrigen Panels:** **entschieden (Otto, 01.11.2026):** UI-04 „Einheitlichkeit“ zieht sie überall durch; NM4-56 geht darin auf.
8. **Processing-Manager (Teil 3):** (1) bleibt 340 px links, Ordnung über feste Spalten und „⋯“ (**Empfehlung**); (2) breiter (420 px), alle Panels links mit.
