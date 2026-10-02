# ADR 0015 — Weg zum Objektspeicher

- **Status:** Entwurf, wartet auf Otto (Fragen in §14).
- **Datum:** 2026-10-02
- **Aufgabe:** M4-04 laut `docs/plans/m4-processing-kern.md` §4.
- **Autonomiestufe:** C. Es gibt keinen Produktivcode und keine Änderung an
  `.importlinter`, `gateway`, `docker-compose.yml`, `compose/objectstore/` oder
  den Lock-Dateien. Gemessen wurde mit Skripten im Kratzverzeichnis der
  Sitzung; der Messanhang (§16) nennt die Befehle.
- **Vorab fest:**
  - Q5: ein eigenes Modul für Plattformdienste mit festem Endpunkt aus der
    Konfiguration und eigenem Importvertrag; nur `jobs` und `api` dürfen es
    importieren; `gateway` bleibt unverändert (nur `https`, nur öffentliche
    Adressen).
  - Q9: Job-IDs sind nicht zu erraten; Ergebnisse bleiben privat und gehen nur
    über signierte URLs hinaus.
  - Q10: 7 Tage Frist für Ergebnisse und gespeicherte Rezepte, belegt durch
    einen Test des Ablaufs.
  - `adr/0012` F3: kein anonymes Lesen, nur signierte URLs.
  - Aus `adr/0014`: Hash nur intern (Q8), Treffer nur mit Fassung aller
    Eingaben (Q11), `jobs` ist die Hülle für Upload und Fortschritt (§13).
- **Grundlage:**
  - `ENTSCHEIDUNGEN_2026-09-18.md` §4; `KLAERUNGEN.md` B8, B9.
  - `architekturplan.md` 3.1, 3.2, 6.4, 6.5, 7.3, 7.4, 10, 11, 12.1, 12.3, mit
    den Nachträgen vom 02.10.2026.
  - `adr/0006` §5 (Verbotsliste, `obstore`); `adr/0012` (Garage, §4.1, §7.3,
    §9, F3, F5); `adr/0014` §4.5, §4.7, §9, §13, §14.
  - `plans/m3-23-garage.md` und die Log-Zeilen zu M3-23 vom 26.09.2026
    (Nachbesserung: keine Zugangsdaten in Logs).
  - Entscheidungslog bis 02.10.2026, besonders „M4 Q4“ bis „M4 Q11“.
- **Betroffen:**
  - M4-06 (Modul, signierte URLs, Ablauf, AST-Test), M4-08 (Job-API, Cache,
    Aufräumen der Zeilen), M4-11 und M4-12 (Ergebnisse), M4-13 (Download im
    Panel).
  - `.importlinter`, `backend/tests/test_module_boundaries.py`,
    `backend/tests/earthx/test_no_outbound_outside_gateway.py`,
    `backend/earthx/logging.py`.
  - `compose/objectstore/bootstrap.py`, `docker-compose.yml`, `.env.example`,
    `backend/requirements.txt` und die Lock-Dateien (M4-00b).
  - `architekturplan.md` 3.1 (neue Zeile), 6.4, 11.

---

## Methode und Belegstufen

Gelesen und gemessen in einer Cloud-Sitzung am 02.10.2026 auf dem Stand von
`main` nach PR #114. Die Belegstufen folgen `adr/0009`:

- **M:** in dieser Sitzung gemessen; Befehl im Messanhang §16.
- **P:** am Primärdokument gelesen, mit Datei und Zeile (Quelltext im Repo, im
  venv, in einem Wheel von PyPI oder im Git-Repo des Herausgebers; offizielle
  Doku).
- **S:** Zusammenfassung einer Quelle, deren Wortlaut nicht geprüft ist.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

Wo ein Beleg fehlt, steht „unbelegt“.

**Garage aus dem Quelltext, wie in `adr/0012`.** Docker hat in der Sitzung
keinen Daemon (`cloud-umgebung.md` §4). Garage v2.4.1 wurde mit
`cargo build --release --locked` aus dem Tag gebaut (6 min 24 s, Commit
`268334b`) und als Einzelknoten auf `127.0.0.1` gestartet. Schlüssel und Bucket
legte das vorhandene `compose/objectstore/bootstrap.py` an (`secrets`, dann
`init` gegen die Admin-API), also derselbe Weg wie in compose **[M]**. Die
selbst gebaute Binärdatei ist dynamisch gegen glibc gelinkt **[M]**; das
offizielle Image ist dagegen `FROM scratch` mit einer musl-Binärdatei
(`Dockerfile`, `flake.nix` Z. 45: `x86_64-unknown-linux-musl`) **[P]**. Das ist
für den Ablauftest wichtig (§7.4).

**Clients.** Jede Bibliothek lag nur in einem eigenen Ordner im
Kratzverzeichnis (`pip install --target`) und wurde über `PYTHONPATH` zum
Python des Projekt-venv gelegt; das Projekt-venv blieb unverändert. Gemessen
mit Python 3.12.3, rasterio 1.5.2/GDAL 3.12.2, botocore 1.43.103,
boto3 1.43.103 (zieht botocore 1.43.107), aiobotocore 3.9.2, minio 7.2.20,
obstore 0.11.1, import-linter 2.15 **[M]**.

**Verstellte Uhr.** Für den Ablauf lief Garage mit `libfaketime` 0.9.10 aus
dem Ubuntu-Archiv (nur entpackt, nicht installiert), Prüfskript mit derselben
Uhr **[M]**.

**Netz.** Alle Messungen am Speicher liefen gegen `127.0.0.1`, mit Wegwerf-
Schlüsseln, ohne Proxy-Variablen und ohne die `AWS_*`-Variablen der Sitzung.
Keine Quelle der Plattform wurde berührt. Abrufe nach außen: `git clone` von
Garage, der Crate-Download für den Bau (crates.io), die Wheels von PyPI, das
Paket `libfaketime` aus dem Ubuntu-Archiv. Ein Recherche-Agent hat die
Sekundärquellen in §15 gesucht; was davon hier als **P** steht, ist am
Primärdokument nachgelesen.

---

## 0. Kurzfassung

Jede Empfehlung hat eine Frage in §14.

1. **Modul `earthx.objectstore` (F1, F2).** Es kennt genau einen Speicher, aus
   der Konfiguration, und nimmt nur Kennungen entgegen, nie eine URL. Zeile in
   3.1: „importiert nichts Fachliches“; `jobs` und `api` dürfen es importieren.
   Der Client wird mit **einer** Zeile `ignore_imports` im Vertrag
   `http-only-in-gateway` erlaubt: `earthx.objectstore.client -> botocore`.
   Gemessen: Dieselbe Zeile lässt jeden anderen Import von `botocore` brechen,
   auch im selben Modul **[M]**. Die Verbotsliste wächst um `botocore`,
   `urllib3` und weitere S3-Clients.
2. **Client: `botocore` allein, ohne `boto3` (F3).**
   - **Befund:** Liegt `boto3` im Image, öffnet rasterio für jede Adresse mit
     `amazonaws.com` im Pfad eine boto3-Sitzung und fragt dabei den
     Metadatendienst unter `169.254.169.254` ab — eine Verbindung außerhalb
     von `gateway` zu einer Link-Local-Adresse **[M]**. Sind `AWS_*`-Variablen
     gesetzt, gibt rasterio sie an GDAL weiter **[M][P]**. Die Quellen von
     Sentinel-2 und DEM liegen unter `amazonaws.com`.
   - Heute wird das nicht ausgelöst, weil `readers` nur `/vsicurl/`-Pfade öffnet
     **[M]**. Es ist eine Falle für jeden späteren Lesepfad.
   - rasterio prüft genau `import boto3` **[P]**. Mit `botocore` allein bleibt
     rasterio unverändert **[M]**, und Multipart geht auch ohne `boto3`
     **[M]**. Neu im Image: `botocore`, `jmespath`, `urllib3`.
3. **Signierte URLs (F4, F5, F6).**
   - Die Links im Ergebnisdokument zeigen auf `api`
     (`/jobs/{jobID}/results/{name}`). Jeder Abruf antwortet `303` mit einer
     frisch signierten URL, gültig 15 Minuten, nie über das Ablaufdatum des
     Ergebnisses hinaus. Kein Byte läuft durch `api`.
   - Signiert wird für einen eigenen **öffentlichen Endpunkt**
     (`S3_PUBLIC_ENDPOINT`). Gemessen: Eine für `objectstore:3900` signierte URL
     wird mit anderem Host abgewiesen (`403`), eine für den öffentlichen
     Endpunkt signierte geht (`200`) **[M]**. Signieren öffnet keine
     Verbindung **[M]**.
   - **Zwei Schlüssel:** `jobs` schreibt und löscht, `api` darf nur lesen und
     signieren. Gemessen: Eine mit dem Leseschlüssel signierte PUT- oder
     DELETE-URL wird abgewiesen (`403`) **[M]**. Die Schlüssel-ID steht in jeder
     signierten URL **[M]**; beim Leseschlüssel ist das ohne Folgen.
   - Abgelaufen: Garage antwortet `400`, AWS `403` (`adr/0012` §4.1). Mit dem
     Redirect sieht der Nutzer das praktisch nie; Tests akzeptieren beides.
