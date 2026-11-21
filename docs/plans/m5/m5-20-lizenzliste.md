# M5-20 — Lizenzliste zur Einstufung (Vorschlag, Stand 20.11.2026)

> **Eingestuft von Otto am 20.11.2026** (Plan §13f): Klassen wie vorgeschlagen, mit diesen Änderungen:
> - Luftfahrt-Bundesamt: K2 als eigene Lizenz.
> - NB-GDIKOM-B: K6.
> - „Sie dürfen: …“: CC BY 4.0.
> - `mdd-nrw-nutzungsbedingungen`: K7.
> - Amtliches Werk: K1, nicht freigegeben.
> - admin.ch (beide): K6.
>
> Umgesetzt in `backend/catalog/licenses/terms.yaml`; freigegeben werden K1 bis K5 über `grant-to-all.yaml`. Die Tabellen unten bleiben als Stand des Vorschlags.

**Zweck:** Vorlage für Ottos Einstufung der Lizenzangaben geernteter Funde in `backend/catalog/licenses/terms.yaml` (`adr/0033` §6.2, L2; Plan §9, §13b, F5 = 1). **Die Einstufung macht Otto. Nichts hier ist entschieden, und nichts ist Rechtsberatung.**

**Datengrundlage:** Ottos `-Classify` vom 20.11.2026, nach dem zweiten Push. Die Angaben sind normalisiert: ohne Leerzeichen am Rand, ohne `/` am Ende.
- opendata-swiss: 16 216 Funde, 7 verschiedene Angaben.
- govdata: 168 882 Funde, 5 559 verschiedene Angaben; hier die 60 häufigsten.
- fsdi-stac: 515 Funde, 12 Angaben.

Wie zu lesen:
- **Zahlen:** Gezählt sind alle Funde, auch die als Nicht-Geodaten verborgenen. Materials Cloud, PSI Data Catalog, Deutsche Bibliotheksstatistik und BKA sind darunter, werden aber nie sichtbar.
- **Lange Angaben:** `-Classify` kürzt sie auf 160 Zeichen. Wörtlich für `matches` stehen sie seit diesem Stand im Abschnitt „Lizenzangaben vollständig“ (JSON).
- **Belege:** Erstellt hat sie der Subagent `license-checker`, aber nur über Suchtreffer. dcat-ap.de und opendata.swiss sind aus der Sitzung nicht erreichbar; vor der Einstufung am Text prüfen.

## 1. Was die Einstufung bewirkt

Für jede Lizenz setzt Otto in `terms.yaml`:
- **Bezeichnung:** `spdx_id` oder Name und URL.
- **Fünf Flags:** Weitergabe, kommerzielle Nutzung, Bearbeitung, Share-Alike, Namensnennung.
- **`tier`** und die zwei Texte der Namensnennung (`{publisher}` wird ersetzt).
- **`terms`**, wahlweise: Link und Hinweistext der Nutzungsbedingungen.

**Sichtbar wird ein Fund** nur, wenn alle drei Bedingungen erfüllt sind:
1. Jede seiner Lizenzangaben steht in `terms.yaml`.
2. Die Lizenz ist für seinen Herausgeber in `grants/<quelle>.yaml` freigegeben.
3. Sein Lauf ist freigegeben (Freigabedatei).

Die Einstufung allein macht nichts sichtbar.

**Gelistete Einträge bleiben immer Katalogeintrag mit Link.** Die Plattform zeigt keine Kacheln und rechnet nichts. Von der Einstufung zeigt der Data catalogue heute:
- **License:** Name mit Link, dazu „Catalogue“ und, wenn `terms.url` gesetzt ist, ein Link „Terms“.
- **Attribution:** die beiden Texte der Namensnennung, sonst „–“.

Die Flags werden gespeichert (`earthx:license_flags`), aber bei gelisteten Einträgen nicht angezeigt. Sie wirken erst bei vollen Einträgen:
- Ohne Weitergabe oder ohne Bearbeitung bleibt es beim Katalogeintrag.
- Ohne kommerzielle Nutzung gilt Processing nur im Gratis-Tier (B11).

Einen eigenen **Warnhinweis** gibt es für gelistete Einträge nicht. Möglich ist nur der Link „Terms“ auf die Bedingungen des Anbieters; der Hinweistext `terms.notice` geht heute nur bei Downloads voller Einträge mit.

**„Nie sichtbar“** erreicht Otto auf drei Wegen:
- Die Angabe gar nicht in `terms.yaml` aufnehmen; der Fund wartet dann (`needs_rule`).
- Die Lizenz dem Herausgeber nicht freigeben.
- Herausgeber oder Eintrag in `blocked.yaml` sperren.

