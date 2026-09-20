# M2 — Zweites Format und generalisierter Viewer: Aufgabenschnitt

**Status:** Fassung 2 vom 20.09.2026, nach dem Merge von #32–#35 und der Annahme
von `adr/0006` (Kachel-Pfad) und `adr/0007` (Zarr). Alle Entscheidungen stehen im
`docs/ENTSCHEIDUNGSLOG.md`; die Fragen aus Abschnitt 1.2 sind beantwortet
(F1 = a, F2 = a). Erledigt: M2-00, M2-01, M2-02, M2-03.
**Ort im Repo:** `docs/plans/m2-format-und-viewer.md`
**Grundlagen:** `projektplan.md` 4 (M2, Viewer-Strang); `architekturplan.md` 3.1,
3.2, 6, 12.3, 13, 15.2; `adr/0001` (Zustand, Z4), `adr/0002` (Tests), `adr/0003`
(Datensätze), `adr/0004` (Coverage), `adr/0005` (föderierte Suche), `adr/0006`
(Kachel-Pfad), `adr/0007` (zweites Format Zarr);
`prototyp-inventar.md`; `projektuebersicht.md` §5 (Onboarding-Checkliste);
`plans/m1-fundament.md`.

Eine Sitzung startet eine Aufgabe mit: „Führe Aufgabe M2-xx aus
`docs/plans/m2-format-und-viewer.md` aus.“ Jede Aufgabe ist ohne das
Planungsgespräch verständlich und endet mit genau einem Draft-PR. Aufgaben mit
Buchstaben (M2-07a, M2-07b …) sind je eine eigene Session und ein eigener PR.

---

## 0. Ziel in einem Satz

Zwei token-freie Datensätze in zwei Formaten (COG und Zarr) laufen im selben
Viewer. Sentinel-2 L2A ist dabei vollständig nach der Onboarding-Checkliste
aufgenommen, und das Frontend spricht nur noch mit der Zielarchitektur `earthx`.

---

## 1. Vor dem Start

### 1.1 Bereits entschieden (Log, 2026-09-20)

| # | Entscheidung | wirkt auf |
|---|---|---|
| D1 | M2a Sentinel-2 durchgehend, M2b Zarr. Zarr-ADR sofort parallel, Kandidatenfeld offen | Schnitt, M2-03 |
| D2 | Die neun Modulverträge zählen nur direkte Importe; `datasets-isolated` und `no-database-in-worker-core` zählen weiter Ketten | M2-01 |
| D3 | Download des Zuschnitts synchron gestreamt, nichts gespeichert, Größendeckel, ZIP aus COG und Hinweisdatei; Objektspeicher und Rezept bleiben M4 | M2-06 |
| D4 | Checkliste v1: Punkt 9 = Suche → Anzeige → Zuschnitt-Download; Punkt 10 = letzter grüner T-D-Smoke | M2-08 |
| D5 | Rahmen des Kachel-Spikes, samt Prüfpunkt Asset-Host | M2-02 |
| D6 | Keine Ratenbegrenzung der Coverage in M2; Cache und Deckel je Host tragen | M2-05 |
| D7 | Tag `prototype-biomass`, dann Frontend vollständig auf `earthx`; Backend `app` bleibt bis zur Vorlage M2-11 | M2-07, M2-11 |
| D8 | Gemischte Suche bleibt `400`; der Viewer sucht je Datensatz | M2-07a, M2-10 |
| D9 | Bug-Report-Pipeline Stufe 2 nicht in M2 | M2-00 |
| D10 | Theme-Umschalter im Viewer-Strang, ohne helle Basiskarte | V-1 |
| D11 | **Mosaik** in M2 nur im Zuschnitt, nicht im Kachel-Pfad (2,7 MB je Mosaik-Kachel, kein CDN) | M2-06 |
| D12 | **`asset_hosts`** als neues Feld an `SourceInfo`, ohne Vorgabewert; fließt in die Gateway-Allowlist ein. Heute liest `policy_from_registry` nur `source.endpoint`, der Asset-Host wird abgewiesen | M2-04, M2-09b |
| D13 | **Statistik-Cache** als eigene Tabelle, 30 Tage. `titiler.core==2.3.0` exakt gepinnt, Pfad über ersetzte `path_dependency`, Streckbereich über `rescale`/`colormap_name` | M2-04 |
| D14 | **Quicklook-Proxy entfällt**, der Browser lädt das Thumbnail direkt; der Asset-Bucket sendet `Access-Control-Allow-Origin: *`. Das hebt den Asset-Proxy aus ENTSCHEIDUNGEN §2 ausdrücklich auf und gilt nur für Quellen mit CORS — der EOPF-Objektspeicher sendet keinen Header, dort käme ein Proxy zurück | M2-04, M2-07a, M2-09b |
| D15 | **Einstieg des `tiler`-Prozesses** wandert nach `api`; `httpx2` und `obstore` kommen auf die Verbotsliste, dazu ein Test, dass nichts `rio_tiler.io.stac` importiert | M2-04 |
| D16 | **M2-09 wird geteilt:** 09a Reader gegen synthetisches Mini-Zarr (quellenunabhängig), 09b realer Datensatz | M2-09a, M2-09b, M2-10 |
| D17 | **Python bleibt 3.11**, `zarr` auf 3.1.x; `titiler-eopf` ist ausgeschieden. Der gemessene Pfad ist eigener `zarr.abc.store.Store` → `zarr` → `xarray` → `rio_tiler.io.xarray.XarrayReader` | M2-09a |
| D18 | **STAC 1.1 → 1.0** wird im Adapter normalisiert; Lizenz des zweiten Datensatzes wie beim ersten | M2-09b |
### 1.2 Fragen an Otto — beantwortet am 20.09.2026

