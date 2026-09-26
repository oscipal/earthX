# ADR 0012 — Objektspeicher: Ersatz für MinIO

- **Status:** Entwurf, wartet auf Otto. Die Fragen stehen in §10.
- **Datum:** 2026-09-26
- **Aufgabe:** M3-20 laut `docs/plans/m3-dritte-quelle-und-interface.md` §4 (P23).
- **Autonomiestufe:** C — nur gemessen, gelesen und berichtet. Kein Code, keine
  Änderung an `docker-compose.yml`, CI oder Registry. Die Übergangslösung
  `bitnamilegacy/minio` bleibt, bis Otto entscheidet.
- **Grundlage:** `architekturplan.md` 3.1, 3.2, 6.4, 6.5, 7.3, 7.4, 12.1, 12.3;
  `projektuebersicht.md` Prinzipien (Zustand in austauschbaren Diensten);
  `KLAERUNGEN.md` B8, B9; `adr/0001` §9.2; `adr/0002` §2; Entscheidungslog
  E6, E7 (19.09.2026), Zeilen vom 19.09.2026 (MinIO im Wartungsmodus) und
  26.09.2026 (Übergang `bitnamilegacy/minio`, Spike vorgezogen);
  `docs/plans/m1-08-compose-topologie.md`.
- **Betroffen:** `docker-compose.yml` (Dienst `minio`), `.github/workflows/ci.yml`
  (Job `compose-topology`), `.env.example`, `README.md`,
  `architekturplan.md` 12.1, `projektuebersicht.md`, `projektplan.md` (M1-Zeile,
  nur Wortlaut), `cloud-umgebung.md` §5; M4 (Ergebnisse, signierte URLs, Ablauf).

---

## Methode und Belegstufen

Gemessen in einer Cloud-Sitzung am 26.09.2026, rund 10:40–12:45 UTC. Belegstufen
wie in `adr/0009`:

- **M** — in dieser Sitzung selbst gemessen; Befehl im Messanhang §12.
- **P** — am Primärdokument gelesen (LICENSE, README, Doku im Repo, Quelltext,
  Commit, Advisory).
- **S** — Suchtreffer oder Sekundärquelle (Presse, Blog, CVE-Aggregator),
  Primärdokument nicht gelesen.
- **A** — eigene Ableitung aus M/P/S; ein Argument, kein Beleg.

Wo ein Beleg fehlt, steht „unbelegt“.

**Ohne Docker.** Die Sitzung hat einen Docker-Client, aber keinen Daemon
(`cloud-umgebung.md` §4), und der Blob-Speicher von Docker Hub
(`production.cloudfront.docker.com`) ist gesperrt **[M]**. Kein Image wurde
gezogen oder gestartet. Gemessen wurde stattdessen an **Binärdateien, die in
der Sitzung aus dem Quelltext gebaut wurden** — über den Go-Modul-Proxy
(`proxy.golang.org`), crates.io und `git clone` von GitHub, alle drei erreichbar
**[M]**. Das misst die Server selbst, nicht die offiziellen Images. Was nur ein
Image-Lauf in CI belegen kann, steht in §9.

**Erreichbar** waren `hub.docker.com` (API mit Tags, Digests, Datum),
`registry-1.docker.io` (Manifeste), `proxy.golang.org`, `index.crates.io`,
`static.crates.io`, `static.rust-lang.org`, `github.com` über `git`.
**Gesperrt** (403 auf CONNECT) waren `quay.io`, `dl.min.io`, `min.io`,
`blog.min.io`, `docs.min.io`, `garagehq.deuxfleurs.fr`, `git.deuxfleurs.fr`,
`rustfs.com`, `docs.rustfs.com`, `dl.rustfs.com`, `seaweedfs.com`,
`production.cloudfront.docker.com`, `sum.golang.org`; die GitHub-API ist auf
das eigene Repo beschränkt **[M]**. Aussagen, die an diesen Hosts hängen, sind
über den Quelltext im Git-Repo belegt **[P]** oder tragen **[S]**.

**Umfang der Abrufe.** Rund 60 einzelne Metadaten-Anfragen (Docker-Hub-API,
Registry-Manifeste, `git ls-remote`, Erreichbarkeit), gedrosselt auf höchstens
eine je Sekunde, dazu fünf flache `git clone` und die Paketdownloads der vier
Builds (Go-Proxy, crates.io, zwei Toolchains, `protoc` aus dem Ubuntu-Archiv,
zusammen rund 1 GB). Die Quellen der Plattform (Sentinel-2, EOPF, DEM) wurden
nicht berührt. Messungen am Speicher liefen nur gegen `127.0.0.1`.

Drei Recherche-Subagenten haben Sekundärquellen gesucht; jede Aussage aus ihren
Berichten, die hier als **P** steht, ist am Quelltext oder an einem in der
Sitzung selbst gelesenen Dokument nachgeprüft, sonst steht **S**.

---

## 1. Kontext und Frage

Der Objektspeicher steht in der Topologie als „S3-kompatibler Objektspeicher
(lokal MinIO)“ (`architekturplan.md` 12.1). Gebraucht wird er erst in **M4**:
Job-Ergebnisse mit Ablaufdatum, Auslieferung über signierte URLs (6.4, 7.4,
12.3), Upload durch die dünne Hülle um den Worker-Kern (7.3, B9). Heute schreibt
nichts hinein (E6); in CI läuft er nur, damit `compose-topology` die
Zieltopologie startet (E7). In Produktion ist ein verwalteter S3-Dienst
vorgesehen, nicht MinIO selbst (Log 19.09.2026). Zugleich ist die compose-
Topologie die Grundlage einer möglichen selbst gehosteten Ausgabe (12.1).

Seit dem 24.09.2026 sind die offiziellen MinIO-Images nicht mehr ziehbar; der
Dienst läuft übergangsweise auf `bitnamilegacy/minio` (Log 26.09.2026).

**Otto entscheidet** nach diesem ADR:

1. Welcher Speicher MinIO in `docker-compose.yml` und CI ersetzt.
2. Wann umgestellt wird (vor M4 oder mit dem ersten Test, der ihn braucht).
3. Wie lange `bitnamilegacy/minio` bleiben darf.

## 2. Kriterien

| # | Kriterium | Herkunft |
|---|---|---|
| K1 | Lizenz OSI-frei und vereinbar mit AGPL-3.0-or-later bei Betrieb als eigener Dienst; kein erkennbares Risiko eines Lizenzwechsels | Plan M3-20; ENTSCHEIDUNGEN §4 |
| K2 | Gepflegt: Releases, Sicherheitsfixes, Träger, Reife | Plan M3-20 |
| K3 | Offizielles, frei ziehbares Image mit nachvollziehbarer Herkunft, per Digest pinnbar | Plan M3-20; Log M1-08 (nie `latest`) |
| K4 | S3-Funktionen für M4: Multipart-Upload, vorsignierte URLs, Range-Reads für COG, Ablauf (Lebenszyklus), Bucket-Richtlinien | Plan M3-20; architekturplan 6.4, 7.4, 12.3 |
| K5 | Ressourcen für lokal und CI: Startzeit, Speicher, Größe | Plan M3-20 |
| K6 | Betriebsaufwand: Start ohne Handarbeit, Zugangsdaten aus Umgebungsvariablen, Healthcheck | Plan M3-20; `docker-compose.yml`, `.env.example` |
| K7 | Nähe zum verwalteten S3 in Produktion: derselbe Client-Code, keine produktspezifischen Admin-APIs im Pfad | architekturplan 12.1; A |

