# ADR 0024 — Prototyp-Quellen

- **Status:** Entwurf, offen. Entscheidungen F1–F10 (§9) liegen bei Otto.
- **Datum:** 2026-10-31
- **Aufgabe:** M5-02 laut `docs/plans/m5/m5-discovery-und-suche.md` §5a (§4 D, Antwort 3).
- **Autonomiestufe:** C — nur gelesen und berichtet. Kein Produktivcode geändert,
  keine Datenquelle aufgerufen, kein Messskript nötig.
- **Stand des untersuchten Codes:** `main` nach #258/#259 (31.10.2026).
- **Grundlage:** `ENTSCHEIDUNGEN_2026-09-18.md` §1, §3, §4; `KLAERUNGEN.md` B8,
  B10, B11, B12, B13; `architekturplan.md` 3.1, 4.3, 4.4, 5.1, 12.1, 12.3;
  `projektuebersicht.md` §2 (Prinzipien 2, 12), §5; `adr/0008`, `adr/0016`,
  `adr/0017`, `adr/0018` §11 C; M5-Plan §2 Punkte 3–5, §5 Antwort 3.

---

## Methode und Belegstufen

Belegstufen wie in `adr/0016` bis `adr/0018`:

- **P:** am Primärdokument selbst gelesen (im Repo mit Pfad und Zeile).
- **A:** eigene Ableitung, ein Argument und kein Beleg.

Keine Messung (**M**) und keine Web-Recherche: Die Frage ist eine nach der
eigenen Architektur, nicht nach einer Quelle. Dieses Dokument ist **keine
rechtliche Einschätzung** einer Quelle und keine Lizenz-Einstufung; beides
bleibt bei Otto (`CLAUDE.md`, M5-Plan §7).

---

## 1. Anlass und Frage

Otto will im Prototyp für die eigene Erprobung auch Quellen mit **unklarer
Rechtslage** nutzen; in der veröffentlichten Version sollen sie verschwinden
(M5-Plan §2 Punkt 5). Sie dürfen ins öffentliche Repo, aber markiert. Dieses ADR
soll festlegen (Antwort 3):

1. wie eine solche Quelle im Repo markiert ist,
2. wie sie nur im Prototyp für Otto geladen wird,
3. wie sie aus veröffentlichten und Cloud-Konfigurationen technisch
   ausgeschlossen ist,
4. wie die Oberfläche sie kennzeichnet,
5. wie Weitergabe per Permalink oder geteiltem Cache verhindert wird.

Das weicht von B11 ab: B11 kennt nur geprüfte Lizenzen mit drei Stufen. Eine
Prototyp-Quelle ist eine Quelle, deren Stufe nicht feststeht, die Otto aber
trotzdem ansehen und verarbeiten will.

## 2. Begriffe (Vorschlag)

| Begriff | Bedeutung |
|---|---|
| **Prototyp-Quelle** | Registry-Eintrag, dessen Lizenz Otto nicht nach B11 einstufen konnte (keine oder mehrdeutige Lizenz, Stufe unbestimmbar). Status setzt nur Otto. |
| **Prototyp-Instanz** | Ottos lokale Compose-Instanz mit eigener Datenbank und eigenem Objektspeicher, ausdrücklich so konfiguriert (§6 R4). |
| **Veröffentlichte Konfiguration** | Alles andere: jedes gebaute Image (auch das Runner-Image, das Nutzer erhalten, `adr/0016`), CI, Live-Smoke, Cloud-Sitzungen, jedes Deployment ab M6, eine selbst gehostete Ausgabe (`architekturplan.md` 12.1). |

Vorbild ist BIOMASS: „Solange der Token gilt, darf Otto BIOMASS lokal als
Testdaten nutzen. In CI, Cloud-Sitzungen und Fixtures kommt BIOMASS nicht vor“
(`ENTSCHEIDUNGEN` §3) [P]. Damals hielt das nur eine Regel in `CLAUDE.md` und
`SECURITY.md`; der Code lag im Hauptpfad, und sein Entfernen brauchte ein
eigenes ADR (`adr/0008`) [P]. Lehre [A]: Die Trennung gehört in die Technik,
nicht nur in einen Absatz.

