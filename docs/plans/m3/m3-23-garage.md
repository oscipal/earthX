# M3-23 — Garage statt MinIO: Plan-Schritt

**Status (26.09.2026):** Plan-Schritt, wartet auf Ottos Freigabe (§8).
**Aufgabe:** M3-23 aus `docs/plans/m3-dritte-quelle-und-interface.md` §4.
**Stufe B.** Keine Abhängigkeit.
**Grundlagen:** `adr/0012` (angenommen, F1–F6), vor allem §4.1, §7.1, §9;
`plans/m1-08-compose-topologie.md`; `adr/0002` §1, §2; `KLAERUNGEN.md` B8,
B9; `ENTSCHEIDUNGEN_2026-09-18.md` §4; `architekturplan.md` 12.1;
`CLAUDE.md` („Ohne Rückfrage nicht ändern“: `.github/` — hier ausdrücklich
Teil der Aufgabe).

Belegstufen wie in `adr/0009`: **M** in dieser Sitzung gemessen, **P** am
Quelltext gelesen (Garage `v2.4.1`, EarthX `main` c646dc8), **A** eigene
Ableitung.

---

## 1. Ziel

`docker compose up -d` startet Garage als Dienst `objectstore` statt
`bitnamilegacy/minio`, ohne Handarbeit, ohne ein Secret im Repo und auch mit
einem schon bestehenden Volume. Der Pflicht-Check `compose-topology` belegt
am offiziellen Image, was `adr/0012` §9 an selbst gebauten Binärdateien
offen ließ: Das Image startet, boto3 kann schreiben und lesen, eine COG lässt
sich per Range lesen. Anwendungscode bleibt unberührt (F5).

---

## 2. Befund

### 2.1 Heute im Repo — **[P]**

- `docker-compose.yml`: Dienst `minio` (Image per Digest, `MINIO_ROOT_USER`,
  `MINIO_ROOT_PASSWORD`, `MINIO_BROWSER`, Ports 9000/9001, Volume
  `minio-data`, Healthcheck mit `curl`); `api`, `tiler`, `worker`, `harvester`
  hängen per `depends_on: minio (healthy)` daran.
- `.env.example`: `MINIO_ROOT_USER=earthx` (7 Zeichen — Garage verlangt
  mindestens 8, `adr/0012` §4.1), `MINIO_ROOT_PASSWORD=changeme12`.
- `ci.yml`, Job `compose-topology`: Wegwerf-`.env` mit den beiden
  `MINIO_*`-Werten; Name „Compose topology (…, minio)“; `minio` in beiden
  Warteschleifen.
- Kein Python-Code liest den Speicher (E6); `boto3` steht nur in der
  Verbotsliste von `.importlinter` und in keiner `requirements*.txt`.
- README: Diensteliste, Volumes, Ports, Fehlerbehebung „`minio`-Image“.
  `architekturplan.md` 12.1: „S3-kompatibler Objektspeicher (lokal MinIO)“
  samt Nachtrag vom 26.09.2026.

### 2.2 Garage v2.4.1, was den Aufbau bestimmt — **[P]**, Quelltext

1. **Das Image ist `FROM scratch`** mit einer Binärdatei `/garage`
   (`Dockerfile`). Keine Shell, kein `curl`: Weder ein Einstiegsskript noch
   ein `curl`-Healthcheck ist im Container möglich. Healthcheck deshalb
   `["CMD", "/garage", "status"]` (`adr/0012` §4.1, dort gemessen).
2. **RPC-Secret und Admin-Token** gehen als Wert (`GARAGE_RPC_SECRET`,
   `GARAGE_ADMIN_TOKEN`) **oder als Datei** (`GARAGE_RPC_SECRET_FILE`,
   `GARAGE_ADMIN_TOKEN_FILE`); eine Datei mit Rechten weiter als `0600` wird
   abgelehnt (`src/garage/secrets.rs`).
3. **Der S3-Zugangsschlüssel aus `--default-bucket`** kommt nur aus den
   Umgebungsvariablen `GARAGE_DEFAULT_ACCESS_KEY`/`_SECRET_KEY`, **ohne**
   Dateivariante (`src/garage/server.rs`, `initial_config`). Er ist dort
   idempotent: bestehender Schlüssel mit gleichem Secret wird übernommen, mit
   anderem Secret bricht der Start ab.
4. **`--single-node`** legt das Layout beim ersten Start an und lässt ein
   bestehendes Layout (Version 1) in Ruhe — ein zweiter Start mit
   bestehendem Volume ist dafür unkritisch.
