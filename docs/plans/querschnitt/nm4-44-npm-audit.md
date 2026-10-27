# NM4-44 — Schwachstellen der Frontend-Pakete prüfen (`npm audit`)

**Stand:** 27.10.2026, beauftragt von Otto (Backlog-Punkt 44 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR. Braucht ein Paket einen Sprung auf eine neue Hauptversion, legt die Session das Otto als Frage vor, bevor sie es ändert.
**Modell:** Sonnet, Effort mittel.
**Start:** nach dem Merge von UI-02a (#211), weil #211 `package.json` ändert. Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-44 aus `docs/plans/querschnitt/nm4-44-npm-audit.md` aus.“

## 1. Befund

`npm install` meldete am 27.10.2026 lokal bei Otto „8 vulnerabilities (3 moderate, 4 high, 1 critical)“. Außerdem verlangen `jsdom@30` und Abhängigkeiten Node `^22.22.2 || ^24.15.0 || >=26`; Otto hat lokal 22.19.

## 2. Umfang

1. `npm audit` (auch `--omit=dev`) ausführen; Tabelle im PR: Paket, Schwere, betroffener Weg (direkt oder über welches Paket), nur Entwicklung/Test oder im ausgelieferten Bundle, Fix verfügbar ja/nein, nötige Version.
2. **Einschätzung je Eintrag:** Ist die Lücke in EarthX erreichbar (etwa nur im Dev-Server, nur in Tests, im Browser des Nutzers)? Kurz begründet.
3. **Gezielt aktualisieren:** innerhalb der Hauptversion per Lock-Datei. Kein `npm audit fix --force`. Ein Hauptversionssprung nur nach Ottos Freigabe.
4. **Node-Version:** Welche Node-Version setzen CI und Projekt voraus (`engines`, `.nvmrc`, Doku)? Im PR sagen, was Otto lokal braucht; eine Zeile in der Entwickler-Doku (README o. ä.), falls dort Node genannt ist. `.github/` bleibt unverändert.
5. Was ohne Hauptversionssprung offen bleibt, steht im PR mit Empfehlung.

## 3. Grenzen

- Keine neue Abhängigkeit ohne Frage an Otto.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 4. Abnahme

- `npm audit` vorher/nachher im PR; Lint, `tsc -b`, `vitest` und Build grün; kurzer Lauf im echten Browser (Playwright), dass die App startet und eine Suche läuft.
- Alle vier Pflicht-Checks grün.
- Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.
