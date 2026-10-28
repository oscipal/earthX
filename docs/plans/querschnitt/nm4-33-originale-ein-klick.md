# NM4-33 — Originale mit einem Klick herunterladen

**Stand:** 26.10.2026, beauftragt von Otto (Backlog-Punkt 33 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Recherche und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach UI-01; Frontend-Aufgabe (höchstens zwei Frontend-Sessions gleichzeitig), höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-33 aus `docs/plans/querschnitt/nm4-33-originale-ein-klick.md` aus.“

## 1. Anlass

„Download originals“ (M4-11b-2) liefert heute eine Liste von Links zur Quelle mit Attributionskopf. Otto (26.10.2026): „Ich will auf jeden Fall einfach einen Download-Button drücken können ohne extra Steps.“ Offen im Log ist zudem „Originale als ZIP über die Plattform“ (Bandbreite, Kosten, nicht fortsetzbar; M4-11b-2) – diese Aufgabe entscheidet das mit.

## 2. Soll

- Ein Klick auf „Download originals“ lädt die Originaldateien ohne weitere Schritte (keine Linkliste, die man einzeln anklicken muss).
- Möglichst kein Byte der Originale durch das eigene Backend (`architekturplan.md` 6.4); Attribution und Lizenzhinweis gehen mit (Datei im Download oder vorab sichtbar).
- Gilt für alle Datensätze; Quellen mit anonymem Token (`adr/0018`, falls Planetary Computer kommt) eingeschlossen.

## 3. Im Plan klären (mit Optionen und Empfehlung)

- **Wege, mit Quellen und Messung:** (a) mehrere direkte Downloads nacheinander (Browser fragt einmal); (b) ZIP über die Plattform (gestreamt, wie Job-ZIP, mit Grenzen); (c) ZIP im Browser: der Browser lädt direkt von der Quelle und packt beim Speichern (Streaming auf die Platte, Speicherbedarf, Abbruch/Fortsetzen); Voraussetzung CORS der Quelle – je Datensatz messen.
- **Quellen mit Token:** Holt der Browser beim Klick selbst ein anonymes Token direkt beim Anbieter (eigene IP, kein Plattform-Token im Browser), oder signiert das Backend? IP-Bindung der Signatur beachten (`adr/0018` N1).
- Große Downloads: Grenze, Fortschritt, Fortsetzen; Verhalten auf dem Handy.
- Neue Abhängigkeit (etwa eine kleine ZIP-Streaming-Bibliothek) nur mit Ottos Freigabe.

## 4. Grenzen

- Keine AOI, Kennungen oder signierten URLs in Logs.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: ein Klick startet den Download (Playwright im echten Browser), Attribution im Ergebnis, Verhalten ohne CORS (Rückfall), mehrere Dateien.
- Nachtrag `architekturplan.md` 6.4 bzw. Log-Zeile zu Punkt „Originale als ZIP“.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n) mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat, siehe Kopf des Backlogs).
- Vor „fertig“ ist main geholt.

## 6. Plan (28.10.2026, Vorschlag, Freigabe durch Otto offen)

Stufe B: Bis zur Freigabe ist kein Produktivcode geändert. Grundlage ist `main` nach #232. Belegstufen wie in `adr/0009`: [M] in der Sitzung gemessen (Wegwerf-Skripte im Kratzverzeichnis, nicht im Repo; ausgegeben wurden nur Statuscodes, Kopfzeilen und Größen, keine Adresse), [P] Primärquelle oder Code gelesen, [S] nur Suchtreffer, [A] eigene Ableitung. Aus der Sitzung nicht erreichbar: `planetarycomputer.microsoft.com` (Proxy `403`), die Seiten von MDN, caniuse, Bugzilla und WebKit-Trac. Für MDN, caniuse und die Fetch-Spezifikation gelten ihre Rohquellen auf GitHub (§6.9).

### 6.0 Kurzfassung

