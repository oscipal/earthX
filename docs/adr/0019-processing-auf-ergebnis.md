# ADR 0019 — Processing auf einem Ergebnis

- **Status:** **Angenommen** von Otto am 2026-10-26. Alle fünf Fragen aus §9
  sind nach Empfehlung beantwortet (F1–F5: Option 1 der jeweiligen Liste). Die
  Umsetzung folgt als eigene Aufgabe NM4-05b nach dem Merge dieses ADR.
- **Datum:** 2026-10-26
- **Aufgabe:** NM4-05 laut `docs/plans/querschnitt/nm4-05-processing-auf-ergebnis.md`
  (Backlog-Punkt 5 in `docs/plans/nach-m4-backlog.md`).
- **Autonomiestufe:** C. Kein Produktivcode, keine Änderung an `backend/`,
  `frontend/`, Fixtures, `.github/`, `.claude/`, `CLAUDE.md` oder den
  Lock-Dateien. Die Umsetzung bekommt nach Ottos Entscheidung eine eigene
  Aufgabe.
- **Vorab fest:**
  - Otto möchte ein Job-Ergebnis als Ausgangspunkt eines neuen Rezepts nutzen,
    etwa erst NDVI rechnen und darauf weiterrechnen, ohne alles in einen
    Auftrag zu packen (Backlog-Punkt 5, 20.10.2026).
  - Bis zur Entscheidung ist ⚙ in der Zeile eines Ergebnis-Layers
    ausgeblendet; es erscheint wieder, wenn NM4-05 umgesetzt ist (Log
    26.10.2026, UI-01d; das geht UI-01 §1 Punkt 11 vor).
  - Regel vom 26.10.2026: Was grundsätzlich nicht geht, wird ausgeblendet; was
    nur im Moment nicht geht, bleibt gesperrt mit Grund im Tooltip.
- **Grundlage:**
  - `KLAERUNGEN.md` B8 (mit Nachtrag 2026-10-05), B9 (mit Nachtrag 02.10.2026).
  - `architekturplan.md` 3.1, 7.1, 7.3, 7.7.
  - `adr/0013` §5.1, §5.8; `adr/0014` §4.1, §4.3–§4.7, §15d (der zweite der
    beiden Abschnitte mit dieser Nummer), §15k, §15o, §15q;
    `adr/0015` §7.1, §8.1–§8.3, §14c, §14d; `adr/0016` §6.1–§6.3.
  - M4 Q8–Q12 und S3 (`plans/m4/m4-processing-kern.md`);
    `plans/m4/m4-08b-job-api.md` §10 (F4); `plans/vp3/ui-01-app-rahmen.md`
    §1 Punkt 11, §4, §6.6, §6.11.
  - Entscheidungslog bis 26.10.2026.
- **Betroffen je nach Option:** Panel und Layer-Manager im Frontend
  (alle Optionen außer 3); bei Option 1 zusätzlich `processing/recipe.py`,
  `api/intake.py`, `jobs` (Tabelle `earthx_run`, Aufseher), `processing`
  (Lesen einer Arbeitsdatei als Eingabe), Runner, Kachel-Pfad, Permalinks,
  Methodentext.

---

## Methode und Belegstufen

Gelesen am 26.10.2026 auf dem Stand von `main` nach PR #201. Belegstufen wie in
`adr/0016` und `adr/0017`:

- **M:** in dieser Sitzung gemessen, das Skript steht in §11.
- **P:** im Repo gelesen, mit Pfad und Zeile.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Keine Anfragen an Datenquellen.** Die Messung in §3.5 rechnet auf
synthetischen Zahlen.

---

## 0. Kurzfassung

1. **Empfehlung: Option 2.** Ein Klick auf ⚙ am Ergebnis-Layer öffnet das
   Panel mit dem Auftrag dieses Jobs. Dessen Schritte stehen fest am Anfang,
   neue Schritte kommen dahinter. Gestartet wird **ein ganz normaler Auftrag**,
   der alles neu rechnet. Kein neuer Eingabetyp, keine Änderung an API, Rezept,
   Hash, Cache, Runner, Permalink oder Ablauf. Die Umsetzung braucht nur das
   Frontend (§7.1).
2. **Warum nicht gleich Option 1 (Ergebnis per Referenz):** Sie ist eine neue
   Art Eingabe und berührt fast jede Festlegung aus M4. Dazu gehören die
   Fassung der Eingabe (§4.6), der Kern ohne Objektspeicher (B9), der Ablauf
   nach 7 Tagen, der Runner (offline, nur `recipe.json`), Permalinks
   (30 Tage gegen 7 Tage) und die Herkunft. Der Gewinn liegt allein in
   Rechenzeit und Abrufen bei den Quellen. Dieser Gewinn ist heute nicht
   gemessen und ohne Konten und Quoten (M6) auch nicht bepreist.
3. **Option 3 gibt es schon:** „Open in panel“ in den Details eines Jobs holt
   den Auftrag zurück ins Panel (UI-01 §6.6). Dort hängt man Schritte an und
   startet. Für den Job sind das bis zu 16 Schritte (`MAX_ORDER_STEPS`); die
   „höchstens 4“ aus dem Plan gelten nur für die Vorschau in der Kachel (§3.1).
   Option 2 ist ein kurzer Weg dorthin, vom Layer aus, mit festem Anfang.
