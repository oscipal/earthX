# NM4-56 — Paket Oberfläche: Zahlenformat, weniger Text, Ausblenden statt Ausgrauen (NM4-21, NM4-22, NM4-30)

**Stand:** 29.10.2026, von Otto beauftragt: kleine Aufgaben zusammenlegen, um Sessions und Konflikte zu sparen (`docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR für alle Teile.
**Modell:** Sonnet, Effort hoch (quer durch die App).
**Start:** als letzte Frontend-Aufgabe vor M5, wenn keine andere Frontend-Session läuft (die Teile gehen quer durch die ganze Oberfläche und kollidieren sonst mit allem).
**Startsatz:** „Führe Aufgabe NM4-56 aus `docs/plans/querschnitt/nm4-56-paket-oberflaeche.md` aus.“

## Teile

| Reihenfolge | Teilaufgabe | Plan |
|---|---|---|
| 1 | NM4-30 Nicht Mögliches ausblenden statt ausgrauen | `querschnitt/nm4-30-nicht-moegliches-ausblenden.md` |
| 2 | NM4-21 Einheitliches Zahlenformat in der ganzen Web-App | `querschnitt/nm4-21-zahlenformat.md` |
| 3 | NM4-22 Weniger Text in der Oberfläche | `querschnitt/nm4-22-weniger-text.md` |

Zusätzlich (Backlog-Punkt 58): Bei 320 px Breite ragen die Toolbar-Knöpfe des Control-Menüs etwa 8 px über den Rand (Fund aus DS-02c, #239); beheben, mit Browserprüfung bei 320 px.

Zuerst eine Bestandsaufnahme über alle Panels (Tabelle im PR: Stelle, heute, künftig), dann die drei Durchgänge. Der Hinweis „resampled to common grid“ (Backlog-Punkt 51) ist Sache von NM4-43e, nicht dieses Pakets.

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
