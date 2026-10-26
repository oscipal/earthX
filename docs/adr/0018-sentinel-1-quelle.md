# ADR 0018 — Quelle für Sentinel-1

- **Status:** Entwurf, wartet auf Otto (Fragen in §9).
- **Datum:** 2026-10-26
- **Aufgabe:** DS-01 laut `docs/plans/ds/ds-01-s1-quelle.md` (Paket DS,
  `docs/plans/ds/ds-00-paket.md`).
- **Autonomiestufe:** C. Kein Produktivcode, keine Änderung an `backend/`,
  `frontend/`, Fixtures, `.github/`, `.claude/`, `CLAUDE.md` oder den
  Lock-Dateien. Gemessen wurde mit `curl` und kurzen Skripten im
  Kratzverzeichnis der Sitzung (§11).
- **Vorab fest:**
  - Die Plattform enthält nichts, was einen Token braucht (`ENTSCHEIDUNGEN`
    §1); Onboarding-Punkt 6 verlangt den anonymen Zugriffs-Check
    (`projektuebersicht.md` §5).
  - Der Planetary Computer bleibt gesperrt, Option C aus `adr/0003` wird
    nicht weiterverfolgt, weil die SAS-Signatur technisch ein Token ist
    (`adr/0003` §6, §10.2).
  - `decomp.py` bleibt ruhend und wird nicht generalisiert; Sentinel-1 ist
    Dual-Pol (`ENTSCHEIDUNGEN` §3).
  - Unterschiede je Datensatz stehen als Daten in der Registry, nicht als Code
    je Datensatz; was nicht geht, erscheint nicht (Otto, 26.10.2026, DS-00).
- **Grundlage:** `ENTSCHEIDUNGEN_2026-09-18.md` §1, §3, §4; `KLAERUNGEN.md`
  B8, B9, B10, B11, B12; `projektuebersicht.md` §5 (Checkliste);
  `architekturplan.md` 3.1, 6.2, 7.3 (Stufe T4); `projektplan.md` M7 Paket 7g;
  `adr/0003` §6, §10, §11; `adr/0004`; `adr/0005` §5 (Regeln, CQL2);
  `adr/0007` §12; `adr/0014` §3.1; `adr/0017`.
- **Betroffen (erst mit DS-04):** Registry (`catalog/registry.py`,
  `catalog/datasets.py`), Allowlist der Umgebung, `docs/cloud-umgebung.md`,
  DS-02 (Suchfelder), DS-05 (SAR-Operatoren).

---

## Methode und Belegstufen

Belegstufen wie in `adr/0016` und `adr/0017`:

- **M:** in dieser Sitzung gemessen; die Anfrage steht in §11.
- **P:** am Primärdokument gelesen (im Repo mit Pfad und Zeile).
- **P\*:** Primärdokument über das Abrufwerkzeug eines Hilfsagenten gelesen,
  der Seiten zusammenfasst; Zitate sinngemäß.
- **S:** Suchtreffer oder Zusammenfassung, Wortlaut nicht geprüft.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Anfragen an Datenquellen:** STAC-Metadaten, Bucket-Listen und je Asset
höchstens ein Range-`GET` auf die ersten Kilobyte bzw. ein Overview-Block.
Keine AOI, keine Downloads ganzer Dateien. Item-IDs und `href` stehen nicht in
diesem Dokument.

**Messung über `gateway` — hier nicht möglich [M].** `gateway` verbindet
absichtlich zur geprüften Adresse; der Proxy der Sitzung arbeitet
namensbasiert und weist das ab. Gemessen am 26.10.2026: Earth Search und
EOPF über `gateway` → `UpstreamUnreachable`; Planetary Computer, CDSE, ASF,
CMR und DE Africa → `AddressRejected` (Name löst in der Sitzung nicht auf).
Das ist der bekannte Stand (Entscheidungslog, Zeile „`gateway` erreicht die
Quelle aus einer Cloud-Sitzung nicht“, offen). Die Befunde zum anonymen
Zugriff unten sind deshalb mit `curl` über den Proxy gemessen, ohne
Anmeldung, ohne Kopfzeilen außer `Range`. Der Check über `gateway` selbst
gehört in den Live-Smoke von DS-04 (CI ohne Proxy) und in Ottos Prüfung
(§11 E).

---

## 0. Kurzfassung

TODO

---

## 1. Kontext und Frage

Otto möchte Sentinel-1 anbieten, mit eigener Suche (Orbitrichtung,
Polarisation, Aufnahmemodus) und eigener Prozessierung (DS-01 §1). Die
naheliegenden Quellen galten als nicht token-frei: S1 GRD bei AWS als
„Requester Pays“, Planetary Computer mit SAS-Token, CDSE mit Anmeldung.

**Frage:** Welche Quelle erfüllt die Onboarding-Checkliste — vor allem den
anonymen Zugriffs-Check — und liefert Daten, die sich mit dem bestehenden
COG-Pfad (Kacheln, Zuschnitt, Operatoren) sinnvoll darstellen und rechnen
lassen? Und was bedeutet Geländekorrektur dabei?

---

## 2. Kriterien

| # | Kriterium | Woher |
|---|---|---|
| K1 | Anonym, ohne Token, Konto, SAS oder Requester Pays (Metadaten **und** Assets) | `ENTSCHEIDUNGEN` §1; Checkliste Punkt 6 |
| K2 | Lizenz erlaubt Anzeige und Processing (B11), Attribution bekannt | `KLAERUNGEN` B11; Checkliste Punkt 4 |
| K3 | Geometrie: Pixel liegen ohne eigene SAR-Prozessierung an der richtigen Stelle | `architekturplan.md` 6.2, 6.3 |
| K4 | Radiometrie: Werte sind physikalisch (σ⁰/γ⁰) oder ohne Sondercode dahin zu bringen | DS-05; „kein datensatzspezifischer Code“ |
| K5 | Kachelbar: COG mit Übersichten, bekannte CRS | `adr/0006`; Checkliste Punkt 5, 8 |
| K6 | Abdeckung global, Archiv tief, neue Szenen zeitnah | `adr/0003` §4; `adr/0005` Regel II |
| K7 | Suchfelder der Quelle (Orbitrichtung, Polarisation, Modus, relativer Orbit) | DS-02 |
| K8 | Fassung je Asset für den Cache | `adr/0014` §3.1 |
| K9 | Coverage-Anbieter zuzuordnen | Checkliste Punkt 2; `adr/0004` |
| K10 | Quelle dauerhaft betrieben, Kosten trägt nicht die Plattform | Prinzip 11; `adr/0007` K9 |
| K11 | Grenzen unverändert: B8, B9, Modulgrenzen, keine neue Abhängigkeit | `CLAUDE.md`; `architekturplan.md` 3.1 |

---

## 3. Befunde je Kandidat

TODO