| # | Frage | Optionen | Antwort | betrifft |
|---|---|---|---|---|
| F1 | **Ortssuche nach der Umstellung.** Das Frontend ruft heute `/api/geocode` des Prototyps auf (Nominatim). In `earthx` gibt es die Route nicht, der Geocoder ist aus der Cloud nicht erreichbar, und die Nominatim-Bedingungen sind offen. | (a) Ortssuche in M2 ausblenden; sie kommt mit M3 („Ortssuche mit Umriss“, projektplan M3). (b) Jetzt eine `earthx`-Route über `gateway` bauen. | **(a)** Ortssuche in M2 ausgeblendet | M2-07a |
| F2 | **Frontend-Tests.** Für das Frontend gibt es heute nur Lint und Typprüfung; `adr/0002` regelt nur das Backend. Die URL-Bildung für Kacheln (Z4) ist aber fehleranfällig. | (a) Vitest für reine Logik (URL-Bau, Gruppierung, Umschaltpunkt Coverage) als Schritt im CI-Job `frontend`; die Änderung an `.github/` ist dafür ausdrücklich erlaubt. (b) Bei Lint und Typprüfung bleiben. | **(a)** Vitest im CI-Job `frontend` | M2-07a |

### 1.3 Von Otto auszuführen

- **Erledigt am 20.09.2026:** `data.eodc.eu` ist in der Allowlist der Cloud-Umgebung freigegeben; `download.user.eopf.eodc.eu` bleibt gesperrt. Die Freigabe wirkt nur in **neu gestarteten** Sessions und betrifft allein die Umgebung — in die Gateway-Allowlist der Plattform kommt der Host erst über den Registry-Eintrag in M2-09b (D12).
- Vor M2-07a: Tag `prototype-biomass` auf `main` setzen (Sessions können keine Tags pushen).
- Offen: der SessionStart-Hook installiert `psycopg` und `stac-fastapi` nicht und migriert pgstac nicht; mehrere Sessions mussten das nachholen. Eigene kleine Aufgabe, nicht Teil von M2.

---

## 2. Abgrenzung

**In M2:** Importverträge nach D2; Kachel-Pfad für COG mit Streckbereich in der URL;
Quicklooks direkt vom Asset-Host (D14); Coverage-Heatmap nach `adr/0004`; Download des
AOI-Zuschnitts; Frontend auf `earthx` mit Suche, Quicklooks, Zeitleiste,
Darstellungssteuerung, Layer-Manager-Basis, Coverage und Download; Datums-Fallback
mit Hinweis; Onboarding-Checkliste v1 als Test; Zarr-ADR, Zarr-Reader und zweiter
Datensatz; Vorlage zum Entfernen des Prototyps; Theme-Umschalter (Viewer-Strang).

**Nicht in M2:** Ergebnisse im Objektspeicher, Rezept, Operatoren, Jobs (M4);
gemischte Suche über mehrere Quellen (M3, D8); Ortssuche (M3, F1);
AOI-Upload über das Backend und Shapefile (M3; der Upload im Client bleibt, wie er
ist); Ratenbegrenzung pro IP oder Nutzer (D6); Bug-Report Stufe 2 (D9); helle
Basiskarte (D10); Vektorkacheln (`adr/0004` §7 Frage 2); Mosaik im Kachel-Pfad
(D11); Wechsel auf Python 3.12 (D17); das Entfernen des Prototyps selbst (erst nach
Ottos Entscheidung zu M2-11).

---

## 3. Übersicht und Reihenfolge

