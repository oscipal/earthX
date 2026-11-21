# Freigaben je Herausgeber

Je Quelle eine Datei `<source_id>.yaml` (`adr/0033` §6.2, L2; M5-20 Plan §9): eine Liste, je Zeile `publisher`
(genau der Wert aus dem Herausgeberfeld der Seed-Datei), `licenses` (die `license_ref`s aus `../terms.yaml`, die dieser
Herausgeber für seine Daten nutzen darf) und `approved_on`. Ein Fund wird nur gelistet, wenn jede seiner Lizenzangaben
eine Lizenz des Katalogs meint, die seinem Herausgeber bei dieser Quelle freigegeben ist; sonst wartet er
(`needs_rule`). Schreiben und mergen tut Otto; `license-checker` schlägt Zeilen vor.
