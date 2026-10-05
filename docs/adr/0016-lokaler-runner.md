# ADR 0016 — Lokaler Runner

- **Status:** **Entwurf**, wartet auf Otto (Fragen in §12).
- **Datum:** 2026-10-05
- **Aufgabe:** M4-05 laut `docs/plans/m4-processing-kern.md` §4.
- **Autonomiestufe:** C. Es gibt keinen Produktivcode und keine Änderung an
  `backend/`, `.importlinter`, `docker-compose.yml`, `.github/` oder den
  Lock-Dateien. Gemessen wurde mit Skripten und einem Image im
  Kratzverzeichnis der Sitzung; der Messanhang (§14) nennt die Befehle.
- **Vorab fest:**
  - Q11: Ein Cache-Treffer gibt es nur mit der Fassung aller Eingaben; lokal
    erzeugte Ergebnisse kommen nie in den gemeinsamen Cache.
  - Q12: In M4 nur der Modus „offline mit Rezeptdatei“; das Image wird lokal
    gebaut, mit festem Tag, nie `latest`, und nicht in einer Registry
    veröffentlicht; Vergleichstest Cloud gegen lokal in der CI; Ergebnisse
    sind `self_attested`.
  - Aus `adr/0014` (angenommen): Rezept in drei Schichten (§4.1), Toleranz
    T2 ↔ T2L **bitgleich** auf derselben CPU-Architektur (F9 mit Auflage,
    §6.3), Vergleich über Pixel-Bytes und Metadaten ohne Provenienzfelder
    (§6.4), Allowlist aus den Hosts des Rezepts (§8, F11), Blockschleife
    ohne Dask (F10).
  - Aus `adr/0013` (angenommen): `processing.run(recipe, *, workdir,
    progress)` ist die Kern-Schnittstelle; das Kind je Job ruft
    `processing.worker_environment()` beim Start; der Runner ruft
    `processing.run` ebenso, ohne Aufseher (§5.3).
  - Aus `adr/0015` (angenommen): Ergebnisse liegen in der Cloud als
    `results/{result_id}/{name}` mit `result.tif`, `recipe.json`,
    `citation.bib`, `attribution.txt` (§4.1, K1); `processing` und damit der
    Kern erreichen den Objektspeicher nie (R2).
- **Grundlage:**
  - `ENTSCHEIDUNGEN_2026-09-18.md` §4, §5; `KLAERUNGEN.md` B8, B9.
  - `architekturplan.md` 3.1, 3.2, 7.3, 7.7, 11, 15.2, 16 (mit Nachträgen).
  - `adr/0002` §1; `adr/0013` §5.3, §6; `adr/0014` §4, §6, §7, §8, §14;
    `adr/0015` §4.1, §8.
  - `plans/m4-processing-kern.md` §1.1 (Q11, Q12), §1.1b (R5), M4-05, Umriss
    M4-16; `plans/m4-00b-lock-datei.md` (universelle Lock-Datei).
  - Entscheidungslog bis 05.10.2026.
- **Betroffen:**
  - M4-16 (Umsetzung des Runners und des Vergleichstests), M4-07a
    (`RunResult`, Versionsangabe des Kerns), M4-09 (Funktionsliste nach R5),
    M4-13 (Text „Lokal ausführen“ erst später, F3).
  - `backend/Dockerfile`, `docker-compose.yml` (Build-Ziel), `.importlinter`,
    `backend/tests/test_module_boundaries.py`, `.github/workflows/ci.yml`
    (in M4-16 ausdrücklich erlaubt), `architekturplan.md` 3.1 und 7.7.

---

## Methode und Belegstufen

Gelesen und gemessen in einer Cloud-Sitzung am 05.10.2026 auf dem Stand von
`main` nach PR #118. Belegstufen wie in `adr/0009`:

- **M:** in dieser Sitzung gemessen; Befehl im Messanhang §14.
- **P:** am Primärdokument gelesen, mit Datei und Stelle.
- **P\*:** Primärdatei abgerufen, aber über das Abrufwerkzeug eines
  Hilfsagenten, das Seiten zusammenfasst. Zitate sind sinngemäß, nicht
  zeichengenau.
- **S:** Zusammenfassung oder Suchtreffer, Wortlaut nicht geprüft.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Werkzeuge.** Projekt-venv: Python 3.12.3, rasterio 1.5.2 mit GDAL 3.12.2,
numpy 2.5.3, numexpr 2.14.2, glibc 2.39 (Ubuntu). Image: `backend/Dockerfile`
aus `backend/requirements.lock`, Python 3.12.15, dieselben Paketversionen,
glibc 2.41 (Debian 13). CPU der Sitzung: Intel Xeon, 4 Kerne, mit AVX2, FMA
und AVX-512.

**Docker in der Sitzung.** Anders als in `cloud-umgebung.md` §4 notiert, lädt
`docker pull` heute Images [M]. Die Debian-Spiegel antworten aber mit `403`,
der apt-Schritt des `Dockerfile` scheitert also [M]. Für die Messung lief eine
Kopie des `Dockerfile` im Kratzverzeichnis. Dort ersetzt eine Kopie von
`libexpat.so.1` aus dem Host den apt-Schritt, und der CA-Bundle des Proxys
liegt für pip im Image. Sonst ist die Kopie unverändert. `curl` fehlt in
diesem Image; die Größe weicht dadurch um unter 1 MB ab [A].

**Gesperrte Hosts** (für den Hilfsagenten): `docs.docker.com`,
`zarr.readthedocs.io`, `sourceware.org`. Primärtexte kamen über
`raw.githubusercontent.com` aus den Repos der Herausgeber (`docker/docs`,
`docker/cli`, `OSGeo/gdal`, `zarr-developers/zarr-python`, `numpy/numpy`,
`bminor/glibc`, `apptainer/apptainer-userdocs`) und über `docker.com/legal`.

**Anfragen an Datenquellen: 0.** Alle Rechnungen laufen auf synthetischen
Daten. Keine AOI kommt vor.

---

## 0. Kurzfassung

Jede Empfehlung hat eine Frage in §12.

1. **Image (F1):** eine eigene Build-Stufe `runner` im selben `Dockerfile`,
   die auf der Stufe der vier Dienste aufsetzt. Sie fügt nur `USER` (Nicht-Root)
   und `ENTRYPOINT` hinzu. Gemessen sind die Schichten beider Stufen gleich,
   also auch Python-Pakete, GDAL 3.12.2 und numpy [M]. Das Image ist 825 MB
   groß, 189 MB komprimiert [M]. Ein eigenes schlankes Image spräche
   rund 0,08 GB (10 %) und bräuchte eine zweite Lock-Datei [M][A].
2. **Modul (F2):** ein neues Modul `earthx.runner` als dritte Hülle um den
   Kern, neben `jobs` und dem `tiler`. Es darf nur `processing` importieren
   (dazu `catalog.datasets` nach F4). Es gilt dieselbe Kettenregel wie für
   `processing`: keine Datenbank, kein Objektspeicher, kein HTTP-Client.
3. **Rezeptdatei (F3):** Der Runner liest genau das Rezept (Schicht 2,
   `adr/0014` §4.2), das als `recipe.json` neben jedem Ergebnis liegt. Er
   prüft es mit denselben strikten Modellen wie `api`, auch die
   Band-Math-Ausdrücke (R5). In M4 gibt es keinen neuen Endpunkt, der ein
   Rezept nur für lokal ausgibt.
4. **Allowlist (F4):** die Hosts der `ResolvedAsset` des Rezepts, wie B9
   sagt. Zusätzlich muss jeder Host in `asset_hosts` seines Datensatzes in
   der Registry **dieses Images** liegen; das ist dieselbe Prüfung, die `api`
   bei der Annahme macht. Ein fremdes Rezept kann den Runner so nicht an
   beliebige Server schicken, deren Dateien GDAL dann auf dem Rechner des
   Nutzers parst (architekturplan 11, „Präparierte Rasterdateien“). Der
   Runner nennt die Hosts vor dem Lesen.