## 3. Befund am Code

Wo die Registry heute wirkt — dort muss eine Prototyp-Quelle fehlen oder
markiert sein:

| Stelle | Heute | Folge für Prototyp-Quellen |
|---|---|---|
| `catalog/datasets.py:735` | `REGISTRY` ist eine Modulkonstante aus zwei Einträgen; importiert in `catalog/load.py`, `api/main.py`, `api/tiler.py`, `discovery/materialize.py`, `runner/cli.py`, `runner/recipe_file.py` [P] | Ein Schalter muss an **einer** Stelle wirken, nicht an sechs |
| `backend/Dockerfile:52`, `:57` | Das Image kopiert nur `earthx/`; das Runner-Image baut darauf auf [P] | Was außerhalb des Pakets liegt, ist in keinem Image — auch nicht im Runner-Image für Nutzer |
| `catalog/registry.py:134` | `Maturity` beschreibt, wie vorläufig die Quelle ist, nicht ihr Recht [P] | Kein passendes Feld vorhanden; `Maturity` nicht umdeuten |
| `catalog/registry.py:285–303` | `LicenseInfo` mit Flags und `tier` (B11) [P] | Bleibt; bei einer Prototyp-Quelle ist `tier` Ottos Arbeitsannahme, nicht Freigabe |
| `catalog/datasets.py:695`, `registry.py:1409` | `RETIRED` hält ausgeschiedene Datensätze mit Nachfolger, `410` statt „unbekannt“ (`adr/0017`) [P] | Weg für eine Prototyp-Quelle, die später freigegeben wird (§6 R9) |
| `catalog/pgstac.py:118` | `catalog-load` entfernt föderierte Collections, die die Registry nicht mehr nennt; materialisierte bleiben [P] | Reste einer abgeschalteten Prototyp-Quelle bleiben teils in pgstac |
| `api/dependencies.py:136–149`, `api/intake.py:351` | Erlaubte Hosts kommen aus der Registry (`endpoint`, `asset_hosts`) [P] | Ohne geladenen Eintrag lehnt das Gateway die Hosts der Quelle ab — ein zweiter, freier Riegel |
| `catalog/search_cache.py:40` | Such-Cache in Postgres mit Spalte `dataset_id` [P] | Reste sind über die ID auffindbar |
| `jobs/submit.py:9–13` | Gleiche Aufträge teilen sich einen Lauf und sein Ergebnis [P] | In der Prototyp-Instanz nur Otto; kein Problem, solange die Instanz lokal bleibt |
| `jobs/permalinks.py:1–30` | „Share“ legt einen Permalink mit Auftrag und Ansicht an, 30 Tage [P] | Muss für Prototyp-Datensätze gesperrt sein (Antwort 3) |
| `api/tiler.py` | Setzt an Kacheln kein `Cache-Control` (Suche nach dem Kopf ohne Treffer) [P] | Für Prototyp-Datensätze ausdrücklich `private, no-store` |
| `frontend/src/api.ts:122` | Das Frontend liest die Datensätze aus `/stac/collections`; außerhalb von Tests ist keine Datensatz-ID verdrahtet [P] | Nichts landet im Bundle; die Marke muss aus der Collection kommen |
| `.github/workflows/ci.yml:1–3`, `live-smoke.yml:1–11` | CI erreicht keine Datenquelle; Live-Smoke läuft geplant gegen echte Quellen [P] | Live-Smoke darf Prototyp-Quellen nie ansprechen |

## 4. Kriterien