- **Empfehlung (Weg A2):** Ein Klick lädt sofort: zuerst `ATTRIBUTION.txt`, dann jede Originaldatei nacheinander. Der Browser lädt jede Datei selbst direkt von der Quelle.
  - **Quelle mit CORS:** per `fetch` in den Speicher, dann unter eigenem Namen `<Szene>_<Asset>.tif` gespeichert.
  - **Quelle ohne CORS:** als Download des Browsers über ein verstecktes iframe, unter dem Namen der Quelle.
  - **Kein Byte durch das Backend**, keine neue Abhängigkeit, keine Änderung am Backend.
- **Warum nicht einfach Links nacheinander anstoßen (Weg A)?** Bei Sentinel-2 heißt jede Originaldatei `TCI.tif` [M]. Im Download-Ordner stünden `TCI.tif`, `TCI (1).tif`, `TCI (2).tif` …, ohne Bezug zur Szene. Den Namen kann die Seite bei fremden Hosts nicht setzen: `download` wird cross-origin ignoriert [M][P]. S3 lehnt anonym `response-content-disposition` mit `400` ab [M]. Safari zeigt TIFF im Tab an, statt es zu speichern [P].
- **ZIP über die Plattform (Weg B): nein.** Jedes Byte liefe zweimal durch `api`, ein Abbruch begänne von vorn, und die Plattform gäbe Originaldaten weiter. Das widerspricht `architekturplan.md` 6.4. Damit ist der offene Punkt „Originale als ZIP“ (Log 2026-10-15) entschieden, sofern Otto zustimmt.
- **ZIP im Browser (Weg C):** Auf die Platte gestreamt geht das verlässlich nur in Chromium am Desktop (`showSaveFilePicker`) [P]. Es braucht CORS an jeder Quelle, und der DEM-Bucket hat keins [M]. Es braucht außerdem eine neue Abhängigkeit oder einen eigenen ZIP-Schreiber. Vorschlag: nicht jetzt (Frage 1).
- **Gemessen [M]:**
  - CORS: Sentinel-2-Bucket ja (`*`, auch `Range`), Sentinel-1-GRD-Bucket ja (`*`), Copernicus-DEM-Bucket nein.
  - Chromium: 171 MB per CORS-`fetch` in 9 s, gespeichert unter eigenem Namen, Heap etwa 172 MB.
  - Mehrere Downloads aus einem Klick in Chromium: per `a.click()` ohne Abstand kommt nur 1 von 4 an, mit 1 s Abstand alle 4. Über versteckte iframes kommen alle 4 ohne Abstand an.
- **Quellen mit anonymem Token (Planetary Computer):** Der Browser holt das Token beim Klick selbst (`adr/0018` N1), danach gilt derselbe Weg. Das Backend signiert nicht. Gebaut wird erst mit dem Datensatz (Frage 5).
- **Fragen an Otto:** 6, in §6.8.

### 6.1 Stand im Code [P]

- **Trefferansicht (`components/ViewBar.tsx`):** „⇩ Download full scene(s)“ öffnet `DownloadDialog` im Fall `originals`. Bei COG ist der Knopf offen, bei anderen Formaten gesperrt mit Grund (`isCogFormat`).
- **Dialog (`DownloadDialog.tsx`, `OriginalFiles.tsx`):**
  - Er zeigt Attribution (unveränderte Fassung, mit Aufnahmejahren) und Nutzungsbedingungen.
  - Hat mindestens ein Überflug zwei oder mehr Szenen, fragt er „Each scene separately“ oder „Merged per pass (job)“ (`MosaicJobs.tsx`).
  - Sonst zeigt er die Links (`<a href download target=_blank>`) je Gruppe und „Save link list“ (`.txt`).
- **Welche Datei:** je Szene genau ein Asset, das erste Asset der Standarddarstellung (`defaultRenderOf(...).assets[0]`). Bei Sentinel-2 ist das `visual` (TCI), beim DEM `data`. Es zählt nur `https` auf Hosts aus `earthx:source.asset_hosts` (`download.ts::isDirectDownloadHref`).
- **Layer-Manager:** Eine angeheftete Ebene aus „View whole scene“ öffnet denselben Dialog. Die Items holt `store.openDownloadDialog` vorher nach.
- **Attributionstext:** Das Backend baut ihn für den Zuschnitt in `access/download.py::build_notice_text`: Titel, Attribution, Bedingungen mit URL, Zitierangabe, Items je Gruppe, Zeitpunkt. Die Collection trägt alles davon auch im Frontend: `earthx:license_flags`, `sci:citation`, `sci:doi`.
- **Kein Logging im Frontend** (kein `console.*` außerhalb der Tests) und keine Content-Security-Policy.

