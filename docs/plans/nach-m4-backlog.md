# Nach der M4-Abnahme: gesammelte Punkte

Stand: 24.10.2026. Otto hat entschieden, zuerst alles bis zur M4-Abnahme (M4-20) fertig zu machen. Danach werden diese Punkte der Reihe nach aufgegriffen. Reihenfolge laut Log vom 24.10.2026: DOC-01, dann UI-01 und UI-02; NM4-01 und NM4-02 als Stufe A daneben. Für die übrigen Punkte entscheidet Otto die Reihenfolge.

## Neu (Plan-Dateien unter `docs/plans/querschnitt/`)

1. **Jahr in der Copernicus-Attribution** (Fund vom 20.10.2026, `provenance.json` des Runners).
   - **Plan:** `querschnitt/nm4-01-attribution-jahr.md`
   - **Befund:** Dort steht „Contains modified Copernicus Sentinel data 2026“, die Szene ist aber vom 29.07.2025.
   - **Vermutung:** Das Jahr kommt aus dem aktuellen Datum statt aus der Aufnahme.
   - **Aufgabe (Stufe A):**
     - zuerst den Wortlaut der Copernicus Sentinel Data Terms mit Quelle prüfen,
     - dann das Jahr aus dem Aufnahmedatum ableiten, bei mehreren Jahren als Spanne, etwa „2024–2025“,
     - eine Stelle für alle Downloads (Zuschnitt, Export, Job, Runner, Linkliste der Originale) und für `citation.bib`.
2. **Zuschnitt und Export auf die Sortierung des Mosaik-Jobs angleichen** (M4-17, Frage 2, 20.10.2026).
   - **Plan:** `querschnitt/nm4-02-sortierung-zuschnitt.md`
   - **Befund:** Die Regel „erstes gültiges Pixel“ ist überall dieselbe, die Reihenfolge der Szenen aber nicht:
     - Mosaik-Job und Mosaik-Kachel sortieren nach Ziel-CRS und Item-ID,
     - Zuschnitt und Export folgen der Reihenfolge der Auswahl.
   - **Folge:** In schmalen Überlappungen kann die Vorschau eine andere Szene zeigen als der Zuschnitt.
   - **Aufgabe (Stufe A):** dieselbe Sortierfunktion für Zuschnitt und Export verwenden. Weil sich dadurch die Bytes des Zuschnitts ändern, gehört die Änderung in die Versionierung.
   - **Erledigt:** NM4-02 (`querschnitt/nm4-02-sortierung-zuschnitt.md`), 25.10.2026, Draft-PR; `adr/0014` §15p, Version 0.4.3.
