# Harvest-Lauf 2026-11-27

## Quellen

- **earth-search:** Funde 9, nicht ableitbar 0; Ergebnis needs_rule 9; warten unknown_licence 9; kein Stapel
- **fsdi-stac:** Funde 515, nicht ableitbar 0; Ergebnis needs_rule 105, ok 410; warten no_licence 60, not_granted 45; Stapel 13 mit 107 Einträgen
- **govdata:** Funde 169973, nicht ableitbar 0; Ergebnis needs_rule 14171, not_geodata 61148, ok 94654; warten no_access 3793, no_licence 109, not_granted 8649, unknown_licence 1620; Stapel 15 mit 982 Einträgen
- **opendata-swiss:** Funde 16253, nicht ableitbar 0; Ergebnis needs_rule 101, not_geodata 7774, ok 8378; warten no_access 101; Stapel 14 mit 104 Einträgen
- **govdata:** Hinweis, planmäßige Pause (kein Fehler): govdata: Lauf 76 (voll) interrupted (Seiten je Lauf erreicht (max_pages_per_run); der nächste Lauf setzt fort)

## Freigabe nach Regeln

- `2026-11-27-fsdi-stac.yaml`: freigegeben (Regeln erfüllt); 107 Einträge, davon 2 mit Warnzeichen draußen; Stichprobe 17 von 17 Links bestanden. Rücknahme: `revoked_on: <Tag>` in dieser Datei.
- `2026-11-27-govdata.yaml`: freigegeben (Regeln erfüllt); 982 Einträge, davon 43 mit Warnzeichen draußen; Stichprobe 9 von 30 Links bestanden. Rücknahme: `revoked_on: <Tag>` in dieser Datei.
- `2026-11-27-opendata-swiss.yaml`: freigegeben (Regeln erfüllt); 104 Einträge, davon 2 mit Warnzeichen draußen; Stichprobe 15 von 20 Links bestanden. Rücknahme: `revoked_on: <Tag>` in dieser Datei.

## Seit dem letzten Lauf automatisch veröffentlicht

0 Einträge. Zum Nachsehen:

- keine

## Linkprüfung

Fällig 90645, geprüft 84876: failed 6675, passed 67441, unchecked 10760; verborgen 4276, zurück 536. Einzelheiten in `linkpruefung.md`.

## Kandidaten des vollen Wegs

- **earth-search:** neu 0, geändert 0, unverändert 0, Zustand fortgeschrieben 0; übersprungen: –
- **fsdi-stac:** neu 6, geändert 0, unverändert 0, Zustand fortgeschrieben 0; übersprungen: über dem Verify-Budget 209, kein lesbares Format 53, Lizenzstufe catalog 13, Verify gescheitert 1
- **govdata:** neu 19, geändert 0, unverändert 0, Zustand fortgeschrieben 0; übersprungen: über dem Verify-Budget 2105, kein lesbares Format 131, Lizenzstufe catalog 3, Verify gescheitert 41
- **opendata-swiss:** neu 20, geändert 0, unverändert 0, Zustand fortgeschrieben 0; übersprungen: über der Grenze 20 233, kein lesbares Format 2, nicht ablösbar 1, Lizenzstufe catalog 1, Verify gescheitert 11

