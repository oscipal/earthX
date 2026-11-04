# EarthX — Leitfaden der Oberfläche

**Stand:** 04.11.2026, UI-04 Teil 2 (`docs/plans/vp3/ui-04-einheitlichkeit.md` §7, §8). Grundlage sind die Regeln und Begriffe aus UI-03 (#277–#283), NM4-75 (#284, `adr/0028`) und die Antworten Ottos zu UI-04 (§7.0, §7.9).

**Gilt für:** jede Änderung an `frontend/`. Künftige Pläne verweisen auf diese Datei. Neue Begriffe, Bauteile oder Symbole kommen zuerst hierher.

**Markierung:** Steht an einer Regel *(folgt in Teil n)*, ist sie entschieden, aber noch nicht überall umgesetzt.

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
| Scale, vmin / vmax, absolute / percentile | der Bereich einer Darstellung und seine Art (NM4-65, UI-03e); RGB hat einen Bereich und eine Art je Kanal | „min/max“ |
| Temporary | Abzeichen neben dem Titel der Ansicht, solange kein Layer das Bild so hält, wie es gezeichnet ist | |
| Filter within AOI only | der Schalter in „Advanced search“ | |
| Copy original scene name | kopiert die Kennungen der Szenen in die Zwischenablage | |
| Download crop / Download full scene(s) / Download | Zuschnitt der AOI / ganze Szenen / ein Layer; die Formen heißen „One file per band“, „One file per resolution“, „One multi-band file“ (NM4-75) | |
| — none — / — choose — | kein Wert, auch die gesperrte Colormap bei RGB / Pflichtwahl ohne Vorgabe | „–“ |
| Choose | auswählen, im Text | „Pick“ |
| finished | Status eines Jobs („Finished“); in Zusammenfassungen klein („3 finished · 1 running“) | „done“ |
| Settings | das Einstellungsmenü unten in der Leiste *(folgt in Teil 4)*; die Seitenleiste heißt für Screenreader nach ihrem Inhalt („Image settings“, „Layer settings“) | |

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
- **Ein Strich:** 1.5 px, an jeder Größe gleich dick (`absoluteStrokeWidth`). Zwei Größen: 16 px als Standard (`<DownloadIcon />`), 14 px in Listenzeilen (`<DownloadIcon size={14} />`). Farbe `currentColor`.
- **Neben einem Text** steht das Symbol davor und bekommt `lead`: `<CogIcon lead />Process`. Der Abstand kommt aus dem CSS (`.icon-lead`), kein Leerzeichen im Text.
- **Ein Knopf nur mit Symbol** hat einen Namen für Screenreader (`aria-label`) und einen Tooltip. Gleiche Aktion, gleiches Symbol, auch wenn Text dabeisteht oder nicht.
- **Eigene Zeichnungen gibt es nicht.** Das einzige `<svg>` im Code ist das Balkendiagramm des Histogramms (`RangeHistogram`), kein Symbol.
- **Der Haken** vor dem gewählten Eintrag eines Menüs ist ein Symbol in einem Platz fester Breite (`MenuTick`), kein Zeichen im CSS.
- **Einzige Ausnahme:** Settings ist „Settings 6 Line“ von MingCute (Apache-2.0, `mingcute_icon` 2.9.72, `svg/system/settings_6_line.svg`). Es wird als einzelnes SVG übernommen, als Strich nachgezeichnet und an Lucide angeglichen; die Änderung ist vermerkt. Herkunft und Lizenz stehen in `frontend/THIRD_PARTY_NOTICES.md` *(folgt in Teil 4)*.
- **Keine Textzeichen als Symbole** (⇩ ✎ ✕ ⚙ ＋ ⋯ ▾ ↻ …). Im Text erlaubt bleiben „…“, „—“ in „— none —“, „·“, „–“, „→“ zwischen zwei Datumsfeldern, „×“ in Maßen („10 m × 10 m“), „µm“.

| Bedeutung | Lucide |
|---|---|
| Download (überall, auch „Download all“) | `download` |
| Zeigen / Verbergen | `eye` / `eye-off` |
| Entfernen / Löschen / Leeren einer Liste (auch „Clear AOI“, „Clear search results“) | `trash-2` |
| Umbenennen | `pencil` |
| Process | `cog` (das Zahnrad bleibt, Otto) |
| Settings | MingCute „Settings 6 Line“ |
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
| Erscheinungsbild | `sun`, `moon`, `monitor` |

## 4. Sperren

- Was gerade nicht geht, ist **gesperrt** (`disabled` oder `aria-disabled="true"`) und nennt den **Grund im Tooltip**. Der Grund wiederholt nicht den Knopftext. Beispiele: „Type a place name first“, „No earlier AOI in this browser“, „Already at the top“, „Job deleted: restore it first“.
- Wo eine gesperrte Stelle einen Platz hält, bleibt sie an diesem Platz, z. B. die Colormap bei RGB als gesperrtes „— none —“, auch in der Processing-Vorschau.
- Es gibt einen Tooltip-Weg: `TipLayer` über `data-tip`. Er erscheint bei Zeiger und Fokus, auch an gesperrten Knöpfen *(folgt in Teil 3a; bis dahin `title`)*.

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
| `icons.ts`, `MenuTick` | alle Symbole; der Haken in Menüs |
| `Tip` / `TipLayer` | (i), Warnung und Tooltips |
| `Popover` | Menüs, Listen und das Formular „Advanced search“ |
| `ResamplingDialog` | die einzige Rückfrage mit Cancel/Continue |
| `PreviewBadge`, `pp-badge` | Abzeichen „Preview“, „Temporary“, „Overview“, „Zoom in“ *(ein Bauteil `Badge` folgt in Teil 3b)* |

Knopfformen: `.btn` (Standard), `.btn.primary`, `.btn.danger`, `.icon-btn`, dazu `.link-btn` im Fließtext *(folgt in Teil 3a; heute `ghost-btn`, `primary-btn`, `lm-btn` u. a.)*. Hinweise: `.hint`, `.hint.warn`, `.error` mit Tokens *(folgt in Teil 3b)*.

**Steuerhöhe:** 28 px; bei Touch und unter 900 px 44 px (`--control-height-touch`).

## 8. Schrift

- Überall die System-Schrift `--font` aus `tokens.css` mit gleich breiten Ziffern.
- Monospace (`--font-mono`) nur im Band-Math-Feld.
- Auch die Attribution der Karte und die Knöpfe der Statusleiste tragen `--font`. Ein Test findet fremde Schriftangaben *(folgt in Teil 3b)*.

## 9. Karte und Einstellungen

- **Einstellungsmenü** *(folgt in Teil 4)*:
  - Ort: ganz unten in der Leiste links (MingCute „Settings 6 Line“, Tooltip „Settings“).
  - Abschnitte: „Basemap“, „Overlays“, „Projection“, „Appearance“ (Light / Dark / System).
  - Die bisherigen Knöpfe „Basemap“ und Light/Dark oben rechts entfallen.
- **Relief** gibt es nur als Overlay. Ein alter Permalink mit Basemap „relief“ öffnet mit der Standard-Basemap und dem Overlay Relief *(folgt in Teil 4)*.
- **„Zoom to selection“** zoomt auf alles Gewählte zusammen *(folgt in Teil 4)*:
  - Dazu gehören AOI, offene Ansicht und sichtbare Layer; ausgeblendete Layer zählen nicht.
  - Über die Datumsgrenze gilt der kürzere Weg.
  - Ohne etwas Gewähltes ist der Knopf gesperrt und nennt den Grund.

## 10. Prüfungen gegen Rückfälle

| Regel | Test |
|---|---|
| rotes x und „Close“ nur in `CloseButton`, kein „Dismiss“, kein x-Zeichen als Inhalt eines Knopfs | `frontend/src/uiRules.test.ts` |
| Esc nur in den Ausnahmen | `frontend/src/uiRules.test.ts`, dazu Esc-Tests je Panel und Dialog |
| keine Einheit an „Scale“ | `frontend/src/uiRules.test.ts`, `ProcessingPreview.test.tsx` |
| Begriffe (§2) gegen alle Texte der Oberfläche | `frontend/src/uiRules.test.ts` |
| Sperrgrund im Tooltip | `frontend/src/fixtures/lockedControls.ts`, benutzt in `ControlPanel.test.tsx` und `LayerManager.test.tsx` |
| Klick neben einen Dialog schließt nicht | `DownloadDialog.bands.test.tsx` |
| Tokens statt fester Werte | `frontend/src/tokens.test.ts` (alle Klassen ab Teil 3) |
| Symbole nur aus `icons.ts`, keine Textzeichen als Symbol (Code und CSS), kein eigenes `<svg>`, Strich und Größen, jedes Symbol benutzt | `frontend/src/uiRules.test.ts`, `frontend/src/components/icons.test.tsx` |
| Schrift | *(folgt in Teil 3b)* |

Ein neuer Begriff, der ein altes Wort ersetzt, bekommt eine Zeile in der Liste `FORBIDDEN` von `uiRules.test.ts` mit Gegenprobe.
