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
- [ ] **H-2026-11-25-01** · 2026-11-25 · govdata · Links auf `datenregister.berlin.de/dataset/<id>` (402) führen auf das
  nicht-öffentliche Redaktionssystem des Berliner Portals (`403`), ihre Einträge bleiben ungeprüft und unsichtbar
  (M5-67 F17 = 1). Auf die öffentliche Seite `https://daten.berlin.de/datensaetze/<name>` umstellen; ob `<name>` dem
  CKAN-Namen entspricht, ist nicht belegt und braucht einen Browsertest von Otto. Eigene Aufgabe.

## Offen, aus den Läufen

Diesen Abschnitt schreibt jeder Lauf neu (zwischen den Markierungen); was nicht mehr auftritt, steht danach
abgehakt unter „Erledigt“.

<!-- auto:start -->
- [ ] **SCHUTZ www.gkd.bayern.de** · seit 2026-11-25 · zuletzt 2026-11-27 · Host: 3670 durchgefallen, 3816 ohne Antwort, 322 bestanden; nichts verborgen, nichts freigegeben, liegt eher an der Prüfung.
  - `www.gkd.bayern.de/de/grundwasser/oberesstockwerk/kelheim/{x}`: 392 durchgefallen, 399 ohne Antwort, 1 bestanden
  - `www.gkd.bayern.de/de/grundwasser/chemie/kelheim/{x}`: 235 durchgefallen, 247 ohne Antwort, 0 bestanden
  - `www.gkd.bayern.de/de/grundwasser/oberesstockwerk/isar/{x}`: 214 durchgefallen, 202 ohne Antwort, 0 bestanden
  - `www.gkd.bayern.de/de/fluesse/biologie/kelheim/{x}`: 160 durchgefallen, 155 ohne Antwort, 48 bestanden
  - `www.gkd.bayern.de/de/grundwasser/oberesstockwerk/passau/{x}`: 166 durchgefallen, 166 ohne Antwort, 0 bestanden
  - und 63 weitere Muster, siehe `linkpruefung.md`
- [ ] **SCHUTZ ckan.open.nrw.de** · seit 2026-11-25 · zuletzt 2026-11-27 · Host: 0 durchgefallen, 576 ohne Antwort, 41 bestanden; nichts verborgen, nichts freigegeben, liegt eher an der Prüfung.
  - `ckan.open.nrw.de/dataset/{x}`: 0 durchgefallen, 576 ohne Antwort, 41 bestanden
- [ ] **SCHUTZ odlinfo.bfs.de** · seit 2026-11-25 · zuletzt 2026-11-27 · Host: 301 durchgefallen, 0 ohne Antwort, 0 bestanden; nichts verborgen, nichts freigegeben, liegt eher an der Prüfung.
  - `odlinfo.bfs.de/ODL/DE/themen/{x}/karte/_documents/{x}?id`: 301 durchgefallen, 0 ohne Antwort, 0 bestanden
- [ ] **SCHUTZ portal-chemnitz.opendata.arcgis.com** · seit 2026-11-25 · zuletzt 2026-11-27 · Host: 0 durchgefallen, 138 ohne Antwort, 0 bestanden; nichts verborgen, nichts freigegeben, liegt eher an der Prüfung.
  - `portal-chemnitz.opendata.arcgis.com/datasets/{x}`: 0 durchgefallen, 93 ohne Antwort, 0 bestanden
- [ ] **SCHUTZ opendata.soest.de** · seit 2026-11-25 · zuletzt 2026-11-27 · Host: 0 durchgefallen, 88 ohne Antwort, 0 bestanden; nichts verborgen, nichts freigegeben, liegt eher an der Prüfung.
  - `opendata.soest.de/dataset/{id}`: 0 durchgefallen, 88 ohne Antwort, 0 bestanden
- [ ] **SCHUTZ www.daten.bmfsfj.de** · seit 2026-11-25 · zuletzt 2026-11-27 · Host: 0 durchgefallen, 65 ohne Antwort, 0 bestanden; nichts verborgen, nichts freigegeben, liegt eher an der Prüfung.
  - `www.daten.bmfsfj.de/daten/daten/{x}`: 0 durchgefallen, 65 ohne Antwort, 0 bestanden