Auch eine geschlossene Lizenz erlaubt einen Katalogeintrag mit Link (B11: dafür gibt es keine Voraussetzung). Ändert Otto eine Einstufung später, gehen die betroffenen Einträge zurück in die Prüfung (A18).

### Vorgeschlagene Klassen

Damit nicht jede Lizenz einzeln durchdacht werden muss, schlage ich sieben Klassen vor. Die Flags stehen in der Reihenfolge Weitergabe/kommerziell/Bearbeitung/Share-Alike/Namensnennung.

| Klasse | Flags | Namensnennung | Wirkung im Data catalogue | Lizenzen (Vorschlag) |
|---|---|---|---|---|
| K1 offen ohne Namensnennung | J/J/J/N/N | keine | Lizenz mit Link | CC0, DL-DE Zero 2.0, PDM, amtliches Werk (§ 5 Abs. 1 UrhG), opendata.swiss `terms_open` |
| K2 offen mit Namensnennung | J/J/J/N/J | „© {publisher}“ bzw. Vorgabe der Lizenz | Lizenz und Text der Namensnennung | CC BY (alle Versionen), DL-DE BY 1.0/2.0, GeoNutzV, `terms_by`, swisstopo OGD, ODC-By |
| K3 Weitergabe unter gleichen Bedingungen | J/J/J/J/J | wie K2 | wie K2 | CC BY-SA, ODbL |
| K4 nicht kommerziell | J/N/J/N/J | wie K2 | wie K2 | CC BY-NC (alle), `terms_ask`, `terms_by_ask` |
| K5 keine Bearbeitung | J/J/N/N/J | wie K2 | wie K2 (voll: nur Katalog) | CC BY-ND |
| K6 Bedingungen unbekannt oder geschlossen | N/N/N/N/N | keine | Lizenzname mit Link, sonst nichts | `other-closed`, `other-open`, `other-opensource`, `other-commercial`, `andere`, Bund `disclaimer.admin.ch` |
| K7 keine Lizenz | – | – | nie sichtbar (wartet) | Hinweistexte, Feeds, Seiten, Zugriffsangaben (Abschnitt 3) |

## 2. Lizenzangaben mit Zahlen

„Herausgeber“ nennt die drei häufigsten mit ihrer Zahl. Schreibweisen derselben Lizenz stehen zusammen: Sie wären je eine Zeile in `matches` derselben `license_ref`.

### opendata.swiss

| Funde | Angabe | Herausgeber | Klasse (Vorschlag) |
|---|---|---|---|
| 9 122 | `https://opendata.swiss/terms-of-use#terms_by` | BFS 3 344; Materials Cloud 1 170; Kanton Basel-Stadt 655 | K2 |
| 6 398 | `https://opendata.swiss/terms-of-use#terms_open` | Kanton Genf 1 001; AGIS Aargau 772; Stadt Zürich 665 | K1 |
| 1 761 | `http://www.opendefinition.org/licenses/cc-by` (ohne Version) | Materials Cloud 1 170; Kanton Basel-Stadt 262; EnviDat 118 | K2 |
| 738 | `https://opendata.swiss/terms-of-use#terms_by_ask` | EnviDat 431; PSI 188; BAZG 25 | K4 |
| 504 | `http://www.opendefinition.org/licenses/cc-by-sa` | PSI 188; EnviDat 173; Amt für Statistik und Daten Freiburg 128 | K3 |
| 249 | `http://www.opendefinition.org/licenses/cc-zero` | Kanton Thurgau 187; EnviDat 59; Materials Cloud 3 | K1 |
| 27 | `https://opendata.swiss/terms-of-use#terms_ask` | BAKOM 24; BFS 2; BAZG 1 | K4 |

### FSDI (STAC)

| Funde | Angabe | Herausgeber | Klasse (Vorschlag) |
|---|---|---|---|
| 492 | `proprietary` | BAFU 156; BFE 39; – 36 | entfällt nach dem nächsten `--reextract` mit `--build` (§13e): dann zählt nur der Link `rel=license` |
| 192 / 11 / 1 | `https://opendata.swiss/en/terms-of-use/#terms_by`, `…/terms-of-use/#terms_by`, `…/en/terms-of-use#terms_by` | BAFU 41; BFE 39; BLW 31 / BAV 11 / BABS 1 | K2 (gleiche Lizenz wie oben, andere Schreibweise) |
| 64 | `https://www.swisstopo.admin.ch/ogd-conditions` | swisstopo 34 + 21; Georessourcen 6 | K2 (Quelle „© swisstopo“) |
| 38 | `http://disclaimer.admin.ch` | BAKOM 17; ASTRA 9; BAG 4 | K6 (Haftungsausschluss, keine Lizenz) |
| 23 | `CC-BY` | MeteoSchweiz 22; Agroscope 1 | K2 |
| 10 / 3 | `https://opendata.swiss/en/terms-of-use#terms_by_ask`, `…/en/terms-of-use/#terms_by_ask` | BFS 9; BAG 1 / BAK 2; BFS 1 | K4 |
| 7 | `https://www.admin.ch/gov/en/start/terms-and-conditions.html` | BABS 1; BASPO 1; ENSI 1 | K6 |
| 1 / 1 | `https://opendata.swiss/en/terms-of-use#terms_open`, `…/en/terms-of-use/#terms_open` | BAFU 1 / BAFU 1 | K1 |