5. **Ausgabe und Provenienz (F5):** ein neuer Unterordner je Lauf mit
   zufälligem Namen, darin dieselben Dateien wie in der Cloud und dazu
   `provenance.json` mit `execution: "local"`, `runner_version`,
   `self_attested: true`, den Versionen aus dem Cache-Schlüssel (`adr/0014`
   §4.5, E2), Plattform und Zeiten. Ein Ordner wird nie überschrieben.
6. **Cache-Volume (F6): in M4 keines.** GDAL cacht `/vsicurl/` nur im
   Speicher, nicht auf Platte [P\*]. Ein Datei-Cache für Zarr-Chunks gibt es
   in zarr nur als experimentelles `CacheStore` ab 3.1.4 [P\*]. Ein eigener
   Cache wäre ein zweiter Lesepfad neben `gateway`.
7. **Vergleichstest (F7):** zwei Teile.
   - In `pytest`: derselbe Kern über den Einstieg von `jobs` und über den
     Einstieg des Runners, beide als frische `spawn`-Prozesse, auf derselben
     Maschine im selben Lauf, gegen synthetische Fixtures. Verglichen werden
     Pixel-Bytes und Metadaten ohne Provenienz, gegeneinander und nicht gegen
     gespeicherte Werte.
   - Im Compose-Job der CI: Die Stufe `runner` wird gebaut. Sie läuft mit
     den Härtungs-Optionen und muss dieselben Versionen melden wie der
     `worker`.
8. **Befund zur Toleranz (F8):** Bitgleichheit hängt nicht nur von der
   Architektur ab, sondern von den CPU-Erweiterungen. Gemessen auf derselben
   CPU mit simuliert abgeschalteten Erweiterungen:
   - NDVI (Grundrechenarten) und Warp (`nearest`, `bilinear`, `cubic`) bleiben
     bitgleich [M].
   - `log`, `exp`, `sin` und Potenzen mit nicht ganzzahligem Exponenten
     weichen ab: bis 1 ULP bei float64 und bis 4 ULP bei float32, an 0,004 %
     bis 22 % der Pixel [M].
   - Ursache sind numpy (Laufzeit-Dispatch nach SIMD-Stufe) und glibc
     (Varianten mit und ohne FMA) [M][P\*].
   - Empfehlung: Die Zusage aus `adr/0014` F9 wird so präzisiert, nicht
     erzwungen. M4-09 bekommt den Befund für die Funktionsliste aus R5.
9. **Plattformen und Befehl (F9):** x86_64 mit Docker Desktop oder Podman
   unter Windows, macOS und Linux. Auf ARM-Rechnern wird nativ gebaut. Das
   Ergebnis liegt dann außerhalb der Bitgleich-Zusage und trägt die
   Plattform in der Provenienz. Der Befehl für PowerShell steht in §8.
10. **Version und Tag (F10, F11):**
    - Heute hat das Paket `earthx` keine Version. Vorschlag: `__version__` in
      `earthx/__init__.py`, Tag `earthx-runner:<version>`, dazu der Commit
      als Build-Argument. `runner_version` ist `<version>+g<commit>`.
    - Das Basis-Image wird per Digest festgenagelt (F11).

---

## 1. Kontext und Frage

`architekturplan.md` 7.7 beschreibt den Runner als dritte Hülle um denselben
Worker-Kern: Der Nutzer führt ein Rezept auf seinem Rechner aus, liest die
Daten direkt bei den Quellen und schreibt das Ergebnis in einen lokalen
Ordner. Q12 schneidet das für M4 auf den Modus „offline mit Rezeptdatei“
zurück. Die M4-Abnahme 1 verlangt, dass dasselbe Rezept als Job und im Runner
übereinstimmt, mit einem Vergleichstest in der CI.

Offen sind laut M4-05:

1. der Einstieg: ein weiterer Startbefehl im Image von `worker` oder ein
   eigenes Image; Größe; gleiche GDAL-Version;
2. Rezeptdatei, Allowlist aus deren Adressen (B9), Ausgabeordner und
   Cache-Volume;
3. die Provenienz `execution: local`, `runner_version`, `self_attested: true`;
4. die Form des Vergleichstests in der CI, mit der Toleranz aus `adr/0014`;
5. der Befehl für Windows und PowerShell; fester Tag, nie `latest`, kein
   Veröffentlichen.

## 2. Kriterien

| # | Kriterium | Herkunft |
|---|---|---|
| K1 | Derselbe Kern, dieselben Bibliotheken wie im `worker`; die Gleichheit ist geprüft, nicht angenommen | 7.3, 7.7; `adr/0014` F9 |
| K2 | Der Kern bleibt zustandslos und ohne Plattformdienste; der Runner bringt keinen mit | B9; R2; `adr/0013` §6.1 |
| K3 | Jede URL läuft durch `check_url`; die Allowlist kommt aus dem Rezept; ein fremdes Rezept richtet keinen Schaden an | B8, B9; architekturplan 11 |
| K4 | Ehrliche Provenienz; nichts Lokales im gemeinsamen Cache | Q11, Q12; 7.7 |
| K5 | Der Vergleich ist in der CI wiederholbar und schlägt nicht zufällig fehl | M4-Abnahme 1; `adr/0002` |
| K6 | Unter Windows mit einem Befehl nutzbar; fester Tag; kein Veröffentlichen | Q12; M4-05 |
| K7 | Wenig neue Fläche: keine neue Abhängigkeit, kein neuer Endpunkt in M4 | projektplan 7; architekturplan 16 |

---

## 3. Befunde

### 3.1 Image: Größe und Inhalt — [M]

| | Platz auf der Platte | komprimiert |
|---|---|---|
| `python:3.12-slim` (Debian 13, glibc 2.41) | 191 MB | 48 MB |
| Image aus `backend/Dockerfile` | 825 MB | 189 MB |
| darin `site-packages` | 470 MB | — |

Größte Pakete im Image (installierte Dateien):

| Paket | MB | braucht der Kern? |
|---|---|---|
| rasterio (mit GDAL, PROJ und Treibern) | 122 | ja |
| numpy | 68 | ja |
| pandas | 68 | ja, über xarray |
| pyproj | 35 | ja |
| psycopg-binary, uvloop, asyncpg, cql2, pypgstac, psycopg, httptools, websockets, fastapi, watchfiles, jinja2 | zusammen rund 81 | nein (`api`, `tiler`, Datenbank) |
| xarray, shapely, zarr, numcodecs, numexpr, rio-tiler, pydantic | zusammen rund 46 | ja |

- Ein Image nur für den Kern spräche also rund 0,08 GB von 0,83 GB (10 %) [A
  aus M]. Bei kleineren Paketen ist offen, wer sie braucht; sie sind nicht
  mitgezählt. pip selbst (10 MB) läge in beiden.
- architekturplan 7.7 schätzt „grob ein Gigabyte“. Das trifft zu.

**Eigene Stufe, gleiche Schichten [M].** Eine zweite Stufe
`FROM app AS runner` mit nur `USER 10001:10001` und `ENTRYPOINT` hat
dieselbe Liste von Schicht-Digests wie die Stufe `app` (gleiche Prüfsumme
über `RootFS.Layers`) und dieselbe Größe. Sie fügt also keine Bytes hinzu.
Der Inhalt, den der Kern sieht, ist bytegleich mit dem des `worker`.

**GDAL-Version [M].** GDAL kommt im Wheel von rasterio. Die Lock-Datei pinnt
`rasterio==1.5.2` mit Hashes, im Image wie im venv also GDAL 3.12.2. Das Image
meldet `3.12.15 1.5.2 3.12.2 2.5.3 2.14.2` (Python, rasterio, GDAL, numpy,
numexpr).

### 3.2 Lauf mit Härtung — [M]

Ein Testskript schreibt eine synthetische COG (2048², uint16) mit
`rio-cogeo` in einen gemounteten Ordner und liest sie zurück. Es lief im
Image mit diesen Optionen:
`--read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges
--user 10001:10001 --network none`.

- Ergebnis: Der Lauf gelingt in 0,41 s. Die Datei gehört UID 10001, die
  Übersichten 2 und 4 sind da.
- PROJ findet seine Daten im Paket; ein beschreibbares Heimatverzeichnis
  braucht es nicht.
