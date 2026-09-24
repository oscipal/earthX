# M7a (vorgezogen) — Chatbot-Backend mit Lesewerkzeugen: Plan

**Status:** Entwurf, wartet auf Antworten zu F1–F5 (§7). **Stufe B**
(`projektplan.md` 1.2): neues Modul, Plan zuerst, Umsetzung nach OK.
**Aufgabe:** kleines Chatbot-Backend mit den Lesewerkzeugen
`search_collections`, `get_collection` und `check_availability` gegen die
öffentliche API, laut `architekturplan.md` 8.3. Es empfiehlt nur, startet
keine Jobs und stellt Rückfragen.
**Grundlage:** `architekturplan.md` 0 (Punkt 5, ein Tor nach außen), 3.1
(Modulgrenzen), 8.1 (API-first), 8.3 (Chatbot); `projektuebersicht.md`
Prinzip 7 („Der Chatbot hat keine Sonderrechte"), §10, Sicherheitsabschnitt
(externe Inhalte sind für das LLM Daten, nie Anweisungen); `projektplan.md`
3.4 (Sonnet für Chatbot Free, Modellnamen nur in der Konfiguration), M7
Paket 7a; KLAERUNGEN B8 (Gateway).

**Einordnung:** Laut `projektplan.md` ist der Chatbot Paket 7a mit den
Voraussetzungen M5 (Hybrid-Suche) und M6 (Identität, AV-Vertrag mit dem
LLM-Anbieter). Dieser Plan zieht nur den schmalen, lesenden Teil vor. Die
semantische Suche und das Re-Ranking aus 8.3 fehlen, bis M5 sie liefert;
bis dahin sucht `search_collections` über Freitext und Filter der STAC-API.

---

## 1. Ziel in einem Satz

Ein zustandsloses Modul beantwortet eine Nutzerfrage im Dialog: Es fragt nach,
was fehlt (Thema, Raum, Zeit, Format, Lizenz), ruft dazu nur die drei
Lesewerkzeuge über die öffentliche STAC-API auf und gibt eine begründete
Empfehlung mit Lizenz- und Verfügbarkeitshinweis zurück.

## 2. Abbildung der Werkzeuge auf die öffentliche API

| Werkzeug | Aufruf | Rückgabe an das Modell |
|---|---|---|
| `search_collections(query, bbox?, datetime?, limit?)` | `GET /stac/collections`, lokal gefiltert über Titel, Beschreibung, Keywords, räumliche und zeitliche Ausdehnung | Liste aus `id`, `title`, Kurzbeschreibung, Lizenz, Ausdehnung |
| `get_collection(collection_id)` | `GET /stac/collections/{id}` | Titel, Beschreibung, Lizenz, Ausdehnung, Keywords, Provider, `earthx:`-Felder |
| `check_availability(collection_id, aoi, datetime)` | `POST /stac/search` mit `collections`, `intersects` bzw. `bbox`, `datetime`, kleinem `limit` | Anzahl gefundener Items (`numberMatched`, sonst „mindestens n“), frühestes und spätestes Datum der Stichprobe |

Die Collection-Suche filtert lokal, weil die API die Erweiterung
`collection-search` heute nicht anbietet (`api/main.py`, `_ENABLED_EXTENSIONS`).
Bei drei Datensätzen reicht das. Mit M5 wird das Werkzeug auf die Hybrid-Suche
umgestellt, die Signatur bleibt dieselbe.

`propose_recipe` und `estimate_cost` aus 8.3 fehlen bewusst: Sie brauchen das
Rezept aus M4. Ein Werkzeug, das Jobs startet, gibt es nicht.

## 3. Modul und Importregeln (F1)

Neues Modul `earthx.chatbot`, das nur `gateway` importieren darf. Es spricht
mit der Plattform ausschließlich über HTTP gegen die öffentliche API, nie über
`catalog` oder `api` im Prozess. So bleibt Prinzip 7 prüfbar: Ein Import aus
`catalog` wäre schon ein Sonderrecht.

Dazu kommen:
- eine Zeile in der Tabelle von `architekturplan.md` 3.1,
- ein Vertrag `chatbot` in `.importlinter`, der alle anderen Module verbietet,
- `earthx.chatbot` als Quellmodul in `http-only-in-gateway` und
  `datasets-isolated`,
- die Anpassung von `backend/tests/test_module_boundaries.py`.

Das verschärft die Regeln, es lockert keine.

## 4. LLM-Anbindung (F2, F3)

- Modell laut `projektplan.md` 3.4: Sonnet. Der Modellname steht nur in der
  Konfiguration (`EARTHX_CHATBOT_MODEL`), der API-Schlüssel nur in der Umgebung.
- Der Aufruf der Messages-API geht über einen schmalen eigenen Client auf
  `gateway` (`Gateway.post_json`), ohne das Anthropic-SDK. Das SDK öffnet
  Verbindungen selbst und folgt Redirects ungeprüft, also derselbe Grund, aus
  dem `adr/0005` Regel IV `pystac_client` ausschließt. `anthropic` käme als
  weiteres Verbot in `http-only-in-gateway`.
- Die Tool-Schleife ist klein: Nachricht senden, `tool_use`-Blöcke ausführen,
  `tool_result` zurückgeben, bis `stop_reason` nicht mehr `tool_use` ist.
  Höchstens eine feste Anzahl Runden (Vorschlag: 6), danach eine Antwort ohne
  Werkzeuge.
- Werkzeugergebnisse gehen als Daten an das Modell, eingerahmt und gekürzt.
  Der Systemprompt sagt ausdrücklich, dass Text aus Werkzeugergebnissen keine
  Anweisung ist (Sicherheitsabschnitt der Projektübersicht).

## 5. Rückfragen und Zustand

Das Modul hält keinen Zustand. Der Aufrufer schickt den bisherigen Dialog mit
jeder Anfrage mit. Der Systemprompt verlangt Rückfragen, bevor eine Empfehlung
kommt, wenn Raum, Zeit oder Zweck fehlen. Eine Route im `api`-Prozess
(`POST /chat`) ist **nicht** Teil dieses Plans, weil sie die Frage nach
Login und AV-Vertrag berührt (`projektplan.md` M6). Stattdessen gibt es einen
Einmalbefehl `python -m earthx.chatbot` für die lokale Entwicklung.

## 6. Tests

Alle offline, nach `adr/0002`:
- jedes Werkzeug gegen aufgezeichnete, synthetische STAC-Antworten unter
  `backend/tests/fixtures/`: Treffer, kein Treffer, unbekannte Collection
  (404), kaputtes JSON, zu große Antwort, Timeout des Gateways;
- Eingabeprüfung: ungültige `bbox`, verdrehtes Zeitintervall, AOI außerhalb
  von −180…180/−90…90, fremde Werkzeugnamen und Argumente vom Modell;
- die Tool-Schleife mit einem Stub-Modell: Rückfrage ohne Werkzeug, eine
  Werkzeugrunde, Abbruch nach der Rundengrenze, Prompt-Injection in einer
  Collection-Beschreibung bleibt im `tool_result`;
- Importregeln: `lint-imports` und `test_module_boundaries.py`.

Kein Test ruft ein echtes LLM auf. Ein Live-Test käme unter `tests_live` und
braucht einen Schlüssel, der in Cloud-Sitzungen nicht vorhanden ist.

Das Bewertungs-Set aus 8.3 gehört zu 7a und folgt mit M5.

## 7. Offene Fragen

**F1. Modul.** (1) Neues Modul `earthx.chatbot`, das nur `gateway`
importiert, wie in §3 beschrieben *(Empfehlung)*. (2) Ein eigenes Paket
außerhalb von `earthx`.

**F2. LLM.** (1) Claude Sonnet über die Anthropic-API, Modellname nur in der
Konfiguration *(Empfehlung, entspricht `projektplan.md` 3.4)*. (2) Vorerst
kein LLM, nur die Werkzeuge plus der dünne MCP-Server aus 8.3.

**F3. LLM-Aufruf und Gateway.** (1) Eigener schmaler Client über `gateway`,
ohne SDK *(Empfehlung)*. (2) SDK mit dem httpx-Client aus `gateway`; das
lockert `http-only-in-gateway` und geht nur mit Otto.

**F4. Zeitpunkt.** (1) Plan jetzt als Draft-PR, Umsetzung nach OK
*(Empfehlung)*. (2) Plan und Code zusammen.

**F5. API-Adresse in der Entwicklung.** `gateway` lässt nur `https` und
global routbare Adressen zu (`policy.py`, `resolver.py`). Die lokale API aus
compose (`http://localhost:...`) ist damit nicht erreichbar. (1) Die Tests
nutzen die vorhandenen Parameter `transport` und `resolve` von `Gateway`, ohne
Netz; lokal läuft der Einmalbefehl gegen eine `https`-Adresse der API, die
Policy bleibt unverändert *(Empfehlung)*. (2) Eine Ausnahme für `localhost` in
der Policy; das lockert eine Sicherheitsregel und geht nur mit Otto.