4. **Ablauf nach 7 Tagen (F7, F8, F9).**
   - **Zwei Schichten.** Ein Aufräumer in `jobs` löscht Objekte und
     zugehörige Zeilen (Job, Ergebnis, Rezept) nach `expires_at`; `api` liefert
     ab `expires_at` keine URL mehr (`410`). Die Bucket-Regel `results/` nach 7
     Tagen plus Abbruch liegengebliebener Multipart-Uploads nach 1 Tag ist das
     Netz für Waisen.
   - **Gemessen mit verstellter Uhr:** Objekte vom 02.10. liegen am 09.10. noch,
     am 10.10. um 0 Uhr UTC sind sie gelöscht; der Multipart-Rest war am 04.10.
     weg **[M]**. Garage rechnet „7 Tage“ also als 7 bis 8 Tage **[M][P]**.
   - Die Regel setzt `objectstore-init` über Garages Admin-API (gemessen
     **[M]**), in Produktion die Infrastruktur. `jobs` prüft sie beim Start
     nur lesend. Der Schreibschlüssel darf die Regel in Garage auch löschen
     **[M]**; deshalb hängt nichts allein an ihr.
   - **Beleg nach `adr/0012` §9 Punkt 5:** Der Aufräumer wird in der CI mit
     injizierter Uhr getestet. Die Regel selbst ist hier an der Binärdatei
     belegt; mit dem offiziellen Image geht `libfaketime` nicht (musl,
     statisch).
5. **Ablage (F10, F11).** Schlüssel `results/{result_id}/{name}` mit eigener
   zufälliger `result_id`, nie Job-ID, Hash oder AOI. Ein Ergebnis ohne Fassung
   wird ebenso 7 Tage gespeichert, nur ohne Cache-Eintrag (Frage aus
   `adr/0014` §14). Ein Treffer zählt nur bei mindestens 24 Stunden
   Restlaufzeit.
6. **Zugangsdaten (F12).** Nur aus der Umgebung, mit Namen `S3_*` (nie
   `AWS_*`, wegen rasterio, Punkt 2), auch als `S3_*_FILE`. `botocore` und
   `urllib3` kommen auf die Liste der Logger, die `configure_logging` auf
   `WARNING` hebt: Bei `DEBUG` schreiben sie Schlüssel-ID und Signatur ins Log,
   bei `INFO` nichts **[M]**. Fehlertexte von Garage nennen die Schlüssel-ID
   **[M]** und laufen deshalb durch eine Schwärzung wie in M3-23.
   Produktion: verwalteter S3 ohne Codeänderung, nur andere Variablen.

---

## 1. Kontext und Frage

Ab M4 schreibt der Worker Ergebnisse in den Objektspeicher, und `api` gibt sie
über signierte URLs heraus (`architekturplan.md` 6.4, 7.4, 12.3). Der Speicher
ist ein Plattformdienst im compose-Netz (`http://objectstore:3900`, Garage
v2.4.1 seit M3-23). `gateway` lässt ihn nicht durch: nur `https`, nur öffentlich
routbare Adressen (`gateway/policy.py`, `gateway/resolver.py`) **[P]**. `boto3`
darf außerhalb von `gateway` nicht importiert werden (`.importlinter`, Vertrag
`http-only-in-gateway`) **[P]**. `adr/0012` F5 hat das offen gelassen; Otto hat
in Q5 den Weg vorgegeben: ein eigenes Modul mit eigenem Vertrag, nur für `jobs`
und `api`.

**Otto entscheidet nach diesem ADR:**

1. Name, Zuschnitt und Importvertrag des Moduls.
2. Den Client.
3. Lebensdauer, Endpunkt und Schlüssel der signierten URLs.
4. Wie die 7 Tage durchgesetzt und belegt werden, für Objekte und Zeilen.
5. Ablage der Ergebnisse und ihr Verhältnis zum Cache.
6. Zugangsdaten, Logs und den Weg zu einem verwalteten S3 in Produktion.

## 2. Kriterien

| # | Kriterium | Quelle |
|---|---|---|
| K1 | Nur `jobs` und `api` erreichen den Speicher; `processing` nicht, auch nicht über eine Kette | Q4, Q5; B9; 3.1 |
| K2 | `gateway` und die Regel „kein Client außerhalb von `gateway`“ werden für kein anderes Modul gelockert | Q5; B8 |
| K3 | Der Speicher ist nur über einen festen Endpunkt aus der Konfiguration erreichbar; keine Funktion nimmt eine URL entgegen | Q5 |
| K4 | Kein neuer Weg nach außen, auch nicht als Nebenwirkung einer Bibliothek | B8; `adr/0006` §5 |
| K5 | Ergebnisse privat, nur über signierte URLs, mit kurzer Laufzeit; Kennungen zufällig, kein Hash, keine AOI | Q8, Q9; `adr/0012` F3; 11 |
| K6 | 7 Tage Frist für Objekte und Zeilen, mit Test belegt | Q10; `adr/0012` §9 Punkt 5 |
| K7 | Zugangsdaten nur aus der Umgebung, nie in Logs, Fehlertexten oder CI-Ausgaben | ENTSCHEIDUNGEN §4; M3-23 Nachbesserung |
| K8 | Produktion mit verwaltetem S3 ohne Codeänderung | `adr/0012` K7; 12.1 |
| K9 | Wenige bewegliche Teile, neue Abhängigkeiten nur mit Grund (Lock-Datei) | 1.1 Ziel 6; M4-Plan §1.2 |

---

## 3. Befunde

### 3.1 rasterio ändert sein Verhalten, sobald `boto3` importierbar ist — [M] und [P]

rasterio versucht beim Laden `import boto3` (`rasterio/session.py` Z. 12–16)
**[P]**. `Session.cls_from_path` wählt für jede Adresse mit Schema `s3` **oder
mit `amazonaws.com` im Pfad** eine `AWSSession`, wenn `boto3` da ist
(Z. 104–111). `rasterio.open` ruft das über `ensure_env_with_credentials` bei
jedem Öffnen auf (`rasterio/env.py` Z. 447–461) **[P]**. `AWSSession` legt eine
`boto3.Session` an und fragt deren Zugangsdaten ab (Z. 283–296) **[P]**.

Gemessen mit `strace -e connect`, synthetische COG über einen lokalen
HTTP-Server unter einem Pfad mit `amazonaws.com`, Proxy- und `AWS_*`-Variablen
entfernt **[M]**:

| Lauf | `AWSSession` | Verbindungen |
|---|---|---|
| ohne `boto3`, `http://…/amazonaws.com/x.tif` | nein | nur `127.0.0.1:8765` |
| mit `boto3`, `http://…/amazonaws.com/x.tif` | **ja**, Zugangsdaten `None` | `127.0.0.1:8765` und **`169.254.169.254:80`** |
| mit `boto3`, `/vsicurl/http://…/amazonaws.com/x.tif` | nein (Pfad wird nicht geparst) | nur `127.0.0.1:8765` |
| nur `botocore`, `http://…/amazonaws.com/x.tif` | nein | nur `127.0.0.1:8765` |

Mit gesetzten `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` fand die Sitzung
Zugangsdaten und reichte sie als GDAL-Optionen weiter **[M]**; das tut
`AWSSession.get_credential_options` **[P]**.

**Lesart [A].**

- Heute folgenlos: `readers/cog.py` öffnet nur Pfade aus
  `gateway.gdal.vsicurl_path`, und die beginnen mit `/vsicurl/` **[P]**.
- Aber die Quellen liegen unter `amazonaws.com` (Earth Search:
  `sentinel-cogs.s3.us-west-2.amazonaws.com`, DEM:
  `copernicus-dem-30m.s3.amazonaws.com`, `adr/0009` §3.1). Jeder spätere Weg,
  der eine solche `https`-Adresse ohne `/vsicurl/` an rasterio gibt, etwa
  rioxarray oder ein Datensatzmodul wie `decomp.py` mit `rasterio.open(href)`,
  würde im Cloud-Betrieb den Metadatendienst fragen. Dort antwortet er, und
  GDAL bekäme die Rolle der Maschine.
- Das Image ist für alle vier Prozesse gleich (3.2). `boto3` für den Worker
  hieße `boto3` auch im `tiler`.
- `moto` (E7, Tests) hängt von `boto3` ab (`Requires-Dist: boto3>=1.9.201`,
  moto 5.2.3) **[P]**. Das betrifft nur die Dev-Umgebung, nicht das Image.

### 3.2 botocore: Endpunkt, Umgebung, Verbindungen — [M]

Client mit `endpoint_url`, `region_name`, Schlüssel und `Config` ausdrücklich
übergeben, `HOME` auf einen leeren Ordner:

- **Signieren öffnet keine Verbindung:** 1 000 signierte GET-URLs, 0
  `connect`-Aufrufe; 0,24 ms je URL **[M]**.
- **`AWS_ENDPOINT_URL` und `AWS_ENDPOINT_URL_S3`** aus der Umgebung ändern den
  Host der URL nicht, wenn `endpoint_url` übergeben ist **[M]**.
- **Region muss passen:** Mit `us-east-1` signiert, antwortet Garage auf
  signierte URL und Header-Signatur mit `400 AuthorizationHeaderMalformed`
  („unexpected scope“) **[M]**. `adr/0012` §4.1 hatte notiert, ein Client mit
  `us-east-1` werde angenommen; für v2.4.1 und botocore 1.43 gilt das nicht.
  Die Region gehört deshalb in die Konfiguration (`S3_REGION`).
- **Logs:** Bei `INFO` schreiben `botocore` und `urllib3` nichts. Bei `DEBUG`
  stehen Schlüssel-ID, kanonische Anfrage und die Signatur einer signierten
  URL im Log; das Secret nicht **[M]**.
