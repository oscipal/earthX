# EarthX

Web-Plattform für Geo- und Satellitendaten. Der frühere BIOMASS-Prototyp
(`backend/app/`) ist entfernt (`docs/adr/0008-prototyp-entfernen.md`); als
Referenz bleibt er über den Tag `prototype-biomass` abrufbar. Die
Zieltopologie unter `backend/earthx/` trägt jetzt die ganze Plattform.

**Planung und Entscheidungen liegen in [`docs/`](docs/)**, verbindlich in
dieser Reihenfolge: [`docs/ENTSCHEIDUNGEN_2026-09-18.md`](docs/ENTSCHEIDUNGEN_2026-09-18.md)
> [`docs/KLAERUNGEN.md`](docs/KLAERUNGEN.md) > Plandokumente
(`architekturplan.md`, `projektplan.md`, `projektuebersicht.md`) >
[`CLAUDE.md`](CLAUDE.md). Der laufende Aufgabenschnitt für den aktuellen
Meilenstein steht unter [`docs/plans/`](docs/plans/), jede Entscheidung als
Zeile in [`docs/ENTSCHEIDUNGSLOG.md`](docs/ENTSCHEIDUNGSLOG.md).

```
earthX/
  backend/
    earthx/            # Zieltopologie: gateway, catalog, adapters, api, …
                        # (Modulgrenzen: docs/architekturplan.md 3.1)
  frontend/             # React + TypeScript + Vite
  docker-compose.yml     # Zieltopologie: api, tiler, worker, harvester, postgres, objectstore
  compose/objectstore/    # Garage-Konfiguration und Bootstrap-Skripte (M3-23, adr/0012)
  docs/                  # Planung, Architektur, ADRs, Entscheidungslog
```

---

## 1. Stand (Meilenstein M3)

M3 trägt **drei token-freie Datensätze** durch denselben Viewer, darunter die
erste Quelle ganz ohne Such-API:

- **Sentinel-2 L2A** (`sentinel-2-c1-l2a`), Earth Search v1 (Element 84),
  Format **COG**, föderierte Suche. Zoomstufen z0–z19, Quicklooks direkt vom
  Asset-Host (kein Proxy, D14).
- **Sentinel-2 L2A (Zarr3)** (`sentinel-2-l2a-zarr3`), EOPF Sentinel Zarr
  Samples Service (EODC), Format **Zarr** (v3), föderierte Suche. Zoomstufen
  z8–z14; die Quelle führt selbst den Status „staging“ (in Registry und
  Oberfläche sichtbar) und keinen Quicklook. Die Abnahme hängt nicht am
  Fortbestand dieser Quelle: Der Zarr-Lesepfad ist zusätzlich gegen ein
  synthetisches Mini-Zarr getestet, ohne jeden Netzzugriff (D24).
- **Copernicus DEM GLO-30** (`cop-dem-glo-30`), direkt aus dem AWS-Open-Data-Bucket,
  Format **COG**, **ohne Such-API**: Die 26 450 Items erzeugt ein Einmal-Befehl
  aus der Kachelliste des Buckets und schreibt sie in den eigenen Katalog
  (pgstac; `adr/0009`). Keine Zeitachse: Der Datensatz wird nie nach Datum
  gefiltert; die Oberfläche nennt den Aufnahmezeitraum.

Was M3 dazu bringt:

- **Suche:** eine gemischte Suche über eigene und föderierte Collections mit
  einer STAC-Antwort und gekennzeichneten Teilergebnissen (`adr/0005`);
  Polygon-AOIs suchen über `intersects`, `ids` wird durchgereicht;
  Datensatz-Auswahl mit Umschalt-Knöpfen (Mehrfachauswahl), Dropdown der
  Treffer je Datensatz, „Load more“ und der Datums-Fallback (±7, ±30, ±90 Tage,
  `architekturplan.md` 5.2).
