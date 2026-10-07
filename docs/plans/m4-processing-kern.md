# M4 — Processing-Kern mit lokalem Runner: Aufgabenschnitt

**Status:** Fassung 2 vom 05.10.2026. Fassung 1 (02.10.2026) hat M4-00 bis
M4-05 beschrieben; nach der Annahme von `adr/0013`, `adr/0014` und `adr/0015`
schneidet Fassung 2 die Umsetzungsaufgaben von M4a (M4-06 bis M4-15) aus und
trifft dafür die Entscheidungen R1–R6 (§1.1b). M4b (M4-16 bis M4-19) bleibt im
Umriss bis nach `adr/0016`. Wo eine erledigte Aufgabe anders umgesetzt wird als
hier beschrieben, gilt das Log.
**Ort im Repo:** `docs/plans/m4-processing-kern.md`
**Grundlagen:** `projektplan.md` 4 (M4), 6.1, 10; `architekturplan.md` 3.1,
3.2, 6.1, 6.3, 6.4, 6.5, 7, 12.1, 12.3, 15.1, 15.2; `adr/0001` §9.2 (Ablauf),
`adr/0002` (Tests), `adr/0006` (Kachel-Pfad, Mosaik), `adr/0011`
(Adapter-Interface, §6, §7, §8.1), `adr/0012` (Objektspeicher, §7.3, §9, F3, F5), `adr/0013` (Job-Queue),
`adr/0014` (Rezept und Operator-Registry), `adr/0015` (Weg zum Objektspeicher);
`KLAERUNGEN.md` B8–B13; `projektuebersicht.md` §5 (Onboarding-Checkliste);
`plans/m3-dritte-quelle-und-interface.md` (P11, P19, P20, „Nicht in M3“);
`plans/m3-15-abnahme.md` §12 („Nach M3 vorgemerkt“); `ENTSCHEIDUNGSLOG.md`, Zeilen
ab dem 30.09.2026, besonders „M4 Q2“ bis „M4 Q16“ vom 02.10.2026 und „M4 Fassung 2“ vom
05.10.2026.

Eine Sitzung startet eine Aufgabe mit: „Führe Aufgabe M4-xx aus
`docs/plans/m4-processing-kern.md` aus.“ Jede Aufgabe ist ohne das
Planungsgespräch verständlich und endet mit genau einem Draft-PR. Aufgaben mit
Buchstaben (M4-00b, M4-01a …) sind je eine eigene Session und ein eigener PR.

---

## 0. Ziel in einem Satz

Ein Rezept beschreibt eine Verarbeitung so vollständig, dass dieselbe
Operator-Implementierung es als Vorschau im `tiler`, als Job im `worker` und
offline im lokalen Runner mit übereinstimmendem Ergebnis ausführt; ein zweiter
identischer Auftrag kommt aus dem Cache.

---

## 1. Vor dem Start

### 1.1 Bereits entschieden (Otto, Log)

| # | Entscheidung | wirkt auf |
|---|---|---|
| Q1 | **Erste Schritte nach `adr/0011`** (30.09.2026, F7): M4-01a Zugriffsauflösung nach `access` und eine Item-Quelle in `api`; M4-01b `AdapterSpec`, Signaturen mit `DatasetConfig`, Fehlerklassen, `harvest_run` entfernen | M4-01a, M4-01b |
| Q2 | **Schnitt:** M4a ist der Kern (M4-00 bis M4-15), M4b der Ausbau (M4-16 bis M4-19). Die Abnahme kommt einmal am Ende (M4-20) | alle |
| Q3 | **Feste ADR-Nummern**, alle Stufe C mit Recherche und Quellen: `adr/0013` Job-Queue (M4-02), `adr/0014` Rezept und Operator-Registry (M4-03), `adr/0015` Weg zum Objektspeicher (M4-04), `adr/0016` lokaler Runner (M4-05) | M4-02 bis M4-05 |
| Q4 | **Worker-Kern und Queue:** Das psycopg-Verbot (`no-database-in-worker-core`) bleibt für `processing`, den Worker-Kern. `jobs` ist die Hülle mit Queue und Datenbank und darf psycopg. Das ist eine Lockerung einer Importregel und von Otto entschieden; die Vertragsform schlägt `adr/0013` vor | M4-02, M4-08 |
| Q5 | **Weg zum Objektspeicher** (`adr/0012` F5): ein eigenes Modul für Plattformdienste mit festem Endpunkt aus der Konfiguration und eigenem Importvertrag; nur `jobs` und `api` dürfen es importieren. `gateway` bleibt unverändert (nur `https`, nur öffentliche Adressen). Name, Client und Vertrag legt `adr/0015` fest | M4-04, M4-06 |
| Q6 | **Erste Operatoren:** Band-Math (T1 und T2) und Reprojektion/Resampling (T2). Weitere (Masking, Normalisierung) danach, je als Stufe-A-Aufgabe | M4-09, M4-10, M4-18 |
| Q7 | **Erste Jobs in M4a:** Export über dem synchronen Deckel (P20) und Mosaik ganzer Szenen je Überflug (P19). Mosaik im Kachel-Pfad (P11) in M4b | M4-11, M4-12, M4-17 |
| Q8 | **Kennungen:** Der Hash des kanonischen Rezepts ist nur intern Cache-Schlüssel. Nach außen (URLs, Job-IDs, Permalinks) gehen nur zufällige Kennungen, weil der Hash aus der AOI zurückrechenbar wäre (wie der Query-Hash in M3-16). Rezepte mit AOI gelten als personenbezogen und folgen der Frist aus Q10 | M4-03, M4-07, M4-08 |
| Q9 | **Zugriff ohne Konto bis M6:** Job-IDs sind nicht zu erraten; Ergebnisse bleiben privat und gehen nur über signierte URLs hinaus (`adr/0012` F3). Ein globaler Deckel für gleichzeitige Jobs schützt Plattform und Quellen, weil die Grenze je Host in `gateway` nur je Prozess gilt. Den Startwert schlägt `adr/0013` vor | M4-02, M4-08 |
| Q10 | **Ablauffrist** (E6): 7 Tage als Startwert für Job-Ergebnisse im Objektspeicher und für gespeicherte Rezepte, belegt durch einen Test des Ablaufs (`adr/0012` §9 Punkt 5) | M4-04, M4-06, M4-08 |
| Q11 | **Ergebnis-Cache:** ein Treffer nur, wenn alle Eingaben eine Fassung tragen (ETag des Assets oder `updated` am Item); sonst wird neu gerechnet. Lokal erzeugte Ergebnisse kommen nie in den gemeinsamen Cache | M4-03, M4-08, M4-16 |
| Q12 | **Lokaler Runner in M4:** nur offline mit Rezeptdatei; das Image wird lokal gebaut, mit festem Tag, und nicht in einer Registry veröffentlicht; Vergleichstest Cloud gegen lokal in der CI; Ergebnisse sind `self_attested` und kommen nicht in den Cache | M4-05, M4-16 |
| Q13 | **Synchroner Zuschnitt-Download:** Das ZIP bekommt zusätzlich `recipe.json` und `citation.bib`; den Inhalt legt `adr/0014` fest | M4-03, M4-14 |
| Q14 | **Onboarding-Checkliste Punkt 9, Fassung v2:** je Datensatz ein Operator-Lauf gegen Fixtures — Band-Math für `sentinel-2-c1-l2a` und `sentinel-2-l2a-zarr3`, Reprojektion für `cop-dem-glo-30`. Ersetzt Fassung v1 ab dem Merge von M4-15 | M4-03, M4-15 |
| Q15 | **Bug-Report Stufe 3** bleibt zusammen mit Stufe 2 vertagt (D9); M4 liefert nur die Rezept-ID als Grundlage | — |
| Q16 | **Vorlauf:** M4-00 Doku (Stufe A) und M4-00b Lock-Datei für die Backend-Pakete (Stufe B), bevor neue Abhängigkeiten landen | M4-00, M4-00b |

### 1.1b Entscheidungen zu Fassung 2 (Otto, 05.10.2026)

Grundlage sind die angenommenen ADRs `adr/0013`, `adr/0014` und `adr/0015`.
Wo diese Tabelle und ein ADR sich widersprechen, gilt die Tabelle; sie löst
genau die Stellen, an denen die ADRs nicht zusammenpassen oder der Schnitt
eine Wahl braucht.