- Zwei Läufe ergeben eine **bytegleiche Datei** (SHA-256 gleich). GDAL
  schreibt keinen Zeitstempel in die COG. Tags: `LAYOUT=COG`,
  `COMPRESSION=DEFLATE`.
- Start des Containers mit allen Importen des Kerns: 2,3 s kalt.

Die Härtungs-Optionen sind einzeln in der CLI-Referenz von Docker beschrieben
(`--read-only`, `--tmpfs`, `--cap-drop`, `--security-opt
no-new-privileges=true`, `--user`). Der Standardnutzer im Container ist
`root` [P\*, `docker/cli` `docs/reference/run.md`]. Eine fertige Kombination
nennt die Referenz nicht.

### 3.3 Bitgleichheit und CPU-Erweiterungen — [M], [P\*]

`adr/0014` F9 sagt „bitgleich auf derselben CPU-Architektur (CI, x86_64)“.
Gemessen ist dort nur eine Maschine. Hier ist geprüft, ob die
**Erweiterungen** einer x86_64-CPU das Ergebnis ändern.

**Aufbau.** Ein Skript rechnet auf festen Zufallsdaten. Es bildet für jedes
Ergebnis SHA-256 über die Bytes:
- NDVI mit Skalierung wie in `adr/0014` (numexpr und numpy, float32);
- `log`, `exp`, `sin`, `sqrt`, `x**1.7` in numexpr und numpy, float32 und
  float64;
- Warp eines DEM von UTM 32N nach EPSG:3035 und EPSG:4326 mit `nearest`,
  `bilinear` und `cubic`.

Gerechnet wurde auf derselben CPU in fünf Einstellungen:

| Lauf | Einstellung | entspricht ungefähr |
|---|---|---|
| A | nichts gesetzt | diese CPU (AVX-512) |
| B | numpy ohne X86_V4/AVX-512 (`NPY_DISABLE_CPU_FEATURES`) | CPU mit AVX2 ohne AVX-512, nur numpy |
| C | wie B, dazu glibc ohne AVX-512 (`GLIBC_TUNABLES`) | dito, auch glibc |
| D | numpy und glibc ohne AVX2, FMA und AVX-512 | CPU der Stufe x86-64-v2 |
| E | nur glibc ohne AVX2, FMA und AVX-512 | — |

Dass glibc 2.39 die Maskierung tatsächlich übernimmt, zeigt
`ld.so --list-diagnostics`: Die Bits für FMA, AVX2 und AVX512F fallen weg. Die
ältere Schreibweise `-AVX2_Usable,-FMA_Usable` wird dagegen still ignoriert
[M].

**Ergebnis (gleich = SHA-256 wie Lauf A):**

| Rechnung | B | C | D | E |
|---|---|---|---|---|
| NDVI, numexpr und numpy | gleich | gleich | gleich | gleich |
| `sqrt` (beide, beide Typen) | gleich | gleich | gleich | gleich |
| numexpr `log`, `exp`, `sin` float32 | gleich | gleich | gleich | gleich |
| numexpr `log`, `exp`, `sin` float64; `x**1.7` beide Typen | gleich | gleich | **anders** | **anders** |
| numpy `exp`, `log`, `x**1.7` float64; `x**1.7` float32 | **anders** | **anders** | **anders** | gleich |
| numpy `log`, `exp`, `sin` float32 | gleich | gleich | **anders** | gleich |
| Warp, alle sechs | gleich | gleich | gleich | gleich |

**Größe der Abweichung** (A gegen B bzw. D, je 4,2 Mio. Werte):

| Rechnung | Anteil abweichender Werte | größte Abweichung |
|---|---|---|
| numexpr `log` float64 (D) | 0,004 % | 1 ULP |
| numexpr `x**1.7` (D) | 0,069 % | 1 ULP |
| numpy `exp` float64 (B, D) | 4,6 % | 1 ULP |
| numpy `x**1.7` float32 (B, D) | 21,8 % | 1 ULP (relativ 1,2·10⁻⁷) |
| numpy `log` float32 (D) | 11,8 % | 4 ULP (relativ 2,9·10⁻⁷) |
| numexpr `x**2` float32 | 0 % | 0 |

**Image gegen venv [M].** Auf derselben CPU gibt das Image (Debian, glibc
2.41, Python 3.12.15) in allen 28 Prüfungen dieselben Bytes wie das venv
(Ubuntu, glibc 2.39, Python 3.12.3). Mit der Einstellung D gilt das ebenso.
Der Wechsel der glibc-Version hat hier also nichts geändert, der Wechsel der
CPU-Stufe schon.

**Erklärung [P\*].**
- numpy wählt Funktionsvarianten beim Import nach den CPU-Merkmalen. Diese
  Wahl lässt sich mit `NPY_DISABLE_CPU_FEATURES` einschränken
  (`numpy/numpy`, `doc/source/reference/simd/build-options.rst`). Eine Zusage
  gleicher Bits über Varianten steht dort nicht. Issue numpy#23523 beschreibt
  Abweichungen zwischen AVX-512 und anderen Pfaden bei `sin`, `cos`, `exp`
  und `log` im Bereich eines ULP.
- glibc rundet `exp`, `log` und `pow` nicht korrekt, sondern mit einer
  Fehlerschranke von rund 0,5 ULP, je nach Variante mit oder ohne FMA (Kommentare
  in `sysdeps/ieee754/dbl-64/e_pow.c`, `e_log.c`). Die Variante wählt ein
  ifunc nach FMA und AVX2 (`sysdeps/x86_64/fpu/multiarch/ifunc-fma.h`). Das
  Handbuch sagt, glibc strebe keine korrekt gerundeten Ergebnisse an
  (`manual/math.texi`).
- Grundrechenarten und `sqrt` sind nach IEEE 754 korrekt gerundet; dort gibt
  es keine Wahl [A]. Das passt zum Befund.

**Kosten, die Stufe festzunageln [M].** Zeit je Aufruf auf 4,2 Mio. Werten,
Lauf A gegen D:

| Rechnung | A | D |
|---|---|---|
| numexpr `log` float64 | 26 ms | 16 ms |
| numexpr `x**1.7` float64 | 37 ms | 39 ms |
| numpy `x**1.7` float32 | 10 ms | 62 ms |
| numpy `log` float32 | 4 ms | 35 ms |

numexpr, die Maschine von Band-Math (`adr/0014` §3.2), verliert kaum etwas.
numpy-Funktionen werden bis achtmal langsamer. Die glibc-Maskierung gilt
außerdem für `memcpy` und Zeichenkettenfunktionen; das ist nicht gemessen.

**Folgen [A].**
- Der Vergleich in der CI muss beide Läufe auf derselben Maschine im selben
  Job rechnen. Ein gespeicherter Referenz-Hash von einer anderen Maschine
  könnte bei Funktionen in Band-Math zufällig scheitern (K5).
- Beim Nutzer gilt Bitgleichheit mit der Cloud sicher nur für
  Grundrechenarten, Vergleiche, `sqrt` und den Warp. Bei Funktionen sind
  Abweichungen von wenigen ULP möglich.
- Dasselbe gilt in der Cloud selbst, wenn Worker auf verschiedenen CPU-Typen
  laufen. Ein Cache-Treffer kann dann wenige ULP von einer Neuberechnung
  abweichen (Nebenfund zu `adr/0014` §4.5, §13).

### 3.4 Cache für heruntergeladene Daten — [P\*]

- **GDAL** (`doc/source/user/virtual_file_systems.rst`, Zweige `master` und
  `release/3.12`) kennt für `/vsicurl/` nur Speicher-Caches:
  - einen globalen LRU-Cache, Standard 16 MB, für die Lebenszeit des Prozesses
    (`CPL_VSIL_CURL_CACHE_SIZE`);
  - einen Cache je Dateihandle (`VSI_CACHE`, `VSI_CACHE_SIZE`, Standard 25 MB),
    der beim Schließen verworfen wird;
  - `/vsicached?` ab GDAL 3.8, ebenfalls im Speicher.
  - Einen Cache auf Platte über das Prozessende hinaus nennt die Doku nicht.
