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

## 6. Plan (28.10.2026, von Otto am 29.10.2026 freigegeben)

**Freigabe (Otto, 29.10.2026, zu #233):** alle sechs Fragen mit Option 1 (A2, Rückfall über iframes mit Linkliste, „Merged per pass (job)“ als zweiter Knopf, 500 MB je Datei, Token-Weg erst mit dem Datensatz, ein PR); K1–K6 angenommen. ZIP über die Plattform: nein. Dazu drei Aufträge: die Rückfrage „mehrere Dateien“ in Chrome/Edge und Firefox prüfen und im PR beschreiben (§6.11), Wiedervorlage zu DS-04 (§6.12), Nachträge heißen „Nachtrag NM4-33“. Antworten in §6.10. Der Code ist Frontend und beginnt erst, wenn Otto einen freien Frontend-Platz meldet; er ist am 30.10.2026 umgesetzt (§6.15).

**Änderung (Otto, 29.10.2026, zu #233): Für Quellen mit CORS ersetzt ein ZIP je Szene den Weg A2.** Das ZIP wird im Browser gebaut, ist unkomprimiert (STORE) und wird über einen Service Worker in den Download gestreamt. client-zip ist erlaubt. Quellen ohne CORS bleiben wie freigegeben. Der überarbeitete Plan steht in §6.14; Otto hat ihn am 29.10.2026 freigegeben (§6.14.10). §6.0–§6.12 bleiben als Stand der ersten Freigabe stehen; wo §6.14 abweicht, gilt §6.14.

Stufe B: Bis zur Freigabe ist kein Produktivcode geändert. Grundlage ist `main` nach #232. Belegstufen wie in `adr/0009`: [M] in der Sitzung gemessen (Wegwerf-Skripte im Kratzverzeichnis, nicht im Repo; ausgegeben wurden nur Statuscodes, Kopfzeilen und Größen, keine Adresse), [P] Primärquelle oder Code gelesen, [S] nur Suchtreffer, [A] eigene Ableitung. Aus der Sitzung nicht erreichbar: `planetarycomputer.microsoft.com` (Proxy `403`), die Seiten von MDN, caniuse, Bugzilla und WebKit-Trac. Für MDN, caniuse und die Fetch-Spezifikation gelten ihre Rohquellen auf GitHub (§6.13).

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
- **Fragen an Otto:** 6, in §6.8; beantwortet am 29.10.2026 (§6.10).

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
  - Chrome lässt den ersten zu und fragt danach einmal „Automatic downloads“. Die Wahl gilt für die Seite [P: `download_request_limiter.h`]; die Rückfrage ist in der Sitzung gemessen (§6.11) [M].
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
  - **Eigener Schritt „Rückfrage mehrere Dateien“** (§6.11): in Chrome oder Edge und in Firefox je einmal mit frischem Profil oder privatem Fenster zwei Szenen laden. Notieren, ob und wann der Browser fragt, ob die übrigen Dateien bis zur Antwort warten und ob ein zweiter Klick nach „Allow“ wieder fragt. Danach entscheidet Otto, ob eine einmalige Erlaubnis je Website tragbar ist oder Chromium ein ZIP im Browser bekommt.
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

### 6.10 Antworten (Otto, 29.10.2026)

| Frage | Antwort |
|---|---|
| 1 Weg | Option 1: A2 |
| 2 Quelle ohne CORS | Option 1: Download des Browsers über iframes, darunter „Save link list“ und die aufklappbaren Links |
| 3 „Merged per pass (job)“ | Option 1: zweiter Knopf im Fenster, bricht den Download nicht ab |
| 4 Grenze je Datei | Option 1: 500 MB, darüber Download des Browsers |
| 5 Token-Quellen | Option 1: Weg beschrieben, gebaut mit dem Datensatz (`adr/0018` Teil B) |
| 6 Schnitt | Option 1: ein PR |
| K1–K6 | angenommen |
| ZIP über die Plattform | nein; damit ist der offene Log-Punkt vom 15.10.2026 entschieden. Backlog-Punkt 37 pflegt der Planungs-Chat |

Zusätzlich: Rückfrage „mehrere Dateien“ prüfen (§6.11) und als eigenen Schritt in die Prüfanleitung (§6.7); Wiedervorlage DS-04 (§6.12); Nachträge heißen „Nachtrag NM4-33“ (`architekturplan.md` 6.4, `adr/0018` §9.3).

### 6.11 Rückfrage „mehrere Dateien“ (Auftrag vom 29.10.2026)

**Chromium [M]:** Chrome for Testing 153 in der Sitzung, mit Fenster unter Xvfb, frisches Profil, ohne Playwright gestartet (Playwright übernimmt die Downloads über CDP und umgeht die Sperre: dort kamen auch mit Fenster immer 4 von 4 ohne Rückfrage an). Der Klick ist ein echtes Mausereignis über CDP, danach 10–14 s gewartet.

| Weg | angekommen ohne Antwort | Rückfrage |
|---|---|---|
| 4 versteckte iframes (Weg A, Rückfall) | 1 von 4 | „http://127.0.0.1:5199 wants to · Download multiple files · Block / Allow“ |
| 4 × `<a>` cross-origin, 1 s Abstand | 1 von 4 | dieselbe |
| 4 × CORS-`fetch` → Blob → `<a download>` (A2) | 1 von 4 | dieselbe |

- Die erste Datei kommt sofort, alle weiteren warten auf die Antwort. Bei A2 ist die erste Datei `ATTRIBUTION.txt`, die Rückfrage erscheint also mit dem ersten Original.
- Die Rückfrage hängt nicht am Weg: Auch Blob-Downloads mit eigenem Namen lösen sie aus. Ein ZIP (eine einzige Datei) wäre der einzige Weg ohne sie.
- **Edge:** dieselbe Engine und dieselbe Sperre (`DownloadRequestLimiter`) [A]; nicht gemessen.
- **Ob „Allow“ dauerhaft gilt:** In der Sitzung nicht prüfbar, weil sich die Schaltfläche der Browser-Oberfläche ohne Werkzeug für X-Eingaben nicht klicken lässt. Laut Quelltext ist es die Einstellung „Automatic downloads“ der Website [P: `download_request_limiter.h`]. Das prüft Otto (§6.7).
- **Firefox:** in der Sitzung nicht vorhanden; `playwright install` ist hier ausgeschlossen. Nach Bug 1859620 fragt Firefox nicht [S]. Das prüft Otto (§6.7).
- **Folge für die Umsetzung [A]:** Wartet ein Download auf „Allow“, darf die Blob-URL nicht vorher ungültig werden. Die Umsetzung misst, ob ein Download aus einer schon freigegebenen (`revokeObjectURL`) Blob-URL nach spätem „Allow“ noch ankommt. Sonst bleiben die Blob-URLs bis zum Ende des Laufs gültig, und es liegen höchstens die noch nicht bestätigten Dateien im Speicher.
- **Entscheidung danach bei Otto:** einmalige Erlaubnis je Website tragbar, oder Chromium bekommt ein ZIP im Browser (Frage 1, Option 3).

### 6.12 Wiedervorlage DS-04 (Sentinel-1 GRD)

Mit DS-04 neu prüfen:
- **Grenze je Datei:** VV-Dateien der GRD liegen bei 0,6–0,9 GB (`adr/0018` §3.1), also über 500 MB. Nach heutiger Regel gehen sie als Download des Browsers, unter dem Namen der Quelle.
- **Benennung:** Die GRD-Dateien heißen je Szene gleich (`vv.tif`, `vh.tif`). Über den Download des Browsers verlöre sich der Bezug zur Szene wie bei `TCI.tif`.
- Optionen dann: Grenze für diesen Datensatz anheben, ein ZIP im Browser für Chromium, oder Unterordner je Szene über den Ordner-Picker. Der Bucket hat CORS (`*`, §6.2).
- **Stand nach §6.14:** Mit dem ZIP je Szene entfällt für Quellen mit CORS die Grenze je Datei, und die Benennung `<Szene>_<Asset>.tif` löst die gleichen Namen. Mit DS-04 bleibt zu prüfen, ob alle Assets des GRD-Buckets CORS haben (gemessen ist nur `GET` auf den Bucket) und wie sich Szenen von 1,0–1,5 GB verhalten.

### 6.14 Überarbeitung: ein ZIP je Szene (Änderung Otto, 29.10.2026; freigegeben am 29.10.2026)

#### 6.14.1 Vorgabe (Otto)

- **Ein ZIP je Szene:** „Download full scene(s)“ lädt je Szene ein ZIP, gebaut im Browser, `<Szenen-ID>.zip`. Kein Byte läuft über das Backend.
- **Inhalt:**
  - alle Daten-Assets der Szene als `<Szenen-ID>_<Asset>.tif`;
  - `ATTRIBUTION.txt`;
  - `item.json` (das STAC-Item);
  - keine Vorschau- oder Thumbnail-Bilder.
  - Welche Assets dazugehören, kommt aus der Registry, nicht aus einer Namensliste im Frontend.
- **STORE, gestreamt über einen Service Worker,** nicht im Arbeitsspeicher. Die Grenze von 500 MB je Datei entfällt. Kann der Browser nicht streamen, schlägt der Plan einen Rückfall vor.
- **client-zip** ist als neue Abhängigkeit erlaubt.
- **Ohne CORS (DEM):** wie freigegeben, eine Datei als Download des Browsers, `ATTRIBUTION.txt` einzeln.
- **Mehrere Szenen:** je Szene ein ZIP, nacheinander. Die einmalige Rückfrage „multiple downloads“ ist akzeptiert; der Tooltip nennt sie.

#### 6.14.2 Welche Assets (aus der Registry) [P][M]

Die Collection trägt schon alles, was die Regel braucht: `earthx:band_units` (jedes Raster-Asset des Datensatzes mit seiner Einheit), `earthx:auxiliary_assets` (aus den Bändern gemachte Bilder) und `earthx:default_render.assets`.

**Regel (Vorschlag):** In ein ZIP kommen
- die Schlüssel von `earthx:band_units` ohne Muster (`*` gibt es nur bei Zarr);
- davon nicht die Assets aus `earthx:auxiliary_assets`, es sei denn, die Standarddarstellung nutzt sie.

Damit bleibt TCI (`visual`, Standarddarstellung) drin, und `preview` fällt heraus. Assets ohne `https`-Adresse auf einem Host des Datensatzes (D12) oder ohne Eintrag im Item fehlen im ZIP und werden in `ATTRIBUTION.txt` genannt.

| Datensatz | im ZIP | nicht im ZIP |
|---|---|---|
| Sentinel-2 L2A (18 Dateien) | `coastal`, `blue`, `green`, `red`, `rededge1`, `rededge2`, `rededge3`, `nir`, `nir08`, `nir09`, `swir16`, `swir22`, `aot`, `wvp`, `cloud`, `snow`, `scl`, `visual` (TCI) | `preview` (Rolle `overview`), `thumbnail` (JPEG), `granule_metadata`, `product_metadata` (XML), `tileinfo_metadata` (JSON) |
| Copernicus DEM GLO-30 | `data` (kein CORS, also kein ZIP: eine Datei, §6.14.5) | – |

- `cloud` und `snow` (Wolken- und Schneewahrscheinlichkeit in %) folgen aus der Regel, obwohl Otto sie nicht genannt hat (Frage Z2).
- Die drei Metadaten-Dateien sind keine `.tif` und fallen aus der Regel heraus (Frage Z3).
- **Nach Ottos Antwort Z3:** Zusätzlich kommen alle Assets des Items mit der STAC-Rolle `metadata` ins ZIP, als `<Szenen-ID>_<Asset><Endung der Quelle>`. Bei S2 sind das `granule_metadata` (`.xml`), `product_metadata` (`.xml`) und `tileinfo_metadata` (`.json`), zusammen unter 1 MB, also 21 Dateien aus der Quelle. Für sie gelten dieselben Prüfungen (`https`, Host des Datensatzes).

**Größe einer ganzen S2-Szene [M]:** Ein Item mit voller Kachel hat 886 MB in den 18 Dateien. `red`, `green`, `blue` und `nir` haben je 143–156 MB, die 20-m-Bänder je rund 47 MB. Alle Assets tragen `file:size`: Daraus berechnet client-zip die Länge des ZIPs vorab (`Content-Length`) ohne zusätzliche Anfrage.

#### 6.14.3 client-zip [P]

| | |
|---|---|
| Version | 2.5.1 (14.09.2026) |
| Lizenz | MIT |
| Größe | `index.js` 6,5 kB, 2,7 kB gzip; `worker.js` (für `importScripts` im Service Worker) 6,4 kB |
| Abhängigkeiten | keine |
| Eigenschaften | nur STORE (keine Kompression); Zip64 bei Bedarf; Data Descriptor; `Content-Length` vorab aus Namen und Größen (`predictLength`/`metadata`); Dateinamen UTF-8 |
| Bekannt (README) | Firefox kann einen Service Worker beenden, der noch einen Download speist (Umgehung: regelmäßige Nachricht der Seite an den Worker); Safari streamt aus dem Service Worker erst ab 15.4 |

#### 6.14.4 Messung in Chromium [M]

- **Aufbau:** Prototyp nur im Kratzverzeichnis.
  - Eine Seite übergibt dem Service Worker per `postMessage` die Liste (Namen, Adressen, Größen) und öffnet ein verstecktes iframe auf `/__originals/<Zufalls-ID>`.
  - Der Worker (`importScripts` von `worker.js`) antwortet mit `downloadZip(...)`, mit `Content-Length` und `Content-Disposition`. Die Assets holt er einzeln nacheinander per CORS-`fetch` von der Quelle.
  - Chromium 153 der Sitzung über Playwright. Speicher als RSS aller Browser-Prozesse, jede Sekunde gemessen.

| Fall | Nutzlast | Dauer | RSS vorher → Spitze | Ergebnis |
|---|---|---|---|---|
| ganze S2-Szene: 18 Assets + `ATTRIBUTION.txt` + `item.json` | 886 MB | 127 s (Proxy der Sitzung) | 366 → 494 MB (+128 MB) | 20 Einträge, alle STORE, alle CRC richtig (`zipfile.testzip`), 886 493 664 Byte, Name aus `Content-Disposition` |
| langsame Quelle (40 MB über 7 min, CORS), Seite schickt alle 10 s eine Nachricht | 42 MB | 420 s | 387 → 440 MB | vollständig, CRC richtig |
| wie oben, ohne Nachricht der Seite | 42 MB | 420 s | 385 → 436 MB | vollständig, CRC richtig: Chromium beendet den Worker auch ohne Nachricht nicht, solange er einen Download speist |

- **Speicher:** Der Speicher wächst um rund 130 MB, nicht um die Größe der Szene. Das ZIP liegt nicht im Arbeitsspeicher.
- **Dauer:** Sie hängt an der Leitung, nicht am Packen. In der Sitzung waren es rund 7 MB/s. Bei 50 Mbit/s wären es für eine Szene etwa 2,5 min, bei 10 Mbit/s etwa 12 min [A].
- **Rückfrage:** Ein Download aus einem Service Worker ist für Chrome ein Download wie jeder andere. Ab der zweiten Szene fragt Chrome einmal (§6.11).

#### 6.14.4a Firefox

- **Firefox:** in der Sitzung nicht messbar. Was fehlt:
  - `download.mozilla.org`, `archive.mozilla.org` und `ftp.mozilla.org` sind gesperrt (Proxy `403`).
  - Das Ubuntu-Paket `firefox` ist nur der Snap-Platzhalter.
  - `playwright install` ist in der Sitzung ausgeschlossen.
  - Für eine Messung hier müsste Otto `download.mozilla.org` in der Allowlist der Umgebung freigeben; das wirkt erst in einer neuen Sitzung. Sonst misst Otto selbst nach der Prüfanleitung (§6.14.7).
- **Bekannte Lage [P][S]:**
  - Firefox beendet einen Service Worker nach etwa 30 s ohne Ereignis. Ein Download, den er speist, kann dann abbrechen (client-zip-README; StreamSaver #366).
  - Umgehung: Die Seite schickt dem Worker während des Downloads alle 10 s eine Nachricht. Die Umsetzung baut das ein (wie im Prototyp).
  - Mit `Content-Length` meldet der Browser ein abgebrochenes ZIP als fehlgeschlagen, statt eine kaputte Datei zu speichern [A].

#### 6.14.5 Ablauf (Vorschlag)

1. **Klick** auf „⇩ Download full scene(s)“, in der Trefferansicht oder im Layer-Manager:
   - Das Fenster „Download full scenes“ öffnet sich und startet sofort.
   - Je Szene steht dort eine Zeile mit Zustand (wartet, lädt mit %, fertig, Fehler), dazu Attribution und Bedingungen sichtbar.
   - Knöpfe: „Cancel“, nach Ende „Retry failed“, „Merged per pass (job)“ (Frage 3 der ersten Freigabe) und „Save link list“.
2. **Welcher Weg** entscheidet sich je Datensatz aus der Registry (`earthx:access.cors`) und je Browser:
   - **ZIP-Weg:** `cors = true`, und der Service Worker ist bereit (unterstützt, sicherer Kontext, registriert, aktiv).
   - **Sonst bei `cors = true`:** der Rückfall (§6.14.6).
   - **`cors = false` (DEM):** wie freigegeben, `ATTRIBUTION.txt` als Blob, dann je Szene die Datei über ein iframe als Download des Browsers.
   - K2 („CORS beim Laden erkennen“) wird damit ersetzt: Das Feld gibt es schon (`adr/0006` §3.6, gesetzt für S2 `true`, DEM `false`). Scheitert der erste `fetch` dennoch mit `TypeError`, gilt der Rückfall (§6.14.6) für den Rest des Laufs.
3. **Je Szene ein ZIP, nacheinander:**
   - Die Seite übergibt dem Worker per `postMessage` den Namen `<Szenen-ID>.zip`, die Liste (`<Szenen-ID>_<Asset><Endung>`, Adresse, `file:size`), `ATTRIBUTION.txt` und `item.json`.
   - Danach öffnet sie ein verstecktes iframe auf `/__originals/<Zufalls-ID>`.
   - Der Worker streamt das ZIP mit `Content-Length` und `Content-Disposition`. Er meldet der Seite die gelesenen Bytes und das Ende bzw. den Fehler.
   - Erst danach beginnt die nächste Szene.
   - Fehlt einem Asset `file:size`, holt die Seite die Größe vorher per `HEAD`.
4. **`ATTRIBUTION.txt`** steht im ZIP, gebaut wie in §6.5 (unveränderte Attribution, Bedingungen, Zitierangabe, Szene, Liste „Datei → Asset“, Hinweis auf unveränderte Originale direkt von der Quelle, Zeitpunkt).
5. **`item.json`** ist das STAC-Item, wie es die Seite hat (Federation über die eigene API), eingerückt. Es enthält die Adressen der Quelle und den Footprint der Szene, keine AOI.
6. **Abbruch und Fehler:**
   - „Cancel“ bricht den laufenden `fetch` im Worker ab, das ZIP endet als abgebrochener Download.
   - Ein Fehler der Quelle (z. B. `403`) beendet das ZIP der Szene. Der Browser meldet „Failed“, weil die Länge nicht stimmt, und die Zeile nennt den Grund.
   - **Fortsetzen:** nur je Szene. „Retry failed“ lädt das ganze ZIP der Szene neu. Innerhalb eines ZIPs geht es nicht: Antworten eines Service Workers setzt Chrome nicht fort [P: `download_item_impl.cc`].
7. **Service Worker:**
   - Script unter `/__originals/sw.js`, Gültigkeitsbereich `/__originals/`. Er steuert die Seiten der App nicht und fängt nur die Download-Adressen ab.
   - Von Vite als eigener Einstieg gebaut (klassisches Skript mit client-zip). Den Weg im Dev-Server und im Build legt die Umsetzung fest.
   - Die Adresse trägt nur eine zufällige ID, keine Szenen-ID, keinen Hash und keine Quelladresse. Kommt sie doch beim Server an (Worker nicht aktiv), steht im Zugriffslog nur die Zufalls-ID.
   - Der Worker schreibt nichts ins Log.
8. **Tooltip des Knopfs** (Englisch, kurz), Vorschlag: „Download each selected scene as one ZIP of its original files, straight from the source. Your browser may ask once to allow several downloads.“ Bei `cors = false`: „… as its original file, straight from the source.“

#### 6.14.6 Rückfall, wenn der Browser nicht streamen kann

- **Wann:** kein Service Worker, etwa im privaten Fenster von Firefox, per Richtlinie abgeschaltet oder Safari vor 15.4. Oder der erste `fetch` scheitert.
- **Vorschlag:** die Einzeldateien wie A2 (§6.5), mit derselben Benennung wie im ZIP und mit `item.json` und `ATTRIBUTION.txt` als eigenen Dateien.
  - Bis 500 MB je Datei über den Speicher, darüber als Download des Browsers mit dem Namen der Quelle.
  - Das Fenster sagt in einer Zeile „Your browser cannot build the ZIP; the files come one by one.“ und nennt den Grund im Tooltip.
  - Für eine S2-Szene sind das 20 Dateien statt einer, mit einer Rückfrage.
- **Alternative:** nur die Linkliste mit „Save link list“, wie heute.

#### 6.14.7 Tests und Prüfung (Änderungen zu §6.7)

- **vitest:**
  - Regel der Assets: S2 ergibt die 18 Dateien aus §6.14.2 aus den Registry-Feldern einer Fixture-Collection. Dazu die drei Assets mit der Rolle `metadata` (Z3). Muster, `auxiliary_assets`, Standarddarstellung und Rolle werden einzeln geprüft. Zweckfremd: Asset ohne `https`, fremder Host, fehlendes `file:size`.
  - Name und Inhalt des ZIPs; Länge vorab gleich der echten Länge (`predictLength` gegen ein mit client-zip gebautes ZIP aus synthetischen Daten).
  - Wahl des Wegs (`cors`, Worker bereit, `TypeError`).
  - Nachrichten zwischen Seite und Worker: Abbruch, Fehler mitten im ZIP, unbekannte ID gibt `404`.
- **Playwright (`frontend/e2e/originals-one-click.cjs`):**
  - Ein Klick auf zwei Szenen ergibt zwei ZIPs nacheinander mit gültiger CRC und je 23 Einträgen (18 `.tif`, 3 Metadaten-Dateien, `ATTRIBUTION.txt`, `item.json`). Synthetische Bytes von einem gestellten CORS-Host.
  - DEM-Fall: eine Datei über das iframe.
  - Rückfall: Worker abgeschaltet.
  - Fehler einer Quelle mitten im ZIP.
  - Hell und dunkel, 1280, 360 und 320 px Breite.
- **Prüfanleitung für Otto, zusätzlich:**
  - **Firefox:** eine ganze S2-Szene als ZIP. Prüfen, ob es vollständig ankommt (Größe, Entpacken mit dem Explorer).
  - Ein ZIP mit Windows Explorer und 7-Zip öffnen.
  - **Safari bzw. iPhone:** Kommt das ZIP an, oder greift der Rückfall?
  - Die Rückfrage „mehrere Dateien“ bleibt ein eigener Schritt (§6.7).
- **Doku:**
  - `architekturplan.md` 6.4 Nachtrag NM4-33 mit dem ZIP je Szene.
  - `adr/0018` §9.3 Nachtrag NM4-33: Bei Token-Quellen holt der Worker mit dem Token der Seite. Das Token geht nur per `postMessage` an den eigenen Worker, nie an die Plattform.

#### 6.14.8 Umfang

Etwa 450–550 geänderte Zeilen mit Tests (Worker, Weg-Wahl, Asset-Regel, Fenster), dazu etwa 250 Zeilen Playwright-Skript und `package-lock.json`. Das liegt über dem Richtwert von 400 Zeilen. Vorschlag: trotzdem ein PR wie freigegeben (Frage 6), mit getrennten Commits für die Abhängigkeit, den Worker, die Oberfläche, die Tests und die Doku.

#### 6.14.9 Fragen an Otto (kurz)

**Z1 — Regel der Assets**
1. Aus der Registry abgeleitet: Schlüssel von `band_units` ohne `auxiliary_assets`, außer denen der Standarddarstellung; S2 ergibt 18 Dateien (§6.14.2). Keine Änderung am Backend. **(Empfehlung)**
2. Ein eigenes Registry-Feld `original_assets` je Datensatz (Backend, Collection, Test). Ausdrücklicher, aber eine Änderung am Backend.

**Z2 — `cloud` und `snow` (Wahrscheinlichkeit in %, je unter 1 MB)**
1. Mit ins ZIP, wie die Regel sie ergibt. **(Empfehlung)**
2. Nicht mit; dafür bräuchte die Registry eine Ausnahme.

**Z3 — Metadaten-Dateien der Szene** (`granule_metadata.xml` mit Sonnen- und Blickwinkeln, `product_metadata.xml`, `tileinfo_metadata.json`; zusammen unter 1 MB)
1. Mit ins ZIP, ausgewählt über die STAC-Rolle `metadata` des Items, nicht über Namen. Wer die Bänder auswertet, braucht die Winkel oft. **(Empfehlung)**
2. Nicht mit, wie vorgegeben; `item.json` nennt ihre Adressen.

**Z4 — Rückfall ohne Streaming**
1. Die Einzeldateien wie A2, bis 500 MB je Datei, mit derselben Benennung, `item.json` und `ATTRIBUTION.txt`. **(Empfehlung)**
2. Nur die Linkliste.

**Z5 — Wahl des Wegs**
1. Aus `earthx:access.cors` der Registry, mit Rückfall bei `TypeError`; ersetzt K2. **(Empfehlung)**
2. Wie K2 nur beim Laden erkennen.

#### 6.14.10 Antworten (Otto, 29.10.2026)

| Frage | Antwort |
|---|---|
| Z1 Regel der Assets | 1: aus der Registry abgeleitet, keine Änderung am Backend |
| Z2 `cloud` und `snow` | 1: mit ins ZIP |
| Z3 Metadaten-Dateien | 1: mit ins ZIP, ausgewählt über die STAC-Rolle `metadata` |
| Z4 Rückfall ohne Streaming | 1: Einzeldateien wie A2, gleiche Benennung, `item.json` und `ATTRIBUTION.txt` |
| Z5 Wahl des Wegs | 1: aus `earthx:access.cors`, Rückfall bei `TypeError`; ersetzt K2 |
| Schnitt | ein PR mit getrennten Commits |
| Firefox | prüft Otto selbst (Schritt in der Prüfanleitung, §6.14.7) |

Ein ZIP einer S2-Szene enthält damit 23 Einträge: 18 `.tif`, 3 Metadaten-Dateien, `ATTRIBUTION.txt` und `item.json`. Der Code beginnt, sobald Otto einen freien Frontend-Platz meldet.

### 6.15 Umsetzung (30.10.2026, Draft-PR [#233](https://github.com/oscipal/earthX/pull/233))

Otto meldete am 30.10.2026 einen freien Frontend-Platz. Umgesetzt ist §6.14 mit Ottos Antworten (§6.14.10), in getrennten Commits.

#### 6.15.1 Was gebaut ist

| Datei | Aufgabe |
|---|---|
| `originals.ts` (rein) | Regel der Assets aus der Collection, Namen, Weg-Wahl, Text von `ATTRIBUTION.txt`, Auftrag für den Worker |
| `originalsZip.ts` | `zipResponse`: STORE-ZIP aus den Dateien der Quelle mit client-zip, mit angekündigter Länge, Fortschritt und genau einer Meldung am Ende |
| `originalsWorker.ts` | der Service Worker; beantwortet nur `<Ordner>/__originals/<Zufalls-ID>` |
| `originalsClient.ts` | Seite: registriert den Worker, Kanal zum Worker, Speichern und Weiterreichen einzelner Dateien |
| `originalsRun.ts` | der Ablauf: Szene für Szene, Weg-Wahl und Rückfälle, Abbruch, „Retry failed“ |
| `components/OriginalFiles.tsx` | eine Zeile je Szene mit Stand, „Cancel“, „Retry failed“, „Merged per pass (job)“, „Save link list“, Links |
| `DownloadDialog.tsx`, `ViewBar.tsx`, `index.css` | Titel, Tooltips, Stil |
| `types.ts` | `file:size` am Asset, `sci:doi` und `sci:citation` an der Collection |

- **Asset-Regel:** wie §6.14.2 mit Z3. Für S2 ergibt sie 18 `.tif` und 3 Metadaten-Dateien; mit `ATTRIBUTION.txt` und `item.json` hat ein ZIP 23 Einträge (gemessen an einer echten Szene, §6.15.3).
- **Worker:**
  - Klassisches Skript im Build (`originalsWorker-<Hash>.js`, 8,8 kB mit client-zip), Modul im Dev-Server. Der Gültigkeitsbereich ist der Ordner des Skripts (`/assets/` im Build, `/src/` im Dev-Server); die Download-Adresse liegt darin als `__originals/<Zufalls-ID>`. Kein Seitenaufruf der App liegt in diesem Ordner.
  - Der Worker hält keinen Zustand außer dem einen Auftrag, schreibt kein Log und meldet Fehler nur als Art und Status.
  - Während des Downloads schickt die Seite alle 10 s eine Nachricht an den Worker (für Firefox, §6.14.4a). Meldet der Worker nicht binnen 10 s, dass der Browser die Datei angefragt hat, gilt er als nicht verfügbar, und die Szene geht den Weg der Einzeldateien.
- **Weg-Wahl (Z5):** `earthx:access.cors` und ob die Seite streamen kann; vor dem ersten Abruf ein `HEAD` auf die erste Datei. Scheitert er mit `TypeError`, gilt der Weg ohne CORS für den Rest des Laufs. Eine HTTP-Fehlerantwort auf dem `HEAD` ist kein CORS-Fall: dann scheitert die Szene mit dem Status.
- **Der Lauf tut vor dem nächsten Tick nichts** in der Seite: React startet und stoppt ihn im Dev-Modus (`StrictMode`) im selben Atemzug, und ein Lauf ohne diese Vorsicht speicherte `ATTRIBUTION.txt` und startete jede Datei doppelt (im Browser gefunden, mit Test abgesichert).
- **Schließen des Dialogs bricht den Lauf ab** (§6.5 Punkt 4), das ✕ nennt es im Tooltip. Schon gespeicherte Dateien bleiben.
- **Blob-Adressen** (Weg der Einzeldateien) gibt die Seite 30 s nach dem Klick frei, siehe §6.15.3.
- **Merged per pass (job):** zweiter Knopf, wenn ein Überflug mindestens zwei Szenen hat; er öffnet den Abschnitt der Jobs wie bisher und stoppt den Download nicht.
- **Keine Änderung** am Backend, an der Registry und an den Importregeln.

#### 6.15.2 Tests

- **vitest:** 3 857 Tests grün in 112 Dateien (vorher 3 763 in 108). Neu: `originals.test.ts` (Regel, Namen, Weg-Tabelle, `ATTRIBUTION.txt`, Auftrag), `originalsZip.test.ts` (ein ZIP-Leser im Test prüft STORE, jede CRC, jedes Byte und die Länge; 404, falsche Länge, Netzfehler, Abbruch, Abbruch durch den Browser), `originalsRun.test.ts` (alle Wege und Rückfälle, Abbruch, Wiederholen, fehlendes Datum), `originalsClient.test.ts` (Protokoll mit einem nachgestellten Worker). Angepasst: `DownloadDialog.test.tsx`, `MosaicJobs.test.tsx`, `ViewBar.test.tsx`.
- **Playwright im echten Chromium (`frontend/e2e/originals-one-click.cjs`, nicht in der CI):** elf Fälle grün, mit der echten App, dem echten Knopf und lokalen HTTPS-Quellen mit und ohne CORS:
  - ZIP hell/dunkel × breit/schmal: zwei Szenen, zwei ZIPs nacheinander, STORE, jede CRC, jedes Byte, `ATTRIBUTION.txt` nur mit der eigenen Szene, `item.json`, Name in der Zeile;
  - Datensatz ohne CORS und Quelle ohne CORS: Downloads des Browsers, `ATTRIBUTION.txt` einmal, keine Metadaten-Dateien;
  - Worker gesperrt: Einzeldateien unter ihren Namen mit `item.json`, Byte für Byte gleich;
  - Quelle antwortet `500`: die Szene scheitert mit Grund, die andere läuft durch, „Retry failed“ lädt nur die gescheiterte;
  - „Cancel“ und ✕: das ZIP endet als fehlgeschlagen, die Quelle sendet nichts mehr, die zweite Szene wird nie begonnen;
  - 14 Szenen im schmalen Fenster: die Liste scrollt im Dialog, nichts überlappt oder läuft über.
- **Produktions-Build:** `npm run build` liefert den Worker als eigene Datei; im `vite preview` streamt der gebaute Worker (Gültigkeitsbereich `/assets/`) ein gültiges STORE-ZIP.
- **Prüfungen:** `npm run lint`, `npx tsc -b`, `npm test` grün; Backend und Importregeln unverändert (Ergebnis im PR).

#### 6.15.3 Messungen mit dem fertigen Code

- **Ganze echte S2-Szene durch die App** (Chromium 153, `REAL_ITEM`): 887 MB in 132 s, Speicher der Browser-Prozesse 569 → 696 MB (+127 MB), 23 Einträge, alle STORE, alle CRC richtig.
- **Rückfrage „mehrere Dateien“ mit echtem Klick auf „Allow“** (Chromium 153 mit Fenster, frisches Profil, XTest-Klick auf die Schaltfläche):
  - Nach dem ersten Download fragt Chromium; die übrigen warten.
  - **Nach „Allow“ kommen alle an**, auch wenn die Blob-Adresse inzwischen freigegeben war (3 von 3 bei Freigabe nach 300 ms). Deshalb gibt die Seite gespeicherte Dateien nach 30 s frei, statt sie bis zum Schließen zu halten.
  - **Ein zweiter Klick fragt nicht wieder**, und die Erlaubnis gilt auch nach dem Neuladen der Seite im selben Profil (9 von 9 Dateien). Chromium merkt sich „Allow“ je Website. Edge: gleiche Engine, nicht gemessen; Firefox: prüft Otto.

#### 6.15.4 Abweichungen, Risiken und was offen ist

- **Umfang:** 2 790 geänderte Zeilen ohne `package-lock.json` (Schätzung §6.14.8: 450–550 Code und Tests, dazu 250 Playwright). Davon Produktivcode etwa 1 050, Tests und Fixture etwa 1 300, Playwright-Skript 437. Die Commits sind getrennt: Abhängigkeit, Regel, Worker mit Ablauf, Oberfläche, Fehlerbehebung, Browser-Prüfung, Doku. Der Richtwert von 400 Zeilen ist weit überschritten; Otto hatte einen PR freigegeben.
- **Viele Szenen, ein Klick:** Der Klick startet alle gewählten Szenen nacheinander; das Fenster nennt oben die Zahl der Szenen und die Summe der Größen, „Cancel“ stoppt. Es gibt keine Obergrenze und keine Frage vorab (Ottos Vorgabe „ohne extra Steps“). 40 Szenen wären etwa 35 GB. Ob eine Grenze oder eine Bestätigung ab einer Summe gewünscht ist, entscheidet Otto.
- **Fortsetzen** geht nur je Szene („Retry failed“ lädt das ZIP der Szene von vorn); ein ZIP aus dem Service Worker setzt Chrome nicht fort.
- **Safari und Firefox** sind nicht gemessen (Prüfanleitung, §6.15.5).
- **`item.json`** ist das Item, wie die Seite es hat, mit den Links der eigenen API (`self`, `collection`) und den Adressen der Quelle; es enthält keine AOI.

#### 6.15.5 Prüfanleitung für Otto

Ein Browser genügt; schmales Fenster und beide Themes sind in der Sitzung geprüft.

1. **Ein Klick, ein ZIP (Chrome oder Edge).** Datensatz Sentinel-2, zwei Szenen wählen, „⇩ Download full scenes“. Erwartet: Das Fenster zeigt je Szene eine Zeile mit „Loading n %“, danach „Done“; im Download-Ordner liegen `<Szenen-ID>.zip` für beide. Das zweite ZIP kommt erst, wenn das erste fertig ist.
2. **Rückfrage „mehrere Dateien“ (eigener Schritt).** In Chrome oder Edge und in Firefox je in einem privaten Fenster: Beim zweiten ZIP fragt Chrome/Edge „Download multiple files“; mit „Allow“ läuft es weiter. Notieren: fragt der Browser (Firefox: ja/nein)? Fragt ein zweiter Klick wieder? Danach entscheidest du, ob die einmalige Erlaubnis je Website tragbar ist oder Chromium ein ZIP im Browser bekommt (Frage 1, Option 3 der ersten Freigabe).
3. **Inhalt.** Ein ZIP mit dem Windows Explorer und mit 7-Zip öffnen: 18 `.tif`, `granule_metadata.xml`, `product_metadata.xml`, `tileinfo_metadata.json`, `ATTRIBUTION.txt`, `item.json`; kein `preview`, kein `thumbnail`. In `ATTRIBUTION.txt` stehen die Attribution mit dem Jahr der Szene, die Bedingungen und die DOI.
4. **Firefox, eine ganze Szene** (rund 0,9 GB): kommt das ZIP vollständig an? Das Fenster darf dabei offen bleiben; ein Firefox, der den Worker beendet, würde „Failed“ zeigen.
5. **Abbruch.** „Cancel“ während des Ladens: das ZIP endet als „Failed“ im Download-Fenster des Browsers, die Zeilen zeigen „Cancelled“, „Retry failed“ erscheint. ✕ im Kopf des Fensters stoppt ebenfalls.
6. **Safari (Mac oder iPhone).** Kommt das ZIP an, oder greift der Rückfall („The files come one by one.“ bzw. „Your browser downloads each file.“)? Bei den Downloads des Browsers zeigt Safari TIFF eventuell im Tab an: Dann hilft „Save link list“ unter dem Fenster.
7. **Ohne CORS: Copernicus DEM.** Eine DEM-Kachel wählen: Die Zeile zeigt „Started in your browser“, der Browser lädt die Kachel selbst unter dem Namen der Quelle (`Copernicus_DSM_COG_…_DEM.tif`), daneben `cop-dem-glo-30_ATTRIBUTION.txt`; kein ZIP. Die Hinweiszeile sagt „Your browser downloads each file.“
8. **CORS-Kopfzeile eines Hosts prüfen (PowerShell 5.1).** Eine Adresse aus „Links to the files“ im Fenster kopieren:

```powershell
$u = 'HIER-EINE-ADRESSE-AUS-DEM-FENSTER'
$r = Invoke-WebRequest -Uri $u -Method Head -Headers @{ Origin = 'https://example.org' } -UseBasicParsing
$r.Headers['Access-Control-Allow-Origin']   # * heißt: die Seite darf lesen; leer heißt: kein CORS, dann gilt der Weg ohne ZIP
$r.Headers['Content-Length']                # die Größe der Datei in Byte
```

### 6.13 Quellen

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
