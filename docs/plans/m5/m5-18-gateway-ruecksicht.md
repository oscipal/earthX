# M5-18 — `gateway`: `User-Agent`, Abstand je Host, `robots.txt`: Plan-Schritt

**Status (06.11.2026):** Plan angenommen (Otto, 06.11.2026; Antworten in §8a), Umsetzung im selben Draft-PR.
**Aufgabe:** M5-18 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.2. **Stufe B.** Hängt von nichts ab; M5-19 (Harvest-Kern) wartet auf den Merge.
**Grundlagen:** `adr/0025` §3 (Befund opendata.swiss), §3a (RFC 9309), §6.2, §8 Schnitt Schritt 3, F9, §12; `architekturplan.md` 4.3 (Fetch) und 6.5; `KLAERUNGEN.md` B8, B9; `adr/0005` §6 (Grenzen je Host).

Belegstufen wie in `adr/0025`: **P** am Quelltext gelesen (Stand `main` bc37bd6), **S** Sekundärquelle, **A** eigene Ableitung. In dieser Aufgabe wird nichts an Quellen gemessen; Tests laufen nur gegen `httpx.MockTransport`.

---

## 1. Ziel

`gateway` bekommt die drei Teile von „Rücksicht auf die Quellen“ (`adr/0025` K1), die heute fehlen:

1. **`User-Agent`** auf jeder Anfrage, für alle Aufrufer, nicht überschreibbar (F9 = 1 in `adr/0025`).
2. **Mindestabstand je Host** zwischen zwei Anfragen, neben den 6 Verbindungen.
3. **`robots.txt`** nach RFC 9309: einmal je Lauf und Host lesen, `Disallow` für den eigenen Produktnamen beachten; `5xx` oder nicht erreichbar heißt, der Host ruht.

Kein Harvester, keine Seed-Datei, keine Tabellen: das ist M5-19. Diese Aufgabe liefert nur die Bausteine in `gateway`, mit Vorgaben, die das Verhalten aller heutigen Aufrufer (Suche, Kacheln, Intake, Runner, Geocoder) außer dem `User-Agent` nicht ändern.

---

## 2. Ausgangslage im Code [P]

- **`Policy`** (`gateway/policy.py`): Allowlist, Grenzen (8 MB, 6 Verbindungen je Host, 3 Weiterleitungen, Timeouts). Kein `user_agent`, kein Abstand, kein `robots.txt`.
- **`Gateway`** (`gateway/client.py`): ein Semaphor je Host; Weiterleitungen folgt es selbst mit `check_url` je Hop; 3 Versuche bei `429/502/503/504`, `Retry-After` bis 10 s; Fehler ab `400`. Den Kopf `Host` darf ein Aufrufer nicht setzen (`_once`); andere Köpfe gehen ungeprüft durch. `sleep` ist schon injizierbar, eine Uhr nicht.
- **`User-Agent` heute:** `gateway` setzt keinen; `httpx` schickt `python-httpx/<version>`. Nur der Geocoder setzt einen eigenen Kopf (`adapters/nominatim.py:384`) aus `EARTHX_GEOCODER_USER_AGENT`, Vorgabe `EarthX/0.1 (+https://github.com/oscipal/earthX)` (`api/dependencies.py:44–45`).
- **GDAL** (`gateway/gdal.py`): öffnet seine Verbindungen selbst; `gdal_options(policy)` setzt Timeouts und Wiederholungen, aber kein `GDAL_HTTP_USERAGENT`. GDAL schickt damit seinen eigenen Standardkopf.
- **Aufrufstellen von `Policy(...)`:** 76 in 51 Dateien, die meisten in Tests; im Produktivcode `api/dependencies.py`, `api/intake.py` (4), `discovery/materialize.py`, `readers/access.py` (3), `readers/zarr_reader.py`.
- **Kein `robots.txt`** irgendwo im Code.

---

## 3. Umsetzung

### 3.1 `User-Agent` (F1 = 1 mit Ergänzungen 1 und 2, §8a)