---

## 3. Lage bei MinIO

### 3.1 Chronologie

| Datum | Ereignis | Beleg |
|---|---|---|
| 2021 | Lizenz Apache-2.0 → AGPL-3.0 | LICENSE ist AGPL-3.0 **[P]**; Datum **[S]** (min.io gesperrt) |
| Feb.–Juni 2025 | Admin-Funktionen der Konsole aus der Community Edition entfernt, nur Objektbrowser bleibt | **[S]** Blocks & Files, 19.06.2025 |
| 23.07.2025 | Release `RELEASE.2025-07-23T15-54-02Z` — der Stand, den `bitnamilegacy/minio:2025.7.23-*` paketiert | Tag im Git-Repo **[M]**; Zuordnung Tag ↔ Image **[A]** |
| 19.08.2025 | Letzte Aktualisierung von `bitnamilegacy/minio`; Beschreibung „Legacy Bitnami images (no longer updated)“ | Docker-Hub-API **[M]** |
| Aug./Sep. 2025 | Bitnami verschiebt den freien Katalog nach `bitnamilegacy`; `bitnami/minio` hat keine öffentlichen Tags mehr | `bitnami/minio`: 0 Tags **[M]**; Hintergrund **[S]** |
| 15.10.2025 | Letzter Release-Tag `RELEASE.2025-10-15T17-29-55Z`; Commit „update README.md … to point to source only releases“; am selben Tag Sicherheitsfix `c1a4949` „check sub-policy properly“ (Service-Accounts konnten ihre Inline-Policy umgehen) | Git-Historie **[M]**, Commit-Text **[P]**; CVE-2025-62506 als Nummer dazu **[S]** |
| 04.12.2025 | „Maintenance Mode“ angekündigt (`minio/minio#21714`) | **[S]**, über Recherche |
| 12.02.2026 | Letzter Commit auf `master`: „clarify state of the project“; README beginnt mit „THIS REPOSITORY IS NO LONGER MAINTAINED“ und verweist auf AIStor Free/Enterprise | `git ls-remote`, Go-Proxy, README **[M]/[P]** |
| 25.04.2026 | Repo archiviert | **[S]** (GitHub-API außerhalb des Repo-Scopes) |
| 24.09.2026 | Offizielle Images nicht mehr ziehbar | Log 26.09.2026; heute: Docker-Hub-API kennt `minio/minio` und `minio/mc` nicht mehr („object not found“), Registry antwortet `401` **[M]**; `quay.io` aus der Sitzung gesperrt, dort unbelegt |

### 3.2 Gibt es noch einen offiziellen, frei ziehbaren Weg?

**Ja, nur aus dem Quelltext.** Das README nennt zwei Wege: `go install
github.com/minio/minio@latest` und ein eigenes Image aus dem Dockerfile
**[P]**. Gemessen:

- `go install` des letzten Release-Commits (`9e49d5e`) läuft über den Go-Proxy
  durch: 2 min, Binärdatei 152 MB, Go 1.24 **[M]**. Die Binärdatei meldet
  `DEVELOPMENT.GOGET` statt einer Version **[M]** — die Herkunft steht nur im
  eigenen Build-Protokoll.
- **Der dokumentierte Docker-Weg ist gebrochen:** Das `Dockerfile` im Repo
  beginnt mit `FROM minio/minio:latest` **[P]** — genau das Image, das es nicht
  mehr gibt (§3.1). `Dockerfile.scratch` (`FROM scratch`, kopiert die
  Binärdatei) ginge **[P]**; gebaut wurde es nicht (kein Docker).
- Die alten Binärdateien auf `dl.min.io` „will not receive updates“ **[P]**;
  der Host ist aus der Sitzung gesperrt.

Nach dem 12.02.2026 kommen keine Fixes mehr (**[P]**, README). Wer MinIO aus dem
Quelltext baut, übernimmt damit Bau, Image und jede künftige Sicherheitslücke
selbst **[A]**.

### 3.3 Wie lange taugt `bitnamilegacy/minio`?

- Das gepinnte Image (`2025.7.23-debian-12-r5`, Digest in `docker-compose.yml`)
  wurde am 19.08.2025 zuletzt gebaut und bekommt keine Updates **[M]/[P]**.
- Es liegt **vor** dem Sicherheitsfix vom 15.10.2025 (§3.1) und damit
  vermutlich in dessen Reichweite **[A]**. Für CI und lokal mit Wegwerf-
  Zugangsdaten und ohne Service-Accounts ist das ohne praktische Folge **[A]**;
  für eine selbst gehostete Ausgabe schließt es MinIO aus.
- Eine Löschfrist für `bitnamilegacy` ist nicht angekündigt (unbelegt); die
  Beschreibung sagt „should only be used for temporary migration purposes“
  **[S]**, über Recherche.
- Anonyme Pulls von Docker Hub sind ratenbegrenzt: Zwei Manifest-Abrufe für
  `bitnamilegacy/minio` bekamen `429` **[M]**. Die GitHub-Runner teilen sich
  ebenfalls IPs (unbelegt, ob der Job das trifft).

**Einschätzung [A]:** trägt als Übergang für Wochen bis wenige Monate, solange
Docker Hub das Repo hält; kein Weg in M4 hinein.

### 3.4 Forks und Distributionen

| Name | frei ziehbar | gepflegt | Beleg |
|---|---|---|---|
| `cgr.dev/chainguard/minio` | laut Anbieter ja, freie Stufe | täglich aus dem Quelltext neu gebaut — aber aus einem Quelltext, der selbst keine Fixes mehr bekommt | **[S]** |
| `pgsty/minio` (Pigsty) | ja, laut Bericht | Ein-Personen-Fork, stellt die Konsole wieder her | **[S]** |
| OpenMaxIO | — | nur Konsolen-Fork, laut Presse ins Stocken geraten | **[S]** |
| Bitnami Secure Images | nein, Abo | ja | **[S]** |

Keiner davon ändert, dass der MinIO-Kern nicht mehr gepflegt wird **[A]**.

---

## 4. Kandidaten

Mindestens Garage, SeaweedFS und RustFS (Plan M3-20); MinIO aus dem Quelltext
als Vergleichsbasis. Weitere in §4.5.

### 4.1 Garage (Deuxfleurs)

- **Lizenz:** AGPL-3.0 (LICENSE, `Cargo.toml`: `license = "AGPL-3.0"`) **[P]**.
  §13 der AGPL verpflichtet nur, wer Garage selbst ändert; als unveränderter
  eigener Dienst hinter der S3-API berührt es den Code von EarthX nicht — und
  EarthX ist ohnehin AGPL-3.0-or-later **[A]**, keine Rechtsberatung. Keine
  Enterprise- oder Open-Core-Variante gefunden **[S]**.
