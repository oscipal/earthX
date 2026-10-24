# M4-27 — Live-Smoke reparieren und Signatur-Drift im PR abfangen

**Stand:** 12.10.2026, beauftragt von Otto.
**Stufe A.** Direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** Nach M4-21. Läuft neben anderen Sessions.
**Startsatz:** „Führe Aufgabe M4-27 aus `docs/plans/m4/m4-27-live-smoke-reparieren.md` aus.“

## 1. Befund

Der tägliche Live-Smoke (T-D, `adr/0002`, `.github/workflows/live-smoke.yml`) ist seit etwa 5 Tagen rot, für Earth Search und für EOPF. Das DEM ist grün.

```
backend/tests_live/test_earth_search_smoke.py:51
backend/tests_live/test_eopf_smoke.py:60
TypeError: search_items() missing 1 required keyword-only argument: 'adapters'
```

- **Ursache:** ein eigener Fehler, keine Änderung an der Quelle. M4-01b (#122) hat den Dispatchern `adapters=` ohne Vorgabe gegeben und die Signaturen auf `DatasetConfig` umgestellt. `backend/tests_live/` wurde dabei nicht nachgezogen.
- **Warum es nicht früher auffiel:** Die Tests in `tests_live` laufen nie im PR. So ist es gewollt, ein PR soll nicht rot werden, weil ein fremder Dienst hustet. Dadurch fällt aber auch ein Fehler im eigenen Testcode erst im täglichen Lauf auf.
- **Folge:** Seit 5 Tagen hat niemand geprüft, ob die Quellen noch so antworten wie aufgezeichnet.

## 2. Umfang

1. **Reparieren.** Alle Tests in `backend/tests_live/` auf die heutigen Signaturen bringen: `search_items` und `get_item` mit `DatasetConfig` und `adapters=ADAPTER_SPECS`, nach demselben Muster wie `api`. Auch die Dateien durchsehen, die heute grün sind, etwa Coverage und DEM.
2. **Drift im PR abfangen, ohne Netz.** Im normalen Backend-`pytest` (T-B, `backend/tests/`) kommt ein Trockenlauf dazu. Er führt jeden Live-Smoke-Test mit einem HTTP-Transport-Double aus. Das Double spielt die vorhandenen aufgezeichneten Fixtures ab, statt ins Netz zu gehen.
   - Ändert jemand eine Signatur, wird der PR rot.
   - Ändert sich die Quelle, bleibt der PR grün. Dafür ist weiter der tägliche Lauf da.
   - Wenn sich ein Test so nicht abspielen lässt, wird das im PR begründet. Mindestens muss dann ein Test belegen, dass alle Aufrufe in `tests_live` zu den aktuellen Signaturen passen.
3. **`.github/` bleibt unverändert.** Der Trockenlauf läuft im bestehenden Backend-Job mit, ohne neuen Workflow. Ist das nicht möglich: Frage an Otto, denn `.github/` darf nur mit seiner ausdrücklichen Erlaubnis geändert werden.

## 3. Tests und Abnahme

- **Gegenprobe:** Mit dem alten Aufruf ohne `adapters=` scheitert der Trockenlauf im normalen `pytest`.
- `pytest`, `ruff check backend` und `lint-imports` sind grün. Alle vier Pflicht-Checks der CI sind grün.
- **Nach dem Merge prüft Otto:** Actions → „Live smoke“ → „Run workflow“ startet den Lauf von Hand. Alle drei Jobs sind grün. Ist ein Job danach immer noch rot, ist das ein echter Befund an der Quelle und kommt als neuer Fund in den Chat.
- **Log:** eine Zeile mit Befund und Umsetzung.
- `docs/plans/m4/m4-processing-kern.md` §3: Zeile M4-27 ergänzen.
- Vor „fertig“ ist main geholt.

## 4. Offener Punkt, nicht in dieser Aufgabe

`projektplan.md` §6 sieht eine Routine vor: „Triage bei fehlgeschlagenem Smoke-Test“ (Sonnet, ausgelöst durch ein GitHub-Ereignis). Sie ist nicht eingerichtet. Darüber entscheidet Otto gesondert, weil sie ohne Secrets auskommen muss.