- **zarr** bringt ab 3.1.4 `zarr.experimental.cache_store.CacheStore`. Es
  verbindet zwei Stores, einer davon dient als Cache. Die Doku nennt die API
  „volatile -- we might change them at any time“ (`docs/user-guide/
  experimental.md`, Release Notes 3.1.4).
- Ein Cache auf Platte wäre also eigener Code. Für COG läge er vor GDAL, das
  seine Anfragen selbst stellt (`readers/cog.py`, „cannot take the socket away
  from GDAL“) [P]. Das hieße: die Datei erst über `gateway` herunterladen und
  dann lokal lesen, ein zweiter Lesepfad [A].

### 3.5 Windows, Podman, ARM, Apptainer — [P\*], [S]

- **Docker Desktop:** kostenlos für persönliche Nutzung, Bildung,
  nicht-kommerzielle Open Source und Unternehmen mit unter 250 Beschäftigten
  **und** unter 10 Mio. USD Jahresumsatz. Behörden und größere Unternehmen
  brauchen ein Abonnement (Docker Subscription Service Agreement §3.2,
  `docker.com/legal`, Stand 26.08.2026).
- **Podman:** `podman build` liest dieselbe Dockerfile-Syntax. Unter Windows
  und macOS läuft Podman in einer VM (`podman machine`). Podman Desktop steht
  unter Apache-2.0 (`containers/podman`, `podman-desktop/podman-desktop`).
  Die volle Gleichheit der Optionen von `podman run` ist nicht geprüft.
- **WSL2:** Bind-Mounts aus dem Linux-Dateisystem sind „much higher“ in der
  Leistung als aus dem Windows-Dateisystem. In PowerShell steht `${PWD}` für
  das aktuelle Verzeichnis, und Pfade müssen absolut sein
  (`docker/docs`, `desktop/features/wsl/best-practices.md`,
  `engine/storage/bind-mounts.md`).
- **ARM:**
  - Ein Image für `linux/amd64` läuft auf ARM nur unter Emulation (QEMU, auf
    Apple Silicon wahlweise Rosetta). Die Doku nennt sie „much slower“, ein
    Wort zur Korrektheit steht dort nicht (`build/building/multi-platform.md`).
  - Die Lock-Datei ist universell und trägt die Hashes der aarch64-Wheels mit;
    zugesichert ist nur x86_64 (Log 02.10.2026, M4-00b).
- **Apptainer** baut aus einem lokal gebauten Docker-Image ohne Registry
  (`docker-daemon:REPO:TAG` oder `docker-archive:datei.tar`,
  `apptainer-userdocs`, `docker_and_oci.rst`). Das deckt Rechencluster ohne
  Docker ab, wie 7.7 es vorsieht.

### 3.6 Was der Code heute mitbringt — [P]

- `backend/Dockerfile` hat eine Stufe ohne Namen, kein `CMD` und kein
  `ENTRYPOINT` (Z. 1–3: „this file sets no CMD/ENTRYPOINT on purpose“). Es
  läuft als `root`.
- Das Basis-Image ist `python:3.12-slim`, ein gleitender Tag ohne Digest.
  Garage ist in `docker-compose.yml` dagegen per Digest festgenagelt.
- `earthx/__init__.py` hat keine `__version__`. Es gibt keine Git-Tags im
  Klon, und `pyproject.toml` konfiguriert nur ruff und pytest.
- `catalog/datasets.py` importiert aus `earthx` nur `catalog.registry`, also
  kein psycopg (Kopf der Datei). `asset_hosts` steht je Eintrag dort
  (Z. 158, 329, 523).
- Die Fixtures für COG und Zarr lenken nur den letzten Schritt um:
  - `mini_cog.serve_cog` tauscht `vsicurl_path` gegen eine lokale Datei;
  - `mini_zarr.serve_store` liefert die Chunks über einen `MockTransport`.
  - `check_url`, Allowlist und Adressprüfung laufen echt
    (`tests/earthx/readers/mini_cog.py`, Docstring).
  - Ein Vergleich über zwei Einstiege kann dieses Muster nutzen, wenn es im
    Kindprozess vor dem Aufruf des Einstiegs gesetzt wird.

---

## 4. Image und Einstieg (Punkt 1)

### 4.1 Optionen

| | I1 eigene Stufe `runner` im selben `Dockerfile` | I2 dasselbe Image, anderer Befehl | I3 eigenes schlankes Image | I4 pip-Paket ohne Container |
|---|---|---|---|---|
| K1 gleiche Bibliotheken | ✓ gleiche Schichten [M] | ✓ | ~ nur bei gleichen Versionen; zweite Lock-Datei | ✗ Plattform des Nutzers |
| K2 kein Plattformdienst im Prozess | ✓ Modul-Regel (§5) | ✓ dito | ✓ psycopg gar nicht im Image | ✓ |
| K6 ein Befehl, Nicht-Root | ✓ `USER` und `ENTRYPOINT` in der Stufe | ~ Nutzer muss `--user` und `python -m …` mitgeben | ✓ | ~ |
| Größe | 825 MB [M] | 825 MB | rund 0,75 GB [A aus M] | — |
| K7 Pflege | eine Stufe mehr | nichts | zweite Lock-Datei, zweites Image in der CI | Paketierung, Windows-Wheels |

**Empfehlung: I1.** Die Stufe fügt keine Bytes hinzu [M] und macht die
Gleichheit mit dem `worker` zur Eigenschaft des Builds statt zu einer
Prüfung. 10 % Größe rechtfertigen keine zweite Lock-Datei. I4 bleibt nach 7.7
ein nachrangiger Weg für später.

### 4.2 Skizze (Vorschlag, nicht gebaut)

```dockerfile
FROM python:3.12-slim@sha256:<digest> AS app      # F11
# … unverändert: apt, Lock-Datei, earthx …

FROM app AS runner
ARG EARTHX_COMMIT=unknown
ENV EARTHX_COMMIT=${EARTHX_COMMIT}
USER 10001:10001
ENTRYPOINT ["python", "-m", "earthx.runner"]
```

- **Build-Ziel der Dienste.** Ohne `--target` baut Docker die letzte Stufe.
  `docker-compose.yml` bekommt deshalb `target: app` an jedem `build:`.
  Sonst liefen die vier Dienste mit dem `ENTRYPOINT` des Runners [A].
- **Nicht-Root nur im Runner.** Die vier Dienste laufen weiter als `root`.
  Sie umzustellen ist eine eigene Aufgabe.
- **Befehle des Runners** (Unterbefehle von `python -m earthx.runner`):
  - `run <rezept.json> [--out /out]`: rechnen;
  - `check <rezept.json>`: nur prüfen und die Hosts nennen, ohne zu lesen;
  - `versions`: die Versionen aus §6.2 als JSON ausgeben (für F7).
- **Exit-Codes** (Vorschlag): 0 fertig; 2 Rezept ungültig; 3 Host abgewiesen
  (F4); 4 Quelle nicht erreichbar oder fehlerhaft; 5 sonstiger Fehler. Die
  Hülle `jobs` unterscheidet dieselben Fälle für die Wiederholung
  (`adr/0013` §5.6); die Zuordnung kommt aus derselben Fehlerklasse im Kern.

---

## 5. Modul und Importregeln (Punkt 1)

### 5.1 Optionen

| | M1 neues Modul `earthx.runner` | M2 in `jobs` (`jobs/runner.py`) | M3 in `processing` (`python -m earthx.processing`) |
|---|---|---|---|
| K2 kein Plattformdienst | ✓ eigener Vertrag ohne psycopg und `objectstore` | ~ `jobs` darf psycopg und `objectstore`; nur ein Test sichert, dass der Runner sie nicht lädt | ✓ |
| 7.3 „drei Hüllen um denselben Kern“ | ✓ | ~ zwei Hüllen in einem Modul | ✗ die Hülle läge im Kern |
| neue Zeile in 3.1 | ja | nein | nein |
| F4 Option 1 (Registry-Prüfung) | ✓ darf `catalog.datasets` | ✗ `jobs` darf `catalog` nicht | ✗ `processing` erreicht nur `catalog.registry` (M4-Plan §1.2) |