- [ ] **SCHUTZ visualize.admin.ch** · seit 2026-11-25 · zuletzt 2026-11-27 · Host: 47 durchgefallen, 0 ohne Antwort, 0 bestanden; nichts verborgen, nichts freigegeben, liegt eher an der Prüfung.
  - `visualize.admin.ch/en/browse?dataSource&dataset&previous`: 33 durchgefallen, 0 ohne Antwort, 0 bestanden
- [ ] **SCHUTZ www.offenedaten-wuppertal.de** · seit 2026-11-27 · zuletzt 2026-11-27 · Host: 0 durchgefallen, 46 ohne Antwort, 0 bestanden; nichts verborgen, nichts freigegeben, liegt eher an der Prüfung.
  - `www.offenedaten-wuppertal.de/dataset/{x}`: 0 durchgefallen, 46 ohne Antwort, 0 bestanden
- [ ] **SCHUTZ geoportal.aachen.de** · seit 2026-11-25 · zuletzt 2026-11-27 · Host: 38 durchgefallen, 0 ohne Antwort, 0 bestanden; nichts verborgen, nichts freigegeben, liegt eher an der Prüfung.
  - `geoportal.aachen.de/extern/?basemap&blop&hl&lang&layers&x&y&zl`: 26 durchgefallen, 0 ohne Antwort, 0 bestanden
- [ ] **SCHUTZ www.duva-server.de** · seit 2026-11-25 · zuletzt 2026-11-27 · Host: 0 durchgefallen, 38 ohne Antwort, 0 bestanden; nichts verborgen, nichts freigegeben, liegt eher an der Prüfung.
  - `www.duva-server.de/{x}/dataset/{x}`: 0 durchgefallen, 38 ohne Antwort, 0 bestanden
- [ ] **SCHUTZ geodienste.hamburg.de** · seit 2026-11-27 · zuletzt 2026-11-27 · Host: 26 durchgefallen, 0 ohne Antwort, 0 bestanden; nichts verborgen, nichts freigegeben, liegt eher an der Prüfung.
  - `geodienste.hamburg.de/download?f&url`: 26 durchgefallen, 0 ohne Antwort, 0 bestanden
- [ ] **SCHUTZ biel-bienne.mapplus.ch** · seit 2026-11-27 · zuletzt 2026-11-27 · Host: 29 durchgefallen, 0 ohne Antwort, 0 bestanden; nichts verborgen, nichts freigegeben, liegt eher an der Prüfung.
- [ ] **SCHUTZ archiv.transparenz.hamburg.de** · seit 2026-11-27 · zuletzt 2026-11-27 · Host: 22 durchgefallen, 0 ohne Antwort, 5 bestanden; nichts verborgen, nichts freigegeben, liegt eher an der Prüfung.
  - `archiv.transparenz.hamburg.de/hmbtgarchive/HMDK/{x}`: 22 durchgefallen, 0 ohne Antwort, 5 bestanden