- **Fehlertexte:** Eine Anfrage mit unbekanntem Schlüssel liefert
  `AccessDenied … No such key: <Schlüssel-ID>`; die ID steht also in
  `str(ClientError)` **[M]**. Mit falschem Secret steht sie nicht darin **[M]**.
- **Proxy aus der Umgebung:** Mit `HTTP_PROXY` in der Umgebung geht eine Anfrage
  an den übergebenen Endpunkt über den Proxy (`connect` auf den Proxy-Port)
  **[M]**. Mit `Config(proxies={})` geht sie direkt **[M]**; botocore liest die
  Umgebung nur, wenn `proxies` `None` ist (`botocore/endpoint.py` Z. 412–413,
  `utils.py` Z. 3194–3198) **[P]**.
- **Metadatendienst:** Mit ausdrücklich übergebenen Schlüsseln baut
  `create_client` die Zugangsdaten direkt; der Resolver mit dem
  Metadatendienst läuft nicht (gemessen: 0 Verbindungen, oben) **[M]**.
  `AWS_EC2_METADATA_DISABLED=true` schaltet den Abruf ganz ab
  (`botocore/utils.py` Z. 420) **[P]**.
- **Vorgaben:** `ExpiresIn` ist 3600 s (`botocore/signers.py` Z. 757)
  **[P]**; Prüfsummen stehen auf `when_supported`
  (`botocore/configprovider.py` Z. 195–204) **[P]**. Ein explizites
  `endpoint_url` geht vor `AWS_ENDPOINT_URL*` (`botocore/args.py` Z. 388–389)
  **[P]**, wie oben gemessen.

### 3.3 Garage v2.4.1: signierte URLs, Rechte, Ablauf — [M] und [P]

| Prüfung | Ergebnis |
|---|---|
| Multipart mit `botocore` allein (3 Teile, ohne `s3transfer`) | ✅ 10 486 994 Bytes |
| URL signiert für `objectstore:3900`, abgerufen über `127.0.0.1:3900` | ❌ `403` |
| dieselbe URL mit Header `Host: objectstore:3900` | ✅ `200` |
| URL signiert für den öffentlichen Endpunkt `localhost:3900` | ✅ `200` |
| `response-content-disposition` in der signierten URL | ✅ Header `attachment; filename="earthx-result.tif"` |
| `Range` auf signierter URL | ✅ `206` |
| `ExpiresIn` 604 801 s | botocore signiert; Garage `400` „X-Amz-Expires may not exceed a week“ |
| abgelaufene URL | `400 InvalidRequest` „Date is too old“ (wie `adr/0012` §4.1) |
| Leseschlüssel: signiertes GET / PUT / DELETE | ✅ `200` / ❌ `403` / ❌ `403` |
| Leseschlüssel: `GetBucketLifecycleConfiguration` / `Put…` | ✅ / ❌ `403 AccessDenied` |
| Schreibschlüssel: `PutBucketLifecycleConfiguration` / `DeleteBucketLifecycle` | ✅ / ✅ |
| Header `x-amz-expiration` am neuen Objekt | fehlt (wie `adr/0012` §5) |
| Regel über Admin-API `POST /v2/UpdateBucket` mit `lifecycleRules` setzen und leeren | ✅ `200`, danach über S3 und Admin-API gleich gelesen |

**Rechte [P].** Garage teilt S3-Aufrufe in drei Stufen
(`src/api/s3/router.rs`, `authorization_type`): Lesen (alle `Get…`,
`Head…`, `List…`, darunter `GetBucketLifecycleConfiguration`), Eigentümer
(nur Bucket löschen, Website, CORS) und Schreiben (alles andere). Damit ist
`PutBucketLifecycleConfiguration` ein **Schreib**-Recht: Wer Objekte schreiben
darf, darf auch die Regel ändern oder löschen. Bei AWS ist das eine eigene
IAM-Aktion (`s3:PutLifecycleConfiguration`); nicht nachgelesen, unbelegt.

**Ablauf [P].** Der Lebenszyklus-Worker (`src/model/s3/lifecycle_worker.rs`)
läuft einmal je Tag (UTC, Z. 210–228): beim Start, wenn er für heute noch nicht
fertig ist (Z. 78–87), sonst ab der nächsten Mitternacht. Ein Objekt gilt als
fällig, wenn `heute − (Schreibtag + 1) ≥ Days` (Z. 297–307, `next_date`
Z. 407–413). Ein Objekt vom Tag *D* verschwindet also mit dem Lauf am Tag
*D* + 8, bei `Days = 7`.

**Ablauf mit verstellter Uhr [M].** Regel `results/`, `Expiration: 7 Tage`,
`AbortIncompleteMultipartUpload: 1 Tag`; Objekte und ein offener
Multipart-Upload am 02.10.2026 gegen 14:45 UTC geschrieben; dann Garage je
einmal mit `libfaketime` neu gestartet:

| Uhr | Lauf des Workers | Objekte unter `results/` | `keep/marker.txt` | offener Multipart |
|---|---|---|---|---|
| +1 Tag (03.10.) | 0 abgelaufen, 0 abgebrochen | 3 | da | da |
| +2 Tage (04.10.) | 0 abgelaufen, **1 abgebrochen** | 3 | da | weg |
| +7 Tage (09.10.) | 0 abgelaufen | 3 | da | — |
| +8 Tage (10.10.) | **3 abgelaufen** | 0 | da | — |

Die Regel greift, der Präfix grenzt richtig ab, und die Frist ist 7 bis 8 Tage
je nach Uhrzeit des Schreibens. AWS rechnet ebenso auf die nächste Mitternacht
UTC auf **[S]** (§15).

### 3.4 Clients im Vergleich — [M] und [P]

| | `botocore` allein | `boto3` | `aiobotocore` | `minio` (minio-py) | `obstore` |
|---|---|---|---|---|---|
| Version | 1.43.103 | 1.43.103 | 3.9.2 | 7.2.20 | 0.11.1 |
| Lizenz | Apache-2.0 | Apache-2.0 | Apache-2.0 | Apache-2.0 | MIT **[S]** |
| installiert | 33 MB | 35 MB | 48 MB | 15 MB | 16 MB |
| neu im Image (nicht schon in `requirements.lock`) | `botocore`, `jmespath`, `urllib3` | dazu `boto3`, `s3transfer` | dazu `aiohttp` und sieben weitere | `minio`, `argon2-cffi`, `pycryptodome`, `urllib3`, … | `obstore` |
| Import + Client | 237–287 ms, +36 MiB | 305–428 ms, +39 MiB | — | 208–226 ms, +20 MiB | 16–21 ms, +10 MiB |
| rasterio sieht `boto3` (§3.1) | **nein** | ja | nein | nein | nein |
| eigene Bindung | — | — | `botocore<1.43.107,>=1.43.101` | — | — |
| auf der Verbotsliste | nein (Lücke, §3.6) | ja | nein | nein | ja (`adr/0006` F6) |
| letztes Release | 01.10.2026 | 01.10.2026 | 30.09.2026 | 27.11.2025 | 21.08.2026 |

Werte gemessen **[M]**; Lizenz von `obstore` und Release-Daten von PyPI über
den Recherche-Agenten **[S]** (§15). `aioboto3` ist nicht gemessen: Es bindet
`aiobotocore[boto3]==2.25.1` fest und hatte seit dem 30.10.2025 weder Release
noch Commit **[S]**.

**Lesart [A].**

- **`boto3`** bringt gegenüber `botocore` nur `upload_file` (Multipart in
  Threads, `s3transfer`) und eine Ressourcen-API. Multipart mit `botocore` ist
  ein Dutzend Zeilen und gemessen **[M]**. Dafür ändert `boto3` das Verhalten
  von rasterio (§3.1).
- **`aiobotocore`** bindet `botocore` an ein enges Fenster
  (`<1.43.107` **[P]**) und zieht `aiohttp` ins Image. `api` signiert ohne Netz
  (§3.2), braucht also nichts Asynchrones; der Worker lädt synchron hoch.
- **`minio`** ist der Client eines Herstellers, der die freie Ausgabe aufgegeben
  hat (`adr/0012` §3). Das Repo von minio-py hat Commits bis September 2026,
  aber kein Release seit November 2025 **[S]**.
- **`obstore`** ist am leichtesten und kann signieren **[S]**, steht aber auf
  der Verbotsliste, weil `titiler.xarray` ihn mitbringen würde (`adr/0006` F6).
  Ihn hier zu erlauben, hieße die Liste für genau den Client zu öffnen, gegen
  den sie geschrieben wurde. Lebenszyklus-Regeln setzt er nicht **[S]**.
- **Eigener SigV4-Client:** Signieren sind rund 60 Zeilen mit `hmac`; zum
  Hochladen bräuchte das Modul aber einen HTTP-Client (`httpx`, `urllib`), und
  der könnte dann jede URL abrufen. `botocore` spricht nur das AWS-Protokoll
  gegen den übergebenen Endpunkt.

### 3.5 import-linter: eine Ausnahme genau für einen Import — [M]

Ein Abzug von `backend/earthx` im Kratzverzeichnis mit einem Modul
`objectstore` (`client.py` importiert `botocore`) und einem Import aus `jobs`;
`.importlinter` ergänzt um `botocore` in der Verbotsliste, `earthx.objectstore`
als Quelle und:

```ini
ignore_imports =
    earthx.objectstore.client -> botocore
```

- Grün, solange nur `objectstore/client.py` `botocore` importiert **[M]**.
- **Gebrochen**, sobald `earthx.objectstore.other` oder
  `earthx.processing.bad` `botocore` importiert, und ein Vertrag „nur `jobs`
  und `api`“ bricht bei `earthx.access.bad -> earthx.objectstore` **[M]**.
