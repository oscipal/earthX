# ADR 0001 — Zustand im Prototyp und seine Verortung in der Zielarchitektur

- **Status:** Vorschlag, Entscheidung in M1 (`KLAERUNGEN.md` B1).
- **Datum:** 2026-09-18
- **Aufgabe:** M0 Schritt 4 laut `ENTSCHEIDUNGEN_2026-09-18.md` §6.
- **Autonomiestufe:** C — nur gelesen und berichtet, kein Produktivcode geändert.
- **Grundlage:** `docs/prototyp-inventar.md` (F13, F14, F16, F19), Code in
  `backend/app/` und `frontend/src/`, Stand `main` vom 18.09.2026.
- **Betroffen:** `architekturplan.md` 3.2, 6.3, 6.4, 12.3, 13; `KLAERUNGEN.md` B8, B9.

## Methode und Grenzen

Reines Lesen des Codes. Kein MAAP-Zugang, kein Dienst aufgerufen, nichts
ausgeführt und nichts gemessen. Alle Aussagen über Laufzeitverhalten
(Neustart, mehrere Instanzen, Wettläufe) sind aus dem Code abgeleitet, nicht
beobachtet. Wo eine Aussage nur an laufenden Instanzen zu prüfen wäre, steht
das dabei.

---

## 1. Kontext

Der Prototyp läuft als **ein** Uvicorn-Prozess auf **einem** Rechner mit **einem**
Nutzer. Unter dieser Annahme ist sein Zustand unauffällig. Die Zielarchitektur
setzt das Gegenteil voraus:

- `api`, `tiler` und `worker` haben laut `architekturplan.md` 3.2 ausdrücklich
  **keinen Zustand** und skalieren horizontal.
- Der Worker-Kern ist plattformunabhängig und zustandslos, ohne Datenbank,
  Queue, Objektspeicher oder interne API (`KLAERUNGEN.md` B9).
- Zwischenspeicherung gehört in die vier Ebenen aus `architekturplan.md` 12.3
  (HTTP/CDN, Anwendung, Ergebnis, Pipeline).

Zwischen beidem liegt kein gradueller Unterschied, sondern eine Eigenschaft, die
der Prototyp heute verletzt: **Eine Antwort hängt davon ab, welche Instanz sie
beantwortet und was diese Instanz vorher gesehen hat.** Dieses ADR benennt jeden
Zustand einzeln, sagt, was bei Neustart und bei mehreren Instanzen bricht, und
schlägt eine Zielverortung vor.

---

## 2. Bestandsaufnahme Backend

Kurzübersicht; die Einzelheiten stehen in Abschnitt 3.

| # | Zustand | Ort | Lebensdauer | schreibt | liest | Zielort |
|---|---|---|---|---|---|---|
| Z1 | Item-Registry | `store.py::_registry` + `cache/registry.json` | Prozess, auf Platte gespiegelt | `/search` | `/tiles`, `/download`, `/stitch`, `/decompose`, `/asset` | **Katalog (pgstac)** |
| Z2 | Zuschnitt-Cache (Dateien) | `cache/<item>__<aoi>__<asset>.tif` | bis LRU-Verdrängung | `/download`, `/stitch`, `/decompose` | `/tiles`, alle Schreibpfade | **Objektspeicher mit Ablauf** |
| Z3 | LRU-Index | `cache/cache_index.json` | wie Z2 | jeder `touch()` | `evict_if_needed()` | entfällt (Ablauf im Objektspeicher) |
| Z4 | Streckbereichs-Cache | `cog.py::_RESCALE_CACHE` (Prozess) | Prozesslaufzeit, unbegrenzt | `render_tile` | `render_tile` | **Cache mit Ablauf** + Teil der Kachel-URL |
| Z5 | Token-Cache | `auth.py`, drei Modulvariablen | bis Ablauf des Access-Tokens | `get_access_token` | dieselbe Funktion | **entfällt ersatzlos** |
| Z6 | Coverage-Datei | `data/coverage/<collection>.geojson` | unbegrenzt, nur `?refresh=true` | `/coverage`, `build_coverage.py` | `/coverage` | **pgstac-Aggregat + Cache mit Ablauf** |
| Z7 | Settings-Singleton | `config.py::get_settings` (`lru_cache`) | Prozesslaufzeit | Import | überall | Konfiguration, unkritisch |
| Z8 | GDAL/VSI-Cache | Prozessspeicher, 64 MiB je Env | Requestdauer | GDAL | GDAL | bleibt (reiner Lesecache) |
| Z9 | AOI-Hash als Schlüssel | kein Speicher, aber Namensvertrag | — | Server | Kachel-URL im Client | **Rezept-/Such-ID** |