- **Pflege:** Tag `v2.4.1`, Commit vom 07.09.2026, Image vom 08.09.2026;
  davor `v2.2.0`–`v2.4.0` **[M]**. Docker Hub `dxflrs/garage` zuletzt
  25.09.2026 (Commit-Builds), 6,6 Mio. Pulls **[M]**. Träger: Kollektiv
  Deuxfleurs, mehrfach über NLnet/NGI gefördert (2021–2025) **[S]**. Keine
  CVE gefunden **[S]**.
- **Image:** `dxflrs/garage:v2.4.1`, ein einziger Layer, 28 MB (amd64), dazu
  arm64, arm und 386 **[M]**; das Dockerfile im Repo ist `FROM scratch` mit
  einer statischen Binärdatei **[P]**. Gebaut mit Nix in der Woodpecker-CI
  des Projekts (`.woodpecker/publish.yaml`), eine Signatur ist dort nicht zu
  finden **[P]**. Feste Versionstags, daneben Commit-Tags; auch auf crates.io
  (`garage = "2.4.1"`) **[M]**.
- **S3 laut eigener Kompatibilitätstabelle [P]:** Multipart vollständig;
  vorsignierte URLs „Implemented“; CORS „Implemented“; **Bucket-Policy
  „Missing“** (Rechte statt dessen je Schlüssel und Bucket, anonymes Lesen nur
  über den Website-Modus); Lebenszyklus „Partially implemented“ — nur
  `Expiration` und `AbortIncompleteMultipartUpload`, Präfix nur im `Filter`;
  keine Versionierung.
- **Start:** Konfigurationsdatei (`garage.toml`) ist Pflicht; `rpc_secret` und
  `admin_token` können aus `GARAGE_RPC_SECRET` bzw. `GARAGE_ADMIN_TOKEN`
  kommen **[P]** (`src/garage/secrets.rs`). Seit v2.x legt
  `garage server --single-node --default-bucket` Layout, Schlüssel und Bucket
  selbst an, aus `GARAGE_DEFAULT_ACCESS_KEY`, `GARAGE_DEFAULT_SECRET_KEY`,
  `GARAGE_DEFAULT_BUCKET` **[P]/[M]**. Schlüssel-IDs brauchen mindestens 8,
  Secrets mindestens 16 Zeichen **[P]** (`src/model/key_table.rs`); der
  heutige Platzhalter `MINIO_ROOT_USER=earthx` aus `.env.example` wird
  abgelehnt („Key identifiers should be at least 8 characters long“) **[M]**.
  Healthcheck `GET /health` auf dem Admin-Port („Garage is fully
  operational“) **[P]/[M]**. Das `scratch`-Image hat kein `curl`; als
  Healthcheck taugt `garage status` — Exit 0 in 0,06 s bei laufendem Knoten,
  Exit 1 ohne **[M]**. Region frei konfigurierbar (Beispiel `garage`); ein
  Client mit `us-east-1` wurde trotzdem angenommen **[M]**.
- **boto3 ≥ 1.36** schickt standardmäßig Prüfsummen als Trailer
  (`STREAMING-UNSIGNED-PAYLOAD-TRAILER`); Sekundärquellen nennen das als Bruch
  mit Garage **[S]**. Der Quelltext von v2.4.1 behandelt diesen Modus
  (`src/api/common/signature/mod.rs`) **[P]**, und mit boto3 1.43 gingen
  einfacher und Multipart-Upload durch (§5) **[M]** — für v2.4.1 erledigt.
- **Abweichung:** Eine abgelaufene vorsignierte URL beantwortet Garage mit
  `400 InvalidRequest` („Date is too old“) statt AWS' `403 AccessDenied`
  **[M]**. Abgewiesen wird sie; ein Test, der genau `403` erwartet, schlägt
  aber fehl **[A]**.
- **Build aus dem Quelltext:** `cargo build --release --locked` aus dem Tag
  `v2.4.1`, 6 min 16 s auf 4 Kernen, statische Binärdatei 56 MB **[M]**.

### 4.2 SeaweedFS

- **Lizenz:** Apache-2.0 **[P]** (LICENSE). Neben dem Open-Source-Kern gibt es
  eine Enterprise-Ausgabe; `weed version` wirbt selbst dafür **[M]**. Welche
  Funktionen nur dort liegen, ist unbelegt.
- **Pflege:** Tags `4.43`–`4.47` zwischen dem 21.08. und 14.09.2026, also etwa
  wöchentlich **[M]** (`git ls-remote`, Commit-Datum von `4.47`). Docker Hub
  `chrislusf/seaweedfs` zuletzt 26.09.2026, 26,7 Mio. Pulls, Images mit
  `.sig`-Artefakten (cosign-Namensschema) **[M]**. Hauptautor Chris Lu **[S]**.
- **Sicherheit:** mehrere CVEs 2026, darunter Path Traversal im S3-Gateway
  (CVSS 10, behoben in 4.30), fehlende Authentifizierung (9.8, < 4.24), SSRF
  (9.3, < 4.24), Umgehung über OIDC-JWT (≤ 4.39, behoben in 4.40) **[S]**
  (CVE-Aggregatoren, Advisories nicht selbst gelesen). Gemessen wurde 4.47.
  Aktive Sicherheitsarbeit, aber eine große Angriffsfläche **[A]**.
- **Image:** `chrislusf/seaweedfs:4.47`, 195 MB (amd64), dazu arm64, arm und
  386 **[M]**; gebaut von GitHub Actions aus `docker/Dockerfile.go_build`,
  finale Stufe `FROM alpine` mit `curl`, signiert mit cosign
  (`container_release_unified.yml`) **[P]**; feste Versionstags **[M]**.
- **S3:** alles aus K4 im Messlauf bestanden, dazu CORS und Bucket-Policy
  (§5) **[M]**. Übergänge zwischen Speicherklassen lehnt der Server ab
  **[P]**. Ablauf wird beim Schreiben als Volume-TTL gestempelt; eine spätere
  Regeländerung wirkt nicht rückwirkend auf schon geschriebene Objekte **[P]**
  (`s3api_bucket_lifecycle_fastpath_warn.go`).
- **Start:** `weed mini -dir=…` startet Master, Volume, Filer, S3, WebDAV,
  Iceberg-Katalog und Admin-Oberfläche in einem Prozess; Zugangsdaten aus
  `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` **[P]/[M]**. Healthcheck
  `GET /healthz` auf dem S3-Port **[P]/[M]**. Admin-Oberfläche ohne Passwort,
  wenn keins gesetzt ist **[P]** (`weed help mini`) — im Messlauf mit
  `-admin.ui=false` abgeschaltet; für compose müsste sie ebenfalls aus oder
  mit Passwort laufen **[A]**.
