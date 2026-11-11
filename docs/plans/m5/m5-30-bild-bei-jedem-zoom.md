# M5-30b — Bild bei jedem Zoom: Plan der Umsetzung

**Status (11.11.2026):** Plan, Stufe B. Umsetzung beginnt mit Teil 1 im selben Draft-PR; Teile mit offener Frage (§6) ruhen bis zur Antwort.
**Aufgabe:** M5-30b, Auftrag von Otto vom 11.11.2026: Umsetzung von `adr/0032` (angenommen 11.11.2026, Antworten §14).
**Grundlagen:** `adr/0032` (vor allem §5.2, §5.3, §6.2, §8.5, §9, §10, §12, §14); `KLAERUNGEN.md` B8, B9, B10, B11; `projektuebersicht.md` §2 Prinzipien 1, 8, 9; `architekturplan.md` 3.1, 6.3, 12.3; `adr/0006` §5; `adr/0015` §7.3; `adr/0024` R6, R7; `plans/m4/m4-17-mosaik-kachel-pfad.md` §5; `plans/m5/m5-18-gateway-ruecksicht.md` §3.2.

Belegstufen wie in `adr/0032`: **P** am Quelltext gelesen (Stand `main` f43c412), **M** in dieser Sitzung gemessen, **A** eigene Ableitung.

**Fest (Auftrag):** Ausgehende Requests nur über `gateway`; Pyramide nur flüchtig (Prinzip 1, Auslegung `adr/0032` §5.3); keine Secrets, keine AOI, keine IDs oder Adressen in Code, Logs, Ausgaben und PRs; `.github/` nur mit Ottos Erlaubnis (dieser Plan braucht keine Änderung dort); Prototyp-Quellen `no-store` (`adr/0024` R7). Ein Draft-PR je Teil; vor „fertig“ `main` holen.

---

## 1. Ziel

Bei keinem angezeigten Datensatz verschwindet das Bild beim Herauszoomen. Zwei Wege (`adr/0032` §0):

- **Szenen-Datensätze** (Sentinel-1, Sentinel-2): die gewählten Szenen über ihre eigenen Übersichten bei jedem Zoom, begrenzt durch ein **Budget je Kachel** statt „12 Szenen ab z8“.
- **Kachel-Datensätze aus vielen Dateien** (swissALTI3D, später BEV; WorldCover, DEM): unter `min_zoom` eine **Übersichtspyramide** als flüchtiges Zwischenprodukt im eigenen Objektspeicher.

Dazu fallen die Grenzen, die nicht aus den Kosten kommen: 64 Items in der Mosaik-URL, 25 Items je Zuschnitt und Job.

---

## 2. Ausgangslage im Code [P]

Wie `adr/0032` §2; die Stellen, die dieser Plan anfasst:

| Was | Stelle |
|---|---|
| Grenzen der Mosaik-Kachel (`MIN_MOSAIC_ZOOM` 8, `MAX_SCENES_PER_TILE` 12, `MAX_MOSAIC_ITEMS` 64) | `backend/earthx/api/mosaic_tiles.py:63-73` |
| Pfad-Abhängigkeit der Mosaik-Kachel, Zoombereich | `backend/earthx/api/tiler.py:795-926` (`_mosaic_zooms`, `mosaic_scenes`) |
| Lesen der Szenen in Portionen von 4, `FirstMethod` | `backend/earthx/access/mosaic_tiles.py:166-198` |
| Spiegel im Frontend (8, 64, 40 Ebenen) | `frontend/src/mosaic.ts:21-23`, `frontend/src/mapLayers.ts:34` |
| Freigabe je Zoom (`_check_zoom_released`, `400`) | `backend/earthx/api/tiler.py:219-268` |
| `ViewerInfo` und sein Docstring zu `min_zoom` | `backend/earthx/catalog/registry.py:700-790` |
| 25 Szenen je Zuschnitt, 25 Items je Auftrag | `backend/earthx/access/download.py:255`, `backend/earthx/api/intake.py:165`, `frontend/src/download.ts:51` |
| Abstand je Host nur im HTTP-Client, nicht für GDAL | `backend/earthx/gateway/policy.py:131-151`, M5-18 §3.2 |
| Fassung der Quelle je Materialisierung | `backend/earthx/catalog/pgstac.py:251` (`last_source_version`), `discovery/materialize.py` |
| Aufräumen stündlich, nur `results/` | `backend/earthx/jobs/cleanup.py`, `backend/earthx/objectstore/results.py:28-33` |
| Image enthält nur `earthx/` und die Registry | `backend/Dockerfile:52-58`; Einmal-Befehle als Compose-Profil wie `materialize` (`docker-compose.yml`) |