5. **Admin-API v2** (Port 3903, Bearer-Token): `GetKeyInfo`, `ImportKey`
   (Fehler, wenn der Schlüssel schon existiert), `GetBucketInfo`
   (`globalAlias`), `CreateBucket`, `AllowBucketKey` (`src/api/admin/`).
6. **Schlüsselformat:** ID mindestens 8 Zeichen aus `[A-Za-z0-9._-]`,
   Secret mindestens 16 druckbare ASCII-Zeichen (`src/model/key_table.rs`).
7. **Digest** `dxflrs/garage:v2.4.1` =
   `sha256:9c96caa2612d3411acc5b0e6701fb238dbfba33e533a6d7d3d811a4b12d0d020`
   (Multi-Arch-Index, 08.09.2026; amd64 28 MB) **[M]**, eine Anfrage an die
   Docker-Hub-API; stimmt mit dem Präfix in `adr/0012` §7.1 überein.

**Folge [A]:** „Secrets beim ersten Start erzeugen“ und „Garage ohne Shell“
passen nur zusammen, wenn das Erzeugen **vor** Garage in einem eigenen
Einmal-Schritt passiert und der S3-Schlüssel **nach** dem Start über die
Admin-API angelegt wird. Punkt 3 schließt den kürzeren Weg über
`--default-bucket` aus, solange die Werte nicht fest in `.env` stehen.

---

## 3. Vorschlag

### 3.1 Dienste in `docker-compose.yml`

| Dienst | Image | Art | Aufgabe |
|---|---|---|---|
| `objectstore-secrets` | Backend-Image (schon gebaut) | einmalig | legt fehlende Secrets als `0600`-Dateien im Volume `objectstore-secrets` an; S3-Schlüssel aus `.env`, wenn gesetzt |
| `objectstore` | `dxflrs/garage:v2.4.1@sha256:9c96…d020` | dauerhaft | `/garage server --single-node`; Konfiguration `garage.toml` schreibgeschützt eingehängt; Secrets per `*_FILE` |
| `objectstore-init` | Backend-Image | einmalig | legt über die Admin-API Schlüssel und Bucket an, idempotent |

Reihenfolge über `depends_on`: `objectstore-secrets` (completed) →
`objectstore` (healthy) → `objectstore-init` (completed) → `api`, `tiler`,
`worker`, `harvester`. Die vier Prozesse hängen dann an `objectstore`
(healthy) und `objectstore-init` (completed) statt an `minio`.

**Volumes:** `objectstore-data` (Metadaten und Daten) und
`objectstore-secrets` getrennt, damit in M4 ein Dienst die Zugangsdaten
lesen kann, ohne das Datenverzeichnis zu sehen. `minio-data` fällt aus der
Datei; ein bestehendes lokales Volume bleibt liegen, bis Otto es löscht
(Löschen von Daten nur durch Otto).

**Ports:** nur `3900:3900` (S3). Admin (3903) und RPC (3901) bleiben im
compose-Netz; es gibt keine Weboberfläche.

### 3.2 Secrets und `.env`

| Wert | Herkunft | liegt |
|---|---|---|
| RPC-Secret (32 Byte hex) | immer erzeugt | `objectstore-secrets:/rpc_secret` |
| Admin-Token | immer erzeugt | `objectstore-secrets:/admin_token` |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | aus `.env`, wenn beide gesetzt; sonst beim ersten Start erzeugt und danach wiederverwendet | `objectstore-secrets:/s3_access_key`, `/s3_secret_key` |
| `S3_BUCKET` | aus `.env`, sonst `earthx` (Vorgabe in compose, kein Secret) | — |

- Erzeugt wird mit Pythons `secrets` (ID `GK` + 24 Hex-Zeichen wie Garages
  eigene Schlüssel, Secret 64 Hex-Zeichen). Vorhandene Dateien werden nie
  überschrieben; ein zweiter Start ändert nichts.
- `.env.example` bekommt `S3_ACCESS_KEY=`, `S3_SECRET_KEY=`, `S3_BUCKET=`
  **ohne Werte**, mit Kommentar „leer = beim ersten Start erzeugt“; die
  `MINIO_*`-Zeilen fallen weg. Ottos bestehende lokale `.env` (mit
  `MINIO_*`, ohne `S3_*`) funktioniert damit unverändert: Die alten Zeilen
  liest niemand mehr, die neuen fehlen und werden erzeugt. In compose stehen
  die Werte als `${S3_ACCESS_KEY:-}`, damit ein Fehlen keine Warnung wirft.
