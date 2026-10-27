# NM4-27 — Jobs löschen mit einem Tag Frist und „Restore“

**Stand:** 26.10.2026, beauftragt von Otto (Backlog-Punkt 27 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach dem Merge von UI-01c (#196). Höchstens zwei Stufe-B-Sessions gleichzeitig; nicht gleichzeitig mit UI-01e (Backend-Route im selben Bereich).
**Startsatz:** „Führe Aufgabe NM4-27 aus `docs/plans/querschnitt/nm4-27-job-loeschen-mit-frist.md` aus.“

## 1. Anlass

In UI-01 hatte Otto festgelegt, dass Jobs nicht löschbar sind, nur archivierbar (12.10.2026). Am 26.10.2026 hat er das erweitert: Ein Job soll sich wirklich löschen lassen – mit Frist, damit ein Versehen rückgängig zu machen ist.

## 2. Soll

- **Delete (Kürzel D, Menüpunkt „Delete (D)“):** Das Ergebnis des Jobs wird nach **einem Tag** gelöscht, oder früher, wenn es ohnehin vorher abläuft (7-Tage-Frist). Keine Rückfrage beim Löschen.
- **Restore:** Innerhalb dieses Tages lässt sich der Job wiederherstellen; danach gilt wieder die ursprüngliche Ablaufzeit. Die Zeile zeigt, bis wann Restore möglich ist.
- **Reiter:** „Active | Expired | Deleted | All“. „Deleted“ zeigt gelöschte Jobs (innerhalb der Frist mit Restore, danach als endgültig gelöscht). Die Einträge bleiben im Browser, auch wenn der Server den Job nicht mehr kennt.
- **Vom Server vergessene Jobs (Fund 26.10.2026):** Antwortet der Server auf einen Job aus der Ablage mit `404` (etwa nach Abbruch oder zurückgesetzter Datenbank), erscheint er als „No longer available“ im Reiter „Deleted“ bzw. „Expired“, nicht als aktiv; kein wiederholtes Abfragen. Test dazu.
- **Geteilte Ergebnisse:** Dient dasselbe Ergebnis noch einem anderen Job (Cache-Treffer, `adr/0013`), verschwindet es nur für den gelöschten Job; die Datei bleibt, bis kein Job mehr darauf zeigt. Ein gelöschter Job liefert nach der Frist keine Treffer mehr.

## 3. Umfang

- Backend in `jobs`, `api` und `objectstore` (über `earthx.objectstore`, B8-Nachtrag): Frist speichern (ursprüngliche Ablaufzeit merken), Aufräumer löscht nach der Frist, sofern kein anderer Job auf das Objekt zeigt.
- Frontend: Kürzel D auf fokussierter Job-Zeile (nur dort, nie in Eingabefeldern), Menüpunkt, Restore, Reiter „Deleted“; Batch: Delete für den ganzen Batch und je Teil.

## 4. Im Plan klären (mit Optionen und Empfehlung)

- **Schnittstelle:** `DELETE /processing/jobs/{jobID}` für fertige Jobs mit Frist (OGC „dismiss“) oder eine eigene Route; Restore als eigene Route. Was antwortet ein gelöschter Job innerhalb der Frist (Status, Downloads gesperrt oder noch erlaubt)?
- **Laufende Jobs:** Bleibt „Cancel“ (sofortiger Abbruch) davon getrennt? Vorschlag ja.
- **Cache:** Ab wann zählt ein gelöschter Job nicht mehr als Treffer – sofort oder nach der Frist?
- **Permalinks (M4-19e):** unberührt, sie halten nur den Auftrag – im Plan bestätigen.
- Nachträge in `adr/0013` und `adr/0015` (Frist, Aufräumer), Migration nur als neue Datei.

## 5. Grenzen

- Keine `jobID` in Logs oder URLs außer der bestehenden Job-Route.
- Bestehende Migrationen bleiben unverändert (Prüfsummen-Test).
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 6. Abnahme

- Tests: Delete setzt die Frist (kürzer, wenn der Job vorher abläuft); Restore innerhalb der Frist stellt die Ablaufzeit her, danach nicht mehr; Aufräumer löscht nur, wenn kein anderer Job auf das Objekt zeigt; Datenschutz wie M4-19e; Frontend: Kürzel, Reiter, Restore, Batch.
- Gegenprobe: Mit dem alten Code scheitern die neuen Tests.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n) mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat, siehe Kopf des Backlogs).
- Vor „fertig“ ist main geholt.