Modulgrenzen (`architekturplan.md` 3.1): `discovery` darf `jobs` nicht importieren; `processing` (Kern) nichts von Datenbank, Queue, Objektspeicher; nur `api` darf alles. Das bestimmt, wo das Messskript (§4.1) und der Anstoß des Pyramidenbaus (§4.6, F1) liegen.

---

## 3. Schnitt und Reihenfolge

Jeder Teil ist ein eigener Draft-PR. Der Branch eines Teils geht vom Branch seines Vorgängers ab, und der PR nennt diesen Vorgänger als Basis, damit jeder Diff nur seinen Teil zeigt. Nach dem Merge eines Teils zieht der nächste auf `main` nach.

| # | Teil (`adr/0032` §12) | Inhalt | Umfang [A] | Hängt ab von |
|---|---|---|---|---|
| 1 | **V1** Messskript | dieser Plan; `python -m earthx.api.measure_tiles` im Image, Compose-Profil `measure`; Tests | ≈ 350 Zeilen ohne Plan | — |
| 2 | **V2** Budget je Kachel | Budget statt `MIN_MOSAIC_ZOOM`/`MAX_SCENES_PER_TILE`; Kopf `X-EarthX-Partial`, `no-store` nach Zeitabbruch; Tooltip-Satzteil; Sentinel-1 `min_zoom` 0 | ≈ 300 | 1 (Zahlen) |
| 3 | **V3** Auswahl-ID | Hash der Item-Liste, `POST …/mosaic`, Ablage 7 Tage, `410`; Frontend legt an und neu an; 64 fällt; Rückfall Szene für Szene nur ohne Mosaik, 40 Ebenen nach Lage | ≈ 400, ggf. 3a Backend / 3b Frontend | 2 |
| 4 | **V4** #319 F13 | Browser-Test aus `many-scenes.cjs`, vorher rot; Behebung, falls 3 sie nicht schon bringt | ≈ 100 | 3 |
| 5 | **V5** Registry | `viewer.overview` (Pflicht, ohne Vorgabe), `viewer.overview_resampling`; Prüfung „Bild bei z0“ beim Laden der Registry und als Test; Docstring; Werte je Datensatz | ≈ 250 | 2 |
| 6 | **V8** Zuschnitt und Job | 25 fallen; Zuschnitt nach geschätzter Dauer ≤ 60 s und ≤ 500 MB, sonst „As a job“; Job ohne Item-Grenze außer Schutzgrenze 2 000 | ≈ 250 | — |
| 7 | **V6a** Lesen mit Abstand | `gateway`: Abstand je Host auch für GDAL-Lesen eines Baus (0,25 s, einstellbar); Kern `processing`: Basiskachel aus Dateien | ≈ 350 | 5, **F1–F3** |
| 8 | **V6b** Bau als Job | Hülle in `jobs`: Anstoß, Stufen aus Kindern, Upload, Kopie unveränderter Kacheln; `objectstore` Präfix `overviews/` und Regel 31 Tage; Prüfung der Fassung nach 30 Tagen, Verlängerung; Aufräumen | ≈ 400, ggf. geteilt | 7 |
| 9 | **V7** Kachelroute | z < `min_zoom` aus der Pyramide, `404` mit `X-EarthX-Overview: building`/`failed`; `X-EarthX-Source: overview`; Marke „Overview“; Quellenangabe „modified“; `min_zoom` von swissALTI3D, DEM, WorldCover nach `adr/0032` §9 | ≈ 350 | 8 |
| 10 | **V9** Nachträge | `architekturplan.md` 6.3, 12.3; `projektuebersicht.md` §2; `adr/0006` §5; `adr/0015` §7.3; m4-17 §5 | ≈ 80 | mit 3 und 9 |

**Warum diese Reihenfolge (Abweichung vom Vorschlag im Auftrag):**

