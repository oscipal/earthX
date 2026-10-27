# NM4-14 — Schnellrechnungen (Index-Knöpfe)

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 14 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Plan und Recherche, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach NM4-07 und NM4-10; nicht gleichzeitig mit NM4-20 (Panel). Höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-14 aus `docs/plans/querschnitt/nm4-14-index-knoepfe.md` aus.“

## 1. Anlass

`projektuebersicht.md` §8 sieht datensatzspezifische Presets auf Band math vor. Otto möchte an einem passenden Layer (etwa „Crop & merge to AOI“ bei Sentinel-2) Knöpfe für häufige Indizes.

## 2. Soll

- Knöpfe etwa für NDVI, NDWI, NDSI, NBR, EVI. Ein Klick erzeugt einen normalen Band-math-Schritt mit Vorschau; Start als Job wie gewohnt.
- **Kein zweiter Weg:** Die Knöpfe füllen nur das Rezept; Vorschau, Job, Cache, Runner und `recipe.json` bleiben dieselben.
- **Daten, nicht Code:** Presets stehen je Datensatz in der Registry (Name, Ausdruck, Wertebereich, Colormap-Vorgabe, Quelle der Formel). Nur Datensätze mit passenden Bändern zeigen sie. Kein datensatzspezifischer Code.

## 3. Im Plan klären (mit Optionen und Empfehlung)

- **Formeln mit Quelle** (etwa Awesome Spectral Indices, Montero et al. 2023, *Scientific Data*); Konstanten (EVI) mit Quelle.
- Welche Indizes zuerst; Ort der Knöpfe (Layer, Panel, beides; Abstimmung mit UI-01).
- Setzt ein Preset die Bänder (NM4-07) und den Ergebnisnamen (NM4-10, etwa `NDVI`)?
- Mosaik (NM4-04) und Kette mit `mask` („NDVI cloud-free“)?

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Preset erzeugt dasselbe Rezept wie der von Hand eingegebene Ausdruck; Datensatz ohne passende Bänder zeigt keinen Knopf; Formeln gegen Referenzwerte.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n) mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat, siehe Kopf des Backlogs).
- Vor „fertig“ ist main geholt.