- **Ein Wert je Instanz:** `EARTHX_USER_AGENT`, leer oder nicht gesetzt heißt Vorgabe `DEFAULT_USER_AGENT = "EarthX/0.1 (+https://github.com/oscipal/earthX)"` (Konstante in `gateway/policy.py`). `user_agent_from_env()` liest und prüft ihn.
- **Prüfung** (Vorgabewert und Variable gleich, `ValueError`): nicht leer; nur druckbares ASCII ohne Steuerzeichen (kein Zeilenumbruch, kein Einschleusen von Köpfen); höchstens 256 Zeichen; kein `@` (keine Mail-Adresse, F9). Der Produktname (Text vor dem ersten `/`) ist der Name, den `robots.txt` sucht (§3.3); ohne `/` ist es der ganze Wert bis zum ersten Leerzeichen.
- **Beim Start geprüft:** `api`, `tiler`, `worker`, `materialize` und der lokale Runner rufen `user_agent_from_env()` beim Start auf; ein ungültiger Wert hält den Prozess an, die Meldung nennt die Variable, nie den Wert.
- **`Policy.user_agent: str`**, Vorgabe aus `user_agent_from_env()`, geprüft wie oben. Die 76 Aufrufstellen bleiben unverändert und bekommen so den Wert der Instanz.
- **Gesetzt in `_once`:** `User-Agent` aus der Policy auf jeder Anfrage, auch bei Wiederholung, Weiterleitung und `HEAD`. Ein `User-Agent` des Aufrufers wird verworfen wie heute `Host`, gleich in welcher Schreibweise. Kein Aufrufer überschreibt ihn.
- **GDAL:** `gdal_options(policy)` setzt `GDAL_HTTP_USERAGENT` auf denselben Wert. Damit tragen auch Kachel- und Runner-Lesezugriffe den Kopf.
- **Geocoder (Ergänzung 2):** `EARTHX_GEOCODER_USER_AGENT` **entfällt und geht in `EARTHX_USER_AGENT` auf.** `GeocoderConfig.user_agent`, der Parameter `user_agent` von `nominatim.geocode` und der eigene Kopf in `nominatim._fetch` entfallen; Nominatim bekommt den Wert der Instanz über die Policy. Wer einen eigenen Nominatim-Betrieb mit eigener Kennung braucht, setzt `EARTHX_USER_AGENT`. Ist die alte Variable noch gesetzt, schreibt `api` beim Start eine Warnung (Name der Variable, nicht der Wert) und liest sie nicht. Entfernt aus `docker-compose.yml`, `.env.example` und README; `EARTHX_USER_AGENT` neu in `.env.example`, README und bei `api`, `tiler`, `worker` und `materialize` in `docker-compose.yml`.

### 3.2 Mindestabstand je Host (nach F2)

- **`Policy.min_interval_s: float = 0.0`** und **`Policy.host_intervals: Mapping[str, float]`** (leer). Der Abstand eines Hosts ist der Eintrag in `host_intervals` (Host in der Schreibweise von `normalize_host`, auch für Subdomains wie bei der Allowlist), sonst `min_interval_s`. Negative Werte, `NaN` und Werte über 300 s sind ein `ValueError`.
- **Was zählt:** der Abstand zwischen den **Starts** zweier Anfragen an denselben Host, je Versuch. Wiederholungen und jeder Hop einer Weiterleitung zählen mit (jeweils für den Host, an den die Anfrage geht). Eine Wartezeit aus `Retry-After` oder dem Backoff kommt hinzu, ersetzt den Abstand also nicht.
- **Mechanik:** je Host ein `asyncio.Lock` und der früheste nächste Start. Unter dem Lock wird der eigene Start reserviert, danach außerhalb des Locks gewartet. So gilt der Abstand auch bei 6 gleichzeitigen Anfragen, und das Semaphor bleibt die Grenze für gleichzeitige Verbindungen.
- **Uhr:** `Gateway(..., clock=time.monotonic)` neu injizierbar, wie `sleep` heute. Tests laufen mit falscher Uhr und falschem `sleep`, ohne echte Wartezeit.
- **Zustand:** nur im Speicher des `Gateway`-Objekts. Ein Lauf des Harvesters ist ein `Gateway` (Muster `materialize`); das passt zu „hält keinen Zustand, den ein Neustart vermissen würde“.
- **GDAL** bekommt keinen Abstand: Kachel- und Runner-Lesen brauchen ihn nicht, und der Harvester liest über den Client, nicht über GDAL (`adr/0025` §6.3).