| # | Kriterium |
|---|---|
| K1 | **Kein Weg in eine veröffentlichte Konfiguration**, auch nicht durch einen Fehler in einer Umgebungsvariable |
| K2 | **Sichtbar markiert** im Repo, im Eintrag, in Adressen und Dateinamen, in der Oberfläche |
| K3 | **Keine Weitergabe:** kein Permalink, kein geteilter Cache, keine Auffindbarkeit (Sitemap, JSON-LD) |
| K4 | **Eine Wahrheit** (B13 Punkt 3): kein zweiter Registry-Typ, derselbe Lader, dieselben Prüfungen |
| K5 | **Aufräumbar:** Abschalten hinterlässt keine Reste in Datenbank und Objektspeicher |
| K6 | **Wenig Aufwand** für 1–3 Personen; passt zum YAML-Lader aus M5-03 (B13 Stufe 2) |
| K7 | **Prüfbar** durch Tests ohne Netz und ohne echte Daten der Quelle |

## 5. Optionen

**Achse 1 — Markierung im Eintrag**

| | Option | Bewertung |
|---|---|---|
| M1 | Neues Pflichtfeld `legal_status` (`cleared` / `unclear`) ohne Vorgabe (B10), bei `unclear` Pflichtsatz `legal_note` | klar, maschinenlesbar, ins STAC-Feld abbildbar (K2, K4) |
| M2 | Neuer Wert `LicenseTier.PROTOTYPE` | vermischt „was erlaubt die Lizenz“ mit „ist sie geklärt“; jeder Code, der `tier` liest, müsste den Wert kennen [A] |
| M3 | Reserviertes Präfix der Datensatz-ID, z. B. `proto-` | sichtbar in jeder Adresse, jedem Rezept, jedem Dateinamen, jedem Cache-Schlüssel; Reste per Präfix auffindbar (K2, K5); allein aber nur eine Konvention |

**Achse 2 — Ablage und Laden**

| | Option | K1 | K4 | K6 | Bewertung |
|---|---|---|---|---|---|
| A1 | Im Paket wie alle Einträge, Filter zur Laufzeit per Schalter | schwach: Einträge in jedem Image, auch im Runner-Image; eine falsche Variable schaltet sie frei | gut | gut | ein Riegel |
| A2 | Eigenes Verzeichnis **außerhalb** des Python-Pakets, nicht im Image, nur per Override-Datei in Ottos Compose gemountet und per Pfad geladen | stark: physisch nicht im Image | gut, wenn derselbe YAML-Lader | gut mit M5-03 | zwei Riegel (Image + Schalter) |
| A3 | Eigener Branch oder Fork | stark | schlecht: Branch läuft auseinander, keine CI | schlecht | widerspricht dem Git-Review (4.4) |
| A4 | Gar nicht im Repo, nur lokal (`.gitignore`) | stark | schlecht: kein Review, keine Versionierung, keine Hilfe aus Cloud-Sitzungen | mittel | Antwort 3 erlaubt das Repo ausdrücklich |

**Achse 3 — Absicherung beim Start**

| | Option | Bewertung |
|---|---|---|
| S1 | Nur der Pfad-Schalter | ein Fehler in der Cloud-Konfiguration genügt [A] |
| S2 | Pfad-Schalter **und** Variable `EARTHX_PROFILE` (`local`, `ci`, `cloud`), Pflicht sobald der Pfad gesetzt ist; Prototyp-Einträge nur bei `local`, nie bei gesetztem `CI` | zwei unabhängige Fehler nötig; das Profil nützt auch M6 [A] |

## 6. Empfehlung

**M1 + M3, A2, S2**, dazu Regeln für Oberfläche und Weitergabe. Als Regelwerk:

- **R1 Status nur durch Otto.** `legal_status` setzt Otto, wie jede
  Lizenz-Einstufung. `license-checker` und der Harvester (M5-03) schlagen höchstens
  „Lizenz unklar“ vor; der Harvester legt nie selbst eine Prototyp-Quelle an.
- **R2 Was Prototyp werden darf.** Nur Quellen, deren Recht **unklar** ist. Quellen,
  deren Bedingungen die Nutzung **ausdrücklich untersagen**, oder die Konto,
  Schlüssel oder das Umgehen einer Sperre verlangen, bleiben ausgeschlossen; die
  Regel „ohne Schlüssel“ (M5-Plan §2 Punkt 3) gilt auch hier (F1).