- Eine Ausnahme, die auf nichts passt (`-> botocore.*`), lässt `lint-imports`
  scheitern („No matches for ignored import“) **[M]**. Eine vergessene
  Ausnahme fällt also auf. Externe Pakete zählen nur mit ihrem obersten Namen
  **[M]**.

### 3.6 Lücken in der heutigen Verbotsliste — [P]

`http-only-in-gateway` verbietet `httpx`, `httpx2`, `requests`, `urllib`,
`pystac_client`, `aiohttp`, `boto3`, `obstore` (`.importlinter`) **[P]**.
**`botocore` fehlt**, obwohl es allein S3-Anfragen stellen kann (§3.3), und
**`urllib3`** fehlt, obwohl es ein HTTP-Client ist. Beide sind heute nicht im
Image (`requirements.lock`) **[P]**; mit diesem ADR kämen sie hinein. Sie
gehören also im selben PR auf die Liste (eine Verschärfung).

---

## 4. Modul (Punkt „Modul“ des Auftrags)

### 4.1 Name und Zuschnitt

| Option | Name | Folge |
|---|---|---|
| **N1** | `earthx.objectstore` | heißt wie der compose-Dienst (`adr/0012` F4); der Vertrag sagt, was er schützt |
| N2 | `earthx.services` | Platz für weitere Plattformdienste (Redis, Mail); lädt zum Sammelbecken ein, und jeder neue Dienst erbt den Client-Vertrag |
| N3 | `earthx.storage` | neutral, aber leicht mit Datenquellen (Buckets der Quellen) zu verwechseln |

`earthx.platform` scheidet aus: Es verdeckt das Standardmodul `platform` in
Werkzeugen, die Pakete flach lesen **[A]**.

**Empfehlung N1.** Kommt ein zweiter Plattformdienst, bekommt er ein eigenes
Modul mit eigenem Vertrag; so bleibt jede Ausnahme so eng wie hier **[A]**.

**Zuschnitt (Vorschlag, nicht gebaut):**

| Datei | Inhalt |
|---|---|
| `objectstore/config.py` | `StoreConfig` aus der Umgebung (§9.1): Endpunkte, Region, Bucket, Schlüssel; prüft Schema, Host und Pfad der Endpunkte |
| `objectstore/client.py` | die **einzige** Stelle mit `botocore`: baut den Client aus `StoreConfig`; Timeouts, Wiederholungen, Prüfsummen |
| `objectstore/results.py` | `upload_result(result_id, name, path)`, `signed_download(result_id, name, *, not_after, filename) -> str`, `delete_result(result_id)`, `lifecycle_ok() -> bool` |
| `objectstore/errors.py` | eigene Fehlerklassen; Texte laufen durch die Schwärzung (§9.2) |

Keine Funktion nimmt Bucket, Endpunkt, Host oder URL entgegen. `result_id` und
`name` werden gegen ein festes Muster geprüft (`result_id` wie
`secrets.token_urlsafe(16)`, `name` aus einer festen Menge wie `result.tif`,
`recipe.json`, `citation.bib`, `attribution.txt`), damit kein Schlüssel aus
Nutzereingaben entsteht **[A]**.

### 4.2 Zeile in 3.1 und Importvertrag

| Modul | Zuständig für | Darf importieren |
|---|---|---|
| `objectstore` | Zugang zum eigenen Objektspeicher: Upload, signierte URLs, Löschen, Prüfen der Ablaufregel; ein Endpunkt aus der Konfiguration | nichts Fachliches |
| `jobs` (geändert) | wie bisher | `processing`, `objectstore` (dazu psycopg nach `adr/0013`) |

`api` darf ohnehin alles. In `.importlinter` heißt das:

1. **Neuer Vertrag `objectstore`** nach dem Muster von `gateway`: verbietet alle
   übrigen Module von 3.1.
2. **Alle anderen Modulverträge** bekommen `earthx.objectstore` in ihre
   `forbidden_modules`, außer `jobs`. `test_module_boundaries.py` rechnet das
   heute schon aus der Tabelle (`ALL_MODULES - ALLOWED_IMPORTS[m]`) **[P]**;
   dort kommen `objectstore` in `ALLOWED_IMPORTS` und `jobs` →
   `{"processing", "objectstore"}` hinzu.
3. **Kettenvertrag für den Worker-Kern:** `processing` bekommt
   `earthx.objectstore` und `botocore` als verboten, ohne
   `allow_indirect_imports`, wie `no-database-in-worker-core` heute psycopg
   (B9). Ob das ein eigener Vertrag ist oder in den von `adr/0013`
   umgeschnittenen eingeht, entscheidet M4-06 mit `adr/0013` **[A]**.
4. **`http-only-in-gateway`:**
   - `earthx.objectstore` kommt zu den `source_modules` (es ist nicht
     `gateway`; alle Clients bleiben ihm verboten);
   - `botocore`, `urllib3`, `s3transfer`, `aiobotocore`, `aioboto3`, `minio`
     kommen zu den `forbidden_modules` (Verschärfung, §3.6);
   - eine Zeile `ignore_imports = earthx.objectstore.client -> botocore`.

So bleibt `http-only-in-gateway` für jedes andere Modul so streng wie heute,
und die einzige Ausnahme steht als ein Import im Vertrag, nicht als ein Modul
(§3.5) **[M]**. Gegenüber einem eigenen Vertrag nur für `objectstore` (Option
V2 in F2) spart das eine zweite Liste, die mit der ersten Schritt halten
müsste.

### 4.3 AST-Test nach dem Muster von `test_no_outbound_outside_gateway.py`

Neue Datei `backend/tests/earthx/test_objectstore_boundary.py`, ohne Netz:

1. **Nur `jobs`, `api` und `objectstore` selbst** importieren
   `earthx.objectstore` — Lauf über den Syntaxbaum jedes Moduls, auch Importe in
   Funktionen und `from earthx import objectstore`.
2. **`botocore` nur in `objectstore/client.py`;** jedes andere Modul (auch
   `gateway`) importiert es nicht.
3. **`objectstore` importiert keinen anderen Client** aus der Verbotsliste.
4. **Kein `boto3` im Image:** `boto3` und `s3transfer` stehen nicht in
   `backend/requirements.lock` (§3.1). Ein Satz im Test sagt, warum.
5. **Gegenproben,** wie dort üblich: Jede Prüfung erkennt den Verstoß, den sie
   verbietet, an einem Quelltext-Schnipsel.

`test_no_outbound_outside_gateway.py` nimmt `objectstore/client.py` dann für
genau `botocore` aus und sonst nichts; die Liste `CORE` wächst um `botocore`
und `urllib3`.

---

## 5. Client (Punkt „Client“ des Auftrags)

**Empfehlung: `botocore` allein, im Lock gepinnt.** Gründe aus §3:

1. Es erhält rasterio unverändert (§3.1) **[M]** — der wichtigste Punkt, weil
   das Image für alle Prozesse gleich ist.
2. Es kann alles, was M4 braucht: Upload einschließlich Multipart, signierte
   URLs mit Dateinamen, Löschen, Lebenszyklus lesen **[M]**.
3. Es spricht nur das S3-Protokoll gegen den übergebenen Endpunkt und
   ignoriert Endpunkte aus der Umgebung, wenn einer übergeben ist **[M]**.
4. `moto` (E7) baut auf botocore auf; Tests und Code sprechen dieselbe
   Bibliothek **[P]** (`Requires-Dist` von moto 5.2.3).

**Einstellungen** (`botocore.config.Config`), als Vorschlag für M4-06:

- `signature_version="s3v4"`, `s3={"addressing_style": "path"}`.
- `request_checksum_calculation="when_required"`,
  `response_checksum_validation="when_required"`: botocore schickt seit
  1.36 sonst standardmäßig Prüfsummen mit, die nicht jeder S3-Dienst versteht
  (§15) **[S]**; mit dieser Einstellung lief der ganze Messlauf **[M]**.
- `connect_timeout` und `read_timeout` ausdrücklich,
  `retries={"mode": "standard", "max_attempts": 3}`.
- `proxies={}`: Sonst nimmt botocore `HTTP_PROXY`/`HTTPS_PROXY` aus der
  Umgebung auch für den internen Endpunkt (§3.2) **[M]**. Mit dem Egress-Proxy
  aus B8 (M6) liefen Uploads sonst über ihn.
- Der Prozess setzt `AWS_EC2_METADATA_DISABLED=true` (Dockerfile) als zweite
  Sicherung gegen den Weg aus §3.1 **[A]**.

**Abhängigkeit:** `botocore` in `backend/requirements.txt` mit Kappe auf die
Hauptversion, erneuerte Lock-Datei im selben PR (M4-Plan §1.2). `moto` kommt in
`requirements-dev.txt` und bringt dort `boto3` mit; das ist nur die
Testumgebung (§3.1).

---

## 6. Signierte URLs

### 6.1 Weg zum Browser: Redirect über `api`

| Option | Ablauf | Folge |
|---|---|---|
| **R1** | Das Ergebnisdokument (`/jobs/{jobID}/results`, `adr/0014` §9) verlinkt `/jobs/{jobID}/results/{name}` in `api`; jeder Abruf antwortet `303 See Other` mit einer frisch signierten URL | der Link im Panel bleibt gültig, solange das Ergebnis lebt; die signierte URL kann kurz leben; kein Byte durch `api` |
| R2 | Das Ergebnisdokument enthält die signierten URLs selbst | einfacher; aber ein geöffnetes Panel hält nach Ablauf tote Links, und das Frontend muss `400`/`403` des Speichers deuten |
| R3 | `api` streamt das Ergebnis selbst | keine signierte URL nötig; widerspricht 6.4 („Auslieferung über signierte URLs“) und belastet `api` mit Hunderten MB |

