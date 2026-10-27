# NM4-43 — Ausgabe-Bänder statt Bandauswahl; Band-Math-Ergebnisse als eigene Bänder; keine Bandgrenze

**Stand:** 27.10.2026, beauftragt von Otto (Backlog-Punkt 43 in `docs/plans/nach-m4-backlog.md`). Nimmt NM4-10 (Schritt-Namen und Chips) in sich auf.
**Stufe C:** nur Entscheidungsvorlage als ADR-Entwurf `docs/adr/0020-ausgabe-baender.md`, kein Produktivcode. Die Umsetzung bekommt nach Ottos Entscheidung eigene Aufgaben.
**Modell:** Opus, Effort hoch.
**Start:** sofort möglich (nur Doku, Messung, Recherche).
**Startsatz:** „Führe Aufgabe NM4-43 aus `docs/plans/querschnitt/nm4-43-ausgabe-baender.md` aus.“

## 1. Wunsch (Otto, 27.10.2026, wörtlich)

> ich will keine obergrenze für anzahl der bänder. Außerdem will ich dass ich ein band math ergebnis, als eigenes band hinzufügen kann. (die auswahl oben soll dann zur gänze verschwinden und nur noch zur info vorhanden sein. Die auswahl soll dann am ende stehen (alle bänder und zusätzlich neu gerechnete, welche ich anclicken kann um sie zum output hinzuzufügen).

Hintergrund (NM4-07, #216): Heute bestimmt die Bandauswahl oben im Panel die Eingabe. Ohne `band_math` ist sie die Ausgabe; mit `band_math` ist die Ausgabe nur das eine Ergebnisband, zusätzlich gewählte Bänder kosten Laufzeit und zählen gegen die Grenze von 16 Assets (M4-07b F5, Startwert vom 07.10.2026, nie gemessen).

## 2. Soll (Otto)

1. **Keine Obergrenze für die Zahl der Bänder** je Auftrag.
2. **Band-Math-Ergebnisse sind eigene Bänder.** Ein `band_math`-Schritt fügt ein neues Band hinzu, statt die Bänder zu ersetzen. Mehrere Schritte ergeben mehrere neue Bänder.
3. **Oben keine Auswahl mehr.** Die Bänder des Datensatzes stehen oben nur zur Information (und als Namenshilfe: Klick fügt den Namen in einen Ausdruck ein).
4. **Ausgabe am Ende.** Am Ende des Panels stehen alle Bänder des Datensatzes und alle neu gerechneten; ein Klick nimmt ein Band in die Ausgabe auf oder heraus.
5. **Vorgabe der Ausgabe** (Otto, 27.10.2026): Standardmäßig ist nur das Band-Math-Ergebnis (bzw. sind nur die Band-Math-Ergebnisse) in der Ausgabe. Andere Bänder kommen nur hinzu, wenn der Benutzer sie anklickt.
6. **Mehrere Band-Math-Schritte** (Otto, 27.10.2026): Es können mehrere `band_math`-Schritte hintereinander laufen, jeder mit anderen Bändern (etwa NDVI aus B04/B08 und NDWI aus B03/B08). Jeder Schritt sieht die Bänder des Datensatzes und die vorher neu gerechneten.

Zusatz Otto (27.10.2026, wörtlich): „ich will auch das standardmäßig ausgewählt ist band math result (also beim rechnen vom result und nur wenn der benutzer will werden andere bänder hinzugefügt). und: es können somit auch mehrere band math schritte hintereinander mit unterschiedlichen bändern durchgeführt werden.“

## 3. Im ADR klären (je Optionen, Empfehlung, bei Rechenrelevanz Quellen und Messung)

1. **Rezeptmodell:** Heute ist die Kette linear (ein Schritt sieht nur das Ergebnis des vorigen). Neu: ein Vorrat an Bändern, in den `band_math` Bänder hinzufügt. Worauf wirken `reproject`, `mask`, `normalize` (auf alle Bänder des Vorrats, auf gewählte, auf die Ausgabe)? Spielt die Reihenfolge der Schritte noch eine Rolle?
2. **Ausgabe im Rezept:** z. B. eine Liste `outputs`. Die Eingabe ergibt sich daraus: Ausgabe-Bänder plus alle Bänder, die Ausdrücke und Maske brauchen. Nur diese werden gelesen.
3. **Namen neu gerechneter Bänder** (aus NM4-10): Vorgabe `Band_Math_1` usw., eigener Name je Schritt (etwa `ndvi`), erlaubte Zeichen, keine Doppel, keine Kollision mit Bandnamen des Datensatzes, Umbenennen bei späterer Nutzung.
4. **Schutz ohne Bandgrenze:** Die Grenze 16 entfällt (Otto). Was schützt dann Worker, Speicher und Quellen? Messung (Laufzeit, Spitzenspeicher, gelesene Bytes) für Sentinel-2 L2A mit 2, 16 und allen Bändern, bei 1 und 25 Szenen, mit und ohne `band_math`. Recherche, wie andere Plattformen das begrenzen (etwa openEO-Backends, Sentinel Hub, Google Earth Engine), mit Quellen. Empfehlung, ob die bestehenden Grenzen (25 Items, Exportgröße, Deckel gleichzeitiger Jobs, Kostenschätzung) genügen oder eine Grenze nach Datenmenge (Pixel × Bänder × Szenen) statt nach Bandzahl nötig ist.
5. **Ausgabedatei:** Neu gerechnete Bänder sind meist `float32`, Quellbänder etwa `uint16`. Eine Datei mit gemeinsamem Typ, eine Datei je Typ oder je Band? Banddeskriptionen, Einheiten (M4-19b), nodata, Größe.
6. **Vorgabe der Ausgabe ohne `band_math`:** Mit `band_math` ist sie entschieden (§2 Punkt 5). Was ist angehakt, wenn das Rezept kein `band_math` hat (nur `reproject`, `mask`, `normalize` oder gar kein Schritt): keines oder alle? Ein leerer Auftrag wird nicht gestartet.
7. **Vorschau und Kacheln:** Welches Band zeigt die Vorschau bei mehreren Ausgaben? Auswahl im Layer-Manager je Band, RGB aus drei Ausgaben? Zusammenhang mit M4-18b und NM4-04 (Mosaik mit Operator, #215).
8. **Hash, Version, Runner, alte Rezepte:** Änderung an `resolved`, `earthx.__version__`, `adr/0014`, `adr/0016`. Werden gespeicherte Rezepte und Permalinks im alten Format weiter angenommen (umgedeutet) oder mit Grund abgewiesen?
9. **Folgen für andere Aufgaben:** NM4-10 geht hierin auf. NM4-11 (Normalize), NM4-14 (Index-Knöpfe: ein Knopf fügt ein neues Band hinzu?), NM4-20 (Panel-Gliederung), NM4-05b (Ergebnis als Eingabe mit mehreren Bändern), DS-06 (Maske nach Werten), `auxiliary_assets` aus NM4-07. Der ADR sagt je Aufgabe, was sich ändert.
10. **Schnitt der Umsetzung:** Vorschlag für Aufgaben (etwa Backend/Rezept, dann Frontend) mit Reihenfolge.

## 4. Grenzen

- Stufe C: nur ADR-Entwurf, Messskripte unter `scripts/` (im PR begründet), keine Änderung an Produktivcode.
- Oberflächentexte im ADR (Knopfnamen, Tooltips) nur Englisch; wenig Text, Erklärungen im Tooltip; nicht Mögliches ausblenden statt ausgrauen.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- `docs/adr/0020-ausgabe-baender.md` als Entwurf mit Fragen F1 … Fn an Otto, je Optionen und Empfehlung.
- Messung reproduzierbar (Skripte und Aufrufe im ADR), Recherche mit Quellen.
- Skizze des Panels (Text oder Bild) für die empfohlene Variante.
- Log-Zeile mit PR-Nummer, Status „offen“. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.
