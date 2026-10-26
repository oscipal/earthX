# NM4-33 — Originale mit einem Klick herunterladen

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 33 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Recherche und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach UI-01; Frontend-Aufgabe (höchstens zwei Frontend-Sessions gleichzeitig), höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-33 aus `docs/plans/querschnitt/nm4-33-originale-ein-klick.md` aus.“

## 1. Anlass

„Download originals“ (M4-11b-2) liefert heute eine Liste von Links zur Quelle mit Attributionskopf. Otto (26.10.2026): „Ich will auf jeden Fall einfach einen Download-Button drücken können ohne extra Steps.“ Offen im Log ist zudem „Originale als ZIP über die Plattform“ (Bandbreite, Kosten, nicht fortsetzbar; M4-11b-2) – diese Aufgabe entscheidet das mit.

## 2. Soll

- Ein Klick auf „Download originals“ lädt die Originaldateien ohne weitere Schritte (keine Linkliste, die man einzeln anklicken muss).
- Möglichst kein Byte der Originale durch das eigene Backend (`architekturplan.md` 6.4); Attribution und Lizenzhinweis gehen mit (Datei im Download oder vorab sichtbar).
- Gilt für alle Datensätze; Quellen mit anonymem Token (`adr/0018`, falls Planetary Computer kommt) eingeschlossen.

## 3. Im Plan klären (mit Optionen und Empfehlung)

- **Wege, mit Quellen und Messung:** (a) mehrere direkte Downloads nacheinander (Browser fragt einmal); (b) ZIP über die Plattform (gestreamt, wie Job-ZIP, mit Grenzen); (c) ZIP im Browser: der Browser lädt direkt von der Quelle und packt beim Speichern (Streaming auf die Platte, Speicherbedarf, Abbruch/Fortsetzen); Voraussetzung CORS der Quelle – je Datensatz messen.
- **Quellen mit Token:** Holt der Browser beim Klick selbst ein anonymes Token direkt beim Anbieter (eigene IP, kein Plattform-Token im Browser), oder signiert das Backend? IP-Bindung der Signatur beachten (`adr/0018` N1).
- Große Downloads: Grenze, Fortschritt, Fortsetzen; Verhalten auf dem Handy.
- Neue Abhängigkeit (etwa eine kleine ZIP-Streaming-Bibliothek) nur mit Ottos Freigabe.

## 4. Grenzen

- Keine AOI, Kennungen oder signierten URLs in Logs.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: ein Klick startet den Download (Playwright im echten Browser), Attribution im Ergebnis, Verhalten ohne CORS (Rückfall), mehrere Dateien.
- Nachtrag `architekturplan.md` 6.4 bzw. Log-Zeile zu Punkt „Originale als ZIP“.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.
