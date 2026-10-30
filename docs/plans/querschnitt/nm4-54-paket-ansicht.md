# NM4-54 — Paket Ansicht und Anheften (NM4-45, NM4-24, NM4-25, NM4-12)

**Stand:** 29.10.2026, von Otto beauftragt: kleine Aufgaben zusammenlegen, um Sessions und Konflikte zu sparen (`docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR für alle Teile.
**Modell:** Sonnet, Effort hoch (vier Teile in einem Bereich).
**Start:** nach dem Merge von NM4-53 (alle Teile ändern die Ansicht bzw. ihre Leiste). Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-54 aus `docs/plans/querschnitt/nm4-54-paket-ansicht.md` aus.“

## Teile

| Reihenfolge | Teilaufgabe | Plan |
|---|---|---|
| 1 | NM4-12 Anheften ohne zweiten Klick | `querschnitt/nm4-12-anheften-ohne-zweiten-klick.md` |
| 2 | NM4-25 Quicklook nach „Crop & merge“ sofort zuschneiden | `querschnitt/nm4-25-quicklook-nach-zuschnitt.md` |
| 3 | NM4-24 Stapelung im Rückfall „Szene für Szene“ wie das Mosaik | `querschnitt/nm4-24-rueckfall-stapelung.md` |
| 4 | NM4-45 Einzelne Bänder in der Ansicht per Dropdown | `querschnitt/nm4-45-band-in-ansicht.md` |

Die Regeln für die Ansicht aus #211, #221, #234 und NM4-53 (Show/Hide, Anhak-Reihenfolge, feste Plätze der Leisten, „Apply“/„Save“, Zeitschritte) gelten weiter; jede Teilaufgabe prüft, dass sie unverändert bleiben.

## Grenzen

- Was in den einzelnen Plänen steht, gilt unverändert; dieser Plan legt nur fest, dass sie zusammen in einer Session und einem Draft-PR umgesetzt werden.
- Je Teilaufgabe ein eigener Commit (Nachricht nennt die Nummer), damit Otto sie getrennt prüfen kann.
- Oberflächentexte nur Englisch; wenig Text, Erklärungen im Tooltip; nicht Mögliches ausblenden statt ausgrauen.
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Nachträge in ADRs heißen nach der Aufgabe („Nachtrag NM4-xx“).
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## Abnahme

- Die Abnahme jedes Teilplans ist erfüllt (Tests mit Gegenprobe, Browserprüfung in Hell/Dunkel und schmalem Fenster).
- Eine gemeinsame Prüfanleitung für Otto im PR, gegliedert nach Teilaufgabe.
- Alle vier Pflicht-Checks grün.
- Je Teilaufgabe eine Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.