- **AOI:** Punkt, Rechteck, Polygon; **Upload** von **GeoJSON, KML und
  Shapefile (ZIP)** über das Backend (`POST /aoi/upload`, einheitliche
  Prüfung, nichts wird gespeichert); **Ortssuche** mit Umriss oder Bounding Box
  über Nominatim (`POST /geocode`, standardmäßig aus, siehe unten).
- **Ansicht und Download:** Die Vollauflösung zeigt mit AOI nur den Zuschnitt,
  ohne AOI die ganze Szene; der Download folgt der Ansicht, in **nativer
  Auflösung** (nie automatisch verkleinert, Deckel 500 MB) und mit einer
  **Maske** für die Fläche des AOI-Polygons (die Datendatei behält jedes Pixel
  der Quelle). Jede erzeugte Datei wird vor dem Ausliefern geprüft.
- **Coverage:** Heatmap je Datensatz, für den DEM die Fläche der Kacheln aus den
  eigenen Items; der Weltüberblick fragt den sichtbaren Ausschnitt ab.
- **Topologie:** **Garage** ersetzt MinIO als S3-kompatibler Objektspeicher
  (`adr/0012`); Python 3.12 in Backend, CI und Image; kein Prozess schreibt
  Koordinaten oder Query-Strings ins Log.
- **Architektur:** Das Adapter-Interface ist aus den drei Quellen abgeleitet
  (`adr/0011`, angenommen); der Umbau ist der erste Schritt von M4.

Vollständige Belege je Abnahmekriterium und die Liste der offenen Punkte:
[`docs/plans/m3-15-abnahme.md`](docs/plans/m3-15-abnahme.md) (Aufgabenschnitt:
[`docs/plans/m3-dritte-quelle-und-interface.md`](docs/plans/m3-dritte-quelle-und-interface.md)).
Die Belege für M2 stehen in
[`docs/plans/m2-12-abnahme.md`](docs/plans/m2-12-abnahme.md).

Noch **nicht** enthalten: Ergebnisse im Objektspeicher, Rezept, Operatoren und
Jobs (M4); Exporte über dem synchronen Deckel und gemergte Mosaike ganzer
Szenen (M4, als Job); Health-Status, Harvester-Zeitplan und Hybrid-Suche (M5);
Login und Quotas (M6).

---

## 2. Lokal starten: die neue Topologie

Die Zieltopologie braucht **Docker** (Docker Desktop oder Docker Engine mit
dem `compose`-Plugin) und sonst nichts — kein Python, kein Node, kein Konto
und kein Token. Alles läuft in Containern.

1. **Repo klonen und hineinwechseln**, falls noch nicht geschehen:
   ```bash
   git clone <URL-dieses-Repos>
   cd earthX
   ```
2. **`.env` aus der Vorlage anlegen.** Sie enthält nur lokale Platzhalter,
   keine echten Zugangsdaten:
   ```bash
   cp .env.example .env
   ```
3. **Alles starten:**
   ```bash
   docker compose up
   ```
   Das baut beim ersten Mal die Images (dauert ein paar Minuten) und startet
   dann sechs Dienste: `postgres`, `objectstore` (Garage, M3-23), sowie die
   vier Prozesse `api`, `tiler`, `worker`, `harvester`. Vier weitere Schritte
   laufen einmalig vorweg und beenden sich danach von selbst: `pgstac-migrate`
   (richtet das STAC-Schema in Postgres ein), `catalog-load` (schreibt die
   Sentinel-2-Collection und die Cache-Tabelle hinein), `objectstore-secrets`
   (legt beim ersten Start Zugangsdaten für den Objektspeicher an, seit M4-06
   auch je einen Schlüssel für `worker` und `api` in eigenen Volumes) und
   `objectstore-init` (legt darüber die Schlüssel und den Bucket an und setzt
   die Ablaufregel für `results/`: 7 Tage, offene Multipart-Uploads nach
   1 Tag). Das ist normal — nur die sechs Dienste oben sollen dauerhaft
   laufen. `worker` startet nur, wenn die Ablaufregel am Bucket steht und die
   Tabellen der Warteschlange da sind (Migration `006`, angewandt von
   `catalog-load`; seit M4-08a). Eine
   bestehende Datenbank braucht nach M3-11a (neues Feld
   `earthx:source.item_holding`) einmal einen neuen Lauf von `catalog-load`,
   damit die Collection-Dokumente das Feld tragen; ein normaler
   `docker compose up` erledigt das von selbst.