3. **Absolute URL für den Link `tiles`** im Ergebnisdokument (M4-13c-5). Heute ist der Link relativ, ein API-Client ohne den gemeinsamen Proxy findet den `tiler` damit nicht. Spätestens mit der öffentlichen API in M6 nötig.
   - **Plan:** `querschnitt/nm4-03-tiles-url-absolut.md`
   - **Erledigt:** NM4-03, 25.10.2026, Draft-PR [#193](https://github.com/oscipal/earthX/pull/193); `EARTHX_TILER_URL`.
   - **Vermerk für M6 (Otto, 25.10.2026):** Die übrigen Links des Ergebnisdokuments und des Auftrags bleiben relativ. Sie liegen auf `api` selbst und lösen sich gegen die Dokument-URL auf. Mit der öffentlichen API (M6) neu prüfen; ein mögliches `EARTHX_API_URL` nach dem Muster von `EARTHX_TILER_URL` wäre dann eine eigene Entscheidung.
4. **Mosaik mit Operator im Kachel-Pfad,** also eine Vorschau des Mosaik-Jobs mit Band math (M4-17, Frage 4).
   - **Plan:** `querschnitt/nm4-04-mosaik-mit-operator.md`
5. **Processing auf einem Ergebnis** (Otto, 20.10.2026), also ein Job-Ergebnis als Eingabe eines neuen Rezepts.
   - **Plan:** `querschnitt/nm4-05-processing-auf-ergebnis.md`
   - **Warum eine Vorlage nötig ist:** Das ist eine neue Art von Eingabe neben Datensatz und Item. Sie berührt „Eingaben per Referenz“ (S3), B8, Herkunft und Ablauf nach 7 Tagen.
   - **Aufgabe:** zuerst eine Entscheidungsvorlage (Stufe C), dann die Umsetzung.
   - **Abgrenzung zu UI-01:** UI-01 sperrt bis dahin den Processing-Knopf bei Ergebnis-Layern mit Grund (UI-01 §1 Punkt 11).
6. **Gemergter Zuschnitt als ein Objekt im Panel** (Otto, 20.10.2026).
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
8. **Methodentext ins Rezept, `methods.txt` entfällt** (Otto, 22.10.2026).
   - **Plan:** `querschnitt/nm4-08-methodentext-ins-rezept.md`
   - **Soll:** `recipe.json` trägt den Methodentext im Block `provenance` als Feld `methods`. Dieser Block geht nicht in den Hash ein, und der Runner trennt ihn beim Einlesen ab (M4-16 F3). Die eigene Datei `methods.txt` entfällt im ZIP und im Runner.
   - **Folgen:**
     - die Definition der Download-Inhalte aus M4-30 und `TEXT_FILES` (M4-19a) anpassen,
     - der Runner schreibt den Text ebenfalls in seine `recipe.json`,
     - Link und Ausgang `methods` in der API: im Plan klären, ob sie bleiben oder entfallen,
     - Nachtrag in `adr/0014`.
   - **Kein Knopf zum Kopieren,** nirgends im Frontend (Otto, 22.10.2026). Die Einträge „Methods“ und „Copy“ der Jobliste entfernt UI-01 (§1 Punkt 12).
   - **Aufgabe:** Stufe A, Backend und Runner.
9. **Feste Gruppenköpfe in den Suchergebnissen** (Otto, 22.10.2026).
   - **Plan:** `querschnitt/nm4-09-feste-gruppenkoepfe.md`
   - **Soll:** Beim Scrollen durch die Suchergebnisse bleibt der Kopf der aktuellen Gruppe oben stehen, solange Einträge dieser Gruppe sichtbar sind. Der Kopf der nächsten Gruppe schiebt ihn dann hinaus („sticky header“).
   - **Gilt mit allem, was im Kopf steht:** Name der Gruppe, Anzahl („loaded (of N)“), „Select all“ der Gruppe (M4-29) und Auf- und Zuklappen.
   - **Zu prüfen:** Der Kopf verdeckt keinen Eintrag, das Nachladen weiterer Treffer am Listenende greift weiter, und das Verhalten passt auch auf schmalen Bildschirmen.
   - **Aufgabe:** Stufe A, nur Frontend. Weil UI-01 die Leisten und Panels neu ordnet, kommt der Punkt nach UI-01 oder wird dort mit aufgenommen.

10. **Laufnummer und Band-Chips für Ergebnisse von Schritten** (Otto, 22.10.2026).
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
   - **Plan:** `querschnitt/nm4-14-index-knoepfe.md`
   - **Soll:** An einem Layer eines passenden Datensatzes (etwa „Crop & merge to AOI“ von Sentinel-2) gibt es Knöpfe für häufige Indizes, etwa NDVI, NDWI, NDSI, NBR, EVI. Ein Klick erzeugt einen ganz normalen Band-math-Schritt mit Vorschau; Start als Job wie gewohnt.
   - **Kein zweiter Weg:** Die Knöpfe füllen nur das Rezept. Vorschau, Job, Cache, Runner, Methodentext und `recipe.json` bleiben dieselben.
   - **Je Datensatz, nicht im Code:** Die Bandnamen unterscheiden sich je Quelle (COG gegen EOPF-Zarr). Die Presets stehen deshalb als Daten in der Registry je Datensatz (Name, Ausdruck, Wertebereich, Colormap-Vorgabe, Quelle der Formel); nur Datensätze mit passenden Bändern zeigen sie. Kein datensatzspezifischer Code.
   - **Quellen:** Formeln mit Beleg, etwa Awesome Spectral Indices (Montero et al., 2023, *Scientific Data*) oder Index DataBase; bei Indizes mit Konstanten (EVI) die Werte mit Quelle.
   - **Zu klären im Plan:** Welche Indizes zuerst; ob die Knöpfe am Layer, im Panel oder an beiden Stellen sitzen (Abstimmung mit UI-01); ob ein Preset die Bänder automatisch wählt (Punkt 7) und den Ergebnisnamen setzt (Punkt 10, etwa `NDVI`); Verhalten bei Mosaik (Punkt 4) und mit `mask` davor („NDVI cloud-free“ als Preset-Kette?).
   - **Aufgabe:** Stufe B (Registry-Feld, Panel), Backend und Frontend.

15. **Nur ein Sentinel-2-L2A-Datensatz sichtbar** (Otto, 22.10.2026).
   - **Plan:** `querschnitt/nm4-15-ein-sentinel-2-datensatz.md`
   - **Erledigt (Vorlage):** `adr/0017`, PR #189, von Otto am 25.10.2026 angenommen (F1–F6 je Option 1). Die Umsetzung folgt als NM4-15b nach dem Merge.
   - **Wiedervorlage Formatachse (F4):** Anfang 2027 oder früher, sobald EOPF operative Zarr-Produkte meldet.
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
   - **Heute:** `aot`, `wvp`, `cloud`, `snow` und `preview` haben in der Registry keine Einheit (`earthx:band_units`), weil die Session keine Quelle dafür gelesen hat.
   - **Aufgabe (Stufe A):** Einheiten mit Quelle nachtragen (Produktspezifikation Sentinel-2 L2A bzw. Item-Metadaten); wo keine Einheit sinnvoll ist (etwa `preview`), das bewusst vermerken. Hinweis: Eine Korrektur der Einheit ändert den Hash (`adr/0014` §15n), also einmal kein Cache-Treffer.

17. **„Clear all“ wird „Clear search results“** (Otto, 24.10.2026).
   - **Plan:** `querschnitt/nm4-17-clear-search-results.md`
   - **Soll:** Der Knopf in den Suchergebnissen heißt „Clear search results“ und löscht nur die Ergebnisliste. Danach öffnet sich wieder das Control-Panel.
   - **Bleibt bestehen:** alle Sucheinstellungen, also AOI, Zeitraum, Datensatzwahl, Filter (etwa Wolkenbedeckung). Ein neuer Klick auf „Search“ sucht mit denselben Einstellungen.
   - **Im Plan zu klären:** was mit angehefteten Layern, offener Ansicht (Mosaik aus M4-17) und Jobs passiert (Vorschlag: angeheftete Layer und Jobs bleiben, die offene Ansicht schließt); wo man AOI und Einstellungen künftig zurücksetzt (eigener Knopf im Control-Panel, falls es keinen gibt); Abstimmung mit UI-01 (linke Leiste, Control-Menü).
   - **Aufgabe:** Stufe A, nur Frontend; Test, dass nach dem Löschen alle Einstellungen erhalten sind.

18. **Abspielen in der Timeline ohne Lücken** (Otto, 24.10.2026).
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
   - **Plan:** `querschnitt/nm4-19-auto-stretch-ueber-aoi.md`
   - **Heute (M4-19c):** Die Messung für die Farbskala der Vorschau gilt für die erste Szene der Karte, auch bei „AOI only“ für die ganze Szene. Das Job-Ergebnis nimmt dagegen die Statistik über die AOI-Maske (M4-32). Vorschau und Ergebnis können sich deshalb unterscheiden.
   - **Soll:** Bei „AOI only“ misst auch die Vorschau über die AOI, damit Vorschau und Ergebnis dieselbe Farbskala zeigen.
   - **Harte Grenze:** Keine AOI in URLs oder Logs. Die AOI geht nur im Body an den `tiler` (etwa `POST /statistics` wie bei rio-tiler, mit der Geometrie als GeoJSON), nie als Query; Caching dann über einen Hash im Body, der nicht geloggt wird.
   - **Im Plan zu klären:** Schnittstelle (POST-Route, Größen- und Punktgrenze der Geometrie wie bei der Annahme), Cache-Schlüssel ohne AOI im Klartext, Messung über mehrere Szenen bzw. Mosaik eines Überflugs, gleiche Methode wie im Job (festes Histogramm, M4-32a) damit die Werte übereinstimmen, Kosten.
   - **Aufgabe:** Stufe B (neue Route im `tiler`, Datenschutz), Backend und Frontend.

20. **Processing-Panel klarer gegliedert** (Otto, 24.10.2026).
   - **Plan:** `querschnitt/nm4-20-panel-gliederung.md`
   - **Soll:** Die Bereiche „Bands“, „Processing steps“, „Output“ und „Preview“ sind deutlich voneinander abgesetzt (etwa eigene Karten oder Abschnitte mit Überschrift, Abstand, Trennlinie, ggf. einklappbar).
   - **Im Plan zu klären:** Gestaltung in Hell- und Dunkelmodus, Reihenfolge, schmale Bildschirme; Abstimmung mit UI-01 (größeres Fenster, linke Leiste) und mit den Punkten 7, 10 und 14 (Bandauswahl, Band-Chips der Schritte, Index-Knöpfe).
   - **Aufgabe:** Stufe A, nur Frontend; Prüfung im echten Browser (Playwright), nicht nur jsdom.
21. **Einheitliches Zahlenformat in der ganzen Web-App** (Otto, 24.10.2026).
   - **Plan:** `querschnitt/nm4-21-zahlenformat.md`
   - **Soll:** Angezeigte Zahlen haben höchstens drei Nachkommastellen. Sehr kleine (und sehr große) Beträge erscheinen wissenschaftlich, etwa 0.000000052 → `5.2e-8`.
   - **Eine Stelle:** eine gemeinsame Formatierfunktion im Frontend für alle Anzeigen (Min/Max der Vorschau und des Ergebnisses, Statistik, Pixelwerte, Schätzung, Auflösung usw.), keine verstreuten `toFixed`.
   - **Im Plan zu klären:**
     - Schwellen für die wissenschaftliche Form (Vorschlag: Betrag < 0.001 außer 0, und ≥ 1e6) und Anzahl gültiger Stellen dort (Vorschlag: bis zu drei, ohne nachgestellte Nullen).
     - Eingabefelder: Was angezeigt wird, ist auch der angewandte Wert (keine versteckte Genauigkeit), oder intern bleibt der volle Wert. Vorschlag: Vorgaben aus der Statistik werden gerundet übernommen; was der Nutzer tippt, gilt genau so.
     - Ausnahmen: Koordinaten, IDs, Daten, Zählungen, Dateigrößen und Werte in `recipe.json`/API bleiben unberührt (nur die Anzeige ändert sich).
   - **Aufgabe:** Stufe A, nur Frontend; Tests für die Grenzfälle (0, negative Werte, 0.001, 0.0009, 1e6, NaN).

22. **Weniger Text in der Oberfläche** (Otto, 24.10.2026).
   - **Plan:** `querschnitt/nm4-22-weniger-text.md`
   - **Grundsatz:** Die Oberfläche zeigt so wenig Text wie möglich. Erklärungen, Hinweise und Gründe stehen im Tooltip (Hover und Tastaturfokus, für Screenreader erreichbar), nicht als Absatz unter Knöpfen oder Feldern – wie bei „Share processing“ (M4-19e).
   - **Sichtbar bleiben nur:** Beschriftungen, Werte, Fehlermeldungen, die eine Handlung verlangen, und Pflichtangaben (Attribution, Lizenz, Datenschutzhinweis).
   - **Umfang:** Durchgang durch Panel, Suchergebnisse, Layer-Manager, Control-Panel; Liste der gekürzten bzw. verschobenen Texte im PR.
   - **Aufgabe:** Stufe A, nur Frontend, zusammen mit Punkt 20 oder in UI-01; gilt ab sofort als Regel für jede neue Oberfläche.

23. **Backend-Tests schneller** (Otto, 24.10.2026).
   - **Plan:** `querschnitt/nm4-23-backend-tests-schneller.md`
   - **Befund (CI-Lauf auf `main`, 24.10.2026):** Job „Backend — lint and tests“ 14,2 min, davon `pytest` 13,2 min; Installation 0,5 min, Ruff und Migration je unter 0,1 min. Frontend 0,7 min, Modulgrenzen 0,7 min, compose-topology 1,9 min.
   - **Schritt 1 – messen:** `pytest --durations=30` (lokal in der Session und einmal in der CI-Ausgabe), Tabelle der langsamsten Tests im PR. Erwartete Kandidaten: Speichertests bei 4096² (`VmHWM`), Vergleiche in `spawn`-Prozessen (Runner, Worker, Import), Tests gegen Postgres. Abhilfe ohne Verlust an Aussage: kleinere synthetische Raster, wo die Größe nicht der Prüfgegenstand ist; teure Fixtures mit Geltungsbereich `module`/`session`; doppelte Prüfungen zusammenlegen. Speicher- und Bitgleich-Tests bleiben in voller Größe.
   - **Schritt 2 – parallel (nur nach Ottos Freigabe):** `pytest-xdist` (neue Abhängigkeit). Vorher mit Quellen klären: Verträglichkeit mit `spawn`-Kindprozessen und Speichermessungen (`VmHWM` je Prozess), eigene Datenbank je xdist-Worker für Postgres-Tests, Zahl der Kerne der GitHub-Runner für öffentliche Repos. Einstellung über die pytest-Konfiguration, nicht über `.github/`.
   - **Grenze:** keine Tests streichen oder überspringen, um Zeit zu sparen; `.github/` bleibt unverändert.
   - **Aufgabe:** Stufe B (Schritt 2 ist eine Abhängigkeit und rechenrelevant), nur Tests und Testkonfiguration.
24. **Rückfall „Szene für Szene“ stapelt nach Auswahl** (Otto, 25.10.2026, aus NM4-02).
   - **Befund:** Wo die Karte keine Mosaik-Kachel nutzt (Überflug über 64 Szenen, abgelehnte Kachel), stapelt sie die Szenen in der Reihenfolge der Auswahl (`stackLikeView`, `mosaic.ts`). Zuschnitt, Export, Job und Kachel ordnen seit NM4-02 mit `mosaic_order`; in Überlappungen kann dieser Rückfall eine andere Szene oben zeigen.
   - **Aufgabe:** nach UI-01, weil dieselbe Stelle betroffen ist. Nicht in NM4-02.

## In UI-01 aufgenommen (20.–22.10.2026)

- Reihenfolge im Layer-Manager greift manchmal nicht (UI-01 §1 Punkt 10, Diagnose mit Test zuerst; Otto liefert die Schritte zum Nachstellen).
- Klick auf einen Ergebnis-Layer öffnet die Darstellung: vmin, vmax, Colormap, Vorgabe aus M4-32 (UI-01 §1 Punkt 11).
- Gleiche Breite der Layer-Zeilen mit festen Knopfpositionen (Punkt 8).
- Download eines Ergebnisses aus dem Layer-Manager (Punkt 9).
- Je fertigem Job nur „Download (ZIP)“, kein „Methods“, kein „Copy“ (Punkt 12).
- Handbereich der Farbskala je Job dauerhaft speichern (§3 Punkt 1).
- Stapelung zwischen Überflügen: Ansicht und angeheftete Layer stapeln verschieden (bekannte Grenze aus M4-17c §15), Prüffall in UI-01 §1 Punkt 10.

## Offen im Entscheidungslog (bewusst nach M4)

24. Earth Search v2: `sentinel-2-c1-l2a` wird durch `sentinel-2-l2a` ersetzt (Termin offen, Quelle im Log von M4-12a).
25. Originale als ZIP über die Plattform. Das kostet Bandbreite und gibt Daten über die Plattform weiter, und ein Abbruch lässt sich nicht fortsetzen (M4-11b-2).
26. Festes nodata je Ganzzahltyp für Quellen ohne nodata, dazu die Kollision gültiger Werte mit nodata nach dem Klemmen (M4-26).
27. Triage-Routine bei rotem Live-Smoke (projektplan §6, nicht eingerichtet; M4-27 §4).
28. Punkte aus S3 (M4-Plan Fassung 3):
    - Export-Job für Zarr blockweise,
    - schnelleres COG-Profil,
    - Laufzeitdeckel an echten Läufen kalibrieren,
    - Zähler der Verbindungen je Lauf,
    - Job-Schnittstelle in eigenem Prozess,
    - Eingaben per Referenz (siehe Punkt 5),
    - Datei-Cache des Runners.
29. CI: Umstellung von `ubuntu-latest` auf Ubuntu 26, Node-20-Warnungen der Actions, kein `cancel-in-progress`. Entschieden, `.github/` nicht zu ändern (19.10.2026). Neu entscheiden, sobald die CI ohne Codeänderung an Systempaketen scheitert.

## Danach geplant

30. VP3: UI-01 (App-Rahmen, Processing-Manager, Batch, „Download all“, Layer-Manager mit den Punkten 8–12), dann UI-02 (Basemap, Projektion). Siehe `projektplan.md` v1.5.

## Verworfen bzw. nur bei Bedarf

- Zarr im Viewer generell durch COG ersetzen (Daten umwandeln): nein. Davon getrennt steht Punkt 15 (Zarr-Datensatz als Doppel entfernen). Jeder Datensatz bleibt bei seiner Quelle. Nur falls Zarr im Viewer langsam auffällt, folgt eine Messung (Stufe C) zu GeoZarr-Multiscales und Quicklooks.
- „Replace source layer“ für Vorschau und Job-Ergebnis: von Otto entfernt (20.10.2026).
- Knopf zum Kopieren des Methodentexts: von Otto abgelehnt (22.10.2026).
- CI bei reinen Plan-Änderungen verkürzen (Filter im Job oder zweiter Workflow): von Otto verworfen (24.10.2026); `.github/` bleibt unverändert.