**Empfehlung: M1.** Zeile für 3.1 (Vorschlag):

| Modul | Zuständig für | Darf importieren |
|---|---|---|
| `runner` | Lokaler Runner offline: Rezeptdatei lesen und prüfen, Hosts nennen, Kern ausführen, Ergebnis und Provenienz in einen lokalen Ordner schreiben | `processing`; `catalog.datasets` (nur für die Prüfung der Hosts, F4) |

**Verträge in M4-16 (Vorschlag):**
- neuer Vertrag `runner` nach dem Muster von `jobs`: verboten sind alle Module
  außer `processing` und `catalog`. Eine zusätzliche Regel erlaubt aus
  `catalog` nur `catalog.datasets` und `catalog.registry`; Form nach dem
  Muster der vorhandenen Verträge;
- `earthx.runner` als Quelle in `no-database-in-worker-core`,
  `no-object-store-in-worker-core` (R2), `http-only-in-gateway` und
  `datasets-isolated`. Diese Verträge zählen Ketten mit (außer
  `http-only-in-gateway`); eine Kette `runner → … → psycopg` fällt also auf;
- `test_module_boundaries.py` kennt die neue Zeile.

Das sind neue, strengere Regeln für ein neues Modul. Keine bestehende Regel
wird gelockert.

**Der Ordner `runner/` im Projektplan** (`projektplan.md`, Repo-Struktur)
bleibt für Verteilung und Wrapper-Skript (`earthx run`, 7.7) vorbehalten. Er
gehört nicht zu M4.

---

## 6. Rezeptdatei, Allowlist, Ausgabe (Punkt 2, 3)

### 6.1 Rezeptdatei (F3)

- **Schema:** genau das Rezept aus `adr/0014` §4.2 (Schicht 2), das als
  `recipe.json` neben jedem Ergebnis liegt (`adr/0015` K1). Das ist der
  Auftrag mit `resolved` je Eingabe, Fassung, Bandangaben und `op_version`.
- **Prüfung:** dieselben pydantic-Modelle wie in `api`, `strict=True`,
  `extra="forbid"`, mit dem I-JSON-Parser aus `adr/0014` §4.4 (doppelte
  Schlüssel, `NaN`). Felder der Provenienz in der Eingabe werden abgewiesen.
  Die Band-Math-Ausdrücke prüft dasselbe Parametermodell wie in der Cloud,
  bevor numexpr sie sieht (R5).
- **Versionen:** Kennt der Runner `recipe_version` oder eine `op_version`
  nicht, bricht er mit Exit-Code 2 ab und nennt die Version des Runners, die
  sie kennt. Er stuft nicht still hoch (`adr/0014` §4.3).
- **Herkunft in M4:**

| | H1 nur vorhandene Dateien | H2 neuer Endpunkt „aufgelöstes Rezept“ | H3 wie H2, AOI nur lokal |
|---|---|---|---|
| Woher | `recipe.json` eines Job-Ergebnisses; das Zuschnitt-ZIP (M4-14, `steps: []`); Fixtures in der CI | `POST` eines Auftrags, Antwort ist das Rezept ohne Lauf | Plattform löst Items und Assets auf, `--aoi` ergänzt lokal |
| K7 neue Fläche | keine | Annahme ohne Lauf: Item-Abrufe und `HEAD` an Quellen ohne Kostenschranke | dito, plus eigenes Teil-Schema |
| 7.7 „AOI verlässt den Rechner nicht“ | nein (der Job lief in der Cloud) | nein | ja; die Item-Auswahl verrät die Gegend aber grob [A] |
| passt zu Q12 | ✓ | ~ geht über „offline“ hinaus | ~ |

**Empfehlung: H1 in M4.** Das trägt die Abnahme 1 (Job und Runner auf
demselben Rezept). „Lokal ausführen“ in der Oberfläche mit fertigem Befehl
(7.7) gehört zum verbundenen Runner bzw. zu 7f; H2 oder H3 kommen dort in
Frage. Bis dahin zeigt M4-13 keinen Knopf „Lokal ausführen“.

### 6.2 Allowlist und umgekehrtes Vertrauen (F4)

B9 sagt: Die Allowlist ergibt sich aus den aufgelösten Asset-Adressen des
Rezepts, und `gateway` läuft im Runner mit. Damit gelten `https`,
öffentliche Adressen, Zeit- und Größengrenzen wie in der Cloud (`readers`,
`read_access_for`, `adr/0014` §8).

Was B9 offenlässt: Wer garantiert, dass die Adressen im Rezept zu einer echten
Quelle gehören? In der Cloud prüft `api` bei der Annahme, dass jeder Host in
`asset_hosts` seines Datensatzes liegt (F11 von `adr/0014`). Im Runner gibt es
keine Annahme. Eine Rezeptdatei kann von Dritten kommen (geteilt,
weitergeleitet, verändert).

| | A1 Hosts des Rezepts, zusätzlich gegen die Registry im Image | A2 nur Hosts des Rezepts | A3 wie A2, mit Rückfrage am Terminal |
|---|---|---|---|
| K3 fremdes Rezept | ✓ nur Hosts bekannter Datensätze dieser Version | ✗ jeder öffentliche `https`-Host; GDAL parst dann fremde Dateien auf dem Rechner des Nutzers (architekturplan 11) | ~ hängt am Nutzer |
| neuer Datensatz | braucht eine neue Runner-Version (ohnehin wegen festem Tag, 7.7) | geht sofort | geht sofort |
| Import | `runner → catalog.datasets` (§5) | keiner | keiner |
| Skripte, CI | ✓ | ✓ | ✗ interaktiv |

**Empfehlung: A1.** `dataset_id` steht in jedem `ResolvedAsset`
(`adr/0011` §6.4). Der Runner prüft Datensatz und Host gegen die Registry
dieses Images, bevor er liest. Ein unbekannter Datensatz oder Host bricht mit
Exit-Code 3 ab. In jedem Fall gibt `check` und der Anfang von `run` die Hosts
aus, nie ganze Adressen und nie die AOI.

### 6.3 Ausgabeordner und Provenienz (F5)

**Ablage (Vorschlag):**

```
/out/<run_id>/            run_id = secrets.token_urlsafe(16)
  result.tif              wie in der Cloud (adr/0015 K1)
  recipe.json             das Eingaberezept, unverändert
  citation.bib
  attribution.txt
  provenance.json         nur lokal: siehe unten
  .work/                  Arbeitsordner von processing.run, am Ende gelöscht
```

- Der Ordner entsteht neu. Gibt es ihn schon, bricht der Runner ab; er
  überschreibt nie.
- Der Arbeitsordner liegt unter `/out`, nicht in `/tmp`. Ein Zwischenergebnis
  von 8192² float32 hat 268 MB [A]; ein `tmpfs` läge im Speicher.
- Erst wenn alles geschrieben ist, wird `.work` gelöscht. Ein abgebrochener
  Lauf hinterlässt einen Ordner ohne `provenance.json`; daran ist er zu
  erkennen.
- Welche Dateien entstehen, bestimmt `processing.run` (Rückgabewert
  `RunResult`, `adr/0014` §13). `jobs` lädt dieselben hoch, der Runner
  schreibt sie. Es gibt keine zweite Liste [A].

**`provenance.json` (Vorschlag):**

```json
{
  "execution": "local",
  "self_attested": true,
  "runner_version": "0.4.0+g1a2b3c4",
  "engine": {"earthx.processing": "…", "gdal": "3.12.2", "rasterio": "1.5.2",
             "numexpr": "2.14.2", "numpy": "2.5.3"},
  "platform": {"machine": "x86_64", "numpy_dispatch": "X86_V4"},
  "started": "…", "finished": "…"
}
```

- `engine` ist derselbe Block wie im Cache-Schlüssel (`adr/0014` §4.5, E2).
- `platform` erklärt Abweichungen nach §3.3. `numpy_dispatch` ist die höchste
  aktive Stufe aus numpys eigener Liste; das ist kein Merkmal, das einen
  Rechner eindeutig macht [A].