- **R3 Markierung.** Pflichtfeld `legal_status` ohne Vorgabe; bei `unclear` ein
  Satz `legal_note` (was unklar ist, keine Rechtsmeinung) und die ID mit Präfix
  `proto-`. Der Lader prüft beides gegeneinander: `unclear` ⇔ `proto-`. In der
  Collection als `earthx:legal_status` und `earthx:legal_note` (`architekturplan.md`
  5.1, neue Zeile bei Annahme).
- **R4 Ablage und Laden.** Prototyp-Einträge liegen als YAML in einem eigenen
  Verzeichnis außerhalb von `backend/earthx/` (Name mit M5-03 abzustimmen, z. B.
  `catalog/prototype/` neben den kuratierten Einträgen). Das Image kopiert nur
  `earthx/` und die freigegebenen Einträge (`Dockerfile:52`); Prototyp-Einträge
  kommen nur über eine Compose-Override-Datei unter `compose/` als Mount hinein.
  Derselbe Lader wie für alle Einträge, eine Registry je Prozess, gebaut an einer
  Stelle statt sechs Importen einer Konstante (§3).
- **R5 Schalter.** Geladen wird nur, wenn `EARTHX_PROTOTYPE_SOURCES` auf das
  Verzeichnis zeigt **und** `EARTHX_PROFILE=local` gesetzt ist **und** `CI` nicht
  gesetzt ist. Jede andere Kombination mit gesetztem Pfad ist ein Startfehler,
  kein stilles Weglassen (B10-Geist: Vergessen fällt auf). Der Runner lädt
  Prototyp-Einträge nie (er ist zum Weitergeben gebaut, `adr/0016`); ein
  `recipe.json` mit `proto-`-Datensatz ist dort „unbekannt“.
- **R6 Aufräumen.** `catalog-load` ohne Schalter entfernt alles mit Präfix
  `proto-`: Collections samt materialisierter Items, Zeilen der Caches. Jobs und
  Ergebnisse laufen nach ihrer Frist aus (7 Tage, `architekturplan.md` 12.3); ein
  neuer Job auf einen `proto-`-Datensatz ist ohne Eintrag ohnehin unbekannt.
- **R7 Keine Weitergabe.** `POST` eines Permalinks mit einem `proto-`-Datensatz
  im Auftrag: `409` mit eigenem Text; „Share“ im Panel ausgegraut mit Tooltip.
  Jede HTTP-Antwort, die Daten eines Prototyp-Datensatzes trägt (Kachel,
  Quicklook, Statistik, Zuschnitt, Ergebnis), mit `Cache-Control: private,
  no-store`. Nie in Sitemap oder JSON-LD (M5, Auffindbarkeit), nie im
  Bewertungs-Set der Suche (M5-04). Download bleibt erlaubt (Otto will
  erproben), mit Hinweis in `ATTRIBUTION.txt`, dass die Rechtslage unklar ist und
  die Datei nicht weitergegeben werden soll; die Dateinamen tragen die ID samt
  Präfix.
- **R8 Oberfläche.** Marke „Prototype“ am Datensatz in Liste, Layer-Manager und
  Download-Fenster, Tooltip mit `legal_note`; in der Kopfzeile ein dauerhafter
  Hinweis „Prototype sources on“, solange ein solcher Eintrag geladen ist. Die
  Marke kommt aus der Collection, nicht aus Code im Frontend (M5-Plan §2
  Punkt 7). Texte bei Annahme mit Otto.
- **R9 Wege hinaus.** Klärt Otto die Rechtslage, wird die Quelle ein normaler
  Eintrag mit neuer ID ohne Präfix; die Prototyp-ID bekommt keinen
  `RETIRED`-Datensatz, weil es außerhalb der Prototyp-Instanz nie Rezepte darauf
  gab [A]. Verliert umgekehrt eine freigegebene Quelle ihre Klarheit (Health-Check
  meldet Lizenzänderung, `architekturplan.md` 4.5), entscheidet Otto: Prototyp,
  Katalogeintrag (B11) oder Ausscheiden nach `adr/0017`.