- **Messen zuerst (1):** Die Budgets (§6.2 in `adr/0032`) sind Startwerte; der Lauf bei Otto legt sie fest. Das Skript misst den heutigen Lesepfad ohne Zählgrenzen, braucht also nichts aus den späteren Teilen.
- **Szenen vor Pyramide (2, 3, 4):** Sie bringen Sentinel-1 und -2 sofort ein Bild bei jedem Zoom und brauchen keinen Speicher. Teil 2 arbeitet mit den Startwerten 32 Dateien / 4 s; nach Ottos Messung ändert ein kleiner Folge-Commit nur die Konstanten.
- **Registry (5) vor der Pyramide (7–9), nicht danach:** Der Bau muss wissen, welche Datensätze `overview: pyramid` haben und mit welchem Resampling (`overview_resampling`, Pflicht ohne Vorgabe, B10). Die Startprüfung „Bild bei z0“ kommt damit vor der Pyramide; für `pyramid` prüft sie nur, dass Feld und Resampling stehen. `min_zoom` von swissALTI3D, DEM und WorldCover ändert sich erst mit Teil 9, wenn die Route die Pyramide liest, sonst verlören DEM und WorldCover zwischen 5 und 9 ihr Bild unter z7 bzw. z5.
- **Zuschnitt und Job (6)** sind unabhängig; sie stehen vor der Pyramide, weil sie keine offene Frage haben.
- **Pyramide (7–9)** zuletzt: der größte Teil, mit den offenen Fragen F1–F3.

---

## 4. Die Teile im Einzelnen

### 4.1 Teil 1 — Messskript (V1, F11)

**Ort:** `backend/earthx/api/measure_tiles.py`. Es setzt Registry, Adapter, pgstac, `gateway` und den Leser der Mosaik-Kachel zusammen; das darf nur `api` (3.1). Damit liegt es im Image und läuft per `docker compose run`, wie `materialize`.

**Aufruf** (Compose-Profil `measure`, nie bei `docker compose up`):

```
docker compose run --rm measure-tiles <dataset_id> --bbox W,S,E,N [--datetime A/B] [--asset KEY] [--zooms 0-14] [--max-files 64] [--format table|json]
```

**Was es tut:**

1. Items im Rechteck holen: föderiert über `adapters.search_items` (Sentinel-1), materialisiert aus pgstac (`pgstac.search`, swissALTI3D). Höchstens `--max-items` (Vorgabe 500).
2. Nach Überflug gruppieren (`overpass_key`, dieselbe Regel wie Mosaik-Kachel und Mosaik-Job) und die größte Gruppe nehmen; Reihenfolge `mosaic_order`, Adressen über `resolve_asset` und `open_asset_ref`, also durch die Policy von `gateway`.
3. Je Zoomstufe die Kachel über der Mitte des Rechtecks (WebMercatorQuad, 512 px wie die Mosaik-Kachel). Die Szenen, deren Umriss sie berührt, liest **derselbe Leser wie die Mosaik-Kachel** (`MosaicTileReader`, `FirstMethod`, Portionen von 4) mit **derselben GDAL-Konfiguration** (`tile_gdal_options`). Übergangen werden nur die Zählgrenzen der Route (`MIN_MOSAIC_ZOOM`, 12 Szenen, 64 Items), die gemessen werden sollen.
4. **Kalt und warm:** Jede Zoomstufe liest in einem frisch abgezweigten Prozess (`fork`, bevor GDAL eine Datei geöffnet hat), einmal kalt und gleich danach dieselbe Kachel warm. So ist der Zwischenspeicher von GDAL bei jeder Stufe leer; ein CDN vor der Quelle kann warm sein.
5. **Anfragen und Bytes:** gezählt aus den Debug-Zeilen von GDAL (`VSICURL: Downloading a-b`), nur als Zahl; keine Zeile wird gespeichert oder ausgegeben.
6. **Kompression (§8.5 Punkt 3):** Die gelesene Kachel wird im Speicher als GeoTIFF wie eine Pyramidenkachel geschrieben (512², gekachelt, DEFLATE mit Prädiktor); ausgegeben wird ihre Größe.
7. **Schutz der Quelle:** Mehr als `--max-files` Dateien je Kachel liest das Skript nicht, es meldet dann nur die Zahl (`over cap`). Für die Basiskachel z10 von swissALTI3D (§8.5 Punkt 2, ≈ 770 Dateien) ruft Otto es einmal ausdrücklich mit `--zooms 10 --max-files 1000` auf.

