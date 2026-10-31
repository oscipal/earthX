# ADR 0027 — Quellen mit kostenlosem Konto

- **Status:** Entwurf, offen (Fragen F1–F8 in §9).
  - Nummer 0027 fest laut `docs/plans/m5/m5-discovery-und-suche.md` §5a.
- **Datum:** 2026-10-31
- **Aufgabe:** M5-05 laut `docs/plans/m5/m5-discovery-und-suche.md` §5a (Entscheidungsvorlage E, §4).
- **Autonomiestufe:** C. Kein Produktivcode. Es gibt keine Änderung an `backend/`, `frontend/`, `scripts/`, Fixtures, `.importlinter`, `.github/`, `.claude/` oder `CLAUDE.md`. An den Quellen gemessen wurde nichts; gemessen ist nur ein Detail am GDAL der Lock-Datei (Abschnitt „Methode“).
- **Vorab fest:**
  - Quellen, die ein kostenloses Konto verlangen, zählen vorerst **nicht** als „ohne Schlüssel“; Ziel ist, sie später zu ermöglichen (Otto, 31.10.2026; M5-Plan §2 Punkt 6, §5 Antwort 4).
  - Ein anonymes Token, das die Quelle ohne Anmeldung ausgibt, gilt als „ohne Schlüssel“ (M5-Plan §2 Punkt 3), unter den Bedingungen (a)–(d) von `adr/0018` F4 und erst nach Ottos Messung (`adr/0018` §11 C, §12).
  - Die fertige Plattform enthält nichts, was einen Token braucht; Token-Logik wird nicht übernommen und nicht generalisiert (`ENTSCHEIDUNGEN` §1, §3). Token-Logik ist nicht Teil von `gateway` (`KLAERUNGEN` B8). **Die Wege W1, W2b, W3 und W4 verlangen eine Änderung dieser Regeln durch Otto; ob W2a eine braucht, ist F3.**
  - Rohdaten: kein Byte durch das eigene Backend (`architekturplan.md` 6.4).
  - Worker-Kern ohne Plattformdienste (`KLAERUNGEN` B9).
  - Keine Secrets im Repo, in Logs, Issues oder PRs (`ENTSCHEIDUNGEN` §4).
  - Konten und AOIs sind personenbezogen; Betrieb in der EU (`adr/0022` F7).
  - Quellen mit unklarer Rechtslage regelt `adr/0024` (M5-02), nicht dieses ADR.
- **Grundlage:**
  - `ENTSCHEIDUNGEN_2026-09-18.md` §1, §3, §4.
  - `KLAERUNGEN.md` B8, B9, B11, B12.
  - `projektuebersicht.md` §2 (Prinzipien 2, 10, 15), §4 (Sicherheit, Datenschutz), §5 (Checkliste Punkt 6), §6 (Auth und Konten), §16.
  - `architekturplan.md` 3.1, 6.1 (letzter Absatz: „Token pro Connector“), 6.4, 7.7, 9, 10, 11.
  - `projektplan.md` 1.1, M6 und M7 (Zeile „später“: Token pro Connector).
  - `adr/0003` §11 (Quad-Pol nur mit Registrierung), `adr/0016` §6.2, `adr/0018` §3.4, §5, §9, §12, `adr/0022` §4.2, §7, F4.
- **Betroffen (erst mit einer Entscheidung):** `ENTSCHEIDUNGEN` §1/§3 (Nachtrag durch Otto), `KLAERUNGEN` B8, Prinzip 2, Checkliste Punkt 6, Registry (`AccessInfo`), `identity`, `gateway`, `runner`, Frontend (Download der Originale).

---

## Methode und Belegstufen

Belegstufen wie in `adr/0018` und `adr/0022`:

- **M:** in dieser Sitzung gemessen; Verfahren im Text.
- **P:** am Primärdokument selbst gelesen (im Repo mit Pfad).
- **P\*:** Primärdokument über das Abrufwerkzeug eines Hilfsagenten gelesen. Das Werkzeug fasst Seiten zusammen; Zitate sind sinngemäß und vor einer Annahme an der Quelle zu prüfen.
- **S:** Suchtreffer oder Zusammenfassung, Wortlaut nicht geprüft.
- **P-Dritt:** Quelltext oder PR-Text eines Dritten selbst gelesen; belegt, aber nicht die Spezifikation des Anbieters.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Was in dieser Sitzung nicht ging [M]:** Der Proxy der Sitzung lehnt die Verbindung zu allen geprüften Konto-Quellen ab: `identity.dataspace.copernicus.eu`, `catalogue.dataspace.copernicus.eu`, `zipper.dataspace.copernicus.eu`, `download.dataspace.copernicus.eu`, `urs.earthdata.nasa.gov`, `cmr.earthdata.nasa.gov`, `data.lpdaac.earthdatacloud.nasa.gov`, `cds.climate.copernicus.eu` (je `connect_rejected`). Damit sind weder die OIDC-Konfiguration der Identitätsdienste (Grant-Arten, PKCE) noch CORS an den Download-Endpunkten messbar. Beides steht als Messpunkt in §10.

**Gemessen [M]:** Das GDAL der Lock-Datei (3.12.2, Wheel von rasterio) kennt die Konfigurationsoptionen `GDAL_HTTP_AUTH`, `GDAL_HTTP_BEARER`, `GDAL_HTTP_HEADERS`, `GDAL_HTTP_HEADER_FILE`, `GDAL_HTTP_NETRC`, `GDAL_HTTP_NETRC_FILE` und `GDAL_HTTP_COOKIE*` (Zeichenketten der Bibliothek, nicht ausgeführt). Ein Zugangsnachweis kann GDAL damit als Konfiguration erreichen statt im Pfad; ob er dann in Fehlertexten oder im Debug-Log erscheint, ist **nicht** gemessen.

**Anfragen an Datenquellen:** keine. Hilfsagenten lasen öffentliche Doku- und Bedingungsseiten. Es gibt kein Konto, keinen Schlüssel und keine Anmeldung in dieser Sitzung.

---

## 0. Kurzfassung

1. **Konten sperren meist den Zugang, nicht die Daten.** Copernicus- und NASA-Daten sind offen lizenziert; das Konto regelt nur, wer laden darf und mit welchem Kontingent [P\*][S]. Die Bedingungen der Zugänge regeln Drittanwendungen und Handeln im Auftrag von Nutzern nirgends ausdrücklich [P\*][S].
2. **Für einen Teil der Bestände gibt es einen anonymen Spiegel** (Sentinel-1/-2, DEM, ERA5 als ARCO-ERA5, PALSAR-Mosaike); Konten braucht es nur für den Rest (CLMS, HLS, OPERA, NISAR, CMEMS, EUMETSAT, CDS außer ERA5) (§3.7).
3. **Sechs Wege** nach dem Ort des Nachweises (§4): W0 Katalogeintrag mit Link; W1 Betreiberkonto; W2a Sitzung des Nutzers bei der Quelle, Download per Navigation; W2b Anmeldung über die Plattform im Browser; W3 Nachweis des Nutzers auf der Plattform („Token pro Connector“); W4 Nachweis des Nutzers im lokalen Runner; dazu W5 (Ottos Konto im Prototyp) für `adr/0024`.
4. **Was dagegen spricht:**
   - **W1:** CDSE teilt 4 Verbindungen und 50 000 COG-Anfragen im Monat auf alle Nutzer, verbietet Mehrfachkonten und verweist öffentliche Anwendungen auf eine eigene Anmeldung [P\*]. Earthdata gibt Anwendungen nur nach Freigabe durch ESDIS frei [S].
   - **W2b:** Keine geprüfte Quelle bietet heute Anmeldung fremder Web-Anwendungen mit PKCE und CORS (CDSE nur Passwort-Grant und Client Credentials [P\*]; Earthdata-Datenhosts ohne CORS nach einem Drittbefund [P-Dritt]).
   - **W3:** fremde Zugangsdaten bei der Plattform, Cache je Nutzer, Login (M6), eine Importgrenze oder Nachweise in der Queue; großer Aufwand.