4. **Preis von Option 2:** Alles wird neu gerechnet, die Quellen werden erneut
   gelesen. Das Ergebnis gleicht nicht immer bitweise dem, was ein Schritt auf
   der gespeicherten Datei ergäbe. In der Kette bleibt der Zwischenwert
   `float64`, die gespeicherte Datei ist schon `float32` oder gerundet.
   Gemessen weichen bei NDVI → `normalize` 22 % der Pixel um ein Bit ab (§3.5).
   Das Panel sagt es im Tooltip.
5. **Option 1 bleibt möglich.** Option 2 wäre auch dann der Weg zum Teilen,
   denn ein Permalink darf keine `jobID` tragen (§5.5). Wiedervorlage mit
   M6, wenn Quoten und Units Rechenzeit bepreisen (F5).

---

## 1. Kontext und Frage

Ein Rezept hat heute genau eine Art Eingabe: einen Datensatz der Registry mit
Item-Gruppen und Asset-Schlüsseln (`processing/recipe.py:276–291`,
`InputRequest`). `api` löst sie bei der Annahme auf: Adresse, Fassung,
Bandangaben, Skalierung (`adr/0014` §4.1). Ein fertiger Job liefert
`result.tif` und `mask.tif` unter `results/{result_id}/` im eigenen
Objektspeicher (`adr/0015` K1). Das Ergebnis lebt 7 Tage ab Abschluss des
Laufs (`objectstore/results.py:31`, `RESULT_TTL`).

**Frage:** Wie kommt ein Nutzer vom Ergebnis-Layer zu einem neuen Rezept, das
darauf aufbaut? Dabei sollen B8, B9 und die Modulgrenzen gelten, die Herkunft
ehrlich bleiben und keine Kennung in URL oder Log gelangen.

---

## 2. Kriterien

| # | Kriterium | Woher |
|---|---|---|
| K1 | Das Rezept beschreibt die Verarbeitung vollständig; ein Ergebnis lässt sich aus seinem `recipe.json` reproduzieren | architekturplan 1.1 Ziel 4, 7.1; `adr/0014` K1 |
| K2 | Cache-Treffer nur mit Fassung jeder Eingabe; kein Hash nach außen | Q8, Q11; `adr/0014` §4.5 |
| K3 | Herkunft und Attribution stimmen für jedes Ergebnis, auch für ein abgeleitetes | Prinzip 2.8; `adr/0014` §15q |
| K4 | Ablauf nach 7 Tagen bleibt einfach; nie ein Ergebnis ohne erklärendes Rezept | Q10; `adr/0015` §7.1, §14d |
| K5 | Der Runner rechnet offline aus `recipe.json` dasselbe wie die Cloud (T2 gegen T2L bitgleich) | Q12; `adr/0014` F9; `adr/0016` §6 |
| K6 | Ein Permalink trägt den Auftrag, keine Kennung eines Jobs, und hält 30 Tage | `adr/0014` §15o; `adr/0015` §14d |
| K7 | Keine `jobID`, `result_id`, AOI, kein Hash und kein `href` in URLs der App oder in Logs | Q8; `adr/0014` §4.7; Plan NM4-05 §4 |
| K8 | B8 und B9 bleiben unberührt; keine Eingabe per Referenz im Sinne von OGC (S3) | B8, B9; `adr/0014` §15d |
| K9 | Wenig Neues: kleine Umsetzung, keine neue Abhängigkeit, keine Lockerung | architekturplan 1.1 Ziel 6; `CLAUDE.md` |
| K10 | Kosten und Rücksicht auf die Quellen | architekturplan 1.1 Ziel 5; `adr/0013` §5.7 |

---

## 3. Befunde

### 3.1 Wie viele Schritte ein Auftrag hat — [P]

- Ein Auftrag nimmt bis zu **16** Schritte (`api/intake.py:154`,
  `MAX_ORDER_STEPS`; Abweisung mit `422`, Zeile 630). Das Panel liest die
  Grenze aus der Prozessbeschreibung (`frontend/src/processingOrder.ts:85`).
- **4** ist die Grenze einer Kette **in der Kachel** (`api/tiler.py:405`,
  `MAX_OPERATOR_STEPS`; `adr/0014` §15m). Das Panel zeigt auf der Karte den
  längsten Anfang aus Kachel-Schritten und sagt, wie viele es sind.
- Der Satz „höchstens 4 Schritte“ in Plan NM4-05 §3 meint also die Vorschau,
  nicht den Job.

### 3.2 Der Browser hält den Auftrag jedes Jobs — [P]

- Beim Start legt das Panel den gesendeten Auftrag zum Job, bis 64 KB
  (`frontend/src/jobShelf.ts:22`, `MAX_ORDER_BYTES`; UI-01 §6.6). Das gilt
  auch für jeden Teil eines Batches (`frontend/src/processingStore.ts:869`).
- „Open in panel“ in den Details holt ihn zurück
  (`frontend/src/components/JobDetails.tsx:97–133`, `restoreOrder`). Ohne
  Kopie ist der Knopf gesperrt, mit Grund im Tooltip.
- Ein `recipe.json` aus einem ZIP lässt sich im Panel öffnen; `readRecipe`
  macht daraus einen Auftrag und lässt `resolved`, `provenance` und
  `recipe_id` weg (`frontend/src/recipeFile.ts`, M4-19d).
- Der Ergebnis-Layer kennt seine `jobID` (`frontend/src/layers.ts:96–111`,
  `ResultLayerInfo`), also auch den Eintrag mit dem Auftrag.

