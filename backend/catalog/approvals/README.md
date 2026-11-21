# Freigaben der Läufe

Je Bericht einer Quelle ein Paar Dateien `<Tag>-<source_id>.yaml` und `.md` (`adr/0033` §8; M5-20 Plan §12),
geschrieben von `python -m earthx.discovery.report <source_id>` über das Skript `scripts/harvest-report.ps1` bzw.
`.sh`. Die `.md` ist der Lauf-Bericht mit Zahlen, Warteliste, Stichprobe, verborgenen Nicht-Geodaten und Dubletten.
In der `.yaml` setzt Otto je Eintrag der Stichprobe `ok: true` oder `ok: false`, dann `decision` (`approved` oder
`rejected`) und `decided_on`; der Merge ist die Freigabe. `catalog-load` macht den Stapel sichtbar, wenn die Datei
`approved` ist und ihr Fingerabdruck dem Stapel in der Datenbank gleicht. `excluded_rules` lässt die Einträge einzelner
Lizenzregeln draußen, `revoked_on` nimmt die Freigabe zurück. Nie ein Name, eine Adresse oder der Wortlaut einer
Anfrage: das Repo ist öffentlich.
