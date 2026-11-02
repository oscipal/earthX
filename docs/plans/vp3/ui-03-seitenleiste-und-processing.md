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

## 7. Plan (01.11.2026, von Otto am 02.11.2026 freigegeben)

**Freigabe (Otto, 02.11.2026, zu #277):** Fragen 1 bis 6 nach Option 1 (eine Spalte rechts; 320 px; bündig, volle Höhe; System-Schrift mit gleich breiten Ziffern; Blatt von unten, höchstens 55 %, einklappbar; ⇩ zusätzlich unter „Actions“, heutige Stellen bleiben, Opacity in der Ansicht der Suche gesperrt mit Grund). Frage 7 war schon beantwortet (UI-04). **Frage 8 abweichend** (in Ottos Antwort Punkt 7): Der Processing-Manager wird ein frei schwebendes Fenster statt eines festen Panels links (§7.9). Die Umsetzung beginnt mit UI-03a.

Stufe B: Bis zur Freigabe ist kein Produktivcode geändert. Grundlage ist `main` nach #272 (NM4-54), #273 (NM4-71) und #270 (NM4-29b), geholt am 02.11.2026. Belegstufen wie in UI-02: [P] Code oder Primärquelle gelesen, [M] in der Sitzung gemessen, [S] nur Zusammenfassung einer Websuche (vor einer Entscheidung gegenzuprüfen), [A] eigene Ableitung.

**Abgrenzung zu UI-04 (Otto, 01.11.2026):** NM4-56 geht in UI-04 „Einheitlichkeit“ auf (`docs/plans/vp3/ui-04-einheitlichkeit.md`, seit 02.11.2026 auf `main`): Bestandsaufnahme über die ganze Oberfläche, Begriffsliste, Leitfaden `docs/ui/leitfaden.md`, Prüfungen gegen Rückfälle, Zahlenformat, weniger Text und schmale Fenster. **UI-03 legt die Tokens fest, UI-04 zieht sie überall durch.** Wo §3 und §4 oben NM4-56 nennen, gilt UI-04 (Originaltext bleibt stehen).

**Vorgabe Otto (01.11.2026, zum Plan):** Die Regeln aus #272 gelten auch in der Seitenleiste: am Layer ist ein Band erst mit „Apply“ zu sehen, „Save“ speichert; „Temporary“ steht neben dem Titel der Ansicht wie umgesetzt; die Colormap bei RGB heißt „— none —“.

### 7.0 Kurzfassung

- **Aufteilung:** links Leiste (48 px) und Panel (340 px) für Listen und Suche; Mitte Karte; rechts **eine** Seitenleiste von 320 px, bündig am rechten Rand, von unter der Knopfzeile oben (64 px) bis zum Fuß des Fensters. Unten in der Mitte der Karte Auswahl- und Zeitleiste wie heute (§7.2).
- **Die Seitenleiste** zeigt die Einstellungen der offenen Ansicht oder des offenen Layers in fester Reihenfolge: Kopf (Titel, „Temporary“, Auge, rotes x; darunter Datensatz und `‹ Datum ›`), „Display“ (Band, Min, Max, Colormap, Opacity, darunter Auto · Apply · Save/Apply to all), „Actions“ (§7.3). Ein Bauteil `Inspector` für alle drei Arten.
- **Processing und Seitenleiste** teilen sich den rechten Rand (Empfehlung V2, §7.2): das Processing-Panel liegt in derselben Spalte, breiter, und deckt die Einstellungen ab, solange es offen ist; beim Schließen sind sie wieder da. Frage 1.
- **Unter 900 px:** die Seitenleiste wird ein Blatt von unten (von der Leiste bis zum rechten Rand, höchstens 55 % der Höhe, Griff zum Einklappen auf den Kopf), wie heute das Processing-Panel; Auswahl- und Zeitleiste liegen darüber (§7.2).
- **Tokens** in einer neuen Datei `frontend/src/tokens.css`: Abstände 4/8/12/16/24/32, Schriftgrade 11/12/13/15/17, Radien 6/10/Pille, Linien, Steuerhöhe 28 px, Farben hell/dunkel (die heutigen Namen bleiben). Eine Schriftfamilie: System-Schrift, Ziffern gleich breit (Frage 4, ersetzt die Monospace-Regel des Prototyps).
- **Schnitt:** UI-03a Seitenleiste + Tokens (diese Session), UI-03b Processing-Panel (nach UI-03a; #273 ist gemergt), UI-03c Processing-Manager (nach UI-03b). UI-04 zieht die Tokens durch die übrige Oberfläche und übernimmt Zahlenformat, weniger Text, Begriffsliste, Leitfaden und die drei Funde bei 320/360 px (§7.6).
- **Fragen an Otto:** alle beantwortet (§7.8): 1–6 nach Empfehlung, 7 mit UI-04, 8 abweichend: Processing-Manager als schwebendes Fenster (§7.9, Teil 3).

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
| 1920 | 48 | 340 | 1212 (ohne Panel 1552) | 320 | 640 statt 320 → Karte 892 |
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
- **V2 (Empfehlung, entschieden: Otto, 02.11.2026)** eine Spalte rechts: das Processing-Panel öffnet an der Stelle der Seitenleiste, breiter (`clamp(520px, 34vw, 640px)`: 1280 → 520, 1920 → 640), und deckt die Einstellungen ab; schließt es (rotes x, Esc), sind die Einstellungen wieder da, mit dem, was darin stand. Wie ein Schritt tiefer auf demselben Platz („⚙ Process“ in der Ansicht führt nach rechts weiter, x führt zurück). Die Jobliste links und die Details rechts bleiben wie heute. Nachteil: Während Processing offen ist, sind die Einstellungen der Ansicht nicht zu sehen; das Panel hat seine eigene Vorschau mit Band · vmin · vmax · Colormap.
- **V3** beide nebeneinander rechts (Seitenleiste links neben Processing). Bei 1280 px bleiben mit Panel links 52 px Karte; nur ab etwa 1600 px brauchbar.

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
│ vmin      [ 100                 ]  │
│ vmax      [ 2900          ] [Val▾] │
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

- **Namen:** Band · vmin · vmax · Colormap wie überall (Regel NM4-65 Teil 6); der Umschalter „Value / %“ bleibt das kleine Dropdown hinter vmax. Die Skizze in §7.2 mit „Min/Max“ ist nur Kurzschrift.
- **Raster:** Beschriftung links in einer Spalte von 72 px (Apple-Formular, §7.5), Bedienelement rechts; jede Zeile 28 px hoch, 8 px Abstand, 24 px zwischen Abschnitten; Abschnittsüberschrift 11 px, halbfett, `--muted`. Keine Rahmen um Abschnitte, nur eine Linie unter dem Kopf.
- **Gesperrt statt weg:** was für die Wahl nicht gilt, bleibt an seinem Platz, gesperrt mit Grund im Tooltip (Colormap bei RGB, Pfeile bei einem Bild, Band bei einem Ergebnis mit einem Band). Regeln aus #272 unverändert (Vorgabe oben): Apply zeichnet, Save behält, Schließen ohne Save stellt den gespeicherten Stand her.
- **Kopf, Zeile 2 am Layer:** das Aufnahmedatum als Text an der Stelle von `‹ Datum ›` (NM4-65), Pfeile gesperrt („A layer holds one image“); ohne Datum bleibt die Zeile leer stehen, damit „Display“ immer an derselben Höhe beginnt [A].
- **Actions je Art (Frage 6):** Ansicht der Suche: „＋ Add to layers“, „＋ Add all to layers“ (gesperrt bei einem Bild), „⚙ Process“, „‹ Change image“, „✕ Clear“, wie heute. **Downloads liegen heute nicht in der Box** [P]: die der Auswahl („⇩ Download crop“, „⇩ Download full scene“) in der Auswahlleiste unten, die eines Layers (⇩, auch „Download (ZIP)“ eines Ergebnisses) in seiner Zeile im Layer-Manager. Empfehlung: ⇩ zusätzlich in „Actions“ der Seitenleiste, mit derselben Funktion und demselben Dialog (`DownloadDialog`), ohne sie an den alten Stellen zu entfernen; Entfernen eines Layers bleibt nur im Layer-Manager.
- **Wechsel:** eine andere Ansicht bzw. ein anderer Layer tauscht den Inhalt, die Leiste bleibt stehen (kein Schließen und Öffnen, keine Animation); für den alten Layer gilt „Schließen ohne Save“ wie heute.
- **Schließen:** nur mit dem roten x (`CloseButton`); an der Ansicht der Suche tut es, was „✕ Clear“ tat (`exitFocus`: Ansicht von der Karte, „Temporary“ geht), „✕ Clear“ selbst entfällt (Browsertest Otto, 02.11.2026, §7.10). **Esc schließt nichts** (Regel Otto, 02.11.2026, zu #277; ersetzt die frühere Auslegung „x und Esc wie Clear“ und gilt in der ganzen Oberfläche: keine Ansicht, keine Seitenleiste, kein Processing-Panel, kein Blatt, kein Panel links, kein Pop-up mit Feldern; nach Ottos Antwort zu #277 auch kein Menü, keine Auswahlliste und kein Tooltip). Ausnahmen, weil dort nichts verloren geht: Esc = „Cancel“ in Bestätigungsdialogen und Esc beendet „Flip through layers“. Am Layer wie heute: Schließen ohne „Save“ stellt den gespeicherten Stand her. Fokus nach dem Schließen auf das Element, das sie geöffnet hat (Layer-Zeile bzw. Knopf der Auswahlleiste) [A].
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
| Höhe | `--control-height`, `--control-height-sm`; `--control-height-touch` | 28, 22 px; 44 px: Touch (`pointer: coarse`) und unter 900 px wird `--control-height` zu `--control-height-touch` (Otto, 02.11.2026) |
| Breiten | `--rail-width`, `--dock-width`, `--inspector-width`, `--sheet-wide-width` | 48, 340, 320, `clamp(520px, 34vw, 640px)` |
| Farbe neu | `--surface-2` (Feldhintergrund), `--danger` (rotes x), `--focus` | je Thema |
| Schrift | `--font` (System), `--font-mono` (nur Code und Formeln) | `system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif` |

- **Schrift (Frage 4):** Empfehlung System-Schrift überall mit `font-variant-numeric: tabular-nums` (Ziffern gleich breit, Zahlen stehen untereinander); Großschreibung und Sperrung nur noch für Abschnittsüberschriften. Das ersetzt die Monospace-Regel des Prototyps (Inventar, „HUD-Oberflächendesign“); die dunklen Tafeln und Farbtoken bleiben.
- **Kleinster Grad 11 px** (heute 8–10 px an rund 34 Stellen): Lesbarkeit und Kontrast, im Inventar als Mangel vermerkt.
- **Umfang je Teil:** Teil 1 legt alle Tokens an, stellt Seitenleiste, die gemeinsamen Bedienelemente (`.ghost-btn`, `.primary-btn`, `select`, Zahlfelder, `.pp-seg`, `.close-x`) und die Schrift um. Teil 2 und 3 stellen ihre Bereiche um. Die übrigen Panels (Suche, Layer-Manager, Ergebnisse, Menüs, Dialoge) stellt UI-04 um; dort kommen auch der Leitfaden und die Prüfungen gegen Rückfälle über die ganze Oberfläche hin. Der Token-Test von UI-03 ist so gebaut, dass UI-04 nur die Liste der geprüften Bereiche erweitert.

### 7.5 Recherche mit Quellen

Abgerufen am 02.11.2026. Erreichbar waren aus der Sitzung `developer.apple.com` (HIG und SwiftUI-Doku über deren JSON-Daten) und `raw.githubusercontent.com`; die Seiten von Esri (doc.arcgis.com), Google (developers.google.com), Copernicus/Sentinel Hub, Material (m3.material.io), IBM Carbon und designtokens.org waren gesperrt und sind **nur Suchtreffer** [S], vor einer Entscheidung, die an ihnen hängt, gegenzuprüfen.

**Apple, im Original gelesen [P]:**

- **Inspector rechts, im schmalen Fenster ein Blatt:** SwiftUI `inspector(isPresented:content:)`: „an inspector can present as a trailing column in a horizontally regular size class, but adapt to a sheet in a horizontally compact size class“. `inspectorColumnWidth(_:)` und `inspectorColumnWidth(min:ideal:max:)`: Beispiel mit fester Breite 225 pt bzw. ideal 225, min 150, max 400 pt. → Platz rechts und Blatt unter 900 px (§7.2); 320 px liegt im Bereich, den Apple als Beispiel nennt [A]. https://developer.apple.com/documentation/swiftui/view/inspector(ispresented:content:), https://developer.apple.com/documentation/swiftui/view/inspectorcolumnwidth(min:ideal:max:)
- **Split Views:** Keynote (macOS) legt „slide navigator, presenter notes, and the inspector pane in areas that surround the main slide canvas“; „Consider letting people hide a pane“; „Provide multiple ways to reveal hidden panes“; „Prefer the thin divider style. The thin divider measures one point in width“. → eine Linie statt Rahmen, Schließen per x und Esc. https://developer.apple.com/design/human-interface-guidelines/split-views
- **Sidebars:** „Avoid putting critical information or actions at the bottom of a sidebar“; „Consider automatically hiding and revealing a sidebar when its container window resizes“. → die Knöpfe stehen direkt unter den Feldern im Abschnitt „Display“, nicht am Fuß der Leiste; Blatt unter 900 px. https://developer.apple.com/design/human-interface-guidelines/sidebars
- **Layout:** „Group related items … you might use negative space, container shapes, or separator lines“; „Align elements to make them easier to scan“; wichtiges oben und vorn. → Abstand und Überschrift statt Kästen, Beschriftungsspalte. https://developer.apple.com/design/human-interface-guidelines/layout
- **Typografie macOS (Tabelle „macOS built-in text styles“):** Title 2 17 pt, Title 3 15 pt, Headline 13 pt fett, Body 13 pt, Callout 12 pt, Subheadline 11 pt, Footnote und Caption 10 pt. → Schriftgrade 17/15/13/12/11 (§7.4); 10 pt lassen wir wegen Kontrast auf halbdurchsichtigen Tafeln weg [A]. „use typefaces designed for optimized legibility, like the system fonts“. https://developer.apple.com/design/human-interface-guidelines/typography
- **Segmented Controls:** „a segmented control in an inspector could let people choose one or more attributes“; Segmente gleich breit. → „Values | %“. https://developer.apple.com/design/human-interface-guidelines/segmented-controls
- **Toggles:** Schalter-Stil „only in a list row“; außerhalb ein Knopf, der sich wie ein Schalter verhält. → Auge bleibt Knopf. https://developer.apple.com/design/human-interface-guidelines/toggles
- **Pop-up und Pull-down Buttons:** Pop-up für „a flat list of mutually exclusive options“ (Band, Colormap, Datensatz); Pull-down für Befehle, „Avoid putting all of a view's actions in one pull-down button“, Menü erst ab drei Einträgen. → Teil 3: Hauptknopf sichtbar, Seltenes hinter „⋯“. https://developer.apple.com/design/human-interface-guidelines/pop-up-buttons, https://developer.apple.com/design/human-interface-guidelines/pull-down-buttons
- **Sheets:** Detents „medium“ und „large“, „Include a grabber in a resizable sheet“. → Blatt bis 55 % mit Griff (§7.2). https://developer.apple.com/design/human-interface-guidelines/sheets
- **Lists and Tables:** gruppierter Stil mit Kopf, Fuß und Abstand; kurze Zeilentexte, Auslassung in der Mitte, wo Anfang und Ende zählen. → Teil 3. https://developer.apple.com/design/human-interface-guidelines/lists-and-tables

**Kartenanwendungen:**

- **QGIS, im Original gelesen [P]:** Der „Layer Styling“-Panel (F7, Ctrl+3) ist ein andockbares Panel statt des modalen Eigenschaften-Dialogs; oben ein Dropdown der Layer, darunter Symbology, Transparency, Histogram für Raster; „Apply“ wendet an, ein Haken „Live update“ zeichnet sofort. → bestätigt Apply als eigenen Schritt (Regel aus #272) und den Inhalt-Tausch bei anderem Layer. Dass das Panel standardmäßig rechts andockt, steht dort nicht (nur eigene Kenntnis, nicht belegt). https://raw.githubusercontent.com/qgis/QGIS-Documentation/master/docs/user_manual/introduction/general_tools.rst (Abschnitt „Layer Styling Panel“)
- **Esri Calcite (Bausteine von ArcGIS Online), im Original gelesen [P]:** `calcite-shell-panel` hat drei Breiten: S `12vw` (150–300 px), M `20vw` (240–420 px), L `45vw` (340–680 px). → Seitenleiste 320 px liegt in M, Processing 520–640 px in L. https://raw.githubusercontent.com/Esri/calcite-design-system/main/packages/calcite-components/src/components/shell-panel/shell-panel.scss
- **ArcGIS Online Map Viewer, nur Suchtreffer [S]:** „Properties pane“ für Informationen und Darstellung eines Layers, Stile über den „Settings toolbar“; die Lage rechts ist in den Treffern nicht belegt. https://doc.arcgis.com/en/arcgis-online/create-maps/set-layer-properties.htm
- **Google Earth Engine Code Editor, nur Suchtreffer [S]:** Darstellung eines Layers über `visParams` (`bands`, `min`, `max`, `palette`, `opacity` 0–1) in `Map.addLayer`; der Dialog der Layer-Einstellungen in der Oberfläche ist in den Treffern nicht beschrieben. https://developers.google.com/earth-engine/apidocs/map-addlayer
- **Copernicus Browser / EO Browser, nur Suchtreffer [S]:** Visualisierungen im linken Panel (vordefiniert oder eigenes Skript), „Add to compare“, Vergleich mit „Split“ und „Opacity“. → Gegenbeispiel: dort steht alles links, Einstellungen und Ergebnisse in einer Spalte. https://documentation.dataspace.copernicus.eu/Applications/Browser.html

**Schmale Fenster, Tokens, nur Suchtreffer [S]:**

- **Material 3 Bottom Sheets:** „standard“ ohne Abdunkelung, „modal“ mit; Griff optional, mindestens 48 dp Zielgröße (aus Umsetzungsdokus, die auf m3.material.io verweisen). → Blatt ohne Abdunkelung, damit die Karte bedienbar bleibt. https://api.flutter.dev/flutter/material/BottomSheet-class.html
- **IBM Carbon Spacing:** Skala aus Vielfachen von 2, 4 und 8, Tokens `$spacing-01` … `$spacing-13`, Werte unabhängig von der Fenstergröße. → Skala 4/8/12/16/24/32. https://carbondesignsystem.com/elements/spacing/overview/
- **Design Tokens Community Group:** erste stabile Fassung des Formats 2025.10 (28.10.2025). → Wir legen die Tokens als CSS-Variablen an (keine neue Abhängigkeit); ein Export in dieses Format wäre später ohne Umbau möglich [A]. https://www.w3.org/community/design-tokens/2025/10/28/design-tokens-specification-reaches-first-stable-version/

**Folgerung [A]:** Apple, Calcite und QGIS ordnen die Einstellungen des Gewählten in einer eigenen Spalte, rechts (Apple ausdrücklich „trailing“), schmal (225–420 px), im schmalen Fenster als Blatt; Anwenden ist ein eigener Schritt (QGIS). EO Browser stellt alles links in eine Spalte; das ist das, was Otto heute als „quer durch“ empfindet.

### 7.6 Schnitt und Konflikte

1. **UI-03a, diese Session nach Freigabe:** Tokens (`tokens.css`), Schrift, gemeinsame Bedienelemente, `Inspector.tsx` mit den drei Inhalten, Platz rechts und Blatt unter 900 px, Mitte der Leiste unten und der Statusleiste, Zoomknöpfe/Attribution, Processing auf dem Platz der Seitenleiste (V2) mit unveränderter Breite. Tests (vitest, jsdom) und Browser-Skripte `settings-box.cjs` (neu: Platz und Maße der Leiste bei 1280/1920/360, Wechsel, x, Esc), `view-index`, `view-steps`, `nm4-65`, `play-steps`, `results-layer`, `dem-layers`, `layer-settings` nachgezogen. Geschätzt 350–450 Zeilen ohne Tests; liegt es darüber, Schnitt in 3a1 (Tokens, Schrift, Bedienelemente) und 3a2 (Seitenleiste).
2. **UI-03b, neue Session:** Processing-Panel breiter (`--sheet-wide-width`), Abschnitte Herkunft/Eingabe · Bandvorrat · Schritte · Ausgabe · Vorschau · Start, Schritte als Karten (Kopf: Name, Umbenennen, ↑ ↓, Entfernen; Inhalt im selben Raster). #273 (NM4-71, ändert `ProcessingPanel.tsx`, `StepForm.tsx`, `NormalizeFields.tsx`) ist seit 02.11.2026 gemergt; UI-03b baut auf diesem Stand auf und läuft nicht gleichzeitig mit einem weiteren Frontend-Teil von NM4-71.
3. **UI-03c, neue Session nach UI-03b:** Processing-Manager: Gruppe als Kopfzeile mit Anzahl und Zustand, Jobs in gleicher Zeilenform mit festen Spalten (Status · Titel · Datum · Aktionen), je Zeile ein Hauptknopf (Download bzw. Retry/Restore) und „⋯“ für den Rest (heute schon `RowMenu`). Nicht mehr im Panel links, sondern ein frei schwebendes Fenster (Frage 8, Antwort Otto; §7.9).

**Konflikte:** #270 (NM4-29b) und #273 (NM4-71) sind gemergt (02.11.2026); kein offener Frontend-PR berührt die Seitenleiste. Die drei Teile laufen nacheinander, weil sie sich `index.css` und `tokens.css` teilen. UI-04 (mit NM4-56, Plan `docs/plans/vp3/ui-04-einheitlichkeit.md`) startet nach dem Merge aller Teile von UI-03, allein, und baut auf den Tokens auf; seine Prüfung „keine festen Farb- oder Abstandswerte außerhalb der Tokens“ setzt auf dem Token-Test aus §7.4 auf; UI-03 ändert deshalb nach Teil 1 keine Werte der Tokens mehr ohne Frage an Otto.

**Grenze zu UI-04, nicht doppelt [A]:**

| Thema | UI-03 | UI-04 |
|---|---|---|
| Zahlenformat (NM4-21) | nicht berührt; Felder zeigen weiter, was der Store liefert | eine Formatierfunktion für alle Anzeigen, auch in der Seitenleiste (UI-04) |
| Weniger Text (NM4-22) | Seitenleiste, Processing-Panel und -Manager gleich nach der Regel (Erklärung hinter (i)/Tooltip) | übrige Panels; die Bestandsaufnahme markiert die UI-03-Bereiche als erledigt |
| Schmale Fenster | Seitenleiste als Blatt, Leiste unten über dem Blatt, Zoomknöpfe | die drei Funde aus Punkt 58 (320 px Control-Menü, Ebenenliste über Statusleiste, Statusmeldung) |
| Tokens | festlegen (`tokens.css`); Seitenleiste, gemeinsame Bedienelemente, Schrift, Processing-Panel und -Manager | überall durchziehen, Prüfung gegen Rückfälle über die ganze Oberfläche |
| Begriffe, Leitfaden | Wortlaut der Seitenleiste und des Processing wie heute (Englisch, kurz) | Begriffsliste, `docs/ui/leitfaden.md` (UI-03 liefert dafür §7.3 und §7.4 als Grundlage) |

### 7.7 Prüfung und Abnahme von Teil 1

- **vitest:** `Inspector` zeigt für alle drei Arten dieselbe Reihenfolge der Abschnitte; Wechsel tauscht den Inhalt ohne Schließen; das x schließt und stellt ohne „Save“ den gespeicherten Stand her (Gegenprobe: mit „Save“ bleibt er); Esc schließt keine der drei Arten (Gegenprobe: mit Esc-Schließweg rot); Steuerhöhe 44 px bei Touch und unter 900 px (Token-Test, Browserprüfung bei 360 px und Touch bei 1280 px); gesperrte Felder tragen ihren Grund; Processing öffnet an derselben Stelle und gibt die Einstellungen beim Schließen zurück; Token-Test aus §7.4. Fehlerfälle: Layer während offener Leiste entfernt (Leiste schließt), Ansicht ohne Bild.
- **Browser (Playwright, vorhandene Attrappe ohne Backend):** hell/dunkel × 1280/1920/360 × Ansicht/angeheftete Ansicht/Ergebnis; gemessen: Platz und Breite der Leiste, gleiche y-Lage der Abschnitte bei allen drei Arten, kein Überlauf, Leiste unten mittig in der freien Karte, Zoomknöpfe sichtbar. Bilder nur im PR beschrieben.
- **Prüfanleitung für Otto** im PR.

### 7.8 Fragen an Otto (beantwortet am 02.11.2026)

1. **Processing und Seitenleiste:** (1) eine Spalte rechts, Processing deckt die Einstellungen ab und gibt sie beim Schließen zurück (**Empfehlung**, V2); (2) Processing nach links an den Platz des Panels (V1); (3) nebeneinander rechts (V3). **Antwort Otto: Option 1.**
2. **Breite der Seitenleiste:** (1) 320 px (**Empfehlung**); (2) 360 px; (3) 280 px. **Antwort Otto: Option 1.**
3. **Rand:** (1) bündig am rechten Rand, volle Höhe unter der Knopfzeile, wie das Panel links (**Empfehlung**); (2) schwebend mit 16 px Abstand und runden Ecken wie heute das Processing-Panel. **Antwort Otto: Option 1.**
4. **Schrift:** (1) System-Schrift überall, Ziffern gleich breit (**Empfehlung**, ersetzt Monospace aus dem Prototyp); (2) System-Schrift, Monospace für Zahlen und Kennungen; (3) Monospace bleibt. **Antwort Otto: Option 1.**
5. **Unter 900 px:** (1) Blatt von unten, höchstens 55 % Höhe, einklappbar (**Empfehlung**); (2) Blatt über die ganze Höhe. **Antwort Otto: Option 1.**
6. **Opacity und Downloads in der Seitenleiste:** (1) Opacity in der Ansicht der Suche gesperrt mit Grund („Add to layers to set the opacity“); ⇩ zusätzlich in „Actions“ (Ansicht: Zuschnitt und ganze Szene wie in der Auswahlleiste; Layer: wie in seiner Zeile), die alten Stellen bleiben (**Empfehlung**); (2) Opacity nur am Layer, Downloads nur an den heutigen Stellen; (3) wie (1), aber die Downloads ziehen ganz in die Seitenleiste um (Auswahlleiste und Layer-Zeile ohne ⇩). **Antwort Otto: Option 1.**
7. **Tokens für die übrigen Panels:** **entschieden (Otto, 01.11.2026):** UI-04 „Einheitlichkeit“ zieht sie überall durch; NM4-56 geht darin auf.
8. **Processing-Manager (Teil 3):** (1) bleibt 340 px links, Ordnung über feste Spalten und „⋯“ (**Empfehlung**); (2) breiter (420 px), alle Panels links mit. **Antwort Otto: abweichend:** ein frei schwebendes Fenster, verschiebbar, Größe änderbar (Mindestbreite etwa 420 px), Position und Größe je Browser gemerkt, rotes x und Esc, unter 900 px Blatt von unten; innen feste Spalten, Gruppen als Kopfzeilen, Seltenes hinter „⋯“ (§7.9).

### 7.9 Processing-Manager als schwebendes Fenster (Teil 3, Antwort Otto zu Frage 8)

Gilt für UI-03c; Teil 1 ändert den Manager nicht. Werte [A], mit der Umsetzung im Browser zu bestätigen.

- **Öffnen:** Der Knopf „Jobs“ der Leiste links öffnet und schließt das Fenster (`aria-pressed`); er öffnet kein Panel links mehr. Zählzahl der laufenden Jobs bleibt am Knopf. Die übrigen Panels links bleiben, wie sie sind, und können gleichzeitig offen sein.
- **Maße:** Vorgabe 480 × höchstens 640 px (nie höher als das Fenster minus 80 px), Mindestgröße 420 × 320 px, höchstens das Fenster. Erster Platz: oben links in der Karte, rechts neben Leiste und offenem Panel, `top: 64px` (unter der Knopfzeile, wie die Seitenleiste), nicht über der Spalte rechts.
- **Verschieben und Größe:** Ziehen am Kopf (ganze Kopfzeile außer den Knöpfen; Ziehgriff 2×3 Punkte wie im Layer-Manager); Größe an der rechten unteren Ecke und an den Kanten rechts und unten. Pfeiltasten verschieben, wenn der Kopf den Fokus hat (Tastatur, kein Ziehen nötig). Der Kopf bleibt immer erreichbar: beim Ziehen, beim Laden und wenn das Browserfenster kleiner wird, wird das Fenster so zurückgeschoben, dass mindestens Kopf und 120 px Breite im Fenster liegen.
- **Gemerkt:** Platz und Größe je Browser in `localStorage` (`earthx.jobsWindow`, `{x, y, width, height}` in px). Leerer, gesperrter oder kaputter Speicher (kein JSON, Fremdtypen, negative oder zu kleine Werte, `localStorage` wirft) ergibt die Vorgabe ohne Fehler; geschrieben wird erst am Ende eines Ziehens bzw. einer Größenänderung. Nicht im Permalink.
- **Überlagerung:** Das Fenster liegt über Karte, Panel links, Auswahl- und Zeitleiste und über der Spalte rechts (Seitenleiste bzw. Processing-Panel), unter Dialogen (`DownloadDialog`, Bestätigungen), Menüs und Tooltips. Ein Klick in die Spalte rechts holt sie nicht nach vorn; wer sie verdeckt, schiebt das Fenster weg. Die Details eines Jobs (Klick auf eine Zeile) öffnen wie heute das Processing-Panel in der Spalte rechts; das Fenster bleibt offen und wird dabei nicht bewegt.
- **Schließen:** nur rotes x (`CloseButton`) und der Knopf „Jobs“; Esc schließt das Fenster nicht (Regel Otto, 02.11.2026, ersetzt „rotes x und Esc“ aus der Antwort zu Frage 8). Fokus zurück auf den Knopf „Jobs“.
- **Unter 900 px:** Blatt von unten wie die Seitenleiste (von der Leiste bis zum rechten Rand, höchstens 55 % Höhe, Griff zum Einklappen), nicht verschiebbar, gemerkte Maße gelten dort nicht. Sind Seitenleiste und Manager offen, liegt das zuletzt geöffnete oben.
- **Innen:** feste Spalten Status · Titel · Datum · Aktionen in jeder Zeile; Gruppe als Kopfzeile mit Faltpfeil, Name, Anzahl und Zustand (z. B. „2 running“); Stapel als Zeile in derselben Form, aufgeklappt mit eingerückten Teilen; je Zeile ein Hauptknopf (Download bzw. Retry/Restore) und „⋯“ für den Rest (heute `RowMenu`); Filter „Active / Expired / Deleted / All“ und „＋ New group“ im Kopf. Mit wachsender Breite wird die Titelspalte breiter, die übrigen bleiben fest.
- **Tests (UI-03c):** Speicher leer, kaputt, gesperrt; Ziehen und Größe mit Grenzen; Zurückschieben bei kleinerem Fenster; x schließt, Esc nicht; Blatt unter 900 px; Browserprüfung bei 1280, 1920 und 360 px, hell und dunkel, mit offener Seitenleiste und offenem Processing-Panel.

### 7.10 Nachtrag: Browsertest Otto (02.11.2026, zu #277)

Ersetzt die betroffenen Stellen von §7.2 (Skizze), §7.3 (Felder, Opacity, Actions) und Frage 6 (Opacity gesperrt) sowie die Punkte (3) und (4) der NM4-59-Freigabe vom 30.10.2026 (Originaltexte bleiben stehen).

1. **Zeitleiste:** gleiche Breite mit und ohne gewählte Szene. Ohne gewählte Szene steht am Platz der Knöpfe „Select a scene“ (`SelectionBlock`, `.select-hint`).
2. **„Search results“ im Layer-Manager** bleibt oben, außer der Nutzer schiebt die Zeile nach unten: Ein neuer Layer kommt dann direkt darunter, sonst wie bisher ganz oben (`resultsAtAfterAdding`). Ansicht und Live-Vorschau liegen innerhalb von „Results“ über den Quicklooks der Suche (Ebenenfolge `TIERS`: Quicklooks, Ansicht, Vorschau, Umrisse). Auslegung [A]: „offene Ansichten bzw. Vorschauen liegen darüber“ heißt auf der Karte über den Suchergebnissen; eine eigene Zeile bekommen sie nicht.
3. **„Change image“** schaltet „Search results“ sichtbar und schiebt die Zeile ganz nach oben (`changeImage`).
4. **Seitenleiste zweispaltig:** Spalte für den Namen (72 px), Spalte für das Feld. „Band“ füllt die Feldspalte; Zeile „Scale“ mit vmin und vmax nebeneinander, dahinter das Dropdown „absolute / percentile“ (nicht mehr über dem Feld vmax). vmin und vmax heißen weiter so, als Platzhalter und als Name für Screenreader (Regel NM4-65).
5. **Opacity und Auge** sind auch in der Ansicht der Suche bedienbar: eigene Deckkraft der Ansicht (`viewOpacity`, 1 bei jeder neuen Ansicht), die „Add to layers“ an den neuen Layer weitergibt. Zeichnet ein angehefteter Layer die Ansicht an ihrer Stelle, stellt der Regler dessen Deckkraft [A].
6. **Actions paarweise:** „Change image“ | „Process“; „Add to layers“ | „Add all to layers“; „Download crop“ | „Download full scene“. Kein „Clear“: Das rote x schließt und verwirft die Ansicht (Tooltip „Close and drop this view“).
7. **„Temporary“** wird nach dem verglichen, was gezeichnet wird: Bereich als Zahlen, leere Felder des Standardbilds als Standard des Datensatzes, die Prozentangabe zählt nicht. Geändert und zurückgestellt verschwindet die Marke.
8. **Dropdown „Band“** soll nur die Bänder des Originals (und RGB) enthalten; die Indizes kommen in UI-03d in einen eigenen Bereich „Quick processing“. Bis dahin bleiben sie, wo sie sind: Die Schnellberechnung eines Index ist in der Ansicht nur über dieses Dropdown erreichbar, Herausnehmen ließe eine Lücke. Vorschlag für UI-03d, **von Otto angenommen (02.11.2026)**: Abschnitt „Quick processing“ zwischen „Display“ und „Actions“ mit Dropdown „Index“ (Vorgaben des Datensatzes, „— none —“), dem Hinweis zur Zoomstufe und „Apply“; „Band“ zeigt dann nur RGB und die Bänder des Originals; ein gewählter Index sperrt „Band“ mit Grund.
9. **Antworten Otto zu den offenen Fragen (02.11.2026):** (1) Esc schließt auch Menüs, Auswahllisten und Tooltips nicht (Option 2); sie schließen mit einer Wahl bzw. einem Klick daneben, ein Tooltip, wenn Zeiger oder Fokus gehen. (2) Ein Klick neben „Advanced search“ schließt das Pop-up weiter (Option 1). (3) „Quick processing“ für UI-03d wie unter 8 (Option 1).
10. **Seitenleiste bis ganz oben:** Seitenleiste und Processing-Panel in derselben Spalte reichen ohne Spalt von der Oberkante bis zum Fuß (`top: 0`); die Knöpfe oben („Zoom to selection“, „Basemap“, Thema) stehen links neben der Spalte. Ersetzt „volle Höhe unter der Knopfzeile“ aus Frage 3.
11. **„Select a scene“** steht als ruhige Pille mit Haken-Symbol mittig zwischen Oberkante des Blocks und Zeitleiste.