**Folge [A]:** Option 2 und Option 3 brauchen keinen neuen Weg zum Auftrag. Er
liegt im Browser oder in der Datei des Nutzers, auch nach dem Ablauf des
Ergebnisses.

### 3.3 Was ein Ergebnis heute ist — [P]

- `result.tif` (das ganze Rechteck) und `mask.tif` (die Fläche des Jobs) liegen
  unter `results/{result_id}/`. Dazu kommen `recipe.json`, `citation.bib` und
  `attribution.txt` (`adr/0015` §8.1). `result_id` ist zufällig und kennt nur
  die Queue (`adr/0015` §14c).
- **Keine Prüfsumme der Datei.** Weder Queue noch Objektspeicher halten einen
  Inhalts-Hash von `result.tif`. `hashlib` kommt in `jobs` nur für den
  Löschschlüssel der Permalinks vor (`jobs/permalinks.py:47`). Die Prüfsummen
  von botocore beim Hochladen stehen auf „when_required“
  (`objectstore/client.py:51–54`) und werden nirgends abgelegt. Eine Eingabe
  „Ergebnis“ hätte heute also keine Fassung im Sinne von `adr/0014` §4.6.
- **Ablauf:** 7 Tage ab Abschluss des Laufs. Ein Cache-Treffer verlängert
  nichts (`adr/0015` §14d). Die Bucket-Regel löscht nach Schreibzeit. Ein
  Treffer braucht mindestens 24 Stunden Restlaufzeit (§8.3, T1).
- **Zeilen:** `earthx_job` und `earthx_run` hängen mit `RESTRICT` aneinander
  (`catalog/migrations/006_jobs.sql`). Der stündliche Aufräumer löscht erst die
  Objekte, dann die Zeilen (`adr/0013` §5.8).

### 3.4 Wo der Kern liest — [P]

- Der Kern liest Quellen nur über `readers`. Jede Adresse hat vorher
  `check_url` passiert (`processing/source.py`, Kopf). Seine eigenen Dateien
  öffnet er nur im Arbeitsordner (`processing/workfile.py`; Test
  `test_no_direct_open.py`).
- Der `tiler` liest Ergebnisse über eine von `objectstore` signierte URL, im
  Modul `api`, ohne `gateway` (`adr/0015` §14c). Das ist die Ausnahme vom
  Nachtrag zu B8. Für `processing` gilt sie nicht: B9 verbietet dem Kern den
  Objektspeicher.
- Der Runner prüft Datensatz und Host jeder Eingabe gegen die Registry seines
  Images. Ein unbekannter bricht mit Exit-Code 3 ab (`adr/0016` §6.2, A1). Er
  hat keinen Weg zur Plattform.

### 3.5 Kette gegen Weiterrechnen auf der Datei — [M]

In einer Kette bleibt der Zwischenwert `float64`; erst der letzte Schritt wird
in den Ausgabetyp gewandelt (`processing/core.py:94`, `_INTERMEDIATE_DTYPE`;
Zeile 532). Rechnet ein zweiter Auftrag auf der gespeicherten Datei, liest er
den schon gewandelten Wert. Gemessen mit numpy 2.5.3 und numexpr 2.14.2, so
wie der Kern rechnet, aber ohne den Kern (§11, Skript E):

| Kette | Pixel (endlich) | bitweise verschieden | größte Abweichung |
|---|---|---|---|
| NDVI (`float32`) → `normalize` −1…1 → 0…1 | 4 194 259 | 26,8 % | 3,8·10⁻⁶ |
| dasselbe, nur Pixel mit \|NDVI\| ≤ 1 | 3 441 479 | 22,2 % | 6,0·10⁻⁸ (1 ulp bei 0,5…1) |
| NDVI → `ndvi*ndvi`, \|NDVI\| ≤ 1 | 3 441 479 | — | 6,0·10⁻⁸ |

Synthetische Reflexion aus `uint16` mit `scale` 0,0001 und `offset` −0,1 auf
2048². Bei einem Ergebnis in ganzen Zahlen (M4-26, etwa `uint8` nach
`normalize`) wäre der Unterschied so groß wie die Rundung **[A]**.

**Folge:** Option 1 (rechnet auf der Datei) und Option 2 (rechnet die Kette)
liefern verschiedene Bytes. Keiner der beiden Wege ist falsch. Sie beantworten
aber verschiedene Fragen: „was ergibt dieser Schritt auf genau dieser Datei“
gegen „was ergäbe der ganze Weg in einem Auftrag“.

---

## 4. Optionen

### Option 1 — Ergebnis als Eingabe per Referenz

Eine zweite Art Eingabe im Auftrag, neben dem Datensatz:

```json
{"name": "prev", "job": "<jobID>"}
```

- **Annahme in `api`:** `jobID` → Job → Lauf → `result_id`. Der Lauf muss
  erfolgreich sein, das Ergebnis mindestens 24 Stunden Rest haben (wie T1 in
  `adr/0015` §8.3), Fläche und Bänder kommen aus dem Ergebnis.
- **Im Rezept** steht nicht die `jobID`, sondern
  - `derived_from`: das Rezept des Elternjobs ohne `recipe_id`; so erklärt das
    Rezept sich selbst (K1), auch wenn die Eltern ablaufen,
  - `version`: SHA-256 von `result.tif`. Das ist **neu**: Der Aufseher müsste
    die Prüfsumme beim Hochladen bilden und am Lauf ablegen (§3.3).