### 3.3 `robots.txt` (nach F3, F4, F5)

- **Schalter `Policy.obey_robots: bool = False`.** Nur Policies mit `True` fragen `robots.txt`. Der Harvester setzt ihn in M5-19 für den Fetch der Kataloge; Verify und Health-Checks nutzen eine eigene Policy je Datensatz ohne Schalter (`adr/0025` §6.2 letzter Satz, §6.3).
- **Abruf:** vor der ersten Anfrage an einen Host `GET https://<host>/robots.txt` über denselben Weg (`check_url`, `User-Agent`, Abstand, Semaphor), ohne Wiederholung. Weiterleitungen folgt `gateway` wie sonst auch, also nur innerhalb der Allowlist und höchstens 3 (RFC 9309 verlangt mindestens 5 [S]; mehr als 3 gilt hier als „nicht erreichbar“, Auslegung A3).
- **Antwort** (RFC 9309 §2.3.1 [S]):

| Antwort | Folge |
|---|---|
| `2xx` | Regeln lesen; höchstens 500 KiB werden ausgewertet (RFC 9309 §2.5), der Rest verworfen |
| `4xx` außer `429` | alles erlaubt |
| `429`, `5xx`, Timeout, nicht erreichbar, mehr als 3 Weiterleitungen | Host ruht: jede weitere Anfrage an ihn wirft `HostResting` |
| Weiterleitung außerhalb der Allowlist | Host ruht (Auslegung A3) |

- **Cache:** je `Gateway`-Objekt und Host, höchstens 24 h (RFC 9309 §2.4). Länger lebt ein Lauf nicht; das Objekt im Prozess `api` setzt den Schalter nie.
- **Regeln (Parser nach F3):** Gruppen nach `user-agent`; passt der Produktname aus §3.1 (ohne Groß-/Kleinschreibung), gilt nur diese Gruppe, sonst die Gruppe `*`, sonst alles erlaubt. Mehrere Gruppen mit gleichem Namen werden zusammengeführt. Innerhalb der Gruppe gewinnt die **längste** passende Regel, bei Gleichstand `Allow`. `*` und `$` in Pfaden, Prozent-Kodierung normiert. Unbekannte Zeilen und `Sitemap` werden übersprungen. Verglichen wird Pfad plus Abfrage, wie RFC 9309 §2.2.2 es vorsieht; der Log schreibt wie heute nur den Pfad.
- **`Crawl-delay`** (nicht Teil von RFC 9309): nach F5.
- **Wirkung:** Eine gesperrte Adresse wirft `RobotsDisallowed` (neue Unterklasse von `UrlRejected`, Text ohne Adresse, wie alle Fehler in `errors.py`), bevor eine Anfrage an sie geht. Gilt für jeden Hop einer Weiterleitung. `HostResting` ist eine eigene Unterklasse von `GatewayError`; der Harvester in M5-19 zählt sie im Lauf-Bericht, statt den Lauf abzubrechen.
- **`/robots.txt` selbst** ist nie gesperrt.

### 3.4 Was sich für bestehende Aufrufer ändert

Nur der `User-Agent`: statt `python-httpx/…` bzw. dem GDAL-Standard steht der Wert der Instanz (Vorgabe `EarthX/0.1 (+https://github.com/oscipal/earthX)`) auf jeder Anfrage; `EARTHX_GEOCODER_USER_AGENT` entfällt (§3.1). Abstand `0` und `obey_robots=False` sind die Vorgaben; Suche, Kacheln, Intake und Runner verhalten sich sonst wie heute. Die 76 Aufrufstellen von `Policy(...)` bleiben unverändert (F1 = 1).

---