Nicht als Zustand gezählt, aber erwähnenswert: `data/` wird beim Start über
`get_settings()` angelegt (Seiteneffekt eines Konfigurationszugriffs), und
`cache_dir`/`data_dir` sind relative Pfade — der Zustand hängt damit zusätzlich
am Arbeitsverzeichnis des Prozesses.

---

## 3. Die Zustände im Einzelnen

### Z1 — Item-Registry

**Was.** Ein Modul-Dictionary `_registry: item_id → {collection, datetime, bbox,
assets, quicklook_key, cog_key, rescale}`, geschützt durch ein `threading.RLock`,
bei jeder Änderung vollständig nach `cache/registry.json` geschrieben.

**Wer schreibt.** Ausschließlich `routes/search.py`: jede Suche registriert jedes
Ergebnis-Item.

**Wer liest.** `cog.py::_resolve_cog_key` und `store.asset_href`, also mittelbar
`/tiles`, `/download`, `/stitch`, `/decompose` und `/asset`. Diese Endpunkte
bekommen nur eine `item_id` und **können ohne die Registry nichts tun**
(`"Item '<id>' is unknown — run a search first."`).

**Lebensdauer.** Unbegrenzt: Es gibt kein Ablaufdatum, keine Obergrenze und kein
Löschen. Die Datei wächst mit jeder je gesuchten Szene.

**Was bricht.**

- *Neustart:* überlebt grundsätzlich, weil gespiegelt. Aber: `_persist_registry`
  schreibt **nicht atomar** (kein Schreiben in eine Temporärdatei mit
  anschließendem Umbenennen). Ein Abbruch mitten im Schreiben hinterlässt eine
  unvollständige JSON-Datei; `_ensure_loaded` fängt `json.JSONDecodeError` ab und
  startet **still** mit leerem Zustand. Der Nutzer sieht dann für jede vorher
  funktionierende Kachel-URL einen 404 „unknown item“, ohne Hinweis auf die
  Ursache.
- *Mehrere Instanzen:* bricht sofort. Die Suche landet auf Instanz A, die
  Kachelanfrage auf Instanz B → 404. Zeigen beide auf dasselbe Verzeichnis,
  überschreiben sie die Datei gegenseitig vollständig (Lost Update), weil jede
  ihr eigenes `_registry` als Ganzes schreibt. Das `RLock` schützt nur innerhalb
  eines Prozesses.
- *Mehrere Nutzer:* Ein globaler Namensraum ohne Mandantentrennung. Nutzer B
  kann jedes Item abrufen, das Nutzer A je gesucht hat — einschließlich der
  Asset-URLs. Beim Prototyp mit einem Nutzer folgenlos, bei einer öffentlichen
  Plattform nicht.

**Bewertung.** Das ist der schwerwiegendste Befund: kein Beschleuniger, sondern
**verdeckter Sitzungszustand, von dem die Funktion abhängt**. Der Sache nach ist
die Registry ein Miniaturkatalog — genau die Aufgabe, die in der Zielarchitektur
pgstac hat.

**Zielort.** **pgstac.** Die Auflösung `item_id → Asset-Adresse` ist eine
Katalogabfrage, keine Sitzungserinnerung. Damit wird jeder Endpunkt unabhängig
davon, ob vorher gesucht wurde, und Kachel-URLs bleiben über Instanzen und
Neustarts hinweg gültig. Für Items, die nicht im eigenen Katalog stehen
(föderierte Suche), bleibt eine Anwendungs-Cache-Ebene mit Ablauf (Redis) nach
`architekturplan.md` 12.3, Zeile „föderierte Item-Suchen“.

