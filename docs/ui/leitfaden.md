# EarthX — Leitfaden der Oberfläche

**Stand:** 04.11.2026, UI-04 Teil 4 (`docs/plans/vp3/ui-04-einheitlichkeit.md` §7, §8). Grundlage sind die Regeln und Begriffe aus UI-03 (#277–#283), NM4-75 (#284, `adr/0028`) und die Antworten Ottos zu UI-04 (§7.0, §7.9).

**Gilt für:** jede Änderung an `frontend/`. Künftige Pläne verweisen auf diese Datei. Neue Begriffe, Bauteile oder Symbole kommen zuerst hierher.

**Markierung:** Steht an einer Regel *(folgt in Teil n)*, ist sie entschieden, aber noch nicht überall umgesetzt. (Nach Teil 4 stehen nur noch Regeln mit Markierung für Teil 6.)

## 1. Grundsätze

1. **Gleiches sieht gleich aus:** Ähnliche Bedienelemente nutzen dasselbe Bauteil und die Tokens aus `frontend/src/tokens.css`. Feste Farben, Abstände, Schriftgrade und Radien gibt es nur dort.
2. **Gleiches heißt gleich:** ein Begriff je Sache (§2), in Knopftext, Überschrift, Tooltip, `aria-label` und Fehlermeldung.
3. **Gleiches bedient sich gleich:** ein Weg zum Schließen (§5), ein Weg zum Übernehmen und Speichern (§6), eine Sperrregel (§4), ein Symbol je Aktion (§3).
4. **Wenig Text:** Sichtbar sind Beschriftungen, Werte, Fehler, die eine Handlung verlangen, und Pflichtangaben (Attribution, Lizenz). Erklärungen stehen im Tooltip oder hinter (i) *(Rest folgt in Teil 6)*.
5. **Keine Funktion entfernen oder ausblenden, um aufzuräumen** (Otto, 31.10.2026). Was gerade nicht geht, bleibt gesperrt und nennt den Grund. Ausnahmen hat Otto einzeln entschieden, z. B. „Quick processing“ zeigt nur, was gilt (#280).
6. **Oberflächentexte nur Englisch.** Dokumente zur Oberfläche sind Deutsch.

## 2. Begriffe

| Begriff | Bedeutung | Nicht |
|---|---|---|
| AOI | das gezeichnete oder geladene Gebiet; die Überschrift im Control-Menü ist „Area of interest“ | „your area“, „Area“ als Name des Gebiets |
| scene | ein Eintrag des Katalogs (Item) | |
| image | was ein Zeitschritt der Ansicht oder ein Layer zeigt | „picture“ |
| view | die geöffnete, noch nicht angeheftete Darstellung in der Seitenleiste („Close and drop this view“, „Add current view to layers“) | |
| time step | ein Datum der Zeitleiste („Previous time step“, Zähler „4 / 7“) | „step“ (das ist ein Schritt im Processing) |
| layer | ein Eintrag im Layer-Manager | |
| Add to layers / Add all to layers / Add current view to layers / Add preview to layers | etwas als Layer anheften; der Tooltip sagt „Add … to the layers“ | „Pin …“ |
| Search results | die Ergebnisse der Suche: Leiste, Kopf der Liste, Zeile im Layer-Manager | „Results“ |
| Jobs | der Processing-Manager | „Processing jobs“ |
| job / batch / order / recipe | Auftrag am Server / mehrere Jobs eines Auftrags / was im Processing-Panel eingestellt ist / die Datei `recipe.json` | |
| Close | schließt Fenster, Leiste, Dialog, Meldung; nur das rote x (§5) | „Dismiss“ |
| Cancel | verwirft eine Rückfrage oder bricht einen Job ab | |
| Stop | hält einen laufenden Vorgang an; was fertig ist, bleibt („Stop checking. What is found stays.“, laufender Download) | „Cancel“ für einen Download |
| Remove | nimmt etwas aus einer Liste der Oberfläche (Layer, Schritt, Gruppe) | |
| Delete | löscht dauerhaft auf der Plattform (Job, Link) | |
| Clear | leert ein Feld, die AOI oder die Suchergebnisse; der Knopf der AOI im Control-Menü heißt „Clear AOI“ (Beschriftung, Tooltip, `aria-label`), der der Ergebnisse „Clear search results“ | „Clear“ allein als Knopftext |
| Hide / Show | das Auge; bei der Coverage „Hide coverage“ | „Clear coverage“ |
| Apply / Apply to all / Save | §6 | |
| Retry / Run again / Retry failed parts | dieselbe Anfrage noch einmal / Job neu starten / nur die gescheiterten Teile eines Stapels | „Try again“ als Knopf (im Satz einer Meldung erlaubt) |
| Auto-scale | 2. bis 98. Perzentil in die Felder | „auto-scale“, „Auto stretch“ |
| Quick processing, Enhance contrast | Abschnitt der Seitenleiste mit Indizes und Kontrast (UI-03d/e) | |
| Scale, vmin / vmax, absolute / percentile | der Bereich einer Darstellung und seine Art (NM4-65, UI-03e); RGB hat einen Bereich und eine Art je Kanal, in Ansicht, Layer, Ergebnis-Layer und Processing-Vorschau, und der Permalink hält beides | „min/max“ |
| Temporary | Abzeichen neben dem Titel der Ansicht, solange kein Layer das Bild so hält, wie es gezeichnet ist | |
| Filter within AOI only | der Schalter in „Advanced search“ | |
| Copy original scene name | kopiert die Kennungen der Szenen in die Zwischenablage | |
| Download crop / Download full scene(s) / Download | Zuschnitt der AOI / ganze Szenen / ein Layer; die Formen heißen „One file per band“, „One file per resolution“, „One multi-band file“ (NM4-75) | |
| — none — / — choose — | kein Wert, auch die gesperrte Colormap bei RGB / Pflichtwahl ohne Vorgabe | „–“ |
| Choose | auswählen, im Text | „Pick“ |
| finished | Status eines Jobs („Finished“); in Zusammenfassungen klein („3 finished · 1 running“) | „done“ |
| Settings | das Einstellungsmenü unten in der Leiste links (§9); die Seitenleiste heißt für Screenreader nach ihrem Inhalt („Image settings“, „Layer settings“) | |
| Basemap, Overlays, Projection, Appearance, Tooltips | die fünf Abschnitte des Menüs „Settings“; Wahl je Abschnitt: Satellite / Streets / Grey / Outlines, Labels / Graticule / Relief, Mercator / Globe, Light / Dark / System, Simple / Advanced | „Theme“, „Mode“ für Light/Dark |
| Coverage, Hide coverage | die Abdeckung des gewählten Datensatzes über den sichtbaren Kartenausschnitt (§9); sie wird mit „Coverage“ gewählt und mit „Hide coverage“ beendet | „Clear coverage“, ein Eintrag „Hide coverage“ in der Wahl des Datensatzes |

**Schreibweise:**
- **Satzanfang-Stil** für Knopftexte, Überschriften und Tooltips („Add to layers“, „Auto-scale“). Großbuchstaben bei Abschnittsköpfen nur per CSS.
- Abkürzungen groß: AOI, CRS, RGB, UTM, auch in Feldnamen aus dem Schema des Servers (`fieldTitle` in `schemaForm.ts`).
- **Ellipse** „…“, nie „...“; nur an Knöpfen, die noch etwas fragen („Load recipe…“, „Move to group…“), und in Ladezuständen („Loading…“).
- Eine **Zahl mit Nomen** steht in Einzahl oder Mehrzahl nach der Anzahl („1 scene“, „3 scenes“; `counted` in `plural.ts`), nie „scene(s)“.
- Kein „&“, sondern „and“. Trenner „·“, Bereich „–“, Bruch der Zeitleiste „4 / 7“.
- **Tooltips:** ein Satzteil ohne Schlusspunkt; ganze Sätze mit Punkt.
- Anführungszeichen typografisch („ “ als “ ”).
- **Keine Einheit an „Scale“** (vmin/vmax), an keiner Stelle: Seitenleiste, Layer, Ergebnis-Layer, Processing-Vorschau (Otto, 03.11.2026). Die Einheiten der Daten stehen in `BANDS.txt` und in den Metadaten; an den Band-Chips des Processing-Panels bleibt die Einheit („· dB“).

## 3. Symbole

- **Eine Quelle:** Lucide (`lucide-react`, ISC; die Symbole aus Feather unter MIT, Hinweise in `frontend/THIRD_PARTY_NOTICES.md`). Importiert werden nur die benutzten Symbole, alle in einer Datei: `frontend/src/components/icons.ts`. Sie gibt jedes unter eigenem Namen weiter (`DownloadIcon`); nur sie importiert `lucide-react`, und jeder Eintrag muss benutzt sein.
- **Ein Strich:** 1.5 px, an jeder Größe gleich dick (`absoluteStrokeWidth`). Drei Größen, als Token in `tokens.css` und als Zahlen in `components/iconSizes.ts` (ein Test hält beide zusammen): 16 px als Standard (`--icon-size`, `<DownloadIcon />`), 14 px in Listenzeilen (`--icon-size-sm`, `<DownloadIcon size={14} />`) und 20 px für die Symbole der Leiste links (`--icon-size-rail`, `size={ICON_SIZES.rail}`; Otto, 04.11.2026). Farbe `currentColor`.
- **Neben einem Text** steht das Symbol davor und bekommt `lead`: `<CogIcon lead />Process`. Der Abstand kommt aus dem CSS (`.icon-lead`), kein Leerzeichen im Text.
- **Ein Knopf nur mit Symbol** hat einen Namen für Screenreader (`aria-label`) und einen Tooltip. Gleiche Aktion, gleiches Symbol, auch wenn Text dabeisteht oder nicht.
- **Eigene Zeichnungen gibt es nicht.** Das einzige `<svg>` im Code ist das Balkendiagramm des Histogramms (`RangeHistogram`), kein Symbol.
- **Der Haken** vor dem gewählten Eintrag eines Menüs ist ein Symbol in einem Platz fester Breite (`MenuTick`), kein Zeichen im CSS.
- **Einzige Ausnahme:** Settings ist „Settings 6 Line“ von MingCute (Apache-2.0, `mingcute_icon` 2.9.72, `svg/system/settings_6_line.svg`). Es wird als einzelnes SVG übernommen, als Strich nachgezeichnet und an Lucide angeglichen; die Änderung ist vermerkt. Herkunft, Änderung und Lizenztext stehen in `frontend/THIRD_PARTY_NOTICES.md`, die Zeichnung (mit dem Vermerk der Änderung, Apache-2.0 §4(b)) in `components/settingsIconNode.ts`; `icons.ts` gibt sie als `SettingsIcon` weiter, wie alle anderen.
- **Das Auge ist ein Bauteil, `EyeButton`** (Otto, 04.11.2026): in der Layer-Zeile, bei „Search results“ (Kopf der Liste und Eintrag im Layer-Manager), im Kopf der Seitenleiste und überall sonst, wo etwas gezeigt oder verborgen wird. Eine Farbe, die des Textes; **verborgen** (oder gesperrt) ist das durchgestrichene Auge (`eye-off`), nie eine andere Farbe und kein Rahmen. In Listenzeilen 22 px mit 14-px-Symbol (`row`), sonst 28 px mit 16 px. `EyeIcon` und `EyeOffIcon` kommen nur in `EyeButton.tsx` vor; kein CSS gibt dem Auge eine eigene Farbe.
- **Keine Textzeichen als Symbole** (⇩ ✎ ✕ ⚙ ＋ ⋯ ▾ ↻ …). Im Text erlaubt bleiben „…“, „—“ in „— none —“, „·“, „–“, „→“ zwischen zwei Datumsfeldern, „×“ in Maßen („10 m × 10 m“), „µm“.

| Bedeutung | Lucide |
|---|---|
| Download (überall, auch „Download all“) | `download` |
| Zeigen / Verbergen (`EyeButton`, Textfarbe) | `eye` / `eye-off` (durchgestrichen = verborgen) |
| Entfernen / Löschen / Leeren einer Liste (auch „Clear AOI“, „Clear search results“) | `trash-2` |
| Umbenennen | `pencil` |
| Process | `cog` (das Zahnrad bleibt, Otto) |
| Settings | MingCute „Settings 6 Line“ (`SettingsIcon`, als Strich nachgezeichnet) |
| Mehr | `ellipsis` |
| Ziehgriff | `grip-vertical` (Zeilen), `grip-horizontal` (Auswahlleiste) |
| Zurück („Change image“, „Order“, Colormap-Liste) | `arrow-left` |
| Bild davor / danach | `chevron-left` / `chevron-right` |
| Auf- / Zuklappen | `chevron-down` / `chevron-up` / `chevron-right` |
| Nach oben / unten schieben | `arrow-up` / `arrow-down` |
| Hinzufügen | `plus` |
| Schließen | `x`, rot, nur in `CloseButton` |
| Feld leeren | `circle-x`, grau (`ClearIcon`) |
| Retry, Run again | `rotate-cw` |
| Wiederherstellen eines Jobs | `archive-restore` |
| Letzte AOI | `history` |
| Hochladen | `upload` |
| Colormap umkehren | `arrow-left-right` |
| (i) / Warnung | `info` / `triangle-alert` (`Tip`: `tone="warn"` zeigt die Warnung) |
| Erledigt, kopiert | `check` |
| Kopieren | `copy` |
| Abspielen | `play` / `pause` |
| Zoom to selection | `scan` |
| Suchergebnisse nach oben | `arrow-up-to-line` |
| Flip through layers | `arrow-up-down` |
| AOI-Werkzeuge | `map-pin`, `square`, `pentagon` |
| Leiste | `search`, `layers`, `clipboard-list`, `list` |
| Coverage | `layout-grid` |
| Erscheinungsbild (Light / Dark / System) | `sun`, `moon`, `monitor` |

## 4. Sperren

- Was gerade nicht geht, ist **gesperrt** (`disabled` oder `aria-disabled="true"`) und nennt den **Grund im Tooltip**. Der Grund wiederholt nicht den Knopftext. Beispiele: „Type a place name first“, „No earlier AOI in this browser“, „Already at the top“, „Job deleted: restore it first“.
- **Ein Aussehen:** ein gesperrtes Element ist auf `--disabled-opacity` (0.4) gedimmt, in einer Regel für `:disabled` und `[aria-disabled='true']`. Keine eigene Deckkraft an einem gesperrten Element.
- **`aria-disabled` für neue Sperren mit Grund:** das Element bleibt in der Tab-Reihenfolge, der Grund ist auch per Tastatur lesbar; der Handler fängt den Klick ab. Ein bestehendes `disabled` bleibt; sein Tooltip erscheint, wo der Zeiger darüber liegt (`TipLayer`), per Tastatur nicht.
- **Bekannte Grenze (Otto, 04.11.2026):** Der Grund eines `disabled`-Knopfs ist per Tastatur und Screenreader nicht lesbar; ein `disabled`-Element nimmt keinen Fokus. Die Umstellung aller gesperrten Knöpfe auf `aria-disabled` ist ein Punkt für M6 (Barrierefreiheit).
- Wo eine gesperrte Stelle einen Platz hält, bleibt sie an diesem Platz, z. B. die Colormap bei RGB als gesperrtes „— none —“, auch in der Processing-Vorschau.
- **Ein Tooltip-Weg:** `TipLayer` über `data-tip`. Er erscheint bei Zeiger und Fokus; `TipLayer` setzt für die Dauer `aria-describedby`, bei einem `label` mit Tooltip am Feld darin; ein Knopf nur mit Symbol hat zusätzlich seinen `aria-label`. **Keine Tooltips an Namen** (Otto, 04.11.2026): nicht an Datensätzen (Auswahl im Control-Menü, Dropdowns in der Suche, in der Liste und in der Ansicht), nicht an Gruppenköpfen, nicht an den Namen von Layern und dem Titel der Ansicht. Ausnahmen: ein Datensatz, der gerade nicht wählbar ist, nennt weiter den Grund („… — not viewable: …“); der Hinweis eines Layers (`note`, etwa bei einer Vorschau je Szene) und die Erklärung des Eintrags „Search results“ im Layer-Manager. Ein langer Name wird gekürzt, nicht erklärt.
- **`title` gibt es an keinem Element** (ein zweiter Tooltip des Browsers), außer an `<option>` (eine native Liste zeigt sonst nichts) und an den Steuerelementen von MapLibre. Ein Test findet jedes andere `title`.

## 5. Schließen

- **Ein Weg:** das kleine rote x aus `CloseButton.tsx` (Tooltip „Close“, ein längerer Tooltip, wo das Schließen eine Folge hat). Das gilt auch für Meldungen der Statusleiste.
- **Esc schließt nichts:** keine Ansicht, Seitenleiste, kein Panel, Blatt, Menü, keine Liste und keinen Tooltip. Ausnahmen:
  - Esc = „Cancel“ in Bestätigungsdialogen („Values are resampled“);
  - Esc beendet „Flip through layers“;
  - Esc bricht das Umbenennen und das Ziehen einer Zeile ab (schließt nichts).
- **Klick daneben:**
  - Dialoge schließen nicht; sonst ginge z. B. ein laufender Download verloren. Ausnahme: die Rückfrage „Values are resampled“ (Klick daneben = Cancel).
  - „Advanced search“ schließt (Otto, 02.11.2026).
  - Menüs und Auswahllisten schließen mit einer Wahl oder einem Klick daneben; Tooltips gehen mit Zeiger oder Fokus.
- Was etwas entfernt (Layer, Schritt, Link, Suchergebnisse) oder leert, ist kein Schließen und hat sein eigenes Symbol (§3).

## 6. Übernehmen und Speichern

- **Ansicht der Suche:**
  - „Apply“ zeichnet die Werte am gezeigten Bild.
  - „Apply to all“ zeichnet alle Bilder des Datensatzes in der Ansicht so.
  - „Temporary“ steht, solange kein Layer das Bild so hält.
- **Layer:** Ein Band ist erst mit „Apply“ zu sehen, „Save“ speichert; ohne „Save“ gibt das Schließen den gespeicherten Layer zurück (#257, #272, Otto).
- **Ergebnis-Layer:** „Apply“ zeichnet, „Save“ hält die Werte für den Layer bzw. für alle Layer des Jobs, wie der Tooltip sagt.
- **Quick processing:** Ein Index und „Enhance contrast“ kommen in die Felder und werden mit „Apply“ gezeichnet. Ein zweiter Klick stellt die Felder zurück.
- **Namen:**
  - Enter oder Verlassen des Feldes speichert, Esc verwirft.
  - Ein leerer Name behält den alten.
  - Es gibt keinen eigenen Knopf „Save“ dafür.

## 7. Bauteile

| Bauteil | wofür |
|---|---|
| `CloseButton` | der einzige Schließen-Knopf |
| `InlineRename` | Umbenennen an Ort und Stelle |
| `Inspector` / `InspectorParts` | die Seitenleiste rechts (320 px, unter 900 px Blatt bis 55 %), Kopf, „Display“, „Actions“ |
| `RenderFields`, `ColormapField`, `ScaleHistograms` | Band, „Scale“, Colormap; überall, wo eine Darstellung eingestellt wird |
| `BandSelect`, `OpacityRow`, `LayerActions`, `LayerDownload`, `CopySceneNames` | gemeinsame Felder und Aktionen von Ansicht und Layer |
| `EyeButton` | das Auge: zeigt oder verbirgt (§3) |
| `icons.ts`, `MenuTick` | alle Symbole; der Haken in Menüs |
| `Tip` / `TipLayer` | (i), Warnung und Tooltips |
| `SettingsMenu` | das Symbol „Settings“ unten in der Leiste und sein Menü (§9); sitzt in `AppRail` |
| `Popover` | Menüs, Listen und das Formular „Advanced search“; `beside` stellt ein Menü rechts neben einen Rand (die Leiste) |
| `ResamplingDialog` | die einzige Rückfrage mit Cancel/Continue |
| `Badge` | das eine Abzeichen („Preview“, „Temporary“, „Overview“, „Zoom in“, „Loading…“): Pille in `--accent-2`, Großbuchstaben per CSS; `PreviewBadge` setzt sie über die Karte |

**Knopfformen** (`index.css`, vorn im Blatt):

| Form | wofür |
|---|---|
| `.btn` | Text, mit oder ohne Symbol davor (`<CogIcon lead />Process`); Standard |
| `.btn.primary` | die eine Handlung eines Formulars oder Dialogs (gefüllt, Text `--on-accent`) |
| `.btn.danger` | verwirft oder löscht (Rand und Schrift `--danger`) |
| `.icon-btn` | nur ein Symbol, quadratisch, so hoch wie ein Steuerelement; `.sm` für Listenzeilen (22 px), `.quiet` für Nebensächliches (Umbenennen, Kopieren, Feld leeren), `.off` für ein ausgeschaltetes Auge |
| `.link-btn` | in einem Satz; sonst `.btn` |
| `.close-x` | nur `CloseButton` (§5) |

- **Ein Schalter** steht mit `aria-pressed`: `.btn` ist dann getönt in Akzent, `.icon-btn` in Akzentfarbe. Die offene Seite der Leiste links trägt `.on`.
- **Eine Klasse für einen Ort** gibt Platz, Breite und Lage (`tool-btn`, `pm-icon`, `dataset-toggle`, `vc-apply`) und höchstens einen Zustand (`aria-expanded`, `.wrong`); sie erfindet keine neue Form, also keine eigene Schrift, Deckkraft oder Füllung. Ein Knopf über der Karte trägt `.panel` dazu (`.btn.panel`).
- **Auswahl aus wenigen** (Segment-Umschalter, Band-Chips, Filter): `.btn.seg` in einer Gruppe (`role="group"`), der gewählte trägt `aria-pressed` (Otto, 04.11.2026). Eigene Formen haben weiter Zeilen in Menüs und Listen, Titel zum Umbenennen und die Falzgriffe (`pp-grip`).
- **Fokus:** ein Ring für alles Bedienbare, `2px solid var(--focus)` per Tastatur (`:focus-visible`), in **einer** Regel. Kein `outline: none`, keine eigene Ringregel an einem Knopf oder Feld; Ausnahmen sind der Schieber (Ring am Griff), der Rahmen eines Popovers (kein bedientes Element) und die Ablagelinie beim Ziehen.
  - **Ein Zeichen, nur am Element** (Otto, 04.11.2026): Ein Feld, das den Fokus hat, zeigt den Ring und sonst nichts: kein Randwechsel, kein Schatten (`:focus`), kein zweiter Rand bei `:focus-visible`. Ein Abschnitt oder eine Zeile bekommt bei `:focus-within` keinen Rahmen, keinen Ring, keinen Schatten; eine Zeile darf getönt werden (Hintergrund). Ein Abschnitt hat höchstens einen Rahmen.
  - **Maus:** Ein Knopf zeigt den Ring nach einem Klick nicht (der Browser setzt `:focus-visible` nur bei Tastatur). Ein Textfeld bekommt ihn vom Browser auch beim Klick; das ist die Schreibmarke des Feldes und bleibt der eine Ring.

**Hinweise** (Teil 3b): drei Klassen für die kleinen Zeilen unter einem Feld oder Knopf, nie eine eigene:
- `.hint` ruhig (`--text-xs`, `--muted`): eine Auskunft, ein Ladezustand, eine Beschriftung wie „Area:“.
- `.hint.warn` gelb (`--accent-2`): es geht, aber mit Folgen.
- `.error` rot (`--danger`): es geht nicht, und was zu tun ist; mit `role="alert"`, wo eine Handlung nötig ist.
- Nicht mehr: `hint-text`, `pp-help`, `vc-note`. Ein falsches Feld trägt `--danger` (`--invalid` gibt es nicht mehr).
- Eine Klasse eines Ortes (`pm-note`, `pm-empty`, `place-attribution`) gibt höchstens Platz.

**Farben:** Keine Farbe als `#hex`, `rgb()`, `hsl()` oder Name außerhalb von `tokens.css`. Ausnahme: die Farben von Daten (`.legend-gradient`, gleiche Palette wie die Zellen der Coverage); jede Ausnahme steht mit Grund in `uiRules.test.ts`. Das Dunkel hinter einem Dialog ist `--scrim`. Das Attribut-Feld der Karte nimmt im dunklen Thema `--panel-bg` und `--text`.

**Steuerhöhe:** 28 px; bei Touch und unter 900 px 44 px (`--control-height-touch`).

## 8. Schrift

- Überall die System-Schrift `--font` aus `tokens.css` mit gleich breiten Ziffern.
- Monospace (`--font-mono`) nur im Band-Math-Feld.
- Eine Regel gibt allen Bedienelementen die Schrift der Seite (`button, input, select, textarea { font: inherit }`); die Karte bekommt `--font` über `.app .maplibregl-map` (MapLibre setzt eine eigene). **Keine Regel nennt eine Familie außer** `body` (`--font`), der Karte und dem Formelfeld (`--font-mono`); `font:` steht nur als `inherit`. Ein Test findet jede andere Angabe, dazu `e2e/focus-and-type.cjs` (berechnete Familie jedes sichtbaren Textes).

## 8a. Tooltips in zwei Stufen (Otto, 04.11.2026)

Jeder Tooltip hat eine Stufe; alles läuft über `TipLayer` (`frontend/src/tipLevel.ts`). **Nichts wird entfernt.**
- **Simple** (ohne Angabe): (a) der **Grund**, warum etwas gesperrt ist; (b) der **Name** eines Knopfs nur mit Symbol, der nicht selbsterklärend ist (Flip through layers, Reverse, Process, die Symbole der Leiste, „Actions“, Nach oben legen); (c) der **volle Text**, wenn ein Text wirklich abgeschnitten ist; dazu alles hinter einem (i), in beiden Stufen.
- **Advanced** (`data-tip-level="advanced"`): alle übrigen: Knöpfe mit Text, selbsterklärende Symbole (rotes x, Auge, Mülleimer, Download, Stift, Plus, Pfeile, Ziehgriff, Kopieren), Beschriftungen, Werte, Datensätze, Gruppen, Layer-Namen, Abzeichen.
- **Gesperrt ist immer simple:** `TipLayer` zeigt den Tooltip eines gesperrten Elements (`disabled`, `aria-disabled="true"`) in beiden Stufen; ein Knopf, dessen Tooltip „Grund, sonst Beschreibung“ ist, trägt also `advanced` und zeigt den Grund trotzdem.
- `aria-label` bleibt überall; die Stufe ändert nur, wann der Tooltip erscheint. **Vorgabe ist „Simple“** (Otto, 04.11.2026); der Schalter steht im Menü „Settings“, Abschnitt „Tooltips“, und wird je Browser gemerkt (`earthx.tooltips`; ein gesperrter Speicher lässt die Vorgabe und stört nichts): `setTipLevel` in `tipLevel.ts`, `setTipLevel` im Store.
- **Der volle Text eines abgeschnittenen Textes (c)** erscheint nur, wenn der Text wirklich abgeschnitten ist, **in beiden Stufen** (Otto, 04.11.2026): `data-tip-cut=""` am Element mit `data-tip`; steht der Tooltip an einem Knopf um den gekürzten Text, nennt der Wert den inneren Selektor (`data-tip-cut=".pm-title"`). `TipLayer` misst beim Zeigen und beim Fokus `scrollWidth > clientWidth` und zeigt sonst nichts. Das Attribut steht nie zusammen mit `data-tip-level`, nie ohne Wert (leer = das Element selbst) und nie an Namen, die keinen Tooltip haben dürfen (§4). Heute: Titel eines Jobs, Titel eines Stapels, Kennung einer Szene in der Liste.
- Neue Tooltips: erst fragen, ob sie (a)–(c) sind; wenn nicht, `data-tip-level="advanced"`. Die Liste der Stellen steht in `docs/plans/vp3/ui-04-einheitlichkeit.md` §8.4.

## 8b. Felder und Browser-Vorschläge

- **Jedes Feld, das Text annimmt** (Text, Suche, Zahl, Datum, Textfläche) hat `autoComplete="off"`: nichts in der Oberfläche ist eine persönliche Formulareingabe, der Browser soll keine „gespeicherten Informationen“ anbieten. Ein Bauteil, das die Eigenschaften eines `input` durchreicht (`ClearableInput`), setzt es selbst.
- Für den Rest (ein Browser, der es trotzdem tut) gibt es zwei Regeln für `:-webkit-autofill` und `:autofill`: Text `--text`, Fläche `--input-bg` über `--map-bg`, damit das Feld im dunklen Thema dunkel bleibt.

## 9. Karte und Einstellungen

- **Einstellungsmenü „Settings“** (Teil 4, Otto, 04.11.2026), `components/SettingsMenu.tsx`:
  - **Ort:** das letzte Symbol der Leiste links, am unteren Rand (MingCute „Settings 6 Line“, 20 px, Tooltip „Settings“). Es ist ein Halt der Pfeiltasten wie die anderen vier und öffnet ein Menü rechts neben der Leiste (`Popover` mit `beside`), kein Panel; Klick daneben und ein zweiter Klick auf das Symbol schließen es, Esc nicht (§5).
  - **Abschnitte:** „Basemap“ (Satellite, Streets, Grey, Outlines), „Overlays“ (Labels, Graticule, Relief), „Projection“ (Mercator, Globe), „Appearance“ (Light, Dark, System, mit `sun`, `moon`, `monitor`), „Tooltips“ (Simple, Advanced; §8a). Eine Wahl schließt das Menü nicht.
  - **Je Browser gemerkt** (`preferences.ts`, `localStorage`): `earthx.basemap`, `earthx.overlays`, `earthx.projection`, `earthx.theme`, `earthx.tooltips`. Ein gesperrter oder werfender Speicher ändert nichts am Verhalten: Vorgabe beim Laden, die Wahl gilt für den Besuch.
  - **Appearance:** Vorgabe „Dark“. Gespeichert wird `tech` (Dark), `normal` (Light) oder `system`, damit eine Wahl aus der Zeit vor „System“ gilt. „System“ folgt `prefers-color-scheme` und wechselt mit dem System, auch während die Seite offen ist.
  - **Die bisherigen Stellen entfallen:** der Knopf „Basemap“ und der Knopf Light/Dark oben rechts. Dort bleibt „Zoom to selection“. Neue Einstellungen dieser Art kommen in dieses Menü, nicht an einen eigenen Knopf.
- **Relief** gibt es nur als Overlay. Ein Browser, der die Basemap „relief“ gemerkt hat, öffnet mit der Standard-Basemap und dem Overlay Relief (der Eintrag wird einmal umgeschrieben). Ein alter Permalink mit Basemap „relief“ öffnet für diese Ansicht ebenso, ohne etwas zu speichern; das Backend nimmt `relief` weiter an, das Frontend schreibt es nicht mehr.
- **„Zoom to selection“** zoomt auf alles Gewählte zusammen (`zoomSelection.ts`):
  - Dazu gehören die AOI, die Bilder der offenen Ansicht und die Bilder der sichtbaren Layer; ein ausgeblendeter Layer und eine Ansicht mit ausgeblendetem Bild zählen nicht. Beispiel: AOI in der Schweiz und Ansicht auf Teneriffa → beide sind im Bild.
  - Über die Datumsgrenze gilt der kürzere Weg (`unionBboxShortest`): Fidschi beiderseits der Linie ist ein Kasten über 180°, nicht die Welt.
  - Ohne etwas Gewähltes ist der Knopf gesperrt und nennt den Grund: „Nothing to zoom to: draw an AOI, open an image or show a layer“.
- **Coverage unabhängig von der AOI** (Teil 4, Otto, 04.11.2026; ersetzt die Regel „mit AOI über die AOI“ aus M3-19):
  - Die Karte zeigt immer die Abdeckung über den **sichtbaren Kartenausschnitt**, bei kleinem Zoom die ganze Welt, auch wenn eine AOI gezeichnet ist. Eine AOI zu zeichnen, zu ändern oder zu löschen stellt keine neue Frage.
  - Die Anfrage ist ein `GET /coverage/{id}` mit Ausschnitt, Zeitraum und Filtern; sie trägt **keine AOI** (`api.fetchCoverage` hat keinen Weg dafür), und das Frontend benutzt `POST /coverage/{id}` nicht mehr.
  - Die Stufenregel (Stufe aus Zoom und Fenstergröße, `levelForViewport`, #286) und „dieselbe Frage nicht zweimal“ bleiben; beantwortete Ausschnitte werden auch mit AOI wiederverwendet. Filter aus „Advanced search“ wirken weiter auf die Coverage.
  - Ein Schalter „Filter within AOI only“ lässt die Filter, die von der Fläche abhängen, in der Coverage weg (sie kann sie nicht messen); die AOI ändert so höchstens die Filter, nie den Ausschnitt.
- **Die Wahl des Datensatzes unter „Coverage“** (mehrere Datensätze gewählt) enthält nur Datensätze, keinen Eintrag „Hide coverage“. Beendet wird die Karte mit dem Knopf „Hide coverage“ neben „Coverage“.

## 10. Prüfungen gegen Rückfälle

| Regel | Test |
|---|---|
| rotes x und „Close“ nur in `CloseButton`, kein „Dismiss“, kein x-Zeichen als Inhalt eines Knopfs | `frontend/src/uiRules.test.ts` |
| Esc nur in den Ausnahmen | `frontend/src/uiRules.test.ts`, dazu Esc-Tests je Panel und Dialog |
| keine Einheit an „Scale“ | `frontend/src/uiRules.test.ts`, `ProcessingPreview.test.tsx` |
| Begriffe (§2) gegen alle Texte der Oberfläche | `frontend/src/uiRules.test.ts` |
| Sperrgrund im Tooltip | `frontend/src/fixtures/lockedControls.ts`, benutzt in `ControlPanel.test.tsx` und `LayerManager.test.tsx` |
| Klick neben einen Dialog schließt nicht | `DownloadDialog.bands.test.tsx` |
| Tokens statt fester Werte | `frontend/src/tokens.test.ts` (Abstände, Schriftgrade, Radien: `.btn`, `.icon-btn`, `.hint`, `.error`, `.badge`, Seitenleiste, Processing; die übrigen Klassen folgen in Teil 6, Otto 04.11.2026) |
| kein `title` an einem Element außer `<option>`, ein Tooltip-Weg, Beschreibung per `aria-describedby`, gesperrter Knopf zeigt seinen Grund | `frontend/src/uiRules.test.ts`, `frontend/src/components/TipLayer.test.tsx`, `frontend/e2e/tooltips.cjs` |
| keine alten Knopfklassen (`ghost-btn`, `primary-btn`, `lm-btn` …) | `frontend/src/uiRules.test.ts` |
| keine feste Deckkraft an einem gesperrten Element | `frontend/src/uiRules.test.ts` |
| ein Fokusring, kein `outline` an einem Knopf oder Feld | `frontend/src/uiRules.test.ts` |
| ein Auge (`EyeButton`), nur in Textfarbe, verborgen = durchgestrichen | `frontend/src/uiRules.test.ts`, `frontend/src/components/EyeButton.test.tsx` |
| kein Tooltip an Datensatz, Gruppenkopf, Layer-Name (außer Grund, Hinweis, Eintrag „Search results“) | `frontend/src/uiRules.test.ts` |
| Symbole der Leiste 20 px, Token und Zahlen gleich | `frontend/src/AppRail.test.tsx`, `frontend/src/components/icons.test.tsx` |
| Symbole nur aus `icons.ts`, keine Textzeichen als Symbol (Code und CSS), kein eigenes `<svg>`, Strich und Größen, jedes Symbol benutzt | `frontend/src/uiRules.test.ts`, `frontend/src/components/icons.test.tsx` |
| Schrift: eine Familie, `font: inherit` an Bedienelementen | `frontend/src/uiRules.test.ts`, `frontend/e2e/focus-and-type.cjs` |
| keine feste Farbe außerhalb von `tokens.css` (Ausnahme: Farben von Daten) | `frontend/src/uiRules.test.ts` |
| keine alten Klassen (`hint-text`, `pp-help`, `pp-badge`, `pp-seg`, …), ein Abzeichen (`Badge`), keine Regel für eine Klasse, die niemand nennt | `frontend/src/uiRules.test.ts` |
| Fokus: ein Zeichen am Element, nichts am Abschnitt | `frontend/src/uiRules.test.ts`, `frontend/e2e/focus-and-type.cjs` |
| Tooltips: nur die Stufe „advanced“, nie an (i), Namen nicht selbsterklärender Symbole; gesperrt zeigt den Grund | `frontend/src/uiRules.test.ts`, `frontend/src/tipLevel.test.ts`, `frontend/src/components/TipLayer.test.tsx` |
| `autocomplete="off"` an jedem Textfeld, Regeln für ein ausgefülltes Feld | `frontend/src/uiRules.test.ts`, `frontend/e2e/focus-and-type.cjs` |
| Einstellungen in einem Menü: kein Knopf „Basemap“, kein Theme-Knopf, Relief nur als Overlay, das Symbol unten in der Leiste; Menü, Merken je Browser, gesperrter Speicher | `frontend/src/uiRules.test.ts`, `frontend/src/components/SettingsMenu.test.tsx`, `frontend/src/preferences.test.ts`, `frontend/e2e/settings-menu.cjs` |
| das eine Symbol aus MingCute: Herkunft, Änderung und Lizenztext vermerkt | `frontend/src/components/icons.test.tsx` |
| Tooltip mit vollem Text nur bei gemessener Kürzung, in beiden Stufen; `data-tip-cut` nur mit `data-tip`, ohne Stufe, mit Wert | `frontend/src/uiRules.test.ts`, `frontend/src/tipLevel.test.ts`, `frontend/src/components/TipLayer.test.tsx`, `frontend/e2e/settings-menu.cjs` |
| „Zoom to selection“ über AOI, Ansicht und sichtbare Layer, der kürzere Weg über die Datumsgrenze, gesperrt mit Grund | `frontend/src/zoomSelection.test.ts`, `frontend/src/geoUtils.test.ts`, `frontend/src/AppTopBar.test.tsx` |
| Coverage ohne AOI: keine AOI in der Anfrage, kein POST, derselbe Ausschnitt mit und ohne AOI | `frontend/src/store.coverage.test.ts`, `frontend/src/api.test.ts`, `frontend/e2e/no-aoi-in-url.cjs` |
| kein Eintrag „Hide coverage“ in der Wahl des Datensatzes | `frontend/src/components/ControlPanel.test.tsx` |

Ein neuer Begriff, der ein altes Wort ersetzt, bekommt eine Zeile in der Liste `FORBIDDEN` von `uiRules.test.ts` mit Gegenprobe.