### 6.2 Messung [M]

Gemessen in der Sitzung mit `curl` (über den Proxy) und mit Playwright/Chromium von einer Seite auf `http://localhost`. Sentinel-2 an den 20 jüngsten Items, das DEM an einer Kachel.

| Host (Datensatz) | CORS `GET` | Preflight `Range` | ETag | Größe je Original | Dateiname der Quelle |
|---|---|---|---|---|---|
| `e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com` (Sentinel-2 L2A) | `Access-Control-Allow-Origin: *` | erlaubt (`range`) | ja (nicht exponiert) | `visual`: 1–171 MB, Median 91 MB | immer `TCI.tif` |
| `copernicus-dem-30m.s3.amazonaws.com` (Copernicus DEM GLO-30) | **kein CORS**; `fetch` scheitert in Chromium (`TypeError`) | `403` | ja | etwa 40 MB je Kachel | eindeutig je Kachel |
| `sentinel-s1-l1c.s3.eu-central-1.amazonaws.com` (Sentinel-1 GRD, DS-04) | `*` (nur `GET`) | nicht gemessen | – | VV 0,6–0,9 GB (`adr/0018` §3.1) | – |
| Planetary Computer (Token-API, Blob) | aus der Sitzung gesperrt | – | – | – | – |

Chromium, von `http://localhost`:

- **`fetch` auf Sentinel-2:**
  - Ohne `Range`: `200`. Mit `Range: bytes=100-`: `206`. `Content-Length` ist lesbar.
  - `ETag` und `Content-Range` sind nicht lesbar, weil sie nicht exponiert werden.
- **171-MB-Datei per `fetch`:**
  - Mit Fortschritt gelesen, danach als Blob unter dem Namen `SCENE-ID_visual.tif` gespeichert: angekommen ist genau dieser Name, mit 171 048 129 Byte.
  - Dauer 9,1 s über den Proxy der Sitzung. Der JS-Heap lag danach bei 172 MB: eine Datei liegt ganz im Speicher.
- **Mehrere Downloads aus einem Klick** (4 Dateien, 2 Hosts, headless):

  | Art | Abstand | angekommen | Dateiname |
  |---|---|---|---|
  | `<a download>` cross-origin | 0 ms | 1 von 4 | der der Quelle; `download` ignoriert |
  | `<a download>` cross-origin | 300 ms | 1 von 4 | der der Quelle |
  | `<a download>` cross-origin | 1000 ms | 4 von 4 | der der Quelle; zweimal `TCI.tif` |
  | verstecktes `iframe` | 0 ms | 4 von 4 | der der Quelle |
  | verstecktes `iframe` | 300 ms | 4 von 4 | der der Quelle |

  Headless fragt Chromium nicht nach „mehreren Dateien“. Im normalen Chrome fragt es einmal (§6.3).
- **Anonymer `GET`** mit `?response-content-disposition=attachment;filename=…` auf den Sentinel-2-Bucket: `400 InvalidRequest` („Request specific response headers cannot be used for anonymous GET requests“).

### 6.3 Was die Browser tun [P][S]

- **`download` cross-origin:** Chrome (ab 65), Safari und Firefox ignorieren `download` bei fremden Hosts. Es folgt eine normale Navigation, und die Antwort der Quelle entscheidet, ob ein Download entsteht. Bei `blob:`, `data:` und gleichem Ursprung gilt der Name aus `download` [P: MDN, BCD, Chrome-65-Blog].
- **TIFF:** Nur Safari zeigt TIFF an [P: MDN]. Ohne `Content-Disposition: attachment`, und die Buckets senden es nicht, öffnet Safari die Datei im Tab bzw. im iframe, statt sie zu speichern [A].
- **Mehrere Downloads:**
  - Chrome lässt den ersten zu und fragt danach einmal „Automatic downloads“. Die Wahl gilt für die Seite [P: `download_request_limiter.h`].
  - Firefox fragt laut Bug 1859620 nicht [S].
  - Safari fragt je Website mit „Ask“ als Vorgabe [S].
