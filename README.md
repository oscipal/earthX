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

## 1. Stand (Meilenstein M2)

M2 trägt **zwei token-freie Datensätze in zwei Formaten** durch denselben
Viewer:

- **Sentinel-2 L2A** (`sentinel-2-c1-l2a`), Earth Search v1 (Element 84),
  Format **COG**. Zoomstufen z0–z19, Quicklooks direkt vom Asset-Host
  (kein Proxy, D14).
- **Sentinel-2 L2A (Zarr3)** (`sentinel-2-l2a-zarr3`), EOPF Sentinel Zarr
  Samples Service (EODC), Format **Zarr** (v3). Zoomstufen z8–z14; die
  Quelle führt selbst den Status „staging" (in Registry und Oberfläche
  sichtbar) und keinen Quicklook — Ersatz ist eine Kachel auf der
  gröbsten freigegebenen Stufe. Die Abnahme von M2 hängt nicht am
  Fortbestand dieser Quelle: der Zarr-Lesepfad ist zusätzlich gegen ein
  synthetisches Mini-Zarr getestet, ohne jeden Netzzugriff (D24).

Für beide Datensätze funktionieren Suche (föderiert, je Datensatz, D8),
Quicklooks bzw. Kachel-Ersatz, dynamische Kacheln über denselben
URL-Aufbau (`dataset`/`item`/`asset`, kein freier `url`-Parameter, Z4),
Coverage (Route `GET /coverage/{dataset_id}`, Heatmap im Frontend
einschaltbar, standardmäßig aus) und der gestreamte AOI-Zuschnitt als ZIP
(COG/Zarr-Ausschnitt plus Hinweisdatei, nichts wird serverseitig
gespeichert). Das Frontend spricht ausschließlich mit `earthx`, keine
Route des früheren Prototyps mehr; die Oberfläche ist durchgehend
englisch (D25).

Vollständige Belege je Abnahmekriterium (`docs/plans/m2-format-und-viewer.md`
Abschnitt 5): [`docs/plans/m2-12-abnahme.md`](docs/plans/m2-12-abnahme.md).
Der Aufgabenschnitt mit allen Einzelaufgaben, Entscheidungen und
Nachbesserungen steht in
[`docs/plans/m2-format-und-viewer.md`](docs/plans/m2-format-und-viewer.md).

Noch **nicht** enthalten (siehe `docs/plans/m2-format-und-viewer.md`
Abschnitt 2 "Abgrenzung"): Ergebnisse im Objektspeicher, Rezept, Operatoren
und Jobs (M4); gemischte Suche über mehrere Quellen (M3); Ortssuche (M3);
AOI-Upload über das Backend; eine verbesserte Coverage-Heatmap (Zählwürfel,
nach M2, D26).

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
   (legt beim ersten Start Zugangsdaten für den Objektspeicher an) und
   `objectstore-init` (legt darüber den S3-Schlüssel und den Bucket an). Das
   ist normal — nur die sechs Dienste oben sollen dauerhaft laufen. Eine
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
   `objectstore-data` und `objectstore-secrets` bleiben dabei erhalten;
   `docker compose down -v` löscht auch sie).
6. **Zugangsdaten des Objektspeichers auslesen** (z. B. für die `aws`-CLI),
   ohne die Topologie neu zu starten:
   ```bash
   docker compose run --rm --no-deps objectstore-secrets show
   ```
   Gibt `S3_ACCESS_KEY`, `S3_SECRET_KEY` und `S3_BUCKET` auf dem eigenen
   Terminal aus, sonst nirgends.

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
3. Es erscheint die Landing Page des Katalogs mit **beiden** Collections:
   **Sentinel-2 L2A** (`sentinel-2-c1-l2a`, COG) und **Sentinel-2 L2A
   (Zarr3)** (`sentinel-2-l2a-zarr3`, Zarr). Auf eine Collection klicken
   zeigt ihre Beschreibung und Lizenz; **„Items"** öffnet die Suche und
   zeigt Treffer aus der jeweiligen Quelle, durch den eigenen Katalog
   gereicht.
4. Fertig — das ist die Abnahme aus `docs/plans/m1-fundament.md` Abschnitt 5,
   Punkt 1: ein STAC-Browser kann den eigenen Katalog lesen, jetzt für beide
   Datensätze.

Ohne einen separaten Browser lässt sich die API auch direkt ansehen:
`http://localhost:8000/stac` liefert die Landing Page als JSON,
`http://localhost:8000/stac/collections/sentinel-2-c1-l2a/items` bzw.
`.../collections/sentinel-2-l2a-zarr3/items` je eine Trefferliste (JSON in
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
   Treffer, und der Viewer findet den Datensatz über den Datensatz-Filter
   (M3-10; bis dahin über die Collection-ID direkt).

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
— das Frontend zeigt sie (M3-07b).

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
4. Oben im Suchmenü zwischen beiden Datensätzen wählen (Kachelpaar
   Sentinel-2/Zarr3), eine AOI zeichnen (Punkt oder Rechteck) oder einen
   Szenennamen eingeben (M2-17), suchen. Für `sentinel-2-l2a-zarr3` zeigt
   die Oberfläche den Status „staging" sichtbar an (D23-Auflage).
5. In „Layers" die Coverage-Heatmap einschalten (standardmäßig aus, D26) —
   das ist die einzige Stelle, an der ihre Qualität außerhalb dieser
   Abnahme geprüft werden kann.
6. Ein ausgewähltes Bild herunterladen: „Download" in der Auswahl-Leiste
   bzw. im Layer-Manager öffnet den Dialog mit Attribution und
   `terms_notice`, vor dem eigentlichen Download.

Vollständige Bedienung und alle Nachbesserungen aus Ottos Durchsicht:
`docs/plans/m2-format-und-viewer.md`, Aufgaben V-1 bis V-4 und ihre
Nachbesserungsrunden.

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