5. **Empfehlung (§7, Option 1):** gestuft und ohne Secrets der Plattform.
   - **M5:** W0 mit Registry-Feld `access.account`; anonyme Spiegel zuerst.
   - **Danach:** W2a (Earthdata, nach Ottos Messung) und W4 (Runner mit Nachweis des Nutzers).
   - **W3** als eigener ADR nach M6.
   - **W1** nur mit schriftlicher Zusage der Quelle.
6. **Gemessen** ist hier nichts an den Quellen: Der Proxy sperrt alle Konto-Hosts. Die Messpunkte (OIDC-Konfiguration, CORS, Cookie-Weg) stehen in §10 für Otto.

---

## 1. Kontext und Frage

> Ich will eigentlich nur frei verfügbare quellen haben die ohne key funktionieren und rechtlich abgesichert sind. […] und wegen anonymen api keys haben wir eh schon mal gesprochen. (Otto, 31.10.2026, M5-Plan §2)

Otto hat dazu festgelegt (M5-Plan §5 Antwort 4): Anonyme Tokens zählen als „ohne Schlüssel“, kostenlose Konten nicht, mit dem Ziel, Konten später zu ermöglichen.

**Warum das zählt [A]:** Ein Teil der wichtigsten offenen Bestände ist nur mit kostenlosem Konto zu laden, obwohl die Daten selbst offen lizenziert sind:

- Copernicus über CDSE: Download und S3 nur mit Konto; dazu die CLMS-Produkte und Sentinel-2 aus einem EU-Archiv (`adr/0018` §3.4, `adr/0022` §4.2).
- NASA Earthdata (ASF, LP DAAC u. a.): Sentinel-1 und OPERA RTC über ASF, HLS (Landsat und Sentinel-2 harmonisiert), NISAR (`adr/0003` §11, `adr/0018` §3.4).
- Quad-Pol-SAR für den ruhenden Operator `decomp.py`: ALOS/ALOS-2 PALSAR und NISAR gibt es nur mit Registrierung (`adr/0003` §11).
- Meteorologie und Klima der Copernicus-Dienste (ERA5 im Climate Data Store, Copernicus Marine, EUMETSAT) verlangen ein Konto bzw. einen Schlüssel (§3).

**Frage dieses ADR:** Auf welchem Weg und unter welchen Bedingungen können solche Quellen in EarthX vorkommen — als Katalogeintrag, zur Anzeige, im Processing, beim Download der Originale —, ohne die Regeln zu Secrets, `gateway`, Worker-Kern und Datenschutz zu brechen, und was müsste Otto dafür ändern?

---

## 2. Kriterien

| # | Kriterium | Woher |
|---|---|---|
| K1 | Bedingungen der Quelle: Nutzung durch eine Plattform, Weitergabe von Zugangsdaten, Handeln im Auftrag von Nutzern, Weitergabe gelesener Daten | M5-Plan §2 Punkt 4; Prinzip 12 |
| K2 | Kontingente der Quelle und wer sie trägt (je Konto, je Plattform) | M5-Plan §5a (CDSE); `adr/0022` §4.2 |
| K3 | Keine Secrets in Repo, CI, Cloud-Sitzungen, Logs; Secrets im Betrieb nur mit Otto | `ENTSCHEIDUNGEN` §4; Projektplan 1.1 |
| K4 | Regeln: `ENTSCHEIDUNGEN` §1/§3, B8, B9, `architekturplan.md` 6.4, Importgrenzen | `CLAUDE.md` „Unverrückbar“ |
| K5 | Datenschutz: Konten, AOIs und fremde Zugangsdaten der Nutzer (DSGVO, revDSG) | `projektuebersicht.md` §4; `architekturplan.md` 10 |
| K6 | Was der Weg freischaltet: Katalog, Anzeige, Processing, Originale | B11; NM4-33 |
| K7 | Cache und Teilen: Ergebnisse, die mit einem Konto gelesen sind, dürfen nur dorthin, wo die Bedingungen es erlauben | `adr/0014` §3.1; `adr/0016` (Q11) |
| K8 | Ausfall: was passiert, wenn die Quelle ein Konto sperrt | Prinzip 11; `adr/0022` §7.3 |
| K9 | Aufwand für 1 bis 3 Personen und Zeitpunkt (Login erst M6) | `architekturplan.md` 1.1; Projektplan M6 |
| K10 | Nutzererlebnis: ein Klick ohne Zusatzschritte, wo möglich | `adr/0018` §9.3 (N1) |

---

## 3. Befunde je Quelle

### 3.1 Copernicus Data Space Ecosystem (CDSE)

Gelesen aus den Bedingungen und dem Quelltext der Doku (`eu-cdse/documentation`, Branch `publish`) [P\*]. Ergänzt `adr/0022` §4.2.

**Bedingungen [P\*]:**

- §4: Wer Daten lädt, registriert sich als Nutzer.
- Drittanwendungen und Handeln im Auftrag von Nutzern regeln die Bedingungen **nicht**. Das ist keine Erlaubnis [A].
- Weitergabe von Zugangsdaten ist nur für das Forum geregelt (§10: kein fremdes Konto ohne Erlaubnis); für Portal und APIs offen.
- §9: keine Mehrfachkonten, um Limits zu umgehen; Folge: sofortige Einstellung oder Begrenzung.
- §7: ESA kann die Bereitstellung prüfen, ändern, aussetzen oder beenden. §8: keine Ansprüche gegen ESA und T-Systems außer bei Vorsatz und grober Fahrlässigkeit.
- FAQ: „commercial services can be built on top, similar to the Copernicus Open Licence“; Quelle nennen.
- FAQ zu öffentlichen Anwendungen: „This is not facilitated by us at the moment; you will have to implement your own authentication service.“

**Anmeldung [P\*]:**

- Dokumentiert ist nur der Passwort-Grant mit dem öffentlichen Client `cdse-public` („Please do not hardcode the username and password in the application code“). Authorization Code und PKCE für fremde Anwendungen sind nicht dokumentiert; ein Forum-Beitrag sagt sinngemäß dasselbe [S].
- Access-Token 10 min, Refresh-Token 60 min, 100 aktive Sitzungen je Konto.
- **Nutzer kann eigene, begrenzte Nachweise erzeugen:**
  - S3-Schlüssel, an sein Konto gebunden, mit gewähltem Ablaufdatum, Secret nur einmal sichtbar; temporäre Schlüssel über eine API.
  - Sentinel-Hub-OAuth-Client (Client Credentials) im Dashboard, mit Ablaufdatum oder „Never expire“; für Single-Page-Apps mit Origin-Beschränkung, wobei das Secret im Frontend liegt.
- CORS an Download-Endpunkten (OData `$value`, `zipper`/`download`, S3 `eodata`): in der Doku nicht erwähnt, **offen** [P\*]; hier nicht messbar [M].

**Kontingente je Konto [P\*]:** wie `adr/0022` §4.2 (4 Verbindungen, 20 MB/s, 12 TB je 30 Tage, 50 000 direkte COG-Anfragen im Monat, S3 2000 Anfragen/min; danach 1 MB/s und eine Verbindung). Sentinel Hub: 10 000 Anfragen und 10 000 Processing Units im Monat, je 300 pro Minute.

**Programme [P\*]:** Höhere Kontingente für EU-Behörden, öffentliche Stellen und Betreiber von Copernicus-Diensten (Formular „Change your Copernicus user type“); kommerziell über CREODIAS; Credits für „value creators“ (kommerzielle Dienste, Start-ups). Ob ein Open-Source-Betreiber darunter fällt, ist offen.

