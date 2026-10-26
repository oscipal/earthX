# DS-00 — Paket „Datensatzabhängige Suche und Prozessierung“

**Stand:** 26.10.2026, beauftragt von Otto. DS-02, DS-03 und DS-06 liegen nach VP3 (UI-01, UI-02) und vor M5; **DS-04 und DS-05 (Sentinel-1) kommen erst mit oder nach M5** (Otto, 26.10.2026: neue Datensätze über den Ablauf aus M5). `projektplan.md` bekommt dazu eine Zeile (Nachtrag durch die nächste Doku-Aufgabe oder Otto).

| Aufgabe | Inhalt | Stufe | Voraussetzung |
|---|---|---|---|
| DS-01 | Quelle für Sentinel-1 (Vorlage) | C | erledigt: `adr/0018`, PR #200 |
| DS-02 | „Advanced search“ mit Filtern je Datensatz | B | UI-01g |
| DS-03 | Wolkenanteil in der AOI | B | DS-02 |
| DS-04 | Sentinel-1 anbinden (Earth Search GRD als Level-1, ggf. PC RTC) | A | `adr/0018` Fassung 2; **mit oder nach M5** |
| DS-05 | SAR-Operatoren und -Presets | B | DS-04, NM4-14; **mit oder nach M5** |
| DS-06 | Maske nach Werten eines Bandes | B | UI-01 |

**Grundsätze für alle DS-Aufgaben (Otto, 26.10.2026):**
- Unterschiede je Datensatz stehen als Daten in der Registry, nicht als Code je Datensatz.
- Was für einen Datensatz oder Layer nicht möglich ist, erscheint nicht (ausgeblendet, nicht ausgegraut).