**Ausgabe:** eine Markdown-Tabelle (oder JSON) je Zoomstufe: Dateien berührt, gelesen, Status, Zeit kalt/warm, Anfragen und MB kalt/warm, Anteil gefüllter Pixel, Größe als GeoTIFF. Datensatz-ID und Zahl der Items stehen darüber; **keine AOI, keine Adresse, keine Item-ID**, auch nicht in Fehlermeldungen (nur die Art des Fehlers).

**Tests** (`backend/tests/earthx/api/test_measure_tiles.py`, ohne Netz): Argumente (Rechteck verkehrt, außerhalb, Zoombereich, unbekannter Datensatz, Datensatz nur „Katalogeintrag“, ohne `viewer`), Wahl der Kachel je Zoom, Auswahl der berührten Szenen und Deckel, Zählen der GDAL-Zeilen (auch Mehrfachbereiche), Messen mit einem synthetischen lokalen COG über den echten Leser, Ausgabe ohne Adresse, ID und Rechteck; Compose-Dienst nur unter Profil.

### 4.2 Teil 2 — Budget je Kachel (V2, F6, F7)

- `api/mosaic_tiles.py`: `MIN_MOSAIC_ZOOM` und `MAX_SCENES_PER_TILE` entfallen. Neu `TILE_FILE_BUDGET = 32` und `TILE_TIME_BUDGET_S = 4.0` (Konstanten, KE6). `scenes_touching` gibt die berührten Szenen in Mosaik-Reihenfolge zurück und kürzt auf das Dateibudget (bei Schritten: Szenen × Assets ≤ 32); die Zahl der weggelassenen Szenen geht mit.
- `access/mosaic_tiles.py`: Der Leser prüft nach jeder Portion die Zeit; ist sie erschöpft, endet er mit dem bis dahin gefüllten Bild und meldet „Zeit erschöpft“. Was schon gelesen ist, bleibt deterministisch in Mosaik-Reihenfolge.
- Antwortköpfe: `X-EarthX-Partial: <n weggelassen>` bei gekürzter Liste; nach Zeitabbruch zusätzlich `Cache-Control: no-store`. Der Kopf wird für die Karte in CORS freigegeben (`expose_headers`).
- `api/tiler.py`: `_mosaic_zooms` liefert den freigegebenen Bereich ohne Untergrenze 8.
- Frontend: `MIN_MOSAIC_ZOOM` entfällt (`mosaic.ts`); eine Mosaik-Ebene gilt ab `min_zoom` des Datensatzes. Antwortet eine sichtbare Mosaik-Kachel mit `X-EarthX-Partial`, ergänzt der Tooltip des Layers den Satzteil „not all scenes at this zoom“; **keine sichtbare Marke** (Otto, 11.11.2026).
- Registry: Sentinel-1 `min_zoom` 7 → 0 (`adr/0032` §6.4), Kommentar in der YAML.
- Tests: Budget greift (33 Szenen → 32 gelesen, Kopf), Zeitabbruch mit falscher Uhr (Kopf, `no-store`), z0–z7 jetzt `200` statt `400`, Schritte zählen Assets, leere Kachel bleibt `404`; Frontend-Tests für den Tooltip.

### 4.3 Teil 3 — Auswahl-ID (V3, F8, F14)

- **ID:** SHA-256 über die kanonische Form `{dataset, asset(s), items sortiert}` (JSON, sortierte Schlüssel), gekürzt auf 32 Hex-Zeichen. Gleiche Liste, gleiche ID; die ID kann nie ein anderes Bild bedeuten (`adr/0032` §10.2).
- **Ablage:** neue Tabelle `earthx_mosaic_selection` (Migration 016, `catalog/migrations`) mit `id`, `dataset`, `content jsonb`, `expires_at` (7 Tage); Lesen und Schreiben über den Pool des `tiler`; Aufräumen in `jobs/cleanup.py` wie beim Statistik-Cache.
- **Routen:** `POST /collections/{dataset}/mosaic` mit `{items, asset}` → `{id}` (Schutzgrenze 2 000 Items bzw. 128 kB Body, `413`); Kachel und TileJSON unter `/collections/{dataset}/mosaic/{id}/…`. Unbekannte oder abgelaufene ID: `410`. Die alte Form mit `?item=` entfällt (Auslegung A1).
- **Frontend:** legt vor dem Zeichnen an, merkt sich die ID je Vorlage, legt bei `410` dieselbe Liste neu an. `MAX_MOSAIC_SCENES` entfällt; `oversizeNote` entfällt. Der Rückfall „Szene für Szene“ bleibt nur für Gruppen, die kein Mosaik sein können (verschiedene Assets, eine Szene); dort bleiben 40 Ebenen, gewählt nach Lage: zuerst die Szenen im sichtbaren Ausschnitt, neu bei jeder Bewegung.
- Tests: ID stabil gegen Reihenfolge, verschieden bei anderem Asset/Datensatz; `410`; Schutzgrenze; Kachel über ID gleich der Kachel über die alte Liste (Bitgleichheit mit vorhandener Fixture); Frontend: Anlegen, Neu-Anlegen nach `410`, Auswahl nach Lage.

