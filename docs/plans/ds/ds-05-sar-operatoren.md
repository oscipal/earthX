# DS-05 — SAR-Operatoren und -Presets

**Stand:** 26.10.2026, beauftragt von Otto. Paket „Datensatzabhängige Suche und Prozessierung“ (DS); Übersicht in `docs/plans/ds/ds-00-paket.md`.
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Plan und Recherche, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach DS-04 (also mit oder nach M5) und nach NM4-14 (Index-Knöpfe). Höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe DS-05 aus `docs/plans/ds/ds-05-sar-operatoren.md` aus.“

## 1. Anlass

Sentinel-1 braucht andere Prozessierung als Sentinel-2 (Otto, 26.10.2026). `projektuebersicht.md` §8 nennt datensatzspezifische Presets wie Pauli RGB bei SAR.

## 2. Soll

- Operatoren bzw. Presets für SAR, freigeschaltet nur für SAR-Datensätze über Registry-Flags; anderswo erscheinen sie nicht.
- Kandidaten: Umrechnung linear ↔ dB, Speckle-Filter (etwa Lee, Refined Lee, Gamma-MAP), Verhältnis- und Differenz-Darstellungen (VV/VH), RGB-Komposite als Presets.

## 3. Im Plan klären (mit Optionen und Empfehlung)

- **Recherche mit Quellen (Pflicht):** übliche Verfahren und Parameter (ESA SNAP, Literatur), was als T1-Vorschau geht (Speckle-Filter braucht Nachbarschaft – Kachelränder!) und was nur als Job.
- Was über Band math als Preset geht und was ein eigener Operator sein muss.
- Bitgleichheit Kachel ↔ Job und Runner (`adr/0014` §6.3); Kostenfaktoren messen.
- `decomp.py` bleibt ruhend und wird nicht generalisiert (fest).

## 4. Grenzen

- `decomp.py` nicht anfassen.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip. Nicht anwendbare Möglichkeiten werden ausgeblendet, nicht ausgegraut (Otto, 26.10.2026).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Ausgehende Requests nur über `gateway`; keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Kein datensatzspezifischer Code: Unterschiede je Datensatz stehen als Daten in der Registry.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests je Operator gegen eine unabhängige Rechnung; Kachel ↔ Job bitgleich auf der nativen Ebene; Runner gleich Kern.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), Hell/Dunkel, schmales Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n).
- Vor „fertig“ ist main geholt.
