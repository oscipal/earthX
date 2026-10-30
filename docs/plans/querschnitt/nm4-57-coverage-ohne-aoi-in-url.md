# NM4-57 — Keine AOI in URLs, keine Dateiadressen in Logs

**Stand:** 30.10.2026, Fund aus DS-02c (#239), von Otto beauftragt (Backlog-Punkt 57 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR (Backend und Frontend).
**Modell:** Sonnet, Effort hoch (Datenschutzregel, Cache).
**Start:** Vorrang vor neuen Funktionen. Frontend-Teil zählt als Frontend-Session (höchstens zwei gleichzeitig). Nicht gleichzeitig mit DS-03a2 und DS-03b, falls diese die Coverage-Route ändern.
**Startsatz:** „Führe Aufgabe NM4-57 aus `docs/plans/querschnitt/nm4-57-coverage-ohne-aoi-in-url.md` aus.“

## 1. Befund

`GET /coverage/{id}` trägt bei gesetzter AOI deren Umriss als `bbox` in der URL (seit M3-19). Das verstößt gegen die feste Regel „keine AOI in URLs oder Logs“ (M4 Q8; AOIs sind personenbezogen).

Zweiter Befund (DS-03a2, #240, 30.10.2026): GDAL schreibt bei einem Lesefehler die ganze Adresse der Datei ins Log. Das verstößt gegen „kein `href` und keine signierten URLs in Logs“; bei Quellen mit signierten URLs (Planetary Computer) stünde dort das Token. DS-03a2 filtert nur in Threads, die gerade eine Szene messen; `tiler` und `worker` haben keinen Schutz.

## 2. Soll

- Coverage mit AOI läuft als `POST`; die AOI (bzw. ihr Umriss) steht nur im Body. Dieselbe Prüfung wie heute (Registry-Filter aus DS-02b, Grenzen, Fehlertexte nur als Status).
- Ohne AOI (Kartenausschnitt) darf `GET` mit dem Ausschnitt bleiben; im PR begründen, dass der Kartenausschnitt keine AOI ist.
- Prüfen und belegen: Weder Zugriffslog noch eigene Logzeilen noch Cache-Schlüssel enthalten die AOI-bbox im Klartext; Cache-Einträge mit AOI leben höchstens 7 Tage.
- Weitere Stellen suchen, an denen eine AOI oder ihr Umriss in eine URL gerät (Kachel-URLs, TileJSON, Statistik, Download, Permalink); Liste im PR, gefundene Fälle im selben PR beheben oder als Frage an Otto.
- **GDAL-Meldungen:** Ein Filter für alle Meldungen von GDAL/rasterio (Fehlerhandler bzw. Log-Filter), prozessweit in `api`, `tiler` und `worker`, der Adressen (URL, `/vsicurl/`, `/vsis3/`, Query mit Token) durch einen Platzhalter ersetzt; der Filter aus DS-03a2 geht darin auf. Test je Prozess mit einem absichtlichen Lesefehler, Gegenprobe.
- Alte `GET`-Aufrufe mit AOI-bbox: Das eigene Frontend ist der einzige Client; die Route darf sie abweisen (Backlog-Punkt 49 bleibt für M6).

## 3. Grenzen

- Keine neue Abhängigkeit ohne Frage an Otto.
- Nachträge in ADRs heißen nach der Aufgabe („Nachtrag NM4-57“), betroffen sind vermutlich `adr/0004` und `adr/0021`.
- Bilder der Browserprüfung nicht ins Repo, nur im PR beschreiben.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 4. Abnahme

- Tests: Coverage mit AOI per `POST`, keine Koordinate der AOI in URL, Log und Cache-Schlüssel (Gegenprobe gegen den alten Code); Coverage ohne AOI unverändert.
- Browserprüfung: In den Entwicklerwerkzeugen (Network) keine URL mit AOI-Koordinaten bei Suche, Coverage, Vorschau, Ansicht; Prüfanleitung für Otto im PR (Schritt für Schritt, mit Filter `coverage` im Reiter Network).
- Alle vier Pflicht-Checks grün.
- Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.
