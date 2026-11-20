# M5-20 — Lizenzliste zur Einstufung (Vorschlag, Stand 20.11.2026)

**Zweck:** Vorlage für Ottos Einstufung der Lizenzangaben geernteter Funde in `backend/catalog/licenses/terms.yaml` (`adr/0033` §6.2, L2; Plan §9, §13b, F5 = 1). **Die Einstufung macht Otto; nichts hier ist eine Entscheidung und keine Rechtsberatung.**

**Belegstand, wichtig:**
- **Zahlen fehlen noch.** Die Zahl der Funde und die häufigsten Herausgeber je Angabe gibt `-Classify` seit diesem Stand selbst aus, im Abschnitt „Lizenzangaben“ (Plan §16). Die Ausgaben vom 20.11. lagen der Sitzung nicht vor. Die Spalte „Funde“ füllt die Session nach Ottos nächstem Lauf.
- **Die Belege sind nicht abgerufen.** Erstellt hat die Liste der Subagent `license-checker`. Die Primärquellen (dcat-ap.de, opendata.swiss) waren aus der Sitzung nicht erreichbar; es gab nur Suchtreffer.
- [S] steht für Suchtreffer, [W] für Vorwissen. Beides ist vor der Einstufung am Text zu prüfen.

Spalten der Tabelle:
- **Flags:** Weitergabe, kommerziell, Bearbeitung, Share-Alike, Namensnennung.
- **Werte:** J = ja, N = nein, ? = am Text nicht geprüft; „(N)“ heißt unklar, vorsichtig als N gesetzt.
- **Stufe** gilt nur für volle Einträge; gelistete Einträge bleiben immer Katalogeintrag.

| Angabe (wie im Katalog, Schreibweisen für `matches`) | Gemeint | SPDX | Flags W/K/B/SA/N | Stufe voll | Beleg | Funde |
|---|---|---|---|---|---|---|
| `http://dcat-ap.de/def/licenses/dl-by-de/2.0`, `https://www.govdata.de/dl-de/by-2-0`, `…/dl-by-de/2_0` [W] | Datenlizenz Deutschland – Namensnennung 2.0 | DL-DE-BY-2.0 | J/J/J/N/J | Processing | dcat-ap.de [S], spdx.org [S] | – |
| `http://dcat-ap.de/def/licenses/dl-zero-de/2.0`, `https://www.govdata.de/dl-de/zero-2-0` [W] | Datenlizenz Deutschland – Zero 2.0 | DL-DE-ZERO-2.0 [W] | J/J/J/N/N | Processing | dcat-ap.de [S] | – |
| `…/cc-by/4.0`, `https://creativecommons.org/licenses/by/4.0/`, CC-BY-Freitexte | CC BY 4.0 | CC-BY-4.0 | J/J/J/N/J | Processing | [W] | – |
| `…/cc-zero`, `https://creativecommons.org/publicdomain/zero/1.0/` | CC0 1.0 | CC0-1.0 | J/J/J/N/N | Processing | [W] | – |
| `…/cc-by-nc-de/3.0` | CC BY-NC 3.0 DE | CC-BY-NC-3.0-DE [W] | J/N/J/N/J | Processing nur Gratis-Tier | Suchtreffer widersprüchlich [S] | – |
| `…/cc-by-sa` (Version offen) | CC BY-SA | je Version | J/J/J/J/J | Processing, Share-Alike | [W] | – |
| `odbl`, `…/odc-odbl` [W] | ODbL 1.0 | ODbL-1.0 | J/J/J/J/J | Processing, Share-Alike | [W] | – |
| `…/ccpdm/1.0` | CC Public Domain Mark (keine Lizenz) | – | J/J/J/N/N | Processing | [S] | – |
| `…/geonutz/20130319` (auch `geoNutz/…`) | GeoNutzV (Geodaten des Bundes) | – | J/J/J/N/J | Processing | dcat-ap.de [S] | – |
| `…/officialWork` | Amtliches Werk nach § 5 Abs. 1 UrhG | – | J/J/J/N/N | Processing | [S]; oft zu weit verwendet (Abs. 2: Änderungsverbot, Quelle) | – |
| `…/other-closed` | Sammelkategorie „geschlossen“ | – | N/N/N/N/(N) | Katalogeintrag | dcat-ap.de, ckanext-dcatde [S] | – |
| `…/other-open` | Sammelkategorie „offen“, Bedingungen unbekannt | – | (N)/(N)/(N)/(N)/(N) | Katalogeintrag | nur in Liste 1.0 [S] | – |
| `other-opensource` | Sammelkategorie „Open Source“ | – | (N)/(N)/(N)/(N)/(N) | Katalogeintrag | [W] | – |
| opendata.swiss `terms_open` | Freie Nutzung | – | J/J/J?/N/N | Processing | dcat-ap.ch [S] | – |
| opendata.swiss `terms_by` | Freie Nutzung, Quelle angeben | – | J/J/J?/N/J | Processing | dcat-ap.ch [S] | – |
| opendata.swiss `terms_ask` | Kommerziell nur mit Erlaubnis | – | J/N/J?/N/N | Processing nur Gratis-Tier | dcat-ap.ch [S] | – |
| opendata.swiss `terms_by_ask` | Quelle angeben, kommerziell nur mit Erlaubnis | – | J/N/J?/N/J | Processing nur Gratis-Tier | dcat-ap.ch [S] | – |
| FSDI: Adresse des Links `rel=license` (seit 20.11. statt „proprietary“) | vermutlich swisstopo-OGD-Bedingungen („© swisstopo“) [S] | – | J/J/J/N/J | Processing | swisstopo [S]; an echter Collection prüfen | – |

**Hinweise von `license-checker` zur Entscheidung (Vorschläge):**
1. Die Sammelkategorien `other-open` und `other-opensource` wie `other-closed` behandeln (alle Flags N), weil sie keine Bedingungen nennen.
2. `officialWork` und `geonutz/20130319` werden von Herausgebern oft zu weit verwendet (GeoNutzV gilt nur für Bundesgeodaten). Freigabe je Herausgeber in `grants/` deshalb bewusst eng.
3. Share-Alike (`cc-by-sa`, `odbl`) ist für gelistete Einträge ohne Folge, für spätere volle Einträge (Kacheln, Jobs) aber zu beachten.
4. FSDI: Je Link-Ziel einstufen, nicht pauschal; nicht jede Collection hat OGD-Bedingungen.

**Für einen vollständigen Beleg** müsste die Sitzung diese Hosts erreichen: dcat-ap.de, opendata.swiss, dcat-ap.ch, swisstopo.admin.ch, data.geo.admin.ch, gesetze-im-internet.de, creativecommons.org, opendatacommons.org, govdata.de. Alternativ prüft Otto die verlinkten Texte selbst.