4. **Warten, bis es bereit ist.** Im Terminal laufen die Logs aller Dienste
   durch. Es ist fertig, wenn keine Fehler mehr erscheinen und `api` seine
   Startzeile zeigt (z. B. `Uvicorn running on http://0.0.0.0:8000`). Im
   Zweifel in einem zweiten Terminal prüfen:
   ```bash
   docker compose ps
   ```
   Alle Dienste sollten `healthy` zeigen.
5. **Zum Beenden:** <kbd>Ctrl+C</kbd> im laufenden Terminal, danach optional
   ```bash
   docker compose down
   ```
   um die Container zu entfernen (die Daten in den Volumes `postgres-data`,
   `objectstore-data`, `objectstore-secrets`, `objectstore-key-jobs` und
   `objectstore-key-api` bleiben dabei erhalten; `docker compose down -v`
   löscht auch sie).
6. **Zugangsdaten des Objektspeichers auslesen** (z. B. für die `aws`-CLI),
   ohne die Topologie neu zu starten:
   ```bash
   docker compose run --rm --no-deps objectstore-secrets show
   ```
   Gibt `S3_ACCESS_KEY`, `S3_SECRET_KEY` und `S3_BUCKET` auf dem eigenen
   Terminal aus, sonst nirgends; dazu die zwei Dienstschlüssel
   (`S3_JOBS_*`, `S3_API_*`). `.env` legt nur den ersten fest, die
   Dienstschlüssel werden immer erzeugt.
7. **Ablaufregel prüfen** (M4-06):
   ```bash
   docker compose logs objectstore-init
   ```
   zeigt `lifecycle rule results-7d set (prefix results/, expire after 7 days,
   abort multipart after 1 day)` — ohne Schlüssel oder Secret.
8. **Worker prüfen** (M4-08a):
   ```bash
   docker compose ps worker
   docker compose logs worker
   ```
   `worker` zeigt `healthy`, das Log `worker started with 2 slots` und keine
   Fehler. Er holt Läufe aus Postgres ab, höchstens 4 gleichzeitig und 2 je
   Quell-Host (die Zeile `earthx_job_limits`), und rechnet jeden in einem
   eigenen Kindprozess. Routen zum Einreihen folgen mit M4-08b.

### Einen STAC-Browser auf den eigenen Katalog richten

Sobald `docker compose up` läuft, ist der Katalog unter
**`http://localhost:8000/stac`** als STAC-API lesbar. Ein "STAC-Browser" ist
nur eine Web-Oberfläche, die diese Adresse anspricht und Collections/Items
grafisch anzeigt — er läuft selbst **nicht** in diesem Repo, sondern separat
(z. B. als eigener Docker-Container):

1. In einem **neuen, zweiten Terminal** (die Topologie aus Schritt 2 muss
   weiterlaufen) den offiziellen STAC-Browser starten. Die Katalog-Adresse
   wird über die Umgebungsvariable `SB_catalogUrl` gesetzt (kein CLI-Flag):

   **Unter Docker Desktop (Windows/macOS)** sieht der Browser-Container den
   Host nicht als `localhost`, sondern als `host.docker.internal`:
   ```bash
   docker run --rm -p 8080:8080 -e SB_catalogUrl="http://host.docker.internal:8000/stac" ghcr.io/radiantearth/stac-browser:latest
   ```

   **Unter Linux** (Docker Engine ohne Docker Desktop) funktioniert
   `localhost` direkt:
   ```bash
   docker run --rm -p 8080:8080 -e SB_catalogUrl="http://localhost:8000/stac" ghcr.io/radiantearth/stac-browser:latest
   ```
