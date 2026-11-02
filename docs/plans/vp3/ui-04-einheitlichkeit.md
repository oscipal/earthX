# UI-04 — Einheitlichkeit: Stil, Namen, Bedienung

**Stand:** 01.11.2026, beauftragt von Otto (Backlog-Punkt 73 in `docs/plans/nach-m4-backlog.md`). Nimmt das Paket NM4-56 (Zahlenformat NM4-21, weniger Text NM4-22, schmale Fenster aus Punkt 58) in sich auf.
**Stufe B:** Erst kommt die Bestandsaufnahme mit Vorschlägen im Draft-PR, Otto gibt frei, dann setzt dieselbe Session **Teil 1** um. Weitere Teile bekommen je eine neue Session und einen eigenen PR.
**Modell:** Opus für Bestandsaufnahme und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach dem Merge aller Teile von UI-03; als letzte Frontend-Aufgabe vor M5, **allein** (keine andere Frontend-Session gleichzeitig, die Teile gehen quer durch die ganze Oberfläche).
**Startsatz:** „Führe Aufgabe UI-04 aus `docs/plans/vp3/ui-04-einheitlichkeit.md` aus.“

## 1. Wunsch (Otto, 01.11.2026, wörtlich)

> Ich will hauptsächlich die verwendeten styles und namen checken und auf consistency überprüfen, ähnlich sachen sollen den gleichen style haben; gleiche sachen sollen gleich heissen und gleich verwendbar sein (zB keine verschiedenen symbole oder wege zum exiten) usw. Es soll einfach alles einheitlich sein und nicht ständig unterschiedlich aussehen.

## 2. Soll

1. **Gleiches sieht gleich aus:** Ähnliche Bedienelemente nutzen dasselbe Bauteil und dieselben Gestaltungswerte (Tokens aus UI-03): Knöpfe, Schalter, Segment-Umschalter, Dropdowns, Zahlfelder, Chips, Abzeichen („Preview“, „Temporary“), Hinweise, Fehlermeldungen, Listenzeilen, Gruppenköpfe, Leisten, Seitenleisten, Dialoge, Tooltips und (i).
2. **Gleiches heißt gleich:** Ein Begriff je Sache in der ganzen Oberfläche (Knopftexte, Überschriften, Tooltips, aria-Labels, Fehlermeldungen); gleiche Schreibweise (Groß-/Kleinschreibung, Ellipse „…“, Einheiten, Zahlen nach NM4-21).
3. **Gleiches bedient sich gleich:** ein Weg zum Schließen (kleines rotes „x“ über `CloseButton.tsx`, dazu Esc, wo es ein Fenster oder eine Leiste ist), ein Weg zum Übernehmen und Speichern („Apply“, „Apply to all“, „Save“ nach den Regeln aus #257/#272), gleiche Sperrregel (gesperrt mit Grund im Tooltip), gleiche Symbole für gleiche Aktionen (Download, Auge, Ziehgriff, Löschen, Umbenennen, Process ⚙, Menü …).
4. **Bleibt dauerhaft so:** Ein kurzer Leitfaden `docs/ui/leitfaden.md` (Begriffe mit Bedeutung, Bauteile, Symbole, Regeln für Texte, Sperren, Schließen, Speichern) und automatische Prüfungen, die Rückfälle finden (z. B. Test: kein Schließen-Knopf außer `CloseButton`; keine festen Farb- oder Abstandswerte außerhalb der Tokens; Begriffsliste gegen die Oberflächentexte). Künftige Pläne verweisen auf den Leitfaden.
5. **Aus NM4-56:** Zahlenformat (NM4-21), weniger Text mit (i) (NM4-22), schmale Fenster (Punkt 58: Toolbar bei 320 px, verdeckte Statusleiste bei 360 px, überragende Statusmeldung).

## 3. Vorgehen

1. **Bestandsaufnahme** über die ganze Oberfläche (Suche, Advanced search, Ergebnisliste, Auswahl- und Zeitleiste, Ansicht, Seitenleiste, Layer-Manager, Processing-Panel, Processing-Manager, Dialoge, Control-Menü, Kopfzeile, Statusleiste): Tabelle im PR mit Stelle, heute (Bauteil, Text, Symbol, Verhalten), Abweichung, Vorschlag. Im echten Browser erhoben (Hell/Dunkel, 1280 und 360 px), Bilder nicht ins Repo.
2. **Begriffsliste** als Vorschlag: je Begriff die Stellen, an denen heute andere Wörter stehen, und der vorgeschlagene eine Begriff.
3. **Schnitt** in Teile (z. B. Teil 1 Leitfaden, Begriffe und Schließen/Speichern; Teil 2 Bauteile und Tokens; Teil 3 Zahlenformat, Text, schmale Fenster), je mit Umfang.

## 4. Grenzen

- Nur Frontend. Keine neue Abhängigkeit ohne Frage an Otto (z. B. ein Stil-Linter nur mit Freigabe).
- **Keine Funktionen entfernen oder ausblenden** (Otto, 31.10.2026; NM4-30 entfällt); gesperrte Elemente bleiben gesperrt mit Grund.
- Entscheidungen Ottos aus den bisherigen PRs gelten (u. a. „Apply to all“ in der Ansicht, „Save“ am Layer, „Temporary“, „Search results“, „Filter within AOI only“, rotes „x“). Weicht der Vorschlag davon ab, steht er als Frage an Otto im PR.
- Oberflächentexte nur Englisch; wenig Text, Erklärungen hinter (i) bzw. im Tooltip.
- Keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Nachträge heißen nach der Aufgabe („Nachtrag UI-04“). Bilder nicht ins Repo.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Bestandsaufnahme, Begriffsliste und Schnitt im Draft-PR; Otto gibt frei.
- Teil 1 danach in derselben Session: Tests mit Gegenprobe (inkl. der neuen Prüfungen gegen Rückfälle), Browserprüfung (Hell/Dunkel, 1280 und 360 px), Prüfanleitung für Otto; berührte Browser-Skripte nachgezogen.
- Alle vier Pflicht-Checks grün; Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.
