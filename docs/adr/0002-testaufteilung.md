# ADR 0002 — Testaufteilung: Cloud-Sitzung, CI, nur lokal

- **Status:** **Angenommen** von Otto am 2026-09-19 (E8, `docs/plans/m1-fundament.md`
  Abschnitt 1), mit der Festlegung E7 aus demselben Abschnitt (`moto` für
  Unit-Tests, MinIO nur als Service-Container in CI).
- **Datum:** 2026-09-18
- **Aufgabe:** M0 Schritt 2 laut `ENTSCHEIDUNGEN_2026-09-18.md` §6, auf Grundlage
  von `projektplan.md` 2.4.
- **Autonomiestufe:** A für das CI-Grundgerüst, C für diese Entscheidungsvorlage.
- **Grundlage:** `docs/cloud-umgebung.md` (gemessen, nicht angenommen),
  `KLAERUNGEN.md` B2, B8, B9, `architekturplan.md` 3.1, 7.3.
- **Betroffen:** `projektplan.md` 2.3, 2.4, 7; `.github/workflows/ci.yml`.

---

## 1. Kontext

Drei Orte führen Tests aus, mit unterschiedlichen Fähigkeiten:

| Ort | Kann | Kann nicht |
|---|---|---|
| Cloud-Sitzung | Python- und Node-Stack, GDAL aus Wheels, Postgres + PostGIS + pgstac | kein Geocoder, **kein Docker-Image**; EO-Quellen siehe Hinweis unten |
| GitHub Actions | dasselbe, zusätzlich Service-Container und geplante Läufe | in PR-Läufen ebenfalls keine Live-Quelle (weil wir es so wollen, nicht weil es nicht ginge) |
| Ottos Rechner | alles, inklusive MAAP-Token und echten Daten | nichts davon ist automatisierbar oder öffentlich |

> **Nachtrag 19.09.2026.** „Keine EO-Quelle" galt zum Zeitpunkt der Messung vom
> 18.09.2026. Seit der Egress-Freigabe aus `adr/0003` §11 ist Earth Search v1
> aus einer Cloud-Sitzung erreichbar (`cloud-umgebung.md` §6). An dieser
> Aufteilung ändert das nichts: Live-Zugriffe bleiben auf T-D beschränkt, und
> PR-Läufe testen weiter ohne Live-Quelle — weil wir es so wollen, nicht weil es
> nicht ginge.

Zwei Regeln stehen bereits fest und sind hier nicht zur Disposition:
Live-Zugriffe auf externe Quellen gibt es in CI nicht (`projektplan.md` 2.4), und
Fixtures sind synthetisch oder eindeutig offen lizenziert
(`ENTSCHEIDUNGEN` §4). BIOMASS und MAAP kommen weder in CI noch in
Cloud-Sitzungen noch in Fixtures vor (`ENTSCHEIDUNGEN` §3).

Die Frage ist deshalb nicht *ob*, sondern *wie* geschnitten wird — und was mit
den Tests passiert, die sich nirgends automatisieren lassen.

## 2. Entscheidung

Vier Testarten, jede mit genau einem Zuhause.

### T-A Unit- und Rechen-Tests — Cloud-Sitzung **und** CI

Reine Funktionen auf synthetischen Mini-Fixtures: Dekomposition, Stitching,
Tile-Rendering, Geometrie, Gruppierung, Konfiguration. Kein Netz, keine
Datenbank, kein Dateisystem außer `tmp_path`. Sekundenbereich.

Fixtures werden **per Skript erzeugt** und als winzige Dateien eingecheckt
(`KLAERUNGEN.md` B2): ein paar Kilobyte COG, ein Mini-Zarr. Das Erzeugungsskript
liegt daneben, damit ein Fixture nachvollziehbar bleibt und niemand raten muss,
woher die Zahlen kommen.

### T-B Vertragstests gegen die eigenen Endpunkte — Cloud-Sitzung **und** CI

Form, Felder, Typen und Statuscodes der eigenen API, gegen aufgezeichnete
Antworten **token-freier** Quellen (`KLAERUNGEN.md` B2). Die Aufzeichnungen sind
klein, bereinigt und eingecheckt; abgespielt wird über einen HTTP-Transport-Double,
nie über das Netz.

