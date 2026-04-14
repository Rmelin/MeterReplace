# MeterReplace

MeterReplace er en selvhostet webapplikation til planlægning, udførsel og dokumentation af vandmålerudskiftninger.

Applikationen samler adresser, arbejdsdage, VVS-opgaver, breve, beboersvar, fotos og lager i et system.

## Hovedfunktioner

- admin-dashboard med statusoverblik
- adresseoversigt og kortvisning
- auto-planlægning med preview og commit
- manuel planlægning
- brevskabeloner, PDF og beboerlink
- import af afsluttede/skiftede sager
- foto-upload og opgavestyring for VVS
- lagerstyring og beskeder fra beboere

## Hurtig start

```bash
git clone https://github.com/Rmelin/MeterReplace.git
cd MeterReplace

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --reload-dir app --host 0.0.0.0 --port 8000
```

Åbn derefter `http://localhost:8000`.

Hvis databasen er tom ved første opstart, oprettes en standard admin-bruger automatisk:

- brugernavn: `admin`
- adgangskode: `admin123`

## Dokumentation

- [Drift og deployment](docs/deployment.md)
- [Sikkerhed](docs/security.md)
- [Statusmodel](docs/status-model.md)
- [Admin-flow](docs/admin-flow.md)
- [Fejlsøgning](docs/troubleshooting.md)
- [Bidrag](CONTRIBUTING.md)

## Teknologi

- FastAPI
- Jinja2 templates
- SQLAlchemy
- SQLite
- Server-renderet HTML, CSS og JavaScript
- WeasyPrint til PDF

## Roller

- `admin`
- `vvs`
- `user`

## Vigtige noter

- databasefilen ligger som standard i `data/data/app.db`
- uploads ligger i `data/uploads/`
- statiske filer serveres fra `/static`
- uploads serveres fra `/upload`

## Drift

De vigtigste miljøvariabler er:

```env
SECRET_KEY=skift-denne-til-en-lang-tilfaeldig-vaerdi
PUBLIC_BASE_URL=https://dit-domaene
```

Se [docs/deployment.md](docs/deployment.md) for produktionssetup.