- **R10 CI und Cloud-Sitzungen.** CI parst und prüft die Prototyp-Einträge wie
  alle anderen (Form, Pflichtfelder, `unclear` ⇔ `proto-`), ohne sie in eine
  Registry zu laden und ohne Netz. Live-Smoke spricht sie nie an. Fixtures für
  Prototyp-Quellen sind nur synthetisch (`CLAUDE.md`). Cloud-Sitzungen dürfen
  Einträge schreiben und prüfen, aber die Quellen nicht abrufen; die Messungen
  des Onboardings (Checkliste Punkt 6, CORS, Formate) macht Otto lokal (F8).

**Tests, die die Regeln halten (bei Umsetzung)** [A]:

1. Die Registry ohne Schalter enthält keinen `unclear`-Eintrag und keine `proto-`-ID.
2. Pfad gesetzt, Profil nicht `local` oder `CI` gesetzt: Startfehler, je Fall.
3. `legal_status: unclear` ohne Präfix und Präfix ohne `unclear`: Ladefehler.
4. `Dockerfile` kopiert das Prototyp-Verzeichnis nicht (Text- oder Build-Prüfung).
5. Runner lehnt ein Rezept mit `proto-`-Datensatz ab, auch mit gesetztem Schalter.
6. Permalink mit `proto-`-Datensatz: `409`; Antworten mit Daten: `no-store`.
7. `catalog-load` ohne Schalter entfernt `proto-`-Collections und Cache-Zeilen,
   materialisierte eingeschlossen; freigegebene bleiben.
8. Die Oberfläche zeigt Marke und Kopfhinweis nur bei `earthx:legal_status: unclear`.

Alle mit synthetischen Einträgen, wie heute der Zarr-Testeintrag (`adr/0017`).

**Aufwand (Schätzung, [A]):** Lader-Teil und Startprüfung 100–200 Zeilen plus
Tests, setzt den YAML-Lader von M5-03 voraus; Weitergabe-Sperren und `no-store`
50–100; Oberfläche 80–150. Zwei bis drei PRs unter dem Richtwert.

## 7. Bewertung der Empfehlung

| Kriterium | Wie erfüllt |
|---|---|
| K1 | Drei unabhängige Riegel: nicht im Image (R4), Schalter mit Profil (R5), Gateway kennt die Hosts nur mit geladenem Eintrag (§3) |
| K2 | Verzeichnis, Feld, Präfix, Collection-Feld, Marke (R3, R8) |
| K3 | Permalink gesperrt, `no-store`, keine Sitemap/JSON-LD (R7) |
| K4 | Ein Lader, ein Eintragstyp, ein Feld mehr (R3, R4) |
| K5 | Präfix macht Reste auffindbar, `catalog-load` räumt (R6) |
| K6 | Hängt am ohnehin geplanten YAML-Lader; kein eigener Dienst |
| K7 | Acht Tests ohne Netz (§6) |

## 8. Risiken und Grenzen

- **Kein Nutzungsrecht durch Technik.** Die Regeln senken die Weitergabe, sie
  machen die Nutzung durch Otto nicht rechtmäßig. Ob eine Quelle für die eigene
  Erprobung genutzt werden darf, bleibt Ottos Abwägung je Quelle [A].
- **Öffentliches Repo.** Endpunkt und Name einer Prototyp-Quelle sind öffentlich
  lesbar; Otto hat das in Antwort 3 angenommen. Der Eintrag nennt nur, was zum
  Laden nötig ist, keine Bewertung der Quelle oder ihres Betreibers.
- **Lokale Instanz ist Ottos Verantwortung.** Wer die Prototyp-Instanz mit
  `EARTHX_PROFILE=local` an eine geteilte Datenbank oder einen geteilten
  Objektspeicher hängt, umgeht R6/R7 teilweise. Die Override-Datei setzt deshalb
  eigene Dienste voraus; prüfen lässt sich das beim Start nicht sicher [A].