| Quelle | Vorschlag ID | Titel | Format | Lizenz | Stufe | Freigabe |
|---|---|---|---|---|---|---|
| fsdi-stac | `ch.swisstopo.pixelkarte-farbe-pk25.noscale` | National Map 1:25'000 | cog | swisstopo: Nutzungsbedingungen für kostenlose Geodaten und Geodienste (OGD) | processing | nach Regeln |
| fsdi-stac | `ch.are.solaranlagen-schutzinteressen` | Solaranlagen: Schutzinteressen | cog | opendata.swiss: Freie Nutzung, Quellenangabe ist Pflicht | processing | nach Regeln |
| fsdi-stac | `ch.meteoschweiz.ogd-climate-normals-grid` | Climate normals - Spatial analyses | hdf5 | Creative Commons Attribution (ohne Versionsangabe) | processing | nach Regeln |
| fsdi-stac | `ch.are.siedlung` | Settlement | geotiff | opendata.swiss: Freie Nutzung, Quellenangabe ist Pflicht | processing | nach Regeln |
| fsdi-stac | `ch.agroscope.fokuskarte-voegel` | Focus map agri-environmental objective birds | cog | opendata.swiss: Freie Nutzung, Quellenangabe ist Pflicht | processing | nach Regeln |
| fsdi-stac | `ch.bafu.luftreinhaltung-stickstoff_kritischer_eintrag` | Exceedance of critical loads for nitrogen | cog | opendata.swiss: Freie Nutzung, Quellenangabe ist Pflicht | processing | nach Regeln |
| govdata | `govdata-modelldaten-langfristiges-ertragspotenzial-offshore-149` | Modelldaten langfristiges Ertragspotenzial Offshore-Windenergie Nordsee - Szenar | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `govdata-modelldaten-ertragspotenzial-in-verschiedenen-ausbaujahren-119` | Modelldaten Ertragspotenzial in verschiedenen Ausbaujahren Offshore-Windenergie  | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `govdata-modelldaten-langfristiges-ertragspotenzial-offshore-131` | Modelldaten langfristiges Ertragspotenzial Offshore-Windenergie Nordsee - Szenar | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `govdata-modelldaten-ertragspotenzial-in-verschiedenen-ausbaujahren-126` | Modelldaten Ertragspotenzial in verschiedenen Ausbaujahren Offshore-Windenergie  | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `govdata-modelldaten-mehrjaehriges-ertragspotenzial-offshore-105` | Modelldaten mehrjähriges Ertragspotenzial Offshore-Windenergie Nordsee -2022-08 | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `govdata-modelldaten-langfristiges-ertragspotenzial-offshore-70` | Modelldaten langfristiges Ertragspotenzial Offshore-Windenergie Nordsee - Szenar | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `govdata-modelldaten-langfristiges-ertragspotenzial-offshore-71` | Modelldaten langfristiges Ertragspotenzial Offshore-Windenergie Nordsee - Szenar | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `modelldaten-mehrjaehriges-ertragspotenzial-offshore` | Modelldaten mehrjähriges Ertragspotenzial Offshore-Windenergie Nordsee -2014-06 | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `govdata-modelldaten-langfristiges-ertragspotenzial-offshore-276` | Modelldaten langfristiges Ertragspotenzial Offshore-Windenergie Nordsee - Szenar | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `govdata-modelldaten-ertragspotenzial-der-offshore-windenergie-fuer-15` | Modelldaten Ertragspotenzial der Offshore-Windenergie für die gesamte Nordsee, A | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `govdata-modellierte-temperatur-und-salzgehalt-des-operationellen-96` | Modellierte Temperatur und Salzgehalt des operationellen Zirkulationsmodells des | hdf5 | Creative Commons Attribution (ohne Versionsangabe) | processing | nach Regeln |
| govdata | `govdata-modellierte-temperatur-und-salzgehalt-des-operationellen-82` | Modellierte Temperatur und Salzgehalt des operationellen Zirkulationsmodells des | hdf5 | Creative Commons Attribution (ohne Versionsangabe) | processing | nach Regeln |
| govdata | `govdata-modelldaten-langfristiges-ertragspotenzial-offshore-159` | Modelldaten langfristiges Ertragspotenzial Offshore-Windenergie Nordsee - Szenar | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `govdata-modelldaten-mehrjaehriges-ertragspotenzial-offshore-59` | Modelldaten mehrjähriges Ertragspotenzial Offshore-Windenergie Nordsee -2020-04 | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `govdata-modelldaten-mehrjaehriges-ertragspotenzial-offshore-103` | Modelldaten mehrjähriges Ertragspotenzial Offshore-Windenergie Nordsee -2016-02 | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `govdata-modelldaten-ertragspotenzial-in-verschiedenen-ausbaujahren-48` | Modelldaten Ertragspotenzial in verschiedenen Ausbaujahren Offshore-Windenergie  | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `govdata-modelldaten-ertragspotenzial-der-offshore-windenergie-fuer-47` | Modelldaten Ertragspotenzial der Offshore-Windenergie für die gesamte Nordsee, A | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `govdata-modelldaten-langfristiges-ertragspotenzial-offshore-80` | Modelldaten langfristiges Ertragspotenzial Offshore-Windenergie Nordsee - Szenar | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| govdata | `govdata-modelldaten-langfristiges-ertragspotenzial-offshore-175` | Modelldaten langfristiges Ertragspotenzial Offshore-Windenergie Nordsee - Szenar | hdf5 | DL-DE-BY-2.0 | processing | nach Regeln |
| opendata-swiss | `histo-carte-traite-turin-paris-annexe-06-1816` | Histo_Carte_Traite_Turin_Paris_Annexe_06_1816 | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `histo-carte-traite-turin-paris-annexe-14-1933` | Histo_Carte_Traite_Turin_Paris_Annexe_14_1933 | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `mna-exposition-2019-pixel-0-5-m` | Mna Exposition 2019 (Pixel 0.5 M) | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `histo-carte-traite-turin-paris-annexe-04-1756` | Histo_Carte_Traite_Turin_Paris_Annexe_04_1756 | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `pollution-de-l-air-immissions-no2-2020` | Pollution De L'Air - Immissions No2 2020 | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `mna-terrain-lac-2003-pixel-5-0-m` | MNA Terrain Lac 2003 (pixel 5.0 m) | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `indice-de-permeabilite-des-sols` | Indice de perméabilité des sols | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `mna-relief-ombre-lac-2005-pixel-5-0-m` | MNA Relief Ombre Lac 2005 (pixel 5.0 m) | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `mna-relief-ombre-surface-agglo-2014-pixel-50-cm` | MNA Relief Ombre Surface Agglo 2014 (Pixel 50 Cm) | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `analyse-climatique-2020-vitesse-du-vent-nocturne-2020-2049` | Analyse climatique 2020 - Vitesse du vent nocturne 2020-2049 | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `orthophotos-1946-pixel-1-25-m` | Orthophotos 1946 (Pixel 1.25 M) | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `orthophotos-agglo-2021-pixel-20-cm` | Orthophotos Agglo 2021 (pixel 20 cm) | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `orthophotos-1983-pixel-50-cm` | Orthophotos 1983 (Pixel 50 Cm) | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `mna-hauteur-2023-pixel-0-2m` | Mna Hauteur 2023 (Pixel 0.2M) | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `mna-relief-ombre-surface-2017-pixel-50-cm` | Mna Relief Ombre Surface 2017 (Pixel 50 Cm) | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `analyse-climatique-2020-temperature-de-l-air-nocturne-1981` | Analyse climatique 2020 - Température de l'air nocturne 1981-2010 | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `mna-relief-ombre-surface-2019-pixel-0-5-m` | Mna Relief Ombre Surface 2019 (Pixel 0.5 M) | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `mna-relief-ombre-terrain-2017-pixel-0-5-m` | Mna Relief Ombre Terrain 2017 (Pixel 0.5 M) | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `mna-exposition-2005-pixel-2-0-m` | MNA Exposition 2005 (Pixel 2.0 m) | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |
| opendata-swiss | `carte-de-hondt-1630` | Carte De Hondt 1630 | cog | opendata.swiss: Freie Nutzung | processing | nach Regeln |

Dateien unter `backend/catalog/candidates/<Quelle>/`; herausnehmen über `blocked.yaml`.

Offene Befunde: `docs/harvest/befunde.md`. Dateien dieses Laufs: `docs/harvest/laeufe/2026-11-27/`.
