# UI-04 — Einheitlichkeit: Stil, Namen, Bedienung

**Stand:** 01.11.2026, beauftragt von Otto (Backlog-Punkt 73 in `docs/plans/nach-m4-backlog.md`). Nimmt das Paket NM4-56 (Zahlenformat NM4-21, weniger Text NM4-22, schmale Fenster aus Punkt 58) in sich auf.
**Stufe B:** Erst kommt die Bestandsaufnahme mit Vorschlägen im Draft-PR, Otto gibt frei, dann setzt dieselbe Session **Teil 1** um. Weitere Teile bekommen je eine neue Session und einen eigenen PR.
**Modell:** Opus für Bestandsaufnahme und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach dem Merge aller Teile von UI-03; als letzte Frontend-Aufgabe vor M5, **allein** (keine andere Frontend-Session gleichzeitig, die Teile gehen quer durch die ganze Oberfläche).
**Startsatz:** „Führe Aufgabe UI-04 aus `docs/plans/vp3/ui-04-einheitlichkeit.md` aus.“

## 1. Wunsch (Otto, 01.11.2026, wörtlich)

> Ich will hauptsächlich die verwendeten styles und namen checken und auf consistency überprüfen, ähnlich sachen sollen den gleichen style haben; gleiche sachen sollen gleich heissen und gleich verwendbar sein (zB keine verschiedenen symbole oder wege zum exiten) usw. Es soll einfach alles einheitlich sein und nicht ständig unterschiedlich aussehen.

## 2. Soll

