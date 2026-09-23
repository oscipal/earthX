# M2 — Zweites Format und generalisierter Viewer: Aufgabenschnitt

**Status:** Fassung 4 vom 20.09.2026, nach dem Merge von #42–#49. Neu: englische
Oberfläche (D25), Heatmap zurückgestellt (D26), V-1 um Kartenbedienung und Globus
erweitert (D27), Aufgabe M2-15. Vorher Fassung 3 nach dem Merge von #37–#40. `adr/0006` und
`adr/0007` sind angenommen, `adr/0007` um die Nachmessung §12 ergänzt. Alle
Entscheidungen stehen im `docs/ENTSCHEIDUNGSLOG.md`. Erledigt: M2-00 bis M2-04,
M2-03b und M2-05a; die Pläne für M2-05 und M2-07a liegen im Repo.
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
| D19 | **`earthx:viewer`** ist die neunte Zeile in `architekturplan.md` 5.1 und trägt in M2 nur `group_by`: Item-Eigenschaften in Schlüsselreihenfolge, `properties.` implizit, ohne Vorgabewert. Eine Eigenschaft mit STAC-Zeitpunkt geht als ihr **UTC-Datum** in den Schlüssel ein. Sentinel-2: `["datetime", "grid:code"]`. Referenzumsetzung `catalog/registry.py::group_key`, Fälle in `tests/catalog/test_group_key.py`. Verworfen: ein zweites Feld `group_by_date` | M2-07a, M2-09b |
| D20 | **`DefaultRender`** trägt die Feldnamen der STAC-`render`-Extension; die **Kachel-URL** verlangt `asset` als Pflichtparameter, damit eine Registry-Änderung nicht dasselbe URL-Bild ändert (Z4). `AccessInfo.cors` gilt je Datensatz und steht für Sentinel-2 auf `True`. `pyproject.toml` nennt `fastapi.Depends`/`Path`/`Query` als unveränderliche Aufrufe (B008) | M2-04 (erledigt), M2-07b |
| D21 | **`gateway`:** `httpx` wirft `InvalidURL` vor `check_url`; die Länge wird deshalb vorher selbst gemessen, und nur sie gilt als `UrlTooLong`. Darauf baut die AOI-Verdünnung aus `adr/0004` §3.4 auf | M2-05b, M2-09b |
| D22 | **Histogramm ist monatlich.** Earth Search ignoriert `datetime_frequency_interval`; die Naht gibt keine Auflösung vor, sondern weist die gelieferte aus. Eine feinere Zeitleiste wäre eine eigene Messung und Entscheidung | M2-05b, M2-07c |
| D23 | **Zweiter Datensatz: `sentinel-2-l2a-zarr3`** trotz „staging“ (F8), Zoomstufen **z8–z14** (F9), Auflösungsstufen aus dem **Store**, nicht aus dem Item (F10). Auflagen: Status „staging“ sichtbar in Registry und Viewer; Byte-Ranges im Store zwingend; nie `to_dataarray`/`to_array`; `zipped_product` (1,2 GB) fernhalten | M2-09b, M2-10 |
| D25 | **Die Oberfläche ist durchgehend englisch:** alle sichtbaren Texte, Legenden, Hinweise, Fehlermeldungen; Vorgabesprache des `terms_notice` ist Englisch. Hebt `adr/0004` §5.3 auf. Planungsdokumente bleiben deutsch | M2-06, M2-07c, M2-07d, M2-15, V-1 |
| D26 | **Coverage-Heatmap im Viewer zurückgestellt.** M2-07c ist mit Minimalumfang gemergt (Ausschnitt auf ±180° begrenzt, standardmäßig aus). Die Verbesserung kommt nach M2; Kandidat ist ein täglich aktualisierter Zählwürfel je Datensatz (Zelle z9 × Monat × Wolkenklasse), der M2-05 F3 aufheben würde und vorher gemessen werden muss | M2-07c, §5 |
| D27 | **Karte ohne Drehen und Kippen, Globus umschaltbar.** Maus und Touch verschieben und zoomen nur; die Globusprojektion von MapLibre (ab 5.0) ist reine Darstellung, Backend und Kachel-URLs bleiben unverändert | V-1 |
| D24 | **Die Abnahme von M2 hängt nicht am Fortbestand der Quelle.** Fällt `sentinel-2-l2a-zarr3` weg, fällt die Aufnahme des zweiten Datensatzes, nicht M2; der Lesepfad gegen das synthetische Zarr aus M2-09a genügt | §5, M2-09a, M2-12 |
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
| M2-03b | Nachmessung EOPF nach der Freigabe | C | — | **erledigt** (#40) |
| M2-04 | Kachel-Pfad für Sentinel-2 | B | — | **erledigt** (#39) |
| M2-05a | Coverage-Anbieter (Naht und Adapter) | B | — | **erledigt** (#38) |
| M2-05b | Coverage-Route | B | — | **erledigt** (#43) |
| M2-06 | Download des AOI-Zuschnitts | B | — | **erledigt** (#46) |
| M2-07a | Frontend: API-Client, Suche, Quicklooks, Zeitleiste | B | — | **erledigt** (#44) |
| M2-07b | Frontend: Kacheln, Darstellungssteuerung, Layer-Manager | B | — | **erledigt** (#47) |
| M2-07c | Frontend: Coverage-Heatmap | B | — | **erledigt**, Minimalumfang (#49, D26) |
| M2-07d | Frontend: Download | B | Sonnet (mittel) | — |
| M2-08 | Onboarding-Checkliste v1 als Test, Sentinel-2 vollständig | B | Plan Opus, Umsetzung Sonnet (mittel) | M2-05b, M2-06, M2-07d |
| M2-09a | Zarr-Lesepfad gegen synthetisches Mini-Zarr | B | Plan Opus, Umsetzung Sonnet (hoch) | — |
| M2-09b | Zweiter Datensatz im Katalog | B | Plan Opus, Umsetzung Sonnet (hoch) | M2-03b, M2-04, M2-09a |
| M2-10 | Zweiter Datensatz im Viewer | B | — | **erledigt** (#61) |
| M2-11 | Vorlage: Prototyp entfernen | C | Opus | M2-08 |
| M2-12 | M2-Abnahme und README | A | Sonnet (mittel) | alle |
| M2-13 | Kleinkram: SessionStart-Hook, Live-Smoke-Nachtrag | A | — | **erledigt** (#42) |
| M2-14 | Auflösung des Asset-Hosts zwischenspeichern | B | — | **erledigt** (#48), Frist 5 s |
| M2-15 | Oberfläche durchgehend englisch | A | Sonnet (mittel) | M2-07d |
| V-1 | Kartenbedienung, Globus, Theme (Viewer-Strang) | A | Sonnet (mittel) | M2-15 |
| M2-16 | Bug: Quicklook-Platzierung an Kachelrändern | A | Sonnet (klein) | M2-07a |
| V-2 | Fünf Befunde aus Ottos Durchsicht (Viewer-Strang) | A | Sonnet (klein) | V-1 |
| V-3 | Zwei Befunde aus Ottos Durchsicht (Viewer-Strang) | A | Sonnet (klein) | V-2 |
| V-4 | Fünf Befunde aus Ottos Durchsicht (Viewer-Strang) | A | Sonnet (klein) | V-3 |

**Wellen.** Höchstens zwei Stufe-B-Sessions gleichzeitig, damit die Reviews nicht
stauen (`m1-fundament.md` §6).

1. ~~M2-00 bis M2-03~~ — erledigt
2. ~~M2-03b, M2-04, M2-05a~~ — erledigt
3. ~~M2-05b, M2-06, M2-07a, M2-07b, M2-07c, M2-13, M2-14~~ — erledigt
4. M2-07d, M2-09a
5. M2-15, M2-09b
6. ~~V-1, M2-10~~ — erledigt
7. M2-08
8. M2-11, M2-12
9. M2-16 — Bugfix nebenbei, hängt an nichts außer dem bereits gemergten M2-07a
10. V-2 — Bugfixes nebenbei, hängt an nichts außer dem bereits gemergten V-1
11. V-3 — Bugfixes nebenbei, hängt an nichts außer dem bereits gemergten V-2
12. V-4 — Bugfixes nebenbei, hängt an nichts außer dem bereits gemergten V-3

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

### M2-05b — Coverage-Route

**Ziel:** Die Coverage aus M2-05a ist über `GET /coverage/{dataset_id}` erreichbar.
**Stufe B**, bewusst **klein**: Route, Fehlerabbildung, Tests. M2-05a lag weit über dem Richtwert, hier gilt er wieder.
**Umfang:**
- Route an der Basis-App von `api`, außerhalb von `/stac`; Pflichtfeld mit den Werten `complete`/`truncated`/`sample`.
- Die Antwort führt die Auflösung des Histogramms mit, weil die Quelle sie vorgibt (monatlich, D22).
- **Der Antwortkörper der Quelle gelangt weder in die Antwort der Route noch ins Log.** Gemessen wurde, dass Earth Search bei `400` keine Koordinaten zurückspiegelt; das ist eine Stichprobe, keine Zusage. Ausgeliefert und geloggt werden Statuscode und eigener Text. Kein Eingriff in `gateway`.
- Prüfung der `intersects`-Stützpunkte auf ±90/±180; die Quelle nimmt Unsinn heute still an (dasselbe Muster wie bei der bbox in `adr/0005` §3.5).

**Abnahme:** Tests für Upstream-Fehler, geleerten Cache, unbekannten Datensatz, ungültige Geometrie; kein Test findet Koordinaten aus der Anfrage in Antwort oder Log.

### M2-05a — Coverage-Anbieter (erledigt, #38)

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
- Route in `access`, die für Item(s) und AOI den Zuschnitt über `readers` liest und als ZIP streamt: COG plus Textdatei mit Attribution, `terms_notice` (Vorgabe Englisch, D25), `terms_url` und Zitierangabe aus der Registry.
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
- Tests mit Vitest für reine Logik (URL-Bau für Kacheln und Statistik, Gruppierung, Umschaltpunkt der Coverage, Datums-Fallback), keine Oberflächentests. Die Gruppierung übernimmt die Fälle aus `backend/tests/catalog/test_group_key.py`, damit Frontend und `group_key` nicht auseinanderlaufen; der Schlüssel kommt aus `earthx:viewer` (D19), das Frontend hat dafür keine Vorgabewerte. M2-07a richtet Vitest ein und nimmt es als Schritt in den CI-Job `frontend` auf; diese Änderung an `.github/workflows/ci.yml` ist ausdrücklich erlaubt (F2).

**M2-07a — API-Client, Suche, Quicklooks, Zeitleiste.** F1 AOI-Auswahl, F3 Upload und letzte AOI (im Client, wie bisher), F4 Suche gegen `/stac` mit eigener Seitenmarke, F5 Gruppierung mit Schlüssel aus der Registry (bei Sentinel-2 naheliegend Datum und MGRS-Kachel; im Plan-Schritt bestätigen), F6 Quicklooks direkt vom Asset-Host, ohne Proxy (D14), mit Canvas-Keying wie im Prototyp, F7 Zeitleiste, F8 Ablauf. **Datums-Fallback:** liegt im gewählten Zeitraum nichts, das nächstgelegene Datum mit sichtbarem Hinweis. **Ortssuche** wird ausgeblendet (Eingabefeld und Aufruf entfernt), sie kommt mit M3 (F1).
**M2-07b — Kacheln, Darstellung, Layer-Manager.** F10 zweistufige Anzeige mit Kacheln aus M2-04; Statistik einmal abfragen, Streckbereich in die Kachelvorlage (Z4), Stretch und Colormap mit „Apply“ (F18); Vorgabe aus der Standard-Visualisierung der Registry; F19 Layer-Manager Basis (ausblenden, Transparenz, Reihenfolge).
**M2-07c — Coverage-Heatmap** (erledigt mit Minimalumfang, #49; Verbesserung zurückgestellt, D26). `fill`-Layer mit logarithmischer Skala, Stützstellen aus dem Maximum der Antwort, Legende „Aufnahmen mit Mittelpunkt in der Zelle“; Anzeige von `gekappt`/`stichprobe`; Zeit-Histogramm an der Zeitleiste; reagiert auf Zeitraum und Filter. **Ersatzregel für den Umschaltpunkt:** `numberMatched < 500` greift nur, wenn die Antwort eine geprüfte Gesamtzahl führt. Fehlt sie — bei einer Stichprobe, siehe `adr/0007` — bleibt die Dichteanzeige, und der Hinweis „Stichprobe“ ist sichtbar; Footprints kommen dort nicht automatisch.
**M2-07d — Download.** Alle Texte englisch (D25). Einzel-Download aus dem Layer-Manager; vor dem Download Attribution und `terms_notice` sichtbar; Meldung bei Überschreiten des Größendeckels.

**Abnahme je PR:** Lint, Typprüfung und Vitest grün; die jeweilige Funktion lokal mit `docker compose up` und `npm run dev` bedienbar, Anleitung im PR; kein Aufruf von `/api/…` des Prototyps mehr in den geänderten Dateien.

### M2-08 — Onboarding-Checkliste v1, Sentinel-2 vollständig

**Ziel:** Die Checkliste aus `projektuebersicht.md` §5 ist ein Test je Registry-Eintrag, und Sentinel-2 besteht ihn.
**Stufe B.** Umsetzungsplan: `plans/m2-08-onboarding-checkliste.md` (22.09.2026, wartet auf Freigabe).
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

**Ziel:** `sentinel-2-l2a-zarr3` (D23) steht in Registry und Katalog und ist über die föderierte Suche erreichbar.
**Stufe B.** Grundlage ist `adr/0007` §12, besonders die dreizehn Umsetzungspunkte in §12.11.
**Umfang:**
- Registry-Eintrag mit allen Capability-Flags (B10), Lizenzfeldern wie beim ersten Datensatz (D18), `asset_hosts` (D12), Coverage-Feldern, Standard-Visualisierung, `earthx:viewer`, `AccessInfo.cors = True`, Zoomstufen z8–z14 und sichtbarem Hinweis auf den Status „staging“.
- **Drei harte Auflagen (D23):** der Store beherrscht Byte-Ranges, sonst holt `zarr` je Kachel den 158-MB-Shard; Bänder werden nie über `to_dataarray`/`to_array` gestapelt; das Asset `zipped_product` (1,2 GB) wird ferngehalten, die Hostsperre tut das nicht mehr.
- Auflösungsstufen aus dem Store lesen, nicht aus dem Item (F10).
- Adapter für die Quelle über `gateway`, mit Normalisierung von STAC 1.1.0 auf 1.0.0 (D18).
- **Ausgewiesene Stichprobe** als Coverage-Anbieter (`adr/0004` Option 6), weil die Quelle weder `numberMatched` noch eine Aggregation liefert; Pflichtfeld `stichprobe` und Probe entsprechend.
- Quicklook: Die Quelle führt keinen. Ersatz kommt aus dem Kachelpfad (gemessen 38 kB, 0,6 s).

**Abnahme:** Suche, Kachel, Statistik und Zuschnitt gegen die echte Quelle vorgeführt; Fixtures im Test synthetisch; kein Request außerhalb von `gateway`.

### M2-10 — Zweiter Datensatz im Viewer — **erledigt** (#61)

**Ziel:** Der zweite Datensatz ist im selben Viewer wählbar, mit Kacheln, Coverage, Zuschnitt und Ersatz für den fehlenden Quicklook, und besteht die Checkliste v1.
**Stufe B.** Frontend ohne datensatzspezifische Verzweigung; Unterschiede kommen aus der Registry, auch die freigegebenen Zoomstufen und das Fehlen des Quicklooks.
**Abnahme:** Checkliste v1 grün für beide Datensätze; Abnahmekriterium 1 aus Abschnitt 5 lokal vorführbar.

**Umgesetzt** nach `plans/m2-10-zweiter-datensatz-viewer.md`, freigegeben am
22.09.2026 (F1–F6 je (a), dazu zwei Zusätze): `earthx:viewer` trägt jetzt
`min_zoom`/`max_zoom` (COG `0..19`, zarr3 `8..14`), und die Kachelroute weist
eine Stufe außerhalb mit `400` ab, bevor sie das Item holt. Der fehlende
Quicklook wird im Browse-Modus durch Kacheln auf der gröbsten freigegebenen
Stufe ersetzt. Der Reifegrad steht in der Oberfläche; ein Prüfdatum
bewusst nicht, weil `earthx:health` heute das Aufnahmedatum trägt (Otto,
22.09.2026, nach dem Befund von M2-08 in #62) — es kommt mit M5.
Nebenbefunde aus dem ersten Zuschnitt über das zweite Format: der ZIP-Eintrag
hieß roh nach dem Asset-Schlüssel, und eine AOI neben der Szene ergab bei Zarr
`500` statt `400`. Die Checkliste v1 **als Test** bleibt M2-08 (F5 a).

### M2-11 — Vorlage: Prototyp entfernen

**Ziel:** Entscheidungsvorlage für Otto (ENTSCHEIDUNGEN §3, Stufe B).
**Stufe C**, kein Produktivcode.
**Inhalt:** je Funktion F1–F21 aus dem Inventar, ob und wo sie token-frei läuft; was beim Entfernen wegfällt (`backend/app/`, zugehörige Tests samt `xfail`, `environment.yml`, README Abschnitt 3, das Client-Secret in `config.py`, das die befristete Ausnahme beendet); wohin `decomp.py` geht, damit es als ruhender Operator mit Quad-Pol-Capability und synthetischen Tests erhalten bleibt (`architekturplan.md` 13), obwohl es noch keinen Datensatz dafür gibt.
**Abnahme:** Vorlage mit nummerierten Optionen und Empfehlung.

### M2-12 — M2-Abnahme und README

**Ziel:** Otto kann M2 anhand des PR abnehmen, ohne Code zu lesen.
**Umfang:** Abnahme-Bericht mit Belegen je Kriterium aus Abschnitt 5; README um beide Datensätze, Attribution und Start des Viewers ergänzt; Anleitung zur lokalen Vorführung.

### M2-13 — Kleinkram: SessionStart-Hook und Live-Smoke-Nachtrag

**Ziel:** Zwei Dinge, die in jeder Session neu auffallen, sind einmal festgehalten.
**Stufe A.**
**Umfang:**
- Der SessionStart-Hook installiert `backend/requirements.txt` vollständig (`psycopg`, `stac-fastapi`, seit M2-04 auch `titiler.core`) und migriert pgstac. Mehrere Sessions mussten das nachholen.
- Nachtrag in `adr/0002`: Ein Live-Smoke ist aus einer Cloud-Sitzung nicht von Hand nachfahrbar, weil `gateway` zur geprüften Adresse verbindet und der Sitzungs-Proxy `CONNECT` auf eine IP abweist. In der CI läuft er, dort gibt es keinen Proxy. Latenzen werden im PR deshalb über `curl` belegt. Dazu eine Log-Zeile, damit der Befund nicht ein viertes Mal entdeckt wird.

**Nicht anfassen:** `gateway` — die Adress-Bindung ist eine Sicherheitseigenschaft aus M1-03.
**Abnahme:** Eine frisch gestartete Session kann `pytest` aus der Repo-Wurzel ohne Nachinstallation laufen lassen.

### M2-14 — Auflösung des Asset-Hosts zwischenspeichern

**Ziel:** Der Asset-Host eines Items wird nicht mehr für jede einzelne Kachel neu
aufgelöst. Die Adress-Bindung aus M1-03 bleibt unverändert: `gateway` prüft
weiterhin den Namen und verbindet die geprüfte Adresse; weg fällt allein die
wiederholte Auflösung **desselben** Namens.
**Stufe B**, bewusst **klein**.
**Grundlage:** `plans/m2-format-und-viewer.md` M2-04; Abschnitt „Ladeverhalten" in
#47, Befund 3: `dataset_asset_path` löst bei jeder Kachel- und Statistik-Anfrage
über `gateway/resolver.py::resolve_host` neu auf — synchron, ungecacht und in einer
`async def`-Abhängigkeit, also blockierend auf der Event-Loop statt im Thread-Pool.
Gemessen **17–40 ms je Aufruf**, mit wechselnder Antwort (Round-Robin).

**Umfang:**
- Zwischenspeicher an der Auflösung, nicht am Ergebnis der Prüfung.
- Messung vorher und nachher mit denselben Gleichzeitigkeiten wie in #47
  (1, 12, 40, 80), im PR belegt.
- Tests: Treffer löst nicht erneut auf; abgelaufener Eintrag löst erneut auf; eine
  nicht global routbare Adresse weist den Host auch beim Treffer ab; Fehlschläge
  werden nicht zwischengespeichert; der Speicher wächst nicht unbegrenzt.

**Nicht anfassen:** die Zahl der Uvicorn-Worker (Befund 2 in #47). Das ist eine
Betriebsfrage und gehört nach M5; sie steht als offene Zeile im Entscheidungslog.
Ebenso wenig die Adress-Bindung selbst und `check_url` als Pflichtweg.

#### Plan-Schritt: Vorschlag zu den drei offenen Punkten

**1. Wo der Zwischenspeicher liegt.**

1. **`CachingResolver` in `gateway/resolver.py`**, durch die schon vorhandene
   `resolve`-Naht von `check_url` hereingereicht (deren Docstring sie seit M1-03
   genau dafür nennt: „so tests, and later a caching resolver, can take the place of
   the system resolver"). Eine Instanz je Prozess, im `tiler` an `app.state`, von
   dort in `asset_path` und in den `Gateway`-Client. **Empfehlung.**
2. Memoisierung direkt in `resolve_host`, als Modulglobal. Kürzester Diff, aber
   verborgener Prozesszustand in `gateway` — gegen die Bauart des Moduls, in das
   Policy und Resolver bisher ausnahmslos hereingereicht werden, und schlecht
   prüfbar, weil kein Aufruf ihn sehen oder ersetzen kann.
3. Den fertigen `AssetPath` je (Item, Asset) zwischenspeichern. Am schnellsten und
   **abzulehnen**: das überspränge `check_url` ganz, also Allowlist, Schema- und
   Adressprüfung für jeden Treffer. Genau das soll die Aufgabe nicht tun.

**2. Wie lange er gilt.** Gemessen am echten Asset-Host
(`e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com`) trägt der A-Eintrag
selbst eine **TTL von 5 s** — die Quelle sagt also selbst, wie lange ihre Adressen
gelten. Eine zu lange Frist hebelt nicht die Namensprüfung aus (die läuft bei jedem
Treffer weiter), sondern die **Aktualität der Bindung**: Cloud-Adressen werden
zügig neu vergeben, und eine lange gehaltene Adresse kann einem anderen gehören,
während der Name längst woanders hinzeigt.

1. **5 s, am gemessenen Satz-TTL.** Deckt einen Kachelstapel (ein Vollbild sind
   20–30 Kacheln, die in ein bis drei Sekunden eintreffen) mit einer einzigen
   Auflösung ab und hält keine Adresse länger, als die Quelle sie für gültig
   erklärt. **Empfehlung.**
2. 30 s. Deckt auch mehrere Stapel beim Schwenken, hält die Adresse aber sechsmal
   länger, als die Quelle sagt.
3. 60 s oder mehr. Eine Auflösung je Ansicht — und zwölffach über der Gültigkeit.

Dazu: nur **erfolgreiche** Auflösungen werden gespeichert (ein vorübergehender
Resolver-Fehler darf nicht kleben bleiben) und höchstens 256 Hosts, ältester
zuerst verdrängt, damit der Speicher nicht mit den Namen wächst.

**3. Was er bei wechselnden Adressen tut.** Der Host antwortet Round-Robin, jeder
Aufruf liefert andere Adressen.

1. **Die Antwort als Ganzes halten und bei jedem Treffer erneut durch
   `check_addresses` schicken.** Eine nicht global routbare Adresse weist den Host
   damit auch beim Treffer ab — die Prüfung hängt nicht am Cache, nur die Auflösung
   tut es. Nach Ablauf ersetzt die frische Antwort die alte vollständig; alte und
   neue Adressen werden **nicht** vereinigt, sonst bliebe eine Adresse am Leben, die
   der Name nicht mehr nennt. Das Round-Robin geht innerhalb der Frist verloren, und
   das ist folgenlos: der Client verbindet ohnehin `addresses[0]`, und GDAL bekommt
   die Adressen gar nicht zu sehen (`vsicurl_path` behält den Namen). **Empfehlung.**
2. Innerhalb des Eintrags reihum durchreichen, um die Last zu verteilen. Zusätzlicher
   Zustand für einen Gewinn, den bei 5 s Frist niemand messen kann.

**Abnahme:** Messung vorher/nachher bei 1, 12, 40, 80 gleichzeitigen Kachelanfragen
liegt im PR; ein Kachelstapel löst den Host einmal statt einmal je Kachel auf; die
Tests oben sind grün; `ruff check backend`, `pytest`, `lint-imports` grün.

### M2-15 — Oberfläche durchgehend englisch

**Ziel:** Kein sichtbarer Text in der Oberfläche ist deutsch (D25).
**Stufe A.** Startet nach M2-07d, weil beide dieselben Dateien berühren.
**Umfang:**
- Alle sichtbaren Texte im Frontend: Bedienelemente, Hinweise (Datums-Fallback, Stichprobe), Legenden, Fehlermeldungen, die Meldung zu fehlendem `earthx:viewer`.
- Die Hinweisdatei des Zuschnitt-Downloads aus M2-06; Vorgabesprache des `terms_notice` ist Englisch.
- Alle Fehlertexte, die die API an den Nutzer ausliefert.
- Nachtrag in `adr/0004` §5.3, dass die Vorgabe deutscher Begriffe aufgehoben ist.

**Nicht anfassen:** Planungs- und Entscheidungsdokumente bleiben deutsch; Bezeichner und Feldwerte der API sind bereits englisch.
**Abnahme:** Eine Suche im Frontend-Quelltext nach deutschen Oberflächentexten findet nichts mehr; Lint, Typprüfung, Vitest und `pytest` grün.

### V-1 — Kartenbedienung, Globus und Theme (Viewer-Strang)

**Ziel:** Die Karte ist ruhig zu bedienen, und der Nutzer kann zwischen flacher Karte und Globus sowie zwischen dunkler und heller Oberfläche wählen (D27, D10).
**Stufe A.** Startet nach M2-15, weil beide dieselben Dateien berühren.
**Umfang:**
- **Keine Drehung, kein Kippen:** Maus und Touch verschieben und zoomen nur; Nordausrichtung und Neigung gesperrt.
- **Globus** über die Globusprojektion von MapLibre, umschaltbar gegen die flache Karte. Voraussetzung MapLibre GL JS ab 5.0; ist die Version im Frontend älter, gehört das Update in diese Aufgabe und in den PR-Text. Backend und Kachel-URLs bleiben unverändert.
- Auf dem Globus ansehen und belegen: Quicklooks mit vier Eckpunkten, Kacheln in voller Auflösung, AOI-Werkzeuge, die Begrenzung des Ausschnitts auf ±180° aus M2-07c.
- **Theme-Umschalter** zwischen dunkler und heller HUD-Palette (Inventar N1); die Basiskarte bleibt Esri World Imagery (D10).
- Beide Wahlen im Client gespeichert. Alle Texte englisch (D25).

**Nicht anfassen:** Basiskarte, Backend.
**Abnahme:** Drehen und Kippen sind mit Maus und Touch nicht möglich; der Globus zeigt Quicklooks, Kacheln und AOI lagerichtig; beide Paletten erfüllen die Kontraste laut Inventar Teil 3; Lint, Typprüfung und Vitest grün.

### M2-16 — Bug: Quicklook-Platzierung an Kachelrändern

**Befund:** Bei manchen Sentinel-2-Szenen liegt der Quicklook an der falschen
Stelle, auf der flachen Karte wie auf dem Globus; der heruntergeladene Zuschnitt
derselben Szene liegt richtig. Beispiel: `S2C_T32TNT_20260920T103025_L2A`
(2026-09-20, MGRS 32TNT, Aufnahme 10:37:40Z).

**Ursache:** Das Thumbnail von Earth Search bildet die ganze MGRS-Kachel ab,
einschließlich Nodata-Rand. `quicklookCoords` (M2-07a) leitete die vier
Eckpunkte bislang aus der Datengeometrie des Items ab, die bei Randszenen
kleiner und unregelmäßig ist als die Kachel.

**Stufe A.** Hängt an M2-07a (gemergt), sonst an nichts.
**Umfang:**
- Eckpunkte kommen jetzt aus der Kachel, nicht aus der Datengeometrie. Earth Search setzt für `sentinel-2-c1-l2a` aber kein `proj:bbox` (STAC-Projection-Extension v1.1 lässt es optional; geprüft an der Beispielszene) — die Aufgabe wurde deshalb mit Otto nachgeschärft: die Eckpunkte kommen aus `proj:transform`/`proj:shape` des `visual`-Assets (derselbe Pixelraster, den die Kachel-URL auch sonst als Standard-Rendering nutzt), nicht aus einem wörtlichen `proj:bbox`-Feld. Das CRS kommt aus `proj:code`, ersatzweise `proj:epsg` (dieselbe Reihenfolge wie in `tiler.py::_proj_code`).
- UTM → WGS84 über `proj4` (neue Frontend-Abhängigkeit); auf die UTM-Zonen beschränkt, die Sentinel-2 tatsächlich liefert (`EPSG:326xx`/`327xx`).
- Fehlt CRS oder eine georeferenzierte Asset-Extent, wird kein Quicklook gezeigt statt eines falsch platzierten.
- Toter Code weg, der nur noch von der alten Geometrie-Herleitung gebraucht wurde (`footprintCorners`, `bboxToImageCoords`).

**Nicht anfassen:** Footprint-Anzeige (Coverage/M2-07c) und `pointInFootprint` — die nutzen weiter die Datengeometrie, das ist ein anderes Feature und nicht Teil dieses Befunds.
**Abnahme:** ein Vitest-Fall mit einer Randszene, deren Geometrie deutlich kleiner als die Kachel ist; die Eckpunkte stammen aus der Kachel. Fehlen `proj:bbox`/`proj:code` (in der Praxis: fehlt CRS oder Asset-Extent), wird kein Quicklook gezeigt statt eines falsch platzierten. Lint, Typprüfung, Vitest grün.

### V-2 — Fünf Befunde aus Ottos Durchsicht (Viewer-Strang)

**Ziel:** Fünf kleine Befunde aus Ottos Durchsicht der Oberfläche von V-1 sind behoben. Alle Texte englisch (D25).
**Stufe A.** Hängt an V-1 (gemergt), sonst an nichts.
**Umfang:**
1. Der Theme-Knopf oben rechts beschriftete die Wirkung, nicht den Zustand. Erster Fix ging von der falschen Lesart aus (Zustand statt Wirkung) und wurde von Otto am 23.09.2026 zurückgewiesen: gemeint war das Gegenteil — der Knopf soll das **Wechselziel** nennen, nicht den aktuellen Zustand. Jetzt zeigt der Knopf im dunklen Theme „☀ Light" (Wechsel zu hell) und im hellen „☾ Dark" (Wechsel zu dunkel); dasselbe Muster für den Projektions-Knopf: im flachen Modus „🌐 Globe", im Globus-Modus „🗺 Mercator".
2. Symbole ergänzt: 🌐 für den Globus, 🗺 für die flache Ansicht (umbenannt von „Flat" zu „Mercator", der interne Projektionswert `mercator` bleibt unverändert — er ist eine MapLibre-Konstante), ☰ (drei waagerechte Balken) für „Layers" statt der vorigen Rasterfläche.
3. „Zoom to selection" (`store.ts::zoomToView`) zoomt jetzt zuerst auf die AOI, sonst auf die Bilder in den angepinnten Layern (`store.layers`, per neuem `geoUtils.ts::coordsBbox` auch für Quicklook-Overlays mit vier Eckpunkten), sonst gar nicht; `App.tsx::canZoom` deckt sich damit und hält den Knopf sichtbar deaktiviert, wenn beides fehlt. Vorher zoomte der Knopf auf die Auswahl bzw. den aktiven Zeitschritt — das ist entfallen.
4. Das native Kalendersymbol von `input[type=date]` war im Dunkelmodus unsichtbar (dunkles Symbol auf dunklem Grund). Erster Fix (`color-scheme: dark` + `filter: invert(1)`) reichte laut Otto nicht; `filter` jetzt um `brightness(1.5)` ergänzt, damit das Symbol garantiert reinweiß statt nur hellgrau erscheint, nur im `tech`-Theme.
5. „Add to layers" steht jetzt zusätzlich direkt neben „View full resolution" in der Auswahl-Leiste (`ViewBar.tsx`), nicht mehr nur im Zeitschieber oder erst nach dem Wechsel in die Volltauflösung — die dafür nötige Store-Funktion (`addCurrentToLayers`) unterstützte das Anpinnen eines Quicklooks im Browse-Modus bereits (M2-10), war aber aus der Auswahl-Leiste nicht erreichbar.

**Nicht anfassen:** Backend; die Basiskarte; der interne Projektionswert `mercator`.
**Abnahme:** Lint, Typprüfung und Vitest grün; im PR eine kurze Anleitung zum Ausprobieren der fünf Punkte.

### V-3 — Zwei Befunde aus Ottos Durchsicht (Viewer-Strang)

**Ziel:** Zwei kleine Befunde aus Ottos Durchsicht des Viewers sind behoben, jeweils an der Ursache, nicht nur am Symptom.
**Stufe A.** Hängt an V-2 (gemergt), sonst an nichts.
**Umfang:**
1. Ein Klick auf ein Bild in Vollauflösung (Fokusmodus, M2-07b) löste dessen Szene über den bestehenden Karten-Klick-Handler zwar bereits `toggleSelected` aus, aber `syncMosaic` (`mapLayers.ts`) schreibt im Fokusmodus bedingungslos eine leere `FeatureCollection` auf die Auswahl-Quelle (`SEL_SRC`) statt sie wie im Browse-Modus aus `selectedIds` zu berechnen. Sichtbar wurde davon nur der Nebeneffekt: Jede Zustandsänderung reißt über `clearDynamicMosaic` alle Kachel-Layer ab und baut sie neu auf, was wie ein Neuladen wirkt, ohne dass je eine gelbe Umrandung erscheint. Fix: die Auswahl-Quelle bekommt im Fokusmodus dieselbe gelbe Umrandung wie im Browse-Modus, aus denselben Daten (`selectedIds` gegen die Items der aktiven Gruppe).
2. Die Karte zeigt im Browse-Modus stets nur die Items der aktiven (aufgeklappten) Gruppe (`groups[activeGroupIndex]`, `MapView.tsx`); `ResultsPanel.tsx` klappt aber immer nur eine Gruppe gleichzeitig auf (Akkordeon über `activeGroupIndex`). Ein ausgewählter Quicklook aus einer anderen Gruppe verschwindet deshalb von der Karte, sobald man zu einer anderen Gruppe wechselt — das Zuklappen der Liste reißt ihn von der Karte mit, obwohl er weiter ausgewählt ist. Fix: die an die Karte übergebene Item-Menge ist die aktive Gruppe vereinigt mit allen ausgewählten Items anderer Gruppen (neue Hilfsfunktion in `grouping.ts`), sowohl im reaktiven Effekt als auch beim `style.load`-Wiederaufbau (Theme-Wechsel). Nicht ausgewählte Items einer zugeklappten Gruppe bleiben wie bisher von der Karte verschwunden — das ist gewolltes Verhalten, nur die Auswahl soll überleben.

**Nicht anfassen:** Backend; Footprint-Anzeige (Coverage/M2-07c) und `pointInFootprint` (M2-16); der Karten-Klick-Handler selbst, der die Szene unter dem Cursor schon richtig ermittelt.
**Abnahme:** Vitest-Fälle für beide Befunde (Auswahl-Umrandung im Fokusmodus aus `selectedIds`, ausgewähltes Item einer nicht aktiven Gruppe bleibt Teil der an die Karte übergebenen Items); Lint, Typprüfung und Vitest grün.

### V-4 — Fünf Befunde aus Ottos Durchsicht (Viewer-Strang)

**Ziel:** Fünf kleine Befunde aus Ottos Durchsicht des Viewers sind behoben. Alle Texte englisch (D25).
**Stufe A.** Hängt an V-3 (gemergt), sonst an nichts.
**Umfang:**
1. Ein ausgewählter Quicklook lässt sich herunterladen: die Originaldaten über die bestehende Zuschnitt-Route (`POST /collections/{dataset}/download`, M2-06), nicht das Vorschaubild. Neuer „Download"-Knopf in `ViewBar.tsx` neben „View full resolution"/„Add to layers", ohne vorher in die Volltauflösung zu wechseln; öffnet denselben `DownloadDialog` wie beim Layer-Download, mit Attribution und `terms_notice`. Der Asset kommt aus der Standard-Visualisierung der Registry (`earthx:default_render`), derselbe, den `enterFocus`/`quicklookPlan` auch sonst verwenden.
2. Der Szenenname lässt sich kopieren, mit dem üblichen Kopiersymbol neben der Szenen-ID in `ResultsPanel.tsx`, per `navigator.clipboard`.
3. Die Trefferliste gruppiert nach Tag und Überflug (`s2:datatake_id`), nicht mehr nach Tag und MGRS-Kachel — reine Darstellung (Log-Eintrag 2026-09-22): `grouping.ts::displayGroupBy` bevorzugt `["datetime", "s2:datatake_id"]`, wenn jedes Item im aktuellen Suchergebnis die Eigenschaft trägt, sonst bleibt es beim registrierten `group_by` (Tag + `grid:code`). D19 und D11 bleiben unberührt: `buildGroups` führt weiterhin jede Szene einzeln mit eigenem Quicklook und eigener Kachel-URL, es entsteht kein Mosaik.
4. Der Hintergrund hinter dem Globus (`mapStyles.ts`) war weiß, jetzt schwarz: MapLibres `sky`-Vorgaben (`sky-color`/`horizon-color`/`fog-color`, per Default hell) sind auf die Farbe der `background`-Ebene (`#04070a`) gesetzt, `atmosphere-blend: 0`.
5. Die beiden Datumsfelder (`ControlPanel.tsx`, `.date-row`) treffen jetzt dieselben zwei Spalten wie die Kachelpaare darüber (Point/Rectangle, Upload/Last AOI, Sentinel-2/Zarr3): `date-row` ist ein Grid mit `repeat(2, 1fr)` und 6px Abstand statt einer Flex-Zeile mit dem Pfeil als drittem Element; der Pfeil liegt jetzt als Overlay über der Lücke.

**Nicht anfassen:** Backend; die Registry (`earthx:viewer.group_by`, D19 bleibt unverändert); Kachel-Pfad und Mosaik-Verbot (D11).
**Abnahme:** Vitest-Fälle für `displayGroupBy` (bevorzugt Datatake, Fallback bei fehlender Eigenschaft, leeres Ergebnis); Lint, Typprüfung und Vitest grün; im PR eine kurze Anleitung zum Ausprobieren der fünf Punkte.

**Nachbesserungen (23.09.2026, Ottos Durchsicht des offenen PR):** vier weitere kleine Befunde, noch vor dem Merge in denselben PR eingearbeitet:
1. Die ESRI-Attribution (Info-Knopf unten rechts) war im Dunkelmodus unlesbar: MapLibres `.maplibregl-compact` setzt `color: #000`/`background: #fff` in derselben Selektor-Spezifität wie unsere Regel und gewinnt je nach Reihenfolge — jetzt für `.maplibregl-ctrl-attrib` samt `.maplibregl-compact`/`.maplibregl-compact-show` explizit auf Weiß gesetzt.
2. Der Kalender-Klick im Dunkelmodus ging ins Leere: `padding-right` verschiebt den unsichtbaren nativen `::-webkit-calendar-picker-indicator` nach innen, während unser gezeichnetes Symbol an einer festen Stelle sitzt — beide laufen auseinander. Ersetzt durch einen echten, transparenten Knopf über dem Symbol, der `input.showPicker()` aufruft (`ControlPanel.tsx::DateField`).
3. Die Trefferliste war frei verschiebbar (`Draggable`) statt wie das Suchmenü fest an einer Seite und ein-/ausklappbar. Jetzt rechts angedockt (`overlay right results-dock`), mit demselben Auf-/Zuklapp-Muster wie `panel-dock` links, nur horizontal gespiegelt.
4. Der Layer-Manager sprang beim Schließen und Wiederöffnen auf seine ursprüngliche Position zurück: `if (!open) return null` hat `Draggable` und damit seinen Verschiebe-Zustand jedes Mal komplett abgebaut. `Draggable` bleibt jetzt montiert und wird nur noch per CSS (`display: none`) versteckt.

**Nachbesserungen, Runde 2 (23.09.2026, Ottos Durchsicht des offenen PR):** fünf weitere Befunde, in Commits mit dem Kürzel „V-6" (an nichts als Runde 1 hängend, kein eigener Plan-Eintrag):
1. Der Globus-Hintergrund war trotz Runde 1 weiterhin weiß: MapLibre leert den WebGL-Canvas jeden Frame transparent, bevor der Sky-Pass zeichnet, und deckt offenbar nicht jeden Zustand vollständig ab. `body { background: #04070a }` (`index.css`) ist jetzt die tatsächliche Garantie, unabhängig vom Sky-Shader; die `sky`-Farben in `mapStyles.ts` bleiben als Ergänzung, der Kommentar dort hält die Fundstelle fest (`drawSky` vs. das separate, an `atmosphere-blend` hängende Halo).
2. Die Datumsfelder waren zu breit, dem Pfeil in der Mitte blieb kein Platz: `date-row`s mittlere Spalte ist jetzt eine echte (`auto`-große) Grid-Spur statt eines Overlays ohne eigenen Platz; die Felder sind dadurch etwas schmäler als die Kachelpaare darüber, die Zeile insgesamt gleich breit.
3. Das Kopiersymbol („⧉") wirkte unpassend. Ersetzt durch dasselbe Icon wie in Claudes eigener Oberfläche (zwei überlappende, abgerundete Rechtecke), als Inline-SVG mit `currentColor` (`ResultsPanel.tsx::CopyIcon`).
4. Der Download war im Layer-Manager nur für Layer verfügbar, die zuvor in Volltauflösung angesehen wurden (`store.downloaded` gefüllt) — ein nur als Quicklook angepinnter Layer zeigte trotz Tooltip „Download the AOI crop for this layer" keinen Download-Knopf. `LayerRestore` trägt jetzt `itemIds` (die gepinnten Szenen zum Zeitpunkt des Anpinnens, unabhängig von den aktuellen Suchergebnissen); `downloadRequestFor` weicht ohne Volltauflösung auf das Standard-Render-Asset der Registry aus (`earthx:default_render`), wie schon bei `downloadRequestForSelection` (Punkt 1 oben).
5. Eine aufgeklappte Gruppe in der Trefferliste ließ sich nicht schließen, ohne eine andere zu öffnen (dieselbe Variable `activeGroupIndex` trieb sowohl den Akkordeon-Zustand als auch Karte/Zeitschieber). `ResultsPanel.tsx` hält den aufgeklappten Index jetzt als eigenen lokalen Zustand, synchronisiert per Effekt mit `activeGroupIndex`; ein manuelles Einklappen ändert nur diesen lokalen Zustand, Karte und Zeitschieber bleiben unverändert.

**Nachbesserungen, Runde 3 (23.09.2026, Ottos Durchsicht des offenen PR):** drei weitere kleine Befunde, Kürzel „V-7":
1. Der ESRI-Info-Knopf (Attribution) unten rechts stand standardmäßig aufgeklappt: `compact: true` macht die Attribution nur einklappbar, MapLibre startet sie aber trotzdem offen (`maplibregl-compact-show`/`open`) und klappt erst beim ersten Verschieben der Karte ein (eigener Listener auf `drag`). Jetzt direkt nach dem Erzeugen der Karte eingeklappt (`MapView.tsx`), ohne auf diese erste Bewegung zu warten.
2. Der Layer-Manager saß standardmäßig fest bei `left: 420px` (auf die Breite des Suchmenüs abgestimmt). Jetzt `left: 16px`, wie das Suchmenü selbst — bleibt frei verschiebbar, das ist nur der Startpunkt.
3. Abgeschnittene Szenennamen: Der Layer-Namensknopf im Layer-Manager trug als `title` nur einen festen Bedienhinweis, nie den (oft abgeschnittenen) Namen selbst — jetzt beides. Die Gruppen-Überschrift in der Trefferliste (kann bei langen Datatake-IDs ebenfalls abschneiden) hat jetzt denselben Hover-Titel; die einzelne Szenen-ID hatte ihn schon.

**Nachbesserungen, Runde 4 (23.09.2026, Otto per Screenshot), Kürzel „V-8":** zwei Befunde, einer davon eine Korrektur von Runde 3 Punkt 2.
1. Die Datumsfelder liefen trotz Runde-2-Korrektur immer noch über den Panelrand hinaus, das Kalendersymbol des rechten Felds wurde am Rand abgeschnitten (Screenshot). Ursache: ein bloßes `1fr` in einem CSS-Grid trägt ein implizites `min-width: auto` und schrumpft nie unter die Content-Mindestbreite — die durch das reservierte Icon-Padding des Datumsfelds größer war als der tatsächlich verfügbare Platz, also lief die Zeile über. Behoben mit `minmax(0, 1fr)` für die beiden Datumsspalten plus `min-width: 0` auf Feld und Input.
2. Der Layer-Manager sollte, wenn die Steuerungstafel links offen ist, rechts daneben ausweichen (nicht darunter liegen) und beim Einklappen der Tafel wieder an den linken Rand zurückwandern — Runde 3 Punkt 2 hatte ihn nur pauschal auf `left: 16px` fest gesetzt, ohne auf `panelCollapsed` zu reagieren. Jetzt `overlay layermgr` in `App.tsx` mit einer `controls-open`-Klasse aus demselben `panelCollapsed`, den auch die Steuerungstafel selbst benutzt; `left: 420px` (deckt Suchmenübreite plus Toggle-Pfeil ab) bei offener Tafel, sonst `left: 16px`, mit Übergang.

**Nachbesserung, Runde 5 (23.09.2026), Kürzel „V-9":** Der Play-Knopf der Zeitleiste lief in die falsche Richtung. `groups` ist neueste-zuerst, die Zeitleiste zeigt links die älteste, rechts die neueste Szene (`sliderValue = groups.length - 1 - activeGroupIndex`); `TimeSlider.tsx`s Intervall zählte `activeGroupIndex` aber **hoch**, was den Schieberegler visuell von rechts nach links laufen ließ (neueste → älteste), entgegen seiner eigenen Beschriftung. Jetzt wird `activeGroupIndex` heruntergezählt (mit Wraparound), läuft also links nach rechts, ältere zu neuere Szenen, ab der aktuellen Position weiter. Der Wraparound liefert nebenbei den zweiten Wunsch: von der Standardposition ganz rechts (neueste Szene) aus beginnt der erste Schritt bei der ältesten (ganz links), ohne dass man den Regler vorher manuell zurücksetzen muss.

**Nachbesserung, Runde 6 (23.09.2026), Kürzel „V-10":** Zwei Wünsche zum Layer-Manager, der bisherige Ansatz aus Runde 4 (`.controls-open`-CSS-Klasse) konnte keinen von beiden erfüllen, weil er rein an `panelCollapsed` hing statt an tatsächlicher Überlappung: (1) er soll nur ausweichen, wenn er der Steuerungstafel wirklich im Weg ist, nicht bei jedem Öffnen der Tafel unabhängig von echter Kollision; (2) er soll nie ganz oder teilweise vom Bildschirm verschwinden. Der `.controls-open`-Mechanismus in `App.tsx`/`index.css` ist entfernt; `Draggable.tsx` bekommt stattdessen zwei generische, opt-in Fähigkeiten:
- `avoidSelector` misst das eigene (unverschobene) Anker-Rechteck gegen das per Selektor benannte Element und weicht nur bei echter Überlappung aus (`getBoundingClientRect`-Kollisionstest), begrenzt durch den Bildschirmrand. Eine manuelle Verschiebung durch den Nutzer gewinnt immer — die automatische Ausweichung greift nur an der unberührten Ankerposition. Neu geprüft wird bei `transitionend` (`transform`) des Ausweich-Ziels und über ein `recalcTrigger`-Prop, das der Aufrufer setzt — nötig, weil das Öffnen des Layer-Managers selbst sein eigenes (am Inhalt bemessenes) Anker-Rechteck von leer auf echte Größe ändert, wofür es kein DOM-Ereignis gibt. `LayerManager.tsx` übergibt `avoidSelector=".panel-dock"` und `recalcTrigger` aus `open`+`panelCollapsed`.
- Eine bedingungslose Bildschirmrand-Klemme (`SCREEN_MARGIN`) für sowohl die automatische Ausweichung als auch jede manuelle Verschiebung — beim Ziehen, beim Öffnen und nach einer Fenstergrößenänderung.

Mit Playwright gegen den lokalen Dev-Server durchgespielt (acht Szenarien: Ausweichen bei echter Überlappung, Rückkehr an den Rand ohne Überlappung, erneutes Ausweichen, manuelles Verschieben bleibt in beide Toggle-Richtungen unangetastet, Klemmen an allen vier Bildschirmrändern).

**Nachbesserung, Runde 7 (23.09.2026), Kürzel „V-11":** Quicklooks blieben auf der Karte sichtbar, obwohl in der Trefferliste keine Gruppe mehr aufgeklappt war. Ursache: `expandedGroupIndex` (V-6, welche Sektion in der Liste offen ist) lebte nur als lokaler State in `ResultsPanel.tsx`; `MapView.tsx` kannte ihn nicht und las weiterhin `activeGroupIndex`, das ein manuelles Einklappen absichtlich unangetastet lässt (genau das war der Witz von V-6). `expandedGroupIndex` zieht jetzt in den Store um, wo beide Komponenten ihn lesen können:
- `setActiveGroupIndex` (Zeitschieber, „Play", Klick auf eine Szene, Auswahl eines angepinnten Layers) hält `expandedGroupIndex` weiterhin synchron mit `activeGroupIndex`, wie zuvor implizit über den `useEffect` in `ResultsPanel.tsx`.
- Neue Aktion `toggleResultsGroup` ist der einzige Pfad, der nur `expandedGroupIndex` ändert (auf `null` beim Einklappen der offenen Gruppe) und `activeGroupIndex` unberührt lässt.
- `grouping.ts::itemsForMap` nimmt jetzt `number | null` für den zweiten Parameter; `null` bedeutet „keine Gruppe aktiv", liefert also nur die ausgewählten Items (wie zuvor schon ein außerhalb liegender Index).
- `MapView.tsx` wählt je Aufrufstelle zwischen `activeGroupIndex` und `expandedGroupIndex`: im Fokusmodus ist die Trefferliste gar nicht sichtbar (App.tsx tauscht sie gegen `ViewerControls`), dort zählt weiterhin die in Volltauflösung angesehene Szene.

Vitest-Fälle für `itemsForMap(_, null, _)` und `toggleResultsGroup` (Einklappen ohne `activeGroupIndex` zu bewegen, erneutes Aufklappen, Resynchronisierung durch `setActiveGroupIndex` nach einem manuellen Einklappen).

---

## 5. Abnahme von M2

1. Der Viewer trägt zwei Formate (COG und Zarr): suchen, Quicklooks, Kacheln, Download. Die Coverage-Heatmap ist vorhanden und einschaltbar; ihre Qualität ist nicht Teil der Abnahme (D26). Otto prüft lokal. Für Zarr genügt der Lesepfad gegen das synthetische Zarr aus M2-09a, falls die Quelle des zweiten Datensatzes wegfällt (D24).
2. Dieselbe Kachel-URL liefert gegen zwei Instanzen dasselbe Bild; kein Endpunkt nimmt eine freie URL an.
3. Coverage weist `complete`/`truncated`/`sample` geprüft aus; Latenz gefiltert unter 1 s, typisch unter 0,5 s. Belegt über `curl`-Messungen im PR, weil ein Live-Test aus einer Cloud-Sitzung nicht durchkommt (M2-13).
4. Download liefert ZIP mit COG und Hinweisdatei; nichts wird gespeichert (Test).
5. Onboarding-Checkliste v1 als Test grün für jeden aufgenommenen Datensatz.
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
| Die Collection nennt sich selbst „Zarr3 staging“, Bestand gut zwei Monate, nur 34°–72° N, kein Quicklook | Status sichtbar in Registry und Viewer; Ersatz-Quicklook aus dem Kachelpfad; die Abnahme hängt nicht an der Quelle (D24) |
| Zarr-Kacheln kosten 0,9–6,3 MB je Band (gemessen, §12) | Zoomstufen z8–z14 aus der Registry; Byte-Ranges und kein `to_dataarray` als harte Auflagen (D23) |
| Mehrere PRs ändern `ENTSCHEIDUNGSLOG.md` am Ende | vor dem Fertigmelden `main` in den Branch holen, alle Zeilen erhalten, eigene ans Ende |
