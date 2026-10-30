# Nach der M4-Abnahme: gesammelte Punkte

**Pflege:** Dieses Backlog pflegt nur der Planungs-Chat bzw. Otto. Sessions ändern es nicht; Erledigtes tragen sie als Log-Zeile mit PR-Nummer in `docs/ENTSCHEIDUNGSLOG.md` ein (Otto, 26.10.2026).

Stand: 27.10.2026. Otto hat entschieden, zuerst alles bis zur M4-Abnahme (M4-20) fertig zu machen. Danach werden diese Punkte der Reihe nach aufgegriffen. Reihenfolge laut Log vom 24.10.2026: DOC-01, dann UI-01 und UI-02; NM4-01 und NM4-02 als Stufe A daneben. Für die übrigen Punkte entscheidet Otto die Reihenfolge.

> **Regel für alle Pläne (Otto, 30.10.2026):** Screenshots und andere Bilder der Browserprüfung kommen nicht ins Repo; die Prüfung wird im PR beschrieben.

## Neu (Plan-Dateien unter `docs/plans/querschnitt/`)

1. **Jahr in der Copernicus-Attribution** (Fund vom 20.10.2026, `provenance.json` des Runners).
   - **Plan:** `querschnitt/nm4-01-attribution-jahr.md`
   - **Erledigt:** NM4-01, PR #190 (25.10.2026).
   - **Befund:** Dort steht „Contains modified Copernicus Sentinel data 2026“, die Szene ist aber vom 29.07.2025.
   - **Vermutung:** Das Jahr kommt aus dem aktuellen Datum statt aus der Aufnahme.
   - **Aufgabe (Stufe A):**
     - zuerst den Wortlaut der Copernicus Sentinel Data Terms mit Quelle prüfen,
     - dann das Jahr aus dem Aufnahmedatum ableiten, bei mehreren Jahren als Spanne, etwa „2024–2025“,
     - eine Stelle für alle Downloads (Zuschnitt, Export, Job, Runner, Linkliste der Originale) und für `citation.bib`.
2. **Zuschnitt und Export auf die Sortierung des Mosaik-Jobs angleichen** (M4-17, Frage 2, 20.10.2026).
   - **Plan:** `querschnitt/nm4-02-sortierung-zuschnitt.md`
   - **Erledigt:** NM4-02, PR #192 (25.10.2026); Version 0.4.3.
   - **Befund:** Die Regel „erstes gültiges Pixel“ ist überall dieselbe, die Reihenfolge der Szenen aber nicht:
     - Mosaik-Job und Mosaik-Kachel sortieren nach Ziel-CRS und Item-ID,
     - Zuschnitt und Export folgen der Reihenfolge der Auswahl.
   - **Folge:** In schmalen Überlappungen kann die Vorschau eine andere Szene zeigen als der Zuschnitt.
   - **Aufgabe (Stufe A):** dieselbe Sortierfunktion für Zuschnitt und Export verwenden. Weil sich dadurch die Bytes des Zuschnitts ändern, gehört die Änderung in die Versionierung.
