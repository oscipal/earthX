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

## 6. Plan (30.10.2026; Stufe B, kein Produktivcode)

Kennzeichnung: [P] im Code geprüft, [M] im echten Browser gemessen, [A] Auslegung bzw. Vorschlag von Claude.

### 6.0 Kurzfassung

- **Fehler (§2.1):** Ottos Klickweg ist im echten Browser (Chromium, echtes MapLibre, synthetische Szenen) in 22 Läufen **nicht** nachstellbar: „Show results“ bringt die offene Gruppe jedes Mal über den Job-Layer zurück (§6.1). Die Ursache ist damit **nicht belegt**; Frage 1 bittet um die fehlenden Umstände. Gefunden wurde dabei eine **andere Abweichung**: In einer offenen Ansicht liegt eine angehakte Szene einer anderen Gruppe über der offenen Gruppe, entgegen §2.5 [M].
- **Kern des Entwurfs:** Im Layer-Manager steht eine Zeile „Results“ zwischen den angehefteten Layern. Ihr Auge ist der bisherige Schalter `resultsOnMap`, ▲/▼ verschieben sie. Auf der Karte gibt es **eine** Ebenenfolge, berechnet aus Liste und Platz von „Results“; sechs der sieben Marker entfallen (§6.6).
- **Innerhalb von „Results“** gilt die feste Folge aus §3.2 (§6.4). Die Ausnahmen aus §2.7 bleiben, wie sie im Store schon stehen (§6.5).
- **Schnitt:** zwei PRs in dieser Session (Frage 8): erst die eine Ebenenfolge ohne sichtbare Änderung außer der Korrektur, dann die Zeile „Results“ mit Auge.

### 6.1 Nachstellung des Fehlers [M]

Werkzeug: ein Playwright-Skript nach dem Muster von `frontend/e2e/layer-order.cjs`. Der Dev-Server läuft ohne Backend, die Antworten sind erfunden: drei Szenen gleicher Fläche in drei Gruppen, je eine Vollfarbe (rot = Gruppe 0, grün, blau), dazu ein Job-Layer in Gelb, angeheftet wie `processingStore.ts::showResultOnMap` (`pinDerivedLayer`, `derived: 'result'`, oben in der Liste). Gemessen wird die Farbe in der Kartenmitte. Ablauf wie Ottos Klickweg: Gruppe 0 offen, nichts angehakt → Job anheften → viermal „Hide results“ / „Show results“ (`toggleResultsOnMap`), einmal mit Warten auf Gelb zwischen den Klicks, einmal ohne.

| Variante | Ergebnis |
|---|---|
| Datensatz mit Quicklook (Bild) bzw. ganze Szene als Kacheln, je mit und ohne Warten | ok |
| Quicklooks 1,5 s verzögert (nicht im Cache) | ok |
| Job-Kacheln 3 s verzögert, Umschalten vor dem Laden (Karte nie `idle`) | ok |
| vorher Gruppenwechsel 0 → 1 → 0 ohne Warten, Quicklooks 0,8 s und Job 3 s verzögert | ok |
| Ansicht offen („full resolution“ einer anderen Szene), Ergebnisse darüber eingeblendet; auch verzögert und mit Gruppenwechsel | ok |
| Szene der offenen Gruppe angehakt, im Browse-Modus und in der Ansicht | ok |
| Szene einer **anderen** Gruppe angehakt, Browse-Modus | ok (offene Gruppe oben) |
| Szene einer **anderen** Gruppe angehakt, **Ansicht offen** | **Abweichung:** die angehakte Szene liegt über der offenen Gruppe |

Ursache der Abweichung [P]: In einer Ansicht zeichnet `mapLayers.ts::syncResultsOverlay` die Ergebnisse. Die nicht angehakten Szenen der offenen Gruppe legt es unter die Ansicht (`results-top`, Regel vom 27.10.2026), die angehakten Szenen aller Gruppen über sie (`tickedPlace` → `open-base`). Die Regel „offene Gruppe über angehakten Szenen anderer Gruppen“ (NM4-55) gilt nur im Browse-Modus (`syncBrowseMosaic`). Die neue Ebenenfolge (§6.4) behebt das, weil beide Wege dieselben Stufen benutzen.