### 4.4 Teil 4 — #319 F13 (V4, F14)

- Browser-Test `frontend/e2e/many-scenes.cjs` erweitert: über 64 Kacheln, Datensatz mit `min_zoom` 14, AOI so, dass die Karte unter z13,5 eingepasst wird. **Er muss auf dem Stand vor Teil 3 rot sein**; ich lasse ihn deshalb zuerst auf dem Branch von Teil 2 laufen und halte das Ergebnis im PR fest. Ist er dort grün, ist die Vermutung aus `adr/0032` §10.4 falsch: dann halte ich Teil 4 an und berichte (kein Raten).
- Nach Teil 3 grün. Playwright läuft nicht in der CI (wie bisher); der Test ist die Prüfung im PR.

### 4.5 Teil 5 — Registry (V5, F9)

- `ViewerInfo.overview: OverviewMode` (`own`, `pyramid`, `scenes`), Pflicht ohne Vorgabe (B10); `overview_resampling: Resampling | None` (`average`, `mode`, `nearest`), Pflicht bei `pyramid`, sonst `None`.
- **Prüfung „Bild bei z0“** beim Laden jedes Eintrags (`ConfigError`, also Startprüfung jedes Prozesses und Test): Jeder Eintrag mit `viewer` hat `overview`; bei `own` und `scenes` ist `min_zoom` 0; bei `pyramid` ist `overview_resampling` gesetzt.
- Werte: Sentinel-1 und Sentinel-2 `scenes`; swissALTI3D, DEM `pyramid`/`average`; WorldCover 2020, 2021 `pyramid`/`mode`. `min_zoom` der Pyramiden-Datensätze bleibt bis Teil 9 (§3).
- Docstring von `ViewerInfo` neu: `min_zoom` heißt „ab hier aus den Originaldateien“, darunter der Weg aus `overview`.
- Frontend liest `overview` nur durch (Typ), es entscheidet nichts damit vor Teil 9.
- Tests: fehlendes Feld, falscher Wert, `own` mit `min_zoom` > 0, `pyramid` ohne Resampling, Resampling bei `scenes`; alle YAML-Einträge laden.

### 4.6 Teil 6 — Zuschnitt und Job (V8, F13)

- `MAX_DOWNLOAD_ITEMS` und `MAX_ORDER_ITEMS` (25) entfallen; neu `MAX_ORDER_ITEMS_GUARD = 2000` (Schutz gegen Missbrauch, keine fachliche Grenze), Spiegel im Frontend.
- Zuschnitt (synchron): Die Schätzung nach `adr/0014` §5.5 zählt die Dateien, die die AOI berühren; über 60 s geschätzter Dauer oder 500 MB antwortet die Route `413` mit dem Hinweis „As a job“ (wie heute über 500 MB).
- Job: Grenzen bleiben Bytes (5 GB), Speicher (1,5 GB) und Laufzeit aus der Schätzung.
- Tests: 26 und 300 Szenen werden angenommen, wenn die Schätzung passt; 2 001 nicht; Dauer über 60 s → `413` mit Hinweis.

### 4.7 Teile 7–9 — Pyramide (V6, V7)

Vorschlag, unter Vorbehalt von F1–F3:

- **Lesen mit Abstand (Teil 7):** GDAL öffnet seine Verbindungen selbst; der Abstand aus M5-18 gilt nur im HTTP-Client. `gateway` bekommt einen Taktgeber je Host für Threads (`HostPacer`), aus `Policy.interval_for(host)`. Der Bau ruft ihn vor jeder Datei; danach zählt er die tatsächlichen Anfragen der Datei (GDAL-Debugzeilen wie im Messskript) und verschiebt den nächsten Start um Anfragen × Abstand. Damit gilt im Mittel höchstens eine Anfrage je 0,25 s und Host (F4). Der Abstand für den Bau ist eine eigene Einstellung, `EARTHX_OVERVIEW_HOST_INTERVAL_S` (Vorgabe 0,25), weil `host_intervals` heute aus dem Code kommt.
- **Kern (Teil 7):** `processing/overview.py`: Basiskachel z = `min_zoom` − 1 aus den Dateien, die sie berühren (gröbste passende Übersicht, Resampling aus der Registry), als Array; Stufe darüber aus vier Kindern. Kein Objektspeicher, keine Datenbank (B9).
- **Hülle (Teil 8):** `jobs/overviews.py`: Zustand je Datensatz und Fassung in einer eigenen Tabelle (F2), Upload nach `overviews/{dataset}/{fassung}/{z}/{x}/{y}.tif` mit Metadatum `checked-at`, Kopie unveränderter Basiskacheln aus der alten Fassung (Hash über ID und `updated` der Items je Kachel), höchstens ein Bau je Host. Lebenszyklusregel 31 Tage auf `overviews/` in `compose/objectstore/bootstrap.py`, Prüfung beim Start des Workers wie bei `results/`. Prototyp-Quellen: 7 Tage, keine Verlängerung, `overviews/proto-*` räumt `catalog-load` mit (`adr/0024` R6).
- **Route (Teil 9):** Kachel z < `min_zoom` mit `overview: pyramid` liest das Objekt über `objectstore` (Leseschlüssel des `tiler`), rechnet Darstellung wie heute; `X-EarthX-Source: overview`; ohne Pyramide `404` mit `X-EarthX-Overview: building|failed`, Karte zeigt die Coverage, der Grund nur im Tooltip. Marke „Overview“ am Layer mit Tooltip (F12). Quellenangabe „modified“. Prototyp: `private, no-store`. TileJSON `minzoom: 0`. Statistik, Zuschnitt, Download, Jobs lesen nie aus der Pyramide.

---

## 5. Auslegungen (gelten, bis Otto widerspricht)

- **A1:** Die Mosaik-URL mit `?item=` entfällt mit Teil 3 ganz, statt neben der ID weiterzuleben. Die Karte baut ihre URLs bei jedem Laden aus der Auswahl neu; Permalinks und Layer-Zustand speichern Items, keine Kachel-URLs [P: `buildMosaicTileTemplate` nur in `api.ts`, `mosaic.ts`]. Zwei Wege wären zwei Grenzen.
- **A2:** Teil 2 nimmt die Startwerte aus `adr/0032` §6.2 (32 Dateien, 4 s, 4 gleichzeitig). Nach Ottos Messlauf ändert ein Commit im PR von Teil 2 (oder ein Folge-PR) nur die Konstanten.
- **A3:** Das Messskript übergeht die Zählgrenzen der Route, nicht ihre Prüfungen von Adressen und Lizenz: Datensätze unter Stufe „Anzeige“ und Adressen außerhalb `asset_hosts` lehnt es ab wie die Route.
- **A4:** Der Browser-Test von Teil 4 läuft wie die anderen unter `frontend/e2e/` nur in der Sitzung, nicht in der CI (keine Änderung an `.github/`).

---

## 6. Fragen an Otto

Teile 1–6 brauchen keine Antwort. **Teile 7–9 ruhen bis zu F1–F3.**

**F1 — Wie wird der Bau nach der Materialisierung angestoßen (`adr/0032` §5.2, „klärt V6“)?**
1. Der Worker sucht in seiner stündlichen Runde (neben `cleanup`) Datensätze mit `overview: pyramid`, deren letzte Fassung in `earthx_materialize_runs` noch keine Pyramide hat, und stellt den Bau ein; dieselbe Runde stellt die Prüfung nach 30 Tagen ein. `materialize` bleibt unverändert (`discovery` darf `jobs` nicht importieren, 3.1). Verzögerung bis zu einer Stunde **(Empfehlung)**
2. `materialize` schreibt nach dem Lauf eine Zeile „Bau gewünscht“ in eine Tabelle, die `jobs` liest (Verzögerung nur bis zum nächsten Abruf der Queue; zweiter Weg in dieselbe Tabelle)
3. Eigener Befehl `docker compose run --rm build-overviews <dataset>` von Hand

**F2 — Wo steht der Zustand einer Pyramide?**
1. Eigene Tabelle `earthx_overview` (Datensatz, Fassung, Status, Basis-Hashes je Kachel, `checked_at`), eigene Job-Art im Worker neben den Rezept-Jobs, ohne Nutzer und ohne Eintrag in der Job-Liste **(Empfehlung)**
2. Als Rezept-Job in `earthx_run`/`earthx_job` mit neuer Rezept-Art (sichtbar in der Job-API, braucht Ausnahmen für „ohne Nutzer“)