- [ ] **SCHUTZ www.stadt-muenster.de** · seit 2026-11-27 · zuletzt 2026-11-27 · Host: 17 durchgefallen, 0 ohne Antwort, 6 bestanden; nichts verborgen, nichts freigegeben, liegt eher an der Prüfung.
- [ ] **UNGEPRUEFT https://data.geo.so.ch?filter={id}** · seit 2026-11-27 · zuletzt 2026-11-27 · 154 Links ohne sichere Prüfung, ihre Einträge bleiben unsichtbar.
- [ ] **UNGEPRUEFT https://datenregister.berlin.de/dataset/{id}** · seit 2026-11-27 · zuletzt 2026-11-27 · 402 Links ohne sichere Prüfung, ihre Einträge bleiben unsichtbar.
- [ ] **UNGEPRUEFT https://map.bern.ch/geoportal/#/produkt/{id}** · seit 2026-11-27 · zuletzt 2026-11-27 · 208 Links ohne sichere Prüfung, ihre Einträge bleiben unsichtbar.
- [ ] **UNGEPRUEFT https://metadata.geo.sg.ch/produkte/{id}** · seit 2026-11-27 · zuletzt 2026-11-27 · 47 Links ohne sichere Prüfung, ihre Einträge bleiben unsichtbar.
- [ ] **UNGEPRUEFT https://mobilithek.info//offers/{id}** · seit 2026-11-27 · zuletzt 2026-11-27 · 847 Links ohne sichere Prüfung, ihre Einträge bleiben unsichtbar.
- [ ] **UNGEPRUEFT https://www.agi.dij.be.ch/de/start/geoportal/geodaten/detail.html?type=geoproduct&code={c** · seit 2026-11-27 · zuletzt 2026-11-27 · 211 Links ohne sichere Prüfung, ihre Einträge bleiben unsichtbar.
- [ ] **UNGEPRUEFT https://www.kiel.de/opendata/index.php?id={id}** · seit 2026-11-27 · zuletzt 2026-11-27 · 66 Links ohne sichere Prüfung, ihre Einträge bleiben unsichtbar.
- [ ] **MUSTER www.govdata.de/suche/daten/{x}** · seit 2026-11-27 · zuletzt 2026-11-27 · 111 durchgefallen, 0 nicht prüfbar, 56102 bestanden. Beispiele: „govdata.035cad17-692f-4499-bfa0-86d0404cec2a“ <https://www.govdata.de/suche/daten/umweltplakette-nutzfahrzeuge0fb3a>; „govdata.05e455ba-ffda-489c-9cdb-e14757a198b4“ <https://www.govdata.de/suche/daten/gewasserstrukturkartierung-der-fliessgewasser-bayerns-2017-vor-ort-verfahren-auestruktur719b7>; „govdata.08a890e1-22bc-4c28-9673-df7f20055aef“ <https://www.govdata.de/suche/daten/klimaatlas-nrw-biodiversitat-und-naturschutz-vegetationszeit56395>
- [ ] **MUSTER www.geoportal.rlp.de/map?LAYER%5Bid%5D&LAYER%5Bzoom%5D** · seit 2026-11-27 · zuletzt 2026-11-27 · 9 durchgefallen, 0 nicht prüfbar, 6723 bestanden. Beispiele: „govdata.1372eef6-499f-4e8b-9d1b-380fd80afc3e“ <https://www.geoportal.rlp.de/map?LAYER%5Bzoom%5D=1&LAYER%5Bid%5D=62127>; „govdata.285230f7-0fd2-448d-801c-87af29cff5ca“ <https://www.geoportal.rlp.de/map?LAYER%5Bzoom%5D=1&LAYER%5Bid%5D=71055>; „govdata.395d94fa-3a59-4616-b377-c1a504eaf371“ <https://www.geoportal.rlp.de/map?LAYER%5Bzoom%5D=1&LAYER%5Bid%5D=47482>
- [ ] **MUSTER open.bydata.de/datasets/{id}** · seit 2026-11-27 · zuletzt 2026-11-27 · 21 durchgefallen, 0 nicht prüfbar, 2579 bestanden. Beispiele: „govdata.15cd19c2-fe78-4ee5-b9a6-07e144e4f2bf“ <https://open.bydata.de/datasets/wanderungssaldo_altersgruppe_65+_unterbezirksebene_ingolstadt>; „govdata.22e5f2b3-543b-4501-af9d-df35672a3ef7“ <https://open.bydata.de/datasets/zuzugs-wegzugssaldo_altersgruppe_65+_stadtbezirksebene_ingolstadt>; „govdata.23ca569e-0ec2-401f-9d53-c146853c83f5“ <https://open.bydata.de/datasets/wohnungen_-_haushaltsgroeße_stadtbezirksebene_ingolstadt>
- [ ] **WARNZEICHEN W1 fsdi-stac** · seit 2026-11-25 · zuletzt 2026-11-27 · 2 Einträge warten. Beispiele: „HQStat flood statistics“ <https://data.geo.admin.ch/browser/index.html#/collections/ch.bafu.hydrologie-hochwasserstatistik>; „NQStat low-flow statistics“ <https://data.geo.admin.ch/browser/index.html#/collections/ch.bafu.hydrologie-niedrigwasserstatistik>
- [ ] **WARNZEICHEN W1 govdata** · seit 2026-11-25 · zuletzt 2026-11-27 · 8 Einträge warten. Beispiele: „Statistisches Jahrbuch 2015 - Bottrop“ <https://www.govdata.de/suche/daten/statistisches-jahrbuch-2015-bottrop81f57>; „govdata.11a29574-214f-4b83-a569-8844eb75fd86“; „Statistisches Jahrbuch 2006 - Bottrop“ <https://www.govdata.de/suche/daten/statistisches-jahrbuch-2006-bottrop46669>
- [ ] **WARNZEICHEN W2 govdata** · seit 2026-11-25 · zuletzt 2026-11-27 · 18 Einträge warten. Beispiele: „Bevölkerungsstand 2023 / Bevölkerung 65 Jahre und älter, Veränderung gegenüber 2“ <https://www.geoportal.rlp.de/map?LAYER%5Bzoom%5D=1&LAYER%5Bid%5D=86329>; „Unfallatlas“ <https://unfallatlas.statistikportal.de/?BL=HE>; „Entnahme“ <https://www.govdata.de/suche/daten/entnahme6f9b7>
- [ ] **WARNZEICHEN W4 govdata** · seit 2026-11-25 · zuletzt 2026-11-27 · 12 Einträge warten. Beispiele: „Energiebedingte CO2-Emissionen aus demPrimärenergieverbrauch im Verkehr nach Art“ <https://www.govdata.de/suche/daten/energiebedingte-co2-emissionen-aus-demprimarenergieverbrauch-im-verkehr-nach-art-des-verkehrs-j9c1d4>; „ATKIS-DGM 1“ <https://hvbg.hessen.de/landesvermessung/geotopographie/3d-daten/digitale-gelaendemodelle>; „Förderung nach dem Stipendiumprogramm-Gesetz (Deutschlandstipendium)“ <https://www.govdata.de/suche/daten/forderung-nach-dem-stipendiumprogramm-gesetz-deutschlandstipendium312ed>
- [ ] **WARNZEICHEN W5 govdata** · seit 2026-11-25 · zuletzt 2026-11-27 · 15 Einträge warten. Beispiele: „Flächenentwicklungsplan für deutsche Seegebiete 2024 Draft“ <https://mobilithek.info//offers/-3460808345040004682>; „Flächenentwicklungsplan für deutsche Seegebiete 2024 Preliminary Draft - WMS“ <https://mobilithek.info//offers/-4050646591338157004>; „Flächenentwicklungsplan für deutsche Seegebiete 2023 Draft“ <https://mobilithek.info//offers/-26756060437703397>
- [ ] **WARNZEICHEN W6 govdata** · seit 2026-11-25 · zuletzt 2026-11-27 · 4 Einträge warten. Beispiele: „govdata.11a29574-214f-4b83-a569-8844eb75fd86“; „govdata.3f06a322-7f94-4af1-8cce-e9de6c4adcf3“; „govdata.e904dd43-d48f-474f-aace-3e82c2b26b46“
- [ ] **WARNZEICHEN W1 opendata-swiss** · seit 2026-11-25 · zuletzt 2026-11-27 · 1 Einträge warten. Beispiele: „Einsatzstatistik Rettungsdienst Zug (RDZ)“ <https://opendata.swiss/de/dataset/einsatzstatistik-rettungsdienst-zug-rdz>
- [ ] **WARNZEICHEN W4 opendata-swiss** · seit 2026-11-25 · zuletzt 2026-11-27 · 1 Einträge warten. Beispiele: „Baumkronenbedeckung in Siedlungsarealen der Gemeinden“ <https://opendata.swiss/de/dataset/baumkronenbedeckung-in-siedlungsarealen-der-gemeinden>
- [ ] **LIZENZ mdd-nrw-nutzungsbedingungen** · seit 2026-11-25 · zuletzt 2026-11-27 · 27 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ Nutzung der Daten nur nach Rücksprache mit dem Dateneigentüm** · seit 2026-11-27 · zuletzt 2026-11-27 · 8 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ http://dcat-ap.de/def/licenses/dl-by-nc-de/1.0** · seit 2026-11-27 · zuletzt 2026-11-27 · 7 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ https://www.wuppertal.de/service/impressum.php** · seit 2026-11-27 · zuletzt 2026-11-27 · 7 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ This dataset results from the joint project 'mDRONES4rivers'** · seit 2026-11-27 · zuletzt 2026-11-27 · 6 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ Die Daten werden fortlaufend aktualisiert. Trotz sorgfältige** · seit 2026-11-27 · zuletzt 2026-11-27 · 5 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ http://dcat-ap.de/def/licenses/bsd** · seit 2026-11-27 · zuletzt 2026-11-27 · 5 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ https://sentinel.esa.int/documents/247904/690755/Sentinel_Da** · seit 2026-11-27 · zuletzt 2026-11-27 · 5 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ Bei den Daten handelt es sich um Rohdaten der RFID-Sensoren.** · seit 2026-11-27 · zuletzt 2026-11-27 · 4 Funde warten auf eine Einstufung von Otto.
- [ ] **LIZENZ -** · seit 2026-11-27 · zuletzt 2026-11-27 · 3 Funde warten auf eine Einstufung von Otto.
<!-- auto:end -->