- **Datensatzspezifischer Code** (`datasets/<id>`, eigener Adapter) einer
  Prototyp-Quelle liegt im Paket und damit im Image, ist dort aber ohne Eintrag
  unerreichbar. Wo es geht, generische Adapter (CKAN, OGC) nutzen.
- **Abhängigkeit von M5-03.** Ohne YAML-Lader gibt es keinen sauberen Ort
  außerhalb des Pakets (F10).

## 9. Fragen an Otto

**F1 — Was darf Prototyp-Quelle werden?**
1. Nur Quellen mit **unklarer** Rechtslage; ausdrücklich untersagte Nutzung,
   Konto, Schlüssel oder Umgehen einer Sperre bleiben ausgeschlossen (**Empfehlung**)
2. Auch ausdrücklich untersagte, solange ohne Schlüssel

**F2 — Markierung im Eintrag**
1. Feld `legal_status` + `legal_note` **und** Präfix `proto-`, gegenseitig geprüft (**Empfehlung**)
2. Nur das Feld
3. Nur das Präfix

**F3 — Ablage**
1. Eigenes Verzeichnis außerhalb des Pakets, nie im Image, per Compose-Override gemountet (**Empfehlung**)
2. Im Paket, Filter zur Laufzeit
3. Gar nicht im Repo, nur lokal

**F4 — Schalter**
1. Pfad `EARTHX_PROTOTYPE_SOURCES` **und** Profil `EARTHX_PROFILE=local`, nie mit `CI`; Runner lädt nie (**Empfehlung**)
2. Nur der Pfad

**F5 — Reste nach dem Abschalten**
1. `catalog-load` entfernt alles mit `proto-`; Jobs laufen nach Frist aus (**Empfehlung**)
2. Start verweigern, solange Reste da sind

**F6 — Weitergabe**
1. Permalink gesperrt (`409`, Knopf ausgegraut), `no-store`, keine Sitemap/JSON-LD; Download erlaubt mit Hinweis (**Empfehlung**)
2. Zusätzlich Download sperren

**F7 — Kennzeichnung in der Oberfläche**
1. Marke „Prototype“ an Liste, Layer-Manager, Download-Fenster und Hinweis in der Kopfzeile (**Empfehlung**)
2. Nur Marke am Datensatz

**F8 — CI und Cloud-Sitzungen**
1. CI prüft die Einträge ohne Netz; Cloud-Sitzungen schreiben Einträge, rufen die Quelle nicht ab; Messungen macht Otto lokal (**Empfehlung**)
2. Cloud-Sitzungen dürfen messen, wenn Otto den Host freigibt
3. Prototyp-Einträge gar nicht in CI

**F9 — In der veröffentlichten Version**
1. Verschwindet vollständig (deine Vorgabe) (**Empfehlung**)
2. Du kannst je Quelle zusätzlich einen Katalogeintrag (B11 Stufe 1, nur Metadaten und Link) freigeben; der ist dann ein eigener, freigegebener Eintrag

**F10 — Zeitpunkt**
1. Erste Prototyp-Quelle erst mit dem YAML-Lader aus M5-03 (**Empfehlung**)
2. Vorher übergangsweise im Python-Modul mit Laufzeitfilter (A1)

## 10. Folgen bei Annahme (nicht Teil dieses Entwurfs)

- `KLAERUNGEN.md` B11: Nachtrag „Prototyp-Quellen nach `adr/0024`“.
- `architekturplan.md` 5.1: Zeilen `earthx:legal_status`, `earthx:legal_note`.
- `projektuebersicht.md` §5: Nachtrag zur Lizenzregel.
- `docs/cloud-umgebung.md`: Regel aus R10.
- M5-03 (`adr/0025`): Ort des Prototyp-Verzeichnisses neben den kuratierten
  Einträgen, Harvester setzt nie `legal_status`.
- M5-04 (`adr/0026`): Bewertungs-Set ohne Prototyp-Datensätze.
- Umsetzung als Stufe B nach M5-03, eigene Aufgabe in Fassung 2 des M5-Plans.
