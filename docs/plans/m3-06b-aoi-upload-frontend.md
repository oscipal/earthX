# M3-06b — AOI-Upload: Frontend auf die Route: Plan

**Aufgabe:** M3-06b aus `docs/plans/m3-dritte-quelle-und-interface.md` §4.
**Stufe B — wartet auf Freigabe durch Otto** (Fragen in §9).
**Ort im Repo:** `docs/plans/m3-06b-aoi-upload-frontend.md`
**Grundlagen:** `plans/m3-dritte-quelle-und-interface.md` P7, M3-06b, §1.2
(Oberflächentexte nur Englisch); `plans/m3-06a-aoi-upload-backend.md` §§6, 8–10
(Route, Deckel, Fehlerform) und Log 26.09.2026 (M3-06a umgesetzt, F5 = 2);
`prototyp-inventar.md` F3; heutiger Code in `frontend/src/aoiFile.ts`,
`frontend/src/components/ControlPanel.tsx` (`AoiExtras`), `frontend/src/api.ts`,
`frontend/vite.config.ts`, `backend/earthx/api/aoi_upload_route.py`,
`backend/earthx/logging.py`.

---

## 1. Ziel in einem Satz

Der Upload-Knopf der Suchkachel schickt die gewählte Datei an
`POST /aoi/upload` statt sie im Browser zu parsen, nimmt damit auch
Shapefile-ZIPs an und zeigt jede Abweisung der Route als verständliche
englische Meldung.

---

## 2. Heutiger Stand

- **`frontend/src/aoiFile.ts`** parst GeoJSON und einen minimalen KML-Teil im
  Browser (`DOMParser`), ohne Größen-, Punktanzahl- oder Gültigkeitsprüfung;
  „erste brauchbare Geometrie gewinnt“; lässt auch `LineString` durch; liest
  eine Datei, die kein JSON ist, ersatzweise als KML (etwa `.txt`/`.xml`).
  Einziger Aufrufer: `AoiExtras` in `ControlPanel.tsx`.
- **`AoiExtras`** ruft `parseAoiFile(file.name, await file.text())`, puffert
  einen Punkt wie das Zeichenwerkzeug (M3-08 F5a: Punkt für die Suche,
  Quadrat für die Karte), setzt die AOI über `setAoi(geom, point)` und fliegt
  zur Bounding Box. Fehler landen über `setError` in der gemeinsamen
  Fehlerzeile. Knopf „⤒ Upload KML/JSON“, `accept` ohne `.zip`.
- **„Last AOI“** (`store.ts`: `lastAoi`, `lastAoiPoint`, `useLastAoi`) lebt
  vollständig im Client und wird von `setAoi` gepflegt — bleibt unverändert
  (F3 laut Aufgabe).
- **Route aus M3-06a** (auf `main`): `POST /aoi/upload?filename=<name>`, der
  Dateiinhalt als roher Anfragekörper (kein `multipart/form-data`,
  M3-06a §6 Option B). `200` liefert eine nackte GeoJSON-Geometrie in
  EPSG:4326 (`Point`, `Polygon` oder `MultiPolygon`; mehrere polygonale
  Features bereits vereinigt). `400` mit `{"detail": "<Regel>"}` für jeden
  inhaltlichen Grund, `413` über 1 MiB oder über den ZIP-Deckeln. Die Texte
  sind englisch, nennen die verletzte Regel und nie eine Koordinate.
- **Dev-Proxy** (`vite.config.ts`) leitet heute `/stac`, `/coverage` und
  `/collections` weiter, **nicht `/aoi`** — ohne Ergänzung erreicht der
  Upload im Entwicklungsserver die Route nicht.
- **Access-Log:** Der Dateiname steht im Query-String. `earthx/logging.py`
  schaltet `uvicorn.access` ab (M3-16); die Route selbst loggt nur die
  Endung. Der Name gelangt also nicht ins Log; dafür ist nichts zu ändern.
- **MultiPolygon im Frontend:** Bisher konnte eine hochgeladene GeoJSON-Datei
  schon eine `MultiPolygon` liefern. `polygonBbox`, `searchArea`,
  `aoiClip.ts` (Zuschnitt) und der Download (`access/download.py` nimmt
  `Polygon`/`MultiPolygon`) können damit umgehen — nachgesehen, keine Änderung
  nötig.

---

## 3. Umfang

1. **API-Aufruf** `uploadAoi(file: File)` in `frontend/src/api.ts`, neben den
   übrigen Aufrufen des eigenen Backends: `POST ${BASE}/aoi/upload?filename=…`
   (Name per `encodeURIComponent`), `body: file` (der `Blob` direkt, kein
   `FormData`), `Content-Type: application/octet-stream`. Fehler wie überall
   über `jsonOrThrow` → `HttpError` mit Status und `detail`.
