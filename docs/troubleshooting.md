# Fejlsøgning

Tilbage til [README](../README.md) | Se også [Drift og deployment](deployment.md)

Se også [Sikkerhed](security.md) for `SECRET_KEY`, HTTPS og generelle driftspunkter.

Denne side samler almindelige fejl og hurtige checks.

## Appen starter ikke

Kontroller:

```bash
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
```

Hvis det fejler, se den fulde stacktrace i terminalen eller via systemd logs i produktion.

## Login virker ikke

Tjek først om databasen er ny eller eksisterende.

Vigtigt:

- standardbrugeren `admin / admin123` oprettes kun hvis databasen er tom
- hvis der allerede findes brugere, bliver den ikke genoprettet

## Produktion ser anderledes ud end lokalt

Typiske årsager:

1. gammel CSS eller JS bliver serveret fra cache
2. produktion kører en ældre kodeversion
3. lokal og produktion bruger ikke samme database

Checks:

- genindlæs med hard refresh
- purge CDN eller reverse proxy cache
- kontroller at `/static/styles.css` er opdateret
- kontroller at det rigtige commit er deployed

## Tallene på dashboard matcher ikke lokalt

Det er ofte ikke en kodefejl.

Typiske årsager:

- lokal database er `data/data/app.db`
- produktion har en anden `app.db`
- produktion indeholder andre adresser, aftaler, lagerbevægelser eller beskeder

Bekræft ved at sammenligne databaser eller eksportere relevante data.

## CSS ændres ikke efter deploy

Hvis HTML ser ny ud, men layoutet er gammelt, er problemet ofte cache på statiske filer.

Mulige løsninger:

- purge cache i CDN eller reverse proxy
- genstart service og verificer filens indhold direkte
- indfør cache-busting på CSS og JS

## PDF eller links i breve er forkerte

Tjek `PUBLIC_BASE_URL`.

Hvis den er forkert eller mangler, kan:

- links i breve pege forkert
- QR-koder pege på forkert domæne
- preview og produktion opfører sig forskelligt

## Sessioner logger brugere ud uventet

Tjek `SECRET_KEY`.

Hvis `SECRET_KEY` ændres mellem deploys:

- eksisterende sessioner bliver ugyldige
- brugere skal logge ind igen

## Uploads eller fotos mangler

Kontroller at disse mapper findes og bevares ved deploy:

- `data/uploads/`
- `data/logs/`
- `data/data/`

Hvis filer er væk efter deploy, er `data/` sandsynligvis ikke persistent eller er blevet overskrevet.

## Planlægning giver ingen resultater

Tjek følgende:

- findes der arbejdsdage på den valgte dato
- findes der adresser som kan planlægges
- er adresser blokerede eller unavailable
- er der allerede planlagte aftaler den dag

Auto-planlægning kræver en dato med gyldige arbejdsdage.

## Alembic og database er ude af sync

Typisk symptom:

- Alembic fejler med fejl som `table already exists`
- databasen har allerede en ny tabel eller kolonne, men `alembic_version` er bagud

Det sker typisk hvis databasen er oprettet eller udvidet direkte fra modelkoden før migrationen er kørt.

Checks:

```bash
sqlite3 data/data/app.db "select version_num from alembic_version;"
sqlite3 data/data/app.db ".tables"
python -m alembic upgrade head
```

Hvis tabellen allerede findes:

- kontroller først at schemaet faktisk matcher migrationen
- gør derefter migrationen idempotent hvis det er en kendt lokal driftssituation
- kør `python -m alembic upgrade head` igen

I dette projekt er det normalt bedst at:

- undgå at slette lokal database unødigt
- gøre migrationen robust mod eksisterende tabel lokalt
- bruge `alembic_version` som sandhed for hvilke migrationer der mangler

Hvis lokal database er teststøj og ikke vigtig, kan en ren lokal DB stadig være den hurtigste løsning.

## Import fejler

Vanlige årsager:

- CSV mangler kolonner
- forkert encoding
- adresse findes ikke i systemet
- VVS-navn matcher ikke en bruger
- datoformat kan ikke parses

Brug fejlbeskeden i UI og kontroller importformatet omhyggeligt.

## Ny side giver 403 eller 404

Tjek først:

- om du er logget ind med korrekt rolle
- om route findes i koden
- om linket i navigationen peger rigtigt

Fejlhåndtering er server-renderet, så du kan som regel se status direkte i browseren.

## Nyttige kommandoer

```bash
git status
git log --oneline -n 10
journalctl -u meterreplace -f
curl -I "https://dit-domaene/static/styles.css"
```
