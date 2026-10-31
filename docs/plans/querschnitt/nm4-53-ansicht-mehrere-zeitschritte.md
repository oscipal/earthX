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

### 2.1 „Apply“ und „Save“ in der Ansicht (Otto, 29.10.2026, entschieden)

- Änderungen an Colormap, vmin/vmax wirken erst mit **„Apply“**, und zwar nur auf das gerade angezeigte Bild (Zeitschritt).
- **„Save“** übernimmt die Einstellung für **alle geladenen Bilder dieses Datensatzes in der Ansicht** (alle Zeitschritte des Datensatzes). Nichts wird dauerhaft gespeichert: Wird ein anderer Quicklook gewählt und die Ansicht neu geladen, gilt wieder die Vorgabe.
- Nur angewendet, nicht gespeichert: Die Änderung gilt nur für das Bild, auf das sie angewendet wurde; andere Zeitschritte zeigen den gespeicherten Stand bzw. die Vorgabe. Beim Verlassen der Ansicht („Clear“, „Change image“) verfallen ungespeicherte Änderungen ohne Rückfrage.
- „Apply“ ist gesperrt, solange nichts geändert ist; „Save“ ist gesperrt, solange es nichts zu übernehmen gibt (Grund im Tooltip). Bei nur einem Bild eines Datensatzes in der Ansicht erscheint „Save“ nicht (nicht Mögliches ausblenden).
- **Anordnung:** „Apply“ steht unter „auto-scale“, „Save“ daneben; beide zusammen nicht höher als die Zeile mit Colormap, vmin und vmax.
- „Add to layers“ / „Add all to layers“ übernehmen die jeweils sichtbare Darstellung.
- Der Layer-Manager hat dasselbe Muster (Apply zeigt, Save speichert dauerhaft); das kommt mit NM4-50 (#234).

## 3. Im Plan klären (Optionen, Empfehlung)

1. **Was ein Zeitschritt ist:** je Datensatz eine Gruppe (Überflug) mit ihren angehakten Szenen, gemergt; Datensätze ohne Zeitachse (DEM) haben einen Zeitschritt. Reihenfolge nach Datum.
2. **Welcher Zeitschritt zuerst:** etwa der früheste oder der zuletzt angehakte.
3. **Darstellung je Zeitschritt oder je Datensatz:** entschieden in §2.1 (Apply je Bild, Save für alle Bilder des Datensatzes).
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

## 6. Plan (31.10.2026; Stufe B, kein Produktivcode)

Kennzeichnung: [P] im Code geprüft, [A] Auslegung bzw. Vorschlag von Claude. Es wurde nichts im Browser gemessen; das Verhalten von heute ist aus dem Code gelesen. Messungen kommen mit der Umsetzung (§6.9).

### 6.0 Kurzfassung

- **Befund:** Die Ansicht kennt heute **einen Datensatz** und **eine Darstellung für alles**. Mehrere Gruppen zeichnet sie schon, aber alle zugleich; mehrere Datensätze gibt es in ihr nicht, weil die Leiste der Auswahl nur auf die Haken des offenen Datensatzes wirkt (NM4-50). Der Wunsch verlangt deshalb ein neues Modell, nicht nur eine Zeile in der Leiste (§6.1).
- **Kern des Entwurfs:** Die Ansicht besteht aus **Bildern**. Ein Bild ist ein Zeitschritt eines Datensatzes (eine Gruppe, deren angehakte Szenen gemergt sind). Die Karte zeichnet immer nur das angezeigte Bild (§6.2). Die Zeile `‹ 2025-07-29 · S2A ›` und das Dropdown wählen es (§6.5).
- **Darstellung:** Jedes Bild hat seine eigene angewendete Darstellung („Apply“), „Save“ legt sie für alle Bilder des Datensatzes fest; beides nur für die Dauer der Ansicht (§6.4, nach §2.1).
- **Anheften:** „Add to layers“ heftet das angezeigte Bild an, „Add all to layers“ alle Bilder aller Datensätze (§6.6).
- **Vorgaben von Otto vom 31.10.2026** (§6.0.1) gelten und sind unten eingearbeitet.
- **Offen** sind zehn kurze Fragen (§6.10). Der Umfang liegt weit über dem Richtwert von 400 Zeilen (§6.9).

#### 6.0.1 Vorgaben von Otto (31.10.2026)

1. Die Ansicht gehört zu „Results“ und liegt dort ganz unten (NM4-59, gemergt). Die Ebenenfolge kommt aus dem Layer-Manager; diese Aufgabe führt keine eigenen Marker und keine eigene Reihenfolge ein. Gezeichnet wird nur das angezeigte Bild, an der Stelle, die `restackAll` der Ansicht gibt [P].
2. Für Sentinel-2 gilt in der Ansicht „RGB“ als Vorgabe, ohne Colormap. Das ist die Echtfarbdarstellung aus der Registry (`earthx:default_render`: Titel „True colour (TCI)“, Asset `visual`, `colormap_name=None`) [P]. Die Vorgabe eines Datensatzes bleibt die Standarddarstellung seiner Registry; für das DEM ist das `terrain` mit 0–5000 m. Keine Namensliste und kein Zweig je Datensatz im Frontend. Ob das Wort „RGB“ auch zu sehen sein soll, ist Frage 8.
3. Nachträge in Log und Plänen heißen „Nachtrag NM4-53“.
4. Bilder der Browserprüfung kommen nicht ins Repo, nur beschrieben in den PR.

### 6.1 Stand im Code [P]

| Bereich | Heute | Folge |
|---|---|---|
| Auswahl | `enterFocus` nimmt `selectionItemsFrom(s)`: die Haken, die in `s.items` stehen, also im **offenen** Abschnitt; ohne Haken die offene Gruppe. Haken anderer Datensätze bleiben, wirken aber nicht (`ticksOfOpen`, NM4-50). Die Leiste der Auswahl zählt nur `ticksOfOpen`. | „Crop & merge“ über Datensätze braucht eine Auswahl über alle Abschnitte. |
| Datensatz der Ansicht | `s.datasetId` (der offene Abschnitt) steht in `enterFocus`, `loadMosaics`, `overlaysOfEntries`, `pinWhenLoaded`, `autoStretch` und `MapView`. `DownloadedInfo` kennt seinen Datensatz nicht. | Der Eintrag muss seinen Datensatz tragen. |
| Gruppen | `passesOf(entries, s.groups)` kennt nur die Gruppen des offenen Abschnitts; Szenen anderer Datensätze würden je „allein“ stehen (`alone …`) und nie gemergt. | Gruppen aller Abschnitte übergeben. |
| Zeichnen | `syncFocusRaster` zeichnet **alle** Durchgänge von `downloaded` zugleich, einen Mosaik oder Einzelszenen je Durchgang; `restackAll` ordnet sie. | Nur das angezeigte Bild übergeben; die Ebenenfolge bleibt (NM4-59). |
| Darstellung | Ein `appliedRender` und ein Satz Felder (`pendingColormapName`, `pendingVmin`, `pendingVmax`) für die ganze Ansicht. „Apply“ schreibt in `appliedRender`. „Save“ gibt es nur, wenn die Ansicht ein angeheftetes Layer ist (`layerOfView`) und schreibt in dieses Layer (NM4-50). | Darstellung je Bild und je Datensatz (§6.4). |
| Eintritt | `enterFocus` setzt die Vorgabe aus `defaultRenderOf` und misst **einmal** die Spanne der ersten Szene (`autoStretch`); sie landet nur in den Feldern, „Apply“ ist danach frei. | Messen gilt für das angezeigte Bild (§6.4). |
| Anheften | `addCurrentToLayers` heftet im Zuschnitt **ein Layer je Gruppe** an, bei der ganzen Szene ein Layer für alles; der Name ist `Datensatz · Gruppenname`. | „Add to layers“ nur das angezeigte Bild; „Add all“ ist das heutige Verhalten, erweitert über Datensätze. |
| Leiste | `App.tsx` zeigt im Ansichtsmodus `ViewerControls` (Kopf, Colormap/vmin/vmax mit „auto-scale“/„Apply“/„Save“, Zeile mit Anheften, Process, Change image, Clear) und, wenn weitere Szenen angehakt sind, darüber `ViewBar`. Die `TimeSlider` ist im Ansichtsmodus nicht eingebunden. | Keine Tastenkonflikte mit der Zeitleiste (Punkt 6). |
| Satellit | Im Frontend wird `platform` nirgends gelesen. Die Registry kennt den Filter `platform` mit den Werten `sentinel-2a/-2b/-2c` und den Beschriftungen „Sentinel-2A“ usw. (`DatasetConfig`, `earthx:search_filters`). | Beschriftung aus der Registry, keine Liste im Frontend (Frage 3). |

### 6.2 Modell: Bilder

Neues reines Modul `viewImages.ts` (kein Zustand, leicht zu testen):

- **Bild** = `{ key, datasetId, group, ids, date, platforms }`. `ids` sind die Szenen der Gruppe, die in der Ansicht liegen (`downloaded`). Der Schlüssel ist Datensatz plus Gruppenschlüssel.
- `imagesOf(downloaded, sections, datasets)` bildet die Liste: nach Datensätzen in der Reihenfolge der Abschnitte (so steht auch das Dropdown), darin **nach Datum aufsteigend**, das früheste zuerst, `‹` geht zurück in der Zeit (Punkt 1). Ein Datensatz ohne Zeitachse (`time_range=False`, DEM) hat die Gruppen, die ihm die Registry gibt (Regel `results_group_by`); in der Regel eine. Ohne Datum steht der Gruppenname in der Zeile.
- Satelliten eines Bildes: die verschiedenen `platform`-Werte seiner Szenen, mit „/“ verbunden (ein Tag kann bei Überlappung zwei Satelliten haben); fehlt der Wert, steht nichts.
- Im Zustand kommt `shownImage: string | null` dazu. Es setzt sich beim Eintritt (Punkt 2), beim Wechsel des Dropdowns (erstes Bild des Datensatzes) und beim Durchschalten.
- **`DownloadedInfo` bekommt `datasetId`.** `loadMosaics`, `overlaysOfEntries`, `pinWhenLoaded`, `autoStretch`, `saveViewLook` und `MapView` lesen ihn statt `s.datasetId`; `passesOf` bekommt die Gruppen aller Abschnitte. Der Datensatz der Ansicht ist damit vom offenen Abschnitt der Ergebnisliste getrennt, wie Layer und Ergebnisse schon (Otto, 26.10.2026).
- **Schlüssel `downloaded`:** bleibt die Szenen-ID (der Umbau auf Datensatz plus ID träfe Layer, Download und Verarbeitung). Szenen-IDs sind nur innerhalb einer Collection eindeutig (`sceneKey`). Trifft die Ansicht dieselbe ID in zwei Datensätzen, nimmt `enterFocus` die zweite nicht auf und sagt es in einer Meldung [A]. Ein Test hält das fest.
- Verlassen der Ansicht („Clear“, „Change image“) setzt `shownImage` und alle Darstellungen zurück (`LEAVE_FOCUS`, §2.1).

### 6.3 Antworten auf die Punkte aus §3

**1. Was ein Zeitschritt ist.** Je Datensatz eine Gruppe mit ihren angehakten Szenen, gemergt; nach Datum aufsteigend; Datensätze ohne Zeitachse haben die Bilder, die ihre Gruppen ergeben (§6.2). Die Zeile heißt `‹ <Datum> · <Satellit> ›`. Das Datum ist der UTC-Tag (`viewDates`, wie im Kopf). Das Tooltip der Zeile nennt „Step 3 of 5“ und den Gruppennamen. Pfeile erscheinen nur bei mehr als einem Bild im Datensatz; die Zeile als Ganzes nur, wenn die Ansicht mehr als ein Bild hat (sonst steht das Datum schon im Kopf).

**2. Welcher Zuerst.** Optionen: (a) das früheste Bild, (b) das späteste, (c) das Bild der Gruppe, die in der Ergebnisliste offen ist, sonst das früheste. **Empfehlung (c):** Otto sieht, was er zuletzt in der Liste vor Augen hatte; die Ergebnisliste bleibt dabei unberührt. Das Durchschalten bewegt die offene Gruppe der Liste nicht [A].

**3. Darstellung.** Entschieden in §2.1; Umsetzung in §6.4.

**4. Die übrigen Knöpfe.** Die Leiste der Auswahl (`ViewBar`) und die Leiste der Ansicht (`ViewerControls`):

| Knopf | Wirkung |
|---|---|
| „Crop & merge to AOI“, „View merged scenes“ (Leiste der Auswahl) | nehmen die Haken **aller** Datensätze der Suche; ein Bild je Gruppe und Datensatz. Die Zahl nennt die Summe, das Tooltip die Aufteilung („12 scenes · Sentinel-2 L2A 8 · Copernicus DEM 4“). |
| „Download merged crop“, „Download full scenes“ (Leiste der Auswahl) | bleiben beim **offenen** Datensatz (Frage 2). Download und Verarbeitung sind je Datensatz gebaut (`download.ts`, `originals.ts`); ein Umbau über Datensätze ist eine eigene Aufgabe. Liegen Haken in anderen Datensätzen, sagt das Tooltip „…only the scenes of <Datensatz>“. Dieses Verhalten ist heute schon so. |
| „Process“ (Leiste der Auswahl) | wie „Download“: offener Datensatz. |
| „Process“ (Leiste der Ansicht) | die Szenen **aller Bilder des angezeigten Datensatzes** (`processFocusView` bekommt nur dessen `ids`); ein Auftrag hat genau einen Datensatz. Frage 4: Alternative nur das angezeigte Bild. Zusammenhang mit NM4-06: dort geht der gemergte Zuschnitt als ein Objekt in das Panel; der Stapel (UI-01) macht je Gruppe einen Auftrag. Der Aufruf bleibt eine Zeile, am Panel ändert diese Aufgabe nichts. |
| „Change image“, „Clear“ | verlassen die **ganze** Ansicht (alle Bilder, alle Datensätze), wie heute. Ungespeicherte Darstellungen verfallen ohne Rückfrage (§2.1). |
| „Hide image“ (Auge im Kopf) | blendet die Ansicht aus, nicht nur das Bild. Durchschalten ändert es nicht; bei ausgeblendeter Ansicht schaltet es nur die Auswahl um, ohne Kacheln zu laden. |

**5. Namen und Reihenfolge der Layer.** Heute `Datensatz · Gruppenname` (z. B. „Sentinel-2 L2A · 2025-07-29 · 32UQD“). **Empfehlung:** der Satellit kommt in der Kurzform hinten dazu („… · S2A“), wo es einen gibt (Frage 6). Neue Layer kommen ganz nach oben (NM4-59, Nachtrag). „Add all“ heftet in der Reihenfolge der Zeile an, Datensatz für Datensatz, je Datensatz das früheste zuerst, in **einem** Schritt (`set`); damit steht das späteste Bild des letzten Datensatzes oben (Frage 5). Otto ordnet mit ▲/▼ um.

**6. Tastatur.** Die Zeile ist eine Gruppe (`role="group"`, Beschriftung „Time step“). Hat ein Pfeil den Fokus, schalten ←/→ zum vorigen bzw. nächsten Bild; die Pfeile sind Knöpfe und mit Tab erreichbar. Keine Taste auf der ganzen Seite: die Karte nutzt die Pfeiltasten zum Verschieben. Die Zeitleiste der Suchergebnisse (NM4-18) ist im Ansichtsmodus nicht eingebunden [P], ein Konflikt ist ausgeschlossen. Die Reihe läuft nicht im Kreis: Am ersten bzw. letzten Bild ist der Pfeil ausgegraut (`aria-disabled`) mit Tooltip („This is the first image“ bzw. „This is the last image“).

**7. Kopf.** Der Kopf zeigt das angezeigte Bild: Datensatz, Datum, Art („AOI crop“ bzw. „whole scene“) und die Zahl der gemergten Szenen **dieses** Bildes. Die Regeln für Breite und „…“ gelten weiter (`vc-title`).

**8. Regeln aus #211/#221.** Unverändert: Show/Hide, Anhak-Reihenfolge, feste Plätze der Leisten. „Show/Hide“ heißt seit NM4-59 das Auge von „Results“; die Ansicht hat ihr eigenes Auge im Kopf. „Crop“ schaltet das Auge von „Results“ aus (Ausnahme), „Change image“ und „Clear“ lassen es. Die Reihenfolge auf der Karte kommt aus `restackAll`; das Bild der Ansicht liegt in Stufe 6 von „Results“, ganz unten (§6.0.1).

### 6.4 Darstellung je Bild und je Datensatz (nach §2.1)

Zustand (nur während der Ansicht, nichts davon wird gespeichert):

- `viewLooks: Record<Bildschlüssel, AppliedRender>`: was mit „Apply“ auf ein Bild angewendet wurde und nicht gespeichert ist.
- `savedLooks: Record<Datensatz, AppliedRender>`: was mit „Save“ für alle Bilder eines Datensatzes festgelegt wurde.
- **Darstellung eines Bildes** = `viewLooks[Bild]` sonst `savedLooks[Datensatz]` sonst die Vorgabe der Registry (`appliedRenderFrom(defaultRenderOf(...))`; bei Sentinel-2 also RGB ohne Colormap, §6.0.1).
- `appliedRender` und die drei Felder bleiben, was sie sind: die Darstellung **des angezeigten Bildes**. Beim Durchschalten schreibt der Store sie nicht zurück, sondern lädt `appliedRender` und die Felder aus der Darstellung des neuen Bildes. So ändern sich `MapView`, `viewLayer` und die Layer-Logik nicht.

Knöpfe:

- **Apply** (nur das angezeigte Bild): schreibt die Felder in `appliedRender` und in `viewLooks[Bild]`; gesperrt, solange die Felder dem entsprechen, was die Karte zeigt (heutige Prüfung `lookChanged`; Grund im Tooltip).
- **Save** (alle Bilder des Datensatzes): wendet die Felder auf das angezeigte Bild an, schreibt `savedLooks[Datensatz]` und löscht die `viewLooks` aller Bilder dieses Datensatzes; die Bilder anderer Datensätze bleiben. Gesperrt, solange kein anderes Bild des Datensatzes anders aussieht als die Felder (Tooltip: „Nothing to save: all images of this dataset are drawn like this“). **Sichtbar** nur, wenn der Datensatz mehr als ein Bild in der Ansicht hat (nicht Mögliches ausblenden) **oder** die Ansicht ein angeheftetes Layer ist; bei einer Ansicht aus einem Layer bleibt das heutige „Save“ in dieses Layer erhalten und gilt zugleich für den Datensatz [A].
- **auto-scale**: misst die erste Szene des **angezeigten Bildes** (`fetchStatistics` mit dem Datensatz des Eintrags); das Ergebnis steht in den Feldern, „Apply“ wirkt wie oben.
- **Durchschalten** und **Dropdown** laden die Felder des neuen Bildes. Was in den Feldern stand und nicht angewendet war, fällt weg (Frage 7).
- **Eintritt:** Wie heute misst `enterFocus` einmal die Spanne des ersten angezeigten Bildes und füllt die Felder; die anderen Bilder zeigen beim Durchschalten ihre Darstellung (Vorgabe oder gespeichert), ohne zu messen [A].
- **Anheften:** Jedes angeheftete Bild nimmt die Darstellung mit, die es in der Ansicht zeigt (`restore.appliedRender`).
- Tooltips und Texte nur Englisch, kurz.

### 6.5 Leiste der Ansicht

Alle Teile liegen im bestehenden Feld `.viewer-controls` und ändern weder seine Breite noch seine Lage. Die Breite bestimmen weiter die zwei Zeilen mit den Knöpfen (#211).

```
Sentinel-2 L2A · 2025-07-29 · AOI crop            (eye)
[ Sentinel-2 L2A ▾ ]   ‹  2025-07-29 · S2A  ›          <- neu
Colormap [ — none — ▾ ]  vmin [ ]  vmax [ ]  [auto-scale]
                                              [Apply][Save]
[＋ Add to layers] [＋ Add all to layers] [⚙ Process] [‹ Change image] [✕ Clear]
```

- **Zeile `vc-steps`** zwischen Kopf und `vc-render`: links das Dropdown „Dataset“ (nur bei mehr als einem Datensatz), rechts die Pfeile mit Datum und Satellit (nur bei mehr als einem Bild im Datensatz). Ist der Datensatz der einzige und hat er ein Bild, fehlt die Zeile. Das Dropdown ist schmal und schneidet lange Namen mit „…“ ab, der volle Name steht im Tooltip. Im schmalen Fenster rutscht es über die Pfeile (eine Spalte).
- **„Add all to layers“** steht neben „Add to layers“, nur bei mehr als einem Bild insgesamt (§2). Sein Tooltip nennt die Zahl („Pin all 6 images …“).
- „Add to layers“ heftet das angezeigte Bild an (Tooltip „Pin this image into the layer manager“, wie heute).
- Satellit: Kurzform aus der Registry-Beschriftung (Frage 3), der volle Name im Tooltip.
- Farben, Abstände, Hell/Dunkel nach den bestehenden Klassen; neues CSS nur für die Zeile.

### 6.6 Karte und Anheften

- `MapView` übergibt `syncFocusRaster` nur die Einträge des angezeigten Bildes und dessen Datensatz (`dataset`, `groups`, `mosaics`). Alles andere (Stufen, Schlüssel, `restackAll`) bleibt aus NM4-59; es kommen **keine** neuen Marker.
- Beim Durchschalten gibt `syncFocusRaster` die Kacheln des alten Bildes über `retireDynamicMosaic`/`settleRetired` frei, sobald die neuen da sind [P]. Ob dabei die Basiskarte aufblitzt, wird beim Bau im Browser gemessen; bleibt es nicht sauber, nutzt das Durchschalten dasselbe Halten wie „Play“ (`Hold`, NM4-18) [A].
- **Mosaike:** `enterFocus` fragt wie heute alle Bilder auf einmal an (je Bild ein TileJSON; „Loading…“ bis alle da sind). Die Anfrage geht bei einem Bild eines anderen Datensatzes mit dessen Kennung. „Add all to layers“ braucht sie alle ohnehin (`pinWhenLoaded`).
- `addCurrentToLayers` bekommt zwei Wege: ein Bild (das angezeigte) und alle Bilder. Der Zuschnitt macht je Bild ein Layer, die ganze Szene ebenso (heute eines für alles); der Layer-Name wie Punkt 5. Alle Layer eines Aufrufs entstehen in einem `set`. Die Schlüssel `viewLayerId` und `layerOfView` bleiben: ein angeheftetes Bild, das alle Szenen der Ansicht hält, ist deren Layer; bei mehreren Bildern gibt es keines.
- Eine Ansicht aus einem Layer (`selectLayer`) ist ein Bild eines Datensatzes; die Zeile fehlt.

### 6.7 Folgen für andere Aufgaben

- **NM4-45** (Band): kommt nach NM4-53 und baut das Dropdown „Band“ in dieselbe Leiste. Die Zeile aus §6.5 steht über `vc-render`, das Dropdown „Band“ kommt in `vc-render`. Die Vorgabe „RGB“ aus §6.0.1 ist dort der erste Eintrag.
- **NM4-54** (Paket Ansicht): NM4-12 (Anheften ohne zweiten Klick) und NM4-25 (Quicklook nach Zuschnitt) fassen `addCurrentToLayers` und den Zuschnitt an; sie bauen auf dem Bild-Modell auf. NM4-24 (Rückfall „Szene für Szene“) sitzt innerhalb eines Bildes. Der Plan von NM4-54 muss danach „Bild“ statt „Ansicht“ sagen.
- **NM4-50** (gemergt): Die Regel, dass die Leiste der Auswahl nur auf den offenen Datensatz wirkt, wird für „Crop & merge to AOI“ und „View merged scenes“ aufgehoben (Nachtrag NM4-53 im Log), für Download und Verarbeitung bleibt sie (Frage 2).
- **NM4-18** (Zeitleiste/Abspielen): ändert nichts; die Zeitleiste ist im Ansichtsmodus nicht da.
- **NM4-43e / NM4-05b/06** (Panel): nicht berührt, außer dass `processFocusView` nur die `ids` eines Datensatzes übergibt.

### 6.8 Tests

Vitest, jeweils mit Gegenprobe gegen den Stand vor der Änderung:

- **`viewImages.test.ts`:** Bilder aus Haken über mehrere Gruppen und zwei Datensätze; Reihenfolge nach Datum und nach Abschnitt; Satelliten mit „/“; DEM ohne Datum und ohne Satellit; fehlendes `platform`; gleiche Szenen-ID in zwei Datensätzen (zweite abgelehnt mit Meldung); Gruppe ohne Szenen in der Ansicht; leere Eingabe.
- **Store (`store.view.test.ts`):** „Crop & merge“ über zwei Gruppen und zwei Datensätze legt vier Bilder an, das erste nach Punkt 2; Durchschalten, am Anfang und am Ende nichts; Dropdown wechselt zum ersten Bild des Datensatzes; nur ein Bild: keine Pfeile; nur ein Datensatz: kein Dropdown; Haken ändern sich nach dem Eintritt: die Ansicht bleibt.
- **Darstellung:** Apply wirkt nur auf das angezeigte Bild, andere Bilder zeigen die Vorgabe; Save wirkt auf alle Bilder des Datensatzes und nicht auf andere Datensätze; Apply gesperrt ohne Änderung; Save gesperrt ohne Unterschied und nicht da bei einem Bild; Apply, dann Wegschalten und Zurück: die angewendete Darstellung bleibt, ohne Save; „Clear“ und „Change image“ verwerfen alles, erneuter Eintritt zeigt die Vorgabe; Sentinel-2 beginnt als RGB ohne Colormap (§6.0.1).
- **Anheften:** „Add to layers“ heftet nur das angezeigte Bild mit seiner Darstellung an; „Add all to layers“ alle Bilder aller Datensätze in einem Schritt, in der Reihenfolge nach Punkt 5, alle oben; „Add all“ fehlt bei einem Bild; Namen mit Satellit.
- **Karte (`mapLayers.viewImage.test.ts`, `fixtures/liveMap.ts`):** nur die Ebenen des angezeigten Bildes liegen auf der Karte; nach dem Durchschalten die des neuen, nicht beider; Ansicht in Stufe 6 von „Results“, `restackAll` bewegt dabei nichts Überflüssiges; Wechsel der Basiskarte und `style.load` zeigen dasselbe Bild.
- **Komponenten (`ViewerControls.test.tsx`, `ViewBar.test.tsx`):** Zeile, Pfeile, Dropdown mit Tooltips, Ausblenden bei einem Eintrag, Tastatur ←/→ bei Fokus und keine Taste ohne Fokus; „Add all“ nur bei mehr als einem Bild; Zahl und Aufteilung in der Leiste der Auswahl; Download und Process bleiben beim offenen Datensatz.
- **Regeln aus #211/#221:** die bestehenden Tests (`resultsOnMap`, `layerDecoupling`, `ViewerControls`) bleiben grün; Durchschalten ändert Auge und Haken nicht.
- **Zweckfremd:** Eingabe außerhalb des Bereichs (`showImage` mit unbekanntem Schlüssel tut nichts), Bild, dessen Szenen verschwinden, Durchschalten bei ausgeblendeter Ansicht, Datensatz, der nicht mehr in der Registry steht.

### 6.9 Abnahme, Umfang und Schnitt

- **Browser** (Chromium/Playwright, `frontend/e2e/view-steps.cjs`, nach dem Muster von `layer-order.cjs`; erfundene Antworten, Vollfarben je Gruppe und Datensatz): Ottos Klickweg mit zwei Überflügen und einem DEM, Pfeile, Dropdown, Apply/Save, „Add to layers“/„Add all to layers“, Auge, Basemap-Wechsel; Hell/Dunkel, breit/schmal; Messung, ob beim Durchschalten die Basiskarte aufblitzt. Bilder nur im PR beschrieben.
- **Prüfanleitung für Otto** im PR: Sentinel-2 aus zwei Überflügen und DEM, „Crop & merge to AOI“, Zeile, Dropdown, Apply/Save, Anheften.
- Pflicht-Checks: `ruff check backend`, `pytest`, `lint-imports --config .importlinter`, `npm run lint`, `npx tsc -b`, `npx vitest run`.
- Log-Zeilen mit PR-Nummer; `docs/plans/nach-m4-backlog.md` bleibt unberührt; vor „fertig“ ist main geholt.
- **Umfang** (Schätzung): Modell und Store 250, Karte und Anheften 150, Leiste und CSS 200, Tests 500–600, Browserskript 250. Das sind etwa 1 300 Zeilen und damit weit über dem Richtwert von 400. Schnitt in Commits, wie bei NM4-59: (a) Modell `viewImages.ts` und `datasetId` am Eintrag, (b) Auswahl über Datensätze und Karte zeichnet ein Bild, (c) Zeile, Dropdown, Pfeile, (d) Darstellung je Bild mit Apply/Save, (e) „Add to layers“/„Add all to layers“, (f) Browserprüfung, Doku, Log. Frage 9: ein PR oder drei.

### 6.10 Fragen an Otto

Kurz beantwortbar: je Frage eine Nummer.

**Frage 1 — Welches Bild zuerst**
1. Das Bild der offenen Gruppe der Ergebnisliste, sonst das früheste. **(Empfehlung)**
2. Das früheste.
3. Das späteste.

**Frage 2 — Auswahl über Datensätze, wo sie wirkt**
1. „Crop & merge to AOI“ und „View merged scenes“ nehmen die Haken aller Datensätze; Download und Process in der Leiste der Auswahl bleiben beim offenen Datensatz (eigene Aufgabe für mehr). **(Empfehlung)**
2. Alle Knöpfe der Leiste über alle Datensätze (Download und Verarbeitung müssen dafür umgebaut werden; eigene Aufgabe vorher).

**Frage 3 — Satellit in der Zeile**
1. Kurzform „S2A“ aus der Beschriftung der Registry („Sentinel-2A“), mit einer kleinen allgemeinen Regel für „Sentinel-<n><Buchstabe>“; sonst die Beschriftung, wie sie ist; der volle Name im Tooltip. **(Empfehlung)**
2. Die Beschriftung der Registry unverkürzt („Sentinel-2A“).
3. Ein neues Registry-Feld für die Kurzform (Backend, Frage vorab).

**Frage 4 — „Process“ in der Leiste der Ansicht**
1. Die Szenen aller Bilder des angezeigten Datensatzes. **(Empfehlung)**
2. Nur die Szenen des angezeigten Bildes.

**Frage 5 — Reihenfolge von „Add all to layers“**
1. Datensatz für Datensatz, früheste zuerst; das späteste Bild des letzten Datensatzes steht danach oben. **(Empfehlung)**
2. Umgekehrt: das früheste steht oben.

**Frage 6 — Layer-Namen**
1. Satellit in der Kurzform hinten dazu („Sentinel-2 L2A · 2025-07-29 · 32UQD · S2A“). **(Empfehlung)**
2. Namen wie heute.

**Frage 7 — Felder beim Durchschalten**
1. Was in den Feldern stand und nicht angewendet war, fällt weg; die Felder zeigen das neue Bild. **(Empfehlung)**
2. Die Felder behalten, was getippt wurde (z. B. eine Spanne, die dann Bild für Bild angewendet wird); „Apply“ wirkt dann beim neuen Bild als frei.

**Frage 8 — Das Wort „RGB“**
1. Nicht zu sehen in dieser Aufgabe; „RGB“ ist die Vorgabe der Darstellung (Echtfarben, keine Colormap) und steht später als erster Eintrag im Dropdown „Band“ (NM4-45). **(Empfehlung)**
2. Das Feld Colormap zeigt bei Bildern mit drei Bändern „RGB“ statt „— none —“ und ist gesperrt (Tooltip „True colour: no colormap“).

**Frage 9 — Schnitt**
1. Ein PR in dieser Session, je Teil eigener Commit (a–f, §6.9), Umfang etwa 1 300 Zeilen. **(Empfehlung)**
2. Drei PRs hintereinander: (a+b), (c+d), (e+f), je unter etwa 500 Zeilen; jeder auf dem vorigen.

**Frage 10 — Szene mit gleicher ID in zwei Datensätzen**
1. Die zweite wird nicht aufgenommen, eine Meldung sagt es. **(Empfehlung, kommt mit heutigen Datensätzen nicht vor)**
2. Die Ansicht schlüsselt `downloaded` künftig nach Datensatz und ID (trifft Layer, Download und Verarbeitung; eigene Aufgabe vorher).

### 6.11 Grenzen dieses Plans

Keine Messung im Browser, kein Backend, keine neue Abhängigkeit. Der Code beginnt erst, wenn Otto den Plan freigibt und einen freien Frontend-Platz meldet.

## 7. Freigabe (Otto, 31.10.2026, zu #257)

| Frage | Antwort | Folge für §6 |
|---|---|---|
| 1, 2, 3, 4, 5, 6, 7, 10 | Option 1, wie empfohlen | wie §6 |
| 8 | Option 1 mit Zusatz: Bei Bildern mit drei Bändern (RGB) wird das Feld Colormap **nicht angezeigt** (nicht Mögliches ausblenden), nicht gesperrt. Das Wort „RGB“ kommt mit dem Dropdown „Band“ (NM4-64 für Vorschau und Ergebnis, NM4-45 für die Ansicht). | §6.4: Feld Colormap fehlt bei drei Bändern; vmin und vmax rücken nach |
| 9 | Option 1: ein PR, je Teil eigener Commit | Commits (a)–(f) wie in §6.9 |

**Hinweis Otto:** NM4-64 (RGB, Registry-Feld `earthx:true_color`) läuft parallel; wer als Zweiter fertig wird, holt main und übernimmt das Feld statt eigener Annahmen. Stand beim Bau: NM4-64 ist nicht in main. „Drei Bänder“ liest `datasets.ts::showsColormap` deshalb aus den drei Spannen (`rescale`) der Standarddarstellung der Registry; das ist die eine Stelle, die NM4-64 durch das Feld ersetzt.

## 8. Umsetzung (31.10.2026, PR #257)

Ein PR mit je einem Commit pro Teil (Antwort 9).

| Teil | Was | Dateien |
|---|---|---|
| a | **Modell der Bilder.** `viewImages.ts` bildet aus den Szenen der Ansicht und den Abschnitten der Ergebnisse die Bilder (Datensatz, Gruppe, Szenen, Datum, Satelliten), nach Abschnitt und Tag geordnet. Jeder Eintrag von `downloaded` trägt seinen Datensatz (`DownloadedInfo.datasetId`). Satellit: Beschriftung aus dem Registry-Filter `platform`, Kurzform „S2A“ nach `Sentinel-<n><Buchstabe>`, sonst unverändert. | `viewImages.ts`, `types.ts`, Testfixtures |
| b | **Auswahl über Datensätze, die Karte zeichnet ein Bild.** `enterFocus` nimmt die Haken aller Abschnitte (`viewSelectionFrom`), liest je Datensatz die Standarddarstellung und beginnt mit dem Bild der offenen Gruppe, sonst dem frühesten des offenen Datensatzes (`firstImageOf`). `showImage`, `stepImage`, `chooseViewDataset`. `loadMosaics`, `overlaysOfEntries`, `pinWhenLoaded`, `autoStretch` und `MapView` folgen dem Datensatz des Eintrags; die Karte zeichnet nur das angezeigte Bild (`shownViewOf`), ohne neue Marker. „Process“ der Ansicht nimmt die Szenen des angezeigten Datensatzes und macht ihn zum offenen. Leiste der Auswahl: Zahl und Aufteilung über alle Datensätze, Download und Process beim offenen. | `store.ts`, `MapView.tsx`, `ViewBar.tsx`, `App.tsx`, `processingStore.ts` |
| c | **Zeile der Schritte.** Dropdown „Dataset“ (nur bei mehr als einem Datensatz), Pfeile mit Datum und Satellit (nur bei mehr als einem Bild im Datensatz), ausgegraut an den Enden, ←/→ bei Fokus in der Zeile; der Kopf nennt das angezeigte Bild. | `ViewerControls.tsx`, `index.css` |
| d | **Darstellung je Bild und je Datensatz.** `viewLooks` und `savedLooks` leben nur so lange wie die Ansicht; „Apply“ gilt dem angezeigten Bild, „Save“ allen Bildern des Datensatzes und erscheint nur bei mehr als einem Bild (oder bei der Ansicht eines Layers, dort auch wie bisher ins Layer). Bei drei Bändern fehlt das Feld Colormap. | `store.ts`, `ViewerControls.tsx`, `datasets.ts`, `render.ts`, `index.css` |
| e | **Anheften.** „Add to layers“ das angezeigte Bild, neu „Add all to layers“ alle Bilder in einem Schritt (Datensatz für Datensatz, früheste zuerst, das letzte oben); Name `Datensatz · Gruppe · Satellit`; jedes Layer mit der Darstellung seines Bildes. | `store.ts`, `ViewerControls.tsx`, `index.css` |
| f | **Browserprüfung, Doku, Log.** | `e2e/view-steps.cjs`, Doku |

### 8.1 Auslegungen (Vorschlag, gelten bis Otto widerspricht)

1. **Ein Layer je Bild**, auch bei „View merged scenes“ (ganze Szene): heute war es dort ein Layer für alles. Das folgt aus „Add to layers = nur das angezeigte Bild“.
2. **Haken sind Szenen-IDs.** Ein Haken gilt für die Szene jedes Datensatzes mit dieser ID; die Ansicht nimmt die Szene des ersten Datensatzes und sagt es (Frage 10, Option 1). Mit heutigen Datensätzen kommt das nicht vor.
3. **Die Spanne, die beim Öffnen gemessen wird, steht wie bisher in den Feldern** und nicht in der Darstellung. Weil sie von der Vorgabe der anderen Bilder abweicht, ist „Save“ gleich nach dem Öffnen frei und würde diese Spanne für alle Bilder des Datensatzes übernehmen. Die anderen Bilder zeigen beim Durchschalten ihre Darstellung (Vorgabe oder gespeichert), ohne zu messen.
4. **Zeile ohne Datum:** Ein Bild ohne Zeitpunkt (DEM) zeigt den Namen seiner Gruppe statt des Datums.
5. **Ansicht eines Layers** (`selectLayer`): ein Bild, keine Zeile; „Save“ wie bisher ins Layer und zugleich für den Datensatz.
6. **Download und Process der Leiste der Auswahl** sind gesperrt, solange im offenen Datensatz nichts angehakt ist (Grund im Tooltip); vorher hätten sie auf die offene Gruppe zurückgegriffen.
7. **Die Leiste der Auswahl** nennt die Zahl über alle Datensätze und die Aufteilung im Tooltip („Sentinel-2 L2A 2 · Copernicus DEM 1“).

### 8.2 Tests

- `viewImages.test.ts` (neu): Bilder aus Gruppen und Datensätzen, Ordnung, Satelliten, DEM ohne Datum, Szenen ohne Gruppe, leere Eingabe, Schlüssel.
- `store.view.test.ts` (neu, 25): Auswahl über Datensätze, erstes Bild, Durchschalten ohne Umlauf, Datensatz wählen, unbekannter Schlüssel, außerhalb einer Ansicht, Auge und Haken bleiben, Messung im Datensatz des Bildes, gleiche ID, Datensatz ohne Registry-Eintrag, Darstellung (Apply nur das Bild, Save alle Bilder des Datensatzes und keinen anderen, nur für die Dauer der Ansicht, Anheften mit der Darstellung des Bildes).
- `components/ViewerControls.steps.test.tsx` (neu, 24): Zeile, Dropdown und Pfeile samt Ausblenden, Tastatur, Auge unverändert, Save (Sichtbarkeit, Sperre mit Grund, Wirkung), kein Colormap-Feld bei drei Bändern, „Add all to layers“, Namen, Platz oben.
- `components/ViewBar.test.tsx` erweitert: Zahl und Aufteilung, Download und Process beim offenen Datensatz.
- Angepasst, weil sich das Verhalten ändert (Nachtrag NM4-53): `store.test.ts`, `store.stack.test.ts`, `store.mosaic.test.ts` („Add to layers“ heftet das angezeigte Bild, „Add all“ jedes Bild), `store.ticks.test.ts` (ein Zuschnitt nimmt die Haken aller Datensätze der Szenen ab, aus denen er besteht).
- **Gegenprobe:** Die neuen und geänderten Tests gegen den Stand von main: 58 von 185 schlagen fehl, alle im Verhalten dieser Aufgabe.
- Browser (Chromium 153, echtes MapLibre, erfundene Antworten, `e2e/view-steps.cjs`): hell/dunkel × breit/schmal grün: erstes Bild die offene Gruppe, „‹“/„›“ zeigen den früheren und den späteren Überflug (Farbe in der Mitte der Karte), Pfeile an den Enden ausgegraut, ←/→ bei Fokus, Dropdown zeigt das DEM, Colormap-Feld nur dort, Apply gilt dem Bild, „Add to layers“ 1 Layer, „Add all to layers“ 4 Layer mit Satellit im Namen, alles innerhalb des Feldes. Dabei fiel auf, dass das Dropdown ungestaltet war; es hat jetzt die Gestalt der anderen Felder. Eine Meldung der Statusleiste ragt im schmalen Fenster 6 px über den Rand; das ist nicht Teil dieser Aufgabe und im Skript ausgenommen.

### 8.3 Prüfanleitung für Otto (Stand nach §10)

1. Sentinel-2 über zwei Überflüge suchen (zwei Tage), dazu das Copernicus DEM; in beiden Datensätzen Szenen anhaken, eine AOI zeichnen.
2. „Crop & merge to AOI“: Die Karte zeigt den Überflug der offenen Gruppe. Die Box ist breit und besteht aus der Kopfzeile und zwei Zeilen. Kopfzeile von links: Titel (ohne Datum), kleines Dropdown „Sentinel-2 L2A / Copernicus DEM“, `‹ 2025-07-29 ›` (nur das Datum, runde Pfeile) und das Auge. Zeile 1: Colormap, vmin, vmax, „auto-scale“ mit „Apply“, „Apply to all“. Zeile 2: alle Knöpfe in einer Reihe („Add to layers“, „Add all to layers“, „Process“, „Change image“, „Clear“).
3. „‹“ und „›“: Der frühere bzw. spätere Überflug erscheint; am Ende ist der Pfeil ausgegraut. Mit dem Fokus auf einem Pfeil schalten ←/→ ebenso. Der Satellit steht im Tooltip des Datums.
4. Dropdown auf „Copernicus DEM“: Das DEM erscheint; die Box „Colormap“ steht an derselben Stelle (mit „terrain“), bei Sentinel-2 steht in ihr „RGB“ und nichts weiter zur Wahl. Datum und Pfeile sind da, die Pfeile ausgegraut, wenn der Datensatz nur ein Bild hat (Tooltip „There is only one image“). Gibt es nur einen Datensatz, fehlt das Dropdown.
5. Bei Sentinel-2 vmin/vmax ändern, „Apply“: nur dieser Überflug ändert sich; „›“ zeigt den anderen noch mit der Vorgabe. „Apply to all“ (ist immer da, beim DEM und bei einem Bild ausgegraut mit Grund im Tooltip): Jetzt zeigen alle Überflüge von Sentinel-2 die Werte, das DEM nicht.
6. „Add to layers“: ein Layer, der angezeigte Überflug. „Add all to layers“: je Bild ein Layer, das letzte Bild des letzten Datensatzes steht oben; der Name nennt Datum und Satellit.
7. „Clear“, dann wieder „Crop & merge to AOI“: Die Vorgabe gilt wieder (RGB ohne Colormap, nichts gespeichert).
8. Auge der Ansicht aus und durchschalten: bleibt aus. Dunkel und hell, schmales Fenster (hier bricht die Box um: Dropdown und Datum unter den Titel, die Knöpfe zu zwei je Zeile).

## 9. Durchsicht Otto nach dem Browsertest (31.10.2026, zu #257)

Nachtrag NM4-53; ersetzt §6.5 (die Zeile unter dem Kopf) und die Regel zu „Save“ in §6.4 und §8, Originaltexte bleiben stehen.

| Nr. | Wunsch | Umsetzung |
|---|---|---|
| 1 | „Save“ in der Ansicht heißt **„Apply to all“**. Der Knopf ist immer da, auch beim DEM und bei einem Datensatz mit nur einem Bild; dann ist er gesperrt (ausgegraut, Grund im Tooltip). Wirkung wie bisher: die Darstellung für alle Bilder des Datensatzes in der Ansicht. | `ViewerControls.tsx`: keine Bedingung mehr für das Erscheinen. Gründe im Tooltip: „Nothing to apply to all: this dataset has only one image in the view“, „…: every image of this dataset is drawn like this“, bei der Ansicht eines Layers „…: the layer is saved as it is drawn“. Wo der Knopf frei ist, sagt der Tooltip „Draw every image of this dataset with these values“ (bei einem Layer zusätzlich „and keep them for this layer“). Das „Save“ der Ergebnisansicht (`ResultControls`) bleibt, wie es ist. |
| 2 | Der Kopf der Ansicht hat kein Datum (es ist über die Pfeile wählbar). Im Namen angehefteter Layer bleibt das Datum. | Titel und Tooltip des Titels ohne Datum; der Name des Layers bleibt `Datensatz · Gruppe · Satellit`, die Gruppe trägt das Datum. |
| 3 | Die Ansicht wird niedriger: Die eigene Zeile und das Dropdown entfallen. In der Kopfzeile zwischen Titel und Auge ein kleines Dropdown für den Datensatz, daneben das Datum mit ‹ ›. Gibt es nur einen Datensatz bzw. nur ein Bild, entfällt der jeweilige Teil. Die Regeln zur Breite des Kopfs gelten weiter. | Kopfzeile: Titel, Dropdown „Dataset“ (nur bei mehr als einem Datensatz), `‹ Datum · Satellit ›` (nur wo der angezeigte Datensatz mehr als ein Bild hat), Auge. Der Titel gibt nach: Er wird mit „…“ gekürzt, der volle Text steht im Tooltip. Im schmalen Fenster rutschen Dropdown und Datum unter den Titel, das Auge bleibt beim Titel; die Ansicht bleibt in jedem Fall nicht breiter als die Knopfzeilen. |

**Auslegung (Vorschlag, gilt bis Otto widerspricht):** Hat ein Datensatz nur ein Bild, fehlt mit den Pfeilen auch das Datum; es steht dann nirgends in der Ansicht (der Name eines angehefteten Layers hat es). Soll es als Text ohne Pfeile bleiben, ist das eine Zeile in `ViewerControls.tsx`.

**Tests:** `ViewerControls.test.tsx` (kein Datum im Titel und im Tooltip, Knopfgruppe „auto-scale“, „Apply“, „Apply to all“, „Apply to all“ immer da und beim Layer mit Grund gesperrt, CSS-Vertrag des Kopfs); `ViewerControls.steps.test.tsx` (Dropdown und Datum mit Pfeilen in der Kopfzeile in dieser Reihenfolge, keine eigene Zeile, Ausblenden bei einem Datensatz bzw. einem Bild, „Apply to all“ auch beim DEM und bei einem Bild gesperrt mit Grund, Wirkung auf den Datensatz). Browser: `e2e/view-steps.cjs` prüft die Reihenfolge der Kopfzeile, das fehlende Datum im Titel, „Apply to all“ (gesperrt beim DEM, wirksam beim Datensatz mit mehreren Bildern) und dass alles innerhalb der Ansicht bleibt; hell/dunkel × breit/schmal grün.

## 10. Zweite Durchsicht Otto (1.11.2026, zu #257, „ist hässlich“)

Nachtrag NM4-53; ersetzt in §9 die Regel zum Datum bei einem Bild und in §7/§8 das Ausblenden des Feldes Colormap bei drei Bändern (Antwort 8, Zusatz); Originaltexte bleiben stehen.

| Wunsch (Otto) | Umsetzung |
|---|---|
| Die Ansichtsbox ist nur **zwei Boxen hoch plus Kopfzeile**; das Menü eher länger als höher. | Die Box ist breiter (`--cell` 46 px, etwa 670 px) und hat die Kopfzeile und zwei Zeilen: Zeile 1 Colormap, vmin, vmax, „auto-scale“ mit „Apply“, „Apply to all“; Zeile 2 alle Knöpfe in einer Reihe (vier, mit mehreren Bildern fünf gleich breite). Unter 600 px bricht sie wie vorher um. |
| **Sentinel-2 hat eine Box für die Colormap**, in der nur „RGB“ wählbar ist; die Knöpfe sind für jeden Datensatz **an derselben Stelle**. | Die Box „Colormap“ ist immer da. Bei Bildern mit drei Bändern steht in ihr „RGB“ als einzige Wahl (Tooltip „True colour: three bands, no colormap“); sie bleibt an derselben Stelle wie bei den anderen Datensätzen, vmin, vmax und die Knöpfe wandern nicht mehr. `showsColormap` (`datasets.ts`) bleibt die eine Stelle, die NM4-64 durch `earthx:true_color` ersetzt. |
| Im **Szenenschalter nur das Datum**, nicht der Sensor. | Der Schalter zeigt nur das Datum; der Satellit steht im Tooltip. Der Name angehefteter Layer behält Datum und Satellit. |
| Bei **nur einer Szene** steht das Datum trotzdem da, die Pfeile sind **ausgegraut**. | Der Schalter ist immer da; bei einem Bild des Datensatzes sind beide Pfeile ausgegraut (Tooltip „There is only one image“). Das ersetzt die Auslegung aus §9, dass dann auch das Datum fehlt. Ein Bild ohne Zeitpunkt (DEM) zeigt den Gruppennamen. |
| Die **Pfeiltasten schöner**. | Runde Knöpfe mit einem als Linie gezeichneten Pfeil (`Chevron.tsx`, folgt der Farbe, in beiden Themen gleich stark), Rahmen und Hover wie die übrigen Felder, ausgegraut mit gedämpfter Farbe. |

**Tests:** `ViewerControls.steps.test.tsx` (Datum auch bei einem Bild, Pfeile ausgegraut mit Grund und ohne Wirkung, nur das Datum im Schalter und der Satellit im Tooltip, Box „Colormap“ mit „RGB“ als einziger Wahl und an derselben Stelle wie bei den anderen Datensätzen), `ViewerControls.test.tsx` (CSS-Vertrag: Zeile 2 in einer Reihe, vier oder fünf gleich breite Knöpfe, die Box breit genug für fünf Knöpfe und breiter als hoch, Umbruch unter 600 px). Browser: `e2e/view-steps.cjs` liest zusätzlich die Lage der Box „Colormap“ bei Sentinel-2 und beim DEM (gleich), die ausgegrauten Pfeile beim DEM, dass die Knöpfe der zweiten Zeile in einer Reihe liegen, die Box aus Kopfzeile und zwei Zeilen besteht und breiter als hoch ist; hell/dunkel × breit/schmal grün.
