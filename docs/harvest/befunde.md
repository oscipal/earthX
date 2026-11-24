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

- [ ] **H-2026-11-24-02** · 2026-11-24 · govdata · Fehltreffer als Geodaten: „Gewerbesteuer: Steuerpflichtige …
  Kreise … (ab 2010)“ (Statistik Sachsen) und „Aktuelle Lage … Aachen zum Corona-Virus“. Beide veröffentlicht.
  Vorschlag: Plan M5-67 §12 (02). Stand 24.11. ([#408](https://github.com/oscipal/earthX/pull/408)): „Corona“ steht in
  `strong_not_geo_terms` (F14) und überstimmt die Ausdehnung von Aachen; „Betriebsstätten“ hält nicht mehr (01). Ob
  beide danach verborgen sind, zeigt der Classify-Auszug des ersten Laufs.
- [ ] **H-2026-11-24-05** · 2026-11-24 · govdata · Sächsisches Landesamt für Umwelt, Landwirtschaft und Geologie
  (LfULG): weiter 228 Funde `unknown_licence`; die Kurzform `dl-by-de/2.0` war nicht die Ursache. Braucht die
  wartenden Lizenzangaben aus dem ersten automatischen Lauf (`lizenzangaben.md`). Vorschlag: Plan M5-67 §12 (05).
- [ ] **H-2026-11-24-06** · 2026-11-24 · govdata · Kategorie falsch („Optical imagery“): Gemeindefinanzen
  („Auszahlungen …“, „Einzahlungen …“) und „[BfTMAP] KOPIE MItarbeiter als Dienst“. Braucht die Belege der
  Kategorie aus dem ersten automatischen Lauf (`warnzeichen.md`). Vorschlag: Plan M5-67 §12 (06).

## Offen, aus den Läufen

Diesen Abschnitt schreibt jeder Lauf neu (zwischen den Markierungen); was nicht mehr auftritt, steht danach
abgehakt unter „Erledigt“.

<!-- auto:start -->
- [ ] **LAUF** · seit 2026-11-24 · zuletzt 2026-11-24 · Lauf gescheitert: Bericht: Der Bericht von earth-search ist gescheitert.. Siehe `docs/harvest/laeufe/2026-11-24/fehler.log`.
- [ ] **LIZENZ Weitere Informationen zu den Daten und Veröffentlichungen er** · seit 2026-11-24 · zuletzt 2026-11-24 · 19 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ https://data-lra-cha.opendata.arcgis.com/api/feed/dcat-ap/3.** · seit 2026-11-24 · zuletzt 2026-11-24 · 165 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ https://www.offenedaten-wuppertal.de/page/nutzungsbedingunge** · seit 2026-11-24 · zuletzt 2026-11-24 · 116 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ Es gelten keine Zugriffsbeschränkungen** · seit 2026-11-24 · zuletzt 2026-11-24 · 82 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ http://inspire.ec.europa.eu/metadata-codelist/LimitationsOnP** · seit 2026-11-24 · zuletzt 2026-11-24 · 36 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ mdd-nrw-nutzungsbedingungen** · seit 2026-11-24 · zuletzt 2026-11-24 · 27 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ https://opendata.kreis-borken.de/pages/datenschutz** · seit 2026-11-24 · zuletzt 2026-11-24 · 18 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ Der Zugang zu den Daten ist nach § 3 des Informationsfreihei** · seit 2026-11-24 · zuletzt 2026-11-24 · 16 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ Es erfolgt ein kompletter Haftungsausschluss. Es wird keiner** · seit 2026-11-24 · zuletzt 2026-11-24 · 8 Funde warten auf eine Einstufung von Otto.
- [ ] **QUELLE govdata** · seit 2026-11-24 · zuletzt 2026-11-24 · Harvest gescheitert: Der Harvest endete mit Fehler (protokoll.txt).
<!-- auto:end -->

## Erledigt

- [x] **H-2026-11-24-01** · 2026-11-24 · govdata · Regel R-G: „Betriebsstätte(n)“ ist als Geo-Begriff zu breit; es
  soll nur zusammen mit PRTR halten. Beispiel: die Steuerstatistik von Destatis wurde dadurch gehalten;
  `PRTR_Betriebsstaetten_RLP` muss Geodaten bleiben. Vorschlag: Plan M5-67 §12 (01).
  Erledigt 24.11.2026 ([#408](https://github.com/oscipal/earthX/pull/408)): die vier Begriffe gestrichen, `prtr` hält weiter.
- [x] **H-2026-11-24-04** · 2026-11-24 · opendata-swiss · Identitas AG: „Katzen – Verteilung pro Gemeinde“ und
  „Ziegen – Verteilung pro Kanton“ sind nicht verborgen wie die übrigen Funde dieses Herausgebers (Stapel 6,
  `ok: false`, veröffentlicht). Vorschlag: Plan M5-67 §12 (04).
  Erledigt 24.11.2026 ([#408](https://github.com/oscipal/earthX/pull/408)): Ausdehnung hält keine Funde von Herausgebern ohne
  Geodaten mehr; ein starkes Signal hält weiter, dann greift W2. Der nächste Bericht verbirgt die beiden.
- [x] **H-2026-11-24-03** · 2026-11-24 · opendata-swiss · „Bibliothekenstatistik der Öffentlichen Bibliotheken im
  Kanton Thurgau (2005-2019)“ wird nicht als Nicht-Geodaten erkannt (in der Stichprobe von Stapel 6 mit `ok: false`,
  veröffentlicht). Vorschlag: Plan M5-67 §12 (03). Stand 24.11. ([#408](https://github.com/oscipal/earthX/pull/408)):
  `bibliothekenstatistik` ist Nicht-Geo-Begriff und Warnzeichen W1 hält solche Funde aus dem Stapel; die Ausdehnung
  „Kanton Thurgau“ hält den schon veröffentlichten Fund aber weiter. Offen bis F14 im Plan.
  Erledigt 24.11.2026 ([#408](https://github.com/oscipal/earthX/pull/408), F14 = 1): `bibliothekenstatistik` steht in
  `strong_not_geo_terms` und überstimmt die Ausdehnung; der nächste Bericht verbirgt den Fund.
