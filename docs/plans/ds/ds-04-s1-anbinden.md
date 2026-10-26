# DS-04 — Sentinel-1 anbinden

**Stand:** 26.10.2026, beauftragt von Otto. Paket „Datensatzabhängige Suche und Prozessierung“ (DS), nach VP3 und vor M5; Übersicht in `docs/plans/ds/ds-00-paket.md`.
**Stufe A:** direkt umsetzen, ein Draft-PR.
**Modell:** Sonnet, Effort hoch.
**Start:** nach Ottos Entscheidung zu DS-01.
**Startsatz:** „Führe Aufgabe DS-04 aus `docs/plans/ds/ds-04-s1-anbinden.md` aus.“

## 1. Anlass

Nach der Entscheidung zur Quelle (DS-01) wird Sentinel-1 als Datensatz angebunden.

## 2. Soll

- Datensatz nach der Onboarding-Checkliste (`projektuebersicht.md` §5, `ADDING_ESA_DATASETS.md`), mit Lizenz und Attribution (B11, Otto prüft), Standarddarstellung (etwa VV in dB), Suche, Kacheln, Zuschnitt, Coverage.
- Suchfilter des Datensatzes über DS-02 (etwa Orbitrichtung, Polarisation, Aufnahmemodus).

## 3. Offene Punkte (bei Unklarheit Frage an Otto)

- Was die Entscheidung zu DS-01 offenlässt (Produktart, Darstellung), im PR mit Vorschlag.

## 4. Grenzen

- Keine Änderung an `readers` für einen Sonderfall; was fehlt, als allgemeine Fähigkeit.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip. Nicht anwendbare Möglichkeiten werden ausgeblendet, nicht ausgegraut (Otto, 26.10.2026).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Ausgehende Requests nur über `gateway`; keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Kein datensatzspezifischer Code: Unterschiede je Datensatz stehen als Daten in der Registry.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Onboarding-Checkliste vollständig (Test je Punkt); Live-Smoke für den Datensatz.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), Hell/Dunkel, schmales Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n).
- Vor „fertig“ ist main geholt.