**Datenschutz [P\*]:** ESA ist Verantwortlicher, T-Systems Auftragsverarbeiter; laut Bedingungen §5 werden IP-Adressen und heruntergeladene Daten gespeichert (Server in der EU); Sentinel Hub protokolliert Konto, IP und User-Agent je Anfrage. Eine andere Seite nennt ESA und T-Systems als gemeinsame Verantwortliche [S].

**Folge für die Wege [A]:**

- **W1:** Ein Konto für alle Nutzer teilt 4 Verbindungen und 50 000 COG-Anfragen im Monat; mehrere Konten verbietet §9; die FAQ verweist öffentliche Anwendungen auf eine eigene Anmeldung. Tragbar nur mit schriftlicher Zusage von CDSE oder einem höheren Kontingent über die Programme.
- **W2a, W2b:** Ohne Authorization Code/PKCE gibt es keinen Weg, den Nutzer bei CDSE anzumelden, ohne sein Passwort in die Seite zu holen. Eine Navigation zur Datei trägt kein Token. **Heute nicht möglich.**
- **W3:** Nur mit einem vom Nutzer selbst erzeugten, befristeten S3-Schlüssel oder Sentinel-Hub-Client, nie mit Passwort. Der Refresh-Token (60 min) taugt nicht zum Hinterlegen.
- **W4:** S3-Schlüssel des Nutzers als Umgebungsvariable oder Datei im Runner; das Kontingent trägt der Nutzer. Lesen über S3 heißt `s3://`-Adressen bzw. `/vsis3/` mit Endpunkt `eodata.dataspace.copernicus.eu`; das kann `gateway` heute nicht (nur `https`) [A].

### 3.2 Copernicus-Dienste von ECMWF, Marine, EUMETSAT

**Climate und Atmosphere Data Store (CDS, ADS) [P\*], [S]:**

- Konto mit persönlichem Token in `~/.cdsapirc`; „agree to the Terms and Conditions of every dataset“ [P\*]. Die Annahme ist ein Klick des Kontoinhabers je Datensatz [A]; ein Betreiberkonto nähme sie für alle Nutzer an.
- Seit 02.07.2025 soll CC BY die „Licence to use Copernicus Products“ ersetzen [S]; ob die Annahme je Datensatz bleibt, ist offen.
- Anfragen laufen über eine Warteschlange (Auftrag, Warten, Download); das ist kein Kachelzugriff [A]. Limits und Regeln zur Weitergabe des Tokens: offen.
- **ERA5 ohne Konto:** ARCO-ERA5 von Google (`gcp-public-data-arco-era5`, anonym, Zarr, us-central1, 1979 bis heute) [P\*]; Datenlizenz und Requester Pays dort offen. AWS `era5-pds` ist „deprecated“ [P\*]. ECMWF Open Data (Vorhersagen, kein ERA5) unter CC BY 4.0 [P\*].

**Copernicus Marine (CMEMS) [P\*], [S]:** Anmeldung mit Benutzername und Passwort (Toolbox), kein eigener Schlüssel; „no quotas, neither on volume size nor bandwidth“ [P\*]. Lizenz und Drittnutzung offen. Für W3 hieße das ein Passwort hinterlegen; scheidet nach §4.4 aus [A].

**EUMETSAT Data Store [S]:** Konto mit Consumer-Key/Secret, daraus befristete Token. Sentinel-Daten unter Copernicus-Bedingungen; für eigene Produkte (z. B. Meteosat) verbieten Beispiellizenzen die Weitergabe der Originale an Dritte. Lizenz je Produkt, offen.

### 3.3 NASA Earthdata Login (EDL)

Alle Anbieterseiten waren für die Hilfsagenten gesperrt; die Befunde sind **S**, wo nicht anders markiert.

**Bedingungen [S]:**

- Eine Klausel, die die Weitergabe von Zugangsdaten oder ein Konto für viele Endnutzer regelt, war nicht zu finden; das ist **offen**.
- Die Guidance von ESDIS sagt sinngemäß: Anwendungen, die Daten abrufen (Mensch oder Maschine), sollen EDL nutzen; neue Anwendungen gibt ESDIS vor der Nutzung frei (Verfahren „TBD“).
- EDL dient laut Policy der Erfassung von Nutzungsmetriken je Person. Ein Betreiberkonto für alle Nutzer liefe dem entgegen [A].
- Forum-Antworten von Moderatoren zu „Service-Konten“ widersprechen sich; keine offizielle Regel.

**Anmeldung für fremde Anwendungen [S]:**

- EDL ist OAuth-2-Anbieter mit Authorization-Code-Flow; Redirect-URIs werden vorab registriert und exakt verglichen; der Nutzer autorisiert die Anwendung beim ersten Zugriff, die Anwendung sieht dann sein Profil.
- **Offen:** PKCE; ob ein Token aus dem App-Flow Daten der DAACs lesen darf oder nur das Profil liefert; Kriterien der Freigabe durch ESDIS.

**Nutzer-Token [S], [P-Dritt]:**

- 60 Tage gültig (ältere Seiten: 90), höchstens zwei gültige Token je Nutzer, Widerruf in der Oberfläche oder per API.
- Ein Token per API zu erzeugen, braucht Benutzername und Passwort (Basic-Auth). `earthaccess` setzt `Authorization: Bearer` und kennt die Umgebungsvariable `EARTHDATA_TOKEN` [P-Dritt].
- Folge [A]: Für W3 und W4 müsste der Nutzer das Token selbst in der EDL-Oberfläche erzeugen und einfügen; das Passwort braucht die Plattform dafür nicht.

**Datenzugriff:**

- Datenhost leitet zur Anmeldung an `urs.earthdata.nasa.gov` und zurück; `earthaccess` setzt die Anmeldung bei dieser Weiterleitung erneut [P-Dritt].
- S3-Direktzugriff nur innerhalb von AWS `us-west-2`, Schlüssel vom Endpunkt `/s3credentials` des DAAC, 1 h gültig [S]. Für einen Rechenort in Frankfurt (`adr/0022`) ohne Belang.
- **CORS [P-Dritt]:** Ein PR eines anderen Projekts (10.10.2026) berichtet, dass die Datenhosts von NSIDC, LP DAAC und ORNL DAAC einen CORS-Preflight mit `405` beantworten und die CloudFront-Adresse nach der Weiterleitung keine CORS-Kopfzeilen trägt; CMR sendet `Access-Control-Allow-Origin: *`. Nicht selbst geprüft; ob es für jeden Host gilt, ist offen.
- Ratenlimits: nicht gefunden.

**Lizenz [S]:** NASA-Daten ohne Einschränkung, mit Zitierwunsch; Daten NASA-geführter Missionen laut aktueller Seite CC0, sofern nicht anders gekennzeichnet. Produktlizenzen (HLS, OPERA, ASF-Sentinel-1) sind offen; Sentinel-1 bei ASF bleibt Copernicus-Lizenz [A]. Einstufung immer durch Otto.

**Datenschutz [S]:** EDL erhebt Name, E-Mail, Land, Organisation, Nutzertyp; jede autorisierte Anwendung sieht das Profil. Protokollierung einzelner Downloads und Drittlandtransfer (USA) sind offen.

**Folge für die Wege [A]:**

- **W2b mit `fetch` (ZIP über den Service Worker) geht nicht**, wenn der CORS-Befund stimmt.
- **W2a als Navigation geht ohne CORS:** Ein Klick auf die Datei-Adresse ist ein Download des Browsers. Ist der Nutzer im selben Browser bei EDL angemeldet, läuft die Weiterleitung mit seinem eigenen Cookie durch. Das ist der Weg „ohne CORS“ von NM4-33 (Einzeldateien), ohne OAuth-Registrierung der Plattform und ohne Token in der Seite. Messpunkt §10.
- W4 mit Nutzer-Token in `.netrc` oder als Bearer passt zu `earthaccess`-Praxis.