2. Im Browser **`http://localhost:8080`** öffnen.
3. Es erscheint die Landing Page des Katalogs mit den Collections:
   **Sentinel-2 L2A** (`sentinel-2-c1-l2a`, COG), **Sentinel-2 L2A
   (Zarr3)** (`sentinel-2-l2a-zarr3`, Zarr) und **Copernicus DEM GLO-30**
   (`cop-dem-glo-30`, COG; Items erst nach dem Schritt unten). Auf eine Collection klicken
   zeigt ihre Beschreibung und Lizenz; **„Items"** öffnet die Suche und
   zeigt Treffer aus der jeweiligen Quelle, durch den eigenen Katalog
   gereicht.
4. Fertig — das ist die Abnahme aus `docs/plans/m1-fundament.md` Abschnitt 5,
   Punkt 1: ein STAC-Browser kann den eigenen Katalog lesen, jetzt für alle
   Datensätze.

Ohne einen separaten Browser lässt sich die API auch direkt ansehen:
`http://localhost:8000/stac` liefert die Landing Page als JSON,
`http://localhost:8000/stac/collections/sentinel-2-c1-l2a/items`,
`.../collections/sentinel-2-l2a-zarr3/items` bzw. `.../collections/cop-dem-glo-30/items`
je eine Trefferliste (JSON in
einem Browser-Tab ist weniger übersichtlich als ein STAC-Browser, aber ohne
einen zweiten Container zu prüfen).

### Den dritten Datensatz laden: Copernicus DEM GLO-30 (M3-11b)

Anders als die beiden Sentinel-2-Einträge hat der DEM keine eigene Such-API
(`adr/0009`): Seine 26 450 Items entstehen einmalig aus der Kachelliste des
AWS-Buckets und werden in den eigenen Katalog geschrieben. `catalog-load`
kennt die Collection selbst schon (Schritt 3 oben), aber ohne diesen Schritt
liefert eine Suche danach `0` Treffer.

1. Die Zieltopologie muss laufen (`docker compose up`).
2. In einem **neuen Terminal**:
   ```bash
   docker compose run --rm materialize cop-dem-glo-30
   ```
   Das läuft einmalig durch (rund 30 Anfragen an den Bucket, keine Bilddaten)
   und endet mit einer Zeile wie `cop-dem-glo-30: loaded (source version …);
   26450 items written, 0 deleted; …`. Ein erneuter Lauf ohne Änderung an der
   Quelle endet stattdessen mit `unchanged` und schreibt nichts.
3. Danach zeigt `http://localhost:8000/stac/collections/cop-dem-glo-30/items`
   Treffer, und der Viewer findet den Datensatz über die Datensatz-Knöpfe in
   der Suchkachel (M3-10).

Absichtlich **kein** Compose-Dienst, der bei `docker compose up` mitläuft
(`profiles: ["materialize"]`): Der Befehl reicht bis zu einer echten externen
Quelle, und weder ein gewöhnlicher lokaler Start noch die CI sollen sie
anfragen.

### Ortssuche lokal einschalten (M3-07a)

Standardmäßig **aus**: `POST /geocode` antwortet `503`, solange
`EARTHX_GEOCODER_URL` in `.env` leer ist — die sichere Voreinstellung, dieselbe
wie bei einer leeren Allowlist. Zum Einschalten in `.env`:

```
EARTHX_GEOCODER_URL=https://nominatim.openstreetmap.org
```