### GovData (die 60 häufigsten von 5 559)

| Funde | Angabe(n) | Herausgeber | Klasse (Vorschlag) |
|---|---|---|---|
| 91 454 | `http://dcat-ap.de/def/licenses/dl-by-de/2.0` | Statistikamt Nord 22 096; LGB Brandenburg 11 155; BSH 6 278 | K2 |
| 620 / 277 / 269 / 48 | `https://www.govdata.de/dl-de/by-2-0`, `…/dl-by-de/2_0`, `http://www.govdata.de/dl-de/by-2-0`, `https://www.dcat-ap.de/def/licenses/dl-by-de/2.0` | Dortmund 242; BKA KI 35 114; HVV 113; Potsdam 47 | K2 (dieselbe Lizenz) |
| 222 / 24 / 23 | Freitexte zur DL-DE BY 2.0 (BSH „Dieser Datensatz kann gemäß der …“; LfU Brandenburg mit Quellenvermerk; EBA „Nutzungsbedingungen: …“) | BSH 209; LfU 24; EBA 22 | K2, Wortlaut aus dem JSON-Abschnitt |
| 56 | `http://dcat-ap.de/def/licenses/dl-by-de` (ohne Version) | Flensburg 34; Amt Mittelholstein 7 | K2 |
| 97 | `http://dcat-ap.de/def/licenses/dl-by-de/1.0` | Polizei NRW 87; LAWI Hessen 4 | K2 |
| 22 944 | `http://dcat-ap.de/def/licenses/dl-zero-de/2.0` | Edewecht 672; Leer 609; Bad Zwischenahn 605 | K1 |
| 938 / 191 / 30 / 14 | `https://www.govdata.de/dl-de/zero-2-0`, `http://dcat-ap.de/def/licenses/dl-de-zero-2.0`, `…/dl-zero-de/2_0`, „Datenlizenz Deutschland – Zero – Version 2.0“ | Dortmund 522; Herne 128; BAuA 14; FGeoWSV 8 | K1 (dieselbe Lizenz) |
| 33 116 | `http://dcat-ap.de/def/licenses/cc-by/4.0` | Bayer. Landesamt für Statistik 12 022; Denkmalpflege 4 359; BASt 1 262 | K2 |
| 314 / 193 / 76 / 72 | „Creative Commons Namensnennung – 4.0 International (CC BY 4.0)“, `https://creativecommons.org/licenses/by/4.0`, `…/by/4.0/legalcode.de`, `http://dcat-ap.de/def/licenses/CC%20BY%204.0` | Referat D/3 63; Landkreis Cham 160; Wuppertal 76; BAW 66 | K2 |
| 122 / 73 / 31 | Freitexte zu CC BY 4.0 (BSH; BAW mit „nicht tauglich für Navigation“ und Quellenvermerk) | BSH 122; BAW 73 + 31 | K2, Wortlaut aus dem JSON-Abschnitt |
| 1 747 | `http://dcat-ap.de/def/licenses/cc-by` (ohne Version) | Stromnetz Berlin 343; UB TUM 295; BSH 226 | K2 |
| 543 | `http://dcat-ap.de/def/licenses/cc-by-de/3.0` | VG Bernkastel-Kues 218; Duisburg 86 | K2 |
| 17 921 | `http://dcat-ap.de/def/licenses/cc-zero` | Bibliotheksstatistik 1 759; MEKUN 838; VG Gerolstein 596 | K1 |
| 2 505 | `http://dcat-ap.de/def/licenses/ccpdm/1.0` | Landesmeldestelle SH 1 494; LVermGeo SH 537; ZIT SH 262 | K1 |
| 261 / 14 / 12 | `http://dcat-ap.de/def/licenses/officialWork`, `…/official-work`, `http://www.gesetze-im-internet.de/urhg/__5.html` | BKA KI 35 114; Bundessortenamt 2; PTB 2 | K1 (Vorsicht: oft zu weit verwendet) |
| 319 | `http://dcat-ap.de/def/licenses/geonutz/20130319` | BGR 106 + 69; BfN 78 | K2 |
| 1 399 / 68 / 16 | `…/cc-by-nc-de/3.0`, `…/cc-by-nc/4.0`, `…/cc-by-nc` | VG Hunsrück-Mittelrhein 274; RVR 19; UB TUM 13 | K4 |
| 60 | `http://dcat-ap.de/def/licenses/cc-by-nd/4.0` | Region Hannover 15; Wuppertal 9 | K5 |
| 454 / 144 | `…/cc-by-sa/4.0`, `…/cc-by-sa` | Augsburg 169; UB TUM 60 | K3 |
| 553 / 9 | `http://dcat-ap.de/def/licenses/odbl`, Freitext Region Hannover („odbl“) | movisda 208; Metropolregion Rhein-Neckar 147; Region Hannover 9 | K3 |
| 47 | `http://dcat-ap.de/def/licenses/odcpddl` | UB LMU 36; TU Dresden 9 | K1 (Public Domain Dedication) |
| 21 | `http://dcat-ap.de/def/licenses/odby` | UB LMU 12; HS Landshut 5 | K2 |
| 8 528 | `http://dcat-ap.de/def/licenses/other-closed` | Moers 500; GDI-RP 362; – 358 | K6 |
| 107 / 86 / 22 / 11 | `…/other-open`, `…/other-opensource`, `…/andere`, `…/other-commercial` | NKK 27; Rhein-Neckar 44; Bochum 22; Wuppertal 4 | K6 |
| 43 / 11 | Freitexte des Luftfahrt-Bundesamts („kostenfrei bereitgestellt und dürfen unter Verweis auf den H…“) | LBA | Otto: K2 als eigene Lizenz oder K7 |
| 36 | „NB-GDIKOM-B für Geodatendienste …“ | Wuppertal | Otto: eigene Lizenz (Bedingungen lesen) oder K7 |
| 27 | „Sie dürfen: Teilen … Bearbeiten …“ (Auszug eines CC-Textes ohne Namen) | NASA Sachsen-Anhalt | Otto: K7 (welche CC-Lizenz ist unklar) |
| 27 | `mdd-nrw-nutzungsbedingungen` | OpenData ÖPNV | Otto: Bedingungen lesen |