- **Der Lauf** hält intern die `result_id` der Eingabe (neue Spalte,
  Migration). Vor dem Kern lädt der Aufseher `result.tif` und `mask.tif` in
  den Arbeitsordner. Er darf `objectstore` importieren, der Kern nicht (B9).
  Der Kern liest die Eingabe als Arbeitsdatei. Das ist eine neue Art `Source`
  ohne `check_url`, weil keine Adresse im Spiel ist.
- **Fläche:** die des Elternjobs, fest. Eine andere AOI wäre ein neuer Zuschnitt
  auf einer schon zugeschnittenen Datei.
- **Vorschau:** Eine Kachel-Kette auf einem Ergebnis gibt es nicht. Der `tiler`
  liest Ergebnisse (`/results/{result_id}/…`), aber ohne Operator. Das wäre
  eine neue Route mit `processing.tile` auf einer nicht geprüften Quelle.

### Option 2 — Schritte an den alten Auftrag anhängen, alles neu rechnen

Kein neuer Eingabetyp. Der Auftrag des Elternjobs (§3.2) plus die neuen
Schritte ist **ein gewöhnlicher Auftrag**: dieselben Eingaben, dieselbe Fläche,
dieselben Items, die Schritte hintereinander, eine Ausgabe.

- Das Panel baut ihn; das Backend sieht einen Auftrag wie jeden anderen.
- Woher der Auftrag kommt: die Kopie im Browser. Ohne sie bleibt „Open
  recipe.json“ mit der Datei aus dem ZIP (F2).
- Grenzen wie heute: 16 Schritte je Auftrag, 4 in der Vorschau.

### Option 3 — nicht anbieten, Ketten im selben Auftrag

Nichts Neues. ⚙ am Ergebnis-Layer bleibt ausgeblendet. Wer weiterrechnen
will, öffnet die Details des Jobs, wählt „Open in panel“, hängt Schritte an
und startet. Das geht heute schon (§3.2). Technisch ist es dasselbe wie
Option 2, nur ohne festen Anfang und ohne Weg vom Layer.

### Verworfen ohne eigene Option

- **Signierte URL des Ergebnisses als Eingabe** (Kern oder Runner liest sie
  direkt): Der Kern griffe auf den Objektspeicher zu (gegen B9). Die Adresse
  bestünde `check_url` gegen die Registry nicht (B8). Im Runner läge eine
  signierte URL in einer Datei, die man weitergibt. Sie erlischt nach Minuten
  und verrät `result_id` und Schlüssel-ID (`adr/0015` §6.2, §14c).
- **Ergebnis als Datensatz der Registry** (jedes Ergebnis ein Eintrag mit
  `asset_hosts` = Objektspeicher): Die Registry ist kuratiert und hat
  Lizenzstufen (B11, B13). Ein Ergebnis eines Nutzers ist kein Datensatz.
- **Zwischenergebnisse einer Kette cachen** (Präfix-Cache, damit Option 2 nicht
  neu liest): Das ist ein eigener Entwurf mit Speicherkosten und neuen
  Schlüsseln. Er lässt sich auf Option 2 später aufsetzen, wenn die Kosten es
  verlangen (F5).

---

## 5. Bewertung

### 5.1 Hash und Cache (`adr/0014` §4.5)

| | Option 1 | Option 2 | Option 3 |
|---|---|---|---|
| Kern des Hashs | neu: Eingabe mit `derived_from` und SHA-256 von `result.tif`; `engine` wie heute | unverändert, der zusammengesetzte Auftrag | unverändert |
| Fassung (Q11) | braucht die neue Prüfsumme; ohne sie kein Treffer | wie die Eltern: `file:checksum`, ETag, `updated` | wie heute |
| Treffer auf die Eltern | nicht nötig: Die Eltern sind gerechnet, gelesen wird die Datei | keiner; der längere Auftrag ist ein neuer Schlüssel, der Anfang wird neu gerechnet | wie Option 2 |
| Zweiter gleicher Auftrag | Treffer, wenn Prüfsumme und Schritte gleich sind | Treffer wie heute | wie heute |
| Hash nach außen (K2) | nein; die Prüfsumme der Datei steht in `recipe.json` wie `file:checksum` einer Quelle **[A]** | nein | nein |

### 5.2 Herkunft und Attribution (`adr/0014` §15q)

- **Option 1:** Die Attribution erbt der Kindjob von den Eltern: Jahre aus
  `acquired_first_year`/`acquired_last_year` des Elternjobs, beim Annehmen
  kopiert. Lizenzprüfung, `citation.bib` und Methodentext lesen die Datensätze
  aus `derived_from`. Neu ist ein Satz im Methodentext („Derived from a
  previous result: …“) und eine Verschachtelung in `methods.py`, `citation.py`,
  `intake.py`. Eine Kette von Ableitungen braucht eine Tiefengrenze, etwa 3;
  sonst wächst `recipe.json` über die Grenzen aus `adr/0016` (4 MiB).
- **Option 2 und 3:** Ein Auftrag wie jeder andere. Datensatz, Items, Jahre
  und Lizenz sind die der Eltern, weil es dieselben Eingaben sind. Methodentext
  und `citation.bib` beschreiben die ganze Kette. Kein Verweis auf den
  Elternjob: Das Ergebnis stammt aus den Quellen, nicht aus der Datei. Haben
  die Quellen inzwischen eine andere Fassung, steht das in `recipe.json`
  (Prinzip 2.9, ehrlich statt still).

