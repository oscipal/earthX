# EarthX

Web-Plattform für Geo- und Satellitendaten. Die Zieltopologie steht in diesem
Repo neben dem BIOMASS-Prototyp (`backend/app/` + `frontend/`) und wächst
nach dem Strangler-Muster: Neues entsteht unter `backend/earthx/`, der
Prototyp bleibt so lange lauffähig, bis seine Funktionen token-frei
nachgebaut sind und Otto seine Entfernung entscheidet.

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
    app/                # BIOMASS-Prototyp — siehe Abschnitt "Prototyp" unten
  frontend/             # React + TypeScript + Vite (bedient bisher den Prototyp)
  docker-compose.yml     # Zieltopologie: api, tiler, worker, harvester, postgres, minio
  docs/                  # Planung, Architektur, ADRs, Entscheidungslog
```

---

## 1. Stand (Meilenstein M1)

M1 trägt **Sentinel-2 L2A** (Earth Search v1, Collection `sentinel-2-c1-l2a`)
token-frei durch die neue Architektur: eigenes `pgstac` für die Collection,
Items föderiert per Adapter, jeder ausgehende Request über das `gateway`,
nach außen eine lesbare STAC-API. Details und Abnahmebelege je Kriterium:
siehe der PR, der diesen Stand einführt, und
[`docs/plans/m1-fundament.md`](docs/plans/m1-fundament.md) Abschnitt 5.

Noch **nicht** enthalten (siehe `docs/plans/m1-fundament.md` Abschnitt 2):
Kacheln, Quicklooks, Zuschnitt/Stitching, Zarr/EOPF, Frontend auf die neue
API umgestellt, Coverage-Heatmap gebaut (nur als ADR vorbereitet).

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
   dann sechs Dienste: `postgres`, `minio`, sowie die vier Prozesse `api`,
   `tiler`, `worker`, `harvester`. Zwei weitere Schritte laufen einmalig vorweg
   und beenden sich danach von selbst: `pgstac-migrate` (richtet das
   STAC-Schema in Postgres ein) und `catalog-load` (schreibt die
   Sentinel-2-Collection und die Cache-Tabelle hinein). Das ist normal — nur
   die sechs Dienste oben sollen dauerhaft laufen.
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
   um die Container zu entfernen (die Daten in den Volumes `postgres-data`
   und `minio-data` bleiben dabei erhalten; `docker compose down -v` löscht
   auch sie).

### Einen STAC-Browser auf den eigenen Katalog richten

Sobald `docker compose up` läuft, ist der Katalog unter
**`http://localhost:8000/stac`** als STAC-API lesbar. Ein "STAC-Browser" ist
nur eine Web-Oberfläche, die diese Adresse anspricht und Collections/Items
grafisch anzeigt — er läuft selbst **nicht** in diesem Repo, sondern separat
(z. B. als eigener Docker-Container):

1. In einem **neuen, zweiten Terminal** (die Topologie aus Schritt 2 muss
   weiterlaufen) den offiziellen STAC-Browser starten:
   ```bash
   docker run --rm -p 8080:8080 ghcr.io/radiantearth/stac-browser \
     --api http://localhost:8000/stac
   ```
   Läuft der Browser-Container selbst nicht auf demselben Rechner wie
   Docker Desktop unter macOS/Windows, `localhost` durch die tatsächlich
   erreichbare Adresse des `api`-Dienstes ersetzen; unter Linux
   funktioniert `localhost` direkt.
2. Im Browser **`http://localhost:8080`** öffnen.
3. Es erscheint die Landing Page des Katalogs mit der Collection
   **Sentinel-2 L2A** (`sentinel-2-c1-l2a`). Auf die Collection klicken zeigt
   ihre Beschreibung und Lizenz; **„Items"** öffnet die Suche und zeigt
   Treffer aus Earth Search, durch den eigenen Katalog gereicht.
4. Fertig — das ist die Abnahme aus `docs/plans/m1-fundament.md` Abschnitt 5,
   Punkt 1: ein STAC-Browser kann den eigenen Katalog lesen.

Ohne einen separaten Browser lässt sich die API auch direkt ansehen:
`http://localhost:8000/stac` liefert die Landing Page als JSON,
`http://localhost:8000/stac/collections/sentinel-2-c1-l2a/items` eine
Trefferliste (JSON in einem Browser-Tab ist weniger übersichtlich als ein
STAC-Browser, aber ohne einen zweiten Container zu prüfen).

### Fehlersuche

