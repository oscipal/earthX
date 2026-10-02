# M4 — Processing-Kern mit lokalem Runner: Aufgabenschnitt

**Status:** Fassung 1 vom 02.10.2026. Die Aufgaben M4-00 bis M4-05 sind
vollständig beschrieben. Die Umsetzungsaufgaben ab M4-06 stehen in §4 nur im
Umriss; sie werden nach der Annahme von `adr/0013`, `adr/0014` und `adr/0015`
in Fassung 2 geschnitten (wie M3-11 nach `adr/0009`). Wo eine erledigte Aufgabe
anders umgesetzt wird als hier beschrieben, gilt das Log.
**Ort im Repo:** `docs/plans/m4-processing-kern.md`
**Grundlagen:** `projektplan.md` 4 (M4), 6.1, 10; `architekturplan.md` 3.1,
3.2, 6.1, 6.3, 6.4, 6.5, 7, 12.1, 12.3, 15.1, 15.2; `adr/0001` §9.2 (Ablauf),
`adr/0002` (Tests), `adr/0006` (Kachel-Pfad, Mosaik), `adr/0011`
(Adapter-Interface, §6, §7, §8.1), `adr/0012` (Objektspeicher, §7.3, §9, F3, F5);
`KLAERUNGEN.md` B8–B13; `projektuebersicht.md` §5 (Onboarding-Checkliste);
`plans/m3-dritte-quelle-und-interface.md` (P11, P19, P20, „Nicht in M3“);
`plans/m3-15-abnahme.md` §12 („Nach M3 vorgemerkt“); `ENTSCHEIDUNGSLOG.md`, Zeilen
ab dem 30.09.2026, besonders „M4 Q2“ bis „M4 Q16“ vom 02.10.2026.

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
| M4-00 | Doku nachziehen | M4a | A | Sonnet (mittel) | — | PR #111 |
| M4-00b | Lock-Datei für die Backend-Pakete | M4a | B | Opus Plan, Sonnet (hoch) | — | PR #113 |
| M4-01a | Zugriffsauflösung nach `access`, eine Item-Quelle in `api` | M4a | B | Opus Plan, Sonnet (hoch) | — | PR #112 |
| M4-01b | `AdapterSpec`, Signaturen, Fehlerklassen, `harvest_run` entfernen | M4a | B | Opus Plan, Sonnet (hoch) | M4-01a (nach Merge, neue Session) | offen |
| M4-02 | Spike Job-Queue → `adr/0013` | M4a | C | Opus (hoch) | — | PR #116, Entwurf |
| M4-03 | Rezept und Operator-Registry → `adr/0014` | M4a | C | Opus (xhigh) | — | PR #114, angenommen |
| M4-04 | Weg zum Objektspeicher → `adr/0015` | M4a | C | Opus (hoch) | — | offen |
| M4-05 | Lokaler Runner → `adr/0016` | M4b | C | Opus (hoch) | `adr/0014` angenommen | offen |
| M4-06 | Modul für Plattformdienste: signierte URLs, Ablauf | M4a | B | Opus Plan, Sonnet (hoch) | `adr/0015` | Umriss, Fassung 2 |
| M4-07 | Rezept, Hash, Operator-Registry, Worker-Kern | M4a | B | Opus Plan, Sonnet (hoch) | `adr/0014`, M4-01a | Umriss, Fassung 2 |
| M4-08 | Queue, `jobs`-Hülle, Job-API, Fortschritt, Ergebnis-Cache | M4a | B | Opus Plan, Sonnet (hoch) | `adr/0013`, M4-06, M4-07 | Umriss, Fassung 2 |
| M4-09 | Operator Band-Math (T1, T2) | M4a | A | Sonnet (hoch) | M4-07 | Umriss, Fassung 2 |
| M4-10 | Operator Reprojektion/Resampling (T2) | M4a | A | Sonnet (hoch) | M4-07 | Umriss, Fassung 2 |
| M4-11 | Export über dem Deckel als Job | M4a | B | Opus Plan, Sonnet (hoch) | M4-08 | Umriss, Fassung 2 |
| M4-12 | Mosaik ganzer Szenen je Überflug als Job | M4a | B | Opus Plan, Sonnet (hoch) | M4-08 | Umriss, Fassung 2 |
| M4-13 | Frontend: Processing-Panel, Kostenschätzung, Vorschau, Job-Status | M4a | B | Opus Plan, Sonnet (mittel) | M4-08, M4-09 | Umriss, Fassung 2 |
| M4-14 | Zuschnitt-ZIP mit `recipe.json` und `citation.bib` | M4a | A | Sonnet (mittel) | M4-07 | Umriss, Fassung 2 |
| M4-15 | Onboarding-Checkliste Punkt 9, Fassung v2 | M4a | A | Sonnet (mittel) | M4-09, M4-10 | Umriss, Fassung 2 |
| M4-16 | Lokaler Runner offline, Vergleichstest in der CI | M4b | B | Opus Plan, Sonnet (hoch) | `adr/0016`, M4-08 | Umriss, Fassung 2 |
| M4-17 | Mosaik im Kachel-Pfad | M4b | B | Opus Plan, Sonnet (hoch) | M4-01a | Umriss, Fassung 2 |
| M4-18 | Operatoren Masking und Normalisierung | M4b | A | Sonnet (hoch) | M4-07 | Umriss, Fassung 2 |
| M4-19 | Permalinks, Methodentext, Skalierung und Einheiten, „Parameter übernehmen“ | M4b | B | Opus Plan, Sonnet (mittel) | M4-13 | Umriss, Fassung 2 |
| M4-20 | M4-Abnahme und README | — | A | Sonnet (mittel) | alle | offen |