| ID | Aufgabe | Stufe | Modell (Effort) | hängt ab von |
|---|---|---|---|---|
| M2-00 | Doku nachziehen | A | — | **erledigt** (#32) |
| M2-01 | Importverträge nach D2 | A | — | **erledigt** (#33) |
| M2-02 | Spike Kachel-Pfad → `adr/0006` | C | — | **erledigt** (#34) |
| M2-03 | Zarr-ADR → `adr/0007` | C | — | **erledigt** (#35) |
| M2-03b | Nachmessung EOPF nach der Freigabe | C | Opus (hoch) | Freigabe `data.eodc.eu` |
| M2-04 | Kachel-Pfad für Sentinel-2 | B | Plan Opus, Umsetzung Sonnet (hoch) | — |
| M2-05 | Coverage-Anbieter und Route | B | Plan Opus, Umsetzung Sonnet (hoch) | — |
| M2-06 | Download des AOI-Zuschnitts | B | Plan Opus, Umsetzung Sonnet (hoch) | M2-04 |
| M2-07a | Frontend: API-Client, Suche, Quicklooks, Zeitleiste | B | Plan Opus, Umsetzung Sonnet (mittel) | Tag |
| M2-07b | Frontend: Kacheln, Darstellungssteuerung, Layer-Manager | B | Plan Opus, Umsetzung Sonnet (hoch) | M2-04, M2-07a |
| M2-07c | Frontend: Coverage-Heatmap | B | Sonnet (mittel) | M2-05, M2-07a |
| M2-07d | Frontend: Download | B | Sonnet (mittel) | M2-06, M2-07b |
| M2-08 | Onboarding-Checkliste v1 als Test, Sentinel-2 vollständig | B | Plan Opus, Umsetzung Sonnet (mittel) | M2-05, M2-06, M2-07d |
| M2-09a | Zarr-Lesepfad gegen synthetisches Mini-Zarr | B | Plan Opus, Umsetzung Sonnet (hoch) | — |
| M2-09b | Zweiter Datensatz im Katalog | B | Plan Opus, Umsetzung Sonnet (hoch) | M2-03b, M2-04, M2-09a |
| M2-10 | Zweiter Datensatz im Viewer | B | Plan Opus, Umsetzung Sonnet (mittel) | M2-09b, M2-07c |
| M2-11 | Vorlage: Prototyp entfernen | C | Opus | M2-08 |
| M2-12 | M2-Abnahme und README | A | Sonnet (mittel) | alle |
| V-1 | Theme-Umschalter (Viewer-Strang) | A | Sonnet (mittel) | M2-07b |

**Wellen.** Höchstens zwei Stufe-B-Sessions gleichzeitig, damit die Reviews nicht
stauen (`m1-fundament.md` §6).

1. ~~M2-00, M2-01, M2-02, M2-03~~ — erledigt
2. M2-04, M2-05; dazu M2-03b (Stufe C, zählt nicht gegen die zwei)
3. M2-06, M2-07a
4. M2-07b, M2-07c, M2-09a
5. M2-07d, M2-09b, V-1
6. M2-08, M2-10
7. M2-11, M2-12

M2b (M2-03b, M2-09a, M2-09b, M2-10) läuft als eigener Strang neben M2a. Nur M2-09b
hängt an M2a, weil es den Kachel-Pfad aus M2-04 wiederverwendet.

---

## 4. Die Aufgaben

Für alle Aufgaben gilt `CLAUDE.md`: ein Branch, ein Draft-PR, Tests für Fehlerfälle
und zweckfremde Nutzung, Fixtures nur synthetisch, keine exakten AOIs in Logs,
alles Ausgehende über `gateway`. Was hier nicht entschieden ist, schlägt die Session
im Plan-Schritt mit nummerierten Optionen und Empfehlung vor und hält an.

### M2-00 bis M2-03 — erledigt

Die vier Aufgaben der ersten Welle sind gemergt: #32 (Doku), #33 (Importverträge),
#34 (`adr/0006`), #35 (`adr/0007`). Die Aufgabentexte bleiben unten als Beleg
stehen; ihre Ergebnisse stecken in D11 bis D18.

### M2-03b — Nachmessung EOPF nach der Freigabe

**Ziel:** Die Aussagen, die `adr/0007` über die gesperrten Collections offenlassen
musste, werden nachgemessen, damit Otto den zweiten Datensatz festlegen kann.
**Stufe C:** nur messen und `adr/0007` ergänzen; kein Produktivcode, nichts außerhalb
von `docs/`. Voraussetzung ist eine **neu gestartete** Session, sonst wirkt die
Freigabe nicht.
**Umfang:** Gegen `data.eodc.eu` und die Collection `sentinel-2-l2a-zarr3` messen:
Erreichbarkeit; Chunk-Aufbau und Chunk-Größen je Auflösungsgruppe; Georeferenzierung
aus `proj:code`; Lesekosten für eine Kachel auf den Stufen, die der Viewer wirklich
zeigt, und für einen AOI-Zuschnitt; tatsächlicher Bestand und Aktualität; ob ein
Quicklook auflöst; CORS des Objektspeichers; erkennbare Ratengrenzen. Den Lesepfad
aus `adr/0007` (eigener Store → `zarr` → `xarray` → `XarrayReader`) einmal end-to-end
gegen die echte Quelle belegen. Umfang der Live-Zugriffe klein halten und im ADR
ausweisen.
**Ergebnis:** Ergänzung in `adr/0007` mit den Messwerten, dazu eine Empfehlung, ob
`sentinel-2-l2a-zarr3` der zweite Datensatz wird, welche Zoomstufen der Viewer
freigeben sollte (eine Kachel in nativer Auflösung kostet 3–16 MB) und was daraus
für M2-09b folgt. Bleibt etwas untragbar, benennt die Ergänzung die Alternative aus
der Kandidatenmatrix.

### M2-00 — Doku nachziehen (erledigt, #32)

**Ziel:** Die Plandokumente widersprechen den Entscheidungen vom 20.09.2026 nicht mehr.
**Umfang:**
- `projektplan.md` M2: Teilung M2a/M2b, Verweis auf diese Datei; Funktionen um „Download des AOI-Zuschnitts“ ergänzen.
- `projektplan.md` 6.1: Stufe 2 der Bug-Report-Pipeline nicht mehr M2, sondern „vertagt bis zur Frage nach dem Deployment“ (D9).
- `projektplan.md` Viewer-Strang: Theme-Umschalter ohne helle Basiskarte (D10).
- `adr/0005` §8 Punkt 4: Nachtrag, dass die gemischte Suche bis M3 abgelehnt bleibt (D8).
- `adr/0004` §8 Punkt 6: Nachtrag, dass die Ratenbegrenzung bewusst vertagt ist (D6).
- `architekturplan.md` 6.4: Nachtrag, dass der Zuschnitt in M2 gestreamt und nicht gespeichert wird (D3).
- `projektuebersicht.md` §5: Fassung v1 der Punkte 9 und 10 (D4).
- `KLAERUNGEN.md` B3: `UEBERGABE_CHAT.md` ist gelöscht.
- `cloud-umgebung.md` §6: Widerspruch benennen, nicht auflösen. Die Tabelle führt `stac.eopf.copernicus.eu` als gesperrt, `adr/0003` §10.1 misst `stac.core.eopf.eodc.eu` und `objects.eodc.eu` als erreichbar; die Klärung macht M2-03.

**Nicht anfassen:** Code, `.github/`, `ENTSCHEIDUNGSLOG.md` (von Otto schon aktualisiert).
**Abnahme:** Keine Stelle in `docs/` widerspricht einer Log-Zeile vom 2026-09-20.

### M2-01 — Importverträge nach D2 (erledigt, #33)

**Ziel:** `access → readers → gateway` und `processing → catalog → gateway` sind erlaubt; direkte Verstöße und die Kette zur Datenbank im Worker-Kern bleiben verboten.
**Umfang:**
- In `.importlinter` bei den Verträgen `gateway`, `catalog`, `adapters`, `readers`, `access`, `processing`, `jobs`, `discovery`, `identity` `allow_indirect_imports = True` setzen, mit Kommentar und Verweis auf die Log-Zeile. `datasets-isolated` und `no-database-in-worker-core` bleiben unverändert. Diese Änderung ist ausdrücklich erlaubt (Lockerung von Otto entschieden).
- `backend/tests/test_module_boundaries.py` erweitern: Der Test prüft, dass genau diese Verträge Ketten ignorieren und die beiden anderen Ketten zählen.
- Gegenproben im PR belegen: ein direkter Import `access → gateway` fällt weiterhin; eine Kette `access → readers → gateway` besteht; eine Kette `processing → catalog → psycopg` fällt.

**Nicht anfassen:** Modulinhalte; alle übrigen Verträge.
**Abnahme:** `lint-imports` grün; die drei Gegenproben im PR dokumentiert.

### M2-02 — Spike Kachel-Pfad (erledigt, #34)

**Ziel:** Entscheidungsvorlage, wie der `tiler`-Prozess Kacheln, Statistik und Quicklooks liefert (`architekturplan.md` 6.3, 15.2; `projektplan.md` 10 „TiTiler-Basis“).
**Stufe C:** nur ADR-Entwurf, kein Produktivcode. Stand der Technik mit Quellen und Versionen; Beleg-Stufen wie in `adr/0004` ([M] gemessen, [P] Primärquelle, [S] Sekundärquelle). Live-Messungen gegen Earth Search nur in kleinem Umfang (Metadaten und einzelne Kachelreads), wie in M1-05.
**Fragen:**
1. Lassen sich die TiTiler-Fabriken so einhängen, dass nach außen **kein freier `url`-Parameter** existiert, sondern nur `dataset`/`item`/`asset`, aufgelöst über Katalog und Adapter (B8, SSRF)? Welche Pakete und Versionen; bringen sie eigene HTTP-Clients mit (z. B. über Mosaik-Pakete), die an `gateway` vorbeigingen?
2. Wie passiert jede URL vor der Übergabe an GDAL/rasterio die Prüfung in `gateway`, und wie greift die zentrale GDAL-Konfiguration aus M1-03?
3. **Streckbereich in der URL (Z4):** Form der Parameter; ein Statistik-Endpunkt, dessen Ergebnis der Client in die Kachelvorlage setzt; Statistik im Postgres-Anwendungs-Cache (E4) mit Frist; Ausfall macht nur langsamer (E5).
4. **Mosaik und Stitching:** zustandslos per Item-Liste in der URL gegen Such-ID mit Cache (`architekturplan.md` 6.3). URL-Länge, CDN-Fähigkeit, Kosten. Empfehlung, ob Stitching in M2 zustandslos machbar ist.
5. **Quicklook-Proxy** (Inventar F6, F15; ENTSCHEIDUNGEN §2): Wo liegt er, ohne 3.1 zu verletzen? `access` darf `gateway` nicht direkt importieren. Optionen z. B. Route in `api` über `gateway` oder ein Byte-Reader in `readers`.
6. Nur `https`, kein `s3` für COG: bestätigen oder begründet widersprechen.
7. **Prüfpunkt Asset-Host:** Welcher Host liefert die Assets von `sentinel-2-c1-l2a` tatsächlich (`sentinel-cogs…` laut `cloud-umgebung.md` oder `e84-earth-search-sentinel-data…` laut `adr/0003` §10.1)? Welcher steht heute in der Allowlist aus der Registry? An echten Items und am Code prüfen.
8. Rendering-Kosten je Kachel (Laufzeit, Bytes von der Quelle) für einige typische Fälle, als Grundlage für Prinzip 10 der Projektübersicht.

**Abnahme:** `adr/0006` mit Optionen, Kriterien, Messwerten, Empfehlung, Quellen und nummerierten Fragen an Otto.

### M2-03 — Zarr-ADR (erledigt, #35)

**Ziel:** Entscheidungsvorlage für den zweiten Datensatz im Format Zarr und für den Lesepfad (`architekturplan.md` 6.2; `adr/0003` §6, §10.3).
**Stufe C**, Stand der Technik mit Quellen, Beleg-Stufen wie `adr/0004`.
**Zuerst:** Erreichbarkeit der Kandidaten-Hosts messen (u. a. `stac.core.eopf.eodc.eu`, `objects.eodc.eu`). Ist ein Host gesperrt: genau benennen und diesen Teil anhalten.
**Fragen:**
1. **Kandidatenfeld offen.** EOPF Sentinel Zarr Samples ist Kandidat, nicht gesetzt. Gibt es andere token- und registrierungsfreie Zarr-Quellen mit Zeitachse? Jeden Kandidaten mit Primärquelle belegen.
2. Je Kandidat: Lizenz nach B11 (Einstufung bleibt Otto vorbehalten, hier nur Vorschlag), Dauerhaftigkeit, tatsächliche Verfügbarkeit im Archiv, Thumbnail/Quicklook, Ratengrenzen, Zugang per `https` oder `s3` (Gateway, M1-03 F4), CORS (`architekturplan.md` 14 Punkt 5).
3. **STAC 1.1 an einer 1.0-API:** Wie werden Items einer 1.1-Quelle durch unsere föderierte API gereicht (Lizenzwert `other`/`proprietary`, Log 2026-09-19)?
4. **Lesepfad:** `zarr_reader.py` auf xarray/zarr gegen titiler-eopf bzw. titiler.xarray; GeoZarr-`multiscales` für die Kacheln; AOI-Zuschnitt über Chunks (Inventar F9, Naht „Array + Maske + Transform“). Reifegrad und Versionen der Bausteine.
5. **Coverage:** Hat die Quelle eine Aggregation, oder greift die ausgewiesene Stichprobe (`adr/0004` Option 6)?
6. Quicklook-Ersatz, falls die Quelle keinen führt (bei EOPF belegt: keiner).
7. Was passiert mit M2, wenn kein Kandidat trägt?

**Abnahme:** `adr/0007` mit Kandidatenmatrix, Empfehlung, Quellen und nummerierten Fragen an Otto.

### M2-04 — Kachel-Pfad für Sentinel-2

**Ziel:** Der `tiler`-Prozess liefert Kacheln und Statistik für Sentinel-2; die Kachel-URL bestimmt das Bild vollständig (Z4).
**Stufe B.** Aufbau laut angenommenem `adr/0006`; die Messwerte und die Begründungen stehen dort, dieser Text nennt nur den Umfang.
**Umfang:**
- **`asset_hosts`** an `SourceInfo`, ohne Vorgabewert, fließt in `policy_from_registry` ein (D12). Ohne das weist `check_url` den Asset-Host ab, und der Lesepfad steht. Eintrag für Sentinel-2: `e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com`.
- `readers/cog.py`: partielle COG-Reads auf rio-tiler; jede URL vorher über `gateway` geprüft; nur `https`.
- `access`: Kacheln und Statistik laut `adr/0006`, `titiler.core==2.3.0` exakt gepinnt, Pfad über ersetzte `path_dependency`, kein freier `url`-Parameter im OpenAPI-Schema; Streckbereich über `rescale`/`colormap_name` (D13).
- **Kein Quicklook-Proxy** (D14): Quicklooks lädt das Frontend direkt vom Asset-Host.
- Statistik-Cache als eigene Tabelle per Migration in `catalog`, 30 Tage (D13, E4); Ausfall macht nur langsamer (E5).
- **Standard-Visualisierung** (Checkliste Punkt 8, `adr/0001` FZ7): Bandzuordnung, Stretch und Colormap als Feld im Registry-Eintrag; Feldform im Plan-Schritt vorschlagen.
- **Einstieg des `tiler`-Prozesses** nach `api` verlegen; `httpx2` und `obstore` auf die Verbotsliste in `.importlinter`; Test, dass kein Modul `rio_tiler.io.stac` importiert (D15).
- `docker-compose.yml`: `tiler` bekommt die Postgres-Umgebungsvariablen und den neuen Einstiegspunkt. Aus M1-07 bekannt: `api` startete ohne sie nicht.

**Nicht anfassen:** `backend/app/`; Suche und STAC-API außer für die Asset-Auflösung; Mosaik (D11).
**Abnahme:** dieselbe Kachel-URL liefert gegen zwei Instanzen dieselben Bytes; ein geleerter Statistik-Cache macht nur langsamer; kein Endpunkt nimmt eine freie URL an (Test mit Umgehungsversuchen, dazu Prüfung am OpenAPI-Schema); ein Asset-Host, der nicht in der Registry steht, wird abgewiesen; fehlerhafte `z/x/y`, unbekanntes Item, unbekanntes Band ergeben definierte Fehler; `lint-imports` und `compose-topology` grün.

### M2-05 — Coverage-Anbieter und Route

**Ziel:** Die gefilterte Coverage für Sentinel-2 nach `adr/0004`.
**Stufe B.**
**Umfang:**
- Nahtstelle „Coverage-Anbieter“ in `catalog`; Earth-Search-Aggregation als Adapter-Fähigkeit in `adapters` (GET mit langer Abfragezeichenfolge über `gateway`); Verdrahtung in `api`.
- Geotile-Gitter, Stufe aus dem Kartenausschnitt, gedeckelt durch die typische Footprint-Größe aus der Registry (Sentinel-2: höchstens z8).
- Zählweise Zentroid; Pflichtfeld `vollstaendig` / `gekappt` / `stichprobe` mit der Probe `sum(Zellen) == total_count` (Regel V).
- Umschaltpunkt: bei `numberMatched < 500` Footprints statt Dichte, Zoom als zusätzliche Bremse.
- Zeit-Histogramm aus derselben Anfrage; Einmal-Produkte aus dem Collection-`extent` (Flag aus der Registry; in M2 nur mit synthetischem Test, weil kein Einmal-Produkt dabei ist).
- Postgres-Cache mit 24 h / 5 min und der 7-Tage-Grenze (Log 2026-09-19).
- Die ausgewiesene Stichprobe wird **nicht** hier gebaut, sondern in M2-09b. `adr/0007` hat belegt, dass die EOPF-Quelle weder `numberMatched` noch eine Aggregation liefert; die Nahtstelle muss diesen Fall also vorsehen, ohne ihn schon zu füllen.

**Im Plan-Schritt vorschlagen:** Pfad der Route; wie der ungefilterte Weltüberblick (`adr/0004` Option 2) bei einer föderierten Quelle vorgehalten wird; ob die Aufteilung in zwei PRs nötig ist (Richtwert 400 Zeilen).
**Abnahme:** Tests für die Kappungsfalle (`adr/0004` §3.3), die vereinfachte AOI (§3.4), Upstream-Fehler, geleerten Cache (E5), Umschaltpunkt; Latenz gegen die Quelle im PR gemessen, Ziel unter 1 s, typisch unter 0,5 s.

### M2-06 — Download des AOI-Zuschnitts

**Ziel:** Der Nutzer erhält den Zuschnitt als Datei (ENTSCHEIDUNGEN §2 „neu zu bauen“; D3).
**Stufe B.**
**Umfang:**
- Route in `access`, die für Item(s) und AOI den Zuschnitt über `readers` liest und als ZIP streamt: COG plus Textdatei mit Attribution, `terms_notice` (Sprache wählbar, Deutsch Vorgabe), `terms_url` und Zitierangabe aus der Registry.
- Nichts wird auf Platte oder in den Objektspeicher geschrieben; Größendeckel (Pixel und Bytes) vor dem Lesen geprüft.
- **Mosaik** aus mehreren Szenen zustandslos über die Item-Liste in der Anfrage; laut `adr/0006` trägt das im Zuschnitt, im Kachel-Pfad nicht (D11).

**Im Plan-Schritt vorschlagen:** Wert des Größendeckels (Otto entscheidet); Prozess (`tiler` oder `api`); Aufbau der Textdatei.
**Abnahme:** Tests für zu große AOI, AOI außerhalb des Items, fehlerhafte Geometrie, unbekanntes Item; Test, dass kein Schreibzugriff außerhalb des Arbeitsspeichers erfolgt; die Hinweisdatei enthält Attribution und den vollständigen `terms_notice`; keine AOI-Koordinaten im Log.

### M2-07 — Frontend auf `earthx` (vier PRs)

**Gemeinsam für 07a–07d:**
- Ausgangspunkt ist `frontend/` nach dem Tag `prototype-biomass`. Die BIOMASS-Teile (Produktmodell in `products.ts`, Polarisationen, Dekomposition in `ViewerControls.tsx`, Token-Meldungen) entfallen, jeweils in der Aufgabe, die ihre Stelle ersetzt.
- Das Frontend spricht nur mit `earthx` (`/stac`, `tiler`-Routen, Coverage-, Download-Route), nie mit `/api` des Prototyps. Die Vite-Proxy-Konfiguration wird entsprechend umgestellt.
- Datensatz ist überall Parameter, kein fester Wert (`ControlPanel.tsx`, `store.ts` generalisieren). Gesucht wird je Datensatz (D8).
- HUD-Design und Bedienmuster laut Inventar Teil 3 bleiben.
- Tests mit Vitest für reine Logik (URL-Bau für Kacheln und Statistik, Gruppierung, Umschaltpunkt der Coverage, Datums-Fallback), keine Oberflächentests. M2-07a richtet Vitest ein und nimmt es als Schritt in den CI-Job `frontend` auf; diese Änderung an `.github/workflows/ci.yml` ist ausdrücklich erlaubt (F2).

**M2-07a — API-Client, Suche, Quicklooks, Zeitleiste.** F1 AOI-Auswahl, F3 Upload und letzte AOI (im Client, wie bisher), F4 Suche gegen `/stac` mit eigener Seitenmarke, F5 Gruppierung mit Schlüssel aus der Registry (bei Sentinel-2 naheliegend Datum und MGRS-Kachel; im Plan-Schritt bestätigen), F6 Quicklooks direkt vom Asset-Host, ohne Proxy (D14), mit Canvas-Keying wie im Prototyp, F7 Zeitleiste, F8 Ablauf. **Datums-Fallback:** liegt im gewählten Zeitraum nichts, das nächstgelegene Datum mit sichtbarem Hinweis. **Ortssuche** wird ausgeblendet (Eingabefeld und Aufruf entfernt), sie kommt mit M3 (F1).
**M2-07b — Kacheln, Darstellung, Layer-Manager.** F10 zweistufige Anzeige mit Kacheln aus M2-04; Statistik einmal abfragen, Streckbereich in die Kachelvorlage (Z4), Stretch und Colormap mit „Apply“ (F18); Vorgabe aus der Standard-Visualisierung der Registry; F19 Layer-Manager Basis (ausblenden, Transparenz, Reihenfolge).
**M2-07c — Coverage-Heatmap.** `fill`-Layer mit logarithmischer Skala, Stützstellen aus dem Maximum der Antwort, Legende „Aufnahmen mit Mittelpunkt in der Zelle“; Anzeige von `gekappt`/`stichprobe`; Zeit-Histogramm an der Zeitleiste; reagiert auf Zeitraum und Filter. **Ersatzregel für den Umschaltpunkt:** `numberMatched < 500` greift nur, wenn die Antwort eine geprüfte Gesamtzahl führt. Fehlt sie — bei einer Stichprobe, siehe `adr/0007` — bleibt die Dichteanzeige, und der Hinweis „Stichprobe“ ist sichtbar; Footprints kommen dort nicht automatisch.
**M2-07d — Download.** Einzel-Download aus dem Layer-Manager; vor dem Download Attribution und `terms_notice` sichtbar; Meldung bei Überschreiten des Größendeckels.

**Abnahme je PR:** Lint, Typprüfung und Vitest grün; die jeweilige Funktion lokal mit `docker compose up` und `npm run dev` bedienbar, Anleitung im PR; kein Aufruf von `/api/…` des Prototyps mehr in den geänderten Dateien.

### M2-08 — Onboarding-Checkliste v1, Sentinel-2 vollständig

**Ziel:** Die Checkliste aus `projektuebersicht.md` §5 ist ein Test je Registry-Eintrag, und Sentinel-2 besteht ihn.
**Stufe B.**
**Umfang:**
- Test über alle Registry-Einträge: Punkte 1–8 aus Registry und Collection prüfbar; Punkt 2 heißt „Coverage-Anbieter zugeordnet und Vollständigkeitsprobe greift“; Punkt 9 als End-to-End-Test Suche → Anzeige → Zuschnitt-Download gegen Fixtures (D4).
- Punkt 10: Zeitpunkt des letzten grünen T-D-Smoke-Laufs, gesetzt und im Viewer sichtbar.

**Im Plan-Schritt vorschlagen:** wie der Zeitpunkt aus GitHub Actions in die Plattform kommt, ohne Secret und ohne dass die Cloud-Session live zugreift. Eine Änderung an `.github/workflows/live-smoke.yml` ist dafür erlaubt, wenn der Plan sie begründet.
**Abnahme:** Test grün für Sentinel-2; ein Eintrag mit fehlendem Punkt lässt ihn fallen.

### M2-09a — Zarr-Lesepfad gegen synthetisches Mini-Zarr

**Ziel:** `readers` kann Zarr lesen — Kachel, Statistik und AOI-Zuschnitt. Hängt an keiner Quellenwahl und kann sofort laufen.
**Stufe B.** Aufbau laut `adr/0007`: eigener `zarr.abc.store.Store`, dessen Byte-Reads durch `gateway` laufen, darauf `zarr` → `xarray` → `rio_tiler.io.xarray.XarrayReader`. Python bleibt 3.11, `zarr` 3.1.x (D17).
**Umfang:**
- `readers/zarr_reader.py`, getrennt von `cog.py`; Dispatch über `format` in der Registry.
- Mini-Zarr per Skript im Test erzeugt, keine Binärdatei im Repo: Auflösungsgruppen statt `multiscales`, keine CRS im Store (Georeferenzierung aus `proj:code`), mehrere Variablen, eine Zeitachse, kleine Chunks, dazu ein Fehlerfall mit fehlender Gruppe.
- Kachelroute aus M2-04 für das Format erweitert, ohne Sonderfall im Frontend.

**Abnahme:** Kachel, Statistik und Zuschnitt aus dem synthetischen Zarr; jeder Byte-Read passiert nachweislich `gateway`; unbekannte Variable oder Gruppe ergibt einen definierten Fehler; `lint-imports` grün.

### M2-09b — Zweiter Datensatz im Katalog

**Ziel:** Der zweite Datensatz laut ergänztem `adr/0007` steht in Registry und Katalog und ist über die föderierte Suche erreichbar.
**Stufe B.** Setzt M2-03b voraus; der Datensatz wird erst dort festgelegt.
**Umfang:**
- Registry-Eintrag mit allen Capability-Flags (B10), Lizenzfeldern wie beim ersten Datensatz (D18), `asset_hosts` (D12), Coverage-Feldern, Standard-Visualisierung und den freigegebenen Zoomstufen aus M2-03b.
- Adapter für die Quelle über `gateway`, mit Normalisierung von STAC 1.1.0 auf 1.0.0 (D18).
- **Ausgewiesene Stichprobe** als Coverage-Anbieter (`adr/0004` Option 6), weil die Quelle weder `numberMatched` noch eine Aggregation liefert; Pflichtfeld `stichprobe` und Probe entsprechend.
- Quicklook: löst keiner auf, wird keiner ausgewiesen. Ein Proxy kommt nur, wenn `adr/0006` D14 es wegen fehlender CORS verlangt; dann im Plan-Schritt vorschlagen.

**Abnahme:** Suche, Kachel, Statistik und Zuschnitt gegen die echte Quelle vorgeführt; Fixtures im Test synthetisch; kein Request außerhalb von `gateway`.

### M2-10 — Zweiter Datensatz im Viewer

**Ziel:** Der zweite Datensatz ist im selben Viewer wählbar, mit Kacheln, Coverage, Zuschnitt und Ersatz für den fehlenden Quicklook, und besteht die Checkliste v1.
**Stufe B.** Frontend ohne datensatzspezifische Verzweigung; Unterschiede kommen aus der Registry, auch die freigegebenen Zoomstufen und das Fehlen des Quicklooks.
**Abnahme:** Checkliste v1 grün für beide Datensätze; Abnahmekriterium 1 aus Abschnitt 5 lokal vorführbar.

### M2-11 — Vorlage: Prototyp entfernen

**Ziel:** Entscheidungsvorlage für Otto (ENTSCHEIDUNGEN §3, Stufe B).
**Stufe C**, kein Produktivcode.
**Inhalt:** je Funktion F1–F21 aus dem Inventar, ob und wo sie token-frei läuft; was beim Entfernen wegfällt (`backend/app/`, zugehörige Tests samt `xfail`, `environment.yml`, README Abschnitt 3, das Client-Secret in `config.py`, das die befristete Ausnahme beendet); wohin `decomp.py` geht, damit es als ruhender Operator mit Quad-Pol-Capability und synthetischen Tests erhalten bleibt (`architekturplan.md` 13), obwohl es noch keinen Datensatz dafür gibt.
**Abnahme:** Vorlage mit nummerierten Optionen und Empfehlung.

### M2-12 — M2-Abnahme und README

**Ziel:** Otto kann M2 anhand des PR abnehmen, ohne Code zu lesen.
**Umfang:** Abnahme-Bericht mit Belegen je Kriterium aus Abschnitt 5; README um beide Datensätze, Attribution und Start des Viewers ergänzt; Anleitung zur lokalen Vorführung.

### V-1 — Theme-Umschalter (Viewer-Strang)

**Ziel:** Umschalten zwischen dunkler und heller HUD-Palette (Inventar N1; zweite Palette in `index.css` vorbereitet).
**Umfang:** nur Oberfläche; die Basiskarte bleibt Esri World Imagery (D10). Wahl im Client gespeichert.
**Nicht anfassen:** Basiskarte, Kartenstil.
**Abnahme:** beide Paletten erfüllen die Kontraste laut Inventar Teil 3; Lint und Typprüfung grün.

---

## 5. Abnahme von M2

1. Zwei Datensätze in zwei Formaten (COG und Zarr) im selben Viewer: suchen, Quicklooks, Kacheln, Coverage, Download. Otto prüft lokal.
2. Dieselbe Kachel-URL liefert gegen zwei Instanzen dasselbe Bild; kein Endpunkt nimmt eine freie URL an.
3. Coverage weist `vollstaendig`/`gekappt`/`stichprobe` geprüft aus, für beide Datensätze; Latenz gefiltert unter 1 s, typisch unter 0,5 s (gemessen im PR).
4. Download liefert ZIP mit COG und Hinweisdatei; nichts wird gespeichert (Test).
5. Onboarding-Checkliste v1 als Test grün für beide Datensätze.
6. Importregeln grün mit den Verträgen nach D2; kein ausgehender Request außerhalb von `gateway`.
7. Das Frontend ruft keine Route des Prototyps mehr auf.
8. Pflicht-CI grün (Backend, Frontend, Modulgrenzen, `compose-topology`).

---

## 6. Risiken

| Risiko | Umgang |
|---|---|
| Kein Zarr-Kandidat trägt (Archiv, Dauerhaftigkeit, Lizenz) | `adr/0007` Frage 7; M2a ist davon unabhängig abnehmbar |
| TiTiler-Pakete bringen eigene HTTP-Clients mit | `adr/0006` Frage 1; im Zweifel nur `titiler.core` und eigene Routen |
| Frontend-Umbau sprengt den 400-Zeilen-Richtwert | vier PRs; im Plan-Schritt weiter teilen |
| Neuer Dienst startet in compose nicht (fehlende Variablen, wie `api` in M1-07) | `compose-topology` ist Pflicht-Check; M2-04 nennt den Fall ausdrücklich |
| Junge Bausteine (GeoZarr, titiler-eopf, zarr v3) | Versionen pinnen, Spikes vor Festlegung, synthetische Mini-Fixtures |
| EOPF und Earth Search ändern sich unbemerkt | T-D-Smoke je Quelle; Fixtures bleiben synthetisch |
| Review-Stau bei Otto | höchstens zwei Stufe-B-Sessions gleichzeitig; Stufe A zuerst sichten |
| EOPF-Bestand reicht nur gut zwei Monate zurück und die Quelle führt keinen auflösenden Quicklook | M2-03b misst nach; Fixtures bleiben synthetisch; Alternative steht in der Kandidatenmatrix |
| Native Zarr-Kacheln kosten 3–16 MB | freigegebene Zoomstufen je Datensatz aus der Registry, festgelegt in M2-03b |
| Mehrere PRs ändern `ENTSCHEIDUNGSLOG.md` am Ende | vor dem Fertigmelden `main` in den Branch holen, alle Zeilen erhalten, eigene ans Ende |