Was der Code für Ottos Klickweg als Ursache hergäbe, ohne dass es sich zeigen ließ [P]:
- Zwei getrennte Zeichenwege für dieselben Ergebnisse (`syncBrowseMosaic` mit zwei Id-Bänken `m-`/`n-` und verzögertem Abbau, `syncResultsOverlay` mit `res-`), dazu `tickedPlace`, das den Platz eines spät ankommenden Bildes nach den Nachbarn wählt, die *gerade* auf der Karte liegen. Die Lage hängt damit von der Reihenfolge ab, in der Bilder ankommen.
- Die Lage gegenüber den angehefteten Layern hängt an sieben Markern (`layers-top` … `overlays-base`), die nur `ensureBaseLayers` beim ersten Laden setzt.

Der Entwurf ersetzt beides durch eine Ebenenfolge, die nur vom Zustand abhängt und nach jeder Änderung vollständig hergestellt wird (§6.6). Ottos Klickweg wird als Browserprüfung und als Test mit Gegenprobe Teil der Abnahme (§6.9). Lässt er sich mit Ottos Angaben (Frage 1) nachstellen, kommt der Befund vor dem Code in diesen Plan.

### 6.2 Stand im Code [P]

Ebenen der App von unten nach oben (`mapLayers.ts::ensureBaseLayers`, `mapStyles.ts::composeStyle`):

| Platz | Was | gesetzt von |
|---|---|---|
| über der Basiskarte | Relief-Schattierung (Overlay) | `composeStyle` |
| unter `layers-top` | angeheftete Layer in Listenfolge | `syncLayers`/`restack` |
| unter `results-top` | Quicklooks der Ergebnisse unter einer Ansicht | `syncResultsOverlay` |
| unter `ticked-top` | Ansicht (Kacheln, Quicklook darunter) | `syncFocusRaster` (`beforeAoi`) |
| unter `open-base` | angehakte Szenen anderer Gruppen | `tickedPlace` |
| unter `open-ticked-base` | übrige Quicklooks (Browse-Modus) | `openRestTop` |
| unter `preview-base` | angehakte Szenen der offenen Gruppe | `tickedPlace` |
| unter `overlays-base` | Live-Vorschau des Processing-Panels | `syncPreview` |
| unter `aoi-fill` | Beschriftung, Gradnetz | `composeStyle` |
| darüber | AOI, Coverage, gelbe Umrisse (`mosaicsel-line`), Zeichenwerkzeug | `ensureBaseLayers`, terra-draw |

- „Results“ liegt damit heute immer über allen angehefteten Layern. Eine Ausnahme ist die Ansicht, die ein angehefteter Layer selbst zeichnet (`viewLayer.ts`): Sie liegt am Platz dieses Layers.
- Sichtbarkeit: `store.resultsOnMap` (im Browser gespeichert), gelesen nur in `mapResults.ts::resultsOnMapOf`. Ausnahmen im Store: Suche zeigt (`runSearch`, `findSceneByName`), Crop verbirgt (`enterFocus`), Anhaken zeigt (`ticking`). Seit NM4-18 zeigt auch „Play“ die Ergebnisse (`TimeSlider.tsx`, Otto 30.10.2026).
- Die angehefteten Layer werden nicht gespeichert; die Liste lebt nur in der Sitzung.

### 6.3 Modell: „Results“ in der Liste

- Im Store kommt `resultsAt` dazu: die Zahl der angehefteten Layer **über** „Results“ (0 = ganz oben). Die Liste `layers` bleibt, wie sie ist. Der Layer-Manager zeichnet `layers[0 … resultsAt)`, dann die Zeile „Results“, dann den Rest.
- ▲/▼ an „Results“ ändern `resultsAt` um 1. ▲/▼ an einem Layer direkt neben „Results“ tauscht ihn mit „Results“ (gleiche Funktion `moveEntry` für alle Zeilen).
- **Neuer Layer** (`addCurrentToLayers`, `pinDerivedLayer`, Frage 3): Er kommt wie heute an die Spitze der angehefteten Layer. Liegt „Results“ ganz oben, bleibt es dort, und der neue Layer liegt direkt darunter (wie heute). Liegt „Results“ tiefer, bleibt es unter denselben Layern (`resultsAt + 1`).
- Entfernen eines Layers über „Results“: `resultsAt − 1`.
- „Clear search results“ setzt `resultsAt` auf 0. Eine neue Suche lässt den Platz, wie er ist (Frage 3).