### 5.3 Ablauf nach 7 Tagen

| | Option 1 | Option 2 | Option 3 |
|---|---|---|---|
| Eltern abgelaufen | Eingabe weg: `410` bei der Annahme, ⚙ ausgeblendet (grundsätzlich nicht mehr möglich) | geht weiter, solange der Auftrag im Browser oder als `recipe.json` vorliegt und die Quellen ihn noch bedienen | wie Option 2 |
| Eltern laufen während der Warteschlange ab | neuer Fehler `input_expired`; Annahme nur mit 24 h Rest (§4) | entfällt | entfällt |
| Kind überlebt die Eltern | ja, bis 7 Tage nach eigenem Abschluss; `derived_from` erklärt es | ja, ohne Bezug | ja |
| Aufräumer | muss die neue Spalte kennen; keine Fremdschlüssel zwischen Läufen, sonst blockiert `RESTRICT` das Löschen der Eltern | unverändert | unverändert |
| Frist verlängern | ein Kind verlängert die Eltern nie (`adr/0015` §14d) | entfällt | entfällt |

### 5.4 Runner (offline, nur `recipe.json`)

- **Option 1:** Der Runner kann die Eingabe nicht holen, denn er hat keinen Weg
  zur Plattform und keinen Objektspeicher (`architekturplan.md` 3.1). Drei
  Wege, alle neu:
  - (a) abweisen, Exit-Code 2 mit Grund;
  - (b) `--input prev=/in/result.tif` (mit `mask.tif`) aus dem ZIP der
    Eltern; der Runner prüft die SHA-256 gegen `version`. Er liest dann eine
    lokale Datei außerhalb seines Arbeitsordners, was er heute nie tut;
  - (c) die Eltern aus `derived_from` selbst rechnen. Dann rechnet er Option 2
    und weicht von der Cloud ab (§3.5); T2 gegen T2L ist nicht mehr bitgleich
    (gegen K5).

  Nur (b) hält K5.
- **Option 2 und 3:** unverändert. `recipe.json` des Kindes ist ein
  gewöhnliches Rezept mit Quellen der Registry; Cloud und Runner rechnen
  bitgleich wie heute.

### 5.5 Permalinks (M4-19e)

- **Option 1:** Ein Permalink hält den Auftrag 30 Tage. Ein Auftrag mit
  `"job": "<jobID>"` trüge die `jobID` der Eltern in einen geteilten Link. Wer
  ihn öffnet, hätte damit Zugriff auf Status, Ergebnis und `recipe.json`
  (mit AOI) des Elternjobs. Nach spätestens 7 Tagen zeigte der Link ins Leere.
  Also müsste „Share“ den Auftrag vorher **flach machen**: die Schritte der
  Eltern vor die eigenen, die Eingaben der Eltern statt `job`. Das ist genau
  Option 2. Oder „Share“ bleibt für solche Aufträge gesperrt.
- **Option 2 und 3:** unverändert. Der Permalink hält den zusammengesetzten
  Auftrag, 30 Tage, ohne Kennung eines Jobs.

### 5.6 Datenschutz (K7)

- **Option 1:** Die `jobID` steht im Rumpf des Auftrags, nie in der URL. Sie
  darf nicht ins gespeicherte Rezept, nicht in `recipe.json` des Kindes, nicht
  in Logs und nicht in eine Fehlermeldung („result of job … expired“). Die
  `result_id` bleibt in der Queue. Eine Regel und ein Test mehr. Der Zugriff
  folgt der `jobID` wie heute der Download. Wer sie hat, sieht ohnehin
  `recipe.json` mit AOI; die AOI der Eltern in `derived_from` legt nichts
  Neues offen **[A]**.
- **Option 2 und 3:** keine neue Stelle. Der Auftrag kommt aus dem Browser;
  die `jobID` dient nur zum Nachschlagen der Kopie im Browser.

### 5.7 B8, B9 und „Eingaben per Referenz“ (S3)

- **S3** meint Eingaben als **Link** im Sinne von OGC Requirement 18 B: eine
  Adresse, die der Server abruft (`adr/0014` §15d). Keine Option hier holt
  eine fremde Adresse. Ein Eingang mit `href` bleibt `400`, `conformsTo` bleibt
  leer.
- **Option 1** ist trotzdem eine Referenz, aber auf eine **interne** Kennung.
  B8 bleibt, weil der Objektspeicher über `objectstore` läuft (Nachtrag
  2026-10-05). B9 bleibt nur, wenn der Aufseher die Datei vorher in den
  Arbeitsordner legt und der Kern keine URL sieht (§4). Neu ist eine Eingabe,
  die nicht durch `check_url` geht. Sie braucht eine eigene, eng gefasste
  Regel im Kern, mit Test.
- **Option 2 und 3:** unverändert.

### 5.8 Zusammenfassung

