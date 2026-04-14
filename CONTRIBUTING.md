# Bidrag

Tilbage til [README](README.md)

Tak fordi du vil bidrage til MeterReplace.

## Mål

Projektet prioriterer:

- enkle flows
- læsbar kode
- minimale, korrekte ændringer
- dokumentation der matcher den faktiske kode

## Lokal opsætning

```bash
git clone https://github.com/Rmelin/MeterReplace.git
cd MeterReplace

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
```

## Før du laver en større ændring

Det er en god ide at oprette et issue eller beskrive retningen først, hvis ændringen er stor.

Eksempler:

- nye hovedflows
- større UI-omlægninger
- databasedesign
- importformat-ændringer
- rolle- eller statuslogik

## Retningslinjer for ændringer

- hold ændringer så små som muligt
- bevar eksisterende flows, medmindre der er en klar grund til at ændre dem
- undgå unødig abstraktion
- opdater dokumentation sammen med kodeændringer
- undgå at indføre breaking changes uden tydelig begrundelse

## Dokumentation

Hvis du ændrer adfærd eller drift, bør de relevante docs opdateres i samme PR:

- [Drift og deployment](docs/deployment.md)
- [Sikkerhed](docs/security.md)
- [Statusmodel](docs/status-model.md)
- [Admin-flow](docs/admin-flow.md)
- [Fejlsøgning](docs/troubleshooting.md)

## Pull request checklist

Før du opretter en PR, bør du som minimum kontrollere:

1. at ændringen virker lokalt
2. at du ikke har introduceret åbenlyse regressions
3. at dokumentation er opdateret hvis flow, deployment eller statuslogik er ændret
4. at commit-beskrivelsen forklarer hvorfor ændringen er lavet

## Kode og stil

Der er ikke et tungt framework for arkitektur eller komponentregler. Følg den eksisterende kodebase.

Praktisk betyder det:

- FastAPI routes er server-renderede og direkte
- logik ligger ofte tæt på route-niveau
- HTML templates og CSS er en vigtig del af appens adfærd

Foretræk:

- tydelige navne
- direkte flow
- få nye lag og helpers

## Rapportering af fejl

En god fejlrapport indeholder:

- hvad du gjorde
- hvad du forventede
- hvad der faktisk skete
- eventuelle skærmbilleder
- relevante logs eller fejlbeskeder

## Forslag til features

Beskriv gerne:

- hvilket problem der skal løses
- hvem der bruger funktionen
- hvilke sider eller flows der påvirkes
- om der er behov for migration eller ny dokumentation