### Z2 — Zuschnitt-Cache auf der Platte

**Was.** Ergebnisdateien `<item>__<aoi-hash>__<asset>.tif` im `cache_dir`:
AOI-Zuschnitte (`crop_to_aoi`), Mosaike unter synthetischer ID
`stitch_<md5>` und Dekompositionen unter dem Asset-Schlüssel `decomp_<methode>`.
Obergrenze 5 GiB, LRU-Verdrängung.

**Wer schreibt.** `/download`, `/stitch`, `/decompose`.
**Wer liest.** `/tiles` über `_resolve_source`, das einen vorhandenen Zuschnitt
dem entfernten Original vorzieht.

**Lebensdauer.** Bis die Summe aller `*.tif` die Obergrenze übersteigt und die
Datei die älteste ist — also unbestimmt und von fremdem Verhalten abhängig.

**Was bricht.**

- *Neustart:* Dateien überleben; der Zustand ist an den Rechner gebunden, nicht
  an den Prozess. In einem Container ohne Volume ist nach dem Neustart alles weg,
  und alle vom Client gemerkten Kachel-URLs zeigen ins Leere.
- *Mehrere Instanzen:* Ohne gemeinsames Verzeichnis trifft dieselbe Kachel-URL
  mal einen Zuschnitt und mal das entfernte Original — unterschiedliche Bilder
  (andere Auflösung, anderer automatischer Streckbereich) unter derselben URL.
  Mit gemeinsamem Verzeichnis (NFS o. ä.) kommen Wettläufe hinzu: `cog_translate`
  schreibt direkt an den Zielpfad; ein zweiter Request, der die Datei zwischen
  Anlegen und Fertigstellung öffnet, liest einen unvollständigen COG. Es gibt
  keine Sperre und kein „erst temporär, dann umbenennen“.
- *Verdrängung aus dem Request heraus:* `evict_if_needed()` statet bei **jedem**
  Schreibvorgang alle Dateien im Verzeichnis und löscht fremde Ergebnisse
  synchron im Request. Zwei gleichzeitige Downloads können sich gegenseitig die
  gerade erzeugten Zuschnitte löschen. Die Größenrechnung zählt nur `*.tif`;
  Ergebnisse in einem anderen Format (Zarr, NetCDF) blieben unsichtbar und die
  Obergrenze damit wirkungslos.
- *Dauerhaftigkeit:* Der Client hält in `downloaded[]` Kachel-URLs zu Dateien,
  die der Server jederzeit verdrängen darf. Danach liefert `/tiles` 404 bzw. bei
  `decomp_*` „hasn't been computed yet“, obwohl die Oberfläche das Bild weiter
  anzeigt.

**Zielort.** **Objektspeicher mit Ablaufdatum**, adressiert über den Rezept-Hash
(`architekturplan.md` 12.3 „Ergebnis“, 6.4). Der Ablauf ist dann eine Eigenschaft
des Speichers, keine Aufgabe des Request-Pfads; Instanzen brauchen kein
gemeinsames Dateisystem. Das Konzept „Ergebnis wird zwischengehalten und
wiederverwendet“ bleibt erhalten — genau so steht es jetzt auch in
`ENTSCHEIDUNGEN` §2 („nur als Konzept; die Umsetzung wird ersetzt“).

### Z3 — LRU-Index

**Was.** `cache/cache_index.json`, Abbildung Dateiname → Zeitpunkt des letzten
Zugriffs.

**Was bricht.** `touch()` liest und schreibt bei **jedem** Aufruf die ganze Datei
— auch bei jeder einzelnen Kachelanfrage aus dem Cache, also im heißesten Pfad
des Systems. Zwei Prozesse überschreiben einander (Lost Update), das Schreiben
ist wieder nicht atomar, und ein beschädigter Index wird still als leer gelesen:
Dann gelten alle Dateien als „sehr alt“ und die nächste Verdrängung löscht
praktisch den ganzen Cache. Für die Zugriffszeit existiert mit `st_atime` bereits
eine Angabe im Dateisystem; der eigene Index ist auch fachlich verzichtbar.

