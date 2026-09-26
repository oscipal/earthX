# M3 — Erste Nicht-STAC-Quelle und Interface-Reflexion: Aufgabenschnitt

**Status:** Fassung 2 vom 26.09.2026. Erledigt und gemergt: M3-00 bis M3-05,
M3-08, M3-09, M3-16, M3-18, M3-19, M3-22 sowie der Hotfix zum MinIO-Image. In
Arbeit: M3-06a und M3-17 (PR #88, im Review), M3-11a (PR #95, im Review).
Fassung 2 schneidet M3-11 nach der
Annahme von `adr/0009` in
M3-11a, M3-11b und M3-11c, nimmt die Entscheidungen vom 23. und 24.09.2026 als
P20 bis P23 auf, hält den Schnitt als P24 fest, ergänzt den Spike M3-20 (Ersatz für MinIO), den Doku-Abgleich M3-21 und
die Fehlersuche M3-22 (gelegentlich unlesbare Download-Dateien) und ordnet die
Wellen neu. Wo eine erledigte Aufgabe anders umgesetzt wurde als hier
beschrieben, gilt das Log; der Aufgabentext bleibt als Geschichte stehen.
Frühere Fassungen: 1.1 (Antworten auf M3-02, M3-16), 1.2 (P19, M3-17),
1.3 (`adr/0010`, M3-19), 1.4 (M3-18).
**Ort im Repo:** `docs/plans/m3-dritte-quelle-und-interface.md`
**Grundlagen:** `projektplan.md` 4 (M3); `architekturplan.md` 3.1, 3.2, 5.1,
5.2, 6.1, 6.5, 12.3, 15.1, 15.2; `adr/0001` (Zustand), `adr/0002` (Tests),
`adr/0003` (Datensätze), `adr/0004` (Coverage), `adr/0005` (föderierte Suche),
`adr/0006` (Kachel-Pfad), `adr/0007` (Zarr), `adr/0008` (Prototyp entfernt),
`adr/0009` (dritte Quelle), `adr/0010` (Zählwürfel);
`plans/m2-format-und-viewer.md` (D1–D31, „Nach M2 vorgemerkt“);
`plans/m2-12-abnahme.md`; `prototyp-inventar.md`; `projektuebersicht.md` §5
(Onboarding-Checkliste); `KLAERUNGEN.md` B8–B13; `plans/m3-02-konformitaetsbericht.md`;
`ENTSCHEIDUNGSLOG.md`, Zeilen ab dem 23.09.2026.

Eine Sitzung startet eine Aufgabe mit: „Führe Aufgabe M3-xx aus
`docs/plans/m3-dritte-quelle-und-interface.md` aus.“ Jede Aufgabe ist ohne das
Planungsgespräch verständlich und endet mit genau einem Draft-PR. Aufgaben mit
Buchstaben (M3-06a, M3-06b …) sind je eine eigene Session und ein eigener PR.

---

## 0. Ziel in einem Satz

Eine strukturell andere Quelle ohne Such-API läuft mit materialisierten Items
neben den beiden STAC-Quellen im selben Viewer, ohne Änderung an `readers` und
ohne datensatzspezifische Sonderfälle im Frontend; aus den drei realen Quellen
entsteht danach das Adapter-Interface als ADR.

---

## 1. Vor dem Start

### 1.1 Bereits entschieden (Otto, ab 23.09.2026, Log)

| # | Entscheidung | wirkt auf |
|---|---|---|
| P1 | **Nicht-STAC-Quelle per Spike.** Kandidaten: Hansen GFC, Copernicus DEM direkt aus dem Bucket, ein Zenodo-Record, ARCO-ERA5. Kriterien: keine Such-API, token-frei, Lizenz nach B11 einstufbar, `readers` unverändert, Art der Coverage. Otto wählt nach dem ADR | M3-01, M3-11 |
| P2 | **Copernicus DEM:** Der Spike klärt, ob der Bucket als Nicht-STAC-Quelle zählt. Wenn ja, kann DEM beide Rollen tragen; wenn nein, wird DEM vierter Datensatz | M3-01 |
| P3 | **Allowlist:** Hosts stehen in §1.3; Otto trägt sie vor dem Start der jeweiligen Session ein | M3-01, M3-07a |
| P4 | **Materialisierung** (pgstac oder stac-geoparquet; Loader in `catalog` oder Prozess `harvester`) schlägt der Spike mit Quellen vor; Otto entscheidet | M3-01, M3-11 |
| P5 | **Quellenbreite statt ESA-only** | alle |
| P6 | **Suche:** gemischte Suche (D8, `adr/0005` Regel I), erneute Prüfung von CQL2 (`adr/0005` Regel VI), Durchreichen von `intersects` und `ids` (D31) | M3-08, M3-13 |
| P7 | **AOI-Upload über das Backend** mit einheitlicher Prüfung, zusätzlich Shapefile | M3-06 |
| P8 | **Ortssuche:** Nominatim über `api` und `gateway`, mit Cache, höchstens 1 Anfrage pro Sekunde, ohne Autocomplete; vorher Recherche zu Bedingungen und Alternativen | M3-07 |
| P9 | **Datensatz-Katalog in der Suchkachel:** einfacher Filter über `/stac/collections`; Hybrid-Suche bleibt M5 | M3-10 |
| P10 | **Datensatzspezifische Sonderfälle im Frontend** werden Registry-Felder, soweit der dritte Datensatz sie trifft | M3-12 |
| P11 | **Mosaik im Kachel-Pfad bleibt M4** | M3-00, M3-09 |
| P12 | **Zuschnitt auf der Karte:** Die Trefferliste zeigt die Quicklooks ganz. In der vollen Auflösung zeigt die Karte von den gewählten Szenen nur den Teil innerhalb der AOI; außerhalb ist das Bild ausgeblendet, die Basiskarte bleibt. Ein Knopf wie bisher (mit AOI zugeschnitten, ohne AOI ganze Szene); Beschriftung im Plan-Schritt. Download unverändert. Weg im Plan-Schritt. **Umgesetzt mit zwei Knöpfen** („Crop & merge to AOI“, „View full selection“; Log 24.09.2026); der Download folgt der Ansicht erst mit M3-17 | M3-09 |
| P13 | **Heatmap-Zählwürfel:** in M3 nur ein Mess-Spike; gebaut wird später | M3-05 |
| P14 | **Health-Status kommt mit M5** | M3-00 |
| P15 | **Interface-Reflexion** nach dem Merge der dritten Quelle, Stufe C, Opus mit Effort hoch | M3-14 |
| P16 | **Kleinaufgaben:** tilejson-Fix als Stufe A; Python 3.12 als frühe Stufe-B-Aufgabe | M3-03, M3-04 |
| P17 | **M3-00 Doku** bereinigt die Widersprüche aus der M3-Vorbereitung | M3-00 |
| P18 | **Konformitätsbericht** einmal zu Beginn von M3, keine Routine | M3-02 |
| P19 | **Download folgt der Ansicht:** heruntergeladen wird, was die Karte zeigt. Zuschnitt sichtbar: je Gruppe (Überflug, Gruppierungsschlüssel der Trefferliste, ab M3-12 aus der Registry) eine gemergte Datei, verschiedene Gruppen als getrennte Dateien im selben ZIP, Deckel 4096 px und 200 MB bleiben. Ganze Szene sichtbar, eine Szene gewählt (COG): Download der Originaldatei direkt von der Quelle durch den Browser, ohne Umweg über die Plattform. Zarr (EOPF): Download immer als Zuschnitt, nie der ganze Speicher; ohne AOI ist der Download-Knopf deaktiviert, Hinweis „Draw an AOI to download“. Mehrere ganze Szenen gewählt: in M3 die Originale einzeln; ein gemergtes Mosaik ganzer Szenen je Überflug ist ein Processing-Job und für M4 vorgemerkt (Vorschlag). **Der Deckel „4096 px und 200 MB“ ist durch P20 ersetzt** | M3-17 |
| P20 | **Download in nativer Auflösung** (24.09.2026): nie automatisch verkleinert; gröber nur, wenn der Nutzer im Dialog ausdrücklich einen Faktor wählt (Native, 2×, 4×, 10×). Deckel 500 MB roh für die Ausgabe, höchstens ein Download ab 100 MB gleichzeitig je `tiler`-Prozess (sonst `503` mit `Retry-After`); über dem Deckel eine Abweisung mit Faktorvorschlag, nie eine stille Verkleinerung. Exporte darüber in voller Auflösung werden in M4 ein Job, kein Teil-Download in M3 | M3-18 (erledigt), M4 |
| P21 | **Maske statt nodata** (24.09.2026): Die Datendatei behält jedes Pixel der Quelle; je Gruppe und Asset kommt eine Maske (1 innerhalb, 0 außerhalb des AOI-Polygons) mit. Ausdehnung von Datei und Maske ist die Bounding Box von (AOI ∩ Vereinigung der Footprints der Gruppe). Einmal je ZIP die Original-AOI als GeoJSON, unbeschnitten | M3-18 (erledigt), M3-17 |
| P22 | **Weltüberblick ohne AOI** (23./24.09.2026): Anfrage auf den sichtbaren Ausschnitt, Zellstufe folgt dem Kartenzoom (Ziel rund 2 000 Zellen je Bildschirm); ersetzt `adr/0010` Antwort 6a | M3-19 (erledigt) |
| P23 | **MinIO** (24.09.2026): Die offiziellen Images sind seit dem 24.09.2026 nicht mehr öffentlich ziehbar. Übergang mit `bitnamilegacy/minio` per Digest, nur CI und lokal. Die Neubewertung wird vorgezogen: Spike zu einem Ersatz vor M4 | M3-20 |
| P24 | **Schnitt von M3-11** (26.09.2026, dieser Plan): drei Teile. M3-11a trennt in Registry und Dispatch „welcher Adapter“ von „föderiert oder materialisiert“ und baut den zweiten Weg für Items aus pgstac; M3-11b bringt den DEM-Adapter, den Einmal-Befehl in `discovery` und den Registry-Eintrag; M3-11c baut die Coverage über eigene Items. Die Zugriffsauflösung bleibt bis M4 in `api/tiler.py` (Log 23.09.2026, K-04) | M3-11a–c |

### 1.2 Was in allen Aufgaben gilt

`CLAUDE.md` gilt vollständig: ein Branch, ein Draft-PR, Tests für Fehlerfälle
und zweckfremde Nutzung, Fixtures nur synthetisch, keine exakten AOIs in Logs,
alles Ausgehende über `gateway`, Worker-Kern zustandslos, `decomp.py` bleibt
unberührt. Dazu aus M2: Oberflächentexte nur Englisch, keine Sprachwahl (D25,
D28). Neue Registry-Felder ohne Vorgabewert (B10). Was hier nicht entschieden
ist, schlägt die Session im Plan-Schritt mit nummerierten Optionen und
Empfehlung vor und hält an. Vor dem Fertigmelden `main` in den Branch holen;
eigene Log-Zeilen ans Ende von `ENTSCHEIDUNGSLOG.md`, alle anderen erhalten.
Messungen an echten Quellen werden gedrosselt (höchstens 1 Anfrage pro
Sekunde); die Zahl der Anfragen steht im Ergebnis.

**Stufe B heißt hier:** Der Plan liegt als `docs/plans/m3-xx-<kurzname>.md` im
Draft-PR, die Session hält an, Otto gibt frei, dann wird in derselben Session
umgesetzt.

### 1.3 Von Otto auszuführen

- **Vor M3-07a:** `nominatim.openstreetmap.org` in der Allowlist der
  Cloud-Umgebung freigeben (heute gesperrt, `cloud-umgebung.md` §6). Nur für
  Messungen per `curl`; Tests laufen gegen synthetische Fixtures.
- **Vor M3-11b:** nichts Neues. `copernicus-dem-30m.s3.amazonaws.com` ist aus
  der Cloud-Umgebung erreichbar (`adr/0009` §10.2).
- **Vor M3-20:** nichts vorab. Braucht die Session für eine Messung einen
  gesperrten Host (etwa für ein Release-Archiv), nennt sie ihn und hält an.
- **Nach den Plan-Schritten** von M3-11a und M3-11b: neue Registry-Felder und
  die Zeitangabe der DEM-Items freigeben (B10, `adr/0009` §10.1).

---

## 2. Abgrenzung

**In M3:** eine Nicht-STAC-Quelle mit materialisierten Items; Onboarding
dieser Quelle nach der Checkliste; gemischte Suche und CQL2-Prüfung;
`intersects` und `ids`; AOI-Upload über das Backend samt Shapefile; Ortssuche
mit Umriss und Bounding Box; Zuschnitt in der Vollauflösungs-Ansicht;
Datensatz-Filter in der Suchkachel; Frontend-Sonderfälle in die Registry;
tilejson-Fix; Python 3.12; Konformitätsbericht; Mess-Spike Zählwürfel;
Interface-ADR; Download folgt der Ansicht; Spike zum Ersatz für MinIO.

**Nicht in M3:** Mosaik im Kachel-Pfad (M4, P11); Rezept, Operatoren, Jobs,
Objektspeicher (M4); Bau des Heatmap-Zählwürfels (P13); Health-Status und
Prüfdatum (M5, P14, D29); Hybrid-Suche (M5); Uvicorn-Worker des `tiler` (M5);
COG-Header-Cache (Log offen); Umbau auf einen MinIO-Ersatz (M4, nach M3-20);
Exporte über dem synchronen Deckel in voller Auflösung (M4, Job, P20);
Zenodo als Metadatenquelle (M5, `adr/0009`); Zählwürfel (kein Bau auf
Vorrat, in M5 je Datensatz nur bei gemessenem Bedarf, Log 26.09.2026); Zugriffsauflösung außerhalb von `api/tiler.py` (M4, K-04); Ratenbegrenzung pro
IP oder Nutzer (D6); Bug-Report Stufe 2 (D9); helle Basiskarte (D10);
Viewer-Pakete Swipe/Export; alles zum ersten öffentlichen Deployment (AGPL
§13, Nutzungsbedingungen); gemergtes Mosaik ganzer Szenen (M4, Job).

---

## 3. Übersicht und Reihenfolge

| ID | Aufgabe | Stufe | Modell (Effort) | hängt ab von | Stand |
|---|---|---|---|---|---|
| M3-00 | Doku nachziehen | A | Sonnet (mittel) | — | erledigt (#74) |
| M3-01 | Spike dritte Quelle → `adr/0009` | C | Opus (hoch) | Allowlist | erledigt (#79) |
| M3-02 | Architektur-Konformitätsbericht | C | Opus (hoch) | — | erledigt (#77) |
| M3-03 | Wechsel auf Python 3.12 | B | Opus Plan, Sonnet (hoch) | — | erledigt (#75) |
| M3-04 | `/tilejson.json` mit freigegebenen Zoomstufen | A | Sonnet (mittel) | — | erledigt (#78) |
| M3-05 | Mess-Spike Heatmap-Zählwürfel → `adr/0010` | C | Opus (hoch) | — | erledigt (#80) |
| M3-06a | AOI-Upload: Backend-Route mit Shapefile | B | Opus Plan, Sonnet (hoch) | M3-03 | in Arbeit |
| M3-06b | AOI-Upload: Frontend auf die Route | B | Opus Plan, Sonnet (mittel) | M3-06a | offen |
| M3-07a | Ortssuche: Recherche und Backend-Route | B | Opus Plan, Sonnet (hoch) | Allowlist §1.3 | offen |
| M3-07b | Ortssuche: Frontend | B | Opus Plan, Sonnet (mittel) | M3-07a, M3-06b | offen |
| M3-08 | `intersects` und `ids` durchreichen | B | Opus Plan, Sonnet (hoch) | M3-16 | erledigt (#76) |
| M3-09 | Vollauflösung zeigt nur den Zuschnitt | B | Opus Plan, Sonnet (hoch) | — | erledigt (#84) |
| M3-10 | Datensatz-Filter in der Suchkachel | B | Opus Plan, Sonnet (mittel) | M3-07b | offen |
| M3-11a | Materialisierte Quellen in Registry, Dispatch und Item-Abruf | B | Opus Plan, Sonnet (hoch) | — | in Arbeit |
| M3-11b | DEM-Adapter, Einmal-Befehl in `discovery`, Registry-Eintrag | B | Opus Plan, Sonnet (hoch) | M3-11a | offen |
| M3-11c | Coverage über eigene Items (`local-sql`) | B | Opus Plan, Sonnet (hoch) | M3-11a | offen |
| M3-12 | Frontend-Sonderfälle in die Registry | B | Opus Plan, Sonnet (hoch) | M3-11b, M3-10 | offen |
| M3-13 | Gemischte Suche und CQL2 | B | Opus Plan (hoch), Sonnet (hoch) | M3-11b | offen |
| M3-14 | Interface-Reflexion → `adr/0011` | C | Opus (hoch) | M3-11c, M3-13 | offen |
| M3-15 | M3-Abnahme und README | A | Sonnet (mittel) | alle | offen |
| M3-16 | Keine AOI im Log | A | Sonnet (hoch) | — | erledigt (#85) |
| M3-17 | Download folgt der Ansicht | B | Opus Plan, Sonnet (hoch) | M3-09 | in Arbeit |
| M3-18 | Download-Deckel nach Ausgabegröße und Maske auf die AOI | B | Opus Plan, Sonnet (hoch) | — | erledigt (#86) |
| M3-19 | Weltüberblick ohne AOI | A→B | Opus Plan, Sonnet (mittel) | — | erledigt (#83) |
| M3-20 | Spike Ersatz für MinIO → `adr/0012` | C | Opus (hoch) | — | offen |
| M3-21 | Doku-Abgleich nach Fassung 2 | A | Sonnet (mittel) | — | offen |
| M3-22 | Gelegentlich unlesbare Download-Dateien | B | Opus Plan (hoch), Sonnet (hoch) | — | offen |

**Wellen ab Fassung 2.** Höchstens zwei Stufe-B-Sessions gleichzeitig; Stufe A
und C laufen daneben.

1. **Jetzt:** M3-06a und M3-17 (laufen, M3-17 im Review); daneben M3-20 (C)
   und M3-21 (A).
2. **Nächster freier B-Platz:** M3-22, weil fehlerhafte Download-Dateien bei
   Nutzern ankommen können. Danach M3-11a, dann M3-11b und M3-11c parallel
   (beide hängen nur an M3-11a). Die dritte Quelle hat Vorrang vor den
   Oberflächen-Aufgaben, weil M3-12, M3-13 und M3-14 an ihr hängen.
3. **Dazwischen, sobald ein Platz frei ist:** M3-07a, M3-06b, dann M3-07b und
   M3-10.
4. **Danach:** M3-12 und M3-13, dann M3-14, zuletzt M3-15.

**Dateikonflikte im Frontend:** M3-06b, M3-07b, M3-10 und M3-12 berühren die
Suchkachel (`ControlPanel.tsx` und Umgebung); deshalb nacheinander in dieser
Reihenfolge. M3-17 berührt Layer-Manager und Download-Dialog und kann parallel
laufen; M3-11a bis M3-11c sind reines Backend.

**Feste ADR-Nummern**, damit parallele Sessions nicht kollidieren:
`adr/0009-dritte-quelle.md` (M3-01), `adr/0010-coverage-zaehlwuerfel.md`
(M3-05), `adr/0011-adapter-interface.md` (M3-14), `adr/0012-objektspeicher.md`
(M3-20).

---

## 4. Die Aufgaben

### M3-00 — Doku nachziehen

**Stand:** erledigt und gemergt (#74). Abweichungen vom Text stehen im Log.

**Ziel:** Die Plandokumente widersprechen einander und dem Log nicht mehr.
**Stufe A.** Nur `docs/`; kein Code.
**Umfang:**
- `projektplan.md`: Stand und Version; M2 als abgenommen; M3-Tabelle nach
  P1–P18 (Health-Status raus, nach M5; „Lizenzfeld mit SPDX und Flags“ besteht
  seit M1-04 und wird zu „Lizenz des neuen Datensatzes erfassen“; Funktionen
  um Upload über das Backend, `intersects`/`ids`, gemischte Suche,
  Zuschnitt-Ansicht und Datensatz-Filter ergänzen; Modell der
  Interface-Reflexion Opus, Fable nur interaktiv); §5 entsprechend; §10:
  Code-Lizenz, erster Datensatz, TiTiler und Quellenbreite als entschieden
  markieren, mit Verweis aufs Log; §6: Konformitätsbericht einmalig in M3
  statt monatlicher Routine (P18).
- **Namenskollision Viewer-Strang:** Die Pakete V1 und V2 im Projektplan heißen
  künftig **VP1** und **VP2**; ein Satz stellt klar, dass „V-n“ in den Plänen
  einzelne Aufgaben des Viewer-Strangs sind.
- `adr/0006` §6: Nachtrag zum Satz „Mosaik-Kacheln wandern nach M3, zusammen
  mit dem CDN“ — entschieden ist M4 (D11, P11). Den Originaltext stehen lassen.
- `plans/m2-format-und-viewer.md`: Status „abgenommen“; unter „Nach M2
  vorgemerkt“ ein Verweis auf diesen Plan.
- `ENTSCHEIDUNGSLOG.md`, nur Status-Spalte bestehender Zeilen ändern, Text
  stehen lassen:
  - Docker-Allowlist (`production.cloudfront.docker.com` …) → „entschieden am
    2026-09-23: vorerst nein“.
  - Schwachstelle `Settings.host_allowed` → „gegenstandslos: `backend/app/`
    entfernt (`adr/0008`); `gateway` normalisiert Hosts seit M1-03“.
  - `plans/m2-format-und-viewer.md` nachziehen, drei Stellen → „erledigt mit
    Fassung 5 des M2-Plans“.
  - Die zweite der beiden gleichlautenden Zeilen „Trefferliste gruppiert nach
    Überflug“ → „Dublette der Zeile mit demselben Inhalt“.
  - Neue Zeile am Ende: „M2 abgenommen“, mit Datum und Nummer des gemergten
    M2-12-PR aus `git log`.

**Nicht anfassen:** Code, `.github/`, `.claude/`, `CLAUDE.md`, andere ADRs als
`adr/0006`.
**Abnahme:** Jeder Widerspruch aus der Liste ist im Diff nachvollziehbar
aufgelöst; keine bestehende Log-Zeile gelöscht oder im Text geändert.

### M3-01 — Spike dritte Quelle → `adr/0009`

**Stand:** erledigt und gemergt (#79). Abweichungen vom Text stehen im Log.

**Ziel:** Otto kann die Nicht-STAC-Quelle, die Art der Materialisierung und die
Rolle von Copernicus DEM auf Grundlage von Messungen entscheiden.
**Stufe C.** Nur `docs/`; kein Produktivcode, keine Daten ins Repo.
**Voraussetzung:** Allowlist aus §1.3 ist eingetragen und die Session neu
gestartet.
**Umfang:**
- Kandidaten: Hansen GFC (`storage.googleapis.com`), Copernicus DEM GLO-30
  direkt aus dem Bucket (`copernicus-dem-30m.s3.amazonaws.com`), ein
  geeigneter Zenodo-Record (Auswahl begründen), ARCO-ERA5. Weitere Kandidaten
  nur mit Begründung.
- Je Kandidat gemessen, nicht angenommen: anonymer Zugriff (HTTP-Status),
  Range-Reads (`206`), ob die Dateien echte COGs sind (Kachelung, Overviews,
  IFD vorn) bzw. welcher vorhandene Reader sie liest, CORS-Header, Größe und
  Aufbau des Bestands (Anzahl Dateien, Kachelschema, Zeitachse), ob es einen
  statischen STAC-Katalog oder eine andere maschinenlesbare Liste gibt,
  Ratengrenzen soweit ohne Last messbar.
- **Zu P2:** Führt der DEM-Bucket selbst einen STAC-Katalog oder eine
  Such-API? Zählt er damit als Nicht-STAC-Quelle im Sinne von
  `architekturplan.md` 5.2 („Tile-adressierte Quellen“)?
- Lizenz je Kandidat am Primärdokument, mit Vorschlag der B11-Stufe. Die
  Einstufung selbst entscheidet Otto.
- Welcher Coverage-Weg passt (`adr/0004`: eigenes SQL über materialisierte
  Items oder, bei Einmal-Produkten, die Ausdehnung laut ENTSCHEIDUNGEN §2)?
- **Materialisierung (P4)** mit Stand der Technik und Quellen: Items in pgstac
  oder stac-geoparquet; ausgeführt als Loader in `catalog` (wie
  `python -m earthx.catalog.load`) oder im Prozess `harvester`; wie Items
  aktualisiert werden, wenn die Quelle nachliefert; Folgen für B13 (Registry
  bleibt bis M5 Python).
- Was sich an den Adapter-Nahtstellen (`architekturplan.md` 6.1) zeigt, knapp
  als Beobachtung für M3-14 festhalten, noch ohne Interface-Vorschlag.
- Messungen per `curl` oder kleinem Skript außerhalb des Repos; `gateway`
  erreicht die Quellen aus einer Session nicht (M2-13). Last auf die Quellen
  gering halten.

**Nicht anfassen:** Code, Registry, Allowlist der Plattform.
**Abnahme:** `adr/0009-dritte-quelle.md` mit Kriterienmatrix, Belegen je
Aussage (gemessen, Primärdokument oder Suchtreffer, wie in `adr/0003`),
Empfehlung und nummerierten Fragen an Otto; unbelegte Aussagen sind als
„unbelegt“ markiert.

### M3-02 — Architektur-Konformitätsbericht

**Stand:** erledigt und gemergt (#77). Abweichungen vom Text stehen im Log.

**Ziel:** Vor dem Ausbau ist bekannt, wo der Code vom Architekturplan und den
Regeln abweicht.
**Stufe C.** Nur lesen und berichten.
**Umfang:** Code in `backend/earthx/` und `frontend/src/` gegen
`architekturplan.md` 3.1, 3.2, 5.1, 6, 13, `KLAERUNGEN.md` B8–B13 und
`CLAUDE.md` prüfen: Verantwortlichkeiten am falschen Modul, Umgehungen, die die
Importverträge nicht fassen, toter Code, Doku, die nicht mehr zum Code passt,
fehlende Fehlerfall-Tests. Eigener Abschnitt: **alle datensatz- oder
quellenspezifischen Stellen im Frontend** (Datensatz-IDs, Eigenschaftsnamen
wie `s2:*`, feste Schwellen, feste Blöcke der Suchkachel) mit Fundstelle — das
ist die Eingabe für M3-12.
**Nicht anfassen:** Code.
**Abnahme:** `docs/plans/m3-02-konformitaetsbericht.md` mit Fundstellen,
Schwere (Blocker / Schuld / Hinweis) und je Fund einem Vorschlag, in welche
Aufgabe er gehört.

### M3-03 — Wechsel auf Python 3.12

**Stand:** erledigt und gemergt (#75). Abweichungen vom Text stehen im Log.

**Ziel:** Backend, CI, Image und Cloud-Session laufen auf Python 3.12, bevor
neue Abhängigkeiten dazukommen.
**Stufe B.**
**Umfang:**
- `backend/requirements.txt`, `pyproject.toml`, `Dockerfile`, CI-Matrix in
  `.github/workflows/ci.yml` und `live-smoke.yml`, der SessionStart-Hook und
  sein Skript. Die Änderung an `.github/` und an der Hook-Datei unter
  `.claude/` ist für diese Aufgabe **ausdrücklich erlaubt**.
- Die Cloud-Umgebung hat Python 3.11 systemweit (`cloud-umgebung.md` §2) auf
  Ubuntu 24.04; das Ubuntu-Archiv ist erreichbar, `deadsnakes` nicht. Im
  Plan-Schritt **messen**, wie 3.12 in die Session kommt, bevor etwas
  umgestellt wird.
- `zarr` bleibt in dieser Aufgabe auf 3.1.x. Die Anhebung ist eine eigene
  Entscheidung.

**Im Plan-Schritt vorschlagen:** Weg zu 3.12 in der Session; ob 3.11 in der CI
übergangsweise mitläuft.
**Abnahme:** CI grün auf 3.12 (alle vier Pflicht-Checks); eine frisch
gestartete Session führt `pytest` aus der Repo-Wurzel ohne Nachinstallation
aus; `compose-topology` baut das Image auf 3.12.

### M3-04 — `/tilejson.json` mit freigegebenen Zoomstufen

**Stand:** erledigt und gemergt (#78). Abweichungen vom Text stehen im Log.

**Ziel:** Ein Client, der dem TileJSON folgt, wird nur auf freigegebene Stufen
geschickt.
**Stufe A.**
**Umfang:** `minzoom`/`maxzoom` im TileJSON kommen aus `earthx:viewer`
(`min_zoom`/`max_zoom` des Registry-Eintrags), nicht aus dem Reader (Log,
Review zu M2-10). Die Reader-Werte sind in rio-tiler berechnet und nicht
setzbar; der Weg ist eine eigene Route oder eine Nachbearbeitung der Antwort.
**Nicht anfassen:** Kachelroute, Riegel mit `400`, Registry-Werte.
**Abnahme:** Tests für beide Datensätze: TileJSON-Stufen gleich der Registry;
eine Kachel-URL aus dem TileJSON auf Grenzstufe liefert `200`, eine Stufe
darüber `400`; weiterhin kein freier `url`-Parameter im OpenAPI-Schema.

### M3-05 — Mess-Spike Heatmap-Zählwürfel → `adr/0010`

**Stand:** erledigt und gemergt (#80). Abweichungen vom Text stehen im Log.

**Ziel:** Otto kann entscheiden, ob und wie ein vorberechneter Zählwürfel die
Coverage-Heatmap verbessert (D26).
**Stufe C.** Kein Bau.
**Umfang:**
- Kandidat aus D26: Zählwürfel je Datensatz, Zelle z9 × Monat × Wolkenklasse,
  täglich aktualisiert. Das würde M2-05 F3 („keine Vorberechnung“) aufheben.
- Gemessen: Aufwand der Erstbefüllung aus der Quelle (Anzahl Anfragen, Dauer,
  Last), tägliche Aktualisierung, Größe in Postgres, Abfragelatenz für
  Weltansicht und AOI, Verhalten bei Quellen nur mit Stichprobe (EOPF).
- Alternativen mit Stand der Technik und Quellen (z. B. andere Zellraster,
  stac-geoparquet mit spaltenbasierter Abfrage, Vektorkacheln) gegen den
  heutigen Weg (`adr/0004`).
- Ort der Berechnung im Rahmen der Architektur: nicht im Worker-Kern (B9); der
  Vertrag `no-database-in-worker-core` bleibt.
- Pflichtfeld `completeness` aus `adr/0004` Regel V muss erhalten bleiben.

**Nicht anfassen:** Code.
**Abnahme:** `adr/0010-coverage-zaehlwuerfel.md` mit Messwerten, Optionen,
Empfehlung und Fragen an Otto.

### M3-06a — AOI-Upload: Backend-Route mit Shapefile

**Stand:** in Arbeit.

**Ziel:** Hochgeladene AOIs werden an einer Stelle einheitlich geprüft,
zusätzlich zu GeoJSON und KML auch als Shapefile (P7).
**Stufe B.**
**Umfang:**
- Route, die eine Datei annimmt und eine geprüfte Geometrie in EPSG:4326
  zurückgibt; nichts wird gespeichert, auch nicht auf Platte (wie der Download:
  Arbeitsspeicher oder `/vsimem/`).
- Formate: GeoJSON, KML, Shapefile als ZIP. Koordinatensystem aus der `.prj`;
  fehlt sie, wird abgewiesen, nicht geraten.
- Schutz: Größendeckel für Upload und entpackte Größe (ZIP-Bombe),
  Punktanzahl-Deckel, sichere XML-Verarbeitung für KML (keine externen
  Entitäten), ungültige und selbstschneidende Geometrien, Antimeridian.
- Keine Koordinaten und keine Dateiinhalte im Log.

**Im Plan-Schritt vorschlagen:** Bibliothek (etwa OGR über ein Paket oder eine
reine Python-Lösung) mit Begründung; Modul und Prozess der Route innerhalb der
Grenzen aus `architekturplan.md` 3.1, ohne neues Modul; erlaubte
Geometrietypen; Deckelwerte; Verhalten bei mehreren Features.
**Abnahme:** Tests für jedes Format mit gültiger Datei, fehlerhafter Datei,
falschem Typ, fehlender `.prj`, zu großer Datei, ZIP-Bombe, KML mit externer
Entität, zu vielen Punkten; Test, dass nichts außerhalb des Arbeitsspeichers
geschrieben wird; `lint-imports` grün.

### M3-06b — AOI-Upload: Frontend auf die Route

**Ziel:** Das Frontend lädt AOIs über die Route aus M3-06a hoch und kann
Shapefile.
**Stufe B.**
**Umfang:** Das Parsen im Client (`frontend/src/aoiFile.ts`) wird durch den
Aufruf der Route ersetzt; „letzte AOI“ bleibt im Client wie heute (F3).
Fehlermeldungen der Route werden verständlich angezeigt, auf Englisch.
**Abnahme:** Vitest für Aufruf und Fehlerabbildung; Otto lädt lokal je eine
Datei jedes Formats hoch.

### M3-07a — Ortssuche: Recherche und Backend-Route

**Ziel:** Die Plattform kann einen Ortsnamen in Umriss und Bounding Box
auflösen, über `gateway` und im Rahmen der Nutzungsbedingungen (P8, F2).
**Stufe B.** Voraussetzung: Allowlist aus §1.3.
**Umfang:**
- **Zuerst Recherche** mit Quellen: Nutzungsbedingungen von Nominatim
  (Anfragerate, Kennung per User-Agent, Attribution, Caching, Verbot von
  Autocomplete oder Massenabfragen) und Alternativen. Steht darin etwas, das
  P8 widerspricht, hält die Session an und berichtet.
- Adapter über `gateway`; Route im Prozess `api`. Nur Suche auf Absenden,
  kein Autocomplete. Höchstens 1 Anfrage pro Sekunde an Nominatim, über alle
  Prozesse hinweg. Cache in Postgres (E4); ein Ausfall des Caches macht nur
  langsamer (E5).
- Umriss als Polygon mit vereinfachter Punktanzahl; dazu die Bounding Box.
- Attribution „© OpenStreetMap contributors“ in der Antwort, damit das
  Frontend sie zeigen kann.
- Suchtext und Ergebnisse nicht im Log (Ortsnamen können personenbezogen
  sein).

**Im Plan-Schritt vorschlagen:** Woher der Geocoder-Host in die
Gateway-Allowlist kommt (heute stammt sie aus der Registry); Umsetzung der
prozessübergreifenden Rate; Cache-Frist; Deckel der Punktanzahl.
**Abnahme:** Tests gegen synthetische Fixtures: Treffer mit Umriss, Treffer
nur mit Punkt, kein Treffer, Quelle `429`/`5xx`/Zeitablauf, leere und zu lange
Eingabe; Test, dass die Rate greift; Test, dass kein Suchtext im Log landet;
Latenz per `curl` im PR belegt (M2-13).

### M3-07b — Ortssuche: Frontend

**Ziel:** Das Suchfeld für Orte ist zurück (F2) und liefert eine AOI.
**Stufe B.**
**Umfang:** Eigenes Feld in der Suchkachel, getrennt vom Feld „Scene name“
(M2-17). Treffer als Liste; Auswahl übernimmt Umriss oder Bounding Box als
AOI. Attribution sichtbar. Texte auf Englisch.
**Im Plan-Schritt vorschlagen:** ob der Nutzer zwischen Umriss und Bounding Box
wählt oder einer der beiden Vorgabe ist.
**Abnahme:** Vitest für Übernahme als AOI; Otto sucht lokal einen Ort und
startet damit eine Suche.

### M3-08 — `intersects` und `ids` durchreichen

**Stand:** erledigt und gemergt (#76). Abweichungen vom Text stehen im Log.

**Merge erst nach M3-16** (Otto, 23.09.2026): `intersects` ist ein weiterer
Query-Parameter mit Geometrie und darf nur in ein Log ohne Query-String.

**Ziel:** Polygon-AOIs suchen genau statt über ihre Bounding Box; `ids` wird
unterstützt statt mit `400` abgewiesen (D31, P6).
**Stufe B.**
**Umfang:**
- Beide Adapter (Earth Search, EOPF) reichen `intersects` und `ids` durch,
  soweit die Quelle sie unterstützt. Im Plan-Schritt per `curl` messen, was
  jede Quelle kann; eine Quelle ohne Unterstützung weist ehrlich ab.
- URL-Obergrenze rund 8 kB (`adr/0005`) und AOI-Verdünnung (`adr/0004` §3.4,
  D21) gelten weiter.
- Cache-Schlüssel mit Geometrie; die Geometrie soll nicht im Klartext in
  Tabellen oder Logs stehen.
- Frontend: Polygon- und Punkt-AOIs senden `intersects`.
- Die Landing Page weist nur aus, was alle beteiligten Quellen können (K8).

**Im Plan-Schritt vorschlagen:** Deckel für Punktanzahl und `ids`-Anzahl;
Verhalten, wenn eine Quelle `intersects` nicht kann.
**Abnahme:** Tests für Polygon, Punkt, zu große Geometrie, ungültige
Geometrie, `ids` mit bekannter, unbekannter und zu vieler Kennung; Test, dass
keine Koordinaten im Log landen; die bisherigen `400`-Tests aus M2-17 sind
angepasst.

### M3-09 — Vollauflösung zeigt nur den Zuschnitt

**Stand:** erledigt und gemergt (#84). Abweichungen vom Text stehen im Log.

**Ziel:** Nach „View full resolution“ sieht der Nutzer von den gewählten
Szenen nur den Teil innerhalb der AOI, also das, was er herunterlädt (P12).
**Stufe B.**
**Verhalten (entschieden):** Trefferliste mit ganzen Quicklooks wie heute. In
der Vollauflösung ist außerhalb der AOI das Bild ausgeblendet, die Basiskarte
bleibt sichtbar. Ein Knopf: mit AOI zugeschnitten, ohne AOI (Szenensuche per
Namen) die ganze Szene. Download: siehe M3-17.
**Randbedingungen:** keine exakte AOI in Kachel-URLs oder Logs; zustandslos,
kein Zwischenspeicher des Zuschnitts (`adr/0001`); kein Mosaik im Kachel-Pfad
(P11); keine datensatzspezifischen Sonderfälle; überlappende Szenen in
derselben Reihenfolge wie das Mosaik des Downloads (erster gültiger Pixel),
damit Ansicht und Datei übereinstimmen.
**Im Plan-Schritt vorschlagen,** mit Stand der Technik und Quellen: den Weg.
Zu prüfen ist mindestens das Beschneiden jeder Kachel im Browser vor der
Anzeige (die AOI verlässt den Browser dann nicht) gegen ein georeferenziertes
Bild aus dem Zuschnitt-Pfad per `POST` (wie die erste Stufe im Prototyp, F10).
Dazu die Beschriftung des Knopfs.
**Abnahme:** Vitest für die Logik; Test oder Beleg, dass keine AOI in einer
Kachel-URL steht; Otto prüft lokal mit einer AOI über zwei Szenen, dass Karte
und heruntergeladene Datei übereinstimmen.

### M3-10 — Datensatz-Filter in der Suchkachel

**Ziel:** Datensätze werden über einen Filter gewählt statt über feste Blöcke
(P9).
**Stufe B.**
**Umfang:** Liste aus `/stac/collections`, Filter über Titel, Beschreibung und
Schlagworte im Client; Reifegrad („staging“) bleibt sichtbar. Keine Suche im
Backend, keine Hybrid-Suche (M5).
**Im Plan-Schritt:** beschreiben, was die „festen Blöcke“ heute sind (am Code),
und die Bedienung vorschlagen.
**Abnahme:** Vitest für den Filter; mit drei Datensätzen keine
Datensatz-Kennung im Frontend-Code nötig.

### M3-11 — Dritte Quelle anbinden: Überblick

Die dritte Quelle ist **Copernicus DEM GLO-30, direkt aus dem Bucket**
(`adr/0009`, angenommen am 23.09.2026): zugleich dritter Datensatz und erste
Nicht-STAC-Quelle. Items liegen in **pgstac**, erzeugt von einem
**Einmal-Befehl in `discovery`**; Coverage ist die **Vereinigung der
Kachel-Umrisse** als Fläche, `completeness = complete`; die Lizenz ist
eingestuft (`adr/0003` §11.1, B11-Stufe *Processing*, Attribution mit
vorgeschriebenem Wortlaut). Die Arbeit ist in drei Teile geschnitten (P24).
Für alle drei gilt: **`readers` bleibt unverändert** (M3-Abnahme), Fixtures
sind synthetisch, und `adr/0009` §3.5 beschreibt den Code-Stand, auf dem sie
aufsetzen.

### M3-11a — Materialisierte Quellen in Registry, Dispatch und Item-Abruf

**Ziel:** Die Plattform kennt Collections, deren Items in pgstac liegen, als
eigene Art von Quelle: Sie sind über `/stac/search` findbar und über die
Kachel- und Download-Route lesbar, ohne dass ein Datensatz dafür schon
eingetragen ist.
**Stufe B.**
**Umfang:**
- **K-05:** `earthx:source` trennt „welcher Adapter die Items erzeugt bzw.
  abfragt“ von „föderiert oder materialisiert“. Heute entscheidet
  `SourceInfo.adapter` allein über die Föderation (`adr/0009` §3.5, §11). Eine
  materialisierte Collection wird ausdrücklich als solche erkannt, nicht daran,
  dass kein bekannter Adapter eingetragen ist. Neue Felder ohne Vorgabewert
  (B10); `architekturplan.md` 5.1 nachziehen.
- **Suche:** Materialisierte Collections gehen über den bestehenden
  pgstac-Pfad (`api/federating_client.py`, `super()`), jetzt aufgrund des neuen
  Felds.
- **Item-Abruf für Kacheln und Download:** zweiter Weg neben
  `adapters.get_item` für Items aus pgstac (`api/tiler.py::build_item_source`).
  Die Zugriffsauflösung bleibt bis M4 in `api/tiler.py` (K-04); keine
  Verlagerung in dieser Aufgabe.
- **K-03:** Die Kachelroute prüft die Lizenzstufe: Kacheln verlangen
  mindestens B11-Stufe „Anzeige“, der Download weiterhin „Processing“.
- **`catalog`** kann Items nach pgstac schreiben (`upsert`, pypgstac ist
  gepinnt), als Funktion für M3-11b; `catalog` importiert dafür keinen Adapter.

**Im Plan-Schritt vorschlagen:** Form und Namen der neuen Registry-Felder;
wie die beiden bestehenden Einträge sie setzen; ob `SourceInfo.harvest_run`
(heute ungenutzt) den Lauf protokolliert.
**Nicht anfassen:** `readers`, bestehende Registry-Werte außer der neuen
Angabe, die Coverage-Route (M3-11c).
**Abnahme:** Integrationstests mit einer synthetischen materialisierten
Collection und synthetischen Items in pgstac: Suche findet sie, eine Kachel und
ein Zuschnitt lesen sie, eine föderierte Collection verhält sich unverändert;
Lizenztest mit einem Eintrag der Stufe `catalog` (Kachel `403` bzw. die
bestehende Abweisung, Download abgewiesen); Onboarding-Checkliste für beide
bestehenden Datensätze grün; `lint-imports` grün.

### M3-11b — DEM-Adapter, Einmal-Befehl in `discovery`, Registry-Eintrag

**Ziel:** Copernicus DEM GLO-30 steht als dritter Datensatz im Katalog, seine
26 450 Items liegen in pgstac, und er besteht die Onboarding-Checkliste.
**Stufe B.** Hängt an M3-11a.
**Umfang:**
- **Adapter** in `adapters`: liest `tileList.txt` über `gateway` und baut
  aus dem Namensschema je Kachel ein Item (Footprint, Asset-`href` auf den
  DEM-COG). Dem Listing nicht blind glauben (`adr/0009` §11): im Plan-Schritt
  vorschlagen, wie fehlende Dateien erkannt werden, ohne 26 450 Anfragen je
  Lauf.
- **Einmal-Befehl** `python -m earthx.discovery.materialize <dataset>` (Name im
  Plan-Schritt): Adapter erzeugt, `catalog` schreibt per `upsert`;
  wiederholbar ohne Doppel; ein erneuter Lauf erkennt eine unveränderte Quelle
  (ETag von `tileList.txt`, `adr/0009` §7.3). Kein Zeitplan, keine
  Review-Queue (das ist M5).
- **Registry-Eintrag** als `DatasetConfig` (B13): Lizenz und Attribution laut
  `adr/0003` §11.1; `asset_hosts` mit genau einem Host, Vorschlag
  `copernicus-dem-30m.s3.amazonaws.com` (`adr/0009` §10.2; nie
  `s3.amazonaws.com` oder `amazonaws.com`); `earthx:data_class` als statisches
  Raster; Beschreibung mit einem Satz zur Lücke über dem Südkaukasus
  (`adr/0009` §10.3; ob Länder genannt werden, im Plan-Schritt); Darstellung
  eines `float32`-Höhenmodells ohne `nodata` (Farbskala, Wertebereich) in
  `earthx:viewer`; freigegebene Zoomstufen.
- **Onboarding-Checkliste** 1–10 grün, Punkt 10 über
  `@pytest.mark.live_dataset` (D29); Test mit synthetischer `tileList.txt`
  und synthetischen COGs.
- README: wie der Befehl lokal läuft.

**Im Plan-Schritt vorschlagen, Otto entscheidet:** die **Zeitangabe der
Items** (`adr/0009` §10.1: je Kachel aus der XML, ein Zeitraum für alle, oder
ein fester `datetime`; pgstac verlangt einen Zeitraum), mit der Folge für
Suchen mit Datumsfilter; wie der Befehl in `docker-compose.yml` bzw. lokal
gestartet wird; Farbskala und Zoomstufen, gemessen an echten Kacheln
(gedrosselt).
**Nicht anfassen:** `readers`; die Coverage-Route (M3-11c); Frontend (M3-12).
**Abnahme:** Befehl lädt synthetische Kacheln vollständig und idempotent;
Checkliste grün für drei Datensätze; eine Kachel und ein Zuschnitt des DEM
über die echte Kette lokal bei Otto; kein ausgehender Request außerhalb von
`gateway`.

### M3-11c — Coverage über eigene Items (`local-sql`)

**Ziel:** Die Coverage einer materialisierten Collection kommt aus ihren
eigenen Items; die Coverage-Route ist nicht mehr fest auf Earth Search und EOPF
verdrahtet (K-06).
**Stufe B.** Hängt an M3-11a; kann parallel zu M3-11b laufen.
**Umfang:**
- `CoverageProvider.LOCAL_SQL` bauen (heute `501`, `api/coverage_route.py`):
  SQL über die Items in pgstac. Für Einmal-Produkte laut `adr/0009` §6 die
  **Vereinigung der Footprints als Fläche**, keine Dichte;
  `completeness = complete` (`adr/0004` Regel V).
- Welcher Weg gilt, folgt aus dem Registry-Eintrag, nicht aus einer
  Fallunterscheidung nach Quelle; Earth Search und EOPF verhalten sich
  unverändert, der Weltüberblick nach P22 auch.
- Antwortgröße im Rahmen von `adr/0004` (500 kB), auch für die Weltansicht
  mit 26 450 Kacheln; im Plan-Schritt messen, ob die Fläche vereinfacht werden
  muss und mit welcher Toleranz.

**Im Plan-Schritt vorschlagen:** Form der Antwort für eine Fläche (die
Heatmap kennt heute Zellen); wo die Vereinigung berechnet wird (SQL bei jeder
Anfrage oder vorberechnet beim Laden durch M3-11b); Cache.
**Nicht anfassen:** das Zeichnen im Frontend (M3-12, F-07).
**Abnahme:** Tests mit synthetischen Items: Fläche deckt genau die Footprints,
Lücken bleiben Lücken; Earth Search und EOPF unverändert; Antwortgröße unter
der Schwelle; keine Koordinaten der Anfrage im Log.

### M3-12 — Frontend-Sonderfälle in die Registry

**Ziel:** Das Frontend kennt keinen Datensatz und keine quellenspezifische
Eigenschaft mehr (P10, M3-Abnahme).
**Stufe B.** Nach M3-11b (echter DEM-Eintrag) und M3-10, mit dem Bericht aus
M3-02 als Eingabe. Braucht M3-17 ein Registry-Feld für COG oder Zarr, wird es
hier übernommen.
**Umfang:** Jede Stelle aus M3-02, die der DEM trifft, wird ein
Registry-Feld (bekannt: Gruppierung der Trefferliste nach `s2:datatake_id`
aus D30, Nodata-Schwelle 16 der Quicklooks). Dazu die vier Stellen, an denen
ein globales Raster in EPSG:4326 scheitert (M3-02, Abschnitt 5): Quicklooks
werden nur für UTM platziert (F-03); die Ausdehnung eines Einmal-Produkts wird
in der Coverage nicht gezeichnet (F-07); das Datumsfeld erscheint auch ohne
Zeitachse (F-06); die Vorschau-Stufe zeigt bei `min_zoom = 0` fast nichts
(F-05). Die Coverage des DEM erscheint als Fläche (Antwortform aus M3-11c).
`earthx:viewer.group_by` setzt heute ein `datetime` voraus (`adr/0009` §10.1).
Bevor dafür ein neues Feld entsteht, prüfen, ob `earthx:data_class`
(`architekturplan.md` 5.1) es schon trägt. Felder ohne Vorgabewert (B10),
Zeile in `architekturplan.md` 5.1 nachziehen. Dazu ein Test, der
`frontend/src` außerhalb der Tests auf Datensatz-Kennungen und
quellenspezifische Eigenschaftsnamen prüft.
**Im Plan-Schritt vorschlagen:** Feldnamen und -form; Otto gibt neue Felder
frei.
**Abnahme:** Test grün; beide bestehenden Datensätze verhalten sich
unverändert; der DEM ist im Viewer suchbar, als Fläche in der Coverage
sichtbar, in voller Auflösung anzeigbar und als Zuschnitt ladbar; Checkliste
grün; Otto prüft lokal.

### M3-13 — Gemischte Suche und CQL2

**Ziel:** Eine Suche über eigene und föderierte Collections liefert eine
einheitliche STAC-Antwort (`adr/0005` Regel I, D8); die CQL2-Frage ist neu
entschieden (Regel VI).
**Stufe B**, Plan-Schritt mit Opus (hoch), weil Paging über mehrere Quellen
heikel ist. Nach M3-11b: Die eigenen Items des DEM sind die erste echte
eigene Collection.
**Umfang:** gemischte Suche statt `400`; Seitenmarke über mehrere Quellen;
Teilergebnisse und Zeitablauf je Quelle gekennzeichnet (`architekturplan.md`
16); Konformitätsklassen der Landing Page passend zur schwächsten beteiligten
Quelle (K8); `filter` nur dort, wo es tatsächlich wirkt.
**Im Plan-Schritt vorschlagen:** Paging-Verfahren; ob CQL2 je Collection
ausgewiesen wird und wie ein Client das erkennt; ob der Viewer die gemischte
Suche nutzt oder je Datensatz bleibt.
**Abnahme:** Tests für gemischte Suche mit eigener und föderierter Collection,
Ausfall einer Quelle, Paging über die Grenze, unbekannte Collection, `filter`
auf einer Collection ohne Unterstützung.

### M3-14 — Interface-Reflexion → `adr/0011`

**Ziel:** Das Adapter-Interface ist aus drei realen Quellen abgeleitet und von
Otto freigegeben.
**Stufe C.** Opus, Effort hoch; Fable nur, wenn Otto die Session interaktiv
führt (P15).
**Umfang:** Die Adapter von Earth Search, EOPF und der dritten Quelle
vergleichen; Fähigkeiten aus `architekturplan.md` 6.1 (Discovery, Suche,
Zugriffsauflösung, Aggregation) gegen das Tatsächliche halten; Optionen für
Signaturen mit Kriterien (Nicht-STAC nicht in STAC-Form gepresst, Test mit
synthetischen Fixtures, Folgen für den Harvester in M5 und Processing in M4);
Lehren aus EODAG knapp mit Quellen (`architekturplan.md` 15.2). Beobachtungen
aus `adr/0009` §11 einbeziehen, dazu die Erfahrungen aus M3-11a–c. Der **Zielort der Zugriffsauflösung** (heute
`api/tiler.py`, K-04 aus M3-02) ist eine eigene Option in `adr/0011`: Das ADR
legt ihn fest, der Umbau ist der erste Schritt von M4, bevor `processing` die
Auflösung braucht (Otto, 23.09.2026).
**Nicht anfassen:** Code.
**Abnahme:** `adr/0011-adapter-interface.md` mit Optionen, Empfehlung und
Fragen; Otto gibt frei (M3-Abnahme).

### M3-15 — M3-Abnahme und README

**Ziel:** Otto kann M3 anhand des PR abnehmen, ohne Code zu lesen.
**Stufe A.**
**Umfang:** Bericht `docs/plans/m3-15-abnahme.md` mit Belegen je Kriterium aus
Abschnitt 5, nach dem Muster von `m2-12-abnahme.md`; README um den neuen
Datensatz, Attribution (auch OpenStreetMap), Upload-Formate und Ortssuche
ergänzt. `architekturplan.md` 5.2 an den Datums-Fallback im Frontend anpassen
(entschieden mit M2-07a am 20.09.2026, bestätigt am 23.09.2026), mit dem
Vermerk: Neubewertung mit der Verfügbarkeits-Zeitleiste in M5.

### M3-16 — Keine AOI im Log

**Stand:** erledigt und gemergt (#85). Abweichungen vom Text stehen im Log.

**Ziel:** Kein Prozess schreibt Koordinaten oder Query-Strings ins Log
(`CLAUDE.md`; K-01, K-02 aus `plans/m3-02-konformitaetsbericht.md`).
**Stufe A.** Sonnet (hoch).
**Umfang:**
- Access-Log jedes HTTP-Prozesses ohne Query-String: Methode, Pfad, Status,
  Dauer, Request-ID.
- `configure_logging` und `RequestIdMiddleware` in jedem Prozess einbinden.
- `summarize_geometry` überall dort, wo Geometrien geloggt werden.
- Startbefehle bzw. `docker-compose.yml` anpassen.

**Nicht anfassen:** `gateway`, Routenlogik.
**Abnahme:** Tests gegen die App mit echtem Logging-Setup für
`GET /stac/search?bbox=…`, `GET /coverage/…?bbox=…` und `POST …/download`:
keine Koordinate im Log, Request-ID vorhanden; `compose-topology` grün.
**Hängt ab von:** —. M3-08 wird erst nach M3-16 gemergt.

### M3-17 — Download folgt der Ansicht

**Stand:** in Arbeit, PR #88 im Review. Freigegeben mit allen Fragen (F1–F6)
nach Empfehlung (Otto, 26.09.2026); Details, Optionen und die Umsetzung
stehen in `plans/m3-17-download-folgt-ansicht.md` §9/§10. Die Abhängigkeit
von M3-12 entfiel wie unten vermerkt (Otto, 23.09.2026): Die Gruppierung je
Überflug hat M3-09 schon gebaut, `download.ts`/`api/tiler.py` verwenden sie
wieder (`groups: string[][]`/`list[list[str]]`), keine neue
datensatzspezifische Stelle. Die Angabe, ob ein Datensatz COG oder Zarr ist,
kam als neues Feld `earthx:format` (Abbildung des vorhandenen
`DatasetConfig.format`, kein neues Registry-Feld nötig) — unabhängig von
M3-12, das den festen Gruppierungs-Eigenschaftsnamen weiterhin selbst in die
Registry räumt. **Status erst nach dem Merge auf „erledigt“ setzen** (Otto,
Review von PR #88).

**Ziel:** Der Download liefert immer das, was die Karte zeigt (P19).
**Stufe B.**
**Verhalten (entschieden):** siehe P19.
**Im Plan-Schritt vorschlagen:** welche Dateien bei „Original“ geladen werden
(nur die Bänder der sichtbaren Darstellung oder alle); wie der Browser
mehrere Originale lädt; wie Gruppen im Download-Request übergeben werden,
ohne datensatzspezifische Logik im Frontend; Beschriftung des Knopfs. Dazu
prüfen: Lizenz und Attribution beim direkten Laden von der Quelle (B11), ob
die Asset-URLs öffentlich über https erreichbar sind, und dass die AOI nicht
in URLs oder Logs landet. **Aus M3-09 bereits bekannt (PR #84, Otto-Review
24.09.2026), als Randbedingung für den Plan-Schritt:** der bestehende
Zuschnitt-Endpunkt taugt nicht für ein Original — er deckelt strukturell auf
`MAX_OUTPUT_SIDE_PX` (`access/download.py`, M3-18) — das Original muss direkt
von der Quelle kommen, ohne Umweg über die Plattform; für Zarr ohne AOI fehlt
noch der deaktivierte Download-Knopf mit Hinweis „Draw an AOI to download“
(das Muster „Knopf deaktiviert + Tooltip mit Begründung“ gibt es in M3-09
schon einmal, dem „Crop & merge to AOI“-Knopf ohne AOI, `ViewBar.tsx`, und
lässt sich hier übernehmen). Weitere Fundstellen aus M3-09: ein
`<a href=… download>`-Link im Browser lädt eine öffentliche Asset-URL ohne
CORS-Freigabe (anders als die Canvas-Weiterverarbeitung der Quicklooks);
ob eine Quelle COG oder Zarr ist, steht heute für das Frontend nirgends ohne
datensatzspezifische Fallunterscheidung — dafür fehlt ein Registry-Feld,
wahrscheinlich zusammen mit M3-12. Details: `plans/m3-09-zuschnitt-ansicht.md`
§7/§8.
**Abnahme:** Tests für jeden Fall aus P19 (Zuschnitt eine Gruppe, Zuschnitt
mehrere Gruppen, eine ganze Szene COG, Zarr ohne AOI deaktiviert, mehrere
ganze Szenen einzeln); Otto prüft lokal, dass Karte und Datei übereinstimmen.

### M3-18 — Download-Deckel nach Ausgabegröße und Maske auf die AOI

**Stand:** erledigt und gemergt (#86). **Umgesetzt wurde abweichend vom Text
unten:** native Auflösung ohne automatische Verkleinerung, Deckel 500 MB roh
mit Gleichzeitigkeitsgrenze (P20), Maske statt nodata mit Ausdehnung
AOI ∩ Footprints (P21). Maßgeblich sind P20, P21 und das Log vom 24.09.2026.

**Ziel:** Ein Zuschnitt über viele Szenen scheitert nicht mehr an einer
Schätzung über die Eingabe-Items. Beim Polygon-AOI enthält die Datei nur
Pixel innerhalb des Polygons.
**Stufe B.**
**Umfang:**
- Die Größenprüfung vor dem Lesen rechnet mit der Ausgabe (Dateien × Assets ×
  Pixel × Bytes nach dem Mergen), nicht mit Items × Assets. Zusätzlich eine
  Grenze für den Arbeitsspeicher, die aus einer Messung stammt.
- Zuschnitt maskiert auf die AOI-Geometrie (nodata außerhalb, für jeden
  Datensatz und jede Gruppe gleich). Die Verdünnung der AOI (`adr/0004` §3.4,
  D21) und der Punktanzahl-Deckel gelten weiter.

**Im Plan-Schritt:** den Spitzenverbrauch an Arbeitsspeicher von
`mosaic_reader` bei 1, 6 und 20 Items mit synthetischen COGs messen; daraus
die Speichergrenze vorschlagen (z. B. höchste Zahl Items je Anfrage oder
Abbruch des Mosaiks, sobald alle Pixel gefüllt sind).
**Abnahme:** Tests für 6 Items unter dem Ausgabe-Deckel (200), Ausgabe über
dem Deckel (Abweisung mit klarer Meldung), Speichergrenze greift; die Meldung
im Frontend auf Englisch und verständlich. Test mit schrägem Polygon: Pixel
außerhalb sind nodata, innerhalb gefüllt; Rechteck-AOI unverändert; keine
Koordinaten im Log.

### M3-19 — Weltüberblick ohne AOI

**Stand:** erledigt und gemergt (#83). **Umgesetzt wurde abweichend vom Text
unten** (Otto, 23./24.09.2026, P22): Ohne AOI fragt die Heatmap den sichtbaren
Ausschnitt ab, die Zellstufe folgt dem Kartenzoom; die Aufgabe lief deshalb
mit Plan-Schritt.

**Ziel:** Ohne AOI fordert die Coverage-Heatmap unabhängig vom Kartenzoom immer
z6 an (`adr/0010`, Frage 6).
**Stufe A.**
**Umfang:** nur die Stelle im Frontend, die die Zellstufe der Coverage-Anfrage
wählt; mit AOI bleibt alles wie heute.
**Abnahme:** Vitest: ohne AOI bei jedem Kartenzoom z6, mit AOI unverändert;
Otto prüft lokal die Weltansicht.

### M3-20 — Spike Ersatz für MinIO → `adr/0012`

**Ziel:** Otto kann vor M4 entscheiden, welcher S3-kompatible Objektspeicher
MinIO in der Topologie ersetzt (P23).
**Stufe C.** Kein Produktivcode; die Übergangslösung `bitnamilegacy/minio`
bleibt, bis Otto entscheidet.
**Umfang:**
- Lage klären, mit Quellen: Was hat MinIO an Images und Lizenz geändert, gibt
  es noch einen offiziellen, frei ziehbaren Weg (etwa Bau aus dem Quelltext),
  und wie lange taugt `bitnamilegacy/minio`?
- Kandidaten, mindestens Garage, SeaweedFS und RustFS; weitere mit
  Begründung. Je Kandidat: Lizenz (vereinbar mit AGPL-3.0-or-later), Pflege
  und Reife, offizielles Image und dessen Herkunft, S3-Funktionen, die M4
  braucht (Multipart-Upload, vorsignierte URLs, Range-Reads für COG, Ablauf
  bzw. Lebenszyklus für Ergebnisse, Bucket-Richtlinien), Ressourcenbedarf für
  lokale Entwicklung und CI, Betriebsaufwand.
- Was sich in `architekturplan.md` (Objektspeicher, Topologie) und in
  `docker-compose.yml` ändern müsste; ob `gateway` betroffen ist.
- Messen, soweit ohne Docker möglich (Binärdatei, gedrosselt); sonst
  „unbelegt“ und im ADR sagen, was die CI später belegen muss.

**Nicht anfassen:** Code, `docker-compose.yml`.
**Abnahme:** `adr/0012-objektspeicher.md` mit Kriterienmatrix, Belegen je
Aussage, Empfehlung und Fragen an Otto.

### M3-21 — Doku-Abgleich nach Fassung 2

**Ziel:** Log und Plandokumente widersprechen einander nicht mehr (Durchsicht
vom 26.09.2026).
**Stufe A.** Nur `docs/`; kein Code.
**Umfang:**
- `ENTSCHEIDUNGSLOG.md`, nur die Status-Spalte bestehender Zeilen ändern, Text
  stehen lassen; die Zeilen am Inhalt finden, nicht an der Zeilennummer:
  - „Zuschnitt sichtbar: je Gruppe … Deckel 4096 px und 200 MB bleiben“ →
    „Deckel ersetzt am 2026-09-24 (native Auflösung, 500 MB, P20)“.
  - „Download-Deckel: 200 MB gelten für die Ausgabe …“ → „Wert ersetzt am
    2026-09-24 (500 MB, F10a)“.
  - „M3-09: Vollauflösung zeigt nur den Zuschnitt (F1 (1), F2 eigener Wortlaut,
    F3)“ → „F3 zurückgenommen am 2026-09-24 (Review-Nachträge zu #84)“.
  - „M3-18 freigegeben mit F1 (1) …“ → „F5 (keine Gleichzeitigkeitsgrenze) und
    200-MB-Deckel ersetzt am 2026-09-24 (F10a)“.
  - „M3-18, Abweichung von F3 (2): … GDAL-interne Maskenband …“ → „ersetzt am
    2026-09-24 (Bug B: nodata-Tag der Quelle, Maske als eigene Datei)“.
  - „M3-03 F4 (1): Der SessionStart-Hook setzt `.venv/bin` …“ → „fest, in
    frischer Session belegt am 2026-09-23“.
  - „Maske statt nodata (Otto) …“: Status „präzisiert am 2026-09-23“ auf
    „präzisiert am 2026-09-24“ berichtigen.
  - Die beiden Zeilen zur Korruption beim COG-Schreiben (ZSTD statt DEFLATE;
    „Aktualisierung/Verschärfung“) bleiben „Vorschlag“, bis M3-22 sie
    auflöst; Status ergänzen um „→ M3-22“.
- `projektplan.md`: Stand und Version; M3-Abschnitt auf M3-00 bis M3-22 und
  P1–P24; §10 „Welche Nicht-STAC-Quelle“ → entschieden (Copernicus DEM
  GLO-30 aus dem Bucket, `adr/0009`); beim Objektspeicher MinIO einen Verweis
  auf P23 und M3-20.
- `adr/0004`, Stelle „ohne räumlichen Filter höchstens z6“: Nachtrag mit Datum,
  dass der Weltüberblick seit M3-19 den sichtbaren Ausschnitt als räumlichen
  Filter schickt (P22) und der z6-Deckel nur noch für Anfragen ganz ohne
  Bounding Box gilt. Originaltext stehen lassen.
- `architekturplan.md` Abschnitt Deployment/Topologie („lokal MinIO“): Verweis
  auf P23 und M3-20.

**Nicht anfassen:** Code, andere Plan-Dateien.
**Abnahme:** Jeder Punkt im Diff nachvollziehbar; keine bestehende Log-Zeile
gelöscht oder im Text geändert.

### M3-22 — Gelegentlich unlesbare Download-Dateien

**Ziel:** Kein Download liefert eine beschädigte Datei. Heute schreibt
`cog_translate` mit Maske gelegentlich eine unlesbare COG (Log 24.09.2026:
„ZIPDecode: incorrect data check“, bei DEFLATE und ZSTD); die CI von #86
scheiterte am 24.09.2026 einmal an „TIFF directory is missing required
ImageLength field“ im Test
`test_a_slanted_aoi_masks_agree_and_values_are_near_identical`. Die Ursache ist
offen.
**Stufe B**, Plan-Schritt mit Opus (hoch).
**Umfang:**
- Ursache finden: Schreibweg (`/vsimem/`, `cog_translate`, fensterweises
  Schreiben), `NUM_THREADS`, GDAL/libtiff-Version 3.12, Wechselwirkung mit
  `pytest`. Reproduktion mit Wiederholungen (z. B. 500 Läufe), auch in der
  CI.
- **Sofortschutz, unabhängig von der Ursache:** Jede erzeugte Datei wird vor
  dem Ausliefern vollständig gelesen bzw. validiert; ist sie defekt, wird
  einmal neu geschrieben, sonst `500` mit Request-ID und klarer englischer
  Meldung. Nie eine defekte Datei an den Nutzer.
- Kompression entscheiden (Log 24.09.2026, ZSTD statt DEFLATE, „Vorschlag“):
  Lesbarkeit in verbreiteten Programmen (QGIS, ältere GDAL) mit Beleg.
- Der betroffene Test wird stabil grün; ein Stresstest läuft in der CI mit
  begrenzter Laufzeit.

**Im Plan-Schritt vorschlagen:** Reproduktionsweg und Messplan; Form des
Sofortschutzes und seine Kosten (Zeit, Speicher bei 500 MB); Kompression.
**Abnahme:** Ursache belegt oder, falls nicht auffindbar, begründet
eingegrenzt; Sofortschutz mit Tests (defekte Datei → Neuversuch → Erfolg bzw.
`500`); der Test aus der CI von #86 in 50 Wiederholungen grün; die zwei
Log-Zeilen zur Korruption auf „fest“ oder „ersetzt“.

---

## 5. Abnahme von M3

1. Die dritte Quelle (ohne Such-API, materialisierte Items) ist im Viewer
   suchbar, anzeigbar und als Zuschnitt ladbar. `readers` ist in M3
   unverändert (Beleg über den Diff), das Frontend enthält keine
   datensatzspezifischen Sonderfälle (Test aus M3-12). Otto prüft lokal.
2. Onboarding-Checkliste als Test grün für jeden aufgenommenen Datensatz.
3. Gemischte Suche über eigene und föderierte Collections liefert eine
   STAC-Antwort; `filter` ist nur dort ausgewiesen, wo es wirkt.
4. AOI aus GeoJSON, KML und Shapefile über das Backend; Ortssuche mit Umriss
   und Bounding Box; Polygon-AOIs suchen über `intersects`.
5. Die Vollauflösung zeigt mit AOI nur den Zuschnitt, ohne AOI die ganze
   Szene; keine AOI in Kachel-URLs oder Logs; der Download entspricht der
   Ansicht (M3-17), in nativer Auflösung (P20), mit Maske (P21).
6. `adr/0011` (Adapter-Interface) ist von Otto freigegeben.
7. Importregeln grün, kein ausgehender Request außerhalb von `gateway`;
   Pflicht-CI grün auf Python 3.12.
8. `adr/0012` (Ersatz für MinIO) liegt Otto zur Entscheidung vor.
9. Kein Download liefert eine beschädigte Datei (M3-22).

---

## 6. Risiken

| Risiko | Umgang |
|---|---|
| Kein Kandidat erfüllt alle Kriterien, vor allem „`readers` unverändert“ | `adr/0009` nennt den Verstoß offen; Otto entscheidet, ob die Abnahme angepasst oder ein anderer Kandidat genommen wird |
| Das Interface wird doch STAC-förmig | M3-14 erst nach der dritten Quelle; Kriterium „Nicht-STAC nicht in STAC-Form gepresst“ |
| Nominatim-Bedingungen passen nicht zum Plan | M3-07a hält nach der Recherche an; Alternativen stehen im Bericht |
| Upload als Angriffsfläche (ZIP-Bombe, XML-Entitäten, riesige Geometrien) | Deckel und Tests in M3-06a; Planung und Review mit Opus |
| Gemischte Suche ist so langsam wie die langsamste Quelle | Zeitablauf je Quelle, Teilergebnisse gekennzeichnet (M3-13) |
| Zuschnitt-Ansicht weicht von der Download-Datei ab | gleiche Reihenfolge wie das Mosaik; lokale Prüfung durch Otto (M3-09) |
| Python 3.12 nicht in die Cloud-Session zu bekommen | M3-03 misst im Plan-Schritt, bevor umgestellt wird |
| Mehrere Frontend-Aufgaben berühren die Suchkachel | feste Reihenfolge M3-06b → M3-07b → M3-10 → M3-12 |
| Zeitangabe der DEM-Items lässt den DEM bei Suchen mit Datumsfilter verschwinden | M3-11b schlägt die Zeitangabe mit Folgen vor, Otto entscheidet; M3-12 blendet das Datumsfeld ohne Zeitachse aus |
| Coverage-Fläche aus 26 450 Kacheln ist zu groß für die Weltansicht | M3-11c misst und vereinfacht mit belegter Toleranz |
| `bitnamilegacy/minio` wird ebenfalls unerreichbar oder unsicher | nur CI und lokal, per Digest gepinnt; M3-20 vor M4 |
| Mehrere PRs ändern `ENTSCHEIDUNGSLOG.md` am Ende | vor dem Fertigmelden `main` holen, alle Zeilen erhalten, eigene ans Ende |
