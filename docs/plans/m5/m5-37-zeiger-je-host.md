# M5-37 — Zeiger und Unterbrecher je Host in Postgres: Plan-Schritt

**Status (16.11.2026):** Plan angenommen (Otto, 16.11.2026: J1–J6 je 1, dazu zwei Vorgaben, §9a), **Stufe B**. PR 1 in [#368](https://github.com/oscipal/earthX/pull/368) (Mechanismus und `materialize`), PR 2 folgt (Pyramidenbau).
**Aufgabe:** M5-37 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.2, Auftrag von Otto vom 16.11.2026.
**Grundlagen:** `plans/m5/m5-35-skalierbarkeit.md` B1 (§2.3 G2, §2.4 Punkte 2 und 4), F1 = 1, W6, W7; `plans/m5/m5-36-grenzen-je-host.md` (`hosts.yaml`, `ReadSlots`, `EARTHX_SOURCE_INSTANCES`, §9); Muster des Zeigers der Ortssuche (`catalog/geocode_cache.py`, `earthx_rate_slots`, Migration 005); `adr/0025` §6.2; `adr/0032` §8.2 und Nachträge 14. und 15.11.2026 (0,25 s je Host im Pyramidenbau); `architekturplan.md` 3.1, 6.5; KLAERUNGEN B8, B9.

Belegstufen wie in `adr/0025`: **P** am Quelltext gelesen (Stand `main` eb7079c), **S** Sekundärquelle, **A** eigene Ableitung. Gemessen wird erst in der Umsetzung, nur gegen die synthetische Quelle (§7); keine echte Quelle aus der Sitzung.

---

## 1. Ziel

Nach M5-36 hält jede Instanz von `api` und `tiler` ihren Anteil an der Grenze eines Hosts. Für die **seltenen, langen Zugriffe** gilt das noch nicht (M5-35 §2.4 Punkt 2): `materialize`, später der Harvester, und der Pyramidenbau halten Verbindungen und Abstand je Lauf bzw. je Bau im Speicher. Zwei Läufe gegen die FSDI fragen zusammen jede halbe Sekunde, nicht jede Sekunde (M5-35 §2.2), und antwortet ein Host mit `503`, wiederholt jede Instanz für sich (W6).

M5-37 soll:

1. **Abstand je Host über alle Instanzen:** ein Zeiger je Host in Postgres, wie die Ortssuche ihn für Nominatim hält (`earthx_rate_slots`, eine Anweisung `INSERT … ON CONFLICT … RETURNING` je Anfrage, keine gehaltene Verbindung, Warten im Aufrufer).
2. **Verbindungen je Host über alle Instanzen** für dieselben drei Aufrufer (J1, J2).
3. **Unterbrecher je Host:** nach wiederholten Fehlern ruht der Host für alle drei Aufrufer und alle Instanzen eine Zeit lang; er schiebt dafür denselben Zeiger vor (M5-35 §2.4 Punkt 4, wie `push_back` der Ortssuche).
4. Beides in Postgres, ohne neuen Dienst; der Kern bleibt ohne Datenbank (B9), `gateway` ohne Datenbank und ohne Datensätze.

**Nicht Teil von M5-37:**
- **Kacheln und Suche** (`api`, `tiler`) bleiben wie in M5-36: Teilbudget je Instanz, kein Abstand, kein Datenbank-Umlauf je Anfrage, kein Unterbrecher (Auftrag). Exakt über alle Instanzen erst mit dem Egress-Proxy in M6.
- **Rezept-Läufe im Worker** (GDAL im Kind eines Laufs): weiter über `host_cap` = 2 Läufe je Host (M6, F6).
- **Bündeln gleicher Anfragen über Instanzen** (zweite Hälfte von W6): im Auftrag nicht genannt; für die drei Aufrufer ohne Nutzen, weil kein zweiter Lauf dieselbe Seite zur selben Zeit braucht [A]. Bleibt offen für M6.
- **Der Harvester selbst** (W7): Er ist noch leer (`discovery/main.py`). M5-37 liefert die Fabrik, über die er sein `Gateway` bekommt (§5.3); die Sperre je Quelle (Lauf-Zeile mit Frist) kommt mit M5-19/M5-24.

---

## 2. Ausgangslage im Code [P]

| Aufrufer | Wie er liest | Grenze heute | Abstand heute | Wiederholen heute |
|---|---|---|---|---|
| `materialize` (`discovery/materialize.py`) | ein `Gateway` je Lauf (`_main_async`), `httpx`; Seiten nacheinander, kein `gather` in den Adaptern | `hosts.yaml` je Lauf (`_policy_for`) | `hosts.yaml` je Lauf: FSDI und BEV 1 s, Buckets keiner; `Gateway._space` im Speicher | `MAX_ATTEMPTS` 3 je Anfrage mit Backoff, `Retry-After` bis 10 s |
| Harvester (`discovery/main.py`) | noch nichts | — | — | — |
| Pyramidenbau (`processing/overview.py`, `overview_build.py`) | GDAL im Kind (`jobs/overview_child.py`), **ein Faden**, Datei nach Datei | keine eigene; höchstens ein Bau je Host im Cluster (`earthx_overview`, `earthx_overview_host`) | `HostPacer` im Kind: 0,25 s je Anfrage (`EARTHX_OVERVIEW_HOST_INTERVAL_S`); `wait` vor, `account(host, requests)` nach jeder Datei | bis 4 Lesungen je Datei (5 s, 20 s, 60 s, `Retry-After` bis 120 s); Bau nach `source_*` bis 3-mal nach 1 h |

- **Das Muster der Ortssuche** (`catalog/geocode_cache.py:41–56`, `:81–106`): Zeile je Upstream mit `next_slot`; `reserve` schiebt ihn um 1 s vor und gibt die Wartezeit zurück, gemessen an `clock_timestamp()` derselben Anweisung; `push_back` schiebt ihn nach einem `429` weiter. Kein Halten einer Verbindung, keine Sperre über die Anweisung hinaus.
- **Importregeln** (`.importlinter`): `gateway` darf nichts Fachliches, `catalog` nur `gateway`, `discovery` `adapters`, `catalog`, `gateway`; **`jobs` weder `gateway` noch `catalog`**; `processing` kein `psycopg` (auch nicht über Ketten). Daraus folgt der Schnitt in §5.
- **Das Kind des Pyramidenbaus kennt keine Datenbank** (`jobs/overview_child.py`, Kopf): Es spricht über eine Pipe mit dem Aufseher (`jobs/overview_builder.py:_step`, `:_watch`), die schon heute **in beide Richtungen** offen ist (`Pipe(duplex=True)`), bisher aber nur vom Kind zum Aufseher genutzt wird.
- **`materialize` hält eine Transaktion über den ganzen Lauf** (`_main_async`, `psycopg.connect(autocommit=False)`). Eine Zeile, die andere Instanzen sehen sollen, darf nicht in dieser Transaktion liegen: sie würde erst beim Commit sichtbar und hielte bis dahin die Zeilensperre.

---

## 3. Zustand in Postgres

### 3.1 Tabellen (Migration 022)

```sql
-- Eine Zeile je Host: Zeiger und Unterbrecher (M5-37). Kein Name eines Datensatzes, keine Adresse, nur der Host.
CREATE TABLE public.earthx_source_host (
    host          text PRIMARY KEY,
    next_start    timestamptz NOT NULL,           -- frühester Beginn der nächsten Anfrage
    failures      integer     NOT NULL DEFAULT 0, -- Fehler in Folge, über alle Aufrufer
    pauses        integer     NOT NULL DEFAULT 0, -- Pausen in Folge, für die Verdopplung (J3)
    paused_until  timestamptz,                    -- nur zur Auskunft und fürs Log; maßgeblich ist next_start
    updated_at    timestamptz NOT NULL DEFAULT now()
);

-- Ein Platz je laufender Anfrage (J1): Nummer 1 bis Grenze, wer hält ihn, bis wann. Eine abgelaufene Zeile zählt
-- nicht mehr und wird vom nächsten übernommen; der Inhaber verlängert sie mit einem Herzschlag (§9a, Punkt 1).
CREATE TABLE public.earthx_source_lease (
    host    text        NOT NULL,
    slot    integer     NOT NULL CHECK (slot >= 1),
    holder  uuid        NOT NULL,
    until   timestamptz NOT NULL,
    PRIMARY KEY (host, slot)
);
```

`host` in der Schreibweise von `normalize_host`. Eine eigene Tabelle statt neuer Spalten in `earthx_rate_slots`: die Zeile der Ortssuche hat eine andere Regel (1 s fest, kein Unterbrecher), und ein Host ist kein Upstream-Name.

### 3.2 Anweisungen

- **`reserve(host, interval)`**, eine Anweisung wie `_RESERVE_SLOT`: `start = greatest(next_start, clock_timestamp())`, `next_start = start + interval`; zurück kommen `start − clock_timestamp()` (die Wartezeit) und `paused_until`. Jeder Aufrufer schiebt um **seinen** Abstand vor (`hosts.yaml`, beim Pyramidenbau sonst 0,25 s, §5.4); ein Aufrufer ohne Abstand (Buckets in `materialize`) wartet hinter dem Zeiger, schiebt ihn aber nicht.
- **`account(host, interval, requests)`** (nur Pyramidenbau): `next_start += (requests − 1) · interval`, wie `HostPacer.account`; bei 0 Anfragen (warmer Cache) geht der Platz zurück, nie vor `clock_timestamp()`.
- **`acquire(host, cap)`** (J1 = 1), eine Anweisung: die kleinste Nummer 1…`cap` ohne lebende Zeile; `INSERT … ON CONFLICT (host, slot) DO UPDATE … WHERE until <= clock_timestamp()` legt sie an oder übernimmt eine abgelaufene. Zwei Aufrufer auf derselben Nummer: einer gewinnt, der andere bekommt keine Zeile zurück und fragt sofort wieder. Mehr als `cap` lebende Plätze kann es nicht geben, weil die Nummer Teil des Schlüssels ist; keine Advisory-Sperre, keine Transaktion. Kein Platz frei: der Aufrufer fragt nach 0,25–1 s (Zufall) erneut; keine Verbindung wartet in der Datenbank.
- **Frist und Herzschlag (§9a, Punkt 1):** Ein Platz gilt 30 s. Solange der Inhaber ihn hält, verlängert ein Herzschlag ihn alle 10 s (`UPDATE … WHERE host, slot, holder`). Stirbt die Instanz, endet der Herzschlag, und der Platz ist spätestens nach 30 s frei. Findet der Herzschlag seine Zeile nicht mehr (übernommen, weil die Instanz zu lange stand), schreibt er eine Warnung; die laufende Anfrage endet regulär. **`release(host, slot, holder)`** löscht die Zeile, auch nach Fehler und Abbruch.
- **`report(host, outcome, retry_after)`**: Erfolg setzt `failures` und `pauses` auf 0. Fehler (§4.1) erhöht `failures`; erreicht es die Schwelle, schiebt dieselbe Anweisung `next_start` auf `greatest(next_start, now() + pause)`, setzt `paused_until` und erhöht `pauses` (J3). Ein `Retry-After` schiebt `next_start` ohne Schwelle um seinen Wert vor, höchstens 10 min.

Alle Anweisungen laufen auf einer **eigenen Verbindung im Autocommit**, nie in der Transaktion des Aufrufers (§2, `materialize`). Ein Fehler der Datenbank ist ein Fehler des Laufs, nie „ohne Grenze weiter“: wer nicht reservieren kann, sendet nicht (wie die Ortssuche, `geocode_cache.py` Kopf).

### 3.3 Kosten [A]

Je Anfrage ein Umlauf für den Zeiger, mit J1 = 1 zwei weitere für den Platz (der zweite zusammen mit `report`). Lokal rund 1 ms je Umlauf, gegen 170 ms Umlaufzeit der synthetischen Quelle und 1 s Abstand der FSDI. Eine heiße Zeile entsteht nicht: Bei 1 s bzw. 0,25 s Abstand sind es höchstens 1–4 Anweisungen je Sekunde und Host. Für die Buckets ohne Abstand in `materialize` (Auflisten in Seiten zu 1000, rund 30 Anfragen je Lauf) ebenso wenig.

---

## 4. Unterbrecher je Host

### 4.1 Was zählt

| Ergebnis eines Versuchs | zählt als |
|---|---|
| Antwort unter 500 außer `429` (auch `404`, `304`) | Erfolg: der Host antwortet |
| `429`, `500`, `502`, `503`, `504` | Fehler |
| Zeitüberschreitung, Verbindung nicht möglich (`UpstreamTimeout`, `UpstreamUnreachable`) | Fehler |
| Pyramidenbau: `source_timeout`, `source_5xx`, `source_429`, `source_unreachable` (`readers.source_failure_kind`) | Fehler |
| alles, was `gateway` vor dem Senden ablehnt (Allowlist, Adresse, Länge, `robots.txt`) | nichts: der Host wurde nicht gefragt |

Gezählt wird **jeder Versuch**, nicht jede Anfrage: drei Versuche einer Anfrage, die alle `503` bekommen, sind drei Fehler in Folge. Das ist die Regel „3 Fehler in Folge“ aus `adr/0025` §6.2 und `adr/0032` §8.2, jetzt für alle Instanzen zusammen statt je Lauf.

### 4.2 Was ein Aufrufer während einer Pause tut (J4)

Die Pause ist ein vorgeschobener Zeiger: `reserve` gibt eine lange Wartezeit und `paused_until` zurück. Vorschlag J4 = 1:

- **Pyramidenbau:** wartet. Der Aufseher hält die Frist des Baus (Herzschlag) und zählt die Pause nicht als Stillstand (`STALL_SECONDS`). Ein Bau von 6–7 h soll nicht wegen 5 min Pause von vorn beginnen.
- **`materialize`, Harvester:** warten bis 60 s; ist die Pause länger, ruht der Host für diesen Lauf (`HostResting`, „host paused after repeated failures“). Der Harvester legt die Funde nach `stale` (`adr/0025` §6.2); `materialize` endet mit Fehler, die Transaktion wird zurückgerollt, nichts ist geschrieben.

Nach der Pause ist die erste Anfrage die Probe: Erfolg schließt den Unterbrecher, ein Fehler öffnet ihn sofort wieder mit doppelter Pause (`failures` steht noch auf der Schwelle).

---

## 5. Schnitt im Code

### 5.1 `gateway`: Protokoll statt Datenbank

`gateway` bekommt ein Protokoll **`HostCoordinator`** (`gateway/coordinator.py`) mit `reserve`, `acquire`/`release` und `report` (asynchron) und eine Fassung im Speicher, die genau das heutige Verhalten hat (`_space`, `ReadSlots`). `Gateway(policy, coordinator=…)`: ohne Angabe die Fassung im Speicher, also unverändert für `api`, `tiler`, Tests, Runner und Worker. `_attempt` fragt vor jedem Versuch `reserve` (statt `_space`) und meldet danach `report`; `_send` nimmt den Platz über `acquire` statt `ReadSlots`, wenn ein Koordinator gesetzt ist. Die Wartezeit über 60 s wird zu `HostResting` (J4). `gateway` importiert dafür nichts Neues.

### 5.2 Postgres-Fassung, zweimal

- **`catalog/source_hosts.py`** (asynchron, wie `geocode_cache.py`): `PostgresHostCoordinator` für `discovery` (`materialize`, Harvester). `catalog` darf `gateway` importieren, das Protokoll passt strukturell.
- **`jobs/source_hosts.py`** (synchron, PR 2): dieselben Anweisungen für den Aufseher des Pyramidenbaus, weil `jobs` weder `catalog` noch `gateway` importieren darf. Ein Test hält die SQL-Texte beider Module gleich (wie die Dateinamen in `overview_builder.py`).
- **Geprüft (§9a, Punkt 2): Es gibt kein Modul, das beide heute importieren dürfen.** Nach `architekturplan.md` 3.1 und `.importlinter` darf `catalog` nur `gateway`, `jobs` nur `processing` und `objectstore`; die Schnittmenge der zwölf Module ist leer. `gateway` scheidet aus (für `jobs` verboten, und es soll keine Datenbank kennen), `processing` ebenso (für `catalog` verboten, und `processing` darf `psycopg` nicht einmal über Ketten erreichen). Bleibt nur ein Modul im Paketstamm: `earthx.logging` ist fachfremd, und ein neues Stamm-Modul stünde unter keinem Vertrag aus 3.1, wäre also ein Umweg um die Regeln statt einer erlaubten Stelle. Ebenso wenig ein Lesen der SQL-Datei aus dem Paket `catalog` durch `jobs`. **Umgesetzt (Auslegung, von Otto am 16.11.2026 bestätigt, §10.1):** Die Regeln liegen als Funktionen `earthx_source_*` in Migration 022; `catalog` ruft sie auf, `jobs` ruft in PR 2 dieselben auf. Doppelt bleiben nur die einzeiligen Aufrufe, kein SQL der Regeln; der Test auf Gleichheit prüft in PR 2 nur noch die Namen und Argumente der Aufrufe.
- `catalog.source_hosts` kommt in die Verbotsliste des Vertrags `runner` (wie jedes Modul von `catalog`, `test_module_boundaries.py`). Sonst keine Änderung an den Importregeln.

### 5.3 `materialize` und Harvester

Eine Fabrik `discovery/source_gateway.py`: `open_source_gateway(policy)` öffnet eine eigene `psycopg.AsyncConnection` im Autocommit und gibt ein `Gateway` mit `PostgresHostCoordinator` zurück; beim Schließen beides zu. `materialize` nutzt sie statt `Gateway(_policy_for(…))`; der Harvester (M5-19) nutzt dieselbe. Grenze und Abstand kommen weiter aus `hosts.yaml` (`_policy_for`).

### 5.4 Pyramidenbau: der Aufseher reserviert, das Kind wartet

Das Kind bleibt ohne Datenbank. Es bekommt statt des `HostPacer` einen **`PipePacer`** (in `jobs/overview_child.py`), der das Protokoll `Pacer` des Kerns erfüllt:

- `wait(host)` schickt `("pace", host)` und wartet auf `("go",)`.
- `account(host, requests, failure)` schickt `("account", host, requests, failure)`; keine Antwort. `failure` ist die Fehlerart des Versuchs oder `None`. Dafür bekommt `Pacer.account` einen dritten Parameter, und `_read_once` übergibt die Art aus `source_failure_kind`. `HostPacer` nimmt ihn an und ignoriert ihn (Fassung ohne Datenbank, z. B. für Tests).
- `build_pyramid` und `patch_pyramid` nehmen den Pacer als Argument, statt ihn selbst über `readers.access.host_pacer()` zu bauen.

Der Aufseher (`_watch`) antwortet: Auf `pace` reserviert er den Zeiger, merkt sich die fällige Zeit, holt bei Fälligkeit einen Platz (J1) und schickt `go`. Er blockiert dabei nie; seine Schleife fragt ohnehin alle ≤ 0,5 s und schlägt weiter die Frist. Während ein `pace` offen ist, zählt keine Zeit zum Stillstand. Auf `account` verrechnet er die Anfragen, meldet Erfolg oder Fehler und gibt den Platz frei. Den Abstand je Host gibt der Worker beim Start mit (wie `pyramid_hosts()`): Eintrag in `hosts.yaml`, sonst `EARTHX_OVERVIEW_HOST_INTERVAL_S` (0,25 s, `adr/0032` F4). Die Sperre „ein Bau je Host“ bleibt, wie sie ist.

Die Wiederholungsstaffel der Datei (5 s, 20 s, 60 s) bleibt; jeder Versuch geht wie heute durch den Pacer, also auch durch eine Pause.

---

## 6. Was sich ändert

- Zwei Läufe von `materialize` gegen die FSDI fragen zusammen höchstens einmal je Sekunde; ein Pyramidenbau und ein Lauf auf demselben Bucket halten zusammen 0,25 s.
- Ein Host, der drei Versuchen in Folge nicht antwortet, wird von keinem der drei Aufrufer gefragt, bis die Pause vorbei ist.
- `api` und `tiler` ändern sich nicht: kein neuer Umlauf, kein neues Warten.
- Neue Fehlermeldung von `materialize`: „host … rests for this run“ bei einer Pause über 60 s (J4). Der Host steht in der Meldung (ein Name aus der Registry), keine Adresse, keine AOI.
- Log: eine Zeile, wenn ein Host pausiert wird (Host, Pause, Fehler in Folge), und eine, wenn er wieder antwortet.

---

## 7. Messung vorher/nachher (synthetisch)

Mit `scripts/tile-bench/slow_source.py` (RTT 170 ms, Verbindungsaufbau 350 ms) und einem neuen Schalter `--fail` (antwortet in einem Zeitfenster mit `503`), lokalem Postgres, `main` gegen den Branch, 5 Wiederholungen im Wechsel. Ein kleines Skript stellt je Prozess Anfragen über `Gateway` nacheinander, wie `materialize` es tut; `materialize` selbst braucht einen echten Adapter und wird nicht gegen die Quelle gefahren. Keine echte Quelle, keine AOI im Log.

| Fall | Aufbau | gemessen | Erwartung |
|---|---|---|---|
| M1 Abstand über Instanzen | 2 Prozesse × 60 Anfragen, Abstand 1 s | kleinster und mittlerer Abstand der Anfänge an der Quelle, Wandzeit | vorher ≈ 0,5 s, nachher ≥ 1 s |
| M2 Kosten je Anfrage | 1 Prozess, 200 Anfragen, ohne Abstand (wie ein Bucket) | Median und p95 je Anfrage, Wandzeit | nachher ≤ +5 % (J5) |
| M3 Unterbrecher | 3 Prozesse, Quelle 60 s lang `503` | Anfragen an der Quelle im Fenster; Zeit bis zur ersten Antwort danach | vorher je Prozess bis 3 Versuche je Anfrage; nachher 3 Fehler, dann Pause |
| M4 Pyramidenbau (PR 2) | Bau aus `make_cogs.py`, allein und mit einem Prozess wie M1 auf demselben Host | Wandzeit des Baus, Abstand der Anfänge an der Quelle | allein ≤ +5 % (J5); zusammen ≥ 0,25 s |

Ergebnis als Tabelle in §10.2 und im PR.

---

## 8. Schnitt (Vorschlag J6 = 1)

| PR | Inhalt | Umfang (ohne Tests, geschätzt) |
|---|---|---|
| **PR 1** ([#368](https://github.com/oscipal/earthX/pull/368)) | Plan; Migration 022; `HostCoordinator` in `gateway` mit Fassung im Speicher; `catalog/source_hosts.py`; `discovery/source_gateway.py`; `materialize` darüber; Messung M1–M3; Nachträge `adr/0025` §6.2, `architekturplan.md` 6.5, README | ~330 Zeilen |
| **PR 2** | `jobs/source_hosts.py`; `PipePacer`, Antworten im Aufseher, `Pacer.account` mit Fehlerart, Abstand aus `hosts.yaml`; Messung M4; Nachtrag `adr/0032` §8.2 | ~250 Zeilen |

Tests je PR, mit Fehlerfällen: zwei Koordinatoren auf derselben Zeile (Abstand hält, auch gleichzeitig), Abstand 0 schiebt nicht, `account` mit 0 Anfragen gibt zurück und nie vor jetzt; Platz: Grenze voll, abgelaufener Platz zählt nicht, Freigabe nach Fehler und Abbruch (`CancelledError`); Unterbrecher: Schwelle, Erfolg setzt zurück, Probe nach der Pause, Verdopplung bis zur Obergrenze, `Retry-After` (Zahl, fehlt, zu groß, kein Zahlwert), `404` zählt als Erfolg, Ablehnung vor dem Senden zählt nicht; Pause über 60 s wird `HostResting`; Datenbank nicht erreichbar heißt kein Senden; die Zeile liegt nicht in der Transaktion von `materialize` (zweite Verbindung sieht sie vor dem Commit); falsche Werte (Abstand negativ, `NaN`, Grenze 0, Host als IP); Pyramide: `pace` ohne Antwort hält den Bau nicht als Stillstand an, Kind stirbt mit offenem Platz (Frist), unbekannte Nachricht wird verworfen, die SQL-Texte beider Module sind gleich.

---

## 9. Fragen an Otto

**J1 — Gleichzeitige Verbindungen über alle Instanzen?**
1. Ja: ein Platz je laufender Anfrage in Postgres (`earthx_source_lease`, Frist 10 min, Warten im Aufrufer), Grenze aus `hosts.yaml` **(Empfehlung: nur so gilt „Grenzen und Abstand“ aus dem Auftrag für alle Instanzen; kostet zwei Umläufe je Anfrage, §3.3)**
2. Nein: nur Zeiger und Unterbrecher in Postgres; die Verbindungen bleiben je Lauf. Heute lesen alle drei Aufrufer nacheinander, die Grenze wirkt erst bei vielen gleichzeitigen Läufen

**J2 — Wie teilen sich die drei Aufrufer die Verbindungen eines Hosts mit `api` und `tiler`?** (nur bei J1 = 1)
1. Getrennt: die drei zusammen halten die volle Grenze aus `hosts.yaml`, `api` und `tiler` ihre Anteile wie in M5-36; die Summe kann bis M6 bis zum Doppelten reichen **(Empfehlung: die Rücksicht der drei liegt im Abstand, der sie bei FSDI und BEV ohnehin auf rund eine Anfrage zugleich hält; Kacheln werden nicht langsamer)**
2. Die drei zählen zusammen als eine weitere Instanz: `EARTHX_SOURCE_INSTANCES` umfasst sie, jeder bekommt `Grenze // N`. Die Summe hält, aber die Kacheln verlieren einen Anteil (FSDI bei einer Instanz von 6 auf 3, gemessen +30 % bei vielen Kacheln, M5-36 §9.4)
3. Die drei zusammen höchstens 1 Verbindung je Host

**J3 — Wann ruht ein Host, und wie lange?**
1. Nach 3 Fehlern in Folge (über alle Aufrufer und Instanzen, §4.1) 5 min; jede weitere Pause direkt danach doppelt so lang, höchstens 60 min; ein Erfolg setzt zurück **(Empfehlung: 3 wie `adr/0025` §6.2 und `adr/0032` §8.2)**
2. Nach 3 Fehlern in Folge fest 15 min
3. Andere Werte: bitte Schwelle und Dauer nennen

**J4 — Was tut ein Aufrufer, während ein Host ruht?**
1. Der Pyramidenbau wartet (hält seine Frist); `materialize` und Harvester warten bis 60 s, sonst ruht der Host für diesen Lauf (`materialize` endet ohne zu schreiben, der Harvester legt Funde nach `stale`) **(Empfehlung, §4.2)**
2. Alle warten, bis die Pause vorbei ist
3. Alle hören auf; der Pyramidenbau endet mit einer neuen Fehlerart `source_paused` und wird nach einer Stunde wiederholt

**J5 — Was heißt „nicht spürbar langsamer“ bei einem einzelnen Lauf (M2, M4)?**
1. Median und p95 höchstens +5 % über `main`, wie G5 in M5-36 **(Empfehlung)**
2. Nur berichten, nicht fordern

**J6 — Schnitt?**
1. Zwei PRs wie §8: dieser mit `materialize` und dem Mechanismus, der zweite mit dem Pyramidenbau **(Empfehlung)**
2. Ein PR mit allem (rund 580 Zeilen ohne Tests)

### 9a. Antworten Otto (16.11.2026)

| Frage | Antwort | Folge |
|---|---|---|
| J1 | 1 | ein Platz je laufender Anfrage in Postgres (`earthx_source_lease`) |
| J2 | 1 | `materialize`, Harvester und Pyramidenbau zusammen halten die volle Grenze aus `hosts.yaml`, getrennt von `api` und `tiler` |
| J3 | 1 | nach 3 Fehlern in Folge 5 min, verdoppelnd bis 60 min, ein Erfolg setzt zurück |
| J4 | 1 | Pyramidenbau wartet; `materialize` und Harvester warten bis 60 s, sonst ruht der Host für den Lauf |
| J5 | 1 | Median und p95 höchstens +5 % bei einem einzelnen Lauf |
| J6 | 1 | zwei PRs wie §8 |

Dazu zwei Vorgaben:

1. **Plätze mit Frist und Herzschlag**, damit eine abgestürzte Instanz keinen Platz dauerhaft belegt; mit Test. Umgesetzt wie §3.2: Frist 30 s, Herzschlag alle 10 s, eine abgelaufene Zeile übernimmt der nächste.
2. **Eine Fassung des SQL, wenn es ein Modul gibt, das `catalog` und `jobs` beide schon heute importieren dürfen**, sonst zwei mit Test auf Gleichheit. Ergebnis der Prüfung: keines (§5.2); also zwei Fassungen, die zweite mit PR 2.

---

## 10. Umsetzung

### 10.1 PR 1 ([#368](https://github.com/oscipal/earthX/pull/368)), Stand 16.11.2026

- **Migration 022** (`earthx_source_host`, `earthx_source_lease`) mit den Regeln als **Funktionen** (`earthx_source_reserve`, `_pause_left`, `_report`, `_acquire`, `_renew`, `_release`, `CREATE OR REPLACE`). **Auslegung zu §9a Punkt 2:** Ein gemeinsames Python-Modul für `catalog` und `jobs` gibt es nicht (§5.2); eine Fassung der Regeln geht trotzdem, und zwar in der Datenbank. Jede Funktion sperrt die Zeile (`FOR UPDATE`), liest die Uhr danach einmal und läuft als eine Anweisung. Das schloss zugleich einen Befund der Prüfung (mehrfaches `clock_timestamp()` in einer Anweisung, H1).
- **`gateway`:** Protokoll `HostCoordinator` (`reserve` mit Höchstwartezeit, `pause_left`, `place`, `report`); `Gateway(…, coordinator=…)`. Ohne Koordinator unverändert. Mit Koordinator: ein Platz je Anfrage (über alle Versuche), ein Zug vor jedem Versuch, eine Meldung nach jedem Versuch (§4.1). Ein Zug über 60 s wird nicht genommen und der Host ruht für den Lauf (`HostResting`, J4). Wer auf seinen Zug gewartet hat, fragt vor dem Senden, ob inzwischen eine Pause begann (Prüfung S3).
- **`catalog/source_hosts.py`:** `PostgresHostCoordinator` auf einer Verbindung im Autocommit (sonst `ValueError`); Plätze mit Frist 30 s und Herzschlag alle 10 s (§9a Punkt 1), Freigabe auf jedem Ausgang, auch bei Abbruch; der Herzschlag wird per Signal beendet, nicht abgebrochen, damit eine laufende Verlängerung auf der gemeinsamen Verbindung zu Ende läuft. Log: „source host paused“ (Host, Pause), „source host answers again“, „source place lost“; nur der Host, keine Adresse.
- **`discovery/source_gateway.py`:** `open_source_gateway(policy)` öffnet eine eigene Verbindung und gibt das `Gateway` mit Koordinator; `materialize` nutzt es, der Harvester (M5-19) ebenso.
- **Auslegungen** (von Otto am 16.11.2026 bestätigt, ebenso die Funktionen in Migration 022; Änderungen an ihnen nur per neuer Migration):
  - „Jede weitere Pause **direkt danach** doppelt so lang“ (J3): Ein Fehler zählt als gescheiterte Probe, solange seit dem Ende der letzten Pause nicht mehr als deren Länge vergangen ist; danach beginnen Zählung und Verdopplung neu (Prüfung S2).
  - Ein Zug, auf den der Aufrufer nicht wartet, schiebt den Zeiger nicht vor (Prüfung S1).
  - Ein Erfolg während einer laufenden Pause (eine Anfrage, die schon unterwegs war) setzt den Unterbrecher zurück, die Pause selbst läuft zu Ende.
- **Bekannte Grenzen:** Ein Platz wird auch während des Wartens auf den Zug und des Backoffs gehalten (wie bisher der Zähler je Prozess); auf einen Platz wird ohne Obergrenze gewartet, solange lebende Inhaber alle halten. Ein abgebrochener Aufrufer kann einen Platz bis zu seiner Frist (30 s) belegen, wenn der Abbruch zwischen Anlegen und Lesen der Zeile fällt. Für den Harvester (M5-19): Ein erfolgreicher Abruf von `robots.txt` zählt als Erfolg des Hosts. `materialize` braucht jetzt zwei Verbindungen je Lauf.
- **Prüfung** (Subagent `reviewer`): kein Blocker; S1–S4, S6, H1, H2 und H4 behoben, S5 mit Tests geschlossen (Datenbank weg → nichts gesendet, Abbruch mit echtem Postgres, gleichzeitige Meldungen → genau eine Pause, falsche Werte, Host als Adresse).
- **Messstand:** `slow_source.py --fail-file` (solange die Datei existiert, `503`), `source_turns.py` (Läufe wie `materialize` über das `Gateway`, mit `--shared` über Postgres), `source_turns_summary.py`.

### 10.2 Messung PR 1 (J5)

Synthetische Quelle `slow_source.py` (RTT 170 ms, Verbindungsaufbau 350 ms, eine Datei von 2 KB), lokales Postgres mit Migration 022, `main` eb7079c gegen den Branch f618720 (Stand des Codes; danach nur Doku), 5 Wiederholungen, je Wiederholung erst `main`, dann der Branch. `main` läuft mit seinem eigenen `backend` (ohne Koordinator), der Branch mit `--shared` (Postgres). Prozesse wie `materialize`: je Prozess ein `Gateway`, Anfragen nacheinander. Keine echte Quelle, keine AOI.

| Fall | Aufbau | `main` | Branch | Ergebnis |
|---|---|---|---|---|
| M1 Abstand über Instanzen | 2 Prozesse × 30 Anfragen, Abstand 1 s | Abstand der Anfänge an der Quelle im Median 0,010 s (je zwei Anfragen fast gleichzeitig), Wandzeit 28,6 s | Median 1,000 s, kleinster 0,997 s zwischen Anfragen auf bestehenden Verbindungen; Wandzeit 58,6 s | die Grenze von 1 s hält für beide Prozesse zusammen |
| M2 Kosten je Anfrage | 1 Prozess × 200 Anfragen, ohne Abstand | Median 216,0 ms, p95 216,5 ms; Wandzeit Median 43,53 s, p95 43,55 s | Median 216,3 ms (+0,1 %), p95 220,3 ms (+1,8 %); Wandzeit Median 43,83 s (+0,7 %), p95 43,92 s (+0,8 %) | innerhalb +5 % (J5) |
| M3 Unterbrecher | 3 Prozesse, 30 s lang Anfragen; die Quelle antwortet von s 2 bis s 22 mit `503` | 89 `503` an der Quelle je Lauf (88–91), jeder Prozess wiederholt für sich | **3** `503` je Lauf in allen 5 Läufen; danach ruht der Host, alle drei Prozesse enden mit „rests for this run“ | nach 3 Fehlern in Folge fragt keine Instanz mehr |

- **M1, Messartefakt:** Der kleinste Abstand an der Quelle liegt je Lauf einmal bei 0,62–0,63 s. Es ist jedes Mal die Lücke nach der ersten Anfrage des zweiten Prozesses: Die Quelle zeichnet `t0` nach dem simulierten Verbindungsaufbau (350 ms) auf, die erste Anfrage einer neuen Verbindung erscheint also um 0,35 s verspätet. Zwischen Anfragen auf bestehenden Verbindungen ist der kleinste Abstand 0,997 s.
- **M3:** Weil eine Pause 5 min dauert und ein Zug über 60 s nicht genommen wird, ruht der Host für jeden der drei Läufe; nach dem Ende der Störung bei s 22 gibt es im Fenster der Messung keine Probe mehr. Die Probe nach der Pause decken die Tests ab (`test_a_failed_probe_after_the_pause_pauses_twice_as_long`, `test_a_successful_probe_closes_the_breaker`).
- **Pyramidenbau (M4)** folgt mit PR 2.

### 10.3 PR 2 ([#373](https://github.com/oscipal/earthX/pull/373)), Stand 17.11.2026

- **Migration 023:** `earthx_source_account(host, interval, requests)` verrechnet die Anfragen, die GDAL für eine Datei stellte: Der Zug des Hosts rückt um `(requests − 1) · interval` vor, wie `HostPacer.account`. **Abweichung:** Bei null Anfragen (GDAL-Cache) gibt es nichts zurück, weil ein inzwischen an eine andere Instanz vergebener Zug sonst vorrücken könnte. Die Regeln aus 022 bleiben unverändert (Änderungen nur per neuer Migration).
- **Kern:** `Pacer.account` erfährt zusätzlich, ob das Lesen an der Quelle scheiterte (`_TRANSIENT`: Zeitüberschreitung, keine Verbindung, `429`, `5xx`), und den `Retry-After`. `build_pyramid` und `patch_pyramid` nehmen den Pacer als Argument. `pyramid_source_limits()` liefert je Host Plätze und Abstand (`hosts.yaml`, sonst `EARTHX_OVERVIEW_HOST_INTERVAL_S`, 0,25 s).
- **Kind:** `PipePacer` schickt `("pace", host)`, wartet auf `("go",)` und meldet danach `("account", host, requests, failed, retry_after)`. Das Kind bleibt ohne Datenbank (B9).
- **Aufseher:** `jobs/source_hosts.py` mit `SourceHosts` (dieselben Aufrufe und Zahlen wie `catalog.source_hosts`, ein Test hält beide gleich) und `TurnKeeper`. Ein Zug wird genommen und ohne Blockieren abgewartet. Liegt eine Pause dazwischen, wird danach ein eigener Zug genommen (J4: der Bau wartet). Ein Platz wird mit Frist und Herzschlag gehalten; danach wird verrechnet, gemeldet und freigegeben. Nur das Warten auf einen Zug zählt nicht als Stillstand; ein Lesen, das hängt, ist nach `STALL_SECONDS` stillstehend und gibt seinen Platz zurück. Eine Nachricht falscher Form oder Reihenfolge und ein Host, den der Bau nicht liest, beenden den Bau als `rejected`. Fehlen beim Start die Grenzen für einen Host einer Pyramide, startet der Worker nicht.
- **Unterbrecher:** Jedes Lesen, das an der Quelle scheitert, ist ein Fehler. Ein Lesen ohne Anfrage (Cache) meldet nichts, damit es keine Pause beendet, die eine andere Instanz begann. Jedes andere Lesen ist ein Erfolg.
- **Prüfung** (Subagent `reviewer`): ein Blocker. Die Ausnahme vom Stillstand galt während des ganzen Lesens, ein hängendes Lesen hätte Bau und Platz für immer gehalten. Behoben und mit einem Test belegt, der ohne die Behebung rot ist. Ebenso behoben: ein Cache-Treffer als Erfolg, eine ungeschützte Freigabe im `finally`, zu lockere Prüfung der Nachrichten des Kindes, Züge von vor einer Pause, ein Platz, der nach dem Verlust weiter verlängert wurde, Subdomains, fehlende Grenzen erst beim Lesen. Dazu Tests für die Fehlerpfade: Hängen, Absturz zwischen `go` und `account`, falsche Nachrichten, Datenbankfehler bei der Freigabe.
- **Seit M5-30b, behoben in diesem PR (§10.5):** Der Zähler des Kerns zählte nur die `Downloading`-Zeilen von GDAL, nicht das `HEAD` am Anfang einer Datei und nicht dessen Wiederholungen.

### 10.4 Messung PR 2 (M4, J5)

Synthetische COGs aus `make_cogs.py` (`B04`, 10980² px, UTM), `slow_source.py` (RTT 170 ms, Verbindungsaufbau 350 ms), lokales Postgres mit 022 und 023. Gemessen wurde mit `pyramid_turns.py`: der echte Aufseher (`OverviewBuilder._step`) mit einem Kind, das 30 Dateien je einmal über den Kern liest (`base_tile`, z9). Auf dem Branch nimmt das Kind seine Züge über `PipePacer`, auf `main` hält es den Abstand selbst (`HostPacer`). Für „zusammen“ läuft daneben ein Lauf wie `materialize` auf demselben Host mit 0,25 s Abstand (`source_turns.py`, auf dem Branch über Postgres). `main` fba73e2 gegen den Branch 44101a2, 5 Wiederholungen im Wechsel. Keine echte Quelle.

| Fall | `main` | Branch | Ergebnis |
|---|---|---|---|
| Bau allein, Wandzeit | Median 13,41 s, p95 13,61 s | Median 13,79 s (+2,8 %), p95 13,91 s (+2,2 %) | innerhalb +5 % (J5) |
| Bau und Lauf zusammen, Züge je Sekunde an der Quelle | 6,38 (jeder hält 0,25 s für sich) | **3,99** (höchstens 4,00) | 0,25 s je Host gilt für beide zusammen |
| dasselbe, alle Anfragen je Sekunde | 8,88 | 5,94 | |
| Wandzeit des Baus zusammen | 13,4 s | 16,8 s | der Bau teilt sich die Züge mit dem Lauf |

- Ein „Zug“ an der Quelle ist ein `GET` des Laufs oder die erste Anfrage für eine Datei des Baus (`HEAD`), siehe §10.3, letzter Punkt.
- Ein erster Lauf vor den Behebungen der Prüfung ergab fast dieselben Zahlen (allein +2,4 % / +0,3 %, zusammen 4,02 Züge/s); gezählt wird der Lauf auf dem Endstand.

