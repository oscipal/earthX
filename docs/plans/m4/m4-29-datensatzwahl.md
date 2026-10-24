# M4-29 — Datensatzwahl und Trefferauswahl: keine Vorauswahl, einzeln per Klick, mehrere nur auf Wunsch, „Select all“

**Stand:** 19.10.2026, beauftragt von Otto.
**Stufe A.** Direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** Nach dem Merge von M4-13c-2 (#153). Kann neben M4-28 laufen, weil die Datensatzwahl und der Layer-Manager verschiedene Stellen im Frontend sind. Wer als Zweiter fertig wird, holt main.
**Startsatz:** „Führe Aufgabe M4-29 aus `docs/plans/m4-29-datensatzwahl.md` aus.“

## 1. Wunsch von Otto (19.10.2026)

1. **Keine Vorauswahl.** Beim Start ist kein Datensatz gewählt.
2. **Einzeln per Klick.** Ein Klick auf einen Datensatz wählt genau diesen. Ein vorher gewählter wird abgewählt.
3. **Mehrere nur mit Schalter.** Erst mit einem eigenen Knopf „Select multiple datasets“ lassen sich mehrere wählen. Dann schaltet jeder Klick den jeweiligen Datensatz ein oder aus.

4. **Alle Treffer wählen (Otto, 19.10.2026).** In der Trefferliste gibt es „Select all“ je Gruppe (Überflug bzw. Gruppe nach `results_group_by`) und einmal für alle Treffer. Dazu kommt „Clear selection“.

## 2. Umfang

- **Ohne Datensatz:** Die Suche ist gesperrt, mit Hinweis (Englisch), etwa „Choose a dataset to search“.
- **Mehrfachwahl beenden:**
  - Es bleibt der zuletzt angeklickte Datensatz gewählt, alle anderen werden abgewählt.
  - Ist keiner gewählt, bleibt keiner gewählt.
  - Der Plan im PR nennt das Verhalten. Bei Unsicherheit ist es eine Frage an Otto.
- **Ein Link mit Datensatz-Parameter** (falls es so etwas gibt) wählt weiterhin genau, was im Link steht. Das gilt nicht als automatische Vorauswahl. Wird beim Neuladen heute die letzte Wahl wiederhergestellt, entfällt das. Am Code prüfen und im PR nennen.
- **Die föderierte Suche über mehrere Datensätze** (`adr/0005`) bleibt unverändert. Sie ist nur noch über die Mehrfachwahl erreichbar.
- **„Select all“ und „Clear selection“:**
  - „Select all“ wählt alle **geladenen** Treffer.
  - Meldet die Quelle mehr Treffer, als geladen sind, sagt der Knopf das, etwa „Select all 100 loaded (of 135)“. Er lädt nicht stillschweigend weitere Seiten nach.
  - „Select all“ einer Gruppe wählt genau die Treffer dieser Gruppe, ein zweiter Klick wählt sie wieder ab.
  - Die Grenzen danach bleiben unverändert und melden sich wie heute mit Grund: 25 Szenen beim Merge, 25 Items je Auftrag, die Höchstzahl je Batch.
- **Bestehende Abläufe,** die einen Datensatz voraussetzen, dürfen ohne Wahl nicht abstürzen, sondern zeigen den Hinweis. Dazu gehören Coverage Map, Zeitleiste, Panel und Download.

## 3. Tests und Abnahme

Tests:
- Start ohne Wahl.
- Ein Klick wählt einen Datensatz, ein zweiter Klick ersetzt ihn.
- Mit Mehrfachwahl: Klicks schalten den jeweiligen Datensatz ein und aus.
- Mehrfachwahl beenden: Danach ist nur noch einer gewählt.
- Die Suche ist ohne Wahl gesperrt.
- Ein Link mit Datensatz wählt genau diesen.
- „Select all“ insgesamt und je Gruppe; ein zweiter Klick auf „Select all“ einer Gruppe wählt sie ab; „Clear selection“ leert die Auswahl.
- Der Hinweis „loaded (of N)“ erscheint, wenn mehr Treffer existieren als geladen sind.
- Gegenprobe: Mit dem alten Verhalten scheitern die neuen Tests.

Abnahme:
- Prüfanleitung für Otto (Browser) im PR.
- Log-Zeile.
- Zeile M4-29 in `docs/plans/m4-processing-kern.md` §3.
- Alle vier Pflicht-Checks der CI sind grün.
- Vor „fertig“ ist main geholt.

## 4. Grenzen

- Nur Frontend.
- Kein Umbau von Ort oder Aussehen des Control-Menüs; das macht UI-01.
- Oberflächentexte nur auf Englisch.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.