**Zielort.** **Entfällt.** Ablaufregeln des Objektspeichers ersetzen ihn.

### Z4 — Streckbereichs-Cache

**Was.** `cog.py::_RESCALE_CACHE: dict[str, list[list[float]]]`, Schlüssel
`"<item_id>|<expression oder idx:1,2,4>"`. Ein Modul-Dictionary **ohne Sperre**
und **ohne Obergrenze**. Dazu `store.set_item_rescale` und das Feld `rescale` in
der Registry — im gelesenen Code nirgends aufgerufen, also toter Pfad.

**Zweck.** Nicht Geschwindigkeit, sondern **Nahtfreiheit**: Alle Kacheln einer
Ansicht müssen denselben 2–98-%-Streckbereich benutzen, sonst entstehen sichtbare
Kanten zwischen den Kacheln. Das ist eine fachliche Anforderung und bleibt gültig.

**Was bricht.**

- *Neustart:* Der Cache ist weg; die erste Kachel danach berechnet die Statistik
  neu. Sie kann anders ausfallen, wenn die Quelldatei ein anderer Zuschnitt ist
  (Z2 verdrängt) — dieselbe URL liefert dann ein anders gestrecktes Bild.
- *Mehrere Instanzen:* Genau das passiert dauerhaft und gleichzeitig. Die Kacheln
  einer einzigen Ansicht werden von verschiedenen Instanzen mit verschiedenen
  Streckbereichen gerendert — die Nähte, die der Cache verhindern soll, kommen
  zurück, und ein zwischengeschaltetes CDN friert die Mischung ein.
- *Speicher:* unbegrenztes Wachstum, ein Eintrag je Item und Bandauswahl, ohne
  Ablauf. Auf einem lange laufenden Dienst ein Leck.
- *Nebenläufigkeit:* Schreiben ohne Sperre ist bei CPython auf Dictionary-Ebene
  zwar unkritisch, doppelte Berechnung durch parallele Kachelanfragen ist aber
  der Normalfall und rechnet unnötig.

**Zielort.** **Zweigeteilt.** Der Zweck gehört in die URL, der Wert in einen
Cache mit Ablauf:

1. Der wirksame Streckbereich wird **Teil der Kachel-URL** (bzw. der Rezept-ID),
   damit die Antwort vollständig durch die URL bestimmt und CDN-fähig ist. Der
   Client tut das heute schon für den ausdrücklich gesetzten Fall
   (`buildTileUrl`, F18) — „auto“ ist die einzige Lücke.
2. Die Statistik selbst (Perzentile je Item und Bandauswahl) ist eine
   COG-Header-nahe Information und gehört in die Anwendungs-Cache-Ebene
   (`architekturplan.md` 12.3, „Header-Infos von COGs“) mit Ablaufdatum.

Praktisch heißt das: Der Client fragt einmal eine Statistik ab, setzt das
Ergebnis in die Kachelvorlage und hält den Wert für die Dauer der Ansicht fest.
Damit ist Nahtfreiheit garantiert statt zufällig.

### Z5 — Token-Cache

**Was.** `auth.py` hält Access-Token, Ablaufzeitpunkt und Quell-Token in drei
Modulvariablen unter einem `threading.Lock`, erneuert 30 s vor Ablauf.

**Was bricht.** Pro Instanz ein eigener Austausch am OIDC-Endpunkt; bei n
Instanzen n-facher Token-Austausch und n-fache Ratenlast beim Identitätsanbieter.
Ein Neustart erzwingt einen neuen Austausch. Für den Prototyp folgenlos.

**Zielort.** **Ersatzlos.** `ENTSCHEIDUNGEN` §1 und §3: kein Token in der
Zielarchitektur, `auth.py` wird nicht übernommen und nicht generalisiert. Dieser
Zustand erledigt sich mit dem Modul und braucht keine Entscheidung.

### Z6 — Coverage-Datei

