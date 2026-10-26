# DS-01 — Quelle für Sentinel-1 (Entscheidungsvorlage)

**Stand:** 26.10.2026, beauftragt von Otto. Paket „Datensatzabhängige Suche und Prozessierung“ (DS), nach VP3 und vor M5; Übersicht in `docs/plans/ds/ds-00-paket.md`.
**Stufe C:** nur Entscheidungsvorlage als ADR-Entwurf unter `docs/adr/`, kein Produktivcode.
**Modell:** Opus, Effort hoch.
**Start:** sofort möglich (nur Doku, Recherche); kann neben VP3 laufen.
**Startsatz:** „Führe Aufgabe DS-01 aus `docs/plans/ds/ds-01-s1-quelle.md` aus.“

## 1. Anlass

Otto möchte Sentinel-1 anbieten, mit eigener Suche (etwa Orbitrichtung, Polarisation) und eigener Prozessierung. Die naheliegenden Quellen sind nicht ohne Weiteres token-frei: S1 GRD bei AWS ist „Requester Pays“, Planetary Computer verlangt ein SAS-Token, CDSE verlangt für den Download eine Anmeldung. Die Regeln der Plattform verlangen token-freien, anonymen Zugriff (Onboarding-Checkliste, KLAERUNGEN).

## 2. Soll

- ADR-Entwurf (nächste freie Nummer) mit Kandidaten, Messung, Empfehlung; Otto entscheidet.

## 3. Umfang

- Kandidaten mindestens: Earth Search (`sentinel-1-grd`), Planetary Computer (GRD, RTC), CDSE (STAC, S3), ASF, EOPF-Zarr für S1 (Muster?), weitere token-freie Quellen.
- **Je Kandidat mit Quellen und Messung:** Produktart (GRD, RTC, SLC), Format (COG, Zarr, SAFE), anonymer Zugriff wirklich ohne Token (Messung über `gateway`, Onboarding-Punkt „Anonymer Zugriffs-Check“), Abdeckung und Aktualität, Lizenz und Attribution, Prüfsummen/Fassung für den Cache (`adr/0014` §3.1), Kachelbarkeit (COG-Übersichten), Kosten für die Quelle.
- Welche Suchfelder die Quelle anbietet (STAC queryables: `sat:orbit_state`, `sar:polarizations`, `sar:instrument_mode`, relativer Orbit …) – Grundlage für DS-02.
- Was RTC/Geländekorrektur bedeutet: fertig von der Quelle oder selbst (dann eher externe Engine, M7 Paket 7g).

## 4. Grenzen

- Kein Produktivcode.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip. Nicht anwendbare Möglichkeiten werden ausgeblendet, nicht ausgegraut (Otto, 26.10.2026).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Ausgehende Requests nur über `gateway`; keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Kein datensatzspezifischer Code: Unterschiede je Datensatz stehen als Daten in der Registry.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- ADR-Entwurf mit Quellen und Messungen; Fragen an Otto nummeriert mit Empfehlung.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n).
- Vor „fertig“ ist main geholt.