und `docker compose up` neu starten (oder nur `api` neu bauen/starten). Das
ist der öffentliche Nominatim-Dienst, dessen Nutzungsbedingung höchstens eine
Anfrage pro Sekunde über alle Prozesse hinweg erlaubt und eine eigene
Kennung verlangt — beides setzt `earthx.adapters.nominatim` bereits um, ein
zweiter, eigener `EARTHX_GEOCODER_USER_AGENT` ist nur für einen eigenen
Nominatim-Betrieb nötig. Die Bedingung erlaubt außerdem, den Dienst jederzeit
zu wechseln, ohne einen Release zu brauchen — daher die Umgebungsvariable statt
einer festen Adresse im Code. Ein ungültiger Wert (kein `https`, ein
Portname, eine eigene Anfrage) schaltet nur die Ortssuche ab, nicht den
ganzen Prozess (Log-Zeile ohne den Wert selbst).

Test per `curl`, sobald `EARTHX_GEOCODER_URL` gesetzt ist:

```bash
curl -X POST http://localhost:8000/geocode -H 'content-type: application/json' -d '{"q": "Berlin"}'
```

Die erste Anfrage geht an Nominatim (gedrosselt, höchstens 1/s über alle
`api`-Prozesse); dieselbe Anfrage kurz danach kommt aus dem Postgres-Cache
(`from_cache` steht nicht in der Antwort, aber nur die erste braucht die
volle Sekunde). Die Antwort trägt `attribution`/`attribution_url`/`license`
— das Frontend zeigt „© OpenStreetMap contributors" unter den Treffern, und
stammt die AOI eines Downloads aus der Ortssuche, steht der Hinweis samt
Lizenz (ODbL-1.0) in `ATTRIBUTION.txt` des ZIP (M3-07b). Im Viewer gibt es ein
eigenes Feld „Place" im AOI-Abschnitt der Suchkachel.

### AOI-Datei hochladen (M3-06a, M3-06b)

Im AOI-Abschnitt der Suchkachel lässt sich eine Datei wählen: **GeoJSON**
(`.geojson`, `.json`), **KML** (`.kml`) oder **Shapefile** als **ZIP** (`.zip`
mit `.shp`, `.shx`, `.dbf` und **`.prj`**; fehlt die `.prj`, wird abgewiesen,
das Koordinatensystem wird nie geraten). Das Frontend schickt die Datei an
`POST /aoi/upload`; das Backend prüft sie einheitlich und gibt eine Geometrie
in EPSG:4326 zurück. Nichts wird gespeichert, auch nicht vorübergehend auf
der Platte. Grenzen: Upload höchstens 1 MiB, ein ZIP höchstens 10 Einträge
und 20 MiB entpackt, höchstens 20 000 Stützpunkte. Die Fehlermeldung nennt den
Grund auf Englisch. Die zuletzt verwendete AOI merkt sich der Browser.

### Den Viewer starten (Frontend)

Der Viewer ist die eigentliche Bedienoberfläche (Suche, Quicklooks,
Zeitleiste, Kacheln, Coverage-Heatmap, Zuschnitt-Download) und läuft separat
vom Backend, damit er im Entwicklungsmodus schnell neu lädt:

1. Die Zieltopologie aus Schritt 2 muss laufen (`docker compose up`).
2. In einem **neuen Terminal**:
   ```bash
   cd frontend
   npm install   # einmalig
   npm run dev
   ```
3. **`http://localhost:5173`** öffnen. Der Dev-Server leitet `/stac` und
   `/coverage` an `api` (Port 8000) weiter, `/collections` (Kacheln,
   Statistik) an `tiler` (Port 8001) — voreingestellt in
   `frontend/vite.config.ts`, überschreibbar über `VITE_API_PROXY` /
   `VITE_TILER_PROXY`.
4. In der Suchkachel einen oder mehrere Datensätze mit den Umschalt-Knöpfen
   wählen (Mehrfachauswahl, gemischte Suche), eine AOI zeichnen (Punkt,
   Rechteck, Polygon), eine Datei hochladen oder einen Ort suchen, oder einen
   Szenennamen eingeben (M2-17), suchen. Das Dropdown über der Trefferliste
   wählt den Datensatz, dessen Treffer die Karte zeigt; „Load more" lädt
   weitere Seiten. Für `sentinel-2-l2a-zarr3` zeigt die Oberfläche den
   Status „staging" sichtbar an (D23-Auflage); der DEM hat keine Zeitachse
   und erscheint bei jedem Zeitraum.
