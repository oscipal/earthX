# NM4-64 — „RGB“ (Echtfarben) als Eintrag in Vorschau und Ergebnis-Layer

**Stand:** 31.10.2026, Wunsch von Otto (Backlog-Punkt 64 in `docs/plans/nach-m4-backlog.md`); aus NM4-43e PR 2 (#255) herausgelöst, weil Registry und Kachel-Routen sich ändern.
**Stufe A:** direkt umsetzen, ein Draft-PR (Backend und Frontend in einer Session, eigene Commits).
**Modell:** Sonnet, Effort hoch.
**Start:** nach dem Merge von NM4-43e PR 2 (#255). Das Backend kann sofort beginnen; das Frontend zählt als Frontend-Session (höchstens zwei gleichzeitig) – erst beginnen, wenn Otto einen freien Platz meldet. Vor NM4-54 (dort nutzt NM4-45 dasselbe Registry-Feld für die Ansicht).
**Startsatz:** „Führe Aufgabe NM4-64 aus `docs/plans/querschnitt/nm4-64-rgb.md` aus.“

## 1. Wunsch (Otto, 31.10.2026)

> für sentinel 2 soll RGB das standardband sein und auch als solches erscheinen, colormap soll nicht möglich sein zur auswahl bei RGB

Entschieden (Otto, Option 2): In der Ansicht ist „RGB“ immer die Vorgabe (kommt mit NM4-45 im Paket NM4-54). In Vorschau („Show“) und Ergebnis-Layer („Band“) ist „RGB“ die Vorgabe nur **ohne** Band-Math-Ergebnis in der Ausgabe; mit Band-Math bleibt das zuletzt angelegte Ergebnis die Vorgabe.

## 2. Soll

1. **Registry:** neues Feld je Datensatz `earthx:true_color` mit den drei Bandnamen (Sentinel-2: `red`, `green`, `blue`; DEM: leer). Pflichtfeld ohne Vorgabe (B10), Prüfung beim Start, dass die Namen Bänder des Datensatzes sind.
2. **Kacheln:** Item- und Mosaik-Kachel, TileJSON und Statistik nehmen bis zu drei `band=` (in der Reihenfolge R, G, B), zeichnen ein Bild mit drei Bändern und **einer** gemeinsamen Skala (`rescale` für alle drei); keine Colormap bei drei Bändern (`400`, falls doch angefragt). Ergebnis-Kachel: mehrere `bidx` gibt es schon.
3. **Dropdowns** (`BandSelect.tsx` aus NM4-43e PR 2): Eintrag „RGB“ ganz oben, nur wenn der Datensatz `earthx:true_color` hat und alle drei Bänder in der Ausgabe bzw. in `result.tif` sind (sonst nicht angezeigt). Vorgabe nach §1.
4. **Bei „RGB“:** keine Colormap (nicht angezeigt), vmin/vmax und „auto-scale“ für alle drei Bänder gemeinsam, „Save“ speichert den RGB-Bereich wie bei einem Band.
5. **Bitgleichheit** Kachel ↔ Job bleibt; Tests auch für drei Bänder.

## 3. Grenzen

- Ausgehende Anfragen nur über `gateway`. Keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Keine neue Abhängigkeit ohne Frage an Otto.
- Nachträge heißen nach der Aufgabe („Nachtrag NM4-64“).
- Bilder nicht ins Repo.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 4. Abnahme

- Tests: Registry-Feld, drei `band=` an allen Routen, keine Colormap bei RGB, Dropdown-Eintrag nur wenn möglich, Vorgabe-Regel, gemeinsame Skala, Gegenprobe.
- Prüfung im echten Browser (Playwright), Hell/Dunkel, schmales Fenster; Prüfanleitung für Otto (Browser und PowerShell).
- Alle vier Pflicht-Checks grün.
- Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern.
- Vor „fertig“ ist main geholt.
