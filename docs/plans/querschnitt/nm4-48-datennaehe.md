# NM4-48 — Datennähe: Hauptquelle und Rechenort (ADR)

**Stand:** 30.10.2026, Wunsch von Otto vom 28.10.2026 (Backlog-Punkt 48 in `docs/plans/nach-m4-backlog.md`).
**Stufe C:** nur Entscheidungsvorlage als ADR-Entwurf `docs/adr/0022-datennaehe.md` (Nummer beim Start prüfen, nächste freie nehmen), kein Produktivcode.
**Modell:** Opus, Effort hoch.
**Start:** sofort möglich (nur Doku, Recherche, Messplan). Vor der Auswahl der Quellen in M5 und vor der Wahl des Cloud-Anbieters in M6.
**Startsatz:** „Führe Aufgabe NM4-48 aus `docs/plans/querschnitt/nm4-48-datennaehe.md` aus.“

## 1. Frage (Otto, 28.10.2026)

> Wäre es nicht smart eine datenquelle zu nehmen wo ich möglichst viele daten von der gleichen quelle haben kann und wo ich auch einen server laufen lassen kann? also für processing speed und rendering speed?

Anlass: Die erste Mosaik-Kachel brauchte lokal kalt 6,0 s (28.10.2026), fast alles Weg über das Netz. Sentinel-2 von Earth Search liegt in AWS `us-west-2` (Oregon); die Plattform soll in EU/CH laufen (`projektuebersicht.md` §4).

## 2. Kandidaten (mindestens)

- **A** Earth Search (AWS Open Data) mit Rechnern in AWS `us-west-2`.
- **B** Copernicus Data Space Ecosystem (CDSE) mit Rechnern bei CloudFerro bzw. Open Telekom Cloud (EU; S3-Zugang mit kostenlosem Konto).
- **C** Microsoft Planetary Computer mit Azure West Europe (Token anonym, `adr/0018`).
- Weitere, falls die Recherche sie nahelegt (z. B. Daten in EU-Regionen von AWS).

## 3. Im ADR klären (Optionen, Empfehlung, Quellen)

1. **Abdeckung:** Welche Datensätze liegen wo (Sentinel-1 GRD/RTC, Sentinel-2 L1C/L2A, Sentinel-3, Sentinel-5P, Landsat, Copernicus DEM, Dienste wie CLMS), in welchem Format (COG, Zarr, SAFE/JP2), mit welchen Metadaten (STAC, Felder für Filter aus DS-02).
2. **Zugang und Bedingungen:** anonym oder Konto/Token, Kosten für Abruf (egress, requester pays), Ratenlimits, Nutzungsbedingungen, Lizenz und Attribution.
3. **Rechenort:** Anbieter in derselben Region, Preise (auf Anfrage vs. öffentlich), EU/CH-Hosting, DSGVO/revDSG, Verfügbarkeit von Containern/Kubernetes.
4. **Messplan:** Latenz und Durchsatz je Region (Kachel kalt/warm, Zuschnitt, Job) mit den vorhandenen Skripten (`scripts/tile-bench/`), von Ottos Rechner und von Test-VMs in den Regionen; Messung aus Cloud-Sessions ist nicht möglich (`adr/0002`). Der ADR legt den Messplan fest; die Messung macht Otto bzw. eine spätere Session.
5. **Föderation bleibt:** Was wird „Hauptquelle“, was bleibt angebunden; Auswirkung auf Adapter, Registry, Health-Checks, Ausfall einer Quelle, Bindung an einen Anbieter.
6. **Folgen für M5/M6:** Auswahl der Quellen in M5, Wahl des Cloud-Anbieters in M6, Zusammenhang mit Punkt 46 (eigene Daten, Projekte) und dem Runner.

## 4. Grenzen

- Recherche mit Primärquellen (Anbieterdoku, Preisseiten, Lizenzen); was nur aus Suchtreffern belegt ist, kennzeichnen.
- Ausgehende Anfragen aus Skripten nur über `gateway`; Netzschritte als dokumentierter Einmal-Schritt.
- Keine Secrets, keine Kontodaten im Repo.
- Bilder nicht ins Repo.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- ADR-Entwurf mit Vergleichstabelle, Optionen, Empfehlung, Fragen F1 … Fn an Otto, Quellenliste.
- Messplan mit konkreten Aufrufen (PowerShell 5.1 für Otto).
- Log-Zeile mit PR-Nummer, Status „offen“. `docs/plans/nach-m4-backlog.md` nicht ändern.
- Vor „fertig“ ist main geholt.
