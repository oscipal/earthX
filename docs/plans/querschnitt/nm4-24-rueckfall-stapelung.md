# NM4-24 — Stapelung im Rückfall „Szene für Szene“ wie das Mosaik

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 24 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** nach dem Merge von UI-01 (ordnet Leisten und Panels neu). Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-24 aus `docs/plans/querschnitt/nm4-24-rueckfall-stapelung.md` aus.“

## 1. Anlass

Seit NM4-02 nutzen Zuschnitt, Export, Mosaik-Job und Mosaik-Kachel dieselbe Reihenfolge (`mosaic_order`; die Kachel liefert sie als `earthx:order`). Fällt die Ansicht auf Einzelszenen zurück (Überflug über 64 Szenen, abgelehnte Mosaik-Kachel, Zoom unter 8), stapelt das Frontend weiter nach Auswahl. In Überlappungen kann dann eine andere Szene oben liegen als im Zuschnitt.

## 2. Soll

- Auch der Rückfall stapelt nach derselben Reihenfolge wie das Mosaik.
- Die Sortierregel wird nicht im Frontend nachgebaut; die Reihenfolge kommt vom Server (bestehendes `earthx:order` oder eine kleine Route ohne AOI).

## 3. Offene Punkte (bei Unklarheit Frage an Otto)

- Woher die Reihenfolge kommt, wenn es gar kein Mosaik gibt (über 64 Szenen): Vorschlag im PR (etwa Route, die nur Item-IDs nimmt und die Reihenfolge zurückgibt, Item-Liste im Body).
- Bekannte Grenze bleibt: Bei gemischten CRS ordnet der Job nur Szenen, die die AOI berühren (`adr/0014` §15p).

## 4. Grenzen

- Backend nur, falls eine kleine Route nötig ist; dann im PR begründen.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Test: Rückfall und Mosaik zeigen in der Überlappung dieselbe Szene, in beiden Auswahlreihenfolgen.
- Gegenprobe: Mit dem alten Code scheitert der Test.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n) mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat, siehe Kopf des Backlogs).
- Vor „fertig“ ist main geholt.