- **Build aus dem Quelltext:** `go build ./weed` aus dem Tag `4.47`, verlangt
  Go 1.26; 2 min 57 s, Binärdatei 221 MB **[M]**.

### 4.3 RustFS

- **Lizenz:** Apache-2.0 (LICENSE, Copyright RustFS, Inc.) **[P]/[S]**. Das
  Repo enthält einen **CLA**, der RustFS, Inc. erlaubt, Beiträge „under any
  license, including proprietary or commercial licenses“ weiterzugeben **[P]**
  (`CLA.md`). Das ist genau die Konstruktion, die einen späteren Lizenzwechsel
  wie bei MinIO möglich macht **[A]**.
- **Reife:** Tag `1.0.0` vom 16.09.2026, davor rund 100 Alpha-, 12 Beta- und
  6 RC-Stände **[M]** (`git ls-remote`). Docker-Hub-Beschreibung: „Do NOT use
  in production environments!“ **[S]**, über Recherche; das README enthält den
  Satz nicht mehr **[S]**. CVE-2025-68926 (CVSS 9.8): fest eingebautes
  gRPC-Token in `1.0.0-alpha.13` bis `alpha.77`, behoben Ende 2025 **[S]**.
  Ohne gesetzte Zugangsdaten fällt der Server auf `rustfsadmin`/`rustfsadmin`
  zurück; `crates/credentials/src/constants.rs` setzt beide Werte als
  Vorgabe **[P]**.
- **Image:** `rustfs/rustfs:1.0.0`, 110 MB (amd64), dazu arm64; sieben Layer
  **[M]**; Alpine-Basis mit `curl`, läuft als Nutzer `rustfs` **[P]**
  (`Dockerfile`); gebaut von GitHub Actions (`docker.yml`), keine Signatur in
  den Workflows gefunden **[P]**. Das Image setzt
  `RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS="*"` als Vorgabe **[P]**.
- **S3:** laut README Multipart, Versionierung, Lebenszyklus, Bucket-Policy,
  CORS **[S]**; im Messlauf bestätigt, soweit geprüft (§5) **[M]**.
  Admin-API unter `/rustfs/admin/v3/`, `mc admin` geht deshalb nicht **[S]**.
- **Start:** Zugangsdaten aus `RUSTFS_ACCESS_KEY`/`RUSTFS_SECRET_KEY`;
  Healthcheck `/health` **[P]/[M]** (`rustfs/src/server/prefix.rs`).
- **Lizenzschlüssel im Code:** RustFS 1.0 enthält eine Lizenzprüfung mit
  RSA-signierten Tokens und „Entitlements“ (`crates/license`,
  `rustfs/src/license.rs`, `rustfs/src/connect/license_renewal.rs`); jede
  S3-Anfrage läuft durch `license_check()` (`rustfs/src/storage/access.rs`)
  **[P]**. Ohne das Cargo-Feature `license` ist die Prüfung ein No-op, und die
  offiziellen Builds setzen es nicht (`.github/workflows/build.yml`) **[P]**.
  Heute also ohne Wirkung — aber die Technik für eine lizenzpflichtige
  Ausgabe liegt fertig im Kern **[A]**.
- **Messung:** alle Prüfungen aus §5 bestanden, einschließlich Policy, CORS
  und `x-amz-expiration` **[M]**. Der Tag `1.0.0` zeigt auf denselben Commit
  wie `1.0.0-preview.4`; die Binärdatei meldet sich so **[M]**. Build nur mit
  Rust 1.98.1 und `protoc`, 1 150 Crates **[M]**.

### 4.4 MinIO aus dem Quelltext (Vergleich)

Gemessen, damit die Kandidaten einen Maßstab haben (§5). Kein Kandidat:
ungepflegt (§3).

### 4.5 Weitere, geprüft und verworfen

| Kandidat | Lizenz | warum nicht | Beleg |
|---|---|---|---|
| Ceph RGW (microceph, `ceph/demo`) | LGPL-2.1 | für einen CI-Einzelcontainer zu schwer, lange Startzeit | **[S]** |
| Zenko CloudServer | Apache-2.0 | Pflegestand 2025/26 nicht belegbar | **[S]** |
| Versity S3 Gateway | Apache-2.0 | Gateway vor POSIX-Dateisystem; Lebenszyklus und Presigning nicht geprüft; ein möglicher Nachrücker, falls §8 scheitert | **[S]** |
| LocalStack (S3) | Apache-2.0, Pro-Teile kommerziell | Emulator für viele AWS-Dienste; Lizenzänderungen 2025/26 uneinheitlich berichtet | **[S]** |
| moto (Server-Modus) | Apache-2.0 | Test-Double, kein Speicher für die selbst gehostete Ausgabe; bleibt nach E7 für Unit-Tests | **[S]**; E7 |
| Adobe S3Mock | Apache-2.0 | kein Lebenszyklus, vorsignierte URLs ungeprüft | **[S]** |
| Apache Ozone | Apache-2.0 | mehrere Dienste, Lebenszyklus unvollständig | **[S]** |
| OpenStack Swift + s3api | Apache-2.0 | eigenes Temp-URL-Konzept, kein schlankes Einzelimage | **[S]** |

---

## 5. Messung: S3-Funktionen und Ressourcen — **[M]**

Jeder Server wurde als Einzelknoten auf `127.0.0.1` gestartet und mit
denselben Skripten geprüft (§12): `boto3` 1.43.103 mit Pfad-Stil und SigV4 —
also mit den Standard-Prüfsummen neuer SDKs —, dazu `rasterio` 1.5.1 / GDAL
3.12.4 aus dem Projekt-venv für Range-Reads auf einer synthetischen COG
(2048 × 2048, Kacheln 512, zwei Overviews). Wegwerf-Zugangsdaten, keine Daten
aus Quellen.

