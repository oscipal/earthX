# DS-03 — Wolkenanteil in der AOI

**Stand:** 26.10.2026, beauftragt von Otto. Paket „Datensatzabhängige Suche und Prozessierung“ (DS), nach VP3 und vor M5; Übersicht in `docs/plans/ds/ds-00-paket.md`.
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Messung, Recherche und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach DS-02. Höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe DS-03 aus `docs/plans/ds/ds-03-wolken-in-aoi.md` aus.“

## 1. Anlass

Die Wolkenangabe der Quelle (`eo:cloud_cover`) gilt für die ganze Szene (rund 110 × 110 km). Otto möchte nach dem Wolkenanteil **in seiner AOI** filtern und sortieren.

## 2. Soll

- Für die Treffer einer Suche (nach der groben Vorauswahl über die Szene) berechnet die Plattform den Anteil bewölkter Pixel in der AOI aus der Klassifizierung (`SCL`, Klassen wie bei `mask`), auf einer groben Übersichtsstufe.
- Ergebnis je Szene, etwa „Clouds in AOI: 3 %“; Filter und Sortierung danach in „Advanced search“ bzw. der Trefferliste.
- Nur für Datensätze mit Klassifizierungsschicht (Registry, wie `earthx:mask`); sonst erscheint die Möglichkeit nicht.

## 3. Im Plan klären (mit Optionen und Empfehlung)

- **Messung und Recherche (Pflicht, rechenrelevant):** Zeit und Bytes je Szene bei verschiedenen Übersichtsstufen; Genauigkeit gegen volle Auflösung; Stand der Technik (etwa übliche AOI-Wolkenstatistik aus SCL bzw. Cloud-Masken) mit Quellen.
- Schnittstelle: AOI nur im Body (POST), nie in URL oder Log; Cache je Szene und AOI-Hash (Hash nicht geloggt); Obergrenze der Szenen je Anfrage; schrittweise Anzeige.
- Welche Klassen zählen als Wolke (Vorschlag wie die Vorgabe von `mask`: 3, 8, 9, 10) und wie mit „no data“ in der AOI umgegangen wird.
- Grenzen der Klassifizierung (Zirren, Schnee) im Tooltip benennen.

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip. Nicht anwendbare Möglichkeiten werden ausgeblendet, nicht ausgegraut (Otto, 26.10.2026).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Ausgehende Requests nur über `gateway`; keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Kein datensatzspezifischer Code: Unterschiede je Datensatz stehen als Daten in der Registry.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Anteil gegen eine unabhängige Rechnung auf synthetischen Rastern; AOI nie im Log/URL; Obergrenze; Datensatz ohne Klassifizierung zeigt die Möglichkeit nicht.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), Hell/Dunkel, schmales Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n).
- Vor „fertig“ ist main geholt.