- Kein Hash, keine Kennung der Plattform. Lokal gibt es keine `jobID`.
- **Nie im Cache (Q11, Q12):** Der Runner hat in M4 keinen Weg zur Plattform.
  Kommt später ein Rückweg (7f), muss die Plattform `self_attested: true`
  ablehnen oder getrennt halten; das ist dann zu entscheiden.

### 6.4 Cache-Volume (F6)

| | C1 keines in M4 | C2 Datei-Cache für Zarr-Chunks über `CacheStore` | C3 Assets vorab ganz herunterladen |
|---|---|---|---|
| Wiederholung | lädt neu | Zarr aus dem Cache, COG neu | lokal |
| K3 Lesepfad | unverändert | `CacheStore` liegt vor `GatewayStore`; Treffer gehen nicht über `gateway` (unbedenklich, aber neu) | zweiter Pfad: Download über `gateway`, dann lokale Datei an GDAL |
| Abhängigkeit | keine | experimentelle API ab zarr 3.1.4 [P\*] | keine |
| Menge | Fenster der AOI | dito | ganze Dateien (S2 rund 94 MB je Band, `adr/0014` §17.1) |
| Fassung | — | Schlüssel braucht die Fassung aus dem Rezept | dito |

**Empfehlung: C1.** 7.7 nennt das Cache-Volume als Festlegung. Der Befund
in §3.4 zeigt aber, dass es heute einen eigenen Lesepfad bräuchte. Für M4,
offline mit einer Datei je Lauf, kauft es wenig. Die Festlegung aus 7.7 steht
als offene Zeile im Log.

---

## 7. Vergleichstest in der CI (Punkt 4)

### 7.1 Optionen

| | V1 `pytest` mit zwei Einstiegen, dazu Image-Prüfung im Compose-Job | V2 nur `pytest` | V3 voller Lauf im Container gegen einen lokalen Fixture-Server |
|---|---|---|---|
| prüft „derselbe Kern in zwei Hüllen“ | ✓ | ✓ | ✓ |
| prüft „gleiches Image wie `worker`“ | ✓ Versionen beider Stufen gleich | ✗ | ✓ |
| prüft Härtung (Nicht-Root, read-only) | ✓ `check` und `versions` unter den Optionen | ✗ | ✓ |
| `gateway` | unverändert | unverändert | ✗ ein lokaler Server hat eine private Adresse; `check_url` müsste dafür gelockert werden |
| K5 stabil | ✓ beide Läufe auf derselben Maschine | ✓ | ~ |

**Empfehlung: V1.** V3 bräuchte einen Testschalter, der in `gateway` private
Adressen erlaubt. Das wäre eine Lockerung einer Sicherheitsregel nur für einen
Test, und der Schalter läge im Image beim Nutzer.

### 7.2 Form (Vorschlag für M4-16)

**Teil 1, `pytest` im Backend-Job:**
- Fixtures: die synthetische COG mit `scale`/`offset` und das Zarr mit
  CF-Attributen aus `adr/0014` §6.4. Je ein Rezept: Band-Math (mit einer
  Funktion aus der Liste von M4-09) und Reprojektion (`bilinear`).
- Zwei Kindprozesse mit `get_context("spawn")`. Der eine ruft den Einstieg von
  `jobs` (`jobs/child.py`), der andere den Einstieg des Runners
  (`earthx.runner`, Unterbefehl `run`). Beide setzen vor dem Aufruf dieselbe
  Umlenkung der Fixtures (§3.6), aus einem kleinen Startziel in `tests/`.
- Verglichen werden:
  - die Pixel-Bytes und die Maske von `result.tif`: `numpy.array_equal`;
  - die Metadaten ohne `execution`, `runner_version`, `self_attested` und
    Zeiten (`adr/0014` §6.3);
  - `recipe.json`, `citation.bib`, `attribution.txt`: bytegleich.
- Beide Läufe rechnen im selben Test. Es gibt **keinen** gespeicherten
  Referenz-Hash (§3.3, K5).
- Zweckfremde Nutzung, je ein Test:
  - Rezept mit fremdem Host → Exit-Code 3, nichts gelesen;
  - unbekannte `op_version` → Exit-Code 2;
  - Ausdruck außerhalb von R5 → Exit-Code 2, numexpr nie aufgerufen;
  - vorhandener Ausgabeordner → Abbruch, nichts überschrieben;
  - Provenienzfelder in der Eingabe → Exit-Code 2;
  - Ausgabe nennt weder AOI noch ganze Adresse.
- Ein Kind des Runners hat weder `psycopg`, `psycopg_pool`, `asyncpg`,
  `botocore` noch `earthx.objectstore` in `sys.modules` (Muster `adr/0013`
  §8 Punkt 11).

**Teil 2, Compose-Job der CI:**
- `docker build --target runner -t earthx-runner:ci backend`.
- Lauf mit den Optionen aus §8 und `--network none`:
  - `versions` gibt denselben `engine`-Block aus wie
    `docker compose run --rm worker python -c …` (Stufe `app`);
  - `check` auf einem synthetischen Rezept gelingt als UID 10001 mit
    schreibgeschütztem Dateisystem;
  - `run` auf demselben Rezept scheitert mit Exit-Code 4, weil kein Netz da
    ist. Das zeigt: Der Runner liest nur über das Netz, nichts kommt aus
    dem Image.
- Diese Änderung an `.github/` ist in M4-16 ausdrücklich erlaubt (Umriss
  M4b).

---

## 8. Befehl für Windows und PowerShell (Punkt 5)

**Einmal bauen** (im Wurzelverzeichnis des Repos, PowerShell):

```powershell
docker build --target runner --build-arg EARTHX_COMMIT=$(git rev-parse --short HEAD) -t earthx-runner:0.4.0 backend
```

**Rechnen** (Rezeptdatei liegt in `.\in`, Ergebnis kommt nach `.\out`):

```powershell
docker run --rm --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges -v "${PWD}\in:/in:ro" -v "${PWD}\out:/out" earthx-runner:0.4.0 run /in/recipe.json
```

- **Eine Zeile.** PowerShell setzt Zeilen mit dem Backtick fort; eine Zeile
  vermeidet diesen Fehler [A].
- **`${PWD}`** ist der in der Docker-Doku genannte Weg für PowerShell;
  Pfade müssen absolut sein [P\*].
- **Nicht-Root** kommt aus der Stufe (`USER 10001`); `--user` ist nicht
  nötig. Unter Linux mit nativem Docker muss `.\out` für UID 10001
  beschreibbar sein. Der Befehl für Linux setzt deshalb
  `--user "$(id -u):$(id -g)"` [A].
- **Kein `-p`.** Der Runner öffnet keinen Port. Er braucht nur ausgehende
  Verbindungen (architekturplan 11).
- **Leistung:** Liegt `.\out` im Windows-Dateisystem, schreibt WSL2 langsamer
  als im Linux-Dateisystem [P\*]. Für M4 genügt der Hinweis in der Anleitung.
- **Podman:** derselbe Befehl mit `podman` statt `docker` [P\*]; nicht
  gemessen.
- **Fester Tag.** Der Tag ist die Version (F10), nie `latest`. Es gibt kein
  `docker push`, und die CI veröffentlicht nichts (Q12).
- **Lizenz von Docker Desktop:** Institute über den Schwellen brauchen ein
  Abonnement oder Podman (§3.5). Die Anleitung nennt beides. Eine
  Lizenzeinstufung ist das nicht.

---

## 9. Versionen und Tag (Punkt 5)

**Heute gibt es keine Versionsangabe** (§3.6). Zwei Stellen brauchen eine:
- `runner_version` (7.7, Q12);
- die Version von `earthx.processing` im Cache-Schlüssel (`adr/0014` §4.5,
  E2). Das baut M4-07a.

| | V1 Paketversion plus Commit | V2 nur Commit | V3 Datum |
|---|---|---|---|
| Tag | `earthx-runner:0.4.0` | `earthx-runner:1a2b3c4` | `earthx-runner:2026.10.05` |
| `runner_version` | `0.4.0+g1a2b3c4` | `1a2b3c4` | `2026.10.05` |
| fest und lesbar | ✓ | ✓ fest, schwer lesbar | ~ zwei Builds an einem Tag |
| zum Cache-Schlüssel (E2) passend | ✓ M4-07a nimmt dieselbe Version; ein Commit ohne Versionssprung leert den Cache nicht | ✗ jeder Commit leerte den Cache (wie E3, abgelehnt) | ~ |

