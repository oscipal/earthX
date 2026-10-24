# M4-19 — Permalinks, Methodentext, Skalierung und Einheiten, „Parameter übernehmen“: Plan

**Stand:** 24.10.2026, Plan freigegeben (§9); M4-19a, d, b und e sind umgesetzt (§10, §11, §12, §13), c folgt in einer neuen Session.
**Stufe B (S6):** Der Plan liegt im Draft-PR, die Session hält an, Otto gibt frei. Danach
setzen die Sessions aus Frage 10 um.
**Modell:** Opus für den Plan, Sonnet (Effort mittel) für die Umsetzung (§3 der Übersicht).
**Startsatz:** „Führe Aufgabe M4-19 aus `docs/plans/m4-processing-kern.md` aus.“
**Voraussetzung:** M4-13c ist vollständig gemergt (c-1 bis c-5, zuletzt #166).
**Grundlage:**
- `plans/m4-processing-kern.md` M4-19, Q8, Q9, Q10, S6 (§1.1c), §1.2.
- `adr/0014` §4.1–§4.7, §5.6, §9 (F15), §10, §14; `adr/0015` §7.1 (F13), §8.3, §13.
- `architekturplan.md` 7.1 (Tabelle „Aus diesem einen Objekt folgt“), 8.2.
- `plans/m4-13-processing-panel.md` F3; `plans/m4-13c-vorschau-und-viewer.md` §3.7, §12.
- `plans/m4-32-ergebnis-statistik.md` §6.7, §7 (PR #168, Entwurf, freigegeben am 20.10.2026).
- Log 05.10.2026 („Frist für Permalinks“, offen), 10.10.2026 (S6).

Belegstufen wie in `adr/0009`: [M] gemessen, [P] am Primärdokument oder im Code
gelesen, [S] Zusammenfassung oder Suchtreffer, [A] eigene Ableitung.

**Kurzfassung.**

- Vier Teile, die wenig miteinander zu tun haben. Vorschlag: fünf kleine PRs
  (M4-19a bis M4-19e, §4), jeder unter 400 Zeilen.
- **Methodentext:** ein englischer Absatz aus dem ausgeführten Rezept und seiner
  Provenienz, gebaut von einer reinen Funktion in `processing`. Er liegt als
  `methods.txt` neben `recipe.json` (Job, Zuschnitt, Runner) und erscheint im Panel
  mit „Copy“. Je Operator ein Satz (§3.1).
- **Einheiten:** Kein Item der drei Datensätze trägt heute eine Einheit [P]. Sie
  kommt deshalb aus einem neuen Registry-Feld je Asset; das Item geht vor, wenn es
  eine nennt. Die Einheit läuft durch das Rezept bis in `bands[].unit` des
  Ergebnisses (§3.2).
- **Skalierung der Vorschau:** `/statistics` im `tiler` nimmt künftig `op`. Die
  Vorschau misst ihren Bereich selbst und wendet dieselbe Regel an wie M4-32 für
  Ergebnisse. Ein von Hand angewandter Bereich geht vor (§3.3).
- **„Parameter übernehmen“:** Eine `recipe.json` lässt sich ins Panel laden,
  wahlweise nur die Schritte (auf die aktuelle Auswahl) oder alles (§3.4).
- **Permalink:** eine eigene zufällige Kennung und eine eigene Tabelle. Er wird nur
  auf „Share“ angelegt und hält Auftrag und Kartenansicht, nie den Job (Q9). Die Frist
  entscheidet Otto (Frage 2); Vorschlag: 30 Tage fest ab Erstellung, dazu ein
  Löschschlüssel (§3.5).
- **Befund am Rande (§2.1):** Ein Cache-Treffer verlängert im Code keine Frist. Zwei
  Docstrings sagen das Gegenteil, ebenso der Wortlaut von F13. Der Code ist richtig,
  denn die Regel am Bucket zählt ab dem Schreiben. Frage 12.
- Zwölf Fragen an Otto (§7), je mit Empfehlung.

---

## 1. Was schon entschieden ist

| Quelle | Inhalt | Folge hier |
|---|---|---|
| Q8 | Nach außen (URLs, Job-IDs, Permalinks) nur zufällige Kennungen, nie der Rezept-Hash; Rezepte mit AOI sind personenbezogen | Permalink-ID `secrets.token_urlsafe(16)`, wie `jobID` (§3.5) |
| Q9 | Ergebnisse bleiben privat, nur über signierte URLs; Job-IDs nicht zu erraten | ein Permalink trägt keinen Job und kein Ergebnis (Frage 4) |
| Q10 | 7 Tage für Ergebnisse und gespeicherte Rezepte | gilt für Rezepte hinter Jobs; die Frist des Permalinks wird hier neu entschieden (Frage 2) |
| §1.2 der Übersicht | keine AOI und kein Rezept-Hash in URLs und Logs | der Zustand steht nicht in der URL (Frage 1, Option 3 scheidet ohne Ottos Freigabe aus) |
| `adr/0015` F13, §13 | Frist des Rezepts: 7 Tage nach der letzten Nutzung; „Für Permalinks (M4-19) wird die Frist neu entschieden“ | Frage 2 |
| `adr/0014` §9 (F15) | `recipe_id` ist die „Grundlage für Permalink (M4-19) und für Bug-Report Stufe 3“ | Frage 1: eigene Kennung statt `recipe_id`, Begründung in §3.5 |
| `adr/0014` §5.6 | `processing:lineage` als kurzer Text je Schritt; „der Methodentext in voller Länge ist M4-19“ | §3.1 |
| `adr/0014` §10.1 | `recipe.json` hat dasselbe Schema wie das Rezept, beim Zuschnitt `steps: []` | Quelle für Methodentext und „Parameter übernehmen“ |
| `architekturplan.md` 7.1, 8.2 | Permalink stellt „Ansicht und Einstellungen wieder her“; „Gesamter Arbeitszustand ist als Rezept + Ansicht serialisierbar“; „Parameter übernehmen kopiert Schritte oder einzelne Parameter zwischen Rezepten“ | §3.4, §3.5 |
| M4-13 F3 (1) | Vorschau von Hand, Start −1…1 und `rdylgn`; „die automatische Skalierung kommt mit M4-19“ | §3.3 |
| M4-32 §6.7, §7 | Ergebnisse: Farbskala aus der Statistik der AOI. Index-artig bleibt −1…1 `rdylgn`, sonst 2–98 % `viridis`, Hand vor Statistik. „Die T1-Vorschau bleibt, wie sie ist“ | §3.3: dieselbe Regel für die Vorschau, eigene Messung |
| KLAERUNGEN B10, §1.2 | neue Registry-Felder ohne Vorgabewert | §3.2 |
| §3 der Übersicht, „Registry“ | M4-18 fügt ein Registry-Feld hinzu; parallel ändert nichts sonst die Registry | M4-19b läuft nicht parallel zu M4-18 (§4) |

---

## 2. Befunde

### 2.1 Rezepte, Jobs und Fristen im Code [P]

- **Tabellen** (`catalog/migrations/006_jobs.sql`): `earthx_recipe(recipe_id, body,
  created_at)`, `earthx_run(… recipe_id, expires_at NOT NULL …)` und
  `earthx_job(job_id, run_id, recipe_id, …)`. Fremdschlüssel sind `RESTRICT`.
- **Jeder Auftrag hat ein eigenes Rezept:** `jobs/submit.py::submit` legt je Auftrag
  eine neue Zeile mit neuer `recipe_id` an (Z. 128–145). Ein Auftrag mit einer
  `recipe_id`, die schon existiert, bekommt `RecipeIdTaken`. Die Aussage in `adr/0014`
  §9, die `recipe_id` „bleibe gleich, wenn derselbe Nutzer dasselbe Rezept erneut
  startet“, ist so nicht gebaut. `adr/0013` §9 Punkt 2 legt „jeder Auftrag hat sein
  eigenes“ fest, und der Code folgt dem.
- **Ein Rezept hat keine eigene Frist:** `jobs/cleanup.py` löscht abgelaufene Läufe
  samt Jobs und danach jede Rezeptzeile ohne Job und Lauf (Z. 78–90). Ein Rezept lebt
  so lange wie der Lauf seines Jobs.
- **Ein Cache-Treffer verlängert nichts:** `_run_for` hängt den neuen Job an einen
  fertigen Lauf mit mindestens 24 Stunden Restlaufzeit (`CACHE_MIN_REMAINING`,
  `adr/0015` §8.3 T1) und schreibt `expires_at` nicht neu (Z. 180–191). Der neue Job
  und sein Rezept laufen also mit dem alten Lauf ab. Die Docstrings in
  `cleanup.py` (Z. 8–12) und `submit.py` sagen dagegen „only a run or a cache hit
  lengthens that“, ebenso F13 in `adr/0015` §7.1.
- **Warum der Code richtig ist [A]:** Die Regel am Bucket (`adr/0015` §7.3,
  `Expiration: Days 7`) zählt ab dem Schreiben des Objekts. Ein Lauf, dessen
  `expires_at` ein Treffer verlängerte, zeigte nach Tag 7 auf gelöschte Bytes. Die
  Verlängerung, die F13 meint, gibt es also nur über einen neuen Lauf. Frage 12.
- **Das Rezept nach außen:** Nur über `GET /processing/jobs/{jobID}/results/recipe.json`
  (`api/processing_route.py` Z. 894–942, `jobs/submit.py::job_recipe`). Das
  Statusdokument nennt die `recipe_id`, nicht das Rezept.
- **Kennungen:** `jobID`, `recipe_id` und `result_id` sind je
  `secrets.token_urlsafe(16)` (22 Zeichen, 128 Bit). Das Access-Log ersetzt `jobID`
  und `result_id` im Pfad (`earthx/logging.py::loggable_path`).

### 2.2 `recipe.json` und der Weg zurück [P]

- `processing/recipe.py::job_recipe_document` (Z. 646–671) gibt Rezept und
  `provenance` aus. Der Zuschnitt baut dasselbe Schema mit `steps: []`
  (`api/tiler.py` Z. 768–800, M4-14).
- **Zurückgelesen** wird eine `recipe.json` nur im lokalen Runner
  (`runner/recipe_file.py::load_recipe`). Er verlangt `provenance.execution ==
  "cloud"`. Eine Route, die eine `recipe.json` annimmt, gibt es nicht.
- **Im Frontend** gibt es keinen Rückweg vom Auftrag zum Panel-Zustand.
  `processingOrder.ts::buildOrder` (Z. 349–390) baut den Auftrag aus Entwurf und
  Auswahl; die Gegenrichtung fehlt. `JobEntry` (`processingStore.ts` Z. 143–161) hält
  weder Auftrag noch Rezept; `recipe.json` ist nur ein Link in der Jobliste.
- **URL:** Das Frontend liest und schreibt keinen Zustand in der Adresse (kein
  `history.pushState`, kein `location.search`). Gespeichert werden nur
  `earthx.theme` und `earthx.projection` (`localStorage`) sowie
  `earthx.processing.jobs` (`sessionStorage`).

### 2.3 Vorschau und Farbskala [P]

- Die Vorschau startet fest mit −1…1 und `rdylgn` (`processingPreview.ts` Z. 35).
  „Auto stretch“ ist gesperrt (`AUTO_STRETCH_REASON`, Z. 37).
- Der Grund steht im `tiler`: `op` gilt nur für Kachel und TileJSON
  (`_OPERATOR_ROUTES = {"tile", "tilejson"}`, `api/tiler.py` Z. 358). `/statistics`
  mit `op` gibt `400`. `processing/tile.py::OperatorTileReader` kennt nur `tile`,
  `info` und die Grenzen, kein `preview` und kein `statistics`.
- `/statistics` ohne Operator liest die gröbste Ebene (`access/resolve.py::
  target_gsd_for`) und nutzt einen Cache in Postgres. Dessen Schlüssel ist ein Hash
  aus Datensatz, Item, Asset und Parametern (`access/tiles.py::
  statistics_cache_key`).
- `render.ts::autoRescale` nimmt das kleinste 2-Perzentil und das größte
  98-Perzentil über die Bänder. M4-32 nutzt dieselbe Funktion für Ergebnisse.

### 2.4 Einheiten [P]

- `processing/operators/base.py::BandMeta` hat ein Feld `unit`, und `reproject`
  reicht es durch (Z. 153). Gefüllt wird es nirgends: Das Rezeptmodell `Band`
  (`recipe.py` Z. 213–223) kennt `data_type`, `nodata`, `scale` und `offset`, keine
  Einheit.
- Kein Item der drei Datensätze trägt eine Einheit. Earth Search hat in
  `raster:bands` `nodata`, `data_type`, `scale` und `offset` (`adr/0014` §17.1), EOPF
  nur `nodata`, `data_type` und `spatial_resolution`, die eigenen DEM-Items gar kein
  `raster:bands`. Die Fixtures zeigen dasselbe.
- Die Registry (`catalog/registry.py::DatasetConfig`) führt keine Einheit.
- Die einzige Einheit in der Oberfläche ist die des Ziel-CRS bei `reproject`
  (`CellSize.tsx`, M4-13c-3).

### 2.5 Kurztext je Schritt [P]

`Operator.lineage` gibt je Schritt einen kurzen Text. Beispiele: „band math:
(nir-red)/(nir+red)“ und „reprojected to EPSG:3035 at 10 (bilinear)“. `processing/
core.py` fügt die Texte zu `processing:lineage` zusammen (Z. 306–323). Der
Methodentext braucht mehr: Datensatz, Szenen, Skalierung, Software und Zitat.

### 2.6 Überschneidung mit M4-32 [P]

M4-32 legt die Farbskala der **Ergebnisse** fest (Statistik der AOI im
Ergebnisdokument, Regel in `resultLayer.ts::resultRender`). Die **Vorschau** lässt
es ausdrücklich, wie sie ist. Der Grund: Die Statistik-Route nimmt keinen Operator,
und eine Statistik je Kachel ließe Kacheln verschieden aussehen. M4-19 schließt
genau diese Lücke. Die Regel (index-artig → −1…1 `rdylgn`, sonst 2–98 % `viridis`,
Hand vor Messung) soll für Vorschau und Ergebnis dieselbe sein, damit beide gleich
aussehen. Wer als Zweiter fertig wird, zieht die Regel in eine gemeinsame Funktion
in `render.ts`.

---

## 3. Entwurf

### 3.1 Methodentext (M4-19a)

**Inhalt** (englisch, ein Absatz, deterministisch, keine Sprachwahl):

> Sentinel-2 L2A surface reflectance (doi:10.5270/S2_-742ikth) was processed on
> EarthX 0.4.2. Two scenes acquired on 2025-07-14 were mosaicked (first valid
> pixel in a fixed order). The bands red and nir were converted to physical values
> with the scale (0.0001) and offset (−0.1) given in the item metadata. The index
> (nir − red) / (nir + red) was computed per pixel in 32-bit floating point.
> The result was reprojected to EPSG:3035 (ETRS89-extended / LAEA Europe) at
> 10 m with bilinear resampling. Software: GDAL 3.12.2, rasterio …, numexpr …,
> numpy …. Contains modified Copernicus Sentinel data 2025.

Die Zahlen im Beispiel sind Platzhalter. Woher die Teile kommen:

| Teil | Quelle |
|---|---|
| Datensatz, DOI, Attribution | Registry (`title`, `doi`, Attribution wie in `citation.bib`) |
| Szenen, Tag, Mosaik | `inputs[].groups`, `acquired_on` des Jobs bzw. `datetime` der Items (im Rezept: Item-IDs; den Tag gibt `api` mit) |
| Skalierung | `resolved[].bands` und die Quelle der Skalierung (`item`, `store-cf`, `none`, `adr/0014` §5.4) |
| je Schritt | neue Funktion `Operator.method(params) -> str`, ein Satz; neben `lineage` |
| Ausgabe | `output` (Datentyp, Format), beim Zuschnitt die Regeln aus `adr/0014` §10.1 |
| Software | `provenance` (Versionen aus `adr/0014` §4.5) |
| Fläche | Frage 6 |

**Ort:** `processing/methods.py`, eine reine Funktion `methods_text(recipe,
provenance, datasets) -> str`. `processing` darf `catalog.registry` lesen, und der
Runner importiert `processing` (Importregeln unverändert). So schreiben Job, Runner
und Zuschnitt denselben Text.

**Ausgabe:**
- `methods.txt` als Datei des Ergebnisses: Link `GET …/results/methods.txt`
  (`LINK_NAMES`), im ZIP eines Jobs (M4-11b-1, M4-30) und im Zuschnitt-ZIP neben
  `recipe.json`.
- Runner: `methods.txt` neben `recipe.json`. Der Text sagt dort „processed locally
  (self-attested)“.
- Panel: In der Jobliste öffnet „Methods“ den Text mit „Copy“. Der Text kommt über
  den Link, nicht aus dem Frontend gebaut.

**Wächtertest:** Jeder registrierte Operator hat ein `method`, das für seine
Beispielparameter einen nicht leeren Satz ohne Platzhalter gibt. M4-18 (Masking,
Normalisierung) muss damit je einen Satz mitbringen.

**Nie im Text:** Hash, `href`, Kennungen (`recipe_id`, `jobID`), AOI-Koordinaten
(Frage 6).

### 3.2 Einheiten je Band (M4-19b)

- **Registry:** neues Feld `band_units` am `DatasetConfig`. Es ist eine Zuordnung
  Asset-Schlüssel → Einheit, ohne Vorgabewert (B10).
  - Für Zarr ist der Schlüssel die Variable (`SR_10m:b04`) oder ein Muster je
    Gruppe; die Form legt die Umsetzung mit Test fest.
  - Einheiten als UCUM-Zeichen: `"m"` für das DEM, `"1"` für dimensionslose
    Reflexion nach der Skalierung.
  - Ein ausdrückliches `None` heißt „unbekannt“; dann zeigt die Oberfläche nichts.
  - Die Registry-Prüfung verlangt einen Eintrag je Asset, das `default_render` oder
    ein Operator lesen kann.
- **Vorrang:** Nennt das Item `raster:bands[].unit` bzw. `bands[].unit`, gilt das
  Item, sonst die Registry. Heute greift immer die Registry (§2.4).
- **Rezept:** `Band` bekommt `unit: str | None`. `api` füllt es bei der Annahme.
  `BandMeta.unit` wird daraus befüllt, `reproject` reicht es durch.
  - Band-Math gibt `unit = None`, denn eine Formel hat keine bekannte Einheit.
    Ausnahme: Der Ausdruck ist ein einzelner Bandname.
  - Das Ergebnis trägt `bands[].unit` (STAC 1.1, `adr/0014` §5.6).
- **Folge für den Cache [A]:** `Band` gehört zum Kern des Hashes (`adr/0014` §4.5).
  Nach dem Deployment gibt es deshalb einmal für alle gecachten Ergebnisse keinen
  Treffer. Bei 7 Tagen Frist ist das vertretbar. Mit der neuen Fassung (`0.4.x`)
  ändern sich die Schlüssel ohnehin. Frage 8 nennt die Option ohne Rezeptänderung.
- **Anzeige:**
  - im Panel an jedem Band („red · 1“, „elevation · m“);
  - in der Wertebereich-Zeile von Vorschau und Ergebnis („−1 … 1“ bzw.
    „120 … 2400 m“);
  - am Ergebnis-Layer im Layer-Manager.
  - Die Collection gibt die Einheiten heraus, als `item_assets.<key>.bands[].unit`
    bzw. `earthx:band_units` (Form in der Umsetzung).

### 3.3 Automatische Farbskala der Vorschau (M4-19c)

- **Backend:** `/statistics` nimmt `op`, `op_version` und `params` wie die Kachel
  (`_OPERATOR_ROUTES` um `statistics` erweitert).
  - `OperatorTileReader` bekommt `statistics`: Jede Quelle wird über dieselben
    Grenzen auf dieselbe Größe gelesen, höchstens 1024 px an der langen Seite (wie
    die heutige Statistik). Dann laufen die Skalierung und der Kernel des Operators
    darüber, dann rio-tilers Statistik.
  - Zarr liest die gröbste Ebene wie heute (`target_gsd_for`).
  - Der Cache-Schlüssel nimmt `op`, `op_version` und das kanonische `params` auf.
    Der Hash bleibt, also kein Ausdruck in einer Spalte.
  - Grenzen, Lizenzstufe, `R5` und `applicable` wie bei der Kachel.
- **Frontend:** Sobald die Vorschau eine neue Formel zeigt, misst sie einmal und
  wendet die Regel an:
  - (1) Hat der Nutzer einen eigenen Bereich angewandt, gilt er.
  - (2) Liegen alle Werte in −1…1, gilt −1…1 mit `rdylgn`.
  - (3) Sonst gilt `autoRescale` (2–98 %) mit `viridis`.
  - (4) Schlägt die Messung fehl, bleibt −1…1 mit einem Hinweis.
  - „Auto stretch“ wird freigeschaltet und misst neu.
  - Die Regel ist dieselbe Funktion wie in M4-32b (§2.6).
- **Welche Pixel:** Bei „Whole scene“ die Szene (gröbste Ebene). Bei „AOI only“
  ebenfalls die Szene: Die POST-Statistik mit GeoJSON gibt es im `tiler` nicht
  (`access/tiles.py` Z. 152), und eine AOI im Abfragetext verböte §1.2. Die Folge
  steht in Frage 7.
- **Rechenrelevant [A]:** Es entsteht keine neue Festlegung. Die Größe (1024) und
  die Perzentile sind die der bestehenden Statistik (`adr/0006` §3.4, F18). Eine
  Messung der Antwortzeit (kalt und warm, eine Szene, zwei Assets) kommt in den PR.

### 3.4 „Parameter übernehmen“ (M4-19d)

- **Laden:** „Load recipe…“ im Kopf des Panels, Dateiwahl, nur `.json`, höchstens
  1 MB (wie `MAX_BODY_BYTES` der Auftragsroute).
- **Prüfen im Browser**, mit einem kurzen englischen Grund statt eines Absturzes:
  - JSON-Fehler;
  - `recipe_version` unbekannt;
  - kein `inputs`/`steps`;
  - Operator oder `op_version`, den die Prozessbeschreibung nicht führt;
  - Parameter, die das Schema des Operators abweist (dieselbe Prüfung wie das
    Formular, `schemaForm.ts`);
  - mehr als ein Datensatz.
  - Zusätzliche Felder (`resolved`, `provenance`, `recipe_id`) werden ignoriert,
    nicht abgewiesen: Es ist die Datei des Nutzers.
- **Was übernommen wird (Frage 9):**
  - „Steps only“: Schritte, Parameter und Datentyp auf die aktuelle Auswahl. Bei
    einem anderen Datensatz prüft das Panel die Bandnamen im Ausdruck gegen die
    Bänder der Auswahl und markiert fehlende („band `nir` is not in this
    dataset“). Es ordnet nichts still um.
  - „Everything“: Datensatz, Szenen (Suche nach `ids`, M3-08), AOI bzw. „Whole
    scene“, Schritte und Datentyp. Fehlen Szenen an der Quelle, sagt das Panel,
    welche.
- **Neu im Code:** `processingOrder.ts::draftFromOrder`, die Umkehrung von
  `buildOrder`. Sie ist getestet als Rundreise `buildOrder(draftFromOrder(x)) ≡ x`
  über die acht Auftrags-Fixtures. Der Permalink nutzt sie wieder (§3.5).

### 3.5 Permalink (M4-19e)

**Was er hält:** den Auftrag in der Form von `RecipeRequest` (ohne `resolved`), dazu
eine kleine Ansicht:
- Kartenmitte und Zoom;
- Basiskarte;
- Darstellung der Vorschau (Bereich, Colormap);
- Titel.

Keinen Job, kein Ergebnis, keinen Link in den Objektspeicher (Frage 4). Wer den Link
öffnet, sieht Auswahl, AOI, Panel und Vorschau. Startet er den Job, kommt das Ergebnis
als Cache-Treffer, solange es noch mindestens 24 Stunden lebt (§2.1).

**Backend (`api`, wie der Geocode-Cache mit eigener Tabelle):**
- Migration `012_permalink.sql`: `earthx_permalink(permalink_id text PK, body jsonb,
  created_at, expires_at NOT NULL, delete_key_hash text)`.
- `POST /processing/permalinks`:
  - Der Auftrag wird mit `parse_request` geprüft (strikt, I-JSON). Die Ansicht hat
    ein eigenes Modell mit `extra="forbid"`. Höchstens 1 MB.
  - Antwort `201`: `{id, expires_at, delete_key}`. Der Löschschlüssel steht nur in
    dieser Antwort; gespeichert wird sein SHA-256.
- `GET /processing/permalinks/{id}`: `200` mit Auftrag und Ansicht, `404` für
  unbekannt oder abgelaufen (nicht `410`: Es soll nicht zu erkennen sein, ob es eine
  Kennung je gab [A]).
- `DELETE /processing/permalinks/{id}` mit Kopf `X-Delete-Key`: `204`. Ein falscher
  Schlüssel gibt dasselbe `404` wie eine unbekannte Kennung.
- **Aufräumen:** Der stündliche Aufräumer in `jobs` löscht abgelaufene Permalinks.
  Andernfalls braucht `api` eine eigene Schleife; der Aufräumer liegt in `jobs`, das
  die Datenbank darf (Q4). Die Umsetzung prüft die Importregel. Ansehen verlängert
  nie (Frage 2).
- **Logs:** `loggable_path` ersetzt die Kennung (`{permalinkID}`). Kein Auftrag und
  keine AOI im Log, nur „permalink created/read/deleted“ mit Datensatz-ID.
- **Missbrauch ohne Konten (bis M6):** Größe 1 MB je Eintrag. Mengen- und
  Ratengrenzen gibt es in M4 nicht (D6, Abgrenzung §2 der Übersicht); die Frist
  begrenzt den Bestand.

**Frontend:**
- „Share“ im Panel legt den Permalink an. Es zeigt die Adresse
  `…/?permalink=<id>` zum Kopieren, das Ablaufdatum und „Delete link“.
- Der Löschschlüssel liegt im `localStorage` unter `earthx.permalinks`. Er ist
  wie die übrigen Einstellungen im Browser, ohne Wert für den Server.
- Beim Start liest die App `?permalink=`, holt den Eintrag und stellt mit
  `draftFromOrder` (§3.4) und der Ansicht wieder her. Danach entfernt sie den
  Parameter per `history.replaceState`, damit ein Neuladen nicht erneut lädt.
- `404` gibt „This link has expired or never existed.“

**Warum nicht die `recipe_id` (Frage 1) [A]:** Ein Rezept lebt nur so lange wie
der Lauf seines Jobs, höchstens 7 Tage (§2.1). Es entsteht erst mit einem Job, also
gäbe es ohne Job keinen Permalink. Außerdem steht die `recipe_id` heute im
Statusdokument und in jeder `recipe.json`. Ein Lesezugriff über sie machte jede
weitergegebene Datei zum Schlüssel. Die `recipe_id` bleibt die Grundlage für
Bug-Report Stufe 3.

---

## 4. Schnitt (Frage 10)

| Teil | Inhalt | Seiten | grob | hängt ab von |
|---|---|---|---|---|
| **M4-19a** | Methodentext: `processing/methods.py`, `Operator.method`, `methods.txt` in Job, ZIP, Zuschnitt, Runner; „Methods“ mit „Copy“ in der Jobliste | Backend, Frontend | 350 | — |
| **M4-19b** | Einheiten: Registry-Feld, `Band.unit`, `bands[].unit` im Ergebnis, Anzeige | Backend, Frontend | 350 | nicht parallel zu M4-18 (Registry) |
| **M4-19c** | Farbskala der Vorschau: `/statistics` mit `op`, Regel mit M4-32 | Backend, Frontend | 300 | M4-32b gemergt (gemeinsame Regel) |
| **M4-19d** | „Load recipe…“, `draftFromOrder`, „Steps only“/„Everything“ | Frontend | 350 | — |
| **M4-19e** | Permalink: Migration, drei Routen, Aufräumer, „Share“, Öffnen per Adresse | Backend, Frontend | 400 | M4-19d (`draftFromOrder`) |

a und d können sofort parallel laufen. Die Reihenfolge danach: e nach d, c nach
M4-32b, b nach M4-18.

**Doku in den Teil-PRs:**
- a: Nachtrag `adr/0014` §5.6 (Methodentext).
- b: Nachtrag `adr/0014` §4.2/§4.5 (`unit` im Kern).
- c: Nachtrag `adr/0006` (Statistik mit Operator).
- e: Nachtrag `adr/0015` §13 (Frist der Permalinks) und `adr/0014` §9 (Kennung).
- Dazu Log-Zeilen und die Zeile in §3 der Übersicht.

---

## 5. Tests (je Teil, Auswahl)

Fixtures nur synthetisch; das Frontend erreicht kein Backend (`fetch` gestubbt).

- **a:**
  - Golden-Texte für Band-Math auf COG mit Item-Skalierung, Zarr mit `store-cf`,
    Reproject auf DEM, Mosaik aus zwei Szenen, Zuschnitt, Runner.
  - Kein Hash, keine Kennung und keine Koordinate im Text (Gegenprobe mit einer AOI,
    deren Koordinaten als Zeichenkette gesucht werden).
  - Wächtertest je Operator; `methods.txt` im ZIP und als Link;
    `410`/`404` wie die übrigen Dateien.
- **b:**
  - Registry-Prüfung: Feld fehlt, Asset fehlt, leere Zeichenkette.
  - Vorrang Item vor Registry.
  - `unit` durch `reproject`, `None` nach Band-Math, `bands[].unit` im Ergebnis.
  - Feste Hashwerte (`adr/0014` §4.4 Punkt 9) bewusst erneuert, im PR benannt.
  - Anzeige im Panel und am Layer.
- **c:**
  - `/statistics` mit `op` gegen eine unabhängige Rechnung auf synthetischem COG
    (zwei Assets, verschiedene Auflösung).
  - `400`/`422` wie die Kachel (falsches `params`, R5, nicht anwendbar,
    Lizenzstufe).
  - Cache-Schlüssel verschieden je `params`; Zarr gröbste Ebene.
  - Frontend: Regel (1)–(4), Hand vor Messung, Fehler → Hinweis.
- **d:**
  - Rundreise über die Fixtures.
  - Fehlerfälle: kaputtes JSON, 1 MB + 1, fremde Version, unbekannter Operator,
    falsche Parameter, zwei Datensätze, Datei ohne `steps`.
  - Zweckfremd: ein GeoJSON statt Rezept, eine `recipe.json` des Zuschnitts
    (`steps: []`, `output.kind: crop`) → „Everything“ stellt die Auswahl her,
    „Steps only“ sagt „no steps“.
  - Fehlende Bänder bei fremdem Datensatz.
- **e:**
  - Anlegen, Lesen, Löschen; `404` für unbekannt, abgelaufen (eigene Uhr) und
    falschen Schlüssel.
  - Größe, `extra` in der Ansicht, ungültiger Auftrag (`422`).
  - Kennung nicht im Access-Log, AOI nicht im Log (`own_log_text`, §1.2).
  - Aufräumer mit eigener Uhr; Ansehen verlängert nicht.
  - Frontend: Öffnen per Adresse, `replaceState`, `404`-Text, „Delete link“.

---

## 6. Nicht in dieser Aufgabe

- Python-Snippet aus dem Rezept (architekturplan 7.1): nicht in M4 genannt.
- Ergebnisse über einen Permalink teilen (Frage 4, Option 2).
- „Parameter übernehmen“ zwischen zwei offenen Rezepten im Panel ohne Datei (nur
  über die Datei bzw. den Permalink).
- Bandnamen zwischen Datensätzen automatisch zuordnen (`red` ↔ `SR_10m:b04`).
- Mengen- und Ratengrenzen für Permalinks (M6, D6).
- Statistik der Vorschau über die AOI (Frage 7, Option 2).

---

## 7. Fragen an Otto

Kurz beantwortbar: je Frage eine Nummer.

**Frage 1 — Kennung des Permalinks (§3.5)**
1. Eigene zufällige Kennung in eigener Tabelle, nur auf „Share“ angelegt, hält
   Auftrag und Ansicht **(Empfehlung)**
2. Die `recipe_id` eines Jobs ist der Permalink. Er lebt dann höchstens so lange
   wie der Job und entsteht erst mit einem Job.
3. Zustand im URL-Fragment (`#…`), ohne Server und ohne Frist. Bricht §1.2 („keine
   AOI in URLs“) und ergibt bei Polygonen lange Adressen.

**Frage 2 — Frist des Permalinks (Log 05.10.2026, `adr/0015` §13)**
1. 30 Tage fest ab Erstellung; Öffnen verlängert nicht **(Empfehlung)**. Lang genug
   zum Weitergeben und Begutachten. Die dauerhafte Fassung für ein Paper ist die
   `recipe.json` im ZIP.
2. 7 Tage fest, wie Ergebnisse (Q10).
3. 7 Tage ab dem letzten Öffnen. Ein Link, den jemand regelmäßig öffnet, lebt dann
   unbegrenzt mit einer AOI darin.
4. 90 Tage fest.

**Frage 3 — Löschen vor Ablauf**
1. Löschschlüssel einmalig bei der Erstellung, im Browser gehalten; „Delete link“
   **(Empfehlung)**
2. Kein Löschen bis zu Konten in M6.

**Frage 4 — Was der Permalink zeigt**
1. Auftrag und Ansicht. Das Ergebnis kommt beim Start als Cache-Treffer, solange es
   lebt **(Empfehlung)**.
2. Dazu der Job: Wer den Link öffnet, sieht Status und Ergebnis-Layer. Das hebt Q9
   (Ergebnisse privat) für geteilte Jobs auf.

**Frage 5 — Ort des Methodentexts (§3.1)**
1. Reine Funktion in `processing` aus Rezept und Provenienz. `methods.txt` liegt
   bei Job, Zuschnitt und Runner, das Panel zeigt den Text mit „Copy“
   **(Empfehlung)**.
2. Nur im Frontend aus dem Auftrag. Ohne Skalierung, Fassungen und
   Software-Versionen, nicht in den ZIPs.

**Frage 6 — Fläche im Methodentext**
1. Nur Größe in km² und Ziel-CRS, keine Koordinaten; der Nutzer nennt sein
   Untersuchungsgebiet selbst **(Empfehlung)**.
2. Dazu die Bounding Box in Grad, auf 0,01° gerundet.
3. Nichts zur Fläche.

**Frage 7 — Farbskala der Vorschau (§3.3)**
1. `/statistics` nimmt `op`. Die Vorschau misst einmal je Formel über die Szene
   und nutzt die Regel von M4-32 (−1…1 `rdylgn` oder 2–98 % `viridis`). Hand geht
   vor, „Auto stretch“ wird frei **(Empfehlung)**.
2. Wie 1, aber bei „AOI only“ über die AOI. Das braucht die POST-Statistik mit
   GeoJSON im `tiler`; ein eigener Weg, etwa 150 Zeilen mehr.
3. Nur „Auto stretch“ freischalten; der Start bleibt −1…1.

**Frage 8 — Einheiten (§3.2)**
1. Neues Registry-Feld `band_units` je Asset ohne Vorgabe. Das Item geht vor. Die
   Einheit steht im Rezept (`Band.unit`) und im Ergebnis; ein einmaliger
   Cache-Fehlschuss **(Empfehlung)**.
2. Wie 1, aber nur zur Anzeige, nicht im Rezept. Kein Fehlschuss, dafür nennt das
   Ergebnis-Item keine Einheit.
3. Nur aus dem Item; heute zeigte das nirgends eine Einheit.

**Frage 9 — „Parameter übernehmen“ (§3.4)**
1. Beim Laden wählbar: „Steps only“ (auf die aktuelle Auswahl) oder „Everything“
   (Datensatz, Szenen, AOI, Schritte) **(Empfehlung)**
2. Nur „Steps only“; alles wiederherstellen kann nur der Permalink.
3. Nur „Everything“.

**Frage 10 — Schnitt (§4)**
1. Fünf PRs M4-19a bis M4-19e in der Reihenfolge aus §4 **(Empfehlung)**
2. Drei PRs: Methodentext und Einheiten; Farbskala; Übernehmen und Permalink.

**Frage 11 — ADR**
1. Kein neues ADR. Nachträge in `adr/0014`, `adr/0015` und `adr/0006` je Teil-PR
   (§4) **(Empfehlung)**. Grund: Die Grundsätze (zufällige Kennung, keine AOI nach
   außen, Frist) stehen schon fest.
2. `adr/0017` für Permalinks (Tabelle, Frist, Löschen).

**Frage 12 — Cache-Treffer und Frist (Befund §2.1)**
1. Der Code bleibt. In M4-19e werden die Docstrings in `cleanup.py` und
   `submit.py` angeglichen, dazu ein Nachtrag in `adr/0015` §7.1: Nur ein neuer
   Lauf verlängert, ein Treffer nie, weil die Bucket-Regel ab dem Schreiben zählt
   **(Empfehlung)**.
2. Ein Treffer soll verlängern. Dazu müsste er das Objekt kopieren (`adr/0015`
   §8.3 T2); eigene Aufgabe nach M4.

---

## 8. Nach der Freigabe

- Die Antworten kommen als §9 in diesen Plan, dazu Log-Zeilen und die Zeilen
  M4-19a bis M4-19e in §3 der Übersicht.
- Jeder Teil startet als neue Session mit dem Satz „Führe Aufgabe M4-19x aus
  `docs/plans/m4-processing-kern.md` aus (Plan: `docs/plans/m4-19-teilen-und-beschreiben.md`).“
- Jeder Teil-PR bringt eine Prüfanleitung für Otto in PowerShell 5.1 (§1.2 der
  Übersicht), geprüft gegen die Antwortform. Der Teil e etwa: Permalink mit
  `Invoke-RestMethod -Method Post` anlegen, im zweiten Browser öffnen, löschen,
  `404` sehen.

---

## 9. Freigabe (Otto, 20.10.2026)

Fragen 1–12 je Option 1. Frage 12: Der Code bleibt; F13 in `adr/0015` wird per Nachtrag
angeglichen, mit der Begründung aus §2.1 (die Regel am Bucket zählt ab dem Schreiben).

**Auflagen:**
- **`methods.txt` gehört zur einen Definition der Download-Inhalte aus M4-30** (Zuschnitt,
  Export, Job-ZIP, Runner), kein zweiter Weg. Ein Test prüft gegen diese Definition, nicht
  gegen eine zweite Liste.
- **Permalink (M4-19e):** Die AOI steht nie in einer URL oder einem Log, der Löschschlüssel
  nie in einem Log. Nach 30 Tagen ist der Eintrag vollständig gelöscht (Test). Im Log ist der
  Permalink als personenbezogen vermerkt.
- **Farbskala der Vorschau (M4-19c):** höchstens eine Messung je Vorschau-Zustand, gecacht,
  innerhalb der Grenzen von `gateway` (Test).

**Schnitt und Start:** M4-19a ist umgesetzt (§10). M4-19b bis M4-19e starten je als neue Session
nach §4 und der Reihenfolge dort.

---

## 10. Umsetzung M4-19a (20.10.2026)

- **Methodentext:** `processing/methods.py` (`methods_text`, `DatasetFacts`), `Operator.method` für
  `band_math` und `reproject` (Version 2 erbt von 3), Nachtrag `adr/0014` §15l.
- **Eine Definition:** `access/crop_rules.py::TEXT_FILES` und `METHODS_FILENAME`. Zuschnitt
  (`build_download_zip(methods_text=…)`), Export (Worker, `Attachments.dataset`), Job-ZIP und
  -Link (`api/processing_route.py`) und Runner (`runner/output.py`) schreiben `methods.txt`; jeder
  hat einen Test gegen `TEXT_FILES`.
- **Link:** `methods.txt` unter `/jobs/{jobID}/results` (Ausgang `methods`, `text/plain`), ein
  Eintrag in `LINK_NAMES`; Prozessbeschreibungen der Fixtures neu geschrieben.
- **Frontend:** „Methods“ in der Jobliste (auch neben dem ZIP) mit „Copy“.
- **Aufnahmetag (Otto, 22.10.2026):** Der Text nennt den UTC-Tag des Überflugs aus derselben
  Quelle wie der Dateiname seit M4-11b-1 (`acquired_on` des Jobs, gefunden von
  `api.intake.acquired_day` nach `catalog.registry.acquisition_day`). Job-Link und Job-ZIP nehmen
  `status.acquired_on`, der Export bekommt ihn als `Attachments.acquired_on`, der Zuschnitt rechnet
  ihn über seine Szenen. Ohne einzelnen Aufnahmetag (DEM, Szenen mehrerer Tage) und im Runner, der
  die Quelle nicht kennt, entfällt der Satz; der Tag des Laufs steht nie als Aufnahme, nur als
  „processed on“. Tests für Sentinel-2 und DEM.
- **Fund:** Die Registry hält die Adresse des DOI (`https://doi.org/…`); der Text nimmt
  `doi_name`, wie `citation.bib`.
- **Version:** Die Ergebnis-Bytes ändern sich nicht, `earthx.__version__` bleibt.

---

## 11. Umsetzung M4-19d (22.10.2026)

- **Lesen:** `recipeFile.ts::readRecipe` prüft die Datei im Browser (1 MB, JSON, `recipe_version`,
  `inputs`/`steps`, ein Datensatz und ein Input, AOI als Polygon, bekannte Ausgabe). `resolved`,
  `provenance` und `recipe_id` werden ignoriert.
- **Umkehrung:** `processingOrder.ts::draftFromOrder` prüft Operator, Version und Parameter gegen die
  Prozessbeschreibung (dieselbe Prüfung wie das Formular). Test: `buildOrder(draftFromOrder(x)) ≡ x` über
  die sieben Auftrags-Fixtures mit Schritten; die mit `steps: []` ergeben einen Entwurf ohne Schritte.
- **Store:** `loadRecipe(text, 'steps' | 'everything')`. Bei einem Fehler bleibt der Entwurf unverändert.
  „Everything“ setzt Datensatz, Szenen (wie `processLayer`, fehlende werden einzeln geholt), AOI und Bereich;
  ohne AOI im Rezept bleibt die AOI auf der Karte, der Bereich ist „Whole scene“.
- **Zuschnitt-Rezept:** „Everything“ stellt die Auswahl her (ohne Schritte und Datentyp), „Steps only“ sagt
  „This recipe has no steps.“
- **Festgelegt (Otto, 22.10.2026):** Mehrere Gruppen im Rezept (Export) wählen alle Szenen aus, den
  Durchgang wählt der Nutzer; ohne AOI bleibt die Karten-AOI, der Bereich ist „Whole scene“; ein
  Zuschnitt-Rezept ohne Schritte ist so angenommen.
- **Ältere Fassung:** Die Prozessbeschreibung listet nur die höchste `op_version` (`_jobs_of`), das Backend
  nimmt ältere weiter an (reproject v2). `draftFromOrder` lädt einen solchen Schritt als die gelistete
  höhere Fassung, wenn seine Parameter deren Formular bestehen, und sagt es in einem Hinweis. Das ist
  verlustfrei für reproject (v2 ist v3 mit engerer Methodenliste, `REPROJECT_V2`). Eine Fassung über der
  gelisteten bleibt „not available“. Vor dieser Änderung wurde ein v2-Rezept abgewiesen.
- **Nur „Steps only“ (Otto, 22.10.2026):** „Everything“ ist aus Panel und Store entfernt, weil es AOI, Auswahl
  und Ergebnisliste auf der Karte ersetzte. „Load recipe…“ (große Schaltfläche) lädt nach der Dateiwahl sofort
  die Schritte und den Datentyp. Die Festlegungen zu mehreren Gruppen und fehlender AOI betreffen damit nur
  noch den Permalink (M4-19e); ein Zuschnitt-Rezept ohne Schritte meldet „This recipe has no steps.“

---

## 12. Umsetzung M4-19b (22.10.2026)

- **Registry:** `DatasetConfig.band_units` (ohne Vorgabe, B10), Schlüssel wie ein Auftrag das Asset nennt, `*`
  für eine Gruppe, `None` für „unbekannt“; der Eintrag prüft Text, Länge und je einen Schlüssel für die
  Standarddarstellung und die Maske. Einheiten: Reflexionsbänder `"1"`, das DEM `"m"`, `scl`/`visual` `None`.
  `aot`, `wvp`, `cloud`, `snow` und `preview` bleiben ohne Eintrag (keine Quelle gelesen, nichts geraten).
- **Rezept und Kern:** `Band.unit` und `ResolvedInput.unit` (beide mit Vorgabe `None`, ältere `recipe.json` lesen
  weiter), `Source.units` → `BandMeta.unit` in Job, Kachel und Schätzung, `bands[].unit` im Ergebnis. Nachtrag
  `adr/0014` §15n.
- **Abweichung vom Plan (§3.2):** Ein COG-Item ohne Bandbeschreibung (das DEM) bekommt kein erfundenes `Band`,
  denn das behauptete eine Bandanzahl, auf die `check_bands` sonst bis zur Datei wartet (ein Test hielt das
  fest und schlug an). Die Einheit steht dort an `ResolvedInput.unit`, `bands` bleibt leer.
- **Hashwerte erneuert (`adr/0014` §4.4 Punkt 9, Auflage des Plans §5):** Alle vier festen Werte in
  `test_recipe.py::EXPECTED` sind neu; jedes Rezept trägt `"unit":null` zweimal mehr. Die alten Werte stehen als
  `OLD`, ein Test leitet sie aus dem neuen Kern her (Schlüssel heraus, gleicher Hash). Nach dem Deployment gibt
  es einmal für alle gecachten Ergebnisse keinen Treffer.
- **Anzeige (Otto, 24.10.2026):** nur die Band-Chips im Panel („data · m“); „1“ zeigt das Frontend nicht („red“),
  `shownUnit` ist dafür die eine Stelle und gilt auch für M4-19c. Der Layer-Manager zeigt bei keiner Layer-Art
  eine Einheit (der Hinweis „Unit: m“ am Ergebnis-Layer ist entfernt, ein Test hält es fest). Die Collection gibt
  `earthx:band_units` heraus.
- **Nicht gebaut, Übergabe an M4-19c (Otto, 23.10.2026):** die Einheit in der Wertebereich-Zeile der Vorschau.
  Sie kommt mit M4-19c als Feld im TileJSON der Operator-Kachel: Der Kern kennt die Einheit hinter den
  Schritten (`OperatorTileReader` rechnet `transform` je Schritt schon vor dem ersten Pixel und hält dabei
  `BandMeta.unit`); das Panel baut diese Bandlogik nicht nach. 19c liest dann `unit` aus dem TileJSON in die
  Zeile neben „min“/„max“ und dasselbe Feld für `/statistics` mit `op`. Dort gilt `shownUnit`
  (`processingOrder.ts`): für „1“ steht nichts, das TileJSON trägt die Einheit unverändert.
- **Angenommen (Otto, 23.10.2026):** `ResolvedInput.unit` für das DEM; `aot`, `wvp`, `cloud`, `snow` und `preview`
  ohne Einheit für M4, eine Einheit dafür kommt nach M4.
- **Belege zu Rezeptdateien (Frage Otto, 23.10.2026):** (a) Eine `recipe.json` ohne Einheiten (Datei aus einem
  alten Job-ZIP) lädt über „Load recipe…“ und gibt die Bestellung zurück, aus der sie gemacht wurde
  (`processingDraft.test.ts`, alle Bestellungen mit Schritten, mit und ohne `unit`). (b) Die Rundreise
  `buildOrder`/`draftFromOrder` trägt die neuen Schlüssel *nicht*, und soll es nicht: Sie stehen in `resolved`,
  das die Bestellung nie enthält; der Test prüft, dass `unit` und `resolved` nicht in der gebauten Bestellung
  stehen. (c) Der Runner nimmt die neue Datei an und lässt sie byte-gleich im Ergebnisordner; die committete
  `recipe-ci.json` (ohne `unit`) liest weiter (`runner/test_cli.py`).

### 12.1 Prüfanleitung für Otto (PowerShell 5.1)

Entwurf. Belegt sind die Antwortformen der Collection (Rundreise durch pgstac, `test_pgstac_load.py`) und der
Ergebniseigenschaften (`test_units.py`); gegen einen laufenden Stack mit echter Quelle ist sie nicht gelaufen, weil
das `gateway` der Sitzung keine Quelle erreicht.

```powershell
docker compose up -d --build
$api = 'http://localhost:8000'

# 1) Die Collections nennen ihre Einheiten (null = unbekannt)
foreach ($id in 'cop-dem-glo-30', 'sentinel-2-c1-l2a', 'sentinel-2-l2a-zarr3') {
    $c = Invoke-RestMethod "${api}/stac/collections/${id}"
    '{0}: {1}' -f $id, ($c.'earthx:band_units' | ConvertTo-Json -Compress)
}
# erwartet: cop-dem-glo-30 {"data":"m"}; sentinel-2-c1-l2a mit "red":"1" und "scl":null; zarr3 {"SR_*":"1","SCL_20m:scl":null}

# 2) Ein DEM-Job: die Einheit steht im Ergebnis
$search = @{ collections = @('cop-dem-glo-30'); bbox = @(10.0, 47.0, 10.5, 47.5); limit = 1 } | ConvertTo-Json -Depth 5
$tile = (Invoke-RestMethod -Method Post -Uri "${api}/stac/search" -ContentType application/json -Body $search).features[0]
$cx = ($tile.bbox[0] + $tile.bbox[2]) / 2; $cy = ($tile.bbox[1] + $tile.bbox[3]) / 2; $h = 0.01
$ring = @(@(($cx - $h), ($cy - $h)), @(($cx + $h), ($cy - $h)), @(($cx + $h), ($cy + $h)),
          @(($cx - $h), ($cy + $h)), @(($cx - $h), ($cy - $h)))
$order = @{ recipe_version = 1; steps = @(); aoi = @{ type = 'Polygon'; coordinates = @(, $ring) }
            inputs = @(@{ name = 'input'; dataset = 'cop-dem-glo-30'; groups = @(, @($tile.id)); assets = @('data') })
            output = @{ kind = 'raster'; format = 'cog'; dtype = 'float32' } }
$body = @{ inputs = @{ recipe = $order } } | ConvertTo-Json -Depth 12
$job = Invoke-RestMethod -Method Post -Uri "${api}/processing/processes/recipe/execution" `
    -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
do { Start-Sleep 5; $status = Invoke-RestMethod "${api}/processing/jobs/$($job.jobID)"; $status.status } while ($status.status -in 'accepted', 'running')
$results = Invoke-RestMethod "${api}/processing/jobs/$($job.jobID)/results"
$results.result.properties.bands | ConvertTo-Json -Depth 4     # "unit": "m" zwischen nodata und statistics

# 3) Im Browser (http://localhost:5173): DEM-Szene wählen, "Process": der Chip heißt "data · m";
#    bei einer Sentinel-2-Szene heißt der Chip "red", ohne Einheit ("1" zeigt das Panel nicht).
#    Den Job starten, "Add to layers": der Layer-Manager zeigt bei keiner Ebene eine Einheit; sie steht
#    nur in den Daten ($results.result.properties.bands, Schritt 2).
```

Aus dem Ergebnis eines Band-Math-Jobs (`(nir - red) / (nir + red)`) fehlt `unit` ganz; ein Ausdruck, der nur `red`
heißt, behält die Einheit `1`.

---

## 13. Umsetzung M4-19e (24.10.2026)

- **Backend:** Migration `012_permalink.sql` (`earthx_permalink`: Kennung, `body` jsonb, SHA-256 des
  Löschschlüssels, `created_at`, `expires_at`, Index auf `expires_at`, kein Fremdschlüssel). `jobs/permalinks.py`
  (`create`, `read`, `delete`, `TTL = 30 Tage`) legt an und liest mit der Uhr der Datenbank; die Routen in
  `api/processing_route.py` (`POST`, `GET`, `DELETE /processing/permalinks`), dazu `loggable_path` mit
  `{permalinkID}`. Der Aufräumer in `jobs/cleanup.py` löscht abgelaufene Permalinks im selben Durchgang
  (`CleanupResult.permalinks`). Importregeln unverändert: `jobs` fasst die Tabelle mit SQL an, `api` ruft `jobs`
  auf wie bei den Aufträgen. Nachträge: `adr/0015` §14d, `adr/0014` §15o.
- **Eingabe:** Rumpf `{"order": …, "view": …}`, höchstens 1 MB (`MAX_BODY_BYTES`, wie die Auftragsroute). Der
  Auftrag geht durch `parse_request` (I-JSON, streng, `resolved` wird abgewiesen, `422`); die Ansicht hat ein eigenes
  Modell mit `extra="forbid"` (`center`, `zoom` 0–24, `range` mit `vmin`, `vmax`, `colormap`; kein Titel). Gespeichert wird der Auftrag wie gesendet, nicht umgeschrieben. Kein Datensatz- oder
  Szenen-Abruf: ob die Szenen noch existieren, zeigt sich beim Öffnen.
- **Antworten:** `201` `{id, expires_at, delete_key}`; `GET` `200` `{order, view, expires_at}`; `DELETE` `204`.
  `404` mit einem Text für unbekannt, falsch geformt, abgelaufen und falschen Schlüssel; ein fehlender Kopf
  `X-Delete-Key` ist `400` für jede Kennung gleich (verrät nichts über die Kennung). Alles `no-store`.
- **Frontend:** `permalink.ts` (Aufrufe, Adresse, Schlüssel in `localStorage` unter `earthx.permalinks`, Ansicht,
  Öffnen), `ShareLink.tsx` im Fuß des Panels („Share“, danach die Adresse in einem schreibgeschützten Feld im Farbschema des Themes, das Kopier-Symbol der Ergebnisliste (`CopyButton`, aus `ResultsPanel` herausgelöst) und ein kleines rotes Kreuz „Delete link“),
  `restoreOrder` im Store, `flyToView` für die Kamera. Beim Start liest `App` `?permalink=` **nach**
  `loadDatasets` (das setzt die Auswahl zurück), holt den Eintrag, stellt Datensatz, Szenen, AOI, Schritte,
  Datentyp, Bereich und Kartenansicht her und entfernt den Parameter mit `history.replaceState`, auch bei einem
  Fehler. `404` meldet „This link has expired or never existed.“
- **Festlegungen aus §11 für den Permalink:** Mehrere Gruppen wählen alle Szenen aus, den Durchgang wählt der
  Nutzer; ohne AOI im Auftrag bleibt die AOI der Karte und der Bereich ist „Whole scene“. Beides hat ein Test.
- **Abweichungen vom Plan und Antworten Otto (24.10.2026):**
  1. **Basiskarte** (§3.5) ist nicht Teil der Ansicht: Die App hat nur eine Basiskarte, Thema und Projektion sind
     Einstellungen des Browsers. Otto: kein Feld; es kommt mit UI-02.
  2. **Ein Link hält einen Auftrag:** „Share“ ist bei „Run as“ Szene/Durchgang gesperrt, der Grund steht im Tooltip
     („A link holds one order: choose “One job”.“). Otto: gesperrt lassen, mit Grund im Panel. Später am 24.10.2026 (Otto): unter „Share“ steht nie ein
     Beschreibungstext; der Grund steht seitdem nur noch im Tooltip des gesperrten Knopfs.
  3. **`jobs/submit.py`** sagte nicht mehr „nur ein Lauf oder ein Treffer verlängert“ (so der Plan §2.1), nur
     `cleanup.py`; nur dort ist der Docstring angeglichen.
  4. **Änderungen vor dem Merge (Otto, 24.10.2026):** (a) Der **Titel entfällt ganz**: kein Feld im Panel, nicht in
     der API, im Speicher und in der Migration 012 (noch nicht gemergt, also dort direkt, ohne neue Migration; die
     Ansicht lehnt `title` wie jedes unbekannte Feld ab). (b) Der Link steht in einem schreibgeschützten Textfeld, das
     die Regel `input[type='text']` des Themes nutzt (`--input-bg`, `--text`), nicht weiß im Dark Mode. (c) „Copy link“
     ist das Kopier-Symbol der Ergebnisliste: Dasselbe `CopyButton` (Glyph, Häkchen, Zwischenablage) ist aus
     `ResultsPanel` in `components/CopyButton.tsx` herausgelöst und wird von beiden benutzt. (d) „Delete link“ ist ein
     kleines rotes Kreuz rechts neben dem Kopier-Symbol, Tooltip und `aria-label` „Delete link“, löscht ohne Rückfrage
     und ohne Browser-Dialog; danach steht im Panel „Link deleted.“.
  5. **Größe:** weit über dem Richtwert (rund 1700 Zeilen, davon etwa 880 Tests). Otto: PR nicht teilen; die
     Begründung steht im PR-Text.
- **Woher die 30 Tage (Frage Otto):** aus §7 Frage 2, Option 1 („30 Tage fest ab Erstellung; Öffnen verlängert nicht“,
  Empfehlung), die Otto in §9 mit „Fragen 1–12 je Option 1“ freigegeben hat; ebenso in der Kurzfassung (Z. 37–40) und
  in §3.5 („Ansehen verlängert nie (Frage 2)“). Gezählt wird **ab Erstellung**, nicht ab dem letzten Öffnen (Option 3
  wäre „7 Tage ab dem letzten Öffnen“ gewesen und ist nicht gewählt). Im Code: `jobs/permalinks.py::TTL`,
  `expires_at = clock_timestamp() + TTL` beim Anlegen, nirgends sonst gesetzt; Test, dass Lesen die Frist nicht
  verschiebt (`test_cleanup.py::TestPermalinks`, `test_permalink_route.py`).
- **Belegt:** Anlegen, Lesen, Löschen gegen die echte Datenbank; `404` für unbekannt, falsch geformt, abgelaufen
  (Uhr der Datenbank, die Zeile wird zurückdatiert) und falschen Schlüssel; Größe, `extra` in der Ansicht,
  ungültiger Auftrag; Kennung, AOI, Schlüssel und Link in keinem Log (Zugriffslog und `caplog` mit
  `own_log_text`); der Aufräumer löscht nach 30 Tagen die ganze Zeile, vorher nicht, in Stapeln; Lesen verlängert
  nichts. Frontend: Öffnen (Zustand, Parameter weg, ein Aufruf bei doppeltem Start, `404`, `503`, Unsinn, fremder
  Operator, fehlende Szene, Auftrag ohne AOI), Teilen (Auftrag und Ansicht gesendet, Schlüssel nur im Browser,
  Löschen mit Schlüssel, Fehler behalten Link und Schlüssel, Stapel gesperrt, Grund im Tooltip, kein Text unter dem Knopf).
- **Belege auf Ottos Fragen (24.10.2026), `test_permalink_route.py`:**
  - *Zufällige Kennung, in keinem Log:* 20 Kennungen sind verschieden, 22 Zeichen aus `token_urlsafe(16)`, keine ist
    eine `recipe_id` (`TestWhatIsStored`); das Zugriffslog schreibt nur `/processing/permalinks/{permalinkID}`
    (`TestNothingPersonalInTheLogs`, `test_logging.py`), und kein Logsatz von Anlegen, Lesen, Löschen enthält Kennung,
    Schlüssel, Koordinaten oder Szene-ID.
  - *Gespeicherter Zustand ohne signierte URL, `href`, `result_id`:* Die Zeile hat genau die Spalten `permalink_id`,
    `body`, `delete_key_hash`, `created_at`, `expires_at`; `body` hat genau `order` und `view`. Nach einem fertigen
    Job mit `result_id` enthält der Text weder `href`, `X-Amz`, `result_id`, `jobID`, `recipe_id`, `resolved` noch die
    echte `jobID` oder `result_id`. Ein Auftrag mit `href`, `result_id`, `recipe_id` oder `provenance` ist `422` und wird
    nicht gespeichert; die Ansicht nimmt weder `href` noch `result_id`, `job_id`, `tiles`, `url` (`extra="forbid"`).
  - *Öffnen nach Ablauf des Ergebnisses:* `TestAfterTheResultIsGone`: Job und Ergebnis laufen ab, der Aufräumer löscht
    Lauf, Job und Rezept, `/jobs/{jobID}` ist `404`, der Permalink liefert weiter den Auftrag, und derselbe Auftrag ergibt
    `201` mit einem neuen Lauf, statt zu scheitern (vorher, bei lebendem Ergebnis, war er ein Cache-Treffer). Im
    Frontend bringt das Öffnen den Auftrag ohne Job und Ergebnis zurück, „Review“ und „Start job“ sind frei
    (`ProcessingShare.test.tsx`). Der Link zeigt also das Rezept und bietet das Neurechnen über den normalen
    „Review“/„Start job“ an; einen eigenen Hinweis „Ergebnis abgelaufen“ gibt es nicht, weil der Link kein Ergebnis kennt.
- **Nicht belegt:** Gegen einen laufenden Stack mit der Oberfläche im Browser ist es nicht gelaufen (kein
  Docker in der Sitzung); die Kamera (`jumpTo`) ist nicht an einer echten Karte gesehen worden.
- **Größe:** Weit über dem Richtwert von 400 Zeilen (rund 700 Zeilen Code, 750 Zeilen Tests). Die Commits trennen
  Backend (zwei) und Frontend (zwei); Otto kann daran teilen.

### 13.1 Prüfanleitung für Otto (PowerShell 5.1)

Entwurf. Belegt ist die Antwortform durch die Tests des Backends; gegen einen laufenden Stack nicht gelaufen.

```powershell
docker compose up -d --build
$api = 'http://localhost:8000'

# 1) Einen Permalink anlegen (die Szene muss nicht existieren, sie wird erst beim Öffnen gebraucht)
$ring = @(@(10.00, 47.00), @(10.01, 47.00), @(10.01, 47.01), @(10.00, 47.01), @(10.00, 47.00))
$order = @{ recipe_version = 1; steps = @(); aoi = @{ type = 'Polygon'; coordinates = @(, $ring) }
            inputs = @(@{ name = 'input'; dataset = 'cop-dem-glo-30'; groups = @(, @('Beispiel-Szene')); assets = @('data') })
            output = @{ kind = 'raster'; format = 'cog'; dtype = 'float32' } }
$view = @{ center = @(10.0, 47.0); zoom = 9.5 }
$body = @{ order = $order; view = $view } | ConvertTo-Json -Depth 12
$made = Invoke-RestMethod -Method Post -Uri "${api}/processing/permalinks" -ContentType 'application/json; charset=utf-8' `
    -Body ([Text.Encoding]::UTF8.GetBytes($body))
$made | Format-List      # id (22 Zeichen), expires_at (in 30 Tagen), delete_key (einmalig)

# 2) Lesen, auch im zweiten Browser: http://localhost:5173/?permalink=<id>
Invoke-RestMethod "${api}/processing/permalinks/$($made.id)" | ConvertTo-Json -Depth 12

# 3) Mit falschem und mit richtigem Schlüssel löschen
function Status($script) { try { & $script; 'ok' } catch { [int]$_.Exception.Response.StatusCode } }
Status { Invoke-RestMethod -Method Delete -Uri "${api}/processing/permalinks/$($made.id)" -Headers @{ 'X-Delete-Key' = 'falsch' } }   # 404
Status { Invoke-RestMethod -Method Delete -Uri "${api}/processing/permalinks/$($made.id)" -Headers @{ 'X-Delete-Key' = $made.delete_key } }  # ok (204)
Status { Invoke-RestMethod "${api}/processing/permalinks/$($made.id)" }   # 404
```

Im Browser (http://localhost:5173): Szene wählen, AOI zeichnen, „Process“, einen Schritt anlegen, unten „Share“. Es gibt
kein Titelfeld. Die Adresse steht in einem schreibgeschützten Feld in den Farben des Themes (auch im Dark Mode nicht
weiß), die Form ist `…/?permalink=<id>`, ohne Koordinaten. Rechts daneben das Kopier-Symbol (wie beim Szenennamen in den
Suchergebnissen; nach dem Klick kurz ein Häkchen) und ein kleines rotes Kreuz mit dem Tooltip „Delete link“. In einem zweiten Fenster öffnen: Datensatz, Szene, AOI,
Schritt und Kartenausschnitt sind wieder da, die Adresszeile zeigt den Parameter nicht mehr. Das Kreuz löscht ohne Rückfrage, das Panel meldet „Link deleted.“; die Adresse neu
öffnen: „This link has expired or never existed.“
