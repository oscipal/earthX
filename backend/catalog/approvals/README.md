# Freigaben der Läufe

Je Bericht einer Quelle ein Paar Dateien `<Tag>-<source_id>.yaml` und `.md` (`adr/0033` §8; M5-20 Plan §12),
geschrieben von `python -m earthx.discovery.report <source_id>` über das Skript `scripts/harvest-report.ps1` bzw.
`.sh`. Die `.md` ist der Lauf-Bericht mit Zahlen, Warteliste, Stichprobe, verborgenen Nicht-Geodaten und Dubletten.
In der `.yaml` setzt Otto je Eintrag der Stichprobe `ok: true` oder `ok: false`, dann `decision` (`approved` oder
`rejected`) und `decided_on`; der Merge ist die Freigabe. `catalog-load` macht den Stapel sichtbar, wenn die Datei
`approved` ist und ihr Fingerabdruck dem Stapel in der Datenbank gleicht. `excluded_rules` lässt die Einträge einzelner
Lizenzregeln draußen, `revoked_on` nimmt die Freigabe zurück. Nie ein Name, eine Adresse oder der Wortlaut einer
Anfrage: das Repo ist öffentlich.

Seit M5-67 (Otto, 24.11.2026) entscheidet ein Lauf von `scripts/harvest-cycle.ps1` nach festen Regeln
(`backend/catalog/approval_rules.yaml`): `decision: approved` mit `decided_by: rules`, je Eintrag der Stichprobe die
automatische Linkprüfung in `check`; sonst bleibt die Datei `pending` und Otto kann sie wie bisher von Hand freigeben.
Sichtbar werden in beiden Fällen nur Einträge, deren eigener Link die Prüfung bestanden hat. `excluded_entries` sind
Einträge mit Warnzeichen (`backend/catalog/flags.yaml`); sie warten.
