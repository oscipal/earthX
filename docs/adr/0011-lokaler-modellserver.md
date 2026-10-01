# ADR 0011 — Lokaler Modellserver für den Chatbot (Ollama über localhost)

**Status:** Entwurf, wartet auf Otto (Lockerung einer Sicherheitsregel, CLAUDE.md)
**Datum:** 2026-10-01
**Kontext-Dokumente:** `plans/m7a-chatbot-lesewerkzeuge.md` §9, §10; KLAERUNGEN B8;
`gateway/policy.py`, `gateway/resolver.py`

## 1. Kontext

Víctor will für den Chatbot vorerst ein freies, kommerziell nutzbares Modell, das
lokal läuft. Umgesetzt ist Qwen3-8B im Prozess über `llama-cpp-python` 0.3.19
(plan §10). Für Windows gibt es diese Version nur als CPU-Paket; ein
Dialog mit zwei Runden dauerte gemessen 7 Minuten. Die RTX 3050 (4 GB VRAM) des
Entwicklungsrechners bleibt ungenutzt.

Ollama bringt CUDA fertig mit und verteilt ein Modell, das nicht ganz in den
VRAM passt, auf GPU und CPU. Es läuft aber als Server auf `http://127.0.0.1:11434`.
Das Gateway lässt nur `https`, Namen auf der Allowlist und global routbare
Adressen zu (`policy.py`, `resolver.py`). Loopback ist also gesperrt, und F5 des
Plans hat eine `localhost`-Ausnahme ausdrücklich ausgeschlossen.

## 2. Optionen

**A. Eng begrenzte Loopback-Ausnahme für einen lokalen Modellserver.**
Ein eigener Policy-Wert im Gateway, z. B. `local_model_endpoint`, erlaubt genau
eine Adresse: Schema `http`, Host `127.0.0.1`, ein fester Port, ein fester Pfad
(`/api/chat`). Er wird nur vom Einmalbefehl `python -m earthx.chatbot` gesetzt,
nie aus der Registry oder der Umgebung des API-Prozesses. Alle anderen Regeln
(Allowlist, Größenlimits, keine Redirects auf andere Hosts) gelten weiter. Ein
Test stellt sicher, dass `policy_from_env` und die Registry diesen Wert nie setzen.

**B. `llama-cpp-python` mit CUDA selbst bauen.** Keine Ausnahme nötig. Dafür
müssen Visual Studio Build Tools und das CUDA Toolkit auf jedem Entwicklungsrechner
installiert werden, mehrere GB. Der Build kann scheitern und ist an die Maschine
gebunden.

**C. Auf der CPU bleiben.** Nichts ändert sich, dafür bleibt der Chatbot zu langsam,
um ihn sinnvoll auszuprobieren.

## 3. Kriterien

| | A | B | C |
|---|---|---|---|
| Sicherheitsregel gelockert | eng, nur Entwicklungsbefehl | nein | nein |
| Aufwand pro Rechner | Ollama installieren | Build-Werkzeuge, ca. 1 h | keiner |
| Geschwindigkeit (geschätzt) | 2–4× schneller | 2–4× schneller | gemessen: 7 min für 2 Runden |
| Nähe zum späteren Betrieb | Modellserver als eigener Dienst | im Prozess | im Prozess |

## 4. Empfehlung

A, beschränkt auf den lokalen Entwicklungsbefehl. Im Cloud-Betrieb wäre ein
Modellserver ohnehin ein eigener Dienst. Dessen Anbindung ist eine eigene
Entscheidung mit M6 und folgt nicht aus diesem ADR.

## 5. Offene Fragen an Otto

1. Ist die Ausnahme nach A vertretbar, oder bleibt Loopback ausnahmslos gesperrt (dann B oder C)?
2. Falls A: Reicht der Test aus §2, oder soll die Ausnahme zusätzlich hinter einem
   eigenen Importvertrag stehen, sodass nur `earthx.chatbot.__main__` sie setzen kann?