**Wellen.** Höchstens zwei Stufe-B-Sessions gleichzeitig; Stufe A und C laufen
daneben.

1. **Sofort:** M4-00b und M4-01a (die zwei B-Plätze); daneben M4-00 (A) und
   M4-03 (C). M4-03 zuerst unter den ADRs, weil Rezept und Registry den Kern
   tragen und `adr/0013` sowie `adr/0016` darauf verweisen.
2. **Danach:** M4-02 und M4-04 (C), sobald Otto Zeit für die Reviews hat;
   M4-01b nach dem Merge von M4-01a.
3. **Nach Annahme von `adr/0013` bis `adr/0015`:** Fassung 2 dieses Plans. Dann
   M4-06 und M4-07 (B), danach M4-08; M4-09, M4-10 und M4-14 (A) laufen
   daneben, sobald M4-07 gemergt ist.
4. **Zuletzt in M4a:** M4-11, M4-12, M4-13, M4-15.
5. **M4b:** M4-05 (C) kann starten, sobald `adr/0014` angenommen ist; M4-17
   hängt nur an M4-01a und kann einen freien B-Platz früher füllen.

**Dateikonflikte:** M4-01a und M4-01b berühren beide `api/tiler.py`,
`api/federating_client.py` und `adapters`; deshalb nacheinander. M4-00b ändert
`.github/workflows/`, `backend/Dockerfile` und das Setup-Skript, M4-01a nichts
davon; die beiden laufen parallel. M4-00 ändert nur `docs/`.

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

### Umriss der Umsetzungsaufgaben (Fassung 2 schneidet sie aus)

- **M4-06 Modul für Plattformdienste:** signierte URLs, Ablaufregel mit Beleg,
  Importvertrag und AST-Test nach `adr/0015`; Tests mit `moto` und Garage in
  der CI (E7).
- **M4-07 Rezept und Kern:** Rezept-Schema, Hash, Operator-Registry,
  Worker-Kern als reine Funktion in `processing`, `Policy`/GDAL im Worker nach
  `adr/0014`.
- **M4-08 Jobs:** Queue und `jobs`-Hülle nach `adr/0013`; Job-API; Fortschritt
  per SSE; Ergebnis-Cache nach Q11; globaler Deckel nach Q9; Ablauf nach Q10.
- **M4-09 Band-Math** auf T1 und T2 mit Vergleich innerhalb der Toleranz.
- **M4-10 Reprojektion/Resampling** auf T2.
- **M4-11 Export über dem Deckel als Job** (P20): Download-Dialog bietet über
  500 MB roh einen Job an, Ergebnis über signierte URL; gleiche Hinweisdateien
  und Maske wie der synchrone Zuschnitt (P21).
- **M4-12 Mosaik ganzer Szenen je Überflug als Job** (P19); die Suche als
  Eingabe läuft in `api`, nie im Worker (`adr/0011` §8.1).
- **M4-13 Frontend:** Processing-Panel aus den Schemas, Kostenschätzung vor dem
  Start, T1-Vorschau auf der Karte, Job-Status, Ergebnis-Download.
- **M4-14 Zuschnitt-ZIP** mit `recipe.json` und `citation.bib` (Q13).
- **M4-15 Checkliste Punkt 9 v2** (Q14) als Test je Datensatz.
- **M4-16 Lokaler Runner** offline nach `adr/0016`, Vergleichstest in der CI;
  Änderung an `.github/` dann ausdrücklich erlaubt.
- **M4-17 Mosaik im Kachel-Pfad** (P11): zustandslos (`adr/0001`), keine
  exakte AOI in der Kachel-URL; Optionen aus `adr/0006` §3 und
  `architekturplan.md` 6.3 (Such-ID mit kurzem Cache in Postgres, E4); Recherche
  mit Quellen im Plan-Schritt, weil rechenrelevant (gemessen bisher 2,7 MB je
  Mosaik-Kachel).
- **M4-18 Masking, Normalisierung,** je eine Stufe-A-Session.
- **M4-19 Permalinks, Methodentext, Skalierung und Einheiten, „Parameter
  übernehmen“;** Schnitt in Fassung 2.

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
| Mehrere PRs ändern `ENTSCHEIDUNGSLOG.md` am Ende | vor dem Fertigmelden `main` holen, alle Zeilen erhalten, eigene ans Ende |
