# NM4-18 — Abspielen in der Timeline ohne Lücken

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 18 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort hoch.
**Start:** Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-18 aus `docs/plans/querschnitt/nm4-18-timeline-ohne-luecken.md` aus.“

## 1. Anlass

Bei „Play“ in der Timeline wechselt die Karte, bevor der nächste Zeitschritt geladen ist; dazwischen ist die Basemap zu sehen, und es steht der Szenenname.

## 2. Soll

- Die Karte wechselt erst zum nächsten Zeitschritt, wenn dessen Kacheln für den sichtbaren Ausschnitt geladen sind; bis dahin bleibt das aktuelle Bild stehen. Nie Basemap dazwischen.
- Während des Abspielens steht nur das Datum der Gruppe (des Überflugs), kein Szenenname.

## 3. Offene Punkte (bei Unklarheit Frage an Otto)

- Vorladen des nächsten Schritts (unsichtbarer Layer oder Kachel-Cache der Kartenbibliothek); Speicher- und Anfragegrenzen; Last auf den `tiler` (Mosaik-Kacheln, M4-17).
- Mindestdauer je Bild; Verhalten bei langsamem Laden („Loading…“ dezent).
- Schritt lädt nicht: Zeitlimit, dann überspringen mit Hinweis.
- Zoomen oder Verschieben während des Abspielens.

## 4. Grenzen

- Nur Frontend; keine neue Route im `tiler`.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Test mit verzögerten Kacheln: Wechsel erst nach dem Laden; Beschriftung nur Datum.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
