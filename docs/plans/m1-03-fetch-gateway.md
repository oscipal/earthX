# M1-03 — Fetch-Gateway: Umsetzungsplan

**Status:** **Von Otto angenommen am 19.09.2026** — F1 bis F4 alle wie empfohlen.
Stufe B laut `docs/plans/m1-fundament.md` §3: Plan zuerst, Umsetzung danach.
Die Umsetzung läuft in den drei PRs aus §8 F1.
**Aufgabe:** M1-03 aus `docs/plans/m1-fundament.md` §4.
**Grundlage:** `architekturplan.md` 3.1, 6.5; `KLAERUNGEN.md` B8, B9;
`adr/0001` §7 (Z8), §9.3; `adr/0004` §3.1, §3.4; `adr/0005` §3.2, §3.4, §3.5, §3.8, Regel IV.
**Voraussetzung:** M1-02 (erledigt) — `backend/earthx/` steht, die Importregel
„HTTP-Clients nur in `gateway`" gatet jeden PR.

---

## 1. Ziel in einem Satz

`earthx.gateway` ist die einzige Stelle, die entscheidet, ob eine URL abgerufen
werden darf, und die einzige, die selbst abruft — für eigene Requests mit einem
schmalen `httpx`-Client, für GDAL/rasterio mit einer Prüffunktion und der
zentralen GDAL-Konfiguration.

## 2. Aufbau des Moduls

Alles unter `backend/earthx/gateway/`. Keine Datenbank, keine Queue, kein
Objektspeicher — das Gateway läuft laut B9 auch im lokalen Runner mit.

| Datei | Zuständig für |
|---|---|
| `errors.py` | Fehlertypen (unten §4) |
| `policy.py` | `Policy` (Allowlist und Grenzwerte), Normalisierung und Prüfung einer URL ohne Netz |
| `resolver.py` | DNS-Auflösung und Einstufung der Adressen (privat, Loopback, Link-Local …) |
| `checks.py` | `check_url()` — die eine Prüffunktion, die Policy und Resolver zusammenzieht |
| `client.py` | `Gateway`: `httpx.AsyncClient` mit Zeit-, Größen- und Parallelitätsgrenzen, Backoff, eigener Redirect-Schleife |
| `gdal.py` | zentrale GDAL/VSI-Konfiguration (Z8), ohne Token |
| `__init__.py` | öffentliche Fläche: `Gateway`, `Policy`, `check_url`, `gdal_options`, Fehlertypen |

Die Allowlist wird **hineingereicht**, nicht im Gateway gesucht: `Policy` ist ein
Wert, den der Aufrufer baut. Bis M1-04 steht, baut ihn `policy_from_env()` aus
`EARTHX_ALLOWED_HOSTS` (kommagetrennt); ab M1-04 liefert ihn die
Datensatz-Registry. Eine leere Allowlist lehnt alles ab — wie im Prototyp
(`test_empty_allowlist_rejects_everything`).

**Tests** liegen unter `backend/tests/earthx/gateway/`. Async-Tests laufen über
das `pytest`-Plugin von `anyio`, das mit `httpx`/`starlette` ohnehin installiert
ist; eine neue Abhängigkeit ist dafür nicht nötig. HTTP-Verhalten wird mit
`httpx.MockTransport` geprüft, DNS über einen eingereichten Resolver — beides
ohne Netz, die Netzsperre aus `backend/tests/conftest.py` bleibt scharf.

## 3. Schnittstelle

```python
@dataclass(frozen=True)
class Policy:
    allowed_hosts: frozenset[str]
    max_url_bytes: int = 8192                 # adr/0004 §3.4
    max_response_bytes: int = 8 * 1024 * 1024 # adr/0005 §6
    max_connections_per_host: int = 6         # adr/0005 §6
    max_redirects: int = 3
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 15.0

def check_url(url: str, policy: Policy, *, resolve=resolve_host) -> CheckedUrl: ...
def gdal_options() -> dict[str, str]: ...

class Gateway:
    def __init__(self, policy: Policy, *, transport=None, resolve=resolve_host): ...
    async def get(self, url: str, *, params=None, headers=None) -> GatewayResponse: ...
    async def post_json(self, url: str, *, json, headers=None, retry: bool = False) -> GatewayResponse: ...
    async def aclose(self) -> None: ...
```

`GatewayResponse` ist ein eigener, schmaler Datentyp (`status_code`, `headers`,
`content`, `json()`). Damit bleibt `httpx` vollständig hinter der Naht — und
`304` (adr/0005 §3.4) ist eine gewöhnliche Antwort, kein Fehler.

