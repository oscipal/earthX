# M3 — Erste Nicht-STAC-Quelle und Interface-Reflexion: Aufgabenschnitt

**Status:** Fassung 1 vom 23.09.2026. Nichts ist begonnen. Die Aufgaben der
dritten Quelle (M3-11) werden nach der Annahme von `adr/0009` in Fassung 2 im
Einzelnen geschnitten.
**Ort im Repo:** `docs/plans/m3-dritte-quelle-und-interface.md`
**Grundlagen:** `projektplan.md` 4 (M3); `architekturplan.md` 3.1, 3.2, 5.1,
5.2, 6.1, 6.5, 12.3, 15.1, 15.2; `adr/0001` (Zustand), `adr/0002` (Tests),
`adr/0003` (Datensätze), `adr/0004` (Coverage), `adr/0005` (föderierte Suche),
`adr/0006` (Kachel-Pfad), `adr/0007` (Zarr), `adr/0008` (Prototyp entfernt);
`plans/m2-format-und-viewer.md` (D1–D31, „Nach M2 vorgemerkt“);
`plans/m2-12-abnahme.md`; `prototyp-inventar.md`; `projektuebersicht.md` §5
(Onboarding-Checkliste); `KLAERUNGEN.md` B8–B13; `ENTSCHEIDUNGSLOG.md`, Zeilen
vom 23.09.2026.

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

### 1.1 Bereits entschieden (Otto, 23.09.2026, Log)

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
| P12 | **Zuschnitt auf der Karte:** Die Trefferliste zeigt die Quicklooks ganz. In der vollen Auflösung zeigt die Karte von den gewählten Szenen nur den Teil innerhalb der AOI; außerhalb ist das Bild ausgeblendet, die Basiskarte bleibt. Ein Knopf wie bisher (mit AOI zugeschnitten, ohne AOI ganze Szene); Beschriftung im Plan-Schritt. Download unverändert. Weg im Plan-Schritt | M3-09 |
| P13 | **Heatmap-Zählwürfel:** in M3 nur ein Mess-Spike; gebaut wird später | M3-05 |
| P14 | **Health-Status kommt mit M5** | M3-00 |
| P15 | **Interface-Reflexion** nach dem Merge der dritten Quelle, Stufe C, Opus mit Effort hoch | M3-14 |
| P16 | **Kleinaufgaben:** tilejson-Fix als Stufe A; Python 3.12 als frühe Stufe-B-Aufgabe | M3-03, M3-04 |
| P17 | **M3-00 Doku** bereinigt die Widersprüche aus der M3-Vorbereitung | M3-00 |
| P18 | **Konformitätsbericht** einmal zu Beginn von M3, keine Routine | M3-02 |

### 1.2 Was in allen Aufgaben gilt

`CLAUDE.md` gilt vollständig: ein Branch, ein Draft-PR, Tests für Fehlerfälle
und zweckfremde Nutzung, Fixtures nur synthetisch, keine exakten AOIs in Logs,
alles Ausgehende über `gateway`, Worker-Kern zustandslos, `decomp.py` bleibt
unberührt. Dazu aus M2: Oberflächentexte nur Englisch, keine Sprachwahl (D25,
D28). Neue Registry-Felder ohne Vorgabewert (B10). Was hier nicht entschieden
ist, schlägt die Session im Plan-Schritt mit nummerierten Optionen und
Empfehlung vor und hält an. Vor dem Fertigmelden `main` in den Branch holen;
eigene Log-Zeilen ans Ende von `ENTSCHEIDUNGSLOG.md`, alle anderen erhalten.

**Stufe B heißt hier:** Der Plan liegt als `docs/plans/m3-xx-<kurzname>.md` im
Draft-PR, die Session hält an, Otto gibt frei, dann wird in derselben Session
umgesetzt.

### 1.3 Von Otto auszuführen

- **Vor M3-01:** `zenodo.org` in der Allowlist der Cloud-Umgebung freigeben
  (heute gesperrt, `adr/0007` §3). Die übrigen Kandidaten sind laut Messung
  schon erreichbar: `storage.googleapis.com` (Hansen GFC, ARCO-ERA5;
  `adr/0007` §3) und `copernicus-dem-30m.s3.amazonaws.com` (`adr/0003` §10).
  Leitet einer davon auf einen anderen Host um, meldet die Session den Host
  und hält an.
- **Vor M3-07a:** `nominatim.openstreetmap.org` freigeben (heute gesperrt,
  `cloud-umgebung.md` §6). Nur für Messungen per `curl`; Tests laufen gegen
  synthetische Fixtures.
- **Nach M3-01:** Quelle wählen, Materialisierung wählen, Lizenz des neuen
  Datensatzes einstufen (B11, immer Otto). Danach schneide ich M3-11 in
  Fassung 2 dieses Plans.
