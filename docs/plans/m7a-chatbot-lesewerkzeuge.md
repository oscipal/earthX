# M7a (vorgezogen) — Chatbot-Backend mit Lesewerkzeugen: Plan

**Status:** Antworten von Víctor zu F1–F5 in §8 (24.09.2026), F2 am 30.09.2026 geändert (§9); Lesewerkzeuge, LLM-Client und Tool-Schleife lokal umgesetzt, Ottos OK steht aus. **Stufe B**
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

## 8. Antworten (Víctor, 24.09.2026)

- **F1:** (1) `earthx.chatbot`, importiert nur `gateway`. Dazu ein Vertragstest:
  `backend/tests/earthx/chatbot/test_contract.py` baut jede Collection der Registry
  mit `catalog.collection.to_stac_collection` und prüft, dass der Chatbot sie findet
  und die zugesagten Felder liest. Benennt der Katalog ein Feld um, schlägt das im
  selben PR fehl.
- **F2:** (2) Vorerst kein LLM. Umgesetzt sind nur die drei Werkzeuge, dazu
  `TOOL_SPECS` (JSON-Schema) und `call_tool`, das jeden falschen Aufruf als
  `error` beantwortet. Das LLM und die Tool-Schleife aus §4 folgen später.
- **F3:** (1) Eigener schmaler Client über `gateway`, wenn das LLM kommt.
- **F4:** Code lokal auf dem Branch, ohne Push, zum Ausprobieren.
- **F5:** (1) Policy bleibt. `python -m earthx.chatbot` läuft nur gegen eine
  öffentliche https-Adresse; lokale Adressen werden abgewiesen.

Abweichung von §2: `check_availability` schickt nur `bbox`, kein `intersects`,
weil `post_search` der föderierten Suche nur `bbox` weiterreicht
(`api/federating_client.py`). Eine Box über den Antimeridian wird abgewiesen.

## 9. Nachtrag: LLM angebunden (Víctor, 30.09.2026)

Víctor hat die Empfehlungen aus §7 bestätigt, F2 jetzt mit Option (1): Claude
Sonnet über die Messages-API. Umgesetzt wie in §4:

- `earthx.chatbot.llm`: schmaler Client auf `Gateway.post_json`, ohne SDK.
  Modellname aus `EARTHX_CHATBOT_MODEL`, Schlüssel aus `ANTHROPIC_API_KEY`,
  beide nur in der lokalen Umgebung. Das Gateway für das Modell erlaubt nur den
  Host der Messages-API; weil eine Antwort mit Werkzeugrunden länger dauert als
  eine STAC-Seite, bekommt diese eine Policy 120 s Lesezeit statt 15 s. Sonst
  gelten die Grenzen der Policy unverändert.
- `anthropic` steht als Verbot in `http-only-in-gateway` und in der
  AST-Prüfung von `test_no_outbound_outside_gateway.py`.
- `earthx.chatbot.dialogue`: eine Dialogrunde, zustandslos. Höchstens 6
  Werkzeugrunden, danach eine Antwort mit `tool_choice: none`. Werkzeugergebnisse
  gehen als JSON im `tool_result`, gekürzt auf 20 000 Zeichen. Der Systemprompt
  verlangt Rückfragen und erklärt Werkzeugergebnisse zu Daten.
- CLI: `python -m earthx.chatbot chat ["Frage"]`, ohne Frage ein Dialog auf
  stdin; der Verlauf lebt nur im Prozess.
- Tests offline mit Stub-Modell und synthetischer API (`test_llm.py`,
  `test_dialogue.py`, `test_cli.py`); kein Test ruft ein echtes Modell auf.

## 10. Nachtrag: lokales Open-Weight-Modell (Víctor, 01.10.2026)

Víctor möchte vorerst ein freies, herunterladbares und kommerziell nutzbares Modell.
Gewählt: Qwen3-8B (Apache 2.0 laut Model Card von Qwen; Einstufung durch Otto
steht aus), im Prozess über `llama-cpp-python` 0.3.19, weil es für Windows nur bis
dahin fertige Pakete gibt und Qwen3.5 eine neuere Laufzeit bräuchte.

