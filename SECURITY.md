# Security Policy

EarthX ist ein öffentliches Repository. **Sicherheitsrelevante Meldungen gehören
nie in ein öffentliches Issue, eine öffentliche Diskussion oder einen PR.**

## Eine Sicherheitslücke melden

Bitte nutze **GitHub Private Vulnerability Reporting**:

1. Im Repo auf den Tab **Security** gehen.
2. **Report a vulnerability** wählen.
3. Beschreibung, betroffene Komponente und Reproduktionsschritte eintragen —
   auch hier gilt: keine persönlichen Daten Dritter, keine echten Tokens oder
   Secrets im Klartext.

Die Meldung ist damit nur für Repo-Maintainer sichtbar, nicht öffentlich.

Falls Private Vulnerability Reporting für dieses Repo nicht verfügbar ist,
wende dich stattdessen direkt und nicht-öffentlich an die Maintainer (z. B.
über einen privaten Kanal außerhalb von GitHub) — nicht über ein Issue.

## Bekannte, bewusst befristete Ausnahme

Das im Code fest eingetragene OIDC-Client-Secret für die BIOMASS/MAAP-Anbindung
(`backend/app/config.py`) ist eine bekannte, bewusst in Kauf genommene Ausnahme
(siehe `CLAUDE.md`) und muss nicht erneut gemeldet werden. Die Ausnahme endet,
wenn der BIOMASS-Code entfernt wird.

## Umfang

Diese Policy gilt für den Code in diesem Repository. Für die Datenquellen, die
EarthX über `gateway` anbindet, ist die jeweilige externe Quelle zuständig.