Solange es keinen token-freien Datensatz gibt (M0 Schritt 6 offen), gibt es hier
nur die Tests, die ohne jede Quelle auskommen: dass die App startet, dass die
Konfiguration lädt, dass Metadaten-Routen antworten, dass Fehlerfälle sauber
400/404/405 liefern. Genau die liegen jetzt in `backend/tests/`.

### T-C Integrationstests mit Postgres — Cloud-Sitzung **und** CI

Katalogsuche gegen pgstac, Migrationen, Datenmodell. In der Sitzung gegen das
lokale Postgres aus dem Setup-Skript, in CI gegen einen Service-Container.
Derselbe Testcode, die Verbindung kommt aus der Umgebung.

Das weicht bewusst von der Rückfallebene in `projektplan.md` 2.3 ab ("nur in
GitHub Actions"): Postgres, PostGIS und pgstac laufen in der Cloud-Sitzung
nachweislich. Tests, die zusätzlich einen **Objektspeicher** brauchen, bleiben
bis auf Weiteres CI-only oder benutzen ein Python-Double — offener Punkt.

### T-D Live-Smoke-Tests — **nur** geplant in GitHub Actions, nie in einer Sitzung

Ein kleiner Lauf gegen die echte Quelle, zeitgesteuert (`projektplan.md` 2.4).
Er beantwortet die eine Frage, die keine Aufzeichnung beantworten kann: *Ist die
Quelle noch so, wie wir sie aufgezeichnet haben?* Er läuft **nicht** im
PR-Workflow — ein PR darf nie rot werden, weil ein fremder Dienst gerade hustet
— und er läuft nicht in Claude-Sitzungen, die ohnehin nicht hinauskommen.

Er existiert noch nicht: Ohne entschiedenen Datensatz gibt es nichts zu
beproben. Er kommt mit M1.

**Nachtrag 2026-09-20 (M2-13).** Ein Live-Smoke lässt sich aus einer
Cloud-Sitzung nicht von Hand nachfahren: `gateway` verbindet absichtlich die
von `check_url` geprüfte **Adresse**, damit sich zwischen Prüfung und
Verbindung nichts bewegt (M1-03, Adress-Pinnung als Sicherheitseigenschaft,
hier **nicht** anzufassen). Die Egress-Freigabe der Sitzungsumgebung
arbeitet dagegen **namensbasiert** und weist `CONNECT` auf eine Adresse mit
`403` ab. Deshalb kommt `curl` (Name) durch, ein Aufruf von `tests_live`
oder des Produktivpfads aus der Sitzung dagegen nicht. In der CI läuft der
Live-Smoke wie vorgesehen, weil dort kein Proxy dazwischensteht. Latenzen
für einen PR werden deshalb **über `curl`** belegt, nicht über einen
Sitzungslauf des eigenen Codes. Dieser Befund wurde bereits dreimal einzeln
entdeckt (`adr/0003` §10.1, `adr/0007` §3.9/§12, `plans/m2-05-coverage.md`
§7.1); diese Zeile hält ihn an der Stelle fest, an der ihn eine künftige
Live-Smoke-Aufgabe zuerst nachschlägt, damit er nicht ein viertes Mal
entdeckt wird.

### Nur lokal bei Otto

Was sich weder in CI noch in einer Sitzung ausführen lässt, ist als solches zu
kennzeichnen (`@pytest.mark.local_only`, in `pyproject.toml` registriert) und
wird nirgends automatisch gesammelt:

- alles, was einen MAAP-Token braucht — das ist BIOMASS und verschwindet mit ihm
- alles, was echte Szenen in Originalgröße liest (Laufzeit, Bandbreite)
- der lokale Runner als Container (T2L, `architekturplan.md` 7.3): braucht ein
  Docker-Image und ist deshalb aus der Cloud-Sitzung ausgeschlossen
- visuelle Prüfung der Oberfläche

Diese Tests sind **kein Sicherheitsnetz**. Was nur lokal läuft, gilt als
ungeprüft, bis ein automatisierter Test dasselbe auf synthetischen Daten zeigt.

### Frontend

Lint (oxlint) und Typprüfung (`tsc -b`) laufen in CI und in der Sitzung.
Komponententests gibt es noch nicht; der Testrunner wird mit dem Viewer-Strang
ab M2 gewählt und ist hier nicht vorweggenommen.

## 3. Wie "kein Netz" durchgesetzt wird

Eine Regel, die nur im Dokument steht, hält nicht. Deshalb dreistufig:

1. **Testlaufzeit:** Eine autouse-Fixture in `backend/tests/conftest.py` ersetzt
   `socket.socket.connect` und `socket.getaddrinfo`. Jeder Versuch, nach draußen
   zu gehen, wird zu einem Fehler mit Hostnamen statt zu einem Timeout.
   `test_no_network.py` prüft die Fixture selbst — ein Wächter, der nicht
   bewacht wird, ist keiner.
2. **Statisch, ab M1:** HTTP-Bibliotheken dürfen nur in `gateway` importiert
   werden (`KLAERUNGEN.md` B8). Der Vertrag steht bereits in `.importlinter`.
3. **Netzwerkseitig, ab M6:** Egress-Proxy mit derselben Allowlist.

## 4. Modulgrenzen: vorbereitet, nicht scharf

`.importlinter` enthält die Verträge aus `architekturplan.md` 3.1 vollständig:
für jedes der elf Module, was es **nicht** importieren darf, plus die Isolation
von `datasets/` und die Beschränkung der HTTP-Clients auf `gateway`.

Scharf geschaltet ist nichts, aus einem einfachen Grund: Die Zielmodule gibt es
noch nicht. Heute existiert `app` als Prototyp-Paket. `lint-imports` würde nicht
einen Verstoß melden, sondern nur, dass es die Module nicht findet.

Solange gilt:

- Der CI-Job `import-boundaries` läuft **nur** auf `workflow_dispatch`, gatet
  also keinen PR.
- `backend/tests/test_module_boundaries.py` läuft bei **jedem** PR und prüft,
  dass die Verträge in `.importlinter` genau die Tabelle aus
  `architekturplan.md` 3.1 abbilden. So kann die Datei nicht unbemerkt von der
  Architektur abdriften, während sie schläft.
- Mit M1, sobald das erste Zielmodul steht, entfällt das `if` im Job.

**Offen für Otto:** Wie heißt das Wurzelpaket der Zielarchitektur?
`.importlinter` nimmt vorläufig `app` an, weil der Prototyp so heißt. Das ist
eine Zeile Änderung, aber es steht nirgends in `docs/` und ist damit nicht
entschieden.

## 5. Erwogene Alternativen

| Alternative | Warum nicht |
|---|---|
| Live-Tests auch im PR-Workflow, mit Retry | Macht die rote Ampel bedeutungslos. Ein PR wird rot, wenn *wir* etwas kaputt machen — sonst nie. |
| Integrationstests nur in CI (Rückfallebene aus 2.3) | Unnötig. Postgres, PostGIS und pgstac laufen in der Sitzung; die längere Rückkopplung würde nichts kaufen. |
| VCR-Kassetten automatisch aufzeichnen lassen | Aufzeichnen braucht einen Live-Zugriff, den eine Sitzung nicht hat. Aufzeichnungen entstehen bewusst und werden gelesen, bevor sie eingecheckt werden — das Repo ist öffentlich. |
| Import-Linter sofort scharf | Es gibt nichts zu prüfen. Ein Job, der grün ist, weil er nichts findet, erzieht zum Wegsehen. |
| Tests in einem Container laufen lassen | In der Cloud-Sitzung nicht möglich (`docs/cloud-umgebung.md` §4). |

## 6. Folgen

- Jeder Test läuft an mindestens zwei Orten oder ist ausdrücklich als `local_only`
  gekennzeichnet. Ein dritter Fall ist ein Fehler.
- Cloud-Sitzung und CI führen **denselben** Befehl aus (`ruff check backend`,
  `pytest`, `npm run lint`, `npx tsc -b`). Was in der Sitzung grün ist, ist in CI
  grün — bis auf die Service-Container.
- Der Schritt vor "fertig" aus `CLAUDE.md` ist damit ausführbar, was er in M0
  bisher nicht war.
- Kein Test braucht MAAP, BIOMASS oder ein Secret. Das ist bei der Aufnahme jedes
  neuen Tests zu prüfen.