**Was.** `data/coverage/<collection>.geojson`, geschrieben entweder vom
Endpunkt selbst (Footprints, Obergrenze 1500, ~20 s) oder vorab vom Skript
`build_coverage.py` (Dichtegitter aus einer Stichprobe, Vorgabe 5000 Aufnahmen,
1°-Zellen). Beide Wege schreiben **denselben Pfad** in unterschiedlichem Format.

**Lebensdauer.** Unbegrenzt. Es gibt kein Ablaufdatum und keinen Stand-Vermerk;
nur `?refresh=true` baut neu — ein schreibender Seiteneffekt hinter einem
GET-Request, den jeder auslösen kann (~20 s Rechenzeit pro Aufruf, keine
Begrenzung).

**Was bricht.** Neustart unkritisch (Datei überlebt), Container ohne Volume
kritisch (erster Aufruf danach 20 s). Bei mehreren Instanzen: jede baut ihre
eigene Datei, oder sie überschreiben sich auf gemeinsamem Speicher, wieder nicht
atomar. Inhaltlich gravierender: Der ausgelieferte Inhalt hängt davon ab, welcher
Weg zuletzt geschrieben hat — Footprints oder Dichtegitter, und das Frontend
stylt nur das Dichtegitter korrekt (Inventar F12/N3).

**Zielort.** **pgstac-Aggregat** nach dem neuen §2 (Heatmap der
Abdeckungsdichte, reagiert auf Filter), Antwort in einem **Cache mit Ablauf**
bzw. über HTTP/CDN. Kein Schreiben aus einem GET-Request. Wie die Aggregation
technisch umgesetzt wird, klärt laut §2 ein eigenes ADR mit Recherche — hier ist
nur festzuhalten: **Die Datei im Dateisystem ist kein tragfähiger Ort.**

### Z7 / Z8 — Settings-Singleton und GDAL-Cache

`get_settings()` ist über `lru_cache` ein Prozess-Singleton und legt beim ersten
Aufruf Verzeichnisse an. Das ist Konfiguration, kein fachlicher Zustand; kritisch
ist nur der Seiteneffekt und die Bindung an relative Pfade. Der VSI-Cache (64 MiB
je `rasterio.Env`) ist ein reiner Lesecache über unveränderliche Fernobjekte: er
darf bleiben, gehört in der Zielarchitektur aber zur zentralen GDAL-Konfiguration
im `gateway` (`KLAERUNGEN.md` B8) statt in `cog.py`.

### Z9 — Der AOI-Hash als Sitzungsschlüssel

Kein Speicher, aber ein Vertrag: Die ersten 12 Zeichen eines SHA-1 über die
kanonisierte AOI-Geometrie verbinden Zuschnitt-Dateinamen (Z2) und Kachel-URLs.
Er wird serverseitig aus der übergebenen Geometrie berechnet; der Client
übernimmt ihn nur. Drei Eigenschaften sind für die Zielarchitektur wichtig:

- Der Hash beschreibt **nur die AOI**, nicht die übrigen Parameter (Bandauswahl,
  Größenbegrenzung, Methode). Zwei verschiedene Rechenwege unter derselben AOI
  landen nur deshalb nicht im selben Eintrag, weil zusätzlich der Asset-Schlüssel
  im Dateinamen steht. Das ist knapp, aber tragfähig — bei mehr Parametern nicht
  mehr.
- Er hängt an der exakten JSON-Darstellung der Geometrie. Eine anders gerundete,
  sachlich identische AOI ergibt einen anderen Hash und damit doppelte Arbeit.
- 12 Hex-Zeichen sind gegen zufällige Kollisionen ausreichend, gegen absichtliche
  nicht; SHA-1 ist dafür ohnehin ungeeignet. Solange der Hash nur ein
  Cache-Schlüssel ohne Zugriffsentscheidung ist, ist das folgenlos — als Adresse
  im Objektspeicher wäre es zu prüfen.

**Zielort.** Aufgehen in der **Rezept-/Such-ID** der Zielarchitektur
(`architekturplan.md` 6.3, 12.3): ein Hash über *alle* Eingaben eines Ergebnisses,
nicht nur über die Geometrie.

---

## 4. Zustand im Frontend, auf den sich das Backend verlässt