**Empfehlung: V1.** `__version__` in `earthx/__init__.py`, SemVer 0.x. Ein
Sprung ist Pflicht, sobald sich ein Ergebnis ändern kann (das deckt sich mit
`op_version`, `adr/0014` §4.3). Der Commit kommt als Build-Argument
`EARTHX_COMMIT` dazu; fehlt Git beim Bauen, steht dort `unknown`, und der
Runner meldet es.

**Basis-Image (F11).** `python:3.12-slim` ist ein gleitender Tag. Wer Wochen
später baut, bekommt eine andere Debian- und Python-Fassung. In §3.3 hat der
Wechsel von glibc 2.39 auf 2.41 nichts geändert; zugesichert ist das nicht
[A]. Vorschlag: Digest im `FROM` wie bei Garage, Erneuern als eigener PR wie
die Lock-Datei. Das betrifft alle vier Dienste.

---

## 10. Toleranz: Präzisierung zu `adr/0014` F9 (F8)

`adr/0014` F9 (angenommen): „T2 ↔ T2L bitgleich … dieselbe CPU-Architektur
(CI, x86_64)“. Der Befund in §3.3 zeigt: Die Architektur reicht nicht.

| | T1 Zusage präzisieren | T2 Dispatch im Image festnageln | T3 Funktionsliste von R5 einschränken |
|---|---|---|---|
| Wortlaut | bitgleich auf derselben Maschine; über Maschinen bitgleich für Grundrechenarten, Vergleiche, `sqrt` und Warp; bei Funktionen bis 1 ULP (float64) bzw. 4 ULP (float32) | bitgleich auf jeder x86_64-CPU ab Stufe v2 | bitgleich über Maschinen, weil nur korrekt gerundete Funktionen bleiben |
| Wie | Text in `adr/0014` §6.3 als Nachtrag; `platform` in der Provenienz; CI vergleicht im selben Job | `ENV NPY_DISABLE_CPU_FEATURES=…` und `GLIBC_TUNABLES=glibc.cpu.hwcaps=-AVX2,-FMA,…` in der Stufe `app`, also für `worker` und Runner; ein Test prüft die Wirkung (`ld.so --list-diagnostics`) | M4-09 erlaubt kein `log`, `exp`, `sin`, keine Potenz mit nicht ganzzahligem Exponenten |
| Kosten | keine | numpy-Funktionen bis 8× langsamer, numexpr kaum [M]; glibc-Maskierung auch für `memcpy` (nicht gemessen); Namen der Tunables ändern sich still zwischen glibc-Versionen [M] | Nutzer verlieren gängige Indizes mit `log` oder Potenzen |
| belegt | [M] | nur simuliert auf einer CPU; eine echte v2-CPU fehlt [A] | [M] |

**Empfehlung: T1.** Lokale Ergebnisse sind ohnehin `self_attested` und nicht
im Cache. Abweichungen von wenigen ULP ändern keine Aussage eines Index. T2
kostet Leistung in jedem Job und hängt an still ignorierbaren Namen. M4-09
bekommt den Befund trotzdem, damit die Funktionsliste nach R5 mit Wissen
entsteht.

---

## 11. Was dieses ADR nicht entscheidet

- Einmalbefehl mit Rezept-ID und verbundener Runner (7.7, 7f); ein Rückweg
  lokaler Ergebnisse zur Plattform.
- Ein Endpunkt, der ein Rezept nur für lokal auflöst (H2, H3), und der Knopf
  „Lokal ausführen“ in der Oberfläche.
- Tile-Server auf `localhost` zur Anzeige lokaler Ergebnisse (7.7, Spike in
  15.2).
- Veröffentlichung, Signatur und Scan von Images (7.7, architekturplan 11):
  in M4 wird nichts veröffentlicht (Q12).
- pip-Paket, Wrapper-Skript `earthx run`, Apptainer-Anleitung (7.7).
- Modelle (T3) und das Flag `local_execution_allowed`.
- Ob der lokale Pfad die NC-Frage entschärft (7.7): rechtlich zu prüfen.
- Ob die vier Dienste als Nicht-Root laufen.

---

## 12. Fragen an Otto

**F1 — Image (§4)**
1. Eigene Build-Stufe `runner` im selben `Dockerfile` auf der Stufe der
   Dienste, mit `USER` 10001 und `ENTRYPOINT`; compose baut `target: app`
   **(Empfehlung)**
2. Dasselbe Image wie `worker`, Runner nur als anderer Befehl
3. Eigenes schlankes Image mit eigener Lock-Datei (rund 10 % kleiner)

**F2 — Modul (§5)**
1. Neues Modul `earthx.runner`, darf nur `processing` und `catalog.datasets`;
   Quelle in den Ketten-Verträgen des Kerns; neue Zeile in 3.1
   **(Empfehlung)**
2. In `jobs`, gesichert durch einen Test auf `sys.modules`
3. In `processing` als `python -m earthx.processing`

**F3 — Rezeptdatei in M4 (§6.1)**
1. Genau das Rezept (`recipe.json` beim Ergebnis), geprüft mit denselben
   Modellen und R5; Herkunft in M4 nur aus vorhandenen Dateien; kein neuer
   Endpunkt, kein Knopf „Lokal ausführen“ in M4-13 **(Empfehlung)**
2. Wie 1, dazu ein Endpunkt, der einen Auftrag ohne Lauf zum Rezept auflöst
3. Wie 2, aber ohne AOI; der Runner ergänzt sie lokal

**F4 — Allowlist (§6.2)**
1. Hosts des Rezepts, zusätzlich gegen `asset_hosts` der Registry im Image;
   unbekannt → Abbruch; Hosts werden vor dem Lesen genannt
   **(Empfehlung)**
2. Nur die Hosts des Rezepts (B9 wörtlich), genannt vor dem Lesen
3. Wie 2, mit Rückfrage am Terminal

**F5 — Ausgabe und Provenienz (§6.3)**
1. Neuer Ordner je Lauf mit zufälligem Namen, nie überschreiben; dieselben
   Dateien wie in der Cloud plus `provenance.json` mit `execution`,
   `self_attested`, `runner_version`, `engine`, `platform`, Zeiten;
   Arbeitsordner unter `/out` **(Empfehlung)**
2. Wie 1, aber die Provenienz in den Metadaten des Ergebnisses statt in
   eigener Datei
3. Dateien direkt in `/out`, vorhandene werden überschrieben

**F6 — Cache-Volume (§6.4)**
1. Keines in M4; die Festlegung aus 7.7 bleibt als offene Zeile im Log
   **(Empfehlung)**
2. Datei-Cache für Zarr-Chunks über `zarr.experimental.cache_store.CacheStore`
3. Assets vorab ganz herunterladen

**F7 — Vergleichstest (§7)**
1. `pytest` mit zwei Einstiegen in frischen `spawn`-Prozessen, Vergleich im
   selben Lauf ohne gespeicherte Hashes, dazu Prüfung der Stufe `runner` im
   Compose-Job (Versionen, Härtung, kein Lesen ohne Netz) **(Empfehlung)**
2. Nur `pytest`
3. Voller Lauf im Container gegen einen lokalen Fixture-Server; braucht eine
   Lockerung von `check_url` für Tests

**F8 — Toleranz über Rechner (§10, Präzisierung zu `adr/0014` F9)**
1. Zusage präzisieren: bitgleich auf derselben Maschine; über Maschinen
   bitgleich für Grundrechenarten, Vergleiche, `sqrt`, Warp; bei Funktionen
   bis 1 ULP (float64) bzw. 4 ULP (float32); Nachtrag in `adr/0014`; Befund
   an M4-09 **(Empfehlung)**
2. Dispatch von numpy und glibc im Image festnageln, für `worker` und Runner
3. Band-Math nur mit korrekt gerundeten Funktionen (R5 enger)