| # | Entscheidung | wirkt auf |
|---|---|---|
| R1 | **Schnitt:** M4-07 zerfällt in M4-07a (Kern in `processing` und `readers`) und M4-07b (Annahme in `api`); M4-08 in M4-08a (Queue und Worker-Hülle in `jobs`) und M4-08b (Job-API und SSE in `api`). M4-09 ist Stufe B statt A, weil es den Kachel-Pfad, eine Pfad-Abhängigkeit für mehrere Assets und die Prüfung von Ausdrücken berührt | §3, M4-07a bis M4-09 |
| R2 | **Kettenvertrag für den Objektspeicher:** ein eigener Vertrag `no-object-store-in-worker-core` nach `adr/0015` §4.2 Punkt 4, nicht als Zusatz zu `no-database-in-worker-core` (Vorschlag in `adr/0013` §6.1). So ändern M4-06 und M4-08a getrennte Verträge, und der Umbau ist so gemessen, wie `adr/0015` ihn beschreibt | M4-06, M4-08a |
| R3 | **Flag `reprojection`** (`adr/0014` F6): alle drei Registry-Einträge setzen es ausdrücklich auf `true` (B10). `interpolation` bleibt, wie es heute je Eintrag steht | M4-07a, M4-10 |
| R4 | **`compose/objectstore/requirements-smoke.txt`** bekommt in M4-06 eine Lock-Datei nach dem Muster von M4-00b; das schließt die offene Zeile vom 02.10.2026 | M4-06 |
| R5 | **Band-Math-Ausdrücke:** erlaubt sind nur die Bandnamen des Rezepts, Zahlen, die Operatoren `+ - * / **`, Vergleiche, Klammern und eine feste Liste von numexpr-Funktionen; höchstens 256 Zeichen. Geprüft wird im Parametermodell, bevor numexpr den Ausdruck sieht. Die Funktionsliste schlägt M4-09 im Plan-Schritt vor. **Eingeengt am 2026-10-06 (`adr/0016` F8, `adr/0014` §15c):** In M4 erlaubt Band-Math nur bitstabile Funktionen: Grundrechenarten, Vergleiche, `where`, `abs`, `minimum`/`maximum`, `sqrt` und ganzzahlige Potenzen mit \|n\| ≤ 50, ausgewertet mit `optimization="aggressive"`. `log`, `exp`, Winkelfunktionen und gebrochene Potenzen folgen später mit eigener Toleranz | M4-09 |
| R6 | **Doppelzeile im Log:** Die Zeile „`adr/0014` §5.4, Auslegung zu F7a“ steht nach dem Merge von #114 und #115 zweimal. Die erste („Vorschlag“) bekommt in der Statusspalte den Verweis auf die zweite („fest am 2026-10-05“); gelöscht wird nichts | `ENTSCHEIDUNGSLOG.md` |

### 1.2 Was in allen Aufgaben gilt

`CLAUDE.md` gilt vollständig: ein Branch, ein Draft-PR, Tests für Fehlerfälle
und zweckfremde Nutzung, Fixtures nur synthetisch, keine exakten AOIs in Logs,
alles Ausgehende über `gateway`, `decomp.py` bleibt unberührt. Oberflächentexte
nur Englisch, keine Sprachwahl. Neue Registry-Felder ohne Vorgabewert (B10).
Was hier nicht entschieden ist, schlägt die Session im Plan-Schritt mit
nummerierten Optionen und Empfehlung vor und hält an. Vor dem Fertigmelden
`main` in den Branch holen; eigene Log-Zeilen ans Ende von
`ENTSCHEIDUNGSLOG.md`, alle anderen erhalten. Messungen an echten Quellen
gedrosselt (höchstens 1 Anfrage pro Sekunde), die Zahl der Anfragen steht im
Ergebnis. `gateway` erreicht die realen Quellen aus einer Session nicht
(`adr/0002`, Nachtrag M2-13); Erreichbarkeit wird per `curl` belegt.

Dazu für M4:

- **Worker-Kern ist `processing`:** keine Datenbank, keine Queue, kein
  Objektspeicher, keine interne API, kein Import aus `gateway`, auch nicht als
  Typ (3.1, B9, `adr/0011` §6.2). `processing` erreicht aus `catalog` nur
  `catalog.registry`; Registry-Einträge und Capability-Flags kommen über die
  übergebene `DatasetConfig` bzw. das Rezept herein. Plattformdienste nutzen nur
  `jobs` und `api` (Q4, Q5).
- **Nach außen kein Rezept-Hash und keine AOI** — weder in URLs noch in
  Job-IDs noch in Logs (Q8, M3-16).
- **Neue Abhängigkeiten** nach dem Merge von M4-00b nur mit erneuerter
  Lock-Datei im selben PR. Öffnet eine neue Bibliothek selbst Verbindungen nach
  außen, kommt sie auf die Verbotsliste von `http-only-in-gateway`, oder der PR
  belegt, dass jede URL durch `check_url` läuft (B8).
- **Rechenrelevante Festlegungen** (Bibliotheken, Chunking, Parallelität,
  Grenzwerte) nur mit Recherche und Quellen im PR oder ADR (`projektplan.md` 7
  Punkt 7).
- **ADR-Belegstufen** wie in `adr/0009`: [M] gemessen, [P] am Primärdokument
  gelesen, [S] Zusammenfassung, [A] eigene Ableitung.

**Stufe B heißt hier:** Der Plan liegt als `docs/plans/m4-xx-<kurzname>.md` im
Draft-PR, die Session hält an, Otto gibt frei, dann wird in derselben Session
umgesetzt.

### 1.3 Von Otto auszuführen

- **Vor dem Start der ersten Session:** diesen Plan und die Log-Zeilen vom
  02.10.2026 auf `main` bringen.
- **Vor M4-02 bis M4-05:** nichts vorab. Braucht eine Session einen gesperrten
  Host (Dokumentation, Release-Archiv), nennt sie ihn und hält an.
- **Nach M4-00b:** lokal einmal `docker compose build --no-cache`, weil das
  Image ab dann aus der Lock-Datei installiert.
- **Nach M4-02 bis M4-04:** die Fragen der ADRs beantworten; danach schneidet
  der Chat Fassung 2 dieses Plans.
- **Vor M4-06 (Fassung 2):** in `CLAUDE.md` die Zeile zu ausgehenden Requests
  um „einzige Ausnahme ist der eigene Objektspeicher über `earthx.objectstore`
  (KLAERUNGEN B8, Nachtrag, `adr/0015`)“ ergänzen. Die Datei ist geschützt;
  das macht nur Otto.
- **Nach M4-06 und nach M4-08a:** lokal `docker compose up -d --build`; die
  Prüfanleitung steht im jeweiligen PR. Nach M4-06 kommen neue
  Dienstschlüssel und Variablen hinzu, `.env` bleibt wie es ist.

---

## 2. Abgrenzung

**In M4a:** Vorlauf (Doku, Lock-Datei); Umbau nach `adr/0011`; ADRs zu Queue,
Rezept und Operator-Registry, Objektspeicher; Modul für Plattformdienste mit
signierten URLs und Ablauf; Rezept-Schema, Hash, Operator-Registry, Worker-Kern
als reine Funktion; Queue, `jobs`-Hülle, Job-API, Fortschritt, Ergebnis-Cache;
Operatoren Band-Math und Reprojektion/Resampling; Export über dem Deckel und
Mosaik ganzer Szenen als Jobs; Processing-Panel aus Schemas mit
Kostenschätzung, Vorschau und Job-Status; `recipe.json` und `citation.bib` im
Zuschnitt-ZIP; Checkliste Punkt 9 Fassung v2.

**In M4b:** ADR und Umsetzung des lokalen Runners (offline) mit Vergleichstest
in der CI; Mosaik im Kachel-Pfad; Masking und Normalisierung; Permalinks,
Methodentext, automatische Skalierung und Einheiten, „Parameter übernehmen“.

**Nicht in M4:** Datacube (bleibt M6, `projektplan.md` M6); Login, Quotas und
Ratenbegrenzung je Nutzer oder IP (M6, D6); verbundener Runner und
Runner-Auswahl in der Oberfläche (7f); Veröffentlichen des Runner-Images (Q12);
Container-Stufe T3 und externe Engines (M7); Bug-Report Stufe 2 und 3 (Q15);
Health-Checks, Harvester, Zählwürfel, STAC-API-Dialekt (M5, `adr/0011` F6);
COG-Header-Cache (Log offen); Uvicorn-Worker des `tiler` (M5); Registrieren des
Quad-Pol-Operators aus `decomp.py` (ruht, ENTSCHEIDUNGEN §3); alles zum ersten
öffentlichen Deployment (AGPL §13, Nutzungsbedingungen).

---

## 3. Übersicht und Reihenfolge