- Eingabeprüfung in `objectstore-secrets`, bevor Garage startet: nur einer
  der beiden S3-Werte gesetzt, ID oder Secret im falschen Format (§2.2
  Punkt 6), ungültiger Bucket-Name → Abbruch mit klarer englischer Meldung.
- Kein Secret erscheint in einem Log: Das Skript gibt höchstens die
  Schlüssel-ID aus, nie Secret, Admin-Token oder RPC-Secret.
- Die Zugangsdaten auslesen (lokal, etwa für die `aws`-CLI):
  `docker compose run --rm --no-deps objectstore-secrets python
  /objectstore/bootstrap.py show` gibt ID und Secret nur auf dem eigenen
  Terminal aus. Steht im README.

### 3.3 Initialisierung (`objectstore-init`), idempotent

1. `GetKeyInfo?id=<S3_ACCESS_KEY>&showSecretKey=true`:
   `404` → `ImportKey`; gleiches Secret → nichts tun; **anderes Secret →
   Abbruch** mit der Meldung, dass der Schlüssel im Volume mit einem anderen
   Secret existiert (so verhält sich auch `--default-bucket`, §2.2 Punkt 3).
2. `GetBucketInfo?globalAlias=<S3_BUCKET>`: `404` → `CreateBucket`.
3. `AllowBucketKey` (Lesen, Schreiben, Eigentümer) — immer, ist idempotent.
4. Zeitablauf und begrenzte Wiederholungen bei nicht erreichbarer API;
   jede andere Antwort als erwartet → Exit ≠ 0 mit Statuscode und
   Garage-Meldung, ohne Token im Text.

Das Skript nutzt nur die Standardbibliothek (`secrets`, `json`,
`urllib.request`). Es liegt **nicht** in `backend/earthx`, gehört also
nicht zur Anwendung und fällt nicht unter `http-only-in-gateway`; es spricht
ausschließlich den eigenen Dienst im compose-Netz an, wie die Healthchecks
mit `curl`. `gateway` regelt den Weg der Anwendung zu Datenquellen (B8); der
Weg der Anwendung zum Speicher bleibt M4 (F5). Das steht als Kommentar im
Skript und in F1.

### 3.4 `garage.toml`

Im Repo, ohne Secret: `replication_factor = 1`, `db_engine = "sqlite"` (so
in `adr/0012` gemessen), `metadata_dir`/`data_dir` im Volume,
`rpc_bind_addr = "[::]:3901"`, `rpc_public_addr = "127.0.0.1:3901"`,
`[s3_api] s3_region = "garage"`, `api_bind_addr = "[::]:3900"`,
`[admin] api_bind_addr = "[::]:3903"`. Eingehängt unter `/etc/garage.toml`,
dem Vorgabepfad der CLI — damit findet auch `garage status` im Healthcheck
die Datei.

### 3.5 Ablage

```
compose/objectstore/garage.toml
compose/objectstore/bootstrap.py        # Unterbefehle: secrets, init, show
compose/objectstore/smoke.py            # nur CI (§4)
compose/objectstore/requirements-smoke.txt   # boto3, rasterio, numpy — gepinnt
backend/tests/compose/test_objectstore_bootstrap.py
```

`compose/` bündelt, was nur die compose-Topologie braucht, und hält es aus
`backend/` (Anwendung) und `scripts/` (Sitzungs-Setup) heraus. Die Dienste
hängen `compose/objectstore/` schreibgeschützt ein; das Backend-Image bleibt
unverändert.

---

## 4. CI (`compose-topology`)

- Wegwerf-`.env` ohne `MINIO_*` **und ohne `S3_*`**: Die CI geht damit
  denselben Weg wie Ottos lokale `.env` (Erzeugung beim ersten Start).
- Diensteliste in beiden Warteschleifen: `postgres objectstore api tiler
  worker harvester`; die Prüfung der Einmal-Schritte um
  `objectstore-secrets` und `objectstore-init` erweitert.