### 3.4 USGS [S], [P\*]

- ERS-Konto für EarthExplorer; die M2M-API braucht zusätzlich einen Antrag (Prüfung 24–48 Geschäftsstunden). Seit 26.02.2025 meldet sich M2M mit einem Application Token statt Passwort an [S]. Laufzeit, Limits und Bedingungen sind offen.
- **Landsat ohne Konto:** AWS `usgs-landsat` ist Requester Pays (braucht ein AWS-Konto und zahlt den Transfer) [P\*]; „There are no restrictions on Landsat data downloaded from the USGS“ [P\*, sinngemäß]. Planetary Computer `landsat-c2-l2` mit anonymem SAS-Token, Limits ohne Schlüssel enger [P-Dritt]. Ein Landsat-Datensatz ist damit eher eine Frage von `adr/0018` F4 (anonymes Token) als von Konten [A].

### 3.5 JAXA [S], [P\*]

- G-Portal verlangt laut EULA eine Registrierung (Name, E-Mail, Zugehörigkeit, Land, Zweck); die Seite „G-Portal Repo“ sagt das Gegenteil. Widerspruch offen [S].
- ALOS-2 ScanSAR „Open & Free“ für registrierte Nutzer; Standardprodukte (darunter Quad-Pol) nur mit Forschungsvertrag (RA) [S]. **Für `decomp.py` heißt das [A]:** Auch ein kostenloses Konto brächte Quad-Pol von ALOS-2 nicht ohne Weiteres; die Spur bleiben NISAR über ASF (Earthdata) und ALOS-1 PALSAR L1.1 über ASF (`adr/0003` §11).
- Nutzung kostenlos mit Namensnennung („© JAXA“), Daten bleiben Eigentum von JAXA [S]. Die JAXA Earth API (COG und STAC) hat eine eigene Lizenzseite; ob sie ein Konto braucht, ist offen [S].
- Die PALSAR-Mosaike liegen als Kopie von DE Africa anonym in AWS `af-south-1` [P\*]; ob JAXAs Bedingungen eine Weitergabe durch EarthX erlauben, ist offen.

### 3.6 Weitere Fälle [S]

- **OpenTopography:** globale DEMs nur mit API-Key; Limits je 24 h widersprüchlich; Integration in kommerzielle Software verlangt einen Enterprise-Key. Copernicus DEM gibt es anonym über AWS (`cop-dem-glo-30` ist schon in der Registry); kein Bedarf [A].
- **Google Earth Engine:** nicht-kommerzielle Nutzung mit Registrierung, Betrieb für Dritte kaum vereinbar; kein Kandidat [A].

### 3.7 Anonyme Spiegel — der Weg ohne Konto

Für mehrere Bestände, die beim Herausgeber ein Konto verlangen, gibt es eine Kopie ohne Konto. Die Lizenz der Daten gilt dort weiter; die Bedingungen des Spiegels kommen dazu.

| Bestand | Herausgeber (mit Konto) | Spiegel ohne Konto | Beleg | Haken |
|---|---|---|---|---|
| Sentinel-1 GRD | CDSE, ASF | Earth Search `sentinel-1-grd`, AWS Frankfurt | P (`adr/0018` §3.1) | schon DS-04 |
| Sentinel-2 L2A | CDSE | Earth Search (Oregon), EOPF (Wien) | P (`adr/0017`, `adr/0022`) | schon in der Registry |
| Copernicus DEM | CDSE, OpenTopography (Key) | AWS `copernicus-dem` | P (Registry) | schon in der Registry |
| ERA5 | CDS | ARCO-ERA5 (Google, Zarr, us-central1) | P\* | Datenlizenz dort und Requester Pays offen; Region USA |
| Landsat C2 | USGS ERS | Planetary Computer (anonymes SAS-Token) | P-Dritt | fällt unter `adr/0018` F4, nicht unter Konten |
| PALSAR-Mosaike | JAXA | DE Africa in AWS `af-south-1` | P\* | Weitergabe durch Dritte offen; Region Afrika |

**Folge [A]:** Vor jedem Weg aus §4 prüft die Auswahl in `adr/0023` (M5-01), ob es einen Spiegel ohne Konto gibt. Konten werden erst für Bestände ohne Spiegel nötig: CLMS über CDSE, HLS, OPERA, NISAR und ALOS-1 PALSAR über Earthdata, CMEMS, EUMETSAT-Produkte, CDS außer ERA5.

---

## 4. Wege

Sechs Wege, nach dem Ort, an dem der Zugangsnachweis liegt. „Nachweis“ heißt hier alles, was die Quelle für einen Download verlangt: Passwort, Access-/Refresh-Token, API-Key, S3-Schlüssel, Cookie.

| Weg | Wessen Konto | Wo der Nachweis liegt | Was er freischaltet |
|---|---|---|---|
| **W0** | keines | nirgends | Katalogeintrag mit Link zur Quelle (B11 Stufe „Katalogeintrag“) |
| **W1** | Betreiber | Secret im Betrieb (Backend, Worker) | Anzeige, Processing, ggf. Originale |
| **W2a/W2b** | Nutzer | nur im Browser des Nutzers | Originale direkt von der Quelle (NM4-33); später Anzeige im Browser |
| **W3** | Nutzer | auf der Plattform hinterlegt („Token pro Connector“) | Anzeige, Processing, Originale für diesen Nutzer |
| **W4** | Nutzer | nur auf dem Rechner des Nutzers (lokaler Runner) | Processing lokal |
| **W5** | Otto | nur auf Ottos Rechner | Erprobung im Prototyp; gehört zu `adr/0024` |

### 4.1 W0 — Katalogeintrag mit Link

- Metadaten anonym über die Discovery (z. B. CDSE-STAC, NASA CMR), Beschreibung, Lizenz, Zitierangabe, Coverage aus Footprints, ein Link „bei der Quelle laden (kostenloses Konto nötig)“.
- Kein Nachweis; am Lesen der Daten ändert sich nichts. B11 kennt die Stufe schon; `adr/0022` §7.5 sieht sie für CLMS über CDSE vor.
- Offen ist nur, ob Prinzip 2 („werden nicht angebunden“) einen solchen Eintrag erlaubt. Der Satz meint nach seinem Zusammenhang das Lesen der Daten [A]; F2 lässt Otto das bestätigen.
- Registry: `AccessInfo` bekommt eine Angabe zur Zugangsart (§6.1), damit Oberfläche, Checkliste und Discovery die Einträge auseinanderhalten.

### 4.2 W1 — Betreiberkonto mit Secret im Betrieb

- Ein Konto der Plattform je Quelle; der Nachweis liegt als Secret in der Laufzeitumgebung (nie im Repo, nie in CI), `gateway` holt und erneuert das Token und reicht es an GDAL als Konfiguration.
- **Kontingent:** gilt für alle Nutzer zusammen. Bei CDSE sind das 4 Verbindungen und 50 000 COG-Anfragen im Monat, also rund 1 500 kalte Kacheln (`adr/0022` §4.2) [P\*][A]. Das trägt keinen Mehrnutzerbetrieb.
- **Bedingungen:** siehe §3 je Quelle. Wo die Quelle öffentliche Anwendungen auf eine eigene Anmeldung verweist (CDSE-FAQ, `adr/0022` §4.2) oder Weitergabe verbietet, ist W1 ohne schriftliche Zustimmung der Quelle nicht tragbar [A].
- **Regeln:** widerspricht `ENTSCHEIDUNGEN` §1 (Plattform braucht einen Token) und §3, B8 (Token-Logik in `gateway`), Prinzip 2; Secrets im Betrieb sind „nie ohne Otto“ (Projektplan 1.1).
- **Ausfall:** Sperrt die Quelle das Konto, fallen alle ihre Datensätze für alle Nutzer aus (`adr/0022` §7.3).
- **Vorteil:** Für den Nutzer am einfachsten; Cache und Kacheln wie bei anonymen Quellen.