**Empfehlung R1.** Die Kennung `jobID` ist ohnehin der Zugang (Q9, 128 Bit,
`adr/0014` §9); der Redirect gibt nichts heraus, was der Halter der `jobID`
nicht schon darf **[A]**. Die Antwort trägt `Cache-Control: no-store`, damit
kein Zwischenspeicher eine signierte URL aufhebt **[A]**.

### 6.2 Lebensdauer

| Option | Laufzeit der signierten URL | Folge |
|---|---|---|
| **L1** | 15 Minuten, nie über `expires_at` des Ergebnisses | reicht vom Redirect bis zum Start des Downloads; ein abgebrochener Download wird über den stabilen Link neu begonnen |
| L2 | 1 Stunde (Vorgabe von botocore, §15) | auch für Download-Manager, die nach Pausen weiterlesen |
| L3 | 24 Stunden | für Weitergabe an Dritte; eine einmal geteilte URL ist einen Tag lang ein Schlüssel |

Oben begrenzt: Garage lehnt mehr als 7 Tage ab **[M]**, AWS ebenso **[S]**
(§15). Eine signierte URL wird beim **Start** einer Anfrage geprüft; ob ein
laufender Download über die Frist hinaus weiterläuft, ist nicht gemessen.

**Wie andere es machen [S]** (§15): Die openEO-API kennt den Fehler
`ResultLinkExpired` (`410`) mit dem Hinweis, die Links über
`GET /jobs/{job_id}/results` zu erneuern; eine Laufzeit schreibt sie nicht vor.
openEO Platform signiert dort je Abruf für 7 Tage, die Orders-API von Planet
gibt Links für 24 Stunden aus, botocore nimmt 1 Stunde als Vorgabe **[P]**.
R1 folgt dem openEO-Muster „Links je Abruf neu“, nur mit kurzer Laufzeit.

**Empfehlung L1** mit R1. `api` antwortet `410 Gone`, wenn `expires_at` weniger
als 60 Sekunden entfernt ist, statt eine fast tote URL auszugeben **[A]**.

### 6.3 Endpunkt für den Browser

Eine signierte URL ist an den Host gebunden, für den sie signiert ist (§3.3,
`403` bei anderem Host) **[M]**. `http://objectstore:3900` ist im Browser nicht
erreichbar.

| Option | Weg | Folge |
|---|---|---|
| **E1** | zwei Endpunkte in der Konfiguration: `S3_ENDPOINT` (intern, zum Hochladen und Löschen) und `S3_PUBLIC_ENDPOINT` (nur zum Signieren); lokal `http://localhost:3900`, in Produktion der öffentliche Endpunkt des Anbieters | gemessen ✅; Signieren öffnet keine Verbindung (§3.2); in Produktion meist beide gleich |
| E2 | ein Reverse-Proxy unter dem Host des Frontends (`/objectstore/…` → `objectstore:3900`) | der Pfad gehört zur Signatur; der Proxy müsste Präfix und `Host` umschreiben; nicht gemessen |
| E3 | `api` streamt (wie R3) | siehe dort |

**Empfehlung E1.** Lokal ist Port 3900 heute schon veröffentlicht
(`docker-compose.yml`) **[P]**. `config.py` verlangt für
`S3_PUBLIC_ENDPOINT` `https`, außer bei `localhost` und `127.0.0.1`
**[A]**. CORS braucht der Download über einen Link nicht; erst wenn das
Frontend Ergebnisse per `fetch` liest, kommt eine CORS-Regel auf den Bucket
(Garage kann das, `adr/0012` §5) **[A]**.

### 6.4 Zwei Schlüssel

| Option | Schlüssel | Folge |
|---|---|---|
| **S1** | `earthx-jobs` mit Lesen und Schreiben für den Worker; `earthx-api` nur mit Lesen für `api` | eine signierte URL kann nur, was ihr Schlüssel darf: kein PUT, kein DELETE (§3.3) **[M]**; die Schlüssel-ID in der URL gibt nichts preis |
| S2 | ein Schlüssel für beide | einfacher; jede signierte URL trägt die ID eines Schlüssels, der schreiben und die Ablaufregel löschen darf (§3.3) |

**Empfehlung S1.** Der Admin-Token und das RPC-Secret aus dem Volume
`objectstore-secrets` erreichen weder `api` noch `worker`; jeder Dienst sieht
nur die Dateien seines eigenen Schlüssels (§9.1) **[A]**.

### 6.5 Dateiname und Antwortkopf

Die signierte URL setzt `response-content-disposition` mit einem festen
Dateinamen aus Datensatz, Operator und Datum, nie mit AOI oder Hash. Garage
übernimmt den Kopf **[M]**. Der Name steht damit in der URL und im
Browser-Verlauf; deshalb dieselben Regeln wie für Logs (`adr/0014` §4.7)
**[A]**.

### 6.6 `400` statt `403`

Garage weist abgelaufene URLs mit `400 InvalidRequest` ab, AWS mit
`403 AccessDenied` (`adr/0012` §4.1) **[M]**. Mit R1 und L1 tritt das im Panel
kaum auf; Tests gegen den Speicher akzeptieren beides, wie
`compose/objectstore/smoke.py` heute **[P]**.

---

## 7. Ablauf nach 7 Tagen

### 7.1 Was „7 Tage“ heißt

- **Für den Nutzer:** Ab `expires_at` = Fertigstellung + 7 Tage gibt `api`
  keinen Link mehr heraus (`410`), und `GET /jobs/{jobID}` antwortet `404`,
  sobald die Zeilen gelöscht sind **[A]**.
- **Für die Bytes:** spätestens einen Tag später, durch Aufräumer oder Regel
  (§3.3) **[M]**.
- **Für Zeilen:** Job, Ergebnis, Rezept und Ereignisse mit `expires_at`
  (Spalte nach architekturplan 10, `result.expires_at`). Das Rezept lebt so
  lange wie das längste Ergebnis, das es verwendet; ein Rezept mit AOI ist
  personenbezogen (Q8) **[A]**.

### 7.2 Zwei Schichten

| Option | Weg | Folge |
|---|---|---|
| **A1** | Aufräumer in `jobs`, stündlich: löscht zuerst die Objekte unter `results/{result_id}/`, dann die Zeilen; dazu die Bucket-Regel als Netz | Objekte und Zeilen verschwinden gemeinsam; testbar mit eigener Uhr; ein Absturz zwischen beiden Schritten lässt höchstens Zeilen zurück, die `api` wegen `expires_at` schon nicht mehr bedient |
| A2 | nur die Bucket-Regel; Zeilen löscht ein eigener Lauf | Objekte und Zeilen laufen auf zwei Uhren auseinander; der Beleg hängt am Speicher, und der Schreibschlüssel kann die Regel löschen (§3.3) |
| A3 | nur der Aufräumer | ein Absturz oder abgebrochener Upload hinterlässt Waisen, die nie gehen |

**Empfehlung A1.** Wann und in welchem Prozess der Aufräumer läuft (geplanter
Job der Queue oder Schleife im Worker), legt `adr/0013` fest **[A]**.

### 7.3 Die Regel am Bucket

```json
{"ID": "results-7d", "Status": "Enabled", "Filter": {"Prefix": "results/"},
 "Expiration": {"Days": 7}, "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1}}
```

| Option | wer setzt sie | Folge |
|---|---|---|
| **W1** | `objectstore-init` über Garages Admin-API (`UpdateBucket`, `lifecycleRules`), in Produktion die Infrastruktur; `jobs` prüft beim Start lesend mit `GetBucketLifecycleConfiguration` und startet ohne passende Regel nicht | bleibt bei der Standardbibliothek in `bootstrap.py` (gemessen, §3.3); der Anwendungscode ändert nie die Bucket-Konfiguration |
| W2 | `jobs` setzt die Regel beim Start selbst | ohne Handarbeit auch in Produktion; der Anwendungsschlüssel braucht dann dort das Recht `s3:PutLifecycleConfiguration` |
| W3 | nur dokumentiert | nichts prüft, ob sie da ist |

**Empfehlung W1.** Die Prüfung beim Start ist mit dem Leseschlüssel möglich
(§3.3); `jobs` nutzt seinen eigenen.

**Andere Präfixe** (`tmp/` für abgebrochene Uploads, später Icechunk unter
`virtual/`, architekturplan 10) bekommen eigene Regeln, wenn sie entstehen.
Garage kennt im Filter nur Präfix und Größe (`adr/0012` §4.1) **[P]**.

### 7.4 Beleg nach `adr/0012` §9 Punkt 5

| Option | Was belegt den Ablauf | Aufwand |
|---|---|---|
| **B1** | (a) Test des Aufräumers mit injizierter Uhr gegen `moto` in `pytest`; (b) Schritt in `compose-topology`: Regel gesetzt und gelesen, Prüfung beim Start von `jobs`; (c) die Messung in §3.3 an der Binärdatei, wiederholt bei jedem Wechsel der Garage-Version | klein; (c) ist kein CI-Lauf |
| B2 | B1 und zusätzlich ein wöchentlicher CI-Job, der Garage aus dem Quelltext baut (dynamisch gelinkt) und den Lauf aus §3.3 mit `libfaketime` wiederholt | rund 7 Minuten Bau je Lauf ohne Cache **[M]**; Änderung an `.github/` |
| B3 | ein zeitgesteuerter Lauf über 24 Stunden mit `Days: 1` | ein Runner von GitHub läuft höchstens 6 Stunden je Job **[S]**; braucht einen eigenen Runner |