- **Neuer Schritt „Object store smoke (adr/0012 §9)“:** installiert
  `compose/objectstore/requirements-smoke.txt` (boto3 1.43.103 wie gemessen,
  rasterio 1.5.1 wie `backend/requirements.txt`), holt die Zugangsdaten über
  `bootstrap.py show` in Variablen, maskiert sie mit `::add-mask::` und
  führt `smoke.py` gegen `localhost:3900` aus. Geprüft wird die Liste aus
  `adr/0012` §5, soweit M4 sie braucht:
  - `PutObject` mit den Standard-Prüfsummen von boto3; Multipart mit drei
    Teilen; Multipart abbrechen; `GetObject` mit `Range` → `206`;
  - vorsignierte GET-URL mit `Range`, vorsignierte PUT-URL; abgelaufene URL
    abgewiesen (`400` oder `403`, `adr/0012` §4.1); umgeschriebene URL →
    `403`; anonym → abgewiesen; falsches Secret → `403`;
  - Lebenszyklus `Expiration` und `AbortIncompleteMultipartUpload`
    angenommen und zurückgelesen;
  - `ListObjectsV2`, `DeleteObjects`;
  - synthetische COG (im Skript erzeugt): Fenster und Overview über
    `/vsis3/`, Fenster über `/vsicurl/` mit vorsignierter URL.
  Bucket-Policy und CORS prüft der Schritt nicht (F3, keine M4-Pflicht).
- **Zweiter Start mit bestehendem Volume:** `docker compose down` (ohne
  `-v`) → `up -d` → warten → Einmal-Schritte wieder Exit 0 →
  `smoke.py --persisted` prüft, dass ein im ersten Lauf geschriebenes Objekt
  noch da ist und die Zugangsdaten gleich geblieben sind.
- Der bestehende Schritt „Restart one service“ bleibt.
- Jobname: siehe F2.

Die Cloud-Sitzung hat keinen Docker-Daemon (`adr/0002` §1); was nur ein
Container belegen kann, belegt dieser Job.

---

## 5. Tests in `pytest` (Cloud-Sitzung und CI)

`backend/tests/compose/test_objectstore_bootstrap.py` lädt `bootstrap.py`
über den Pfad und prüft ohne Netz nach außen:

- **Secrets:** leeres Volume → vier Dateien mit `0600`, Formate gültig;
  zweiter Lauf ändert keine Datei; `.env`-Werte gewinnen und werden
  geschrieben; nur ID oder nur Secret gesetzt → Abbruch; ID zu kurz oder mit
  verbotenem Zeichen, Secret zu kurz oder mit Leerzeichen, ungültiger
  Bucket-Name → Abbruch mit Meldung.
- **Init gegen eine Admin-API-Attrappe** (`http.server` im Thread auf
  `127.0.0.1`): erster Lauf ruft `ImportKey`, `CreateBucket`,
  `AllowBucketKey`; zweiter Lauf legt nichts neu an; Schlüssel mit anderem
  Secret → Abbruch; `401`, `500`, nicht erreichbar → Exit ≠ 0 nach
  begrenzten Versuchen.
- **Zweckfremd:** Weder Secret noch Admin-Token noch RPC-Secret stehen in
  Ausgabe oder Fehlermeldung, auch nicht, wenn die API das Token im Fehler
  zurückspiegelt; das Token geht nur an die konfigurierte Admin-Adresse.

In der Sitzung zusätzlich, nicht im Repo: `bootstrap.py` einmal gegen eine
aus dem Tag `v2.4.1` gebaute Garage-Binärdatei laufen lassen (wie in
`adr/0012` §12), damit die Admin-API-Aufrufe vor der CI an echtem Garage
geprüft sind. Ergebnis und Zahl der Abrufe stehen im PR.

---

## 6. Doku

- `architekturplan.md` 12.1: „(lokal MinIO)“ → „(lokal Garage, Dienst
  `objectstore`, `adr/0012`)“; der Nachtrag vom 26.09.2026 bekommt einen
  Satz, dass M3-23 umgestellt hat.
- README: Diensteliste (`objectstore` statt `minio`, die zwei neuen
  Einmal-Schritte), Volumes, Ports (3900 statt 9000/9001), Zugangsdaten
  auslesen (§3.2), Fehlerbehebung: der Absatz „`minio`-Image“ wird zu
  „Umstieg von MinIO“ (alter Container: einmal
  `docker compose up -d --remove-orphans`; altes Volume `minio-data` bleibt
  liegen, bis man es selbst löscht) und „Schlüssel mit anderem Secret“
  (§3.3).
- `projektplan.md` Z. 511 („MinIO-Ersatz … offen“) und das Beispiel
  „z. B. MinIO“ in `projektuebersicht.md` (Prinzipien) — siehe F3.
- `plans/m3-dritte-quelle-und-interface.md`: Stand von M3-23; Log-Zeile ans
  Ende von `ENTSCHEIDUNGSLOG.md` nach der Freigabe.

---

## 7. Umfang, Risiken, Abnahme