2. **`frontend/src/aoiFile.ts` neu:** Der Client-Parser (`geomFromGeoJSON`,
   `geomFromKML`, `parseAoiFile`) entfällt vollständig. An seine Stelle tritt
   `readAoiFile(file)`: prüft vor dem Senden die Größe (F2), ruft
   `uploadAoi`, prüft die Antwort auf die drei erlaubten Typen
   (`Point`/`Polygon`/`MultiPolygon` — Abwehr gegen eine unerwartete Antwort,
   keine zweite Geometrieprüfung) und liefert entweder die Geometrie oder
   eine fertige Meldung für die Fehlerzeile (Abbildung in §5).
3. **`AoiExtras`** ruft `readAoiFile` statt `parseAoiFile`; Punktpufferung,
   `setAoi`, `flyTo` und „Last AOI“ bleiben, wie sie sind. Während der
   Anfrage ist der Upload-Knopf gesperrt (`aria-busy`, Text „Reading…“),
   damit ein Doppelklick nicht zwei Anfragen schickt. Knopftext, `title` und
   `accept` nach F3.
4. **Dev-Proxy:** `'/aoi': { target: apiTarget, changeOrigin: true }` in
   `vite.config.ts`, Kommentar dort ergänzt (die Route sitzt wie `/coverage`
   auf der Basis-App von `api`).
5. **Doku:** `prototyp-inventar.md` F3 bekommt einen Nachtrag (Parsen und
   Prüfen jetzt im Backend, Shapefile dazu, Größendeckel vorhanden); Zeile im
   `ENTSCHEIDUNGSLOG.md` mit Ottos Antworten; Stand von M3-06b im
   Aufgabenschnitt.

**Verhaltensänderungen gegenüber heute**, alle aus M3-06a folgend und in der
Log-Zeile genannt: `LineString` wird abgewiesen (F6); mehrere Polygone werden
vereinigt statt „erste gewinnt“ (F5 = 2); eine KML-Datei muss auf `.kml`
enden (die Route erkennt das Format an der Endung, der Ersatzweg „kein JSON,
also vielleicht KML“ entfällt); Dateien über 1 MiB werden abgewiesen.

---

## 4. Ablauf beim Hochladen

```
Datei gewählt
  └─ größer als 1 MiB? → Meldung (§5, „too large“), keine Anfrage
  └─ POST /aoi/upload?filename=…   (Knopf gesperrt)
       ├─ 200, Point            → Quadrat puffern, setAoi(quadrat, punkt), flyTo
       ├─ 200, (Multi)Polygon   → setAoi(geom), flyTo
       ├─ 200, anderer Typ      → Meldung „unexpected answer“
       └─ Fehler                → Meldung nach §5
  └─ Knopf wieder frei, Dateiauswahl zurückgesetzt (gleiche Datei erneut wählbar)
```

Eine laufende Anfrage wird nicht abgebrochen, wenn der Nutzer währenddessen
zeichnet; die Antwort überschreibt dann die gezeichnete AOI. Das ist heute
genauso (das Parsen war nur schneller) und bei einer Obergrenze von 1 MiB eine
Sache von Sekundenbruchteilen — kein eigener Abbruchmechanismus.

---

## 5. Fehlerabbildung (→ F1)

Alle Texte englisch, in der bestehenden Fehlerzeile (`setError`), ohne
Koordinaten. `<name>` ist der Dateiname, wie heute schon in der Meldung
„Could not read an AOI geometry from "<name>".“

| Fall | Meldung (Vorschlag) |
|---|---|
| Datei über 1 MiB (vor dem Senden) oder `413` | `"<name>" is too large for an AOI (max. 1 MB).` |
| `400` | `Could not use "<name>" as an AOI: <detail der Route>.` |
| `400` ohne lesbares `detail` | `Could not use "<name>" as an AOI.` |
| `5xx`, anderer Status | `Uploading "<name>" failed (<status>). Please try again.` |
| Netzwerkfehler (`fetch` wirft) | `Could not reach the server to read "<name>".` |
| `200` mit unerwarteter Antwort | `The server returned no usable AOI for "<name>".` |

Beispiele, wie die `400`-Zeile mit den heutigen Texten der Route aussieht:
„Could not use "parcels.zip" as an AOI: the ZIP has no .prj file; the
coordinate system is not guessed.“ — „Could not use "route.geojson" as an
AOI: not a GeoJSON geometry type we support: 'LineString'.“ Nicht jeder Text
ist gleich deutlich: Eine KML-Datei nur mit `LineString` ergibt „no usable
geometry found in the file“ (nachgeprüft). Das bleibt so (§8), der PR nennt
es.

Der Satzpunkt am Ende wird nicht verdoppelt, falls ein `detail` schon mit
einem Punkt endet.

---

## 6. Größendeckel im Client (→ F2)

Ohne Prüfung im Client schickt der Browser auch eine 50-MB-Datei los; die
Route bricht nach 1 MiB ab und antwortet `413`, während der Browser noch
sendet. Browser melden eine Antwort, die vor dem Ende des eigenen Uploads
kommt, oft nicht als `413`, sondern als Netzwerkfehler — der Nutzer sähe dann
„Could not reach the server“ statt „too large“. Deshalb schlage ich eine
Prüfung vor dem Senden vor: `AOI_UPLOAD_MAX_BYTES = 1_048_576` in
`aoiFile.ts`, mit Kommentar auf `MAX_UPLOAD_BYTES` in
`backend/earthx/access/aoi_upload.py`. Der `413`-Zweig bleibt trotzdem, weil
die Route allein maßgeblich ist (z. B. für ZIPs, die entpackt zu groß sind).
Die doppelte Zahl ist der Preis; eine Config-Route gibt es nicht mehr
(`store.ts`: „no server config endpoint any more“), und eine neue nur dafür
wäre mehr als die Aufgabe verlangt.

