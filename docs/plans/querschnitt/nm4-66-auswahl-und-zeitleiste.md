# NM4-66 — Auswahlleiste und Zeitleiste als ein Block

**Stand:** 31.10.2026, Wunsch von Otto (Backlog-Punkt 66 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort hoch.
**Start:** Frontend-Aufgabe (höchstens zwei Frontend-Sessions gleichzeitig); nicht gleichzeitig mit NM4-53 und NM4-54 (alle ändern die Leisten unten).
**Startsatz:** „Führe Aufgabe NM4-66 aus `docs/plans/querschnitt/nm4-66-auswahl-und-zeitleiste.md` aus.“

## 1. Wunsch (Otto, 31.10.2026, wörtlich)

> diese zwei blöcke sollen verbunden werden zu einem einzigen, die timeline sollte dann genau so breit wie die ober box sein und das erste das letzte das aktuelle datum sowie das nächste und das vorige zeigen (mit kleinen pfeilen zwischen aktuell und davor und danach (bzw eig nur <> zeichen)), der verbundene block soll außerdem ein kleines "x" haben dass ich es schliessen kann. Wenn ich wieder auf eine szene clicke oder eine gruppe öffne solls wieder erscheinen.

Gemeint sind die Auswahlleiste („1 scene selected · Crop to AOI · View whole scene · Download crop · Download full scene · Process“) und die Zeitleiste darunter (Abspielen, Datum, Regler, „1/298“).

## 2. Soll

1. **Ein Block:** Auswahlleiste und Zeitleiste sind ein gemeinsamer, verschiebbarer Block (ein Griff, eine Position; feste Plätze aus #211 gelten für den Block). Die Zeitleiste ist genau so breit wie die Knopfzeile.
2. **Datumszeile der Zeitleiste:** erstes Datum · `<` vorheriges · **aktuelles** · nächstes `>` · letztes Datum. `<` und `>` sind klickbar und springen einen Schritt. Abspielen, Regler und Zähler („1/298“) bleiben.
3. **„x“ zum Schließen:** kleines „x“ oben rechts am Block, Tooltip „Close“. Schließen ändert nichts an Haken, Show/Hide oder Ebenen. Der Block erscheint wieder, wenn Otto eine Szene anhakt/anklickt oder eine Gruppe öffnet.
4. Ist keine Szene angehakt, zeigt der Block nur die Zeitleiste (heutiges Verhalten der Auswahlleiste prüfen und im PR beschreiben).
5. Regeln aus NM4-55 (Abspielen ohne Lücken, offene Gruppe/aktueller Zeitschritt oben) und NM4-59 bleiben.

## 3. Grenzen

- Oberflächentexte nur Englisch; wenig Text, Erklärungen im Tooltip; nicht Mögliches ausblenden.
- Keine neue Abhängigkeit ohne Frage an Otto.
- Nachträge heißen nach der Aufgabe („Nachtrag NM4-66“).
- Bilder nicht ins Repo.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 4. Abnahme

- Tests: ein Block, gleiche Breite, Datumszeile mit `<`/`>`, Schließen und Wiedererscheinen (Szene anklicken, Gruppe öffnen), feste Plätze; Gegenprobe.
- Prüfung im echten Browser (Playwright), Hell/Dunkel, schmales Fenster (Datumszeile bricht sauber um oder kürzt).
- Prüfanleitung für Otto im PR.
- Alle vier Pflicht-Checks grün.
- Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern.
- Vor „fertig“ ist main geholt.