3. **Absolute URL für den Link `tiles`** im Ergebnisdokument (M4-13c-5). Heute ist der Link relativ, ein API-Client ohne den gemeinsamen Proxy findet den `tiler` damit nicht. Spätestens mit der öffentlichen API in M6 nötig.
   - **Plan:** `querschnitt/nm4-03-tiles-url-absolut.md`
   - **Erledigt:** NM4-03, 25.10.2026, Draft-PR [#193](https://github.com/oscipal/earthX/pull/193); `EARTHX_TILER_URL`.
   - **Vermerk für M6 (Otto, 25.10.2026):** Die übrigen Links des Ergebnisdokuments und des Auftrags bleiben relativ. Sie liegen auf `api` selbst und lösen sich gegen die Dokument-URL auf. Mit der öffentlichen API (M6) neu prüfen; ein mögliches `EARTHX_API_URL` nach dem Muster von `EARTHX_TILER_URL` wäre dann eine eigene Entscheidung.
4. **Mosaik mit Operator im Kachel-Pfad,** also eine Vorschau des Mosaik-Jobs mit Band math (M4-17, Frage 4).
   - **Plan:** `querschnitt/nm4-04-mosaik-mit-operator.md`
   - **Backend erledigt:** PR #215 (gemergt 28.10.2026; Otto: §11 Fragen 1–6 Option 1, Frage 7 Option 3). Mosaik-Kachel nimmt `op`/`params` wie die Item-Kachel, rechnet wie der Job (erst Mosaik, dann Schritte), ab z8, höchstens 4 Assets mit Schritten, URL bis 7 168 Byte (sonst `414`). Messskripte unter `scripts/tile-bench/`. Otto-Messung 28.10.2026 (lokal, echte Quelle, 4 Szenen über die UTM-Grenze 31/32, `red`+`nir`, NDVI, z10, 512 px): kalt 6,0 s, warm 0,16 s.
   - **Frontend erledigt:** NM4-04b, PR #221 (gemergt 28.10.2026), mit Ottos Regeln: Live-Vorschau über angehakten Szenen, „Hide results“ blendet auch die Auswahl aus (Haken bleiben), Anhaken bei „Hide“ schaltet auf „Show“, zuletzt angehakte Szene oben.
5. **Processing auf einem Ergebnis** (Otto, 20.10.2026), also ein Job-Ergebnis als Eingabe eines neuen Rezepts.
   - **Plan:** `querschnitt/nm4-05-processing-auf-ergebnis.md`
   - **Vorlage:** `adr/0019` (PR #204, 26.10.2026), Empfehlung Option 2: ⚙ am Ergebnis-Layer öffnet das Panel mit dem Auftrag des Jobs, bisherige Schritte gesperrt vorn, neue dahinter, alles als ein Auftrag neu gerechnet; nur Frontend. Entschieden: F1–F5 je Option 1 (Otto, 26.10.2026). Umsetzung: `querschnitt/nm4-05b-processing-auf-ergebnis.md`.
   - **Warum eine Vorlage nötig ist:** Das ist eine neue Art von Eingabe neben Datensatz und Item. Sie berührt „Eingaben per Referenz“ (S3), B8, Herkunft und Ablauf nach 7 Tagen.
   - **Aufgabe:** zuerst eine Entscheidungsvorlage (Stufe C), dann die Umsetzung.
   - **Abgrenzung zu UI-01:** UI-01 sperrt bis dahin den Processing-Knopf bei Ergebnis-Layern mit Grund (UI-01 §1 Punkt 11).
6. **Gemergter Zuschnitt als ein Objekt im Panel** (Otto, 20.10.2026).
   - **Zusammengelegt (29.10.2026):** wird mit NM4-05b umgesetzt; nicht einzeln starten.
   - **Plan:** `querschnitt/nm4-06-zuschnitt-als-ein-objekt.md`
   - **Heute:** Wird Processing aus einem Layer gestartet, der schon gemergt und auf die AOI zugeschnitten ist, bietet das Panel trotzdem „Run as: One job / per pass / per scene“ an.
   - **Soll:**
     - kein „Run as“,
     - „Area“ fest auf „AOI only“,
     - genau ein Auftrag (Mosaik des Überflugs mit AOI).
   - **Sonderfall:** Bei Szenen mehrerer Überflüge sagt das Panel mit Grund, dass ein einzelner Auftrag nicht geht.
   - **Aufgabe:** Stufe A, nur Frontend. Der frühere Entwurf (M4-33, nie im Repo) ist in NM4-06 aufgegangen.
7. **Bandauswahl im Panel** (Otto, 22.10.2026).
   - **Plan:** `querschnitt/nm4-07-bandauswahl.md`
   - **Ein Band:** Hat das Item bzw. Asset nur ein Band (etwa DEM `data` oder ein Ergebnis), ist es beim Öffnen des Panels automatisch gewählt.
   - **Alle Bänder:** Mit einem Knopf „Select all bands“ (und „Clear“) werden alle Bänder gewählt.
   - **Grenze:** Je Auftrag gilt die Obergrenze von 16 Assets bzw. Bändern (M4-07b F5). Hat ein Datensatz mehr, wählt „Select all“ keine stille Teilmenge, sondern sagt es mit Grund. Welche Assets dabei als Bänder zählen, prüft die Aufgabe; Hilfs-Assets wie `visual`, `thumbnail` oder `scl` zählen eher nicht. Bei Unklarheit ist das eine Frage an Otto.
   - **Aufgabe:** Stufe A, nur Frontend. Bänder aus dem Ausdruck kommen weiter automatisch dazu (M4-13c).
   - **Erledigt:** NM4-07, PR #216 (27.10.2026). Neues Registry-Pflichtfeld `auxiliary_assets` (S2 L2A: `visual`, `preview`), `adr/0014` §15s.
   - **Folge (Otto, 27.10.2026):** Die Grenze von 16 und die Auswahl oben entfallen mit Punkt 43.
8. **Methodentext ins Rezept, `methods.txt` entfällt** (Otto, 22.10.2026).
   - **Plan:** `querschnitt/nm4-08-methodentext-ins-rezept.md`
   - **Erledigt:** NM4-08, PR #201 (26.10.2026). Text in `recipe.json` → `provenance.methods`; ZIPs ohne `methods.txt`; Link `methods` der API bleibt; Runner schreibt den Text in `provenance.json`. `adr/0014` §15r, `adr/0016` §12c.
   - **Soll:** `recipe.json` trägt den Methodentext im Block `provenance` als Feld `methods`. Dieser Block geht nicht in den Hash ein, und der Runner trennt ihn beim Einlesen ab (M4-16 F3). Die eigene Datei `methods.txt` entfällt im ZIP und im Runner.
   - **Folgen:**
     - die Definition der Download-Inhalte aus M4-30 und `TEXT_FILES` (M4-19a) anpassen,
     - der Runner schreibt den Text ebenfalls in seine `recipe.json`,
     - Link und Ausgang `methods` in der API: im Plan klären, ob sie bleiben oder entfallen,
     - Nachtrag in `adr/0014`.
   - **Kein Knopf zum Kopieren,** nirgends im Frontend (Otto, 22.10.2026). Die Einträge „Methods“ und „Copy“ der Jobliste entfernt UI-01 (§1 Punkt 12).
   - **Aufgabe:** Stufe A, Backend und Runner.
9. **Feste Gruppenköpfe in den Suchergebnissen** (Otto, 22.10.2026).
   - **Zusammengelegt (29.10.2026):** wird mit Paket NM4-55 umgesetzt; nicht einzeln starten.
   - **Plan:** `querschnitt/nm4-09-feste-gruppenkoepfe.md`
   - **Soll:** Beim Scrollen durch die Suchergebnisse bleibt der Kopf der aktuellen Gruppe oben stehen, solange Einträge dieser Gruppe sichtbar sind. Der Kopf der nächsten Gruppe schiebt ihn dann hinaus („sticky header“).
   - **Gilt mit allem, was im Kopf steht:** Name der Gruppe, Anzahl („loaded (of N)“), „Select all“ der Gruppe (M4-29) und Auf- und Zuklappen.
   - **Zu prüfen:** Der Kopf verdeckt keinen Eintrag, das Nachladen weiterer Treffer am Listenende greift weiter, und das Verhalten passt auch auf schmalen Bildschirmen.
   - **Aufgabe:** Stufe A, nur Frontend. Weil UI-01 die Leisten und Panels neu ordnet, kommt der Punkt nach UI-01 oder wird dort mit aufgenommen.
10. **Laufnummer und Band-Chips für Ergebnisse von Schritten** (Otto, 22.10.2026).
   - **Stand 27.10.2026:** geht in Punkt 43 (NM4-43, `adr/0020`) auf; nicht einzeln starten.
   - **Plan:** `querschnitt/nm4-10-schritt-namen-und-chips.md`
   - **Format (Otto):** Schritt-Titel „1. Band_Math_1“, „2. Normalize_2“ usw. Die Nummer steckt auch im Namen des Ergebnisbands: Schritt 1 gibt das Band `Band_Math_1` aus, nicht mehr `band_math`.
   - **Eigener Name (Otto):** Der Name des Ergebnisbands lässt sich je Schritt umbenennen, etwa `ndvi`. `Band_Math_1` ist nur die Vorgabe. Der eigene Name steht im Rezept, erscheint als Chip und im Titel und gilt in den folgenden Schritten. Im Plan zu klären: erlaubte Zeichen und Länge, keine Doppel innerhalb der Kette, keine Kollision mit Bandnamen des Datensatzes, Umbenennen nachdem spätere Schritte den alten Namen schon nutzen (mitziehen oder Hinweis).
   - **Gleiches Format wie die Bänder:** Das Ergebnisband eines Schritts erscheint in den folgenden Schritten als Chip im selben runden Format wie die Bänder des Datensatzes (M4-13c). Ein Klick fügt es in den Ausdruck ein, wie bei den Band-Chips. So ist klar, womit man weiterarbeiten kann.
   - **Nur verfügbare Bänder:** Ein späterer Schritt zeigt nur die Chips, die nach den vorigen Schritten noch vorhanden sind (nach Band math nur dessen Ergebnisband, nach `mask` die Bänder ohne die Schicht). Die Regel kommt aus dem Backend, das Frontend baut sie nicht nach (wie in M4-18b).
   - **Folgen, im Plan zu klären:**
     - Der Bandname ändert Rezept, Hash und Bytes des Ergebnisses (Bandbeschreibung in `result.tif`), gehört also in die Versionierung (`op_version` bzw. `earthx.__version__`), mit Nachtrag in `adr/0014`.
     - Woher die Laufnummer kommt (Platz in der Kette, ab 1), und ob alte Rezepte mit `band_math` weiter angenommen werden.
     - Groß- und Kleinschreibung sowie erlaubte Zeichen gegen die bestehenden Regeln für Bandnamen im Ausdruck prüfen; bei Konflikt Frage an Otto.
     - Kachel-Pfad (M4-18b), Runner und Methodentext ziehen mit.
   - **Aufgabe:** Stufe B (ändert Ergebnis-Bytes), Backend und Frontend.
11. **Normalize klarer und mit mehreren Methoden** (Otto, 22.10.2026).
   - **Stand 27.10.2026:** wartet auf die Entscheidung zu Punkt 43.
   - **Plan:** `querschnitt/nm4-11-normalize-methoden.md`
   - **Klarer:** Im Panel steht kurz, was der Schritt tut, mit Beispiel (etwa „NDVI −1…1 → 0…1“) und der Formel der gewählten Methode. Die Felder tragen verständliche Namen und Hilfetexte (Englisch).
   - **Methoden, Vorschlag:**
     - linear von einem festen Bereich auf einen anderen (heute, `normalize` v1),
     - Z-Score: (x − Mittelwert) / Standardabweichung,
     - über Perzentile, etwa 2–98 %, auf einen Zielbereich, mit Clip,
     - eventuell robust über Median und Interquartilsabstand.
   - **Kern der Sache, im Plan zu klären:** Z-Score und Perzentile brauchen Statistik über die ganze Eingabe.
     - Im Job heißt das zwei Durchgänge oder eine Statistik vorab; Rechenzeit, Speicher (500 MB) und Bitgleichheit (zweimal gerechnet, Cloud gegen Runner) müssen halten.
     - In der Kachel-Vorschau darf die Statistik nicht je Kachel gerechnet werden, sonst passen Kacheln nicht zusammen und die Vorschau weicht vom Job ab. Optionen: Statistik einmal je Auftrag vorab, oder Vorschau nur für die lineare Methode.
     - Ob die Werte (Mittelwert, Perzentile) im Rezept stehen, damit Rezept und Ergebnis eindeutig sind, oder erst im Lauf entstehen.
     - Perzentile deterministisch wie in M4-32 (festes Histogramm), Weg wiederverwenden.
     - Je Band oder ein Bereich für alle Bänder.
   - **Vorher:** Stand der Technik mit Quellen recherchieren (Compute-Relevanz), etwa rio-tiler/GDAL-Statistik, scikit-learn-Skalierer, übliche Verfahren in der Fernerkundung.
   - **Aufgabe:** Stufe B, Backend und Frontend; neue `op_version` bzw. neuer Parameter `method`, Nachtrag in `adr/0014`, Kostenfaktor messen.
12. **Anheften ohne zweiten Klick** (Otto, 22.10.2026, aus M4-17c).
   - **Zusammengelegt (29.10.2026):** wird mit Paket NM4-54 umgesetzt; nicht einzeln starten.
   - **Plan:** `querschnitt/nm4-12-anheften-ohne-zweiten-klick.md`
   - **Heute:** „Add to layers“ bei einer Teilauswahl, deren Mosaik noch lädt, weist ab („The mosaic of this time step is still loading — add it to the layers in a moment.“); erst ein zweiter Klick heftet an.
   - **Soll:** Der Knopf zeigt „Loading…“ und heftet den Layer automatisch an, sobald das TileJSON da ist. Bei einem Fehler bleibt die bestehende Meldung.
   - **Aufgabe:** Stufe A, nur Frontend; Test, der am heutigen Code scheitert.
13. **`docs/plans/` je Meilenstein aufräumen** (Otto, 22.10.2026).
   - **Erledigt:** DOC-01 (`querschnitt/doc-01-plaene-je-meilenstein.md`), 24.10.2026.
   - **Soll:** ein Unterordner je Meilenstein, etwa `docs/plans/m0/` … `docs/plans/m4/`, `docs/plans/vp3/` (UI-01, UI-02); Dateinamen bleiben.
   - **Zeitpunkt:** nach M4-20 und vor dem Start von UI-01, wenn keine Session läuft. Grund: Startsätze und Verweise laufender Sessions zeigen auf die alten Pfade.
   - **Umfang:**
     - Verschieben mit `git mv`, damit die Historie erhalten bleibt.
     - Alle Verweise nachziehen: Pläne untereinander, `adr/`, `ENTSCHEIDUNGSLOG.md`, `KLAERUNGEN.md`, `projektplan.md`, `architekturplan.md`, README, Kommentare im Code und in Tests. Verweise in `CLAUDE.md`, `.github/` und `.claude/` nur mit Ottos Erlaubnis; die Session listet sie im PR.
     - Prüfung, dass kein Verweis auf `docs/plans/<datei>` ohne Unterordner übrig ist (Suche im PR belegen), am besten als kleiner Test.
     - Neue Startsätze lauten dann etwa „Führe Aufgabe UI-01 aus `docs/plans/vp3/ui-01-app-rahmen.md` aus.“
   - **Zu klären im PR:** wohin Querschnittsdateien ohne Meilenstein gehören (etwa Zusätze über mehrere Aufgaben); Vorschlag: zum Meilenstein, in dem sie entstanden sind.
   - **Aufgabe:** Stufe A, nur Doku, Sonnet mittel.
14. **Schnellrechnungen (Index-Knöpfe)** (Otto, 22.10.2026; Grundlage `projektuebersicht.md` §8: „datensatzspezifische Presets … bauen auf Band-Math auf“).
   - **Stand 27.10.2026:** wartet auf die Entscheidung zu Punkt 43 (Index-Knopf fügt ein neues Band hinzu?).
   - **Plan:** `querschnitt/nm4-14-index-knoepfe.md`
   - **Soll:** An einem Layer eines passenden Datensatzes (etwa „Crop & merge to AOI“ von Sentinel-2) gibt es Knöpfe für häufige Indizes, etwa NDVI, NDWI, NDSI, NBR, EVI. Ein Klick erzeugt einen ganz normalen Band-math-Schritt mit Vorschau; Start als Job wie gewohnt.
   - **Kein zweiter Weg:** Die Knöpfe füllen nur das Rezept. Vorschau, Job, Cache, Runner, Methodentext und `recipe.json` bleiben dieselben.
   - **Je Datensatz, nicht im Code:** Die Bandnamen unterscheiden sich je Quelle (COG gegen Zarr; der EOPF-Zarr-Datensatz entfällt mit NM4-15b, die Presets bleiben je Datensatz). Die Presets stehen deshalb als Daten in der Registry je Datensatz (Name, Ausdruck, Wertebereich, Colormap-Vorgabe, Quelle der Formel); nur Datensätze mit passenden Bändern zeigen sie. Kein datensatzspezifischer Code.
   - **Quellen:** Formeln mit Beleg, etwa Awesome Spectral Indices (Montero et al., 2023, *Scientific Data*) oder Index DataBase; bei Indizes mit Konstanten (EVI) die Werte mit Quelle.
   - **Zu klären im Plan:** Welche Indizes zuerst; ob die Knöpfe am Layer, im Panel oder an beiden Stellen sitzen (Abstimmung mit UI-01); ob ein Preset die Bänder automatisch wählt (Punkt 7) und den Ergebnisnamen setzt (Punkt 10, etwa `NDVI`); Verhalten bei Mosaik (Punkt 4) und mit `mask` davor („NDVI cloud-free“ als Preset-Kette?).
   - **Aufgabe:** Stufe B (Registry-Feld, Panel), Backend und Frontend.
15. **Nur ein Sentinel-2-L2A-Datensatz sichtbar** (Otto, 22.10.2026).
   - **Plan:** `querschnitt/nm4-15-ein-sentinel-2-datensatz.md` (Vorlage, `adr/0017`); Umsetzung `querschnitt/nm4-15b-eopf-datensatz-entfernen.md`
   - **Entschieden:** `adr/0017` angenommen, PR #189 (25.10.2026), Fragen 1–6 je Option 1.
   - **Erledigt:** NM4-15b, 25.10.2026, Draft-PR [#195](https://github.com/oscipal/earthX/pull/195); `sentinel-2-l2a-zarr3` verließ Registry, Katalog und Oberfläche, die ID antwortet mit `410`.
   - **Wiedervorlage (Otto, 25.10.2026):** Anfang 2027 oder früher, sobald EOPF operative Zarr-Produkte meldet (FAQ des Dienstes: „late 2026 or early 2027“). Dann eine operative, token-freie Zarr-Quelle prüfen; bis dahin ist die Formatachse (Prinzip 3, Checkliste Punkt 5) nur synthetisch belegt (`projektuebersicht.md` §5).
   - **Wunsch:** Die Plattform bietet nicht mehrere Datensätze an, die dasselbe zeigen. Heute gibt es `sentinel-2-c1-l2a` (Earth Search, COG) und `sentinel-2-l2a-zarr3` (EOPF, Zarr). Otto will den Zarr-Datensatz loswerden.
   - **Warum zuerst eine Vorlage (Stufe C):** Der Zarr-Datensatz trägt Belege und Entscheidungen: zweites Format (`adr/0007`), Zarr-Vergleich T1 ↔ T2 (`adr/0014` §15d, Kriterium 1 der M4-Abnahme), Tests und Fixtures, Prüfanleitungen, `SCL_20m:scl` in der Maske (M4-18c).
   - **Optionen für die Vorlage:**
     1. EOPF-Datensatz aus Katalog und Registry entfernen; der Zarr-Reader bleibt als generische Fähigkeit mit synthetischen Tests für künftige Zarr-Quellen (`ADDING_ESA_DATASETS.md`).
     2. Ein sichtbarer Datensatz „Sentinel-2 L2A“ mit zwei Quellen dahinter (eine primär, eine als Rückfall, `adr/0005` föderierte Suche); der Nutzer sieht nur einen Eintrag.
     3. Earth Search entfernen und EOPF behalten.
   - **Vorher recherchieren, mit Quellen:** Betriebsstatus des EOPF-Zarr-Dienstes (Muster oder operativ), Zeitplan von Earth Search v2 (Punkt „Earth Search v2“ unten), Abdeckung und Aktualität beider Quellen, Unterschiede bei Skalierung (Zarr-Item ohne `raster:scale`), Bandnamen und Prüfsummen (`adr/0014` §3.1, Cache-Fähigkeit).
   - **Folgen in jedem Fall:** Abnahmebelege aus M4 bleiben gültig (sie belegen den Stand von M4); Registry, Fixtures, Tests, Prüfanleitungen und Doku nachziehen; bestehende Permalinks und `recipe.json` mit dem alten Datensatz: abweisen mit Grund oder umleiten (im Plan klären).
   - **Aufgabe:** Stufe C (Entscheidungsvorlage), danach Umsetzung.
16. **Einheiten für die übrigen Sentinel-2-Assets** (aus M4-19b, 23.10.2026).
   - **Plan:** `querschnitt/nm4-16-einheiten-uebrige-assets.md`
   - **Erledigt:** NM4-16, PR #199 (26.10.2026): `aot` "1", `wvp` "cm", `cloud` und `snow` "%", `preview` bewusst ohne Einheit; Quellen: Sen2Cor-L2A-IODD Tab. 6, 7, 16, 20.
   - **Heute:** `aot`, `wvp`, `cloud`, `snow` und `preview` haben in der Registry keine Einheit (`earthx:band_units`), weil die Session keine Quelle dafür gelesen hat.
   - **Aufgabe (Stufe A):** Einheiten mit Quelle nachtragen (Produktspezifikation Sentinel-2 L2A bzw. Item-Metadaten); wo keine Einheit sinnvoll ist (etwa `preview`), das bewusst vermerken. Hinweis: Eine Korrektur der Einheit ändert den Hash (`adr/0014` §15n), also einmal kein Cache-Treffer.
17. **„Clear all“ wird „Clear search results“** (Otto, 24.10.2026).
   - **Plan:** `querschnitt/nm4-17-clear-search-results.md`
   - **In UI-01g aufgenommen (Otto, 26.10.2026, zweite Fassung):** Statt „Clear all“ gibt es den Umschalter „Show/Hide results“; zusätzlich unter „Load more“ ein Knopf mit rotem ✕ „Clear search results“ (löscht nur die Liste, Einstellungen bleiben, Control-Menü öffnet sich). Erledigt mit UI-01g (#209).
   - **Soll:** Der Knopf in den Suchergebnissen heißt „Clear search results“ und löscht nur die Ergebnisliste. Danach öffnet sich wieder das Control-Panel.
   - **Bleibt bestehen:** alle Sucheinstellungen, also AOI, Zeitraum, Datensatzwahl, Filter (etwa Wolkenbedeckung). Ein neuer Klick auf „Search“ sucht mit denselben Einstellungen.
   - **Im Plan zu klären:** was mit angehefteten Layern, offener Ansicht (Mosaik aus M4-17) und Jobs passiert (Vorschlag: angeheftete Layer und Jobs bleiben, die offene Ansicht schließt); wo man AOI und Einstellungen künftig zurücksetzt (eigener Knopf im Control-Panel, falls es keinen gibt); Abstimmung mit UI-01 (linke Leiste, Control-Menü).
   - **Aufgabe:** Stufe A, nur Frontend; Test, dass nach dem Löschen alle Einstellungen erhalten sind.
18. **Abspielen in der Timeline ohne Lücken** (Otto, 24.10.2026).
   - **Zusammengelegt (29.10.2026):** wird mit Paket NM4-55 umgesetzt; nicht einzeln starten.
   - **Plan:** `querschnitt/nm4-18-timeline-ohne-luecken.md`
   - **Soll:** Bei „Play“ wechselt die Karte erst zum nächsten Zeitschritt, wenn dessen Kacheln für den sichtbaren Ausschnitt geladen sind. Zwischen zwei Bildern ist nie die Basemap zu sehen.
   - **Beschriftung:** Während des Abspielens steht nur das Datum der Gruppe (des Überflugs), kein Szenenname.
   - **Im Plan zu klären:**
     - Vorladen des nächsten Schritts im Hintergrund (unsichtbarer Layer oder Kachel-Cache der Kartenbibliothek), Speicher- und Anfrage-Grenzen, Wirkung auf den `tiler` (Mosaik-Kacheln aus M4-17).
     - Mindestdauer je Bild und was bei langsamem Laden passiert (das aktuelle Bild bleibt stehen; Hinweis „Loading…“).
     - Verhalten bei einem Schritt, der nicht lädt (Zeitlimit, überspringen mit Hinweis).
     - Verhalten beim Zoomen oder Verschieben während des Abspielens.
   - **Aufgabe:** Stufe A, nur Frontend; Test, dass der Wechsel erst nach dem Laden erfolgt (mit verzögerten Kacheln).
19. **Auto stretch der Vorschau über die AOI** (Otto, 24.10.2026).
   - **Erledigt:** NM4-19b, PR #230 (30.10.2026): Vorschau misst bei „AOI only“ über die Route aus #218 (POST, AOI nur im Body), Rückfall auf die erste Szene mit Konsolenzeile nur mit Statuscode; Index-Regel nach Perzentilen in Vorschau und Ergebnis (nur Frontend, keine neue Version). Von Otto im Browser geprüft.
   - **Backend erledigt:** PR #218 (28.10.2026): `POST /collections/{dataset}/statistics` im `tiler`, Body = Auftrag, Zählung mit dem Code des Jobs, exakt bis 2048² Pixel, darüber `exact: false`; Cache 7 Tage. Frontend und Index-Regel nach Perzentilen: NM4-19b (§15 des Plans), nach dem Merge in neuer Session.
   - **Plan:** `querschnitt/nm4-19-auto-stretch-ueber-aoi.md`
   - **Heute (M4-19c):** Die Messung für die Farbskala der Vorschau gilt für die erste Szene der Karte, auch bei „AOI only“ für die ganze Szene. Das Job-Ergebnis nimmt dagegen die Statistik über die AOI-Maske (M4-32). Vorschau und Ergebnis können sich deshalb unterscheiden.
   - **Soll:** Bei „AOI only“ misst auch die Vorschau über die AOI, damit Vorschau und Ergebnis dieselbe Farbskala zeigen.
   - **Harte Grenze:** Keine AOI in URLs oder Logs. Die AOI geht nur im Body an den `tiler` (etwa `POST /statistics` wie bei rio-tiler, mit der Geometrie als GeoJSON), nie als Query; Caching dann über einen Hash im Body, der nicht geloggt wird.
   - **Im Plan zu klären:** Schnittstelle (POST-Route, Größen- und Punktgrenze der Geometrie wie bei der Annahme), Cache-Schlüssel ohne AOI im Klartext, Messung über mehrere Szenen bzw. Mosaik eines Überflugs, gleiche Methode wie im Job (festes Histogramm, M4-32a) damit die Werte übereinstimmen, Kosten.
   - **Aufgabe:** Stufe B (neue Route im `tiler`, Datenschutz), Backend und Frontend.
20. **Processing-Panel klarer gegliedert** (Otto, 24.10.2026).
   - **Stand 27.10.2026:** wartet auf die Entscheidung zu Punkt 43 (Ausgabe am Ende des Panels).
   - **Plan:** `querschnitt/nm4-20-panel-gliederung.md`
   - **Soll:** Die Bereiche „Bands“, „Processing steps“, „Output“ und „Preview“ sind deutlich voneinander abgesetzt (etwa eigene Karten oder Abschnitte mit Überschrift, Abstand, Trennlinie, ggf. einklappbar).
   - **Im Plan zu klären:** Gestaltung in Hell- und Dunkelmodus, Reihenfolge, schmale Bildschirme; Abstimmung mit UI-01 (größeres Fenster, linke Leiste) und mit den Punkten 7, 10 und 14 (Bandauswahl, Band-Chips der Schritte, Index-Knöpfe).
   - **Aufgabe:** Stufe A, nur Frontend; Prüfung im echten Browser (Playwright), nicht nur jsdom.
21. **Einheitliches Zahlenformat in der ganzen Web-App** (Otto, 24.10.2026).
   - **Zusammengelegt (29.10.2026):** wird mit Paket NM4-56 umgesetzt; nicht einzeln starten.
   - **Plan:** `querschnitt/nm4-21-zahlenformat.md`
   - **Soll:** Angezeigte Zahlen haben höchstens drei Nachkommastellen. Sehr kleine (und sehr große) Beträge erscheinen wissenschaftlich, etwa 0.000000052 → `5.2e-8`.
   - **Eine Stelle:** eine gemeinsame Formatierfunktion im Frontend für alle Anzeigen (Min/Max der Vorschau und des Ergebnisses, Statistik, Pixelwerte, Schätzung, Auflösung usw.), keine verstreuten `toFixed`.
   - **Im Plan zu klären:**
     - Schwellen für die wissenschaftliche Form (Vorschlag: Betrag < 0.001 außer 0, und ≥ 1e6) und Anzahl gültiger Stellen dort (Vorschlag: bis zu drei, ohne nachgestellte Nullen).
     - Eingabefelder: Was angezeigt wird, ist auch der angewandte Wert (keine versteckte Genauigkeit), oder intern bleibt der volle Wert. Vorschlag: Vorgaben aus der Statistik werden gerundet übernommen; was der Nutzer tippt, gilt genau so.
     - Ausnahmen: Koordinaten, IDs, Daten, Zählungen, Dateigrößen und Werte in `recipe.json`/API bleiben unberührt (nur die Anzeige ändert sich).
   - **Aufgabe:** Stufe A, nur Frontend; Tests für die Grenzfälle (0, negative Werte, 0.001, 0.0009, 1e6, NaN).
22. **Weniger Text in der Oberfläche** (Otto, 24.10.2026).
   - **Zusammengelegt (29.10.2026):** wird mit Paket NM4-56 umgesetzt; nicht einzeln starten.
   - **Plan:** `querschnitt/nm4-22-weniger-text.md`
   - **Grundsatz:** Die Oberfläche zeigt so wenig Text wie möglich. Erklärungen, Hinweise und Gründe stehen im Tooltip (Hover und Tastaturfokus, für Screenreader erreichbar), nicht als Absatz unter Knöpfen oder Feldern – wie bei „Share processing“ (M4-19e).
   - **Sichtbar bleiben nur:** Beschriftungen, Werte, Fehlermeldungen, die eine Handlung verlangen, und Pflichtangaben (Attribution, Lizenz, Datenschutzhinweis).
   - **Umfang:** Durchgang durch Panel, Suchergebnisse, Layer-Manager, Control-Panel; Liste der gekürzten bzw. verschobenen Texte im PR.
   - **Aufgabe:** Stufe A, nur Frontend, zusammen mit Punkt 20 oder in UI-01; gilt ab sofort als Regel für jede neue Oberfläche.
23. **Backend-Tests schneller** (Otto, 24.10.2026).
   - **Plan:** `querschnitt/nm4-23-backend-tests-schneller.md`
   - **Erledigt:** NM4-23, PR #207 (27.10.2026): `pytest-xdist` (Dev), `-n auto --dist worksteal`, Datenbank je Worker; Session 989–1009 s → 280–284 s (3× grün), seriell 850 s; CI-Schritt pytest 4:10 min. 9 wackelige Tests stabilisiert (u. a. Shutdown-Test in `jobs/test_worker.py`), Live-Smokes bleiben seriell; Nachtrag `adr/0002` §6. Offen als möglicher kleiner Punkt: Wartezeit bis 1 s je Test beim Worker-Stopp (`WorkerConfig.listen_seconds`, Produktcode).
   - **Befund (CI-Lauf auf `main`, 24.10.2026):** Job „Backend — lint and tests“ 14,2 min, davon `pytest` 13,2 min; Installation 0,5 min, Ruff und Migration je unter 0,1 min. Frontend 0,7 min, Modulgrenzen 0,7 min, compose-topology 1,9 min.
   - **Schritt 1 – messen:** `pytest --durations=30` (lokal in der Session und einmal in der CI-Ausgabe), Tabelle der langsamsten Tests im PR. Erwartete Kandidaten: Speichertests bei 4096² (`VmHWM`), Vergleiche in `spawn`-Prozessen (Runner, Worker, Import), Tests gegen Postgres. Abhilfe ohne Verlust an Aussage: kleinere synthetische Raster, wo die Größe nicht der Prüfgegenstand ist; teure Fixtures mit Geltungsbereich `module`/`session`; doppelte Prüfungen zusammenlegen. Speicher- und Bitgleich-Tests bleiben in voller Größe.
   - **Schritt 2 – parallel (nur nach Ottos Freigabe):** `pytest-xdist` (neue Abhängigkeit). Vorher mit Quellen klären: Verträglichkeit mit `spawn`-Kindprozessen und Speichermessungen (`VmHWM` je Prozess), eigene Datenbank je xdist-Worker für Postgres-Tests, Zahl der Kerne der GitHub-Runner für öffentliche Repos. Einstellung über die pytest-Konfiguration, nicht über `.github/`.
   - **Grenze:** keine Tests streichen oder überspringen, um Zeit zu sparen; `.github/` bleibt unverändert.
   - **Aufgabe:** Stufe B (Schritt 2 ist eine Abhängigkeit und rechenrelevant), nur Tests und Testkonfiguration.
24. **Stapelung im Rückfall „Szene für Szene“ wie das Mosaik** (aus NM4-02, 25.10.2026).
   - **Zusammengelegt (29.10.2026):** wird mit Paket NM4-54 umgesetzt; nicht einzeln starten.
   - **Plan:** `querschnitt/nm4-24-rueckfall-stapelung.md`
   - **Befund:** Seit NM4-02 nutzen Zuschnitt, Export, Mosaik-Job und Mosaik-Kachel dieselbe Reihenfolge (`mosaic_order`, Kachel liefert `earthx:order`). Fällt die Ansicht auf Einzelszenen zurück (Überflug über 64 Szenen, abgelehnte Mosaik-Kachel), stapelt das Frontend weiter nach Auswahl. In Überlappungen kann dann eine andere Szene oben liegen.
   - **Soll:** Auch der Rückfall stapelt nach derselben Reihenfolge, ohne die Sortierregel im Frontend nachzubauen (etwa Reihenfolge vom Server holen).
   - **Bekannte Grenze, nicht Teil davon:** Bei Überflügen mit gemischten CRS ordnet der Job nur die Szenen, die die AOI berühren, die Kachel die ganze Liste (die Kachel kennt keine AOI). Steht als Grenze in `adr/0014` §15p.
   - **Aufgabe:** Stufe A, Frontend (ggf. kleine Route im Backend), nach UI-01.
25. **Quicklook nach „Crop & merge to AOI“ sofort zuschneiden** (Otto, 25.10.2026).
   - **Zusammengelegt (29.10.2026):** wird mit Paket NM4-54 umgesetzt; nicht einzeln starten.
   - **Plan:** `querschnitt/nm4-25-quicklook-nach-zuschnitt.md`
   - **Heute:** Nach „Crop & merge to AOI“ bleibt der Quicklook der ganzen Szene noch eine Weile sichtbar, auch außerhalb der AOI.
   - **Soll:** Außerhalb der AOI verschwindet der Quicklook sofort. Innerhalb der AOI bleibt er stehen, bis die Kacheln des Zuschnitts geladen sind, dann wird er ersetzt – ohne Aufblitzen der Basemap (Vorgabe „Bild verschwindet nie“, UI-01a).
   - **Aufgabe:** Stufe A, nur Frontend (gemeinsame Layer-Logik), nach UI-01.
26. **Kacheln schneller: Durchsatz von `tiler` und `gateway`** (Otto, 25.10.2026; hohe Priorität). **Erledigt (#197, 26.10.2026).**
   - **Plan:** `querschnitt/nm4-26-kachel-leistung.md`
   - **Befund:** NDVI-Vorschau rund 40 s für 325 Anfragen; Kacheln 1,7–6,5 s mit steigenden Zeiten (Warteschlange), auch reine `visual`-Kacheln 2,6–4,2 s. Gleich schon vor UI-01a (`745ecb2`), also keine Regression daraus. Dazu: Suche dreifach geladen (je 1,9 MB), `statistics` mit `op` einmal `400`.
   - **Aufgabe:** Stufe B mit Messung und Recherche (Gleichzeitigkeit im `tiler`, GDAL-Einstellungen, Verbindungen über `gateway`), Backend und Frontend.
   - **Erledigt (26.10.2026, #197):** GDAL-Profil der Kacheln `SERIAL` + 256 MiB Cache, Zuschnitt unverändert, Item-Abrufe gebündelt. NDVI-Ansicht mit 13 Szenen 45,6 → 27,9 s, bei 100 Mbit/s 145,3 → 38,8 s, Kacheln byte-identisch. Suche: jede Seite einmal, mit Test. Probe auch vor einer einstufigen Statistik. Plan §19.
27. **Jobs löschen mit einem Tag Frist und „Restore“** (Otto, 26.10.2026; erweitert die Entscheidung „nicht löschbar“ vom 12.10.2026).
   - **Plan:** `querschnitt/nm4-27-job-loeschen-mit-frist.md`
   - **Soll:** Delete (Kürzel D) löscht das Ergebnis nach einem Tag (oder früher, wenn es vorher abläuft); innerhalb des Tages „Restore“; keine Rückfrage. Reiter „Active | Expired | Deleted | All“. Geteilte Ergebnisse verschwinden nur für den gelöschten Job.
   - **Aufgabe:** Stufe B, Backend und Frontend, nach UI-01c.
   - **Erledigt:** NM4-27, PR #214 (gemergt 28.10.2026): Migration 015 (`deleted_until`), `DELETE` mit einem Tag Frist (nie über den Ablauf), `POST …/restore`, `404` innerhalb der Frist, Cache und Aufräumer; Reiter „Deleted“, Kürzel `D`, Restore im Menü und als ↺, gesperrter Layer mit Tooltip; Fix „gone“ nach `404`. `adr/0013` §10c, `adr/0015` §14g, `adr/0014` §9.

28. **Suchergebnisse links angedockt** (Otto, 26.10.2026).
   - **Plan:** `vp3/ui-01g-suchergebnisse-angedockt.md` (Teil von UI-01, nach UI-01f).
   - **Erledigt:** UI-01g, PR #209 (26.10.2026), mit den Ergänzungen unter „In UI-01 aufgenommen“.
29. **512er-Kacheln im Frontend** (Otto, 26.10.2026, aus NM4-26 Frage 3).
   - **Plan:** `querschnitt/nm4-29-kacheln-512.md`
   - **Befund (NM4-26 §8.2, §10 S3):** Mit `tileSize: 512` braucht dieselbe Fläche ein Drittel der Anfragen (325 → 117). Die Ansicht wird gemessen 18 % schneller (28,3 → 23,0 s), bei gleichen Bytes von der Quelle.
   - **Berührt:** Zuordnung Kartenzoom → Kachelstufe (`TILE_LEVEL_AHEAD`, `previewMaxZoom`, `zoomHint`), die freigegebenen Stufen je Datensatz (`earthx:viewer`, `adr/0007` §12.10) und die Grenzen der Mosaik-Kachel (M4-17 §5).
   - **Aufgabe:** Stufe B, Frontend und `tiler`; nach NM4-26.
30. **Nicht Mögliches ausblenden statt ausgrauen** (Otto, 26.10.2026).
   - **Zusammengelegt (29.10.2026):** wird mit Paket NM4-56 umgesetzt; nicht einzeln starten.
   - **Plan:** `querschnitt/nm4-30-nicht-moegliches-ausblenden.md`
   - **Regel:** Was für Datensatz oder Layer grundsätzlich nicht geht, erscheint nicht; was nur im Moment nicht geht, bleibt gesperrt mit Grund im Tooltip. Gilt ab sofort für alles Neue.
31. **Toter Zweig „Einmal-Produkt mit Extent-Antwort“ in der Coverage-Route** (aus NM4-15b, Otto, 26.10.2026).
   - **Befund:** Mit dem Ausscheiden von `CoverageProvider.SAMPLE` ist der Zweig `single_coverage_product` ohne Flächenweg in `api/coverage_route.py` (`extent_result`) nicht mehr erreichbar: `_check_coverage` verbietet `single_coverage_product` mit Aggregation, `local-sql` nimmt den Flächenweg. Ebenso wirkungslos ist `and not config.capabilities.single_coverage_product` in `check_adapter_specs` (`adapters/spec.py`) samt `_required` in `tests/earthx/adapters/test_spec.py`.
   - **Berührt:** `adr/0004` (Einmal-Produkte: Ausdehnung allein).
   - **Aufgabe (Stufe A, eigener PR):** prüfen, ob der Zweig für eine künftige Quelle ohne Aggregation gebraucht wird; sonst mit seinen Tests entfernen.
   - **Erledigt:** NM4-31, PR #203 (26.10.2026): `extent_result`, Zweig in `coverage_route.py` und die Klausel in `check_adapter_specs` entfernt; Feld `extent` der Antwort bleibt; Nachtrag `adr/0004`.
32. **Paket „Datensatzabhängige Suche und Prozessierung“ (DS)** (Otto, 26.10.2026). DS-02, DS-03, DS-06 nach VP3 und vor M5; DS-04 und DS-05 (Sentinel-1) erst mit oder nach M5.
   - **DS-03a1 erledigt** (PR #235, 30.10.2026): Grundlagen der Wolkenmessung in der AOI (SCL, Klassen 8/9/10, Stufe mit ≥ 10 000 Pixeln), `adr/0021` „§6 Nachtrag DS-03“. Offen: DS-03a2 (Filter „Within AOI“ in der Suche, nur mit AOI und Zeitraum), DS-03b (Oberfläche).
   - **DS-03a2 erledigt** (PR #240, 30.10.2026): Filter „Within AOI“ in der Suche, nur mit AOI und Zeitraum, höchstens 500 geprüfte Szenen; Live-Test im Job `earth-search` (Ausnahme `.github/`, Otto).
   - **DS-02c erledigt** (PR #239, 30.10.2026; mit Popup über „Search“ und allen filterbaren Feldern von Earth Search): „Advanced search“ im Control-Menü, Filter je Datensatz aus `earthx:search_filters`, Umschalter wie „Showing dataset“, Filter nicht im Permalink und nicht gemerkt.
   - **Otto, 30.10.2026:** „Advanced search“ wird ein eigener Knopf über „Search“, der ein Popup öffnet (Umbau in #239). Filter: alles, wonach Earth Search filtern kann, je Feld an der Quelle belegt und im Live-Test – ebenfalls in #239 (keine eigene Aufgabe, Otto).
   - **DS-02a erledigt** (PR #217, gemergt 28.10.2026): Filter je Datensatz in der Registry (`earthx:search_filters`; S2: Cloud cover, No data, Satellite), `query_by_collection`, `adr/0021`; Live-Abgleich `tests_live/test_search_filters_live.py`, eingetragen im Job `earth-search` von `live-smoke.yml` (ausdrückliche Ausnahme für `.github/`, Otto 28.10.2026). Orbit-Richtung und relative Umlaufbahn tragen S2-Items nicht, kommen mit DS-04 für S1. Offen: DS-02b (Coverage), DS-02c (Oberfläche, Umschalter je Datensatz).
   - **DS-02b erledigt** (PR #226, 28.10.2026): `GET /coverage/{id}` nimmt `query` wie die Suche, `max_cloud_cover` entfällt; Prüfung gegen die Registry, Fehler der Quelle nur als Status.
   - **DS-01 erledigt:** `adr/0018` Fassung 2 (PR #200): keine regionale Quelle; Earth Search `sentinel-1-grd` als Level-1-Datensatz mit TPS-Georeferenz überall und Hinweisen „Approximate geolocation“/„Uncalibrated (DN)“; Planetary Computer RTC nur nach positiver Messung durch Otto (anonymes Token zulässig unter Bedingungen, Originale per Klick); eigene Geländekorrektur als eigenes ADR nach DS-04.
   - **Pläne:** `ds/ds-00-paket.md` (Übersicht) und `ds/ds-01` bis `ds/ds-06`: Sentinel-1-Quelle (C), „Advanced search“ (B), Wolken in der AOI (B), S1 anbinden (A), SAR-Operatoren (B), Maske nach Werten (B).

33. **Originale mit einem Klick herunterladen** (Otto, 26.10.2026: „einfach einen Download-Button drücken ohne extra Steps“).
   - **Freigegeben (Otto, 29.10.2026, PR #233):** A2 – ein Klick lädt `ATTRIBUTION.txt` und die Originale nacheinander direkt von der Quelle (mit CORS per `fetch` unter `<Szene>_<Asset>.tif`, ohne CORS als normaler Browser-Download), kein Byte über das Backend; Grenze 500 MB je Datei (Wiedervorlage DS-04 wegen S1 um 1 GB). Offen: ob der Browser einmalig nach „mehrere Dateien“ fragt (Prüfung bei Otto).
   - **Plan:** `querschnitt/nm4-33-originale-ein-klick.md`
   - **Benennung (UI-01g, Otto 26.10.2026):** Der Knopf heißt „Download full scene“ bzw. bei mehreren Szenen „Download full scenes“ (Originale, nicht gemergt).
   - **Entscheidet mit:** den offenen Punkt „Originale als ZIP über die Plattform“ (unten). Wege: direkte Downloads nacheinander, ZIP über die Plattform, ZIP im Browser (CORS je Quelle).
   - **Aufgabe:** Stufe B mit Recherche und Messung, nach UI-01.

34. **Job neu starten („Retry“) und Umbenennen im Processing-Fenster** (Otto, 26.10.2026).
   - **Erledigt:** NM4-34, PR #225 (28.10.2026): ↻ bei gescheiterten, abgebrochenen, abgelaufenen und „No longer available“-Jobs (mit Auftragskopie), auch `disk_space` und `source_429`; nicht bei `source_4xx`/`runtime_exceeded` („Open in panel“). Neuer Job an derselben Stelle, alter als „Superseded“ archiviert; „Retry failed parts“; Umbenennen per Klick auf den Titel.
   - **Plan:** `querschnitt/nm4-34-job-neu-starten.md`
   - **Soll:** Ein kleines Symbol (↻, kein Tastenkürzel) startet einen gescheiterten, abgebrochenen oder abgelaufenen Job mit demselben Auftrag neu; bei einem Batch nur die gescheiterten Teile. Der neue Job ersetzt den alten in der Zeile, der alte wird archiviert. Wo es nicht geht (keine Auftragskopie, Datensatz ausgeschieden), erscheint das Symbol nicht. Dazu: Titel direkt in den Details im Processing-Fenster umbenennen.
   - **Aufgabe:** Stufe A, nur Frontend, nach UI-01f, nicht gleichzeitig mit NM4-27.

35. **Relief (Schummerung) als Overlay und optional als Basemap** (Otto, 27.10.2026; Vorschlag aus UI-02).
   - **Plan:** `querschnitt/nm4-35-relief.md`
   - **Soll:** Schalter „Relief“ bei den Overlays des Basemap-Menüs, über jeder Basemap; optional Basemap „Relief“. Erste Option: MapLibre zeichnet `hillshade` im Browser aus freien Höhenkacheln (etwa AWS Terrain Tiles), ohne Backend und Pyramide; Alternative: eigenes Copernicus DEM.
   - **Aufgabe:** Stufe B mit Recherche, nach UI-02a.
   - **Erledigt (PR #222, 28.10.2026):** Option A (MapLibre `hillshade`, AWS Terrain Tiles, bis Zoom 12), Basemap „Relief“ allein, nur die Basemap im Permalink. Attribution: Kurzform „Terrain: USGS, NOAA, EU-DEM (Copernicus) and others“ als Link auf die Joerd-Liste; Rest-Risiko bei CC BY 3.0 AT/NZ, OGL Canada, EU-DEM, INEGI von Otto in Kauf genommen, **vor dem öffentlichen Betrieb (M6) rechtlich prüfen**.
43. **Ausgabe-Bänder statt Bandauswahl, Band-Math-Ergebnisse als eigene Bänder, keine Bandgrenze** (Otto, 27.10.2026).
   - **Plan:** `querschnitt/nm4-43-ausgabe-baender.md`
   - **Soll (Otto):** keine Obergrenze für die Zahl der Bänder; ein `band_math`-Ergebnis wird ein eigenes Band; oben keine Auswahl mehr, nur Info und Namenshilfe; am Ende des Panels alle Bänder des Datensatzes und alle neu gerechneten, per Klick in die Ausgabe. Standardmäßig ist nur das Band-Math-Ergebnis in der Ausgabe; mehrere `band_math`-Schritte hintereinander mit unterschiedlichen Bändern sind möglich.
   - **Aufgabe:** Stufe C, ADR-Entwurf `adr/0020` mit Messung und Recherche (Schutz ohne Bandgrenze, Ausgabedatei mit gemischten Typen, Vorschau, Hash, alte Rezepte). Nimmt NM4-10 in sich auf; NM4-11, NM4-14, NM4-20, DS-06 warten auf die Entscheidung.
   - **Entschieden (Otto, 28.10.2026, PR #219):** `adr/0020` angenommen, F1–F13 Option 1 außer F7 Option 2 (ohne `band_math` alle wählbaren Bänder angehakt). Aufgaben in §6 des Plans: NM4-43a (Schätzung nach feinstem Asset; erledigt #224, `adr/0014` §15v) und NM4-43b (`reproject` Version 4 je Band; erledigt #229, band-Interleave für Zwischendateien, Version 0.4.4, „§15 Nachtrag NM4-43b“) sofort und unabhängig; dann NM4-43c (Kern, zwei PRs; PR 1 erledigt #236, PR 2 erledigt #241: keine Bandgrenze, Speicherschätzung 1,5 GB je Kindprozess, `units` je Schritt nach eigenen Bändern), NM4-43d (Kachel), NM4-43e (Frontend). Runner liest Rezept-Version 1 dauerhaft; `api` bis 30 Tage nach dem Deploy von NM4-43e. NM4-11, NM4-14, NM4-20, DS-06 nach NM4-43c.
44. **Schwachstellen der Frontend-Pakete prüfen (`npm audit`)** (Otto, 27.10.2026; 8 Meldungen bei `npm install`, dazu Node-Version für `jsdom`).
   - **Plan:** `querschnitt/nm4-44-npm-audit.md`
   - **Aufgabe:** Stufe A, nach UI-02a (#211). Gezielt aktualisieren, kein `npm audit fix --force`; Hauptversionssprung nur nach Ottos Freigabe.
45. **Einzelne Bänder in der Vollauflösungs-Ansicht per Dropdown** (Otto, 27.10.2026).
   - **Zusammengelegt (29.10.2026):** wird mit Paket NM4-54 umgesetzt; nicht einzeln starten.
   - **Plan:** `querschnitt/nm4-45-band-in-ansicht.md`
   - **Soll:** Dropdown „Band“ in der Ansicht, Vorgabe `visual`, dazu jedes Band aus der Registry; bei einem Band Colormap, vmin/vmax, „auto-scale“; Anheften behält das Band. Nur Einzelbänder.
   - **Aufgabe:** Stufe A, Frontend, nach NM4-53 (beide ändern die Leiste der Ansicht).

46. **Eigene Dateien hochladen** (Otto, 28.10.2026: „dass ich eigene dateien hochladen kann“).
   - **Stand heute:** Nur AOIs lassen sich hochladen (GeoJSON, KML, Shapefile als ZIP; M3-06a/b), nichts wird gespeichert. Eigene Rasterdaten gibt es nicht.
   - **Geplant:** `projektplan.md` M7 Paket 7h „eigene Daten per URL“, Voraussetzung M6 (Login, Quotas, Speicher je Nutzer).
   - **Offen (Otto):** welche Dateien (eigene GeoTIFF/COG zum Ansehen und Rechnen, Vektoren als Overlay, Ergebnisse anderer Tools); Upload der Datei oder Verweis per URL; privat oder teilbar; Aufbewahrung.
   - **Zu beachten:** Härtung der Dateiverarbeitung (projektuebersicht §4: Größenlimits, Timeouts, Treiber-Allowlist), Datenschutz, Lizenz der eigenen Daten, Speicherkosten. Erst als ADR (Stufe C), frühestens mit M6.
   - **Otto, 28.10.2026:** bleibt in M7. Zwei Stufen für den ADR: (1) lokale Datei bleibt auf dem Rechner und ist ein normaler Layer, gerendert im Browser (eigene Kachelquelle in MapLibre, etwa geotiff.js): Anzeige, Band, Colormap, vmin/vmax, Zuschnitt-Download, kleine Band-Math-Vorschau; keine Server-Jobs, kein Teilen per Permalink. (2) Upload oder URL für Jobs und Teilen (M6/M7). Ganz ohne Unterschied nur mit lokalem tiler im Runner (M7 Paket 7f). Recherche: Bibliotheken, Browser-Unterstützung (File System Access nur Chromium), Dateigrößen, COG gegen GeoTIFF ohne Übersichten.
   - **Otto, 28.10.2026:** Für Einzelnutzer ist Stufe 1 (lokal) gut. Zusätzlich gewünscht: Projekte, für die mehrere Nutzer freigeschaltet sind, mit geteilten Dateien. Gehört zu `projektplan.md` M7 Paket 7h (Arbeitsbereiche, Voraussetzung M6). Im ADR mitdenken: Dateien eines Projekts liegen im Objektspeicher des Projekts (Stufe 2); eine lokale Datei lässt sich mit einem Klick ins Projekt hochladen; Rollen (lesen/bearbeiten), Kontingent je Projekt, Lizenz beim Teilen abgeleiteter Daten, Löschen beim Austritt.
   - **Otto, 28.10.2026:** Ein Reiter „Projects“ speichert alles Nutzerspezifische (Arbeitsstand: AOI, Zeitraum, Datensätze, Filter, Kartenausschnitt, Layer, Auswahl, offene Rezepte). Ein Neuladen ohne Projekt bleibt wie heute (Auswahl weg); kein eigenes Wiederherstellen der Sitzung im Browser.
47. **Item-IDs in Logs** (aus NM4-19, #218, 28.10.2026). Abgelehnte Annahmen und der Item-Abruf loggen die Item-ID; die Regel verbietet AOI, Job-/Bündel-/Permalink-Kennungen, Hashes, `href` und signierte URLs, aber keine Item-IDs. Eine Item-ID verrät grob den Ort des Interesses (MGRS-Kachel, rund 110 km).
   - **Aufgabe:** Mit der Datenschutzprüfung von M6 entscheiden (alle Routen einheitlich: behalten, kürzen oder entfernen). Bis dahin unverändert.
48. **Datennähe: eine Hauptquelle, Rechnen und Rendern dort, wo die Daten liegen** (Otto, 28.10.2026).
   - **Anlass:** Lokal gemessen (28.10.2026) braucht die erste Mosaik-Kachel kalt 6,0 s, fast alles ist Weg über das Netz. Sentinel-2 von Earth Search liegt in AWS `us-west-2` (Oregon); die Plattform soll in EU/CH laufen (projektuebersicht §4).
   - **Kandidaten:** (A) Earth Search mit Rechnern in AWS `us-west-2` (schnell, aber außerhalb der EU); (B) Copernicus Data Space Ecosystem mit CloudFerro bzw. Open Telekom Cloud (EU, alle Copernicus-Daten, S3-Zugang mit kostenlosem Konto); (C) Planetary Computer mit Azure West Europe (EU, viele Datensätze, Token anonym).
   - **Aufgabe:** Stufe C, ADR mit Recherche und Messung (Latenz und Durchsatz je Region, Kosten, Abdeckung der Datensätze, Lizenz, Ausfall, Bindung an einen Anbieter; Föderation bleibt). Vor der Wahl des Cloud-Anbieters in M6, am besten zu Beginn von M5 (Auswahl der Quellen). Messung braucht Ottos Rechner oder Test-VMs, aus Cloud-Sessions sind die Quellen nicht erreichbar (adr/0002).
49. **Unbekannte Query-Parameter abweisen** (aus DS-02b, #226, 28.10.2026). Heute ignorieren Routen unbekannte Parameter still; ein alter Client mit `max_cloud_cover` bekäme eine ungefilterte Coverage-Karte. Solange das eigene Frontend der einzige Client ist, bleibt es so (Otto). Mit der öffentlichen API (M6) einheitlich entscheiden: unbekannte Parameter mit `400` und Namen des Parameters (ohne Wert) abweisen.
50. **DEM: Layer-Manager und Ergebnisse wie bei Sentinel-2; Augen-Symbol** (Otto, 28.10.2026). Beim DEM wird ein Layer nicht immer ausgeblendet, Colormap und Skala werden nicht gespeichert, Show/Hide results verhält sich anders als bei S2. Der Sichtbarkeits-Schalter im Layer-Manager wird ein Auge. Die Vorschau eines DEM-Ergebnisses zeigt die ganze Kachel statt des Zuschnitts (ersetzt teilweise die Entscheidung vom 26.09.2026, M3-12).
   - **Erledigt:** NM4-50, PR #234 (30.10.2026): eigener DEM-Weg (`searchCrops`) ausgebaut, Vorschau ganze Kachel, Haken über Datensätze, Auge im Layer-Manager, „Apply“/„Save“, „auto-scale“ einheitlich, offener Datensatz liegt oben.
   - **Zusatz (Otto, 29.10.2026, an #234):** Layer-Manager mit „Apply“ (zeigt auf der Karte) und „Save“ (speichert für den Layer dauerhaft); ungespeicherte Änderungen verfallen beim Schließen der Einstellungen ohne Rückfrage.
   - **Plan:** `querschnitt/nm4-50-dem-layer-und-ergebnisse.md`
   - **Aufgabe:** Stufe A, Frontend, Vorrang vor neuen Funktionen. Ein Weg für alle Datensätze, keine Zweige je Datensatz.
51. **Hinweis „resampled to common grid“ nur, wenn Werte betroffen sind** (Otto, 28.10.2026). Kein Hinweis, wenn nur die Maskenschicht (`scl`, nächster Nachbar) auf das Raster gebracht wird; Hinweis bleibt, wenn Wertebänder umgerechnet werden (verschiedene Auflösungen oder CRS/UTM-Zonen). Grund nur im Tooltip.
   - **Aufgabe:** mit NM4-43e (Panel-Umbau), Stufe A; vorher prüfen, ob die Annahme im Backend beide Fälle schon unterscheidet. Der NM4-43e-Session beim Start mitgeben.
52. **Tooltips liegen immer über allem und bleiben im Fenster** (Otto, 28.10.2026; Anlass: Tooltip am Rufzeichen wird von anderen Kästen verdeckt).
   - **Erledigt:** NM4-52, PR #238 (30.10.2026): Tooltips über eine Schicht in `App`, außerhalb jedes Panels, Platzierung mit Ausweichen, `Esc`.
   - **Plan:** `querschnitt/nm4-52-tooltips-ueber-allem.md`
   - **Aufgabe:** Stufe A, Frontend, klein.
53. **Ansicht nach „Crop & merge“ über mehrere Gruppen und Datensätze: Zeitschritte durchschalten** (Otto, 28.10.2026). Kleine Zeile `‹ Datum · S2A ›` in der Leiste der Ansicht, Dropdown für den Datensatz, „Add to layers“ nur der angezeigte Zeitschritt, neu „Add all to layers“. „Apply“ wirkt auf das angezeigte Bild, „Save“ für alle Bilder des Datensatzes in der Ansicht (nicht dauerhaft), §2.1 des Plans (Otto, 29.10.2026).
   - **Plan:** `querschnitt/nm4-53-ansicht-mehrere-zeitschritte.md`
   - **Aufgabe:** Stufe B, Frontend, nach NM4-50; danach NM4-45 (beide ändern die Leiste der Ansicht). Der Fehler „Haken verschwinden beim Wechsel der Gruppe/des Datensatzes“ geht an NM4-50.
54. **Paket Ansicht und Anheften** = NM4-12, NM4-25, NM4-24, NM4-45 in einer Session (Otto, 29.10.2026: kleine Sessions zusammenlegen). Plan: `querschnitt/nm4-54-paket-ansicht.md`. Nach NM4-53.
55. **Paket Suchergebnisse und Zeitleiste** = NM4-09, NM4-18. Plan: `querschnitt/nm4-55-paket-suchergebnisse.md`. Sofort möglich, nicht gleichzeitig mit DS-03b.
56. **Paket Oberfläche** = NM4-30, NM4-21, NM4-22. Plan: `querschnitt/nm4-56-paket-oberflaeche.md`. Als letzte Frontend-Aufgabe vor M5, allein.
   - Außerdem: NM4-06 wird mit NM4-05b zusammen umgesetzt (Vermerk im Plan von NM4-05b).
57. **Keine AOI in URLs, keine Dateiadressen in Logs** (erweitert 30.10.2026 um GDAL-Meldungen mit voller Adresse, Fund aus DS-03a2, #240) (Fund aus DS-02c, #239, 30.10.2026). `GET /coverage` trägt mit AOI deren Umriss als `bbox` in der URL (seit M3-19). Das verstößt gegen die feste Regel „keine AOI in URLs oder Logs“ (M4 Q8). Soll: Coverage mit AOI als `POST`, AOI im Body; ohne AOI (Kartenausschnitt) darf `GET` bleiben. Prüfen, ob Logs oder Cache-Schlüssel die bbox tragen.
   - **Plan:** `querschnitt/nm4-57-coverage-ohne-aoi-in-url.md`
   - **Aufgabe:** Stufe A, Backend und Frontend, Vorrang vor neuen Funktionen.
58. **Toolbar des Control-Menüs bei 320 px etwa 8 px zu breit** (Fund aus DS-02c, #239). Wird mit Paket NM4-56 erledigt.
59. **Suchergebnisse als Eintrag „Results“ im Layer-Manager** (Otto, 30.10.2026). Mit Reihenfolge und Auge statt „Show/Hide results“; die Ebenenlogik der Suchergebnisse stützt sich auf den Layer-Manager. Dazu Fehler: nach Hide/Show erscheinen angehakte Ergebnisse nicht immer wieder.
   - **Plan:** `querschnitt/nm4-59-results-als-layer.md`
   - **Aufgabe:** Stufe B, Frontend; Code nach NM4-55 (#242), vor NM4-53 und NM4-54.
60. **Normalize je Batch mit gleichen Werten** (Wiedervorlage aus NM4-11, #244): Option „gleiche Werte für alle Aufträge“, damit normalisierte Zeitreihen vergleichbar sind.
## In UI-01 aufgenommen (20.–22.10.2026)

- Reihenfolge im Layer-Manager greift manchmal nicht (UI-01 §1 Punkt 10, Diagnose mit Test zuerst; Otto liefert die Schritte zum Nachstellen).
- Klick auf einen Ergebnis-Layer öffnet die Darstellung: vmin, vmax, Colormap, Vorgabe aus M4-32 (UI-01 §1 Punkt 11).
- Gleiche Breite der Layer-Zeilen mit festen Knopfpositionen (Punkt 8).
- Download eines Ergebnisses aus dem Layer-Manager (Punkt 9).
- Je fertigem Job nur „Download (ZIP)“, kein „Methods“, kein „Copy“ (Punkt 12).
- Handbereich der Farbskala je Job dauerhaft speichern (§3 Punkt 1).
- Stapelung zwischen Überflügen: Ansicht und angeheftete Layer stapeln verschieden (bekannte Grenze aus M4-17c §15), Prüffall in UI-01 §1 Punkt 10.
- In UI-01g aufgenommen (Otto, 26.10.2026, direkt an die Session): Umschalter „Show results / Hide results“ statt „Clear all“ (Ergebnisse auf der Karte immer über allen Layern; Auswahl bei verborgener Kartenanzeige erscheint trotzdem mit den normalen Steuerelementen); Anzahl in Klammern neben „Results“; Steuerleiste einer Auswahl ohne „Full resolution“-Titel, gleich große Felder, kein „Clear“; Zeitleiste ohne „Add to layers“ und „Select all frames“; Benennung (Otto, 26.10.2026): eine Szene „Crop to AOI“, „View whole scene“, „Download crop“, „Download full scene“; mehrere Szenen „Crop & merge to AOI“, „View merged scenes“ (die ganzen Szenen werden in der Ansicht gemergt), „Download merged crop“, „Download full scenes“. „Clear search results“ mit rotem ✕ unter „Load more“. Ein Klick auf einen angehefteten Layer (Zuschnitt, Ergebnis) wählt nichts in den Suchergebnissen aus – Layer und Suchergebnisse sind vollständig entkoppelt.
- Fehler nach UI-01g (Otto, 27.10.2026), Auftrag an die UI-02a-Session (#211, eigener Commit): Zuschnitt lässt sich nicht entfernen; nach dem Verlassen der Ansicht erscheint der Quicklook trotz „Hide results“. Regel: „Hide results“ gilt immer, einzige Ausnahme ist die Auswahl; nur der Umschalter ändert den Zustand. Dazu: Knopf „Clear“ in der Steuerleiste der Ansicht (ersetzt „kein Clear“ aus UI-01g), weniger Text im Kopf, Knopfzeilen gleich breit, Text nicht breiter als die Knopfzeilen. Erledigt mit #211 (28.10.2026).

## Offen im Entscheidungslog (bewusst nach M4)

36. Earth Search v2: `sentinel-2-c1-l2a` wird durch `sentinel-2-l2a` ersetzt (Termin offen, Quelle im Log von M4-12a).
37. Originale als ZIP über die Plattform: **entschieden nein** (Otto, 29.10.2026, NM4-33, #233). Das kostet Bandbreite und gibt Daten über die Plattform weiter, und ein Abbruch lässt sich nicht fortsetzen (M4-11b-2).
38. Festes nodata je Ganzzahltyp für Quellen ohne nodata, dazu die Kollision gültiger Werte mit nodata nach dem Klemmen (M4-26).
39. Triage-Routine bei rotem Live-Smoke (projektplan §6, nicht eingerichtet; M4-27 §4).
40. Punkte aus S3 (M4-Plan Fassung 3):
    - Export-Job für Zarr blockweise,
    - schnelleres COG-Profil,
    - Laufzeitdeckel an echten Läufen kalibrieren,
    - Zähler der Verbindungen je Lauf,
    - Job-Schnittstelle in eigenem Prozess,
    - Eingaben per Referenz (siehe Punkt 5),
    - Datei-Cache des Runners.
41. CI: Umstellung von `ubuntu-latest` auf Ubuntu 26, Node-20-Warnungen der Actions, kein `cancel-in-progress`. Entschieden, `.github/` nicht zu ändern (19.10.2026). Neu entscheiden, sobald die CI ohne Codeänderung an Systempaketen scheitert.

## Danach geplant

42. VP3: UI-01 (App-Rahmen, Processing-Manager, Batch, „Download all“, Layer-Manager mit den Punkten 8–12), dann UI-02 (Basemap, Projektion). Siehe `projektplan.md` v1.5. **UI-01 abgeschlossen** mit UI-01a bis UI-01g (#188, #191, #196, #202, #206, #208, #209; 26.10.2026). **UI-02a erledigt** (#211, gemergt 28.10.2026; mit Ottos Zusätzen zu Ergebnissen auf der Karte, Ansicht, festen Plätzen der Leisten). **UI-02b erledigt** (#220, gemergt 28.10.2026; Labels global, Vorgabe aus). Offen: UI-02c (Permalink), Schnitt in `vp3/ui-02-basemap-projektion.md` §6.9.

## Verworfen bzw. nur bei Bedarf

- Zarr im Viewer generell durch COG ersetzen (Daten umwandeln): nein. Davon getrennt steht Punkt 15 (Zarr-Datensatz als Doppel entfernen). Jeder Datensatz bleibt bei seiner Quelle. Nur falls Zarr im Viewer langsam auffällt, folgt eine Messung (Stufe C) zu GeoZarr-Multiscales und Quicklooks.
- „Replace source layer“ für Vorschau und Job-Ergebnis: von Otto entfernt (20.10.2026).
- Knopf zum Kopieren des Methodentexts: von Otto abgelehnt (22.10.2026).
- QGIS-Stildatei (`result.qml`) im Job-ZIP: von Otto verworfen (25.10.2026), weil bei Analyse-Rastern nicht üblich; die Statistik steht als GDAL-Tags in `result.tif` (M4-32).
- Equal Earth (und andere Projektionen außer Mercator/Globe) in der Kartenansicht: von Otto zurückgestellt (27.10.2026); MapLibre kann es nicht, ein Wechsel der Kartenbibliothek lohnt nicht.
- CI bei reinen Plan-Änderungen verkürzen (Filter im Job oder zweiter Workflow): von Otto verworfen (24.10.2026); `.github/` bleibt unverändert.