**F3 — Abstand je Host beim Bau (F4 = 0,25 s): wie gezählt?**
1. Je tatsächlicher Anfrage von GDAL (gezählt nach jeder Datei, nächster Start um Anfragen × 0,25 s verschoben), einstellbar über `EARTHX_OVERVIEW_HOST_INTERVAL_S` **(Empfehlung)**
2. Je Datei 0,25 s (doppelt so schnell, bei 1–2 Anfragen je Datei bis zu 8 Anfragen je Sekunde)
3. Lesen über den HTTP-Client von `gateway` statt GDAL (ganze Datei, Abstand wie M5-18; rund 8 GB statt 3–7 GB für swissALTI3D)

---

## 7. Prüfanleitung

Je Teil im PR wiederholt; hier zusammengefasst. Alle Befehle aus der Repo-Wurzel.

**Teil 1 (Messung, bei Otto):**

```
docker compose build
docker compose run --rm materialize swissalti3d
docker compose run --rm measure-tiles swissalti3d --bbox <W,S,E,N um eine Stadt> --zooms 6-14
docker compose run --rm measure-tiles swissalti3d --bbox <dasselbe> --zooms 10 --max-files 1000
docker compose run --rm measure-tiles sentinel-1-grd --bbox <W,S,E,N> --datetime <ein Tag mit Überflug> --zooms 0-12
```

Die Tabellen in den PR kopieren; sie enthalten kein Rechteck und keine ID. Erwartet: Zeiten je Stufe, ab der Stufe mit über 64 Dateien `over cap`.

**Teile 2–4 (Karte):** `docker compose up`, Frontend `npm run dev`; Sentinel-1 einen Überflug wählen, bis z3 herauszoomen: das Bild bleibt. swissALTI3D: AOI über rund 10 × 10 km, „Crop and merge to AOI“: das Bild steht ohne Bewegung der Karte ab z13 (vor Teil 9 darunter die Coverage).

**Teil 5:** ein Eintrag ohne `viewer.overview` hält `catalog-load` und `tiler` an, die Meldung nennt Feld und Datensatz.

**Teil 6:** Zuschnitt über 30 Kacheln swissALTI3D läuft; eine AOI über das halbe Land antwortet „As a job“.

**Teile 7–9:** nach F1–F3.

**Immer:** `ruff check backend`, `pytest`, `PYTHONPATH=backend lint-imports --config .importlinter`; im Frontend `npm run lint`, `npx tsc -b --pretty false`, `npm test`.

---

## 8. Umsetzung

### 8.1 Teil 1 — Messskript

- `backend/earthx/api/measure_tiles.py`, Compose-Dienst `measure-tiles` (Profil `measure`), README-Abschnitt „Kachelzeiten messen“; `catalog.pgstac.search_items_in_bbox` für die Items materialisierter Datensätze.
- **Abweichung von §4.1:** Jede Zoomstufe läuft in einem mit `spawn` gestarteten Prozess statt `fork`. Der Kindprozess bekommt die aufgelösten Assets (`ResolvedAsset`) und prüft ihre Adressen selbst noch einmal über die Policy von `gateway`; so bleibt es bei den zwei Stellen, die einen Lesepfad bauen (`test_only_two_places_build_an_asset_path`).
- **Probe in der Sitzung [M]:** Mit 40 echten Items von swissALTI3D (per `curl` geholt, weil der HTTP-Client von `gateway` aus der Sitzung nicht hinauskommt) lief der Lesepfad mit `dtm_2m` durch: z13 berührt 12 Dateien, kalt 1,7 s mit 27 Anfragen und 2,7 MB, warm 0,7 s ohne Anfrage; z10 30 Dateien, kalt 4,0 s. Das sind keine Zahlen für die Budgets (Ort der Sitzung, kleine Stichprobe); die liefert Ottos Lauf.
- **Tests:** `test_measure_tiles.py` (Argumente, Datensatz, Zählen der GDAL-Zeilen, Kachel und Szenen, Lesen über den echten Leser mit synthetischen COGs, Ausgabe ohne Rechteck/Adresse/ID, Compose), `integration/test_pgstac_search_bbox.py`.
