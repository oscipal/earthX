# NM4-03 — Absolute URL für den Link `tiles` im Ergebnisdokument

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 3 in `docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort mittel.
**Start:** sofort möglich (Backend).
**Startsatz:** „Führe Aufgabe NM4-03 aus `docs/plans/querschnitt/nm4-03-tiles-url-absolut.md` aus.“

## 1. Anlass

Seit M4-13c-5 trägt das Ergebnisdokument einen Link `tiles` auf den `tiler`. Er ist relativ; ein API-Client ohne den gemeinsamen Proxy des Frontends findet den `tiler` damit nicht. Spätestens mit der öffentlichen API (M6) nötig.

## 2. Soll

- Der Link `tiles` (und jeder andere Link des Ergebnisdokuments auf den `tiler`) ist absolut.
- Die Basis-URL kommt ausschließlich aus der Konfiguration (Umgebungsvariable mit Vorgabe für `docker compose`), nie aus dem `Host`-Header der Anfrage (Header-Injection).

## 3. Umfang

- Stelle(n) finden, an denen das Ergebnisdokument Links baut; eine gemeinsame Funktion.
- Konfiguration in `docker-compose.yml` und `.env.example` (ohne Secrets) ergänzen; README-Abschnitt zur Variablen.
- Frontend: nutzt es den Link? Falls ja, prüfen, dass es mit absoluter URL weiter funktioniert.

## 4. Offene Punkte (bei Unklarheit Frage an Otto)

- Gilt dasselbe für andere relative Links (etwa `recipe.json`, `methods`, Download)? Liste im PR mit Vorschlag.

## 5. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 6. Abnahme

- Test: Link absolut mit konfigurierter Basis; ein gefälschter `Host`-Header ändert ihn nicht.
- Gegenprobe: Mit dem alten Code scheitert der Test.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