| Kriterium | Option 1 | Option 2 | Option 3 |
|---|---|---|---|
| K1 reproduzierbar aus `recipe.json` | ~ mit `derived_from` und Prüfsumme | ✓ | ✓ |
| K2 Hash und Cache | ~ neue Fassung nötig | ✓ unverändert | ✓ |
| K3 Herkunft, Attribution | ~ Vererbung neu zu bauen | ✓ | ✓ |
| K4 Ablauf | ✗ neue Fehlerfälle, 24-h-Regel | ✓ | ✓ |
| K5 Runner bitgleich | ~ nur mit lokaler Datei (b) | ✓ | ✓ |
| K6 Permalink | ✗ braucht Flachmachen (= Option 2) oder Sperre | ✓ | ✓ |
| K7 keine Kennung in URL/Log | ~ eine Regel mehr | ✓ | ✓ |
| K8 B8, B9, S3 | ~ neue Eingabe ohne `check_url` | ✓ | ✓ |
| K9 wenig Neues | ✗ Backend, Migration, Kern, Runner, Tiler, Frontend | ✓ nur Frontend | ✓ nichts |
| K10 Kosten, Quellen | ✓ liest nur die Datei | ✗ liest alles neu | ✗ wie Option 2 |
| Bedienung vom Layer aus | ✓ | ✓ | ✗ nur über die Details des Jobs |
| Rechnet auf genau der Datei | ✓ | ✗ (§3.5) | ✗ |

---

## 6. Empfehlung

**Option 2 jetzt; Option 1 nur, wenn Kosten es später verlangen.**

- Otto will vom Ergebnis aus weiterrechnen, ohne alles in einen Auftrag zu
  packen. Option 2 erfüllt das in der Bedienung: Der Nutzer packt nichts
  zusammen, das Panel tut es. Im Backend bleibt es ein Auftrag. So bleibt jede
  Festlegung aus M4 unberührt, auch die, die am teuersten zu ändern wären:
  Hash, Runner, Permalink, Ablauf.
- Option 1 hätte den einen Vorteil, dass Abrufe und Rechenzeit gespart werden.
  Den kann heute niemand in Zahlen fassen. Es gibt keine Units, keine Quoten,
  keinen Preis (M6). Die Rechnung einer 8192²-Szene dauerte lokal rund 9 bis
  24 Sekunden, ohne Lesezeit (`adr/0014` §3.5). Bezahlt würde dieser Vorteil
  mit Änderungen in Kern, Queue, Annahme, Runner, Kachel-Pfad und Frontend
  und mit zwei neuen Fehlerfällen (§7.2).
- Auch mit Option 1 bräuchte „Share“ das Flachmachen aus Option 2 (§5.5).
  Option 2 ist damit kein Umweg, sondern der Teil, der in jedem Fall entsteht.
- Option 3 allein verschenkt den Weg vom Layer, den Otto ausdrücklich nennt.

**Ehrlichkeit von Option 2:** Der Tooltip an ⚙ und an „Start“ sagt, dass der
ganze Weg neu gerechnet wird. Das Ergebnis kann bitweise von einem Schritt auf
der gespeicherten Datei abweichen (§3.5).

---

## 7. Folgen

### 7.1 Folgen von Option 2 (empfohlen)

- **Frontend:**
  - ⚙ erscheint wieder in der Zeile eines Ergebnis-Layers;
    `layerProcessBlock` gibt dafür keinen Grund mehr zurück.
  - Das Panel öffnet mit dem Auftrag des Jobs. Dafür gibt es eine neue Stufe
    neben `restoreOrder`, etwa „extendOrder“: Die Schritte der Eltern stehen
    fest am Anfang, Fläche und Auswahl sind fest (§8).
  - Tests: ⚙ vorhanden und aktiv mit Kopie, gesperrt ohne Kopie; der
    gesendete Auftrag ist Eltern plus neue Schritte; die feste Schritte lassen
    sich nicht ändern; 16 Schritte gesamt; Vorschau mit höchstens 4
    Kachel-Schritten; abgelaufenes Ergebnis (F4).
- **Backend:** keine Änderung. Das Backend sieht einen gewöhnlichen Auftrag;
  derselbe Auftrag aus einem Guss gibt denselben Hash und damit einen Treffer.
- **Doku:** Nachtrag in `adr/0014` (ein Ergebnis ist keine Eingabe; der Weg
  über das Panel); Log-Zeile; UI-01 §1 Punkt 11 als erledigt vermerken.
- **Stufe:** A, nur Frontend (Vorschlag).

### 7.2 Folgen von Option 1

- `processing/recipe.py`: neue Eingabeart in `InputRequest`/`Input` mit
  `derived_from` und `version` aus SHA-256. `recipe_version` 2 oder ein
  diskriminiertes Feld; ältere Rezepte bleiben gültig.
- `jobs`: Prüfsumme beim Hochladen; Spalte für die `result_id` der Eingaben
  (Migration); Laden in den Arbeitsordner vor dem Kern; Fehler
  `input_expired`; Aufräumer.
- `processing`: `Source` aus einer Arbeitsdatei, ohne `check_url`, mit Test,
  dass nur der Aufseher sie setzen kann.
- `api`: Annahme (`jobID` im Rumpf, 24 h Rest, Bänder aus dem Ergebnis,
  Attribution geerbt), Flachmachen für „Share“, Methodentext und
  `citation.bib` verschachtelt, Kachel-Kette auf einem Ergebnis.
- Runner: `--input name=Datei` mit Prüfsumme (§5.4 b), README.
- Frontend: Eingabe „Result“ im Panel, Sperre mit 24-h-Grund, Ausblenden nach
  Ablauf.
- **Stufe:** B, eigener Plan; nach Richtwert mehrere PRs.

### 7.3 Folgen von Option 3

- Keine Änderung am Code. Die Log-Zeile vom 26.10.2026 („⚙ erscheint wieder,
  wenn NM4-05 umgesetzt ist“) wird zu „⚙ bleibt ausgeblendet; Weg über die
  Details“.

