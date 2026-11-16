# ADR 0034 — Schlüssel der Nutzer

- **Status:** **Entwurf**, Stufe C. Fragen an Otto in §13.
- **Datum:** 2026-11-16
- **Aufgabe:** M5-32 laut `docs/plans/m5/m5-discovery-und-suche.md` §6.2 und §2 Punkt 10. Die Nummer 0034 war beim Start frei: Auf `main` endet die Reihe mit 0033, der einzige offene PR (#362, M5-09) legt kein ADR an.
- **Autonomiestufe:** C. Kein Produktivcode.
  - Geändert sind nur dieses ADR und zwei Zeilen im Entscheidungslog (Ottos Vorgabe vom 11.11.2026, die dort noch fehlte, und dieser Entwurf).
  - Unverändert bleiben `backend/`, `frontend/`, `scripts/`, Registry, Fixtures, M5-Plan, `.importlinter`, `.github/`, `.claude/`, `CODEOWNERS` und `CLAUDE.md`.
- **Vorab fest (Otto, 11.11.2026, M5-Plan §2 Punkt 10; ändert dort Punkt 6 und `adr/0027`):**
  - Quellen, die einen Key oder ein kostenloses Konto brauchen, dürfen angebunden werden, zuerst Copernicus Data Space (CDSE), z. B. für SLC und vollständige GRD mit Annotation.
  - Der Nutzer hinterlegt seinen Key selbst beim Datensatz im Data catalogue.
  - Ein Key schaltet alle Datensätze desselben Anbieters frei.
  - Solche Datensätze tragen ein **kleines Schloss** (ausdrückliche Ausnahme von „keine Marken“) und lassen sich freischalten.
  - Der Key wird laufend auf Gültigkeit geprüft.
  - Die Plattform hat **keinen eigenen Key**; keine Secrets im Repo (öffentlich, AGPL-3.0-or-later).
- **Weiter fest:**
  - Modulgrenzen nach `architekturplan.md` 3.1; Importregeln lockert nur Otto.
  - Ausgehende Requests nur über `gateway` (`KLAERUNGEN` B8).
  - Worker-Kern zustandslos und ohne Plattformdienste (B9).
  - Regel R-Z (`adr/0027` §6.4), soweit Ottos Vorgabe sie nicht berührt (§12).
  - Login erst mit M6 (Projektplan M6).
  - Mehrere Instanzen je Prozesstyp (Prinzip 16, M5-35, M5-36).
  - Keine Anfrage an echte Quellen aus der Session (Auftrag).
- **Grundlage:**
  - `ENTSCHEIDUNGEN_2026-09-18.md` §1, §3, §4; `KLAERUNGEN.md` B8, B9, B11, B13.
  - `projektuebersicht.md` Prinzipien 1, 2, 8, 9, 15, 16; §4 (Sicherheit, Datenschutz); §6 (Auth und Konten).
  - `architekturplan.md` 3.1, 3.2, 6.4, 6.5, 7.3, 7.7, 9, 10, 11, 12.3.
  - `adr/0016` (Runner), `adr/0018` §3.1 (Annotation fehlt im AWS-Bucket), `adr/0022` §4.2 (Kontingente CDSE), `adr/0024` R7 (Antworten `private, no-store`), `adr/0027` (Wege W0–W5, R-Z, `access.account`), `adr/0032` (Pyramide, Auswahl-ID, Ersatz), `adr/0033` (gelistete Einträge).
  - `plans/m5/m5-35-skalierbarkeit.md` (B1), `plans/m5/m5-36-grenzen-je-host.md` (`hosts.yaml`).
- **Betroffen (erst mit einer Entscheidung):** `ENTSCHEIDUNGEN` §1/§3 (Satz von Otto), Prinzip 2, `projektuebersicht.md` §6, `KLAERUNGEN` B8, `adr/0027` (F6, R-Z, §6.1), `architekturplan.md` 3.1, 6.5, 11; Registry (`AccessInfo`, `hosts.yaml`, neue `providers.yaml`), `identity`, `gateway`, `access`, `api`/`tiler`, `jobs`, `.importlinter`, Frontend (Data catalogue, Layer-Zeile, Processing-Panel).

---

## Methode und Belegstufen

Belegstufen wie in `adr/0027` und `adr/0032`:

- **M:** in dieser Sitzung gemessen.
- **P:** am Primärdokument selbst gelesen; im Repo mit Pfad.
- **P\*:** Primärdokument über das Abrufwerkzeug eines Hilfsagenten gelesen. Das Werkzeug fasst Seiten zusammen; Zitate sind sinngemäß und vor einer Annahme an der Quelle zu prüfen.
- **S:** Suchtreffer, Zusammenfassung oder Vorwissen, Wortlaut nicht geprüft.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Anfragen an Datenquellen:** keine. Gemessen wurde nichts. Ein Hilfsagent las öffentliche Doku-, Bedingungs- und Standardseiten; die API- und Datenhosts von CDSE und Earthdata waren für ihn ausdrücklich gesperrt. Es gibt kein Konto, keinen Key und keine Anmeldung in dieser Sitzung. Was nur mit einem Konto messbar ist, steht als Messpunkt für Otto in §14.

---

## 0. Kurzfassung

1. **Ablage (§5):** serverseitig, verschlüsselt, an eine **anonyme Sitzung des Browsers** gebunden. Der Browser hält nach der Eingabe nur ein `HttpOnly`-Cookie mit zufälliger Kennung und einem zufälligen Schlüsselteil; die Datenbank hält nur Chiffrat. Entschlüsseln kann nur, wer **beides** hat: das Cookie (Nutzer) und den Schlüssel der Instanz (Konfiguration, nie Datenbank, nie Repo). Frist 30 Tage ohne Nutzung, höchstens bis zum Ablauf des Keys, jederzeit löschbar. „Nur im Browser“ scheitert an Jobs, die laufen, wenn der Browser zu ist, und an R-Z (kein Nachweis in der Auftragskopie).
2. **Weg (§5.4):** `api`/`tiler` lösen aus dem Cookie einen Nachweis im Speicher auf und reichen ihn als undurchsichtiges Objekt (Typ in `readers`, wie `HostSlot` aus M5-36) über `access` an `readers`; `gateway` bekommt nur die Werte und setzt sie nur für Hosts, die `hosts.yaml` als Key-Hosts dieses Anbieters führt. Für Jobs legt `api` je Lauf eine eigene, befristete Freigabe ab (nicht im Auftrag); die Hülle `jobs` reicht den Nachweis über die Pipe an das Kind. Der Kern bekommt ihn als Argument und hält nichts (B9). Dafür braucht es **eine neue Importkante `jobs → identity`** (nur Otto).
3. **Art des Keys bei CDSE (§6):** zuerst der **S3-Schlüssel** des Nutzers (selbst erzeugt, mit eigenem Ablauf, widerrufbar, nie das Passwort). Er erlaubt Bereichslesen in den entpackten Produkten samt Annotation, also Kacheln und Jobs. Das verlangt `/vsis3/` in `gateway` und eine Auslegung von R-Z für die S3-Signatur.
4. **Prüfung (§6.3):** bei der Eingabe, beim Öffnen der Seite (höchstens alle 6 h je Key), vor jedem Job und sofort bei `401`/`403` der Quelle. Kein Prüflauf ohne den Nutzer. Läuft der Key während eines Jobs ab, endet der Lauf mit eigener Fehlerart, ohne zweiten Versuch.
5. **Cache (§7):** Vor jedem Cache steht die Prüfung „gültiger Key dieses Anbieters“. Alles Dauerhafte (Ergebnis-Cache, Browser) je Nutzer, wie Otto zu `adr/0027` F6 bis zur Rechtsklärung festgelegt hat; nur der flüchtige Lese-Cache im Prozess ist gemeinsam. Nach außen jede Antwort `private, no-store`. **Keine Pyramide** aus Nutzer-Keys; unter `min_zoom` ein anonymer Ersatz, wo es einen gibt.
6. **Registry (§8):** Weg `W3` wird freigegeben (`account_paths: [W3]`), neue Datei `backend/catalog/providers.yaml` (ein Eintrag je Anbieter, ein Key je Anbieter), Feld `credential` in `hosts.yaml`. Ohne Key: Datensatz gelistet, Suche und Coverage wie heute, Rasterebene und Processing mit Schloss gesperrt.
7. **Bedrohungen (§9):** Vor M6 nötig sind Verschlüsselung mit geteiltem Schlüssel, `HttpOnly`-Cookie, Key-Hosts nur aus der Registry, Prüforakel gedrosselt, kein Nachweis in Logs, Fehlern, URLs, Hashes, Rezepten oder Provenienz (mit Testschlüssel als Fangwert), CSP. M6 bringt Login, Quotas je Nutzer, Egress-Proxy, Audit und Datenschutz-Folgenabschätzung.
8. **Schnitt (§10):** fünf Aufgaben (M5-44 bis M5-48), je höchstens zwei PRs; Jobs mit Key (M5-48) sind die Voraussetzung für die Radar-Kette auf CDSE-Daten aus M5-31.

---

## 1. Kontext und Frage

`adr/0027` hat am 06.11.2026 den Weg „Konto des Nutzers, auf der Plattform hinterlegt“ (W3) als eigenen ADR **nach M6** vorgesehen (F6) und in M5 nur den Katalogeintrag mit Link (W0) zugelassen. Otto hat das am 11.11.2026 geändert (Vorgabe oben). Anlass ist die Radar-Verarbeitung: Vollständige GRD-Produkte mit Annotation und SLC gibt es über CDSE nur mit Konto. Im anonymen AWS-Bucket fehlt die Annotation, und die STAC-Assets von Earth Search zeigen auf die RFI-Annotation (`adr/0018` §3.1, Befund #343; M5-Plan §2 Punkt 10).

**Frage:** Wo liegt der Key eines Nutzers, bevor es einen Login gibt? Wie kommt er zu `gateway`, ohne Modulgrenzen, B9 und R-Z zu brechen? Welche Art Key je Anbieter, wie geprüft? Was heißt das für Cache, Pyramiden, Registry und Oberfläche? Welche Bedrohungen entstehen, und welche Aufgaben folgen?

**Was dieses ADR nicht entscheidet:**

- welche CDSE-Datensätze zuerst kommen und ihre Lizenz-Einstufung: immer Otto;
- die Radar-Kette: M5-31;
- Login und Identity-Provider: M6;
- Download der Originale mit Key im Browser (W2b): bleibt nach `adr/0027` bei Quellen mit PKCE und CORS (§8.4).

---

## 2. Kriterien

| # | Kriterium | Woher |
|---|---|---|
| K1 | Kein Key der Plattform, keine Secrets im Repo, in CI, in Cloud-Sitzungen, Logs, Issues, PRs | Vorgabe Otto; `ENTSCHEIDUNGEN` §4 |
| K2 | Nachweis nie in Logs, URLs, Rezepten, Hashes, Provenienz, Fehlermeldungen, Cache-Schlüsseln, Permalinks, Auftragskopie | Auftrag; R-Z |
| K3 | Modulgrenzen, B8, B9; jede Lockerung nur mit Otto | `CLAUDE.md`; `architekturplan.md` 3.1 |
| K4 | Mehrere Instanzen je Prozesstyp, kein Zustand im Prozess | Prinzip 16; M5-35 |
| K5 | Schaden bei Abfluss klein: begrenzte, widerrufbare Keys; Datenbank allein reicht nicht | `projektuebersicht.md` §4; `adr/0027` §6.3 |
| K6 | Was der Key freischaltet: Kacheln, Statistik, Zuschnitt, Jobs | Vorgabe Otto; B11 |
| K7 | Bedingungen und Kontingente des Anbieters; Kontingent anderer Nutzer nie verbrauchen | `adr/0027` K1, K2, K7 |
| K8 | Ein Klick nach der Eingabe; ein Key je Anbieter | Vorgabe Otto |
| K9 | Aufwand für 1 bis 3 Personen; Weg nach M6 ohne Umbau | `architekturplan.md` 1.1 |
| K10 | Ehrlichkeit: Schloss, Fehler mit eigenem Text statt leerer Karte | Prinzipien 9, 11 |

---

## 3. Befund am Code [P]

Stand `main` 10f55cb.

- **Registry** (`backend/earthx/catalog/registry.py`): `AccountKind` (`none`, `anonymous_token`, `free_account`, `requester_pays`, `paid`) und `AccountPath` (`W2a`, `W2b`, `W3`, `W4`) gibt es schon. `_check_access` verbietet jeden Wert in `account_paths` und hält jede Konto-Quelle auf der B11-Stufe „Katalogeintrag“. Alle sechs vollen Einträge haben `account: none`.
- **Hosts** (`backend/catalog/hosts.yaml`): eine Zeile je Host mit `connections`, `reason` (Pflicht, `catalog/hosts.py`) und optional `interval_s`; Grenzen für alle Instanzen zusammen (M5-36).
- **Frontend:** `frontend/src/catalogue.ts` (`accountOf`) und `components/DataCatalogue.tsx` zeigen bei Konto-Quellen die Marke „Account“ und statt „Add“ den Link zur Quelle. `preferences.ts` speichert nur Einstellungen in `localStorage` und schickt nichts ans Backend. Eine Content Security Policy setzt das Repo nirgends (Suche über `frontend/` und `backend/earthx/`).
- **Same Origin, nur in der Entwicklung:** Der Proxy des Vite-Servers legt `api` und `tiler` unter den Ursprung des Frontends (`frontend/vite.config.ts`: `/stac`, `/catalogue`, `/processing`, `/collections`, `/results`). Ein Cookie der Seite erreicht dort auch die Kachel-Anfragen von MapLibre, ohne dass das Frontend die Kachel-URL ändert. Einen Reverse-Proxy für den Betrieb gibt es im Repo nicht (`compose/`, `docker-compose.yml`); der Vite-Server läuft über `http`.
- **`gateway`:**
  - nur `https` (`architekturplan.md` 6.5, Nachtrag M4 Q5), keine Nachweise (`gateway/gdal.py`, Docstring: „No token“);
  - `Gateway._send` folgt Weiterleitungen selbst und gibt **dieselben `headers` an jedes Ziel** weiter, auch an einen anderen Host der Allowlist (`gateway/client.py`, Schleife in `_send`). Für eine Kopfzeile mit Nachweis wäre das ein Bruch von R-Z Punkt 2;
  - `UpstreamError` (`gateway/errors.py`) bekommt bis zu `EXCERPT_CHARS` = 500 Zeichen der Fehlerantwort in den Text (`gateway/client.py`). S3 gibt bei `SignatureDoesNotMatch` die Access-Key-ID im Fehlertext zurück [S, Vorwissen];
  - das Log nennt Host, Pfad und einen Hash der Query mit Prozess-Schlüssel, nie die Query (`_log`);
  - **GDAL folgt Weiterleitungen selbst**; Prüfung und Schleife von `gateway` erreichen es nicht. Erst der Egress-Proxy in M6 schließt das (`gateway/gdal.py`, Docstring; B8 Stufe 2).
- **GDAL:** Optionen kommen als `dict` und werden über `rasterio.Env` je Faden gesetzt (`gateway/gdal.py`). Der `/vsicurl/`-Bereichscache des `tiler` ist prozessweit (256 MB, `TILER_CURL_CACHE_BYTES`) und nach Dateiname geschlüsselt [P, Kommentar dort].
- **Jobs:** Die Hülle schreibt `recipe.json` in ein Arbeitsverzeichnis und startet je Lauf ein Kind per `spawn` mit Pipe (`jobs/worker.py`, `jobs/child.py`). Das Kind konfiguriert sein Logging selbst, weil GDAL Adressen in Meldungen nennt. **Ein Kind je Lauf** heißt: Ein Nachweis im Kind ist von anderen Läufen getrennt.
- **Module:** `identity` ist leer; `.importlinter` verbietet `identity` jeden Import und `jobs` den Import von `identity` (Verträge `identity`, `jobs`).
- **Prototyp-Muster:** `adr/0024` R7 schickt jede Antwort mit Daten eines Prototyp-Datensatzes `private, no-store` (`PROTOTYPE_CACHE_CONTROL` in `api/mosaic_tiles.py`, beschrieben in `api/tiler.py`). Dasselbe Muster passt für Daten mit Key.
- **Importregeln für den Weg eines Nachweises:** `access`, `processing`, `jobs` und `identity` dürfen `gateway` nicht direkt importieren; `jobs` auch `readers` nicht (`.importlinter`). M5-36 löst dasselbe für die Plätze je Host mit einem Protokoll `HostSlot` in `access`, hereingereicht von `api` (`plans/m5/m5-36-grenzen-je-host.md` §5.2).

---

## 4. Stand der Technik

Gelesen über einen Hilfsagenten (Quellen §15). Die Doku von CDSE lag als Quelltext auf GitHub (`eu-cdse/documentation`, Branch `publish`, Stand 16.11.2026); die Seiten des Forums und einige Standardseiten (RFC-Editor, OWASP-Website, MDN) waren nicht erreichbar, OWASP und MDN dafür als Quelltext.

### 4.1 Secrets im Browser

- **OWASP HTML5 Security Cheat Sheet:** keine sensiblen Daten in `localStorage`; „A single Cross Site Scripting can be used to steal all the data“ [P\*].
- **IETF `draft-ietf-oauth-browser-based-apps`:** Ein rein browserbasierter Client ist für sensible Anwendungen nicht empfohlen; empfohlen ist ein **Backend for Frontend** (BFF, vertraulicher Client, Token nur auf dem Server, Browser nur mit Cookie). Ein „Token-Mediating Backend“, das Token an den Browser gibt, ist „less secure than a BFF“. Speicher des Browsers schützt nicht gegen bösartiges JavaScript und ist nicht sicher verschlüsselt abgelegt [P\*].
- **Web Crypto:** `extractable: false` verhindert den Export eines Schlüssels, nicht seine Benutzung durch ein eingeschleustes Skript [P\*][A].
- **Folge [A]:** A1 und A2 (§5) liegen auf der Seite, die der Entwurf als schwächer einstuft; A3 ist ein BFF für fremde Nachweise.

### 4.2 Secrets auf dem Server

- **OWASP Cryptographic Storage:** Envelope Encryption, Datenschlüssel (DEK) unter einem Schlüsselschlüssel (KEK); „KEK must be stored separately from the DEK“, nicht neben den Daten; AES-GCM als erste Wahl; Rotation mit Schlüssel-ID je Datensatz oder Neuverschlüsseln [P\*].
- **OWASP Secrets Management:** Secrets mit Ablauf anlegen, vor Gebrauch prüfen, ob sie noch gelten („verify that the secret is still active before trusting it“), widerrufen, wenn nicht mehr gebraucht, nie loggen [P\*].
- **`cryptography`:** Fernet (AES-128-CBC + HMAC) mit optionaler `ttl` beim Entschlüsseln; Zeitstempel im Klartext [P\*]. AES-GCM über `AESGCM` derselben Bibliothek ist die Wahl nach OWASP [A].
- **Vault Transit, KMS:** DEK unter einem Schlüssel im Dienst, `rewrap` nach Rotation ohne Klartext [S].

### 4.3 Wie andere Systeme fremde Nachweise halten

| System | Ablage | Schutz | Beleg |
|---|---|---|---|
| Grafana | Datenbank, `secureJsonData` je Datenquelle | Envelope Encryption, KEK aus `secret_key` oder KMS (AWS, Azure, GCP, Vault), Rotation mit Neuverschlüsselung | P\* |
| n8n | Datenbank | Instanzschlüssel `N8N_ENCRYPTION_KEY` über rotierbarem Datenschlüssel | S |
| QGIS | lokale Datenbank | Master-Passwort des Nutzers; ohne es „no way to retrieve“ | P\* |
| PrivateBin | Server hält nur Chiffrat | Schlüssel im URL-Fragment, erreicht den Server nie | P\* |
| Planetary Computer | kurzlebiges SAS-Token, anonym abrufbar | Ablauf im Token | S |
| openEO (CDSE) | Nachweis bleibt beim OIDC-Anbieter; auch Client Credentials (experimentell) | — | P\*, S |

- **Schlüsselteil beim Client:** Eine feste Bezeichnung für „Server kann ohne das Cookie nicht entschlüsseln“ fand die Recherche nicht [S]. Am nächsten liegen PrivateBin (Schlüssel nie beim Server) und QGIS (Schlüssel beim Nutzer). A3 ist schwächer als PrivateBin: Der Server sieht das Cookie bei jeder Anfrage und kann im laufenden Betrieb entschlüsseln. A3 schützt deshalb gegen den **Abfluss** von Datenbank oder Backup, nicht gegen einen übernommenen Server (§9 T1, T2) [A].
- **Verlust des Cookies** heißt: Key neu eingeben. Das ist gewollt [A].

### 4.4 Secrets aus Logs, Fehlern und URLs

- **Pydantic `SecretStr`:** `repr`/`str` maskiert, JSON maskiert, Klartext nur über `get_secret_value()` [P\*]. Ein Muster für `Credential` (§5.4).
- **Python-Logging:** Filter dürfen Records ändern; ein Filter am Handler greift für alle Logger, die dort ankommen [P\*].
- **GDAL** [P\* am Quelltext `port/cpl_http.cpp` und an der Doku]:
  - `CPL_CURL_VERBOSE` (mit `CPL_DEBUG`) gibt die Ausgabe von libcurl **ungefiltert** aus, Kopfzeilen wie `Authorization` eingeschlossen; Passwörter in URLs maskiert GDAL, Kopfzeilen nicht.
  - `VSISetPathSpecificOption` (ab 3.6) setzt Optionen je Pfadpräfix, prozessweit; wie das mit mehreren Fäden wirkt, ist offen. Zwei Nutzer mit Keys für denselben Bucket lesen denselben Präfix: Der Weg passt nicht [A].
  - `CPL_VSIL_CURL_AUTHORIZATION_HEADER_ALLOWED_IF_REDIRECT` (ab 3.10, Vorgabe `IF_SAME_HOST`) regelt, ob GDAL eine `Authorization`-Kopfzeile bei Weiterleitung mitgibt.
  - `AWS_S3_ENDPOINT` darf ab 3.11 das Schema enthalten; `AWS_SESSION_TOKEN` für temporäre S3-Schlüssel.
- **curl:** Es gab 2025/2026 CVEs zu Bearer-Token bei Weiterleitungen in libcurl [S]. GDAL hängt daran; die Version im Image gehört in die Prüfung von M5-46 [A].
- **Sentry** (falls je genutzt): der Standard-Scrubber filtert nur Schlüssel in Dictionaries, keine URLs und keinen Freitext; nötig ist `before_send` [P\*].

### 4.5 HTTP-Cache und Lizenz der Daten

- **RFC 9111 §3.5:** Ein gemeinsamer Cache darf Antworten auf Anfragen mit `Authorization` nur speichern, wenn die Antwort es ausdrücklich erlaubt (`public`, `s-maxage`, `must-revalidate`) [S, Wortlaut nicht gelesen]. Ein Cookie fällt nicht unter diese Regel; deshalb braucht jede Antwort mit Key-Daten selbst `Cache-Control: private` [A].
- Der eigene Cache der Anwendung (GDAL, Objektspeicher, Postgres) fällt nicht unter RFC 9111; dort entscheidet die Plattform [A].
- **Lizenz der Sentinel-Daten:** Das „Legal Notice on the use of Copernicus Sentinel Data“ (gestützt auf VO (EU) 377/2014 und Delegierte VO (EU) 1159/2013) erlaubt Vervielfältigung, Verbreitung, öffentliche Wiedergabe und Bearbeitung mit Quellenangabe [S, Volltext nicht gelesen]. Die Bedingungen von CDSE verweisen darauf (§3) [P\*].
- **Zugang ≠ Lizenz [A]:** Die Lizenz erlaubt Weitergabe der Daten; die Bedingungen des Zugangs regeln Konten und Kontingente. Ob ein gemeinsamer Cache unter Nutzern mit eigenem Konto die Kontingentlogik von CDSE „umgeht“, sagen die gelesenen Bedingungen nicht. §9 der Bedingungen verbietet ausdrücklich nur Mehrfachkonten „in tens, hundreds or thousands“ [P\*].

---

## 5. Punkt 1: Ablage vor dem Login

### 5.1 Optionen

| | Wo liegt der Key | Kacheln | Jobs | Abfluss bei Einbruch | Skalierung |
|---|---|---|---|---|---|
| **A1** nur im Browser | Speicher der Seite oder `IndexedDB`; mit jeder Anfrage als Kopfzeile ans Backend | ja, Kopfzeile über `transformRequest` von MapLibre | **nein**: Ein Job läuft, wenn der Browser zu ist; den Key mit dem Auftrag abzulegen, verbietet R-Z. Bleibt der Runner (W4) | XSS liest den Key | zustandslos |
| **A2** Chiffrat beim Nutzer | Server verschlüsselt mit Schlüssel der Instanz, Browser hält das Chiffrat und schickt es mit | ja | wie A1: Chiffrat müsste in den Auftrag | XSS liest Chiffrat; nutzbar nur über die Plattform | zustandslos |
| **A3** Server, an die Sitzung gebunden, geteilter Schlüssel (**Empfehlung**) | Postgres hält Chiffrat; Cookie (`HttpOnly`) hält Kennung und Schlüsselteil; Schlüssel der Instanz aus der Konfiguration | ja, das Cookie reist mit (Same Origin) | ja, über eine Freigabe je Lauf (§5.4) | Datenbank allein nutzlos; XSS kann den Key nicht lesen, nur über die Seite benutzen | Postgres, kein Zustand im Prozess |
| **A4** Server, ohne Sitzungsbindung | Postgres, Kennung im `localStorage` | ja | ja | Datenbank + Schlüssel der Instanz reichen; XSS liest die Kennung | Postgres |

**Empfehlung A3.** Gründe [A]:

- **Jobs:** Otto will Radar-Verarbeitung auf CDSE-Daten (M5-31). Nur A3 und A4 erlauben einen Cloud-Job mit Key, ohne den Key in die Auftragskopie zu legen.
- **Zwei Hälften:** Bei A3 braucht ein Angreifer Datenbank **und** Schlüssel der Instanz **und** das Cookie des Nutzers. Das liegt nahe an PrivateBin und QGIS (Schlüssel beim Nutzer, §4.3), ist aber schwächer: Es schützt gegen den Abfluss der Datenbank, nicht gegen einen übernommenen Server.
- **Kein Key im JavaScript:** Nach der Eingabe kennt die Seite den Key nicht mehr; eine XSS-Lücke kann ihn benutzen, solange die Seite offen ist, aber nicht mitnehmen. Bei A1 und A2 liegt er für jedes Skript lesbar da (§4).
- **Frontend unverändert:** Kachel-URLs bleiben, wie sie sind; das Cookie geht mit, weil alles am selben Ursprung hängt (§3).
- **Weg zu M6:** Mit dem Login wird aus der anonymen Sitzung ein Konto; die Zeile bekommt den Eigentümer, das Chiffrat bleibt (§10, M6).

### 5.2 A3 im Einzelnen

**Sitzung.**

- Cookie `__Host-earthx-keys`: `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`, ohne `Domain`. Inhalt: zufällige Sitzungskennung (128 Bit) und zufälliger Schlüsselteil (256 Bit), base64url.
- `__Host-` und `Secure` verlangen HTTPS; Browser behandeln `http://localhost` als sicheren Kontext, die Entwicklung mit Vite geht also [S]. Im Betrieb müssen Frontend, `api` und `tiler` unter **einem** Ursprung liegen (Reverse-Proxy, M6), sonst erreicht das Cookie die Kacheln nicht (§3).
- Gesetzt erst beim ersten Speichern eines Keys, nicht beim Besuch. Ohne Key gibt es kein Cookie und keine Sitzung (Datenminimierung).
- Lebensdauer wie die Frist unten; jede Nutzung verlängert.

**Speicher.**

- Tabelle im Schema von `identity` (`architekturplan.md` 10: getrenntes Schema, eigene DB-Rolle), eine Zeile je Sitzung und Anbieter:
  - Sitzungskennung als Hash (nicht im Klartext, damit ein Leser der Tabelle kein Cookie bauen kann);
  - Anbieter, Art des Keys;
  - Chiffrat (AES-256-GCM), Nonce, Fassung des Instanzschlüssels;
  - Status (`valid`, `invalid`, `expired`, `unchecked`), `checked_at`, `expires_at` (Ablauf des Keys, falls bekannt), `last_used_at`;
  - keine IP, kein User-Agent, keine AOI.
- **Schlüssel:** Datenschlüssel = HKDF(Instanzschlüssel ‖ Schlüsselteil aus dem Cookie, Kontext „Anbieter + Sitzung“). Die Kennung des Anbieters steht als zusätzliche Daten in GCM, damit ein Chiffrat nicht unter einem anderen Anbieter gilt.
- **Instanzschlüssel:** aus der Konfiguration wie die Schlüssel des Objektspeichers (`docker-compose.yml` erzeugt sie lokal in eigenen Volumes). Nie in der Datenbank, nie im Repo, nie mit Vorgabewert: ohne ihn startet `api` nicht mit Key-Routen. Eine Fassungsnummer erlaubt Rotation. In der Cloud später aus einem KMS (M6). **Ein Secret im Betrieb ist „nie ohne Otto“** (Projektplan 1.1): F2.
- **Frist:** 30 Tage ohne Nutzung, höchstens bis `expires_at`; danach löscht die Aufräumrunde (`jobs/cleanup.py`-Muster, unter Advisory Lock wie M5-35 B2). „Remove key“ löscht sofort.

**Routen** (in `api`, Präfix z. B. `/keys`):

- `PUT /keys/{provider}`: Key annehmen (Body JSON, nie Query), sofort prüfen (§6.3), bei Erfolg speichern und Cookie setzen. Antwort nur der Status.
- `GET /keys`: Status je Anbieter dieser Sitzung (`valid`, `invalid`, `expired`, `unchecked`, `none`), nie der Key und kein Teil davon.
- `DELETE /keys/{provider}`: löschen.
- CSRF: `SameSite=Strict` und Pflicht-Kopfzeile `Content-Type: application/json` bei `PUT`/`DELETE`.

### 5.3 Mehrere Instanzen (M5-35)

- `api` und `tiler` sind weiter ohne Zustand: Jede Instanz liest die Zeile aus Postgres und entschlüsselt mit Cookie und Instanzschlüssel.
- Ein Cache entschlüsselter Keys im Prozess ist zulässig, aber höchstens 60 s und nur im Speicher; sonst kostet jede Kachel eine Datenbankabfrage (Messung in M5-47).
- Der Instanzschlüssel ist für alle Instanzen derselbe; Rotation über die Fassungsnummer.
- Die Frist und die Prüfung halten ihren Zustand in Postgres, nicht im Prozess.

### 5.4 Weg durch `api`, `gateway` und Runner

```
Browser ── Cookie ──▶ api / tiler ──▶ identity: Zeile lesen, entschlüsseln
                         │
                         ▼  Credential (undurchsichtig, im Speicher)
                       access ──▶ readers ──▶ gateway ──▶ nur Key-Hosts des Anbieters
```

- **Typ `Credential` in `readers`** (Anbieter, Art, Werte), von `processing` weitergereicht, damit auch das Kind eines Jobs ihn bauen kann (`jobs` darf `processing` importieren, `readers` nicht). `__repr__` und `__str__` zeigen nur „Credential(<provider>)“; nicht picklebar, kein JSON (Muster `SecretStr`, §4.4). `access` gibt ihn nur durch, wie `HostSlot` (§3). `readers` übergibt `gateway` nur die nackten Werte und den Host; `gateway` kennt keinen Typ von oben.
  - `identity` gibt nur Bytes bzw. ein `dict` zurück; `api` und das Kind bauen daraus das `Credential`.
  - Neue Importkanten: **nur `jobs → identity`** (Jobs, unten). `api → identity` ist erlaubt (`api` darf alles).
- **`gateway` entscheidet, wohin:** Ein Nachweis geht nur an Hosts, die `hosts.yaml` mit `credential: <provider>` führt (§8.2). Für andere Hosts wird er still weggelassen. Bei Weiterleitungen über `httpx` fällt er weg, auch innerhalb der Allowlist (heute gehen die Kopfzeilen mit, §3). **GDAL folgt Weiterleitungen selbst** (§3): Vor M6 hängt R-Z Punkt 2 dort an GDAL (`CPL_VSIL_CURL_AUTHORIZATION_HEADER_ALLOWED_IF_REDIRECT=IF_SAME_HOST`, Signatur V4 je Endpunkt) und an einem Test mit Fixture-Server; erzwungen wird es erst vom Egress-Proxy.
- **GDAL:** Optionen je Lesevorgang über `rasterio.Env` (Faden), nie global, nie `VSISetPathSpecificOption` (prozessweit). Für S3: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_ENDPOINT`, `AWS_VIRTUAL_HOSTING=FALSE`, `AWS_HTTPS=YES`, `GDAL_HTTP_UNSAFESSL=NO`; `CPL_CURL_VERBOSE` und `CPL_DEBUG` aus. Ob GDAL Nachweise zwischen Fäden in Handles oder Caches mitnimmt, ist ein Messpunkt (§14, T7).
- **Jobs (R-Z, B9):**
  1. `api` prüft bei der Annahme den Key (§6.3) und legt eine **Freigabe je Lauf** an: eigene Tabelle in `identity`, Chiffrat nur unter dem Instanzschlüssel (das Cookie ist im Worker nicht da), gebunden an Lauf-ID und Anbieter, Frist = Ablauf des Laufs (`max_seconds` plus Warteschlange, höchstens 24 h).
  2. Die Hülle `jobs` liest die Freigabe beim Start des Kinds, entschlüsselt sie und gibt die Werte über die Pipe ans Kind; nichts davon im Arbeitsverzeichnis, in `recipe.json` oder im Log.
  3. Das Kind baut daraus das `Credential` und gibt es dem Kern als Argument; der Kern hält nichts zwischen Aufrufen (B9).
  4. Am Ende des Laufs (jeder Ausgang) löscht die Hülle die Freigabe; die Aufräumrunde löscht abgelaufene.
  - **Warum das R-Z einhält** [A]: Die Freigabe liegt nicht in der Auftragskopie (Tabelle der Queue, `recipe.json`), sondern getrennt, verschlüsselt und kürzer befristet als der Auftrag. Ob Otto das so auslegt, ist F3.
  - **Was es kostet:** `jobs` muss `identity` importieren (nur das Lesen und Löschen der Freigabe). Das ist eine Lockerung der Importregeln (F3). Alternative ohne Lockerung: ein eigenes kleines Modul `keystore` mit eigener Zeile in 3.1, das `api`, `tiler` und `jobs` importieren dürfen; dasselbe Problem unter anderem Namen.
- **Lokaler Runner (W4):** unverändert nach `adr/0027` F4: Der Nutzer gibt dem Container seinen Nachweis selbst (Datei, Umgebungsvariable); die Plattform liefert nichts aus. Der Runner bekommt keinen Zugang zur Ablage. Für S3 heißt das: Datei mit `AWS_*`-Werten, gelesen von `gateway` des Runners mit denselben Regeln (Key-Hosts aus der Registry des Images, F4).
- **Vorschau und Kachel desselben Operators** (`architekturplan.md` 7.3: T1 und T2 mit derselben Implementierung) brauchen denselben Nachweis; das ist durch den Weg oben gegeben.

### 5.5 Nie in Logs, URLs, Rezepten, Hashes, Provenienz, Fehlermeldungen

| Ort | Maßnahme |
|---|---|
| Log | `Credential` ohne Klartext-`repr`; Filter am Root-Logger, der Werte aktiver Nachweise ersetzt; `gateway._log` unverändert ohne Kopfzeilen; GDAL ohne `CPL_CURL_VERBOSE` |
| URL | Key nie in Query oder Pfad; **keine vorsignierten URLs** für Key-Hosts (die tragen Access-Key-ID und Signatur in der Query) |
| Rezept, Auftragskopie | nur Datensatz und Item-IDs wie heute; das Rezept vermerkt `requires_key: <provider>` (ohne Kennung des Keys) |
| Hash | kein Key und nichts daraus in Rezept-Hash, Auswahl-ID, Cache-Schlüssel, Fassung; die Sitzungskennung steht nur als Hash in `identity` und nirgends sonst |
| Provenienz | `access: user_key`, Anbieter; nie Kennung oder Teil des Keys |
| Fehlermeldung | an den Nutzer nur „Key for <provider> rejected“ bzw. „expired“; `UpstreamError` ohne Auszug der Antwort für Key-Hosts (§3) |
| Antwort | `GET /keys` nur Status |
| Test | ein Fangwert als Key (`AKIA…CANARY`) läuft durch Kachel, Job, Fehler und Abbruch; danach dürfen Logs, Dateien, Antworten, `recipe.json`, `provenance.json` und die Queue ihn nicht enthalten |

---

## 6. Punkt 2: Art der Keys je Anbieter

### 6.1 CDSE

Aus der Doku von CDSE (Quelltext auf GitHub, §15) [P\*], ergänzt um Forum-Treffer [S]:

| Art | Erzeugung | Ablauf | Wofür | Bewertung [A] |
|---|---|---|---|---|
| **Benutzer/Passwort → Token** (Passwort-Grant, öffentlicher Client `cdse-public`) | Konto | Access-Token 10 min, Erneuerung innerhalb 60 min; 100 aktive Sitzungen je Konto | OData-Suche und -Download (auch `$zip`) als `Authorization: Bearer` | **scheidet aus:** die Plattform müsste das Passwort halten, um nach 60 min neu anzufangen (`adr/0027` §4.4: nie ein Passwort) |
| **OAuth-Client** (Sentinel Hub, Client Credentials) | Dashboard, Ablauf wählbar oder „Never expire“, Secret nur einmal sichtbar; SPA-Variante mit Origin | Token rund 1 h (`exp` im JWT) [S]; Token-Anfragen mit `429` begrenzt | Sentinel-Hub-APIs (Kontingent 10 000 Anfragen und 10 000 Processing Units im Monat), openEO (experimentell) | geeignet als widerrufbarer Nachweis; **ob das Token OData-Download und `zipper` öffnet, ist offen** (Foren widersprechen sich [S]). Sentinel Hub liefert gerechnete Bilder, keine Originaldateien: für die eigene Kette der Plattform nicht der Leseweg |
| **S3-Schlüssel** (`eodata`) | S3-Keys-Manager, Ablaufdatum selbst gewählt, Secret nur einmal sichtbar; temporäre Schlüssel über eine API | bis zum gewählten Tag; Höchstzahl je Konto nicht dokumentiert | Bereichslesen in den Produkten unter `eodata.dataspace.copernicus.eu` | **Empfehlung:** widerrufbar, befristet, schmal (nur Lesen von `eodata`), und der einzige Weg zu Bereichslesen in GRD, SLC und Annotation ohne ganze ZIP-Dateien |

**Kontingente je Konto** (gelten für S3, OData und STAC zusammen) [P\*]: 4 parallele Verbindungen, 20 MB/s je Verbindung, 12 TB in 30 Tagen, S3 zusätzlich 2000 Anfragen je Minute. Nach Überschreiten des Volumens stuft CDSE stündlich herab: 1 MB/s und **eine** Verbindung, keine Sperre.

**Prüfweg `s3_head` [A, Messpunkt M1]:** eine signierte `HEAD`-Anfrage auf ein festes, kleines Objekt in `eodata`, das jeder Nutzer lesen darf. Ein ungültiger oder abgelaufener Schlüssel antwortet `403` mit `InvalidAccessKeyId` [S]. Kostet eine von 2000 Anfragen je Minute und keine Datenmenge. Welches Objekt, legt Otto mit M1 fest; seine Adresse steht dann in `providers.yaml` (keine AOI, öffentlich bekannter Pfad). Einen Endpunkt zur Prüfung ohne Datenzugriff (Introspection, `userinfo`) dokumentiert CDSE nicht [P\*].

**Ablaufdatum:** Die Plattform kann den Ablauf eines S3-Schlüssels nicht abfragen. Das Formular fragt deshalb das Datum ab, das der Nutzer beim Erzeugen gewählt hat (`expires_on`, freiwillig). Fehlt es, gilt die Frist von 30 Tagen und die Prüfung bei Gebrauch.

**R-Z und S3 [A]:** R-Z erlaubt einen Nachweis nur am Anmelde-Host. Bei S3 gibt es keinen Anmelde-Host: Jede Anfrage trägt eine Signatur (AWS Signature V4) an den Datenhost. Das Secret selbst verlässt den Prozess nie; die Signatur gilt für genau diesen Host, Pfad und rund 15 min, und die Access-Key-ID geht als Kennung mit. Vorschlag für F4: R-Z gilt für S3 mit dem Key-Host aus `providers.yaml` als „Anmelde-Host“, ohne Weiterleitung, nie mit vorsignierter URL. GDAL folgt Weiterleitungen bei `/vsis3/` selbst; ob es dabei neu signiert oder eine `Authorization` weitergibt, prüft M5-46 am Fixture-Server (`CPL_VSIL_CURL_AUTHORIZATION_HEADER_ALLOWED_IF_REDIRECT` bleibt `IF_SAME_HOST`, §4.4).

**Endpunkt [P\*]:** `eodata.dataspace.copernicus.eu` wird per DNS auf zwei Betreiber verteilt (CloudFerro, Open Telekom Cloud). Für `gateway` ist das ein Host der Allowlist; die Prüfung privater Adressen bleibt (B8).

### 6.2 Weitere Anbieter (Ausblick)

Ein Key je Anbieter heißt: Jede Zeile in `providers.yaml` legt die Art fest. Aus `adr/0027` §3 [P\*][S], nicht neu geprüft:

| Anbieter | geeignete Art | Hinweis |
|---|---|---|
| NASA Earthdata | Nutzer-Token (60 Tage) | Datenhosts leiten auf den Anmeldedienst um; R-Z verlangt eine eigene Auslegung; zuerst W2a/W4 nach `adr/0027` |
| CDS/ADS (ECMWF) | persönlicher API-Token | Aufträge über eine Warteschlange, kein Kachelzugriff; Annahme der Bedingungen je Datensatz durch den Kontoinhaber |
| Copernicus Marine | nur Benutzer/Passwort | scheidet aus (nie ein Passwort, `adr/0027` §4.4) |
| EUMETSAT | Consumer-Key/Secret → Token | Lizenz je Produkt offen |

Jeder weitere Anbieter kommt mit eigener kleiner Vorlage (Art, Prüfweg, Bedingungen); dieses ADR legt nur das Muster fest.

### 6.3 Prüfung

| Zeitpunkt | was | Folge |
|---|---|---|
| **Eingabe** | eine Anfrage des Prüfwegs (§6.1), synchron | `valid` → speichern; sonst nicht speichern, Text „Key rejected by <provider>“ |
| **Öffnen der Seite** | `GET /keys`; ist `checked_at` älter als 6 h, prüft `api` neu | Status ins Schloss |
| **Suche** | keine Prüfung: Katalog und Items liest die Plattform anonym (§8.4) | — |
| **Kachel, Statistik, Zuschnitt** | keine eigene Prüfung; `401`/`403` der Quelle setzt `invalid` | Kachel `403` mit `X-EarthX-Locked: <provider>`; Schloss geht zu |
| **vor dem Job** | Prüfung, dazu `expires_at` gegen geschätzte Laufzeit | sonst `409` mit Text, kein Auftrag |
| **periodisch ohne Nutzer** | **keine** | Die Plattform fragt nie im Namen eines Nutzers, der nicht da ist (Datenschutz, Kontingent) |

- Höchstens eine Prüfung je Key und 10 min; höchstens 5 Eingaben je Sitzung und Stunde und je IP und Stunde (Prüforakel, §9 T6).
- Auslegung von „laufend“: bei jedem Gebrauch und spätestens alle 6 h, solange die Seite offen ist. Ein täglicher Lauf über alle Keys ist F5 Option 2.

### 6.4 Ablauf während eines Jobs

- Ein S3-Schlüssel läuft an einem festen Tag ab; die Prüfung vor dem Job vergleicht ihn mit der Laufzeit. Ein Token mit kurzer Laufzeit (OAuth) erneuert das Kind selbst im Speicher, ohne Rückweg zur Plattform.
- Antwortet die Quelle mitten im Lauf `401`/`403`: Das Kind meldet `("failed", "credential_rejected")`. Neue Fehlerart, **nicht** in `RETRYABLE`: Ein zweiter Versuch mit demselben Key scheitert gleich. Die Hülle setzt die Zeile in `identity` auf `invalid`, löscht die Freigabe und verwirft Teildateien wie bei jedem Fehler.
- Text am Job: „Key for <provider> was rejected during the run. Renew it in the Data catalogue and run again.“
- `429` der Quelle (Kontingent) ist kein Key-Fehler: wie heute mit Warten und Wiederholen; ist das Monatskontingent erschöpft, eigene Fehlerart `quota_exhausted` mit Text „Quota at <provider> exhausted“ (`adr/0027` §4.4).

---

## 7. Punkt 3: Cache und Ergebnisse

### 7.1 Optionen

| | Wer bekommt Daten aus dem Cache | Kontingent | Bedingungen | Aufwand |
|---|---|---|---|---|
| **C1** je Nutzer, auch im Prozess | nur die Sitzung, die gelesen hat | jede Sitzung liest selbst; kalte Kacheln für jeden | sicher | Cache-Schlüssel mit Sitzungsbezug; das widerspricht §5.5 („nichts aus dem Key im Schlüssel“) nur, wenn der Bezug aus dem Key käme, nicht bei einer zufälligen Kennung |
| **C1a** je Nutzer für alles Dauerhafte, gemeinsam nur im flüchtigen Prozesscache (**Empfehlung**) | Ergebnis-Cache und Browser je Sitzung; GDAL-Lesecache und Item-Köpfe im Prozess (Sekunden bis Minuten) für jede Sitzung mit gültigem Key | Dateien im Prozesscache einmal gelesen, alles Gespeicherte je Nutzer | hält Ottos Antwort zu `adr/0027` F6 („Cache je Nutzer bis zur Rechtsklärung“); der Prozesscache speichert nichts über die Anfrage hinaus | Sitzung im Schlüssel des Ergebnis-Caches |
| **C2** gemeinsam unter gültigen Keys desselben Anbieters | jede Sitzung mit gültigem Key dieses Anbieters | jede Datei wird einmal gelesen, mit dem Key dessen, der zuerst fragt | Lizenz erlaubt Weitergabe (§4.5); der Empfänger hat selbst ein Konto und darf dieselben Daten laden | Prüfung vor dem Cache, sonst wie heute |
| C3 gemeinsam für alle | auch ohne Key | wie C2 | macht das Schloss zur Attrappe und wäre ein Betreiberkonto durch die Hintertür (W1, `adr/0027` F5) | keiner |

**Empfehlung C1a.** Gründe [A]:

- Otto hat zu `adr/0027` F6 „Cache je Nutzer bis zur Rechtsklärung“ festgelegt. C1a hält das für alles, was die Plattform speichert.
- Die Prozesscaches von GDAL lassen sich nicht nach Nutzern trennen: Der `/vsicurl/`-Bereichscache ist prozessweit und nach Dateinamen geschlüsselt (§3). C1 hieße, sie für Key-Daten abzuschalten, und jede Kachel läse dieselben Köpfe neu, mit dem Kontingent von 4 Verbindungen (§7.3). C1a behandelt sie als flüchtigen Lesepuffer, nicht als Cache im Sinne der Antwort; das ist eine Auslegung (F6).
- Der Key ist eine Eintrittskarte zum Anbieter; wer eine hat, darf dieselben Daten ohnehin laden, und die Lizenz erlaubt Weitergabe (§4.5). Nach dem Rechtsrat (F9) ist C2 der nächste Schritt: Ergebnis-Cache gemeinsam unter gültigen Keys.

### 7.2 Je Ebene (`architekturplan.md` 12.3)

| Ebene | Regel für Key-Daten |
|---|---|
| HTTP/CDN | jede Antwort mit Daten (Kachel, Quicklook, Statistik, Zuschnitt) `Cache-Control: private, no-store` wie `adr/0024` R7. Ohne gültigen Key `403` ohne Daten. Ob der Browser später doch cachen darf (`private` ohne `no-store`, schnellere Karte), gehört zu C2 |
| Prozess (GDAL, Region-Cache, Item-Köpfe) | gemeinsam als flüchtiger Lesepuffer (C1a), aber nur nach der Prüfung; ein Lesevorgang ohne `Credential` kommt an Key-Hosts nie bis zum Cache, weil `gateway` ihn vorher ablehnt |
| Anwendung: Item-Suchen, Auswahl-IDs | unverändert: Metadaten liest die Plattform anonym; die **Auswahl-ID** (`adr/0032` §10.2) ist ein Hash der Item-Liste mit Datensatz und Darstellung und enthält nichts vom Key. Eine Kachel unter einer Auswahl-ID eines Key-Datensatzes prüft den Key wie jede andere |
| Ergebnis (Rezept-Hash) | je Sitzung (C1a): Rezept-Hash plus Sitzungskennung als Schlüssel; nie ein Treffer aus der Sitzung eines anderen. Mit C2 gemeinsam unter gültigen Keys |
| Übersicht (Pyramide) | **keine** (§7.4) |

**Fertige Ergebnisse** im Objektspeicher sind bearbeitete Daten mit eigener Ablauffrist. Sie zu zeigen, liest nichts mehr beim Anbieter. Vorschlag: Ein Ergebnis-Link, den der Nutzer selbst weitergibt, wirkt wie heute auch ohne Key (Weitergabe durch den Nutzer, kein Cache der Plattform; Auslegung); `ATTRIBUTION.txt` nennt „Contains modified Copernicus Sentinel data [Jahr]“ (§4.5) [A]. Teil von F6.

### 7.3 Kontingente des Anbieters

- **4 Verbindungen je Konto** (§6.1) sind die enge Stelle: Eine Kartenansicht fordert 10–30 Kacheln gleichzeitig an [A]. Ohne Grenze je Key antwortet CDSE mit Drosselung oder Fehlern, und die Karte zeigt Lücken.
- Deshalb `connections_per_key` in `providers.yaml` (Vorgabe 4), durchgesetzt wie die Grenze je Host aus M5-36: ein Zähler je Key und Prozess, geteilt durch `EARTHX_SOURCE_INSTANCES`; Anfragen warten statt abgelehnt zu werden (M5-36 §5.3). Ein Zähler je Prozess sieht den Worker nicht: Ohne Teilung kämen 4 im `tiler` und 4 im Job zusammen. Vorschlag: feste Teilung je Prozesstyp (Kacheln 2, Job 2), bis ein Zähler je Key in Postgres (Muster Ortssuche, M5-35) oder der Egress-Proxy (M6) cluster-weit zählt.
- **Bandbreite und Volumen:** 20 MB/s je Verbindung, 12 TB in 30 Tagen; danach 1 MB/s und eine Verbindung. Für Kacheln reicht das bei Weitem [A]; ein SLC-Job über viele Szenen kann einen Nutzer in die Drosselung bringen. Die Kostenschätzung vor dem Job nennt deshalb die Menge, die er bei CDSE liest (`adr/0032` §10.3, „Kostenschätzung statt Grenze“).
- **Der Kontingentverbrauch gehört dem Nutzer:** Ein Treffer im Lesepuffer des Prozesses (C1a) verbraucht nichts; eine Lücke liest mit dem Key des Fragenden, nie mit dem eines anderen (T7).

### 7.4 Pyramiden und Ersatz (`adr/0032`)

- Eine Pyramide entsteht nach der Materialisierung, ohne Nutzer (`adr/0032` F1 = 2). Für Key-Daten gibt es dann keinen Key, mit dem sie gebaut werden könnte, außer dem eines zufälligen Nutzers (dessen Kontingent für alle verbraucht würde) oder einem Betreiberkonto (ausgeschlossen). **Keine Pyramide aus Nutzer-Keys** [A].
- Szenen-Datensätze (Sentinel-1) brauchen nach `adr/0032` ohnehin keine Pyramide; unter `min_zoom` gelten das Budget je Kachel und die Übersichten der Dateien. Ob die Messdateien in den SAFE-Produkten von CDSE innere Übersichten haben, ist offen (Messpunkt M3); ohne sie wird jede grobe Kachel teuer.
- **„Nie verschwindet ein Bild“** (M5-Plan §2 Punkt 9): Unter `min_zoom` zeigt ein anonymer **Ersatz-Datensatz**, wo es einen gibt (Muster des Ersatzes aus `adr/0032`, F7 im Plan M5-30: GLO-30 für swissALTI3D). Für vollständiges GRD von CDSE wäre das Sentinel-1 GRD aus Earth Search (DS-04), mit der Marke „Overview“ (UI-08) und der Quellenzeile des Ersatzes. Ohne Ersatz: Coverage, als ausdrückliche Ausnahme (F7).

---

## 8. Punkt 4: Registry und Oberfläche

### 8.1 Datensatz

- `access.account: free_account`, `access.account_provider: cdse`, `access.account_paths: [W3]`.
- **W3 bekommt die Bedeutung** „Key des Nutzers auf der Plattform, an die Sitzung gebunden (dieses ADR), nach M6 an das Konto“. Das ersetzt die Zeile W3 in `adr/0027` §4 nicht, sondern zieht sie vor; `adr/0027` F6 ist damit erledigt.
- Startcheck (`_check_access`), neu:
  - `W3` nur mit `account: free_account` und einem `account_provider`, den `providers.yaml` kennt;
  - jeder Host aus `source.asset_hosts` ist in `hosts.yaml` Key-Host desselben Anbieters; `source.endpoint` (Katalog) ist es nicht, solange der Katalog anonym ist;
  - die B11-Stufe darf über „Katalogeintrag“ hinaus, wenn W3 gesetzt ist; die Stufe selbst bleibt Ottos Einstufung;
  - `token_free_checked_at` bleibt leer; dafür trägt `providers.yaml` den letzten erfolgreichen Prüflauf des Wegs mit Fixture-Server (Checkliste Punkt 6, Auslegung).
- Ohne W3 bleibt alles wie heute (W0).

### 8.2 `providers.yaml` und `hosts.yaml`

Neue Datei `backend/catalog/providers.yaml`, ein Eintrag je Anbieter, **ein Key je Anbieter**:

```yaml
providers:
  cdse:
    title: Copernicus Data Space Ecosystem
    credential: s3                    # Art des Keys (§6.1)
    fields: [access_key_id, secret_access_key, expires_on]
    check: s3_head                    # Prüfweg, im Code von gateway
    key_hosts: [eodata.dataspace.copernicus.eu]
    connections_per_key: 4            # Kontingent je Konto (§7)
    create_key_url: <öffentliche Doku-Seite des Anbieters>
    terms_url: <Bedingungen des Anbieters>
```

- Keine Adresse eines Token-Endpunkts im Datensatz (`adr/0027` §6.1); sie gehört, wenn je nötig, zum Prüfweg in `providers.yaml`.
- `hosts.yaml` bekommt je Key-Host `credential: cdse`. Weiter genau eine Zeile je Host (M5-36 G1); die Grenzen gelten für alle Instanzen zusammen. Neu ist die Grenze **je Key** (`connections_per_key`), weil CDSE Verbindungen je Konto zählt (§7.3).
- Startcheck: Jeder `key_hosts`-Eintrag hat eine Zeile in `hosts.yaml` mit passendem `credential`, und umgekehrt.

### 8.3 Data catalogue

- **Schloss statt „Account“** an Datensätzen mit `W3` (ausdrückliche Ausnahme von „keine Marken“). Zustände: zu (kein Key), offen (gültig), zu mit Warnfarbe (`invalid`/`expired`). Tooltip: „Needs a key from <provider>“ bzw. „Key rejected – click to renew“.
- Klick auf das Schloss oder die Aktion „Unlock“ öffnet ein kleines Formular **beim Datensatz**: Felder nach `providers.yaml`, ein Link „Create a key at <provider>“, Knöpfe „Unlock“ und, wenn hinterlegt, „Remove key“. Kein weiterer Text; Erklärungen im Tooltip (M5-Plan §2 Punkt 9).
- Ein Key schaltet alle Datensätze des Anbieters frei: Alle Schlösser dieses Anbieters wechseln gemeinsam.
- **Gelistete Einträge** (`adr/0033`) mit Konto bleiben wie heute: Link zur Quelle, keine Marke (M5-40 F6), kein Schloss, weil sie keinen Leseweg haben. Das Schloss steht nur dort, wo Freischalten etwas bewirkt.

### 8.4 Suche und Karte ohne Key

- **Suche:** Datensätze mit Schloss erscheinen in Data catalogue, Control Panel und „Advanced search“ wie andere. Items, Footprints, Coverage und Zeitleiste kommen aus dem anonymen Katalog des Anbieters (CDSE-STAC bzw. OData-Katalog, `adr/0027` §3.1, W0).
- **Karte:** Ein Datensatz ohne Key lässt sich hinzufügen; die Ebene zeigt Coverage und Footprints, das Raster bleibt aus, die Layer-Zeile trägt das Schloss. Das Frontend fordert ohne gültigen Key keine Kacheln an; fordert jemand sie direkt an, antwortet der `tiler` `403` mit `X-EarthX-Locked: cdse`.
- **Processing:** Datensätze mit Schloss sind im Panel sichtbar, aber gesperrt (Tooltip); `api` lehnt einen Auftrag ohne gültigen Key mit `409` ab.
- **Permalink:** Ein Link mit einem solchen Datensatz öffnet beim Empfänger mit Schloss, solange er keinen Key hat. Kein Key reist mit.
- **Download der Originale:** „Download full scene(s)“ bleibt für diese Datensätze der Link zur Quelle (W0). Ein Download über die Plattform wäre ein Byte durch das eigene Backend (`architekturplan.md` 6.4); W2b scheitert bei CDSE an PKCE und CORS (`adr/0027` §3.1).

### 8.5 Was die Registry nicht bekommt

- Keinen Key, keine Kennung eines Nutzers, kein Beispiel-Key, auch nicht in Fixtures (Fangwerte nur im Testcode, erkennbar unecht).

---

## 9. Punkt 5: Bedrohungen im öffentlichen Repo

Das Repo ist öffentlich: Jeder kennt Code, Tabellen, Cookie-Name und Prüfwege. Sicherheit darf an nichts davon hängen [A].

| # | Bedrohung | Weg | vor M6 nötig | was M6 dazubringt |
|---|---|---|---|---|
| T1 | **Abfluss der Datenbank** (Dump, Backup, SQL-Lücke) | Tabelle in `identity` | geteilter Schlüssel: Chiffrat ohne Cookie und Instanzschlüssel nutzlos; Sitzungskennung nur als Hash. **Ausnahme:** Die Freigaben laufender Jobs liegen nur unter dem Instanzschlüssel (§5.4); Datenbank plus Instanzschlüssel öffnen sie. Deshalb kurz befristet (≤ 24 h) und am Ende des Laufs gelöscht | verwaltetes Postgres mit Verschlüsselung, Audit |
| T2 | **Einbruch in einen Prozess** (präparierte Rasterdatei, RCE im `tiler`) | Keys der laufenden Anfragen im Speicher | Ein Prozess hält nur die Keys der Anfragen, die er gerade bedient (Cache ≤ 60 s); Jobs in eigenem Kind je Lauf. `architekturplan.md` 11 („Reader in Prozessen ohne Secrets“) gilt für Key-Daten **nicht mehr**: F3 | getrennte Pools für Key-Daten, Egress-Proxy |
| T3 | **XSS** im Frontend | Skript in der Seite | Key nach der Eingabe nie mehr im JavaScript; `HttpOnly`; **CSP** (heute keine, §3) vor dem ersten Key | — |
| T4 | **Leck über Logs, Fehler, URLs, Dateien** | GDAL-Meldungen, `UpstreamError`, Provenienz | §5.5 mit Fangwert-Test; `CPL_CURL_VERBOSE` aus; Fehlerauszug weg | zentrale Log-Pipeline mit Filter |
| T5 | **Sitzungsklau, CSRF** | Cookie | `__Host-`, `Secure`, `SameSite=Strict`, JSON-Pflicht | Bindung an Login, kurze Sitzungen |
| T6 | **Prüforakel** für gestohlene Keys | `PUT /keys` | Grenzen je Sitzung und IP (§6.3), gleiche Antwort für jeden Fehler | Rate Limits je Nutzer |
| T7 | **Kontingent anderer verbrauchen** | falscher Key an der Anfrage: Faden-Wiederverwendung, globale GDAL-Optionen, geteilte Caches, falsche Freigabe am Job | Key je Lesevorgang über `rasterio.Env`, nie global; Freigabe an Lauf-ID; Cache nur hinter der Prüfung (§7); Test mit zwei Fangwerten, die sich nie mischen | Quotas je Nutzer |
| T8 | **Weiterleitung** an einen fremden Host | Quelle oder DNS leitet um | Nachweis fällt bei Weiterleitungen über `httpx` weg; bei GDAL nur über dessen Einstellung und Test (§5.4); S3-Signatur gilt nur für den Host (§6.1) | Egress-Proxy erzwingt die Hosts (B8 Stufe 2) |
| T9 | **Böser Betreiber** eines Forks (AGPL) sammelt Keys | eigene Instanz | nicht zu verhindern; deshalb nur begrenzte, widerrufbare Keys mit Ablauf, nie das Passwort; Tooltip am Formular „Use a key with an expiry date“ (Wortlaut Vorschlag) | — |
| T10 | **Sperre durch den Anbieter** (viele Konten von einer IP, Kontingent) | Plattform-IP | Grenze je Key (`connections_per_key`) und je Host (`hosts.yaml`), `User-Agent` der Instanz | Egress-Proxy mit Grenzen je Ziel |
| T11 | **Missbrauch als Proxy** (eigener Key, große Mengen über die Plattform) | Kacheln, Zuschnitt, Jobs | bestehende Grenzen (Budget je Kachel, Größendeckel, Job-Grenzen); Kontingent trägt der Nutzer selbst | Processing Units, Quotas |
| T12 | **Secret der Instanz im Repo** | Vorgabewert, Fixture, Compose | kein Vorgabewert; Start ohne Schlüssel scheitert; lokal erzeugt wie Objektspeicher-Schlüssel; Secret-Scan der CI deckt die Datei mit ab | KMS |

**Datenschutz [A]:** Fremde Zugangsdaten bei der Plattform sind ein eigenes Schutzgut (`adr/0027` §6.3). Vor M6 ohne Login ist die Sitzung kein Konto, aber der Key ist ein personenbezogenes Datum des Nutzers bei der Quelle. Nötig vor dem ersten öffentlichen Betrieb: Abschnitt in der Datenschutzerklärung, Löschfrist (30 Tage, §5.2), Löschen auf Knopfdruck. Otto hat zu `adr/0027` F7 festgelegt: Rechtsrat und Datenschutz-Folgenabschätzung **vor W3**. Dieses ADR schlägt vor, das auf „vor dem öffentlichen Betrieb“ zu verschieben, weil die lokale Umsetzung bei Otto nur seinen eigenen Key berührt. Das ändert eine Antwort Ottos (§12, F9).

**Rechtsfrage (`adr/0027` F7):** Ob die Plattform „im Namen“ des Nutzers bei CDSE lesen darf, ist nach den gelesenen Bedingungen nicht geregelt (`adr/0027` §3.1). Für die lokale Umsetzung bei Otto ist das unkritisch; vor dem öffentlichen Betrieb Rechtsrat (F9).

---

## 10. Punkt 6: Schnitt der Umsetzung

Je Aufgabe höchstens zwei PRs (M5-Plan §2 Punkt 11). Nummern ab M5-44 (auf `main` vergeben bis M5-43).

| Aufgabe | Inhalt | Stufe | Modell | PRs | hängt ab von |
|---|---|---|---|---|---|
| **M5-44** | Registry: Lader und Startcheck für `providers.yaml`, `credential` in `hosts.yaml` und `W3` (geprüft an Fixtures; echte Zeilen erst mit dem ersten Datensatz in M5-47, weil eine Host-Zeile ohne vollen Eintrag ein Ladefehler ist, M5-36 G1), Feld `earthx:access` in der Collection (Anbieter, Weg); Frontend: Schloss statt „Account“, Formular ohne Speichern (gesperrt, Tooltip) | B | Opus, mittel | 1 | Entscheidung zu diesem ADR |
| **M5-45** | Ablage: Schema in `identity`, AES-GCM mit geteiltem Schlüssel, Cookie, Routen `/keys`, Frist und Aufräumen, Grenzen gegen Prüforakel, CSP; Frontend-Formular mit Speichern und Status | B | **Opus, hoch** (Sicherheit, Projektplan M6-Zeile) | 2 (Backend, Frontend) | M5-44 |
| **M5-46** | `gateway`: Typ `Credential`, Key-Hosts aus der Registry, Weglassen bei Weiterleitung, `/vsis3/` nur für Key-Hosts, GDAL je Lesevorgang, kein Fehlerauszug, Prüfweg `s3_head` gegen einen Fixture-Server, Fangwert-Tests | B | **Opus, hoch** | 1–2 | Antworten F4; Messpunkte M1–M3 |
| **M5-47** | Kacheln mit Key: Prüfung vor jedem Cache, `private`, Grenze je Key, `403` mit `X-EarthX-Locked`; erster CDSE-Datensatz (Auswahl und Lizenz durch Otto), Ersatz unter `min_zoom` | B | Opus, hoch | 2 | M5-45, M5-46; Datensatz-Onboarding |
| **M5-48** | Jobs mit Key: Freigabe je Lauf, Import `jobs → identity` (nach F3), Weg über die Pipe, Fehlerarten `credential_rejected` und `quota_exhausted`, Provenienz `access: user_key` | B | Opus, hoch | 1–2 | M5-47; F3 |

- **Bezug zu M5-31 (Radar):** M5-31 entscheidet die Kette und die Eingaben. Braucht sie vollständige GRD oder SLC von CDSE, setzen die Radar-Operatoren auf diesen Daten M5-48 voraus. M5-31 kann parallel entschieden werden; Operatoren, die mit dem anonymen GRD aus AWS auskommen (DS-05a bis DS-05d), hängen nicht daran.
- **UI-07** (Reiter im Processing-Panel) wartet laut M5-Plan auf die Entscheidung zu diesem ADR, nicht auf die Umsetzung: Der Reiter „Radar“ zeigt Operatoren auf Key-Daten mit Schloss, bis M5-48 da ist.
- **M6:** Login bindet die Sitzung an ein Konto (beim ersten Login übernimmt das Konto die Zeilen der Sitzung, auf Bestätigung); Quotas und Rate Limits je Nutzer; Egress-Proxy mit Key-Hosts; Instanzschlüssel aus einem KMS; Audit-Log der Key-Nutzung (Zeitpunkt, Anbieter, nie Inhalt); Datenschutz-Folgenabschätzung; Lasttest mit Key-Daten.
- **Doku-Nachträge** (mit M5-44, erster Commit): `adr/0027` (F6, §4 W3, §6.1, R-Z nach F4), `projektuebersicht.md` Prinzip 2 und §6, `KLAERUNGEN` B8, `architekturplan.md` 3.1 (Zeile `identity`, ggf. `jobs`), 6.5, 11, 12.3; der Satz in `ENTSCHEIDUNGEN` nur durch Otto (§12).

---

## 11. Optionen im Überblick

| Option | Ablage | Jobs mit Key | Regeländerung | Aufwand |
|---|---|---|---|---|
| **1** (**Empfehlung**) | A3: Server, Sitzung, geteilter Schlüssel | ja, Freigabe je Lauf | `ENTSCHEIDUNGEN` §1/§3 (Otto), B8, Prinzip 2, R-Z (S3), `jobs → identity`, `architekturplan.md` 6.5 und 11 | mittel (fünf Aufgaben) |
| **2** | A1: nur Browser | nein; nur Runner (W4) | wie 1 ohne `jobs → identity` | klein bis mittel; Radar-Kette auf CDSE nur lokal |
| **3** | A4: Server ohne Sitzungsbindung | ja | wie 1 | mittel; schwächer bei T1 und T3 |
| **4** | W3 erst nach M6 (`adr/0027` F6 bleibt) | nach M6 | keine | verschiebt M5-31 auf CDSE-Daten |

---

## 12. Widersprüche zu bestehenden Regeln

Ottos Vorgabe vom 11.11.2026 ändert Regeln mit höherem Rang. Dieses ADR schlägt nur den Wortlaut vor; `ENTSCHEIDUNGEN` ändert nur Otto.

| Regel | heute | Vorschlag |
|---|---|---|
| `ENTSCHEIDUNGEN` §1 | „Die fertige Plattform enthält nichts, was einen Token braucht.“ | Nachtrag: „Ausnahme (Otto, 11.11.2026): Datensätze, die der Nutzer mit seinem eigenen Key freischaltet (`adr/0034`). Die Plattform hat keinen eigenen Key.“ |
| `ENTSCHEIDUNGEN` §2 | Asset-Proxy „ohne Token-Injektion“ | gilt weiter für den Asset-Proxy; der Nachweis des Nutzers geht nur über `gateway` an Key-Hosts (`adr/0034`) |
| `ENTSCHEIDUNGEN` §3 | Token pro Connector „fernes Zukunftsthema“; Token-Logik (`auth.py`, MAAP-OIDC, Token in der GDAL-Umgebung) nicht übernehmen | Nachtrag: Token pro Connector nach `adr/0034`, Nachweis des Nutzers je Lesevorgang an GDAL (nie prozessweit); `auth.py` und MAAP-OIDC bleiben ausgeschlossen |
| Prinzip 2 | „Nur token-freie Datenquellen“ | „Token-freie Quellen zuerst; Quellen mit Key nur mit dem Key des Nutzers (`adr/0034`)“ |
| `projektuebersicht.md` §6 | Token-Verwaltung „fernes Zukunftsthema“; Login kommt früher als die Token-Verwaltung | vorgezogen nach `adr/0034`, vor dem Login an die Sitzung gebunden |
| `architekturplan.md` 1.2, 6.1, 13 | nichts, was einen Token braucht; „Auth … in der Zielarchitektur zunächst nicht vorhanden“; `auth.py` nicht übernehmen | Nachträge wie `ENTSCHEIDUNGEN` §1/§3 |
| M5-Plan §2 Punkt 3 und 6 | nur frei und ohne Schlüssel; kostenlose Konten nur als Katalogeintrag | durch Punkt 10 (Otto, 11.11.2026) geändert; Nachtrag mit M5-44 |
| M5-Plan §2 Punkt 9 | nie eine leere Karte | Ausnahme Coverage unter `min_zoom` ohne Ersatz (F7) |
| `KLAERUNGEN` B8 | „Token-Logik ist nicht Teil des Gateways“ | `gateway` setzt den Nachweis des Nutzers nur für Key-Hosts aus der Registry; es holt und speichert keinen |
| `adr/0027` F6, §4.4 | W3 eigener ADR nach M6; Login als Voraussetzung; Audit-Log; **Cache je Nutzer bis zur Rechtsklärung** | W3 vor dem Login an die Sitzung gebunden; Audit mit M6; Cache nach C1a (§7.1): dauerhaft je Nutzer, Lesepuffer im Prozess gemeinsam (Auslegung, F6) |
| `adr/0027` F7 | Rechtsrat und Datenschutz-Folgenabschätzung vor W3 | vor dem öffentlichen Betrieb (F9) |
| `adr/0027` §6.1 | `free_account`: kein Kartenlayer, kein Processing; Startcheck „höchstens Katalogeintrag“ | mit `W3` Kartenlayer und Processing für Sitzungen mit gültigem Key |
| `adr/0027` R-Z | Nachweis nur an den Anmelde-Host | Auslegung für S3 (F4): Signatur an den Key-Host, Secret verlässt den Prozess nie |
| `architekturplan.md` 6.5 | nur `https` | `/vsis3/` für Key-Hosts aus der Registry, weiter über `https` |
| `architekturplan.md` 11 | „Reader in Prozessen ohne … Secrets“ | gilt für Key-Daten nicht; Ausgleich nach §9 T2 |
| `.importlinter` | `jobs` darf `identity` nicht | `jobs → identity` (nur Freigaben), F3 |

---

## 13. Fragen an Otto

**F1 — Wo liegt der Key vor dem Login?**
1. Auf dem Server, verschlüsselt, an eine Sitzung des Browsers gebunden; entschlüsseln nur mit Cookie und Schlüssel der Instanz (A3) **(Empfehlung)**
2. Nur im Browser (A1); Jobs mit Key nur im lokalen Runner
3. Auf dem Server ohne Bindung an die Sitzung (A4)
4. Gar nicht vor M6 (`adr/0027` F6 bleibt)

**F2 — Frist und Schlüssel der Instanz?**
1. 30 Tage ohne Nutzung, höchstens bis zum Ablauf des Keys, löschbar per Knopf; Schlüssel der Instanz lokal erzeugt wie die Objektspeicher-Schlüssel, in der Cloud aus einem KMS (M6) **(Empfehlung)**
2. 7 Tage ohne Nutzung
3. Nur bis zum Schließen des Browsers

**F3 — Key für Jobs?**
1. Eigene Freigabe je Lauf (nicht im Auftrag), Hülle `jobs` liest sie und gibt den Key über die Pipe ans Kind; dafür Import `jobs → identity`; R-Z so ausgelegt; Satz in `architekturplan.md` 11 angepasst **(Empfehlung)**
2. Keine Cloud-Jobs mit Key; nur lokaler Runner
3. Key verschlüsselt mit dem Auftrag in der Queue (bricht R-Z)

**F4 — Art des Keys bei CDSE?**
1. Zuerst nur der S3-Schlüssel des Nutzers; `/vsis3/` für Key-Hosts in `gateway`; R-Z: Signatur an den Key-Host erlaubt, nie Weiterleitung, nie vorsignierte URLs **(Empfehlung)**
2. OAuth-Client des Nutzers (Token an Download-Hosts über `https`)
3. Beide gleich

**F5 — „Laufend geprüft“?**
1. Bei Eingabe, beim Öffnen der Seite (höchstens alle 6 h), vor jedem Job und sofort bei Ablehnung durch die Quelle; nie ohne den Nutzer **(Empfehlung)**
2. Dazu täglich für alle hinterlegten Keys auf dem Server
3. Nur bei Eingabe und bei Ablehnung

**F6 — Cache mit Key-Daten (`adr/0027` F6: je Nutzer bis zur Rechtsklärung)?**
1. Alles Gespeicherte je Nutzer, nur der flüchtige Lesepuffer im Prozess gemeinsam hinter der Prüfung (C1a); ein Ergebnis-Link, den der Nutzer weitergibt, wirkt auch ohne Key **(Empfehlung)**
2. Streng je Nutzer, auch im Prozess (C1; Lesepuffer für Key-Daten aus)
3. Gemeinsam unter gültigen Keys desselben Anbieters schon jetzt (C2)

**F7 — Unter `min_zoom` (`adr/0032`)?**
1. Keine Pyramide aus Nutzer-Keys; anonymer Ersatz-Datensatz, wo es einen gibt (z. B. Sentinel-1 GRD aus AWS), sonst Coverage als Ausnahme von „nie verschwindet ein Bild“ **(Empfehlung)**
2. Pyramide mit dem Key dessen, der zuerst schaut
3. Keine Ausnahme: Key-Datensätze erst ab `min_zoom` hinzufügbar

**F8 — Oberfläche?**
1. Wie §8.3–§8.4: Schloss statt „Account“, Formular beim Datensatz, ohne Key gelistet mit Coverage, Raster und Processing gesperrt; gelistete Einträge ohne Schloss **(Empfehlung)**
2. Ohne Key gar nicht auf die Karte
3. Formular zentral (Einstellungen) statt beim Datensatz

**F9 — Schnitt und Bedingungen?**
1. M5-44 bis M5-48 wie §10; Rechtsrat und Datenschutz-Folgenabschätzung vor dem öffentlichen Betrieb statt vor W3 (ändert `adr/0027` F7) **(Empfehlung)**
2. Jobs mit Key (M5-48) vor den Kacheln, wegen M5-31
3. Wie `adr/0027` F7: Rechtsrat und Folgenabschätzung vor jeder Umsetzung

**F10 — Regeltexte?**
1. Otto übernimmt die Vorschläge aus §12 in `ENTSCHEIDUNGEN`; die übrigen Nachträge macht M5-44 als ersten Commit **(Empfehlung)**
2. Otto formuliert selbst; Nachträge danach

---

## 14. Was offen bleibt

**Messpunkte für Otto** (mit eigenem CDSE-Konto, lokal, nie in CI oder Cloud-Sitzungen; keine Adresse, keine Item-ID und kein Key ins Repo). Vor M5-46:

- **M1 Prüfweg:** Ein kleines, für jedes Konto lesbares Objekt in `eodata` wählen; mit eigenem S3-Schlüssel `HEAD` darauf: `200`? Mit abgelaufenem bzw. gelöschtem Schlüssel: `403` mit welchem Code? Steht die Access-Key-ID im Fehlertext?
- **M2 Bereichslesen:** In einem GRD- und einem SLC-Produkt: liegen Annotation (`annotation/*.xml`, `calibration/`, `noise`) und Messdateien entpackt im Bucket, und antworten sie auf Bereichsanfragen (`206`)?
- **M3 Übersichten:** Haben die Messdateien (`measurement/*.tiff`) Kacheln und innere Übersichten (`gdalinfo`), oder sind es Streifen ohne Übersicht? Davon hängen `min_zoom` und Kosten grober Kacheln ab.
- **M4 Weiterleitungen und Grenzen:** Leitet `eodata` je nach Betreiber weiter (DNS oder `307`)? Was antwortet es bei mehr als 4 gleichzeitigen Verbindungen (warten, `429`, `503`)?
- **M5 OAuth-Client (nur bei F4 = 2 oder 3):** Öffnet ein Token eines Sentinel-Hub-Clients den OData-Download (`$value`) oder `zipper`?

**Technik:**

- Ob GDAL Nachweise zwischen Fäden mitnimmt (Handle-Cache, Verbindungen) oder in Meldungen zeigt (Test in M5-46 mit Fixture-Server und zwei Fangwerten).
- Wie viele Datenbankabfragen eine Kachel mit Key kostet und ob der Cache von 60 s nötig ist (Messung in M5-47).
- Grenze je Key für alle Instanzen: je Prozess geteilt durch `EARTHX_SOURCE_INSTANCES` wie M5-36 PR 2, cluster-weit exakt erst mit dem Egress-Proxy (M6).

---

## 15. Quellen

Gelesen von einem Hilfsagenten am 16.11.2026. Nicht erreichbar waren `documentation.dataspace.copernicus.eu`, `forum.dataspace.copernicus.eu`, `rfc-editor.org`, `datatracker.ietf.org`, `cheatsheetseries.owasp.org` und `developer.mozilla.org`; dafür die Quelltexte auf GitHub. Gesperrt (Auftrag, keine Anfrage an Quellen): alle API- und Datenhosts von CDSE und Earthdata.

**P\* (über das Abrufwerkzeug gelesen):**

- CDSE-Doku (Branch `publish`):
  - https://raw.githubusercontent.com/eu-cdse/documentation/publish/APIs/Token.qmd
  - https://raw.githubusercontent.com/eu-cdse/documentation/publish/APIs/S3.qmd
  - https://raw.githubusercontent.com/eu-cdse/documentation/publish/APIs/OData.qmd
  - https://raw.githubusercontent.com/eu-cdse/documentation/publish/Quotas.qmd
  - https://raw.githubusercontent.com/eu-cdse/documentation/publish/APIs/SentinelHub/Overview/Authentication.qmd
  - https://raw.githubusercontent.com/eu-cdse/documentation/publish/APIs/SentinelHub/Overview/RateLimiting.qmd
  - https://raw.githubusercontent.com/eu-cdse/documentation/publish/APIs/openEO/authentication/client_credentials.qmd
- CDSE-Bedingungen: https://dataspace.copernicus.eu/node/10; Änderung §9: https://dataspace.copernicus.eu/node/1031
- OWASP:
  - https://raw.githubusercontent.com/OWASP/CheatSheetSeries/master/cheatsheets/HTML5_Security_Cheat_Sheet.md
  - https://raw.githubusercontent.com/OWASP/CheatSheetSeries/master/cheatsheets/Cryptographic_Storage_Cheat_Sheet.md
  - https://raw.githubusercontent.com/OWASP/CheatSheetSeries/master/cheatsheets/Secrets_Management_Cheat_Sheet.md
- IETF OAuth 2.0 for Browser-Based Applications (Entwurf, Arbeitsstand): https://raw.githubusercontent.com/oauth-wg/oauth-browser-based-apps/main/draft-ietf-oauth-browser-based-apps.md
- MDN `SubtleCrypto.generateKey`: https://raw.githubusercontent.com/mdn/content/main/files/en-us/web/api/subtlecrypto/generatekey/index.md
- PrivateBin: https://raw.githubusercontent.com/PrivateBin/PrivateBin/master/README.md
- `cryptography` Fernet: https://raw.githubusercontent.com/pyca/cryptography/main/docs/fernet.rst
- Python Logging Cookbook: https://raw.githubusercontent.com/python/cpython/main/Doc/howto/logging-cookbook.rst
- Pydantic `SecretStr`: https://raw.githubusercontent.com/pydantic/pydantic/main/pydantic/types.py
- Sentry Scrubber: https://raw.githubusercontent.com/getsentry/sentry-python/master/sentry_sdk/scrubber.py
- GDAL:
  - https://raw.githubusercontent.com/OSGeo/gdal/master/port/cpl_http.cpp (bis Zeichen 100 000)
  - https://raw.githubusercontent.com/OSGeo/gdal/master/doc/source/user/configoptions.rst
  - https://raw.githubusercontent.com/OSGeo/gdal/master/doc/source/user/virtual_file_systems.rst
- Grafana:
  - https://raw.githubusercontent.com/grafana/grafana/main/docs/sources/setup-grafana/configure-security/configure-database-encryption/_index.md
  - https://raw.githubusercontent.com/grafana/grafana/main/pkg/services/datasources/models.go
- QGIS Authentifizierung: https://raw.githubusercontent.com/qgis/QGIS-Documentation/master/docs/user_manual/auth_system/auth_overview.rst

**S (Suchtreffer, Wortlaut nicht geprüft):**

- CDSE-Forum:
  - https://forum.dataspace.copernicus.eu/t/download-products-in-odata-with-clientid-and-client-secret/1284
  - https://forum.dataspace.copernicus.eu/t/unauthorized-oauth-token-401-when-downloading-s1-orbits-from-catalogue-dataspace-copernicus-eu-download/257
  - https://forum.dataspace.copernicus.eu/t/is-the-access-token-lifetime-10-minutes/1017
  - https://forum.dataspace.copernicus.eu/t/invalidaccesskeyid-on-non-expired-key-and-other-queries/4344
  - https://forum.dataspace.copernicus.eu/t/s3cmd-403-error-when-listing-eodata/992
- sentinelhub-py, Token-Laufzeit: https://sentinelhub-py.readthedocs.io/en/latest/examples/session_sharing.html
- openEO-Föderation bei CDSE: https://documentation.dataspace.copernicus.eu/APIs/openEO/federation/backends/api.html
- RFC 9111: https://datatracker.ietf.org/doc/rfc9111/
- Sentinel Data Legal Notice: https://sentinel.esa.int/documents/247904/690755/Sentinel_Data_Legal_Notice
- Vault Transit: https://developer.hashicorp.com/vault/api-docs/v1.21.x/secret/transit
- n8n Encryption Key: https://docs.n8n.io/hosting/configuration/configuration-examples/encryption-key
- Planetary Computer SAS: https://planetarycomputer.microsoft.com/docs/concepts/sas
- curl CVE zu Bearer-Token bei Weiterleitung: https://curl.se/docs/CVE-2025-14524.html

**S (Vorwissen, nicht nachgelesen):** S3 nennt die Access-Key-ID im Fehlertext von `SignatureDoesNotMatch`; Wirkung von `Cache-Control: private`; Signatur V4 gilt rund 15 min.

**Im Repo (P):** `ENTSCHEIDUNGEN_2026-09-18.md` §1, §3, §4; `KLAERUNGEN.md` B8, B9, B13; `projektuebersicht.md` §2, §4, §6; `architekturplan.md` 3.1, 3.2, 6.4, 6.5, 7.3, 7.7, 9–12; `projektplan.md` 1.1, M6; `plans/m5/m5-discovery-und-suche.md` §2, §6; `plans/m5/m5-35-skalierbarkeit.md` §2; `adr/0024` R6–R8; `adr/0027` §3.1, §4, §6, §9; `adr/0032` §5.2, §8.4, §10.2; `.importlinter`; `backend/earthx/catalog/registry.py`; `backend/catalog/hosts.yaml`; `backend/earthx/gateway/client.py`, `errors.py`, `gdal.py`; `backend/earthx/jobs/worker.py`, `child.py`; `frontend/src/catalogue.ts`, `components/DataCatalogue.tsx`, `preferences.ts`; `frontend/vite.config.ts`.
