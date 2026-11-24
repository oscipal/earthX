# Harvest-Befunde

Offene und erledigte Befunde der Harvest-Läufe (`docs/plans/m5/m5-67-harvest-automatisch.md` §9). Der Lauf
`scripts/harvest-cycle.ps1` schreibt den Abschnitt „Offen, aus den Läufen“ bei jedem Lauf neu und hakt dort ab, was
nicht mehr auftritt. Die Abschnitte „Offen, von Hand“ und „Erledigt“ pflegen Otto und die Sessions.

**Für eine Session mit dem Auftrag „Arbeite die offenen Harvest-Befunde ab“:**

1. Diese Datei, den neuesten Ordner unter `docs/harvest/laeufe/` und die Freigabedateien in
   `backend/catalog/approvals/` lesen; Grundlagen `adr/0033` §8.5 und der Plan M5-67.
2. Je Befund die Ursache am Code und an den Laufdateien belegen. Regeldaten (`backend/catalog/geodata.yaml`,
   `flags.yaml`, `place_names.yaml`) und Code per Draft-PR ändern, mit Tests.
3. Nie eine Lizenz einstufen (`terms.yaml`), nie `blocked.yaml` oder `revoked_on` selbst setzen: als Vorschlag mit
   nummerierten Optionen an Otto.
4. Behobene Befunde von Hand nach „Erledigt“ verschieben und abhaken, mit Datum und PR.

Keine Personen, keine AOI, keine Hashes oder signierten Adressen in dieser Datei: das Repo ist öffentlich.

## Offen, von Hand

- [ ] **H-2026-11-24-01** · 2026-11-24 · govdata · Regel R-G: „Betriebsstätte(n)“ ist als Geo-Begriff zu breit; es
  soll nur zusammen mit PRTR halten. Beispiel: die Steuerstatistik von Destatis wurde dadurch gehalten;
  `PRTR_Betriebsstaetten_RLP` muss Geodaten bleiben. Vorschlag: Plan M5-67 §12 (01).
- [ ] **H-2026-11-24-02** · 2026-11-24 · govdata · Fehltreffer als Geodaten: „Gewerbesteuer: Steuerpflichtige …
  Kreise … (ab 2010)“ (Statistik Sachsen) und „Aktuelle Lage … Aachen zum Corona-Virus“. Beide veröffentlicht.
  Vorschlag: Plan M5-67 §12 (02).
- [ ] **H-2026-11-24-03** · 2026-11-24 · opendata-swiss · „Bibliothekenstatistik der Öffentlichen Bibliotheken im
  Kanton Thurgau (2005-2019)“ wird nicht als Nicht-Geodaten erkannt (in der Stichprobe von Stapel 6 mit `ok: false`,
  veröffentlicht). Vorschlag: Plan M5-67 §12 (03).
- [ ] **H-2026-11-24-04** · 2026-11-24 · opendata-swiss · Identitas AG: „Katzen – Verteilung pro Gemeinde“ und
  „Ziegen – Verteilung pro Kanton“ sind nicht verborgen wie die übrigen Funde dieses Herausgebers (Stapel 6,
  `ok: false`, veröffentlicht). Vorschlag: Plan M5-67 §12 (04).
- [ ] **H-2026-11-24-05** · 2026-11-24 · govdata · Sächsisches Landesamt für Umwelt, Landwirtschaft und Geologie
  (LfULG): weiter 228 Funde `unknown_licence`; die Kurzform `dl-by-de/2.0` war nicht die Ursache. Braucht die
  wartenden Lizenzangaben aus dem ersten automatischen Lauf (`lizenzangaben.md`). Vorschlag: Plan M5-67 §12 (05).
- [ ] **H-2026-11-24-06** · 2026-11-24 · govdata · Kategorie falsch („Optical imagery“): Gemeindefinanzen
  („Auszahlungen …“, „Einzahlungen …“) und „[BfTMAP] KOPIE MItarbeiter als Dienst“. Braucht die Belege der
  Kategorie aus dem ersten automatischen Lauf (`warnzeichen.md`). Vorschlag: Plan M5-67 §12 (06).

## Offen, aus den Läufen

Noch kein automatischer Lauf.

## Erledigt

Noch nichts.