---

## 8. Panel-Skizze (Option 2; kein Code)

Texte Englisch, kurz; Erklärungen im Tooltip (UI-01 §4).

```
Layer-Manager, Zeile eines Ergebnis-Layers
  👁  NDVI · sentinel-2-c1-l2a · 26 Oct   ▬▬  ▲ ▼  ⚙  ⇩  ⚠  ✕
                                                   └ tooltip: "Process further"

PROCESSING
  From result  NDVI · sentinel-2-c1-l2a · 26 Oct          ⓘ
               └ tooltip: "Runs the original steps again, then yours."
  Input        sentinel-2-c1-l2a · 3 scenes · AOI only    🔒
  Steps
    🔒 1. Band_Math_1          (aus dem Auftrag, fest, zuklappbar)
    ── your steps ──
       2. Normalize_2   [Band_Math_1]  …                  ✕
       + Add step
  Output       float32 ▾
  Map shows 2 of 2 steps
  [ Review ]  [ Start ]
```

- **Kopf:** „From result“ mit Titel des Elternjobs; ⓘ trägt den Satz zur
  Neuberechnung.
- **Eingabe:** Datensatz, Szenen und Fläche aus dem Auftrag, gesperrt (🔒,
  Tooltip „Fixed by the result.“). Kein „Run as“ (ein Auftrag), „Area“ fest wie
  in NM4-06.
- **Schritte:** Die Schritte der Eltern stehen gesperrt am Anfang, zugeklappt
  auf eine Zeile, wenn es mehrere sind. Neue Schritte zählen weiter (NM4-10:
  „2. Normalize_2“). Die Chips zeigen die Bänder nach dem letzten
  Elternschritt; die Regel kommt aus dem Backend wie in M4-18b.
- **Grenzen:** „+ Add step“ gesperrt bei 16 Schritten gesamt („At most 16
  steps“, gibt es schon). Die Vorschau zeigt den längsten Anfang aus
  Kachel-Schritten, also höchstens 4 und nur, solange kein Elternschritt `T2`
  ist (etwa `reproject`). Der Hinweis „Map shows N of M steps“ gibt es schon.
- **Ausgabe:** Vorgabe ist der Typ der Eltern.
- **Vorgabetitel:** Titel der Eltern plus „→ Normalize“.
- **⚙ gesperrt** (im Moment nicht möglich), mit Tooltip:
  - ohne Kopie des Auftrags im Browser: „No copy of the original order is kept
    in this browser. Open its recipe.json instead.“ (F2);
- **Abgelaufenes Ergebnis:** ⚙ bleibt (F4), Tooltip „Expired: runs everything
  again from the scenes.“ Das ist kein Widerspruch zur Regel vom 26.10.2026,
  denn es geht weiterhin.

Bei **Option 1** sähe die Eingabe anders aus: ein Chip „Result · <title>“ mit
dem Band des Ergebnisses statt Datensatz und Szenen. „Start“ wäre gesperrt bei
weniger als 24 h Rest („Expires too soon to be used as input.“). Nach Ablauf
wäre ⚙ ausgeblendet, und „Share“ würde flach machen oder gesperrt sein.

---

## 9. Fragen an Otto — beantwortet am 2026-10-26

Otto hat alle fünf Fragen mit Option 1 der jeweiligen Liste beantwortet, also
nach Empfehlung. Die Fragen stehen mit ihrem ursprünglichen Wortlaut da; die
Antwort folgt je Frage. Die Nummer der Antwort ist die Nummer in der Liste der
Frage, nicht die Nummer der Option aus §4: Bei F1 ist die Liste „1. Option 2“.

**F1 — Welche Option?**
1. Option 2: Schritte an den Auftrag des Ergebnisses anhängen, ein gewöhnlicher Auftrag, alles neu gerechnet; nur Frontend **(Empfehlung)**
2. Option 1: Ergebnis als neue Eingabe per Referenz (eigener Plan, Stufe B, Backend, Runner, Kachel, Frontend)
3. Option 3: nichts bauen; weiter über „Open in panel“ in den Details, ⚙ bleibt ausgeblendet

**Antwort F1: (1)** Option 2 aus §4: Schritte an den Auftrag des Ergebnisses
anhängen, ein gewöhnlicher Auftrag, alles neu gerechnet; nur Frontend.

**F2 — Ergebnis-Layer ohne Kopie des Auftrags im Browser (nur bei F1 = 1)?**
1. ⚙ gesperrt mit Grund; der Tooltip verweist auf „Open recipe.json“ mit der Datei aus dem ZIP **(Empfehlung)**
2. Wie 1, dazu holt das Panel `recipe.json` des Jobs über die bestehende Route, solange das Ergebnis lebt, und macht daraus den Auftrag (`readRecipe`)
3. ⚙ ausblenden, wenn keine Kopie da ist

**Antwort F2: (1)** ⚙ gesperrt mit Grund; der Tooltip verweist auf „Open recipe.json“
mit der Datei aus dem ZIP.

**F3 — Die Schritte der Eltern im Panel (nur bei F1 = 1)?**
1. Gesperrt am Anfang, nur anhängen; wer ändern will, nimmt „Open in panel“ **(Empfehlung)**
2. Frei änderbar wie bei „Open in panel“ (dann unterscheidet sich ⚙ nur im Einstieg davon)

**Antwort F3: (1)** Die Schritte der Eltern stehen gesperrt am Anfang, neue Schritte
werden nur angehängt.