| Prüfung | MinIO (Quelltext, 15.10.2025) | Garage 2.4.1 | SeaweedFS 4.47 | RustFS 1.0.0 |
|---|---|---|---|---|
| Start bis Healthcheck `200` | 0,46–0,69 s | 0,13 s | 0,78–0,90 s | 0,14 s |
| RSS drei Sekunden nach dem Start | 127–133 MiB | 26–27 MiB | 119–146 MiB | 204 MiB ¹ |
| RSS nach dem Prüflauf | 140–149 MiB | 44–63 MiB | 198–222 MiB | 271 MiB ¹ |
| Binärdatei (selbst gebaut) | 152 MB | 56 MB | 221 MB | 374 MB ¹ |
| Offizielles Image (amd64, komprimiert) | — (`bitnamilegacy`: 99 MB) | 28 MB | 195 MB | 110 MB |
| `PutObject` mit Standard-Prüfsummen von boto3 1.43 | ✅ | ✅ | ✅ | ✅ |
| Multipart-Upload, drei Teile | ✅ | ✅ | ✅ | ✅ |
| Multipart abbrechen | ✅ | ✅ | ✅ | ✅ |
| `GetObject` mit `Range` → `206` | ✅ | ✅ | ✅ | ✅ |
| vorsignierte GET-URL mit `Range` | ✅ | ✅ | ✅ | ✅ |
| vorsignierte PUT-URL | ✅ | ✅ | ✅ | ✅ |
| abgelaufene URL abgewiesen | ✅ `403` | ⚠ `400` | ✅ `403` | ✅ `403` |
| URL auf anderen Schlüssel umgeschrieben → `403` | ✅ | ✅ | ✅ | ✅ |
| anonym ohne Policy → abgewiesen | ✅ | ✅ | ✅ | ✅ |
| Lebenszyklus `Expiration` angenommen | ✅ | ✅ | ✅ | ✅ |
| Header `x-amz-expiration` am neuen Objekt | ✅ | — | — | ✅ |
| Lebenszyklus `AbortIncompleteMultipartUpload` | ❌ `InvalidArgument` | ✅ | ✅ | ✅ |
| Bucket-Policy, anonymes Lesen auf Präfix | ✅ | ❌ `NotImplemented` | ✅ | ✅ |
| CORS je Bucket | ❌ `NotImplemented` | ✅ | ✅ | ✅ |
| `ListObjectsV2`, `DeleteObjects` | ✅ | ✅ | ✅ | ✅ |
| GDAL `/vsis3/`: Fenster und Overview | ✅ | ✅ | ✅ | ✅ |
| GDAL `/vsicurl/` mit vorsignierter URL | ✅ | ✅ | ✅ | ✅ |
| Verbindung nach außen während des Laufs ² | keine | keine | keine | keine |

MinIO, Garage und SeaweedFS wurden zweimal gemessen (Spannen), RustFS einmal.
¹ RustFS gebaut **ohne** das LTO-Profil des Projekts: mit `lto = "thin"` und
einer Codegen-Einheit brauchte ein einzelner `rustc` 8,8 GB und wurde vom
Speicherlimit der Sitzung beendet **[M]**; gebaut dann mit
`CARGO_PROFILE_RELEASE_LTO=false`, `CODEGEN_UNITS=16` in 70 min. Größe und
Speicher des offiziellen Builds weichen deshalb ab (unbelegt).
² `ss -tunp` alle 0,5 s über 60 s, Proxy-Variablen entfernt: kein Socket zu
einer Adresse außer `127.0.0.1`. Seltene Aufrufe (etwa eine tägliche
Update-Prüfung) schließt das nicht aus.

**Lesart.**

- **Ablauf:** Geprüft ist, dass der Server die Regel annimmt und zurückgibt.
  Ob er ein Objekt nach einem Tag wirklich löscht, ist bei **keinem**
  Kandidaten belegt — das kleinste Intervall der S3-API ist ein Tag. Belegen
  kann das nur ein Lauf über 24 Stunden oder ein Test mit verstellter Uhr (§9).
- **MinIO** lehnt CORS je Bucket ab (`NotImplemented`) und die Regel
  `AbortIncompleteMultipartUpload` (`InvalidArgument`); beides ist keine
  M4-Pflicht, zeigt aber, dass auch MinIO nicht „das S3“ ist.
- **`x-amz-expiration`** setzen nur MinIO und RustFS. Der Header ist
  Auskunft für Clients, keine Voraussetzung für den Ablauf selbst.

---

## 6. Kriterienmatrix

Bewertung **[A]** aus den Belegen in §3–§5: ✅ erfüllt, ⚠ mit Einschränkung,
❌ nicht erfüllt.

| # | Kriterium | MinIO (Quelltext / `bitnamilegacy`) | Garage 2.4.1 | SeaweedFS 4.47 | RustFS 1.0.0 |
|---|---|---|---|---|---|
| K1 | Lizenz, Wechselrisiko | ⚠ AGPL-3.0; Hersteller hat die freie Ausgabe aufgegeben | ✅ AGPL-3.0, kein CLA, kein Open-Core | ⚠ Apache-2.0; Enterprise-Ausgabe daneben | ⚠ Apache-2.0; CLA erlaubt proprietäre Weitergabe; Lizenzprüfung im Kern angelegt |
| K2 | Pflege, Sicherheit | ❌ keine Fixes seit 12.02.2026; Übergangs-Image vor einem Sicherheitsfix | ✅ Releases 2026, öffentliche Förderung, keine CVE gefunden | ⚠ wöchentliche Releases; mehrere kritische CVEs 2026, behoben | ⚠ 1.0 seit 16.09.2026; kritische CVE in der Alpha-Zeit |
| K3 | Offizielles Image, Herkunft | ❌ offiziell weg; `bitnamilegacy` ohne Updates; eigenes Image nötig | ✅ `scratch`, Projekt-CI (Nix); ohne Signatur | ✅ Projekt-CI, cosign-signiert | ⚠ Projekt-CI, ohne Signatur |
| K4 | S3 für M4 | ✅ alles außer CORS je Bucket | ⚠ alles außer Bucket-Policy | ✅ alles | ✅ alles |
| K5 | Ressourcen | ⚠ 99 MB Image, 127–133 MiB RSS | ✅ 28 MB, 26 MiB | ⚠ 195 MB, 119–146 MiB | ⚠ 110 MB, 204 MiB (Build ohne LTO) |
| K6 | Betrieb ohne Handarbeit | ✅ Zugangsdaten aus Env, `curl`-Healthcheck | ⚠ Konfigurationsdatei und RPC-Secret nötig; Bucket per Env | ✅ ein Befehl; Admin-UI abschalten | ⚠ Bucket nicht per Env; Vorgabe-Zugangsdaten, wenn Env fehlt |
| K7 | Nähe zu verwaltetem S3 | ✅ | ⚠ `400` statt `403` bei abgelaufener URL | ✅ | ✅ |

---

## 7. Was sich ändern müsste

### 7.1 `docker-compose.yml`, CI, `.env.example`, README

Heute hängen am Dienst `minio`: das Image mit Digest, `MINIO_ROOT_USER` und
`MINIO_ROOT_PASSWORD`, `MINIO_BROWSER`, die Ports 9000/9001, das Volume
`minio-data` unter `/bitnami/minio/data`, ein Healthcheck mit `curl` auf
`/minio/health/live` und `depends_on` in `api`, `tiler`, `worker`,
`harvester` **[P]**. CI schreibt die beiden `MINIO_*`-Werte in eine
Wegwerf-`.env`, nennt `minio` im Jobnamen und in beiden Warte-Schleifen
**[P]**.

Was sich je Kandidat ändert **[A]**, aus §4 und §5:

