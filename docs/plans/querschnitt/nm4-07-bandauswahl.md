# NM4-07 — Bandauswahl im Panel

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 7 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig. Nicht gleichzeitig mit NM4-10, NM4-14 oder NM4-20 (alle ändern den Bandbereich des Panels).
**Startsatz:** „Führe Aufgabe NM4-07 aus `docs/plans/querschnitt/nm4-07-bandauswahl.md` aus.“

## 1. Anlass

Heute muss man jedes Band einzeln anklicken, auch wenn es nur eines gibt (DEM `data`, Ergebnisse).

## 2. Soll

- **Ein Band:** Hat das Item bzw. Asset nur ein Band, ist es beim Öffnen des Panels automatisch gewählt.
- **Alle Bänder:** „Select all bands“ und „Clear“ wählen alle bzw. keine Bänder.
- **Grenze:** Je Auftrag höchstens 16 Assets bzw. Bänder (M4-07b F5). Hat ein Datensatz mehr, wählt „Select all“ keine stille Teilmenge, sondern sagt es mit Grund.
- Bänder aus dem Ausdruck kommen weiter automatisch dazu (M4-13c).

## 3. Offene Punkte (bei Unklarheit Frage an Otto)

- Welche Assets zählen als Bänder? Hilfs-Assets wie `visual`, `thumbnail`, `preview` oder die Maskenschicht (`scl`, M4-18c) eher nicht. Die Regel soll aus der Registry kommen, nicht aus Namenslisten im Frontend. Bei Unklarheit Frage an Otto.

## 4. Grenzen

- Nur Frontend, außer die Regel für „was zählt als Band“ braucht ein Feld in der Registry; dann im PR begründen.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: ein Band automatisch gewählt; „Select all“/„Clear“; Datensatz mit mehr als 16 Bändern; Hilfs-Assets werden nicht gewählt.
- Gegenprobe: Mit dem alten Code scheitern die neuen Tests.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