5. In „Layers" die Coverage-Heatmap einschalten (standardmäßig aus, D26) —
   das ist die einzige Stelle, an der ihre Qualität außerhalb dieser
   Abnahme geprüft werden kann.
6. „Crop & merge to AOI" zeigt von den gewählten Szenen nur den Teil in der
   AOI, „View full selection" die ganzen Szenen. „Download" in der
   Auswahl-Leiste bzw. im Layer-Manager öffnet den Dialog mit Attribution,
   `terms_notice` und der Wahl der Auflösung (Native, 2×, 4×, 10×), vor dem
   eigentlichen Download. Der Download folgt der Ansicht (Zuschnitt: ein ZIP
   mit Datei und Maske je Gruppe, `aoi.geojson` und `ATTRIBUTION.txt`).

Vollständige Bedienung und alle Nachbesserungen aus Ottos Durchsicht:
`docs/plans/m2-format-und-viewer.md`, Aufgaben V-1 bis V-4 und ihre
Nachbesserungsrunden.

### Backend-Abhängigkeiten ändern oder erneuern (M4-00b)

`backend/requirements.txt` und `backend/requirements-dev.txt` sagen, was das
Backend braucht. Installiert wird aber überall — CI, Image, Cloud-Sitzung — aus
den Lock-Dateien `backend/requirements.lock` und
`backend/requirements-dev.lock`: feste Versionen, jede Datei gegen einen Hash
geprüft. Eine neue Veröffentlichung irgendwo im Abhängigkeitsbaum ändert damit
nichts, bis die Lock-Dateien bewusst erneuert werden.

Erzeugt werden sie mit [`uv`](https://pypi.org/project/uv/) (in der
Cloud-Sitzung vorhanden, lokal z. B. `pip install uv`), aus der Repo-Wurzel:

```bash
scripts/lock-backend.sh            # nach einer Änderung an einer .txt-Datei
scripts/lock-backend.sh --upgrade  # alles auf die neuesten erlaubten Versionen
```

Ohne `--upgrade` bleiben alle schon gesperrten Versionen stehen; nur was die
`.txt`-Dateien neu verlangen, kommt dazu. Danach
`pytest backend/tests/test_backend_lock.py` und die ganze Suite. Ein Erneuern
mit `--upgrade` ist ein eigener PR, der die neuen Pakete im Baum nennt. Nach dem
Merge einer neuen Lock-Datei lokal einmal `docker compose build --no-cache`.

### Job-Schnittstelle (seit M4-08b)

`api` (Port 8000) trägt unter `/processing` die Schnittstelle für Rechenaufträge.
Sie folgt der Form von OGC API – Processes und erhebt **keinen Anspruch auf
Konformität** (`/processing/conformance` ist leer): Eingaben werden nur inline
angenommen, nie als Link. Ansehen ohne Auftrag:

```bash
curl http://localhost:8000/processing/                      # Einstieg mit Links
curl http://localhost:8000/processing/processes/recipe      # Prozess mit dem Schema des Auftrags
curl "http://localhost:8000/processing/processes/recipe?dataset=cop-dem-glo-30"
```

Einen Auftrag stellt das Processing-Panel (M4-13); der Rumpf von
`POST /processing/processes/recipe/execution` ist
`{"inputs": {"recipe": <Auftrag>}}`. Die `jobID` ist der Zugang zum Ergebnis:
Sie steht in keinem Log, und ohne Konten gibt es keine Job-Liste.