**F4 — Abgelaufenes Ergebnis (nur bei F1 = 1)?**
1. ⚙ bleibt verfügbar; der Tooltip sagt, dass alles aus den Szenen neu gerechnet wird **(Empfehlung)**
2. ⚙ ausblenden wie den Download

**Antwort F4: (1)** ⚙ bleibt bei einem abgelaufenen Ergebnis verfügbar; der Tooltip
sagt, dass alles aus den Szenen neu gerechnet wird.

**F5 — Option 1 später wieder vorlegen?**
1. Ja, als Log-Zeile „offen“ mit Wiedervorlage bei M6 (Konten, Quoten, Units), wenn die Kosten des Neurechnens messbar werden **(Empfehlung)**
2. Nein, Option 1 ist verworfen

**Antwort F5: (1)** Ja. Option 1 (Ergebnis per Referenz) bleibt als Log-Zeile „offen“
mit Wiedervorlage bei M6 (Konten, Quoten, Units), wenn die Kosten des
Neurechnens messbar werden.

---

## 10. Was offen bleibt

- **Vorschau-Layer** (`derived: 'preview'`) tragen ⚙ weiter gesperrt. Ob sie
  denselben Weg bekommen, ist die offene Frage aus UI-01d (Log 26.10.2026).
  Mit Option 2 ginge es auf dieselbe Weise, sofern der Layer seinen Auftrag
  hält **[A]**. Das ist nicht Teil dieser Vorlage.
- **Präfix-Cache** für Ketten (§4, verworfen) nur, wenn F5 auslöst.
- Die Umsetzung: eigene Aufgabe **NM4-05b** nach dem Merge dieses ADR, Stufe A,
  nur Frontend (§7.1). Nachtrag in `adr/0014` (ein Ergebnis ist keine Eingabe;
  der Weg über das Panel) und der Vermerk in UI-01 §1 Punkt 11 gehören dazu.
- Die Wiedervorlage von Option 1 bei M6 (F5) steht als Zeile „offen“ im
  Entscheidungslog.

---

## 11. Prüfanleitung für Otto

Nur Repo und Browser, keine AOI, keine Anfrage an eine Quelle. Windows
PowerShell 5.1 im Repo-Ordner.

**A. Grenzen der Schritte (§3.1).** Erwartung in Klammern.

```powershell
git fetch origin
Select-String -Path backend\earthx\api\intake.py -Pattern '^MAX_ORDER_STEPS'
#   (MAX_ORDER_STEPS = 16)
Select-String -Path backend\earthx\api\tiler.py -Pattern '^MAX_OPERATOR_STEPS'
#   (MAX_OPERATOR_STEPS = 4)
Select-String -Path frontend\src\jobShelf.ts -Pattern 'MAX_ORDER_BYTES ='
#   (export const MAX_ORDER_BYTES = 64 * 1024;)
```

**B. Keine Prüfsumme eines Ergebnisses (§3.3).**

```powershell
Select-String -Path backend\earthx\jobs\*.py, backend\earthx\objectstore\*.py -Pattern 'sha256|checksum'
#   (jobs\permalinks.py: Löschschlüssel; objectstore\client.py: botocore-Einstellung „when_required“; sonst nichts)
```

**C. Option 3 gibt es schon (§3.2), im Browser.**

1. App öffnen, einen kleinen Band-math-Job starten und warten, bis er fertig
   ist.
2. Processing-Manager öffnen, den Job anklicken, „Open in panel“ wählen.
   (Das Panel zeigt den Auftrag mit seinem Schritt.)
3. „+ Add step“, etwa `normalize` −1…1 → 0…1, dann „Review“.
   (Schätzung für einen Auftrag mit zwei Schritten; „Start“ rechnet alles neu.)
4. Im Layer-Manager: Die Zeile des Ergebnis-Layers hat kein ⚙ (Platz leer).

**D. Messung §3.5 nachrechnen (optional, Python mit numpy und numexpr).**
Skript E, als `chain.py` speichern, mit `python chain.py` starten:

```python
import numpy, numexpr
rng = numpy.random.default_rng(42)
n = 2048
red = rng.integers(1, 10000, (n, n), dtype=numpy.uint16).astype("float64") * 0.0001 - 0.1
nir = rng.integers(1, 10000, (n, n), dtype=numpy.uint16).astype("float64") * 0.0001 - 0.1
ndvi = numexpr.evaluate("(nir-red)/(nir+red)")              # Zwischenwert der Kette: float64
norm = lambda x: (x + 1.0) / 2.0                             # normalize -1..1 -> 0..1
chain = norm(ndvi).astype("float32")                         # Option 2: ein Auftrag
on_file = norm(ndvi.astype("float32").astype("float64")).astype("float32")  # Option 1
ok = numpy.isfinite(chain) & (numpy.abs(ndvi) <= 1)
d = (chain.view("uint32") != on_file.view("uint32")) & ok
print(ok.sum(), d.sum(), 100 * d.sum() / ok.sum())
#   (3441479 764814 22.2…)
```

`norm` ist hier verkürzt; in der Messung stand die volle Formel von
`normalize` v1 mit `out_min` 0 und `out_max` 1. Beide ergeben dieselben Werte.

**E. Kein Produktivcode im PR.**

```powershell
git diff --stat origin/main...origin/claude/relaxed-rubin-4saw3t
#   (nur Dateien unter docs/)
```
