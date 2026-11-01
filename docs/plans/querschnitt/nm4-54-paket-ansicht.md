# NM4-54 — Paket Ansicht und Anheften (NM4-45, NM4-24, NM4-25, NM4-12, dazu gleiche Einstellungsbox)

**Stand:** 01.11.2026 (Teil 5 und Vermerk zu „Index“ ergänzt); 29.10.2026 von Otto beauftragt: kleine Aufgaben zusammenlegen, um Sessions und Konflikte zu sparen (`docs/plans/nach-m4-backlog.md`).
**Stufe A:** direkt umsetzen, ein Draft-PR für alle Teile.
**Modell:** Sonnet, Effort hoch (fünf Teile in einem Bereich).
**Start:** nach dem Merge von NM4-53 (alle Teile ändern die Ansicht bzw. ihre Leiste); seit #257, #264, #266 auf deren Stand aufbauen. Frontend-Aufgabe: höchstens zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-54 aus `docs/plans/querschnitt/nm4-54-paket-ansicht.md` aus.“

## Teile

| Reihenfolge | Teilaufgabe | Plan |
|---|---|---|
| 1 | NM4-12 Anheften ohne zweiten Klick | `querschnitt/nm4-12-anheften-ohne-zweiten-klick.md` |
| 2 | NM4-25 Quicklook nach „Crop & merge“ sofort zuschneiden | `querschnitt/nm4-25-quicklook-nach-zuschnitt.md` |
| 3 | NM4-24 Stapelung im Rückfall „Szene für Szene“ wie das Mosaik | `querschnitt/nm4-24-rueckfall-stapelung.md` |
| 4 | NM4-45 Einzelne Bänder in der Ansicht per Dropdown | `querschnitt/nm4-45-band-in-ansicht.md` |
| 5 | Gleiche Einstellungsbox für alle Layer (Otto, 01.11.2026) | unten |

**Zu Teil 4 (Otto, 31.10.2026):** Seit #264 hat die Ansicht ein eigenes Dropdown „Index“ (Schnellrechnung ohne Job). Mit NM4-45 gibt es **ein** Dropdown: oben „RGB“ (Vorgabe bei Sentinel-2), dann die Einzelbänder, nach einer Trennlinie die Presets (NDVI, NDWI …). Das eigene Dropdown „Index“ entfällt; Verhalten der Presets (ohne Job, Hinweis „Zoom in to compute …“, gesperrt am angehefteten Index-Layer) bleibt wie in #264.

**Teil 5 – Gleiche Einstellungsbox (Otto, 01.11.2026, wörtlich):** „in der layer ansicht sind die boxen noch immer unterschiedlich je nachdem ob ich einen job layer offen habe oder einen crop to AOI layer. außerdem ändert sich die form der box je nach ausgewähltem band.“
- Eine Einstellungsbox für Ergebnis-Layer (Job), angeheftete Ansicht („Crop to AOI“, „Crop & merge to AOI“) und die Ansicht der Suche: dasselbe Bauteil, gleiche Breite, gleiche Zeilen in der Reihenfolge aus NM4-65 Teil 6 (Band · vmin · vmax · Colormap, dazu Opacity und Knopfzeile).
- Die Form ändert sich nicht mit dem gewählten Band: Ein Feld, das für die Wahl gerade nicht gilt (z. B. Colormap bei RGB), behält seinen Platz und ist gesperrt mit Grund im Tooltip, statt zu verschwinden. Felder, die es für die Art des Layers nie gibt, dürfen fehlen; die Session listet im PR je Layer-Art, welche Zeilen erscheinen (Tabelle), und hält die Höhe gleich, wo es geht.
- Test: Box-Maße für Job-Layer, angeheftete Ansicht und Ansicht der Suche bei RGB, Einzelband und Index (Browser, beide Themen, 1280 und 360 px).

**Nicht hier:** Der Fehler „Apply“ bei reiner Änderung der Farbskala im Processing-Panel (Otto, 01.11.2026) geht an NM4-11b (#269).

Die Regeln für die Ansicht aus #211, #221, #234 und NM4-53 (Show/Hide, Anhak-Reihenfolge, feste Plätze der Leisten, „Apply“/„Save“, Zeitschritte) gelten weiter; jede Teilaufgabe prüft, dass sie unverändert bleiben.

## Grenzen

- Was in den einzelnen Plänen steht, gilt unverändert; dieser Plan legt nur fest, dass sie zusammen in einer Session und einem Draft-PR umgesetzt werden.
- Je Teilaufgabe ein eigener Commit (Nachricht nennt die Nummer), damit Otto sie getrennt prüfen kann.
- Oberflächentexte nur Englisch; wenig Text, Erklärungen hinter (i) bzw. im Tooltip; bestehende gesperrte Elemente nicht entfernen (NM4-30 entfällt, Otto 31.10.2026).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Nachträge in ADRs heißen nach der Aufgabe („Nachtrag NM4-xx“).
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## Abnahme

- Die Abnahme jedes Teilplans ist erfüllt (Tests mit Gegenprobe, Browserprüfung in Hell/Dunkel und schmalem Fenster).
- Eine gemeinsame Prüfanleitung für Otto im PR, gegliedert nach Teilaufgabe.
- Alle vier Pflicht-Checks grün.
- Je Teilaufgabe eine Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.