### 6.4 Reihenfolge innerhalb von „Results“ (fest nach §3.2) [A]

Von oben nach unten, als Stufen eines Blocks:

1. gelbe Umrisse der angehakten Szenen (`mosaicsel-line`); Auslegung: Umrisse gehören laut §3.1 zu „Results“ und liegen dort ganz oben.
2. Live-Vorschau des Processing-Panels.
3. angehakte Szenen der offenen Gruppe (bzw. des gespielten Zeitschritts), die zuletzt angehakte oben.
4. übrige Quicklooks der offenen Gruppe.
5. angehakte Szenen anderer Gruppen und Datensätze, die zuletzt angehakte oben.
6. Ansicht (Kacheln, Mosaik, Quicklook darunter), innen wie heute (erste Szene oben, `stackLikeView`).

Folge [A]: Mit eingeblendeten Ergebnissen liegt die offene Gruppe in einer Ansicht **über** der Ansicht. Das ersetzt die Regel vom 27.10.2026 („die Ansicht liegt über den Quicklooks der Ergebnisse“, #211) und braucht einen Nachtrag im Log. Weil „Crop“ die Ergebnisse ausschaltet, ändert sich nach einem Zuschnitt nichts, bis Otto das Auge wieder einschaltet. Frage 4 bestätigt das.

Die Ansicht eines angehefteten Layers (`viewLayer.ts`, unverändert) liegt weiter am Platz dieses Layers, nicht in „Results“.

### 6.5 Auge und Ausnahmen (fest nach §2.7)

- Das Auge der Zeile „Results“ **ist** `resultsOnMap`; es schaltet, was es heute schaltet: Quicklooks, angehakte Szenen, Umrisse. Die Store-Aktion `toggleResultsOnMap` bleibt; die Ausnahmen bleiben unverändert im Store (Suche, Crop, Anhaken). Das Auge zeigt also nach „Crop“ zu und nach „Search“ offen.
- **Ansicht und Live-Vorschau** liegen in „Results“, behalten aber ihre eigenen Schalter („Hide image“ der Ansicht; die Vorschau gehört zum offenen Panel). Grund [A]: „Crop“ schaltet das Auge aus (§2.7). Schaltete es auch die Ansicht aus, zeigte ein Zuschnitt nichts. Frage 2.
- „Play“ schaltet das Auge ein (NM4-18, Otto 30.10.2026). Das ist eine vierte Ausnahme neben §2.7 und bleibt [A], Frage 2.
- Der Knopf „Hide results / Show results“ im Kopf der Ergebnisliste wird zum selben Auge (Eye-Symbol, gleicher Zustand, Tooltip „Hide results on the map“ / „Show results on the map“). Der veraltete Tooltip („ticked scenes still show“, vor #221) entfällt damit. Frage 5.

### 6.6 Eine Ebenenfolge auf der Karte [A]

- **Ein Marker bleibt:** `overlays-base`. Jedes Raster der App und die Umrisse liegen darunter; Beschriftung und Gradnetz liegen darüber (Overlays, `composeStyle` setzt sie vor `aoi-fill`), darüber AOI und Zeichnung. `layers-top`, `results-top`, `ticked-top`, `open-base`, `open-ticked-base` und `preview-base` entfallen.
- **Jede Ebene bekommt beim Hinzufügen einen Schlüssel:** Platz in der Liste (Layer bzw. „Results“), Stufe in „Results“ (§6.4), Rang in der Stufe (Index der Szene in den Haken, Nummer des Platzierens für die Ansicht, Index des Overlays für einen Layer). Die Schlüssel stehen in einer Tabelle in `mapLayers.ts`.
- **`restackAll(map)`** sortiert alle Ebenen der App nach Schlüssel und legt sie, nur wenn die Folge abweicht, von oben nach unten unter `overlays-base` (`moveLayer`, lädt keine Kachel nach, wie heute `restack`). Jede Sync-Funktion ruft es am Ende auf, ebenso jedes Bild, das später ankommt. Damit hängt die Lage nicht mehr davon ab, was beim Ankommen eines Bildes schon auf der Karte liegt; `tickedPlace`, `topOfAll`, `otherTickedTop`, `openRestTop`, `underTheView`, `aboveAll`, `beforeAoi` und `previewTop` entfallen.
- **Zwei Wege bleiben zwei Funktionen, aber mit denselben Stufen:** `syncBrowseMosaic` (Browse, mit Bänken und Halten beim Abspielen, NM4-18) und `syncResultsOverlay` (über einer Ansicht). Zusammenlegen wäre eine weitere Vereinfachung, ändert aber das Abspielen; nicht in dieser Aufgabe [A].
- **`style.load`:** Beim ersten Laden setzt `ensureBaseLayers` nur `overlays-base` und die festen Ebenen, alle Syncs folgen, dann `restackAll`. Beim Wechsel der Basiskarte trägt `composeStyle` die Ebenen der App in ihrer Folge mit (heute schon); ein Test hält fest, dass die Folge danach gleich ist und `restackAll` nichts bewegt.
- **Umrisse:** `mosaicsel-line` kommt aus dem Bereich über der AOI in die oberste Stufe von „Results“. Die Coverage-Ebenen bleiben, wo sie sind (gehören nicht zu „Results“).

### 6.7 Zeile im Layer-Manager [A]

- Gleiches Raster wie die übrigen Zeilen (neun Plätze, `LayerRow`): Auge, Name „Results“, ▲, ▼. Deckkraft, Process, Download, Hinweis und ✕ bleiben leere Plätze (`Slot`). Kein Colormap-/Skala-Menü (§3.6). „Clear search results“ bleibt in der Ergebnisliste.
- Tooltip des Namens: „Search results, the view and the processing preview. Move to change what lies above.“
- Keine Zahl in der Zeile (die Ergebnisliste zeigt sie schon); Frage 6.
- Die Zeile erscheint, sobald es Suchergebnisse gibt, und verschwindet mit „Clear search results“ (§3.5). Eine Ansicht oder Vorschau ohne Suchergebnisse (z. B. aus einem angehefteten Layer) liegt am Platz, den „Results“ hätte (`resultsAt`, nach „Clear“ oben), ohne Zeile; Frage 7.
- Die Zahl im Kopf des Layer-Managers zählt weiter nur die angehefteten Layer; der Hinweis „No layers yet …“ erscheint nur ohne Layer und ohne „Results“.

### 6.8 Folgen für andere Aufgaben (§3.8)

- **NM4-53** (Zeitschritte der Ansicht): Die Zeitschritte sind Stufe 6 von „Results“. „Add to layers“ und „Add all to layers“ heften nach §6.3 an. Plan §3 Punkt 8 („Show/Hide … bleiben“) heißt danach „Auge von ‚Results‘“.
- **NM4-54:** NM4-12 (Anheften ohne zweiten Klick) heftet nach §6.3 an. NM4-24 (Rückfall „Szene für Szene“) und NM4-25 (Quicklook nach Zuschnitt) ordnen innerhalb von Stufe 6 über den Rang, ohne eigene Marker. NM4-45 ist nicht betroffen. Wo der Plan „Show/Hide“ sagt, gilt das Auge.
- **NM4-43e** (Panel-Umbau): Die Live-Vorschau bleibt Stufe 2; „Pin preview“ heftet nach §6.3 an. Sonst keine Folge.
- **DS-03b** (Wolken in der AOI, Oberfläche): ändert den Kopf der Ergebnisliste; der Knopf dort ist nach NM4-59 das Auge (§6.5). Nicht gleichzeitig mit dem zweiten PR dieser Aufgabe.
- **Overlays** (Beschriftung, Gradnetz, Relief) bleiben feste Plätze, wie heute, im Menü „Basemap“ (Frage 9).

### 6.9 Tests und Abnahme

Vitest mit `fixtures/liveMap.ts` (Ebenenfolge), Komponententests für Layer-Manager und Ergebnisliste; jeweils mit Gegenprobe gegen den Code vor der Änderung.

- **Ottos Klickweg:** Gruppe offen, nichts angehakt, Job-Layer anheften, Auge aus, Auge an: die offene Gruppe liegt über dem Job-Layer; viermal hintereinander und mit spät ankommenden Bildern. Gegenprobe: „Results“ unter den Job-Layer verschoben → der Job-Layer liegt oben.
- **Lage per Reihenfolge:** „Results“ ▲/▼ zwischen drei Layern; neuer Layer bei „Results“ oben bzw. tiefer (§6.3); Entfernen eines Layers darüber; „Clear“ setzt zurück; neue Suche behält den Platz.
- **Auge:** schaltet Quicklooks, angehakte Szenen und Umrisse; Ansicht und Vorschau bleiben (bzw. nach Antwort 2).
- **Ausnahmen:** Suche schaltet ein, „Crop to AOI“ und „Crop & merge to AOI“ schalten aus, Anhaken bei ausgeschaltetem Auge schaltet ein, Abhaken ändert nichts, „Play“ schaltet ein.
- **Innerhalb von „Results“:** die sechs Stufen in Browse-Modus und Ansicht, die zuletzt angehakte oben, offene Gruppe über angehakten Szenen anderer Gruppen auch in der Ansicht (die Abweichung aus §6.1), egal in welcher Reihenfolge die Bilder ankommen.
- **`style.load` und Basiskarte:** erstes Laden und Wechsel der Basiskarte mit und ohne Beschriftung/Gradnetz: gleiche Folge, Overlays über allen Rastern, AOI ganz oben.
- **Zweckfremd:** ▲ an „Results“ ganz oben und ▼ ganz unten tun nichts; `resultsAt` außerhalb der Liste wird begrenzt; ein Layer, dessen Bild nach dem Entfernen ankommt, landet nicht auf der Karte.
- **Browser (Playwright, `frontend/e2e/results-layer.cjs`):** Ottos Klickweg über die Knöpfe der Oberfläche, Lage von „Results“ per ▲/▼, Hell/Dunkel, breites und schmales Fenster. Bilder nur im PR beschrieben.
- **Prüfanleitung für Otto** im PR mit seinem Klickweg (Sentinel-2, eine Gruppe offen, Job anheften, Auge aus/an, „Results“ unter den Job schieben).
- `ruff check backend`, `pytest`, `lint-imports`, `npm run lint`, `npx tsc -b`, `npx vitest run`.

### 6.10 Fragen an Otto

Kurz beantwortbar: je Frage eine Nummer.

**Frage 1 — Umstände des Fehlers** (nicht nachstellbar, §6.1). Was traf zu? Mehrfachnennung möglich.
1. Eine Ansicht war offen („Crop to AOI“ o. Ä.).
2. Das Processing-Panel war offen (Live-Vorschau).
3. „angeklickt“ hieß: Szenen angehakt (nicht nur „Show results“ gedrückt).
4. Mehrere Datensätze in der Suche.
5. Weiß ich nicht mehr; der Test aus §6.9 genügt. **(Empfehlung, wenn keine der anderen sicher ist)**

**Frage 2 — Was das Auge von „Results“ schaltet**
1. Nur die Suchergebnisse (Quicklooks, angehakte Szenen, Umrisse); Ansicht und Vorschau behalten ihre Schalter; „Play“ schaltet ein. **(Empfehlung)**
2. Alles in „Results“, auch Ansicht und Vorschau („Crop“ zeigt dann erst nach Klick aufs Auge etwas).

**Frage 3 — Neuer Layer und neue Suche**
1. Neuer Layer direkt unter „Results“, wenn „Results“ oben liegt, sonst ganz oben; neue Suche behält den Platz, „Clear“ setzt „Results“ nach oben. **(Empfehlung)**
2. Neuer Layer immer ganz oben, auch über „Results“.
3. Neue Suche setzt „Results“ immer nach oben.

**Frage 4 — Ansicht in „Results“ ganz unten (§3.2, ersetzt die Regel vom 27.10.2026)**
1. Ja: mit eingeschaltetem Auge liegt die offene Gruppe über der Ansicht. **(Empfehlung, so in §3.2)**
2. Nein: die übrigen Quicklooks bleiben unter der Ansicht, nur angehakte Szenen darüber.

**Frage 5 — Knopf in der Ergebnisliste**
1. Wird zum selben Auge. **(Empfehlung)**
2. Entfällt, nur das Auge im Layer-Manager.

**Frage 6 — Zahl in der Zeile „Results“**
1. Keine. **(Empfehlung)**
2. Zahl der Szenen auf der Karte.

**Frage 7 — Ansicht oder Vorschau ohne Suchergebnisse**
1. Keine Zeile; sie liegen am Platz von „Results“. **(Empfehlung)**
2. Zeile „Results“ erscheint auch dann.

**Frage 8 — Schnitt**
1. Zwei PRs in dieser Session: (a) eine Ebenenfolge mit Korrektur, (b) Zeile „Results“ mit Auge. **(Empfehlung, je unter etwa 400 Zeilen)**
2. Ein PR.

**Frage 9 — Overlays (Beschriftung, Gradnetz, Relief)**
1. Feste Plätze wie heute, im Menü „Basemap“. **(Empfehlung)**
2. Eigene Einträge im Layer-Manager.

## 7. Freigabe (Otto, 30.10.2026, zu #249)

| Frage | Antwort | Folge für §6 |
|---|---|---|
| 1 | Option 5: Umstände unbekannt. Der Test für Ottos Klickweg genügt; die eine Ebenenfolge soll den Fehler unabhängig davon ausschließen, in welcher Reihenfolge die Bilder ankommen. | §6.9: Der Test lässt die Bilder in wechselnder Reihenfolge ankommen. |
| 2 | Option 1: Das Auge schaltet nur die Suchergebnisse. Ansicht und Vorschau gehören in der Reihenfolge zu „Results“, behalten aber ihre eigenen Schalter. „Play“ schaltet ein. | wie §6.5 |
| 3 | **Jede neue Suche setzt „Results“ ganz nach oben** (Vorgabe nach jeder Suche). Ein neu angehefteter Layer kommt direkt unter „Results“, wenn „Results“ oben liegt, sonst ganz oben. | §6.3: Eine Suche (`runSearch`, `findSceneByName`) setzt `resultsAt` auf 0, ebenso „Clear search results“. Der Satz „Eine neue Suche lässt den Platz, wie er ist“ gilt nicht. |
| 4 | Option 1: Die Ansicht liegt ganz unten in „Results“; das ersetzt die Regel vom 27.10.2026 per Nachtrag. „Crop to AOI“ / „Crop & merge to AOI“ schaltet das Auge aus (bestehende Ausnahme), sodass nach dem Zuschnitt die Ansicht zu sehen ist. | wie §6.4 |
| 5 | Option 1: Der Knopf in der Ergebnisliste wird zum selben Auge. | wie §6.5 |
| 6 | Option 1: keine Zahl in der Zeile. | wie §6.7 |
| 7 | Option 1: Ansicht oder Vorschau ohne Suchergebnisse haben keine Zeile und liegen am Platz von „Results“. | wie §6.7 |
| 8 | **Option 2: alles in dieser Session und einem PR**, je Teil eigene Commits. | Ein PR (#249). Commits je Teil: (a) eine Ebenenfolge mit der Korrektur der Abweichung bei offener Ansicht, (b) `resultsAt` im Store und die Zeile „Results“ mit Auge und ▲/▼, (c) der Knopf in der Ergebnisliste als dasselbe Auge, (d) Browserprüfung, Doku und Log. |
| 9 | Option 1: Die Overlays bleiben fest im Menü „Basemap“. | wie §6.8 |

**Start des Codes:** erst, wenn Otto einen freien Frontend-Platz meldet.

**Nachtrag NM4-59 zu den Regeln vom 27.10.2026** (Log-Zeilen „Antworten Otto zu §8.7 (zu #211)“, Punkt 1, und „Ein angehaktes Suchergebnis ist immer der oberste Layer“): Die Originaltexte bleiben stehen. Es gilt ab der Umsetzung:
- Die Ansicht liegt ganz unten in „Results“, unter den Quicklooks der Suchergebnisse.
- Angehakte Szenen liegen innerhalb von „Results“ nach §6.4 und damit nicht mehr über allen angehefteten Layern, sondern dort, wo „Results“ in der Liste steht.
- Die Umrisse liegen oben in „Results“, unter Beschriftung, Gradnetz und AOI.
- „Hide results“ / „Show results“ ist das Auge von „Results“.

## 8. Umsetzung (30.10.2026, PR #249)

Ein PR mit je einem Commit pro Teil (Antwort 8).

| Teil | Was | Dateien |
|---|---|---|
| a | **Eine Ebenenfolge.** Jede Ebene bekommt beim Platzieren einen Schlüssel: Platz in der Liste (über oder unter „Results“), Stufe in „Results“ (§6.4), Rang (Index im Anhaken, sonst Reihenfolge des Platzierens). `restackAll` legt alles unter dem einzigen Marker `overlays-base` aus und bewegt nur, was nicht am Platz ist; eine Bewegung lädt keine Kachel nach. Entfallen: die Marker `layers-top`, `results-top`, `ticked-top`, `open-base`, `open-ticked-base`, `preview-base` und die Platz-Hilfen `tickedPlace`, `topOfAll`, `otherTickedTop`, `openRestTop`, `underTheView`, `aboveAll`, `beforeAoi`, `previewTop`, `layerAbove`, `restack`. Die Umrisse (`mosaicsel-line`) sind die oberste Stufe von „Results“. Über einer Ansicht gelten dieselben Stufen wie beim Blättern; damit ist die Abweichung aus §6.1 behoben. | `mapLayers.ts`, `MapView.tsx` |
| b | **Zeile „Results“.** Im Store steht `resultsAt` (Zahl der Layer über „Results“), die reine Logik in `resultsEntry.ts`. Die Zeile hat das Auge und ▲/▼; die übrigen Plätze bleiben leer (`Slot`). Jede Suche und jeder Schritt, der die Ergebnisse verwirft, setzt `resultsAt` auf 0 (`forgetSearch`). Ein neuer Layer kommt direkt unter „Results“, wenn „Results“ oben liegt, sonst ganz oben. Wird ein Layer über „Results“ entfernt, rückt „Results“ nach. | `store.ts`, `resultsEntry.ts`, `LayerManager.tsx`, `index.css` |
| c | **Knopf der Ergebnisliste = dasselbe Auge.** Eine Komponente `ResultsEye`; Tooltip „Hide results on the map“ / „Show results on the map“. Der veraltete Tooltip („ticked scenes still show“) entfällt. | `ResultsEye.tsx`, `ResultsPanel.tsx`, `mapResults.ts` (Regelkommentar) |
| d | **Browserprüfung** `frontend/e2e/results-layer.cjs`; `dem-layers.cjs` überspringt die Zeile „Results“. Nachtrag in `plans/vp3/ui-02-basemap-projektion.md` nach §8, Log. | `e2e/`, `docs/` |

### 8.1 Auslegungen (Vorschlag, gelten bis Otto widerspricht)

1. **Ohne Suchergebnisse** gibt es keine Zeile „Results“ (Antwort 7). ▲/▼ eines Layers tauscht dann nur mit dem Nachbarlayer und zieht nicht unsichtbar an „Results“ vorbei; `resultsAt` bleibt, nach „Clear“ also 0 (Ansicht und Vorschau oben).
2. **„Load more“ ist keine neue Suche:** Der Platz von „Results“ bleibt. Eine andere Wahl der Datensätze verwirft die Ergebnisse und setzt „Results“ wie „Clear“ nach oben.
3. **Umrisse** liegen oben in „Results“ und damit unter Beschriftung und Gradnetz (vorher über der AOI). Die Coverage-Ebenen bleiben über der AOI; sie gehören nicht zu „Results“.
4. **Quicklook unter der Ansicht (O5):** Er bekommt seinen Schlüssel vor den Kacheln seiner Szene und liegt deshalb darunter, egal wann sein Bild ankommt.
5. **Die Zahl im Kopf des Layer-Managers** zählt nur die angehefteten Layer; „No layers yet …“ erscheint nur ohne Layer und ohne Zeile „Results“.

### 8.2 Tests

- `mapLayers.resultsPlace.test.ts` (neu): Ottos Klickweg auf Kartenebene, viermal aus/an mit Bildern in wechselnder Reihenfolge, auch mit Anheften, während die Bilder noch unterwegs sind; Gegenprobe mit „Results“ unter dem Job; Lage bei 0–3 Layern darüber; keine Kachel neu beim Verschieben; Platz außerhalb der Liste; Ansicht, Vorschau und Umrisse wandern mit „Results“.
- `mapLayers.resultsTiers.test.ts` (umbenannt aus `…resultsUnderView…`, Regeln nach Antwort 4), `mapLayers.datasetOrder.test.ts` (die Stufen über einer Ansicht wie beim Blättern: die Abweichung aus §6.1), `mapLayers.groupOrder.test.ts`, `mapLayers.test.ts` (ein Marker).
- `resultsEntry.test.ts` (neu): Anheften, Entfernen, Begrenzen, ▲/▼ an beiden Enden, Tausch mit „Results“, ohne Zeile „Results“, unbekannte Kennung.
- `resultsLayerEntry.test.tsx` (neu, ganze App): Zeile mit Auge und ▲/▼ und nichts sonst; Anheften unter bzw. über „Results“; Verschieben; Entfernen darüber und darunter; Suche setzt nach oben, „Load more“ nicht; „Clear search results“; Auge mit Tooltip; Ausnahmen (Crop aus, Haken an, Suche an, „Play“ an); Verschieben ändert das Auge nicht.
- Angepasst auf das Auge: `ResultsPanel.test.tsx`, `ResultsDock.test.tsx`, `resultsOnMap.test.tsx`.
- Gegenprobe: Gegen `mapLayers.ts` vor Teil a schlagen 22 der Ebenen-Tests fehl, darunter die Abweichung bei offener Ansicht. Ottos Klickweg selbst besteht dort auch (er war nicht nachstellbar, §6.1).
- Browser (Chromium, echtes MapLibre): `results-layer.cjs` hell/dunkel × breit/schmal grün; `layer-order.cjs`, `dem-layers.cjs`, `group-heads.cjs`, `play-steps.cjs`, `layer-rows.cjs`, `tooltips.cjs` grün.

### 8.3 Prüfanleitung für Otto

1. Sentinel-2 suchen, eine Gruppe in den Ergebnissen öffnen, nichts anhaken.
2. Einen fertigen Job „Add to layers“: Im Layer-Manager steht „Results“ oben, der Job darunter; auf der Karte liegen die Quicklooks über dem Job.
3. Auge von „Results“ aus: Der Job ist zu sehen. Auge an: Die Quicklooks liegen wieder darüber. Mehrmals, auch über das Auge im Kopf der Ergebnisliste.
4. „Results“ mit ▼ unter den Job schieben: Der Job liegt oben. Mit ▲ zurück.
5. Einen weiteren Job anheften, während „Results“ unten liegt: Er kommt ganz nach oben. Neue Suche: „Results“ springt nach oben.
6. Szenen anhaken und „Crop & merge to AOI“: Das Auge geht aus, die Ansicht ist zu sehen. Auge an: Die offene Gruppe liegt über der Ansicht. Eine Szene einer anderen Gruppe anhaken: Sie liegt unter der offenen Gruppe, über der Ansicht.
7. Basemap wechseln, Labels an: Die Reihenfolge bleibt, die Beschriftung liegt über den Bildern.