- **Blob speichern** (`<a download>` auf `blob:`): alle Engines, iOS-Safari ab 13 [P: BCD].
- **Speichergrenzen für Blobs:**
  - Chrome am Desktop etwa 2 GB, Firefox laut einer älteren Tabelle 800 MiB [S].
  - Auf Android ein Bruchteil des RAM [S].
  - iOS: Ein Bericht nennt einen Absturz bei 1,41 GB, 227 MB gingen [S: StreamSaver #373].
- **Auf die Platte streamen:**
  - `showSaveFilePicker` und `showDirectoryPicker` gibt es nur in Chromium am Desktop. Mozilla und WebKit lehnen sie ab [P: BCD, standards-positions].
  - Der Ordner-Picker sperrt `Downloads` und `Home` selbst, der Nutzer müsste einen Unterordner wählen [P: Chromium].
  - Ein ZIP per Service Worker wäre die einzige Lösung ohne Picker für Safari und Firefox. Firefox beendet den Worker aber nach etwa 30 s Leerlauf, ein Download per Service Worker ist nie fortsetzbar, und iOS 18.2/18.3 hatte eine Regression [P: StreamSaver-README, Chromium `download_item_impl.cc`; S: #366, #373].
- **Fortsetzen:**
  - Chrome setzt einen per Navigation gestarteten Download mit ETag oder `Last-Modified` selbst fort, automatisch bis zu 5 Mal, danach über „Resume“ [P: `download_item_impl.cc`].
  - Was per `fetch` geladen wird, setzt nur eigene Logik fort.
- **`Range` ohne Preflight:** `bytes=N-` ist seit Chrome 99, Firefox 117 und Safari 16 ohne Preflight erlaubt; `Content-Length` ist lesbar [P: Fetch-Spec, BCD].
- **Planetary Computer:**
  - Für CORS an der Token-API gibt es keinen Beleg, weder dafür noch dagegen.
  - Blob-Container haben teils CORS: Ein Container hatte es bis 09/2026 nicht, das ist laut Maintainer behoben [P: PlanetaryComputer #499].
  - Das Doku-Beispiel des `sign`-Endpunkts trägt `sip=` (IP-Bindung), das Beispiel der Token-Antwort nicht [P: `sas.md`].

| Browser | A: Links nacheinander (Navigation) | A2: CORS-`fetch` → Blob, eigener Name | C: ZIP per `showSaveFilePicker` | C′: ZIP per Service Worker |
|---|---|---|---|---|
| Chrome/Edge Desktop | Download, Name der Quelle, einmal Nachfrage, fortsetzbar | ja, einmal Nachfrage [M] | ja | ja, nicht fortsetzbar |
| Firefox | Download, Name der Quelle | ja; Grenze je Datei beachten | nein | Worker endet nach ~30 s Leerlauf |
| Safari macOS | **zeigt TIFF an, kein Download** | ja | nein | ab 15.4 |
| iOS Safari | wie Safari | ja, Datei für Datei; Speicher je Datei klein halten | nein | Absturzberichte |
| Android Chrome | wie Chrome | ja; Speicher je Datei | ungeklärt | wie Chrome |

### 6.4 Optionen

| | **A2 (Empfehlung)** | A: Links nacheinander | C: ZIP im Browser | B: ZIP über die Plattform |
|---|---|---|---|---|
| Ein Klick | ja | ja | Chromium: Klick plus Speichern-Dialog; sonst Rückfall | ja |
| Dateiname | `<Szene>_<Asset>.tif` (CORS); Name der Quelle (sonst) | Name der Quelle (`TCI (3).tif`) | im ZIP frei | im ZIP frei |
| Attribution | `ATTRIBUTION.txt` als erste Datei, im Dialog sichtbar | wie A2 (Blob) | im ZIP | im ZIP |
| Safari/iOS | ja (CORS-Quellen) | nein | nein (Rückfall) | ja |
| Quelle ohne CORS (DEM) | iframe-Download (Chrome, Firefox); Safari: Links | gleich | nicht möglich | egal |
| Speicher im Browser | eine Datei (S2 ≤ 171 MB) | keiner | keiner (Chromium) | keiner |
| Fortsetzen | je Datei: Fertiges bleibt, „Retry“ lädt den Rest; innerhalb einer Datei von vorn | Browser setzt fort | nein | nein |
| Bytes durch das Backend | 0 | 0 | 0 | alles, zweimal |
| Neue Abhängigkeit | nein | nein | client-zip (MIT, 2,6 kB) oder Eigenbau | nein |
| Aufwand | Frontend, etwa 350 Zeilen mit Tests | etwa 150 Zeilen | A2 plus ZIP plus Weiche | Route, Grenzen, Lizenzstufe, Nachtrag `adr/0015` |

**Empfehlung: A2.** Sie ist der einzige Weg, der in allen Browsern ohne Zusatzschritt Dateien mit Szenenbezug liefert und die Bytes nicht durchs Backend schickt. Der Preis ist eine Datei im Speicher und kein Fortsetzen innerhalb einer Datei. Bei Originalen bis etwa 0,5 GB ist das tragbar [A]. Größere Dateien gehen den Weg der Navigation (Frage 4).

### 6.5 Ablauf nach Freigabe (A2)

1. **Klick** auf „⇩ Download full scene(s)“, in der Trefferansicht oder im Layer-Manager:
   - Das Fenster „Download full scenes“ öffnet sich und **startet sofort**. Die Frage „Each scene separately / Merged per pass (job)“ entfällt (Frage 3).
   - Sichtbar sind Titel, Attribution, Bedingungen und je Datei eine Zeile mit Zustand (wartet, lädt mit %, gespeichert, im Browser gestartet, Fehler). Dazu „Cancel“, nach Ende „Retry failed“ und „Close“.
   - Erklärungen stehen im Tooltip (UI-01 §4).
2. **`ATTRIBUTION.txt` zuerst:**
   - Im Browser gebaut, in derselben Gliederung wie `build_notice_text`: Titel, unveränderte Attribution mit Aufnahmejahren, Bedingungen und URL, Zitierangabe, Items je Gruppe, die Zuordnung „Datei → Szene, Asset“, Hinweis „unmodified original files, downloaded directly from the source“, Zeitpunkt.
   - Name: `<dataset-id>_ATTRIBUTION.txt`. Ohne Aufnahmejahre bei `{year}` (NM4-01) startet nichts, und das Fenster nennt den Grund.
3. **Je Datei nacheinander**, immer nur eine gleichzeitig (Rücksicht auf die Quelle, Speicher):
   - **CORS-Weg:**
     - `fetch(href)`; an der Antwort entscheidet sich, ob CORS geht.
     - Der Fortschritt kommt aus `Content-Length` und den gelesenen Bytes. Danach wird ein Blob gespeichert unter `<itemId>_<asset><Endung der Quelle>`.
     - Der Name ist bereinigt (nur `[A-Za-z0-9._-]`); doppelte Namen bekommen `-2`, `-3`.
     - Die Blob-URL wird nach dem Speichern wieder freigegeben.
   - **Rückfall:**
     - `fetch` scheitert mit `TypeError` (CORS oder Netz, der Browser unterscheidet das nicht).
     - Die Datei und alle weiteren desselben Hosts gehen dann als verstecktes iframe an den Download des Browsers. Ihr Zustand ist „Started in your browser“, Name der Quelle.
     - Darunter steht „Save link list“, und die Links bleiben aufklappbar. Das ist der Weg für Safari und für Download-Manager (Frage 2).
   - **Über der Grenze** (Frage 4): `HEAD` nennt die Größe vorab. Über der Grenze geht die Datei gleich den Rückfall-Weg.
4. **Abbruch:**
   - „Cancel“ bricht den laufenden `fetch` ab (`AbortController`). Gespeicherte Dateien bleiben.
   - „Retry failed“ lädt die nicht fertigen Dateien neu, die fertigen nicht.
   - Wird das Fenster während des Ladens geschlossen, bricht das ebenfalls ab. Der Grund steht im Tooltip von ✕.
5. **Chrome** fragt beim zweiten Download einmal nach „mehreren Dateien“. Das ist ein Schritt des Browsers, nicht der App, und er kommt pro Seite einmal. Der Tooltip des Knopfs sagt es.
6. **Handy:** derselbe Weg. Es liegt immer nur eine Datei im Speicher (S2 höchstens 171 MB). Die Grenze aus Frage 4 gilt dort gleich. Ob iOS je Datei nachfragt, prüft Otto am Gerät (§6.7).
7. **Nichts im Log oder in URLs:**
   - Kein `console.*`.
   - Fehlertexte nennen Datei-Nummer und Szene, nie `href` oder Token.
   - Die App-URL ändert sich nicht.
   - Weder Items noch Adressen gehen an die Plattform.

**Code (geplant):**
- **`frontend/src/originals.ts` (neu, rein):** Plan der Dateien, Dateinamen, Text von `ATTRIBUTION.txt`, Zustandsmaschine des Ladens mit eingespritztem `fetch` und Speichern.
- **`components/OriginalFiles.tsx`:** Fortschrittsliste statt Wahl und Linkliste.
- **`DownloadDialog.tsx`:** Titel und Start beim Öffnen.
- **`download.ts`:** Name bei „Save link list“ unverändert.
- **Ohne Änderung:** Backend, Registry, Importregeln, Abhängigkeiten.

### 6.6 Quellen mit anonymem Token (Planetary Computer, `adr/0018` Teil B)

- **Ablauf:**
  - Vor dem ersten Abruf eines Hosts holt der Browser das Token selbst bei der Token-API der Quelle. Die Adresse steht in der Registry, als Feld der Quelle, das mit dem Datensatz kommt.
  - Das Token hängt der Browser nur im Speicher an die Adresse. Danach gilt §6.5: `fetch` mit CORS am Blob-Container, sonst iframe.
  - Bindet die Quelle das Token an die IP (`sip=`), ist es die IP des Nutzers.
- **Das Token geht nie an die Plattform**, nicht in den Speicher des Browsers (`localStorage`), nicht in `ATTRIBUTION.txt`, „Save link list“, Permalink oder Fehlertexte. Die Linkliste nennt bei solchen Quellen die Adressen ohne Token.
- **Das Backend signiert nicht:** Ein vom Backend signierter Link trüge die IP des Backends (`sip=`) und liefe beim Nutzer nicht. Außerdem schließt Bedingung (c) es aus (`adr/0018` N1).
- **Voraussetzung:** Ottos Messung `adr/0018` §11 C, also CORS an der Token-API. Ohne sie bekommt der Datensatz keine Originale (N1). Ob der Blob-Container CORS hat, entscheidet nur zwischen eigenem Namen und Namen der Quelle.
- **Nachtrag:** `adr/0018` „§9.3 Nachtrag NM4-33“. N1 meinte eine Navigation zur Blob-Adresse; mit NM4-33 ist es zuerst `fetch` und bei fehlendem CORS die Navigation.

### 6.7 Tests und Prüfung (nach Freigabe)

- **vitest (`originals.test.ts`):**
  - Dateinamen: bereinigt, Endung aus der Quelle, doppelte Namen, fremde Zeichen in der Item-ID.
  - `ATTRIBUTION.txt`: Jahre, fehlendes Jahr bei `{year}` sperrt, DEM ohne Jahr, Zitierangabe, Gruppen.
  - Zustandsmaschine: alles CORS; `TypeError` mit Rückfall für den Host; HTTP `403`/`404` als Fehler der Datei (kein Rückfall); Abbruch; „Retry failed“ lädt nur den Rest; Größe über der Grenze gleich Rückfall.
  - Zweckfremd: `javascript:`/`s3://`/fremder Host fließt nicht ein; Ergebnisse aus einem abgebrochenen Lauf landen nicht im nächsten.
- **Komponententest:** Ein Klick öffnet das Fenster und startet. Attribution und Bedingungen sind sichtbar, keine Wahlfrage.
- **Playwright (`frontend/e2e/originals-one-click.cjs`, wie die übrigen Skripte nicht in der CI):**
  - Dev-Server; Antworten der API und der beiden Quell-Hosts gestellt (synthetische Bytes), ein Host mit CORS, einer ohne.
  - Ein Klick ergibt:
    - `ATTRIBUTION.txt` mit Attribution und Zuordnung;
    - Dateien mit Szenennamen vom CORS-Host;
    - Download-Ereignisse über iframes vom Host ohne CORS;
    - mehrere Dateien.
  - Cancel und Retry.
  - Hell und dunkel, 1280, 360 und 320 px Breite. Prüfung auf Überlappen und Überlauf, Bildschirmfotos.
- **Prüfanleitung für Otto im PR:**
  - Chrome und Safari (Mac oder iPhone) mit S2 (CORS) und DEM (ohne).
  - PowerShell 5.1 für die CORS-Kopfzeilen der Hosts.
- **Pflicht-Checks:** Backend, Frontend, Importregeln und Compose müssen grün sein. Lokal laufen `npm run lint`, `npx tsc -b`, `npm test`, `ruff check backend` und `pytest`.
- **Doku:**
  - Nachtrag NM4-33 in `architekturplan.md` 6.4: Originale holt der Browser selbst; kein ZIP über die Plattform.
  - `adr/0018` „§9.3 Nachtrag NM4-33“.
  - Log-Zeilen mit PR-Nummer.

### 6.8 Fragen an Otto

Kurz beantwortbar: je Frage eine Nummer.

**Frage 1: Weg**
1. A2: Der Browser lädt jede Datei selbst; mit CORS unter Szenennamen, ohne CORS als Download des Browsers. Kein ZIP. **(Empfehlung)**
2. A: nur Links nacheinander anstoßen. Die Namen sind die der Quelle (`TCI (3).tif`), und Safari speichert nicht.
3. A2 und zusätzlich in Chromium am Desktop ein ZIP über den Speichern-Dialog. Dafür braucht es die neue Abhängigkeit client-zip (MIT, 2,6 kB) oder einen eigenen ZIP-Schreiber von etwa 150 Zeilen.
4. ZIP über die Plattform (Weg B).

**Frage 2: Quelle ohne CORS (heute das DEM)**
1. Download des Browsers über iframes, Name der Quelle; darunter „Save link list“ und die aufklappbaren Links. Das ist der Weg für Safari. **(Empfehlung)**
2. Für solche Quellen gleich nur die Links wie heute, kein Ein-Klick.

**Frage 3: „Merged per pass (job)“**
Bisher fragt der Dialog vorher „Each scene separately / Merged per pass (job)“; diese Wahlfrage widerspricht dem einen Klick.
1. Der Klick lädt sofort. Im Fenster steht zusätzlich der Knopf „Merged per pass (job)“, wenn ein Überflug zwei oder mehr Szenen hat. Er bricht den Download nicht ab und öffnet die Jobs wie heute. **(Empfehlung)**
2. „Merged per pass (job)“ entfällt in diesem Fenster. Ein Mosaik ganzer Szenen ohne Schritte ist dann in der Oberfläche nicht mehr erreichbar.
3. Die Frage bleibt vor dem Download.

**Frage 4: Grenze je Datei im Speicher**
1. Bis 500 MB je Datei über `fetch`, darüber gleich der Download des Browsers mit dem Namen der Quelle. Sentinel-2 und DEM liegen darunter, Sentinel-1 GRD (VV bis 0,9 GB) darüber. **(Empfehlung)**
2. 1 GB (riskant in Firefox und auf Handys).
3. Keine Grenze.

**Frage 5: Token-Quellen (Planetary Computer)**
1. Der Weg steht in §6.6 und im Nachtrag zu `adr/0018`. Gebaut wird er mit dem Datensatz (Teil B, nach Ottos Messung), weil es heute weder einen Datensatz noch eine Messung gibt. **(Empfehlung)**
2. Den Token-Schritt jetzt schon bauen, mit einem Registry-Feld, das noch kein Datensatz nutzt.

**Frage 6: Schnitt**
1. Ein PR: Plan, Code, Tests und Doku, als eigene Commits. Etwa 350 Zeilen Code und Tests, dazu etwa 200 Zeilen Playwright-Skript. **(Empfehlung)**
2. Zwei PRs: zuerst `originals.ts` mit vitest, dann Oberfläche und Playwright.

**Kleinentscheidungen** (gelten, wenn Otto nicht widerspricht):
- **K1** Die Dateinamen sind `<itemId>_<asset><Endung>`; `ATTRIBUTION.txt` heißt `<dataset-id>_ATTRIBUTION.txt`.
- **K2** CORS wird beim Laden erkannt, nicht als Feld in der Registry. Element 84 kann CORS ändern, und der Rückfall fängt das ab.
- **K3** Es läuft immer nur eine Datei gleichzeitig.
- **K4** `ATTRIBUTION.txt` baut der Browser aus der Collection, ohne neue Backend-Route. Die Gliederung folgt `build_notice_text`, die Fassung ist die unveränderte.
- **K5** „Save link list“ bleibt, als kleiner Knopf mit Tooltip.
- **K6** Der Layer-Manager nimmt denselben Weg.

### 6.9 Quellen

- **Fetch-Spezifikation** (Range ohne Preflight, `Content-Length` lesbar): https://raw.githubusercontent.com/whatwg/fetch/main/fetch.bs
- **MDN:**
  - `<a download>`: https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/html/reference/elements/a/index.md
  - Bildformate (TIFF nur in Safari): https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/media/guides/formats/image_types/index.md
  - `showSaveFilePicker`: https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/api/window/showsavefilepicker/index.md
- **Browser-Compat-Data:**
  - https://raw.githubusercontent.com/mdn/browser-compat-data/main/html/elements/a.json
  - https://raw.githubusercontent.com/mdn/browser-compat-data/main/api/Window.json
  - https://raw.githubusercontent.com/mdn/browser-compat-data/main/http/headers/Range.json
- **Chrome 65, `download` cross-origin:** https://raw.githubusercontent.com/GoogleChrome/developer.chrome.com/main/site/en/blog/chrome-65-deprecations/index.md
- **Chromium:**
  - Mehrere Downloads: https://raw.githubusercontent.com/chromium/chromium/main/chrome/browser/download/download_request_limiter.h
  - Fortsetzen: https://raw.githubusercontent.com/chromium/chromium/main/components/download/internal/common/download_item_impl.cc
  - Gesperrte Ordner: https://raw.githubusercontent.com/chromium/chromium/main/chrome/browser/file_system_access/chrome_file_system_access_permission_context.cc
- **Standardpositionen:** https://github.com/mozilla/standards-positions/issues/154, https://github.com/WebKit/standards-positions/issues/28
- **StreamSaver.js:**
  - README: https://raw.githubusercontent.com/jimmywarting/StreamSaver.js/master/README.md
  - Issues: https://github.com/jimmywarting/StreamSaver.js/issues/366, https://github.com/jimmywarting/StreamSaver.js/issues/373
- **FileSaver.js (Blob-Grenzen):** https://raw.githubusercontent.com/eligrey/FileSaver.js/master/README.md
- **client-zip:** https://github.com/Touffy/client-zip (MIT, 2,6 kB, nur Store, Zip64)
- **multi-download** (1 s Abstand, MIT): https://github.com/sindresorhus/multi-download
- **Planetary Computer:**
  - SAS-Doku: https://raw.githubusercontent.com/microsoft/PlanetaryComputerDataCatalog/main/docs/concepts/sas.md
  - CORS der Blob-Container: https://github.com/microsoft/PlanetaryComputer/issues/499