`get()` nimmt `params` und baut die Abfragezeichenfolge selbst: `/aggregate` bei
Earth Search kennt kein POST (`adr/0004` §3.1), eine AOI muss also als langer
Query-Parameter durchgehen können.

## 4. Die Regeln und ihre Fehler

| Regel | Wert | Fehler | Quelle |
|---|---|---|---|
| Nur `https` | — | `UrlRejected` | architekturplan 6.5 |
| Host in der Allowlist, exakt oder als echte Subdomain | — | `UrlRejected` | B8 |
| Keine Zugangsdaten in der URL, kein Port außer 443 | — | `UrlRejected` | §5 |
| URL-Länge vor dem Absenden | 8 kB | `UrlTooLong` (trägt Länge und Grenze) | adr/0004 §3.4 |
| Keine private, Loopback-, Link-Local-, Multicast- oder reservierte Adresse | — | `AddressRejected` | architekturplan 6.5 |
| Redirects nur innerhalb der Allowlist, höchstens 3 | 3 | `UrlRejected` / `TooManyRedirects` | B8 |
| Antwortgröße je Rumpf | 8 MB | `ResponseTooLarge` | adr/0005 §6 |
| Parallele Verbindungen je Host | 6 | wartet, kein Fehler | adr/0005 §6 |
| Zeitgrenzen | 5 s verbinden, 15 s lesen | `UpstreamTimeout` | adr/0005 §3.2 (0,4–2,5 s gemessen) |
| Verbindung kommt gar nicht zustande | — | `UpstreamUnreachable` (Oberklasse von `UpstreamTimeout`) | in 03b ergänzt |
| Nicht-2xx nach den Wiederholungen | — | `UpstreamError` mit `status_code` und kurzem Auszug | adr/0005 §3.5 |

Alle Fehler erben von `GatewayError`. `UpstreamError` trägt den Statuscode
ungefälscht weiter — M1-06 muss `400`, `404` und `429` unterscheiden können,
genau das geht bei `pystac_client` verloren (`adr/0005` §3.8).

`UrlTooLong` ist der Fall, für den `adr/0004` §3.4 den Rückfall verlangt: Das
Gateway scheitert früh und nennt Länge und Grenze; die AOI vereinfacht der
Aufrufer (M1-06, Coverage in M2), und dessen Antwort weist das aus.

**Backoff:** höchstens 3 Versuche bei `429`, `502`, `503`, `504`,
Verbindungsfehler und Lesezeitüberschreitung; 0,5 / 1 / 2 s mit Streuung,
`Retry-After` wird beachtet (gedeckelt bei 10 s). Wiederholt wird nur `GET`;
`post_json()` nur, wenn der Aufrufer `retry=True` setzt — `POST /search` ist
fachlich ein Lesezugriff, das entscheidet aber der Aufrufer, nicht das Gateway.

**Logs:** eine Zeile je ausgehendem Request über den Standard-Logger
`earthx.gateway` mit Host, Methode, Pfad, Status, Dauer, Bytes, Versuch und
Redirect-Zahl. **Die Abfragezeichenfolge wird nie geloggt**, nur ihr gekürzter
Hash — dort steht die AOI (`projektplan.md` 7 Punkt 6). Das JSON-Format setzt
M1-01; das Gateway bringt keine eigene Logging-Konfiguration mit und hängt
damit nicht an M1-01.

## 5. Host-Normalisierung und SSRF

Der `endswith`-Fehler des Prototyps (`backend/tests/test_config.py`, `xfail`)
darf hier nicht wiederkehren. Der Prototyp behält seine Allowlist und seinen
`xfail` — `backend/app/` wird nicht angefasst.

**Vor dem Netz** (`policy.py`), rein textlich:

1. `urlsplit`; Schema muss `https` sein.
2. Benutzername oder Passwort in der URL → abgelehnt (`https://allowed@evil.tld`).
3. Port: nur leer oder 443.
4. Host: ASCII-Kleinschreibung; Nicht-ASCII wird IDNA-kodiert, schlägt das fehl,
   ist der Host abgelehnt; höchstens ein abschließender Punkt wird entfernt;
   leere Label und unzulässige Zeichen werden abgelehnt.
5. IP-Literale sind nie erlaubt — die Allowlist führt Namen. Das sperrt
   `169.254.169.254` (Cloud-Metadaten) und die dezimalen und hexadezimalen
   Schreibweisen mit.