- **Lokal prüfen, offen aus M2:** Was passiert beim Download mit einer AOI
  größer als 4096 px je Seite (verkleinert oder abgewiesen)? Soll sich das
  ändern, wird daraus eine kleine Aufgabe.

---

## 2. Abgrenzung

**In M3:** eine Nicht-STAC-Quelle mit materialisierten Items; Onboarding
dieser Quelle nach der Checkliste; gemischte Suche und CQL2-Prüfung;
`intersects` und `ids`; AOI-Upload über das Backend samt Shapefile; Ortssuche
mit Umriss und Bounding Box; Zuschnitt in der Vollauflösungs-Ansicht;
Datensatz-Filter in der Suchkachel; Frontend-Sonderfälle in die Registry;
tilejson-Fix; Python 3.12; Konformitätsbericht; Mess-Spike Zählwürfel;
Interface-ADR.

**Nicht in M3:** Mosaik im Kachel-Pfad (M4, P11); Rezept, Operatoren, Jobs,
Objektspeicher (M4); Bau des Heatmap-Zählwürfels (P13); Health-Status und
Prüfdatum (M5, P14, D29); Hybrid-Suche (M5); Uvicorn-Worker des `tiler` (M5);
COG-Header-Cache (Log offen); Neubewertung MinIO (vor M4); Ratenbegrenzung pro
IP oder Nutzer (D6); Bug-Report Stufe 2 (D9); helle Basiskarte (D10);
Viewer-Pakete Swipe/Export; alles zum ersten öffentlichen Deployment (AGPL
§13, Nutzungsbedingungen).

---

## 3. Übersicht und Reihenfolge

| ID | Aufgabe | Stufe | Modell (Effort) | hängt ab von |
|---|---|---|---|---|
| M3-00 | Doku nachziehen | A | Sonnet (mittel) | — |
| M3-01 | Spike dritte Quelle → `adr/0009` | C | Opus (hoch) | Allowlist §1.3 |
| M3-02 | Architektur-Konformitätsbericht | C | Opus (hoch) | — |
| M3-03 | Wechsel auf Python 3.12 | B | Opus Plan, Sonnet (hoch) | — |
| M3-04 | `/tilejson.json` mit freigegebenen Zoomstufen | A | Sonnet (mittel) | — |
| M3-05 | Mess-Spike Heatmap-Zählwürfel → `adr/0010` | C | Opus (hoch) | — |
| M3-06a | AOI-Upload: Backend-Route mit Shapefile | B | Opus Plan, Sonnet (hoch) | M3-03 |
| M3-06b | AOI-Upload: Frontend auf die Route | B | Opus Plan, Sonnet (mittel) | M3-06a |
| M3-07a | Ortssuche: Recherche und Backend-Route | B | Opus Plan, Sonnet (hoch) | Allowlist §1.3 |
| M3-07b | Ortssuche: Frontend | B | Opus Plan, Sonnet (mittel) | M3-07a, M3-06b |
| M3-08 | `intersects` und `ids` durchreichen | B | Opus Plan, Sonnet (hoch) | — |
| M3-09 | Vollauflösung zeigt nur den Zuschnitt | B | Opus Plan, Sonnet (hoch) | — |
| M3-10 | Datensatz-Filter in der Suchkachel | B | Opus Plan, Sonnet (mittel) | M3-07b |
| M3-11 | Dritte Quelle anbinden (Teile in Fassung 2) | B | Opus Plan, Sonnet (hoch) | `adr/0009` angenommen |
| M3-12 | Frontend-Sonderfälle in die Registry | B | Opus Plan, Sonnet (hoch) | `adr/0009` angenommen, M3-02, M3-10 |
| M3-13 | Gemischte Suche und CQL2 | B | Opus Plan (hoch), Sonnet (hoch) | M3-11 (eigene Items) |
| M3-14 | Interface-Reflexion → `adr/0011` | C | Opus (hoch) | M3-11, M3-13 |
| M3-15 | M3-Abnahme und README | A | Sonnet (mittel) | alle |

**Wellen.** Höchstens zwei Stufe-B-Sessions gleichzeitig; Stufe A und C laufen
daneben.

1. **Welle 1:** M3-00, M3-01, M3-02, M3-04, M3-05 (A/C), dazu M3-03 und M3-08 (B).
2. **Welle 2:** M3-06a, M3-09, danach M3-06b, M3-07a.
3. **Welle 3:** M3-07b, M3-10; nach Annahme von `adr/0009` M3-11 und M3-12.
4. **Welle 4:** M3-13, dann M3-14, zuletzt M3-15.