**Einen echten Job einmal durchspielen (PowerShell, Windows PowerShell 5.1):**
`scripts/try-job.ps1` schickt gegen `http://localhost:8000` eine Reprojektion
des Copernicus DEM über eine kleine, ausgedachte Fläche, wartet auf das Ende,
holt `result.tif`, `mask.tif` und `recipe.json` nach `.\try-job-output\`,
sendet denselben Auftrag noch einmal (muss ein Cache-Treffer sein), verwirft
beide Jobs und sucht in `docker compose logs api` nach den `jobID`s. Jeder
Schritt steht als `OK` oder `FEHLER` da, am Ende eine Zusammenfassung; der
Exit-Code ist `1`, sobald ein Schritt fehlschlägt.

```powershell
docker compose run --rm materialize cop-dem-glo-30   # einmalig, siehe oben
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\try-job.ps1
```

Fläche, Ziel-CRS, Auflösung, Resampling und Zeitlimit stehen als Variablen
oben im Skript. Es braucht laufende Dienste `api` und `worker` und für den
Download den veröffentlichten Port 3900 des Objektspeichers.

### Fehlersuche

- **Port belegt** (`address already in use`): Ein anderer Prozess nutzt
  5432, 8000–8003 oder 3900. Ihn beenden oder in `docker-compose.yml`
  ein anderes Host-Port-Mapping wählen (das Format ist `"host:container"`,
  nur die linke Zahl ändern).
- **Ein Dienst wird nicht `healthy`:** Logs des einzelnen Diensts ansehen,
  z. B. `docker compose logs api`. Ein Neustart eines einzelnen Diensts
  lässt die anderen unberührt: `docker compose restart api`.
- **`catalog-load` ist fehlgeschlagen:** `docker compose logs catalog-load`.
  Meist reicht ein sauberer Neustart mit leeren Volumes:
  `docker compose down -v && docker compose up`.
- **`api` startet nicht, im Log steht „S3_… is not set“ oder „… must be …“
  (seit M4-08b):** `api` signiert die Ergebnis-Links der Job-Schnittstelle und
  braucht dafür die `S3_*`-Angaben des Objektspeichers (in `docker-compose.yml`
  gesetzt, Schlüssel nur lesend). Die Meldung nennt die Variable, nie ihren Wert.
- **`worker` wird nicht `healthy`, im Log steht „worker not started: the
  bucket has no enabled lifecycle rule …“:** Die Regel für `results/` fehlt
  oder wurde geändert (z. B. mit der `aws`-CLI und dem Besitzerschlüssel).
  `docker compose up -d objectstore-init` setzt sie neu, danach
  `docker compose restart worker`.
- **Garage zeigt keine einzelnen Anfragen im Log (seit M4-06):** Absicht —
  diese Zeilen nennen die Schlüssel-ID jeder Anfrage, und `docker compose logs`
  landet in der CI im öffentlichen Log. Zum Nachsehen lokal einmal mit
  geändertem `RUST_LOG` starten (in `docker-compose.yml` beim Dienst
  `objectstore` `garage_api_common=error` weglassen), danach zurücksetzen.
- **Umstieg von MinIO (M3-23):** Ein alter `minio`-Container aus einem
  Checkout vor M3-23 stört einen neuen Start nicht; einmal
  `docker compose up -d --remove-orphans` räumt ihn auf. Das alte Volume
  `minio-data` bleibt dabei bestehen, bis man es selbst löscht
  (`docker volume rm earthx_minio-data`) — es enthält keine Daten, die der
  neue Objektspeicher braucht.
- **`objectstore-secrets` oder `objectstore-init` schlägt fehl mit „already
  exists with a different secret“:** `S3_ACCESS_KEY`/`S3_SECRET_KEY` in
  `.env` weichen von den beim ersten Start erzeugten Werten ab. Entweder die
  Zeilen in `.env` wieder leeren oder das Volume `objectstore-secrets`
  löschen, um mit den `.env`-Werten neu zu beginnen (löscht nur
  Zugangsdaten, keine Objekte).

---

## 3. Attribution

- **Sentinel-2 L2A** (`sentinel-2-c1-l2a`, Earth Search v1 / Registry of Open
  Data on AWS, Format COG) **und Sentinel-2 L2A (Zarr3)**
  (`sentinel-2-l2a-zarr3`, EOPF Sentinel Zarr Samples Service / EODC, Format
  Zarr): beide Copernicus-Sentinel-Daten, derselbe Text. Bei Weitergabe
  **veränderter** Daten: „Contains modified Copernicus Sentinel data [Jahr]",
  bei unveränderten: „Copernicus Sentinel data [Jahr]"
  (`docs/adr/0003-erster-datensatz.md` §11.2, für den zweiten Datensatz
  identisch übernommen, D18/`docs/adr/0007-zweites-format-zarr.md` §12.6).
  Nutzung unterliegt zusätzlich dem
  [Sentinel Data Legal Notice](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice)
  (kein Gewährleistungsversprechen, Anspruchsverzicht des Nutzers). Beide
  Zitierangaben (`cite-as` der jeweiligen Quell-Collection):
  Sentinel-2 L2A [doi.org/10.5270/S2_-742ikth](https://doi.org/10.5270/S2_-742ikth),
  Sentinel-2 L2A (Zarr3) [doi.org/10.5270/S2_-znk9xsj](https://doi.org/10.5270/S2_-znk9xsj).
  Die Zarr3-Quelle führt selbst den Status „staging" und kann ohne
  Vorankündigung verschwinden (adr/0007 §12.11 Punkt 14) — die Abnahme von M2
  hängt davon nicht ab (D24).
- **Copernicus DEM GLO-30** (`cop-dem-glo-30`, direkt aus dem AWS-Open-Data-Bucket,
  Format COG; **M3-11b**, muss vor der ersten Anzeige erst über
  `docker compose run --rm materialize cop-dem-glo-30` geladen werden, siehe
  Abschnitt 2): „© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH
  2014-2018 provided under COPERNICUS by the European Union and ESA; all
  rights reserved"; bei Weitergabe **veränderter** Daten zusätzlich „produced
  using Copernicus WorldDEM-30" (`docs/adr/0003-erster-datensatz.md` §11.1).
  Nutzung unterliegt der
  [Licence for Copernicus DEM instance COP-DEM-GLO-30-F Global 30m Full, Free & Open](https://dataspace.copernicus.eu/sites/default/files/media/files/2025-06/copernicus_contributing_mission_data_access_v2_cop_dem_licenses.pdf)
  (Haftungsausschluss der Copernicus-Trägerorganisationen). Zitierangabe:
  [doi.org/10.5270/ESA-c5d3d65](https://doi.org/10.5270/ESA-c5d3d65).
- **Ortssuche** (`POST /geocode`, nur wenn eingeschaltet): „© OpenStreetMap
  contributors" (Daten unter der Open Database License, ODbL-1.0;
  [openstreetmap.org/copyright](https://www.openstreetmap.org/copyright)),
  über den öffentlichen Nominatim-Dienst. Die Nutzungsbedingungen des Dienstes
  sind vor dem ersten öffentlichen Deployment noch zu klären
  (`docs/ENTSCHEIDUNGSLOG.md`).
- **Basiskarte**: Esri World Imagery — *Esri, Maxar, Earthstar
  Geographics, and the GIS User Community*.

---

## 4. Lizenz

Anwendungscode: **AGPL-3.0-or-later**, siehe [`LICENSE`](./LICENSE). Vor
2026-09-18 veröffentlichte Releases bleiben unter der MIT-Lizenz verfügbar,
unter der sie erschienen sind.

Die AGPL deckt nur diesen Code, **nicht** die Satellitendaten oder
Basiskarten-Ergebnisse Dritter (siehe Abschnitt 3).

Hinweis zu AGPL §13: Wer eine veränderte Version dieser Software betreibt und
Nutzer darauf über ein Netzwerk zugreifen lässt, muss ihnen Zugang zum
zugehörigen Quellcode anbieten.
