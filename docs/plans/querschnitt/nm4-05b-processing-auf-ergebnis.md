# NM4-05b — Processing auf einem Ergebnis (Umsetzung)

**Stand:** 26.10.2026, beauftragt von Otto (Backlog-Punkt 5; Entscheidung in `docs/adr/0019-processing-auf-ergebnis.md`, §9 F1–F5 je Option 1).
**Stufe A:** direkt umsetzen nach `adr/0019`, ein Draft-PR.
**Modell:** Sonnet, Effort hoch.
**Start:** nach dem Merge von #204 (`adr/0019` angenommen). Nicht gleichzeitig mit NM4-27 oder NM4-34 (alle ändern Processing-Manager, Panel bzw. Ablage). Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-05b aus `docs/plans/querschnitt/nm4-05b-processing-auf-ergebnis.md` aus.“

## 1. Grundlage

`adr/0019` (angenommen): Option 2 – ⚙ am Ergebnis-Layer öffnet das Processing-Panel mit dem Auftrag dieses Jobs (Kopie in der Ablage, bis 64 KB, UI-01b). Die bisherigen Schritte stehen gesperrt vorn, neue Schritte kommen dahinter, alles wird als **ein** normaler Auftrag neu gerechnet. API, Rezept, Hash, Cache, Runner, Permalinks und Ablauf bleiben unverändert; nur Frontend.

## 2. Soll

- ⚙ erscheint wieder am Ergebnis-Layer (UI-01d hatte es ausgeblendet, weil es nicht ging), wenn die Auftragskopie vorhanden ist – **auch bei abgelaufenen Ergebnissen** (F4). Ohne Kopie erscheint ⚙ nicht (F2, Regel 26.10.2026).
- Das Panel zeigt die bisherigen Schritte gesperrt (nicht änderbar, nicht entfernbar) vorn (F3); neue Schritte lassen sich dahinter anhängen, mit Vorschau wie gewohnt (Kachel-Kette höchstens 4 Schritte; ein Job nimmt bis `MAX_ORDER_STEPS`).
- Start als neuer Job; Titel aus dem alten Titel plus neuem Schritt (Vorschlag im PR), gleiche Gruppe.
- Tooltip am gesperrten Anfang (wenig Text): Die Kette wird neu gerechnet; Werte können im letzten Bit von einer Rechnung auf der gespeicherten Datei abweichen (float64 in der Kette gegen float32 in der Datei, `adr/0019` Befund).

## 3. Grenzen

- Nur Frontend. Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip.
- Keine neue Abhängigkeit. Keine Kennungen in URLs oder Logs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 4. Abnahme

- Tests: ⚙ mit und ohne Auftragskopie, auch abgelaufen; gesperrte Schritte nicht änderbar; angehängter Schritt ergibt einen Auftrag mit allen Schritten in Reihenfolge; Vorschau der Kette; Start legt einen neuen Job an.
- Gegenprobe: Mit dem alten Code scheitern die neuen Tests.
- Prüfung im echten Browser (Playwright), Hell/Dunkel, schmales Fenster; Prüfanleitung für Otto im PR.
- Alle vier Pflicht-Checks grün; Log-Zeile mit PR-Nummer (Backlog pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.
