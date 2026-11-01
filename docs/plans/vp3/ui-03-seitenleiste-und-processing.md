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