**F9 — Plattformen (§3.5, §8)**
1. x86_64 mit Docker Desktop oder Podman; ARM baut nativ, außerhalb der
   Bitgleich-Zusage, mit `platform` in der Provenienz **(Empfehlung)**
2. Immer `--platform linux/amd64`, auch auf ARM (Emulation)
3. Nur x86_64

**F10 — Version und Tag (§9)**
1. `__version__` in `earthx/__init__.py` (SemVer 0.x), Tag
   `earthx-runner:<version>`, `runner_version` = `<version>+g<commit>`;
   dieselbe Version nutzt M4-07a im Cache-Schlüssel **(Empfehlung)**
2. Tag und Version = kurzer Commit
3. Tag = Datum

**F11 — Basis-Image (§9)**
1. `python:3.12-slim` per Digest festnageln, Erneuern als eigener PR wie die
   Lock-Datei; gilt für alle vier Dienste **(Empfehlung)**
2. Gleitender Tag bleibt

**Kleinentscheidungen** (gelten mit der Annahme, sofern Otto nicht
widerspricht): Unterbefehle `run`, `check`, `versions` und die Exit-Codes aus
§4.2; UID 10001; Befehle in einer Zeile; der Hinweis zu WSL2 und zur Lizenz
von Docker Desktop in der Anleitung.

---

## 13. Quellen

**Im Repo [P]**
- `backend/Dockerfile` Z. 1–8 (eine Stufe, kein `CMD`); `docker-compose.yml`
  (Garage per Digest).
- `backend/earthx/__init__.py`; `pyproject.toml` (keine Version).
- `backend/earthx/catalog/datasets.py` (Importe, `asset_hosts` Z. 158, 329,
  523).
- `backend/tests/earthx/readers/mini_cog.py`, `mini_zarr.py` (Umlenkung der
  Fixtures).
- `.importlinter` (Verträge `jobs`, `no-database-in-worker-core`,
  `http-only-in-gateway`, `datasets-isolated`).
- `.github/workflows/ci.yml` (Compose-Job mit Docker).
- `docs/cloud-umgebung.md` §4 (Docker in der Sitzung, Stand 18.09.2026).

**Extern, abgerufen am 2026-10-05 [P\*], soweit nicht anders vermerkt**
- GDAL, virtuelle Dateisysteme und Konfiguration:
  `raw.githubusercontent.com/OSGeo/gdal/release/3.12/doc/source/user/virtual_file_systems.rst`,
  `…/master/doc/source/user/configoptions.rst`.
- zarr `CacheStore`:
  `raw.githubusercontent.com/zarr-developers/zarr-python/main/docs/release-notes.md`,
  `…/main/docs/user-guide/experimental.md`,
  `…/v3.1.4/src/zarr/experimental/cache_store.py`.
- Docker Subscription Service Agreement §3.2:
  `www.docker.com/legal/docker-subscription-service-agreement/`.
- Docker-Doku über `raw.githubusercontent.com/docker/docs/main/content/manuals/`:
  `desktop/features/wsl/best-practices.md`, `engine/storage/bind-mounts.md`,
  `build/building/multi-platform.md`,
  `desktop/settings-and-maintenance/settings.md`.
- Docker CLI: `raw.githubusercontent.com/docker/cli/master/docs/reference/commandline/container_run.md`,
  `…/docs/reference/run.md`.
- Podman: `raw.githubusercontent.com/containers/podman/main/docs/source/markdown/podman-build.1.md.in`,
  `…/main/README.md`; `podman-desktop/podman-desktop` `LICENSE`.
- numpy: `raw.githubusercontent.com/numpy/numpy/main/doc/source/reference/simd/build-options.rst`,
  `…/numpy/_core/src/common/npy_cpu_features.c`; Issue
  `github.com/numpy/numpy/issues/23523` (ohne Kommentare gelesen).
- glibc über den Spiegel `raw.githubusercontent.com/bminor/glibc/master/`:
  `manual/math.texi`, `manual/tunables.texi`,
  `sysdeps/ieee754/dbl-64/e_pow.c`, `…/e_log.c`,
  `sysdeps/x86_64/fpu/multiarch/ifunc-fma.h`, `sysdeps/x86/cpu-tunables.c`.
- Apptainer: `raw.githubusercontent.com/apptainer/apptainer-userdocs/main/docker_and_oci.rst`,
  `…/build_a_container.rst`.

---

## 14. Messanhang

Alle Skripte lagen im Kratzverzeichnis der Sitzung, nicht im Repo.

### 14.1 Image bauen (§3.1)

```bash
# Kopie von backend/Dockerfile mit zwei Abweichungen (Debian-Spiegel 403):
#   apt-Schritt -> COPY libexpat.so.1 (aus dem Host); CA-Bundle des Proxys für pip
sudo dockerd &                         # Daemon startet, docker pull geht
docker build --network host -t earthx-m405:measure .
docker image ls                        # 825MB Platte, 189MB komprimiert
docker run --rm earthx-m405:measure python -c "import importlib.metadata …"   # Größen je Paket
docker run --rm earthx-m405:measure python -c "import rasterio, numpy, numexpr, sys; …"
# -> 3.12.15 1.5.2 3.12.2 2.5.3 2.14.2
```

### 14.2 Stufe `runner` (§3.1)

```bash
# Dockerfile.stages: FROM python:3.12-slim AS app … ; FROM app AS runner; USER 10001:10001; ENTRYPOINT […]
docker build -f Dockerfile.stages --target app -t m405:app .
docker build -f Dockerfile.stages --target runner -t m405:runner .
docker image inspect m405:app    --format '{{json .RootFS.Layers}}' | sha256sum   # 4c212a4666bd…
docker image inspect m405:runner --format '{{json .RootFS.Layers}}' | sha256sum   # 4c212a4666bd…
```

### 14.3 Härtung (§3.2)

```bash
docker run --rm --read-only --tmpfs /tmp:size=512m --cap-drop ALL \
  --security-opt no-new-privileges --user 10001:10001 --network none \
  -v $PWD/hard.py:/m/hard.py:ro -v $PWD/out:/out earthx-m405:measure python /m/hard.py
# -> ok 512 [2, 4] 10001 0.41 s; zweiter Lauf: sha256 von result.tif gleich (68dc262104da…)
time docker run --rm earthx-m405:measure python -c "import earthx, rasterio, numexpr, xarray, zarr, rio_tiler.io"
# -> real 2,3 s
```

### 14.4 CPU-Erweiterungen (§3.3)

```bash
# dispatch.py: SHA-256 je Ergebnis; Daten aus default_rng(42), 2048² bzw. 1024² DEM
python dispatch.py                                                            # A
NPY_DISABLE_CPU_FEATURES=X86_V4,AVX512_ICL,AVX512_SPR python dispatch.py      # B
… dazu GLIBC_TUNABLES=glibc.cpu.hwcaps=-AVX512F,-AVX512CD,-AVX512BW,-AVX512DQ,-AVX512VL  # C
NPY_DISABLE_CPU_FEATURES=X86_V3,X86_V4,AVX512_ICL,AVX512_SPR \
  GLIBC_TUNABLES=glibc.cpu.hwcaps=-AVX2,-FMA,-AVX512F,-AVX512CD,-AVX512BW,-AVX512DQ,-AVX512VL \
  python dispatch.py                                                          # D
GLIBC_TUNABLES=glibc.cpu.hwcaps=-AVX2,-FMA,-AVX512F,… python dispatch.py      # E
# Wirkung der Tunables:
GLIBC_TUNABLES=… /lib64/ld-linux-x86-64.so.2 --list-diagnostics | grep 'features\[0x0\].active\[0x2\]'
# ohne: 0x7ed83203; mit -AVX2,-FMA,-AVX512F: 0x7ed82203 (Bit 12 FMA weg); mit -…_Usable: unverändert
# ulp.py: ULP-Abstand über die Bitmuster (int32/int64-Sicht), Zeit als Mittel aus 5 Aufrufen
# Im Image: dieselben Skripte per docker run, ohne und mit Einstellung D -> wie venv
```