## 3. Keine Lizenz (Vorschlag K7, bleibt wartend)

| Funde | Angabe | Herausgeber |
|---|---|---|
| 332 / 19 | „Weitere Informationen zu den Daten und Veröffentlichungen erhalten Sie über das Portal.“ | KBA |
| 165 | `https://data-lra-cha.opendata.arcgis.com/api/feed/dcat-ap/3.0.0.json` (Feed) | Landkreis Cham |
| 116 | `https://www.offenedaten-wuppertal.de/page/nutzungsbedingungen-kontakt-lizenzen` (Seite) | Wuppertal |
| 82 | „Es gelten keine Zugriffsbeschränkungen“ (Zugang, keine Lizenz) | UBA 78; Geobasis NRW 3 |
| 36 | `http://inspire.ec.europa.eu/metadata-codelist/LimitationsOnPublicAccess/noLimitations` (Zugang) | Wuppertal 13; Kreis Paderborn 12 |
| 18 | `https://opendata.kreis-borken.de/pages/datenschutz` | Kreis Borken |
| 11 | Projektbeschreibung mDRONES4rivers | BfG |
| 9 / 9 | „Nutzungseinschränkungen: Das DLR ist nicht haftbar …“; „Nutzungsbedingungen: Bedingungen unbekannt …“ | DLR; Region Hannover |

## 4. Belege (Stand 20.11.2026, nur Suchtreffer)

- dcat-ap.de Lizenzliste <https://www.dcat-ap.de/def/licenses/>; ckanext-dcatde <https://github.com/GovDataOfficial/ckanext-dcatde>; DCAT-AP CH <https://www.dcat-ap.ch/vocabulary/licenses/>; opendata.swiss <https://opendata.swiss/en/terms-of-use>; swisstopo OGD <https://www.swisstopo.admin.ch/en/terms-of-use-free-geodata-and-geoservices>; SPDX DL-DE-BY-2.0 <https://spdx.org/licenses/DL-DE-BY-2.0.html>.
- Hinweise von `license-checker`:
  - „other-open“ und „other-opensource“ sagen keine Bedingungen; deshalb K6.
  - „officialWork“ und „geonutz/20130319“ werden zu weit verwendet: GeoNutzV gilt nur für Bundesgeodaten, § 5 Abs. 1 UrhG nur für Gesetze, Verordnungen, Erlasse und Entscheidungen. Die Freigabe in `grants/` deshalb eng halten.
  - Bei FSDI je Link-Ziel einstufen, nicht pauschal.
