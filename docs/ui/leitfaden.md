# EarthX — Leitfaden der Oberfläche

**Stand:** 11.11.2026, Ganzzahl-Ergebnisse und Tooltips im Layer-Manager (Browserprüfung Otto), davor am selben Tag Kompass, Zoom und 3D an der Karte (UI-06, `docs/plans/vp3/ui-06-3d-und-nordpfeil.md` §9a, §10), davor 07.11.2026, Seiten der Datensätze ohne Obergrenze (Otto, Review von UI-05 Teil 2), davor 06.11.2026 UI-05 Teil 2 (Data catalogue als Fenster, Datensätze in „Search and area“ aus dem Katalog), davor UI-05 Teil 1 (Seiten der Datensätze, „Advanced search“ immer da, Datum im Zeitraum der Datensätze, kein Zusatztext im Panel; `docs/plans/vp3/ui-05-data-catalogue.md`), davor UI-04 Teil 6 (Zahlenformat, weniger Text, schmale Fenster, Tokens für alle Maße) (`docs/plans/vp3/ui-04-einheitlichkeit.md` §7, §8). Grundlage sind die Regeln und Begriffe aus UI-03 (#277–#283), NM4-75 (#284, `adr/0028`) und die Antworten Ottos zu UI-04 (§7.0, §7.9).

**Gilt für:** jede Änderung an `frontend/`. Künftige Pläne verweisen auf diese Datei. Neue Begriffe, Bauteile oder Symbole kommen zuerst hierher.

**Markierung:** Steht an einer Regel *(folgt in Teil n)*, ist sie entschieden, aber noch nicht überall umgesetzt. Nach UI-06 gibt es keine Regel mit dieser Markierung.

## 1. Grundsätze

1. **Gleiches sieht gleich aus:** Ähnliche Bedienelemente nutzen dasselbe Bauteil und die Tokens aus `frontend/src/tokens.css`. Feste Farben, Abstände, Schriftgrade und Radien gibt es nur dort, in **jeder** Regel von `index.css` (§7).
2. **Gleiches heißt gleich:** ein Begriff je Sache (§2), in Knopftext, Überschrift, Tooltip, `aria-label` und Fehlermeldung.
3. **Gleiches bedient sich gleich:** ein Weg zum Schließen (§5), ein Weg zum Übernehmen und Speichern (§6), eine Sperrregel (§4), ein Symbol je Aktion (§3).
4. **Wenig Text:** Sichtbar sind Beschriftungen, Werte, Fehler, die eine Handlung verlangen, und Pflichtangaben (Attribution, Lizenz). Erklärungen stehen im Tooltip oder hinter einem (i) neben der Zeile, die sie erklären (§4); der Grund eines gesperrten Knopfs steht in seinem Tooltip, nie als Absatz darunter.
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
| page / Previous page / Next page | eine Seite der Datensätze in „Search and area“ (UI-05), Zähler „1 / 3“ zwischen `chevron-left` und `chevron-right`, klein rechts neben der Überschrift „Datasets“ | „1/3“ ohne Leerzeichen |
| layer | ein Eintrag im Layer-Manager | |
| Add to layers / Add all to layers / Add current view to layers / Add preview to layers | etwas als Layer anheften; der Tooltip sagt „Add … to the layers“ | „Pin …“ |
| Search results | die Ergebnisse der Suche: Leiste, Kopf der Liste, Zeile im Layer-Manager | „Results“ |
| Jobs | der Processing-Manager | „Processing jobs“ |
| job / batch / order / recipe | Auftrag am Server / mehrere Jobs eines Auftrags / was im Processing-Panel eingestellt ist / die Datei `recipe.json` | |
| Close | schließt Fenster, Leiste, Dialog, Meldung; nur das rote x (§5) | „Dismiss“ |
| Cancel | verwirft eine Rückfrage oder bricht einen Job ab | |
| Stop | hält einen laufenden Vorgang an; was fertig ist, bleibt („Stop checking. What is found stays.“, laufender Download) | „Cancel“ für einen Download |
| Remove | nimmt etwas aus einer Liste der Oberfläche (Layer, Schritt, Gruppe, Datensatz aus „Search and area“ im Data catalogue) | |
| Data catalogue / Add | das Fenster mit allen Datensätzen (UI-05) und sein Symbol in der Leiste; „Add“ nimmt einen Datensatz in „Search and area“ auf, ohne ihn zu wählen; „Source“ statt „Add“ bei einem Datensatz, der ein Konto braucht; Marken „Prototype“, „Account“ | |
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
| Evaluate: per pass / per scene | Segment-Knöpfe oben in „Advanced search“, **Vorgabe per pass** (DS-03c): ob jeder Filter über die zusammengeführten Szenen eines Überflugs oder je Szene beurteilt wird; was beides heißt, mit Beispiel, steht hinter einem (i); die Einstellungen von „Advanced search“ bleiben für die Sitzung stehen wie die Datumseinstellungen, nicht dauerhaft | „by pass“, „Group“ |
| AOI coverage | **der erste Filter** in „Advanced search“, für alle Datensätze; der Filter „mindestens n % der AOI von den Umrissen der Szenen gedeckt“ (Schieber und Zahl, gesperrt ohne AOI); misst Umrisse, nicht gültige Pixel (DS-03c) | „Coverage“ (so heißt die Karte), „Overlap“ |
| Copy original scene name | kopiert die Kennungen der Szenen in die Zwischenablage | |
| Download crop / Download full scene(s) / Download | Zuschnitt der AOI / ganze Szenen / ein Layer; die Formen heißen „One file per band“, „One file per resolution“, „One multi-band file“ (NM4-75) | |
| — none — / — choose — | kein Wert, auch die gesperrte Colormap bei RGB / Pflichtwahl ohne Vorgabe | „–“ |
| Choose | auswählen, im Text | „Pick“ |
| finished | Status eines Jobs („Finished“); in Zusammenfassungen klein („3 finished · 1 running“) | „done“ |
| Settings | das Panel der Einstellungen, das Symbol unten in der Leiste links (§9); die Seitenleiste heißt für Screenreader nach ihrem Inhalt („Image settings“, „Layer settings“) | |
| Basemap, Overlays, Projection, Appearance, Tooltips | die fünf Abschnitte des Panels „Settings“; Wahl je Abschnitt: Satellite / Streets / Grey / Outlines, Labels / Graticule / Relief, Mercator / Globe, Light / Dark / System, Simple / Advanced | „Theme“, „Mode“ für Light/Dark |
| Compass, Reset north and tilt, Zoom in, Zoom out, 3D | die Knöpfe unten rechts an der Karte, von oben nach unten (§9); der Kompass heißt im Tooltip und `aria-label` „Reset north and tilt“, der Knopf „3D“ schaltet das Gelände | „North“, „Terrain“ als Knopftext, „Tilt“ allein |
| Coverage, Hide coverage | die Abdeckung des gewählten Datensatzes über den sichtbaren Kartenausschnitt (§9); sie wird mit „Coverage“ gewählt und mit „Hide coverage“ beendet | „Clear coverage“, ein Eintrag „Hide coverage“ in der Wahl des Datensatzes |

**Schreibweise:**
- **Satzanfang-Stil** für Knopftexte, Überschriften und Tooltips („Add to layers“, „Auto-scale“). Großbuchstaben bei Abschnittsköpfen nur per CSS.
- Abkürzungen groß: AOI, CRS, RGB, UTM, auch in Feldnamen aus dem Schema des Servers (`fieldTitle` in `schemaForm.ts`).
- **Ellipse** „…“, nie „...“; nur an Knöpfen, die noch etwas fragen („Load recipe…“, „Move to group…“), und in Ladezuständen („Loading…“).
- Eine **Zahl mit Nomen** steht in Einzahl oder Mehrzahl nach der Anzahl („1 scene“, „3 scenes“; `counted` in `plural.ts`), nie „scene(s)“.
- Kein „&“, sondern „and“. Trenner „·“, Bereich „–“, Bruch der Zeitleiste „4 / 7“.
- **Tooltips:** ein Satzteil ohne Schlusspunkt; ganze Sätze mit Punkt.
- Anführungszeichen typografisch („ “ als “ ”).
- **Zahlen** (NM4-21, Teil 6): eine Funktion, `formatNumber` in `frontend/src/numberFormat.ts`; nur dort wird eine Zahl für das Auge gerundet oder ein Datum geschrieben (`toFixed`, `toPrecision`, `toLocale…`, `Intl` sonst nirgends).
  - **Höchstens drei Nachkommastellen**, ohne nachgestellte Nullen: 12.3456 → „12.346“, 2.5 → „2.5“.
  - **Sehr kleine und sehr große Beträge wissenschaftlich**, mit höchstens drei gültigen Stellen und ohne „+“: unter 0.001 (außer 0) und ab 1e6, also 0.000000052 → „5.2e-8“, 1234567 → „1.23e6“. Das Minus ist der einfache Bindestrich, damit ein gezeigter Wert wieder in ein Feld getippt werden kann.
  - **Nicht-Zahlen:** `NaN` ist „—“, unendlich „∞“ und „-∞“.
  - **Einheit mit Leerzeichen, Prozent und Grad ohne:** „4.2 MB“, „12 s“, „10 m“, aber „50%“, „2–98%“, „52.5° N“. Dateigrößen in kB ganz, in MB und GB mit höchstens einer Stelle; „1 unit“, „2.5 units“ nach der Zahl.
  - **Felder:** Die Startwerte eines Bereichs aus der Statistik gehen durch `fieldNumber` (dieselbe Rundung, leer für eine Nicht-Zahl). **Was der Nutzer tippt, gilt genau so** und wird nie umgeschrieben. Ein Regler schreibt ebenso höchstens drei Stellen; auf einer Skala schmaler als 1 hat er darum weniger als tausend Schritte.
  - **Unberührt (volle Genauigkeit):** Werte in `recipe.json`, API, Permalink, Dateinamen und `BANDS.txt` (`formatResolution`, `formatG` in `bandChoice.ts`), Kennungen, Koordinaten, Zählungen. Die Zeile der Zellgröße gibt die getippte Auflösung als Ziffern ohne Exponent zurück (`formatPlain`: 0.0000001 bleibt 0.0000001), die Meter am Boden laufen durch `formatNumber`.
- **Daten:** „31 Oct, 14:02“ (`formatMoment`; das Jahr nur, wenn es nicht das laufende ist: „5 Jan 2027, 14:02“), überall gleich, in der Zeile eines Jobs wie in den Details; ein Tag als „2026-12-03“ (`formatDay`, unabhängig von der Sprache des Browsers). Kein Monatskürzel in Großbuchstaben („08OCT-12:34“) und kein `toLocaleDateString`.
- **Keine Einheit an „Scale“** (vmin/vmax), an keiner Stelle: Seitenleiste, Layer, Ergebnis-Layer, Processing-Vorschau (Otto, 03.11.2026). Die Einheiten der Daten stehen in `BANDS.txt` und in den Metadaten; an den Band-Chips des Processing-Panels bleibt die Einheit („· dB“).

## 3. Symbole

- **Eine Quelle:** Lucide (`lucide-react`, ISC; die Symbole aus Feather unter MIT, Hinweise in `frontend/THIRD_PARTY_NOTICES.md`). Importiert werden nur die benutzten Symbole, alle in einer Datei: `frontend/src/components/icons.ts`. Sie gibt jedes unter eigenem Namen weiter (`DownloadIcon`); nur sie importiert `lucide-react`, und jeder Eintrag muss benutzt sein.
- **Ein Strich:** 1.5 px, an jeder Größe gleich dick (`absoluteStrokeWidth`). Drei Größen, als Token in `tokens.css` und als Zahlen in `components/iconSizes.ts` (ein Test hält beide zusammen): 16 px als Standard (`--icon-size`, `<DownloadIcon />`), 14 px in Listenzeilen (`--icon-size-sm`, `<DownloadIcon size={14} />`) und 20 px für die Symbole der Leiste links (`--icon-size-rail`, `size={ICON_SIZES.rail}`; Otto, 04.11.2026). Farbe `currentColor`.
- **Neben einem Text** steht das Symbol davor und bekommt `lead`: `<CogIcon lead />Process`. Der Abstand kommt aus dem CSS (`.icon-lead`), kein Leerzeichen im Text.
- **Ein Knopf nur mit Symbol** hat einen Namen für Screenreader (`aria-label`) und einen Tooltip. Gleiche Aktion, gleiches Symbol, auch wenn Text dabeisteht oder nicht.
- **Eigene Zeichnungen gibt es nicht.** Das einzige `<svg>` im Code ist das Balkendiagramm des Histogramms (`RangeHistogram`), kein Symbol.
- **Der Haken** vor dem gewählten Eintrag eines Menüs ist ein Symbol in einem Platz fester Breite (`MenuTick`), kein Zeichen im CSS.
- **Einzige Ausnahme:** Settings ist „Settings 6 Line“ von MingCute (Apache-2.0, `mingcute_icon` 2.9.72, `svg/system/settings_6_line.svg`). Es wird als einzelnes SVG übernommen, als Strich nachgezeichnet und an Lucide angeglichen; die Änderung ist vermerkt. Herkunft, Änderung und Lizenztext stehen in `frontend/THIRD_PARTY_NOTICES.md`, die Zeichnung (mit dem Vermerk der Änderung, Apache-2.0 §4(b)) in `components/settingsIconNode.ts`; `icons.ts` gibt sie als `SettingsIcon` weiter, wie alle anderen.
- **Zweite Ausnahme: die Nadel des Kompasses** (Otto, 11.11.2026, UI-06 F3 und F17): eine Nadel aus zwei Spitzen wie bei Google Maps, Nordhälfte `--danger`, Südhälfte `--text`, als eigene Zeichnung in `components/CompassNeedle.tsx`, weil Lucide keine Nadel mit roter Nordhälfte hat. Sie ist neben dem Balkendiagramm (`RangeHistogram`) das einzige weitere `<svg>`; sie dreht sich mit der Karte.
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
| Leiste | `search`, `library` (Data catalogue), `layers`, `clipboard-list`, `list` |
| Coverage | `layout-grid` |
| Zoom in / Zoom out | `plus` / `minus` |
| Kompass (Reset north and tilt) | eigene Nadel (`CompassNeedle.tsx`), siehe oben |
| 3D | kein Symbol, der Text „3D“ |
| Erscheinungsbild (Light / Dark / System) | `sun`, `moon`, `monitor` |

## 4. Sperren

- Was gerade nicht geht, ist **gesperrt** (`disabled` oder `aria-disabled="true"`) und nennt den **Grund im Tooltip**. Der Grund wiederholt nicht den Knopftext. Beispiele: „Type a place name first“, „No earlier AOI in this browser“, „Already at the top“, „Job deleted: restore it first“, „Already on the first page“, „Choose a dataset to see its filters“; die gesperrten Datumsfelder nennen den Zeitraum des Datensatzes ohne Zeitachse („No time axis – acquired Dec 2010 to Jan 2015“).
- **Ein Aussehen:** ein gesperrtes Element ist auf `--disabled-opacity` (0.4) gedimmt, in einer Regel für `:disabled` und `[aria-disabled='true']`. Keine eigene Deckkraft an einem gesperrten Element.
- **`aria-disabled` für neue Sperren mit Grund:** das Element bleibt in der Tab-Reihenfolge, der Grund ist auch per Tastatur lesbar; der Handler fängt den Klick ab. Ein bestehendes `disabled` bleibt; sein Tooltip erscheint, wo der Zeiger darüber liegt (`TipLayer`), per Tastatur nicht.
- **Bekannte Grenze (Otto, 04.11.2026):** Der Grund eines `disabled`-Knopfs ist per Tastatur und Screenreader nicht lesbar; ein `disabled`-Element nimmt keinen Fokus. Die Umstellung aller gesperrten Knöpfe auf `aria-disabled` ist ein Punkt für M6 (Barrierefreiheit).
- Wo eine gesperrte Stelle einen Platz hält, bleibt sie an diesem Platz, z. B. die Colormap bei RGB als gesperrtes „— none —“, auch in der Processing-Vorschau.
- **Weniger Text, Erklärungen hinter (i)** (NM4-22, Teil 6): Sichtbar bleiben Beschriftungen, Werte, Fehler, die eine Handlung verlangen, ein Leerzustand, der sagt, was zu tun ist („No layers yet — …“), und Pflichtangaben. Eine **Erklärung** (wie etwas läuft, warum, was ein Wort heißt) ist ein `Tip` (das (i), `tone="warn"` für eine Warnung) **neben der Zeile, die sie erklärt**: „An estimate, not a promise.“ hinter der Schätzung, die Regel der Warteschlange dahinter, „One job covers the scenes of one pass“ hinter „Pass“, die Verschmelzung der Szenen hinter der Auswahl, der Hinweis zu überlappenden Szenen hinter „Preview on the map“, das Zusammenführen im Download-Dialog hinter „Start job“. Der **Grund eines gesperrten Knopfs** steht im Tooltip des Knopfs („Choose a dataset to search“), nicht in einem Absatz darunter. Ein Fehler, der etwas zu korrigieren verlangt („Correct the filters in Advanced search.“), bleibt sichtbar. Ein Test findet die verschobenen Texte als Absatz und jeden neuen Hinweis aus einem langen festen Satz.
- **Ein Tooltip-Weg:** `TipLayer` über `data-tip`. Er erscheint bei Zeiger und Fokus; `TipLayer` setzt für die Dauer `aria-describedby`, bei einem `label` mit Tooltip am Feld darin; ein Knopf nur mit Symbol hat zusätzlich seinen `aria-label`. **Keine Tooltips an Namen** (Otto, 04.11.2026): nicht an Datensätzen (Auswahl im Control-Menü, Dropdowns in der Suche, in der Liste und in der Ansicht), nicht an Gruppenköpfen, nicht an den Namen von Layern und dem Titel der Ansicht. Ausnahmen: ein Datensatz, der gerade nicht wählbar ist, nennt weiter den Grund („… — not viewable: …“); der Hinweis eines Layers (`note`, etwa bei einer Vorschau je Szene) und die Erklärung des Eintrags „Search results“ im Layer-Manager. Ein langer Name wird gekürzt, nicht erklärt.
- **Layer-Manager, Zeilen gleich behandelt** (Otto, 11.11.2026): Zeilen eines Datensatzes, eines Ergebnisses und „Search results“ geben denselben Bedienelementen dieselbe Stufe und denselben Wortlaut. Ein gelöschter Job (wiederherstellbar bis Tagesende) sperrt alles seiner Zeile mit **einem** Grund „Job deleted: restore it first“: Auge, Umbenennen, Deckkraft, Band, ＋, Download; ein abgelaufenes Ergebnis blendet Download und ＋ aus (Regel Otto, 26.10.2026: was grundsätzlich nicht mehr geht, fehlt) und sperrt das Band mit „Expired: start the job again“. „Process“ heißt für jeden Layer „Process layer“ (Tooltip und `aria-label`), bei einem abgelaufenen Ergebnis „Process layer: the result has expired, so the job runs again from the scenes“.
- **„Auto-scale“ ist nie gesperrt** (Otto, 11.11.2026), in der Processing-Vorschau so wenig wie in Ansicht und Ergebnis-Layer: ein Bauteil (`AutoScaleButton`); ist der gemessene Bereich schon gezeichnet, misst es neu bzw. setzt ihn zurück. Vorher war es in der Vorschau ohne Grund gesperrt, solange der gemessene Bereich galt, auch während ein Job lief und danach. „Add current view to layers“ eines gelöschten Jobs nennt in der Seitenleiste den Grund „Job deleted: restore it first“.
- **Gesperrtes Feld in einem `label` mit Tooltip:** das Label ist nicht gesperrt, `TipLayer` kann den Grund dort nicht als (a) erkennen; das Label trägt den Tooltip darum ohne Stufe, solange das Feld gesperrt ist (`BandSelect`).
- **`title` gibt es an keinem Element** (ein zweiter Tooltip des Browsers), außer an `<option>` (eine native Liste zeigt sonst nichts) und an den Steuerelementen von MapLibre. Ein Test findet jedes andere `title`.

## 5. Schließen

- **Linke Panels: ein- und ausschalten über das Symbol, kein x** (Otto, 04.11.2026). Search and area, Layers, Jobs, Search results und Settings öffnen und schließen nur mit ihrem Symbol in der Leiste (ein zweiter Klick schließt); ihr Kopf hat den Titel und kein x. Das rote x bleibt für die **Seitenleiste rechts, Dialoge, Fenster, Blätter (Popover-Formulare, Processing-Panel) und Meldungen**.
- **Fenster** (Otto, 06.11.2026, UI-05): ein größeres Fenster über der Karte, das ein Symbol der Leiste links öffnet, heute nur der „Data catalogue“. Es schließt mit dem roten x in seinem Kopf **oder** einem zweiten Klick auf sein Symbol (wie die linken Panels); Esc schließt nichts; ein Klick daneben schließt es nicht (wie bei Dialogen).
- **Ein Weg:** das kleine rote x aus `CloseButton.tsx` (Tooltip „Close“, ein längerer Tooltip, wo das Schließen eine Folge hat). Das gilt auch für Meldungen der Statusleiste.
- **Esc schließt nichts:** keine Ansicht, Seitenleiste, kein Panel, Blatt, Menü, keine Liste und keinen Tooltip. Ausnahmen:
  - Esc = „Cancel“ in Bestätigungsdialogen („Values are resampled“);
  - Esc beendet „Flip through layers“;
  - Esc bricht das Umbenennen und das Ziehen einer Zeile ab (schließt nichts).
- **Klick daneben:**
  - Dialoge und Fenster schließen nicht; sonst ginge z. B. ein laufender Download verloren. Ausnahme: die Rückfrage „Values are resampled“ (Klick daneben = Cancel).
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
| `SettingsPanel` | das Panel „Settings“ (§9), geöffnet vom letzten Symbol der Leiste (`AppRail`) |
| `Popover` | Menüs, Listen und das Formular „Advanced search“ |
| `ResamplingDialog` | die einzige Rückfrage mit Cancel/Continue |
| Fenster (`DataCatalogue`) | größeres Fenster über der Karte, geöffnet und geschlossen über sein Symbol in der Leiste, dazu das rote x im Kopf (§5); der Kopf ist ein eigener Bereich, in den später Suchfeld und AOI-Schalter kommen, ohne sichtbar leere Fläche, solange sie fehlen |
| `MapControls` | die Gruppe unten rechts an der Karte: Kompass, Zoom +, Zoom −, 3D (§9); ersetzt `NavigationControl` von MapLibre |
| `Badge` | das eine Abzeichen („Preview“, „Temporary“, „Overview“, „Loading…“): Pille in `--accent-2`, Großbuchstaben per CSS; `PreviewBadge` setzt sie über die Karte. Hinweise eines Datensatzes (`earthx:notices`, etwa „Approximate geolocation“) sind keine Marke, nirgends; was die Daten nicht können, steht als Sätze in der Zeile „Limitations“ der Angaben im Data catalogue (Otto, 10.11.2026, `adr/0018` F2, Nachtrag DS-04c). Texte für Nutzer nennen keine internen Dokumente (`adr/…`, `§…`) |

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
- **Auswahl aus wenigen** (Segment-Umschalter, Band-Chips, Filter, Basemap, Projection, Appearance): `.btn.seg` in einer Gruppe (`role="group"`), der gewählte trägt `aria-pressed` und ist **gefüllt** (Akzent, Text `--on-accent`; Otto, 04.11.2026). Etwas, das neben anderem an sein kann (ein Overlay), ist ein Knopf derselben Form, der gedrückt ist, solange es an ist (`aria-pressed`). Keine Häkchen-Liste in einem Panel.
- **Schalter** (`role="switch"`): **nur für etwas, das an oder aus ist** (Otto, 04.11.2026). Eine Wahl unter mehreren ist nie ein Schalter, sondern Segment-Knöpfe, auch zwei Stufen wie „Simple“ / „Advanced“ (zwei Boxen). Heute gibt es genau einen: „Filter within AOI only“ in „Advanced search“ (bleibt, Otto 04.11.2026); ein eigenes Bauteil dafür gibt es nicht. „Evaluate“ in „Advanced search“ (per pass / per scene) ist eine Wahl unter zwei und darum Segment-Knöpfe (DS-03c).
- **Der Haken** (`MenuTick`) steht nur in Menüs und Listen mit Wahl (Gruppe eines Jobs), nie in einem Panel. Eigene Formen haben weiter Zeilen in Menüs und Listen, Titel zum Umbenennen und die Falzgriffe (`pp-grip`).
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

**Abstände, Schriftgrade und Radien** (Teil 6, Otto, 04.11.2026): **jede** Regel von `index.css` nimmt Tokens aus `tokens.css`, keine Regel mehr eine Länge in `px` oder `rem` für `padding`, `margin`, `gap`, `font-size` und `border-radius` (`0` und `%` sind keine Länge). Die Stufen:

| Bereich | Tokens |
|---|---|
| Abstand | `--space-0` 2, `--space-1` 4, `--space-1-5` 6, `--space-2` 8, `--space-3` 12, `--space-4` 16, `--space-5` 24, `--space-6` 32 px |
| Schrift | `--text-2xs` 10, `--text-xs` 11, `--text-sm` 12, `--text-md` 13, `--text-lg` 15, `--text-xl` 17 px |
| Radius | `--radius-xs` 4, `--radius-sm` 6, `--radius-md` 10 px, `--radius-full` Pille |

- Ein Wert dazwischen gibt es nicht; wer einen braucht, nimmt die nächste Stufe (bei Gleichstand die größere: 10 → `--space-3`, 14 → `--space-4`, 8 Radius → `--radius-md`) oder rechnet mit einem Token (`calc(var(--control-height) + var(--space-1))`, z. B. der Platz für den Knopf in einem Feld). **Eine neue Stufe kommt zuerst nach `tokens.css`** und in die Liste in `tokens.test.ts`.
- Ein Feld für eine Zahl behält `--number-field-width` (88 px: „-0.123456“ mit Rand), auch im schmalsten Fenster, **überall, wo dasselbe Feld vorkommt** (Otto, 04.11.2026): Seitenleiste (Ansicht, Layer, Ergebnis-Layer) und Vorschau im Processing-Panel, auch in den Kanalzeilen eines Farbbilds; was daneben steht (die Einheit des Bereichs), gibt nach. In der Seitenleiste steht dazu der Name „Scale“ über den Feldern (nicht in einer Spalte links), damit sie die Breite der Leiste haben. Der Download-Dialog hat kein solches Feld; ein neues Zahlenfeld nimmt dieselbe Regel.
- **Test:** `tokens.test.ts` prüft **alle** Regeln (`hardValues` mit `ALL_RULES`), nicht mehr nur eine Liste von Bereichen. Ausnahmen gibt es nicht; ein Maß wie `width`, `height` oder `top` ist kein Abstand und bleibt frei.

**Steuerhöhe:** 28 px; bei Touch und unter 900 px 44 px (`--control-height-touch`).

## 8. Schrift

- Überall die System-Schrift `--font` aus `tokens.css` mit gleich breiten Ziffern.
- Monospace (`--font-mono`) nur im Band-Math-Feld.
- Eine Regel gibt allen Bedienelementen die Schrift der Seite (`button, input, select, textarea { font: inherit }`); die Karte bekommt `--font` über `.app .maplibregl-map` (MapLibre setzt eine eigene). **Keine Regel nennt eine Familie außer** `body` (`--font`), der Karte und dem Formelfeld (`--font-mono`); `font:` steht nur als `inherit`. Ein Test findet jede andere Angabe, dazu `e2e/focus-and-type.cjs` (berechnete Familie jedes sichtbaren Textes).

## 8a. Tooltips in zwei Stufen (Otto, 04.11.2026)

Jeder Tooltip hat eine Stufe; alles läuft über `TipLayer` (ein gezeigter Tooltip geht mit dem Zeiger oder dem Fokus und mit einem Wechsel der Stufe, auch wenn die neue Stufe ihn nicht mehr zeigen würde) (`frontend/src/tipLevel.ts`). **Nichts wird entfernt.**
- **Simple** (ohne Angabe): (a) der **Grund**, warum etwas gesperrt ist; (b) der **Name** eines Knopfs nur mit Symbol, der nicht selbsterklärend ist (Flip through layers, Reverse, Process, die Symbole der Leiste, „Actions“, Nach oben legen); (c) der **volle Text**, wenn ein Text wirklich abgeschnitten ist; dazu alles hinter einem (i), in beiden Stufen.
- **Advanced** (`data-tip-level="advanced"`): alle übrigen: Knöpfe mit Text, selbsterklärende Symbole (rotes x, Auge, Mülleimer, Download, Stift, Plus, Pfeile, Ziehgriff, Kopieren), Beschriftungen, Werte, Datensätze, Gruppen, Layer-Namen, Abzeichen.
- **Gesperrt ist immer simple:** `TipLayer` zeigt den Tooltip eines gesperrten Elements (`disabled`, `aria-disabled="true"`) in beiden Stufen; ein Knopf, dessen Tooltip „Grund, sonst Beschreibung“ ist, trägt also `advanced` und zeigt den Grund trotzdem.
- `aria-label` bleibt überall; die Stufe ändert nur, wann der Tooltip erscheint. **Vorgabe ist „Simple“** (Otto, 04.11.2026); die Wahl („Simple“ und „Advanced“ als zwei Boxen, Vorgabe „Simple“) steht im Panel „Settings“, Abschnitt „Tooltips“, und wird je Browser gemerkt (`earthx.tooltips`; ein gesperrter Speicher lässt die Vorgabe und stört nichts): `setTipLevel` in `tipLevel.ts`, `setTipLevel` im Store.
- **Der volle Text eines abgeschnittenen Textes (c)** erscheint nur, wenn der Text wirklich abgeschnitten ist, **in beiden Stufen** (Otto, 04.11.2026): `data-tip-cut=""` am Element mit `data-tip`; steht der Tooltip an einem Knopf um den gekürzten Text, nennt der Wert den inneren Selektor (`data-tip-cut=".pm-title"`). `TipLayer` misst beim Zeigen und beim Fokus `scrollWidth > clientWidth` und zeigt sonst nichts. Das Attribut steht nie zusammen mit `data-tip-level`, nie ohne Wert (leer = das Element selbst) und nie an Namen, die keinen Tooltip haben dürfen (§4). Heute: Titel eines Jobs, Titel eines Stapels, Kennung einer Szene in der Liste.
- Neue Tooltips: erst fragen, ob sie (a)–(c) sind; wenn nicht, `data-tip-level="advanced"`. Die Liste der Stellen steht in `docs/plans/vp3/ui-04-einheitlichkeit.md` §8.4.

## 8b. Felder und Browser-Vorschläge

- **Jedes Feld, das Text annimmt** (Text, Suche, Zahl, Datum, Textfläche) hat `autoComplete="off"`: nichts in der Oberfläche ist eine persönliche Formulareingabe, der Browser soll keine „gespeicherten Informationen“ anbieten. Ein Bauteil, das die Eigenschaften eines `input` durchreicht (`ClearableInput`), setzt es selbst.
- Für den Rest (ein Browser, der es trotzdem tut) gibt es zwei Regeln für `:-webkit-autofill` und `:autofill`: Text `--text`, Fläche `--input-bg` über `--map-bg`, damit das Feld im dunklen Thema dunkel bleibt.

## 9. Karte und Einstellungen

- **Panel „Settings“** (Teil 4, Otto, 04.11.2026; erst ein Menü, am selben Tag auf Ottos Zusatz ein Panel), `components/SettingsPanel.tsx`:
  - **Ort:** das letzte Symbol der Leiste links, am unteren Rand (MingCute „Settings 6 Line“, 20 px, Tooltip „Settings“), ein Halt der Pfeiltasten wie die anderen vier. Es öffnet ein **Panel in der Leiste wie die übrigen** (`dock-slot` im `.dock`): dieselbe Breite (340 px, unter 900 px über der Karte von der Leiste bis zum rechten Rand), derselbe Kopf (`.results-head`: nur der Titel „Settings“, **kein x**, wie bei den anderen linken Panels, §5). Es öffnet und schließt mit dem Symbol, **Esc schließt nichts**. Eine Wahl schließt es nicht.
  - **Abschnitte** (Überschrift in Großbuchstaben per CSS): „Basemap“ (Satellite, Streets, Grey, Outlines), „Overlays“ (Labels, Graticule, Relief), „Projection“ (Mercator, Globe), „Appearance“ (Light, Dark, System, mit `sun`, `moon`, `monitor`), „Tooltips“ (die Boxen „Simple“ und „Advanced“; §8a).
  - **Bedienformen:** Basemap, Projection und Appearance sind Segment-Knöpfe (`.btn.seg`, der gewählte gefüllt), jedes Overlay ein Knopf derselben Form, gedrückt = an, „Simple“ und „Advanced“ zwei Boxen. **Alle Boxen des Panels haben dieselbe Größe** (Otto, 04.11.2026): jede Reihe ein Raster aus vier gleich breiten Spalten (`.settings-row`, `--settings-columns`), so hoch wie ein Steuerelement, der Text einer Box nie abgeschnitten; so sieht das Panel wie die Zeilen des Processing-Managers ruhig aus. Keine Häkchen-Liste, kein Menü, kein Schalter.
  - **Je Browser gemerkt** (`preferences.ts`, `localStorage`): `earthx.basemap`, `earthx.overlays`, `earthx.projection`, `earthx.theme`, `earthx.tooltips`. Ein gesperrter oder werfender Speicher ändert nichts am Verhalten: Vorgabe beim Laden, die Wahl gilt für den Besuch.
  - **Appearance:** Vorgabe „Dark“. Gespeichert wird `tech` (Dark), `normal` (Light) oder `system`, damit eine Wahl aus der Zeit vor „System“ gilt. „System“ folgt `prefers-color-scheme` und wechselt mit dem System, auch während die Seite offen ist.
  - **Die bisherigen Stellen entfallen:** der Knopf „Basemap“ und der Knopf Light/Dark oben rechts. Dort bleibt „Zoom to selection“. Neue Einstellungen dieser Art kommen in dieses Panel, nicht an einen eigenen Knopf.
- **Ausgabetyp im Processing-Panel** (Otto, 11.11.2026): angeboten wird nur, was Sinn macht, kein Typ ist gesperrt oder „nicht empfohlen“. Gibt jeder Schritt nur Werte weiter (Bänder wählen, Zuschnitt, Maske, Reprojektion mit `nearest` oder `mode`, Mosaik ganzer Szenen): der Typ der Quelle und float32, Vorgabe der Typ der Quelle. Werden Werte neu gerechnet (Band math, Index, Normalize, interpolierende Reprojektion, eine Quelle, deren Skalierung der Kern anwendet, wie Sentinel-2) oder haben die Bänder verschiedene oder keine angegebenen Typen: nur float32. Passt eine Wahl nach einer Änderung der Kette nicht mehr, gilt float32, ohne Meldung. Die Regel steht in der Operator-Registry (`PassesValues`, in der Prozessbeschreibung als `x-earthx-passes-values`); das Frontend hat keine eigene Liste (`processingDefaults.ts`). Was der Server annimmt, bleibt wie in M5-28.
- **Ergebnisse aus ganzen Zahlen** (Otto, 11.11.2026): „so wie es ist“ (nur Opacity, (i) „A layer of classes is drawn as it is: it has no range or colormap to set.“) gilt nur für ein **Band aus Klassen**: das Band, das die Registry als Klassenschicht des Datensatzes nennt (`earthx:mask`, z. B. WorldCover `map`, Sentinel-2 `scl`), ganzzahlig und nicht aus Band math (`resultLayer.ts::isClassBand`). Jedes andere Ergebnis aus ganzen Zahlen (Sentinel-2 als `uint16`, Höhen als `int16`) hat die Einstellungen eines Gleitkomma-Ergebnisses: Bereich mit Histogramm, vmin/vmax, absolute/percentile, Auto-scale, Band, Colormap; die Vorgabe sind die 2–98 % der Statistik, die das nodata nicht zählt (M5-28). Ein Ergebnis ohne bekannten Datentyp wird wie bisher gezeichnet, wie es ist, und sagt das im (i).
  - **Die bisherigen Stellen entfallen:** der Knopf „Basemap“ und der Knopf Light/Dark oben rechts. Dort bleibt „Zoom to selection“. Neue Einstellungen dieser Art kommen in dieses Panel, nicht an einen eigenen Knopf; Ausnahme ist der Knopf „3D“ unten rechts an der Karte (Otto, 11.11.2026, UI-06 F4).
- **Kompass, Zoom und 3D** (Otto, 11.11.2026, UI-06 §9a), `components/MapControls.tsx`:
  - **Ort und Reihenfolge:** eine Gruppe unten rechts an der Karte, von oben nach unten **Kompass, Zoom +, Zoom −, 3D**; gleich große Knöpfe in der Form von `.icon-btn` mit Tokens, Steuerhöhe 28 px, bei Touch und unter 900 px 44 px. Sie rückt mit, wo rechts eine Seitenleiste oder ein Blatt offen ist, und deckt bei 320 px nichts, was man bedienen muss. Kein Eintrag „3D“ im Panel „Settings“.
  - **Kompass:** immer sichtbar, auch in 2D und ohne Drehung (dann zeigt die Nadel nach oben); runder Knopf mit der Nadel (§3), die sich mit der Karte dreht und bei Neigung flach bleibt. Klick: Norden oben und Neigung 0. In 3D dreht Ziehen am Kompass die Karte, im Fokus ←/→ um 15°; ein Klick ohne Bewegung richtet aus. In 2D nicht gesperrt. Tooltip (advanced) und `aria-label` „Reset north and tilt“.
  - **3D:** ein Schalter mit dem Text „3D“, an = gedrückt (`aria-pressed`) und gefüllt in Akzent wie eine gewählte Segment-Schaltfläche. An legt die Karte über die AWS Terrain Tiles (Überhöhung 1,5, Kacheln bis Zoom 12) und kippt sie auf 50°; aus setzt Neigung und Drehung auf 0 und nimmt das Gelände weg. Tooltip (advanced) mit dem Hinweis „Elevation tiles load from amazonaws.com.“ wie beim Relief.
  - **Drehen und Kippen nur mit 3D** (D27 gilt in 2D weiter; Otto, 11.11.2026): mit Maus (rechte Taste oder Strg + Ziehen), Touch (zwei Finger) und Tastatur (Umschalt + Pfeiltasten an der Karte); Neigung höchstens 60°. In 2D verschiebt und zoomt die Karte nur.
  - **Gemerkt** je Browser als `earthx.terrain` (3D an oder aus); Neigung und Drehung nicht. Der Permalink trägt nichts davon und öffnet flach.
  - **Coverage** fragt bei gekippter Karte den Ausschnitt ab, den die Karte flach bei gleicher Mitte und gleichem Zoom hätte.
  - Verliert die Karte mit 3D den WebGL-Kontext, geht 3D aus und die Statusmeldung sagt es.
- **Relief** gibt es nur als Overlay. Ein Browser, der die Basemap „relief“ gemerkt hat, öffnet mit der Standard-Basemap und dem Overlay Relief (der Eintrag wird einmal umgeschrieben). Ein alter Permalink mit Basemap „relief“ öffnet für diese Ansicht ebenso, ohne etwas zu speichern; das Backend nimmt `relief` weiter an, das Frontend schreibt es nicht mehr.
- **Unter der Startzoomstufe** zeigt ein Layer nichts; über der Karte steht dazu nichts (kein „Zoom in to level n …“, keine Marke „Zoom in“; Otto, 10.11.2026). Den Grund nennt der Tooltip seiner Zeile im Layer-Manager, in beiden Stufen, solange er gilt: „Nothing shown at this zoom: this layer is drawn from zoom n.“ (`zoomHint.ts`). Die Zeile „Search results“ sagt es für einen Datensatz mit Vorschau-Kacheln (`browse: preview_tiles`), die Marke „Preview“ für die Vorschau des Processing-Panels. Gilt für jeden Datensatz.
- **„Zoom to selection“** zoomt auf alles Gewählte zusammen (`zoomSelection.ts`):
  - Dazu gehören die AOI, die Bilder der offenen Ansicht und die Bilder der sichtbaren Layer; ein ausgeblendeter Layer und eine Ansicht mit ausgeblendetem Bild zählen nicht. Beispiel: AOI in der Schweiz und Ansicht auf Teneriffa → beide sind im Bild.
  - Über die Datumsgrenze gilt der kürzere Weg (`unionBboxShortest`): Fidschi beiderseits der Linie ist ein Kasten über 180°, nicht die Welt.
  - Ohne etwas Gewähltes ist der Knopf gesperrt und nennt den Grund: „Nothing to zoom to: draw an AOI, open an image or show a layer“.
- **Coverage unabhängig von der AOI** (Teil 4, Otto, 04.11.2026; ersetzt die Regel „mit AOI über die AOI“ aus M3-19):
  - Die Karte zeigt immer die Abdeckung über den **sichtbaren Kartenausschnitt**, bei kleinem Zoom die ganze Welt, auch wenn eine AOI gezeichnet ist. Eine AOI zu zeichnen, zu ändern oder zu löschen stellt keine neue Frage.
  - Die Anfrage ist ein `GET /coverage/{id}` mit Ausschnitt, Zeitraum und Filtern; sie trägt **keine AOI** (`api.fetchCoverage` hat keinen Weg dafür), und das Frontend benutzt `POST /coverage/{id}` nicht mehr.
  - Die Stufenregel (Stufe aus Zoom und Fenstergröße, `levelForViewport`, #286) und „dieselbe Frage nicht zweimal“ bleiben; beantwortete Ausschnitte werden auch mit AOI wiederverwendet. Filter aus „Advanced search“ wirken weiter auf die Coverage.
  - Ein Schalter „Filter within AOI only“ lässt die Filter, die von der Fläche abhängen, in der Coverage weg (sie kann sie nicht messen); die AOI ändert so höchstens die Filter, nie den Ausschnitt.
  - Auch „AOI coverage“ (DS-03c) bleibt aus der Coverage: sie liest die Umrisse der gefundenen Szenen gegen die AOI, die Karte zählt an der Quelle und trägt keine AOI. „Evaluate“ ändert die Anfrage der Karte nicht.
- **Schmale Fenster** (unter 900 px; Teil 6, Punkt 58 des Backlogs):
  - **Statusmeldung:** liegt über jedem Panel (`z-index` 13 nur unter 900 px, wo ein Panel die ganze Karte deckt: über dem Panel der Leiste 11 und der Seitenleiste und dem Sheet 12, unter der Leiste 14; im breiten Fenster steht sie neben dem Panel), steht unter der Reihe der Knöpfe oben rechts (`top` = 16 px + `--control-height` + `--space-2`) und nie über dem Rand (Breite höchstens die Karte rechts der Leiste); ein langer Text bricht um, das rote x ist immer erreichbar. Die Meldung ist **deckend** (`--panel-bg` über `--map-bg`), weil sie über einem Panel liegt.
  - **Knöpfe oben rechts:** eine Reihe, nicht zwei; die Statusmeldung liegt nicht darüber.
  - **AOI-Werkzeuge** im Control-Menü: bei 320 px kein Überstand der Zeile (`.toolbar`, `.tool-btn`).
  - **Felder eines Bereichs** („Scale“) in Seitenleiste und Processing-Panel: behalten `--number-field-width`; die Einheit daneben kürzt mit „…“ und ist in ihrer Liste vollständig.
  - Prüfungen: `frontend/e2e/narrow-windows.cjs` (320, 360 und 1280 px, Hell und Dunkel, jedes Panel der Leiste: Meldung im Fenster, nicht verdeckt, unter den Knöpfen, mit rotem x schließbar; Gegenprobe mit den alten Regeln über `FAULT=1`), `frontend/e2e/range-layout.cjs` (Vorschau des Processing-Panels: kein abgeschnittener Wert), `frontend/src/narrowWindows.test.ts`. `narrow-windows.cjs` prüft zusätzlich die Felder in Ansicht, Layer und Ergebnis-Layer mit „-0.123456“ (Gegenprobe `FAULT=1` mit den alten Regeln: Feld 33 px breit, Wert abgeschnitten).
- **Datensätze in „Search and area“** (UI-05 Teil 1, Otto 06.11.2026):
  - **Seiten** zu zwei Knöpfen je Reihe, so vielen Reihen, wie ohne Scrollen des Panels Platz haben (gemessen, neu bei jeder Größenänderung des Fensters, mindestens eine, ohne Obergrenze; Otto, 07.11.2026); erst der Rest kommt auf die nächste Seite; klein rechts neben der Überschrift „Datasets“ immer „‹ 1 / n ›“ (Otto, 06.11.2026, Review von Teil 1), auch mit einer Seite, ohne Umbruch; ein Pfeil am Rand ist gesperrt mit Grund. Das Raster behält auf der letzten Seite die Höhe einer vollen Seite. Ändert sich die Seitengröße, zeigt das Panel die Seite des zuletzt gewählten Datensatzes; gewählte Datensätze auf anderen Seiten bleiben gewählt und werden mit gesucht.
  - **„Advanced search“** steht immer über „Search“; ohne Datensatz mit Filtern gesperrt mit Grund.
  - **Datum:** Jede neue Wahl im Panel füllt die Felder mit dem frühesten und dem spätesten Tag der gewählten Datensätze mit Zeitachse (offenes Ende = heute, UTC; `prefilledDays` in `dateBounds.ts`; Otto, 06.11.2026); was der Nutzer einträgt, bleibt bis zur nächsten Wahl. Ohne gewählten Datensatz sind sie leer. Die Felder bieten nur diese Tage an (`min`/`max`); ein Tag außerhalb geht beim Verlassen des Feldes auf die Grenze. Ohne Zeitachse gesperrt, mit dem Zeitraum des Datensatzes gefüllt und im Tooltip; bei gemischter Wahl steht er hinter einem (i) an „Acquisition date“.
  - **Kein Zusatztext im Panel:** der Reifegrad eines gewählten Datensatzes als Warnung (`Tip tone="warn"`) an „Datasets“, der Ort mit der Attribution der Ortssuche hinter einem (i) am Feld, „Scenes counted by their center point in the cell“ hinter einem (i) an der Legende. Sichtbar bleiben „sample: n of m scenes“ (Pflicht) und „n scenes found“.
- **Das Panel scrollt nie wegen seines Inhalts** (Otto, 10.11.2026): Was wachsen könnte, behält eine feste Größe und wird gröber, nicht länger. **Balken der Coverage** (Aufnahmen über die Zeit): eine Reihe von 32 px Höhe in der Breite des Panels; ein Balken je Monat, bei mehr als 36 Monaten je Quartal, bei mehr als 36 Quartalen je Jahr (`coverageHistogram.ts`); Tooltip je Balken „2024-07: 120“, „2024 Q3: 360“ bzw. „2024: 1440“; markiert sind die Balken, die in die gewählten Daten fallen. Prüfung: `frontend/e2e/coverage-histogram.cjs` (30, 60 und 146 Monate, Hell und Dunkel, breit und 360 px).
- **Die Wahl des Datensatzes unter „Coverage“** (mehrere Datensätze gewählt) enthält nur Datensätze, keinen Eintrag „Hide coverage“. Beendet wird die Karte mit dem Knopf „Hide coverage“ neben „Coverage“.

## 10. Prüfungen gegen Rückfälle

| Regel | Test |
|---|---|
| kein x im Kopf eines linken Panels (Search and area, Layers, Jobs, Search results, Settings: kein `CloseButton`, kein `close-x`, kein `closeDock`) | `frontend/src/uiRules.test.ts`, `frontend/src/AppRail.test.tsx`, `frontend/src/components/SettingsPanel.test.tsx`, `frontend/e2e/settings-panel.cjs` |
| rotes x und „Close“ nur in `CloseButton`, kein „Dismiss“, kein x-Zeichen als Inhalt eines Knopfs | `frontend/src/uiRules.test.ts` |
| Esc nur in den Ausnahmen | `frontend/src/uiRules.test.ts`, dazu Esc-Tests je Panel und Dialog |
| keine Einheit an „Scale“ | `frontend/src/uiRules.test.ts`, `ProcessingPreview.test.tsx` |
| Begriffe (§2) gegen alle Texte der Oberfläche | `frontend/src/uiRules.test.ts` |
| Sperrgrund im Tooltip | `frontend/src/fixtures/lockedControls.ts`, benutzt in `ControlPanel.test.tsx` und `LayerManager.test.tsx` |
| Klick neben einen Dialog schließt nicht | `DownloadDialog.bands.test.tsx` |
| Tokens statt fester Werte: keine Länge in `px`/`rem` für Abstand, Schriftgrad und Radius in **irgendeiner** Regel von `index.css` | `frontend/src/tokens.test.ts` |
| eine Zahl nur über `numberFormat.ts`: kein `toFixed`, `toPrecision`, `toLocale…`, `Intl` sonst (Ausnahme: Dateien und Namen in `bandChoice.ts`), kein Prozent mit Leerzeichen, keine Monatstabelle | `frontend/src/uiRules.test.ts`, `frontend/src/numberFormat.test.ts` |
| Erklärungen als (i) statt als Absatz: die verschobenen Texte nicht zwischen Tags, kein Hinweis aus einem langen festen Satz (außer den Zuständen mit Handlung) | `frontend/src/uiRules.test.ts`, `ProcessingPanel.test.tsx`, `ProcessingBatch.test.tsx`, `ProcessingPreview.test.tsx`, `ControlPanel.test.tsx` |
| schmale Fenster: Statusmeldung über dem Panel und unter den Knöpfen, deckend; Felder eines Bereichs mit Mindestbreite | `frontend/src/narrowWindows.test.ts`, `frontend/e2e/narrow-windows.cjs`, `frontend/e2e/range-layout.cjs` |
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
| Einstellungen in einem Panel der Leiste (Slot im Dock, Kopf ohne x, kein Popup, keine Häkchen-Liste): kein Knopf „Basemap“, kein Theme-Knopf, Relief nur als Overlay, das Symbol unten in der Leiste; Segment-Knöpfe gleicher Größe, Overlays als gedrückte Knöpfe, „Simple“ und „Advanced“ als zwei Boxen, Merken je Browser, gesperrter Speicher | `frontend/src/uiRules.test.ts`, `frontend/src/components/SettingsPanel.test.tsx`, `frontend/src/AppRail.test.tsx`, `frontend/src/preferences.test.ts`, `frontend/e2e/settings-panel.cjs` |
| ein Schalter nur für An/Aus (`role="switch"` nur im Filter der AOI, kein Bauteil `Switch`); die gewählte Segment-Schaltfläche ist gefüllt; alle Boxen im Panel gleich groß | `frontend/src/uiRules.test.ts`, `frontend/src/components/SettingsPanel.test.tsx`, `frontend/e2e/settings-panel.cjs` |
| ein Tooltip geht mit dem Zeiger oder dem Fokus, auch wenn die Stufe inzwischen auf „Simple“ steht, und mit dem Wechsel der Stufe | `frontend/src/components/TipLayer.step.test.tsx`, `frontend/e2e/settings-panel.cjs` |
| das eine Symbol aus MingCute: Herkunft, Änderung und Lizenztext vermerkt | `frontend/src/components/icons.test.tsx` |
| Tooltip mit vollem Text nur bei gemessener Kürzung, in beiden Stufen; `data-tip-cut` nur mit `data-tip`, ohne Stufe, mit Wert | `frontend/src/uiRules.test.ts`, `frontend/src/tipLevel.test.ts`, `frontend/src/components/TipLayer.test.tsx`, `frontend/e2e/settings-panel.cjs` |
| „Zoom to selection“ über AOI, Ansicht und sichtbare Layer, der kürzere Weg über die Datumsgrenze, gesperrt mit Grund | `frontend/src/zoomSelection.test.ts`, `frontend/src/geoUtils.test.ts`, `frontend/src/AppTopBar.test.tsx` |
| Coverage ohne AOI: keine AOI in der Anfrage, kein POST, derselbe Ausschnitt mit und ohne AOI | `frontend/src/store.coverage.test.ts`, `frontend/src/api.test.ts`, `frontend/e2e/no-aoi-in-url.cjs` |
| kein Eintrag „Hide coverage“ in der Wahl des Datensatzes | `frontend/src/components/ControlPanel.test.tsx` |
| Zeitleiste: Daten und Pfeile an einer Stelle bei jedem Schritt (auch erstem und letztem); ←/→ blättern durch die Überflüge, nicht in Feldern, Listen, Dialogen, am Regler, nicht mit Umschalttaste/Strg/Alt/Meta | `frontend/src/components/TimeSlider.keys.test.tsx`, `frontend/e2e/selection-block.cjs` |
| Datensätze in Seiten mit so vielen Reihen, wie ohne Scrollen passen, ohne Obergrenze, neu gemessen bei jeder Größenänderung, Zähler und gesperrte Pfeile mit Grund klein rechts neben „Datasets“, volle Höhe auf der letzten Seite; „Advanced search“ immer da, gesperrt mit Grund; Datum bei jeder Wahl vorausgefüllt und im Zeitraum der gewählten Datensätze, gesperrt mit Zeitraum im Tooltip; kein Zusatztext im Panel | `frontend/src/components/ControlPanel.test.tsx`, `frontend/src/components/AdvancedSearch.test.tsx`, `frontend/src/datasetPages.test.ts`, `frontend/src/dateBounds.test.ts`, `frontend/src/uiRules.test.ts`, `frontend/e2e/dataset-pages.cjs`, `frontend/e2e/advanced-search.cjs` |
| Data catalogue: zweites Symbol der Leiste, öffnet und schließt das Fenster, rotes x schließt, Esc und Klick daneben nicht; Gruppen in der Reihenfolge von `earthx:category`; „Add“ ohne Wahl und mit Blättern, „Remove“ wählt ab und lässt die Ergebnisse; Konto-Datensatz mit Link statt „Add“, „Prototype“ nur bei `unclear`, Links nur `https://`; Speicher `earthx.datasets` (gesperrt, kaputt, unbekannte und ausgemusterte Kennungen); Erstbesuch höchstens sechs in der Reihenfolge der Gruppen; Permalink fügt seinen Datensatz hinzu | `frontend/src/components/DataCatalogue.test.tsx`, `frontend/src/catalogue.test.ts`, `frontend/src/store.catalogue.test.ts`, `frontend/src/preferences.test.ts`, `frontend/src/components/ProcessingShare.test.tsx`, `frontend/e2e/data-catalogue.cjs` |
| „Evaluate“: Segment-Knöpfe, per pass zuerst und gedrückt, Erklärung mit Beispiel hinter dem (i), nicht als Absatz; „AOI coverage“ als Schieber und Zahl, gesperrt mit Grund ohne AOI, bei einem Punkt frei (das Quadrat um ihn ist die AOI), ohne Zeitraum frei; die (i)-Box am Schalter nennt die gemessenen Filter | `frontend/src/components/AdvancedSearch.evaluate.test.tsx`, `frontend/src/store.evaluate.test.ts`, `frontend/e2e/evaluate-coverage.cjs` |
| Ganzzahl-Ergebnisse: Einstellungen wie Gleitkomma, „so wie es ist“ nur für ein Band aus Klassen (Maskenband der Registry), Grund im (i); keine Regel nach dem Datentyp allein | `frontend/src/resultLayer.test.ts`, `frontend/src/components/ResultControls.test.tsx`, `frontend/src/components/ProcessingResultLayer.test.tsx`, `frontend/src/components/ResultPercent.test.tsx`, `frontend/src/uiRules.test.ts`, `frontend/e2e/whole-numbers.cjs` |
| „Auto-scale“ der Processing-Vorschau bedienbar ab der ersten Vorschau, nach „Review“, bei laufendem und fertigem Job, mit automatischem Typ und `uint16`; setzt den gemessenen Bereich zurück | `frontend/src/components/ProcessingPreview.test.tsx`, `frontend/src/components/ProcessingShow.test.tsx`, `frontend/e2e/preview-auto-scale.cjs` |
| Ausgabetyp: Typ der Quelle und float32 nur, wo alle Schritte Werte weitergeben, sonst nur float32; Regel aus `x-earthx-passes-values`, keine eigene Liste, kein gesperrter oder markierter Typ; eine unpassende Wahl wird float32 | `frontend/src/processingDefaults.test.ts`, `frontend/src/components/ProcessingPanel.test.tsx`, `frontend/src/components/ProcessingMask.test.tsx`, `frontend/src/components/MosaicJobs.test.tsx`, `frontend/src/uiRules.test.ts`, `backend/tests/earthx/api/test_processing_docs.py`, `frontend/e2e/preview-auto-scale.cjs` |
| Layer-Manager: gesperrtes Bedienelement zeigt den Grund in „Simple“, auch im `label`; ein Grund für einen gelöschten Job; „Process layer“ für jeden Layer; gleiche Stufen in allen Zeilen | `frontend/src/components/LayerTooltips.test.tsx`, `frontend/src/components/LayerManager.test.tsx`, `frontend/src/components/ResultBandLayer.test.tsx`, `frontend/src/uiRules.test.ts`, `frontend/e2e/layer-tooltips.cjs` |
| Kompass, Zoom und 3D: Reihenfolge und Größe der Gruppe, Kompass immer da und mit der Karte gedreht, Klick richtet aus; Drehen und Kippen nur mit 3D, höchstens 60°; 3D an kippt auf 50°, aus auf 0; kein Eintrag „3D“ in „Settings“; hell, dunkel, schmale Fenster | `frontend/src/components/MapControls.test.tsx`, `frontend/src/terrain.test.ts`, `frontend/src/uiRules.test.ts`, `frontend/src/store.terrain.test.ts`, `frontend/src/mapStyles.diff.test.ts`, `frontend/e2e/terrain-3d.cjs` (1280, 360 und 320 px, hell und dunkel) |

Ein neuer Begriff, der ein altes Wort ersetzt, bekommt eine Zeile in der Liste `FORBIDDEN` von `uiRules.test.ts` mit Gegenprobe.