| Stelle | Garage | SeaweedFS | RustFS |
|---|---|---|---|
| Image | `dxflrs/garage:v2.4.1@sha256:9c96…` | `chrislusf/seaweedfs:4.47@sha256:ce9e…` | `rustfs/rustfs:1.0.0@sha256:8cc9…` |
| Start | `/garage server --single-node --default-bucket` | `weed mini -dir=/data -admin.ui=false` | Vorgabebefehl des Images |
| Konfiguration | neue Datei `garage.toml` im Repo, ohne Secrets, schreibgeschützt eingehängt | keine | keine |
| Zugangsdaten | `GARAGE_DEFAULT_ACCESS_KEY` (≥ 8 Zeichen), `GARAGE_DEFAULT_SECRET_KEY` (≥ 16), `GARAGE_DEFAULT_BUCKET`, `GARAGE_RPC_SECRET` (64 Hex-Zeichen) | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | `RUSTFS_ACCESS_KEY`, `RUSTFS_SECRET_KEY` |
| Bucket beim Start | ja (`--default-bucket`) | ja (`-bucket=…`) | nein, erst per Client |
| Ports | 3900 (S3), 3903 (Admin/Health) | 8333 (S3) | 9000 (S3), 9001 (Konsole) |
| Healthcheck | `["CMD", "/garage", "status"]` (kein `curl` im Image) | `curl -f` auf `/healthz` (`curl` im Image) | `curl -f` auf `/health` (`curl` im Image) |
| Weboberfläche | keine im Kern | Admin-UI, abschalten oder Passwort | Konsole (`--console-enable`, Port 9001) |

**Vorschlag unabhängig vom Produkt [A]:** Die Variablen in `.env` neutral
benennen (etwa `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`) und im
compose-Dienst auf die produktspezifischen Namen abbilden. Dann bleiben
`.env.example`, die CI-`.env` und später die Dienste `api` und `worker`
beim nächsten Wechsel unverändert, und der Dienstname (`objectstore` statt
`minio`) legt kein Produkt fest. Die Platzhalter müssen die Mindestlängen aus
§4.1 erfüllen.

Mitzuändern: Jobname und Dienstliste im CI-Job `compose-topology`,
`README.md` (Diensteliste, Fehlerbehebung „`minio`-Image“), der
Kommentarblock über dem Dienst in `docker-compose.yml`. `.github/` ändert nur
Otto oder eine Aufgabe, die es ausdrücklich verlangt (`CLAUDE.md`).

### 7.2 Plandokumente

- `architekturplan.md` 12.1: „S3-kompatibler Objektspeicher (lokal MinIO)“ →
  gewählter Speicher. Der Rest von 12.1, 6.4, 7.4, 12.3 bleibt: Er beschreibt
  S3-Funktionen, kein Produkt **[A]**.
- `projektuebersicht.md` (Prinzip „Zustand in austauschbaren Diensten“, dort
  „z. B. MinIO“) und `projektplan.md` (M1-Zeile): nur das Beispiel tauschen.
- `cloud-umgebung.md` §5: Satz zu MinIO; mit einer Binärdatei statt eines
  Containers wäre ein Objektspeicher auch in der Cloud-Sitzung startbar — das
  hat diese Messung gezeigt **[M]**.
- `adr/0002` §2 und E7 bleiben: `moto` für Unit-Tests, der echte Speicher als
  Dienst in CI.

### 7.3 Ist `gateway` betroffen?

**Von der Wahl des Produkts nicht [A].** Alle Kandidaten sprechen dieselbe
S3-API mit SigV4 und Pfad-Stil; der Client-Code ist derselbe.

**Aber M4 muss eine Frage lösen, die heute schon gilt — mit jedem Produkt:**
Der Speicher ist ein **Plattformdienst**, keine Datenquelle. `gateway` lässt
nur `https` zu (`policy.py`) und verweigert jede nicht global routbare Adresse
(`resolver.py`, `is_public`) **[P]**; ein Speicher unter `http://minio:9000`
im compose-Netz käme durch `gateway` nicht hindurch. Zugleich darf `boto3`
außerhalb von `gateway` nicht importiert werden (`.importlinter`, Vertrag
`http-only-in-gateway`) **[P]**. Die Hülle um den Worker (Upload) und `api`
(signierte URL erzeugen) brauchen also einen Weg zum eigenen Speicher, den die
Regeln heute nicht vorsehen. Das gehört in den M4-Plan (Frage F5), nicht in
die Produktwahl.

---

## 8. Empfehlung

**Garage v2.4.1 ersetzt MinIO in `docker-compose.yml` und CI; SeaweedFS ist
der Rückfallweg. Umstellen als eigene kleine Stufe-B-Aufgabe noch in M3, nicht
erst mit M4.**

Begründung **[A]**, aus §4–§6:

1. **K4 reicht für M4.** Alles, was 6.4, 7.4 und 12.3 verlangen — Multipart,
   vorsignierte URLs, Range-Reads, eine Ablaufregel nach Tagen (angenommen;
   ob sie greift, ist bei allen Kandidaten unbelegt, §5) — hat Garage im
   Messlauf bestanden, dazu CORS und die Abbruchregel für liegengebliebene
   Multipart-Uploads, die MinIO ablehnt. Was fehlt, ist die Bucket-Policy. M4
   braucht sie nach dem Plan nicht: Ergebnisse bleiben privat und gehen nur
   über signierte URLs hinaus (6.4); anonymes Lesen ist nirgends vorgesehen
   (Frage F3).
2. **Kleinste Angriffsfläche und bester Sicherheitsstand.** `scratch`-Image mit
   einer statischen Binärdatei, keine Weboberfläche, keine CVE gefunden;
   SeaweedFS hatte 2026 mehrere kritische Lücken im S3-Gateway selbst, RustFS
   eine kritische mit fest eingebautem Token.
3. **Am leichtesten für lokal und CI:** 28 MB Image, 0,13 s bis `healthy`,
   26 MiB Speicher im Leerlauf — rund ein Fünftel von MinIO und SeaweedFS.
4. **Lizenz ohne Wechselrisiko sichtbar:** AGPL-3.0 wie EarthX, gemeinnütziger
   Träger mit öffentlicher Förderung, kein CLA, keine Enterprise-Ausgabe.
   RustFS hat mit seinem CLA die Konstruktion, die MinIO den Wechsel erlaubt
   hat; SeaweedFS führt eine Enterprise-Ausgabe.
5. **Produktion bleibt verwalteter S3 (K7).** Garage wird nur über die
   S3-API angesprochen; produktspezifisch sind allein Start und Zugangsdaten im
   compose-Dienst. Die neutralen Variablennamen aus §7.1 halten das so.

**Was gegen Garage spricht, offen benannt:** eine Konfigurationsdatei mehr im
Repo; ein 64-stelliges `GARAGE_RPC_SECRET` mehr in `.env`; der Status `400`
statt `403` bei abgelaufenen URLs (§4.1); keine Bucket-Policy, falls ein
späterer Anwendungsfall doch anonymes Lesen will. Ändert sich F3, ist
SeaweedFS die Wahl: Es hat alle Prüfungen bestanden, startet mit einem Befehl
und bringt die Policy mit — zum Preis von 195 MB Image, sieben
Teildiensten in einem Prozess und einer schwereren Sicherheitsgeschichte.