Das Backend hält bewusst keinen Sitzungsbegriff. Vier Dinge trägt deshalb der
Client — er ist heute faktisch die Sitzung.

| # | Zustand | Ort | Worauf sich das Backend verlässt | Was bricht |
|---|---|---|---|---|
| FZ1 | Suchhistorie | implizit: „es wurde vorher gesucht“ | dass Z1 gefüllt ist, bevor `/tiles`, `/download`, `/asset` kommen | Neuladen nach Backend-Neustart mit leerer Registry → 404 „unknown item“ |
| FZ2 | `aoi` + `aoiHash` | `store.ts` | dass der Client für `/download` **dieselbe** Geometrie erneut sendet, damit der Hash zum bereits erzeugten Zuschnitt passt | abweichende Zahlendarstellung → anderer Hash → Zuschnitt wird doppelt gerechnet |
| FZ3 | `downloaded{ tileUrl, aoiHash, bounds, asset }` | `store.ts` | dass die Datei zu dieser URL noch existiert | LRU-Verdrängung (Z2) → 404 bei weiterem Zoomen, ohne Rückmeldung |
| FZ4 | `appliedRender`, `polBand`, `vmin/vmax` | `store.ts`, in die Kachel-URL gebacken | nichts — alle Renderparameter stehen in der URL | nichts; **das ist das Vorbild** (F18) |
| FZ5 | Layer-Manager mit `restore`-Block | `layers.ts` | nichts | nur Browserspeicher: nach Neuladen weg (F19) |
| FZ6 | `qlDataUrlCache`, `coverageFC` | Modul-`Map` bzw. Store | nichts | reine Anzeigebeschleuniger, unkritisch |
| FZ7 | Polarisation → Bandindex (`products.ts`) | Client | das Backend nimmt `indexes`/`expression` ungeprüft entgegen | Datensatzwissen liegt auf der falschen Seite; gehört in die Registry (B13) |

Die entscheidende Zeile ist FZ1: **Der Client hält die einzige Kopie der
Sitzungsannahme, und das Backend hat keine Möglichkeit, sie wiederherzustellen.**
Genau diese Kopplung fällt weg, sobald Z1 durch den Katalog ersetzt ist. FZ4
zeigt zugleich, wie es richtig geht: Steht alles in der URL, ist der Dienst
zustandslos und die Antwort cachefähig.

---

## 5. Optionen

### Option A — Bestand härten, Zustand bleibt lokal

Atomares Schreiben (Temporärdatei + `os.replace`), Dateisperren, Obergrenze für
`_RESCALE_CACHE`, Verdrängung aus dem Request-Pfad heraus in eine Hintergrund­aufgabe.

*Dafür:* geringster Aufwand, keine neue Infrastruktur, Prototyp bleibt sofort
lauffähig.
*Dagegen:* löst keinen der Mehrinstanz-Befunde. Registry, Zuschnitt-Cache und
Streckbereiche bleiben instanzgebunden; `architekturplan.md` 3.2 und
`KLAERUNGEN.md` B9 bleiben verletzt. Härtet den Weg fest, der ohnehin verlassen
wird.

### Option B — Eine Instanz festschreiben (Sticky Sessions / Einzelprozess)

Der Zustand bleibt, wird aber per Lastverteilung an einen Prozess gebunden.

*Dafür:* funktioniert kurzfristig ohne Codeänderung.
*Dagegen:* widerspricht dem Grundprinzip Skalierbarkeit direkt
(`projektuebersicht.md` 2.16), verhindert serverlose Tiler, macht jeden Neustart
zum Datenverlust und ist bei mehreren Nutzern ein gemeinsamer Namensraum ohne
Trennung. Keine Zielarchitektur, nur ein Aufschub.

### Option C — Zustandslose Dienste, Zustand in benannte Ebenen (empfohlen)

Jeder Zustand bekommt den Ort, den `architekturplan.md` 12.3 dafür vorsieht:
Katalog (pgstac) für die Auflösung `item_id → Adresse`, Anwendungs-Cache mit
Ablauf für Statistiken und föderierte Suchen, Objektspeicher mit Ablauf für
Ergebnisse, HTTP/CDN für Kacheln, Client für Ansichtszustand. Kein Dienst hält
etwas, dessen Verlust eine Funktion kaputt macht.

