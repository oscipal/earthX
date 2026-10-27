# NM4-21 — Einheitliches Zahlenformat in der ganzen Web-App

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 21 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-21 aus `docs/plans/querschnitt/nm4-21-zahlenformat.md` aus.“

## 1. Anlass

Zahlen erscheinen heute mit vielen Nachkommastellen (etwa Min/Max der Vorschau).

## 2. Soll

- Angezeigte Zahlen haben höchstens drei Nachkommastellen. Sehr kleine und sehr große Beträge erscheinen wissenschaftlich, etwa 0.000000052 → `5.2e-8`.
- Eine gemeinsame Formatierfunktion im Frontend für alle Anzeigen (Min/Max, Statistik, Pixelwerte, Schätzung, Auflösung …), keine verstreuten `toFixed`.
- Nur die Anzeige ändert sich; Werte in `recipe.json`, API und Rezepten bleiben unberührt.

## 3. Offene Punkte (bei Unklarheit Frage an Otto)

- Schwellen (Vorschlag: Betrag < 0.001 außer 0, und ≥ 1e6) und gültige Stellen in wissenschaftlicher Form (Vorschlag: bis drei, ohne nachgestellte Nullen).
- Eingabefelder: Vorgaben aus der Statistik gerundet übernehmen; was der Nutzer tippt, gilt genau so.
- Ausnahmen: Koordinaten, IDs, Daten, Zählungen, Dateigrößen.

## 4. Grenzen

- Nur Frontend.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests für Grenzfälle: 0, negativ, 0.001, 0.0009, 1e6, NaN, Unendlich; Suche im Code, dass keine Anzeige an der Funktion vorbeigeht.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n) mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat, siehe Kopf des Backlogs).
- Vor „fertig“ ist main geholt.
