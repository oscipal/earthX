# NM4-52 — Tooltips liegen immer über allem und bleiben im Fenster

**Stand:** 28.10.2026, Wunsch von Otto (Backlog-Punkt 52 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR, nur Frontend.
**Modell:** Sonnet, Effort mittel.
**Start:** Frontend-Aufgabe, höchstens zwei Frontend-Sessions gleichzeitig. Klein; passt in jede Lücke.
**Startsatz:** „Führe Aufgabe NM4-52 aus `docs/plans/querschnitt/nm4-52-tooltips-ueber-allem.md` aus.“

## 1. Befund (Otto, 28.10.2026)

> Generell beim hovern über dieses rufzeichen ist es ein bisschen lästig weil die nachricht unten ist und nicht über anderen boxes.

Anlass war das Rufzeichen „resampled to common grid“ im Processing-Panel: Der Tooltip erscheint unterhalb und wird von anderen Kästen (Panels, Leisten) verdeckt oder abgeschnitten.

## 2. Soll

- **Jeder Tooltip der App** (gemeinsame Komponente, etwa `components/Tip.tsx`) liegt über allen Panels, Leisten, Menüs und der Karte; er wird von keinem Kasten verdeckt oder abgeschnitten (auch nicht durch `overflow` eines Panels).
- **Platzierung:** bevorzugt über dem Element; reicht der Platz nicht, darunter oder seitlich; immer vollständig im Fenster (Rand 8 px), auch im schmalen Fenster.
- **Bedienung bleibt:** Maus, Tastatur-Fokus und Screenreader wie heute (UI-01c); `Esc` schließt.
- Gilt für alle Stellen, die heute eigene Tooltips bauen: die Session listet sie im PR und stellt sie auf die gemeinsame Komponente um, soweit das ohne Verhaltensänderung geht.

## 3. Grenzen

- Keine neue Abhängigkeit ohne Frage an Otto (React-Portal und eigene Platzierung reichen voraussichtlich).
- Oberflächentexte unverändert.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 4. Abnahme

- Tests: Tooltip wird außerhalb des Panels gerendert (Portal), Platzierung kippt am Fensterrand, Tastatur und `Esc`.
- Prüfung im echten Browser (Playwright): Tooltip am Rufzeichen im Processing-Panel, im Layer-Manager und in der Steuerleiste der Ansicht; liegt über anderen Kästen; Hell/Dunkel, schmales Fenster; Bilder im PR.
- Prüfanleitung für Otto im PR.
- Alle vier Pflicht-Checks grün.
- Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.