### 4.3 W2 — Konto des Nutzers, nur im Browser

Vorbild ist die Antwort auf N1 in `adr/0018` §9.3: Der Browser holt sich den Nachweis selbst bei der Quelle, die Plattform sieht ihn nie.

Zwei Spielarten [A]:

- **W2a — Sitzung des Nutzers bei der Quelle, Navigation.** Der Nutzer ist im selben Browser bei der Quelle angemeldet (eigenes Cookie). „Download full scene(s)“ nimmt für diesen Datensatz den Weg ohne CORS aus NM4-33: jede Datei ein Download des Browsers über ihre Adresse. Die Quelle leitet zur Anmeldung und zurück; die Seite der Plattform sieht kein Token. Kein OAuth-Client der Plattform, kein Backend.
  - Geht nur, wenn die Quelle den Download per Cookie-Sitzung erlaubt. Bei Earthdata ist das der übliche Weg im Browser [A, Messpunkt §10]; bei CDSE braucht der Download ein Token in der Kopfzeile, W2a geht dort nicht (§3.1).
  - Ist der Nutzer nicht angemeldet, landet er auf der Anmeldeseite der Quelle; danach muss er den Download neu starten [A].
- **W2b — Anmeldung über die Plattform (OAuth im Browser).** Der Nutzer meldet sich über einen OAuth-Client der Plattform an (Authorization Code mit PKCE, öffentlicher Client); das Access-Token liegt nur im Speicher der Seite und dient `fetch` bzw. dem Service Worker (ZIP).
  - Voraussetzungen: (1) die Quelle lässt fremde Web-Anwendungen als Client zu, ohne Client-Secret; (2) CORS an Token- und Download-Endpunkt; (3) der Download nimmt ein Bearer-Token.
  - Heute bei keiner geprüften Quelle belegt: CDSE dokumentiert keinen solchen Fluss, die Earthdata-Datenhosts haben nach einem Drittbefund kein CORS (§3.1, §3.3).
  - Die Plattform braucht eine Registrierung als Anwendung bei der Quelle (bei Earthdata mit Freigabe durch ESDIS), also ein Betreiberkonto für die Registrierung, aber keines zum Lesen.
- **Regeln:** W2a ist im Kern ein Link auf die Datei; die Plattform enthält dafür nichts, was einen Token braucht. Ob das `ENTSCHEIDUNGEN` §1 schon erfüllt oder einen Satz von Otto braucht, ist F3. W2b berührt §1 (Anmeldung im Frontend der Plattform). B8, B9 und 6.4 bleiben bei beiden unverändert [A].
- **Grenze:** Anzeige und Processing über die Plattform gehen so nicht, weil Tiler und Worker den Nachweis nicht haben. Erst eine Anzeige im Browser (Projektplan „später: Rendering im Browser“) nutzt W2 auch für Kacheln.
- **Datenschutz:** Die Plattform erfährt nichts Neues. Die Quelle sieht wie bei jedem Download Konto und IP des Nutzers, bei W2b dazu die Client-ID der Plattform [A].

### 4.4 W3 — Konto des Nutzers, auf der Plattform hinterlegt

Das ist „Token pro Connector“ (`projektuebersicht.md` §6, `architekturplan.md` 6.1). Nutzer hinterlegen einen Nachweis; Tiler, Zuschnitt und Jobs lesen damit **für diesen Nutzer**.

- **Voraussetzung:** Plattform-Login (M6), weil ein Nachweis einem Konto der Plattform gehören muss.
- **Was hinterlegt wird:** nach Möglichkeit ein widerrufbares, begrenztes Token aus einer OAuth-Zustimmung (Refresh-Token) oder ein eigens erzeugtes Nutzer-Token der Quelle, **nie ein Passwort** [A]. Quellen, die nur Passwort-Grant kennen, scheiden für W3 aus.
- **Speicher:** verschlüsselt (`projektuebersicht.md` §4), im Schema `identity` mit eigener DB-Rolle (`architekturplan.md` 10), Schlüssel außerhalb der Datenbank; Audit-Log; Löschen mit dem Konto und auf Wunsch sofort.
- **Fluss:** `api` löst den Nachweis für die Anfrage auf und gibt ihn an `access` bzw. an den Job; `gateway` setzt ihn als Kopfzeile bzw. GDAL-Konfiguration (Abschnitt „Methode“). Er steht nie im Rezept, in der Provenienz, im Permalink, im Cache-Schlüssel, in einer URL oder einem Log.
- **Worker-Kern (B9):** Ein Nachweis als Eingabe des Auftrags ist kein Plattformdienst; der Kern bleibt zustandslos, wenn er ihn im Speicher bekommt [A]. Wer ihn dem Job gibt, ist offen:
  - (i) die Hülle `jobs` holt ihn beim Start aus `identity`. Heute verbietet `.importlinter` den Import `jobs → identity` (Vertrag `jobs`); das wäre eine Lockerung der Importgrenzen, die nur Otto entscheidet.
  - (ii) `api` legt ihn bei der Annahme verschlüsselt und kurzlebig an den Auftrag; dann liegt er in der Queue, wenn auch verschlüsselt.
  - Beides gehört in einen eigenen ADR mit W3 (F6).
- **Cache:** Der Kachel- und Ergebnis-Cache ist heute gemeinsam. Daten, die mit dem Konto von A gelesen sind, dürfen B nur erreichen, wenn die **Bedingungen des Zugangs** das erlauben; die **Lizenz der Daten** (Copernicus, NASA) erlaubt Weitergabe meist ohnehin. Das ist eine Rechtsfrage je Quelle (§3). Bis zur Klärung: Cache je Nutzer für diese Datensätze, also kalte Kacheln für jeden [A].
- **Kontingent:** je Nutzer, skaliert damit mit den Nutzern; Fehler 429 der Quelle gehen als eigener Text an den Nutzer („Kontingent bei <Quelle> erschöpft“).
- **Regeln:** widerspricht `ENTSCHEIDUNGEN` §1/§3, B8, Prinzip 2; braucht Datenschutz-Folgenabschätzung, weil ein fremdes Konto des Nutzers bei uns liegt [A].
- **Aufwand:** groß (Identität, Verschlüsselung, Erneuerung, Widerruf, Cache-Trennung, Tests). Für 1 bis 3 Personen erst nach M6 sinnvoll.

### 4.5 W4 — Konto des Nutzers im lokalen Runner

- Der Runner läuft auf dem Rechner des Nutzers und liest von seiner IP (`architekturplan.md` 7.7, `adr/0016`). Den Nachweis gibt der Nutzer dem Container selbst, etwa als Datei `.netrc` oder Umgebungsvariable; GDAL liest `.netrc` über `GDAL_HTTP_NETRC_FILE` (Abschnitt „Methode“).
- Die Plattform sieht den Nachweis nie; das Rezept nennt nur unsignierte Adressen (wie bei `adr/0018` §5.3).
- **Grenzen:** nur Jobs, keine Kacheln; die Host-Prüfung des Runners (`adr/0016` §6.2, A1) muss Weiterleitungen auf den Anmeldedienst der Quelle kennen (z. B. Earthdata: Datenhost leitet auf `urs.earthdata.nasa.gov` und zurück, §3) [A].
- **Regeln:** berührt `ENTSCHEIDUNGEN` §3 („Token-Logik nicht übernehmen“) nur, wenn der Runner selbst ein Token holt; reicht der Nutzer einen fertigen Nachweis über `.netrc` herein, ist im Code nur die Weitergabe an GDAL [A].
- **Aufwand:** klein: ein Datei-Mount, eine GDAL-Option, ein Test, dass der Nachweis nicht in `provenance.json`, Ausgabe oder Fehlertexte gelangt.