*Dafür:* erfüllt 3.2, B9 und 12.3; Kachel-URLs werden stabil, cachefähig und
instanzunabhängig; Neustart wird folgenlos; Mandantentrennung wird möglich.
*Dagegen:* braucht Postgres/pgstac, einen Anwendungs-Cache und einen
Objektspeicher — in M1 noch nicht vorhanden. Höchster Umbauaufwand.

### Option D — Vollständig zustandslos, alles in der URL

Wie C, aber ohne eigenen Ergebnisspeicher: Jede Kachel wird direkt aus der
Quelle gerechnet, sämtliche Parameter stehen in der URL, zwischengespeichert wird
nur per HTTP/CDN.

*Dafür:* die einfachste denkbare Betriebsform, keine eigene Zustandshaltung.
*Dagegen:* teure Wiederholungsarbeit (AOI-Zuschnitt, Mosaik und Dekomposition
sind Sekunden bis Minuten, nicht Millisekunden), und lange Rechnungen passen
nicht in eine Kachelanfrage. Als Ziel für den reinen Anzeigepfad (T1) richtig,
für Rechenaufträge (T2) nicht — `architekturplan.md` 7.3 trennt das ausdrücklich.

---

## 6. Kriterien

| # | Kriterium | Gewicht | Begründung |
|---|---|---|---|
| K1 | Konformität mit 3.2 / B9 (kein Zustand in `api`, `tiler`, `worker`) | hoch | unverrückbar laut `CLAUDE.md` |
| K2 | Gleiches Bild unter gleicher URL, unabhängig von Instanz und Zeit | hoch | Voraussetzung für CDN und für nahtlose Kacheln |
| K3 | Neustart ohne Funktionsverlust | hoch | Cloud-Betrieb, Container ohne Volume |
| K4 | Mandantentrennung möglich | hoch | öffentliches Deployment, mehrere Nutzer |
| K5 | Kosten vermiedener Wiederholungsarbeit | mittel | Zuschnitt und Dekomposition sind teuer |
| K6 | Betriebsaufwand (Dienste, die laufen müssen) | mittel | Einmann-Projekt |
| K7 | Migrationsaufwand aus dem Bestand | mittel | M1 soll liefern, nicht nur umbauen |
| K8 | Testbarkeit ohne Plattformdienste | mittel | Worker-Kern muss lokal laufen (B9) |

| Kriterium | A | B | C | D |
|---|---|---|---|---|
| K1 Konformität | − | −− | ++ | ++ |
| K2 URL-Determinismus | − | − | ++ | ++ |
| K3 Neustart | ○ | − | ++ | ++ |
| K4 Mandanten | − | − | + | + |
| K5 Wiederholungsarbeit | + | + | ++ | −− |
| K6 Betriebsaufwand | ++ | ++ | − | + |
| K7 Migration | ++ | ++ | − | ○ |
| K8 Testbarkeit | ○ | ○ | + | ++ |

---

## 7. Empfehlung

**Option C**, mit den Elementen aus D dort, wo sie billig sind (alles, was die
Anzeige bestimmt, gehört in die URL). Konkret je Zustand:

| Zustand | Empfehlung |
|---|---|
| Z1 Item-Registry | nach **pgstac**; föderierte Treffer in den Anwendungs-Cache mit Ablauf. Kein Endpunkt setzt eine vorherige Suche voraus |
| Z2 Zuschnitt-Cache | **Objektspeicher mit Ablauf**, adressiert über den Rezept-Hash; kein gemeinsames Dateisystem, kein Verdrängen im Request |
| Z3 LRU-Index | **entfällt** |
| Z4 Streckbereich | Wert **in die Kachel-URL**; Statistik in den Anwendungs-Cache mit Ablauf. Nahtfreiheit wird damit garantiert statt zufällig |
| Z5 Token-Cache | **entfällt ersatzlos** mit `auth.py` |
| Z6 Coverage | **pgstac-Aggregat** + Cache mit Ablauf; kein Schreiben aus einem GET; Stand und Vollständigkeit sichtbar ausweisen |
| Z7 Settings | bleibt; absolute Pfade, Verzeichnisanlage aus der Konfiguration herauslösen |
| Z8 GDAL/VSI | bleibt, Konfiguration zentral in `gateway` (B8) |
| Z9 AOI-Hash | aufgehen in der **Rezept-/Such-ID** über alle Eingaben |
| FZ1 Suchannahme | entfällt mit Z1 |
| FZ3 `downloaded` | Ergebnis bekommt eine Adresse mit bekanntem Ablauf; der Client zeigt den Ablauf an, statt auf eine Datei zu hoffen |
| FZ5 Layer-Manager | Ansichtszustand darf im Client bleiben; was eine Sitzung überdauern soll, wird ein Objekt mit Adresse |
| FZ7 Bandzuordnung | in die Datensatz-Registry (B13), nicht in den Client |

**Reihenfolge des Umbaus.** Nicht alles auf einmal; die Abhängigkeiten geben eine
Reihenfolge vor:

1. **Z4 in die URL** — kleinster Schritt, keine neue Infrastruktur, behebt sofort
   Nähte und Speicherleck.
2. **Z1 in den Katalog** — löst die schwerste Kopplung und FZ1 mit.
3. **Z2/Z3 in den Objektspeicher** — erst danach sinnvoll, weil Ergebnisse dann
   über die Rezept-ID adressiert werden.
4. **Z6** — zusammen mit dem eigenen Coverage-ADR nach §2.
5. **Z5** — fällt ohne eigenen Schritt mit dem BIOMASS-Code weg.

**Zwischenzustand in M1.** Solange pgstac und Objektspeicher fehlen, ist ein
lokaler Zwischenspeicher hinter einer Schnittstelle zulässig, **wenn** keine
Funktion von seinem Inhalt abhängt: Ein Fehlschlag darf nur langsamer machen,
nie einen 404 erzeugen. Das ist die Trennlinie, an der der heutige Code scheitert
— und der Prüfpunkt für jeden Ersatz.

---

## 8. Folgen

- `store.py` wird nicht portiert, sondern ersetzt (bestätigt
  `architekturplan.md` 13, „Kandidat für Ersatz“).
- Der Prototyp bleibt unverändert lauffähig; dieses ADR ändert keinen Code.
- Für M1 ergeben sich Tests, die es heute nicht gibt: dieselbe Kachel-URL liefert
  gegen zwei Instanzen dasselbe Bild; ein Neustart zwischen Suche und Kachel
  ändert nichts; ein geleerter Zwischenspeicher macht Antworten langsamer, nicht
  fehlerhaft.
- `architekturplan.md` 12.3 bleibt unverändert gültig; dieses ADR ordnet den
  Bestand nur ein.

---

## 9. Offene Punkte (nicht in `docs/` entschieden, hier nur benannt)

1. **Anwendungs-Cache: Redis oder Postgres?** `architekturplan.md` 12.3 nennt
   beides. (a) *Empfehlung:* zunächst Postgres, weil es für pgstac ohnehin läuft
   — ein Dienst weniger; (b) Redis von Anfang an, wenn Kachel-Statistiken zur
   Lastspitze werden.
2. **Ablauffrist für Ergebnisse im Objektspeicher.** (a) *Empfehlung:* 7 Tage,
   sichtbar in der Oberfläche; (b) 24 Stunden; (c) an die Sitzung gebunden.
3. **Zwischenzustand in M1:** lokaler Zwischenspeicher hinter einer Schnittstelle
   oder von Anfang an ohne? (a) *Empfehlung:* hinter einer Schnittstelle und mit
   der Regel aus Abschnitt 7 (Fehlschlag macht nur langsamer); (b) bis zum
   Objektspeicher ganz ohne Zwischenspeicher, dafür langsamer.
4. **Mandantentrennung:** Ab wann brauchen Ergebnisse und Registry einen Bezug
   zum Nutzer? Hängt an der offenen Frage Registrierungspflicht (Projektplan 10)
   und ist hier nicht zu entscheiden.