Warum nicht das offizielle Image mit `libfaketime`: Es ist eine statische
musl-Binärdatei ohne dynamischen Lader (§Methode) **[P]**; `LD_PRELOAD` greift
dort nicht **[A]**, nicht gemessen.

**Empfehlung B1.** Der Ablauf, den Nutzer sehen, hängt am Aufräumer und an
`expires_at` (A1), und genau das prüft (a) in jeder CI. Die Regel ist das Netz;
ihr Greifen ist für v2.4.1 hier gemessen.

---

## 8. Ablage und Cache

### 8.1 Schlüssel im Bucket

| Option | Schlüssel | Folge |
|---|---|---|
| **K1** | `results/{result_id}/{name}`, `result_id` zufällig (128 Bit), eigene Spalte | der Pfad steht in jeder signierten URL; er verrät weder Job noch Rezept; ein Cache-Treffer gibt dem zweiten Nutzer nicht die `jobID` des ersten |
| K2 | `results/{jobID}/{name}` | einfacher; bei einem Cache-Treffer sähe B in der URL die `jobID` von A und könnte dessen Status abfragen |
| K3 | `results/{hash}/{name}` | verboten (Q8): der Hash ist aus der AOI zurückrechenbar |

**Empfehlung K1.** Neben dem Ergebnis liegen `recipe.json`, `citation.bib` und
`attribution.txt` unter demselben Präfix (6.4, `adr/0014` §10) **[A]**.

### 8.2 Ergebnis ohne Fassung (offen aus `adr/0014` §14)

Fehlt einer Eingabe die Fassung, gibt es keinen Cache-Treffer (Q11). **Vorschlag:**
Das Ergebnis wird trotzdem gespeichert, 7 Tage, unter eigener `result_id`, nur
ohne Eintrag im Cache (`cacheable = false`). Sonst gäbe es für diese Aufträge
keinen Download. Eine kürzere Frist bräuchte einen zweiten Präfix mit eigener
Regel **[A]** (F9).

### 8.3 Restlaufzeit eines Treffers

Ein Ergebnis ist 7 Tage alt, wenn ein zweiter Nutzer denselben Auftrag
schickt. Ohne Regel bekäme er einen Link, der in Minuten erlischt.

| Option | Weg | Folge |
|---|---|---|
| **T1** | Treffer nur bei mindestens 24 Stunden Restlaufzeit; sonst rechnen | einfach; im schlimmsten Fall einmal je Woche neu gerechnet |
| T2 | Treffer kopiert das Objekt (`CopyObject`) unter neue `result_id` mit neuer Frist | jeder Treffer hat volle 7 Tage; doppelter Speicher für eine Weile |
| T3 | Treffer mit beliebiger Restlaufzeit | der Nutzer sieht die kurze Frist im Ergebnisdokument |

**Empfehlung T1.** Der Wert steht als Konstante neben der Frist (Q10) **[A]**.

---

## 9. Zugangsdaten, Logs, Produktion

### 9.1 Zugangsdaten nur aus der Umgebung

| Variable | Inhalt | lokal (compose) |
|---|---|---|
| `S3_ENDPOINT` | interner Endpunkt | `http://objectstore:3900` |
| `S3_PUBLIC_ENDPOINT` | Endpunkt für signierte URLs | `http://localhost:3900` |
| `S3_REGION` | Signaturregion (§3.2: muss passen) | `garage` |
| `S3_BUCKET` | Bucket | `earthx` |
| `S3_ACCESS_KEY` oder `S3_ACCESS_KEY_FILE` | Schlüssel-ID des Prozesses | Datei aus einem Volume je Dienst |
| `S3_SECRET_KEY` oder `S3_SECRET_KEY_FILE` | Secret des Prozesses | dito |

- Je Variable genau eine der beiden Formen; beide oder keine → Start mit
  Fehler, der keinen Wert nennt **[A]**.
- **Nie `AWS_ACCESS_KEY_ID` und `AWS_SECRET_ACCESS_KEY`:** rasterio würde sie in
  jedem Prozess an GDAL geben, sobald es eine `AWSSession` baut (§3.1) **[M]**.
  Die neutralen Namen gelten seit M3-23 (`adr/0012` F4).
- `objectstore-init` legt die zwei Schlüssel aus §6.4 an und schreibt sie in
  getrennte Volumes (oder Unterordner) für `api` und `worker`; das Volume mit
  Admin-Token und RPC-Secret bleibt bei `objectstore` und den
  Einmal-Schritten **[A]**. Die Form legt M4-06 fest.
- `.env` bleibt ohne Werte (`.env.example`); erzeugt wird wie heute.

### 9.2 Nichts in Logs

- **Logger:** `botocore` und `urllib3` kommen zu `_URL_LOGGING_LIBRARIES` in
  `earthx/logging.py` und werden damit auf `WARNING` gehoben, wie `httpx` seit
  M3-16 **[P]**. Grund: Bei `DEBUG` stehen Schlüssel-ID und Signatur im Log
  (§3.2) **[M]**.
- **Fehlertexte:** `objectstore/errors.py` übernimmt die Schwärzung aus
  `compose/objectstore/redact.py` (M3-23) für Schlüssel-ID und Secret; jede
  `ClientError` wird in eine eigene Fehlerklasse ohne Originaltext übersetzt
  **[A]**. Grund: Garage nennt die Schlüssel-ID in `AccessDenied` (§3.2) **[M]**.
- **Signierte URLs** sind Schlüssel auf Zeit. Sie erscheinen in keinem Log; die
  Zeile von `RequestIdMiddleware` nennt nur Pfad und Status, nie den
  `Location`-Kopf **[P]** (`earthx/logging.py`).
- Ein Test je Weg, nach dem Muster der sechs Tests aus der M3-23-Nachbesserung.

### 9.3 Produktion mit verwaltetem S3

Ohne Codeänderung, nur andere Werte: `S3_ENDPOINT` und `S3_PUBLIC_ENDPOINT` auf
den Endpunkt des Anbieters, `S3_REGION` auf dessen Region, Schlüssel aus dessen
Secret-Verwaltung. Voraussetzungen beim Anbieter (§15):

- signierte URLs mit SigV4;
- Pfad-Stil-Adressierung (sonst eine Einstellung mehr, `S3_ADDRESSING_STYLE`,
  ohne Codeänderung) **[A]**;
- Lebenszyklus mit Präfix und Abbruch liegengebliebener Multipart-Uploads.
  Fehlt das, trägt der Aufräumer (A1) den Ablauf allein, und `jobs` startet nur
  mit ausdrücklichem Verzicht auf die Prüfung (F8) **[A]**;
- Rechte je Schlüssel getrennt nach Lesen und Schreiben (S1).

Stand bei EU-Anbietern, nur aus Suchtreffern und Doku-Quellen auf GitHub,
weil die Doku-Hosts aus der Sitzung gesperrt waren **[S]** (§15):

| Anbieter | SigV4 signiert | Ablauf mit Präfix | Abbruch Multipart | Pfad-Stil |
|---|---|---|---|---|
| Hetzner | ja | ja | ja | ja |
| Scaleway | ja | ja | ja | ja |
| OVHcloud | ja | ja | ja | ja |
| IONOS | unbelegt | ja | ja | ja |
| Exoscale | ja | ja | uneinheitlich berichtet | unbelegt |

Die Wahl des Anbieters ist Sache des ersten öffentlichen Deployments; vorher
prüft eine Sitzung mit Zugang zur Doku die Zeilen am Primärtext.

---

## 10. Kriterienmatrix

Bewertung **[A]** aus §3–§9: ✅ erfüllt, ⚠ mit Einschränkung, ❌ nicht erfüllt.

**Clients**

| # | `botocore` | `boto3` | `aiobotocore` | `minio` | `obstore` | eigener SigV4 |
|---|---|---|---|---|---|---|
| K1, K2 Grenzen | ✅ eine Ausnahme | ✅ eine Ausnahme | ⚠ bringt `aiohttp` mit | ✅ | ⚠ öffnet die Liste für den Client aus `adr/0006` | ⚠ braucht einen allgemeinen HTTP-Client |
| K3 fester Endpunkt | ✅ gemessen | ✅ | ✅ | ✅ | ✅ | ✅ |
| K4 kein neuer Weg nach außen | ✅ gemessen | ❌ rasterio fragt den Metadatendienst | ✅ | ✅ | ✅ | ✅ |
| K5 signierte URLs, Dateiname | ✅ gemessen | ✅ | ✅ | ✅ | ⚠ unbelegt | ✅ |
| K8 verwaltetes S3 | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠ jede Abweichung selbst |
| K9 Teile | ✅ drei Pakete | ⚠ fünf | ❌ elf, enge Bindung | ⚠ eigene Kryptografie | ✅ eines | ⚠ eigener Code |

**Durchsetzung des Ablaufs**

| # | A1 Aufräumer + Regel | A2 nur Regel | A3 nur Aufräumer |
|---|---|---|---|
| K6 Frist für Objekte | ✅ | ⚠ Schreibschlüssel kann Regel löschen | ⚠ Waisen bleiben |
| K6 Frist für Zeilen | ✅ gemeinsam | ⚠ zwei Uhren | ✅ |
| K6 Beleg in CI | ✅ eigene Uhr | ❌ nur an der Binärdatei | ✅ |
| K8 verwaltetes S3 | ✅ auch ohne Regel | ⚠ hängt am Anbieter | ✅ |