| ID | Aufgabe | Teil | Stufe | Modell (Effort) | hängt ab von | Stand |
|---|---|---|---|---|---|---|
| M4-00 | Doku nachziehen | M4a | A | Sonnet (mittel) | — | erledigt (#111) |
| M4-00b | Lock-Datei für die Backend-Pakete | M4a | B | Opus Plan, Sonnet (hoch) | — | erledigt (#113) |
| M4-01a | Zugriffsauflösung nach `access`, eine Item-Quelle in `api` | M4a | B | Opus Plan, Sonnet (hoch) | — | erledigt (#112) |
| M4-01b | `AdapterSpec`, Signaturen, Fehlerklassen, `harvest_run` entfernen | M4a | B | Opus Plan, Sonnet (hoch) | M4-01a | PR #122 |
| M4-02 | Spike Job-Queue → `adr/0013` | M4a | C | Opus (hoch) | — | erledigt, angenommen (#116) |
| M4-03 | Rezept und Operator-Registry → `adr/0014` | M4a | C | Opus (xhigh) | — | erledigt, angenommen (#114) |
| M4-04 | Weg zum Objektspeicher → `adr/0015` | M4a | C | Opus (hoch) | — | erledigt, angenommen (#115) |
| M4-05 | Lokaler Runner → `adr/0016` | M4b | C | Opus (hoch) | `adr/0014` | erledigt, angenommen (#121) |
| M4-06 | Modul `objectstore`: Client, signierte URLs, Schlüssel, Ablaufregel | M4a | B | Opus Plan, Sonnet (hoch) | `adr/0015` | in Arbeit (PR #119) |
| M4-07a | Kern: Rezept, Hash, Operator-Registry, Blockschleife, Lesen im Worker | M4a | B | Opus Plan, Sonnet (hoch) | `adr/0014` | PR #120 |
| M4-07b | Annahme in `api`: Auftrag → Rezept, Fassung, Host-Prüfung | M4a | B | Opus Plan, Sonnet (hoch) | M4-07a, M4-01b | PR #123 |
| M4-08a | Queue und Worker-Hülle in `jobs` | M4a | B | Opus Plan, Sonnet (hoch) | `adr/0013`, M4-06, M4-07a | PR #124 |
| M4-08b | Job-API (OGC-Form), Ergebnis-Links, SSE | M4a | B | Opus Plan, Sonnet (hoch) | M4-07b, M4-08a | offen |
| M4-09 | Operator Band-Math (T1, T2) | M4a | B | Opus Plan, Sonnet (hoch) | M4-07a | offen |
| M4-10 | Operator Reprojektion/Resampling (T2) | M4a | A | Sonnet (hoch) | M4-07a | erledigt (#125) |
| M4-10b | Nachbesserung M4-10: Spitzenspeicher von `reproject` unter 500 MB | M4a | A | Opus (hoch) | M4-10 | PR #126 (Entwurf) |
| M4-08a-fix | Nachbesserung M4-08a: Logtests prüfen Nachricht und Felder, nicht den Zeitstempel | M4a | A | Sonnet (hoch) | M4-08a | PR (Entwurf) |
| M4-11 | Export über dem Deckel als Job | M4a | B | Opus Plan, Sonnet (hoch) | M4-08b, M4-14 | offen |
| M4-12 | Mosaik ganzer Szenen je Überflug als Job | M4a | B | Opus Plan, Sonnet (hoch) | M4-08b, M4-10 | offen |
| M4-13 | Frontend: Processing-Panel, Kostenschätzung, Vorschau, Job-Status | M4a | B | Opus Plan, Sonnet (hoch) | M4-08b, M4-09 | offen |
| M4-14 | Zuschnitt-ZIP mit `recipe.json` und `citation.bib`, `sci:doi` | M4a | A | Sonnet (mittel) | M4-07b | offen |
| M4-15 | Onboarding-Checkliste Punkt 9, Fassung v2 | M4a | A | Sonnet (mittel) | M4-07b, M4-09, M4-10 | offen |
| M4-16 | Lokaler Runner offline, Vergleichstest in der CI | M4b | B | Opus Plan, Sonnet (hoch) | `adr/0016`, M4-08a | Umriss |
| M4-17 | Mosaik im Kachel-Pfad | M4b | B | Opus Plan, Sonnet (hoch) | M4-01a | Umriss |
| M4-18 | Operatoren Masking und Normalisierung | M4b | A | Sonnet (hoch) | M4-07a | Umriss |
| M4-19 | Permalinks, Methodentext, Skalierung und Einheiten, „Parameter übernehmen“ | M4b | B | Opus Plan, Sonnet (mittel) | M4-13 | Umriss |
| M4-20 | M4-Abnahme und README | — | A | Sonnet (mittel) | alle | offen |

**Wellen (Fassung 2).** Höchstens zwei Stufe-B-Sessions gleichzeitig; Stufe A
und C laufen daneben. Die Reihenfolge folgt dem kritischen Pfad
M4-07a → M4-08a → M4-08b → M4-13.

1. **Sofort:** M4-07a und M4-06 (die zwei B-Plätze); daneben M4-05 (C).
2. **Wird ein B-Platz frei:** M4-01b, danach M4-08a (braucht M4-06 und
   M4-07a). M4-10 (A) läuft, sobald M4-07a gemergt ist.
3. **Danach:** M4-07b (nach M4-01b) und M4-09; M4-14 (A) nach M4-07b.
4. **Danach:** M4-08b; dann M4-13, M4-11, M4-12; M4-15 (A), sobald M4-07b,
   M4-09 und M4-10 gemergt sind.
5. **M4b:** M4-16 nach Annahme von `adr/0016`; M4-17, M4-18 und M4-19 sobald
   B-Plätze frei sind. Ihr Zuschnitt wird nach `adr/0016` in Fassung 3
   geschärft.

**Dateikonflikte:**
- **Lock-Dateien:** M4-06 (`botocore`) und M4-07a (falls es eine direkte
  Abhängigkeit wie `rio-cogeo` braucht) ändern beide `requirements*.txt` und
  die Lock-Dateien. Wer als Zweiter gemergt wird, holt `main` und erzeugt die
  Lock-Dateien mit `scripts/lock-backend.sh` neu, statt Konflikte von Hand zu
  lösen.
- **`.importlinter` und `test_module_boundaries.py`:** M4-06 (Modul
  `objectstore`, R2) und M4-08a (Vertrag `no-database-in-worker-core`) ändern
  beide; M4-08a hängt an M4-06, also nacheinander.
- **`jobs/main.py`:** M4-06 (Prüfung der Ablaufregel beim Start) vor M4-08a
  (Aufseher).
- **`api`:** M4-01b, M4-07b, M4-08b und M4-09 (`api/tiler.py`) berühren
  `api`; die Abhängigkeiten oben ordnen sie. M4-09 und M4-07b berühren
  verschiedene Dateien und dürfen parallel laufen.
- **`architekturplan.md` 3.1:** M4-06 (Zeile `objectstore`) und M4-08a (Zeile
  `jobs`); nacheinander.

**Feste ADR-Nummern**, damit parallele Sessions nicht kollidieren:
`adr/0013-job-queue.md` (M4-02), `adr/0014-rezept-operator-registry.md`
(M4-03), `adr/0015-objektspeicher-zugang.md` (M4-04),
`adr/0016-lokaler-runner.md` (M4-05).

---

## 4. Die Aufgaben

### M4-00 — Doku nachziehen

**Ziel:** Die Plandokumente spiegeln Q1–Q16 und widersprechen dem Log nicht.
**Stufe A.** Nur `docs/`; kein Code.
**Umfang:**
- `projektplan.md`: Stand und Version 1.5.
  - M4-Tabelle: Verweis auf diesen Plan als maßgeblich, Teilung M4a/M4b (Q2).
    Den Inhalt um Export über dem Deckel als Job, Mosaik ganzer Szenen als Job,
    Mosaik im Kachel-Pfad und den Weg zum Objektspeicher ergänzen. Bei den
    Operatoren: „zuerst Band-Math und Reprojektion/Resampling, weitere danach“
    (Q6). „Deine Entscheidungen“: `adr/0013` bis `adr/0016`.
  - §10: „Adapter-Interface (ADR)“ als entschieden (`adr/0011`, 30.09.2026);
    „Job-Queue“ → wird mit `adr/0013` entschieden; „Status lokaler Ergebnisse“
    als entschieden (Q12).
  - §6.1, Ausbaustufe 3: vertagt mit Stufe 2 (Q15); M4 liefert nur die
    Rezept-ID. §5 entsprechend.
- `architekturplan.md`, nur Nachträge mit Datum, Originaltext stehen lassen:
  - 3.1: `jobs` darf die Datenbank, `processing` nicht (Q4); ein Modul für
    Plattformdienste kommt mit `adr/0015` (Q5).
  - 6.4: `recipe.json` und `citation.bib` im Zuschnitt-ZIP (Q13).
  - 6.5: „nur `https`“ (M1-03 F4) statt „und `s3` für bekannte Buckets“; der
    eigene Objektspeicher läuft nicht über `gateway` (Q5).
  - 7.1: Hash nur intern, nach außen zufällige Kennungen (Q8); Cache-Treffer
    nur mit Fassung aller Eingaben (Q11).
  - 7.7: In M4 nur offline mit Rezeptdatei, Image nicht veröffentlicht (Q12).
  - 12.3, Zeile „Ergebnis“: Q11 und Frist 7 Tage (Q10).
  - 15.1, Inkrement 4: erste Operatoren nach Q6.
- `projektuebersicht.md` §5 Punkt 9: Fassung v2 (Q14), mit dem Satz, dass sie
  ab dem Merge von M4-15 gilt und bis dahin Fassung v1.
- `KLAERUNGEN.md` B9: Nachtrag „Der Worker-Kern ist `processing`; `jobs` ist
  die Hülle mit Queue und Datenbank (Q4, 02.10.2026).“

**Nicht anfassen:** Code, `.github/`, `.claude/`, `CLAUDE.md`, ADRs,
`ENTSCHEIDUNGEN_2026-09-18.md`.
**Abnahme:** Jeder Punkt ist im Diff nachvollziehbar; keine bestehende
Log-Zeile gelöscht oder im Text geändert.

### M4-00b — Lock-Datei für die Backend-Pakete

**Ziel:** CI, Image und Cloud-Session installieren dieselben Versionen mit
Hashes; eine neue Veröffentlichung irgendwo im Abhängigkeitsbaum bricht nichts
mehr unbemerkt (Anlass: Installationsfehler `stac-fastapi.types` am 28.09.2026,
`plans/m3-15-abnahme.md` §12).
**Stufe B.**
**Umfang:**
- Lock-Dateien mit exakten Versionen und Hashes, erzeugt aus den bestehenden
  Anforderungsdateien, eingecheckt (Arbeitsnamen `backend/requirements.lock`,
  `backend/requirements-dev.lock`). Die `.txt`-Dateien bleiben die Eingabe.
- `.github/workflows/ci.yml`, `.github/workflows/live-smoke.yml`,
  `backend/Dockerfile` und `scripts/setup-cloud-session.sh` installieren mit
  `--require-hashes` aus der Lock-Datei. **Die Änderung an `.github/` ist für
  diese Aufgabe ausdrücklich erlaubt.** `.claude/settings.json` nur, falls der
  Hook-Eintrag sich ändern muss; dann im Plan-Schritt begründen.
- Ein Test (Muster: `test_frontend_deps_hook.py`) prüft ohne Netz, dass
  Lock-Datei und Anforderungsdateien zueinander passen.
- Erneuern der Lock-Datei ist ein eigener, bewusster PR; die Anleitung dazu
  steht in `README.md` bzw. `cloud-umgebung.md` §7.

**Im Plan-Schritt vorschlagen:** Werkzeug (z. B. `pip-tools` oder `uv`), mit
Quellen und Prüfung, dass es in der Session installierbar ist; welche
Plattformen die Lock-Datei abdecken muss (CI, Image, Session sind Linux x86_64;
ob Otto das Backend je außerhalb von Docker startet, als Frage).
**Nicht anfassen:** die Versionen der heute exakt gepinnten Pakete (`rio-tiler`,
`pypgstac`, `stac-fastapi.pgstac`, `titiler.core`, Kappe auf `zarr`) und den
Anwendungscode.
**Abnahme:** Pflicht-CI grün mit Installation aus der Lock-Datei; der Test fällt,
wenn eine Anforderung in der Lock-Datei fehlt (Gegenprobe im PR); die Wirkung
des SessionStart-Hooks ist in einer neu gestarteten Session belegt (wie M3-03
F4) oder als offen markiert.

### M4-01a — Zugriffsauflösung nach `access`, eine Item-Quelle in `api`

**Ziel:** `processing` kann Assets auflösen, ohne eine Importregel zu lockern,
und alle Wege holen Items über eine Stelle (`adr/0011` §6.4, §6.5 Punkte 1–2,
§7 D2; F2, F4).
**Stufe B.**
**Umfang:**
- `access/resolve.py`: `ResolvedAsset` (serialisierbar), `resolve_asset` (rein:
  kein Netz, keine Policy; Reader nach `format`, Zarr-Trenner, CRS, Abweisung
  eines Formats ohne Reader) und `open_asset_ref` (reicht `policy` und `resolve`
  an `readers.asset_path` bzw. `readers.zarr_asset` durch). `_target_gsd` zieht
  mit nach `access`.
- `readers` bekommt eine eigene Fehlerklasse (Vorschlag aus dem ADR:
  `AssetRejected(UrlRejected)`); `split_asset_key`, `asset_path` und
  `zarr_asset` werfen nur noch sie. `access` fängt die Klasse aus `readers`.
- `access` importiert aus `catalog` nur `catalog.registry`, aus `gateway`
  nichts, auch nicht als Typ.
- `api/tiler.py` ruft nur noch diese Funktionen auf.
- Die Item-Quelle zieht aus `api/tiler.py` in ein eigenes Modul in `api`,
  genutzt von Kachel, Download und `federating_client.get_item`. Das Routing
  „föderiert oder materialisiert“ liest die Python-Registry. `api` prüft beim
  Start, dass jede Collection in pgstac dieselbe `item_holding` trägt, sonst
  Start mit Fehler; der `tiler` prüft das nur mit Pool und startet ohne
  Datenbank wie heute (E5).

**Nicht in dieser Aufgabe:** Wer im Worker `Policy` und GDAL-Konfiguration baut
(`adr/0014`); Adapter-Signaturen (M4-01b).
**Nicht anfassen:** `.importlinter` (kein Vertrag wird gelockert),
Registry-Felder, Verhalten der Routen.
**Abnahme:** bestehende Tests zu Kachel und Download unverändert grün, auch die
Unterscheidung `400` (Schlüssel) gegen `502` (Item); reine Tests von
`resolve_asset` mit synthetischen Items für COG, Zarr und ein materialisiertes
Item; Hin- und Rückweg von `ResolvedAsset` über JSON; Test für den
Startabgleich (abweichende `item_holding` → Start scheitert); `lint-imports`
grün mit unveränderten Verträgen.

### M4-01b — `AdapterSpec`, Signaturen, Fehlerklassen, `harvest_run` entfernen

**Ziel:** Jede Quelle meldet ihre Fähigkeiten an einer Stelle; was fehlt, wird
abgewiesen (`adr/0011` §5, §6.5 Punkt 3; F1, F3, F5).
**Stufe B.** Neue Session nach dem Merge von M4-01a.
**Umfang:**
- `adapters/spec.py`: je Quelle ein `AdapterSpec` mit Suche, Einzelabruf,
  Materialisierung, Coverage-Wegen und Filter-Fähigkeiten; `None` heißt
  „ausdrücklich nicht vorhanden“ und führt zu einer definierten Abweisung.
- Signaturen nehmen die `DatasetConfig` statt `dataset_id` mit
  `registry=REGISTRY`; die DEM-Zeitkonstanten kommen aus
  `config.temporal_extent`. Regel I prüft der Dispatcher einmal.
- `adapters/errors.py` mit den gemeinsamen Fehlerklassen.
- `SourceInfo.harvest_run` entfällt in Registry, Collection-Abbildung, Tests und,
  falls genannt, `architekturplan.md` 5.1.
- Kein gemeinsames Modul für STAC-APIs (F6, M5).
- `coverage_route` bekommt die Registry aus `build_app(registry)`; in einer App
  gibt es danach nur eine Registry (Test).

**Nicht anfassen:** `access/resolve.py` (M4-01a), das Verhalten der Routen.
**Abnahme:** bestehende Routen-Tests grün; ein Test über jeden Registry-Eintrag,
dass jede Fähigkeit durch den `AdapterSpec` gedeckt oder ausdrücklich
abgewiesen ist; `harvest_run` kommt im Code nicht mehr vor;
Onboarding-Checkliste grün; `lint-imports` grün.

### M4-02 — Spike Job-Queue → `adr/0013`

**Ziel:** Otto wählt die Queue und die Form der Hülle `jobs`.
**Stufe C.** Kein Produktivcode, keine Änderung an `.importlinter`.
**Vorab fest:** Q4, Q9, Q10.
**Umfang:**
- Kriterien aus `architekturplan.md` 7.5. Dazu:
  - Kettenregel: `processing` ohne psycopg, `jobs` mit (Q4); Vorschlag für den
    Vertrag in `.importlinter` und die Zeile `jobs` in 3.1.
  - Fortschritt bis in `api` (SSE, 7.4), Abbruch, Wiederholung mit Idempotenz
    über den Rezept-Hash.
  - Globaler Deckel für gleichzeitige Jobs (Q9) mit begründetem Startwert.
  - Rücksicht auf die Quellen über Prozessgrenzen: die Grenze je Host gilt heute
    nur je Prozess; `RateSlot` aus M3-07a als Vorbild prüfen.
  - Aufräumen der Job-Zeilen nach der Frist (Q10).
  - Lizenz vereinbar mit AGPL-3.0-or-later.
- Kandidaten, mit Quellen: Procrastinate, eine eigene schlanke Queue mit
  `SKIP LOCKED`, pgmq; Celery mit Redis, Hatchet und Temporal nur als Vergleich.
  Je Kandidat: Pflege, Reife, Abhängigkeiten, und ob die Bibliothek selbst
  Verbindungen nach außen öffnet (B8).
- Messen in der Session gegen das dort vorhandene Postgres 16: Einreihen und
  Abholen, Verhalten bei abgebrochenem Worker, Fortschrittsmeldungen. Keine
  echte Quelle nötig.

**Abnahme:** `adr/0013-job-queue.md` mit Kriterienmatrix, Belegstufen,
Empfehlung und nummerierten Fragen an Otto.

### M4-03 — Rezept und Operator-Registry → `adr/0014`

**Ziel:** Otto kann Rezept, Operator-Registry und Ausführung entscheiden, bevor
Code entsteht.
**Stufe C.** Kein Produktivcode.
**Vorab fest:** Q6, Q8, Q11, Q13, Q14; aus `adr/0011` §6.4: `ResolvedAsset`
steht im Rezept, der Worker-Kern sieht weder Adapter noch pgstac.
**Umfang:**
1. **Rezept** (7.1): Schema mit `ResolvedAsset`, Versionierung, Kanonisierung
   und Hash (Verfahren mit Quellen, z. B. RFC 8785). Fassung der Eingaben (Q11):
   ETag per Asset-HEAD oder `updated` am Item, je Datensatz belegt; was gilt für
   `data.eodc.eu`, das kein ETag sendet.
2. **Operator-Registry** (7.2):
   - Form und JSON-Schema der Parameter.
   - Anwendbarkeit über die Capability-Flags des Datensatzes (B10), die
     `processing` nur über die übergebene `DatasetConfig` bzw. das Rezept
     erreicht, nicht über `catalog.datasets` (Kettenregel, `adr/0011` §6.2).
   - Kostenmodell und Kostenschätzung vor dem Start, Metadaten-Transformation,
     Ausführungsstufen.
3. **Planer T1/T2** (7.3): welche Schritte sich in Kachelparameter übersetzen
   lassen und wie dieselbe Implementierung T1 und T2 bedient. Dazu die
   **Toleranz** für „übereinstimmend“ zwischen Vorschau, Job und Runner, als
   Zahl je Operator; die M4-Abnahme hängt daran.
4. **Lesen im Worker:**
   - Bausteine mit Quellen und synthetischer Messung: xarray/rioxarray,
     odc-stac oder ein eigener Weg; Dask lokal ja oder nein; Chunking;
     Speicherbedarf.
   - Nachweis, dass jede URL durch `check_url` läuft und die GDAL-Konfiguration
     aus `gateway` in jedem Lese-Thread gilt (B8).
5. **`Policy` und GDAL-Optionen im Worker** aus den Hosts der `ResolvedAsset`
   (`adr/0011` §6.5; Vorschlag dort: eine Fabrik in `readers`).
6. **Job-Schnittstelle** nach außen (7.6, OGC API Processes): welche Teile in
   M4; Kennungen zufällig (Q8).
7. **`recipe.json` und `citation.bib`** im Zuschnitt-ZIP (Q13); die
   Zitierangabe kommt aus der Registry (DOI, `scientific`).
8. **Checkliste Punkt 9, Fassung v2** (Q14): Form des Tests.
9. **`decomp.py`:** nur beschreiben, wie ein Quad-Pol-Operator später
   registriert würde; nicht registrieren, nicht anfassen.

**Abnahme:** `adr/0014-rezept-operator-registry.md` mit Kriterienmatrix,
Belegstufen, Toleranzwerten, Empfehlung und nummerierten Fragen an Otto.

### M4-04 — Weg zum Objektspeicher → `adr/0015`

**Ziel:** Otto entscheidet Name, Client und Importvertrag des Moduls für
Plattformdienste (Q5) und wie Ergebnisse privat bleiben und ablaufen.
**Stufe C.** Kein Produktivcode.
**Vorab fest:** Q5, Q9, Q10; `adr/0012` F3 (nur signierte URLs, kein anonymes
Lesen).
**Umfang:**
- **Modul:**
  - Name und Zuschnitt, Zeile in 3.1, Importvertrag (nur `jobs` und `api`).
  - Ein AST-Test nach dem Muster `test_no_outbound_outside_gateway.py`.
  - Wie der Client dort erlaubt wird, ohne `http-only-in-gateway` für andere
    Module zu lockern.
- **Client,** mit Quellen: `boto3`, `aiobotocore` oder ein schlanker
  SigV4-Client; Pflege und Abhängigkeiten. `obstore` steht auf der Verbotsliste
  (`adr/0006` F6); wird es trotzdem vorgeschlagen, dann mit Begründung.
- **Signierte URLs:**
  - Lebensdauer.
  - Der Endpunkt für den Browser ist getrennt vom Endpunkt im compose-Netz: eine
    für `http://objectstore:…` signierte URL ist im Browser nicht erreichbar.
  - Garage antwortet bei abgelaufener URL mit `400` statt `403` (`adr/0012`
    §4.1).
- **Ablauf nach 7 Tagen** (Q10): Regel am Bucket und Beleg nach `adr/0012` §9
  Punkt 5; das Löschen von Job- und Rezeptzeilen passend dazu.
- **Zugangsdaten** nur aus der Umgebung, nichts davon in Logs (Muster:
  Nachbesserung zu M3-23). Produktion mit verwaltetem S3 ohne Codeänderung.
- **Messen** gegen eine Garage-Binärdatei in der Session wie in `adr/0012`;
  sonst „unbelegt“ und nennen, was die CI belegen muss.

**Abnahme:** `adr/0015-objektspeicher-zugang.md` mit Kriterienmatrix,
Belegstufen, Empfehlung und nummerierten Fragen an Otto.

### M4-05 — Lokaler Runner → `adr/0016`

**Ziel:** Otto entscheidet Aufbau und Prüfung des Runners für den
Offline-Betrieb (Q12).
**Stufe C.** Startet, sobald `adr/0014` angenommen ist.
**Vorab fest:** Q11, Q12.
**Umfang:**
- Einstieg: ein weiterer Startbefehl im selben Image wie `worker` (3.2) oder ein
  eigenes Image; Größe, gleiche GDAL-Version wie in der Cloud.
- Rezeptdatei mit `ResolvedAsset`; Allowlist aus deren Adressen (B9);
  Ausgabeordner und Cache-Volume.
- Provenienz `execution: local`, `runner_version`, `self_attested: true`.
- Vergleichstest Cloud gegen lokal in der CI: welcher Job, Toleranz aus
  `adr/0014`.
- Befehl für Windows/PowerShell; fester Image-Tag, nie `latest`, kein
  Veröffentlichen (Q12).

**Abnahme:** `adr/0016-lokaler-runner.md` mit Empfehlung und nummerierten
Fragen an Otto.

### Gemeinsam für M4-06 bis M4-15

- **Maßgeblich sind die angenommenen ADRs** samt ihren Auflagen (§10a bzw.
  §14a bzw. §15a/§15b) und R1–R6 in §1.1b. Wo ein ADR eine Skizze zeigt, ist
  sie ein Vorschlag; Abweichungen nennt der Plan-Schritt.
- **Was ein ADR ausdrücklich als Test verlangt** („Was M4-08 belegen muss“,
  „Was M4-06 bauen und die CI belegen muss“, „für die Umsetzung vorgesehen“),
  gehört in die jeweilige Aufgabe; der PR nennt je Punkt den Test.
- **Nie nach außen:** Rezept-Hash, AOI, `href`, Schlüssel-IDs, Endpunkte.
  Fehlertexte sind englisch, kurz und geschwärzt.
- **Vor dem Fertigmelden:** `main` holen, `pytest`, `ruff check backend`,
  `PYTHONPATH=backend lint-imports --config .importlinter`; bei
  Frontend-Änderungen zusätzlich `npm run lint`, `npm run build` und die
  Frontend-Tests; Ergebnisse im PR.

### M4-06 — Modul `objectstore`: Client, signierte URLs, Schlüssel, Ablaufregel

**Ziel:** `jobs` und `api` erreichen den eigenen Objektspeicher über genau ein
Modul, ohne dass `gateway` oder ein anderer Vertrag gelockert wird.
**Stufe B.** Grundlage `adr/0015` §4–§9, §12 Punkte 1–8, §14a; R2, R4.
**Umfang:**
- **Modul `earthx.objectstore`:** Konfiguration nur aus `S3_*` bzw.
  `S3_*_FILE` (`StoreConfig`), Client nur aus `botocore` mit
  `Config(proxies={})` und festen Zeitlimits, Upload samt Multipart, Löschen,
  signierte GET-URL mit Dateinamen für den öffentlichen Endpunkt, lesende
  Prüfung der Ablaufregel, Schwärzung von Fehlertexten. Keine öffentliche
  Funktion nimmt Endpunkt, Host, Bucket oder URL entgegen (Auflage F2).
- **Verträge** nach `adr/0015` §4.2 Punkte 1–5 und R2: neuer Modulvertrag
  `objectstore`, `earthx.objectstore` in den übrigen `forbidden_modules`,
  Quelle in `datasets-isolated`, neuer Kettenvertrag
  `no-object-store-in-worker-core`, Verschärfung und eine
  `ignore_imports`-Zeile in `http-only-in-gateway`. Zeile `objectstore` in die
  Tabelle `architekturplan.md` 3.1; `test_module_boundaries.py` und
  `test_no_outbound_outside_gateway.py` wie in §4.2/§4.3 beschrieben; neue
  Datei `test_objectstore_boundary.py`.
- **Abhängigkeiten:** `botocore` in die Anforderungen, Lock-Dateien neu
  erzeugen; Wächtertest, dass `boto3` und `s3transfer` nicht in der Lock-Datei
  stehen. `backend/Dockerfile`: `AWS_EC2_METADATA_DISABLED=true`.
- **compose:** `objectstore-init`/`bootstrap.py` erzeugt zwei Dienstschlüssel
  (Worker schreibt, `api` liest) mit getrennten Volumes und setzt die Regel
  `results/` (7 Tage, Multipart nach 1 Tag) über die Admin-API;
  `docker-compose.yml` reicht `S3_ENDPOINT`, `S3_PUBLIC_ENDPOINT`, Region und
  die Schlüssel-Dateien an `api` und `worker`; `.env` überschreibt weiter nur
  den Besitzerschlüssel (M3-23). `smoke.py`: Leseschlüssel kann nicht
  schreiben, Regel gesetzt, öffentliche signierte URL geht, interne über
  anderen Host nicht.
- **`jobs`-Start:** prüft die Regel lesend und startet ohne sie nicht;
  `S3_LIFECYCLE_CHECK=off` schreibt genau eine Warnung ohne
  Konfigurationswerte und steht nie in `docker-compose.yml` (Auflage F8).
- **Logs:** `botocore` und `urllib3` in die Liste von `configure_logging`, die
  auf `WARNING` hebt.
- **R4:** Lock-Datei für `compose/objectstore/requirements-smoke.txt` nach dem
  Muster von M4-00b. Falls die CI dafür eine Zeile in
  `.github/workflows/ci.yml` braucht (compose-topology), ist genau diese
  Änderung erlaubt; der Plan-Schritt nennt sie.

**Nicht in dieser Aufgabe:** Aufräumer und `410` (M4-08a/M4-08b), Job-Tabellen,
Routen.
**Nicht anfassen:** `gateway`, `processing`, sonst `.github/`.
**Abnahme:** die Punkte 1–8 aus `adr/0015` §12 mit je einem Test bzw. einem
Schritt in compose-topology; `lint-imports` hält alle Verträge mit genau einer
ignorierten Zeile; Gegenprobe im PR, dass ein zweiter `botocore`-Import bricht;
Prüfanleitung für Otto (PowerShell): `docker compose up -d --build`, dann
`docker compose logs objectstore-init` zeigt die gesetzte Regel ohne
Schlüssel.

### M4-07a — Kern: Rezept, Hash, Operator-Registry, Blockschleife, Lesen im Worker

**Ziel:** `processing.run(recipe, *, workdir, progress)` rechnet ein Rezept als
reine Funktion, mit derselben Implementierung, die später Kachel und Runner
nutzen.
**Stufe B.** Grundlage `adr/0014` §4–§8, §13, §15a, §15b; R3.
**Umfang:**
- `processing/recipe.py`: Modelle für Auftrag, Rezept und Provenienz (§4.1,
  §4.2), Versionierung (§4.3), Kanonisierung und Hash nach §4.4 mit Test gegen
  feste erwartete Hashwerte (Auflage F2), Cache-Schlüssel nach §4.5 inklusive
  der Versionen von GDAL, rasterio, numexpr und numpy (Auflage F3), Fassung je
  Eingabe nach §4.6.
- `processing/operators/`: Registry aus pydantic-Modellen, JSON Schema
  2020-12, `applicable(config)` gegen die übergebene `DatasetConfig` (§5.1–§5.3).
  Konkrete Operatoren kommen mit M4-09 und M4-10; für Tests ein
  Test-Operator nur im Testbaum.
- `processing/plan.py`: Planer T1/T2 (§6.1), Ausgaberaster, Kostenschätzung
  nach §5.5.
- `processing/core.py`: `run` mit der Blockschleife L1 (§7.2: 1024er Blöcke,
  ein Lesethread, `GDAL_CACHEMAX`, Fortschritt und Abbruch je Block, COG am
  Ende), Skalierung nach §5.4 (F7, F7a und Auslegung: Item, sonst `store-cf`,
  Vergleich, Abbruch bei Abweichung oder bei COG-Tags ohne Angabe),
  Metadaten-Transformation (§5.6), `worker_environment()`.
- `readers/access.py`: `process_gdal_options()` und `read_access_for(hrefs)`
  (§8); generische Option, Zarr ohne CF-Dekodierung zu öffnen (§5.4).
- Registry: neues Flag `reprojection` ohne Vorgabewert, in allen drei
  Einträgen `true` (R3).
- AST-Test nach §7.3 Punkt 1: kein `rasterio.open`, `xarray.open_*`,
  `rioxarray.open_rasterio` oder `rio_tiler.io.Reader` mit einer Zeichenkette in
  `processing`; Test für die GDAL-Optionen aus einem Thread-Pool (§7.3 Punkt 2).
- Test, dass der Import von `earthx.processing` kein `psycopg`, `psycopg_pool`,
  `asyncpg`, `botocore` oder `earthx.objectstore` lädt.
- **Versionsangabe (`adr/0016` F10):** `__version__` in `earthx/__init__.py`,
  SemVer 0.x. Sie ist die Version von `earthx.processing` im Cache-Schlüssel
  (§4.5, E2); M4-16 übernimmt sie für den Image-Tag und `runner_version`. Ein
  Sprung ist Pflicht, sobald sich ein Ergebnis ändern kann.

**Nicht in dieser Aufgabe:** Annahme in `api` (M4-07b), Band-Math und
Reprojektion (M4-09, M4-10), Queue (M4-08a).
**Nicht anfassen:** `.importlinter`, `gateway`, `api`, `jobs`,
`datasets/` (`decomp.py` ruht).
**Abnahme:** Tests aus §4.4, §5.4 (synthetisches Item mit Offset und Nodata,
Mini-Zarr mit CF-Attributen, alle vier Fälle aus F7a) und §7.3; ein
T2-Lauf des Test-Operators auf einem synthetischen COG braucht nachweislich
weniger als 300 MB Spitzenspeicher für 8192² (Messung im PR, Bezug §3.5).

### M4-07b — Annahme in `api`: Auftrag → Rezept, Fassung, Host-Prüfung

**Ziel:** `api` macht aus einem Auftrag ein vollständiges Rezept, ohne Routen;
M4-08b, M4-14 und M4-15 bauen darauf.
**Stufe B.** Neue Session nach dem Merge von M4-07a und M4-01b. Grundlage
`adr/0014` §4.1, §4.6, §5.3, §8 (Allowlist), §10.1.
**Umfang:**
- Auftrag validieren, Items über die Item-Quelle (M4-01a) holen,
  `access.resolve_asset` je Asset, Bandangaben und Skalierungsquelle
  übernehmen, `applicable` gegen die Registry prüfen.
- Fassung je Eingabe nach F4: `file:checksum`, sonst ETag per `HEAD` über
  `gateway`, sonst `updated`; ohne Fassung wird das Rezept markiert (kein
  Cache-Treffer, Q11).
- **Host-Prüfung:** Jeder Host eines `ResolvedAsset` liegt in `asset_hosts`
  seines Datensatzes; ein eingereichtes Rezept mit fremden Adressen wird neu
  aufgelöst oder mit `400` abgewiesen, nie durchgereicht (§8).
- Baustein für `recipe.json` mit `steps: []` nach §10.1, als Bytes für
  `access.download` (ohne `processing`-Import dort).
- Zufällige `recipe_id` je Auftrag (`adr/0013` §9 Punkt 2).

**Nicht anfassen:** `processing` außer Fehlern, die der Plan-Schritt nennt;
Routen.
**Abnahme:** Tests für jeden Datensatz mit synthetischen Items (Fassung je
Quelle, Skalierungsquelle), für die Abweisung fremder Hosts und für zweckfremde
Aufträge (unbekannter Datensatz, Operator nicht anwendbar, AOI ohne Überschneidung mit den Items);
kein Log enthält AOI oder `href`.

### M4-08a — Queue und Worker-Hülle in `jobs`

**Ziel:** Läufe werden zuverlässig abgeholt, begrenzt, beobachtet, wiederholt,
abgebrochen und aufgeräumt.
**Stufe B.** Grundlage `adr/0013` §5, §6, §8, §10a; `adr/0015` §7, §8,
§12 Punkt 9.
**Umfang:**
- Migration `catalog/migrations/006_jobs.sql` nach §5.1 und §6.3, mit Index
  auf jedem Fremdschlüssel; Deckel (4) und Grenze je Host (2) als Zeilen.
- Vertrag `no-database-in-worker-core` nach §6.1 (nur `processing`, dazu
  `psycopg_pool`, `asyncpg`); Zeile `jobs` in 3.1; Test angepasst.
- Aufseher in `jobs/worker.py` mit 2 Slots, Kind je Lauf in `jobs/child.py`
  über `spawn`; `jobs/__init__.py` ohne Importe; das Kind ruft
  `processing.worker_environment()` und `processing.run`.
- Abholen mit Deckel (Sperre in eigener Anweisung vor dem Zählen) und Grenze
  je Host; Lease 60 s, Heartbeat 15 s; Abschluss nur mit eigener
  Versuchsnummer; Wiederholung nach der Tabelle in §5.6; Job getrennt vom
  Lauf (F6).
- Upload des Ergebnisses über `objectstore` unter `results/{result_id}/`;
  Cache-Eintrag nur mit Fassung aller Eingaben; Treffer nur mit mindestens
  24 h Restlaufzeit.
- Aufräumer stündlich in Stapeln: erst Objekte, dann Zeilen; Rezeptfrist
  verlängert nur ein Lauf oder Treffer (Auflage F13).
- `NOTIFY` bei Fortschritt (die Zeile ist die Wahrheit).

**Nicht in dieser Aufgabe:** Routen und SSE (M4-08b).
**Abnahme:** die Punkte 1–5, 7, 8, 10, 11 und 13 aus `adr/0013` §8 gegen echtes
Postgres in CI und Session; Punkt 9 aus `adr/0015` §12; Prüfanleitung für Otto
(Worker startet, `docker compose logs worker` zeigt 2 Slots ohne Fehler).

### M4-08b — Job-API (OGC-Form), Ergebnis-Links, SSE

**Ziel:** Ein Auftrag lässt sich über HTTP stellen, verfolgen, abbrechen und
herunterladen.
**Stufe B.** Grundlage `adr/0014` §9, `adr/0013` §5.4, §5.5, `adr/0015` §6.
**Umfang:**
- Landing Page und `/conformance` unter eigenem Präfix (Vorschlag im
  Plan-Schritt), `GET /processes`, `GET /processes/recipe` (Schema als
  Discriminated Union, je Datensatz filterbar), `POST
  /processes/recipe/execution` nur asynchron, `GET /jobs/{jobID}`,
  `/results`, `DELETE /jobs/{jobID}`; keine Job-Liste.
- Ergebnis-Links auf `api`, die mit `303` und `Cache-Control: no-store` auf
  eine frisch signierte URL leiten (15 Minuten, nie über das Ablaufdatum);
  `410` ab `expires_at` oder bei weniger als 60 s Rest.
- SSE: genau eine `LISTEN`-Verbindung je `api`-Prozess, verteilt auf alle
  Clients; beim Verbinden zuerst der Stand der Zeile.
- **`recipe.json` erzeugt `api`** je Job aus dessen eigenem Rezept; sie liegt
  nicht im Objektspeicher (Otto, 07.10.2026, M4-08a F4), damit kein Auftrag die
  `recipe_id` eines anderen sieht. Neben `result.tif` und `mask.tif` legt der
  Worker nichts unter `results/{result_id}/` ab.
- **Im Plan-Schritt zu entscheiden** (`adr/0015` §13): ob `DELETE` eines
  fertigen Jobs das Ergebnis löscht; ein Ergebnis, das Treffer anderer Jobs
  bedient, darf nicht verschwinden.

**Abnahme:** die Punkte 6, 9 und 12 aus `adr/0013` §8; Tests für `303`, `410`,
`no-store`, Dateiname aus Datensatz, Operator und Datum; zweckfremde Nutzung
(fremde, falsch geformte, abgelaufene `jobID` → `404`).

### M4-09 — Operator Band-Math (T1, T2)

**Ziel:** NDVI und ähnliche Ausdrücke rechnen als Vorschau und als Job
bitgleich auf der nativen Ebene.
**Stufe B** (R1). Grundlage `adr/0014` §3.2, §3.3, §5.4, §6.2–§6.4; R5.
**Umfang:**
- Operator `band_math` in `processing/operators/`, `kind="pixel"`,
  `tiers={T1, T2}`, Parameter nach R5, Ausgabe `float32` mit Nodata.
- T1: `api/tiler.py` reicht einen `process_dependency` in die Fabrik; die
  Kachel-URL trägt `op`, `op_version` und `params`, keine Rezept-Kennung, keinen
  Hash, keine AOI. Pfad-Abhängigkeit für mehrere Assets desselben Items
  (§6.2, Mehr-Asset-Lücke).
- Vergleichstest T1 ↔ T2 nach §6.4 mit synthetischem COG (Skalierung,
  Offset) und Mini-Zarr (CF-Attribute).
- **Hinweis (`adr/0016` F8, `adr/0014` §15c):** R5 ist eingeengt. Die
  Funktionsliste enthält nur bitstabile Funktionen (siehe R5 in §1.1b);
  `log`, `exp`, Winkelfunktionen und gebrochene Potenzen sind abzuweisen.
  numexpr zerlegt ganzzahlige Exponenten nur bis |n| ≤ 50 und nur mit
  `optimization="aggressive"` in Multiplikationen; darüber rechnet es mit
  `pow`, und das Ergebnis hängt von der CPU ab (`adr/0016` §12a, §14.5).

**Abnahme:** Vergleichstest bitgleich auf der nativen Ebene; Tests für R5
(abgewiesene Namen, Attribute, Aufrufe, Länge, abgewiesene Funktionen und
Exponenten über 50) und für fehlende Capability; ein Test zeigt, dass jede
erlaubte Funktion unter den Einstellungen A und D aus `adr/0016` §3.3
dieselben Bytes liefert; bestehende Kachel-Tests grün.

### M4-10 — Operator Reprojektion/Resampling (T2)

**Stufe A.** Grundlage `adr/0014` §3.4, §5.3, §6.3 (vierte Zeile); R3.
**Umfang:** Operator `reproject`, `kind="grid"`, `tiers={T2}`, Ziel-CRS,
Auflösung, Resampling; Methoden außer `nearest` verlangen `interpolation`;
Blockplan fest in `op_version`.
**Abnahme:** Plausibilitätstest gegen ein ganzes `reproject` mit den
Grenzen aus §6.3; Test, dass ohne `reprojection` bzw. `interpolation`
abgewiesen wird; T2 zweimal gerechnet ist bitgleich.

### M4-10b — Spitzenspeicher von `reproject` (Nachbesserung zu M4-10)

**Stufe A.** Grundlage `adr/0014` §3.5 (Nachtrag F11), §6.3, §7.2;
Log-Zeilen zu M4-07a F11 und M4-10.
**Anlass:** `test_memory_reproject.py` riss in der CI: bilinear 4096² mit
503,9 MB `VmHWM` gegen die Grenze von 500 MB.

**Messung [M]** (`VmHWM` des Kindprozesses in MB, `GDAL_CACHEMAX` 64 MB, Szene
wie in M4-07a; „Kern“ ist der Lauf mit dem Test-Operator `scale`; Spannen über
drei Läufe, 8192² je ein Lauf):

| Lauf | Größe | vorher, Sitzung | vorher, CI | nachher, Sitzung | nachher, CI |
|---|---|---|---|---|---|
| `reproject` bilinear | 2048² | 382–383 | — | 346 | 354 |
| `reproject` bilinear | 4096² | 479–492 | 480–508 (5 Läufe) | 425 | 433 |
| `reproject` bilinear | 8192² | 531 | — | 443 | — |
| `reproject` nearest | 2048² | 389 | — | 343 | — |
| `reproject` nearest | 4096² | 497–529 | — | 422 | — |
| `reproject` nearest | 8192² | 523 | — | 440 | — |
| Kern | 2048² | 327–329 | 334–336 | 288 | 294 |
| Kern | 4096² | 420–424 | — | 370 | — |
| Kern | 8192² | 462 | 475–486 | 394 | 400 |

- Nach den Imports liegt das Kind bei 161 MB (CI 165 MB), vorher wie nachher.
- Nachher streuen die drei Läufe je Größe um höchstens 0,4 MB, vorher um bis
  zu 32 MB.
- Die Spitze sättigt: Bilinear wächst von 2048² auf 4096² um 79 MB und von
  4096² auf 8192² nur noch um 18 MB.
- Zeit für bilinear 4096² in der Sitzung: 25–28 s nachher gegen 32–34 s vorher.

**Ursache [M].**
- **Heap-Fragmentierung durch glibc, rund 80 MB und die Streuung.** glibc hebt
  die mmap-Schwelle nach jedem freigegebenen großen Puffer auf dessen Größe an
  (bis 32 MB). Danach landen die Blockpuffer eines Durchgangs (16 MB float64 je
  Block, dazu Masken und Kopien) im Heap, wo kleine, länger lebende
  Allokationen von GDAL sie festhalten. Der Prozess gibt den Speicher dann nicht
  mehr zurück, und die Spitze hängt von der Reihenfolge der Freigaben ab. Beleg:
  Mit fester Schwelle (`MALLOC_MMAP_THRESHOLD_=131072`, sonst unverändert)
  fällt nearest 4096² von 497–529 auf 423 MB, und das RSS nach dem
  Warp-Durchgang von 416–473 auf 282 MB.
- **Ein zweiter Lesevorgang für die Maske.** `vrt.read(masked=True)` lässt GDAL
  die Maske aus einem zweiten Lesen des gewarpten Bandes ableiten. Das kostet
  Zeit und eigene Puffer, und es stimmt nicht immer mit dem ersten überein: Bei
  2048² maskierte es 3 Pixel je Band, die Werte hatten.
- **Nicht die Ursache:**
  - `warp_mem_limit`: 16 MB senkt die Spitze nach dem Umbau nur um 8 MB
    (418 gegen 425 MB), 256 MB ändern nichts. Das VRT warpt in eigenen Blöcken
    von 512 × 128 px, weit unter 64 MB. Der Blockplan bleibt deshalb, wie er
    ist.
  - Der GDAL-Cache: Er bleibt bei 64 MB gedeckelt, auch im Warp-Durchgang.
  - Die Zwischendatei: Sie liegt auf Platte, nicht im Speicher.
  - Ein über den ganzen Durchgang wiederverwendetes `WarpedVRT` war schlechter
    (537 MB, nearest 4096²), weil seine Blöcke bis zum Ende im Cache bleiben.

**Umsetzung.**
- `worker_environment()` setzt die mmap-Schwelle von glibc über `mallopt` fest
  auf 128 KiB, den Startwert von glibc. Das gilt für den ganzen Prozess
  und ändert keinen berechneten Wert. Ohne glibc passiert nichts. Das Image
  (`python:3.12-slim`, Debian) hat glibc.
- `reproject` liest einmal und maskiert, wo der Warp NaN gelassen hat.
  Toleranz, `warp_mem_limit` und Blockgröße bleiben gleich. Das Ergebnis
  ändert sich in den Pixeln der zweiten Maske, deshalb gilt jetzt
  **`op_version` 2**; ein Rezept mit Version 1 wird abgewiesen (K7).
- `test_memory_reproject.py` rechnet 2048² und 4096² mit `bilinear`: 4096² unter
  500 MB, Wachstum dazwischen höchstens `GROWTH_LIMIT_MB` = 120 MB.

**F1 (Otto, 07.10.2026): Option 1.** Die feste mmap-Schwelle bleibt in
`worker_environment()` und gilt für das Kind in `jobs` und den lokalen Runner;
der Runner ruft `worker_environment()` selbst auf (M4-16). Festgehalten in
`adr/0014` §7.2 und §7.3 Punkt 2.

**Abstand zur Grenze [M]:** In der CI (Lauf 433) liegt bilinear 4096² bei
433 MB, 67 MB unter der Grenze; die fünf Läufe davor lagen bei 480–508 MB.
Gefordert waren stabil mindestens 30 MB.

**Wachstumsgrenze:** gemessen 79 MB von 2048² auf 4096², in der Sitzung wie in
der CI. 120 MB lassen ein Drittel Reserve und bleiben unter den 192 MB, um die
die float64-Zwischendatei zwischen den beiden Größen wächst; ein Warp, der seine
Quelle hielte, läge darüber.

**Laufzeit [M]:** CI bilinear 4096² 13,6 s statt 16,5–17,0 s. Der Kern bei
8192² braucht 35,8 s statt 31,4–34,0 s; vermutlich kostet die feste Schwelle
dort zusätzliche mmap-Aufrufe und Seitenfehler [A].

### M4-11 — Export über dem Deckel als Job

**Stufe B.** Grundlage P20, P21, `adr/0014` §10.
**Umfang:** Der Download-Dialog bietet über 500 MB roh einen Job an (Rezept
mit `steps: []`, Ausgabe wie der synchrone Zuschnitt in voller Auflösung);
gleiche Hinweisdateien, Maske, `recipe.json` und `citation.bib`; Ergebnis über
den Link aus M4-08b.
**Im Plan-Schritt zu entscheiden:** ZIP wie beim synchronen Zuschnitt oder
einzelne Dateien.
**Abnahme:** Test über die Grenze; Prüfanleitung für Otto mit einer großen
AOI.

### M4-12 — Mosaik ganzer Szenen je Überflug als Job

**Stufe B.** Grundlage P19, `adr/0011` §8.1.
**Umfang:** Die Suche als Eingabe läuft in `api`, nie im Worker; der Job
mosaikiert die Szenen eines Überflugs, bei mehreren UTM-Zonen über die
Reprojektion aus M4-10.
**Im Plan-Schritt zu entscheiden:** ob das Mosaik ein eigenes Capability-Flag
braucht (B10), und die Regel für Überlappungen.
**Abnahme:** Test mit synthetischen Szenen über zwei Zonen; Prüfanleitung.

### M4-13 — Frontend: Processing-Panel, Kostenschätzung, Vorschau, Job-Status

**Stufe B.** Grundlage `adr/0014` §6.3 (Auflage F9), §9; `adr/0013` §5.4.
**Umfang:** Panel aus dem Schema von `/processes/recipe`, je Datensatz nur
anwendbare Operatoren; Kostenschätzung vor dem Start; T1-Vorschau auf der
Karte, auf Übersichtsstufen sichtbar als „Preview“ gekennzeichnet; Job-Status
per SSE mit Rückfall auf Abfragen; Ergebnis-Download. Oberflächentexte nur
Englisch.
**Im Plan-Schritt zu entscheiden:** eigener Formularbau oder eine Bibliothek
für JSON Schema (mit Recherche zu Größe und Pflege).
**Abnahme:** Frontend-Tests; Prüfanleitung für Otto (NDVI auf Sentinel-2,
Vorschau, Start, Fortschritt, Download).

### M4-14 — Zuschnitt-ZIP mit `recipe.json` und `citation.bib`, `sci:doi`

**Stufe A.** Grundlage `adr/0014` §10, F13.
**Umfang:** `api` baut beide Dateien und gibt sie als Bytes an
`access.download.build_download_zip`; `collection.py` schreibt `sci:doi` als
DOI-Namen und einen Link `rel: cite-as`.
**Abnahme:** Tests je Datensatz (mit und ohne DOI); `sci:doi` ohne `https://`;
bestehende Download-Tests grün.

### M4-15 — Onboarding-Checkliste Punkt 9, Fassung v2

**Stufe A.** Grundlage `adr/0014` §11, Q14.
**Umfang:** Testmodul parametrisiert über `REGISTRY` auf dem Gerüst von
`synthetic_chain.py`, Kette 1–6 aus §11, Zuordnung Datensatz → Operator als
Konstante, Wächtertest für fehlende Zuordnung; `CHECKLIST` Punkt 9 zeigt auf
das neue Modul; die Kette aus v1 bleibt als eigener Test.
**Abnahme:** grün für alle drei Einträge; der Wächtertest fällt mit einem
vierten Eintrag ohne Zuordnung (Gegenprobe im PR).

### Umriss M4b (Fassung 3 schärft nach `adr/0016`)

- **M4-16 Lokaler Runner** offline nach `adr/0016`, Vergleich T2 ↔ T2L
  bitgleich in der CI (`adr/0014` §6.3, §6.4); Änderung an `.github/` dann
  ausdrücklich erlaubt.
  Der Einstieg des Runners ruft im Hauptthread
  `processing.worker_environment()` auf, nicht nur `rasterio.Env`: Es setzt
  auch die feste mmap-Schwelle aus M4-10b (`adr/0014` §7.2, §7.3 Punkt 2).
- **M4-17 Mosaik im Kachel-Pfad** (P11): zustandslos (`adr/0001`), keine
  exakte AOI in der Kachel-URL; Optionen aus `adr/0006` §3 und
  `architekturplan.md` 6.3 (Such-ID mit kurzem Cache in Postgres, E4);
  Recherche mit Quellen im Plan-Schritt, weil rechenrelevant (gemessen bisher
  2,7 MB je Mosaik-Kachel).
- **M4-18 Masking, Normalisierung,** je eine Stufe-A-Session.
- **M4-19 Permalinks, Methodentext, Skalierung und Einheiten, „Parameter
  übernehmen“;** mit der offenen Frage der Rezeptfrist für Permalinks
  (`adr/0015` §13, Log 05.10.2026).

### M4-20 — M4-Abnahme und README

**Ziel:** Otto kann M4 anhand eines Berichts abnehmen, ohne Code zu lesen.
**Stufe A.** Muster: `plans/m3-15-abnahme.md`.
**Umfang:** Belege je Kriterium aus §5; eine kurze lokale Prüfanleitung
(Windows/PowerShell, `docker compose up -d --build`); ein Abschnitt „Nach M4
vorgemerkt“ mit allen offenen Punkten aus Log und Plan; Stand aller
M4-Aufgaben in §3; README nachziehen; keine Codeänderung.
**Abnahme:** Bericht `plans/m4-20-abnahme.md` im PR.

---

## 5. Abnahme von M4

1. Dasselbe Rezept liefert als T1-Vorschau, als Job (T2) und im lokalen Runner
   (offline) übereinstimmende Ergebnisse innerhalb der Toleranz aus `adr/0014`;
   der Vergleichstest läuft in der CI.
2. Ein zweiter identischer Auftrag kommt aus dem Cache, wenn alle Eingaben eine
   Fassung tragen (Q11); lokale Ergebnisse kommen nie in den Cache.
3. `processing` ist ohne Datenbank, Queue, Objektspeicher und `gateway`;
   `jobs` und `api` nutzen das Modul für Plattformdienste; `gateway` ist dafür
   nicht gelockert. Importregeln grün.
4. Ergebnisse sind privat und nur über signierte URLs erreichbar; der Ablauf
   nach 7 Tagen ist belegt; Job-IDs sind zufällig; weder Rezept-Hash noch AOI
   erscheinen in URLs oder Logs.
5. Export über dem Deckel und Mosaik ganzer Szenen je Überflug laufen im Viewer
   als Job, mit Attribution, Terms, `citation.bib` und `recipe.json`.
6. Band-Math und Reprojektion/Resampling sind registriert und im
   Processing-Panel aus ihren Schemas bedienbar, mit Kostenschätzung vor dem
   Start.
7. Mosaik im Kachel-Pfad ist zustandslos und ohne exakte AOI in der URL.
8. Onboarding-Checkliste Fassung v2 grün für jeden Datensatz.
9. M4-01a und M4-01b sind umgesetzt; Pflicht-CI grün mit Installation aus der
   Lock-Datei.

---

## 6. Risiken

| Risiko | Umgang |
|---|---|
| Vorschau (je Kachel) und Job (ganze AOI) weichen ab, etwa beim Resampling | Toleranz je Operator in `adr/0014`; Vergleichstest in der CI |
| Worker belasten die Quellen, weil die Grenze je Host nur je Prozess gilt | globaler Deckel für Jobs (Q9); `adr/0013` prüft eine Grenze über Prozesse |
| Eine Bibliothek im Worker (odc-stac, Dask, Queue) öffnet selbst Verbindungen | Nachweis in `adr/0013` und `adr/0014`; Verbotsliste `http-only-in-gateway` |
| Signierte URL zeigt auf den Hostnamen im compose-Netz und ist im Browser nicht erreichbar | getrennter Endpunkt für den Browser in `adr/0015` |
| Der Ablauf im Speicher greift nicht, der Speicher läuft voll | Beleg nach `adr/0012` §9 Punkt 5 (Q10) |
| Föderierte Eingaben ohne Fassung verhindern Cache-Treffer | ehrlich neu rechnen (Q11); das Abnahmekriterium 2 wird mit einer Eingabe belegt, die ein ETag trägt |
| Rezepte enthalten die AOI | personenbezogen, Frist 7 Tage, nie in Logs oder URLs (Q8, Q10) |
| Die Lock-Datei bricht die Installation in der Session | Beleg in einer neu gestarteten Session (M4-00b) |
| M4 ist zu groß (XL) | Teilung M4a/M4b, Fassung 2 erst nach den ADRs |
| `sentinel-2-l2a-zarr3` („staging“) fällt weg | Checkliste v2 läuft gegen Fixtures; die Abnahme hängt nicht am Fortbestand der Quelle (wie D24) |
| Zwei PRs erzeugen die Lock-Dateien gleichzeitig neu | wer als Zweiter gemergt wird, holt `main` und erzeugt sie mit `scripts/lock-backend.sh` neu (§3) |
| `boto3` gerät über eine Abhängigkeit ins Image, rasterio fragt dann den Metadatendienst | Wächtertest auf die Lock-Datei, `AWS_EC2_METADATA_DISABLED=true` (M4-06) |
| Ein Band-Math-Ausdruck wird zweckfremd genutzt | Prüfung im Parametermodell vor numexpr (R5, M4-09) |
| Der Deckel für Jobs hält unter Last nicht | Sperre in eigener Anweisung vor dem Zählen, Gegentest gegen die Variante in einer Anweisung (`adr/0013` §8 Punkt 1) |
| Mehrere PRs ändern `ENTSCHEIDUNGSLOG.md` am Ende | vor dem Fertigmelden `main` holen, alle Zeilen erhalten, eigene ans Ende |