**Dateikonflikte im Frontend:** M3-06b, M3-07b, M3-10 und M3-12 berühren die
Suchkachel (`ControlPanel.tsx` und Umgebung); deshalb nacheinander in dieser
Reihenfolge. M3-09 berührt Karte und Layer (`MapView.tsx`, `mapLayers.ts`) und
kann parallel laufen.

**Feste ADR-Nummern**, damit parallele Sessions nicht kollidieren:
`adr/0009-dritte-quelle.md` (M3-01), `adr/0010-coverage-zaehlwuerfel.md`
(M3-05), `adr/0011-adapter-interface.md` (M3-14).

---

## 4. Die Aufgaben

### M3-00 — Doku nachziehen

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

**Ziel:** Nach „View full resolution“ sieht der Nutzer von den gewählten
Szenen nur den Teil innerhalb der AOI, also das, was er herunterlädt (P12).
**Stufe B.**
**Verhalten (entschieden):** Trefferliste mit ganzen Quicklooks wie heute. In
der Vollauflösung ist außerhalb der AOI das Bild ausgeblendet, die Basiskarte
bleibt sichtbar. Ein Knopf: mit AOI zugeschnitten, ohne AOI (Szenensuche per
Namen) die ganze Szene. Download unverändert.
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

### M3-11 — Dritte Quelle anbinden

**Ziel:** Die in `adr/0009` gewählte Nicht-STAC-Quelle läuft mit
materialisierten Items im Katalog und im Viewer und besteht die Checkliste.
**Stufe B.** **Wird nach Annahme von `adr/0009` in Fassung 2 in Teile
geschnitten**; bis dahin nicht starten.
**Bekannte Eckpunkte:** Adapter nach `architekturplan.md` 6.1; Items einmalig
erzeugt und laut Entscheidung zu P4 abgelegt; Registry-Eintrag als
`DatasetConfig` in `catalog/datasets.py` (B13), `asset_hosts` gesetzt (D12);
Coverage laut `adr/0009`; Lizenz wie von Otto eingestuft; Checkliste 1–10 grün,
Punkt 10 über `@pytest.mark.live_dataset` (D29); **`readers` unverändert**
(M3-Abnahme); Fixtures synthetisch.

### M3-12 — Frontend-Sonderfälle in die Registry

**Ziel:** Das Frontend kennt keinen Datensatz und keine quellenspezifische
Eigenschaft mehr (P10, M3-Abnahme).
**Stufe B.** Nach Annahme von `adr/0009`, mit dem Bericht aus M3-02 als
Eingabe.
**Umfang:** Jede Stelle aus M3-02, die der dritte Datensatz trifft, wird ein
Registry-Feld (bekannt: Gruppierung der Trefferliste nach `s2:datatake_id`
aus D30, Nodata-Schwelle 16 der Quicklooks). Felder ohne Vorgabewert (B10),
Zeile in `architekturplan.md` 5.1 nachziehen. Dazu ein Test, der
`frontend/src` außerhalb der Tests auf Datensatz-Kennungen und
quellenspezifische Eigenschaftsnamen prüft.
**Im Plan-Schritt vorschlagen:** Feldnamen und -form; Otto gibt neue Felder
frei.
**Abnahme:** Test grün; beide bestehenden Datensätze verhalten sich
unverändert; Checkliste grün.

### M3-13 — Gemischte Suche und CQL2

**Ziel:** Eine Suche über eigene und föderierte Collections liefert eine
einheitliche STAC-Antwort (`adr/0005` Regel I, D8); die CQL2-Frage ist neu
entschieden (Regel VI).
**Stufe B**, Plan-Schritt mit Opus (hoch), weil Paging über mehrere Quellen
heikel ist.
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
aus `adr/0009` einbeziehen.
**Nicht anfassen:** Code.
**Abnahme:** `adr/0011-adapter-interface.md` mit Optionen, Empfehlung und
Fragen; Otto gibt frei (M3-Abnahme).

### M3-15 — M3-Abnahme und README

**Ziel:** Otto kann M3 anhand des PR abnehmen, ohne Code zu lesen.
**Stufe A.**
**Umfang:** Bericht `docs/plans/m3-15-abnahme.md` mit Belegen je Kriterium aus
Abschnitt 5, nach dem Muster von `m2-12-abnahme.md`; README um den neuen
Datensatz, Attribution (auch OpenStreetMap), Upload-Formate und Ortssuche
ergänzt.

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
   Szene; keine AOI in Kachel-URLs oder Logs.
6. `adr/0011` (Adapter-Interface) ist von Otto freigegeben.
7. Importregeln grün, kein ausgehender Request außerhalb von `gateway`;
   Pflicht-CI grün auf Python 3.12.

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
| Mehrere PRs ändern `ENTSCHEIDUNGSLOG.md` am Ende | vor dem Fertigmelden `main` holen, alle Zeilen erhalten, eigene ans Ende |