- `earthx.chatbot.local.LocalModel`: dieselbe `ChatModel`-Schnittstelle. Übersetzt
  das Transkript in Chat-Nachrichten und die `<tool_call>`-Ausgabe des Modells
  zurück in `tool_use`-Blöcke. Lädt nur eine lokale GGUF-Datei, öffnet keine
  Verbindung; die Gateway-Regeln bleiben unberührt.
- Gewählt per `EARTHX_CHATBOT_LOCAL_MODEL` (Pfad zur Datei); ohne sie bleibt
  Claude der Weg.
- `llama-cpp-python` ist eine optionale lokale Abhängigkeit, nicht in den
  requirements.
- Messung am 02.10.2026, derselbe Dialog mit zwei Runden gegen Earth Search:
  CPU-Paket 0.3.19 7 min 3 s; selbst gebaut mit CUDA 12.9 und
  `EARTHX_CHATBOT_GPU_LAYERS=20` auf der RTX 3050 (4 GB) 1 min 30 s. Qwen3-8B
  fragt sinnvoll nach und findet `sentinel-1-grd`, ruft `check_availability`
  aber nicht von sich aus auf und deutet „proprietary“ als kostenpflichtig.
- 06.10.2026: Qwen3-8B schreibt einen Aufruf gelegentlich in `<tools>` statt
  `<tool_call>` (das Tag, mit dem sein Template die Werkzeugliste umschließt);
  `LocalModel` liest beide als Aufruf. Ab und zu kündigt es eine Suche an, ohne
  sie aufzurufen; das fängt kein Parser ab.


## 11. Lokales Modell einrichten (06.10.2026)

Die Modelldatei kommt nicht ins Repo: Sie ist etwa 5 GB groß, und die
Lizenz-Einstufung von Qwen3-8B durch Otto steht aus (§10). Jede Person lädt sie
selbst. Einen lokalen Katalog-Index gibt es nicht: Das Modell liest den Katalog bei
jeder Frage live über die drei Lesewerkzeuge und `gateway` aus der STAC-API in
`EARTHX_CHATBOT_STAC_URL`; mit derselben URL sieht jeder Rechner dieselben Datensätze.

1. `Qwen3-8B-Q4_K_M.gguf` aus dem Hugging-Face-Repo `Qwen/Qwen3-8B-GGUF` laden,
   z. B. nach `%USERPROFILE%\models\`.
2. In der `.venv` des Repos die Laufzeit installieren:
   - nur CPU: `pip install llama-cpp-python==0.3.19` (eine Antwort mit zwei
     Werkzeugrunden etwa 7 min);
   - mit NVIDIA-GPU (adr/0011 §6): VS Build Tools 2022 und CUDA Toolkit 12.9
     installieren, dann in PowerShell
     `$env:CMAKE_ARGS="-DGGML_CUDA=on"; pip install llama-cpp-python==0.3.19 --no-cache-dir --force-reinstall`
     (etwa 1–2 min pro Antwort mit `EARTHX_CHATBOT_GPU_LAYERS=20` auf 4 GB VRAM).
3. Umgebung setzen und aus dem Repo-Wurzelverzeichnis starten (PowerShell):

   ```powershell
   $env:PYTHONPATH = "backend"
   $env:EARTHX_CHATBOT_STAC_URL = "https://earth-search.aws.element84.com/v1"
   $env:EARTHX_CHATBOT_LOCAL_MODEL = "$env:USERPROFILE\models\Qwen3-8B-Q4_K_M.gguf"
   $env:EARTHX_CHATBOT_GPU_LAYERS = "20"   # nur mit CUDA-Build; -1 alle Schichten
   .venv/Scripts/python.exe -m earthx.chatbot chat
   ```

   Findet der CUDA-Build seine DLLs nicht, vorher
   `$env:PATH = "$env:CUDA_PATH\bin;$env:PATH"` setzen.

Die Zeile `llama_context: n_ctx_seq (16384) < n_ctx_train (40960)` beim Laden ist
nur ein Hinweis: `LocalModel` nutzt absichtlich 16k Token Kontext.