**Nicht empfohlen:** RustFS — funktional im Messlauf vollständig und am
nächsten an MinIO, aber 1.0 erst seit zehn Tagen, Vorgabe-Zugangsdaten, ein
CLA für proprietäre Weitergabe und eine fertig angelegte Lizenzprüfung im
Kern; wer MinIO wegen des Rückzugs ersetzt, sollte nicht auf dieselbe
Konstruktion setzen **[A]**. MinIO aus dem Quelltext (ungepflegt; eigener Bau
ohne Fixes). Die Distributionen aus §3.4 (paketieren denselben ungepflegten
Kern).

**Warum schon in M3:** Der Pflicht-Check `compose-topology` hängt an einem
Image, das keine Updates bekommt, ratenbegrenzt gezogen wird und jederzeit
verschwinden kann (§3.3); das ist am 24.09.2026 mit den offiziellen Images
schon einmal passiert. Heute schreibt nichts in den Speicher (E6), der Umbau
ist also klein — `docker-compose.yml`, CI-Job, `.env.example`, README, eine
neue `garage.toml` — und berührt keinen Python-Code.

---

## 9. Was CI später belegen muss

Die Sitzung hat keine Images gestartet. Mit der Umstellung (eigene Aufgabe,
Stufe B) muss der Job `compose-topology` belegen:

1. Das gewählte Image zieht per Digest, startet und wird `healthy` — mit dem
   Healthcheck-Befehl, den das Image tatsächlich mitbringt (ein
   `scratch`-Image hat weder `curl` noch `wget`).
2. Zugangsdaten und Bucket entstehen ohne Handarbeit aus `.env`.
3. Neustart eines anderen Diensts lässt den Speicher `healthy` (bestehender
   Schritt).
4. Die Prüfungen aus §5 laufen gegen den Container (einmal, als eigener
   Schritt oder als Test mit Marker), damit der Befund dieser Binär-Messung am
   Image bestätigt ist.
5. Ablauf nach Lebenszyklus-Regel: in M4, sobald Ergebnisse geschrieben
   werden — ein Test mit verstellter Uhr oder ein zeitgesteuerter Lauf über
   24 Stunden; ohne diesen Beleg gilt „Ablauf“ als unbelegt.

---

## 10. Fragen an Otto

**F1 — Welcher Speicher ersetzt MinIO in compose und CI?**
1. Garage v2.4.1 — **Empfehlung** (§8)
2. SeaweedFS 4.47
3. RustFS 1.0.0
4. MinIO bleibt: `bitnamilegacy/minio` weiter oder eigener Bau aus dem
   Quelltext

**F2 — Wann wird umgestellt?**
1. Jetzt, als eigene Stufe-B-Aufgabe in M3 (nächste freie Nummer, M3-23),
   mit den Prüfungen aus §9 Punkte 1–4 — **Empfehlung**
2. Mit dem ersten M4-Plan, zusammen mit dem ersten Test, der den Speicher
   braucht
3. Erst, wenn `bitnamilegacy/minio` bricht

**F3 — Braucht M4 anonymes Lesen per Bucket-Policy?**
1. Nein: Ergebnisse bleiben privat und gehen nur über signierte URLs hinaus
   (6.4) — **Empfehlung**; dann trägt Garage
2. Ja: dann SeaweedFS (F1 Option 2)

**F4 — Sollen die `.env`-Variablen neutral heißen (`S3_ACCESS_KEY` …) und der
Dienst `objectstore` statt nach dem Produkt (§7.1)?**
1. Ja, mit der Umstellung aus F2 — **Empfehlung**
2. Nein, produktspezifische Namen wie heute

**F5 — Weg vom eigenen Code zum eigenen Speicher (für den M4-Plan, nicht
jetzt zu bauen).** `gateway` lässt heute nur `https` und öffentliche Adressen
zu, und `boto3` darf nur in `gateway` stehen (§7.3). Der Speicher ist ein
Plattformdienst im compose-Netz.
1. Der M4-Plan schlägt den Weg vor, Otto entscheidet dort — **Empfehlung**;
   dieser ADR legt nichts fest
2. Jetzt festlegen: ein eigener, schmaler S3-Client in `gateway` mit genau
   einem Endpunkt aus der Konfiguration, ausgenommen von der Prüfung auf
   öffentliche Adressen
3. Jetzt festlegen: ein eigenes Modul für Plattformdienste mit eigenem
   Importvertrag

**F6 — Messung der Images:** Die Messung hier lief an selbst gebauten
Binärdateien. Reicht das mit der Bestätigung in CI (§9 Punkt 4), oder soll
eine Sitzung mit Docker-Freigabe (`production.cloudfront.docker.com`,
`cloud-umgebung.md` §7) die Images vorher messen?
1. CI-Bestätigung in der Umstellungsaufgabe reicht — **Empfehlung**
2. Vorher eine Sitzung mit Freigabe

---

## 11. Quellen

**Primär, in der Sitzung gelesen [P]** (Quelltext jeweils am gemessenen Tag):

- MinIO: `README.md`, `LICENSE`, `Dockerfile`, `Dockerfile.scratch`, Commits
  `9e49d5e`, `c1a4949`, `7aac2a2` — <https://github.com/minio/minio>
- Garage v2.4.1: `LICENSE`, `Dockerfile`,
  `doc/book/reference-manual/s3-compatibility.md`,
  `doc/book/quick-start/_index.md`, `src/garage/server.rs`,
  `src/garage/secrets.rs`, `src/api/admin/router_v2.rs` —
  <https://github.com/deuxfleurs-org/garage> (Spiegel von
  `git.deuxfleurs.fr/Deuxfleurs/garage`)
- SeaweedFS 4.47: `LICENSE`, `docker/Dockerfile.go_build`,
  `weed/s3api/s3api_server.go`, `weed/s3api/s3api_bucket_handlers.go`,
  `weed/s3api/s3api_object_lifecycle_ttl.go`,
  `weed/s3api/s3api_bucket_lifecycle_fastpath_warn.go`, `weed help mini` —
  <https://github.com/seaweedfs/seaweedfs>
- RustFS 1.0.0: `LICENSE`, `CLA.md`, `README.md`, `Dockerfile`,
  `rustfs/src/server/prefix.rs`, `crates/credentials/src/constants.rs` —
  <https://github.com/rustfs/rustfs>
- Docker Hub API: `hub.docker.com/v2/repositories/<repo>/` und `/tags` für
  `minio/minio`, `minio/mc`, `bitnami/minio`, `bitnamilegacy/minio`,
  `dxflrs/garage`, `chrislusf/seaweedfs`, `rustfs/rustfs`
- EarthX: `docker-compose.yml`, `.github/workflows/ci.yml`, `.importlinter`,
  `backend/earthx/gateway/policy.py`, `backend/earthx/gateway/resolver.py`

**Sekundär [S]:**

- Blocks & Files, 19.06.2025, Entfernen der Admin-Konsole:
  <https://www.blocksandfiles.com/ai-ml/2025/06/19/minio-users-complain-after-admin-ui-removed-from-community-edition/1610856>
- MinIO Issue #21714 (Wartungsmodus, Archivierung):
  <https://github.com/minio/minio/issues/21714>
- CVE-2025-62506, Advisory GHSA-jjjj-jwhf-8rgr:
  <https://github.com/minio/minio/security/advisories/GHSA-jjjj-jwhf-8rgr>