---

## 7. Tests (Vitest)

`frontend/src/aoiFile.test.ts` (neu) und Ergänzungen in `api.test.ts`,
`fetch` wie in den bestehenden Tests über `vi.stubGlobal` ersetzt:

- **Aufruf:** `POST` an `/aoi/upload`, `filename` richtig kodiert (Leerzeichen,
  `&`, `#`, Umlaute), Körper ist genau das `File`-Objekt, kein `FormData`.
- **Erfolg:** `Polygon`, `MultiPolygon` und `Point` kommen unverändert zurück.
- **Fehlerabbildung**, je eine Zeile aus §5: `400` mit `detail`, `400` mit
  Nicht-JSON-Körper, `413`, `500`, `502`, `fetch` wirft (`TypeError`),
  Antwort ohne `type`, Antwort `LineString`, Antwort `null`.
- **Deckel im Client:** Datei mit 1 048 577 Byte → Meldung, **kein**
  `fetch`-Aufruf; Datei mit genau 1 048 576 Byte → wird geschickt.
- **Zweckfremde Nutzung:** leere Datei (0 Byte) wird geschickt und die
  `400` der Route abgebildet (der Client prüft Inhalte nicht selbst);
  Dateiname ohne Endung; sehr langer Dateiname (wird kodiert, nicht
  abgeschnitten); `422` mit einem `detail`, das eine Liste statt eines
  Strings ist (FastAPI-Validierungsfehler, etwa wenn `filename` fehlt) →
  Zeile „anderer Status“.
- **Komponente** (`jsdom`, Muster aus `StatusBar.test.tsx`): Dateiauswahl in
  `AoiExtras` → bei `Point` landen Quadrat und Punkt im Store (`aoi`,
  `aoiPoint`, danach auch `lastAoi`); bei einem Fehler steht die Meldung in
  `error` und die bisherige AOI bleibt; der Knopf ist während der Anfrage
  gesperrt.

Dazu `npm run lint`, `npx tsc -b --pretty false`, `npm test`. Backend bleibt
unverändert; `ruff`, `pytest` und `lint-imports` laufen trotzdem einmal zur
Bestätigung.

**Abnahme durch Otto** (laut Aufgabe): lokal je eine Datei jedes Formats
hochladen — GeoJSON, KML, Shapefile-ZIP — und je eine fehlerhafte (etwa ZIP
ohne `.prj`), um die Meldung zu sehen. Der PR nennt dafür die Befehle
(`api` starten, `npm run dev`).

---

## 8. Nicht in dieser Aufgabe

- Änderungen an der Route oder ihren Texten (M3-06a, erledigt). Fällt beim
  Umsetzen ein Text auf, der für Nutzer unverständlich ist, nennt der PR ihn,
  ändert ihn aber nicht.
- Maschinenlesbare Fehlercodes in der Route (siehe F1, Option 3).
- Ortssuche (M3-07b), Datensatz-Filter (M3-10) — dieselbe Kachel, eigene
  Aufgaben danach.
- Drag-and-drop einer Datei auf die Karte.
- Ein Produktions-Reverse-Proxy für `/aoi`: Es gibt noch kein Deployment des
  Frontends (`docker-compose.yml` enthält keins); das Thema kommt mit M6.

---

## 9. Fragen an Otto

**F1 — Fehlermeldungen (§5).**
(1) Eigene Texte für Größe, Netzwerk und Serverfehler; bei `400` der Text der
Route mit dem Vorspann „Could not use "<name>" as an AOI:“. **Empfehlung.**
(2) Jeden bekannten Text der Route im Frontend auf einen eigenen Text
abbilden — freier formulierbar, aber jede Textänderung im Backend bricht die
Abbildung still.
(3) Die Route bekommt zusätzlich einen maschinenlesbaren `code`; das Frontend
bildet nur Codes ab — sauberste Trennung, ändert aber das Backend und gehört
in eine eigene Aufgabe.

**F2 — Größenprüfung vor dem Senden (§6).**
(1) Ja, 1 MiB als Konstante im Frontend, mit Verweis auf das Backend; `413`
bleibt abgebildet. **Empfehlung.**
(2) Nein, nur die `413` der Route — eine Zahl weniger doppelt, aber große
Dateien erscheinen oft als Netzwerkfehler.

**F3 — Knopf.**
(1) Text „⤒ Upload AOI“, Tooltip „Upload a GeoJSON, KML or zipped Shapefile
(max. 1 MB) as the AOI“, `accept=".geojson,.json,.kml,.zip"`. **Empfehlung.**
(2) Text „⤒ Upload GeoJSON/KML/SHP“, sonst wie (1) — länger, zeigt die
Formate ohne Tooltip.
