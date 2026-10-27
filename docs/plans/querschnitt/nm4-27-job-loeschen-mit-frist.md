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
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