### 4.6 W5 — Ottos eigenes Konto im Prototyp

Wie BIOMASS bis heute (`ENTSCHEIDUNGEN` §3): Otto nutzt ein eigenes Konto lokal, nie in CI, Cloud-Sitzungen oder Fixtures. Ob und wie das für Prototyp-Quellen gilt, entscheidet `adr/0024` (M5-02). Dieses ADR schlägt nur vor, dass W5 **dieselbe** Schnittstelle nutzt wie W4 (Nachweis als Datei, an GDAL als Konfiguration), damit kein zweiter Token-Pfad entsteht [A].

---

## 5. Vergleich

### 5.1 Wege nach Kriterien [A]

| | W0 | W1 | W2a | W2b | W3 | W4 |
|---|---|---|---|---|---|---|
| K1 Bedingungen | ✓ | ✗ CDSE (FAQ, §9); ? Earthdata | ✓ Nutzer handelt selbst | ? je Quelle | ? Handeln im Auftrag, nirgends geregelt | ✓ Nutzer handelt selbst |
| K2 Kontingent | — | ✗ eines für alle | ✓ je Nutzer | ✓ je Nutzer | ✓ je Nutzer | ✓ je Nutzer |
| K3 Secrets der Plattform | keine | Secret im Betrieb | keine | Client-ID (öffentlich) | fremde Nachweise, verschlüsselt | keine |
| K4 Regeln | Nachtrag Prinzip 2 | §1, §3, B8, Prinzip 2 | §1 (F3) | §1 | §1, §3, B8, B9-Nähe, Importgrenze | §1/§3 (Weitergabe an GDAL) |
| K5 Datenschutz | — | Betreiber haftet für alle Abrufe | Quelle sieht Nutzer | Quelle sieht Nutzer und Client | fremde Zugangsdaten bei uns, DSFA | — |
| K6 freigeschaltet | Katalog | alles | Originale | Originale; später Anzeige im Browser | Anzeige, Processing, Originale | Processing lokal |
| K7 Cache | — | gemeinsam | — | — | je Nutzer bis zur Klärung | lokal |
| K8 Sperre trifft | — | alle Nutzer | einen Nutzer | einen Nutzer | einen Nutzer | einen Nutzer |
| K9 Aufwand | klein | mittel | klein | mittel | groß, nach M6 | klein |
| K10 Erlebnis | Link | wie anonym | Anmeldung bei der Quelle, dann ein Klick | Anmeldung über die Plattform | einmal hinterlegen | Datei mit Nachweis lokal |

### 5.2 Wege nach Quellen [A]

| Quelle | W0 | W1 | W2a | W2b | W3 | W4 |
|---|---|---|---|---|---|---|
| CDSE | ✓ (STAC anonym) | ✗ ohne Zusage | ✗ Token in Kopfzeile | ✗ kein PKCE dokumentiert | ~ nur mit S3-Schlüssel oder SH-Client des Nutzers | ~ S3-Schlüssel, braucht `/vsis3/` in `gateway` |
| Earthdata | ✓ (CMR anonym, CORS) | ✗ ohne Zusage | ~ nach Messung | ✗ Datenhosts ohne CORS (Drittbefund) | ~ Nutzer-Token 60 Tage | ✓ Token oder `.netrc` |
| CDS/ADS | ✓ | ? Betreiber nähme Lizenzen für alle an | ✗ Warteschlange, kein Dateilink | ✗ | ~ Token des Nutzers | ✓ Token, aber Auftrag statt Datei |
| CMEMS | ✓ | ? | ? | ? | ✗ nur Passwort | ~ Passwort lokal beim Nutzer |
| EUMETSAT | ✓ | ? Weitergabe je Produkt verschieden | ? | ? | ~ Key/Secret des Nutzers | ✓ |

✓ geht · ~ geht mit Einschränkung · ✗ geht nicht · ? offen

---

## 6. Folgen quer durch

### 6.1 Registry

`AccessInfo` (`catalog/registry.py`) sagt heute nur, dass der anonyme Check bestanden ist (`token_free_checked_at`, `method`, `cors`). Vorschlag [A], eingeführt mit der YAML-Registry in M5 (B13):

| Feld | Werte | Wirkung |
|---|---|---|
| `access.account` | `none` · `anonymous_token` · `free_account` | `none` wie heute; `anonymous_token` nach `adr/0018` F4; `free_account` nur als Katalogeintrag (W0), bis Otto einen weiteren Weg freigibt |
| `access.account_provider` | z. B. `cdse`, `earthdata` | Name des Identitätsdienstes für Hinweis, Link und spätere Wege; keine Adresse eines Token-Endpunkts im Datensatz, die liegt (wenn je nötig) in der Konfiguration des Wegs |
| `access.account_paths` | Teilmenge von `W2a`, `W2b`, `W3`, `W4` | welche Wege für diesen Datensatz freigegeben sind; leer bis F3–F6 entschieden sind |

- Ein Startcheck verlangt: `free_account` ⇒ B11-Stufe höchstens „Katalogeintrag“, solange `account_paths` leer ist; `token_free_checked_at` bleibt bei `free_account` leer, und Checkliste Punkt 6 gilt als „nicht anwendbar, Katalogeintrag“.
- Discovery (M5-03) liest die Metadaten weiter anonym; findet sie eine Collection, deren Assets ohne Konto `401`/`403` antworten, setzt der Vorschlag `free_account` statt den Eintrag zu verwerfen.
- Oberfläche: Hinweis am Datensatz „Free account at <Quelle> required to download“ mit Link; kein Kartenlayer, kein Processing.

### 6.2 Regeltext

Wie bei `adr/0018` N2 gehen `ENTSCHEIDUNGEN` §1/§3 allen anderen vor. Wird ein Weg außer W0 freigegeben, braucht es einen Satz von Otto in `ENTSCHEIDUNGEN`, dazu Nachträge in B8, Prinzip 2 und Checkliste Punkt 6. Für W0 reicht ein Nachtrag zu Prinzip 2 („Katalogeintrag mit Link ist kein Anbinden“), weil sich am Lesen der Daten nichts ändert. Wortlaut entsteht erst nach der Antwort auf F1–F2.

### 6.3 Datenschutz

- **W0, W4, W5:** keine personenbezogenen Daten der Plattform berührt [A].
- **W2a, W2b:** Die Plattform verarbeitet nichts Neues; die Quelle erfährt Konto und IP des Nutzers, bei W2b dazu die Client-ID der Plattform. Ein Hinweis in der Datenschutzerklärung der Plattform genügt vermutlich [A, Rechtsfrage].
- **W1:** Die Quelle sieht alle Abrufe unter einem Konto; AOIs der Nutzer gehen als Bereichsanfragen unter dem Namen des Betreibers hinaus. Kein Personenbezug zur Quelle, aber der Betreiber haftet für alle [A].
- **W3:** Fremde Zugangsdaten der Nutzer liegen bei der Plattform. Das ist ein eigenes Schutzgut (Diebstahl öffnet das Konto des Nutzers bei der Quelle) und macht eine Datenschutz-Folgenabschätzung, Verschlüsselung mit Schlüssel außerhalb der Datenbank, Audit und eine Löschfrist nötig. Dazu die Rechtsfrage, ob die Plattform „im Namen“ des Nutzers handeln darf (§3) [A].

### 6.4 Sicherheit