1. **Gleiches sieht gleich aus:** Ähnliche Bedienelemente nutzen dasselbe Bauteil und dieselben Gestaltungswerte (Tokens aus UI-03): Knöpfe, Schalter, Segment-Umschalter, Dropdowns, Zahlfelder, Chips, Abzeichen („Preview“, „Temporary“), Hinweise, Fehlermeldungen, Listenzeilen, Gruppenköpfe, Leisten, Seitenleisten, Dialoge, Tooltips und (i).
2. **Gleiches heißt gleich:** Ein Begriff je Sache in der ganzen Oberfläche (Knopftexte, Überschriften, Tooltips, aria-Labels, Fehlermeldungen); gleiche Schreibweise (Groß-/Kleinschreibung, Ellipse „…“, Einheiten, Zahlen nach NM4-21).
3. **Gleiches bedient sich gleich:** ein Weg zum Schließen (kleines rotes „x“ über `CloseButton.tsx`, dazu Esc, wo es ein Fenster oder eine Leiste ist), ein Weg zum Übernehmen und Speichern („Apply“, „Apply to all“, „Save“ nach den Regeln aus #257/#272), gleiche Sperrregel (gesperrt mit Grund im Tooltip), gleiche Symbole für gleiche Aktionen (Download, Auge, Ziehgriff, Löschen, Umbenennen, Process ⚙, Menü …).
4. **Bleibt dauerhaft so:** Ein kurzer Leitfaden `docs/ui/leitfaden.md` (Begriffe mit Bedeutung, Bauteile, Symbole, Regeln für Texte, Sperren, Schließen, Speichern) und automatische Prüfungen, die Rückfälle finden (z. B. Test: kein Schließen-Knopf außer `CloseButton`; keine festen Farb- oder Abstandswerte außerhalb der Tokens; Begriffsliste gegen die Oberflächentexte). Künftige Pläne verweisen auf den Leitfaden.
5. **Aus NM4-56:** Zahlenformat (NM4-21), weniger Text mit (i) (NM4-22), schmale Fenster (Punkt 58: Toolbar bei 320 px, verdeckte Statusleiste bei 360 px, überragende Statusmeldung).

## 3. Vorgehen

1. **Bestandsaufnahme** über die ganze Oberfläche (Suche, Advanced search, Ergebnisliste, Auswahl- und Zeitleiste, Ansicht, Seitenleiste, Layer-Manager, Processing-Panel, Processing-Manager, Dialoge, Control-Menü, Kopfzeile, Statusleiste): Tabelle im PR mit Stelle, heute (Bauteil, Text, Symbol, Verhalten), Abweichung, Vorschlag. Im echten Browser erhoben (Hell/Dunkel, 1280 und 360 px), Bilder nicht ins Repo.
2. **Begriffsliste** als Vorschlag: je Begriff die Stellen, an denen heute andere Wörter stehen, und der vorgeschlagene eine Begriff.
3. **Schnitt** in Teile (z. B. Teil 1 Leitfaden, Begriffe und Schließen/Speichern; Teil 2 Bauteile und Tokens; Teil 3 Zahlenformat, Text, schmale Fenster), je mit Umfang.

## 4. Grenzen

- Nur Frontend. Keine neue Abhängigkeit ohne Frage an Otto (z. B. ein Stil-Linter nur mit Freigabe).
- **Keine Funktionen entfernen oder ausblenden** (Otto, 31.10.2026; NM4-30 entfällt); gesperrte Elemente bleiben gesperrt mit Grund.
- Entscheidungen Ottos aus den bisherigen PRs gelten (u. a. „Apply to all“ in der Ansicht, „Save“ am Layer, „Temporary“, „Search results“, „Filter within AOI only“, rotes „x“). Weicht der Vorschlag davon ab, steht er als Frage an Otto im PR.
- Oberflächentexte nur Englisch; wenig Text, Erklärungen hinter (i) bzw. im Tooltip.
- Keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Nachträge heißen nach der Aufgabe („Nachtrag UI-04“). Bilder nicht ins Repo.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Bestandsaufnahme, Begriffsliste und Schnitt im Draft-PR; Otto gibt frei.
- Teil 1 danach in derselben Session: Tests mit Gegenprobe (inkl. der neuen Prüfungen gegen Rückfälle), Browserprüfung (Hell/Dunkel, 1280 und 360 px), Prüfanleitung für Otto; berührte Browser-Skripte nachgezogen.
- Alle vier Pflicht-Checks grün; Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.

## 6. Vorgemerkt aus UI-03e (Otto, 03.11.2026, zu #282)

Nach UI-03b, in diesem Plan zu klären und zu schneiden:

- **Ergebnis-Layer in RGB:** absolute/percentile je Kanal in den Einstellungen eines Job-Ergebnisses (`ResultControls`, `PreviewRange`), wie UI-03e es für die Ansicht und angeheftete Layer umgesetzt hat (`AppliedRender.percentChannels`, `ChannelRange.percent`).
- **Permalink:** Erweiterung um Kanäle und Einheit je Kanal (`view.range` hält heute ein `vmin`/`vmax` und die Colormap; das Schema prüft das Backend, `jobs/permalinks.py`). Bis dahin bleibt der Permalink unverändert.


## 7. Bestandsaufnahme, Begriffe, Symbole und Schnitt (Vorschlag Claude, 03.11.2026)

**Status:** angenommen (Otto, 03.11.2026, Antworten in §7.9). Teil 1 folgt in dieser Session, die Teile 2–6 je in einer neuen.

### 7.0 Vorgaben Otto seit dem Plan (03.11.2026)

1. **RGB je Kanal** (Bereich und absolute/percentile) auch in den Einstellungen eines Job-Ergebnisses und im Permalink der Processing-Vorschau. Für das Permalink-Schema gibt es eine kleine Backend-Ausnahme; alte Permalinks bleiben lesbar. Löst §6 auf.
2. **Esc schließt nirgends etwas.** Ausnahmen: In Bestätigungsdialogen ist Esc = „Cancel“, und Esc beendet „Flip through layers“. Das bestätigt den Log-Eintrag UI-03a vom 02.11.2026 und ersetzt „dazu Esc, wo es ein Fenster oder eine Leiste ist“ in §2.3.
3. **Alle Symbole aus einer Quelle und im selben Strich:** Lucide (`lucide-react`, ISC) ist freigegeben. Importiert werden nur die benutzten Symbole. Download ist überall „download“ (Pfeil nach unten in eine offene Schale) statt „⇩“. Ebenso werden Auge, Mülleimer, Stift, Zahnrad, ⋯, Ziehgriff, Zurück-Pfeil, Plus und das rote x ersetzt, und Textzeichen als Symbole (⇩, ✎, ✕ usw.) fallen weg.
4. **Schrift:** überall die System-Schrift aus `tokens.css`, Monospace nur im Band-Math-Feld. Ein Test findet fremde Schriftangaben.
5. **Zusatz:**
   - (a) Relief gibt es nur noch unter „Overlays“; der Eintrag „Relief“ bei den Basemaps entfällt. Ein alter Permalink mit Basemap „relief“ öffnet mit der Standard-Basemap und Relief als Overlay.
   - (b) „Zoom to selection“ zoomt auf alles Gewählte zusammen: AOI, offene Ansicht und sichtbare Layer. Beispiel: AOI in der Schweiz und Ansicht auf Teneriffa → so weit heraus, dass beide zu sehen sind. Heute gewinnt die AOI.
   - (c) Ein Einstellungsmenü sitzt ganz unten in der Leiste links (Lucide „settings“, Tooltip „Settings“) und enthält Basemap und Erscheinungsbild (Light / Dark / System). Die bisherigen Stellen für Basemap und Light/Dark entfallen.
   - Zu allen drei: Tests mit Gegenprobe, Browserprüfung, Eintrag im Leitfaden.
6. Grundlage des Leitfadens sind alle Regeln und Begriffe aus UI-03 (#277–#283) und NM4-75 (#284, `adr/0028`).
7. **Zusatz (03.11.2026, später am Tag):**
   - (a) Im Processing-Panel entfällt bei „Whole scene“ bzw. „Full scene“ der Hinweis „The result covers the whole scene; the mask marks where they have data.“ ersatzlos.
   - (b) Bei „Scale“ (vmin/vmax) steht keine Einheit, überall wo Scale vorkommt: Seitenleiste, Layer, Ergebnis-Layer, Processing-Vorschau. Die Einheiten bleiben in `BANDS.txt` und in den Metadaten.
   - Tests mit Gegenprobe; Eintrag im Leitfaden.

### 7.1 Wie erhoben

- **Code:** drei Lesedurchgänge über alle Bedienelemente in `frontend/src` (Suche und Kopf; Seitenleiste, Layer und Dialoge; Processing), je Element mit Text, Symbol, Klasse, Schließweg und Sperrregel. Dazu Zählungen: 214 `title=`, 47 `data-tip`, 95 `disabled=`, 77 `aria-disabled`.
- **Browser:** 14 der Skripte unter `frontend/e2e` (advanced-search, selection-block, settings-box, layer-rows, jobs-dock, processing-panel, results-layer, rgb, band-download, resampling-warning, group-heads, tooltips, quick-processing, job-retry) liefen in Hell und Dunkel bei 1280 und 360 px, einige auch bei 320 px. Dazu kamen zwei eigene Messungen: Breite der Toolbar und Lage der Statusmeldung bei 320/360/1280 px sowie die berechnete Schriftfamilie aller Textknoten. Die Bilder liegen nicht im Repo.
  - Grün: 12 Skripte.
  - `settings-box` lief zweimal in die Zeitgrenze, `quick-processing` blieb bei „dark narrow“ an einem Selektor hängen (`waitForSelector`, 8 s). Beide werden in Teil 1 geprüft und nachgezogen, sobald sie berührt sind.
- **Messwerte:**
  - Toolbar des Control-Menüs bei 320 px: `scrollWidth` 246 > `clientWidth` 243. Sie ragt noch 3 px über (Punkt 58: früher etwa 8 px).
  - Bei 320 und 360 px liegt die Statusmeldung (`.toast`, y 16–54) über den Knöpfen oben rechts; diese brechen in zwei Reihen um (bis y 84).
  - Schriften außer `system-ui`: die Attribution der Karte in „Helvetica Neue, Arial“ (MapLibre setzt `font` auf `.maplibregl-map`) und das ✕ der Statusmeldung in „Arial“ (Knopf ohne `font-family`).

### 7.2 Bestandsaufnahme

Legende: **S** = Symbol, **T** = Text/Begriff, **B** = Bauteil/Stil, **V** = Verhalten. Die Spalte „Teil“ verweist auf den Schnitt in §7.7.

| # | Stelle | Heute | Abweichung | Vorschlag | Teil |
|---|---|---|---|---|---|
| 1 | Oben rechts (`App.tsx`) | „⤢ Zoom to selection“, „Basemap“, „☀ Light“/„☾ Dark“ als `zoom-btn` | Textzeichen-Symbole (S); bei 360 px zwei Reihen, unter der Statusmeldung (V) | Basemap und Light/Dark ins Einstellungsmenü (Vorgabe 5c); oben rechts bleibt nur „Zoom to selection“ mit Lucide `scan` | 4 |
| 2 | „Zoom to selection“ | zoomt auf die AOI, sonst auf die angehefteten Layer; gesperrt ohne Grund im Tooltip | Vorgabe 5b; Sperre ohne Grund (V) | Vereinigung der Grenzen von AOI, offener Ansicht und sichtbaren Layern; gesperrt mit „Nothing to zoom to: draw an AOI, open an image or show a layer“ | 4 |
| 3 | Basemap-Menü | „Relief“ als Basemap und als Overlay | doppelt (Vorgabe 5a) | nur Overlay; Permalink `basemap: "relief"` → Standard-Basemap + Overlay Relief | 4 |
| 4 | Leiste links (`AppRail`) | vier eigene SVGs; Tooltips „Search and area“, „Layers“, „Processing jobs“, „Results“ | eigene Zeichnungen (S); „Results“ statt „Search results“, „Processing jobs“ statt „Jobs“ (T) | Lucide `search`, `layers`, `clipboard-list`, `list`; Tooltips „Search and area“, „Layers“, „Jobs“, „Search results“; unten `settings` (Vorgabe 5c) | 2, 4 |
| 5 | Control-Menü: AOI-Werkzeuge | Point/Rectangle/Polygon als eigene SVGs, „Clear“ mit eigenem X; `tool-btn` | eigene Symbole (S); X für „Leeren“ sieht aus wie Schließen (S); bei 320 px 3 px zu breit (V) | `map-pin`, `square`, `pentagon`; „Clear“ mit `trash-2`; Toolbar bei 320 px ohne Überstand | 2, 6 |
| 6 | Control-Menü: „⤒ Upload AOI“, „↺ Last AOI“ | Textzeichen; „Last AOI“ gesperrt ohne Grund | S; V | `upload`, `history`; gesperrt mit „No earlier AOI in this browser“ | 2, 1 |
| 7 | Ortssuche, Szenenname | × in `clear-btn` (muted, 15 px) | dritte Form eines x (S) | Lucide `circle-x` (muted) als einziger Weg, ein Feld zu leeren; kein rotes x | 2 |
| 8 | „Find“, „Search“ | gesperrt ohne Tooltip; der Grund steht als Absatz darunter („Choose a dataset to search.“ usw.) | V; Text sichtbar statt hinter (i) (NM4-22) | Grund im Tooltip des Knopfes, die drei Absätze entfallen | 1, 6 |
| 9 | Datensatz-Knöpfe, Coverage | `dataset-toggle`, `coverage-btn` (gestrichelt), „Clear coverage“, Menü „Hide coverage“ | drei Knopfstile (B); „Clear“ und „Hide“ für dasselbe (T) | ein Umschalter-Stil `.btn` + `aria-pressed`; „Hide coverage“ an beiden Stellen | 3, 1 |
| 10 | Advanced search | Popover mit CloseButton, „Done“ (primär), „Reset filters“ | „Done“ und rotes x schließen beide (V, zulässig) | so lassen; im Leitfaden: ein Formular-Popover hat x und „Done“ | – |
| 11 | Ergebnisliste: Kopf | „Results (0/1)“, Symbole „nach oben“ und Auge als eigene SVGs | „Results“ statt „Search results“ (T); S | „Search results (0/1)“; `arrow-up-to-line`, `eye`/`eye-off` | 1, 2 |
| 12 | Ergebnisliste: Gruppen | ▾/▸ als Textzeichen | S | `chevron-down`/`chevron-right` | 2 |
| 13 | „✕ Clear search results“ | rotes ✕ als Text (`clear-results-x`, #ff5a6e fest) | sieht aus wie Schließen (S); feste Farbe, im hellen Thema nicht `--danger` (B) | `trash-2` + „Clear search results“, Farbe `--danger` | 2, 3 |
| 14 | „Stop“ beim Prüfen | zwei Tooltips: „Stop checking. What is found stays.“ und „…; Load more goes on.“ | T | ein Text: „Stop checking. What is found stays.“ | 1 |
| 15 | Auswahlleiste (`ViewBar`) | „⇩ Download crop“, „⇩ Download full scene(s)“, „⚙ Process“, „Crop & merge to AOI“, „View merged scenes“ | S; „&“ (T); „scene(s) selected“ (T) | `download`, `cog`; „Crop and merge to AOI“; Zahl und Wort nach Anzahl („1 scene selected“, „3 scenes selected“) | 2, 1 |
| 16 | Zeitleiste | Chevron-SVG, „▶“/„❚❚“, Tooltip „Previous step“, Zähler „4/7“ | S; „step“ statt „time step“ (T) | `chevron-left`/`-right`, `play`/`pause`; „Previous time step“ / „Next time step“; „4 / 7“ | 2, 1 |
| 17 | Auswahlleiste: Ziehgriff | CSS-Balken (`drag-grip`) | eigener Griff (S) | Lucide `grip-horizontal` | 2 |
| 18 | Seitenleiste: Kopf | Stift `PencilIcon` 12 px, rotes x (CloseButton, eigenes SVG 10 px), Grip ▾/▴ | S | `pencil`, `x` (rot, im CloseButton), `chevron-down`/`-up` | 2 |
| 19 | Seitenleiste: Display | „auto-scale“ klein; Einheit als `select` „absolute/percentile“; Colormap „⇄“ ohne Text, in der Liste „⇄ Reverse“ | Groß-/Kleinschreibung (T); Textzeichen (S); dieselbe Aktion einmal mit, einmal ohne Text | „Auto-scale“; `arrow-left-right` an beiden Stellen, in der Liste mit Text | 1, 2 |
| 20 | Seitenleiste: Actions | „‹ Change image“, „⚙ Process“, „＋ Add to layers“, „＋ Add all to layers“, „⇩ Download crop“, „⇩ Download full scene“, „＋ Add current view to layers“, Mülleimer | Textzeichen (S); Tooltips „Pin …“ neben „Add to layers“ (T) | `arrow-left`, `cog`, `plus`, `download`, `trash-2`; Tooltips „Add … to the layers“ | 2, 1 |
| 21 | „Temporary“, „Preview“, „Overview“, „Zoom in“ | `pp-badge vc-temporary` und `preview-badge`: gleiches Aussehen, zwei Klassen, eigene Polsterung für „Temporary“ | B | ein Bauteil `Badge` (`.badge`, Pille, `--accent-2`) | 3 |
| 22 | Hinweise „Measured on the first scene“ und Index-Hinweis | `vc-note hint-text`, im hellen Thema `#8a5a00` fest | B | `.hint` und `.hint.warn` mit Token | 3 |
| 23 | Layer-Manager: Zeile | Griff als Punkte-SVG, Auge 22 px (Ansicht: 28 px), Stift 11 px (Kopf: 12), ▲/▼, „⚙“ allein, „⇩“ allein, Mülleimer 12 px (Actions: 14), „＋“ für ein Band, ⚠ | Symbolgrößen und Formen gemischt (S); ▲/▼ und ↑/↓ für dasselbe | `grip-vertical`, `eye`, `pencil`, `arrow-up`/`arrow-down`, `cog`, `download`, `trash-2`, `plus`, `triangle-alert`, alle in einer Größe | 2 |
| 24 | Layer-Manager: gesperrt | Stift, Deckkraft, Band bei gelöschtem Job ohne Grund; ▲/▼ am Rand ohne Grund | V | Grund im Tooltip („Job deleted: restore it first“, „Already at the top“) | 1 |
| 25 | „Flip through layers“ | Tooltip „… Esc to stop“; Esc beendet | Ausnahme laut Vorgabe 2 | bleibt | – |
| 26 | Ergebnis-Layer (`ResultControls`) | RGB: ein Bereich und eine Einheit für alle Kanäle; in Prozent ein Feldpaar | Vorgabe 1 (V) | je Kanal Bereich und Einheit wie in der Ansicht (`ChannelRange.percent`), gespeichert in `jobShelf` | 5 |
| 27 | Processing-Panel: Vorschau | ein Bereich, eine Einheit, kein Kanal; Colormap bei RGB ausgeblendet (Seitenleiste: gesperrt „— none —“); „Auto stretch“ statt „auto-scale“ | Vorgabe 1 (V); ausgeblendet statt gesperrt (V); T | Kanäle und Einheit je Kanal, Permalink mit Kanälen (§7.6); Colormap gesperrt „— none —“; „Auto-scale“ | 5, 1 |
| 28 | Processing-Panel: Kopf und Abschnitte | „⬆ Load recipe…“ (Label statt Knopf), Grip ▾/▴, „Select Bands that are processed“, Feldname „Crs“ | S; Groß-/Kleinschreibung (T) | `upload`; „Select bands to process“; Feldnamen aus der Registry nach Liste („CRS“) | 2, 1 |
| 29 | Processing-Panel: Schrittkarte | ✎, ↑, ↓, rotes ✕ (Remove) | Remove sieht aus wie Schließen (S); ✎ neben `PencilIcon` an anderer Stelle | `pencil`, `arrow-up`, `arrow-down`, `trash-2` (wie am Layer, #280) | 2 |
| 30 | Processing-Panel: „＋ {operator}“, „＋ Add preview to layers“ | Textzeichen | S | `plus` | 2 |
| 31 | Processing-Panel: lange Absätze | z. B. „The scenes are merged into one mosaic first; …“, „Jobs run 2 at a time per source; the rest wait.“, „An estimate, not a promise.“ (zweimal) | NM4-22 | hinter (i) | 6 |
| 32 | Processing-Manager | Filter `pp-seg`, „＋ New group“, ⋯ als Text, ↻/↺, ⇊ „Download all (ZIP)“, ⇩, Stift-SVG, ▼/▸, Hinweis in Gelb | Textzeichen (S); ⇊ und ⇩ für Download (S) | `plus`, `ellipsis`, `rotate-cw` (Retry/Run again), `archive-restore` (Restore), `download` (auch „Download all“), `pencil`, `chevron-down`/`-right` | 2 |
| 33 | Processing-Manager: Datum | „10NOV-20:15“ in der Zeile, „10 Nov, 20:15“ in den Details | zwei Formate (T) | „10 Nov, 20:15“ überall | 6 |
| 34 | Job-Details | „‹ Order“, ✎ als Text, „↻“ ohne Text, „Download (ZIP)“, „＋ Add to layers“, „Cancel“ gesperrt ohne Grund | S; V | `arrow-left` + „Order“, `pencil`, `rotate-cw`; Gründe im Tooltip | 2, 1 |
| 35 | Batch-Zusammenfassung | „1 done · 2 running“ (klein), Status sonst „Finished“ | zwei Wörter (T) | „1 finished · 2 running“ | 1 |
| 36 | Download-Dialog (NM4-75) | rotes x + „Cancel“ + Klick daneben schließt; während eines laufenden Downloads Tooltip „Close. This stops a download that is still running.“ | Klick daneben bricht einen laufenden Download ab (V) | Klick daneben schließt Dialoge nicht (Frage 2) | 1 |
| 37 | „Values are resampled“ | Bestätigungsdialog ohne x: „Cancel“/„Continue“, Esc = Cancel, Klick daneben = Cancel | Ausnahme laut Vorgabe 2 | bleibt | – |
| 38 | Export-Angebot | „Try again“ als Link | T | „Retry“ | 1 |
| 39 | Originaldateien | „Cancel“ stoppt den Lauf, Dateien bleiben | anderes Wort als „Stop“ beim Prüfen (T) | „Stop“ | 1 |
| 40 | Statusleiste | Fehler und Hinweis mit ✕ (Text, aria „Dismiss“, Schrift Arial); bei 320/360 px über den Knöpfen oben rechts; bei 360 px verdeckt der Layer-Manager die Leiste (Punkt 58) | zweites x neben CloseButton (S, B); „Dismiss“ statt „Close“ (T); Schrift (B); Lage (V) | CloseButton; unter 900 px unterhalb der Kopfknöpfe und über dem Dock, nie über den Rand | 1, 6 |
| 41 | Teilen (`ShareLink`) | ✕ „Delete link“ (rot, `delete-btn`), Datum `toLocaleDateString` | S; Datumsformat hängt vom Browser ab | `trash-2`; Datum `2026-12-03` | 2, 6 |
| 42 | Tooltips allgemein | drei Wege: natives `title`, `data-tip` (TipLayer), `Tip` (ⓘ/⚠) | B; gesperrte Knöpfe zeigen `title` nicht in jedem Browser | Frage 3 | 3 |
| 43 | Gesperrte Knöpfe allgemein | Deckkraft 0.3/0.35/0.4/0.45/0.5/0.55; teils `disabled`, teils `aria-disabled` | B | ein Token `--disabled-opacity` (0.4); Regel im Leitfaden: `aria-disabled` + Grund im Tooltip | 3 |
| 44 | Knopffamilien | `ghost-btn`, `lm-btn`, `tool-btn`, `zoom-btn`, `coverage-btn`, `primary-btn`, `lm-btn primary`, `link-btn`, `pp-icon-btn`, `pm-icon`, `vc-step`, `delete-btn`, `clear-results`, `copy-btn`, `play-btn` | B | vier Formen: `.btn` (Standard), `.btn.primary`, `.btn.danger`, `.icon-btn` (nur Symbol, `--control-height` bzw. `-sm`); dazu `.link-btn` im Fließtext | 3 |
| 45 | Hinweise und Fehler | `hint-text` (10 px fest), `pp-help`, `pm-note`, `vc-note`; Fehlerrot `#ff6b6b` fest, `--danger`, `--invalid`; Warngelb `#ffd166` fest auch im hellen Thema | B | `.hint` (`--text-xs`, `--muted`), `.hint.warn` (`--accent-2`), `.error` (`--danger`, `role="alert"`, wenn eine Handlung nötig ist) | 3 |
| 46 | Feste Farben | u. a. `.ghost-btn.danger`, `.lm-btn.danger`, `.toast.error`, `.delete-btn` (`#ff5a6e`/`#ff9aa7`), `.primary-btn` Text, `.dialog-backdrop` | B | alles über Tokens; Test (§7.5 Nr. 4) | 3 |
| 47 | Schrift | 33 Regeln setzen einzeln `font-family: var(--font)`; MapLibre-Attribution in Helvetica; Knopf der Statusleiste in Arial; `.cm-search`, `.lm-band select` ohne Familie | Vorgabe 4 | eine Regel `button, input, select, textarea { font: inherit }`, `.maplibregl-map { font-family: var(--font) }`, Einzelangaben entfallen; Test (§7.5 Nr. 5) | 3 |
| 48 | Fokusring | gemeinsamer Ring nur für `ghost-btn`, `primary-btn`, `close-x`, `link-btn`, Felder; andere mit `outline: none` | B | ein Ring für alles Bedienbare (Token `--focus`) | 3 |
| 49 | Zahlen | `toFixed` verstreut; „50%“ neben „42 %“; „max. 1 MB“ | NM4-21 | eine Formatierfunktion laut `querschnitt/nm4-21-zahlenformat.md`; Prozent ohne Leerzeichen („50%“, englisch) | 6 |
| 50 | Veraltete Kommentare | `Inspector.tsx` nennt „✕ Clear“, `TipLayer.tsx` sagt, Esc schließe | – | in Teil 1 berichtigen | 1 |
| 51 | Tote Regeln | `.vc-polmodes`, Klassen ohne Regel (`dialog-as`, `resampling-*`, `results-head-right`) | B | in Teil 3 entfernen bzw. zuordnen | 3 |

| 52 | Processing-Panel: „Area: Whole scene“ | Absatz „The result covers the whole {scene(s)}; the mask marks where they have data.“, bei einem Ergebnis „The result covers the area it has.“ (`ProcessingPanel.tsx`) | Vorgabe 7a | der Absatz entfällt ersatzlos; Auslegung: auch die Fassung für ein Ergebnis, weil sie im selben Fall „Whole scene“ steht | 1 |
| 53 | „Scale“ | Processing-Vorschau: Einheit des Bandes hinter vmax (`pp-unit`, aria „Unit of the range“); Seitenleiste und Ergebnis-Layer reichen eine Einheit an `RenderFields`/`ScaleHistograms` durch, wo eine bekannt ist | Vorgabe 7b | keine Einheit an „Scale“, auch nicht im Histogramm; „absolute / percentile“ bleibt (keine Maßeinheit, sondern die Art des Bereichs); die Einheit an den Band-Chips („· dB“) bleibt, sie gehört nicht zu Scale | 1 |

Esc-Wege heute (Vorgabe 2): `ResamplingDialog` (Cancel), `LayerManager`/`AppRail` (Flip beenden), `InlineRename` (Umbenennen abbrechen, Otto zu #280 Frage 4), `useRowDrag` (Ziehen abbrechen, nichts wird abgelegt). Sonst schließt nichts mit Esc. Die zwei letzten schließen nichts und bleiben; der Leitfaden nennt sie als Abbruch, nicht als Schließen.

### 7.3 Symbole (Lucide)

**Regel:**
- Alle Symbole kommen aus einer Datei `frontend/src/components/icons.ts`, die nur die benutzten Lucide-Symbole einzeln importiert und unter eigenem Namen weitergibt (z. B. `DownloadIcon`).
- Strich überall 1.5 px mit `absoluteStrokeWidth`, damit er bei jeder Größe gleich dick ist.
- Zwei Größen: 16 px (Standard) und 14 px (in Listenzeilen).
- Farbe `currentColor`; das rote x bekommt `--danger` über `CloseButton`.
- Lizenz: ISC; die Symbole aus Feather stehen unter MIT. Beide Hinweise kommen in `frontend/THIRD_PARTY_NOTICES.md`.

| Bedeutung | Heute | Lucide | Stellen |
|---|---|---|---|
| Download | ⇩, ⇊ | `download` | ViewBar, Actions, LayerDownload, JobRow, DownloadAll, Layer-Zeile |
| Zeigen/Verbergen | `Eye.tsx` | `eye` / `eye-off` | Ansicht, Layer, Suchergebnisse |
| Entfernen/Löschen | `BinIcon`, ✕ (Schritt, Link, Suchergebnisse) | `trash-2` | Layer, Schritt, Link, „Clear search results“, AOI „Clear“ |
| Umbenennen | `PencilIcon`, ✎ | `pencil` | Seitenleiste, Layer, Job, Batch, Schritt |
| Process | ⚙ | `cog` (Frage 1) | ViewBar, Actions, Layer-Zeile |
| Einstellungen | – | `settings` | Leiste unten (Vorgabe 5c) |
| Mehr | ⋯ | `ellipsis` | Jobs, Gruppen |
| Ziehgriff | Punkte-SVG, CSS-Balken | `grip-vertical` (Zeilen), `grip-horizontal` (Auswahlleiste) | Layer-Manager, Auswahlleiste |
| Zurück | ‹ (Text), Chevron | `arrow-left` | „Change image“, „Order“, Colormap-Liste |
| Bild davor/danach | Chevron | `chevron-left` / `chevron-right` | Seitenleiste, Zeitleiste |
| Auf-/Zuklappen | ▾ ▴ ▸ ▼ | `chevron-down` / `chevron-up` / `chevron-right` | Blätter, Gruppen, Batch, Datensatz-Liste |
| Nach oben/unten schieben | ▲ ▼ ↑ ↓ | `arrow-up` / `arrow-down` | Layer, Schritte |
| Hinzufügen | ＋ | `plus` | Add to layers, Operator, Band, New group |
| Schließen | `CloseButton`-SVG | `x` (rot) | nur `CloseButton` |
| Feld leeren | × | `circle-x` (muted) | `ClearableInput` |
| Erneut | ↻ | `rotate-cw` | Retry, Run again |
| Wiederherstellen | ↺ | `archive-restore` | Job „Restore“ |
| Letzte AOI | ↺ | `history` | Control-Menü |
| Hochladen | ⤒, ⬆ | `upload` | Upload AOI, Load recipe |
| Umkehren | ⇄ | `arrow-left-right` | Colormap |
| Hinweis (i) / Warnung | ⓘ, ⚠ | `info` / `triangle-alert` | `Tip` |
| Erledigt | ✓, Haken-SVG | `check` | „Preview measured“, Kopieren |
| Kopieren | eigenes SVG | `copy` | Szenenname, Link |
| Abspielen | ▶ ❚❚ | `play` / `pause` | Zeitleiste |
| Zoom to selection | ⤢ | `scan` | oben rechts |
| Nach oben legen | eigenes SVG | `arrow-up-to-line` | Suchergebnisse |
| Durchblättern | eigenes SVG | `arrow-up-down` | Flip through layers |
| Werkzeuge AOI | eigene SVGs | `map-pin`, `square`, `pentagon` | Toolbar |
| Leiste | eigene SVGs | `search`, `layers`, `clipboard-list`, `list` | AppRail |
| Coverage | eigenes SVG | `layout-grid` | Control-Menü |
| Erscheinungsbild | ☀ ☾ | `sun`, `moon`, `monitor` | Einstellungsmenü |

Kein Symbol mehr als Textzeichen. Erlaubt bleiben typografische Zeichen im Text: „…“, „—“ in „— none —“, „·“ als Trenner, „–“ in Bereichen, „→“ zwischen zwei Datumsfeldern, „×“ in „10 m × 10 m“, „µm“.

### 7.4 Begriffsliste

| Begriff | Bedeutung | Heute auch | Vorschlag |
|---|---|---|---|
| AOI | das gezeichnete oder geladene Gebiet | „area of interest“, „Area“, „your area“, „Area of interest“ (Überschrift) | sichtbar „AOI“; die Überschrift im Control-Menü „Area of interest (AOI)“; die Wahl im Processing-Panel „Area: Whole scene / AOI only“ bleibt |
| scene | ein Eintrag des Katalogs (Item) | „image“ in „Select a scene“ bleibt | bleibt |
| image | was ein Zeitschritt der Ansicht oder ein Layer zeigt | „picture“ („This picture has one band“, „This picture is not a layer“) | „image“; „picture“ entfällt |
| view | die geöffnete, noch nicht angeheftete Darstellung in der Seitenleiste | – | bleibt („Close and drop this view“); „Add current view to layers“ bleibt (Otto, #280) |
| time step | ein Datum der Zeitleiste | „step“ („Previous step“, „First step“), „mosaic groups“ (aria) | „time step“; „step“ nur im Processing |
| layer | ein Eintrag im Layer-Manager | „pinned layer images“, „Pin … into the layer manager“ | „layer“; Tooltips „Add … to the layers“; „Pin“ entfällt |
| Search results | die Ergebnisse der Suche (Otto) | „Results“ (Leiste, Kopf der Liste) | „Search results“ überall |
| Jobs | der Processing-Manager | „Processing jobs“ (Leiste, aria) | „Jobs“ |
| job / batch / order | Auftrag am Server / mehrere Jobs eines Auftrags / was im Processing-Panel eingestellt ist | – | bleibt; „recipe“ ist nur die Datei |
| Close | schließt Fenster, Leiste, Dialog, Meldung; nur `CloseButton` | „Dismiss“ (Statusleiste), Textknopf „Close“ im Dialog | „Close“; die Statusleiste nutzt `CloseButton` |
| Cancel | verwirft eine Rückfrage oder bricht einen Job ab | „Cancel“ für einen laufenden Download | Rückfrage und Job; Esc = Cancel nur in der Rückfrage |
| Stop | hält einen laufenden Vorgang an; was fertig ist, bleibt | „Cancel“ (Originaldateien) | „Stop“ |
| Remove | nimmt etwas aus einer Liste der Oberfläche (Layer, Schritt, Gruppe) | ✕ | „Remove …“ mit `trash-2` |
| Delete | löscht dauerhaft auf der Plattform (Job, Link) | – | „Delete …“ mit `trash-2` |
| Clear | leert ein Feld, die AOI, die Coverage oder die Suchergebnisse | „Hide coverage“ / „Clear coverage“ | „Clear …“; bei der Coverage einheitlich „Hide coverage“ (es ist ein Auge-Fall) |
| Hide / Show | Auge | „Hide image“ (Ansicht) neben „Hide layer“ | bleibt, je mit dem Ding |
| Apply / Apply to all / Save | zeichnen ohne Speichern / alle Bilder der Ansicht / am Layer speichern (#257, #272, Otto) | – | bleibt |
| Retry / Run again | dieselbe Anfrage noch einmal / Job neu starten | „Try again“, „Retry failed parts“ | „Retry“, „Run again“, „Retry failed parts“ |
| Auto-scale | 2.–98. Perzentil in die Felder | „auto-scale“, „Auto stretch“ | „Auto-scale“ |
| Enhance contrast | Quick processing (Otto) | – | bleibt |
| vmin / vmax, absolute / percentile | Bereich (NM4-65) | – | bleibt |
| — none — / — choose — | kein Wert / Pflichtwahl | „–“ (Download-Dialog, Auflösung) | „— choose —“ |
| Choose | auswählen im Text | „Pick“ | „Choose“ |
| Finished | Status eines Jobs | „done“ in der Batch-Zusammenfassung | „finished“ im Fließtext, „Finished“ als Status |
| Settings | das neue Menü (Vorgabe 5c) und der Kopf der Seitenleiste (aria) | – | Menü „Settings“; die Seitenleiste nennt sich nach ihrem Inhalt (aria „Image settings“ / „Layer settings“) |

**Schreibweise:**
- Knopftexte, Überschriften und Tooltips im Satzanfang-Stil („Add to layers“, nicht „Add To Layers“), auch „Auto-scale“.
- Überschriften von Abschnitten in Großbuchstaben nur per CSS.
- Ellipse immer „…“, nur bei Knöpfen, die noch etwas fragen („Load recipe…“, „Move to group…“), und in Ladezuständen.
- Tooltips ohne Schlusspunkt, wenn sie ein Satzteil sind; mit Punkt, wenn sie aus Sätzen bestehen.
- Anführungszeichen typografisch („ “ als “ ”).
- Trenner „·“; Bereich „–“; kein „&“.
- Einzahl und Mehrzahl nach Anzahl, kein „scene(s)“.

### 7.5 Prüfungen gegen Rückfälle

1. **Schließen:** Kein Knopf mit `aria-label`/`title` „Close“ und keine Klasse `close-x` außerhalb von `CloseButton.tsx`; kein ✕/×/✖ als Knopfinhalt (statisch über `components/**/*.tsx`, Gegenprobe mit einer Beispielzeile).
2. **Esc:** `'Escape'` kommt nur in den Dateien der erlaubten Ausnahmen vor (`ResamplingDialog`, `LayerManager`, `AppRail`, `InlineRename`, `useRowDrag`). Dazu ein jsdom-Test je offenem Panel bzw. Dialog: Esc lässt es offen.
3. **Symbole:** Keine Symbol-Textzeichen (Liste aus §7.3) als JSX-Text oder in Knopftexten. `lucide-react` wird nur in `icons.ts` importiert (eine `no-restricted-imports`-Regel in oxlint, sonst ein Test).
4. **Farben und Maße:** Der Token-Test (`tokens.test.ts`) gilt für alle Klassen in `index.css`, nicht nur für die aufgezählten Bereiche: keine `#hex`/`rgb()`/`rgba()` außerhalb von `tokens.css`. Ausnahmen stehen mit Grund in einer kurzen Liste (Daten-Legenden, Kanalfarben der Histogramme laufen schon über Tokens).
5. **Schrift (Vorgabe 4):** statisch keine `font-family`/`font:`-Angabe außer `var(--font)`, `inherit` und `var(--font-mono)` an genau einer Regel (Band-Math); kein `fontFamily` in TSX. Dazu ein Browser-Skript: Jeder sichtbare Textknoten hat die berechnete Familie von `--font`, die Band-Math-Fläche `--font-mono`; Gegenprobe mit einem eingeschleusten Knoten in Arial.
6. **Keine Einheit an „Scale“ (Vorgabe 7b):** jsdom-Test je Stelle (Seitenleiste mit Band mit Einheit, Layer, Ergebnis-Layer, Processing-Vorschau): In der Zeile „Scale“ und im Histogramm steht die Einheit des Bandes nicht; Gegenprobe mit dem alten `pp-unit`.
7. **Begriffe:** Eine Liste verbotener Wörter je Begriff (z. B. „Dismiss“, „Pin “, „picture“, „Try again“, „Auto stretch“, „scene(s)“, „ & “, „...“) prüft alle Zeichenketten in `components/**/*.tsx` und den Textmodulen; Gegenprobe je Wort.
8. **Sperren:** Jeder Knopf mit `disabled`/`aria-disabled` hat einen Tooltip mit Grund. Statisch nicht sicher prüfbar, darum ein jsdom-Durchgang über die wichtigsten Panels: Jeder gesperrte Knopf hat `title` oder `data-tip`, und der Text ist nicht der Aktionstext.

### 7.6 RGB je Kanal und Permalink (Vorgabe 1)

- **Ergebnis-Layer** (`ResultControls`): `RenderFields` bekommt wie in der Ansicht `onUnit`/`onPercent` je Kanal. `resolve` misst je Kanal in Prozent. `PreviewRange.channels[i].percent` wird in `jobShelf.rangeJson` gespeichert (heute ohne `channels`); alte Einträge ohne `channels` lesen sich wie heute.
- **Processing-Vorschau:** Bei RGB zeigt die Vorschau drei Kanalzeilen wie die Seitenleiste.
- **Permalink:** `view.range` bekommt optional `channels: [{vmin, vmax, percent?: {low, high}}] × 3` und am Bereich `percent?`.
  - Backend: `PermalinkRange` in `api/processing_route.py` mit `channels: list[PermalinkChannel] | None` (genau drei, strikt, `extra="forbid"`), dazu `percent` optional.
  - Ein alter Body ohne die Felder bleibt gültig und öffnet wie heute.
  - Tests: alter Body, neuer Body, zwei Kanäle (422), Prozent außerhalb 0–100 (422), Kanäle bei einem Band ignoriert bzw. 422 (Vorschlag: 422).
  - Etwa 40 Zeilen Backend mit Tests; ein Nachtrag in `adr/0015` §13 („Nachtrag UI-04“).
- **Relief im Permalink (Vorgabe 5a):** Das Backend nimmt `basemap: "relief"` weiter an (alte Links). Das Frontend schreibt es nicht mehr und liest es als Standard-Basemap + Overlay Relief. Keine Schemaänderung.

### 7.7 Schnitt

| Teil | Inhalt | Umfang (Schätzung) | Session |
|---|---|---|---|
| **1** | Leitfaden `docs/ui/leitfaden.md` (Begriffe, Bauteile, Symbole, Regeln für Texte, Sperren, Schließen, Speichern, Esc, Einstellungsmenü, Zoom, Relief, keine Einheit an „Scale“); Begriffe und Texte nach §7.4 (Zeilen 6, 8 Grund im Tooltip, 11, 14–16, 19–20, 24, 27–28, 34–36, 38–40, 50, 52, 53); Schließen über `CloseButton` auch in der Statusleiste; Prüfungen 1, 2, 6, 7 und 8 | 380–420 Zeilen (ohne Leitfaden etwa 330) | diese |
| **2** | Lucide: `lucide-react` als Abhängigkeit, `icons.ts`, alle Symbole nach §7.3, `Eye`/`Icons`/`Chevron` entfallen, `CloseButton` mit `x`; Hinweisdatei; Prüfung 3; Browser-Skripte mit Symbol-Selektoren nachziehen | 300–400 | neu |
| **3** | Bauteile und Tokens: Knopffamilien → vier Formen, `Badge`, Hinweise/Fehler, Sperr-Deckkraft, Fokusring, feste Farben → Tokens, Schrift (Vorgabe 4) mit Prüfungen 4 und 5, tote Regeln; Tooltip-Weg nach Frage 3 | 400+, darum in 3a (Knöpfe, Sperren, Fokus) und 3b (Hinweise, Abzeichen, Farben, Schrift) | je neu |
| **4** | Einstellungsmenü in der Leiste (Basemap, Overlays, Projektion, Light/Dark/System), Relief nur als Overlay mit altem Permalink, „Zoom to selection“ über alles Gewählte (Vorgaben 5a–5c); Theme „System“ folgt `prefers-color-scheme` und wird als `earthx.theme = "system"` gemerkt | 250–300 | neu |
| **5** | RGB je Kanal im Ergebnis-Layer und in der Processing-Vorschau, Permalink mit Kanälen (Backend-Ausnahme, §7.6) | 300–350 | neu |
| **6** | NM4-56: Zahlenformat (NM4-21), weniger Text mit (i) (NM4-22, Zeilen 8, 31), Datums- und Prozentformat (Zeilen 33, 41, 49), schmale Fenster (Punkt 58: Toolbar 320 px, Statusleiste bei 360 px, Statusmeldung über den Kopfknöpfen) | 350–400 | neu |

**Stand 04.11.2026:** Teil 1 ist umgesetzt und gemergt (#285). Teil 2 ist umgesetzt (§8.2); die Liste `UNTIL_PART_2` in `frontend/src/uiRules.test.ts` ist entfallen. Teil 3a ist umgesetzt (§8.3), Teil 3b ist umgesetzt (§8.4, Hinweise, Abzeichen, feste Farben, Schrift, `.btn.seg`, dazu drei Zusätze Ottos vom 04.11.2026: Tooltip-Stufen, Fokusring, Autofill). Teil 5 ist umgesetzt (§8.5).

Reihenfolge 1 → 2 → 3a → 3b → 4 → 5 → 6, nacheinander, weil alle Teile quer durch dieselben Dateien gehen. Teil 4 kann vor Teil 3 kommen, wenn Otto es zuerst sehen will. Die Teile 2 bis 6 bekommen je einen eigenen Plan-Abschnitt in dieser Datei („§8 Teil n“), damit eine neue Session ohne dieses Gespräch auskommt.

### 7.8 Fragen an Otto

1. **Process neben Settings:** Lucide `settings` und ein Zahnrad für „Process“ sehen fast gleich aus.
   (1) Process `cog`, Settings `settings` — **Empfehlung**: beide bleiben Zahnräder wie gewünscht, aber unterscheidbar (Speichen gegen Kreis).
   (2) Process `workflow`.
   (3) Process `square-function`.
2. **Klick neben einen Dialog** (Download-Dialog, NM4-75): Heute schließt er ihn und stoppt dabei einen laufenden Download.
   (1) Klick daneben schließt Dialoge nicht mehr; es schließen nur das rote x, „Cancel“ bzw. „Close“. Ausnahme: die Rückfrage „Values are resampled“, wo Klick daneben = Cancel bleibt — **Empfehlung**.
   (2) So lassen.
   „Advanced search“ bleibt, wie entschieden (Klick daneben schließt).
3. **Ein Weg für Tooltips:**
   (1) Alle Tooltips über `TipLayer` (`data-tip`): gleich gestaltet, auch per Tastaturfokus und an gesperrten Knöpfen sichtbar. `title` entfällt, `aria-label` bzw. `aria-describedby` tragen den Text für Screenreader. Das betrifft gut 200 Stellen und läuft in Teil 3a — **Empfehlung**.
   (2) `title` bleibt für Knöpfe, `data-tip` nur, wo heute.
4. **Einstellungsmenü (5c) mit Overlays und Projektion:** Das Basemap-Menü enthält heute Basemap, Overlays und Projektion.
   (1) Alles davon ins Einstellungsmenü, Abschnitte „Basemap“, „Overlays“, „Projection“, „Appearance“ — **Empfehlung**.
   (2) Nur Basemap und Appearance; Overlays und Projektion an anderer Stelle (welche?).
5. **„Zoom to selection“ (5b):** Ziel ist die Vereinigung aus AOI, offener Ansicht und sichtbaren Layern.
   (1) So, ausgeblendete Layer zählen nicht — **Empfehlung**.
   (2) Nur der Layer bzw. die Ansicht, deren Einstellungen offen sind, plus AOI.
   Über die Datumsgrenze (z. B. Fidschi) wird der kürzere Weg genommen — **Empfehlung** — oder einfach die größte Ausdehnung.
6. **Leeren eines Feldes:** `circle-x` in Grau als einziges zweites „x“ der Oberfläche.
   (1) Ja — **Empfehlung**: es ist kein Schließen und sieht anders aus als das rote x.
   (2) Stattdessen `eraser`.
7. **Schnitt:**
   (1) wie §7.7, Teil 1 in dieser Session — **Empfehlung**.
   (2) Teil 4 (Einstellungsmenü, Relief, Zoom) zuerst, weil sichtbar und klein.

### 7.9 Antworten Otto (03.11.2026)

1. **„Process“ behält das Zahnrad** (Lucide `cog`). **Settings bekommt „Settings 6 Line“ von MingCute**, nicht Lucide `settings`. Es ist die **einzige Ausnahme** von „alle Symbole aus Lucide“ und steht so im Leitfaden. Ersetzt Frage 1 und die Zeile „Einstellungen“ in §7.3. Umsetzung in Teil 4 (Einstellungsmenü):
   - **Übernahme:** nur das eine SVG, nicht die Bibliothek.
   - **Quelle geprüft (03.11.2026):** npm-Paket `mingcute_icon` 2.9.72, Datei `svg/system/settings_6_line.svg`, Repository `github.com/Richard9394/MingCute`, Lizenz Apache-2.0 (LICENSE im Paket und im Repository).
   - **Angleichung:** Das Original ist eine gefüllte Fläche mit 2 px breiten Linien auf 24 px. Damit Strich und Größe zu Lucide passen (1.5 px absolut, 16/14 px), wird es mit derselben Geometrie als Strich nachgezeichnet. Das ist eine Änderung im Sinn von Apache-2.0 §4(b) und steht als solche im Kopf der Datei.
   - **Herkunft im Repo:** Lizenztext und Herkunft kommen nach `frontend/THIRD_PARTY_NOTICES.md` (§4(a)).
2. Klick neben einen Dialog schließt nicht; Ausnahme ist die Rückfrage „Values are resampled“ (Klick daneben = Cancel). Option 1.
3. Ein Tooltip-Weg: `TipLayer` (`data-tip`) für alles, in Teil 3a. Option 1.
4. Overlays und Projektion kommen ins Einstellungsmenü, mit den Abschnitten „Basemap“, „Overlays“, „Projection“, „Appearance“. Option 1.
5. „Zoom to selection“ zoomt über AOI, offene Ansicht und sichtbare Layer; ausgeblendete Layer zählen nicht. Über die Datumsgrenze gilt der kürzere Weg. Option 1.
6. Ein Feld wird mit grauem `circle-x` geleert. Option 1.
7. Schnitt wie §7.7, Teil 1 in dieser Session. Option 1.
8. Die Auslegung zu Zusatz 7a ist angenommen: Auch „The result covers the area it has.“ fällt weg.

## 8. Teile 2 bis 6, je ein Abschnitt

### 8.2 Teil 2 — Lucide (umgesetzt, 04.11.2026)

**Umfang:** `lucide-react` (ISC, von Otto freigegeben, §7.0 Nr. 3) als einzige Symbolquelle; alle Symbole nach §7.3 mit Ausnahme von Settings (MingCute, Teil 4) und den Symbolen des Einstellungsmenüs.

**Umgesetzt:**
- `frontend/src/components/icons.ts`: einzige Datei, die `lucide-react` importiert; jedes Symbol unter eigenem Namen (`DownloadIcon`), Strich 1.5 px an jeder Größe (`absoluteStrokeWidth`), Größen 16 px (Standard) und 14 px (Listenzeilen), `lead` für den Abstand vor einem Text (`.icon-lead`).
- Weg: `Eye`, `Chevron`, `Icons` (Bin, Stift) und alle `<svg>` mit eigenen Zeichnungen (Leiste, AOI-Werkzeuge, Coverage, Kopieren, „nach oben“, Ziehgriff, Flip, Haken). Alle Textzeichen als Symbole (⇩ ✎ ✕ × ⚙ ＋ ⋯ ▾ ▴ ▸ ▲ ▼ ↑ ↓ ↻ ↺ ⤒ ⬆ ⇄ ⓘ ⚠ ✓ ▶ ❚ ⤢ ☀ ☾ ‹) in Code und CSS.
- `CloseButton` zeichnet das Lucide-`x` (14 px, rot über `--danger`).
- `frontend/THIRD_PARTY_NOTICES.md`: Lizenztexte von Lucide (ISC) und Feather (MIT).
- Prüfungen (§7.5 Nr. 3): `uiRules.test.ts` (kein Symbol-Textzeichen in Code und CSS, `lucide-react` nur in `icons.ts`, kein eigenes `<svg>` außer dem Histogramm, kein x-Zeichen als Knopfinhalt) und `icons.test.tsx` (Strich, Größen, jedes Symbol benutzt), je mit Gegenprobe.

**Auslegungen (Vorschlag, gelten bis Otto widerspricht):**
1. **Leiste links** zeigt die vier Symbole mit 16 px statt der 22 px der alten Zeichnungen: es gibt nur zwei Größen (§7.3). Sieht es zu klein aus, ist das eine Entscheidung für Teil 3 (dritte Größe für die Leiste).
2. **Haken in Menüs** (Basemap, „Move to group…“): ein Symbol in einem Platz fester Breite (`MenuTick`) statt `content: '✓'` im CSS.
3. **Knöpfe nur mit Symbol** in der Layer-Zeile (Process, Download) bekommen einen Namen für Screenreader (`aria-label`: „Process layer“, „Download“); ihr Tooltip bleibt der Grund bzw. die Beschreibung. Vorher hatten sie nur den Tooltip.
4. **`Tip`** zeigt `info`, mit `tone="warn"` `triangle-alert`; die Eigenschaft `symbol` entfällt.
5. **Tastennamen** stehen in Worten, nicht als Pfeilzeichen: „Flip through layers (Up and Down or the mouse wheel …)“.
6. **Theme-Knopf** oben rechts zeigt `sun`/`moon` bis Teil 4 (Einstellungsmenü) ihn ablöst.
7. **„Clear“ der AOI** und **„Clear search results“** zeigen `trash-2`, **Teilen** „Delete link“ ebenfalls; das graue `circle-x` leert nur ein Feld (`ClearIcon`).
8. **Download überall `download`**, auch „Download all (ZIP)“ (vorher ⇊) und die Zeile eines Jobs.
9. **Nicht berührt:** `.vc-eye` (28 px), `.lm-eye` (22 px) und andere feste Knopfgrößen; sie gehören zu Teil 3a (Knopfformen).
10. **Antworten Otto (04.11.2026):** Die Leiste links bekommt in Teil 3 eine dritte Größe 20 px als Token (hier 16 px, unverändert). Der Knopf „Clear“ der AOI im Control-Menü heißt „Clear AOI“ (Beschriftung, Tooltip, `aria-label`); gesperrt ohne AOI mit dem Grund „No AOI to clear“.

### 8.3 Teil 3a — Knöpfe, Sperren, Fokus, Tooltip-Weg (umgesetzt, 04.11.2026)

**Umfang:** Teil 3 war in §7.7 als „400+“ in 3a und 3b geschnitten. Diese Session setzt **3a** um, dazu Ottos Vorgabe vom 04.11.2026 (Symbole der Leiste links 20 px als eigenes Token). Teil 3b (Hinweise, Abzeichen, feste Farben, Schrift, tote Regeln; Prüfungen 4 und 5) folgt in einer neuen Session. Der PR ist mit rund 1100 geänderten Zeilen größer als der Richtwert; etwa die Hälfte ist mechanisch (`title` → `data-tip` an gut 180 Stellen, die Nachführung der Tests).

**Umgesetzt:**
- **Token:** `--icon-size` (16 px), `--icon-size-sm` (14 px), `--icon-size-rail` (20 px, Otto), `--disabled-opacity` (0.4), `--on-accent` (Text auf gefülltem Akzent, beide Themen). `components/iconSizes.ts` hält dieselben Zahlen für `icons.ts`; `icons.test.tsx` prüft, dass Datei und Token gleich sind. Die vier Symbole der Leiste sind 20 px groß, der Strich bleibt 1.5 px (`AppRail.test.tsx`).
- **Vier Knopfformen** (`index.css`, ganz vorn, damit Klassen eines Ortes sie überschreiben dürfen): `.btn`, `.btn.primary`, `.btn.danger`, `.icon-btn` (mit `.sm` = 22 px für Listenzeilen und `.quiet` = leise, `.off` = aus). Dazu `.link-btn` im Fließtext und `.close-x` (nur `CloseButton`). Ein Schalter steht mit `aria-pressed` (`.btn`: getönt mit Akzent; `.icon-btn`: Akzentfarbe) oder `.on` (die offene Seite der Leiste).
- **Weg:** `ghost-btn`, `primary-btn`, `lm-btn`, `lm-eye`, `vc-eye`, `vc-step`, `zoom-btn`, `coverage-btn`, `play-btn`, `pp-icon-btn`, `delete-btn`, `copy-btn`, `vc-pencil`, `vc-back`, `lm-pencil`. Übrig bleiben Klassen eines Ortes mit Platz und Breite, nie mit Farbe, Rand oder Schrift (`tool-btn`, `pm-icon`, `dataset-toggle`, `aoi-stop`, `vc-apply`, `lm-flip`, …).
- **Sperren:** `:disabled` und `[aria-disabled='true']` werden in **einer** Regel auf `--disabled-opacity` gedimmt; die Deckkraftwerte 0.3 bis 0.55 an Knöpfen, Feldern und Zeilen entfallen.
- **Fokus:** ein Ring (`2px solid var(--focus)`) für alles Bedienbare (`a[href]`, `button`, Felder, `summary`, `[role=button|menuitem|menuitemradio]`, `[tabindex]`); die Einzelregeln und alle `outline: none` an Knöpfen und Feldern entfallen. Ausnahmen mit Grund: der Schieber (Ring am Griff), der Rahmen eines Popovers (kein bedientes Element), die gestrichelte Ablagelinie.
- **Ein Tooltip-Weg** (Frage 3, Otto): `data-tip` für alles, `TipLayer` zeichnet ihn. `title` steht an keinem Element mehr, **außer** an `<option>` (eine native Liste kann sonst nichts zeigen) und an den eigenen Steuerelementen von MapLibre. `TipLayer` setzt für die Dauer des Tooltips `aria-describedby` am Steuerelement (bei einem `label` mit Tooltip am Feld darin; nicht, wenn der Name schon derselbe Text ist), der Tooltip hat `role="tooltip"`.
- **Gesperrte Knöpfe:** Ein `disabled`-Knopf bekommt nicht in jedem Browser Mausereignisse. Er nimmt darum keine Zeigerereignisse an (`pointer-events: none`), und `TipLayer` findet ihn über die Lage des Zeigers (höchstens einmal je Bild). Ausnahme: ein gesperrter Knopf direkt in `.overlay` (oben rechts) nimmt Zeigerereignisse an, sonst ginge sein Klick an die Karte darunter.
- **Prüfungen** (`uiRules.test.ts`, je mit Gegenprobe): kein `title` an einem Element außer `<option>`; keine der alten Knopfklassen in Code und CSS; keine feste Deckkraft in einer Regel eines gesperrten Elements; kein eigener Ring außer den Ausnahmen; der Ring nutzt den Token. `TipLayer.test.tsx` (Beschreibung, gesperrter Knopf), `AppRail.test.tsx` (20 px), `tokens.test.ts` (neue Token; `.btn` und `.icon-btn` ohne feste Maße). Die Tests lesen Tooltips über `fixtures/tips.ts` (`tipOf`).
- **Browser** (Hell/Dunkel, 1280 und 360 px): `tooltips.cjs` prüft zusätzlich einen gesperrten Knopf („Already at the top“ erscheint, geht mit dem Zeiger) und dass kein `title` außer an `<option>` und MapLibre steht. Alle Skripte außer `settings-box` laufen grün (Stand siehe Log).

**Auslegungen (Vorschlag, gelten bis Otto widerspricht):**
1. **Gesperrt = `disabled` bleibt**, wo es steht (253 Prüfungen in den Tests hängen daran). Der Tooltip erscheint über die Zeigerlage; **per Tastatur ist ein `disabled`-Knopf nicht erreichbar**, sein Grund also nur mit der Maus zu lesen. Neue Sperren mit Grund nehmen `aria-disabled="true"` (bleibt in der Tab-Reihenfolge, Tooltip auch per Fokus); ein Klick darauf muss der Handler abfangen. Siehe Frage 1.
2. **Knöpfe nur mit Symbol sind quadratisch und leise:** die runden Pfeile der Zeitleiste und des Datumsschritts und der Abspielknopf sind jetzt `.icon-btn`; Augen, Pfeile und Stift in Listenzeilen sind `.icon-btn.sm`. Das Auge ist in Textfarbe (siehe Zusatz Otto unten: ein Bauteil `EyeButton`), ein anderer gesetzter Schalter (`aria-pressed`) in Akzentfarbe.
3. **Alle Knopftexte 12 px ohne Sperrung der Buchstaben:** `zoom-btn` (11 px, 1 px Abstand), `primary-btn` (0.5 px) und `tool-btn`/`coverage-btn` (11 px) tragen jetzt `--text-sm` und keinen Buchstabenabstand.
4. **Primäre Knöpfe sind gefüllt:** die Knöpfe „Continue“, „Download“, „Run as a job“ in Dialogen (`lm-btn primary`: nur Rand und Schrift in Akzent) sind jetzt `.btn.primary`.
5. **Datensatz-, Coverage- und Werkzeugknöpfe** sind `.btn` mit `aria-pressed`; „Coverage“ ist nicht mehr gestrichelt. Die Datensatzknöpfe bleiben zweizeilig mit dem Reifegrad-Chip.
6. **Die Knöpfe oben rechts** (`Zoom to selection`, `Basemap`, Theme) sind `.btn.panel` (Panel-Hintergrund) in einer Flexreihe mit `--space-2` Abstand; der Theme-Knopf hat kein `aria-pressed` mehr, bis ihn Teil 4 ablöst.
7. **`Segment-Umschalter` (`pp-seg`), Chips (`pp-chip`), Zeilen in Menüs und Listen (`pm-menu-list button`, `lm-name`, `result-group-head`, `cm-item`), Titel zum Umbenennen (`vc-title-btn`, `pm-title-edit`) und die Falzgriffe (`pp-grip`)** haben weiter eigene Formen; sie sind keine Knopfformen im Sinn von Zeile 44. Siehe Frage 2.
8. **Namen von Komponenten-Eigenschaften** (`CloseButton title`, `CopyButton title`, `AutoScaleButton title`) bleiben; sie reichen den Tooltip nur an `data-tip` weiter.

**Zusätze Otto (04.11.2026, zu #289), umgesetzt:**
1. **Ein Auge:** Das Auge in Textfarbe gilt überall. `components/EyeButton.tsx` ist das eine Bauteil (Layer-Zeile, „Search results“ in Liste und Layer-Manager, Kopf der Seitenleiste); verborgen oder gesperrt ist das durchgestrichene Auge in derselben Textfarbe, ohne `.off` und ohne Akzent. Prüfung in `uiRules.test.ts` (Auge nur in `EyeButton.tsx`, keine Regel mit eigener Farbe, jeweils mit Gegenprobe), Verhalten in `EyeButton.test.tsx`. Im Leitfaden §3.
2. **Keine Tooltips an Namen:** Datensätze (Auswahl im Control-Menü, Dropdowns in der Suche, in der Liste und in der Ansicht), Gruppenköpfe, Layer-Namen und der Titel der Ansicht haben keinen Tooltip mehr; ein nicht wählbarer Datensatz nennt weiter den Grund. Auslegung (gilt bis Otto widerspricht): Der Hinweis eines Layers (`note`, z. B. „Preview per scene …“) bleibt als Tooltip am Namen, weil er eine Auskunft und nicht der Name ist; ebenso die Erklärung des Eintrags „Search results“ im Layer-Manager. Prüfung in `uiRules.test.ts` mit Gegenprobe; im Leitfaden §4.

**Antworten Otto (04.11.2026, zu #289):**
1. **Sperren per Tastatur:** `disabled` bleibt. Der Grund per Tastatur (`aria-disabled` an allen gesperrten Knöpfen) kommt nicht jetzt, sondern als Punkt für M6 (Barrierefreiheit) ins Backlog; im Leitfaden §4 steht er als bekannte Grenze.
2. **Segment-Umschalter und Chips:** `pp-seg` und `pp-chip` werden in Teil 3b zu **einer** Form `.btn.seg` (in einer Gruppe).

### 8.4 Teil 3b — Hinweise, Abzeichen, Farben, Schrift, Auswahlknöpfe (umgesetzt, 04.11.2026)

**Umfang:** Rest von Teil 3 (§7.7): Hinweise und Fehler (Zeile 45), Abzeichen (21, 22), feste Farben (46), Schrift (47), tote Regeln (51), `.btn.seg` (Antwort Otto zu #289), Prüfungen 4 und 5. Dazu drei Zusätze Ottos vom 04.11.2026, die in dieselbe Session kamen: Tooltips in zwei Stufen, der doppelte Rahmen im Control-Menü, Autofill. Der PR ist deutlich über dem Richtwert (mechanische Umbenennungen in gut 40 Dateien und den Tests, siehe unten).

**Umgesetzt:**
- **Hinweise:** `.hint` (`--text-xs`, `--muted`), `.hint.warn` (`--accent-2`), `.error` (`--danger`). Weg: `hint-text`, `pp-help`, `vc-note` und `--invalid` (ein falsches Feld nimmt `--danger`). `pm-note`, `pm-empty` und `place-attribution` bleiben als Klassen eines Ortes (nur Platz).
- **Abzeichen:** `components/Badge.tsx` mit `.badge` (Pille, `--accent-2`, `--text-xs`); „Preview“, „Temporary“, „Overview“, „Zoom in“ und „Loading…“ sind dasselbe Bauteil. Weg: `pp-badge`, `preview-badge`, `vc-temporary` und das tote `.badge`/`.badge.preview`.
- **`.btn.seg`:** `pp-seg` und `pp-chip` sind eine Form (`.btn` mit `--text-xs`); der gewählte trägt `aria-pressed`, die Klasse `on` entfällt dort.
- **Farben:** Außer der Daten-Legende (`.legend-gradient`) steht keine Farbe mehr in `index.css`. Neues Token `--scrim` (Dunkel hinter einem Dialog). Die Karten-Attribution im dunklen Thema nimmt `--panel-bg` und `--text` (vorher Schwarz 0.6 und Weiß).
- **Schrift:** `button, input, select, textarea { font: inherit }`; 22 Einzelregeln mit `font-family: var(--font)` entfallen; die Karte bekommt `--font` über `.app .maplibregl-map` (MapLibre setzt `Helvetica Neue, Arial`). Gemessen vor und nach: Bedienelemente mit Text behalten ihre Größe; nur Symbolknöpfe, Kästchen und Schieber ohne eigene Größe wechseln von 13.33 px auf die Seitengröße (ohne sichtbaren Text).
- **Tote Regeln:** `.db-select`, `.field-label-aside`, `.pp-options`, `.result-collection`, `.searchbox`, `.searchbox-spinner`, `.vc-polmodes` (mit `.level-btn`); Klassen ohne Regel `dialog-as`, `resampling-label`, `results-head-right` aus dem Code. Bleiben als Haken für Tests und Browser-Skripte: `resampling-dialog`, `resampling-part`.
- **Prüfungen** (`uiRules.test.ts`, je mit Gegenprobe): keine feste Farbe (mit Ausnahmeliste und Grund), eine Familie, keine alten Klassen, `Badge` nur in `Badge.tsx`, keine Regel für eine Klasse, die niemand nennt; `tokens.test.ts` (`--scrim`, kein `--invalid`, `.hint`, `.error`, `.badge` ohne feste Maße).

**Tooltips in zwei Stufen (Zusatz Otto):**
- `data-tip-level="advanced"` (ohne Angabe = simple), ein Weg über `TipLayer` (`tipLevel.ts`: `tipShown`, `currentTipLevel`, `setTipLevel`). Bis Teil 4 den Schalter bringt, gilt „Advanced“ (das bisherige Verhalten). `aria-label` bleibt überall; nichts ist entfernt.
- **Gesperrt ist immer simple:** `TipLayer` zeigt den Tooltip eines gesperrten Elements in beiden Stufen, auch wenn seine Beschreibung `advanced` ist (Grund sonst Beschreibung). Das ist der Weg für (a), ohne 150 Stellen einzeln umzustellen.
- **Als „advanced“ markiert (154 Stellen in 41 Dateien):** Knöpfe mit Text, selbsterklärende Symbole (rotes x, Auge, Mülleimer, Download, Stift, Plus, Pfeile der Zeitleiste und der Zeilen, Ziehgriff, Falzgriffe, Kopieren, Feld leeren), Beschriftungen und Werte (Datum, Ablauf, Deckkraft, Histogramm), Filter, Gruppen, Abzeichen. Nach Datei: App 2, AdvancedSearch 5, AutoScaleButton 1, Badge 1, BandChoice 2, BandSelect 1, BasemapMenu 2, ClearableInput 1, CloseButton 1, ColormapPicker 2, ControlPanel 8, CopyButton 1, CopySceneNames 1, DownloadAll 1, DownloadDialog 3, Draggable 1, ExportJobOffer 1, EyeButton 1, Inspector 1, InspectorParts 6, JobDetails 10, JobRow 3, LayerActions 3, LayerDownload 2, LayerManager 12, MosaicJobs 1, OpacityRow 2, OriginalFiles 6, ProcessingManager 12, ProcessingPanel 15, RangeHistogram 1, RenderFields 7, ResultControls 2, ResultsPanel 6, ShareLink 2, StatusBar 1, StepForm 4, TimeSlider 4, Toolbar 2, ViewBar 6, ViewerControls 11.
- **Simple (21 Stellen, ohne Stufe):** (i) (`Tip`); Namen nicht selbsterklärender Symbole: Leiste links, Reverse (Colormap-Feld und Liste), „Process layer“, „Flip through layers“, „Actions“ (Job, Gruppe), „Restore“, die Aktion der Zeile eines Jobs, „Search results“ nach oben; reine Gründe: „Search“, „Apply“ und die Auswahl der Ausführung im Processing-Panel, ein nicht wählbarer Datensatz, „ZIP“ eines abgelaufenen Jobs, „Download all“ gesperrt, „Add to layers“ eines Jobs, der schon Layer ist; Texte, die abgeschnitten sein können: Titel von Job und Stapel, Kennung der Szene.
- **Prüfungen:** `uiRules.test.ts` (jede Angabe ist „advanced“ und steht an einem `data-tip`; (i), die Namen und die Gründe sind nie „advanced“, rotes x, Auge, Mülleimer, Abzeichen sind es; je mit Gegenprobe), `tipLevel.test.ts`, `TipLayer.test.tsx` (simple hält advanced zurück, ein gesperrtes Element zeigt seinen Grund).
- **Auslegungen (gelten bis Otto widerspricht):** (1) Bei (c) bleibt es beim Tooltip, der immer erscheint; der volle Text eines abgeschnittenen Textes bleibt simple, auch wenn der Text nicht abgeschnitten ist (keine Messung der Kürzung). (2) Ein Pfeil (Zeitleiste, nach oben/unten) und das Kopieren gelten als selbsterklärend; „Process“ (Zahnrad), „Actions“ (⋯), „Restore“ und die Symbole der Leiste nicht. (3) „Link channels“ gibt es in dieser Fassung des Codes noch nicht; es kommt als simple, sobald es da ist. (4) Abzeichen („Temporary“, „Preview“) sind advanced: ihre Erklärung ist keine Erklärung hinter einem (i).

**Fund Otto: doppelter Rahmen im Control-Menü (nachgestellt, hell und dunkel, 1280 und 360 px):**
- **Ursache:** Ein Feld mit dem Fokus zeigte **drei** Zeichen auf einmal: den Ring aus 3a (`outline`, bei Textfeldern auch nach einem Mausklick, weil der Browser `:focus-visible` dort immer setzt), dazu den alten Rand in Akzentfarbe und den Schein (`box-shadow`) aus den Regeln `input[type='text']:focus`, `input[type='date']:focus`, `.vc-field … :focus` und `.filter-range input:focus`. Im Control-Menü betraf das „Scene name“, „Place name“ („Area of interest“) und die beiden Datumsfelder. Ein Rahmen in einem Rahmen um den Abschnitt selbst fand sich nicht; der Rahmen um das Feld war doppelt.
- **Weitere Stellen, gefunden mit demselben Prüflauf über alle Panels:** `.vc-unit` und `.pm-title-edit` (Randfarbe zusätzlich zum Ring bei `:focus-visible`), `.vc-scene-names` (die Randfarbe folgte der Textfarbe), `.pm-line:focus-within` (Balken um die ganze Zeile eines Jobs).
- **Behoben:** alle `:focus`-Regeln mit Rand, Schein oder Ring entfallen, ebenso die zweiten Zeichen bei `:focus-visible`; `.pm-line:focus-within` tönt die Zeile nur noch (der Balken bleibt beim Zeigen). Der Ring ist das eine Zeichen, am bedienten Element, bei einem Knopf nur per Tastatur.
- **Prüfung:** `uiRules.test.ts` (kein Rand/Schein/Ring bei `:focus`, kein zweites Zeichen bei `:focus-visible`, nichts um einen Abschnitt bei `:focus-within`) und `e2e/focus-and-type.cjs` (setzt den Fokus auf jedes Bedienelement des Control-Menüs und meldet jedes zweite Zeichen am Element und jede Änderung an einem umgebenden Kasten; Gegenprobe mit der alten Regel; ein Mausklick auf einen Knopf lässt keinen Ring). Dieselbe Messung lief über Advanced search, Layer-Manager, Seitenleiste, Ergebnis-Layer, Processing-Panel, Jobs und Auswahlleiste ohne Fund; `settings-box` lief in die Zeitgrenze.

**Autofill (Zusatz Otto):** `autoComplete="off"` an jedem Feld, das Text annimmt (Suche, Szenenname, Ort, Zahlen, Datum, Namen, Ausdrücke; `ClearableInput` setzt es selbst); zwei Regeln für `input:-webkit-autofill` und `input:autofill` mit `--text` und `--input-bg` über `--map-bg` (ein Feld bleibt im dunklen Thema dunkel). Prüfung: `uiRules.test.ts` (jedes Textfeld hat es; die Regeln stehen; je mit Gegenprobe) und `e2e/focus-and-type.cjs` (Attribute im DOM, die Regeln im Blatt). **Grenze:** Chromium im Test lässt sich nicht von einem gespeicherten Eintrag füllen und bietet keinen Weg, `:autofill` zu erzwingen; die Farbe eines echten Vorschlags ist darum nicht im Bild geprüft, nur dass die Regel im Blatt steht und die Tokens nimmt.

**Nicht in 3b (Vorschlag):** Abstände, Schriftgrade und Radien der übrigen Klassen (201 feste Längen in 287 Klassen von `index.css`; der Token-Test prüft sie nur für die Bereiche, die schon auf Tokens stehen). Das ist eine eigene Umstellung, siehe Frage 1.

**Auslegungen (Vorschlag, gelten bis Otto widerspricht):**
1. `.hint` ist 11 px (vorher `hint-text` 10 px, `pp-help` 11 px): ein Wert für alle.
2. Badge: Polsterung `--space-1`/`--space-2` (vorher 2/8 px), Schrift `--text-xs` mit 0.08 em Abstand.
3. Die Attribution der Karte im dunklen Thema ist `--panel-bg` mit `--text` (leicht bläulicher als vorher Weiß).
4. `maturity-chip` (die Reife im Datensatzknopf) bleibt eine Beschriftung in `--accent-2`, kein Abzeichen: er sitzt in einem Knopf mit wenig Platz.
5. Ein Textfeld zeigt den Ring auch nach einem Mausklick (der Browser setzt `:focus-visible` für Textfelder immer); Knöpfe nicht.

**Fragen an Otto (kurz zu beantworten):**
1. Die übrigen Abstände, Schriftgrade und Radien (201 feste Längen) auf Tokens: (1) eigener Teil nach 3b, vor 4 — **Empfehlung**; (2) in Teil 6 mitnehmen; (3) so lassen.
2. Textfeld und Mausklick: (1) Ring bleibt auch beim Klick, das Textfeld braucht ein sichtbares Zeichen für die Schreibmarke — **Empfehlung**; (2) ein Textfeld zeigt nur bei Tastatur ein Zeichen (dann ohne Zeichen beim Klick hinein).
3. Tooltip (c): (1) wie umgesetzt, immer ein Tooltip mit dem vollen Text — **Empfehlung** für Teil 3b; (2) Teil 4 misst die Kürzung (`scrollWidth > clientWidth`) und zeigt den Tooltip nur dann.

### 8.5 Teil 5 — RGB je Kanal (umgesetzt, 04.11.2026)

**Umfang:** §7.6, Vorgabe 1 (§7.0): Bereich und Art (absolute/percentile) je Kanal im Ergebnis-Layer und in der Processing-Vorschau, der Permalink hält beides. Löst §6 auf.

**Umgesetzt:**
- **Ergebnis-Layer** (`ResultControls`): drei Kanalzeilen, jede mit eigener Einheit wie in der Ansicht (`RenderFields` mit `onUnit`/`onPercent`). „Apply“ misst die Kanäle in Perzentilen an ihren eigenen Werten (`channelsAtOwnPercent`), die anderen bleiben wie getippt. Der Layer hält die Paare in `ResultLayerInfo.percentChannels` (und `savedPercentChannels`, solange ein Look angewendet und nicht gespeichert ist), „Save“ schreibt `channels[i].percent` in `jobShelf` (`rangeJson`/`rangeOf`, ohne neue `SHELF_VERSION`: alte Einträge lesen sich wie vorher).
- **Processing-Vorschau:** bei RGB drei Kanalzeilen; „Apply“ misst über `applyRangeChannels` (die Messung teilt sich `bandsAtPercent` mit `applyRangePercent`). `rangeDraft.channels` und `range.channels` tragen die Paare; ein Wert in den gemeinsamen Feldern gilt für alle und löscht `channels`.
- **Permalink:** `view.range` bekommt `percent?` und `channels?` (§7.6; Backend `PermalinkRange`, `adr/0015` §14h). Das Frontend schreibt und liest sie in `permalinkRange.ts`; ein Link ohne beides öffnet wie vorher, ein ungültiger macht den Link unlesbar (wie jedes andere Glied der Ansicht).
- **Nur für RGB:** `channels` gilt nur, solange die Vorschau das Farbbild zeigt (`handRangeOnShownBand`, `previewSpec`, `resultRender`); bei einem Band gilt nur der erste Kanal. So kann ein Rest aus RGB keine drei `rescale` an eine Einzelband-Kachel hängen.
- **Alt:** Ein Paar für alle drei Kanäle (Look aus der Zeit vor UI-03e, auch in `jobShelf`) steht auf jedem Kanal, bis einer geändert wird (`channelsOfRange`).

**Auslegungen (Vorschlag, gelten bis Otto widerspricht):**
1. `percent` und `channels` am selben Bereich sind ein `422` (§7.6 „Kanäle bei einem Band: Vorschlag 422“): Das Backend kennt das Band nicht, es prüft die Form; ein Bereich nennt seine Einheit nur einmal.
2. „Auto-scale“ bei RGB: Jeder Kanal in Perzentilen bekommt 2/98, die anderen den gemessenen Bereich (wie in der Ansicht); in der Vorschau ohne Kanal in Perzentilen bleibt es der alte Weg (`autoStretch`).
3. ~~Ein Kanal mit unzulässigem Paar lässt „Apply“ und „Save“ offen~~ — **Antwort Otto (04.11.2026): gesperrt.** Ein Kanal mit unzulässigem Bereich oder Paar sperrt „Apply“ und „Save“ (Ergebnis-Layer) bzw. „Apply“ (Vorschau); der Tooltip nennt Kanal und Grund („G: vmin must be below vmax“, „B: the lower percentile must be below the upper one“), die Felder des Kanals sind markiert (`aria-invalid`, Rand `--invalid`). Die Meldung unter den Feldern entfällt für Kanäle (`channelProblems` in `channels.ts`).
4. Prozente im Permalink sind ganze Zahlen (`int`, 0–100, `low` < `high`), wie sie die Felder zulassen.
5. Das Schema schreibt nur, was da ist: ein alter Link kommt ohne `percent: null` zurück (`_Sparse`), damit sich nichts an ihm ändert.

**Prüfungen:** Backend `test_permalink_route.py` (alt, neu, Prozent je Kanal, zwei Kanäle, vier Kanäle, Prozent außerhalb 0–100, falsche Reihenfolge, Text, beides zusammen; Gegenprobe ohne die Prüfungen schlägt fünf Fälle fehl), Frontend `permalink.test.ts`, `ProcessingResultRgb.test.tsx`, `ProcessingShowRgb.test.tsx`, `ProcessingShare.test.tsx`, `jobShelf.test.ts`; Browser `e2e/rgb.cjs` (Hell/Dunkel, 1280 und 360 px, Einheiten je Kanal, Überlappung und Überstand).