---

# Plan (27.10.2026)

Belegstufen wie in `adr/0009`: [P] am Primärdokument oder im Code gelesen, [A] eigene Ableitung. Gemessen wurde nichts; die Aufgabe ist nicht rechenrelevant.

Voraussetzungen geprüft: UI-01c (#196) und UI-01e (#206) sind gemergt. Offen ist nur UI-02a (#211), ein Frontend-PR zu Basemap und Ansicht; er berührt den Processing-Manager nach seiner Dateiliste nicht. NM4-34 läuft nicht.

## 7. Kurzfassung

- **Schnittstelle:** `DELETE /processing/jobs/{jobID}` bleibt die eine Route (OGC „dismiss“). Für einen wartenden oder laufenden Job bleibt sie der Abbruch wie heute. Für einen fertigen (erfolgreich oder gescheitert) wird sie zum Löschen mit Frist. Dazu kommt `POST /processing/jobs/{jobID}/restore` (außerhalb von OGC). Frage 1.
- **Frist:** Die Spalte `earthx_job.deleted_until` (neue Migration `015_job_deleted.sql`) wird gesetzt auf `least(jetzt + 1 Tag, Ablauf des Laufs)`. Die ursprüngliche Ablaufzeit muss nicht eigens gemerkt werden: Sie steht unverändert in `earthx_run.expires_at`. Restore leert die Spalte, danach gilt wieder diese Zeit.
- **Innerhalb der Frist** antwortet der Job wie heute ein verworfener Job: `404` auf allen Routen, Downloads gesperrt. Nur `restore` kennt ihn noch. Frage 2.
- **Cache:** Ein Lauf, an dem nur noch gelöschte (oder verworfene) Jobs hängen, ist ab dem Löschen kein Treffer mehr. Nach einem Restore ist er es wieder. Frage 4.
- **Aufräumer:** Nach der Frist entfernt er die Zeile des Jobs. Hängt kein lebender Job mehr am Lauf, löscht er auch das Objekt und den Lauf, sonst bleiben beide. Die Bucket-Regel (7 Tage) bleibt als Netz.
- **Frontend:** Reiter „Active | Expired | Deleted | All“, Kürzel `D`, Menüpunkte „Delete“ und „Restore“, Batch als Ganzes und je Teil. Ein Job, den der Server mit `404` nicht mehr kennt, wird gespeichert und nie wieder abgefragt.
- **Permalinks (M4-19e)** sind nicht berührt: Sie halten nur den Auftrag, keinen `jobID` und kein Ergebnis [P] (`jobs/permalinks.py`, Kopf).

## 8. Befund im Code

- **Job und Lauf [P]** (`jobs/submit.py`, Migration 006): Ein Ergebnis gehört zum Lauf (`earthx_run.result_id`, `expires_at`). Mehrere Jobs teilen sich einen Lauf: gleichzeitig gleiche Aufträge oder ein Cache-Treffer. Ein Job hat keine eigene Ablaufzeit.
- **`DELETE` heute [P]** (`submit.dismiss`): Er setzt `earthx_job.dismissed`. Bei einem fertigen Job bleibt das Ergebnis bis zum Ablauf des Laufs, weil es anderen als Treffer dienen kann (Plan F5). Der Job antwortet danach überall `404` (`_live_job`, K8). Das Frontend ruft `DELETE` nur für „Cancel“. Vorher fragt es den Zustand frisch ab, damit ein inzwischen fertiger Job nicht verworfen wird (`processingStore.cancelJob`).
- **OGC [P]:** „Dismiss can be seen as cancelling a running job or removing artifacts of a finished job“. Die Antwort ist `200` mit `statusInfo`, `status` = `dismissed`. Ein unbekannter Job ist `404` (OGC API – Processes 1.0, `core/sections/clause_14_dismiss.adoc`, `requirements/dismiss/REQ_job-dismiss-success.adoc`, Stand wie in `adr/0014` §16). Ein „Restore“ kennt OGC nicht. Die API erklärt ohnehin keine Konformität (`adr/0014` §15d).
- **Aufräumer [P]** (`jobs/cleanup.py`): Er löscht stündlich abgelaufene Läufe: erst das Objekt, dann Jobs und Lauf, danach Rezepte ohne Bezug. Der Lauf verweist auf das Rezept des ersten Jobs (`earthx_run.recipe_id`). Gelesen wird es nur beim Abholen durch den Worker (`queue.CLAIM_SQL`).
- **Kacheln eines Ergebnisses [P]** (`api/result_tiles.py`) laufen über `result_id`, nicht über den Job. Der Server kann bei einer Kachel nicht sagen, für welchen Job sie geholt wird.
- **Fund 26.10.2026 [P]:** Einen Job mit `404` setzt das Frontend auf die Phase `gone` und zeigt ihn als „Expired“ (`jobView.jobState`). Diese Phase wird nicht gespeichert. Nach jedem Neuladen steht der Job deshalb wieder als `active` mit „Checking…“ unter „Active“ und wird erneut abgefragt (`processingStore.jobEntry`, `followJob`). Bei mehreren Tabs fragt jeder Tab. Bleibt die Antwort aus oder ist sie ein `5xx`, steht er dauerhaft als aktiv da. Das deckt Ottos Beobachtung, gesehen habe ich sie selbst nicht.

## 9. Backend

**Migration `015_job_deleted.sql`** (neue Datei, 006–014 unverändert):

```sql
ALTER TABLE public.earthx_job ADD COLUMN deleted_until timestamptz;
CREATE INDEX earthx_job_deleted_until_idx ON public.earthx_job (deleted_until) WHERE deleted_until IS NOT NULL;
```

**`jobs/submit.py`:**

- `DELETE_GRACE = timedelta(days=1)`.
- `dismiss` sperrt zuerst den Lauf (`FOR UPDATE`) und entscheidet dann nach seinem Zustand:
  - `accepted`/`running`: wie heute (`dismissed = true`, Abbruch nur ohne weiteren lebenden Job).
  - `successful`/`failed`: `deleted_until = least(clock_timestamp() + DELETE_GRACE, r.expires_at)`, `dismissed` bleibt `false`.
  - Bisher wird erst `dismissed` gesetzt und danach gesperrt. Die neue Reihenfolge verhindert, dass ein Lauf zwischen Lesen und Sperren fertig wird und der Job dann falsch behandelt wird.
- `restore(conn, job_id) -> JobStatus | None`: `deleted_until = NULL` nur, wenn die Frist noch läuft, der Lauf nicht abgelaufen ist und der Job nicht verworfen wurde. Für einen lebenden, nicht gelöschten Job gibt es seinen Zustand zurück (idempotent), sonst `None`.
- `_status`: Ein Job mit `deleted_until` gilt als `dismissed`. Damit antworten `_live_job`, die Ergebnis-Links, `/events` und die Bündel (`MISSING.txt`: „no longer available“) ohne eigene Regel. `JobStatus` bekommt `deleted_until`. Die Antwort auf `DELETE` setzt `expires` auf die Frist.
- **Cache-Treffer** (`_run_for`): Zusätzlich gilt: `EXISTS` (lebender Job: nicht verworfen, nicht gelöscht) `OR NOT EXISTS` (gelöschter Job). Ein Lauf mit nur verworfenen Jobs bleibt also ein Treffer wie heute (F5). Einer, an dem nur noch Gelöschte hängen, ist keiner.

**`jobs/cleanup.py`**, im selben Batch und unter demselben Lock, vor den Rezepten:

1. Jobs mit `deleted_until < clock_timestamp()` holen (`LIMIT batch`, `FOR UPDATE`), dazu ihre Läufe sperren.
2. Für jeden solchen Lauf: Er läuft nicht, und kein Job daran lebt (nicht verworfen und nicht gelöscht mit laufender Frist)? Dann das Objekt löschen (`delete_result`), danach alle Jobs des Laufs und den Lauf.
3. Sonst nur die Zeilen der abgelaufenen gelöschten Jobs löschen. Zeigt `run.recipe_id` auf das Rezept eines davon, übernimmt der Lauf das Rezept eines verbleibenden Jobs (Frage 9). So geht das Rezept des Gelöschten (AOI, `recipe_id`) mit der Frist.
4. Die bestehende Rezeptlöschung räumt danach auf. `CleanupResult` zählt `deleted_jobs`. Die Logzeile nennt nur Zahlen.

Schlägt das Löschen eines Objekts fehl, rollt der Batch zurück wie heute. Gelöscht wird bis zu eine Stunde nach der Frist, die API antwortet schon ab der Frist mit `404`.

**`api/processing_route.py`:**

- `DELETE /jobs/{jobID}`: Summary „Dismiss a job: cancel it, or delete a finished one (restorable for a day)“. Die Antwort trägt `status` = `dismissed` und `expires` = Frist (bei Abbruch wie heute).
- `POST /jobs/{jobID}/restore`: `200` mit `statusInfo` (ursprünglicher `expires`). `404` mit dem festen Text für unbekannt, falsch geformt, verworfen, nicht mehr in der Frist oder abgelaufen. `Cache-Control: no-store`, kein Body. Im Zugriffslog steht wie bei allen Job-Routen die Vorlage `{jobID}`.
- Modul-Docstring und OpenAPI-Beschreibung nachziehen.

**Nachträge:** `adr/0013` §10c (Löschen mit Frist, Cache-Regel, Aufräumer). `adr/0015` §14g: Ein Objekt kann vor den 7 Tagen gehen, die Bucket-Regel bleibt das Netz. F13 bekommt die Umhängung des Rezepts. In `adr/0014` §9 nennt die Zeile zu `DELETE` dann „Abbruch oder Löschen mit Frist“.

## 10. Frontend

- **`processing.ts`:** `deleteJob(jobId): Promise<StatusInfo>` (ersetzt `dismissJob`, Cancel nutzt dieselbe Funktion) und `restoreJob(jobId)`.
- **`jobShelf.ts`** (Format bleibt Version 1, optionale Felder wie `titleDefault`):
  - `deletedUntil: string | null`: die Restore-Frist, gesetzt beim Löschen.
  - `lost: boolean`: Der Server hat `404` gesagt, der Job wird nie wieder abgefragt.
  - Ein fehlerhafter Wert wird verworfen, der Eintrag bleibt.
- **`processingStore.ts`:**
  - `deleteTarget(target)` und `restoreTarget(target)` für Job und Batch.
  - Ein fertiger Job, der noch nicht abgelaufen ist, geht an den Server: Bei `200` gilt `deletedUntil = expires`, bei `404` wird er als gelöscht und `lost` markiert.
  - Abgelaufene, abgebrochene und verlorene Einträge werden nur im Browser gelöscht: Frist ein Tag, Restore lokal (Frage 7).
  - Ein Batch löscht alle Teile, die nicht warten oder laufen.
  - `onGone` setzt `lost` und speichert. `jobEntry` und `followJob` fragen einen verlorenen oder gelöschten Job nicht ab.
- **`jobView.ts`:** zwei neue Zustände.
  - `deleted`: Text „Deleted“, solange die Frist läuft mit „until …“ (Tooltip „Restore possible until …“), danach ohne Datum.
  - `lost`: Text „No longer available“.
  - Ein Batch gilt als gelöscht, wenn alle Teile es sind.
- **`ProcessingManager.tsx`:**
  - Reiter „Active | Expired | Deleted | All“ (`preferences.JobFilter` um `deleted` erweitert, gespeichert). „Active“ und „Expired“ zeigen keine gelöschten Einträge.
  - Kürzel `D` auf der fokussierten Zeile, nach den Regeln von R/G/A: nie in Feldern, im Menü oder mit Strg/Alt/Meta. Auf einem Teil wirkt `D` auf den Batch (wie R/G/A).
  - Menüpunkt „Delete“ mit `aria-keyshortcuts="D"`, für jeden Teil eines Batches auch. Bei einem wartenden oder laufenden Job ist er ausgeblendet (Regel 26.10.2026), ebenso bei einem Batch mit wartendem oder laufendem Teil. Dort bleibt „Cancel“.
  - Auf einer gelöschten Zeile innerhalb der Frist: „Restore“ im Menü und das Symbol ↺ am Platz des Download-Symbols, Tooltip mit der Frist.
  - Keine Rückfrage beim Löschen. Der Fokus geht wie bei `A` auf die Nachbarzeile, wenn die Zeile den Reiter verlässt.
- **`JobDetails.tsx`:** Ein gelöschter Job zeigt „Deleted“, die Frist und „Restore“, ohne Download.
- **Ergebnis-Layer** eines gelöschten Jobs: nach Frage 6.

## 11. Tests (Gegenprobe: am alten Code rot)

**Backend** (`tests/earthx/jobs/test_submit.py`, `test_cleanup.py`, `tests/earthx/api/test_processing_route.py`, echtes Postgres wie bisher):

- Löschen setzt die Frist auf jetzt + 1 Tag. Bei einem Lauf, der früher abläuft, auf dessen Ablauf. `DELETE` auf einen laufenden Job bricht weiter ab und setzt keine Frist.
- Innerhalb der Frist ist `GET`, `/results`, `/results/result.zip`, `/events` und `DELETE` ein `404` mit demselben Text wie für eine unbekannte Kennung. Ein Bündel nennt den Job in `MISSING.txt`.
- Restore in der Frist stellt Zustand und ursprüngliches `expires` her, die Links gehen wieder. Nach der Frist (Uhr über `clock_timestamp` verstellt bzw. Zeile zurückdatiert) ist es `404`, ebenso für einen abgebrochenen Job.
- Cache: Nach dem Löschen des einzigen Jobs kein Treffer, nach Restore wieder einer. Löscht einer von zwei Jobs, bleibt der Lauf ein Treffer.
- Aufräumer:
  - Nach der Frist, mit nur einem Job am Lauf: Objekt, Job, Lauf und Rezept sind weg (`delete_result` gerufen).
  - Mit einem zweiten lebenden Job: Das Objekt bleibt, der Lauf auch. Nur die Zeile des Gelöschten und sein Rezept gehen, der Lauf hängt am Rezept des anderen.
  - Innerhalb der Frist: nichts gelöscht.
  - Ein Fehler des Objektspeichers rollt den Batch zurück.
- Datenschutz wie M4-19e: Kein `jobID`, keine `recipe_id`, kein Rezept in Logzeilen (`caplog` über Löschen, Restore, Aufräumen). Zugriffslog nur mit `{jobID}`. Restore mit falsch geformter, unbekannter und abgelaufener Kennung liefert byte-gleiche Antworten.
- Fehleingaben: Restore mit Body, mit falscher Methode (`GET` → `405`), mit überlanger Kennung.

**Frontend** (`processingStore.test.ts`, `jobShelf.test.ts`, `jobView.test.ts`, `ProcessingManager.test.tsx`):

Die Uhr wird festgesetzt, wie es `src/testClock.test.ts` verlangt (Log 27.10.2026).


- `D` löscht die fokussierte Zeile. Kein Löschen in einem Eingabefeld, im Rename, mit Strg/Alt/Meta oder bei offenem Dialog. Auf einem laufenden Job tut `D` nichts.
- Die Reiter filtern richtig, auch für Batches mit teils gelöschten Teilen. Der Reiter wird gespeichert.
- Restore zeigt den Job wieder unter „Active“ mit dem ursprünglichen Ablauf. Nach der Frist gibt es kein Restore.
- Batch: Delete für alle Teile und je Teil, Restore für alle.
- **Fund 26.10.2026:** Ein Job mit `404` erscheint als „No longer available“ (nicht unter „Active“) und wird nach dem Neuladen nicht erneut abgefragt (die Zahl der `fetch`/`EventSource` wird gezählt).
- Eine fehlerhafte Ablage (`deletedUntil` kein Datum, `lost` kein Boolean) wird gelesen, ohne den Eintrag zu verlieren.

**Browser:** Chromium der Sitzung mit nachgestellten Antworten, hell und dunkel, schmales Fenster (Reiter umbrechen nicht über die Panelbreite), `D`, Menü, ↺, Batch. Beschrieben im PR.

## 12. Fragen an Otto

Kurz beantwortbar: je Frage eine Nummer.

**Frage 1 — Schnittstelle?**
1. `DELETE /jobs/{jobID}` bricht wartende und laufende Jobs ab und löscht fertige mit Frist. Restore ist `POST /jobs/{jobID}/restore`. **(Empfehlung: eine Route wie OGC „dismiss“, das Frontend braucht für Cancel nichts Neues)**
2. Eigene Route `POST /jobs/{jobID}/delete` für das Löschen mit Frist. `DELETE` bleibt das heutige endgültige Verwerfen ohne Restore. Zwei Wege zum Löschen.
3. Wie 1, aber Restore mit dem `jobID` im Body (`POST /jobs/restore`), damit die Kennung in keiner neuen Adresse steht.

**Frage 2 — Was antwortet ein gelöschter Job innerhalb der Frist?**
1. `404` auf allen Routen wie heute ein verworfener Job, Downloads gesperrt. Nur Restore kennt ihn. **(Empfehlung: K8 bleibt unberührt, die Frist kennt das Frontend aus der Antwort auf `DELETE`)**
2. `GET /jobs/{jobID}` antwortet `200` mit `dismissed` und der Frist als `expires`, Downloads `404`.
3. Wie 2, aber Downloads und Kacheln bleiben bis zum Ende der Frist erlaubt.

**Frage 3 — Laufende Jobs?**
1. „Cancel“ bleibt getrennt. „Delete“ ist bei wartenden und laufenden Jobs ausgeblendet, bei einem Batch, solange ein Teil wartet oder läuft. **(Empfehlung)**
2. „Delete“ auf einem laufenden Job bricht ab und löscht in einem Schritt.

**Frage 4 — Ab wann zählt ein gelöschter Job nicht mehr als Cache-Treffer?**
1. Sofort: Hängt kein lebender Job mehr am Lauf, ist er ab dem Löschen kein Treffer. Restore macht ihn wieder zu einem. **(Empfehlung: Was gelöscht ist, kommt nicht über einen fremden Auftrag zurück, und das Objekt kann pünktlich gehen)**
2. Nach der Frist: bis dahin ein Treffer. Ein Treffer in dieser Zeit hält das Objekt für den neuen Job am Leben.

**Frage 5 — Wo steht ein Job, den der Server nicht mehr kennt (`404`), ohne dass er gelöscht wurde?**
1. Im Reiter „Expired“, mit „No longer available“. Unter „Deleted“ steht nur, was jemand gelöscht hat. **(Empfehlung)**
2. Im Reiter „Deleted“, mit „No longer available“.
In beiden Fällen wird der Zustand gespeichert, und der Job wird nie wieder abgefragt.

**Frage 6 — Ergebnis-Layer auf der Karte von einem gelöschten Job?**
1. Sie bleiben und enden am Ende der Frist wie bei abgelaufenen Ergebnissen. Nach Restore gilt wieder der ursprüngliche Ablauf. **(Empfehlung: Ein Restore stellt so auch die Karte wieder her)**
2. Sie verschwinden sofort von der Karte. Nach Restore muss man sie neu hinzufügen.

**Frage 7 — Delete auch für abgelaufene, abgebrochene und nicht mehr verfügbare Einträge?**
1. Ja, nur im Browser, mit einem Tag Restore wie bei den übrigen. **(Empfehlung: Jedes Löschen ist rückgängig zu machen, deshalb braucht es keine Rückfrage)**
2. Ja, endgültig, ohne Restore.
3. Nein, nur fertige und gescheiterte Jobs.

**Frage 8 — Kürzel für Restore?**
1. Keines: „Restore“ im Menü und ↺ in der Zeile. **(Empfehlung)**
2. `D` auf einer gelöschten Zeile stellt sie wieder her (Umschalter wie `A`).

**Frage 9 — Rezept des Gelöschten, wenn der Lauf für andere Jobs weiterlebt?**
1. Der Lauf übernimmt nach der Frist das Rezept eines verbleibenden Jobs, das Rezept des Gelöschten geht mit der Frist. **(Empfehlung: Danach ist nichts vom Gelöschten mehr da, wie bei M4-19e)**
2. Es bleibt, bis der Lauf abläuft (heutige Regel F13, höchstens 7 Tage).

**Frage 10 — PR-Größe?** Geschätzt etwa 350 Zeilen Code, Frontend und Backend zusammen, und etwa 600 Zeilen Tests.
1. Ein PR (dieser), Plan und Code, in thematisch getrennten Commits: Backend, Frontend, Doku. **(Empfehlung: Die Abnahme prüft den ganzen Weg im Browser, wie bei UI-01c)**
2. Zwei PRs: NM4-27a Backend (dieser), NM4-27b Frontend auf dessen Branch.

## 13. Umsetzung nach Freigabe

Commits in dieser Reihenfolge, je ein Thema:

1. Migration 015 und `submit` mit Tests.
2. Aufräumer mit Tests.
3. Routen mit Tests.
4. Nachträge in den ADRs.
5. Frontend-API und Ablage.
6. Store mit dem Fund vom 26.10.2026.
7. Manager, Reiter, Kürzel und Details.
8. Log, Backlog-Punkt 27 als erledigt mit PR-Nummer.

Vor „fertig“: `main` holen, dann `ruff check backend`, `pytest`, `lint-imports --config .importlinter`, `npm run lint`, `npx tsc -b`, `npm test`. Danach die Prüfung im Browser. Die Prüfanleitung für Otto (Browser und PowerShell 5.1: `Invoke-WebRequest -Method Delete`, dann `…/restore`) kommt mit der Umsetzung in den PR.

## 14. Freigabe (Otto, 27.10.2026) und Umsetzung

Alle Empfehlungen aus §12 sind angenommen (jeweils Option 1). Zwei Präzisierungen:

- **Frage 6:** Weil innerhalb der Frist alles `404` liefert (Frage 2), bleibt ein Ergebnis-Layer eines gelöschten Jobs im Layer-Manager stehen, wird aber nicht gezeichnet. Er ist gesperrt, der Grund steht im Tooltip (kurz, etwa „Job deleted – restore to show“). Restore macht ihn wieder sichtbar; nach Ablauf der Frist verschwindet der Eintrag. Kein Text in der Zeile, keine Kachelanfragen für gesperrte Layer.
- **Frage 10:** Ein PR. Wegen der Grenze von zwei Frontend-Sessions zuerst das Backend, das Frontend erst, wenn Otto meldet, dass #211 oder #216 gemergt ist.
- Der Fund vom 26.10.2026 (Phase „gone“ nach `404` nicht gespeichert) wird in diesem PR behoben, mit Test: Neuladen → der Job steht unter „Expired“ mit „No longer available“, keine erneute Abfrage.
- `docs/plans/nach-m4-backlog.md` bleibt unverändert (pflegt der Planungs-Chat).

### 14.1 Backend (umgesetzt)

Wie in §9, mit diesen Abweichungen und Auslegungen:

- **`dismiss` sperrt den Lauf vor dem Job** (zuvor umgekehrt). Der Aufräumer sperrt ebenfalls erst den Lauf; so warten beide nicht aufeinander.
- **Zustand statt Wert:** `JobStatus.expires_at` eines gelöschten Jobs ist das Ende der Frist, `JobStatus.deleted_until` das Feld dazu. Die Antwort auf `DELETE` trägt es als `expires`, die auf `restore` wieder die ursprüngliche Ablaufzeit.
- **Treffer:** Der Lauf wird beim Wählen des Treffers mit `FOR SHARE` gesperrt, bis der neue Job daran hängt. Ohne die Sperre könnte der Aufräumer das Objekt zwischen Wahl und Einfügen löschen.
- **Aufräumer:** Ein Lauf bleibt, solange ein Job lebt oder noch in seiner Frist liegt (er könnte wiederhergestellt werden). Ein verworfener Job hält ihn nicht. `CleanupResult.deleted_jobs` zählt die Jobs, deren Frist zu Ende war.
- **Tests (Gegenprobe):** Mit dem alten `submit.py`, `cleanup.py` und `processing_route.py` schlagen 40 der neuen und angepassten Tests fehl, zwei Dateien lassen sich nicht einmal importieren.

### 14.2 Frontend (offen)

Beginnt, wenn Otto meldet, dass #211 oder #216 gemergt ist. Reihenfolge wie in §13, Punkte 5 bis 7, dazu die Präzisierung zu Frage 6 für den Layer-Manager.