- Jeder Nachweis ist ein Secret im Sinne von Projektplan 1.1; Tests laufen nur mit Fixtures, nie mit einem echten Konto (CLAUDE.md, `ENTSCHEIDUNGEN` §4).
- `gateway` loggt schon heute keine Query-Strings; ein Nachweis in Kopfzeile oder GDAL-Konfiguration braucht dieselbe Prüfung für Kopfzeilen und Fehlertexte (Test „kein Nachweis in Log, Fehlertext, Provenienz“) [A].
- Weiterleitungen: Earthdata-Hosts leiten zum Anmeldedienst und zurück (§3). `gateway` prüft jede Weiterleitung gegen die Allowlist; der Anmeldedienst müsste darin stehen und darf den Nachweis nicht an fremde Hosts weitergeben (Kopfzeile nur an den Host, für den sie gilt) [A].

---

## 7. Optionen

| Option | Inhalt | Regeländerung | Aufwand | Zeitpunkt |
|---|---|---|---|---|
| **1** gestuft, ohne Secrets der Plattform (empfohlen) | jetzt W0 mit Registry-Feld und anonyme Spiegel zuerst (§3.7); danach W2a (Earthdata, nach Messung) und W4 (Runner); W2b nur, wo eine Quelle PKCE und CORS bietet; W3 erst als eigener ADR nach M6; W1 nur mit schriftlicher Zusage der Quelle | W0: Nachtrag Prinzip 2; W2a: nach F3; W4: Satz in `ENTSCHEIDUNGEN` §3 | klein bis mittel | W0 mit M5; W2a und W4 nach M5 |
| **2** Betreiberkonto | W1 für CDSE und Earthdata | `ENTSCHEIDUNGEN` §1/§3, B8, Prinzip 2; Secret im Betrieb | mittel | nach schriftlicher Zusage der Quellen |
| **3** Token pro Connector früh | W3 als Ziel mit M6 | wie 2, dazu Importgrenze `jobs → identity` oder Nachweis in der Queue | groß | M6/M7 |
| **4** nichts | Konto-Quellen bleiben ganz draußen, auch als Katalogeintrag | keine | keiner | — |

**Empfehlung: Option 1.** Gründe [A]:

- W0 bringt die Quellen sofort in Suche und Coverage, ohne Nachweis und ohne Regelbruch.
- Für mehrere Konto-Bestände gibt es einen anonymen Spiegel (§3.7). Der ist immer der bessere Weg und gehört in die Rangliste von `adr/0023`.
- W2a und W4 lassen den Nachweis beim Nutzer; die Plattform hält kein Secret, kein fremdes Konto und keinen Cache unter fremdem Namen. B8, B9 und 6.4 bleiben unverändert.
- W1 scheitert bei CDSE am Kontingent je Konto, an §9 und an der Aussage der FAQ zu öffentlichen Anwendungen; bei Earthdata an der Freigabe durch ESDIS und dem Zweck „Metriken je Person“ (§3.3, nur S). Das ändert nur eine schriftliche Zusage der Quelle.
- W3 ist der einzige Weg zu Anzeige und Processing in der Cloud mit Nutzerkonten, aber er bringt das größte Risiko (fremde Zugangsdaten) und setzt Login, Verschlüsselung und Cache-Trennung voraus. Er gehört deshalb in einen eigenen ADR nach M6, mit dem Plattform-Login als Grundlage.

---

## 8. Was dieses ADR nicht entscheidet

- Welche Konto-Quellen zuerst kommen: das ist `adr/0023` (M5-01); dieses ADR liefert nur die Wege.
- Quellen mit unklarer Rechtslage und Ottos eigenes Konto im Prototyp (W5): `adr/0024` (M5-02).
- Lizenz-Einstufung eines Datensatzes: immer Otto.
- Identity-Provider, Login und Registrierungspflicht: M6.

---

## 9. Fragen an Otto

**F1 — Grundsatz?**
1. Gestuft ohne Secrets der Plattform (Option 1): W0 jetzt, W2a und W4 danach, W3 als eigener ADR nach M6, W1 nur mit schriftlicher Zusage **(Empfehlung)**
2. Betreiberkonto (Option 2), nach Anfrage bei CDSE und Earthdata
3. Token pro Connector als Ziel mit M6 (Option 3)
4. Konto-Quellen bleiben ganz draußen, auch als Katalogeintrag (Option 4)

**F2 — Katalogeintrag mit Link (W0) für Konto-Quellen in M5?**
1. Ja, mit `access.account = free_account`, Hinweis „Free account at <Quelle> required to download“, B11-Stufe höchstens „Katalogeintrag“, Startcheck; Nachtrag zu Prinzip 2 („Katalogeintrag mit Link ist kein Anbinden“) **(Empfehlung)**
2. Ja, aber erst mit der Harvest-Pipeline (`adr/0025`), nicht von Hand
3. Nein

**F3 — Download der Originale mit der Sitzung des Nutzers bei der Quelle (W2a)?**
1. Ja, für Quellen, deren Download per Cookie-Sitzung läuft (Kandidat Earthdata), nach Ottos Messung (§10 M3); gilt als Link, kein Satz in `ENTSCHEIDUNGEN` nötig **(Empfehlung)**
2. Ja, aber mit einem Satz von Otto in `ENTSCHEIDUNGEN` §1
3. Nein, nur Link zur Seite der Quelle (W0)

**F4 — Lokaler Runner mit Nachweis des Nutzers (W4)?**
1. Ja, als eigene kleine Aufgabe nach M5: Nachweis als Datei (`.netrc` bzw. Umgebungsvariable), an GDAL nur als Konfiguration, Test „kein Nachweis in Ausgabe, Provenienz, Fehlertext“; S3-Lesen für CDSE erst mit einer eigenen Entscheidung zu `/vsis3/` in `gateway` **(Empfehlung)**
2. Ja, auch mit S3 für CDSE gleich
3. Nein

**F5 — Betreiberkonto (W1)?**
1. Nein; nur, wenn eine Quelle schriftlich zusagt, dass ein Plattformkonto für viele Nutzer erlaubt ist, und das Kontingent reicht. Otto fragt bei Bedarf selbst an (CDSE: Programm „Copernicus services user type“; Earthdata: ESDIS) **(Empfehlung)**
2. Otto fragt jetzt bei CDSE und Earthdata an
3. Ja, für CDSE mit dem Kontingent eines kostenlosen Kontos

**F6 — Token pro Connector (W3)?**
1. Eigener ADR nach M6 (Login), nur mit widerrufbaren Nachweisen, nie mit Passwörtern; Cache je Nutzer bis zur Rechtsklärung; Weg zum Job (Importgrenze `jobs → identity` oder verschlüsselt in der Queue) dort entscheiden **(Empfehlung)**
2. Mit M6 einplanen
3. Nicht verfolgen

**F7 — Rechtsfragen?**
1. Vor W1, W2b oder W3: Rechtsrat zu „Handeln im Auftrag des Nutzers“ und zur Weitergabe von Daten, die mit dem Konto eines Nutzers gelesen sind, je Quelle; vor W3 eine Datenschutz-Folgenabschätzung. Für W0, W2a und W4 nicht nötig **(Empfehlung)**
2. Rechtsrat schon vor W2a und W4
3. Kein Rechtsrat

**F8 — Registry-Feld?**
1. `access.account` (`none` · `anonymous_token` · `free_account`), `access.account_provider` und `access.account_paths` mit der YAML-Registry in M5 (B13) **(Empfehlung)**
2. Nur `access.account`; die anderen Felder mit dem ersten Weg außer W0
3. Kein Feld; Konto-Quellen stehen nur in der Beschreibung

---

## 10. Was offen bleibt

**Messpunkte für Otto (aus dieser Sitzung nicht erreichbar):**