- **Port belegt** (`address already in use`): Ein anderer Prozess nutzt
  5432, 8000–8003, 9000 oder 9001. Ihn beenden oder in `docker-compose.yml`
  ein anderes Host-Port-Mapping wählen (das Format ist `"host:container"`,
  nur die linke Zahl ändern).
- **Ein Dienst wird nicht `healthy`:** Logs des einzelnen Diensts ansehen,
  z. B. `docker compose logs api`. Ein Neustart eines einzelnen Diensts
  lässt die anderen unberührt: `docker compose restart api`.
- **`catalog-load` ist fehlgeschlagen:** `docker compose logs catalog-load`.
  Meist reicht ein sauberer Neustart mit leeren Volumes:
  `docker compose down -v && docker compose up`.

---

## 3. Prototyp — Referenz, lokal mit eigenem Token

`backend/app/` + `frontend/` sind der ursprüngliche **BIOMASS-Viewer**: ein
Client für den ESA-MAAP-STAC-Katalog mit Kacheln, Zuschnitt, Stitching und
Polarimetrie-Decompositionen. Er bleibt vorerst als lauffähige Referenz
bestehen, wird aber nicht weiterentwickelt und braucht ein **eigenes
MAAP-Konto samt Offline-Token** (siehe unten) — ohne Token startet nur die
Suche, nicht Vorschau/Download.

### Conda-Umgebung anlegen

```bash
conda env create -f environment.yml
conda activate biomass-viewer
```

### Token konfigurieren

```bash
cd backend
cp .env.example .env      # dann .env bearbeiten
```

`MAAP_TOKEN` in `backend/.env` setzen:

1. ESA-MAAP-Konto anlegen: <https://portal.maap.eo.esa.int>
2. Offline-Token erzeugen:
   <https://portal.maap.eo.esa.int/ini/services/auth/token/index.php>
3. Token als `MAAP_TOKEN=...` in `backend/.env` eintragen.

Der Token bleibt serverseitig; das Frontend spricht nur mit diesem Backend.

### Backend starten

```bash
# aus backend/, mit aktivierter conda-Umgebung:
uvicorn app.main:app --reload --port 8000
```

- API-Doku: <http://localhost:8000/docs>
- Health: <http://localhost:8000/api/health>

### Frontend starten

```bash
cd frontend
npm install
npm run dev
```

<http://localhost:5173> öffnen; der Vite-Dev-Server leitet `/api` an das
Backend auf Port 8000 weiter — Backend muss also laufen.

Prototyp und neue Zieltopologie belegen beide lokal Port 8000 (Backend des
Prototyps per `uvicorn`, `api`-Dienst der Zieltopologie per
`docker compose`) — nicht gleichzeitig starten, ohne einen der beiden Ports
zu verlegen.

---

## 4. Attribution

- **Sentinel-2 L2A** (Zieltopologie, Earth Search v1 / Registry of Open Data
  on AWS): Copernicus-Sentinel-Daten. Bei Weitergabe **veränderter** Daten:
  „Contains modified Copernicus Sentinel data [Jahr]", bei unveränderten:
  „Copernicus Sentinel data [Jahr]" (`docs/adr/0003-erster-datensatz.md` §11.2).
  Nutzung unterliegt zusätzlich dem
  [Sentinel Data Legal Notice](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice)
  (kein Gewährleistungsversprechen, Anspruchsverzicht des Nutzers).
- **ESA-BIOMASS-Daten** (Prototyp) — © ESA, verteilt über
  [MAAP](https://portal.maap.eo.esa.int). ESA-Datenrichtlinie beachten,
  Mission und Verarbeitungsstufe bei Veröffentlichung nennen.
- **Basiskarte** (Prototyp): Esri World Imagery — *Esri, Maxar, Earthstar
  Geographics, and the GIS User Community*.
- **Geokodierung** (Prototyp): [Nominatim](https://nominatim.org/) über
  [OpenStreetMap](https://www.openstreetmap.org/copyright)-Daten,
  © OpenStreetMap-Mitwirkende (ODbL).

---

## 5. Lizenz

Anwendungscode: **AGPL-3.0-or-later**, siehe [`LICENSE`](./LICENSE). Vor
2026-09-18 veröffentlichte Releases bleiben unter der MIT-Lizenz verfügbar,
unter der sie erschienen sind.

Die AGPL deckt nur diesen Code, **nicht** die Satellitendaten oder
Basiskarten- bzw. Geokodierungsergebnisse Dritter (siehe Abschnitt 4).

Hinweis zu AGPL §13: Wer eine veränderte Version dieser Software betreibt und
Nutzer darauf über ein Netzwerk zugreifen lässt, muss ihnen Zugang zum
zugehörigen Quellcode anbieten.