## Erledigt

- [x] **H-2026-11-24-07** · 2026-11-24 · Lauf · Der erste Probelauf brach nach `spellings` ab: `spellings.yaml` war mit
  YAML-Ankern geschrieben (eine `date` in mehreren Zeilen), der Lader lehnte sie ab („an anchor is not allowed (line 8)“).
  Erledigt 24.11.2026 (Fix 1, [#414](https://github.com/oscipal/earthX/pull/414), Plan M5-67 §22): `dump_yaml` schreibt ohne Anker und liest sein Ergebnis zurück; alle
  Schreiber des Laufs geprüft; Integrationstest über alle Schritte.
- [x] **H-2026-11-24-08** · 2026-11-24 · Lauf · Eine planmäßige Pause von `harvest` (govdata: Seiten je Lauf erreicht)
  galt als „Harvest gescheitert“. Erledigt 24.11.2026 (Fix 1): Exit-Code 75 ist Erfolg, nur ein Hinweis im Bericht; das
  Skript wertet nur Exit-Codes aus (Auslegung A24 im Plan §22).
- [x] **H-2026-11-24-09** · 2026-11-24 · Lauf · Fenster, `fehler.log` und PR-Text nannten bei einem Abbruch nur den Schritt,
  nicht die Fehlerzeile. Erledigt 24.11.2026 (Fix 1): jeder Schritt hängt die Zeile an, die sagt warum.
- [x] **H-2026-11-24-10** · 2026-11-24 · Lauf · Ein zweiter Lauf am selben Tag stieß auf Branch und Draft-PR des ersten.
  Erledigt 24.11.2026 (Fix 1): Branch `harvest/<Tag>-<Uhrzeit>`; Draft-PRs gescheiterter Läufe schließt der nächste Lauf
  selbst und löscht ihre Branches.
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
- [x] **SCHUTZ www.govdata.de** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ www.geoportal.rlp.de** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ registry.gdi-de.org** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ open.bydata.de** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ open.rlp.de** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ mobilithek.info** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ datenregister.berlin.de** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ www.agi.dij.be.ch** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ map.bern.ch** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ data.geo.so.ch** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ opendata.herne.de** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ geodatenkatalog.frankfurt.de** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ metadata.geo.sg.ch** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ opendata.ruhr** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ www.geocat.ch** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ www.kiel.de** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ opendata-duisburg.de** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **SCHUTZ www.geoportal.hessen.de** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **LIZENZ Weitere Informationen zu den Daten und Veröffentlichungen er** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **LIZENZ https://data-lra-cha.opendata.arcgis.com/api/feed/dcat-ap/3.** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **LIZENZ https://www.offenedaten-wuppertal.de/page/nutzungsbedingunge** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **LIZENZ Es gelten keine Zugriffsbeschränkungen** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **LIZENZ http://inspire.ec.europa.eu/metadata-codelist/LimitationsOnP** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **LIZENZ https://opendata.kreis-borken.de/pages/datenschutz** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **LIZENZ Der Zugang zu den Daten ist nach § 3 des Informationsfreihei** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
- [x] **LIZENZ Es erfolgt ein kompletter Haftungsausschluss. Es wird keiner** · 2026-11-25 bis 2026-11-27 · im Lauf vom 2026-11-27 nicht mehr aufgetreten