## 4. Tests

Alle gegen `httpx.MockTransport`, falsche Uhr und falsches `sleep`; kein Netz.

- **`User-Agent`:** auf `GET`, `HEAD`, `POST`, jeder Wiederholung und jedem Hop; Kopf des Aufrufers in drei Schreibweisen verworfen; Geocoder schickt den Wert der Instanz; `gdal_options` enthält `GDAL_HTTP_USERAGENT`; `EARTHX_USER_AGENT` gesetzt, leer und nicht gesetzt; Start von `api` mit gesetztem `EARTHX_GEOCODER_USER_AGENT` warnt ohne Wert. Fehleingaben (für Variable und `Policy`): nur Leerzeichen, `\r\n` (Kopf-Einschleusung), Tabulator, Nicht-ASCII, über 256 Zeichen, mit `@`; die Fehlermeldung enthält den Wert nicht.
- **Abstand:** zwei Anfragen an denselben Host im Abstand, an verschiedene Hosts ohne; Eintrag je Host vor Vorgabe, Subdomain erbt; sechs gleichzeitige Anfragen starten im Abstand; Wiederholung nach `503` wartet Backoff **und** Abstand; Weiterleitung auf anderen Host zählt dort; Fehleingaben: negativ, `NaN`, unendlich, über 300 s, Host in der Tabelle, der nicht normalisierbar ist; Vorgabe `0` wartet nie.
- **`robots.txt`:** Gruppe für `EarthX` vor `*`; längste Regel; `Allow` bei Gleichstand; `*` und `$`; Prozent-Kodierung; leere Datei; Datei ohne passende Gruppe; `404` alles erlaubt; `429`, `500`, Timeout, Transportfehler → `HostResting` für alle folgenden Anfragen; einmal je Host abgerufen (zweite Anfrage ohne neuen Abruf); nach 24 h neu (falsche Uhr); über 500 KiB nur der Anfang ausgewertet; ungültiges UTF-8 und Binärmüll ohne Absturz; Weiterleitung von `robots.txt` außerhalb der Allowlist → ruht; gesperrtes Ziel einer Weiterleitung → `RobotsDisallowed`; `obey_robots=False` fragt nie; `RobotsDisallowed` und `HostResting` nennen keine Adresse und keine Abfrage.
- **Zweckfremd:** Eine Policy ohne Schalter kann `robots.txt` nicht abschalten, wo ein Aufrufer sie mit Schalter gebaut hat (`within` engt nur ein, schaltet `robots.txt` nicht ab).

---

## 5. Auslegungen

- **A1:** „Pflicht“ in F9 heißt: jede Anfrage trägt den Wert, kein Aufrufer überschreibt ihn, ein leerer oder ungültiger Wert lässt `Policy` nicht entstehen. Ein Pflicht-**Argument** ohne Vorgabe wäre F1 Option 2.
- **A2:** „Abstand je Host aus der Seed-Datei“ (`adr/0025` §6.2): `gateway` nimmt die Werte nur entgegen; das Lesen der Seed-Datei ist M5-19.
- **A3:** RFC 9309 will mindestens 5 Weiterleitungen für `robots.txt`; `gateway` bleibt bei 3 und der Allowlist, weil die Grenze aus `adr/0005` §6 für alle Anfragen gilt. Mehr als 3 oder ein Ziel außerhalb gilt als „nicht erreichbar“, also ruht der Host. Das ist die vorsichtige Seite.
- **A4:** `429` auf `robots.txt` behandelt `gateway` wie `5xx` (Host ruht), nicht wie ein übriges `4xx` (alles erlaubt). RFC 9309 nennt `429` nicht eigens [S]; ein Host, der uns gerade bremst, soll nicht als „alles erlaubt“ gelten.
- **A5:** „Einmal je Lauf“ = einmal je `Gateway`-Objekt und Host, höchstens 24 h.

---

## 6. Doku mit der Umsetzung

