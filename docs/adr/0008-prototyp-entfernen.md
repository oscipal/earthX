# ADR 0008 — Den Prototyp entfernen

- **Status:** **Entwurf — Entscheidungsvorlage.** Die Entscheidung liegt bei Otto
  (`ENTSCHEIDUNGEN_2026-09-18.md` §3: „Er wird entfernt, sobald seine Funktionen
  mit einem token-freien Datensatz laufen — eigene Entscheidung von Otto,
  Stufe B"). §9 stellt sechs Fragen, jede mit nummerierten Optionen und einer
  Empfehlung. Dieses Dokument ändert nichts am Code.
- **Datum:** 2026-09-22
- **Aufgabe:** M2-11 laut `docs/plans/m2-format-und-viewer.md` §4.
- **Autonomiestufe:** C — nur gelesen und berichtet. Kein Produktivcode geändert,
  keine Datei außerhalb von `docs/` angefasst, kein Dienst aufgerufen.
- **Stand des untersuchten Codes:** `main` nach #58 (22.09.2026), einschließlich
  V-1 und M2-16. Die Abhängigkeit von M2-08 ist für diese Vorlage von Otto
  aufgehoben. Offen sind M2-08, M2-10 und M2-12.
- **Grundlage:** `ENTSCHEIDUNGEN_2026-09-18.md` §1, §2, §3, §4;
  `KLAERUNGEN.md` B8, B9, B10, B12; `architekturplan.md` 3.1, 3.2, 6.1, 7.2,
  7.3, 12.3, 13; `adr/0001` (Z1–Z9), `adr/0002` (T-A), `adr/0005` Regel IV,
  `adr/0006`, `adr/0007`; `prototyp-inventar.md` F1–F21, N1–N5, Teil 4;
  `projektuebersicht.md` §5; `plans/m2-format-und-viewer.md` D7, D11, D14, §5;
  Entscheidungslog.
- **Betroffen:** `backend/app/`, `backend/build_coverage.py`, `backend/tests/`,
  `backend/Dockerfile`, `backend/requirements.txt`, `pyproject.toml`,
  `environment.yml`, `README.md` §3, `SECURITY.md`, `CLAUDE.md`;
  `architekturplan.md` 13; Entscheidungslog.

## Methode und Grenzen

Reines Lesen des Repos in einer Cloud-Sitzung vom 22.09.2026. Kein MAAP-Zugang,
kein externer Dienst aufgerufen, nichts ausgeführt außer Lesebefehlen. Aussagen
über Laufzeitverhalten sind aus dem Code abgeleitet, nicht gemessen. Zeilenzahlen
stammen aus `wc -l`.

Der Wert des Client-Secrets aus `backend/app/config.py` wird hier **nicht**
wiedergegeben, auch nicht auszugsweise. Die Vorlage nennt nur, dass es das Feld
gibt und was mit der Ausnahme geschieht; sie schlägt weder eine
History-Bereinigung noch einen Widerruf vor — beides ist in `CLAUDE.md`
ausdrücklich ausgeschlossen.

---

## 1. Kontext und Frage

`ENTSCHEIDUNGEN_2026-09-18.md` §3 hält den Prototyp als Referenz im Repo und
knüpft sein Ende an **eine** Bedingung: *seine Funktionen laufen mit einem
token-freien Datensatz*. §2 zählt auf, was dabei erhalten bleiben soll, und
`prototyp-inventar.md` ist der maßgebliche Bestand dazu (F1–F21).

Seither ist M2 fast fertig: Sentinel-2 L2A läuft über den eigenen Kachel-Pfad
(M2-04), Coverage (M2-05), Zuschnitt-Download (M2-06), das Frontend spricht seit
M2-07a nur noch mit `earthx` (D7), der Zarr-Lesepfad steht (M2-09a/b), und V-1
hat Theme und Kartenbedienung nachgezogen.

Die Frage dieser Vorlage ist deshalb zweiteilig:

1. **Ist die Bedingung aus §3 erfüllt?** — Abschnitt 3 prüft das Funktion für
   Funktion.
2. **Wenn ja: was genau fällt weg, und wohin geht `decomp.py`?** — Abschnitte 4
   bis 6.

Zwei Randbedingungen stehen schon fest und werden hier nicht neu aufgerollt:
Der Tag **`prototype-biomass`** liegt seit dem 20.09.2026 auf `main`
(Commit `48d573c`, vor M2-07a) und hält den vollständigen, lauffähigen Prototyp
samt seinem Frontend dauerhaft abrufbar (D7). Und die Token-Logik wird nicht
übernommen und nicht generalisiert (§1, §3, `architekturplan.md` 13).

---

## 2. Kriterien

| # | Kriterium | Warum |
|---|---|---|
| K1 | Jede Funktion F1–F21 läuft token-frei **oder** ihr Wegfall ist bereits entschieden | Die Bedingung aus ENTSCHEIDUNGEN §3 |
| K2 | Nichts geht unwiederbringlich verloren | Der Prototyp ist Referenz, nicht Produkt (§2) |
| K3 | `decomp.py` bleibt als ruhender Operator mit Quad-Pol-Capability erhalten | ENTSCHEIDUNGEN §3, KLAERUNGEN B10, `architekturplan.md` 7.2, 13 |
| K4 | Der Umbau macht die Regeln des Zielpfads nicht schwächer, sondern schärfer | KLAERUNGEN B8, B9; M2-Abnahme §5 Punkte 6 und 7 |
| K5 | CI, Lint, Importverträge und `compose-topology` bleiben grün | M2-Abnahme §5 Punkt 8 |
| K6 | Ein PR, thematisch geschnitten, überschaubar zu prüfen | `CLAUDE.md`, Projektplan 1.3 |

---

## 3. Läuft jede Funktion token-frei? (F1–F21)

Gelesen wurde `backend/earthx/` und `frontend/src/` gegen `prototyp-inventar.md`
Teil 1. „In `earthx`" heißt: die Funktion ist im Zielpfad vorhanden und braucht
keinen Token.

| F | Funktion | In `earthx` | Fundstelle (Beispiel) |
|---|---|---|---|
| F1 | AOI Punkt/Rechteck/Polygon | **ja** | `frontend/src/components/Toolbar.tsx`, `MapView.tsx`, `store.ts` |
| F2 | Ortssuche (Geocoding) | **nein — verschoben** | entfällt in M2 laut Otto (M2-Plan §1.2 F1: kommt mit M3) |
| F3 | AOI aus KML/GeoJSON, „letzte AOI" | **ja** | `frontend/src/aoiFile.ts`, `ControlPanel.tsx` |
| F4 | STAC-Suche + Filter | **ja** | `earthx/api/federating_client.py`, `adapters/earth_search.py`, `frontend/src/api.ts` |
| F5 | Gruppierung zu Zeitschritten | **ja**, jetzt aus der Registry | `catalog/registry.py::group_key`, `frontend/src/grouping.ts` (D19) |
| F6 | Quicklook-Overlays | **ja**, ohne Proxy | `frontend/src/mapLayers.ts` (D14); Platzierung korrigiert in M2-16 |
| F7 | Zeitleiste | **ja** | `frontend/src/components/TimeSlider.tsx` |
| F8 | Anklicken → Auswählen → Bestätigen | **ja** | `MapView.tsx`, `ResultsPanel.tsx`, `DownloadDialog.tsx` |
| F9 | AOI-Zuschnitt, partielle Reads | **ja** | `earthx/access/download.py`, `readers/cog.py`, `readers/zarr_reader.py` |
| F10 | Zweistufige Anzeige (PNG → Kacheln) | **ja** | `earthx/api/tiler.py`, `access/tiles.py`, `frontend/src/mapLayers.ts` |
| F11 | Stitching über eine AOI | **ja im Zuschnitt**, kein eigener Endpunkt | `access/download.py` (`mosaic_reader`); im Kachel-Pfad bewusst nicht (D11) |
| F12 | Coverage Map | **ja** | `earthx/api/coverage_route.py`, `catalog/coverage.py`, `frontend/src/coverage.ts` |
| F13 | Platten-Cache mit LRU | **bewusst nicht** | widerspricht B9 und `architekturplan.md` 3.2; Ersatz laut `adr/0001` Z2 |
| F14 | Streckbereichs-Cache im Prozess | **bewusst anders** | Statistik-Cache in Postgres (`catalog/stats_cache.py`), Streckbereich in der URL (D13, D20) |
| F15 | Asset-Proxy mit Token | **ersatzlos** | Grund war der Token; Allowlist ist in `gateway` aufgegangen (B8, D14, Log 20.09.) |
| F16 | MAAP-Anmeldung, OIDC | **ersatzlos** | ENTSCHEIDUNGEN §1, §3 |
| F17 | Polarimetrische Dekomposition | **ruht** | Capability-Flag `quad_pol` steht (`catalog/registry.py:113`), Rechenkern noch in `backend/app/decomp.py` — siehe §6 |
| F18 | Darstellungssteuerung | **ja** | `frontend/src/components/ViewerControls.tsx`, `render.ts`, `api/tiler.py` |
| F19 | Layer-Manager | **ja** | `frontend/src/layers.ts`, `components/LayerManager.tsx` |
| F20 | Bedienfunktionen (Sammelposten) | **ja**, bis auf den Token-Hinweis | `Draggable.tsx`, `StatusBar.tsx`, `store.ts::zoomToView`, `clearAll` |
| F21 | Fehlerbehandlung pro Item | **ja** | `access/download.py`, `frontend/src/download.ts` |
| N1 | Theme-Umschalter | **ja, neu gebaut** | V-1: `frontend/src/preferences.ts`, `App.tsx` |
| N2 | Dunkles Kartendesign | **ja**, ohne helle Basiskarte | D10: helle Basiskarte bewusst nicht in M2 |

### 3.1 Die vier Fälle, die kein glattes „ja" sind

**F2 Ortssuche.** Nicht in `earthx`, und das ist keine Lücke, sondern Ottos
Antwort auf Frage F1 des M2-Plans vom 20.09.2026: Die Ortssuche ist in M2
ausgeblendet und kommt mit M3 („Ortssuche mit Umriss"), weil der Geocoder aus
der Cloud nicht erreichbar und die Nominatim-Bedingungen offen sind. Der alte
`routes/geocode.py` ist ein 48-Zeilen-Proxy ohne Token — als Vorlage genügt
dafür der Tag.

**F11 Stitching.** In `earthx` vorhanden, aber nur im Zuschnitt-Pfad
(`mosaic_reader` in `access/download.py`), nicht als eigener Endpunkt und nicht
im Kachel-Pfad. Auch das ist entschieden: D11 nimmt das Mosaik in M2
ausdrücklich aus dem Kachel-Pfad heraus (2,7 MB je Mosaik-Kachel, kein CDN).

**F13/F14 Zustand.** Nicht übertragen, weil sie nicht übertragen werden
*dürfen*: `adr/0001` ordnet Z1 bis Z9 den Zielebenen zu, B9 verbietet dem
Worker-Kern Plattformdienste. Der Zweck lebt weiter (Statistik-Cache in
Postgres, Streckbereich in der Kachel-URL), die Umsetzung nicht.

**F17 Dekomposition.** Der einzige Punkt, an dem beim Entfernen tatsächlich
Substanz verloren ginge. Abschnitt 6 behandelt ihn eigens.

**Ergebnis zu K1:** Von 21 Funktionen laufen 17 token-frei im Zielpfad, zwei
sind durch ausdrückliche Entscheidungen verschoben (F2 nach M3, F11 teilweise
nach M4), zwei sind durch ebenso ausdrückliche Entscheidungen ersatzlos
gestrichen (F15, F16), zwei sind bewusst anders gelöst (F13, F14). Offen bleibt
allein F17. **Die Bedingung aus ENTSCHEIDUNGEN §3 ist damit erfüllt**, sobald
F17 geregelt ist.

---

## 4. Was beim Entfernen wegfällt

### 4.1 `backend/app/` — 20 Dateien, 1703 Zeilen

| Datei | Zeilen | Was sie tut | Token |
|---|---|---|---|
| `__init__.py` | 3 | Paket-Init | — |
| `main.py` | 38 | FastAPI-App, hängt neun Router unter `/api` ein | — |
| `config.py` | 86 | `Settings`, Allowlist, OIDC-Felder | **ja** (Feld `oidc_client_secret`, Zeile 33) |
| `auth.py` | 131 | Offline-Token → Access-Token am MAAP-OIDC-Endpunkt | **ja, ganz** |
| `stac.py` | 162 | Suche im MAAP-STAC über `pystac_client` | — |
| `store.py` | 178 | Item-Registry, Zuschnitt-Cache, LRU (Z1–Z3) | — |
| `cog.py` | 372 | Kacheln, Zuschnitt, Stitching, Streckbereichs-Cache | **ja** (GDAL-Umgebung) |
| `decomp.py` | 224 | Pauli und Freeman–Durden auf Quad-Pol-SCS | **ja** (Lesepfad) |
| `geo.py` | 45 | AOI normalisieren, Punktpuffer | — |
| `schemas.py` | 24 | Request-Modelle | — |
| `routes/` (9 Module + Paket-Init) | 440 | `meta`, `search`, `coverage`, `geocode`, `tiles`, `assets`, `download`, `stitch`, `decompose` | fünf davon **ja** |

### 4.2 Was außerhalb von `backend/app/` daran hängt

| Ort | Was | Beim Entfernen |
|---|---|---|
| `backend/build_coverage.py` (85 Z.) | Skript, das die BIOMASS-Coverage als Dichtegitter vorberechnet; `from app import stac` | entfällt — ersetzt durch den Coverage-Anbieter aus M2-05 (`adr/0004`) |
| `backend/tests/test_app_starts.py` (65 Z., 7 Tests) | prüft, dass der Prototyp startet und seine neun Router anbietet | entfällt |
| `backend/tests/test_config.py` (74 Z., 10 Tests) | prüft `Settings`, die Allowlist und dass `/api/config` keinen Wert preisgibt | entfällt |
| `backend/tests/test_config.py:64` | der einzige `xfail` im Repo (`strict=True`): `Settings.host_allowed` lässt über ein blankes `endswith` einen Ähnlich-Host durch | entfällt **mitsamt der Schwäche**; `gateway/policy.py` hat sie nie geerbt |
| `backend/earthx/gateway/policy.py:4` | Docstring verweist auf genau diesen `xfail` | Verweis umschreiben, Aussage bleibt |
| `backend/tests/conftest.py:54` | `clean_settings` (autouse) importiert `app.config` — heute zieht **jeder** Test im Repo den Prototyp mit | Fixture entfällt; die `no_network`-Fixture bleibt unberührt |
| `backend/Dockerfile:36` | `COPY app ./app` — der Prototyp liegt in jedem Image, obwohl kein Prozess ihn startet | Zeile entfällt |
| `backend/requirements.txt` | `pystac-client` wird **nur** von `app/stac.py` gebraucht; `requests` von gar nichts | beide können gehen — siehe 4.3 |
| `pyproject.toml:24` | `known-first-party = ["app", "earthx", "tests"]` | `"app"` entfällt |
| `pyproject.toml:34` | `filterwarnings = ["error::DeprecationWarning:app.*"]` | entfällt oder zeigt auf `earthx.*` |
| `environment.yml` (30 Z.) | Conda-Umgebung `biomass-viewer`; nur vom Prototyp-Abschnitt der README benutzt, nicht von CI (die nimmt `backend/requirements-dev.txt`) und nicht vom SessionStart-Hook | entfällt |
| `README.md:4` und `README.md:140–198` (Abschnitt 3) | beschreiben `backend/app/` + `frontend/` als Prototyp samt Conda, Token und Start | Abschnitt 3 entfällt, der Einleitungssatz wird umgeschrieben |
| `SECURITY.md:22–27` | Abschnitt „Bekannte, bewusst befristete Ausnahme" | Ausnahme endet — siehe §9 Frage 4 |
| `CLAUDE.md:27–31` | derselbe Absatz unter „Unverrückbar" | dito; `CLAUDE.md` steht unter „ohne Rückfrage nicht ändern" |
| `docker-compose.yml` | **nichts** — alle fünf Dienste starten `earthx.*` | unverändert |
| `.importlinter` | **nichts** — die elf Verträge kennen nur `earthx.*` | unverändert |
| `frontend/` | **nichts** — spricht seit M2-07a nur `/stac`, `/coverage`, `/collections` | unverändert |

### 4.3 Zwei Nebenwirkungen, die für den Zielpfad sprechen

**`pystac_client` verlässt das Image.** `adr/0005` Regel IV schließt die
Bibliothek aus dem Zielpfad aus, weil sie Weiterleitungen ungeprüft folgt, und
zwei Tests führen sie als verbotenen Import (`test_module_boundaries.py:119`,
`test_no_outbound_outside_gateway.py:33`). Verwendet wird sie heute an genau
einer Stelle: `backend/app/stac.py:11`. Solange der Prototyp im Repo liegt, ist
das Paket trotzdem in `requirements.txt` und damit in jedem Image installiert.

**Die Importverträge gewinnen Geltung.** `backend/app/` liegt außerhalb der elf
Verträge aus `.importlinter` und ruft in `auth.py`, `routes/assets.py` und
`routes/geocode.py` direkt `httpx` auf — also drei Stellen im Repo, an denen
ausgehende Requests an `gateway` vorbeigehen. Abnahmekriterium 6 aus dem M2-Plan
(„kein ausgehender Request außerhalb von `gateway`") gilt heute nur, weil man
`backend/app/` nicht mitzählt. Nach dem Entfernen stimmt der Satz ohne Fußnote.

### 4.4 Was **nicht** wegfällt

Das Wissen über den Prototyp liegt in vier Formen vor, von denen keine am Code
hängt: der Tag `prototype-biomass` (vollständiger, lauffähiger Stand samt
Frontend), `docs/prototyp-inventar.md` (F1–F21 mit Fundstellen und Bewertung),
`adr/0001` (Zustand Z1–Z9) und `architekturplan.md` 13 (Abbildung auf die
Zielarchitektur). Lokal bleibt der Prototyp über
`git worktree add ../biomass-prototyp prototype-biomass` in einem eigenen
Verzeichnis lauffähig — damit bleibt auch Ottos Erlaubnis aus §3, BIOMASS lokal
als Testdaten zu nutzen, praktisch nutzbar.

---

## 5. Der Befund, der die Frage schon halb entschieden hat

**Seit M2-07a ist der Prototyp nicht mehr vollständig lauffähig.**

`README.md` Abschnitt 3 beschreibt ihn als „`backend/app/` + `frontend/`" und
sagt zum Start: „der Vite-Dev-Server leitet `/api` an das Backend auf Port 8000
weiter". Das trifft nicht mehr zu. `frontend/vite.config.ts` kennt heute genau
drei Proxy-Regeln — `/stac`, `/coverage` und `/collections` —, und
`frontend/src/api.ts` hält im Kopfkommentar fest: „Never talks to the
prototype's `/api/…` routes." Das war so beschlossen (D7: Tag setzen, dann
Frontend vollständig auf `earthx`).

Was im Repo liegt, ist also kein „lauffähiger Prototyp" mehr, sondern ein
Backend ohne Oberfläche, bedienbar nur noch über `/docs`. Die Referenz, die §3
erhalten wollte, hängt seither ohnehin am Tag, nicht am Arbeitsbaum. Der
Arbeitsbaum trägt nur noch die Kosten: 1703 Zeilen Code in jedem Image, von denen
zwei Testdateien nur Start und Konfiguration berühren, drei `httpx`-Aufrufe außerhalb von `gateway`, ein Paket auf der
Verbotsliste in `requirements.txt`, ein Import des Prototyps in der
suite-weiten `conftest.py` und eine README, die einen Zustand beschreibt, den es
nicht mehr gibt.

---

## 6. `decomp.py` — drei Schichten, zwei davon schon tot

`backend/app/decomp.py` (224 Zeilen) besteht aus drei klar getrennten Schichten.
Das ist der Grund, warum „übernehmen" und „löschen" hier nicht die einzigen
Möglichkeiten sind.

| Schicht | Zeilen | Abhängigkeiten | Zustand im Zielpfad |
|---|---|---|---|
| **Rechenkern** — `METHODS`, `_boxcar`, `_boxcar_c`, `_pauli`, `_freeman`, `_DECOMP` | 31, 39–56, 113–165 (~125) | nur `numpy` | unverändert brauchbar, synthetisch testbar |
| **Geometrie** — `_warp_complex` | 57–112 (56) | `rasterio`, GCP-Warp, `_gdal_env(token)` | an zwei GCP-georeferenzierte GeoTIFFs gebunden; die Regel dahinter (Nächster-Nachbar, damit Betrag und Phase je Pixel zusammenbleiben) ist das Wertvolle daran |
| **Plattform-Anbindung** — `decompose_crop` | 167–224 (58) | `app.auth` (Token), `app.store` (Registry + Plattencache), `rio_cogeo` | **im Zielpfad nicht mehr zulässig**: `auth` ist gestrichen (§1/§3), `store` verstößt gegen B9 und `adr/0001` Z1/Z2 |

Der Rechenkern ist reines `numpy` und hängt an nichts: Pauli rechnet
`R=|HH−VV|/√2, G=√2·|HV|, B=|HH+VV|/√2` auf dem komplexen Streuvektor,
Freeman–Durden bildet die Kovarianzelemente über einen eigenen Boxcar auf
Integralbildbasis. Beides lässt sich gegen synthetische Streuvektoren prüfen,
für die das Ergebnis analytisch bekannt ist (reine Oberfläche, reine
Doppelreflexion, reines Volumen) — genau die Art Rechen-Test, die `adr/0002`
unter T-A in CI und Cloud-Sitzung vorsieht, und genau das, was
`ENTSCHEIDUNGEN` §3 mit „ruht mit synthetischen Tests" meint.

Die dritte Schicht dagegen ist nicht „noch nicht portiert", sondern **durch
geltende Regeln ausgeschlossen**. Sie mitzunehmen hieße, `store.py` und
`auth.py` mitzunehmen.

**Wohin.** `architekturplan.md` 3.1 stellt `datasets/<id>` isoliert, und der
Vertrag `datasets-isolated` in `.importlinter` erzwingt das bereits für
`earthx.datasets` (heute ein leeres Paket). `architekturplan.md` 7.2 und
KLAERUNGEN B10 binden die Dekomposition an eine Capability; das Flag `quad_pol`
steht seit M1-04 in `catalog/registry.py:113` und ist für beide Datensätze
`False`. Eine Operator-Registry gibt es noch nicht — sie kommt mit Inkrement 4
(M4). Bis dahin ist der Operator schlicht ein isoliertes Modul mit Tests und
ohne Aufrufer.

Offen ist allein der **Verzeichnisname**: `datasets/<id>` verlangt eine
Datensatz-Kennung, und es gibt keinen Datensatz — es ist nach ENTSCHEIDUNGEN §3
nicht einmal klar, ob es eine token-freie Quelle für komplexe Quad-Pol-Daten
gibt (Sentinel-1 ist Dual-Pol). Ein Verzeichnis `datasets/biomass…` würde
außerdem den Namen BIOMASS in CI-Pfade tragen, was `ENTSCHEIDUNGEN` §3 und
`CLAUDE.md` gerade ausschließen. Siehe §9 Frage 3.

---

## 7. Optionen

### Option A — Alles bleibt, bis die Operator-Registry steht (M4)

Der Prototyp bleibt unverändert liegen, `decomp.py` zieht erst um, wenn es einen
Platz für Operatoren gibt.

*Dafür:* kein Umbau ohne Zielstruktur; `decomp.py` landet genau einmal am
richtigen Ort. *Dagegen:* verlängert alles aus §5 um mindestens einen
Meilenstein — inklusive `pystac_client` im Image und der Ausnahme in
`SECURITY.md`; und die README beschreibt weiter einen Prototyp, der so nicht
mehr startet. M2-12 müsste Abschnitt 3 der README pflegen, statt ihn zu
streichen.

### Option B — Nur `backend/app/` löschen, sonst nichts

Ein Commit, `git rm -r backend/app`, Tests und README nachziehen — `decomp.py`
geht mit, abrufbar bleibt es über den Tag.

*Dafür:* kleinster Diff. *Dagegen:* verletzt K3. `ENTSCHEIDUNGEN` §3 sagt
ausdrücklich „wird als Operator mit entsprechender Capability übernommen" und
„ruht mit synthetischen Tests" — ein Tag ist kein ruhender Operator, und eine
Mathematik, die niemand mehr testet, ist nach einem Jahr eine Mathematik, der
niemand mehr traut.

### Option C — `decomp.py` retten, dann den Rest entfernen *(empfohlen)*

Zwei Commits in einem PR: zuerst zieht der Rechenkern samt Warp-Regel als
ruhender Operator nach `earthx/datasets/<id>/` um und bekommt synthetische
Tests; danach fällt `backend/app/` mit allem aus §4.2.

*Dafür:* erfüllt K1 bis K6; der Diff bleibt lesbar, weil Umzug und Löschung
getrennte Commits sind. *Dagegen:* der Operator hat vorerst keinen Aufrufer und
keinen Datensatz — er ist Code, der nur von Tests berührt wird. Das ist genau
das, was §3 „ruht" nennt, muss aber im Modul-Docstring stehen, damit es nicht
später als toter Code aufgeräumt wird.

### Option D — Wie C, aber in zwei PRs

PR 1: Operator-Umzug mit Tests. PR 2: Entfernen.

*Dafür:* zwei kleine, unabhängig prüfbare Reviews; PR 1 kann grün sein, bevor
über PR 2 entschieden wird. *Dagegen:* zwei Review-Runden für eine Sache, und
zwischen beiden liegt dieselbe Mathematik doppelt im Repo.

---

## 8. Empfehlung

**Option C**, ausgeführt als **ein** Stufe-B-PR mit getrennten Commits, und
zwar **vor M2-12**.

Die Reihenfolge ist der eigentliche Punkt: M2-12 schreibt die README für die
M2-Abnahme neu („README um beide Datensätze, Attribution und Start des Viewers
ergänzt"). Liegt das Entfernen davor, verschwindet Abschnitt 3 einfach; liegt es
danach, schreibt M2-12 einen Abschnitt, der kurz darauf gelöscht wird — und
beschreibt dabei einen Start, der seit M2-07a nicht mehr funktioniert (§5).
M2-08 und M2-10 sind davon unberührt: beide fassen nur `earthx` an.

Begründung gegen die Alternativen in einem Satz: Option A zahlt einen
Meilenstein lang weiter für eine Referenz, die seit M2-07a am Tag hängt und
nicht mehr am Arbeitsbaum; Option B spart zwei Stunden und gibt dafür die
einzige Zusage aus §3 auf, die überhaupt Substanz verlangt; Option D ist
vertretbar, wenn Otto den Umzug getrennt prüfen will, kostet aber eine
Review-Runde mehr.

Der PR bliebe bei geschätzt rund 300 bewegten Zeilen netto (1703 gelöscht,
davon ~130 als Operator wieder eingefügt, dazu ~120 Zeilen neue Tests und die
Dokumentationsschnitte) — innerhalb des Richtwerts, weil Löschungen den Review
kaum belasten.

---

## 9. Fragen an Otto

Sechs Fragen, jede mit Empfehlung. Kurz beantwortbar mit „1a, 2a, 3a, 4a, 5a,
6a" oder den Abweichungen.

**Frage 1 — Wird der Prototyp entfernt, und wann?**

1. **Ja, jetzt, vor M2-12**, in einem eigenen Stufe-B-PR. *(Empfehlung, §8)*
2. Ja, aber erst nach der M2-Abnahme (M2-12).
3. Nein, erst mit M4, wenn die Operator-Registry steht (Option A).

**Frage 2 — Was fällt mit weg?**

1. **Alles aus §4.2:** `backend/app/`, `build_coverage.py`, die beiden
   Prototyp-Testdateien, `environment.yml`, README-Abschnitt 3, die
   `COPY app`-Zeile im Dockerfile, die beiden `pyproject`-Einträge, dazu
   `pystac-client` und das ungenutzte `requests` aus `requirements.txt`.
   *(Empfehlung)*
2. Nur `backend/app/` und was sonst die CI rot machen würde; `environment.yml`,
   README-Abschnitt 3 und die Paketliste bleiben vorerst.

**Frage 3 — Wohin geht `decomp.py`, und wie viel davon?**

1. **Rechenkern und Warp-Regel nach `backend/earthx/datasets/quadpol_slc/`**,
   ohne `decompose_crop` (hängt an `auth` und `store`, beide im Zielpfad
   ausgeschlossen), mit synthetischen T-A-Tests für Pauli und Freeman–Durden.
   Der Verzeichnisname ist ein neutraler Platzhalter nach der Capability, nicht
   nach dem Datensatz — er wird umbenannt, sobald eine echte Quelle eine Kennung
   liefert. *(Empfehlung)*
2. Wie 1, aber das Verzeichnis trägt die Kennung des BIOMASS-Produkts
   (`datasets/biomass_l1a_scs/`). Ehrlicher benannt, trägt aber den Namen
   BIOMASS in CI-Pfade — gegen ENTSCHEIDUNGEN §3 und `CLAUDE.md`.
3. Die ganze Datei 1:1 umziehen, `decompose_crop` eingeschlossen und
   stillgelegt. Zieht `store.py` und `auth.py` faktisch mit — nicht empfohlen.
4. Gar nicht umziehen; bei Bedarf aus dem Tag holen (Option B).

**Frage 4 — Die befristete Secret-Ausnahme endet. Was wird dazu geschrieben?**

Mit `backend/app/config.py` verschwindet das Feld aus dem Arbeitsbaum. `CLAUDE.md`
und `SECURITY.md` sagen beide: „Die Ausnahme endet, wenn der BIOMASS-Code
entfernt wird." Beide Dateien stehen unter „ohne Rückfrage nicht ändern",
deshalb die Frage. An der Festlegung selbst ändert keine Option etwas: die
History bleibt unberührt, der Wert wird nicht widerrufen.

1. **Im selben PR:** eine Zeile im Entscheidungslog, der Abschnitt in
   `SECURITY.md` und der Absatz in `CLAUDE.md` gestrichen — jeweils mit einem
   Satz, dass die Ausnahme mit dem Code endete und History und Wert unangetastet
   bleiben. *(Empfehlung)*
2. Nur die Entscheidungslog-Zeile; die beiden Dateien ändert Otto selbst.

**Frage 5 — F2 und F11 laufen noch nicht token-frei. Blockiert das?**

1. **Nein.** Beide sind durch eigene Entscheidungen verschoben (Ortssuche nach
   M3, M2-Plan §1.2 F1; Mosaik im Kachel-Pfad nach M4, D11), und der Tag bleibt
   die Vorlage. *(Empfehlung)*
2. Ja — erst entfernen, wenn M3 die Ortssuche gebaut hat.

**Frage 6 — Schnitt in PRs.**

1. **Ein PR, zwei Commits** (erst Operator-Umzug, dann Entfernen).
   *(Empfehlung)*
2. Zwei PRs (Option D), falls der Operator-Umzug getrennt geprüft werden soll.

---

## 10. Folgen, wenn wie empfohlen entschieden wird

- Das Repo enthält genau eine Topologie. `README.md` beschreibt nur noch den
  Zielpfad; `architekturplan.md` 13 („Prototyp gesamt … bleibt im Repo, bis …")
  wird zur Historie und bekommt einen Verweis auf diesen ADR.
- Abnahmekriterium 6 des M2-Plans gilt ohne Einschränkung: im Repo gibt es
  keinen ausgehenden Request mehr außerhalb von `gateway`.
- `pystac-client` verlässt Abhängigkeitsliste und Image; die beiden Tests, die
  es als verbotenen Import führen, bleiben als Schutz gegen die Rückkehr.
- Die suite-weite `clean_settings`-Fixture entfällt; kein Test zieht mehr den
  Prototyp mit.
- Der Quad-Pol-Operator liegt isoliert unter `earthx/datasets/` und ruht mit
  synthetischen Tests, bis eine Quelle für komplexe Quad-Pol-Daten gefunden ist.
  Die offene Log-Zeile dazu bleibt offen.
- Die befristete Secret-Ausnahme endet; SECURITY.md und CLAUDE.md verlieren
  ihren Absatz dazu. Git-History und Wert bleiben unverändert, wie festgelegt.
- Verloren geht die Möglichkeit, den Prototyp ohne Tag-Checkout zu starten —
  praktisch nichts, weil ihm seit M2-07a die Oberfläche fehlt (§5).

## 11. Was offen bleibt

1. **Eine token-freie Quelle für komplexe Quad-Pol-Daten.** Steht seit dem
   18.09.2026 als offene Zeile im Entscheidungslog und wird von dieser Vorlage
   nicht beantwortet. Solange sie fehlt, hat der Operator keinen Datensatz, kein
   `quad_pol = True` und keinen Aufrufer.
2. **Der endgültige Ort des Operators.** Mit der Operator-Registry aus M4
   (`architekturplan.md` 7.2) bekommt er Schema, Kostenmodell und
   Ausführungsstufen. Der Umzug jetzt ist die Ablage, nicht die Registrierung.
3. **F2 Ortssuche** bleibt für M3 offen, samt der Frage nach den
   Nutzungsbedingungen von Nominatim (`prototyp-inventar.md` Teil 5, Punkt 4).
4. **`_warp_complex` gegen eine echte Quelle.** Die Annahme über die
   Bandreihenfolge HH/HV/VH/VV ist aus dem Code allein nicht überprüfbar
   (Inventar F17) und bleibt es auch mit synthetischen Tests. Das gehört in die
   Onboarding-Prüfung des ersten Quad-Pol-Datensatzes.