- **M1 CDSE-Anmeldung:** `https://identity.dataspace.copernicus.eu/auth/realms/CDSE/.well-known/openid-configuration` öffnen; stehen `authorization_code` in `grant_types_supported` und `S256` in `code_challenge_methods_supported`? Das heißt noch nicht, dass fremde Clients zugelassen sind.
- **M2 CORS:** In der Konsole des Browsers auf einer fremden Seite `fetch` gegen den Download-Endpunkt von CDSE (OData `$value`) und einen Earthdata-Datenhost; erscheint ein CORS-Fehler? (Prüft den Drittbefund in §3.3.)
- **M3 Earthdata per Navigation (W2a):** Mit eigenem kostenlosem Konto im Browser bei Earthdata anmelden, dann die Adresse einer HLS- oder OPERA-Datei direkt öffnen. Lädt sie ohne weitere Anmeldung? Und nach Abmelden: Landet man auf der Anmeldeseite und danach wieder bei der Datei?
- Alles mit Ottos eigenem Konto, lokal, nie in CI oder Cloud-Sitzungen; keine Adresse und keine Item-ID ins Repo.

**Rechts- und Bedingungsfragen:**

- CDSE: Betrieb für viele Endnutzer mit einem Konto; Weitergabe von Zugangsdaten außerhalb des Forums; Änderungsvorbehalt; Zugang zu den Programmen für einen Open-Source-Betreiber; gemeinsame oder getrennte Verantwortung ESA/T-Systems.
- Earthdata: Wortlaut der EULA zu Weitergabe und Service-Konten; PKCE; ob Tokens aus dem App-Flow Daten lesen; Ratenlimits; Protokollierung und Drittlandtransfer.
- CDS/ADS: aktueller Lizenztext (CC BY seit 02.07.2025, nur S), Annahme je Datensatz, Limits.
- ARCO-ERA5: Datenlizenz, Requester Pays.
- CMEMS, EUMETSAT: Lizenzen je Produkt, Weitergabe, Token-Laufzeiten.
- JAXA: Wortlaut der Bedingungen, Konto für die JAXA Earth API, Weitergabe durch Dritte.

**Technik:**

- Ob GDAL einen Nachweis aus `GDAL_HTTP_BEARER` oder `GDAL_HTTP_HEADERS` in Fehlertexten oder im Debug-Log zeigt (Test in der Umsetzung von W4).
- `/vsis3/` mit fremdem Endpunkt in `gateway` (CDSE S3): heute nicht vorgesehen, eigene Entscheidung.
- Wie die Discovery (`adr/0025`) `free_account` erkennt (`401`/`403` an Assets bei anonymem Abruf).

---

## 11. Quellen

Abgerufen am 31.10.2026 durch Hilfsagenten. Belegstufe in Klammern; **P-Dritt** = Quelltext oder PR-Text Dritter selbst gelesen.

**CDSE (P\*, Auszug über das Abrufwerkzeug):**

- https://dataspace.copernicus.eu/terms-and-conditions
- https://dataspace.copernicus.eu/privacy-policy
- Doku-Quelltext unter https://raw.githubusercontent.com/eu-cdse/documentation/publish/: `Quotas.qmd`, `FAQ.qmd` (teilweise), `APIs/Token.qmd`, `APIs/S3.qmd`, `APIs/SentinelHub/Overview/Authentication.qmd`
- Nur S: https://forum.dataspace.copernicus.eu/t/cdse-authentication-on-third-party-sites-pkce/4899, https://dataspace.copernicus.eu/node/1238
- Genannt, nicht abgerufen: https://dataspace.copernicus.eu/copernicus-services-user, https://dataspace.copernicus.eu/ecosystem/services, https://creodias.eu/pricing/credits-for-value-creators/

**ECMWF, Copernicus Marine, EUMETSAT:**

- P\*: https://github.com/ecmwf/cdsapi, https://raw.githubusercontent.com/ecmwf/ecmwf-datastores-client/main/README.md, https://raw.githubusercontent.com/ecmwf/ecmwf-opendata/main/README.md, https://github.com/google-research/arco-era5 (teilweise), https://registry.opendata.aws/ecmwf-era5/, https://raw.githubusercontent.com/mercator-ocean/copernicus-marine-toolbox/main/doc/usage/login-usage.rst, https://github.com/mercator-ocean/copernicus-marine-toolbox
- Nur S: https://forum.ecmwf.int/t/cc-by-licence-to-replace-licence-to-use-copernicus-products-on-02-july-2025/13464, https://help.marine.copernicus.eu/en/articles/8185007-copernicus-marine-toolbox-credentials-configuration, https://manpages.ubuntu.com/manpages/plucky/man1/eumdac.1.html, https://www-cdn.eumetsat.int/files/2026-01/45173%20-%20Data_Policy.pdf

**NASA Earthdata:**

- P-Dritt: https://raw.githubusercontent.com/nsidc/earthaccess/main/earthaccess/auth.py, https://github.com/opengeos/GeoLibre/pull/3085 (PR vom 10.10.2026, CORS-Befund)
- Nur S: https://www.earthdata.nasa.gov/data/earthdata-login, https://www.earthdata.nasa.gov/data/earthdata-login/guidance, https://earthdata.nasa.gov/data/earthdata-login/policy, https://urs.earthdata.nasa.gov/documentation/for_users/user_token, https://urs.earthdata.nasa.gov/documentation/for_users/what_is_app_auth, https://urs.earthdata.nasa.gov/documentation/what_do_i_need_to_know, https://sit.urs.earthdata.nasa.gov/documentation/faq, https://forum.earthdata.nasa.gov/viewtopic.php?t=6782, https://www.earthdata.nasa.gov/earth-observation-data/data-use-policy, https://data.nsidc.earthdatacloud.nasa.gov/s3credentialsREADME, https://tea-docs.asf.alaska.edu/s3access/

**USGS, JAXA, weitere:**

- P\*: https://registry.opendata.aws/usgs-landsat/, https://registry.opendata.aws/deafrica-alos-jers/
- P-Dritt: https://raw.githubusercontent.com/microsoft/planetary-computer-sdk-for-python/main/README.md
- Nur S: https://www.usgs.gov/centers/eros/science/earthexplorer-help-index, https://www.usgs.gov/media/files/m2m-application-token-documentation, https://gportal.jaxa.jp/gpr/index/eula, https://repo.gportal.jaxa.jp/G-PortalRepo_Policy_e.html, https://www.eorc.jaxa.jp/ALOS/en/activity/faq_ra_e.htm, https://data.earth.jaxa.jp/api/python/v0.1.6/en/, https://opentopography.org/blog/introducing-api-keys-access-opentopography-global-datasets, https://developers.google.com/earth-engine/guides/noncommercial_tiers

**Gesperrt für die Hilfsagenten:** `identity`, `documentation` und `forum.dataspace.copernicus.eu`; `cds.climate.copernicus.eu`, `ewds.climate.copernicus.eu`, `forum.ecmwf.int`; `marine.copernicus.eu`; `user.eumetsat.int`; `urs.earthdata.nasa.gov`, `www.earthdata.nasa.gov`, `wiki.earthdata.nasa.gov`; `www.usgs.gov`; `www.eorc.jaxa.jp`, `gportal.jaxa.jp`; `opentopography.org`; `developers.google.com`; `asf.alaska.edu`.

**Im Repo (P):** `ENTSCHEIDUNGEN_2026-09-18.md` §1, §3, §4; `KLAERUNGEN.md` B8, B9, B11; `projektuebersicht.md` §2, §4, §5, §6; `architekturplan.md` 3.1, 6.1, 6.4, 7.7, 9–11; `projektplan.md` 1.1, M6, M7; `adr/0003` §11; `adr/0016` §6.2; `adr/0018` §3.4, §5.3, §9, §12; `adr/0022` §4.2, §7; `.importlinter` (Vertrag `jobs`); `backend/earthx/catalog/registry.py` (`AccessInfo`).