6. Treffer nur bei `host == eintrag` oder `host.endswith("." + eintrag)`. Kein
   nacktes `endswith`.

**Mit dem Netz** (`resolver.py`): `getaddrinfo` liefert **alle** Adressen; jede
einzelne muss global routbar sein (`ipaddress`, IPv4-gemappte IPv6-Adressen
werden vorher ausgepackt). Eine einzige unzulässige Adresse lehnt den ganzen
Host ab — ein Name, der A-Record und 127.0.0.1 nebeneinander führt, kommt so
nicht durch.

**Redirects** führt `httpx` nicht selbst aus (`follow_redirects=False`); die
Schleife liegt im Gateway, und jeder Sprung durchläuft die volle Prüfung
erneut. Das ist genau der Punkt, an dem `pystac_client` scheitert
(`adr/0005` §3.8).

**Offen bleibt die Lücke zwischen Prüfung und Verbindung** (DNS-Rebinding). Sie
schließt sich, wenn das Gateway nicht den Namen, sondern die geprüfte Adresse
verbindet und Hostname nur für SNI und Zertifikatsprüfung mitgibt
(`extensions={"sni_hostname": …}` plus `Host`-Kopfzeile). Das ist Frage F2 in §8.
Bei GDAL bleibt die Lücke in jedem Fall offen: GDAL folgt Redirects selbst —
B8 sagt, dass erst die Netzwerk-Policy in M6 das schließt.

## 6. GDAL (Z8)

`gdal_options()` liefert die Konfiguration als reines `dict` — ohne `rasterio`
zu importieren, damit die Prüfung auch ohne GDAL testbar bleibt. Übernommen aus
`backend/app/cog.py`, **ohne** `GDAL_HTTP_HEADERS`: Token-Logik gehört laut
`ENTSCHEIDUNGEN` §3 nicht ins Gateway und nicht in die Zielarchitektur.
Dazu kommen Zeit- und Wiederholungsgrenzen (`GDAL_HTTP_TIMEOUT`,
`GDAL_HTTP_MAX_RETRY`, `GDAL_HTTP_RETRY_DELAY`).

Wer eine URL an rasterio gibt, ruft vorher `check_url()`. In M1-03 gibt es noch
keinen solchen Aufrufer — `readers` entsteht erst mit M2. Deshalb liefert
M1-03 die Prüffunktion und den Nachweis, dass sie greift; der Abnahmefall
„jede an rasterio übergebene URL hat `gateway` passiert" wird erst prüfbar,
wenn der erste Leser existiert. Das gehört so in den Abnahmebericht von M1-10.

## 7. Bewusst nicht in M1-03

| Was | Warum, und wann dann |
|---|---|
| Circuit Breaker | Der Plan erlaubt das ausdrücklich, wenn es begründet wird. Ein sinnvoller Breaker braucht Zustand über Prozessgrenzen (die `api`-Prozesse sind zustandslos und skalieren horizontal); der gemeinsame Speicher ist der Anwendungs-Cache in Postgres und kommt mit M1-04. In M1 tragen Parallelitätsdeckel und Backoff die Rücksicht auf die Quelle. Als Issue nach M1-04. |
| Request-Bündelung (architekturplan 6.5) | Ihr Anwendungsfall ist der gemeinsame COG-Header vieler Kacheln — Kacheln sind laut E3 M2. |
| Metriken je Host, Health-Status | In M1 gibt es die Logzeile je Request als Datengrundlage; Auswertung und Health-Status gehören zur Discovery-Ebene. |
| `s3://` für bekannte Buckets | In M1 liest nichts aus dem Objektspeicher (E6), `boto3` ist außerhalb von `gateway` ohnehin gesperrt. Frage F4 in §8. |
| Token, Zugangsdaten jeder Art | `ENTSCHEIDUNGEN` §3: Token-Logik ist nicht Teil des Gateways. |

## 8. Fragen an Otto — beantwortet am 19.09.2026

**Alle vier wie empfohlen entschieden:** drei PRs, die geprüfte Adresse verbinden,
Circuit Breaker auf ein Issue nach M1-04 vertagen, in M1 nur `https`.

