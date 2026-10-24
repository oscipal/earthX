# Pläne

Ein Unterordner je Meilenstein; Dateinamen tragen weiter das Präfix der Aufgabe.

| Ordner | Inhalt |
|---|---|
| `m1/` … `m4/` | Pläne des jeweiligen Meilensteins, auch Zusätze, Unteraufgaben und Abnahmeberichte (`m0/` entsteht mit dem ersten Plan) |
| `vp3/` | Pläne der Oberfläche (UI-01, UI-02) |
| `querschnitt/` | Pläne ohne Meilenstein, etwa DOC-01 |
| `nach-m4-backlog.md` | die lebende Liste der Aufgaben nach M4 |

Bei Widerspruch gilt die Rangfolge aus `CLAUDE.md`: `docs/ENTSCHEIDUNGEN_2026-09-18.md` vor `docs/KLAERUNGEN.md` vor den Plandokumenten. Ein Plan hält fest, wie eine Aufgabe umgesetzt wird; Beschlossenes steht im `docs/ENTSCHEIDUNGSLOG.md`.

Ein neuer Plan liegt im Ordner seines Meilensteins, verlinkt als `docs/plans/<ordner>/<datei>.md`. `backend/tests/test_plans_layout.py` schlägt fehl, wenn eine Datei flach in `docs/plans/` liegt oder ein Verweis den alten Pfad nennt.