- Bitnami-Katalogänderung: <https://github.com/bitnami/charts/issues/35164>
- Chainguard MinIO: <https://images.chainguard.dev/directory/image/minio/overview>
- InfoQ, 12/2025, MinIO-Alternativen (u. a. `pgsty/minio`):
  <https://infoq.com/news/2025/12/minio-s3-api-alternatives/>
- OpenMaxIO: <https://biggo.com/news/202510240123_OpenMaxIO-Object-Browser-Fork-Stalls>
- NLnet, Garage: <https://nlnet.nl/project/Garage/>
- Garage und boto3-Prüfsummen:
  <https://git.deuxfleurs.fr/Deuxfleurs/garage/issues/824>,
  <https://github.com/boto/boto3/issues/4435>
- SeaweedFS-CVEs: <https://www.strix.ai/cve/CVE-2026-54917>,
  <https://www.strix.ai/cve/CVE-2026-72920>,
  <https://www.strix.ai/cve/CVE-2026-73080>,
  <https://www.sentinelone.com/vulnerability-database/cve-2026-77298/>
- RustFS CVE-2025-68926:
  <https://github.com/rustfs/rustfs/security/advisories/GHSA-h956-rh7x-ppgj>
- RustFS, Docker Hub: <https://hub.docker.com/r/rustfs/rustfs>
- Vergleich Garage/SeaweedFS/RustFS/MinIO, 25.03.2026 (Durchsatz, nicht
  nachgemessen): <https://gist.github.com/komsit37/7029089c05b741931dd21ac49687dd4b>

---

## 12. Messanhang

Alle Skripte und Daten lagen im Kratzverzeichnis der Sitzung, nicht im Repo.
Zugangsdaten waren Wegwerfwerte, nur auf `127.0.0.1`.

### 12.1 Bau

```sh
# MinIO, letzter Release-Commit (Go 1.24.7; sum.golang.org gesperrt, daher GOSUMDB=off)
GOSUMDB=off GOFLAGS=-mod=mod go install github.com/minio/minio@9e49d5e7a648
# SeaweedFS 4.47 (verlangt Go 1.26; Toolchain-Zip direkt vom Go-Proxy)
git clone --depth 1 --branch 4.47 https://github.com/seaweedfs/seaweedfs
go1.26.8 build -o weed ./weed
# Garage v2.4.1
git clone --depth 1 --branch v2.4.1 https://github.com/deuxfleurs-org/garage
cargo build --release --locked -p garage
# RustFS 1.0.0 (verlangt Rust 1.98.1)
git clone --depth 1 --branch 1.0.0 https://github.com/rustfs/rustfs
cargo +1.98.1 build --release --locked -p rustfs
```

`GOSUMDB=off` schaltet die Prüfsummen-Datenbank ab; für eine Messung
vertretbar, für einen Bau, der ausgeliefert wird, nicht **[A]**.

### 12.2 Start

```sh
minio server <dir> --address 127.0.0.1:9100            # MINIO_ROOT_USER/_PASSWORD
weed mini -dir=<dir> -ip=127.0.0.1 -admin.ui=false       # AWS_ACCESS_KEY_ID/_SECRET_ACCESS_KEY
garage server --single-node --default-bucket             # GARAGE_CONFIG_FILE, GARAGE_RPC_SECRET,
                                                         # GARAGE_DEFAULT_ACCESS_KEY/_SECRET_KEY/_BUCKET
rustfs server <dir> --address 127.0.0.1:9200             # RUSTFS_ACCESS_KEY/_SECRET_KEY
```

`garage.toml` für die Messung: `db_engine = "sqlite"`,
`replication_factor = 1`, `rpc_bind_addr`/`rpc_public_addr` auf
`127.0.0.1:3901`, `[s3_api] s3_region = "garage"`, `api_bind_addr =
"127.0.0.1:3900"`, `[admin] api_bind_addr = "127.0.0.1:3903"`; kein Secret in
der Datei.

Startzeit: vom Start des Prozesses bis zur ersten `200` des Healthchecks, alle
100 ms abgefragt. Speicher: RSS des Serverprozesses samt Kindprozessen, drei Sekunden nach
`healthy` und nach dem Prüflauf.

### 12.3 Prüflauf S3

`boto3` 1.43.103, `addressing_style = "path"`, SigV4, Standard-Prüfsummen.
Je Server einmal, in dieser Reihenfolge:

1. `CreateBucket`
2. `PutObject` 1 MB
3. Multipart: 5 MiB + 5 MiB + 4 000 B, ETag mit Suffix `-3`, Größe per
   `HeadObject`
4. Multipart abbrechen
5. `GetObject` mit `Range: bytes=100-199` → `206`, Inhalt verglichen
6. vorsignierte GET-URL mit `Range: bytes=0-9` über `urllib`
7. vorsignierte PUT-URL, danach Inhalt gelesen
8. vorsignierte URL mit 1 s Gültigkeit, nach 2,5 s abgerufen → Abweisung
9. vorsignierte URL auf einen anderen Schlüssel umgeschrieben → `403`
10. anonymes `GET` ohne Policy → `401`/`403`
11. Lebenszyklus `Expiration: Days 1` auf Präfix `results/`, zurückgelesen;
    Header `x-amz-expiration` am neuen Objekt
12. dieselbe Regel plus `AbortIncompleteMultipartUpload`
13. Bucket-Policy: anonymes `s3:GetObject` auf `public/*`; anonymes `GET`
    dort → `200`, außerhalb → `403`
14. `PutBucketCors` für eine Origin, dann vorsignierte GET-URL mit `Origin` →
    `Access-Control-Allow-Origin`
15. `ListObjectsV2`, `DeleteObjects`

### 12.4 Prüflauf GDAL

Synthetische COG, 2048 × 2048 `uint16`, `DEFLATE`, Kacheln 512, Overviews
2 und 4, 0,9 MB, per `upload_file` hochgeladen. Gelesen mit `rasterio` aus dem
Projekt-venv, einmal über `/vsis3/` (`AWS_S3_ENDPOINT`,
`AWS_VIRTUAL_HOSTING=FALSE`, `AWS_HTTPS=NO`), einmal über `/vsicurl/` mit
einer vorsignierten URL: ein 64 × 64-Fenster aus voller Auflösung (mit dem
erwarteten Muster verglichen) und die erste Overview-Stufe ganz.

### 12.5 Metadaten

```sh
curl https://hub.docker.com/v2/repositories/<repo>/            # Status, Datum, Pulls
curl https://hub.docker.com/v2/repositories/<repo>/tags/<tag>  # Digest, Größe je Architektur
curl -H "Authorization: Bearer <anonymes Token>" \
     https://registry-1.docker.io/v2/<repo>/manifests/<tag>    # Layer; Blob → 307 auf gesperrten CDN
git ls-remote --tags https://github.com/<repo>                  # Tags und Commits
curl https://proxy.golang.org/github.com/minio/minio/@latest   # letzter Commit
```