**F1 — Schnitt.** Umsetzung und Tests liegen zusammen bei rund 900 Zeilen, der
Richtwert sind 400 je PR. Vorschlag: **drei PRs nacheinander**, jeder für sich
grün und abnehmbar.
1. **M1-03a** `errors.py`, `policy.py`, `resolver.py`, `checks.py` — alle Sperrregeln ohne HTTP (~350 Zeilen mit Tests).
2. **M1-03b** `client.py` — Zeit-, Größen-, Parallelitätsgrenzen, Backoff, Redirect-Schleife (~350 Zeilen mit Tests).
3. **M1-03c** `gdal.py`, der Wächtertest „kein ausgehender Request außerhalb des Gateways", Logzeile im Entscheidungslog (~150 Zeilen).

*Empfehlung: ja, drei PRs.* Alternative: ein PR über dem Richtwert.

**F2 — DNS-Rebinding.** Soll der Client die **geprüfte Adresse** verbinden statt
den Namen (§5, letzter Absatz)?
1. **Ja, gleich** — schließt die Lücke zwischen Prüfung und Verbindung; kostet
   wenige Zeilen, aber die Zertifikatsprüfung über `sni_hostname` ist in der
   Umsetzung erst nachzuweisen.
2. Nein, erst mit der Netzwerk-Policy in M6 (B8 sieht die Durchsetzung dort vor).

*Empfehlung: 1.* Das Gateway ist bis M6 die einzige Durchsetzung.

**F3 — Circuit Breaker.** Wie in §7 vorgeschlagen auf ein Issue nach M1-04
vertagen (1), oder in M1-03 prozesslokal bauen (2)?
*Empfehlung: 1,* mit einer Zeile im Entscheidungslog.

**F4 — `s3://`.** `architekturplan.md` 6.5 nennt „nur `https` (und `s3` für
bekannte Buckets)". In M1 braucht es kein `s3`.
1. **Nur `https` in M1**, `s3` wenn der erste Leser es braucht (M2).
2. `s3` gleich mitbauen.

*Empfehlung: 1.*

## 9. Tests (Abnahme)

Je eine Prüfung, ohne Netz, mit eingereichtem Resolver und `MockTransport`:

| Gruppe | Fälle |
|---|---|
| Schema | `http`, `file`, `ftp`, schemalos, leer |
| Allowlist | exakter Treffer; echte Subdomain; `evilearth-search.…` (der `endswith`-Fehler); `…element84.com.evil.tld`; Großschreibung; abschließender Punkt; leere Allowlist lehnt alles ab |
| URL-Form | Zugangsdaten in der URL; Port 8443; IPv4-Literal; IPv6-Literal; `0x7f.0.0.1`; `2130706433`; IDNA-Homograph |
| DNS | Name löst auf 127.0.0.1, 10.0.0.1, 169.254.169.254, `::1`, `::ffff:127.0.0.1` auf; ein Name mit einer globalen **und** einer privaten Adresse wird abgelehnt |
| Redirects | Ziel außerhalb der Allowlist; Ziel mit `http`; Ziel mit privater Adresse; Kette länger als 3 |
| Grenzen | URL knapp unter und knapp über 8 kB; Rumpf knapp über 8 MB (auch komprimiert gesendet); Lesezeitüberschreitung; siebter gleichzeitiger Request wartet |
| Fehlerformen | `400`, `404`, `429` mit `Retry-After`, `503` → Statuscode bleibt erhalten; `304` ist kein Fehler |
| Backoff | `503` dann `200` ergibt eine Antwort; dreimal `503` ergibt `UpstreamError`; `POST` ohne `retry=True` wird nicht wiederholt |
| Logs | kein Query-String in der Logzeile, auch nicht bei einer Fehlermeldung mit AOI |
| GDAL | `gdal_options()` enthält kein `GDAL_HTTP_HEADERS` und keinen Token |
| Wächter | kein Modul unter `backend/earthx/` außerhalb `gateway` importiert `httpx`, `requests`, `urllib`, `aiohttp`, `pystac_client` oder `boto3` — auch nicht innerhalb einer Funktion |

## 10. Risiken

| Risiko | Umgang |
|---|---|
| `sni_hostname` prüft das Zertifikat nicht wie erwartet (F2) | In M1-03b mit einem Test belegen; hält es nicht, fällt F2 auf Option 2 zurück und das wird im PR benannt |
| Die Sperrregeln sperren später eine legitime Quelle aus (z. B. Redirect auf eine CDN-Domain) | Fehlertypen benennen den Grund; die Allowlist kommt mit M1-04 aus der Registry, nicht aus Code |
| Drei PRs statt einem verlängern den Review-Stau | Jeder PR ist für sich klein; M1-03a und M1-03b sind unabhängig prüfbar |