- `architekturplan.md` 6.5: ein Satz zu `User-Agent`, Abstand und `robots.txt` im `gateway`.
- `docs/ENTSCHEIDUNGSLOG.md`: Zeile mit Ottos Antworten, dann Zeile zur Umsetzung.
- Kein Nachtrag an `adr/0025`: §6.2 und §12 beschreiben das schon.

---

## 7. Umfang und Schnitt

Geschätzt [A]: `policy.py` ~50, `client.py` ~60, neues `gateway/robots.py` ~110, `errors.py` ~15, `gdal.py`/Geocoder ~10; Tests ~300. Zusammen rund 550 Zeilen, über dem Richtwert von 400; daher F6.

Commits (je eine Sache): (1) `User-Agent` in `Policy`, Client und GDAL; (2) Geocoder nutzt ihn; (3) Abstand je Host; (4) Parser `robots.txt`; (5) Abruf und Cache im Client; (6) Doku und Log.

---

## 8. Fragen an Otto — beantwortet am 06.11.2026 (§8a)

**F1 — Form des `User-Agent` in `Policy`?**
1. Feld mit Vorgabe `EarthX/0.1 (+https://github.com/oscipal/earthX)`, geprüft, nicht überschreibbar; Geocoder gibt seinen Wert aus `EARTHX_GEOCODER_USER_AGENT` in seine Policy; 76 Aufrufstellen bleiben **(Empfehlung)**
2. Pflichtargument ohne Vorgabe; alle 76 Aufrufstellen nennen den Wert (rund 80 Zeilen mehr, fast nur Tests)
3. Wie 1, dazu eine neue Umgebungsvariable `EARTHX_USER_AGENT` für alle Prozesse

**F2 — Abstand je Host: Vorgabe?**
1. Vorgabe `0` (wie heute), Werte je Host nur vom Harvester aus der Seed-Datei (M5-19) **(Empfehlung)**
2. Vorgabe 1 s für alle Aufrufer (bremst Kacheln und Suche spürbar)

**F3 — Parser für `robots.txt`?**
1. Eigener kleiner Parser nach RFC 9309 in `gateway/robots.py` (rund 110 Zeilen) **(Empfehlung)**
2. `urllib.robotparser` aus der Standardbibliothek: nicht RFC-9309-konform (erste statt längste Regel, kein `*` und `$` in Pfaden)
3. `protego` als neue Abhängigkeit (BSD-3-Clause, von Scrapy)

**F4 — Für wen gilt `robots.txt`?**
1. Schalter in `Policy`, Vorgabe aus; an nur beim Fetch der Kataloge im Harvester, nicht bei Verify und Health (`HEAD`/`Range` auf Assets) **(Empfehlung)**
2. Immer an, für alle Aufrufer (auch Suche, Kacheln, Runner; eine Sperre an einer Bucket-Wurzel hielte dann Lesen an)

**F5 — `Crawl-delay` (nicht in RFC 9309)?**
1. Beachten als Untergrenze des Abstands für diesen Host, höchstens 30 s; ein größerer Wert lässt den Host im Lauf ruhen **(Empfehlung)**
2. Nicht beachten; nur der Wert aus der Seed-Datei zählt

**F6 — Schnitt (rund 550 Zeilen, §7)?**
1. Ein PR mit getrennten Commits, knapp über dem Richtwert **(Empfehlung)**
2. Zwei PRs: `User-Agent` und Abstand hier, `robots.txt` als M5-18b

## 8a. Antworten Otto (06.11.2026)

F1–F6 jeweils **Option 1**, Auslegungen A1–A5 angenommen. Ergänzungen:

1. **Ein Wert je Instanz:** `EARTHX_USER_AGENT`, beim Start geprüft wie der Vorgabewert (kein Zeilenumbruch, kein `@`), Vorgabe `EarthX/0.1 (+https://github.com/oscipal/earthX)`. Kein Aufrufer überschreibt ihn. Eingetragen in §3.1.
2. **`EARTHX_GEOCODER_USER_AGENT`:** im Plan festlegen, was damit geschieht; Nominatim bekommt danach denselben Wert. Festgelegt in §3.1: Die Variable entfällt und geht in `EARTHX_USER_AGENT` auf.