---

## 11. Empfehlung

**Modul `earthx.objectstore` mit `botocore` als einzigem Client, erlaubt durch
eine Zeile `ignore_imports`; signierte URLs nur über einen Redirect aus `api`,
15 Minuten, für einen eigenen öffentlichen Endpunkt und mit einem
Leseschlüssel; Ablauf durch einen Aufräumer in `jobs` und eine Bucket-Regel als
Netz.**

Begründung **[A]**, aus §3–§10:

1. **Die Ausnahme ist ein Import, kein Modul.** `http-only-in-gateway` bleibt
   für jedes andere Modul so streng wie heute und wird um `botocore` und
   `urllib3` verschärft; die Ausnahme passt auf genau eine Datei (§3.5, §3.6).
2. **`boto3` bliebe nicht ohne Folgen.** Es ändert rasterio in allen vier
   Prozessen (§3.1). `botocore` allein kann alles Nötige (§3.3).
3. **Signierte URLs leben kurz und können wenig.** Der Redirect hält den Link
   im Panel stabil, die URL selbst 15 Minuten; der Leseschlüssel kann weder
   schreiben noch löschen (§3.3, §6).
4. **Der Ablauf hängt nicht an einer Stelle.** Der Aufräumer trägt die Frist
   für Objekte und Zeilen und ist in jeder CI testbar; die Regel fängt Waisen
   und ist an Garage v2.4.1 gemessen (§3.3, §7).
5. **Nichts davon ist an Garage gebunden.** Produktion braucht nur andere
   Variablen (§9.3).

**Was dagegen spricht, offen benannt:**

- Zwei Endpunkte und zwei Schlüssel sind mehr Konfiguration als einer.
- Multipart ohne `s3transfer` ist eigener Code, wenn auch kurz.
- Der Beleg der Bucket-Regel ist eine Sitzungsmessung, kein CI-Lauf (B2 wäre
  einer).
- Die Frist ist für Bytes 7 bis 8 Tage, für Nutzer genau 7.

---

## 12. Was M4-06 bauen und die CI belegen muss

1. Modul, Verträge und Tests aus §4; `lint-imports` grün mit der einen
   Ausnahme; Gegenprobe im PR (ein zweiter `botocore`-Import bricht).
2. Test, dass `boto3` und `s3transfer` nicht in `requirements.lock` stehen.
3. `bootstrap.py`: zwei Schlüssel (§6.4), Regel über die Admin-API (§7.3),
   getrennte Volumes (§9.1); weiterhin keine Kennung in der Ausgabe.
4. `compose/objectstore/smoke.py` oder ein neuer Schritt: Leseschlüssel kann
   nicht schreiben; Regel ist gesetzt; signierte URL für den öffentlichen
   Endpunkt geht, für den internen über einen anderen Host nicht.
5. Tests mit `moto`: Upload, Multipart, Signieren mit Dateinamen, Löschen,
   Aufräumer mit injizierter Uhr, `410` ab `expires_at`, Schwärzung,
   Konfigurationsfehler ohne Werte im Text.
6. Test, dass der Client mit `proxies={}` gebaut ist und ein
   `HTTP_PROXY` in der Umgebung ihn nicht umleitet (§3.2).

---

## 13. Was dieses ADR nicht entscheidet

- Queue, Prozess und Takt des Aufräumers, Vertragsform für psycopg in `jobs`:
  `adr/0013`.
- Form des Ergebnisdokuments und der Statuswerte: `adr/0014` §9.
- Anzeige von Ergebnissen auf der Karte (der `tiler` müsste dann aus dem
  eigenen Speicher lesen, an `gateway` vorbei): nicht in M4a; eigene Frage, wenn
  sie kommt.
- Virtuelle Stores (Icechunk) im Speicher: später.
- Die selbst gehostete Ausgabe und Produktion im Einzelnen: erstes öffentliches
  Deployment.

---

## 14. Fragen an Otto

**F1 — Name des Moduls (§4.1)**
1. `earthx.objectstore` **(Empfehlung)**
2. `earthx.services`
3. `earthx.storage`

**F2 — Wie der Client erlaubt wird (§4.2, §3.5)**
1. Zeile in 3.1 (`objectstore` importiert nichts Fachliches; `jobs` darf es);
   `objectstore` als Quelle in `http-only-in-gateway` mit genau einer
   `ignore_imports`-Zeile `earthx.objectstore.client -> botocore`; Liste um
   `botocore`, `urllib3`, `s3transfer`, `aiobotocore`, `aioboto3`, `minio`
   verschärft; Kettenvertrag für `processing` um `earthx.objectstore` und
   `botocore` **(Empfehlung)**
2. Wie 1, aber `objectstore` nicht in `http-only-in-gateway`, sondern mit
   eigenem Vertrag und eigener Liste ohne `botocore`
3. Wie 1, ohne die Verschärfung um `urllib3` und die übrigen Clients

**F3 — Client (§5, §3.1, §3.4)**
1. `botocore` allein, `boto3` nie im Image (Wächtertest),
   `AWS_EC2_METADATA_DISABLED=true` im Dockerfile **(Empfehlung)**
2. `boto3`
3. `obstore` (von der Verbotsliste nehmen, nur für `objectstore`)
4. eigener SigV4-Client

**F4 — Weg der signierten URL zum Browser (§6.1)**
1. Stabiler Link in `api`, `303` auf eine frisch signierte URL
   **(Empfehlung)**
2. Signierte URLs direkt im Ergebnisdokument
3. `api` streamt

**F5 — Lebensdauer der signierten URL (§6.2)**
1. 15 Minuten, nie über `expires_at`; `410` ab weniger als 60 Sekunden
   Restlaufzeit **(Empfehlung)**
2. 1 Stunde
3. 24 Stunden

**F6 — Endpunkt und Schlüssel (§6.3, §6.4)**
1. Zwei Endpunkte (`S3_ENDPOINT`, `S3_PUBLIC_ENDPOINT`), zwei Schlüssel
   (Worker liest und schreibt, `api` nur lesen) **(Empfehlung)**
2. Zwei Endpunkte, ein Schlüssel
3. Reverse-Proxy unter dem Host des Frontends, ein Schlüssel

**F7 — Durchsetzung der 7 Tage (§7.2)**
1. Aufräumer in `jobs` für Objekte und Zeilen, Bucket-Regel als Netz
   **(Empfehlung)**
2. Nur Bucket-Regel; Zeilen getrennt
3. Nur Aufräumer

**F8 — Wer setzt die Bucket-Regel (§7.3)**
1. `objectstore-init` über die Admin-API, in Produktion die Infrastruktur;
   `jobs` prüft beim Start lesend und startet ohne Regel nicht
   **(Empfehlung)**
2. `jobs` setzt sie beim Start selbst
3. Nur dokumentiert

**F9 — Beleg des Ablaufs (§7.4)**
1. Aufräumer-Test mit eigener Uhr in jeder CI, Regel in `compose-topology`
   gesetzt und gelesen, Greifen der Regel durch die Messung hier, wiederholt
   bei jedem Garage-Wechsel **(Empfehlung)**
2. Wie 1, dazu ein wöchentlicher CI-Job mit Garage aus dem Quelltext und
   `libfaketime`
3. Lauf über 24 Stunden auf einem eigenen Runner

**F10 — Ablage und Ergebnis ohne Fassung (§8.1, §8.2)**
1. `results/{result_id}/{name}` mit eigener zufälliger `result_id`; Ergebnisse
   ohne Fassung ebenso 7 Tage, nur ohne Cache-Eintrag **(Empfehlung)**
2. `results/{jobID}/{name}`; sonst wie 1
3. Wie 1, aber Ergebnisse ohne Fassung nur 24 Stunden (zweiter Präfix)

**F11 — Restlaufzeit eines Cache-Treffers (§8.3)**
1. Treffer nur bei mindestens 24 Stunden Restlaufzeit **(Empfehlung)**
2. Treffer kopiert das Objekt mit neuer Frist
3. Treffer mit beliebiger Restlaufzeit

**F12 — Zugangsdaten und Logs (§9.1, §9.2)**
1. `S3_*` und `S3_*_FILE`, nie `AWS_*`; ein Volume je Dienst; `botocore` und
   `urllib3` auf `WARNING`; Fehlertexte geschwärzt und übersetzt
   **(Empfehlung)**
2. Wie 1, aber nur `S3_*` als Wert (ohne `_FILE`); compose reicht die Werte aus
   den Dateien über ein Startskript durch

---

## 15. Quellen

**Primär, in der Sitzung gelesen [P]:**

- Garage v2.4.1 (Commit `268334b`): `src/model/s3/lifecycle_worker.rs`
  (Z. 63–110, 195–228, 280–320, 395–420), `src/api/s3/router.rs`
  (`authorization_type`, Z. 579–652; `response-content-disposition`, Z. 701),
  `src/api/common/signature/payload.rs` (Z. 505–565: „Date is too old“,
  „X-Amz-Expires may not exceed a week“), `src/api/admin/api.rs` (Z. 966–980,
  `UpdateBucketRequestBody.lifecycle_rules`), `src/api/admin/bucket.rs`
  (Z. 362–376), `Dockerfile`, `flake.nix` (Z. 45–48) —
  <https://github.com/deuxfleurs-org/garage>
- rasterio 1.5.2 im Projekt-venv: `rasterio/session.py` (Z. 12–16, 83–128,
  150–197, 280–296), `rasterio/env.py` (Z. 172–210, 440–465).