**Umfang [A]:** compose rund +70/−35, `ci.yml` rund +60/−10,
`bootstrap.py` rund 150, `smoke.py` rund 150, Tests rund 180, dazu
`garage.toml`, `.env.example`, Doku. Zusammen etwa 600 Zeilen und damit über
dem Richtwert von 400; der Überhang sind Tests und das CI-Skript, die F6
ausdrücklich verlangt. Teilen hieße, die CI-Belege aus §9 in einen zweiten
PR zu schieben — nicht vorgeschlagen, weil die Umstellung ohne sie
unbelegt wäre.

| Risiko | Umgang |
|---|---|
| Docker-Hub-Ratenbegrenzung beim Ziehen in CI (`adr/0012` §3.3) | 28 MB, ein Layer; tritt es auf, steht es im PR — kein Wechsel der Registry ohne Otto |
| `garage status` meldet gesund, bevor die S3-API antwortet | `objectstore-init` wiederholt begrenzt; der Smoke-Schritt prüft die S3-API selbst |
| Otto setzt später `S3_*` in `.env` mit einer schon erzeugten ID, aber anderem Secret | Abbruch mit Meldung (§3.3), README beschreibt den Ausweg |
| Nur eines der beiden Volumes wird gelöscht | Secrets neu → neuer Schlüssel wird importiert, der alte bleibt ungenutzt; Daten bleiben lesbar (RPC-Secret betrifft nur das Cluster-Netz eines Einzelknotens) **[A]**, in der Sitzung an der Binärdatei geprüft |
| Der Pflicht-Check ändert seinen Namen | F2 |

**Abnahme (aus der Aufgabe):** `compose-topology` grün mit Garage; keine
Secrets im Diff; zweiter Start mit bestehendem Volume grün (CI-Schritt §4);
Otto startet lokal mit `docker compose up -d` ohne Handarbeit. Dazu:
`ruff check backend`, `pytest`, `lint-imports` grün; `backend/earthx`
unverändert (Beleg über den Diff).

---

## 8. Fragen an Otto

**F1 — Wie entstehen Secrets, Schlüssel und Bucket?**
1. Zwei Einmal-Schritte aus dem vorhandenen Backend-Image
   (`objectstore-secrets` vor, `objectstore-init` nach Garage), Garage nur
   mit `--single-node`; S3-Schlüssel aus `.env`, sonst erzeugt; Skript mit
   Standardbibliothek außerhalb von `backend/earthx` (§3.1–3.3) —
   **Empfehlung**: keine Handarbeit, kein zusätzliches Image.
2. Alles fest aus `.env`, Garage mit `--single-node --default-bucket`, keine
   Hilfsschritte; compose bricht ohne Werte mit Meldung ab. Am einfachsten,
   aber Otto trägt einmal vier Werte in `.env` ein — verfehlt „ohne
   Handarbeit“.
3. Wie 1, aber die Hilfsschritte in einem kleinen, per Digest gepinnten
   Fremdimage (`busybox`/`alpine`) statt des Backend-Images: unabhängig vom
   Backend-Build, dafür ein Image mehr von Docker Hub.

**F2 — Name des CI-Checks.** Der angezeigte Check-Name ist das `name:` des
Jobs und nennt heute `minio`. Ist er im Branch-Schutz als Pflicht-Check
eingetragen, wartet der PR nach einer Umbenennung auf den alten Namen, bis
Otto ihn dort austauscht.
1. Umbenennen in neutral „Compose topology“ ohne Diensteliste; Otto tauscht
   den Namen beim Merge im Branch-Schutz — **Empfehlung**: nie wieder ein
   Produktname im Check.
2. Name unverändert lassen (nennt weiter `minio`), kein Eingriff in den
   Branch-Schutz.

**F3 — Doku über die Aufgabe hinaus.** Die Aufgabe nennt
`architekturplan.md` und README.
1. Zusätzlich `projektplan.md` Z. 511 (Status „offen“ → entschieden,
   `adr/0012`) und das Beispiel in `projektuebersicht.md` („z. B. MinIO“ →
   „z. B. Garage“), je eine Zeile — **Empfehlung**.
2. Nur die zwei genannten; der Rest bleibt für M3-15.

**Kleinentscheidungen, die mit der Freigabe gelten, wenn Otto nicht
widerspricht:** Ablage unter `compose/objectstore/` (§3.5); nur Port 3900
veröffentlicht; `db_engine = "sqlite"`; Region `garage`; Bucket-Vorgabe
`earthx`; RPC-Secret und Admin-Token nie aus `.env`, immer erzeugt; alte
Plandokumente (`m1-08`, `adr/0002`) bleiben als Geschichte unverändert.
