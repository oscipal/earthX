# NM4-55 — Paket Suchergebnisse und Zeitleiste (NM4-09, NM4-18)

**Stand:** 29.10.2026, von Otto beauftragt: kleine Aufgaben zusammenlegen, um Sessions und Konflikte zu sparen (`docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR für alle Teile.
**Modell:** Sonnet, Effort hoch (NM4-18).
**Start:** sofort möglich; nicht gleichzeitig mit DS-03b (ändert ebenfalls die Ergebnisliste). Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-55 aus `docs/plans/querschnitt/nm4-55-paket-suchergebnisse.md` aus.“

## Teile

| Reihenfolge | Teilaufgabe | Plan |
|---|---|---|
| 1 | NM4-09 Feste Gruppenköpfe in den Suchergebnissen | `querschnitt/nm4-09-feste-gruppenkoepfe.md` |
| 2 | NM4-18 Abspielen in der Timeline ohne Lücken | `querschnitt/nm4-18-timeline-ohne-luecken.md` |

Die Ergebnisliste ist seit UI-01g links angedockt (#209); Haken bleiben über Gruppen- und Datensatzwechsel (#234). Beides gilt weiter.

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
