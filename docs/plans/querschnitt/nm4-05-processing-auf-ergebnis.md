# NM4-05 — Processing auf einem Ergebnis (Entscheidungsvorlage)

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 5 in `docs/plans/nach-m4-backlog.md`).
**Stufe C:** nur Entscheidungsvorlage als ADR-Entwurf unter `docs/adr/`, kein Produktivcode. Die Umsetzung bekommt nach Ottos Entscheidung eine eigene Aufgabe.
**Modell:** Opus, Effort hoch.
**Start:** sofort möglich (nur Doku).
**Startsatz:** „Führe Aufgabe NM4-05 aus `docs/plans/querschnitt/nm4-05-processing-auf-ergebnis.md` aus.“

## 1. Anlass

Otto möchte ein Job-Ergebnis als Eingabe eines neuen Rezepts verwenden (etwa NDVI rechnen, dann darauf weiterrechnen, ohne alles in einen Auftrag zu packen). Das ist eine neue Art Eingabe neben Datensatz und Item. Bis zur Entscheidung sperrt UI-01 den Processing-Knopf bei Ergebnis-Layern mit Grund (UI-01 §1 Punkt 11).

## 2. Soll

- Ein ADR-Entwurf (nächste freie Nummer) mit Optionen, Empfehlung und Folgen; Otto entscheidet.

## 3. Umfang

- Optionen mindestens: (1) Ergebnis als Eingabe per Referenz (`jobID`/Ergebnis), (2) das neue Rezept hängt die Schritte an das alte Rezept an und rechnet alles neu (kein neuer Eingabetyp), (3) nicht anbieten, stattdessen Ketten im selben Auftrag (heute schon möglich, höchstens 4 Schritte).
- Je Option: Hash und Cache (`adr/0014` §4.5), Herkunft und Attribution, Ablauf nach 7 Tagen (was, wenn das Ergebnis abläuft?), Runner (offline, nur `recipe.json`), Permalinks (M4-19e), Datenschutz (keine `jobID` in URLs/Logs), B8/B9 und „Eingaben per Referenz“ (S3).
- Was das Panel dafür bräuchte (Skizze, kein Code).

## 4. Grenzen

- Kein Produktivcode.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- ADR-Entwurf im PR, Fragen an Otto nummeriert mit Empfehlung.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