- Wheels von PyPI, `METADATA`: `aiobotocore` 3.9.2
  (`Requires-Dist: botocore<1.43.107,>=1.43.101`), `moto` 5.2.3
  (`Requires-Dist: boto3>=1.9.201`).
- EarthX: `.importlinter`, `backend/tests/test_module_boundaries.py`,
  `backend/tests/earthx/test_no_outbound_outside_gateway.py`,
  `backend/earthx/logging.py`, `backend/earthx/gateway/gdal.py`,
  `backend/earthx/readers/cog.py`, `backend/requirements.lock`,
  `compose/objectstore/bootstrap.py`, `redact.py`, `smoke.py`,
  `docker-compose.yml`.

- botocore 1.43.103 (Wheel von PyPI): `signers.py` Z. 757, `args.py`
  Z. 388–389, `endpoint.py` Z. 412–413 und 435–438, `utils.py` Z. 420 und
  3194–3198, `configprovider.py` Z. 195–204.

**Sekundär [S]** (Recherche-Agent; Seiten abgerufen und von einem Hilfsmodell
zusammengefasst, Wortlaut nicht selbst geprüft; gesperrt waren u. a.
`docs.aws.amazon.com` und die Doku-Hosts von Hetzner, Scaleway, OVHcloud,
IONOS und Exoscale):

- PyPI JSON zu `boto3`, `botocore`, `s3transfer`, `aiobotocore`, `aioboto3`,
  `minio`, `obstore`, `requests-aws4auth`:
  <https://pypi.org/pypi/{name}/json>
- aiobotocore, Changelog: <https://raw.githubusercontent.com/aio-libs/aiobotocore/master/CHANGES.rst>
- aioboto3, Commits: <https://github.com/terricain/aioboto3/commits/main>
- minio-py, Releases und Commits: <https://github.com/minio/minio-py/releases>,
  <https://github.com/minio/minio-py/commits/master>; API:
  <https://raw.githubusercontent.com/minio/minio-py/master/docs/API.md>
- obstore, Signieren:
  <https://raw.githubusercontent.com/developmentseed/obstore/main/obstore/python/obstore/_sign.pyi>
- boto3 1.36, neue Prüfsummen: <https://github.com/boto/boto3/issues/4392>;
  Brüche bei anderen Anbietern: <https://github.com/seaweedfs/seaweedfs/issues/6548>,
  <https://github.com/kubernetes-sigs/prow/issues/970>
- AWS, signierte URLs bis 7 Tage:
  <https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html>
- AWS, Lebenszyklus „rounding the resulting time to the next day midnight
  UTC“ und asynchrones Löschen (archivierte Doku):
  <https://raw.githubusercontent.com/awsdocs/amazon-s3-developer-guide/master/doc_source/intro-lifecycle-rules.md>,
  <https://raw.githubusercontent.com/awsdocs/amazon-s3-developer-guide/master/doc_source/lifecycle-expire-general-considerations.md>
- openEO, `ResultLinkExpired`:
  <https://raw.githubusercontent.com/Open-EO/openeo-api/draft/errors.json>;
  openEO Platform, 7 Tage: <https://docs.openeo.cloud/federation/>
- Planet Orders, 24 Stunden: <https://docs.planet.com/develop/apis/orders/mechanics/>
- Scaleway, Lebenszyklus:
  <https://raw.githubusercontent.com/scaleway/docs-content/main/pages/object-storage/api-cli/lifecycle-rules-api.mdx>
- OVHcloud, Lebenszyklus und signierte URLs:
  <https://raw.githubusercontent.com/ovh/ovhcloud-docs/develop/docs/en/guides/storage-and-backup/object-storage/s3-bucket-lifecycle.mdx>,
  <https://raw.githubusercontent.com/ovh/ovhcloud-docs/develop/docs/en/guides/storage-and-backup/object-storage/s3-share-object-externally.mdx>
- Hetzner: <https://docs.hetzner.com/storage/object-storage/howto-protect-objects/manage-lifecycle/>
- IONOS: <https://docs.ionos.com/cloud/storage-and-backup/ionos-object-storage/settings/lifecycle>
- Exoscale: <https://community.exoscale.com/product/storage/object-storage/how-to/bucketlifecycle/>
- GitHub Actions, höchstens 6 Stunden je Job auf gehosteten Runnern:
  <https://docs.github.com/en/actions/administering-github-actions/usage-limits-billing-and-administration>

---

## 16. Messanhang

Alle Skripte und Daten lagen im Kratzverzeichnis der Sitzung, nicht im Repo.
Schlüssel waren Wegwerfwerte, nur auf `127.0.0.1`.

### 16.1 Garage bauen und starten (§3.3)

```sh
git clone --depth 1 --branch v2.4.1 https://github.com/deuxfleurs-org/garage
cargo build --release --locked -p garage          # 6 min 24 s, rustc 1.97.0
OBJECTSTORE_SECRETS_DIR=<dir> python compose/objectstore/bootstrap.py secrets
GARAGE_CONFIG_FILE=garage.toml GARAGE_RPC_SECRET_FILE=<dir>/rpc_secret \
  GARAGE_ADMIN_TOKEN_FILE=<dir>/admin_token garage server --single-node
OBJECTSTORE_SECRETS_DIR=<dir> python compose/objectstore/bootstrap.py init \
  --admin-url http://127.0.0.1:3903
```

`garage.toml` wie `compose/objectstore/garage.toml`, aber Ordner im
Kratzverzeichnis und alle Adressen auf `127.0.0.1`.

### 16.2 Prüflauf (§3.2, §3.3)

`botocore` 1.43.103 allein auf `PYTHONPATH`, Client mit Pfad-Stil, SigV4,
Region `garage`, Prüfsummen `when_required`. In dieser Reihenfolge:

1. Leseschlüssel über die Admin-API (`CreateKey`, `AllowBucketKey` mit
   `read: true`).
2. `PutObject` 200 kB unter `results/r1/`, Marker unter `keep/`, Multipart
   5 MiB + 5 MiB + 1 234 B unter `results/r2/`, ein offener Multipart unter
   `results/r3/`.
3. Mit dem Leseschlüssel signiert: GET, PUT, DELETE; Lebenszyklus lesen und
   setzen.
4. Mit dem Schreibschlüssel: Lebenszyklus setzen, löschen, wieder setzen.
5. Für `http://objectstore:3900` signiert, über `127.0.0.1:3900` abgerufen,
   einmal mit und einmal ohne `Host`-Kopf; für `http://localhost:3900`
   signiert, mit `ResponseContentDisposition` und mit `Range`.
6. Region `us-east-1` gegen `garage`; `ExpiresIn` 604 801; `ExpiresIn` 1, nach
   2,5 s abgerufen.
7. `ClientError` mit falschem Secret und mit unbekanntem Schlüssel.
8. Logger auf `INFO` und `DEBUG`, Ausgabe nach Schlüssel-ID, Secret und
   Signatur durchsucht.
9. Admin-API: `UpdateBucket` mit `lifecycleRules: []`, dann mit der Regel aus
   §7.3; `GetBucketInfo` und `GetBucketLifecycleConfiguration` zurückgelesen.

### 16.3 Ablauf mit verstellter Uhr (§3.3)

```sh
LD_PRELOAD=<libfaketimeMT.so.1> FAKETIME=+8d FAKETIME_DONT_FAKE_MONOTONIC=1 \
  garage server --single-node          # Neustart je Stufe: +1d, +2d, +7d, +8d
# Warten auf die Logzeile „Lifecycle worker finished for <Datum>“,
# dann ListObjectsV2 und ListMultipartUploads mit derselben FAKETIME
```

`libfaketime` 0.9.10 aus `libfaketime_0.9.10-2.1_amd64.deb` (Ubuntu, universe),
mit `dpkg-deb -x` entpackt.

### 16.4 rasterio und `boto3` (§3.1)

```sh
python -m pip install --target <dir>/boto boto3==1.43.103
python -m pip install --target <dir>/botocore-only botocore==1.43.103
python -m http.server 8765 --bind 127.0.0.1      # dient srv/amazonaws.com/x.tif
env -u HTTPS_PROXY -u HTTP_PROXY -u AWS_ACCESS_KEY_ID -u AWS_SECRET_ACCESS_KEY \
  HOME=<leer> PYTHONPATH=<dir>/boto strace -f -e trace=connect \
  python open.py http://127.0.0.1:8765/amazonaws.com/x.tif
```

`open.py` öffnet die Adresse mit `rasterio.open`, liest ein 8 × 8-Fenster und
meldet, ob eine `AWSSession` entstanden ist. Synthetische COG 256 × 256,
`uint16`, Kacheln 64.

### 16.5 Clients und Proxy (§3.2, §3.4)

Proxy: Client gegen `http://objectstore.invalid:3900` mit `HTTP_PROXY` auf
`127.0.0.1:9`, einmal ohne und einmal mit `Config(proxies={})`, `strace -e
connect`.

`pip install --target` je Kandidat, Größe mit `du -sh`, neue Pakete gegen
`backend/requirements.lock` abgeglichen. Import und Client-Bau je dreimal in
frischen Prozessen, Zeit mit `time.perf_counter`, Speicher als Zuwachs von
`ru_maxrss`.

### 16.6 import-linter (§3.5)

Abzug von `backend/earthx` und `.importlinter` im Kratzverzeichnis; Modul
`objectstore` mit `client.py` (`import botocore.session`), `jobs/store_use.py`
importiert es; Verträge wie in §4.2; `lint-imports` 2.15 einmal sauber, einmal
mit den drei Verstößen aus §3.5.
